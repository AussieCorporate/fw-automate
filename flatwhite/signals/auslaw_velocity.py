from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import median

from flatwhite.db import get_connection, get_current_week_iso, get_recent_signals, insert_signal
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid


LEGAL_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "partner_exits": ["partner", "lateral", "left the firm", "moved to", "departed", "equity"],
    "graduate_market": ["clerkship", "graduate", "plt", "clerk", "trainee", "seasonal clerk", "grad program"],
    "ai_in_legal": ["ai ", "automation", "legal tech", "chatgpt", "document review", "machine learning"],
    "billing_pressure": ["billable", "hours", "targets", "utilisation", "write-off", "time sheet"],
    "lateral_moves": ["lateral", "recruited", "poached", "headhunter", "moved firms", "new role"],
    "redundancies": ["redundan", "restructur", "let go", "laid off", "cut", "downsiz"],
    "salary_comp": ["salary", "pay", "bonus", "special counsel", "underpaid", "raise", "comp"],
}

_LEGAL_STRESS_MARKERS: list[str] = [
    "redundan", "restructur", "let go", "laid off", "downsiz",
    "billable", "target", "utilisation", "write-off",  # billing pressure
    "toxic", "bullying", "hostile", "harassment",
    "burnout", "burn out", "overwork", "mental health",
    "left the firm", "departed", "exodus",
    "underpaid", "below market", "pay cut",
    "no clerkship", "rejected", "struggling to find",
    "ai replacing", "automation threat",
]

_LEGAL_POSITIVE_MARKERS: list[str] = [
    "promoted", "special counsel", "made partner",
    "pay rise", "salary increase", "bonus",
    "clerkship offer", "grad offer", "got the role",
    "lateral move", "great firm", "love the work",
    "work life balance", "flexible", "hybrid",
    "expanding", "new team", "hiring",
]


def _classify_legal_post(title: str, body: str | None) -> list[str]:
    """Return list of topic labels matching a post. A post can match multiple topics."""
    text = (title + " " + (body or "")).lower()
    return [label for label, keywords in LEGAL_TOPIC_KEYWORDS.items()
            if any(kw in text for kw in keywords)]


def _score_legal_post_stress(title: str, body: str | None) -> float:
    """Score a single r/auslaw post for legal profession stress level.

    Returns 0.0 (positive) to 1.0 (high stress).
    """
    text = (title + " " + (body or "")).lower()

    stress_hits = sum(1 for m in _LEGAL_STRESS_MARKERS if m in text)
    positive_hits = sum(1 for m in _LEGAL_POSITIVE_MARKERS if m in text)

    if stress_hits == 0 and positive_hits == 0:
        return 0.5  # Neutral

    total = stress_hits + positive_hits
    return stress_hits / total


def _get_reference_range() -> dict:
    """Load reference range from config, with sensible defaults."""
    import yaml
    CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    ref = config.get("signal_reference_ranges", {}).get("signals", {}).get("auslaw_velocity", {})
    return {
        "floor": ref.get("floor", 30.0),
        "ceiling": ref.get("ceiling", 70.0),
        "inverted": ref.get("inverted", True),
    }


def pull_auslaw_velocity() -> float:
    """
    Analyse r/auslaw posts for the current week using per-post stress scoring.

    Each post is scored individually for legal profession stress level (0.0-1.0)
    based on keyword co-occurrence -- a post mentioning "billable" + "burnout"
    scores differently from "billable" + "made partner".

    Topic clusters are still computed and stored in reddit_topic_clusters
    for the editorial "What We're Watching" section.

    Returns normalised score (0-100) for the pulse signal.
    INVERTED: higher stress = lower pulse score (legal profession stress is bad).
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    posts = conn.execute(
        """
        SELECT title, body FROM raw_items
        WHERE week_iso = ? AND lane = 'editorial' AND source = 'reddit_rss' AND subreddit = 'auslaw'
        """,
        (week_iso,),
    ).fetchall()

    if not posts:
        conn.close()
        insert_signal(
            signal_name="auslaw_velocity",
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
    for post in posts:
        stress_scores.append(_score_legal_post_stress(post["title"], post["body"]))

    avg_stress = sum(stress_scores) / len(stress_scores)

    # --- Topic cluster classification (drives editorial "What We're Watching") ---
    current_counts: Counter = Counter()
    for post in posts:
        for label in _classify_legal_post(post["title"], post["body"]):
            current_counts[label] += 1

    # Store topic clusters for editorial use (velocity scoring still uses baseline when available)
    baseline_rows = conn.execute(
        """
        SELECT topic_label, velocity_score FROM reddit_topic_clusters
        WHERE week_iso != ? AND subreddit = 'auslaw'
        ORDER BY week_iso DESC
        LIMIT 100
        """,
        (week_iso,),
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
            (week_iso, label, "auslaw", count, base_median, velocity_score, is_anomaly),
        )

    conn.commit()
    conn.close()

    # --- Normalise stress score for pulse ---
    # raw_value = avg_stress * 100 (0 = all positive, 100 = all stressed)
    # INVERTED: high stress = low pulse score (legal profession stress is bad)
    raw_stress_pct = round(avg_stress * 100, 2)

    recent = get_recent_signals("auslaw_velocity", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = _get_reference_range()
    normalised, source_weight = normalise_hybrid(
        raw_value=raw_stress_pct,
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    insert_signal(
        signal_name="auslaw_velocity",
        lane="pulse",
        area="corporate_stress",
        raw_value=raw_stress_pct,
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )

    return normalised
