"""Hybrid normalisation: absolute floor/ceiling for cold start, median+MAD when warm.

Cold start (0-4 weeks):   100% absolute scoring from config floor/ceiling.
Transition (5-9 weeks):   Blend of absolute and self-calibrating (weighted by week count).
Warm (10+ weeks):         100% median+MAD self-calibrating from signal's own history.

OUTPUT CONVENTION: STRESS SCORE (0 = calm, 100 = max stress).
- For a raw signal where high raw = bad/stressful (e.g. layoff news count), set
  inverted=True and the higher raw maps to higher stress score directly.
- For a raw signal where high raw = good/healthy (e.g. consumer confidence), set
  inverted=False and we flip the absolute mapping so high raw → low stress score.
"""
from __future__ import annotations

from statistics import median as _median


def get_min_weeks_warm(config: dict | None, default: int = 10) -> int:
    """Return the configured warm-up threshold for hybrid normalisation."""
    if not isinstance(config, dict):
        return default
    return int(config.get("signal_reference_ranges", {}).get("min_weeks_for_self_calibration", default))


def _absolute_score(raw: float, floor: float, ceiling: float, inverted: bool) -> float:
    """Map raw value to a 0-100 stress score using fixed reference range.

    inverted=True  → high raw = high stress (no flip needed)
    inverted=False → high raw = low stress (flip)
    """
    if ceiling == floor:
        return 50.0
    score = ((raw - floor) / (ceiling - floor)) * 100.0
    score = max(0.0, min(100.0, score))
    if not inverted:
        score = 100.0 - score
    return round(score, 2)


def _mad_score(raw: float, history: list[float], inverted: bool) -> float:
    """Map raw value to a 0-100 stress score using median + MAD from history.

    Score of 50 = at median. Each MAD of deviation moves the score by 10 points.
    inverted=True  → high raw = high stress (raw above median raises score)
    inverted=False → high raw = low stress (raw above median lowers score)
    """
    med = _median(history)
    deviations = [abs(v - med) for v in history]
    mad = _median(deviations)
    # Floor MAD to prevent division by zero / extreme scores from uniform data.
    # Use 1% of median as minimum meaningful deviation.
    mad = max(mad, abs(med) * 0.01, 0.01)
    score = 50.0 + ((raw - med) / mad) * 10.0
    score = max(0.0, min(100.0, score))
    if not inverted:
        score = 100.0 - score
    return round(score, 2)


def normalise_hybrid(
    raw_value: float,
    floor: float,
    ceiling: float,
    inverted: bool,
    history: list[float],
    min_weeks_warm: int = 10,
) -> tuple[float, float]:
    """Normalise a raw signal value using the hybrid approach.

    Args:
        raw_value: Current week's raw measurement.
        floor: Reference range lower bound (from config).
        ceiling: Reference range upper bound (from config).
        inverted: If True, higher raw = lower score.
        history: List of raw_values from previous weeks (most recent first),
                 filtered to exclude backfill placeholders.
        min_weeks_warm: Weeks of real data needed for full self-calibration.

    Returns:
        (normalised_score, source_weight) tuple.
        source_weight: 0.8 during cold start, blends to 1.0 as history builds.
    """
    n = len(history)

    if n < 5:
        # Cold start: pure absolute scoring
        score = _absolute_score(raw_value, floor, ceiling, inverted)
        weight = 0.8
    elif n < min_weeks_warm:
        # Transition: blend absolute and self-calibrating
        abs_score = _absolute_score(raw_value, floor, ceiling, inverted)
        mad_score_val = _mad_score(raw_value, history, inverted)
        # Linear blend: at 5 weeks = 50/50, at 9 weeks = 10/90
        blend = (n - 5) / (min_weeks_warm - 5)
        score = abs_score * (1.0 - blend) + mad_score_val * blend
        score = round(max(0.0, min(100.0, score)), 2)
        weight = 0.8 + 0.2 * blend
    else:
        # Warm: pure self-calibrating
        score = _mad_score(raw_value, history, inverted)
        weight = 1.0

    return score, round(weight, 2)
