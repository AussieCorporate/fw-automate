import time
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError
from flatwhite.db import insert_signal, get_current_week_iso
from flatwhite.auth.cookie_manager import get_google_cookies, invalidate_cookies
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"
_RETRY_WAITS = [300, 600, 1200]


def pull_resume_anxiety() -> float:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    gt_config = config["google_trends"]
    keywords = gt_config["keyword_groups"]["resume_anxiety"]

    # Fetch Trends data with retry
    raw_avg = 0.0
    for attempt, wait in enumerate(_RETRY_WAITS + [None]):
        try:
            cookies = get_google_cookies()
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            pt = TrendReq(hl="en-AU", tz=600, requests_args={"headers": {"Cookie": cookie_str}})
            pt.build_payload(keywords, cat=0, timeframe=gt_config["timeframe"], geo=gt_config["geo"])
            df = pt.interest_over_time()
            if df.empty:
                raw_avg = 0.0
                break
            last_7d = df.tail(7) if len(df) > 30 else df
            scores = [float(last_7d[kw].mean()) for kw in keywords if kw in last_7d.columns]
            raw_avg = sum(scores) / len(scores) if scores else 0.0
            break
        except TooManyRequestsError:
            if wait is None:
                raise
            print(f"  ⚠ resume_anxiety 429 (attempt {attempt + 1}/{len(_RETRY_WAITS)}). Retrying in {wait // 60} min...")
            invalidate_cookies()
            time.sleep(wait)

    # Trip wire scoring: silent at baseline, fires when spiking
    if raw_avg <= 5.0:
        normalised = 50.0  # Below detection threshold — neutral
    else:
        normalised = max(0.0, 50.0 - (raw_avg / 2.0))  # Higher searches = lower score

    week_iso = get_current_week_iso()
    insert_signal(
        signal_name="resume_anxiety",
        lane="pulse",
        area="labour_market",
        raw_value=round(raw_avg, 2),
        normalised_score=round(normalised, 2),
        source_weight=1.0,
        week_iso=week_iso,
    )
    time.sleep(gt_config["sleep_between_calls_seconds"])
    return normalised
