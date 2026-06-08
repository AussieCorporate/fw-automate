"""Tests for section_outputs DB functions."""
import sqlite3
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


# Old section_outputs schema as created by pre-saved_at versions of the app.
# Live databases still carry this shape; migrate_db() must add saved_at.
_LEGACY_SECTION_OUTPUTS_SQL = """
    CREATE TABLE section_outputs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_iso TEXT NOT NULL,
        section TEXT NOT NULL,
        output_text TEXT NOT NULL,
        model_used TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(week_iso, section)
    )
"""


@pytest.fixture
def so_db(tmp_path: Path):
    db_path = tmp_path / "so_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def test_section_outputs_table_exists(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        conn = db_module.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "section_outputs" in tables


def test_save_and_load_section_output(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        db_module.save_section_output("2026-W13", "pulse", "Some pulse text", "claude-sonnet-4-6")
        outputs = db_module.load_all_section_outputs("2026-W13")
        assert "pulse" in outputs
        assert outputs["pulse"]["output_text"] == "Some pulse text"
        assert outputs["pulse"]["model_used"] == "claude-sonnet-4-6"


def test_save_replaces_existing_output(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        db_module.save_section_output("2026-W13", "pulse", "Old text", None)
        db_module.save_section_output("2026-W13", "pulse", "New text", "claude-haiku-4-5")
        outputs = db_module.load_all_section_outputs("2026-W13")
        assert outputs["pulse"]["output_text"] == "New text"
        assert len([k for k in outputs if k == "pulse"]) == 1


def test_load_returns_only_matching_week(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        db_module.save_section_output("2026-W13", "pulse", "W13 text", None)
        db_module.save_section_output("2026-W12", "pulse", "W12 text", None)
        outputs = db_module.load_all_section_outputs("2026-W13")
        assert outputs["pulse"]["output_text"] == "W13 text"
        w12 = db_module.load_all_section_outputs("2026-W12")
        assert w12["pulse"]["output_text"] == "W12 text"


def test_load_returns_empty_dict_for_unknown_week(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        outputs = db_module.load_all_section_outputs("2026-W99")
        assert outputs == {}


def test_migrate_adds_saved_at_to_legacy_section_outputs(tmp_path: Path):
    """Regression: a legacy section_outputs table (no saved_at column) must be
    migrated so save/load works. Reproduces the dashboard 'Internal Server Error'
    (unparseable JSON) from POST /api/section-output/{section}.
    """
    db_path = tmp_path / "legacy.db"

    # Simulate a database created by an older app version.
    conn = sqlite3.connect(db_path)
    conn.execute(_LEGACY_SECTION_OUTPUTS_SQL)
    conn.commit()
    conn.close()

    with patch.object(db_module, "DB_PATH", db_path):
        # init_db() -> migrate_db() must add the missing column.
        db_module.init_db()

        conn = db_module.get_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(section_outputs)").fetchall()}
        conn.close()
        assert "saved_at" in cols

        # The previously-failing write + read must now succeed.
        db_module.save_section_output("2026-W22", "pulse", "hi", "test")
        outputs = db_module.load_all_section_outputs("2026-W22")
        assert outputs["pulse"]["output_text"] == "hi"
