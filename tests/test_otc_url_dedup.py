"""Cross-week URL dedup for Off the Clock lifestyle items.

Evergreen RSS items (e.g. "Best new restaurants in Sydney 2026") would
otherwise re-insert as a fresh row every week they remain in the feed,
making the OTC dashboard show the same stale content week after week.
_insert_lifestyle_item must skip any URL it has seen in any prior week.
"""
from __future__ import annotations

from unittest.mock import patch

import flatwhite.db as db_module
from flatwhite.editorial.off_the_clock import _insert_lifestyle_item


def test_url_dedup_skips_url_seen_in_prior_week(temp_db):
    """An identical URL in a later week must not be inserted."""
    with patch.object(db_module, "DB_PATH", temp_db):
        # Week 1: first time we see the article — gets inserted.
        first_id = _insert_lifestyle_item(
            title="Best new bars in Sydney 2026",
            body="A round-up.",
            source="otc_rss_concrete_playground_sydney",
            url="https://example.com/best-bars-2026",
            city="sydney",
            category_hint="going",
            week_iso="2026-W22",
            published_at="2026-05-25T01:00:00+00:00",
        )
        assert first_id > 0

        # Week 2: same URL re-surfaces in the feed — must be skipped.
        second_id = _insert_lifestyle_item(
            title="Best new bars in Sydney 2026",
            body="A round-up.",
            source="otc_rss_concrete_playground_sydney",
            url="https://example.com/best-bars-2026",
            city="sydney",
            category_hint="going",
            week_iso="2026-W23",
            published_at="2026-06-01T01:00:00+00:00",
        )
        assert second_id == 0, "duplicate URL across weeks must be skipped"

        # Only one row exists for this URL across all weeks.
        conn = db_module.get_connection()
        n = conn.execute(
            "SELECT COUNT(*) FROM raw_items WHERE url = ?",
            ("https://example.com/best-bars-2026",),
        ).fetchone()[0]
        conn.close()
        assert n == 1


def test_url_dedup_does_not_block_distinct_urls(temp_db):
    """Different URLs from the same source still insert."""
    with patch.object(db_module, "DB_PATH", temp_db):
        a = _insert_lifestyle_item(
            title="Article A", body=None, source="otc_rss_x",
            url="https://example.com/a", city=None, category_hint="eating",
            week_iso="2026-W22", published_at="2026-05-25T01:00:00+00:00",
        )
        b = _insert_lifestyle_item(
            title="Article B", body=None, source="otc_rss_x",
            url="https://example.com/b", city=None, category_hint="eating",
            week_iso="2026-W22", published_at="2026-05-26T01:00:00+00:00",
        )
        assert a > 0 and b > 0 and a != b


def test_url_dedup_ignores_null_urls(temp_db):
    """Items without a URL should not all collapse into a single dedup'd row."""
    with patch.object(db_module, "DB_PATH", temp_db):
        a = _insert_lifestyle_item(
            title="Manual whisper A", body=None, source="otc_manual",
            url=None, city=None, category_hint="eating",
            week_iso="2026-W22", published_at=None,
        )
        b = _insert_lifestyle_item(
            title="Manual whisper B", body=None, source="otc_manual",
            url=None, city=None, category_hint="eating",
            week_iso="2026-W22", published_at=None,
        )
        assert a > 0 and b > 0 and a != b
