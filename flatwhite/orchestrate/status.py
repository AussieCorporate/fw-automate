"""Pipeline status checker for the current week.

Reads database state and reports what has been completed for the current
week_iso. Used by the editor to check pipeline progress before reviewing
in Streamlit.
"""

from flatwhite.db import get_connection, get_current_week_iso
from flatwhite.orchestrate.runner import get_next_rotation


def get_pipeline_status() -> dict:
    """Check the current state of the pipeline for this week.

    Queries:
    - signals table: count for current week_iso
    - raw_items table: count for current week_iso
    - curated_items table: count for current week_iso (joined via raw_items.week_iso)
    - editor_decisions table: count of approved items for current week_iso
    - pulse_history table: score, direction, summary_text for current week_iso
    - newsletters table: check if current week_iso has a record

    Output: dict matching schema in Section 3.4.
    Consumed by: cli.py cmd_status().
    """
    week_iso = get_current_week_iso()
    conn = get_connection()

    # Signals count
    signals_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()
    signals_count = signals_row["cnt"] if signals_row else 0

    # Raw items count
    raw_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM raw_items WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()
    raw_items_count = raw_row["cnt"] if raw_row else 0

    # Curated items count
    curated_row = conn.execute(
        """SELECT COUNT(*) as cnt FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ?""",
        (week_iso,),
    ).fetchone()
    curated_items_count = curated_row["cnt"] if curated_row else 0

    # Approved items count
    approved_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM editor_decisions WHERE issue_week_iso = ? AND decision = 'approved'",
        (week_iso,),
    ).fetchone()
    approved_items_count = approved_row["cnt"] if approved_row else 0

    # Pulse data
    pulse_row = conn.execute(
        "SELECT composite_score, smoothed_score, direction, summary_text FROM pulse_history WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()

    pulse_score = pulse_row["smoothed_score"] if pulse_row else None
    pulse_direction = pulse_row["direction"] if pulse_row else None
    has_summary = bool(pulse_row and pulse_row["summary_text"] and len(pulse_row["summary_text"]) > 10)

    # Hook check — hooks are not stored in DB, so we infer from summary existence
    has_hooks = has_summary

    # Newsletter check
    newsletter_row = conn.execute(
        "SELECT week_iso FROM newsletters WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()
    has_newsletter = bool(newsletter_row)

    # Last published
    last_pub_row = conn.execute(
        "SELECT week_iso FROM newsletters WHERE published_at IS NOT NULL ORDER BY week_iso DESC LIMIT 1"
    ).fetchone()
    last_published = last_pub_row["week_iso"] if last_pub_row else None

    conn.close()

    rotation = get_next_rotation()

    return {
        "week_iso": week_iso,
        "signals_count": signals_count,
        "raw_items_count": raw_items_count,
        "curated_items_count": curated_items_count,
        "approved_items_count": approved_items_count,
        "pulse_score": round(pulse_score, 1) if pulse_score else None,
        "pulse_direction": pulse_direction,
        "has_summary": has_summary,
        "has_hooks": has_hooks,
        "has_newsletter": has_newsletter,
        "rotation": rotation,
        "last_published": last_published,
    }
