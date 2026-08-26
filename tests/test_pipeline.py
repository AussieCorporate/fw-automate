"""Integration tests for the full pipeline: pulse calc, anomaly detection, newsletter render, audit."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import flatwhite.db as db_module


def test_pulse_calculation_produces_valid_score(populated_db: Path) -> None:
    """calculate_pulse should produce a composite score between 0 and 100."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        result = calculate_pulse(week_iso="2026-W12")

        assert "composite" in result
        assert "smoothed" in result
        assert "direction" in result
        assert "top_drivers" in result
        assert 0 <= result["composite"] <= 100
        assert 0 <= result["smoothed"] <= 100
        assert result["direction"] in ("up", "down", "stable")
        assert len(result["top_drivers"]) <= 3


def test_pulse_direction_stable_without_history(populated_db: Path) -> None:
    """First pulse calculation with no history should report 'stable'."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        result = calculate_pulse(week_iso="2026-W12")
        assert result["direction"] == "stable"


def test_pulse_stored_in_history(populated_db: Path) -> None:
    """calculate_pulse should insert a row into pulse_history."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        calculate_pulse(week_iso="2026-W12")

        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT * FROM pulse_history WHERE week_iso = ?",
            ("2026-W12",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert 0 <= row["composite_score"] <= 100
        assert 0 <= row["smoothed_score"] <= 100
        assert row["direction"] in ("up", "down", "stable")


def test_anomaly_detection_short_baseline(temp_db: Path) -> None:
    """detect_anomalies should return is_anomaly=False with insufficient data (< 3 weeks)."""
    with patch.object(db_module, "DB_PATH", temp_db):
        from flatwhite.pulse.anomaly import detect_anomalies

        week_iso = db_module.get_current_week_iso()

        # Insert current week + 1 baseline week — below the 2-week minimum for baseline
        db_module.insert_signal(
            "job_anxiety", "pulse", "labour_market", 60.0, 40.0, 1.0, week_iso
        )
        db_module.insert_signal(
            "job_anxiety", "pulse", "labour_market", 62.0, 42.0, 1.0, "2025-W01"
        )

        result = detect_anomalies("job_anxiety")
        assert result["is_anomaly"] is False
        assert result["reason"] == "insufficient_data"


def _insert_signal_on_date(signal_name, lane, area, raw_value, normalised_score,
                            source_weight, week_iso, pulled_at) -> None:
    """Insert a signal row with an explicit pulled_at, unlike db_module.insert_signal
    (which always stamps datetime('now')). detect_anomalies requires baseline rows
    from at least 2 distinct pull dates (real ingest runs, not a single backfill
    batch) - see flatwhite/pulse/anomaly.py's backfill_only guard - so tests that
    build a multi-week baseline must spread pulled_at across days, matching how
    real weekly ingests land one day apart."""
    conn = db_module.get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO signals
        (signal_name, lane, area, raw_value, normalised_score, source_weight, pulled_at, week_iso)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (signal_name, lane, area, raw_value, normalised_score, source_weight, pulled_at, week_iso),
    )
    conn.commit()
    conn.close()


def test_anomaly_detection_with_enough_data(temp_db: Path) -> None:
    """detect_anomalies with a near-uniform baseline uses the MAD floor and
    detects a large deviation.

    Uses a slightly-varied baseline (49-51), not a perfectly uniform one (all
    50.0): a perfectly uniform baseline now hits anomaly.py's own
    "uniform_baseline" guard (raw MAD == 0 and only one distinct value), which
    deliberately suppresses the alert as having no meaningful pattern to
    compare against. This test's actual target - the 5.0 MAD floor that
    prevents tiny real variation from producing an exaggerated score - needs a
    baseline with real (if small) variance, not zero variance.
    """
    with patch.object(db_module, "DB_PATH", temp_db):
        from flatwhite.pulse.anomaly import detect_anomalies

        week_iso = db_module.get_current_week_iso()

        # Insert 5 weeks of near-stable baseline data (scores 49-51), each from
        # a different ingest day so the backfill_only guard doesn't suppress detection.
        baseline_scores = [49.0, 49.5, 50.0, 50.5, 51.0]
        for i, score in enumerate(baseline_scores):
            week = f"2025-W{i + 1:02d}"
            _insert_signal_on_date(
                "job_anxiety", "pulse", "labour_market", score, score, 1.0, week,
                f"2025-{i + 1:02d}-01T00:00:00",
            )

        # Insert current week with extreme value
        db_module.insert_signal(
            "job_anxiety", "pulse", "labour_market", 95.0, 95.0, 1.0, week_iso
        )

        result = detect_anomalies("job_anxiety")
        # Baseline median 50.0, raw MAD = 0.5, but floor is 5.0
        # Deviation = |95 - 50| / 5.0 = 9.0 MADs -> anomaly
        assert "deviation_mads" in result
        assert result["is_anomaly"] is True
        assert result["deviation_mads"] > 2.0


