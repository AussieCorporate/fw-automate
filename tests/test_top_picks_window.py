"""Top Picks must show ONE window only, never a cumulative list.

Victor, 10 Aug 2026: "the flat white dashboard for top picks, need to ONLY show
the last 7 days of top picks + feature stories, it's not a cumulative list (its
getting too long). I just need the last 7 days mate"

The seed features (fw_feature_seed.json) were bolted on with no date filter at
all, so six stories from 16-20 July sat permanently at the top of a list that is
supposed to cover the last seven days. Measured on the live dashboard that day:
24 business items, 6 of them from July.
"""
import datetime as dt
import json

from flatwhite.dashboard import api


def _seed(tmp_path, monkeypatch, records):
    p = tmp_path / "fw_feature_seed.json"
    p.write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setenv("FW_TOP_PICKS_FEATURE_SEED", str(p))
    return p


def _no_scraping(monkeypatch):
    """Neutralise every network call so only the seed path is under test."""
    import flatwhite.editorial.beehiiv_picks as bp
    from flatwhite.editorial import ps_picks_feed
    monkeypatch.setattr(bp, "scrape_top_picks", lambda *a, **k: [])
    monkeypatch.setattr(bp, "scrape_one_more_scroll", lambda *a, **k: [])
    monkeypatch.setattr(ps_picks_feed, "read_feed", lambda *a, **k: {"business": [], "odd": []})


def test_seed_features_outside_the_window_are_dropped(tmp_path, monkeypatch):
    _no_scraping(monkeypatch)
    today = dt.datetime.now(dt.timezone.utc).date()
    recent = (today - dt.timedelta(days=2)).isoformat()
    stale = (today - dt.timedelta(days=21)).isoformat()
    _seed(tmp_path, monkeypatch, [
        {"url": "https://x/recent", "title": "Recent feature", "summary": "s", "edition_date": recent},
        {"url": "https://x/stale", "title": "Three weeks old", "summary": "s", "edition_date": stale},
    ])

    out = api._combined_top_picks(days=7)
    urls = {b["url"] for b in out["business"]}

    assert "https://x/recent" in urls
    assert "https://x/stale" not in urls


def test_seed_features_respect_an_explicit_calendar_range(tmp_path, monkeypatch):
    _no_scraping(monkeypatch)
    _seed(tmp_path, monkeypatch, [
        {"url": "https://x/in", "title": "In range", "summary": "s", "edition_date": "2026-08-05"},
        {"url": "https://x/out", "title": "Out of range", "summary": "s", "edition_date": "2026-07-19"},
    ])

    start = dt.datetime(2026, 8, 3, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 8, 10, 23, 59, 59, tzinfo=dt.timezone.utc)
    out = api._combined_top_picks(days=7, start=start, end=end)
    urls = {b["url"] for b in out["business"]}

    assert urls == {"https://x/in"}


def test_undated_seed_feature_is_dropped(tmp_path, monkeypatch):
    """An item we cannot place in time cannot be shown to be in the window."""
    _no_scraping(monkeypatch)
    _seed(tmp_path, monkeypatch, [
        {"url": "https://x/undated", "title": "No date", "summary": "s"},
    ])

    out = api._combined_top_picks(days=7)

    assert out["business"] == []
