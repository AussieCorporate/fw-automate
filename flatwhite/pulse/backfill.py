"""Backfill historical pulse signals and pulse_history.

Usage: flatwhite backfill --weeks 12
"""
from datetime import date, timedelta
from flatwhite.db import get_connection, insert_signal, init_db


def _get_backfill_weeks(weeks: int) -> list[str]:
    """Generate ISO week strings for the last N weeks, oldest first.

    Skips any week that already has signal data in the database.
    """
    today = date.today()
    all_weeks: list[str] = []
    for i in range(weeks, 0, -1):
        d = today - timedelta(weeks=i)
        iso = d.isocalendar()
        week_iso = f"{iso[0]}-W{iso[1]:02d}"
        all_weeks.append(week_iso)

    # Filter out weeks that already have a full set of signal data (>= 10 signals).
    # Weeks with only 1-2 partial signals from previous ingests should still be backfilled.
    conn = get_connection()
    rows = conn.execute(
        """SELECT week_iso, COUNT(*) as cnt FROM signals
        WHERE lane = 'pulse'
        GROUP BY week_iso
        HAVING cnt >= 10"""
    ).fetchall()
    conn.close()
    existing_set = {r["week_iso"] for r in rows}

    backfill_weeks = [w for w in all_weeks if w not in existing_set]
    return backfill_weeks


# --- Neutral placeholders for non-backfillable signals ---

_NEUTRAL_SIGNALS = [
    ("market_hiring", "labour_market"),
    ("employer_hiring_breadth", "labour_market"),
    ("employer_req_freshness", "labour_market"),
    ("employer_net_delta", "labour_market"),
    ("salary_pressure", "labour_market"),
    ("reddit_topic_velocity", "corporate_stress"),
    ("auslaw_velocity", "corporate_stress"),
]


def _backfill_neutral_placeholders(week_list: list[str]) -> None:
    """Insert score=50.0, source_weight=0.3 for signals without historical sources."""
    for week_iso in week_list:
        for signal_name, area in _NEUTRAL_SIGNALS:
            insert_signal(
                signal_name=signal_name,
                lane="pulse",
                area=area,
                raw_value=0.0,
                normalised_score=50.0,
                source_weight=0.3,
                week_iso=week_iso,
            )
    print(f"  Neutral placeholders: {len(week_list) * len(_NEUTRAL_SIGNALS)} rows inserted")


def _backfill_asx(week_list: list[str]) -> None:
    """Pull ~120 days of XJO data from yfinance, compute per-week volatility + momentum."""
    import yfinance as yf

    ticker = yf.Ticker("^AXJO")
    hist = ticker.history(period="120d")

    if hist.empty or len(hist) < 25:
        print("  ⚠ ASX data insufficient — inserting neutral for all weeks")
        for week_iso in week_list:
            insert_signal("asx_volatility", "pulse", "economic", 0.0, 50.0, 0.3, week_iso)
            insert_signal("asx_momentum", "pulse", "economic", 0.0, 50.0, 0.3, week_iso)
        return

    # Add ISO week column to the dataframe
    hist["week_iso"] = hist.index.map(
        lambda d: f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
    )

    daily_returns = hist["Close"].pct_change().dropna()

    vol_count = 0
    mom_count = 0

    for week_iso in week_list:
        week_data = hist[hist["week_iso"] == week_iso]
        if week_data.empty:
            insert_signal("asx_volatility", "pulse", "economic", 0.0, 50.0, 0.3, week_iso)
            insert_signal("asx_momentum", "pulse", "economic", 0.0, 50.0, 0.3, week_iso)
            continue

        # --- Volatility: 5-day std of returns, percentile-inverted ---
        last_idx = hist.index.get_loc(week_data.index[-1])
        if last_idx >= 5:
            week_returns = daily_returns.iloc[max(0, last_idx - 4):last_idx + 1]
            volatility_5d = float(week_returns.std()) * 100.0

            rolling_vols = daily_returns.rolling(5).std().dropna() * 100.0
            up_to_week = rolling_vols.iloc[:last_idx + 1]
            if len(up_to_week) > 0:
                percentile = float((up_to_week < volatility_5d).mean()) * 100.0
            else:
                percentile = 50.0

            vol_norm = max(0.0, min(100.0, 100.0 - percentile))
            insert_signal("asx_volatility", "pulse", "economic", volatility_5d, vol_norm, 1.0, week_iso)
            vol_count += 1
        else:
            insert_signal("asx_volatility", "pulse", "economic", 0.0, 50.0, 0.3, week_iso)

        # --- Momentum: 20-day return %, scaled ---
        if last_idx >= 20:
            current_price = float(hist["Close"].iloc[last_idx])
            price_20d_ago = float(hist["Close"].iloc[last_idx - 20])
            return_pct = ((current_price - price_20d_ago) / price_20d_ago) * 100.0
            mom_norm = max(0.0, min(100.0, 50.0 + (return_pct * 5.0)))
            insert_signal("asx_momentum", "pulse", "economic", return_pct, mom_norm, 1.0, week_iso)
            mom_count += 1
        else:
            insert_signal("asx_momentum", "pulse", "economic", 0.0, 50.0, 0.3, week_iso)

    print(f"  ASX volatility: {vol_count}/{len(week_list)} weeks with real data")
    print(f"  ASX momentum: {mom_count}/{len(week_list)} weeks with real data")


