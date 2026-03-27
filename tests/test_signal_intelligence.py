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


def test_section_state_has_step_fields():
    """After _run_section_background, state should have step/total/step_name."""
    from flatwhite.dashboard.api import _section_state, _run_section_background
    call_log = []

    import flatwhite.dashboard.api as api_module
    original_runners = api_module._SECTION_RUNNERS

    # Temporarily replace classify (1-step) runner with a controlled one
    api_module._SECTION_RUNNERS = {
        "test_section": [
            ("Step one", lambda: call_log.append("one")),
            ("Step two", lambda: call_log.append("two")),
        ]
    }
    # Set up initial state as api_run_section would before spawning the thread
    _section_state["test_section"] = {
        "running": True, "done": False, "error": None,
        "step": 0, "total": 2, "step_name": "Step one", "completed_at": None,
    }

    _run_section_background("test_section")

    api_module._SECTION_RUNNERS = original_runners

    state = _section_state["test_section"]
    assert state["done"] is True
    assert state["running"] is False
    assert state["step"] == 2
    assert state["total"] == 2
    assert call_log == ["one", "two"]
