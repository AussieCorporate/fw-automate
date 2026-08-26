"""Tests for flatwhite.dashboard.tac_instagram_state - topic bank / calendar /
quarterly planner read-write functions.

Uses the shared `temp_db` fixture (tests/conftest.py), which patches
flatwhite.db.DB_PATH to a tmp_path sqlite file and runs init_db(). All
functions under test read/write via flatwhite.db.get_connection(), which
picks up the patched path.
"""

from __future__ import annotations

import datetime
import sqlite3

import pytest

import flatwhite.db as db_module
from flatwhite.dashboard import tac_instagram_state as tis


def _frozen_today(monkeypatch, iso_date):
    """Freeze tis's notion of "today" so today_actions' default-arg branch
    is deterministic. Mirrors tests/test_brains_trust_refresh.py's
    _frozen_today helper."""
    fixed = datetime.datetime.strptime(iso_date, "%Y%m%d").date()

    class _FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return fixed

    class _FixedDateTimeModule:
        date = _FixedDate
        timedelta = datetime.timedelta
        datetime = datetime.datetime

    monkeypatch.setattr(tis, "datetime", _FixedDateTimeModule)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_topic(**overrides) -> int:
    fields = {
        "topic_number": 1,
        "topic": "Is staying loyal to one company still worth it?",
        "best_format": "Big Conversation",
        "content_pillar": "Money & Salary",
        "engagement_level": "High",
        "used": 0,
        "used_date": None,
        "angle_notes": None,
        "community_question": None,
        "tac_answer": None,
    }
    fields.update(overrides)
    conn = db_module.get_connection()
    cursor = conn.execute(
        """INSERT INTO tac_topic_bank
           (topic_number, topic, best_format, content_pillar, engagement_level,
            used, used_date, angle_notes, community_question, tac_answer)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fields["topic_number"],
            fields["topic"],
            fields["best_format"],
            fields["content_pillar"],
            fields["engagement_level"],
            fields["used"],
            fields["used_date"],
            fields["angle_notes"],
            fields["community_question"],
            fields["tac_answer"],
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def _insert_quarterly(**overrides) -> int:
    fields = {
        "item_number": 1,
        "campaign_event": "Graduate Salary Survey",
        "type": "Survey Campaign",
        "launch_date": "2 Jun 2026",
        "close_event_date": "16 Jun 2026",
        "results_publish": "23 Jun 2026",
        "sponsor": 1,
        "notes": "Run 2 weeks.",
        "quarter_label": "Q2 2026  ·  APR – JUN",
    }
    fields.update(overrides)
    conn = db_module.get_connection()
    cursor = conn.execute(
        """INSERT INTO tac_quarterly_planner
           (item_number, campaign_event, type, launch_date, close_event_date,
            results_publish, sponsor, notes, quarter_label)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fields["item_number"],
            fields["campaign_event"],
            fields["type"],
            fields["launch_date"],
            fields["close_event_date"],
            fields["results_publish"],
            fields["sponsor"],
            fields["notes"],
            fields["quarter_label"],
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


# ---------------------------------------------------------------------------
# list_topics
# ---------------------------------------------------------------------------


def test_list_topics_no_filters_returns_all(temp_db):
    _insert_topic(topic_number=1, topic="Topic A")
    _insert_topic(topic_number=2, topic="Topic B")

    rows = tis.list_topics()

    assert len(rows) == 2
    assert {r["topic"] for r in rows} == {"Topic A", "Topic B"}


def test_list_topics_filters_by_pillar(temp_db):
    _insert_topic(topic_number=1, topic="Salary topic", content_pillar="Money & Salary")
    _insert_topic(topic_number=2, topic="Culture topic", content_pillar="Workplace Culture")

    rows = tis.list_topics(pillar="Money & Salary")

    assert len(rows) == 1
    assert rows[0]["topic"] == "Salary topic"


def test_list_topics_filters_by_best_format(temp_db):
    _insert_topic(topic_number=1, topic="BC topic", best_format="Big Conversation")
    _insert_topic(topic_number=2, topic="Reel topic", best_format="Reel")

    rows = tis.list_topics(best_format="Reel")

    assert len(rows) == 1
    assert rows[0]["topic"] == "Reel topic"


def test_list_topics_filters_by_engagement_level(temp_db):
    _insert_topic(topic_number=1, topic="Hot topic", engagement_level="High")
    _insert_topic(topic_number=2, topic="Cold topic", engagement_level="Low")

    rows = tis.list_topics(engagement_level="Low")

    assert len(rows) == 1
    assert rows[0]["topic"] == "Cold topic"


def test_list_topics_filters_by_used(temp_db):
    _insert_topic(topic_number=1, topic="Used topic", used=1, used_date="1 Jun 2026")
    _insert_topic(topic_number=2, topic="Unused topic", used=0)

    used_rows = tis.list_topics(used=True)
    unused_rows = tis.list_topics(used=False)

    assert len(used_rows) == 1
    assert used_rows[0]["topic"] == "Used topic"
    assert len(unused_rows) == 1
    assert unused_rows[0]["topic"] == "Unused topic"


def test_list_topics_combines_filters(temp_db):
    _insert_topic(
        topic_number=1, topic="Match",
        content_pillar="Money & Salary", best_format="Reel",
        engagement_level="High", used=0,
    )
    _insert_topic(
        topic_number=2, topic="Wrong pillar",
        content_pillar="Workplace Culture", best_format="Reel",
        engagement_level="High", used=0,
    )
    _insert_topic(
        topic_number=3, topic="Wrong format",
        content_pillar="Money & Salary", best_format="Carousel",
        engagement_level="High", used=0,
    )

    rows = tis.list_topics(
        pillar="Money & Salary", best_format="Reel",
        engagement_level="High", used=False,
    )

    assert len(rows) == 1
    assert rows[0]["topic"] == "Match"


def test_list_topics_returns_dicts_with_all_columns(temp_db):
    _insert_topic(topic_number=1, topic="Topic A", angle_notes="Some angle")

    rows = tis.list_topics()

    assert isinstance(rows[0], dict)
    assert rows[0]["angle_notes"] == "Some angle"
    assert "id" in rows[0]


# ---------------------------------------------------------------------------
# next_unused_topic
# ---------------------------------------------------------------------------


def test_next_unused_topic_returns_lowest_topic_number(temp_db):
    _insert_topic(topic_number=5, topic="Fifth", used=0)
    _insert_topic(topic_number=2, topic="Second", used=0)
    _insert_topic(topic_number=8, topic="Eighth", used=0)

    result = tis.next_unused_topic()

    assert result is not None
    assert result["topic_number"] == 2
    assert result["topic"] == "Second"


def test_next_unused_topic_skips_used_topics(temp_db):
    _insert_topic(topic_number=1, topic="Used first", used=1, used_date="1 Jun 2026")
    _insert_topic(topic_number=2, topic="Unused second", used=0)

    result = tis.next_unused_topic()

    assert result is not None
    assert result["topic_number"] == 2


def test_next_unused_topic_respects_format_filter(temp_db):
    _insert_topic(topic_number=1, topic="Reel topic", best_format="Reel", used=0)
    _insert_topic(topic_number=2, topic="Carousel topic", best_format="Carousel", used=0)

    result = tis.next_unused_topic(best_format_contains="Carousel")

    assert result is not None
    assert result["topic"] == "Carousel topic"


def test_next_unused_topic_returns_none_when_none_match(temp_db):
    _insert_topic(topic_number=1, topic="Used", used=1, used_date="1 Jun 2026")

    result = tis.next_unused_topic()

    assert result is None


def test_next_unused_topic_returns_none_when_format_filter_matches_nothing(temp_db):
    _insert_topic(topic_number=1, topic="Reel topic", best_format="Reel", used=0)

    result = tis.next_unused_topic(best_format_contains="Big Conversation")

    assert result is None


# ---------------------------------------------------------------------------
# mark_topic_used
# ---------------------------------------------------------------------------


def test_mark_topic_used_sets_used_and_used_date(temp_db):
    topic_id = _insert_topic(topic_number=1, topic="Topic A", used=0)

    result = tis.mark_topic_used(topic_id, used_date="5 Jun 2026")

    assert result is True
    rows = tis.list_topics()
    assert rows[0]["used"] == 1
    assert rows[0]["used_date"] == "5 Jun 2026"


def test_mark_topic_used_defaults_used_date_to_today(temp_db):
    import datetime

    topic_id = _insert_topic(topic_number=1, topic="Topic A", used=0)

    tis.mark_topic_used(topic_id)

    rows = tis.list_topics()
    assert rows[0]["used"] == 1
    assert rows[0]["used_date"] == datetime.date.today().isoformat()


def test_mark_topic_used_returns_false_for_missing_id(temp_db):
    result = tis.mark_topic_used(99999)

    assert result is False


# ---------------------------------------------------------------------------
# add_topic
# ---------------------------------------------------------------------------


def test_add_topic_returns_new_id_and_persists(temp_db):
    new_id = tis.add_topic(
        topic="Should salary bands be public?",
        best_format="Carousel",
        content_pillar="Money & Salary",
        engagement_level="High",
        angle_notes="Transparency angle",
        community_question="Should companies publish salary bands?",
        tac_answer="Transparency helps everyone negotiate.",
    )

    assert isinstance(new_id, int)
    rows = tis.list_topics()
    assert len(rows) == 1
    assert rows[0]["id"] == new_id
    assert rows[0]["topic"] == "Should salary bands be public?"
    assert rows[0]["best_format"] == "Carousel"
    assert rows[0]["used"] == 0


def test_add_topic_minimal_args(temp_db):
    new_id = tis.add_topic(topic="Bare minimum topic")

    rows = tis.list_topics()
    assert rows[0]["id"] == new_id
    assert rows[0]["topic"] == "Bare minimum topic"
    assert rows[0]["best_format"] is None


# ---------------------------------------------------------------------------
# tac_calendar CRUD
# ---------------------------------------------------------------------------


def test_list_calendar_no_filters(temp_db):
    tis.add_calendar_row(post_date="11 May 2026", day_of_week="Monday", week_label="WEEK 1")
    tis.add_calendar_row(post_date="18 May 2026", day_of_week="Monday", week_label="WEEK 2")

    rows = tis.list_calendar()

    assert len(rows) == 2


def test_list_calendar_filters_by_week_label(temp_db):
    tis.add_calendar_row(post_date="11 May 2026", week_label="WEEK 1")
    tis.add_calendar_row(post_date="18 May 2026", week_label="WEEK 2")

    rows = tis.list_calendar(week_label="WEEK 2")

    assert len(rows) == 1
    assert rows[0]["post_date"] == "18 May 2026"


def test_list_calendar_filters_by_status(temp_db):
    tis.add_calendar_row(post_date="11 May 2026", status="Scheduled")
    tis.add_calendar_row(post_date="18 May 2026", status="Not Started")

    rows = tis.list_calendar(status="Scheduled")

    assert len(rows) == 1
    assert rows[0]["post_date"] == "11 May 2026"


def test_add_calendar_row_round_trip(temp_db):
    row_id = tis.add_calendar_row(
        post_date="11 May 2026",
        day_of_week="Monday",
        post_type="Reel",
        content_pillar="Career Advice",
        caption_hook="Hook text",
        status="Scheduled",
        notes="Some notes",
        week_label="WEEK 1",
    )

    rows = tis.list_calendar()
    assert len(rows) == 1
    assert rows[0]["id"] == row_id
    assert rows[0]["post_type"] == "Reel"
    assert rows[0]["caption_hook"] == "Hook text"
    assert rows[0]["status"] == "Scheduled"


def test_update_calendar_row_round_trip(temp_db):
    row_id = tis.add_calendar_row(post_date="11 May 2026", status="Not Started")

    updated = tis.update_calendar_row(row_id, status="Scheduled", caption_hook="New hook")

    assert updated is True
    rows = tis.list_calendar()
    assert rows[0]["status"] == "Scheduled"
    assert rows[0]["caption_hook"] == "New hook"


def test_update_calendar_row_returns_false_for_missing_id(temp_db):
    result = tis.update_calendar_row(99999, status="Scheduled")

    assert result is False


def test_add_calendar_row_rejects_unknown_field(temp_db):
    with pytest.raises(ValueError):
        tis.add_calendar_row(post_date="11 May 2026", not_a_real_field="x")


def test_update_calendar_row_rejects_unknown_field(temp_db):
    row_id = tis.add_calendar_row(post_date="11 May 2026")

    with pytest.raises(ValueError):
        tis.update_calendar_row(row_id, not_a_real_field="x")


# ---------------------------------------------------------------------------
# tac_quarterly_planner
# ---------------------------------------------------------------------------


def test_list_quarterly_no_filters(temp_db):
    tis.add_quarterly_item(campaign_event="Survey A", quarter_label="Q2 2026")
    tis.add_quarterly_item(campaign_event="Survey B", quarter_label="Q3 2026")

    rows = tis.list_quarterly()

    assert len(rows) == 2


def test_list_quarterly_filters_by_quarter_label(temp_db):
    tis.add_quarterly_item(campaign_event="Survey A", quarter_label="Q2 2026")
    tis.add_quarterly_item(campaign_event="Survey B", quarter_label="Q3 2026")

    rows = tis.list_quarterly(quarter_label="Q3 2026")

    assert len(rows) == 1
    assert rows[0]["campaign_event"] == "Survey B"


def test_add_quarterly_item_round_trip(temp_db):
    row_id = tis.add_quarterly_item(
        campaign_event="Graduate Salary Survey",
        type="Survey Campaign",
        launch_date="2 Jun 2026",
        close_event_date="16 Jun 2026",
        results_publish="23 Jun 2026",
        sponsor=1,
        notes="Run 2 weeks.",
        quarter_label="Q2 2026",
    )

    rows = tis.list_quarterly()
    assert len(rows) == 1
    assert rows[0]["id"] == row_id
    assert rows[0]["launch_date"] == "2 Jun 2026"
    assert rows[0]["sponsor"] == 1


# ---------------------------------------------------------------------------
# generate_survey_week_rows
# ---------------------------------------------------------------------------


def test_generate_survey_week_rows_produces_five_rows(temp_db):
    item_id = _insert_quarterly(
        campaign_event="Graduate Salary Survey", launch_date="2 Jun 2026",
    )

    row_ids = tis.generate_survey_week_rows(item_id)

    assert len(row_ids) == 5
    rows = tis.list_calendar()
    assert len(rows) == 5


def test_generate_survey_week_rows_dates_relative_to_launch_date(temp_db):
    # 2 Jun 2026 is a Tuesday - the Monday of that week is 1 Jun 2026.
    item_id = _insert_quarterly(
        campaign_event="Graduate Salary Survey", launch_date="2 Jun 2026",
    )

    row_ids = tis.generate_survey_week_rows(item_id)

    rows = tis.list_calendar()
    by_id = {r["id"]: r for r in rows}
    ordered = [by_id[i] for i in row_ids]

    expected_dates = ["1 Jun 2026", "2 Jun 2026", "3 Jun 2026", "4 Jun 2026", "5 Jun 2026"]
    expected_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    assert [r["post_date"] for r in ordered] == expected_dates
    assert [r["day_of_week"] for r in ordered] == expected_days


def test_generate_survey_week_rows_content_pillar_and_notes(temp_db):
    item_id = _insert_quarterly(
        campaign_event="Graduate Salary Survey", launch_date="2 Jun 2026",
    )

    row_ids = tis.generate_survey_week_rows(item_id)

    rows = tis.list_calendar()
    for r in rows:
        assert r["content_pillar"] == "Survey Campaign"
        assert "Graduate Salary Survey" in r["notes"]


def test_generate_survey_week_rows_month_and_year_boundary(temp_db):
    # 1 Jan 2027 is a Friday - the Monday of that week is 28 Dec 2026, which
    # crosses both a month boundary and a year boundary from the launch_date.
    item_id = _insert_quarterly(
        campaign_event="New Year Survey", launch_date="1 Jan 2027",
    )

    row_ids = tis.generate_survey_week_rows(item_id)

    rows = tis.list_calendar()
    by_id = {r["id"]: r for r in rows}
    ordered = [by_id[i] for i in row_ids]

    expected_dates = [
        "28 Dec 2026", "29 Dec 2026", "30 Dec 2026", "31 Dec 2026", "1 Jan 2027",
    ]
    expected_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    assert [r["post_date"] for r in ordered] == expected_dates
    assert [r["day_of_week"] for r in ordered] == expected_days


def test_generate_survey_week_rows_monday_already_a_monday(temp_db):
    # 1 Jun 2026 is already a Monday - Monday of that week should stay 1 Jun 2026.
    item_id = _insert_quarterly(
        campaign_event="Graduate Salary Survey", launch_date="1 Jun 2026",
    )

    row_ids = tis.generate_survey_week_rows(item_id)

    rows = {r["id"]: r for r in tis.list_calendar()}
    monday_row = rows[row_ids[0]]
    assert monday_row["post_date"] == "1 Jun 2026"
    assert monday_row["day_of_week"] == "Monday"


def test_generate_survey_week_rows_raises_for_missing_item(temp_db):
    with pytest.raises(ValueError):
        tis.generate_survey_week_rows(99999)


def test_generate_survey_week_rows_raises_for_missing_launch_date(temp_db):
    item_id = _insert_quarterly(
        campaign_event="Graduate Salary Survey", launch_date=None,
    )

    with pytest.raises(ValueError):
        tis.generate_survey_week_rows(item_id)


# ---------------------------------------------------------------------------
# today_actions
# ---------------------------------------------------------------------------
# All dates below are real 2026 dates: 24-30 Aug 2026 is Mon-Sun.


def test_today_actions_monday_suggests_plain_oldest_unused_topic(temp_db):
    _insert_topic(topic_number=2, topic="Second", best_format="Reel", used=0)
    _insert_topic(topic_number=1, topic="First", best_format="Carousel", used=0)

    actions = tis.today_actions(today=datetime.date(2026, 8, 24))

    assert len(actions) == 1
    assert actions[0]["time"] == "9:00 AM"
    assert actions[0]["day"] == "Monday"
    assert "farm the week's theme" in actions[0]["task"]
    assert actions[0]["suggested_topic"]["topic"] == "First"


def test_today_actions_tuesday_has_four_items_none_suggest_topics(temp_db):
    _insert_topic(topic_number=1, topic="Unused", used=0)

    actions = tis.today_actions(today=datetime.date(2026, 8, 25))

    assert len(actions) == 4
    assert [a["time"] for a in actions] == ["9:00 AM", "2:00 PM", "2:10 PM", "2:30 PM"]
    assert all(a["day"] == "Tuesday" for a in actions)
    assert all(a["suggested_topic"] is None for a in actions)


def test_today_actions_wednesday_filters_big_conversation_format(temp_db):
    _insert_topic(topic_number=1, topic="Reel topic", best_format="Reel", used=0)
    _insert_topic(topic_number=2, topic="BC topic", best_format="Big Conversation", used=0)

    actions = tis.today_actions(today=datetime.date(2026, 8, 26))

    assert len(actions) == 1
    assert actions[0]["time"] == "11:00 AM"
    assert actions[0]["day"] == "Wednesday"
    assert actions[0]["suggested_topic"]["topic"] == "BC topic"


def test_today_actions_thursday_filters_meme_format(temp_db):
    _insert_topic(topic_number=1, topic="Reel topic", best_format="Reel", used=0)
    _insert_topic(topic_number=2, topic="Meme topic", best_format="Meme", used=0)

    actions = tis.today_actions(today=datetime.date(2026, 8, 27))

    assert len(actions) == 1
    assert actions[0]["time"] == "12:00 PM"
    assert actions[0]["day"] == "Thursday"
    assert actions[0]["suggested_topic"]["topic"] == "Meme topic"


def test_today_actions_friday_has_four_items_first_suggests_plain_topic(temp_db):
    _insert_topic(topic_number=1, topic="Oldest", used=0)

    actions = tis.today_actions(today=datetime.date(2026, 8, 28))

    assert len(actions) == 4
    assert [a["time"] for a in actions] == ["9:00 AM", "9:05 AM", "9:10 AM", "11:30 AM"]
    assert all(a["day"] == "Friday" for a in actions)
    assert actions[0]["suggested_topic"]["topic"] == "Oldest"
    assert all(a["suggested_topic"] is None for a in actions[1:])


def test_today_actions_saturday_is_empty(temp_db):
    actions = tis.today_actions(today=datetime.date(2026, 8, 29))

    assert actions == []


def test_today_actions_sunday_is_empty(temp_db):
    actions = tis.today_actions(today=datetime.date(2026, 8, 30))

    assert actions == []


def test_today_actions_no_matching_unused_topic_returns_none(temp_db):
    _insert_topic(topic_number=1, topic="Used already", used=1, used_date="1 Jun 2026")

    actions = tis.today_actions(today=datetime.date(2026, 8, 24))

    assert actions[0]["suggested_topic"] is None


def test_today_actions_defaults_to_real_today(temp_db, monkeypatch):
    _insert_topic(topic_number=1, topic="Frozen Monday topic", used=0)
    _frozen_today(monkeypatch, "20260824")  # a Monday

    actions = tis.today_actions()

    assert len(actions) == 1
    assert actions[0]["day"] == "Monday"
    assert actions[0]["suggested_topic"]["topic"] == "Frozen Monday topic"
