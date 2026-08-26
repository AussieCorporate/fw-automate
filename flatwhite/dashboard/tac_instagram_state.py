"""TAC Instagram tab state - DB reads and writes for the topic bank, calendar
and quarterly planner tables (see flatwhite/db.py SCHEMA_SQL).

All database access for the TAC Instagram tab is centralised here.
No LLM calls are made in this module.
"""

from __future__ import annotations

import datetime
from typing import Any

from flatwhite.db import get_connection

# Date strings in these three tables are stored in the same free-text format
# the source workbook uses, e.g. "2 Jun 2026" (see
# scripts/import_tac_instagram_calendar.py and its tests). ISO ("2026-06-02")
# is accepted too, for rows added straight through this module.
_DATE_FORMATS = ("%d %b %Y", "%Y-%m-%d", "%d %B %Y")

_CALENDAR_FIELDS = {
    "post_date", "day_of_week", "post_type", "content_pillar", "caption_hook",
    "story_cta_link", "canva_project", "visual_asset", "collab_tag",
    "publish_time", "status", "notes", "week_label", "topic_bank_id",
}

_QUARTERLY_FIELDS = {
    "item_number", "campaign_event", "type", "launch_date", "close_event_date",
    "results_publish", "sponsor", "notes", "quarter_label",
}

# (day offset from Monday, day name, post type, notes template)
_SURVEY_WEEK_PLAN = [
    (0, "Monday", "Carousel + Story", "Launch carousel + story for {campaign}"),
    (1, "Tuesday", "Newsletter Feature", "Newsletter feature for {campaign}"),
    (2, "Wednesday", "Big Conversation", "Big Conversation on the {campaign} survey topic"),
    (3, "Thursday", "Reminder Meme", "Reminder meme for {campaign}"),
    (4, "Friday", "Open Floor Questions", "Open Floor questions for {campaign}"),
]


def _parse_date(date_str: str) -> datetime.date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {date_str!r}")


def _format_date(d: datetime.date) -> str:
    """Format like the imported workbook does: '2 Jun 2026' (no leading zero)."""
    return f"{d.day} {d.strftime('%b')} {d.year}"


# ---------------------------------------------------------------------------
# tac_topic_bank
# ---------------------------------------------------------------------------


