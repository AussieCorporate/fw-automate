"""Tests for fetch_reddit_top_posts.

Reddit's unauthenticated .json API has been 403-blocked since the 2023
lockdown and the script-app OAuth grant is broken, so the only working path
is /top/.rss with a synthetic position-based score. The test pins that path
to a canned RSS payload (no network).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from flatwhite.utils import http as http_mod


_CANNED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>top scoring links : auscorp</title>
  <entry>
    <title>Top auscorp post #1</title>
    <link href="https://www.reddit.com/r/auscorp/comments/aaa/post_one/" />
    <published>2026-05-30T01:00:00+00:00</published>
    <summary>body one</summary>
  </entry>
  <entry>
    <title>Top auscorp post #2</title>
    <link href="https://www.reddit.com/r/auscorp/comments/bbb/post_two/" />
    <published>2026-05-29T01:00:00+00:00</published>
    <summary>body two</summary>
  </entry>
  <entry>
    <title>Top auscorp post #3</title>
    <link href="https://www.reddit.com/r/auscorp/comments/ccc/post_three/" />
    <published>2026-05-28T01:00:00+00:00</published>
    <summary>body three</summary>
  </entry>
</feed>
"""


def _fake_response(status_code: int, text: str = "", json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if json_body is not None:
        resp.json = MagicMock(return_value=json_body)
    return resp


def test_top_posts_rss_returns_engagement_ordered(monkeypatch):
    """fetch_reddit_top_posts hits /top/.rss and synthesises position-based scores."""
    monkeypatch.setattr(http_mod.time, "sleep", lambda *_: None)

    seen_urls = []

    def fake_get(url, *args, **kwargs):
        seen_urls.append(url)
        return _fake_response(200, text=_CANNED_RSS)

    monkeypatch.setattr(http_mod.httpx, "get", fake_get)

    posts = http_mod.fetch_reddit_top_posts("auscorp", time_filter="week", limit=10)

    # Hit /top/.rss, not the dead .json endpoint.
    assert any("/top/.rss" in u for u in seen_urls), seen_urls
    assert not any("top.json" in u for u in seen_urls), seen_urls

    # Entries returned in feed order with descending synthetic scores.
    assert [p["title"] for p in posts] == [
        "Top auscorp post #1",
        "Top auscorp post #2",
        "Top auscorp post #3",
    ]
    scores = [p["score"] for p in posts]
    assert scores == sorted(scores, reverse=True), f"scores not descending: {scores}"
    assert all(s > 0 for s in scores), f"all scores must be positive: {scores}"

    # URL + published carried through; num_comments unknown in RSS mode.
    assert posts[0]["url"].startswith("https://www.reddit.com/r/auscorp/comments/aaa")
    assert posts[0]["published"].startswith("2026-05-30")
    assert posts[0]["num_comments"] == 0
