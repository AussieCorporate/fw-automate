"""Tests for update_raw_item_engagement DB function."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def eng_db(tmp_path: Path):
    db_path = tmp_path / "eng_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def _insert_item(db_path, title, url, week_iso="2026-W13"):
    with patch.object(db_module, "DB_PATH", db_path):
        conn = db_module.get_connection()
        conn.execute(
            "INSERT INTO raw_items (title, source, url, lane, pulled_at, week_iso) "
            "VALUES (?, 'r/auscorp', ?, 'editorial', datetime('now'), ?)",
            (title, url, week_iso),
        )
        conn.commit()
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return item_id


def test_engagement_columns_exist(eng_db):
    with patch.object(db_module, "DB_PATH", eng_db):
        conn = db_module.get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(raw_items)").fetchall()}
        conn.close()
        assert "post_score" in cols
        assert "comment_engagement" in cols


def test_update_raw_item_engagement(eng_db):
    item_id = _insert_item(eng_db, "Test post", "https://reddit.com/test1")
    with patch.object(db_module, "DB_PATH", eng_db):
        db_module.update_raw_item_engagement(item_id, post_score=42, comment_engagement=155)
        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT post_score, comment_engagement FROM raw_items WHERE id = ?", (item_id,)
        ).fetchone()
        conn.close()
        assert row["post_score"] == 42
        assert row["comment_engagement"] == 155


def test_update_engagement_does_not_affect_other_rows(eng_db):
    id1 = _insert_item(eng_db, "Post 1", "https://reddit.com/p1")
    id2 = _insert_item(eng_db, "Post 2", "https://reddit.com/p2")
    with patch.object(db_module, "DB_PATH", eng_db):
        db_module.update_raw_item_engagement(id1, post_score=10, comment_engagement=20)
        conn = db_module.get_connection()
        row2 = conn.execute(
            "SELECT post_score, comment_engagement FROM raw_items WHERE id = ?", (id2,)
        ).fetchone()
        conn.close()
        assert row2["post_score"] is None
        assert row2["comment_engagement"] is None


def test_update_engagement_with_zero_values(eng_db):
    item_id = _insert_item(eng_db, "Zero post", "https://reddit.com/zero")
    with patch.object(db_module, "DB_PATH", eng_db):
        db_module.update_raw_item_engagement(item_id, post_score=0, comment_engagement=0)
        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT post_score, comment_engagement FROM raw_items WHERE id = ?", (item_id,)
        ).fetchone()
        conn.close()
        assert row["post_score"] == 0
        assert row["comment_engagement"] == 0
