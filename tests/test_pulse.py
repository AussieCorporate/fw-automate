"""Tests for pulse composite calculation using shared fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
