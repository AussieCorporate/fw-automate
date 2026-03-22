"""Local feedback loop — manual entry of newsletter performance metrics.

The editor views open/click rates in the newsletter analytics dashboard,
then records them here so the pipeline can track performance over time and
eventually use the data for classifier tuning.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flatwhite.db import get_connection, get_current_week_iso


def record_feedback(
    week_iso: str | None = None,
    open_rate: float | None = None,
    click_rate: float | None = None,
    notes: str | None = None,
) -> dict:
    """Record newsletter performance metrics for a given week.

    - Updates editor_decisions.click_rate for all decisions in that week.
    - Adds a ``notes`` column to newsletters if missing (ALTER TABLE).
    - Updates newsletters.published_at and notes for the week.

    Returns a dict with week_iso, click_rate, open_rate, decisions_updated.
    """
    if week_iso is None:
        week_iso = get_current_week_iso()

    conn = get_connection()

    # Ensure newsletters has a notes column (idempotent migration)
    try:
        conn.execute("ALTER TABLE newsletters ADD COLUMN notes TEXT")
    except Exception:
        pass  # Column already exists

    # Ensure newsletters has an open_rate column (idempotent migration)
    try:
        conn.execute("ALTER TABLE newsletters ADD COLUMN open_rate REAL")
    except Exception:
        pass  # Column already exists

    # Update editor_decisions.click_rate for the week
    decisions_updated = 0
    if click_rate is not None:
        cursor = conn.execute(
            "UPDATE editor_decisions SET click_rate = ? WHERE issue_week_iso = ?",
            (click_rate, week_iso),
        )
        decisions_updated = cursor.rowcount

    # Update newsletters row
    now_iso = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT id FROM newsletters WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()

    if existing:
        updates = ["published_at = ?"]
        params: list = [now_iso]
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if open_rate is not None:
            updates.append("open_rate = ?")
            params.append(open_rate)
        params.append(week_iso)
        conn.execute(
            f"UPDATE newsletters SET {', '.join(updates)} WHERE week_iso = ?",
            params,
        )
    else:
        conn.execute(
            "INSERT INTO newsletters (week_iso, beehiiv_post_id, rotation, published_at, notes, open_rate) "
            "VALUES (?, NULL, 'A', ?, ?, ?)",
            (week_iso, now_iso, notes, open_rate),
        )

    conn.commit()
    conn.close()

    result = {
        "week_iso": week_iso,
        "click_rate": click_rate,
        "open_rate": open_rate,
        "decisions_updated": decisions_updated,
    }
    return result


def get_feedback_history(weeks_back: int = 8) -> list[dict]:
    """Query editor_decisions grouped by issue_week_iso.

    Returns a list of dicts with:
        week_iso, avg_click_rate, total_decisions, approved_count, rejected_count
    Ordered by week_iso descending, limited to ``weeks_back`` weeks.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT
            ed.issue_week_iso AS week_iso,
            AVG(ed.click_rate) AS avg_click_rate,
            COUNT(*) AS total_decisions,
            SUM(CASE WHEN ed.decision = 'approved' THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN ed.decision = 'rejected' THEN 1 ELSE 0 END) AS rejected_count
        FROM editor_decisions ed
        WHERE ed.issue_week_iso IS NOT NULL
        GROUP BY ed.issue_week_iso
        ORDER BY ed.issue_week_iso DESC
        LIMIT ?""",
        (weeks_back,),
    ).fetchall()
    conn.close()

    return [
        {
            "week_iso": row["week_iso"],
            "avg_click_rate": row["avg_click_rate"],
            "total_decisions": row["total_decisions"],
            "approved_count": row["approved_count"],
            "rejected_count": row["rejected_count"],
        }
        for row in rows
    ]
