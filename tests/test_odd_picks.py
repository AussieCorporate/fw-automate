"""Tests for odd-picks ('One More Scroll') extraction and shortening.

Covers the two things that were breaking in production: summaries that ran too
long / kept a trailing 'LINK', and picks that got truncated when their own text
contained a bolded word (the parser split on any <b>, not the pick label).
"""
from flatwhite.editorial import beehiiv_picks as bp


def test_shorten_strips_trailing_link():
    assert bp._shorten_odd("Josh went for a beer after the record. LINK") == \
        "Josh went for a beer after the record."


def test_shorten_keeps_first_sentence_only():
    assert bp._shorten_odd("First sentence stands on its own. Second one.") == \
        "First sentence stands on its own."


def test_shorten_caps_rambly_narrative():
    long = ("Spain has secured a historic World Cup title with a late winner over "
            "ten-man Argentina while a substitute sparked an ugly post-match fracas "
            "that overshadowed the whole tournament finale in front of a record crowd")
    out = bp._shorten_odd(long)
    assert len(out) <= 133          # 130 cap + trailing ellipsis
    assert out.endswith("...")


def test_scrape_one_more_scroll_parses_picks(monkeypatch):
    html = (
        '<h4><span>ONE MORE SCROLL</span></h4>'
        "<p><b>Editor’s Pick:</b> Something <b>bold</b> happened here today. "
        '<a href="https://ex.com/a?utm_source=x">LINK</a></p>'
        "<p><b>Doctor’s Pick:</b> A short one. "
        '<a href="https://ex.com/b">LINK</a></p>'
        '<h4>TRIVIA</h4><p>ignore me</p>'
    )
    monkeypatch.setattr(bp, "fetch_recent_posts",
                        lambda days=7, start=None, end=None:
                        [{"id": "p1", "publish_date": "2026-07-20T00:00:00"}])
    monkeypatch.setattr(bp, "fetch_post_clicks_and_content",
                        lambda pid: {"html": html})

    out = bp.scrape_one_more_scroll(days=7)
    assert len(out) == 2

    first = out[0]
    # A bolded word INSIDE the pick must not truncate it (split on pick label).
    assert "bold happened here today" in first["summary"]
    assert first["summary"].endswith(".")          # LINK stripped, sentence kept
    assert "LINK" not in first["summary"]
    assert first["label"].endswith("Pick")
    assert first["url"] == "https://ex.com/a"       # utm stripped
    assert first["edition_date"] == "2026-07-20"

    assert out[1]["summary"] == "A short one."


def test_scrape_one_more_scroll_no_section_is_empty(monkeypatch):
    monkeypatch.setattr(bp, "fetch_recent_posts",
                        lambda days=7, start=None, end=None:
                        [{"id": "p1", "publish_date": "2026-07-20T00:00:00"}])
    monkeypatch.setattr(bp, "fetch_post_clicks_and_content",
                        lambda pid: {"html": "<p>no odd picks segment here</p>"})
    assert bp.scrape_one_more_scroll(days=7) == []
