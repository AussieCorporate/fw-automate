from concurrent.futures import ThreadPoolExecutor, as_completed
import time as _time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from flatwhite.utils.http import fetch_rss, fetch_reddit_comments, fetch_reddit_top_posts
from flatwhite.db import insert_raw_item, update_raw_item_engagement, get_current_week_iso
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

# Primary subreddits use /top.json (engagement-ranked), others use RSS (recency)
PRIMARY_SUBREDDITS = {"auscorp", "auslaw"}

MAX_POST_AGE_DAYS = 7


def _is_recent_epoch(created_utc: float, max_age_days: int = MAX_POST_AGE_DAYS) -> bool:
    """Return True if a Reddit post's created_utc is within max_age_days."""
    if not created_utc:
        return True
    cutoff = _time.time() - (max_age_days * 86400)
    return created_utc >= cutoff


def _is_recent_rss(entry: dict, max_age_days: int = MAX_POST_AGE_DAYS) -> bool:
    """Return True if an RSS entry was published within max_age_days.

    Reddit RSS publishes dates in ISO 8601 (e.g. '2025-06-22T16:00:39+00:00').
    We try ISO 8601 first, then fall back to RFC 2822. If the date can't be
    parsed or is missing, we fail-closed (drop the post) — the previous fail-open
    behaviour silently let stale posts through.
    """
    pub = entry.get("published", "")
    if not pub:
        return False
    try:
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        return dt >= cutoff
    except Exception:
        return False


def _enrich_one(item_id: int, url: str) -> None:
    """Fetch engagement data for a single post.

    Skips the update entirely when fetch_reddit_comments returns its empty
    failure sentinel (post_score=0 and no comments). Otherwise the row's
    pre-existing post_score (from /top OAuth or the RSS-position synthetic)
    would be stomped with a 0, killing engagement ranking on every Reddit
    failure. Real updates only happen when we got something back.
    """
    try:
        data = fetch_reddit_comments(url, top_n=10)
        post_score = data.get("post_score") or 0
        comments = data.get("comments", [])
        if post_score == 0 and not comments:
            return
        comment_engagement = sum(c.get("score", 0) for c in comments)
        update_raw_item_engagement(item_id, post_score, comment_engagement)
    except Exception as e:
        print(f"  ⚠ Engagement enrichment failed for item {item_id}: {e}")


def pull_reddit_editorial() -> int:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    week_iso = get_current_week_iso()
    total_inserted = 0
    items_to_enrich: list[tuple[int, str]] = []

    for sub in config["reddit"]["subreddits"]:
        sub_name = sub["name"]
        max_posts = config["reddit"]["max_posts_per_subreddit"]

        try:
            if sub_name in PRIMARY_SUBREDDITS:
                # Use /top.json for primary subs — ranked by engagement, not recency
                entries = fetch_reddit_top_posts(
                    sub_name, time_filter="week", limit=max_posts, delay_seconds=2.0,
                )
                for entry in entries:
                    if not _is_recent_epoch(entry.get("created_utc", 0)):
                        continue
                    ts = entry.get("created_utc", 0)
                    pub_iso = (
                        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                        if ts else None
                    )
                    item_id = insert_raw_item(
                        title=entry["title"],
                        body=entry["body"][:2000] if entry["body"] else None,
                        source="reddit_rss",
                        url=entry["url"],
                        lane="editorial",
                        subreddit=sub_name,
                        week_iso=week_iso,
                        published_at=pub_iso,
                    )
                    total_inserted += 1
                    # Store upvotes and comment count from the top listing.
                    # comment_engagement (sum of top-N comment scores) is filled in
                    # later by _enrich_one — pass 0 here so we don't conflate the two.
                    if item_id and entry.get("score"):
                        update_raw_item_engagement(
                            item_id,
                            post_score=entry["score"],
                            comment_engagement=0,
                            num_comments=entry.get("num_comments", 0),
                        )
                    if item_id and entry.get("url"):
                        items_to_enrich.append((item_id, entry["url"]))
            else:
                # Secondary subs still use RSS (recency-based, lighter weight)
                entries = fetch_rss(sub["url"], delay_seconds=2.0)
                for entry in entries[:max_posts]:
                    if not _is_recent_rss(entry):
                        continue
                    item_id = insert_raw_item(
                        title=entry["title"],
                        body=entry["body"][:2000] if entry["body"] else None,
                        source="reddit_rss",
                        url=entry["url"],
                        lane="editorial",
                        subreddit=sub_name,
                        week_iso=week_iso,
                        published_at=entry.get("published") or None,
                    )
                    total_inserted += 1
        except Exception as e:
            print(f"  ⚠ Reddit r/{sub_name} fetch failed: {e}")
            continue

    # Enrich top posts with full comment data (parallel, capped at 15)
    to_enrich = items_to_enrich[:15]
    if to_enrich:
        print(f"  Enriching {len(to_enrich)} posts with comment data...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_enrich_one, iid, url) for iid, url in to_enrich]
            for f in as_completed(futures):
                f.result()

    return total_inserted
