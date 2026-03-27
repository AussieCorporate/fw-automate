"""Tests for the Lobby employer trend data."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def lobby_db(tmp_path: Path) -> Path:
    """DB with employer snapshots across 8 weeks for trend testing."""
    db_path = tmp_path / "lobby_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import sqlite3
        conn = sqlite3.connect(db_path)
        # Insert employer
        conn.execute(
            """INSERT INTO employer_watchlist (employer_name, sector, careers_url)
            VALUES ('Deloitte Australia', 'big4', 'https://seek.com.au/deloitte')"""
        )
        emp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Insert 8 weeks of snapshots: role counts 100,105,110,108,112,115,118,120
        import datetime
        week = datetime.datetime.strptime("2026-W05-1", "%G-W%V-%u")
        counts = [100, 105, 110, 108, 112, 115, 118, 120]
        for i, count in enumerate(counts):
            w_iso = (week + datetime.timedelta(weeks=i)).strftime("%G-W%V")
            conn.execute(
                """INSERT INTO employer_snapshots (employer_id, open_roles_count, snapshot_date, week_iso)
                VALUES (?, ?, date('now'), ?)""",
                (emp_id, count, w_iso),
            )
        conn.commit()
        conn.close()
        yield db_path


def test_lobby_returns_mom_delta(lobby_db):
    """api_lobby should return mom_delta (current - 4 weeks ago)."""
    with patch.object(db_module, "DB_PATH", lobby_db):
        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W12"):
            from flatwhite.dashboard.api import api_lobby
            import json
            result = api_lobby()
            d = json.loads(result.body)
            emp = d["employers"][0]
            # current=120 (W12), 4wk ago=112 (W08) → mom_delta=+8
            assert emp["mom_delta"] == 8


def test_lobby_returns_history_array(lobby_db):
    """api_lobby employer objects should include a history array of last 6 week counts."""
    with patch.object(db_module, "DB_PATH", lobby_db):
        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W12"):
            from flatwhite.dashboard.api import api_lobby
            import json
            result = api_lobby()
            d = json.loads(result.body)
            emp = d["employers"][0]
            assert "history" in emp
            assert len(emp["history"]) == 6
            assert emp["history"][-1] == 120  # most recent
