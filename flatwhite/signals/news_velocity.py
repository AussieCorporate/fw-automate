from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_signal, get_current_week_iso, get_recent_signals
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid
import yaml
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _count_recent_articles(entries: list[dict], days: int = 7) -> int:
    """Count only articles published within the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    count = 0
    for entry in entries:
        pub = entry.get("published", "")
        if not pub:
            continue
        try:
            dt = parsedate_to_datetime(pub)
            if dt.replace(tzinfo=None) >= cutoff:
                count += 1
        except Exception:
            continue
    return count


def pull_layoff_news_velocity() -> float:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    total_articles = 0
    queries_with_results = 0
    for query in config["google_news"]["pulse_queries"]:
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
        try:
            entries = fetch_rss(url, delay_seconds=2.0)
            count = _count_recent_articles(entries, days=7)
            total_articles += count
            if count > 0:
                queries_with_results += 1
        except Exception:
            continue

    week_iso = get_current_week_iso()

    recent = get_recent_signals("layoff_news_velocity", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = config["signal_reference_ranges"]["signals"]["layoff_news_velocity"]
    normalised, source_weight = normalise_hybrid(
        raw_value=float(total_articles),
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    # If all queries returned 0 articles, this is likely a scrape failure, not genuine "no news"
    n_queries = len(config["google_news"]["pulse_queries"])
    if queries_with_results == 0 and n_queries > 0:
        print("  ⚠ layoff_news_velocity: all Google News queries returned 0 articles — possible scrape failure, applying weight penalty")
        source_weight = min(source_weight, 0.3)

    insert_signal(
        signal_name="layoff_news_velocity",
        lane="pulse",
        area="corporate_stress",
        raw_value=float(total_articles),
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )
    return normalised