def list_topics(
    pillar: str | None = None,
    best_format: str | None = None,
    engagement_level: str | None = None,
    used: bool | int | None = None,
) -> list[dict]:
    """List tac_topic_bank rows, filters combine with AND.

    Ordered by topic_number ascending (nulls last), then id.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if pillar is not None:
        clauses.append("content_pillar = ?")
        params.append(pillar)
    if best_format is not None:
        clauses.append("best_format = ?")
        params.append(best_format)
    if engagement_level is not None:
        clauses.append("engagement_level = ?")
        params.append(engagement_level)
    if used is not None:
        clauses.append("used = ?")
        params.append(1 if used else 0)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT * FROM tac_topic_bank {where}
            ORDER BY (topic_number IS NULL), topic_number, id""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_topic_used(topic_id: int, used_date: str | None = None) -> bool:
    """Mark a topic used, setting used_date (defaults to today, ISO YYYY-MM-DD).

    Returns True if a row was updated, False if topic_id doesn't exist.
    """
    if used_date is None:
        used_date = datetime.date.today().isoformat()
    conn = get_connection()
    cursor = conn.execute(
        """UPDATE tac_topic_bank
           SET used = 1, used_date = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (used_date, topic_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def add_topic(
    topic: str,
    best_format: str | None = None,
    content_pillar: str | None = None,
    engagement_level: str | None = None,
    angle_notes: str | None = None,
    community_question: str | None = None,
    tac_answer: str | None = None,
) -> int:
    """Insert a new topic bank row. topic_number is set to one past the current max.

    Returns the new row's id.
    """
    conn = get_connection()
    max_num = conn.execute("SELECT MAX(topic_number) FROM tac_topic_bank").fetchone()[0]
    next_num = (max_num or 0) + 1
    cursor = conn.execute(
        """INSERT INTO tac_topic_bank
           (topic_number, topic, best_format, content_pillar, engagement_level,
            angle_notes, community_question, tac_answer)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            next_num, topic, best_format, content_pillar, engagement_level,
            angle_notes, community_question, tac_answer,
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def next_unused_topic(best_format_contains: str | None = None) -> dict | None:
    """Return the unused topic with the lowest topic_number.

    Optionally filtered to best_format values containing
    `best_format_contains` (case-insensitive substring match).
    Returns None if no unused topic matches.
    """
    clauses = ["used = 0"]
    params: list[Any] = []
    if best_format_contains is not None:
        clauses.append("best_format LIKE ?")
        params.append(f"%{best_format_contains}%")
    where = " AND ".join(clauses)
    conn = get_connection()
    row = conn.execute(
        f"""SELECT * FROM tac_topic_bank
            WHERE {where}
            ORDER BY (topic_number IS NULL), topic_number, id
            LIMIT 1""",
        params,
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# tac_calendar
# ---------------------------------------------------------------------------


def list_calendar(week_label: str | None = None, status: str | None = None) -> list[dict]:
    """List tac_calendar rows, filters combine with AND. Ordered by id."""
    clauses: list[str] = []
    params: list[Any] = []
    if week_label is not None:
        clauses.append("week_label = ?")
        params.append(week_label)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = get_connection()
    rows = conn.execute(f"SELECT * FROM tac_calendar {where} ORDER BY id", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_calendar_row(**fields: Any) -> int:
    """Insert a tac_calendar row from keyword fields. Returns the new row's id."""
    unknown = set(fields) - _CALENDAR_FIELDS
    if unknown:
        raise ValueError(f"Unknown tac_calendar field(s): {sorted(unknown)}")
    columns = list(fields.keys())
    placeholders = ", ".join("?" for _ in columns)
    conn = get_connection()
    cursor = conn.execute(
        f"INSERT INTO tac_calendar ({', '.join(columns)}) VALUES ({placeholders})",
        [fields[c] for c in columns],
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def update_calendar_row(row_id: int, **fields: Any) -> bool:
    """Update a tac_calendar row by id. Returns True if a row was updated."""
    if not fields:
        return False
    unknown = set(fields) - _CALENDAR_FIELDS
    if unknown:
        raise ValueError(f"Unknown tac_calendar field(s): {sorted(unknown)}")
    set_clause = ", ".join(f"{c} = ?" for c in fields)
    conn = get_connection()
    cursor = conn.execute(
        f"UPDATE tac_calendar SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
        [*fields.values(), row_id],
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


# ---------------------------------------------------------------------------
# tac_quarterly_planner
# ---------------------------------------------------------------------------


def list_quarterly(quarter_label: str | None = None) -> list[dict]:
    """List tac_quarterly_planner rows, optionally filtered by quarter_label. Ordered by id."""
    clauses: list[str] = []
    params: list[Any] = []
    if quarter_label is not None:
        clauses.append("quarter_label = ?")
        params.append(quarter_label)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM tac_quarterly_planner {where} ORDER BY id", params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_quarterly_item(**fields: Any) -> int:
    """Insert a tac_quarterly_planner row from keyword fields. Returns the new row's id."""
    unknown = set(fields) - _QUARTERLY_FIELDS
    if unknown:
        raise ValueError(f"Unknown tac_quarterly_planner field(s): {sorted(unknown)}")
    columns = list(fields.keys())
    placeholders = ", ".join("?" for _ in columns)
    conn = get_connection()
    cursor = conn.execute(
        f"INSERT INTO tac_quarterly_planner ({', '.join(columns)}) VALUES ({placeholders})",
        [fields[c] for c in columns],
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def generate_survey_week_rows(quarterly_item_id: int) -> list[int]:
    """Insert the five standard survey-week tac_calendar rows for a quarterly item.

    Reads the quarterly item's launch_date, computes the Monday of that week,
    and inserts: Mon (launch carousel + story), Tue (newsletter feature),
    Wed (Big Conversation on the survey topic), Thu (reminder meme), Fri
    (Open Floor questions). Each row gets content_pillar='Survey Campaign'
    and notes referencing the campaign name.

    Raises ValueError if the quarterly item id doesn't exist or has no
    launch_date. Returns the five new tac_calendar row ids, Monday to Friday.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tac_quarterly_planner WHERE id = ?", (quarterly_item_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"tac_quarterly_planner row {quarterly_item_id} not found")

    item = dict(row)
    launch_date = item.get("launch_date")
    if not launch_date:
        conn.close()
        raise ValueError(f"tac_quarterly_planner row {quarterly_item_id} has no launch_date")

    parsed = _parse_date(launch_date)
    monday = parsed - datetime.timedelta(days=parsed.weekday())
    campaign_name = item.get("campaign_event") or "the campaign"

    row_ids: list[int] = []
    for offset, day_name, post_type, note_template in _SURVEY_WEEK_PLAN:
        post_date = monday + datetime.timedelta(days=offset)
        cursor = conn.execute(
            """INSERT INTO tac_calendar
               (post_date, day_of_week, post_type, content_pillar, notes, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                _format_date(post_date),
                day_name,
                post_type,
                "Survey Campaign",
                note_template.format(campaign=campaign_name),
                "Not Started",
            ),
        )
        row_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    return row_ids
