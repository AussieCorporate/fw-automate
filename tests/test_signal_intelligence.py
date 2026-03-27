"""Tests for signal_intelligence module and DB table."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def si_db(tmp_path: Path):
    db_path = tmp_path / "si_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def test_signal_intelligence_table_exists(si_db):
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "signal_intelligence" in tables


def test_signal_intelligence_unique_constraint(si_db):
    """Duplicate (signal_name, week_iso) should be replaced, not duplicated."""
    import json
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        articles = json.dumps([{"title": "Test", "url": "http://x.com", "published": "2026-03-20", "snippet": "foo"}])
        conn.execute(
            """INSERT INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "Commentary A"),
        )
        conn.commit()
        conn.execute(
            """INSERT OR REPLACE INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "Commentary B"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT commentary FROM signal_intelligence WHERE signal_name='asx_volatility' AND week_iso='2026-W13'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "Commentary B"
