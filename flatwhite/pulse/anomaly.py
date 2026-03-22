import numpy as np
import yaml
from pathlib import Path
from flatwhite.db import get_connection, get_current_week_iso, get_recent_signals

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

def detect_anomalies(signal_name: str) -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    baseline_weeks = config["anomaly_detection"]["baseline_weeks"]
    threshold_mads = config["anomaly_detection"]["threshold_mads"]

    # get_recent_signals excludes current week, so fetch current week separately
    week_iso = get_current_week_iso()
    conn = get_connection()
    current_row = conn.execute(
        "SELECT normalised_score FROM signals WHERE signal_name = ? AND week_iso = ? LIMIT 1",
        (signal_name, week_iso),
    ).fetchone()
    conn.close()

    if current_row is None:
        return {"signal": signal_name, "is_anomaly": False, "reason": "no_current_data"}

    current = float(current_row["normalised_score"])
    baseline = get_recent_signals(signal_name, weeks=baseline_weeks)
    if len(baseline) < 2:
        return {"signal": signal_name, "is_anomaly": False, "reason": "insufficient_data"}

    # Filter out neutral placeholders (source_weight <= 0.3).
    real_baseline = [r for r in baseline if r.get("source_weight", 1.0) > 0.3]
    if len(real_baseline) < 2:
        return {"signal": signal_name, "is_anomaly": False, "reason": "building_baseline"}

    # Require baseline data from at least 2 separate ingest runs (distinct pull dates).
    # Backfill writes all weeks in one batch (same day) — comparing live data against
    # a single-batch backfill is not meaningful anomaly detection.
    pull_dates = set(r.get("pulled_at", "")[:10] for r in real_baseline)
    if len(pull_dates) < 2:
        return {"signal": signal_name, "is_anomaly": False, "reason": "backfill_only"}

    baseline_scores = [r["normalised_score"] for r in real_baseline]

    median = float(np.median(baseline_scores))
    raw_mad = float(np.median(np.abs(np.array(baseline_scores) - median)))

    # If baseline has zero variance (all identical scores), there is no
    # meaningful pattern to detect anomalies against — suppress the alert.
    if raw_mad == 0.0:
        unique_vals = set(baseline_scores)
        if len(unique_vals) <= 1:
            return {
                "signal": signal_name,
                "is_anomaly": False,
                "reason": "uniform_baseline",
                "current": round(current, 1),
                "median": round(median, 1),
            }

    # Floor of 5.0 on a 0-100 scale: prevents tiny natural variation from
    # producing exaggerated MAD scores.
    mad = max(raw_mad, 5.0)

    # Progressive thresholds: use wider thresholds with less real baseline
    # data, tightening as confidence grows.
    n = len(baseline_scores)
    if n < 5:
        effective_threshold = threshold_mads + 1.0   # 3.0 MAD with 2-4 weeks
        confidence = "low"
    elif n < 10:
        effective_threshold = threshold_mads + 0.5   # 2.5 MAD with 5-9 weeks
        confidence = "medium"
    else:
        effective_threshold = threshold_mads          # 2.0 MAD with 10+ weeks
        confidence = "high"

    deviation = abs(current - median) / mad

    return {
        "signal": signal_name,
        "is_anomaly": deviation > effective_threshold,
        "current": round(current, 1),
        "median": round(median, 1),
        "mad": round(mad, 2),
        "deviation_mads": round(deviation, 2),
        "threshold": effective_threshold,
        "baseline_weeks": n,
        "confidence": confidence,
        "direction": "above" if current > median else "below",
    }

def detect_all_anomalies() -> list[dict]:
    signal_names = [
        "job_anxiety", "career_mobility", "market_hiring",
        "employer_hiring_breadth", "salary_pressure", "layoff_news_velocity",
        "contractor_proxy", "consumer_confidence", "asx_volatility",
        "asx_momentum", "reddit_topic_velocity", "resume_anxiety",
        "auslaw_velocity",
    ]
    results = []
    for name in signal_names:
        result = detect_anomalies(name)
        if result["is_anomaly"]:
            results.append(result)
    return results
