import time

from flatwhite.utils.http import fetch_rss, fetch_reddit_comments
from flatwhite.db import insert_raw_item, update_raw_item_engagement, get_current_week_iso
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def pull_reddit_editorial() -> int:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    week_iso = get_current_week_iso()
    total_inserted = 0
    auscorp_items: list[tuple[int, str]] = []  # (item_id, url) for engagement enrichment

    for sub in config["reddit"]["subreddits"]:
        try:
            entries = fetch_rss(
                sub["url"],
                delay_seconds=config["reddit"]["delay_between_pulls_seconds"],
            )
            for entry in entries[:config["reddit"]["max_posts_per_subreddit"]]:
                item_id = insert_raw_item(
                    title=entry["title"],
                    body=entry["body"][:2000] if entry["body"] else None,
                    source="reddit_rss",
                    url=entry["url"],
                    lane="editorial",
                    subreddit=sub["name"],
                    week_iso=week_iso,
                )
                total_inserted += 1
                if sub["name"] == "auscorp" and item_id and entry.get("url"):
                    auscorp_items.append((item_id, entry["url"]))
        except Exception as e:
            print(f"  ⚠ Reddit r/{sub['name']} fetch failed: {e}")
            continue

    # Enrich r/auscorp posts with engagement scores (post_score + comment_engagement)
    # fetch_reddit_comments already sleeps 2s; add 1s gap between calls
    for item_id, url in auscorp_items:
        try:
            data = fetch_reddit_comments(url, top_n=10)
            post_score = data.get("post_score") or 0
            comment_engagement = sum(c.get("score", 0) for c in data.get("comments", []))
            update_raw_item_engagement(item_id, post_score, comment_engagement)
        except Exception as e:
            print(f"  ⚠ Engagement enrichment failed for item {item_id}: {e}")
        time.sleep(1.0)

    return total_inserted
