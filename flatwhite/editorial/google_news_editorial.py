from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso
import yaml
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

MAX_AGE_DAYS = 7


def _is_recent(entry: dict, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """Return True if the article was published within max_age_days.

    Tries ISO 8601 first (Google News), then RFC 2822. Fails closed when the
    date is missing or unparseable to prevent stale items leaking through.
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


def pull_google_news_editorial() -> int:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    week_iso = get_current_week_iso()
    total_inserted = 0
    skipped_old = 0

    for query in config["google_news"]["editorial_queries"]:
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
        try:
            entries = fetch_rss(url, delay_seconds=2.0)
            for entry in entries[:10]:
                if not _is_recent(entry):
                    skipped_old += 1
                    continue
                insert_raw_item(
                    title=entry["title"],
                    body=entry["body"][:2000] if entry["body"] else None,
                    source="google_news_editorial",
                    url=entry["url"],
                    lane="editorial",
                    subreddit=None,
                    week_iso=week_iso,
                    published_at=entry.get("published") or None,
                )
                total_inserted += 1
        except Exception:
            continue

    if skipped_old:
        print(f"google_news_editorial: skipped {skipped_old} articles older than {MAX_AGE_DAYS} days")

    return total_inserted
