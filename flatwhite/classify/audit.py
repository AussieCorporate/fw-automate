"""Classifier accuracy audit tool.

Samples classified items for a given week and displays them for human review,
enabling editors to verify that the LLM classifier is routing items correctly.
"""

from __future__ import annotations

from flatwhite.db import get_connection, get_current_week_iso


def audit_classifications(
    week_iso: str | None = None,
    section: str | None = None,
    limit: int = 50,
) -> dict:
    """Query curated_items joined with raw_items for audit review.

    Parameters:
        week_iso: ISO week string (e.g. '2026-W12'). Defaults to current week.
        section: Optional filter to one section.
        limit: Max items per section (default 50).

    Returns:
        Dict with keys: week_iso, total, discard_count, by_section, stats.
    """
    if week_iso is None:
        week_iso = get_current_week_iso()

    conn = get_connection()

    # Build main query
    params: list[str | int] = [week_iso]
    section_filter = ""
    if section is not None:
        section_filter = " AND ci.section = ?"
        params.append(section)

    rows = conn.execute(
        f"""SELECT ci.id, ci.section, ci.summary, ci.tags,
               ci.score_relevance, ci.score_novelty, ci.score_reliability,
               ci.score_tension, ci.score_usefulness,
               ci.weighted_composite, ci.confidence_tag,
               ri.title, ri.body, ri.source, ri.url, ri.subreddit
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ?{section_filter}
        ORDER BY ci.section, ci.weighted_composite DESC""",
        tuple(params),
    ).fetchall()

    # Count auto-discarded items (classified=1 but not in curated_items)
    discard_row = conn.execute(
        """SELECT COUNT(*) as cnt FROM raw_items
        WHERE week_iso = ? AND classified = 1 AND lane = 'editorial'
        AND id NOT IN (SELECT raw_item_id FROM curated_items)""",
        (week_iso,),
    ).fetchone()
    discard_count: int = discard_row["cnt"] if discard_row else 0

    conn.close()

    # Group by section
    by_section: dict[str, list[dict]] = {}
    for row in rows:
        d = dict(row)
        sec = d["section"]
        if sec not in by_section:
            by_section[sec] = []
        if len(by_section[sec]) < limit:
            by_section[sec].append(d)

    # Stats: count per section
    stats: dict[str, int] = {}
    for row in rows:
        sec = row["section"]
        stats[sec] = stats.get(sec, 0) + 1

    total = len(rows)

    return {
        "week_iso": week_iso,
        "total": total,
        "discard_count": discard_count,
        "by_section": by_section,
        "stats": stats,
    }


def print_audit_report(result: dict) -> None:
    """Pretty-print the audit result for terminal review."""
    week_iso: str = result["week_iso"]
    total: int = result["total"]
    discard_count: int = result["discard_count"]
    by_section: dict[str, list[dict]] = result["by_section"]
    stats: dict[str, int] = result["stats"]

    grand_total = total + discard_count

    # Header
    print("")
    print("=" * 72)
    print(f"  CLASSIFIER AUDIT — {week_iso}")
    print("=" * 72)
    print(f"  Curated items:     {total}")
    print(f"  Auto-discarded:    {discard_count}")
    print(f"  Grand total:       {grand_total}")
    print("")

    # Section breakdown with percentages
    if stats or discard_count > 0:
        print("  Section breakdown:")
        for sec, count in sorted(stats.items(), key=lambda x: -x[1]):
            pct = (count / grand_total * 100) if grand_total > 0 else 0.0
            print(f"    {sec:30s}  {count:4d}  ({pct:5.1f}%)")
        if discard_count > 0:
            pct = (discard_count / grand_total * 100) if grand_total > 0 else 0.0
            print(f"    {'(auto-discarded)':30s}  {discard_count:4d}  ({pct:5.1f}%)")
        print("")

    # Per-section item details
    for sec in sorted(by_section.keys()):
        items = by_section[sec]
        print("-" * 72)
        print(f"  SECTION: {sec.upper()}  ({len(items)} items)")
        print("-" * 72)
        for item in items:
            title = item.get("title", "") or ""
            if len(title) > 70:
                title = title[:67] + "..."

            source = item.get("source", "")
            subreddit = item.get("subreddit", "")
            source_display = f"{source}"
            if subreddit:
                source_display += f" / {subreddit}"

            summary = item.get("summary", "") or ""
            if len(summary) > 100:
                summary = summary[:97] + "..."

            tags = item.get("tags", "") or ""
            confidence = item.get("confidence_tag", "") or ""

            print(f"  [{item['id']}] {title}")
            print(f"       Source: {source_display}")
            print(
                f"       Scores: rel={item['score_relevance']} "
                f"nov={item['score_novelty']} "
                f"rel={item['score_reliability']} "
                f"ten={item['score_tension']} "
                f"use={item['score_usefulness']} "
                f"| composite={item['weighted_composite']:.2f}"
            )
            if confidence:
                print(f"       Confidence: {confidence}")
            print(f"       Summary: {summary}")
            if tags:
                print(f"       Tags: {tags}")
            print("")

    # Review checklist
    print("=" * 72)
    print("  REVIEW CHECKLIST")
    print("=" * 72)
    print("  [ ] Are big_conversation_seed items genuinely debate-worthy?")
    print("  [ ] Are whisper items unverified/speculative (not hard news)?")
    print("  [ ] Are what_we_watching items forward-looking lead indicators?")
    print("  [ ] Are thread_candidate items high-engagement community discussions?")
    print("  [ ] Are finds items useful links/resources (not duplicates)?")
    print("  [ ] Were any items incorrectly auto-discarded?")
    print("  [ ] Do composite scores align with editorial judgment?")
    print("")
