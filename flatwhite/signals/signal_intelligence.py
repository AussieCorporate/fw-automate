"""Signal intelligence: auto-fetch supporting news for significant WoW movers.

After the pulse scrape, for each signal where abs(WoW delta) >= DELTA_THRESHOLD,
queries Google News RSS, fetches top articles, and synthesises a short commentary
via Claude Haiku. Stored in the signal_intelligence table.
"""
from __future__ import annotations

import json
import time
from urllib.parse import quote

from flatwhite.db import get_connection, get_current_week_iso
from flatwhite.model_router import route
from flatwhite.utils.http import fetch_rss

DELTA_THRESHOLD = 5.0

_QUERY_TEMPLATES: dict[str, str] = {
    "asic_insolvency":      "Australian corporate insolvency administration {month} {year}",
    "market_hiring":        "Australian job market hiring white collar {month} {year}",
    "asx_volatility":       "ASX market volatility week {month} {year}",
    "asx_momentum":         "ASX market rally correction {month} {year}",
    "salary_pressure":      "Australian salary wages pressure {month} {year}",
    "consumer_confidence":  "Australian consumer confidence {month} {year}",
    "layoff_news_velocity": "Australian corporate layoffs redundancies {month} {year}",
    "news_velocity":        "Australian corporate layoffs redundancies {month} {year}",
    "indeed_hiring":        "Australian job listings Indeed hiring {month} {year}",
    "contractor_proxy":     "Australian contract work freelance market {month} {year}",
    "job_anxiety":          "Australian job anxiety employment stress {month} {year}",
    "career_mobility":      "Australian career change job switching {month} {year}",
    "auslaw_velocity":      "Australian employment law tribunal {month} {year}",
    "reddit_topic_velocity": "Australian corporate workplace {month} {year}",
}

_SYSTEM_PROMPT = (
    "You are a data analyst for Flat White, an Australian corporate market newsletter. "
    "Be specific, concise, and authoritative. Australian English."
)


def _fetch_articles(signal_name: str, month: str, year: str) -> list[dict]:
    """Fetch top 5 Google News articles for the signal's query template."""
    template = _QUERY_TEMPLATES.get(signal_name)
    if not template:
        return []
    query = template.format(month=month, year=year)
    encoded = quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
    try:
        entries = fetch_rss(url, delay_seconds=1.0)
        articles = []
        for e in entries[:5]:
            articles.append({
                "title":     e.get("title", ""),
                "url":       e.get("url", ""),
                "published": e.get("published", ""),
                "snippet":   (e.get("body") or "")[:200],
            })
        return articles
    except Exception as e:
        print(f"  signal_intelligence: article fetch failed for {signal_name}: {e}")
        return []


def _synthesise(signal_name: str, delta: float, articles: list[dict]) -> str:
    """Call Claude Haiku to write 2-3 sentences explaining the signal movement."""
    direction = "up" if delta > 0 else "down"
    articles_text = "\n".join(
        f"{i+1}. {a['title']} ({a['published'][:16]}) — {a['snippet']}"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Signal: {signal_name}\n"
        f"WoW delta: {delta:+.1f} points ({direction})\n\n"
        f"Supporting articles:\n{articles_text or '(no articles found)'}\n\n"
        "Write 2-3 sentences explaining what likely drove this movement and what it means "
        "for the Australian corporate market. Be specific. Cite article titles where relevant. "
        "Do not use bullet points."
    )
    return route("signal_intelligence", prompt, system=_SYSTEM_PROMPT)


def run_signal_intelligence() -> None:
    """Main entry point — called as a step in the pulse runner.

    Skips gracefully if fewer than 2 weeks of signal data exist.
    """
    import datetime as _dt

    week_iso = get_current_week_iso()
    year, wn = int(week_iso[:4]), int(week_iso[6:])
    dt = _dt.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u")
    prev_week = (dt - _dt.timedelta(weeks=1)).strftime("%G-W%V")
    month = dt.strftime("%B")  # e.g. "March"

    conn = get_connection()
    prev_rows = conn.execute(
        "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (prev_week,),
    ).fetchall()

    if not prev_rows:
        print("  signal_intelligence: no previous week data — skipping")
        conn.close()
        return

    curr_rows = conn.execute(
        "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (week_iso,),
    ).fetchall()
    conn.close()

    prev_map = {r["signal_name"]: r["normalised_score"] for r in prev_rows}
    curr_map = {r["signal_name"]: r["normalised_score"] for r in curr_rows}

    movers = []
    for name, score in curr_map.items():
        prev = prev_map.get(name)
        if prev is not None:
            delta = score - prev
            if abs(delta) >= DELTA_THRESHOLD:
                movers.append((name, delta))

    if not movers:
        print("  signal_intelligence: no significant movers this week (threshold: ±5pts)")
        return

    print(f"  signal_intelligence: processing {len(movers)} movers: {[m[0] for m in movers]}")

    for signal_name, delta in movers:
        articles = _fetch_articles(signal_name, month, str(year))
        time.sleep(1.0)  # be polite to Google News
        commentary = _synthesise(signal_name, delta, articles)

        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO signal_intelligence
               (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (signal_name, week_iso, round(delta, 1), json.dumps(articles), commentary),
        )
        conn.commit()
        conn.close()
        print(f"  signal_intelligence: {signal_name} ({delta:+.1f}) — commentary stored")
