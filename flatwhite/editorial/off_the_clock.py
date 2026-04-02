"""Off the Clock lifestyle ingest — pulls content from Broadsheet, Google News,
Reddit, and other lifestyle sources across 5 categories: Eating, Watching,
Reading, Wearing, Going.

Each source is configured in config.yaml under off_the_clock. Items are
inserted into raw_items with lane='lifestyle' and lifestyle_category set
where determinable from config (category_hint or keyword match).

Follows the same pattern as rss_feeds.py: parallel fetch, per-source error
handling, returns total inserted count.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from flatwhite.utils.http import fetch_rss
from flatwhite.db import get_connection, get_current_week_iso
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

OTC_CATEGORIES = {"eating", "watching", "reading", "wearing", "going"}


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f).get("off_the_clock", {})


def _is_recent(entry: dict, max_age_days: int) -> bool:
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


def _insert_lifestyle_item(
    title: str,
    body: str | None,
    source: str,
    url: str | None,
    city: str | None,
    category_hint: str | None,
    week_iso: str,
) -> int:
    """Insert a lifestyle item into raw_items with lane='lifestyle'.

    Uses the subreddit column to store city (sydney/melbourne/national).
    Sets lifestyle_category if a category_hint is provided.
    Returns the row id.
    """
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO raw_items
        (title, body, source, url, lane, subreddit, pulled_at, week_iso, lifestyle_category)
        VALUES (?, ?, ?, ?, 'lifestyle', ?, datetime('now'), ?, ?)""",
        (title, body, source, url, city, week_iso, category_hint),
    )
    conn.commit()
    row_id = cursor.lastrowid
    if row_id == 0:
        existing = conn.execute(
            "SELECT id FROM raw_items WHERE title = ? AND source = ? AND week_iso = ?",
            (title, source, week_iso),
        ).fetchone()
        conn.close()
        return existing["id"] if existing else 0
    conn.close()
    return row_id


def _match_reddit_category(title: str, body: str | None, keyword_filters: dict) -> str | None:
    """Match a Reddit post to an OTC category using keyword filters.

    Returns the first matching category, or None if no match.
    """
    text = (title + " " + (body or "")).lower()
    for category, keywords in keyword_filters.items():
        if any(kw in text for kw in keywords):
            return category
    return None


