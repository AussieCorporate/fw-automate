"""Tests for section_outputs DB functions."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


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
