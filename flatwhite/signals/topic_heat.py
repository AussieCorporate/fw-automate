"""Topic heat signal for Big Conversation angle selection.

Combines two real engagement sources to tell the editor and LLM what's
actually hot in Australian corporate circles this week:

1. Reddit topic anomalies — topics with unusual posting volume vs baseline
2. Google Trends rising queries — what Australians are searching more than
   usual, seeded from AusCorp-relevant keywords

Output: a formatted text block injected into the Big Conversation angles
prompt so the LLM can prioritise angles that align with real-world engagement.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml
from pytrends.exceptions import TooManyRequestsError

from flatwhite.db import get_connection, get_current_week_iso

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

# Seed keywords for Google Trends rising query discovery.
# Each group maps to an AusCorp editorial theme. We pull related_queries()
# for each seed and surface the "rising" and "top" results.
# Broader seeds work better — niche terms return empty on short timeframes.
SEED_KEYWORDS: dict[str, list[str]] = {
    "jobs_economy": ["redundancy australia", "hiring australia"],
    "workplace": ["return to office australia", "work from home australia"],
    "pay_careers": ["salary increase australia", "career change australia"],
    "corporate": ["layoffs australia", "corporate australia"],
    "finance": ["interest rates australia", "ASX australia"],
    "ai_tech": ["AI australia", "automation australia"],
}


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_reddit_topic_heat(week_iso: str | None = None) -> list[dict]:
    """Pull Reddit topic clusters with above-average velocity for the week.

    Returns list of dicts: {topic, post_count, velocity, is_anomaly}
    sorted by velocity descending.
    """
    w = week_iso or get_current_week_iso()
    conn = get_connection()
    rows = conn.execute(
        """SELECT topic_label, post_count, velocity_score, is_anomaly
        FROM reddit_topic_clusters
        WHERE week_iso = ? AND velocity_score > 55
        ORDER BY velocity_score DESC""",
        (w,),
    ).fetchall()
    conn.close()

    return [
        {
            "topic": r["topic_label"].replace("_", " "),
            "post_count": r["post_count"],
            "velocity": round(r["velocity_score"], 1),
            "is_anomaly": bool(r["is_anomaly"]),
        }
        for r in rows
    ]


def fetch_google_rising_queries(max_per_seed: int = 5) -> list[dict]:
    """Pull trending Google queries seeded from AusCorp keywords.

    Calls related_queries() for each seed keyword group using a 1-month window
    (7 days returns too few results). Collects both "rising" (breakout queries)
    and "top" (highest volume related queries) to ensure we always have data.

    Falls back to 3-month window if 1-month returns nothing.

    Returns list of dicts: {query, seed_theme, rise_pct, type}
    sorted by rise_pct descending. Deduplicates across seed groups.
    """
    from flatwhite.signals.google_trends import _make_pytrends

    config = _load_config()
    sleep_secs = config.get("google_trends", {}).get("sleep_between_calls_seconds", 65)
    geo = config.get("google_trends", {}).get("geo", "AU")

    seen_queries: set[str] = set()
    results: list[dict] = []

    # Try 1-month first, fall back to 3-month if empty
    timeframes = ["today 1-m", "today 3-m"]

    for theme, seeds in SEED_KEYWORDS.items():
        theme_results: list[dict] = []

        for timeframe in timeframes:
            try:
                pt = _make_pytrends()
                pt.build_payload(seeds[:2], cat=0, timeframe=timeframe, geo=geo)
                related = pt.related_queries()
            except TooManyRequestsError:
                print(f"  Google Trends 429 on {theme} ({timeframe}) — skipping")
                time.sleep(sleep_secs)
                break
            except Exception as e:
                print(f"  Rising queries failed for {theme} ({timeframe}): {e}")
                time.sleep(sleep_secs)
                break

            for kw in seeds[:2]:
                kw_data = related.get(kw, {})

                # Collect rising queries (breakout — these are the gold)
                rising = kw_data.get("rising")
                if rising is not None and not rising.empty:
                    for _, row in rising.head(max_per_seed).iterrows():
                        query = str(row.get("query", "")).strip().lower()
                        value = row.get("value", 0)
                        if not query or query in seen_queries:
                            continue
                        seen_queries.add(query)
                        theme_results.append({
                            "query": query,
                            "seed_theme": theme.replace("_", " "),
                            "rise_pct": int(value) if str(value).isdigit() else value,
                            "type": "rising",
                        })

                # Also collect top queries (high volume — useful context)
                top = kw_data.get("top")
                if top is not None and not top.empty:
                    for _, row in top.head(3).iterrows():
                        query = str(row.get("query", "")).strip().lower()
                        value = row.get("value", 0)
                        if not query or query in seen_queries:
                            continue
                        seen_queries.add(query)
                        theme_results.append({
                            "query": query,
                            "seed_theme": theme.replace("_", " "),
                            "rise_pct": int(value) if str(value).isdigit() else value,
                            "type": "top",
                        })

            # If we got results from 1-month, don't try 3-month for this theme
            if theme_results:
                break

            time.sleep(sleep_secs)

        results.extend(theme_results)
        time.sleep(sleep_secs)

    # Sort: rising queries first (by value desc), then top queries
    results.sort(
        key=lambda x: (0 if x.get("type") == "rising" else 1, -(x["rise_pct"] if isinstance(x["rise_pct"], int) else 0)),
    )
    return results


def build_topic_heat_block(week_iso: str | None = None) -> str:
    """Build the topic heat context block for injection into Big Conversation prompts.

    Pulls Reddit anomalies from the DB (no API call) and formats them.
    Google Trends rising queries must be fetched separately via
    fetch_google_rising_queries() and passed in, since they're expensive.

    Returns formatted string, or empty string if no heat data exists.
    """
    reddit_heat = fetch_reddit_topic_heat(week_iso)

    if not reddit_heat:
        return ""

    lines = [
        "TOPIC HEAT — what is generating real engagement this week "
        "(use this to prioritise angles aligned with what people actually care about):"
    ]

    if reddit_heat:
        lines.append("")
        lines.append("Reddit volume spikes (topics with unusual posting activity):")
        for r in reddit_heat[:8]:
            flag = " [ANOMALY]" if r["is_anomaly"] else ""
            lines.append(
                f"- {r['topic']} — {r['post_count']} posts, "
                f"velocity {r['velocity']}/100{flag}"
            )

    return "\n".join(lines) + "\n"


def build_full_topic_heat_block(
    week_iso: str | None = None,
    rising_queries: list[dict] | None = None,
) -> str:
    """Build topic heat block with both Reddit anomalies and Google rising queries.

    Args:
        week_iso: Week to query Reddit data for (defaults to current).
        rising_queries: Pre-fetched rising queries from fetch_google_rising_queries().
            If None, only Reddit data is included.
    """
    reddit_heat = fetch_reddit_topic_heat(week_iso)

    if not reddit_heat and not rising_queries:
        return ""

    lines = [
        "TOPIC HEAT — what is generating real engagement this week "
        "(use this to prioritise angles aligned with what people actually care about):"
    ]

    if reddit_heat:
        lines.append("")
        lines.append("Reddit volume spikes (topics with unusual posting activity):")
        for r in reddit_heat[:8]:
            flag = " [ANOMALY]" if r["is_anomaly"] else ""
            lines.append(
                f"- {r['topic']} — {r['post_count']} posts, "
                f"velocity {r['velocity']}/100{flag}"
            )

    if rising_queries:
        rising = [q for q in rising_queries if q.get("type") == "rising"]
        top = [q for q in rising_queries if q.get("type") == "top"]
        if rising:
            lines.append("")
            lines.append("Google Trends BREAKOUT queries in Australia (searches spiking recently):")
            for q in rising[:10]:
                pct = q["rise_pct"]
                pct_str = f"+{pct}%" if isinstance(pct, int) else str(pct)
                lines.append(f"- \"{q['query']}\" ({pct_str}, theme: {q['seed_theme']})")
        if top:
            lines.append("")
            lines.append("Google Trends TOP queries in Australia (highest search volume):")
            for q in top[:8]:
                lines.append(f"- \"{q['query']}\" (volume index: {q['rise_pct']}, theme: {q['seed_theme']})")

    return "\n".join(lines) + "\n"