def _backfill_consumer_confidence(week_list: list[str]) -> None:
    """Scrape Roy Morgan historical table and map weekly CCI values to ISO weeks."""
    from bs4 import BeautifulSoup
    from flatwhite.utils.http import fetch_url
    from datetime import datetime

    ROYMORGAN_URL = "https://www.roymorgan.com/morgan-poll/consumer-confidence-anz-roy-morgan-australian-cc-summary/"
    FLOOR = 65.0
    CEILING = 95.0

    try:
        html = fetch_url(ROYMORGAN_URL, delay_seconds=2.0)
    except Exception as e:
        print(f"  ⚠ Consumer confidence scrape failed ({e}) — inserting neutral")
        for week_iso in week_list:
            insert_signal("consumer_confidence", "pulse", "economic", 85.0, 66.7, 0.3, week_iso)
        return

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    # Parse all weekly values from all tables (current year + previous years)
    weekly_values: list[tuple[str, float]] = []  # (date_text, value)
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) >= 3 and cells[2] and cells[2] != "WEEKLY AVERAGE":
                try:
                    value = float(cells[2])
                    date_text = cells[0].strip() if cells[0] else ""
                    weekly_values.append((date_text, value))
                except ValueError:
                    pass

    if not weekly_values:
        print("  ⚠ No values parsed from Roy Morgan — inserting neutral")
        for week_iso in week_list:
            insert_signal("consumer_confidence", "pulse", "economic", 85.0, 66.7, 0.3, week_iso)
        return

    # Map parsed values to ISO weeks by date
    value_by_week: dict[str, float] = {}
    for date_text, value in weekly_values:
        parsed_date = None
        for fmt in ["%d/%m/%Y", "%d %B %Y", "%d %b %Y"]:
            try:
                parsed_date = datetime.strptime(date_text, fmt).date()
                break
            except ValueError:
                continue
        if parsed_date is None and "ending" in date_text.lower():
            date_part = date_text.lower().replace("week ending", "").strip()
            for fmt in ["%d %B %Y", "%d %b %Y", "%d/%m/%Y"]:
                try:
                    parsed_date = datetime.strptime(date_part, fmt).date()
                    break
                except ValueError:
                    continue

        if parsed_date:
            iso = parsed_date.isocalendar()
            week_iso = f"{iso[0]}-W{iso[1]:02d}"
            value_by_week[week_iso] = value

    count = 0
    for week_iso in week_list:
        if week_iso in value_by_week:
            raw = value_by_week[week_iso]
            normalised = max(0.0, min(100.0, ((raw - FLOOR) / (CEILING - FLOOR)) * 100.0))
            insert_signal("consumer_confidence", "pulse", "economic", raw, normalised, 1.0, week_iso)
            count += 1
        else:
            closest_value = None
            for vw, val in sorted(value_by_week.items(), reverse=True):
                if vw <= week_iso:
                    closest_value = val
                    break
            if closest_value is None and value_by_week:
                closest_value = list(value_by_week.values())[-1]

            if closest_value:
                raw = closest_value
                normalised = max(0.0, min(100.0, ((raw - FLOOR) / (CEILING - FLOOR)) * 100.0))
                insert_signal("consumer_confidence", "pulse", "economic", raw, normalised, 0.7, week_iso)
                count += 1
            else:
                insert_signal("consumer_confidence", "pulse", "economic", 85.0, 66.7, 0.3, week_iso)

    print(f"  Consumer confidence: {count}/{len(week_list)} weeks populated")


