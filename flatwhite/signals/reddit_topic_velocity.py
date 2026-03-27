from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import median

from flatwhite.db import get_connection, get_current_week_iso, get_recent_signals, insert_signal
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid


TOPIC_KEYWORDS: dict[str, list[str]] = {
    "redundancies": ["redundan", "layoff", "laid off", "retrenchment", "let go", "cut", "restructur"],
    "return_to_office": ["rto", "return to office", "back to office", "wfh", "hybrid", "remote"],
    "ai_displacement": ["ai replacing", "automation", "replaced by ai", "ai taking", "chatgpt"],
    "graduate_hiring": ["grad", "graduate", "intern", "entry level", "new grad"],
    "pay_and_promotions": ["salary", "pay rise", "promotion", "underpaid", "raise", "bonus"],
    "toxic_culture": ["toxic", "bullying", "hostile", "hr complaint", "micromanag"],
    "big4_consulting": ["deloitte", "pwc", "kpmg", "ey ", "ernst", "big 4", "big four"],
    "banking": ["cba", "anz", "nab", "westpac", "macquarie", "commonwealth bank"],
    "tech_sector": ["atlassian", "canva", "afterpay", "seek", "carsales", "realestate.com"],
}

_STRESS_MARKERS: list[str] = [
    "redundan", "layoff", "laid off", "let go", "fired", "sacked",
    "restructur", "downsiz", "cut jobs", "job cuts",
    "toxic", "bullying", "hostile", "harassment", "micromanag",
    "underpaid", "overwork", "burnout", "burn out",
    "hiring freeze", "freeze", "no new roles",
    "anxiety", "stressed", "depressed", "mental health",
    "rto mandate", "forced back",
    "ai replacing", "replaced by ai", "automated away",
]

_POSITIVE_MARKERS: list[str] = [
    "promoted", "promotion", "got the job", "new role",
    "pay rise", "raise", "salary increase", "bonus",
    "hiring", "expanding", "new team", "growing",
    "love my job", "great culture", "good workplace",
    "work life balance", "flexible",
    "offer accepted", "signed contract",
]


def _classify_post(title: str, body: str | None) -> list[str]:
    """Return list of topic labels matching a post. A post can match multiple topics."""
    text = (title + " " + (body or "")).lower()
    return [label for label, keywords in TOPIC_KEYWORDS.items()
            if any(kw in text for kw in keywords)]


def _score_post_stress(title: str, body: str | None) -> float:
    """Score a single post for corporate stress level.

    Returns 0.0 (positive) to 1.0 (high stress).
    Scores each post as a whole unit — keywords are evaluated in context
    of what else appears in the same post.
    """
    text = (title + " " + (body or "")).lower()

    stress_hits = sum(1 for m in _STRESS_MARKERS if m in text)
    positive_hits = sum(1 for m in _POSITIVE_MARKERS if m in text)

    if stress_hits == 0 and positive_hits == 0:
        return 0.5  # Neutral — no stress or positive signals

    total = stress_hits + positive_hits
    # Stress ratio: 1.0 = all stress, 0.0 = all positive
    return stress_hits / total


def _get_reference_range() -> dict:
    """Load reference range from config, with sensible defaults."""
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    ref = config.get("signal_reference_ranges", {}).get("signals", {}).get("reddit_topic_velocity", {})
    return {
        "floor": ref.get("floor", 30.0),
        "ceiling": ref.get("ceiling", 70.0),
        "inverted": ref.get("inverted", True),
    }


def pull_reddit_topic_velocity() -> float:
    """
    Analyse Reddit posts for the current week using per-post stress scoring.

    Each post is scored individually for corporate stress level (0.0-1.0)
    based on keyword co-occurrence — a post mentioning "Deloitte" + "restructuring"
    scores differently from "Deloitte" + "got promoted".

    Topic clusters are still computed and stored in reddit_topic_clusters
    for the editorial "What We're Watching" section.

    Returns normalised score (0-100) for the pulse signal.
    INVERTED: higher stress = lower pulse score (corporate stress is bad).
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    current_posts = conn.execute(
        """
        SELECT title, body, subreddit FROM raw_items
        WHERE week_iso = ? AND lane = 'editorial' AND source = 'reddit_rss'
        """,
        (week_iso,)
    ).fetchall()

    if not current_posts:
        conn.close()
        insert_signal(
            signal_name="reddit_topic_velocity",
            lane="pulse",
            area="corporate_stress",
            raw_value=0.0,
            normalised_score=50.0,
            source_weight=0.5,
            week_iso=week_iso,
        )
        return 50.0

    # --- Per-post stress scoring (drives the pulse signal) ---
    stress_scores: list[float] = []
    for post in current_posts:
        stress_scores.append(_score_post_stress(post["title"], post["body"]))

    avg_stress = sum(stress_scores) / len(stress_scores)

    # --- Topic cluster classification (drives editorial "What We're Watching") ---
    current_counts: Counter = Counter()
    for post in current_posts:
        for label in _classify_post(post["title"], post["body"]):
            current_counts[label] += 1

    # Store topic clusters for editorial use (velocity scoring still uses baseline when available)
    baseline_rows = conn.execute(
        """
        SELECT topic_label, velocity_score FROM reddit_topic_clusters
        WHERE week_iso != ?
        ORDER BY week_iso DESC
        LIMIT 200
        """,
        (week_iso,)
    ).fetchall()

    baseline_by_topic: dict[str, list[float]] = {}
    for row in baseline_rows:
        baseline_by_topic.setdefault(row["topic_label"], []).append(row["velocity_score"])

    for label, count in current_counts.items():
        baseline_scores = baseline_by_topic.get(label, [])
        if len(baseline_scores) >= 4:
            base_median = median(baseline_scores)
            deviations = [abs(s - base_median) for s in baseline_scores]
            mad = median(deviations) or 1.0
            velocity_score = min(100.0, max(0.0, 50.0 + ((count - base_median) / mad) * 10))
            is_anomaly = int(abs(count - base_median) > 1.5 * mad)
        else:
            base_median = None
            velocity_score = 50.0
            is_anomaly = 0

        conn.execute(
            """
            INSERT INTO reddit_topic_clusters
                (week_iso, topic_label, subreddit, post_count, baseline_median, velocity_score, is_anomaly)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_label, subreddit, week_iso) DO UPDATE SET
                post_count = excluded.post_count,
                velocity_score = excluded.velocity_score,
                is_anomaly = excluded.is_anomaly
            """,
            (week_iso, label, "mixed", count, base_median, velocity_score, is_anomaly)
        )

    conn.commit()
    conn.close()

    # --- Normalise stress score for pulse ---
    # raw_value = avg_stress * 100 (0 = all positive, 100 = all stressed)
    # INVERTED: high stress = low pulse score (corporate stress is bad)
    raw_stress_pct = round(avg_stress * 100, 2)

    recent = get_recent_signals("reddit_topic_velocity", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = _get_reference_range()
    import yaml as _yaml
    with open(Path(__file__).parent.parent.parent / "config.yaml") as _f:
        _config = _yaml.safe_load(_f)
    normalised, source_weight = normalise_hybrid(
        raw_value=raw_stress_pct,
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(_config),
    )

    insert_signal(
        signal_name="reddit_topic_velocity",
        lane="pulse",
        area="corporate_stress",
        raw_value=raw_stress_pct,
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )

    return normalised
