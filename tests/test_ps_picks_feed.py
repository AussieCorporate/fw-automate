"""FW reader for the PS picks feed: dedup, day-window, fail-open."""
import datetime as dt
import json

from flatwhite.editorial import ps_picks_feed


def _write(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


NOW = dt.datetime(2026, 7, 19, 12, 0, tzinfo=dt.timezone.utc)


def _iso(days_ago):
    return (NOW - dt.timedelta(days=days_ago)).isoformat()


def test_reads_business_and_odd(tmp_path):
    p = tmp_path / "feed.jsonl"
    _write(p, [{"edition_date": _iso(1),
                "business": [{"url": "u1", "title": "T1", "summary": "S1", "category": "AUS", "is_feature": True}],
                "odd": [{"url": "o1", "title": "Odd", "summary": "quirky"}]}])
    d = ps_picks_feed.read_feed(days=7, now=NOW, path=str(p))
    assert len(d["business"]) == 1 and d["business"][0]["is_feature"] is True
    assert len(d["odd"]) == 1 and d["odd"][0]["title"] == "Odd"


def test_excludes_editions_older_than_window(tmp_path):
    p = tmp_path / "feed.jsonl"
    _write(p, [
        {"edition_date": _iso(10), "business": [{"url": "old", "summary": "old"}], "odd": []},
        {"edition_date": _iso(2), "business": [{"url": "new", "summary": "new"}], "odd": []},
    ])
    d = ps_picks_feed.read_feed(days=7, now=NOW, path=str(p))
    urls = {b["url"] for b in d["business"]}
    assert urls == {"new"}  # 10-day-old edition dropped


def test_newest_edition_wins_on_dedup(tmp_path):
    p = tmp_path / "feed.jsonl"
    _write(p, [
        {"edition_date": _iso(3), "business": [{"url": "u", "summary": "old summary", "is_feature": False}], "odd": []},
        {"edition_date": _iso(1), "business": [{"url": "u", "summary": "new summary", "is_feature": True}], "odd": []},
    ])
    d = ps_picks_feed.read_feed(days=7, now=NOW, path=str(p))
    assert len(d["business"]) == 1
    assert d["business"][0]["summary"] == "new summary"  # newest edition's version


def test_missing_feed_is_fail_open(tmp_path):
    d = ps_picks_feed.read_feed(days=7, now=NOW, path=str(tmp_path / "nope.jsonl"))
    assert d == {"business": [], "odd": []}


def test_corrupt_lines_skipped(tmp_path):
    p = tmp_path / "feed.jsonl"
    p.write_text('not json\n{"edition_date": "%s", "business": [{"url":"u","summary":"s"}], "odd": []}\n' % _iso(1))
    d = ps_picks_feed.read_feed(days=7, now=NOW, path=str(p))
    assert len(d["business"]) == 1
