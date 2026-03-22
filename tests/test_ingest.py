"""Integration tests for data ingestion: dedup, signal storage, schema tables."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import flatwhite.db as db_module


def test_raw_item_deduplication(temp_db: Path) -> None:
    """Inserting the same (title, source, week_iso) twice should not create a duplicate row."""
    with patch.object(db_module, "DB_PATH", temp_db):
        week = "2026-W12"
        first_id = db_module.insert_raw_item(
            title="Duplicate test item",
            body="Body text",
            source="reddit_rss",
            url="https://example.com/1",
            lane="editorial",
            subreddit="auscorp",
            week_iso=week,
        )
        second_id = db_module.insert_raw_item(
            title="Duplicate test item",
            body="Body text",
            source="reddit_rss",
            url="https://example.com/1",
            lane="editorial",
            subreddit="auscorp",
            week_iso=week,
        )

        assert first_id > 0
        assert second_id == first_id

        conn = db_module.get_connection()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM raw_items WHERE title = ? AND source = ? AND week_iso = ?",
            ("Duplicate test item", "reddit_rss", week),
        ).fetchone()["cnt"]
        conn.close()
        assert count == 1


def test_different_weeks_not_deduped(temp_db: Path) -> None:
    """Same title+source in different weeks should create separate rows."""
    with patch.object(db_module, "DB_PATH", temp_db):
        id_w12 = db_module.insert_raw_item(
            title="Weekly item",
            body="Body",
            source="reddit_rss",
            url=None,
            lane="editorial",
            subreddit="auscorp",
            week_iso="2026-W12",
        )
        id_w13 = db_module.insert_raw_item(
            title="Weekly item",
            body="Body",
            source="reddit_rss",
            url=None,
            lane="editorial",
            subreddit="auscorp",
            week_iso="2026-W13",
        )

        assert id_w12 > 0
        assert id_w13 > 0
        assert id_w12 != id_w13


def test_signal_storage_and_upsert(temp_db: Path) -> None:
    """insert_signal should store signals and upsert on (signal_name, week_iso) conflict."""
    with patch.object(db_module, "DB_PATH", temp_db):
        week = "2026-W12"
        first_id = db_module.insert_signal(
            signal_name="job_anxiety",
            lane="pulse",
            area="labour_market",
            raw_value=60.0,
            normalised_score=40.0,
            source_weight=1.0,
            week_iso=week,
        )
        assert first_id > 0

        # Upsert with new value
        second_id = db_module.insert_signal(
            signal_name="job_anxiety",
            lane="pulse",
            area="labour_market",
            raw_value=65.0,
            normalised_score=42.0,
            source_weight=1.0,
            week_iso=week,
        )

        # Should have replaced, so only one row
        conn = db_module.get_connection()
        rows = conn.execute(
            "SELECT * FROM signals WHERE signal_name = ? AND week_iso = ?",
            ("job_anxiety", week),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["normalised_score"] == 42.0


def test_employer_tables_exist_after_init(temp_db: Path) -> None:
    """init_db should create employer_watchlist, employer_snapshots, employer_roles, extraction_health."""
    with patch.object(db_module, "DB_PATH", temp_db):
        conn = db_module.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()

        table_names = {row["name"] for row in tables}
        expected = {
            "employer_watchlist",
            "employer_snapshots",
            "employer_roles",
            "extraction_health",
        }
        for table in expected:
            assert table in table_names, f"Table {table} missing after init_db"


def test_all_core_tables_exist(temp_db: Path) -> None:
    """init_db should create all core tables defined in the schema."""
    with patch.object(db_module, "DB_PATH", temp_db):
        conn = db_module.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()

        table_names = {row["name"] for row in tables}
        expected = {
            "signals",
            "pulse_history",
            "raw_items",
            "curated_items",
            "editor_decisions",
            "newsletters",
            "reddit_topic_clusters",
            "polls",
            "drafts",
        }
        for table in expected:
            assert table in table_names, f"Table {table} missing after init_db"