def _backfill_google_trends(week_list: list[str]) -> None:
    """Pull Google Trends data for all keyword groups and slice into weekly signals.

    Makes 6 API calls (one per keyword group), each returning ~90 days of daily data.
    Slices daily data into ISO weeks and applies the same normalisation as live collectors.
    """
    import time
    import pandas as pd
    from pytrends.request import TrendReq
    from pytrends.exceptions import TooManyRequestsError
    from flatwhite.auth.cookie_manager import get_google_cookies, invalidate_cookies
    import yaml
    from pathlib import Path

    CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    gt_config = config["google_trends"]
    sleep_secs = gt_config["sleep_between_calls_seconds"]
    retry_waits = [300, 600, 1200]

    def _fetch_trends(keywords: list[str]) -> pd.DataFrame:
        """Fetch Google Trends data with retry logic. Returns daily DataFrame."""
        for attempt, wait in enumerate(retry_waits + [None]):
            try:
                cookies = get_google_cookies()
                cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                pt = TrendReq(
                    hl="en-AU", tz=600,
                    requests_args={"headers": {"Cookie": cookie_str}},
                )
                pt.build_payload(keywords, cat=0, timeframe=gt_config["timeframe"], geo=gt_config["geo"])
                df = pt.interest_over_time()
                return df
            except TooManyRequestsError:
                if wait is None:
                    raise
                print(f"    ⚠ 429 (attempt {attempt + 1}/{len(retry_waits)}). Retrying in {wait // 60} min...")
                invalidate_cookies()
                time.sleep(wait)
        return pd.DataFrame()

    def _slice_weekly(df: pd.DataFrame, keywords: list[str]) -> dict[str, float]:
        """Slice daily Trends data into ISO weeks. Returns {week_iso: avg_score}."""
        if df.empty:
            return {}
        df = df.copy()
        df["week_iso"] = df.index.map(
            lambda d: f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        )
        result: dict[str, float] = {}
        for week_iso, group in df.groupby("week_iso"):
            scores = []
            for kw in keywords:
                if kw in group.columns:
                    scores.append(float(group[kw].mean()))
            if scores:
                result[week_iso] = sum(scores) / len(scores)
        return result

    # --- 1. job_anxiety (inverted: 100 - score) ---
    print("    Fetching job_anxiety...")
    kw_ja = gt_config["keyword_groups"]["job_anxiety"]
    df_ja = _fetch_trends(kw_ja)
    weekly_ja = _slice_weekly(df_ja, kw_ja)
    for week_iso in week_list:
        if week_iso in weekly_ja:
            raw = weekly_ja[week_iso]
            normalised = max(0.0, min(100.0, 100.0 - raw))
            insert_signal("job_anxiety", "pulse", "labour_market", raw, normalised, 1.0, week_iso)
        else:
            insert_signal("job_anxiety", "pulse", "labour_market", 50.0, 50.0, 0.3, week_iso)
    print(f"    job_anxiety: {sum(1 for w in week_list if w in weekly_ja)}/{len(week_list)} weeks")
    time.sleep(sleep_secs)

    # --- 2. career_mobility (rescaled 5-35 -> 0-100) ---
    print("    Fetching career_mobility...")
    kw_cm = gt_config["keyword_groups"]["career_mobility"]
    df_cm = _fetch_trends(kw_cm)
    weekly_cm = _slice_weekly(df_cm, kw_cm)
    FLOOR_CM, CEILING_CM = 5.0, 35.0
    for week_iso in week_list:
        if week_iso in weekly_cm:
            raw = weekly_cm[week_iso]
            normalised = max(0.0, min(100.0, ((raw - FLOOR_CM) / (CEILING_CM - FLOOR_CM)) * 100.0))
            insert_signal("career_mobility", "pulse", "labour_market", raw, normalised, 1.0, week_iso)
        else:
            insert_signal("career_mobility", "pulse", "labour_market", 20.0, 50.0, 0.3, week_iso)
    print(f"    career_mobility: {sum(1 for w in week_list if w in weekly_cm)}/{len(week_list)} weeks")
    time.sleep(sleep_secs)

    # --- 3. contractor_proxy (positive - negative, scaled +/-50 -> 0-100) ---
    print("    Fetching contractor_proxy_positive...")
    kw_pos = gt_config["keyword_groups"]["contractor_proxy_positive"]
    df_pos = _fetch_trends(kw_pos)
    weekly_pos = _slice_weekly(df_pos, kw_pos)
    time.sleep(sleep_secs)

    print("    Fetching contractor_proxy_negative...")
    kw_neg = gt_config["keyword_groups"]["contractor_proxy_negative"]
    df_neg = _fetch_trends(kw_neg)
    weekly_neg = _slice_weekly(df_neg, kw_neg)

    for week_iso in week_list:
        pos = weekly_pos.get(week_iso)
        neg = weekly_neg.get(week_iso)
        if pos is not None and neg is not None:
            raw = pos - neg
            normalised = max(0.0, min(100.0, 50.0 + (raw / 50.0) * 50.0))
            insert_signal("contractor_proxy", "pulse", "corporate_stress", raw, normalised, 1.0, week_iso)
        else:
            insert_signal("contractor_proxy", "pulse", "corporate_stress", 0.0, 50.0, 0.3, week_iso)
    pos_count = sum(1 for w in week_list if w in weekly_pos and w in weekly_neg)
    print(f"    contractor_proxy: {pos_count}/{len(week_list)} weeks")
    time.sleep(sleep_secs)

    # --- 4. resume_anxiety (trip wire: <=5 -> 50, else 50 - raw/2) ---
    print("    Fetching resume_anxiety...")
    kw_ra = gt_config["keyword_groups"]["resume_anxiety"]
    df_ra = _fetch_trends(kw_ra)
    weekly_ra = _slice_weekly(df_ra, kw_ra)
    for week_iso in week_list:
        if week_iso in weekly_ra:
            raw = weekly_ra[week_iso]
            if raw <= 5.0:
                normalised = 50.0
            else:
                normalised = max(0.0, 50.0 - (raw / 2.0))
            insert_signal("resume_anxiety", "pulse", "labour_market", round(raw, 2), round(normalised, 2), 1.0, week_iso)
        else:
            insert_signal("resume_anxiety", "pulse", "labour_market", 0.0, 50.0, 0.3, week_iso)
    print(f"    resume_anxiety: {sum(1 for w in week_list if w in weekly_ra)}/{len(week_list)} weeks")
    time.sleep(sleep_secs)

    # --- 5. layoff_news_velocity PROXY (inverted: high search = low score) ---
    print("    Fetching layoff_news_velocity (Trends proxy)...")
    kw_news = config["google_news"]["pulse_queries"]
    df_news = _fetch_trends(kw_news)
    weekly_news = _slice_weekly(df_news, kw_news)

    for week_iso in week_list:
        if week_iso in weekly_news:
            raw = weekly_news[week_iso]
            normalised = max(0.0, min(100.0, 100.0 - raw))
            insert_signal("layoff_news_velocity", "pulse", "corporate_stress", raw, normalised, 0.7, week_iso)
        else:
            insert_signal("layoff_news_velocity", "pulse", "corporate_stress", 0.0, 50.0, 0.3, week_iso)
    print(f"    layoff_news_velocity (proxy): {sum(1 for w in week_list if w in weekly_news)}/{len(week_list)} weeks")

    print("  Google Trends backfill complete.")


