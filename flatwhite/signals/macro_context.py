"""Fetch macro headlines from Google News for editorial context in Pulse summary and hooks.

This is NOT a signal — it provides narrative context to the LLM so it can acknowledge
real-world events that readers are feeling, even when quantitative signals haven't moved yet.
"""

from flatwhite.utils.http import fetch_rss
from urllib.parse import quote
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import yaml

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _extract_source(title: str) -> str:
    """Extract source name from Google News title format 'Headline - Source'."""
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return ""


def _clean_title(title: str) -> str:
    """Remove source suffix from Google News title."""
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title.strip()


def _is_duplicate(title: str, seen: list[str]) -> bool:
    """Check if a headline is a near-duplicate of one already seen."""
    clean = _clean_title(title).lower()
    for s in seen:
        s_clean = s.lower()
        # If either title contains 60%+ of the other's words, treat as duplicate
        words_a = set(clean.split())
        words_b = set(s_clean.split())
        if not words_a or not words_b:
            continue
        overlap = len(words_a & words_b)
        if overlap / min(len(words_a), len(words_b)) > 0.6:
            return True
    return False


def fetch_macro_headlines(max_headlines: int = 5) -> str:
    """Fetch recent macro headlines for editorial context.

    Returns a formatted string of headlines for injection into LLM prompts,
    or empty string if no headlines found.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    queries = config.get("google_news", {}).get("macro_queries", [])
    if not queries:
        return ""

    cutoff = datetime.utcnow() - timedelta(days=7)
    headlines: list[dict[str, str]] = []
    seen_titles: list[str] = []

    for query in queries:
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
        try:
            entries = fetch_rss(url, delay_seconds=2.0)
        except Exception:
            continue

        for entry in entries[:5]:
            pub = entry.get("published", "")
            if pub:
                try:
                    dt = parsedate_to_datetime(pub)
                    if dt.replace(tzinfo=None) < cutoff:
                        continue
                except Exception:
                    continue

            title = entry.get("title", "")
            if not title:
                continue

            if _is_duplicate(title, seen_titles):
                continue

            clean = _clean_title(title)
            source = _extract_source(title)
            seen_titles.append(clean)
            headlines.append({"title": clean, "source": source})

            if len(headlines) >= max_headlines:
                break

        if len(headlines) >= max_headlines:
            break

    if not headlines:
        return ""

    lines = ["Recent macro headlines (for editorial context only — do not use as signal data):"]
    for h in headlines:
        source_part = f" ({h['source']})" if h["source"] else ""
        lines.append(f"- \"{h['title']}\"{source_part}")

    return "\n".join(lines) + "\n"
