"""Tests for /api/backfill endpoint — employer snapshot seeding."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import pytest
import flatwhite.db as db_module


@pytest.fixture
def backfill_db(tmp_path: Path):
    db_path = tmp_path / "backfill_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO employer_watchlist (employer_name, sector, careers_url) VALUES ('ANZ', 'banking', 'http://anz.com')"
        )
        emp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO employer_snapshots (employer_id, open_roles_count, snapshot_date, week_iso, extraction_method, ats_platform) VALUES (?, 150, '2026-03-27', '2026-W13', 'html_scrape', 'workday')",
            (emp_id,),
        )
        conn.commit()
        conn.close()
        yield db_path


def test_backfill_seeds_employer_snapshots(backfill_db):
    """POST /api/backfill should copy W13 employer snapshots as W12."""
    with patch.object(db_module, "DB_PATH", backfill_db):
        # Patch run_backfill to avoid real external calls
        with patch("flatwhite.pulse.backfill.run_backfill") as mock_rb:
            with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
                from flatwhite.dashboard.api import api_backfill
                import asyncio

                class FakeRequest:
                    async def json(self):
                        return {"target_week": "2026-W12"}

                result = asyncio.get_event_loop().run_until_complete(api_backfill(FakeRequest()))
                data = json.loads(result.body)
                assert data["seeded_employers"] > 0

                conn = db_module.get_connection()
                rows = conn.execute(
                    "SELECT * FROM employer_snapshots WHERE week_iso = '2026-W12'"
                ).fetchall()
                conn.close()
                assert len(rows) == 1
                assert rows[0]["open_roles_count"] == 150


def test_backfill_skips_existing_target_week(backfill_db):
    """If target_week already has employer snapshots, don't re-seed."""
    with patch.object(db_module, "DB_PATH", backfill_db):
        conn = db_module.get_connection()
        emp_id = conn.execute("SELECT id FROM employer_watchlist LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO employer_snapshots (employer_id, open_roles_count, snapshot_date, week_iso) VALUES (?, 140, '2026-03-21', '2026-W12')",
            (emp_id,),
        )
        conn.commit()
        conn.close()

        with patch("flatwhite.pulse.backfill.run_backfill"):
            with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
                from flatwhite.dashboard.api import api_backfill
                import asyncio

                class FakeRequest:
                    async def json(self):
                        return {"target_week": "2026-W12"}

                result = asyncio.get_event_loop().run_until_complete(api_backfill(FakeRequest()))
                data = json.loads(result.body)
                # seeded_employers should be 0 — already existed
                assert data["seeded_employers"] == 0
