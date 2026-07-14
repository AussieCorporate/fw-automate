"""Tests for Big Conversation topic archive + drag-drop pairing state.

Both are stored in FW's own SQLite DB (never in the read-only Instagram
output folder) — see flatwhite/dashboard/state.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import flatwhite.db as db_module


def test_archive_state_round_trips(tmp_path: Path):
    db_path = tmp_path / "bc_state_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        from flatwhite.dashboard.state import load_topic_archive_state, set_topic_archived

        assert load_topic_archive_state() == {}
        set_topic_archived("Kids in the Office", True)
        assert load_topic_archive_state() == {"Kids in the Office": True}
        set_topic_archived("Kids in the Office", False)
        assert load_topic_archive_state() == {}


def test_pairing_overrides_round_trip(tmp_path: Path):
    db_path = tmp_path / "bc_pairing_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        from flatwhite.dashboard.state import load_pairing_overrides, save_pairing_override

        assert load_pairing_overrides("Kids in the Office") == {}
        save_pairing_override("Kids in the Office", "p1_1_Katie_Moloney.png", 3)
        assert load_pairing_overrides("Kids in the Office") == {"p1_1_Katie_Moloney.png": 3}
        # Moving it again overwrites, does not duplicate.
        save_pairing_override("Kids in the Office", "p1_1_Katie_Moloney.png", 2)
        assert load_pairing_overrides("Kids in the Office") == {"p1_1_Katie_Moloney.png": 2}


def test_pairing_overrides_are_scoped_per_topic(tmp_path: Path):
    db_path = tmp_path / "bc_pairing_scope_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        from flatwhite.dashboard.state import load_pairing_overrides, save_pairing_override

        save_pairing_override("Kids in the Office", "shot.png", 1)
        save_pairing_override("Career Pivoting", "shot.png", 4)
        assert load_pairing_overrides("Kids in the Office") == {"shot.png": 1}
        assert load_pairing_overrides("Career Pivoting") == {"shot.png": 4}
