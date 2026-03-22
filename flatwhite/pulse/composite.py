from __future__ import annotations

import json
import yaml
from pathlib import Path
from flatwhite.db import (
    get_connection, get_current_week_iso,
    get_pulse_history, get_pulse_history_before, insert_pulse,
)

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

SIGNAL_TO_WEIGHT_KEY = {
    "job_anxiety": "job_anxiety",
    "career_mobility": "career_mobility",
    "market_hiring": "market_hiring",
    "employer_hiring_breadth": "employer_hiring_breadth",
    "employer_req_freshness": "employer_req_freshness",
    "employer_net_delta": "employer_net_delta",
    "layoff_news_velocity": "layoff_news_velocity",
    "contractor_proxy": "contractor_proxy",
    "consumer_confidence": "consumer_confidence",
    "asx_volatility": "asx_volatility",
    "asx_momentum": "asx_momentum",
    "reddit_topic_velocity": "reddit_topic_velocity",
    "salary_pressure": "salary_pressure",
    "resume_anxiety": "resume_anxiety",
    "auslaw_velocity": "auslaw_velocity",
    "indeed_job_postings": "indeed_job_postings",
    "indeed_remote_pct": "indeed_remote_pct",
    "asic_insolvency": "asic_insolvency",
}

def calculate_pulse(week_iso: str | None = None) -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    weights = config["pulse_weights"]
    if week_iso is None:
        week_iso = get_current_week_iso()

    conn = get_connection()
    signals = conn.execute(
        "SELECT signal_name, normalised_score, source_weight FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (week_iso,),
    ).fetchall()
    conn.close()

    signal_map = {s["signal_name"]: s["normalised_score"] for s in signals}
    weight_map = {s["signal_name"]: s["source_weight"] for s in signals}

    weighted_sum = 0.0
    total_weight = 0.0
    drivers = []

    for signal_name, weight_key in SIGNAL_TO_WEIGHT_KEY.items():
        if signal_name in signal_map and weight_key in weights:
            w = weights[weight_key]
            score = signal_map[signal_name]
            sw = weight_map.get(signal_name, 1.0)
            effective_weight = w * sw
            weighted_sum += score * effective_weight
            total_weight += effective_weight
            drivers.append({
                "signal": signal_name,
                "score": round(score, 1),
                "weight": round(effective_weight, 3),
                "contribution": round(score * effective_weight, 2),
            })

    if total_weight > 0:
        composite = weighted_sum / total_weight
    else:
        composite = 50.0

    history = get_pulse_history_before(week_iso, weeks=config["pulse_smoothing"]["span_weeks"])
    if history:
        span = config["pulse_smoothing"]["span_weeks"]
        alpha = 2.0 / (span + 1.0)
        prev_smoothed = history[0]["smoothed_score"]
        smoothed = alpha * composite + (1.0 - alpha) * prev_smoothed
    else:
        smoothed = composite

    threshold = config["direction_threshold_points"]
    if history:
        prev = history[0]["smoothed_score"]
        diff = smoothed - prev
        if diff > threshold:
            direction = "up"
        elif diff < -threshold:
            direction = "down"
        else:
            direction = "stable"
    else:
        direction = "stable"

    drivers.sort(key=lambda d: abs(d["contribution"]), reverse=True)
    top_drivers = drivers[:3]

    insert_pulse(
        week_iso=week_iso,
        composite_score=round(composite, 1),
        smoothed_score=round(smoothed, 1),
        direction=direction,
        drivers_json=json.dumps(top_drivers),
    )

    return {
        "week_iso": week_iso,
        "composite": round(composite, 1),
        "smoothed": round(smoothed, 1),
        "direction": direction,
        "top_drivers": top_drivers,
    }
