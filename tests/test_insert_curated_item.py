"""Tests for insert_curated_item DB function."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def ci_db(tmp_path: Path):
    db_path = tmp_path / "ci_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def _insert_raw(db_path, title, url, week_iso="2026-W13"):
    with patch.object(db_module, "DB_PATH", db_path):
        conn = db_module.get_connection()
        conn.execute(
            "INSERT INTO raw_items (title, source, url, lane, pulled_at, week_iso) "
            "VALUES (?, 'google_news_top_au', ?, 'editorial', datetime('now'), ?)",
            (title, url, week_iso),
        )
        conn.commit()
        raw_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return raw_id


def test_insert_curated_item_basic(ci_db):
    raw_id = _insert_raw(ci_db, "RBA raises rates", "https://abc.net.au/rba")
    with patch.object(db_module, "DB_PATH", ci_db):
        curated_id = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="RBA raises cash rate by 25bp.",
            score_relevance=4,
            score_novelty=4,
            score_reliability=4,
            score_tension=4,
            score_usefulness=4,
            weighted_composite=4.0,
            confidence_tag="yellow",
        )
        assert curated_id is not None
        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT section, summary, weighted_composite, confidence_tag FROM curated_items WHERE id = ?",
            (curated_id,),
        ).fetchone()
        conn.close()
        assert row["section"] == "big_conversation_seed"
        assert row["weighted_composite"] == 4.0
        assert row["confidence_tag"] == "yellow"


def test_insert_curated_item_duplicate_returns_none(ci_db):
    raw_id = _insert_raw(ci_db, "ASX drops", "https://afr.com/asx")
    with patch.object(db_module, "DB_PATH", ci_db):
        first = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="ASX drops 2%.",
            score_relevance=4, score_novelty=4, score_reliability=4,
            score_tension=4, score_usefulness=4, weighted_composite=4.0,
        )
        second = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="ASX drops 2%.",
            score_relevance=4, score_novelty=4, score_reliability=4,
            score_tension=4, score_usefulness=4, weighted_composite=4.0,
        )
        assert first is not None
        assert second is None  # duplicate — INSERT OR IGNORE


def test_insert_curated_item_without_confidence_tag(ci_db):
    raw_id = _insert_raw(ci_db, "Budget surplus", "https://abc.net.au/budget")
    with patch.object(db_module, "DB_PATH", ci_db):
        curated_id = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="Government announces surplus.",
            score_relevance=4, score_novelty=4, score_reliability=4,
            score_tension=4, score_usefulness=4, weighted_composite=4.0,
        )
        assert curated_id is not None
