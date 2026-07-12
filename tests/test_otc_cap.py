"""Off the Clock candidates must be capped per category by
config.yaml's off_the_clock.candidates_per_category (default 3).

load_otc_candidates previously returned every candidate in a category
(docstring: "Returns all candidates (no cap)"). That flooded the editor
pick UI with a dumping ground instead of a ranked shortlist.
"""
from __future__ import annotations

from unittest.mock import patch

import flatwhite.db as db_module
from flatwhite.dashboard.state import load_otc_candidates

TEST_WEEK = "2026-W22"


def _seed_item(db_path, title, url, category, weighted_composite, week_iso=TEST_WEEK):
    with patch.object(db_module, "DB_PATH", db_path):
        raw_id = db_module.insert_raw_item(
            title=title,
            body="A round-up.",
            source="otc_rss_test",
            url=url,
            lane="lifestyle",
            subreddit=None,
            week_iso=week_iso,
        )
        db_module.insert_curated_item(
            raw_item_id=raw_id,
            section=category,
            summary=f"Summary for {title}",
            score_relevance=4,
            score_novelty=4,
            score_reliability=4,
            score_tension=4,
            score_usefulness=4,
            weighted_composite=weighted_composite,
        )


def test_otc_capped_to_three_per_category(temp_db):
    # 6 otc_eating items, descending weighted_composite
    for i in range(6):
        _seed_item(
            temp_db,
            title=f"Eating item {i}",
            url=f"https://example.com/eating-{i}",
            category="otc_eating",
            weighted_composite=6.0 - i,
        )

    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)

    assert len(grouped["otc_eating"]) == 3
    scores = [row["weighted_composite"] for row in grouped["otc_eating"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] >= scores[-1]
    # the 3 kept are the 3 highest
    assert scores == [6.0, 5.0, 4.0]


def test_cap_is_a_ceiling_not_a_floor(temp_db):
    # 2 otc_watching items: fewer than the cap, must be unchanged
    for i in range(2):
        _seed_item(
            temp_db,
            title=f"Watching item {i}",
            url=f"https://example.com/watching-{i}",
            category="otc_watching",
            weighted_composite=3.0 - i,
        )

    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)

    assert len(grouped["otc_watching"]) == 2
