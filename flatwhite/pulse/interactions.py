"""Signal interaction pattern detection.

Evaluates pairs of signals to detect meaningful narratives that individual
scores cannot express — e.g. 'defensive mobility' when career search is
high but consumer confidence is low.

Pattern definitions live in config.yaml under signal_interactions.patterns.
Each pattern specifies signal roles, threshold conditions, and a narrative
template. This module evaluates all patterns against current scores and
returns detected interactions with severity (0-1).
"""
from __future__ import annotations

import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _load_patterns() -> list[dict]:
    """Load interaction pattern definitions from config."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config.get("signal_interactions", {}).get("patterns", [])


def _evaluate_single_pattern(
    pattern: dict, scores: dict[str, float]
) -> dict | None:
    """Evaluate one pattern against current scores.

    Returns a result dict if the pattern fires, or None if conditions not met.
    Severity is 0-1, based on how far beyond the thresholds each signal is.
    """
    signals = pattern["signals"]
    thresholds = pattern["thresholds"]

    # Collect the signal scores referenced by this pattern
    signal_scores: dict[str, float] = {}
    for role, signal_name in signals.items():
        if signal_name not in scores:
            return None
        signal_scores[role] = scores[signal_name]

    # Check each threshold condition
    # Threshold keys follow the convention: {role}_{above|below}
    violations: list[float] = []
    for threshold_key, threshold_value in thresholds.items():
        # Parse the role and direction from the key
        # e.g. "high_above" -> role="high", direction="above"
        # e.g. "stressed_below" -> role="stressed", direction="below"
        parts = threshold_key.rsplit("_", 1)
        if len(parts) != 2:
            return None
        role, direction = parts[0], parts[1]

        if role not in signal_scores:
            return None

        score = signal_scores[role]

        if direction == "above":
            if score <= threshold_value:
                return None
            # How far above the threshold, normalised so half the remaining
            # range maps to severity 1.0 (makes moderate overshoots visible)
            half_range = max(1.0, (100.0 - threshold_value) / 2.0)
            violations.append((score - threshold_value) / half_range)
        elif direction == "below":
            if score >= threshold_value:
                return None
            # How far below the threshold, normalised so half the range
            # to zero maps to severity 1.0
            half_range = max(1.0, threshold_value / 2.0)
            violations.append((threshold_value - score) / half_range)
        else:
            return None

    if not violations:
        return None

    # Severity is the average of how far each signal exceeds its threshold
    severity = round(min(1.0, sum(violations) / len(violations)), 2)

    # Build comma-separated list of signal names involved
    signal_names = ", ".join(signals.values())

    return {
        "name": pattern["name"],
        "severity": severity,
        "signals_involved": signal_names,
        "narrative": pattern["narrative"],
    }


def evaluate_patterns(scores: dict[str, float]) -> list[dict]:
    """Evaluate all interaction patterns against current signal scores.

    Args:
        scores: Dict mapping signal_name to normalised_score (0-100).

    Returns:
        List of detected patterns, sorted by severity (highest first).
        Each dict has keys: name, severity, signals_involved, narrative.
    """
    patterns = _load_patterns()
    results: list[dict] = []

    for pattern in patterns:
        result = _evaluate_single_pattern(pattern, scores)
        if result is not None:
            results.append(result)

    results.sort(key=lambda r: r["severity"], reverse=True)
    return results