def _fetch_rss_feed(feed: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch and insert items from a single RSS feed."""
    name = feed["name"]
    url = feed["url"]
    category_hint = feed.get("category_hint")
    city = feed.get("city")
    source_tag = f"otc_rss_{name.lower().replace(' ', '_')}"

    try:
        entries = fetch_rss(url, delay_seconds=0)
        count = 0
        for entry in entries[:max_items]:
            if not _is_recent(entry, max_age_days):
                continue
            _insert_lifestyle_item(
                title=entry["title"],
                body=entry["body"][:2000] if entry["body"] else None,
                source=source_tag,
                url=entry["url"],
                city=city,
                category_hint=category_hint,
                week_iso=week_iso,
            )
            count += 1
        return {"name": name, "count": count, "error": None}
    except Exception as e:
        return {"name": name, "count": 0, "error": str(e)}


def _fetch_all_rss(rss_feeds: list, max_items: int, max_age_days: int, week_iso: str) -> list[dict]:
    """Fetch all RSS feeds in parallel. Returns list of result dicts."""
    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_fetch_rss_feed, feed, max_items, max_age_days, week_iso): feed
            for feed in rss_feeds
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _fetch_single_google_query(category: str, query: str, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch and insert items from a single Google News query."""
    encoded = quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
    try:
        entries = fetch_rss(url, delay_seconds=1.0)
        count = 0
        for entry in entries[:max_items]:
            if not _is_recent(entry, max_age_days):
                continue
            _insert_lifestyle_item(
                title=entry["title"],
                body=entry["body"][:2000] if entry["body"] else None,
                source="otc_google_news",
                url=entry["url"],
                city=None,
                category_hint=category,
                week_iso=week_iso,
            )
            count += 1
        return {"query": query, "count": count, "error": None}
    except Exception as e:
        return {"query": query, "count": 0, "error": str(e)}


def _fetch_google_news_lifestyle(queries_by_category: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch lifestyle items from Google News RSS for all categories in parallel."""
    total = 0
    errors = []

    tasks = [(cat, q) for cat, queries in queries_by_category.items() for q in queries]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_single_google_query, cat, q, max_items, max_age_days, week_iso): q
            for cat, q in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result["error"]:
                errors.append(f"Google News '{result['query']}': {result['error']}")
            else:
                total += result["count"]

    return {"count": total, "errors": errors}


def _fetch_single_reddit_sub(sub: dict, keyword_filters: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch and insert lifestyle posts from a single subreddit."""
    try:
        entries = fetch_rss(sub["url"], delay_seconds=1.0)
        city = sub.get("city")
        sub_category_hint = sub.get("category_hint")
        count = 0

        for entry in entries[:max_items * 3]:
            if not _is_recent(entry, max_age_days):
                continue

            category = sub_category_hint or _match_reddit_category(
                entry["title"], entry["body"], keyword_filters
            )
            if category is None:
                continue

            _insert_lifestyle_item(
                title=entry["title"],
                body=entry["body"][:2000] if entry["body"] else None,
                source=f"otc_reddit_r/{sub['name']}",
                url=entry["url"],
                city=city,
                category_hint=category,
                week_iso=week_iso,
            )
            count += 1
        return {"name": sub["name"], "count": count, "error": None}
    except Exception as e:
        return {"name": sub["name"], "count": 0, "error": str(e)}


def _fetch_reddit_lifestyle(subreddits: list, keyword_filters: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch lifestyle-relevant posts from Reddit, filtered by keyword, in parallel."""
    total = 0
    errors = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_fetch_single_reddit_sub, sub, keyword_filters, max_items, max_age_days, week_iso): sub
            for sub in subreddits
        }
        for future in as_completed(futures):
            result = future.result()
            if result["error"]:
                errors.append(f"Reddit r/{result['name']}: {result['error']}")
            else:
                total += result["count"]

    return {"count": total, "errors": errors}


def pull_off_the_clock() -> int:
    """Pull lifestyle items from all configured Off the Clock sources.

    Fetches RSS feeds in parallel, then Google News and Reddit sequentially.
    Returns count of newly inserted items.
    """
    config = _load_config()

    if not config.get("enabled", False):
        print("  Off the Clock is disabled in config")
        return 0

    week_iso = get_current_week_iso()
    max_items = config.get("max_items_per_source", 10)
    max_age_days = config.get("max_age_days", 30)
    total_inserted = 0

    rss_feeds = config.get("rss_feeds", [])
    gn_queries = config.get("google_news_queries", {})
    reddit_subs = config.get("reddit_subreddits", [])
    keyword_filters = config.get("reddit_keyword_filters", {})

    # Run all source types concurrently
    with ThreadPoolExecutor(max_workers=3) as outer:
        rss_future = outer.submit(_fetch_all_rss, rss_feeds, max_items, max_age_days, week_iso) if rss_feeds else None
        gn_future = outer.submit(_fetch_google_news_lifestyle, gn_queries, max_items, max_age_days, week_iso) if gn_queries else None
        reddit_future = outer.submit(_fetch_reddit_lifestyle, reddit_subs, keyword_filters, max_items, max_age_days, week_iso) if reddit_subs else None

        if rss_future:
            rss_results = rss_future.result()
            for result in rss_results:
                if result["error"]:
                    print(f"  FAILED: {result['name']}: {result['error']}")
                else:
                    total_inserted += result["count"]
                    if result["count"]:
                        print(f"  {result['name']}: {result['count']} items")

        if gn_future:
            gn_result = gn_future.result()
            total_inserted += gn_result["count"]
            if gn_result["count"]:
                print(f"  Google News lifestyle: {gn_result['count']} items")
            for err in gn_result["errors"]:
                print(f"  FAILED: {err}")

        if reddit_future:
            reddit_result = reddit_future.result()
            total_inserted += reddit_result["count"]
            if reddit_result["count"]:
                print(f"  Reddit lifestyle: {reddit_result['count']} items")
            for err in reddit_result["errors"]:
                print(f"  FAILED: {err}")

    return total_inserted
