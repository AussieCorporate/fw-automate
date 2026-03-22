"""Generic RSS feed ingest — pulls editorial content from think tanks, RBA,
courts, business media, and Substacks.

Each feed is configured in config.yaml under rss_feeds.feeds with a name,
url, and source_tag. Exceptions are caught per-feed so one broken source
does not block the rest.

Feeds are fetched in parallel using ThreadPoolExecutor (max_workers=6)
since they target different domains and don't need inter-feed delays.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

MAX_AGE_DAYS = 14


def _is_recent(entry: dict, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """Return True if the article was published within max_age_days, or has no date."""
    pub = entry.get("published", "")
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        return dt.replace(tzinfo=None) >= cutoff
    except Exception:
        return True


def _fetch_single_feed(feed: dict, max_items: int, week_iso: str) -> dict:
    """Fetch and insert items from a single RSS feed.

    Returns a dict with keys: name, count, skipped, error.
    """
    name = feed["name"]
    url = feed["url"]
    source_tag = feed["source_tag"]
    try:
        entries = fetch_rss(url, delay_seconds=0)
        count = 0
        skipped = 0
        for entry in entries[:max_items]:
            if not _is_recent(entry):
                skipped += 1
                continue
            insert_raw_item(
                title=entry["title"],
                body=entry["body"][:2000] if entry["body"] else None,
                source=source_tag,
                url=entry["url"],
                lane="editorial",
                subreddit=None,
                week_iso=week_iso,
            )
            count += 1
        return {"name": name, "count": count, "skipped": skipped, "error": None}
    except Exception as e:
        return {"name": name, "count": 0, "skipped": 0, "error": str(e)}


def pull_rss_feeds() -> int:
    """Pull editorial items from all configured RSS feeds.

    Fetches feeds in parallel using ThreadPoolExecutor(max_workers=6).
    Returns count of newly inserted items.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    rss_config = config.get("rss_feeds", {})
    feeds = rss_config.get("feeds", [])
    max_items = rss_config.get("max_items_per_feed", 15)

    if not feeds:
        print("  No RSS feeds configured in config.yaml")
        return 0

    week_iso = get_current_week_iso()
    total_inserted = 0
    total_skipped_old = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_fetch_single_feed, feed, max_items, week_iso): feed
            for feed in feeds
        }

        for future in as_completed(futures):
            result = future.result()
            if result["error"] is not None:
                print(f"  FAILED: {result['name']}: {result['error']}")
            else:
                total_inserted += result["count"]
                total_skipped_old += result["skipped"]
                print(
                    f"  {result['name']}: {result['count']} items"
                    + (f" (skipped {result['skipped']} old)" if result["skipped"] else "")
                )

    if total_skipped_old:
        print(f"  rss_feeds: skipped {total_skipped_old} articles older than {MAX_AGE_DAYS} days total")

    return total_inserted
