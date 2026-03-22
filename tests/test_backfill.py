"""Test backfill module — unit tests that don't hit external APIs."""
from flatwhite.db import init_db, get_connection, insert_signal
from flatwhite.pulse.backfill import _get_backfill_weeks, _backfill_neutral_placeholders, _backfill_pulse_history


def test_get_backfill_weeks_skips_existing():
    """Weeks with >= 10 signals should be excluded from the backfill list."""
    init_db()

    # Use a wide range (52 weeks) to guarantee some weeks predate existing data
    weeks = _get_backfill_weeks(52)
    assert len(weeks) > 0
    assert all(isinstance(w, str) and "-W" in w for w in weeks)

    # Insert 10+ signals for the first backfill week (threshold for "full" week)
    first_week = weeks[0]
    test_signals = [
        "job_anxiety", "career_mobility", "market_hiring", "employer_hiring_breadth",
        "salary_pressure", "layoff_news_velocity", "contractor_proxy",
        "consumer_confidence", "asx_volatility", "asx_momentum",
    ]
    for sig in test_signals:
        insert_signal(sig, "pulse", "labour_market", 50.0, 50.0, 1.0, first_week)

    # Now that week should be excluded (>= 10 signals)
    weeks_after = _get_backfill_weeks(52)
    assert first_week not in weeks_after
    print("PASS: _get_backfill_weeks skips existing weeks")


def test_neutral_placeholders():
    """Neutral placeholders should insert 5 signals per week at 50.0 / 0.3."""
    init_db()
    test_weeks = ["9999-W01", "9999-W02"]
    _backfill_neutral_placeholders(test_weeks)

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals WHERE week_iso IN ('9999-W01', '9999-W02') AND source_weight = 0.3"
    ).fetchall()
    conn.close()

    # 7 neutral signals x 2 weeks = 14
    assert len(rows) == 14
    assert all(r["normalised_score"] == 50.0 for r in rows)
    print("PASS: neutral placeholders insert correctly")


def test_pulse_history_chain():
    """Backfill pulse history should produce valid scores for each week."""
    init_db()
    test_weeks = ["9998-W01", "9998-W02", "9998-W03"]

    # Insert minimal signals for each week (all 13 signals)
    signals = [
        ("job_anxiety", "labour_market", 50.0),
        ("career_mobility", "labour_market", 55.0),
        ("market_hiring", "labour_market", 52.0),
        ("employer_hiring_breadth", "labour_market", 48.0),
        ("salary_pressure", "labour_market", 55.0),
        ("layoff_news_velocity", "corporate_stress", 45.0),
        ("contractor_proxy", "corporate_stress", 55.0),
        ("consumer_confidence", "economic", 57.0),
        ("asx_volatility", "economic", 60.0),
        ("asx_momentum", "economic", 75.0),
        ("reddit_topic_velocity", "corporate_stress", 50.0),
        ("resume_anxiety", "labour_market", 50.0),
        ("auslaw_velocity", "corporate_stress", 50.0),
    ]

    for week_iso in test_weeks:
        for name, area, score in signals:
            insert_signal(name, "pulse", area, 0.0, score, 1.0, week_iso)

    _backfill_pulse_history(test_weeks)

    conn = get_connection()
    history = conn.execute(
        "SELECT * FROM pulse_history WHERE week_iso IN ('9998-W01', '9998-W02', '9998-W03') ORDER BY week_iso"
    ).fetchall()
    conn.close()

    assert len(history) == 3
    for h in history:
        assert 0 <= h["composite_score"] <= 100
        assert 0 <= h["smoothed_score"] <= 100
        assert h["direction"] in ("up", "down", "stable")
    print("PASS: pulse history chain builds correctly")


if __name__ == "__main__":
    test_get_backfill_weeks_skips_existing()
    test_neutral_placeholders()
    test_pulse_history_chain()
    print("\nAll backfill tests passed.")