def test_anomaly_detection_varied_baseline(temp_db: Path) -> None:
    """detect_anomalies should return deviation info when baseline has variance."""
    with patch.object(db_module, "DB_PATH", temp_db):
        from flatwhite.pulse.anomaly import detect_anomalies

        week_iso = db_module.get_current_week_iso()

        # Insert varied baseline (scores spread around 50), each from a different
        # ingest day so the backfill_only guard doesn't suppress detection.
        baseline_scores = [45.0, 48.0, 50.0, 52.0, 55.0]
        for i, score in enumerate(baseline_scores):
            week = f"2025-W{i + 1:02d}"
            _insert_signal_on_date(
                "job_anxiety", "pulse", "labour_market", score, score, 1.0, week,
                f"2025-{i + 1:02d}-01T00:00:00",
            )

        # Insert current week with high value
        db_module.insert_signal(
            "job_anxiety", "pulse", "labour_market", 90.0, 90.0, 1.0, week_iso
        )

        result = detect_anomalies("job_anxiety")
        assert "deviation_mads" in result
        assert "median" in result
        assert "mad" in result


def test_render_newsletter_produces_html(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """render_newsletter should produce an HTML string containing the hook text."""
    mock_gemini.return_value = json.dumps([
        {"signal": "job_anxiety", "direction": "up", "bullet": "Rising search volume for redundancy terms."}
    ])

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        calculate_pulse(week_iso="2026-W12")

        # Store a pulse summary so the pulse block renders
        conn = db_module.get_connection()
        conn.execute(
            "UPDATE pulse_history SET summary_text = ? WHERE week_iso = ?",
            ("Market anxiety continues to rise.", "2026-W12"),
        )
        conn.commit()
        conn.close()

        # Patch get_current_week_iso to return our test week
        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W12"):
            from flatwhite.assemble.renderer import render_newsletter

            html = render_newsletter(
                hook_text="Testing the pipeline end to end.",
                rotation="A",
            )

            assert isinstance(html, str)
            assert len(html) > 0
            assert "Testing the pipeline end to end." in html
            assert "Good morning AusCorp" in html


def test_render_newsletter_rotation_b(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """Rotation B should also produce valid HTML with the hook text."""
    mock_gemini.return_value = json.dumps([
        {"signal": "asx_volatility", "direction": "down", "bullet": "Markets calming."}
    ])

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        calculate_pulse(week_iso="2026-W12")

        conn = db_module.get_connection()
        conn.execute(
            "UPDATE pulse_history SET summary_text = ? WHERE week_iso = ?",
            ("Pulse summary for rotation B test.", "2026-W12"),
        )
        conn.commit()
        conn.close()

        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W12"):
            from flatwhite.assemble.renderer import render_newsletter

            html = render_newsletter(
                hook_text="Rotation B hook.",
                rotation="B",
            )

            assert isinstance(html, str)
            assert "Rotation B hook." in html


def test_audit_classifications_returns_correct_structure(populated_db: Path) -> None:
    """audit_classifications should return a dict with the expected keys."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.audit import audit_classifications

        result = audit_classifications(week_iso="2026-W12")

        assert isinstance(result, dict)
        assert "week_iso" in result
        assert "total" in result
        assert "discard_count" in result
        assert "by_section" in result
        assert "stats" in result
        assert result["week_iso"] == "2026-W12"
        assert isinstance(result["total"], int)
        assert isinstance(result["discard_count"], int)
        assert isinstance(result["by_section"], dict)
        assert isinstance(result["stats"], dict)


def test_audit_classifications_empty_week(populated_db: Path) -> None:
    """audit_classifications on a week with no curated items should return zero totals."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.audit import audit_classifications

        result = audit_classifications(week_iso="9999-W01")

        assert result["total"] == 0
        assert result["discard_count"] == 0
        assert result["by_section"] == {}
        assert result["stats"] == {}
