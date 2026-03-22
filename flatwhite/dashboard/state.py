"""Dashboard state management — DB reads and writes for the Flat White editor dashboard.

All database access for the dashboard is centralised here.
No LLM calls are made in this module. LLM calls are triggered by button clicks in view files.
"""

from __future__ import annotations
import json
from typing import Any
from flatwhite.db import get_connection, get_current_week_iso


def load_pulse_state() -> dict[str, Any] | None:
    """Return the pulse_history row for the current ISO week, or None if not found.

    Output keys: id, week_iso, composite_score, smoothed_score, direction,
                 drivers_json, summary_text, created_at.
    Consumed by: app.py -> pulse_view.render_pulse_view().
    """
    conn = get_connection()
    week_iso = get_current_week_iso()
    row = conn.execute(
        "SELECT * FROM pulse_history WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def load_signals_this_week() -> list[dict[str, Any]]:
    """Return all pulse-lane signals for the current ISO week, sorted by score descending.

    Output keys per item: id, signal_name, lane, area, raw_value, normalised_score,
                          source_weight, pulled_at, week_iso.
    Consumed by: app.py -> pulse_view.render_pulse_view().
    """
    conn = get_connection()
    week_iso = get_current_week_iso()
    rows = conn.execute(
        "SELECT * FROM signals WHERE week_iso = ? AND lane = 'pulse' ORDER BY normalised_score DESC",
        (week_iso,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_curated_items_by_section() -> dict[str, list[dict[str, Any]]]:
    """Return curated items for the current week grouped by section.

    Joins curated_items with raw_items for content fields.
    Left-joins editor_decisions to surface existing decisions.
    Excludes items with section='discard'.

    Output: dict with keys 'whisper', 'big_conversation_seed', 'what_we_watching',
            'thread_candidate', 'finds'. Each value is a list of dicts.
    Each dict has all curated_items columns plus: title, body, source, url,
    subreddit (from raw_items), decision (from editor_decisions, may be None),
    decision_id (from editor_decisions, may be None).
    Sorted by weighted_composite DESC within each section.
    Consumed by: app.py -> curation_view.render_curation_view().
    """
    conn = get_connection()
    week_iso = get_current_week_iso()
    rows = conn.execute(
        """
        SELECT
            ci.id, ci.raw_item_id, ci.section, ci.summary,
            ci.score_relevance, ci.score_novelty, ci.score_reliability,
            ci.score_tension, ci.score_usefulness,
            ci.weighted_composite, ci.tags, ci.confidence_tag, ci.created_at,
            ri.title, ri.body, ri.source, ri.url, ri.subreddit,
            ed.decision, ed.id AS decision_id
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        LEFT JOIN editor_decisions ed
            ON ed.curated_item_id = ci.id AND ed.issue_week_iso = ?
        WHERE ri.week_iso = ? AND ci.section != 'discard'
        ORDER BY ci.weighted_composite DESC
        """,
        (week_iso, week_iso),
    ).fetchall()
    conn.close()

    sections: dict[str, list[dict[str, Any]]] = {
        "whisper": [],
        "big_conversation_seed": [],
        "what_we_watching": [],
        "thread_candidate": [],
        "finds": [],
    }
    for row in rows:
        d = dict(row)
        section = d["section"]
        if section in sections:
            sections[section].append(d)
    return sections


def load_top_thread() -> dict[str, Any] | None:
    """Return the highest-weighted thread_candidate for the current week, or None.

    Joins curated_items with raw_items and surfaces the existing editor decision if any.
    Output keys: all curated_items columns + title, body, source, url, subreddit,
                 decision, decision_id.
    Consumed by: app.py -> thread_view.render_thread_view().
    """
    threads = load_top_threads()
    return threads[0] if threads else None


def load_top_threads(limit: int = 10, weeks: int = 1) -> list[dict[str, Any]]:
    """Return the top r/auscorp thread_candidates, up to limit.

    Joins curated_items with raw_items and surfaces existing editor decisions.
    Includes top_comments (parsed from JSON) and our_take.

    Args:
        limit: maximum number of threads to return.
        weeks: 1 = current week only, 2 = current + previous week (fortnight).

    Output: list of dicts with curated_items + raw_items + decision columns.
    Consumed by: api.py -> /api/threads endpoint, load_top_thread() fallback.
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    if weeks >= 2:
        # Build list of week ISOs to include (current + previous weeks)
        import datetime
        year, week_num = int(week_iso[:4]), int(week_iso[6:])
        # Parse ISO week correctly using %G (ISO year) and %V (ISO week)
        dt = datetime.datetime.strptime(f"{year}-W{week_num:02d}-1", "%G-W%V-%u")
        week_isos = [week_iso]
        for i in range(1, weeks):
            prev = dt - datetime.timedelta(weeks=i)
            week_isos.append(prev.strftime("%G-W%V"))
        placeholders = ",".join("?" for _ in week_isos)
        current_week_iso = week_iso
        params = [current_week_iso] + week_isos + [limit]
        rows = conn.execute(
            f"""
            SELECT
                ci.id, ci.section, ci.summary, ci.score_relevance, ci.score_novelty,
                ci.score_reliability, ci.score_tension, ci.score_usefulness,
                ci.weighted_composite, ci.tags, ci.confidence_tag, ci.our_take,
                ri.title, ri.body, ri.source, ri.url, ri.subreddit, ri.top_comments,
                ri.week_iso AS thread_week_iso, ri.pulled_at,
                ed.decision, ed.id AS decision_id
            FROM curated_items ci
            JOIN raw_items ri ON ci.raw_item_id = ri.id
            LEFT JOIN editor_decisions ed
                ON ed.curated_item_id = ci.id AND ed.issue_week_iso = ?
            WHERE ri.week_iso IN ({placeholders})
              AND ci.section = 'thread_candidate'
              AND ri.subreddit = 'auscorp'
            ORDER BY ci.weighted_composite DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                ci.id, ci.section, ci.summary, ci.score_relevance, ci.score_novelty,
                ci.score_reliability, ci.score_tension, ci.score_usefulness,
                ci.weighted_composite, ci.tags, ci.confidence_tag, ci.our_take,
                ri.title, ri.body, ri.source, ri.url, ri.subreddit, ri.top_comments,
                ri.week_iso AS thread_week_iso, ri.pulled_at,
                ed.decision, ed.id AS decision_id
            FROM curated_items ci
            JOIN raw_items ri ON ci.raw_item_id = ri.id
            LEFT JOIN editor_decisions ed
                ON ed.curated_item_id = ci.id AND ed.issue_week_iso = ?
            WHERE ri.week_iso = ?
              AND ci.section = 'thread_candidate'
              AND ri.subreddit = 'auscorp'
            ORDER BY ci.weighted_composite DESC
            LIMIT ?
            """,
            (week_iso, week_iso, limit),
        ).fetchall()
    conn.close()

    result = []
    for row in rows:
        d = dict(row)
        # Parse top_comments JSON — normalise old string-only format to dicts
        raw_comments = d.get("top_comments")
        if raw_comments:
            try:
                parsed = json.loads(raw_comments)
                # Normalise old format: ["text", ...] → [{"text": ..., "score": 0}, ...]
                if parsed and isinstance(parsed[0], str):
                    parsed = [{"text": c, "score": 0} for c in parsed]
                d["top_comments"] = parsed
            except Exception:
                d["top_comments"] = []
        else:
            d["top_comments"] = []
        result.append(d)
    return result


def load_seed_items() -> list[dict[str, Any]]:
    """Return up to 10 big_conversation_seed items for the current week, sorted by score desc.

    Output keys per item: id, summary, tags, weighted_composite, title, source, url.
    Consumed by: app.py -> big_conv_view.render_big_conversation_view().
    """
    conn = get_connection()
    week_iso = get_current_week_iso()
    rows = conn.execute(
        """
        SELECT ci.id, ci.summary, ci.tags, ci.weighted_composite,
               ri.title, ri.source, ri.url
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ? AND ci.section = 'big_conversation_seed'
        ORDER BY ci.weighted_composite DESC
        LIMIT 10
        """,
        (week_iso,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_editor_decision(
    curated_item_id: int,
    decision: str,
    section_placed: str | None,
    issue_week_iso: str,
) -> int:
    """Insert or replace an editor decision for a curated item.

    If a decision for this curated_item_id + issue_week_iso already exists,
    it is deleted and replaced. This ensures one active decision per item per week.

    Input:
        curated_item_id: int — curated_items.id
        decision: str — one of 'approved', 'rejected', 'reserve'
        section_placed: str | None — section key (e.g. 'whisper', 'what_we_watching') or None
        issue_week_iso: str — the ISO week this decision belongs to

    Output: int — the new editor_decisions.id (lastrowid).
    Consumed by: curation_view.py, thread_view.py.
    """
    conn = get_connection()
    conn.execute(
        "DELETE FROM editor_decisions WHERE curated_item_id = ? AND issue_week_iso = ?",
        (curated_item_id, issue_week_iso),
    )
    cursor = conn.execute(
        """INSERT INTO editor_decisions (curated_item_id, decision, section_placed, issue_week_iso)
           VALUES (?, ?, ?, ?)""",
        (curated_item_id, decision, section_placed, issue_week_iso),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def save_big_conversation_draft(
    headline: str,
    pitch: str,
    supporting_item_ids: list[int],
    draft_text: str,
) -> int:
    """Save a Big Conversation draft to the drafts table with status='approved'.

    Any previous drafts for the same week and section are set to 'discarded'.
    Input: headline (str), pitch (str), supporting_item_ids (list[int]), draft_text (str).
    Output: int — the new draft row ID.
    Consumed by: big_conv_view.py "Save Draft" button.
    """
    import json
    week_iso = get_current_week_iso()
    conn = get_connection()

    # Discard any previous approved drafts for this week/section
    conn.execute(
        """UPDATE drafts SET status = 'discarded', updated_at = datetime('now')
        WHERE week_iso = ? AND section = 'big_conversation' AND status = 'approved'""",
        (week_iso,),
    )

    cursor = conn.execute(
        """INSERT INTO drafts
        (week_iso, section, headline, pitch, supporting_item_ids, draft_text, status)
        VALUES (?, 'big_conversation', ?, ?, ?, ?, 'approved')""",
        (week_iso, headline, pitch, json.dumps(supporting_item_ids), draft_text),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def save_thread_our_take(curated_item_id: int, our_take: str) -> None:
    """Update the our_take field on a curated_item (editor-revised thread editorial).

    Input:
        curated_item_id: int — curated_items.id
        our_take: str — editor-revised 2-3 sentence editorial take

    Consumed by: api.py -> POST /api/thread-take.
    """
    conn = get_connection()
    conn.execute(
        "UPDATE curated_items SET our_take = ? WHERE id = ?",
        (our_take.strip(), curated_item_id),
    )
    conn.commit()
    conn.close()


def load_saved_draft(section: str = "big_conversation") -> dict | None:
    """Load the most recent approved draft for the current week and given section.

    Output: dict with draft fields, or None if no approved draft exists.
    Consumed by: big_conv_view.py to show previously saved draft, Session 4 renderer.
    """
    week_iso = get_current_week_iso()
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM drafts
        WHERE week_iso = ? AND section = ? AND status = 'approved'
        ORDER BY updated_at DESC LIMIT 1""",
        (week_iso, section),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
