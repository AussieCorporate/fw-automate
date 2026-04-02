from __future__ import annotations

"""Podcast RSS editorial source — pulls episode descriptions from native
podcast feeds (Omny.fm / Libsyn) and inserts them as editorial items.

Each feed is configured in config.yaml under podcast_feeds.feeds with a
name, rss_url, and source_tag. Falls back gracefully on any fetch error.
"""

import yaml
from pathlib import Path

from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


def pull_podcast_feeds() -> int:
    """Pull editorial items from podcast RSS feeds.

    For each configured feed:
    1. Fetch RSS (episodes up to max_episodes_per_feed)
    2. Insert episode title + description as a raw_item
    3. Skip silently on fetch errors so one bad feed never blocks others

    Returns count of newly inserted items.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    pod_config = config.get("podcast_feeds", {})
    if not pod_config.get("enabled", False):
        print("  Podcast feeds disabled in config")
        return 0

    feeds = pod_config.get("feeds", [])
    max_episodes = pod_config.get("max_episodes_per_feed", 3)
    week_iso = get_current_week_iso()
    total_inserted = 0

    for feed in feeds:
        name = feed.get("name", "unknown")
        rss_url = feed.get("rss_url", "")
        source_tag = feed.get("source_tag", "podcast_unknown")

        if not rss_url:
            print(f"  SKIP: {name} — no rss_url configured")
            continue

        try:
            entries = fetch_rss(rss_url, delay_seconds=1.0)
        except Exception as e:
            print(f"  FAILED: {name} RSS fetch: {e}")
            continue

        feed_count = 0
        for entry in entries[:max_episodes]:
            title = entry.get("title", "")
            body = entry.get("body") or entry.get("summary") or ""
            url = entry.get("url", rss_url)

            if not title:
                continue

            insert_raw_item(
                title=f"[{name}] {title}"[:200],
                body=body[:2000] if body else None,
                source=source_tag,
                url=url,
                lane="editorial",
                subreddit=None,
                week_iso=week_iso,
            )
            feed_count += 1

        total_inserted += feed_count
        print(f"  Podcast '{name}': {feed_count} items")

    return total_inserted
