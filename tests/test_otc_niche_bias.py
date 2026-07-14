"""Off the Clock should surface niche small businesses over mass outlets
(Concrete Playground, Time Out, the Guardian, SMH, Gourmet Traveller) that
already get mass coverage. Before this fix, load_otc_candidates ranked
purely on weighted_composite, so a mass-outlet story with a slightly higher
score always crowded out an equally-relevant niche one.
"""
from __future__ import annotations

from unittest.mock import patch

import flatwhite.db as db_module
from flatwhite.dashboard.state import load_otc_candidates

TEST_WEEK = "2026-W28"


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


def test_mass_outlet_ranks_below_niche_at_equal_score(temp_db):
    _seed_item(
        temp_db, "New Sydney opening at Concrete Playground",
        "https://concreteplayground.com/sydney/new-opening", "otc_eating", 6.0,
    )
    _seed_item(
        temp_db, "A tiny Marrickville sandwich shop opened",
        "https://smallbusiness-example.com.au/marrickville-sandwiches", "otc_eating", 6.0,
    )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    titles = [row["title"] for row in grouped["otc_eating"]]
    assert titles[0] == "A tiny Marrickville sandwich shop opened"
    assert titles[1] == "New Sydney opening at Concrete Playground"


def test_mass_outlet_still_surfaces_if_nothing_niche_beats_it(temp_db):
    _seed_item(
        temp_db, "Only item this week, from Concrete Playground",
        "https://concreteplayground.com/melbourne/only-item", "otc_going", 5.0,
    )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    assert len(grouped["otc_going"]) == 1
    assert grouped["otc_going"][0]["title"] == "Only item this week, from Concrete Playground"


def test_google_news_mass_outlet_ranks_below_niche_at_equal_score(temp_db):
    # Google News RSS items store a news.google.com redirect URL (not the
    # publisher's real domain), so the URL-based check alone can't see this
    # is a mass outlet - the title's "- Publisher Name" suffix must catch it.
    _seed_item(
        temp_db, "Melbourne's best rooftop bar is getting a huge upgrade - Time Out Worldwide",
        "https://news.google.com/rss/articles/CBMi_fake_time_out_article", "otc_going", 6.0,
    )
    _seed_item(
        temp_db, "A tiny Brunswick wine bar just opened",
        "https://smallbusiness-example.com.au/brunswick-wine-bar", "otc_going", 6.0,
    )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    titles = [row["title"] for row in grouped["otc_going"]]
    assert titles[0] == "A tiny Brunswick wine bar just opened"
    assert titles[1] == "Melbourne's best rooftop bar is getting a huge upgrade - Time Out Worldwide"


def test_cap_still_applies_after_niche_rerank(temp_db):
    # 6 niche items with descending scores; still capped to 3, still ordered by score.
    for i in range(6):
        _seed_item(
            temp_db, f"Niche eating item {i}",
            f"https://example.com/eating-{i}", "otc_eating", 6.0 - i,
        )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    assert len(grouped["otc_eating"]) == 3
    scores = [row["weighted_composite"] for row in grouped["otc_eating"]]
    assert scores == [6.0, 5.0, 4.0]
