"""Twitter/X editorial source — pulls tweets from curated accounts via RSS proxy.

Used as a SECONDARY source for "What We're Watching" — US trends that
tend to arrive in Australia 6-12 months later.

Uses Nitter RSS or equivalent public proxy. No API key needed.
"""

from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def pull_twitter_editorial() -> int:
    """Pull tweets from curated Twitter/X accounts via RSS proxy.

    Returns count of newly inserted items.
    Disabled by default — set twitter.enabled=true in config.yaml.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    twitter_config = config.get("twitter", {})
    if not twitter_config.get("enabled", False):
        print("  Twitter/X source disabled in config.yaml")
        return 0

    rss_base = twitter_config.get("rss_proxy_base", "")
    if not rss_base:
        print("  WARN: twitter.rss_proxy_base not configured")
        return 0

    accounts = twitter_config.get("accounts", [])
    rss_key = twitter_config.get("rss_key", "")
    week_iso = get_current_week_iso()
    total_inserted = 0
    delay = twitter_config.get("delay_between_pulls_seconds", 3)
    max_posts = twitter_config.get("max_posts_per_account", 10)

    for account in accounts:
        handle = account["handle"]
        url = f"{rss_base}/{handle}/rss"
        if rss_key:
            url += f"?key={rss_key}"
        try:
            entries = fetch_rss(url, delay_seconds=delay)
            for entry in entries[:max_posts]:
                insert_raw_item(
                    title=entry["title"][:200],
                    body=entry["body"][:2000] if entry["body"] else None,
                    source="twitter_rss",
                    url=entry["url"],
                    lane="editorial",
                    subreddit=None,
                    week_iso=week_iso,
                )
                total_inserted += 1
        except Exception as e:
            print(f"  WARN: Failed to pull @{handle}: {e}")
            continue

    return total_inserted
