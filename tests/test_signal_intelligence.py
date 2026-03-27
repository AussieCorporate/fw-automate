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


def test_run_signal_intelligence_skips_when_cold(si_db):
    """run_signal_intelligence should no-op when only 1 week of signal data exists."""
    with patch.object(db_module, "DB_PATH", si_db):
        # Only insert signals for current week — no previous week
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.2, 60.0, 1.0, "2026-W13")

        with patch("flatwhite.signals.signal_intelligence.get_current_week_iso", return_value="2026-W13"):
            from flatwhite.signals.signal_intelligence import run_signal_intelligence
            run_signal_intelligence()  # Should not raise, should not write anything

            conn = db_module.get_connection()
            rows = conn.execute("SELECT * FROM signal_intelligence").fetchall()
            conn.close()
            assert len(rows) == 0


def test_run_signal_intelligence_generates_for_movers(si_db):
    """run_signal_intelligence should generate commentary for signals with abs(delta) >= 5."""
    with patch.object(db_module, "DB_PATH", si_db):
        # Insert W12 and W13 signals — asx_volatility moves +8 pts
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.2, 52.0, 1.0, "2026-W12")
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.8, 60.0, 1.0, "2026-W13")
        # market_hiring moves only +2 pts — should be skipped
        db_module.insert_signal("market_hiring",  "pulse", "labour_market", 20000.0, 55.0, 1.0, "2026-W12")
        db_module.insert_signal("market_hiring",  "pulse", "labour_market", 20500.0, 57.0, 1.0, "2026-W13")

        mock_articles = [{"title": "ASX swings wildly", "url": "http://afr.com/asx", "published": "2026-03-20", "snippet": "Markets volatile"}]

        with patch("flatwhite.signals.signal_intelligence.get_current_week_iso", return_value="2026-W13"):
            with patch("flatwhite.signals.signal_intelligence._fetch_articles", return_value=mock_articles):
                with patch("flatwhite.model_router.route", return_value="ASX rose sharply this week due to global risk sentiment."):
                    from flatwhite.signals.signal_intelligence import run_signal_intelligence
                    run_signal_intelligence()

        conn = db_module.get_connection()
        rows = conn.execute("SELECT signal_name, commentary FROM signal_intelligence").fetchall()
        conn.close()

        signal_names = [r["signal_name"] for r in rows]
        assert "asx_volatility" in signal_names
        assert "market_hiring" not in signal_names  # delta < 5
        asx_row = next(r for r in rows if r["signal_name"] == "asx_volatility")
        assert "ASX" in asx_row["commentary"]


def test_api_get_signal_intelligence(si_db):
    """GET /api/signal-intelligence/{week_iso} should return records keyed by signal."""
    import json as _json
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        articles = _json.dumps([{"title": "Test", "url": "http://x.com", "published": "2026-03-20", "snippet": "foo"}])
        conn.execute(
            """INSERT INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "ASX rose sharply."),
        )
        conn.commit()
        conn.close()

        from flatwhite.dashboard.api import api_get_signal_intelligence
        result = api_get_signal_intelligence("2026-W13")
        data = _json.loads(result.body)
        assert "asx_volatility" in data
        assert data["asx_volatility"]["commentary"] == "ASX rose sharply."
        assert isinstance(data["asx_volatility"]["articles"], list)


def test_api_refresh_signal_intelligence_returns_refreshing(si_db):
    """POST /api/signal-intelligence/refresh should return refreshing:True for existing record."""
    import json as _json, asyncio
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        articles = _json.dumps([])
        conn.execute(
            """INSERT INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "Old commentary"),
        )
        conn.commit()
        conn.close()

        from flatwhite.dashboard.api import api_refresh_signal_intelligence

        class FakeRequest:
            async def json(self):
                return {"signal_name": "asx_volatility", "week_iso": "2026-W13"}

        with patch("flatwhite.signals.signal_intelligence._fetch_articles", return_value=[]):
            with patch("flatwhite.signals.signal_intelligence._synthesise", return_value="New commentary"):
                result = asyncio.get_event_loop().run_until_complete(
                    api_refresh_signal_intelligence(FakeRequest())
                )
                data = _json.loads(result.body)
                assert data["refreshing"] is True
                assert data["signal_name"] == "asx_volatility"


def test_api_refresh_signal_intelligence_404_for_missing_record(si_db):
    """POST /api/signal-intelligence/refresh should return 404 if record doesn't exist."""
    import json as _json, asyncio
    with patch.object(db_module, "DB_PATH", si_db):
        from flatwhite.dashboard.api import api_refresh_signal_intelligence

        class FakeRequest:
            async def json(self):
                return {"signal_name": "nonexistent_signal", "week_iso": "2026-W13"}

        result = asyncio.get_event_loop().run_until_complete(
            api_refresh_signal_intelligence(FakeRequest())
        )
        data = _json.loads(result.body)
        assert result.status_code == 404
        assert "error" in data


def test_preview_prompt_returns_context_breakdown(si_db):
    """POST /api/preview-prompt for pulse should return context_breakdown."""
    import json as _json
    import asyncio
    with patch.object(db_module, "DB_PATH", si_db):
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.2, 60.0, 1.0, "2026-W13")

        with patch("flatwhite.signals.macro_context.fetch_macro_headlines", return_value=""):
            with patch("flatwhite.db.get_interactions", return_value=[]):
                from flatwhite.dashboard.api import api_preview_prompt

                class FakeRequest:
                    async def json(self):
                        return {"section": "pulse", "data": {}}

                result = asyncio.get_event_loop().run_until_complete(api_preview_prompt(FakeRequest()))
                data = _json.loads(result.body)
                assert "context_breakdown" in data
                assert "signals" in data["context_breakdown"]
                assert "signal_intelligence" in data["context_breakdown"]
                assert "composite" in data["context_breakdown"]
