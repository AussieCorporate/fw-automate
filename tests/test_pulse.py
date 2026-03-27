"""Tests for pulse composite calculation using shared fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import flatwhite.db as db_module


def test_composite_calculation(populated_db: Path) -> None:
    """Pulse composite should be 0-100, direction valid, and have <= 3 drivers."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        result = calculate_pulse(week_iso="2026-W12")

        assert 0 <= result["composite"] <= 100
        assert result["direction"] in ("up", "down", "stable")
        assert len(result["top_drivers"]) <= 3


def test_composite_with_no_signals(temp_db: Path) -> None:
    """calculate_pulse with no signals should default to composite 50.0."""
    with patch.object(db_module, "DB_PATH", temp_db):
        from flatwhite.pulse.composite import calculate_pulse

        result = calculate_pulse(week_iso="2026-W99")

        assert result["composite"] == 50.0
        assert result["direction"] == "stable"


def test_composite_drivers_sorted_by_contribution(populated_db: Path) -> None:
    """Top drivers should be sorted by absolute contribution, descending."""
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.pulse.composite import calculate_pulse

        result = calculate_pulse(week_iso="2026-W12")
        drivers = result["top_drivers"]

        if len(drivers) >= 2:
            for i in range(len(drivers) - 1):
                assert abs(drivers[i]["contribution"]) >= abs(drivers[i + 1]["contribution"])


def test_load_signal_trends_returns_all_signal_deltas(populated_db):
    """load_signal_trends should return WoW deltas for all signals, not just top 5."""
    import datetime
    with patch.object(db_module, "DB_PATH", populated_db), \
         patch("flatwhite.dashboard.state.get_current_week_iso", return_value="2026-W12"):
        from flatwhite.db import insert_signal

        # Insert signals for a second (previous) week
        week_iso = "2026-W11"
        test_signals = [
            ("job_anxiety", "pulse", "labour_market", 60.0, 70.0, 1.0),
            ("career_mobility", "pulse", "labour_market", 55.0, 40.0, 1.0),
            ("market_hiring", "pulse", "labour_market", 20000.0, 30.0, 1.0),
            ("employer_hiring_breadth", "pulse", "labour_market", 9000.0, 55.0, 1.0),
            ("salary_pressure", "pulse", "labour_market", 115000.0, 60.0, 1.0),
            ("layoff_news_velocity", "pulse", "corporate_stress", 64.0, 50.0, 1.0),
            ("contractor_proxy", "pulse", "corporate_stress", 10.0, 45.0, 1.0),
            ("consumer_confidence", "pulse", "economic", 82.0, 75.0, 1.0),
            ("asx_volatility", "pulse", "economic", 1.2, 50.0, 1.0),
            ("asx_momentum", "pulse", "economic", 2.5, 55.0, 1.0),
        ]
        for name, lane, area, raw, norm, sw in test_signals:
            insert_signal(name, lane, area, raw, norm, sw, week_iso)

        from flatwhite.dashboard.state import load_signal_trends
        result = load_signal_trends(n_weeks=6)

        # all_signal_deltas should have an entry for every signal in current week
        all_deltas = result.get("all_signal_deltas", {})
        assert "consumer_confidence" in all_deltas
        assert "job_anxiety" in all_deltas
        # consumer_confidence: current=57.0, prev=75.0 → delta=-18.0
        assert all_deltas["consumer_confidence"]["delta"] == pytest.approx(-18.0, abs=0.5)
        # Must return more than 5 signals (not just biggest_movers)
        assert len(all_deltas) >= 10


def test_driver_bullets_prompt_includes_wow_delta(populated_db, mock_gemini):
    """generate_driver_bullets should pass WoW delta data to the LLM prompt."""
    import json
    with patch.object(db_module, "DB_PATH", populated_db), \
         patch("flatwhite.pulse.summary.get_current_week_iso", return_value="2026-W12"):
        from flatwhite.db import insert_signal

        # Insert prev week signals so delta can be computed
        for name, lane, area, raw, norm, sw in [
            ("consumer_confidence", "pulse", "economic", 82.0, 75.0, 1.0),
            ("job_anxiety", "pulse", "labour_market", 60.0, 70.0, 1.0),
        ]:
            insert_signal(name, lane, area, raw, norm, sw, "2026-W11")

        mock_gemini.return_value = json.dumps([
            {"signal": "consumer_confidence", "direction": "down", "bullet": "Consumer confidence dropped sharply"},
            {"signal": "job_anxiety", "direction": "up", "bullet": "Job anxiety rising"},
            {"signal": "asx_momentum", "direction": "up", "bullet": "ASX holding firm"},
        ])

        from flatwhite.pulse.summary import generate_driver_bullets
        bullets = generate_driver_bullets()

        assert len(bullets) == 3
        # Verify the prompt passed to the LLM included delta info
        call_args = mock_gemini.call_args
        prompt_used = call_args[1].get("prompt") or (call_args[0][0] if call_args[0] else "")
        assert "prev:" in prompt_used or "Δ:" in prompt_used or "delta" in prompt_used.lower()
