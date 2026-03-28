"""Scraper: top Australian business/economic news for Big Conversation seeding.

Runs 5 broad AU-focused Google News queries, deduplicates by URL, keeps the
first 5 unique items, and inserts them directly as big_conversation_seed
curated items (bypassing the classifier).
"""
from urllib.parse import quote
from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, insert_curated_item, get_current_week_iso

TOP_AU_NEWS_QUERIES = [
    "australia business news",
    "australia economy news",
    "australia corporate news",
    "ASX news australia",
    "australia banking finance news",
]

MAX_ITEMS = 5
RESULTS_PER_QUERY = 3
_FIXED_SCORES = dict(
    score_relevance=4,
    score_novelty=4,
    score_reliability=4,
    score_tension=4,
    score_usefulness=4,
    weighted_composite=4.0,
    confidence_tag="yellow",
)


def pull_google_news_top_au() -> int:
    """Fetch top AU news items and seed them directly as big_conversation_seed candidates.

    Returns the number of items successfully inserted into curated_items.
    """
    week_iso = get_current_week_iso()
    seen_urls: set[str] = set()
    candidates: list[dict] = []

    for query in TOP_AU_NEWS_QUERIES:
        if len(candidates) >= MAX_ITEMS:
            break
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
        try:
            entries = fetch_rss(url, delay_seconds=2.0)
            for entry in entries[:RESULTS_PER_QUERY]:
                item_url = entry.get("url", "")
                if item_url in seen_urls:
                    continue
                seen_urls.add(item_url)
                candidates.append(entry)
                if len(candidates) >= MAX_ITEMS:
                    break
        except Exception:
            continue

    inserted = 0
    for entry in candidates:
        body = entry.get("body") or ""
        summary = body[:300].strip() if body else (entry.get("title", "")[:300])
        raw_id = insert_raw_item(
            title=entry["title"],
            body=body[:2000] if body else None,
            source="google_news_top_au",
            url=entry.get("url"),
            lane="editorial",
            subreddit=None,
            week_iso=week_iso,
        )
        if not raw_id:
            continue
        result = insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary=summary or entry["title"][:300],
            **_FIXED_SCORES,
        )
        if result is not None:
            inserted += 1

    return inserted
