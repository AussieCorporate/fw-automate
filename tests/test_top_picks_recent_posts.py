"""PS Top Picks currently only shows click-ranked links, so a FEATURE story
(no click-link, since the story runs inline in the newsletter) never
appears - the click data that does show is just the OTHER links in that
same article. This exposes the raw list of recent editions so Victor can
manually flag which ones were features and include them.
"""
from __future__ import annotations

import json

import flatwhite.editorial.beehiiv_picks as beehiiv_picks


def test_recent_posts_endpoint_returns_editions_for_feature_flagging(monkeypatch):
    fake_posts = [
        {
            "id": "p1",
            "title": "Why 'no budget' is a cop-out when negotiating pay",
            "slug": "no-budget-cop-out",
            "publish_date": "2026-07-10T00:00:00+00:00",
            "web_url": "https://thepickandscroll.beehiiv.com/p/no-budget-cop-out",
        },
    ]
    monkeypatch.setattr(beehiiv_picks, "fetch_recent_posts", lambda days=7: fake_posts)

    from flatwhite.dashboard.api import api_top_picks_recent_posts
    result = api_top_picks_recent_posts()
    data = json.loads(result.body)
    assert data["posts"] == fake_posts


def test_recent_posts_endpoint_survives_fetch_error(monkeypatch):
    def _raise(days=7):
        raise RuntimeError("beehiiv API down")
    monkeypatch.setattr(beehiiv_picks, "fetch_recent_posts", _raise)

    from flatwhite.dashboard.api import api_top_picks_recent_posts
    result = api_top_picks_recent_posts()
    assert result.status_code == 500
    data = json.loads(result.body)
    assert data["posts"] == []
