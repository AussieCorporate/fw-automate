"""Tests for pull_google_news_top_au scraper."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import flatwhite.db as db_module
import flatwhite.editorial.google_news_top_au as top_au_module


@pytest.fixture
def top_db(tmp_path: Path):
    db_path = tmp_path / "top_au_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def _fake_entries(n=3, prefix="Story"):
    return [
        {
            "title": f"{prefix} {i}",
            "body": f"Body of story {i}",
            "url": f"https://example.com/story-{prefix}-{i}",
            "published": "",
        }
        for i in range(n)
    ]


def test_inserts_up_to_5_items(top_db):
    # Each query returns 3 unique entries (different prefix per call via side_effect)
    call_count = [0]
    def side_effect(url, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        return _fake_entries(3, prefix=f"Q{idx}")
    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", side_effect=side_effect):
        count = top_au_module.pull_google_news_top_au()
    assert count == 5


def test_deduplicates_by_url(top_db):
    # All queries return the same 3 entries — only 3 unique URLs total
    same_entries = _fake_entries(3, prefix="Same")
    fake_fetch = MagicMock(return_value=same_entries)
    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", fake_fetch):
        count = top_au_module.pull_google_news_top_au()
    assert count == 3  # capped at unique URLs (3 here)


def test_items_inserted_as_big_conversation_seed(top_db):
    fake_fetch = MagicMock(return_value=_fake_entries(3))
    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", fake_fetch):
        top_au_module.pull_google_news_top_au()
    with patch.object(db_module, "DB_PATH", top_db):
        conn = db_module.get_connection()
        rows = conn.execute(
            "SELECT section, confidence_tag FROM curated_items"
        ).fetchall()
        conn.close()
    assert all(r["section"] == "big_conversation_seed" for r in rows)
    assert all(r["confidence_tag"] == "yellow" for r in rows)


def test_fetch_error_on_one_query_does_not_abort(top_db):
    # First query raises, rest succeed
    def side_effect(url, **kwargs):
        if "australia%20business%20news" in url:
            raise Exception("network error")
        return _fake_entries(3, prefix="Ok")

    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", side_effect=side_effect):
        count = top_au_module.pull_google_news_top_au()
    assert count > 0  # at least some items from other queries
