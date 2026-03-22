"""Tests for hybrid normalisation: cold-start absolute + self-calibrating median+MAD."""
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid


def test_cold_start_absolute_midpoint():
    """With no history, raw at midpoint of floor/ceiling should score ~50."""
    score, weight = normalise_hybrid(
        raw_value=20000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=[],
    )
    assert 49.0 <= score <= 51.0
    assert weight == 0.8


def test_cold_start_absolute_floor():
    """Raw at floor should score 0."""
    score, _ = normalise_hybrid(
        raw_value=8000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=[],
    )
    assert score == 0.0


def test_cold_start_absolute_ceiling():
    """Raw at ceiling should score 100."""
    score, _ = normalise_hybrid(
        raw_value=32000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=[],
    )
    assert score == 100.0


def test_cold_start_absolute_clamped():
    """Raw below floor should clamp to 0."""
    score, _ = normalise_hybrid(
        raw_value=5000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=[],
    )
    assert score == 0.0


def test_cold_start_inverted():
    """Inverted signal: high raw -> low score."""
    score, _ = normalise_hybrid(
        raw_value=350.0,
        floor=100.0,
        ceiling=350.0,
        inverted=True,
        history=[],
    )
    assert score == 0.0

    score2, _ = normalise_hybrid(
        raw_value=100.0,
        floor=100.0,
        ceiling=350.0,
        inverted=True,
        history=[],
    )
    assert score2 == 100.0


def test_self_calibrating_at_median():
    """With 10+ weeks of history, raw at median should score ~50."""
    history = [20000.0, 20500.0, 19500.0, 21000.0, 19000.0,
               20200.0, 20800.0, 19800.0, 20600.0, 19400.0]
    score, weight = normalise_hybrid(
        raw_value=20000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=history,
    )
    assert 45.0 <= score <= 55.0
    assert weight == 1.0


def test_self_calibrating_above_median():
    """Raw well above median should score > 60."""
    history = [20000.0] * 10
    score, _ = normalise_hybrid(
        raw_value=25000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=history,
    )
    assert score > 60.0


def test_self_calibrating_inverted():
    """Inverted + self-calibrating: raw above median = lower score."""
    history = [200.0] * 10
    score, _ = normalise_hybrid(
        raw_value=280.0,
        floor=100.0,
        ceiling=350.0,
        inverted=True,
        history=history,
    )
    assert score < 40.0


def test_transition_zone():
    """With 5-9 weeks of history, should blend absolute and self-calibrating."""
    history = [20000.0, 20500.0, 19500.0, 21000.0, 19000.0]
    score, weight = normalise_hybrid(
        raw_value=20000.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=history,
    )
    # Should be between 0 and 100 (not crashed)
    assert 0.0 <= score <= 100.0
    # Weight should be between cold-start (0.8) and full (1.0)
    assert 0.8 <= weight <= 1.0


def test_configured_min_weeks_warm():
    """The config helper should expose the warm-up threshold used by callers."""
    config = {
        "signal_reference_ranges": {
            "min_weeks_for_self_calibration": 12,
        }
    }
    assert get_min_weeks_warm(config) == 12


def test_custom_warm_threshold_delays_self_calibration():
    """A larger warm-up threshold should keep 10-week history in transition mode."""
    history = [20000.0 + i * 100.0 for i in range(10)]
    score, weight = normalise_hybrid(
        raw_value=20500.0,
        floor=8000.0,
        ceiling=32000.0,
        inverted=False,
        history=history,
        min_weeks_warm=12,
    )
    assert 0.0 <= score <= 100.0
    assert 0.8 < weight < 1.0
