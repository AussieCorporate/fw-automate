"""Tests for signal interaction pattern detection."""
from flatwhite.pulse.interactions import evaluate_patterns


def _make_scores(**overrides: float) -> dict[str, float]:
    """Build a scores dict with defaults at 50 (neutral) plus overrides."""
    defaults = {
        "job_anxiety": 50.0,
        "career_mobility": 50.0,
        "consumer_confidence": 50.0,
        "layoff_news_velocity": 50.0,
        "asx_momentum": 50.0,
        "asic_insolvency": 50.0,
        "employer_hiring_breadth": 50.0,
        "salary_pressure": 50.0,
        "market_hiring": 50.0,
    }
    defaults.update(overrides)
    return defaults


def test_defensive_mobility_detected():
    """High career mobility + low consumer confidence = defensive."""
    scores = _make_scores(career_mobility=75.0, consumer_confidence=25.0)
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "Defensive mobility" in names
    match = [p for p in patterns if p["name"] == "Defensive mobility"][0]
    assert match["severity"] > 0.5
    assert "career_mobility" in match["signals_involved"]
    assert "consumer_confidence" in match["signals_involved"]
    assert len(match["narrative"]) > 10


def test_defensive_mobility_not_detected_when_confidence_ok():
    """If consumer confidence is fine, no defensive mobility."""
    scores = _make_scores(career_mobility=75.0, consumer_confidence=65.0)
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "Defensive mobility" not in names


def test_confident_mobility_detected():
    """High career mobility + high consumer confidence = confident."""
    scores = _make_scores(career_mobility=75.0, consumer_confidence=75.0)
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "Confident mobility" in names


def test_news_leading_public_lagging():
    """Calm job anxiety + stressed layoff news = news leading."""
    scores = _make_scores(job_anxiety=70.0, layoff_news_velocity=25.0)
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "News leading, public lagging" in names


def test_confirmed_anxiety():
    """Both job anxiety and layoff news stressed."""
    scores = _make_scores(job_anxiety=25.0, layoff_news_velocity=25.0)
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "Confirmed anxiety" in names


def test_broad_pessimism():
    """ASX down + consumer confidence down."""
    scores = _make_scores(asx_momentum=20.0, consumer_confidence=20.0)
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "Broad pessimism" in names


def test_no_patterns_at_neutral():
    """All signals at 50 should trigger no patterns."""
    scores = _make_scores()
    patterns = evaluate_patterns(scores)
    assert patterns == []


def test_severity_scales_with_distance():
    """Severity should be higher when signals are further from thresholds."""
    mild = _make_scores(career_mobility=62.0, consumer_confidence=38.0)
    strong = _make_scores(career_mobility=90.0, consumer_confidence=15.0)
    mild_patterns = evaluate_patterns(mild)
    strong_patterns = evaluate_patterns(strong)
    mild_sev = [p for p in mild_patterns if p["name"] == "Defensive mobility"][0]["severity"]
    strong_sev = [p for p in strong_patterns if p["name"] == "Defensive mobility"][0]["severity"]
    assert strong_sev > mild_sev


def test_multiple_patterns_can_fire():
    """Multiple patterns can be detected simultaneously."""
    scores = _make_scores(
        career_mobility=75.0,
        consumer_confidence=20.0,
        asx_momentum=20.0,
    )
    patterns = evaluate_patterns(scores)
    names = [p["name"] for p in patterns]
    assert "Defensive mobility" in names
    assert "Broad pessimism" in names
