from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

def pull_reddit_editorial() -> int:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    week_iso = get_current_week_iso()
    total_inserted = 0

    for sub in config["reddit"]["subreddits"]:
        try:
            entries = fetch_rss(
                sub["url"],
                delay_seconds=config["reddit"]["delay_between_pulls_seconds"],
            )
            for entry in entries[:config["reddit"]["max_posts_per_subreddit"]]:
                insert_raw_item(
                    title=entry["title"],
                    body=entry["body"][:2000] if entry["body"] else None,
                    source="reddit_rss",
                    url=entry["url"],
                    lane="editorial",
                    subreddit=sub["name"],
                    week_iso=week_iso,
                )
                total_inserted += 1
        except Exception:
            continue

    return total_inserted