def _backfill_pulse_history(week_list: list[str]) -> None:
    """Calculate pulse for each backfilled week in chronological order.

    This builds the EMA smoothing chain — each week's smoothed score
    depends on the previous week's smoothed score.
    """
    from flatwhite.pulse.composite import calculate_pulse

    for i, week_iso in enumerate(week_list):
        result = calculate_pulse(week_iso=week_iso)
        arrow = {"up": "↑", "down": "↓", "stable": "→"}[result["direction"]]
        print(f"  {week_iso}: {result['smoothed']:.1f} {arrow}  (raw: {result['composite']:.1f})")

    print(f"  Pulse history: {len(week_list)} weeks calculated")


def run_backfill(weeks: int = 12) -> None:
    """Main backfill orchestrator."""
    init_db()

    print(f"=== PULSE BACKFILL — {weeks} weeks ===\n")

    week_list = _get_backfill_weeks(weeks)
    if not week_list:
        print("No weeks to backfill — all weeks already have data.")
        return

    print(f"Backfilling {len(week_list)} weeks: {week_list[0]} → {week_list[-1]}\n")

    # Phase 1: Fast signals
    print("Phase 1: Fast signals (ASX + consumer confidence)...")
    _backfill_asx(week_list)
    _backfill_consumer_confidence(week_list)

    # Phase 2: Google Trends (slow — rate limited)
    print("\nPhase 2: Google Trends (6 calls × 65s = ~6.5 min)...")
    _backfill_google_trends(week_list)

    # Phase 3: Neutral placeholders
    print("\nPhase 3: Neutral placeholders...")
    _backfill_neutral_placeholders(week_list)

    # Phase 4: Pulse history
    print("\nPhase 4: Building pulse history (EMA chain)...")
    _backfill_pulse_history(week_list)

    print(f"\n=== BACKFILL COMPLETE — {len(week_list)} weeks populated ===")
