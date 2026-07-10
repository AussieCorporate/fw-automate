"""Signal intelligence: auto-fetch supporting news for significant WoW movers.

After the pulse scrape, for each signal where abs(WoW delta) >= DELTA_THRESHOLD,
queries Google News RSS, fetches top articles, and synthesises a short commentary
via Claude Haiku. Stored in the signal_intelligence table.
"""
from __future__ import annotations

import datetime as _dt
import json
import time
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from flatwhite.db import get_connection, get_current_week_iso
from flatwhite.model_router import route, LLMRateLimitError
from flatwhite.utils.http import fetch_rss

DELTA_THRESHOLD = 5.0
MAX_AGE_DAYS = 7

_QUERY_TEMPLATES: dict[str, str] = {
    "asic_insolvency":      "Australian corporate insolvency administration {month} {year}",
    "market_hiring":        "Australian job market hiring white collar {month} {year}",
    "asx_volatility":       "ASX market volatility week {month} {year}",
    "asx_momentum":         "ASX market rally correction {month} {year}",
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
    "Be specific, concise, and authoritative. Australian English.\n\n"
    "CRITICAL — SCORE CONVENTION: Every normalised score we discuss is a STRESS score "
    "on a 0–100 scale where 0 = calm and 100 = maximum stress. A POSITIVE delta means "
    "stress in that dimension INCREASED week-on-week (worse for the market). A NEGATIVE "
    "delta means stress EASED (better). Never invert this. If the score rose +32 for "
    "ASX volatility, that means volatility climbed and conditions deteriorated — NEVER "
    "describe a positive delta as 'calmed', 'improved', 'eased', or 'rebound'.\n\n"
    "Ground your analysis in the supporting articles. If the articles describe the raw "
    "metric in a way that aligns with the stress direction, lean into it; if they appear "
    "to disagree (e.g. articles describe a rebound but our score shows higher stress), "
    "explain the nuance — for example, the rebound was tactical and bears retained "
    "control, or one strong day didn't reverse a weakening weekly trend. Never contradict "
    "the stress direction implied by the score delta."
)


def _is_recent(published: str, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """Return True if published date is within max_age_days. Missing/unparseable → False.

    Stricter than the editorial pipeline's _is_recent (which lets dateless entries
    through) because signal commentary must not be grounded in undateable articles.
    """
    if not published:
        return False
    try:
        dt = parsedate_to_datetime(published)
        cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=max_age_days)
        return dt.replace(tzinfo=None) >= cutoff
    except Exception:
        return False


def _fetch_articles(signal_name: str, month: str, year: str) -> list[dict]:
    """Fetch top 5 Google News articles for the signal's query template, scoped to last 7 days."""
    template = _QUERY_TEMPLATES.get(signal_name)
    if not template:
        return []
    query = template.format(month=month, year=year)
    # when:7d restricts Google News to the last 7 days at source
    encoded = quote(f"{query} when:7d")
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
    try:
        entries = fetch_rss(url, delay_seconds=1.0)
        articles = []
        for e in entries:
            pub = e.get("published", "")
            if not _is_recent(pub):
                continue
            articles.append({
                "title":     e.get("title", ""),
                "url":       e.get("url", ""),
                "published": pub,
                "snippet":   (e.get("body") or "")[:200],
            })
            if len(articles) >= 5:
                break
        return articles
    except Exception as e:
        print(f"  signal_intelligence: article fetch failed for {signal_name}: {e}")
        return []


