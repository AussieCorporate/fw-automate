import time
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError
from flatwhite.db import insert_signal, get_current_week_iso, get_recent_signals
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid
from flatwhite.auth.cookie_manager import get_google_cookies, invalidate_cookies
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

# Retry config: waits in seconds between attempts (5 min, 10 min, 20 min)
_RETRY_WAITS = [300, 600, 1200]

def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

def _make_pytrends() -> TrendReq:
    """Build a TrendReq session authenticated with fresh Google cookies."""
    cookies = get_google_cookies()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return TrendReq(
        hl="en-AU",
        tz=600,
        requests_args={"headers": {"Cookie": cookie_str}},
    )

def _get_keyword_group_score(pytrends: TrendReq, keywords: list[str], geo: str, timeframe: str) -> float:
    pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo)
    df = pytrends.interest_over_time()
    if df.empty:
        return 50.0
    # For multi-month timeframes (daily data), use only the last 7 days
    # so the score reflects the current week against a stable 3-month baseline
    if len(df) > 30:
        df = df.tail(7)
    scores = []
    for kw in keywords:
        if kw in df.columns:
            scores.append(float(df[kw].mean()))
    if not scores:
        return 50.0
    return sum(scores) / len(scores)

def _call_with_retry(keywords: list[str], geo: str, timeframe: str) -> float:
    """
    Call Google Trends with automatic retry on 429.
    On each 429: invalidate cached cookies, fetch fresh ones via Playwright, then retry.
    Raises after all retries exhausted.
    """
    for attempt, wait in enumerate(_RETRY_WAITS + [None]):
        try:
            pytrends = _make_pytrends()
            return _get_keyword_group_score(pytrends, keywords, geo, timeframe)
        except TooManyRequestsError:
            if wait is None:
                raise
            print(f"  ⚠ Google Trends 429 (attempt {attempt + 1}/{len(_RETRY_WAITS)}). "
                  f"Refreshing cookies and retrying in {wait // 60} min...")
            invalidate_cookies()
            time.sleep(wait)
    raise RuntimeError("Google Trends retry loop exited without returning or raising")

def pull_job_anxiety() -> float:
    config = _load_config()
    gt_config = config["google_trends"]
    score = _call_with_retry(
        gt_config["keyword_groups"]["job_anxiety"],
        gt_config["geo"],
        gt_config["timeframe"],
    )
    week_iso = get_current_week_iso()

    recent = get_recent_signals("job_anxiety", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = config["signal_reference_ranges"]["signals"]["job_anxiety"]
    normalised, source_weight = normalise_hybrid(
        raw_value=score,
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    insert_signal(
        signal_name="job_anxiety",
        lane="pulse",
        area="labour_market",
        raw_value=score,
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )
    time.sleep(gt_config["sleep_between_calls_seconds"])
    return normalised

def pull_career_mobility() -> float:
    config = _load_config()
    gt_config = config["google_trends"]
    score = _call_with_retry(
        gt_config["keyword_groups"]["career_mobility"],
        gt_config["geo"],
        gt_config["timeframe"],
    )
    week_iso = get_current_week_iso()

    recent = get_recent_signals("career_mobility", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = config["signal_reference_ranges"]["signals"]["career_mobility"]
    normalised, source_weight = normalise_hybrid(
        raw_value=score,
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    insert_signal(
        signal_name="career_mobility",
        lane="pulse",
        area="labour_market",
        raw_value=score,
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )
    time.sleep(gt_config["sleep_between_calls_seconds"])
    return normalised

def pull_contractor_proxy() -> float:
    config = _load_config()
    gt_config = config["google_trends"]
    positive_score = _call_with_retry(
        gt_config["keyword_groups"]["contractor_proxy_positive"],
        gt_config["geo"],
        gt_config["timeframe"],
    )
    time.sleep(gt_config["sleep_between_calls_seconds"])
    negative_score = _call_with_retry(
        gt_config["keyword_groups"]["contractor_proxy_negative"],
        gt_config["geo"],
        gt_config["timeframe"],
    )
    raw = positive_score - negative_score
    # Scale difference: ±50 maps to 0-100 (50 = neutral).
    # Google Trends 0-100 scale with AU niche keywords gives realistic range ±50.
    normalised = max(0.0, min(100.0, 50.0 + (raw / 50.0) * 50.0))
    week_iso = get_current_week_iso()
    insert_signal(
        signal_name="contractor_proxy",
        lane="pulse",
        area="corporate_stress",
        raw_value=raw,
        normalised_score=normalised,
        source_weight=1.0,
        week_iso=week_iso,
    )
    time.sleep(gt_config["sleep_between_calls_seconds"])
    return normalised

def pull_all_google_trends() -> dict[str, float]:
    return {
        "job_anxiety": pull_job_anxiety(),
        "career_mobility": pull_career_mobility(),
        "contractor_proxy": pull_contractor_proxy(),
    }
