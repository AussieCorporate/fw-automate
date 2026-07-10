"""Off The Clock ingest guards: no uncategorised items, no inflated counts."""

from unittest.mock import patch

from flatwhite.editorial import off_the_clock


def test_feed_without_category_hint_is_skipped():
    """Null-hint feeds used to insert lifestyle_category=NULL and let the
    classifier guess, which put career essays in 'Going'."""
    feed = {"name": "CP Sydney", "url": "https://example.com/feed", "city": "sydney"}
    result = off_the_clock._fetch_rss_feed(feed, 10, 7, "2026-W28")
    assert result["count"] == 0
    assert "no category_hint" in result["error"]


def test_count_excludes_items_skipped_as_duplicates():
    """_insert_lifestyle_item returns 0 for an already-seen URL. Counting
    unconditionally overstated how much fresh content a run added."""
    feed = {
        "name": "Good Food", "url": "https://example.com/feed",
        "category_hint": "eating", "city": "national",
    }
    entries = [
        {"title": "New", "body": "b", "url": "https://x.test/1", "published": "2026-07-09T00:00:00Z"},
        {"title": "Dupe", "body": "b", "url": "https://x.test/2", "published": "2026-07-09T00:00:00Z"},
    ]
    # 41 = a fresh row id, 0 = URL seen in a prior week and skipped.
    with patch.object(off_the_clock, "fetch_rss", return_value=entries), \
         patch.object(off_the_clock, "_insert_lifestyle_item", side_effect=[41, 0]):
        result = off_the_clock._fetch_rss_feed(feed, 10, 3650, "2026-W28")

    assert result["count"] == 1, "duplicate must not be counted as inserted"


def test_same_title_from_a_different_feed_is_not_reinserted(tmp_path, monkeypatch):
    """One CP article syndicates through several feeds under different URLs."""
    import flatwhite.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()

    first = off_the_clock._insert_lifestyle_item(
        title="MIFF's 2026 Program Is Here",
        body=None, source="otc_rss_cp_sydney_arts", url="https://cp.test/syd/miff",
        city="sydney", category_hint="going", week_iso="2026-W28",
    )
    second = off_the_clock._insert_lifestyle_item(
        title="MIFF's 2026 Program Is Here",   # same story, different feed + URL
        body=None, source="otc_rss_cp_melbourne_arts", url="https://cp.test/melb/miff",
        city="melbourne", category_hint="going", week_iso="2026-W28",
    )
    assert first > 0
    assert second == 0, "same title from another feed must not create a second row"
