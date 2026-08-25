"""Reddit product threads for Odd Picks, gated on engagement.

Victor approved Reddit here on 26 Aug 2026 on one condition: "ONLY if there's
high engagement on that post." This does NOT reopen Reddit for Off the Clock -
that exclusion stands.

The floors are also a data-quality gate. Reddit access from this machine is
intermittent: one call succeeds, the next 429s, and a degraded response comes
back with scores like 2-15 on a million-member sub whose real top-of-week is
in the thousands. A high bar means a bad response yields nothing rather than
something wrong.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.db as db_module
from flatwhite.editorial import off_the_clock as otc


def _posts(*specs):
    return [{"title": t, "body": "b", "url": f"https://reddit.com/{i}",
             "published": None, "score": s, "num_comments": c}
            for i, (t, s, c) in enumerate(specs)]


def _run(tmp_path, posts_by_sub, cfg=None):
    cfg = cfg or {
        "reddit_review_subs": [{"name": "BuyItForLife", "min_score": 1000, "min_comments": 40}],
        "reddit_review_time_filter": "week",
    }

    def fake_fetch(sub, time_filter="week", limit=15):
        got = posts_by_sub[sub]
        if isinstance(got, Exception):
            raise got
        return got

    db_path = tmp_path / "reddit_reviews.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        with patch.object(otc, "_load_config", lambda: cfg), \
             patch("flatwhite.utils.http.fetch_reddit_top_posts", fake_fetch):
            kept = otc.pull_reddit_reviews()
        conn = db_module.get_connection()
        rows = conn.execute("SELECT title, source FROM raw_items").fetchall()
        conn.close()
    return kept, [dict(r) for r in rows]


def test_a_genuinely_high_engagement_post_is_kept(tmp_path):
    kept, rows = _run(tmp_path, {"BuyItForLife": _posts(
        ("The boots I have worn daily for eleven years", 4200, 310))})
    assert kept == 1
    assert "4200 upvotes" in rows[0]["title"]
    assert rows[0]["source"].startswith("review_reddit")


def test_a_low_score_post_is_rejected_however_many_comments(tmp_path):
    kept, rows = _run(tmp_path, {"BuyItForLife": _posts(("A quiet thread", 15, 600))})
    assert kept == 0 and rows == []


def test_a_high_score_post_with_few_comments_is_rejected(tmp_path):
    """Upvotes alone can be a photo that got scrolled past. Both floors apply."""
    kept, rows = _run(tmp_path, {"BuyItForLife": _posts(("A nice photo", 9000, 3))})
    assert kept == 0 and rows == []


def test_a_degraded_reddit_response_yields_nothing(tmp_path):
    """Seen live: top-of-week came back with scores of 2-15 on a sub whose real
    top is in the thousands. The bar must reject that rather than ship it."""
    kept, rows = _run(tmp_path, {"BuyItForLife": _posts(
        ("$8 at a Habitat Restore", 5, 0), ("Found a chair", 4, 0), ("Silicone", 3, 1))})
    assert kept == 0 and rows == []


def test_an_unreachable_subreddit_is_reported_not_crashed(tmp_path, capsys):
    kept, rows = _run(tmp_path, {"BuyItForLife": RuntimeError("429 Too Many Requests")})
    assert kept == 0 and rows == []
    assert "unreachable" in capsys.readouterr().out


def test_reddit_review_items_carry_the_prefix_the_otc_classifier_skips(tmp_path):
    _, rows = _run(tmp_path, {"BuyItForLife": _posts(("Great boots", 4200, 310))})
    assert rows[0]["source"].startswith(otc.REVIEW_SOURCE_PREFIX)