# Every normalised score below is a STRESS score: 0 = calm, 100 = max stress.
# Each entry says (a) what the raw metric is, (b) how it maps to stress.
_SIGNAL_DESCRIPTIONS: dict[str, str] = {
    "consumer_confidence":     "ANZ-Roy Morgan Consumer Confidence Index. Higher raw value = more confident consumers. Stress score INVERTS this: lower raw confidence → higher stress. Score rising = confidence falling.",
    "market_hiring":           "SEEK job posting volume. Higher raw = more jobs advertised. Stress score INVERTS this: fewer postings → higher stress. Score rising = hiring contracting.",
    "layoff_news_velocity":    "Volume of layoff/redundancy news articles. Higher raw = more layoff coverage = worse. Score rising = more layoff news = stress increasing.",
    "employer_hiring_breadth": "Percentage of tracked employers actively adding roles. Higher raw = more firms hiring. Stress INVERTS: fewer firms hiring → higher stress. Score rising = hiring breadth contracting.",
    "asx_volatility":          "ASX 200 realised volatility. Higher raw = more turbulent market = worse. Score rising = volatility climbing = stress increasing.",
    "asx_momentum":            "ASX 200 weekly momentum (% change). Higher raw = stronger market. Stress INVERTS: weaker/negative momentum → higher stress. Score rising = momentum weakening or turning negative.",
    "job_anxiety":             "Google search volume for job-anxiety / redundancy terms. Higher raw searches = more anxiety = worse. Score rising = anxiety searches climbing.",
    "career_mobility":         "Google search volume for career-change terms. Higher raw = more people actively exploring moves. Stress INVERTS: low mobility → higher stress (people stuck/scared to move).",
    "asic_insolvency":         "ASIC corporate insolvency filings. Higher raw = more failures = worse. Score rising = insolvencies climbing = stress increasing.",
    "indeed_job_postings":     "Indeed job-posting index. Higher raw = more listings. Stress INVERTS: fewer listings → higher stress. Score rising = job postings contracting.",
    "indeed_remote_pct":       "Share of Indeed listings offering remote work. Higher raw = more remote roles available. Stress INVERTS: less remote availability → higher stress.",
    "resume_anxiety":          "Google search volume for resume/CV help. Higher raw searches = more anxiety = worse. Score rising = resume-help searches climbing.",
    "reddit_topic_velocity":   "Velocity of stress-themed topics on r/auscorp. Higher raw = more chatter about stress topics = worse. Score rising = more stress chatter.",
    "auslaw_velocity":         "Velocity of legal-sector stress topics on r/auslaw. Higher raw = more stress = worse.",
    "contractor_proxy":        "Net Google search interest for contracting vs. layoffs. Higher raw = healthier contract market. Stress INVERTS: low contractor demand → higher stress.",
    "employer_req_freshness":  "Share of new vs. stale roles across tracked employers. Higher raw = roles being refreshed. Stress INVERTS: stale postings dominating → higher stress.",
    "employer_net_delta":      "Net headcount change across tracked employers (% of total roles). Higher raw = net hiring. Stress INVERTS: net cuts → higher stress.",
}


def _synthesise(signal_name: str, delta: float, articles: list[dict]) -> str:
    """Call Claude Haiku to write 2-3 sentences explaining the signal movement.

    The score is a STRESS score (high = bad). delta > 0 means stress in this
    dimension increased week-on-week; delta < 0 means stress eased.
    """
    stress_direction = "stress INCREASED" if delta > 0 else "stress EASED"
    desc = _SIGNAL_DESCRIPTIONS.get(signal_name, "")
    articles_text = "\n".join(
        f"{i+1}. {a['title']} ({a['published'][:16]}) — {a['snippet']}"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Signal: {signal_name}\n"
        f"What it measures: {desc}\n"
        f"Stress score delta (WoW): {delta:+.1f} points  →  {stress_direction}\n"
        f"REMINDER: Higher score = MORE stress. A positive delta means conditions deteriorated "
        f"in this dimension. A negative delta means conditions improved. Do NOT call a positive "
        f"delta an 'improvement', 'rebound', or 'easing'.\n\n"
        f"Supporting articles:\n{articles_text or '(no articles found)'}\n\n"
        "Write 2-3 sentences explaining what likely drove the stress movement and what it means "
        "for the Australian corporate market. Be specific. Cite article titles where relevant. "
        "If the supporting articles describe the raw metric in a way that aligns with the stress "
        "direction (e.g. articles describe rising volatility and the stress score rose), lean "
        "into that. If they appear to disagree (e.g. articles describe a rally but stress went up "
        "because the rally was tactical), reconcile by explaining the nuance — never flip the "
        "stress direction. Do not use bullet points."
    )
    return route("signal_intelligence", prompt, system=_SYSTEM_PROMPT)


def run_signal_intelligence() -> None:
    """Main entry point — called as a step in the pulse runner.

    Skips gracefully if fewer than 2 weeks of signal data exist.
    """
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
        # fetch_rss already sleeps delay_seconds between requests; no extra sleep needed here
        articles = _fetch_articles(signal_name, month, str(year))
        try:
            commentary = _synthesise(signal_name, delta, articles)
        except LLMRateLimitError as e:
            # Quota exhausted — stop generating commentary rather than crashing
            # the whole Pulse run. Movers already processed keep their commentary.
            print(f"  ⚠ signal_intelligence stopped — LLM rate-limited ({e}). "
                  f"Remaining movers skipped this run.")
            return

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
