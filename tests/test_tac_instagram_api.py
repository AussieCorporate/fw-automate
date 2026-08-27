"""Tests for the TAC Instagram tab API routes - topic bank, calendar,
quarterly planner (flatwhite/dashboard/api.py, "TAC Instagram tab" group).

Follows the pattern in tests/test_brains_trust_refresh.py: fastapi.testclient
.TestClient against api_module.app, patching flatwhite.dashboard.tac_instagram_state
functions directly (one test per route). One integration-style test at the
bottom skips the mocks entirely - it runs the real one-time importer against
the real workbook into a temp_db, then hits the live GET /topics endpoint
end-to-end to confirm the topic count really is 118.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import flatwhite.db as db_module
import flatwhite.dashboard.api as api_module
from flatwhite.dashboard import tac_instagram_state as tis
from flatwhite.dashboard import big_conversation_bank as bcb
from flatwhite.dashboard.state import load_skill_run_outcome, save_skill_run_outcome


@pytest.fixture
def client() -> TestClient:
    return TestClient(api_module.app)


# ---------------------------------------------------------------------------
# Topic bank
# ---------------------------------------------------------------------------


def test_get_topics_lists_and_passes_filters(client):
    with patch.object(
        tis, "list_topics", return_value=[{"id": 1, "topic": "Sunday scaries"}]
    ) as mock_list:
        resp = client.get(
            "/api/tac-instagram/topics",
            params={
                "pillar": "Money & Salary",
                "best_format": "Big Conversation",
                "engagement_level": "High",
                "used": "false",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"topics": [{"id": 1, "topic": "Sunday scaries"}]}
    mock_list.assert_called_once_with(
        pillar="Money & Salary",
        best_format="Big Conversation",
        engagement_level="High",
        used=False,
    )


def test_get_topics_with_no_filters(client):
    with patch.object(tis, "list_topics", return_value=[]) as mock_list:
        resp = client.get("/api/tac-instagram/topics")
    assert resp.status_code == 200
    assert resp.json() == {"topics": []}
    mock_list.assert_called_once_with(
        pillar=None, best_format=None, engagement_level=None, used=None
    )


def test_post_topics_adds_a_topic(client):
    with patch.object(tis, "add_topic", return_value=42) as mock_add:
        resp = client.post(
            "/api/tac-instagram/topics",
            json={
                "topic": "Sunday scaries",
                "best_format": "Poll + Meme",
                "content_pillar": "Work-Life Balance",
                "engagement_level": "High",
                "angle_notes": "Relatable Monday opener",
                "community_question": "Does anyone else dread Sunday afternoon?",
                "tac_answer": "Sunday scaries are data, not weakness.",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"id": 42}
    mock_add.assert_called_once_with(
        topic="Sunday scaries",
        best_format="Poll + Meme",
        content_pillar="Work-Life Balance",
        engagement_level="High",
        angle_notes="Relatable Monday opener",
        community_question="Does anyone else dread Sunday afternoon?",
        tac_answer="Sunday scaries are data, not weakness.",
    )


def test_post_topics_requires_topic_field(client):
    with patch.object(tis, "add_topic") as mock_add:
        resp = client.post("/api/tac-instagram/topics", json={"best_format": "Poll + Meme"})
    assert resp.status_code == 400
    mock_add.assert_not_called()


def test_post_topics_400s_on_exact_duplicate(client):
    # F4 (fix wave): tis.add_topic raises ValueError on an exact-match
    # duplicate (case-sensitive) - the route must turn that into a plain
    # 400, not let it bubble up as a raw 500.
    with patch.object(
        tis, "add_topic", side_effect=ValueError("Topic already exists: 'Sunday scaries'")
    ):
        resp = client.post("/api/tac-instagram/topics", json={"topic": "Sunday scaries"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "That topic is already in the bank"


def test_post_mark_used_returns_ok(client):
    with patch.object(tis, "mark_topic_used", return_value=True) as mock_mark:
        resp = client.post("/api/tac-instagram/topics/7/mark-used")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_mark.assert_called_once_with(7)


def test_post_mark_used_404s_for_unknown_topic(client):
    with patch.object(tis, "mark_topic_used", return_value=False):
        resp = client.post("/api/tac-instagram/topics/99999/mark-used")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------


def test_get_today_returns_actions_from_state(client):
    fake_actions = [
        {
            "time": "9:00 AM",
            "task": "Post a submission-question story to farm the week's theme",
            "day": "Monday",
            "suggested_topic": {"id": 1, "topic": "Sunday scaries"},
        },
    ]
    with patch.object(tis, "today_actions", return_value=fake_actions) as mock_today:
        resp = client.get("/api/tac-instagram/today")
    assert resp.status_code == 200
    assert resp.json() == {"actions": fake_actions}
    mock_today.assert_called_once_with()


def test_get_today_returns_empty_list_on_weekend(client):
    with patch.object(tis, "today_actions", return_value=[]):
        resp = client.get("/api/tac-instagram/today")
    assert resp.status_code == 200
    assert resp.json() == {"actions": []}


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def test_get_calendar_lists_and_passes_filters(client):
    with patch.object(
        tis, "list_calendar", return_value=[{"id": 1, "post_type": "Reel"}]
    ) as mock_list:
        resp = client.get(
            "/api/tac-instagram/calendar",
            params={"week_label": "WEEK 1   ·   11 May – 15 May 2026", "status": "Scheduled"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"id": 1, "post_type": "Reel"}]}
    mock_list.assert_called_once_with(
        week_label="WEEK 1   ·   11 May – 15 May 2026", status="Scheduled"
    )


def test_get_calendar_with_no_filters(client):
    with patch.object(tis, "list_calendar", return_value=[]) as mock_list:
        resp = client.get("/api/tac-instagram/calendar")
    assert resp.status_code == 200
    assert resp.json() == {"rows": []}
    mock_list.assert_called_once_with(week_label=None, status=None)


def test_post_calendar_adds_a_row(client):
    with patch.object(tis, "add_calendar_row", return_value=13) as mock_add:
        resp = client.post(
            "/api/tac-instagram/calendar",
            json={"post_date": "2 Jun 2026", "post_type": "Carousel", "status": "Not Started"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"id": 13}
    mock_add.assert_called_once_with(
        post_date="2 Jun 2026", post_type="Carousel", status="Not Started"
    )


def test_post_calendar_requires_at_least_one_field(client):
    with patch.object(tis, "add_calendar_row") as mock_add:
        resp = client.post("/api/tac-instagram/calendar", json={})
    assert resp.status_code == 400
    mock_add.assert_not_called()


def test_post_calendar_unknown_field_returns_400(client):
    with patch.object(
        tis, "add_calendar_row", side_effect=ValueError("Unknown tac_calendar field(s): ['bogus']")
    ):
        resp = client.post("/api/tac-instagram/calendar", json={"bogus": "x"})
    assert resp.status_code == 400
    # Plain-English detail only - no brackets, quotes, or internal table name.
    assert resp.json()["error"] == "Unknown field: bogus"


def test_patch_calendar_updates_a_row(client):
    with patch.object(tis, "update_calendar_row", return_value=True) as mock_update:
        resp = client.patch(
            "/api/tac-instagram/calendar/5", json={"status": "Posted"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_update.assert_called_once_with(5, status="Posted")


def test_patch_calendar_requires_at_least_one_field(client):
    with patch.object(tis, "update_calendar_row") as mock_update:
        resp = client.patch("/api/tac-instagram/calendar/5", json={})
    assert resp.status_code == 400
    mock_update.assert_not_called()


def test_patch_calendar_unknown_field_returns_400(client):
    with patch.object(
        tis, "update_calendar_row", side_effect=ValueError("Unknown tac_calendar field(s): ['bogus']")
    ):
        resp = client.patch("/api/tac-instagram/calendar/5", json={"bogus": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Unknown field: bogus"


def test_patch_calendar_404s_for_unknown_row(client):
    with patch.object(tis, "update_calendar_row", return_value=False):
        resp = client.patch("/api/tac-instagram/calendar/99999", json={"status": "Posted"})
    assert resp.status_code == 404


def test_patch_calendar_blank_status_returns_400_not_raw_500(client):
    # F2 (fix wave): tac_calendar.status is NOT NULL (with a DEFAULT that
    # only applies on INSERT, not on an explicit UPDATE ... SET status =
    # NULL). Before the fix, sqlite3.IntegrityError propagated straight out
    # of the route as an unhandled exception -> FastAPI's raw 500, which the
    # frontend toast shows as JSON-parse garbage. Must be a plain 400.
    import sqlite3

    with patch.object(
        tis,
        "update_calendar_row",
        side_effect=sqlite3.IntegrityError(
            "NOT NULL constraint failed: tac_calendar.status"
        ),
    ):
        resp = client.patch("/api/tac-instagram/calendar/5", json={"status": None})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Status needs a value"


# ---------------------------------------------------------------------------
# Quarterly planner
# ---------------------------------------------------------------------------


def test_get_quarterly_lists_and_passes_filter(client):
    with patch.object(
        tis, "list_quarterly", return_value=[{"id": 1, "campaign_event": "Salary Survey"}]
    ) as mock_list:
        resp = client.get(
            "/api/tac-instagram/quarterly", params={"quarter_label": "Q3 2026"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"items": [{"id": 1, "campaign_event": "Salary Survey"}]}
    mock_list.assert_called_once_with(quarter_label="Q3 2026")


def test_get_quarterly_with_no_filter(client):
    with patch.object(tis, "list_quarterly", return_value=[]) as mock_list:
        resp = client.get("/api/tac-instagram/quarterly")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}
    mock_list.assert_called_once_with(quarter_label=None)


def test_post_quarterly_adds_an_item(client):
    with patch.object(tis, "add_quarterly_item", return_value=9) as mock_add:
        resp = client.post(
            "/api/tac-instagram/quarterly",
            json={"campaign_event": "Salary Survey", "launch_date": "1-2 Jun 2026"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"id": 9}
    mock_add.assert_called_once_with(
        campaign_event="Salary Survey", launch_date="1-2 Jun 2026"
    )


def test_post_quarterly_requires_at_least_one_field(client):
    with patch.object(tis, "add_quarterly_item") as mock_add:
        resp = client.post("/api/tac-instagram/quarterly", json={})
    assert resp.status_code == 400
    mock_add.assert_not_called()


def test_post_quarterly_unknown_field_returns_400(client):
    with patch.object(
        tis,
        "add_quarterly_item",
        side_effect=ValueError("Unknown tac_quarterly_planner field(s): ['bogus']"),
    ):
        resp = client.post("/api/tac-instagram/quarterly", json={"bogus": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Unknown field: bogus"


def test_post_calendar_unknown_field_returns_400_multiple_fields(client):
    with patch.object(
        tis,
        "add_calendar_row",
        side_effect=ValueError("Unknown tac_calendar field(s): ['bogus', 'nope']"),
    ):
        resp = client.post("/api/tac-instagram/calendar", json={"bogus": "x", "nope": "y"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Unknown field: bogus, nope"


def test_patch_quarterly_updates_an_item(client):
    with patch.object(tis, "update_quarterly_item", return_value=True) as mock_update:
        resp = client.patch(
            "/api/tac-instagram/quarterly/5", json={"notes": "Moved a week"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_update.assert_called_once_with(5, notes="Moved a week")


def test_patch_quarterly_requires_at_least_one_field(client):
    with patch.object(tis, "update_quarterly_item") as mock_update:
        resp = client.patch("/api/tac-instagram/quarterly/5", json={})
    assert resp.status_code == 400
    mock_update.assert_not_called()


def test_patch_quarterly_unknown_field_returns_400(client):
    with patch.object(
        tis,
        "update_quarterly_item",
        side_effect=ValueError("Unknown tac_quarterly_planner field(s): ['bogus']"),
    ):
        resp = client.patch("/api/tac-instagram/quarterly/5", json={"bogus": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Unknown field: bogus"


def test_patch_quarterly_404s_for_unknown_item(client):
    with patch.object(tis, "update_quarterly_item", return_value=False):
        resp = client.patch("/api/tac-instagram/quarterly/99999", json={"notes": "x"})
    assert resp.status_code == 404


def test_patch_quarterly_blank_campaign_event_returns_400_not_raw_500(client):
    # F2 (fix wave): PATCH {"campaign_event": null} (what the frontend sends
    # when an inline cell is cleared - see _tacQuarterlyCoerce in index.html,
    # "" is coerced to null before the PATCH) hits tac_quarterly_planner
    # .campaign_event's NOT NULL column -> sqlite3.IntegrityError. Before the
    # fix this was an unhandled exception -> raw 500 -> the frontend toast
    # showed JSON-parse garbage instead of a plain-English error.
    import sqlite3

    with patch.object(
        tis,
        "update_quarterly_item",
        side_effect=sqlite3.IntegrityError(
            "NOT NULL constraint failed: tac_quarterly_planner.campaign_event"
        ),
    ):
        resp = client.patch("/api/tac-instagram/quarterly/5", json={"campaign_event": None})
    assert resp.status_code == 400
    assert resp.json()["error"] == "The campaign or event needs a name"


def test_post_generate_survey_week_returns_created_row_ids(client):
    with patch.object(
        tis, "generate_survey_week_rows", return_value=[101, 102, 103, 104, 105]
    ) as mock_gen:
        resp = client.post("/api/tac-instagram/quarterly/3/generate-survey-week")
    assert resp.status_code == 200
    assert resp.json() == {"created_row_ids": [101, 102, 103, 104, 105]}
    mock_gen.assert_called_once_with(3)


def test_post_generate_survey_week_400s_on_unknown_item(client):
    with patch.object(
        tis,
        "generate_survey_week_rows",
        side_effect=ValueError("tac_quarterly_planner row 99999 not found"),
    ):
        resp = client.post("/api/tac-instagram/quarterly/99999/generate-survey-week")
    assert resp.status_code == 400
    assert resp.json()["error"] == "That planner item was not found"


def test_post_generate_survey_week_400s_on_missing_launch_date(client):
    with patch.object(
        tis,
        "generate_survey_week_rows",
        side_effect=ValueError("tac_quarterly_planner row 3 has no launch_date"),
    ):
        resp = client.post("/api/tac-instagram/quarterly/3/generate-survey-week")
    assert resp.status_code == 400
    assert resp.json()["error"] == "That planner item has no launch date"


def test_post_generate_survey_week_400s_on_unparseable_launch_date(client):
    # F1 (fix wave): "TBD Sep 2026" is real data in Victor's planner (rows 2
    # and 7) and launch dates are inline-editable, so this is not a
    # hypothetical. Before the fix, tac_instagram_state.UnparseableDateError
    # is a ValueError whose message doesn't contain "launch_date", so the old
    # string-sniffing route code fell through to the wrong "not found"
    # message. Must get its own plain-English detail instead.
    with patch.object(
        tis,
        "generate_survey_week_rows",
        side_effect=tis.UnparseableDateError("Unrecognised date format: 'TBD Sep 2026'"),
    ):
        resp = client.post("/api/tac-instagram/quarterly/2/generate-survey-week")
    assert resp.status_code == 400
    assert resp.json()["error"] == (
        "That launch date could not be read as a date - try a format like 2 Jun 2026"
    )


# ---------------------------------------------------------------------------
# Integration: real workbook data through the live endpoint (no mocks)
# ---------------------------------------------------------------------------


def test_topic_count_is_118_through_the_live_endpoint(tmp_path: Path):
    """Imports the real TAC Instagram workbook (Task 1's importer) into a
    fresh temp DB, then hits the live GET /topics endpoint with no mocking
    at all, to confirm the 118-topic bank really round-trips through the API.
    """
    import flatwhite.db as db_module
    from scripts import import_tac_instagram_calendar

    real_xlsx = (
        Path(__file__).parent.parent
        / "flatwhite"
        / "data"
        / "tac_instagram"
        / "TAC_Instagram_Content_Calendar_2026.xlsx"
    )
    db_path = tmp_path / "test_tac_api_live.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import_tac_instagram_calendar.run(str(real_xlsx), db_path=str(db_path))

        live_client = TestClient(api_module.app)
        resp = live_client.get("/api/tac-instagram/topics")

    assert resp.status_code == 200
    assert len(resp.json()["topics"]) == 118


# ---------------------------------------------------------------------------
# Build carousel (headless community-carousel skill run)
# ---------------------------------------------------------------------------
# Mirrors tests/test_brains_trust_refresh.py's endpoint tests: skill_runner
# .start_run is always patched here, so no test in this file ever launches a
# real `claude -p` run. big_conversation_bank.INSTAGRAM_OUTPUT_DIR is
# monkeypatched to a tmp_path tree, same as tests/test_big_conversation_api.py,
# so no test touches the real Instagram output folder either.
#
# carousel_env ALSO patches flatwhite.db.DB_PATH to a temp DB (mirrors
# tests/test_big_conversation_api.py's bc_env fixture) so the on_complete
# tests below can exercise the REAL save_bank_item / save_skill_run_outcome /
# load_skill_run_outcome round trip - no test touches the developer's live
# DB, but nothing about the persistence path is mocked away either. This
# matters because the bug this section regression-tests (a run that reports
# "done" without ever actually saving anything - the same silent-run failure
# class docs/bigconv-silent-run-report.md records) is exactly the kind of
# thing a mocked-out save_bank_item can't catch: the earlier version of these
# tests only asserted save_bank_item was/wasn't called, which says nothing
# about whether the TRUE outcome (saved vs silently not-saved) was ever made
# observable to the frontend.


@pytest.fixture
def carousel_env(tmp_path, monkeypatch):
    """A fake sorted topic folder with one screenshot, list_topics() patched
    to return one matching topic bank row, and a temp DB."""
    db_path = tmp_path / "carousel_api_test.db"
    output_dir = tmp_path / "output"
    topic_folder = output_dir / "Sunday scaries"
    topic_folder.mkdir(parents=True)
    (topic_folder / "screenshot_0001.png").write_bytes(b"x")
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(api_module, "_claude_available", lambda: True)
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        with patch.object(
            tis, "list_topics",
            return_value=[{"id": 7, "topic": "Sunday scaries"}],
        ):
            yield output_dir


def test_build_carousel_starts_a_run(client, carousel_env):
    with patch(
        "flatwhite.dashboard.skill_runner.start_run",
        return_value=("carrun1", True),
    ) as mock_start:
        resp = client.post("/api/tac-instagram/build-carousel/7")
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "carrun1", "started": True}
    args, kwargs = mock_start.call_args
    assert args[0] == "tac-carousel-build"
    assert args[1] == "tac-carousel-7"
    argv = args[2]
    assert argv[0].endswith("claude")
    assert "-p" in argv
    assert kwargs["cwd"] == str(carousel_env)
    assert callable(kwargs.get("on_complete"))
    # The prompt names the exact file on_complete will read back - not a
    # captured-stdout marker (see the module docstring above and
    # _read_carousel_script's docstring in api.py for why).
    prompt = argv[2]
    assert "_CAROUSEL_SCRIPT.md" in prompt
    assert str(carousel_env / "Sunday scaries") in prompt


def test_build_carousel_429s_on_concurrency_cap(client, carousel_env):
    with patch(
        "flatwhite.dashboard.skill_runner.start_run",
        side_effect=RuntimeError("Another skill run is already in progress."),
    ):
        resp = client.post("/api/tac-instagram/build-carousel/7")
    assert resp.status_code == 429
    assert "already in progress" in resp.json()["error"]


def test_build_carousel_404s_when_topic_not_found(client, carousel_env):
    with patch.object(tis, "list_topics", return_value=[]), patch(
        "flatwhite.dashboard.skill_runner.start_run",
    ) as mock_start:
        resp = client.post("/api/tac-instagram/build-carousel/999")
    assert resp.status_code == 404
    mock_start.assert_not_called()


def test_build_carousel_404s_when_no_sorted_folder(client, tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(api_module, "_claude_available", lambda: True)
    with patch.object(
        tis, "list_topics", return_value=[{"id": 7, "topic": "No Folder Topic"}]
    ), patch("flatwhite.dashboard.skill_runner.start_run") as mock_start:
        resp = client.post("/api/tac-instagram/build-carousel/7")
    assert resp.status_code == 404
    mock_start.assert_not_called()


def _post_and_get_on_complete(client, topic_id=7):
    """POST the route (start_run mocked) and hand back the real on_complete
    closure it wired up, so a test can invoke it directly with a fake
    finished-run record - same technique tests/test_brains_trust_refresh.py
    doesn't need (it has no on_complete) but tests/test_big_conversation_api.py's
    equivalent flows do."""
    with patch(
        "flatwhite.dashboard.skill_runner.start_run",
        return_value=("carrun1", True),
    ) as mock_start:
        client.post(f"/api/tac-instagram/build-carousel/{topic_id}")
    return mock_start.call_args.kwargs["on_complete"]


def test_build_carousel_on_complete_saves_bank_item_and_persists_done_outcome(client, carousel_env):
    on_complete = _post_and_get_on_complete(client)

    script_path = carousel_env / "Sunday scaries" / "_CAROUSEL_SCRIPT.md"
    script_path.write_text("Slide 1: hook\nSlide 2: A vs B", encoding="utf-8")

    fake_record = {"id": "carrun1", "status": "done", "output": "CAROUSEL_BUILD_DONE\n"}
    on_complete(fake_record)

    rows = db_module.list_bank_items(segment_type="tac_instagram_carousel")
    assert len(rows) == 1
    assert rows[0]["title"] == "Sunday scaries"
    assert rows[0]["body_text"] == "Slide 1: hook\nSlide 2: A vs B"
    assert rows[0]["source_note"].startswith("Built ")

    outcome = load_skill_run_outcome("tac-carousel-7")
    assert outcome["status"] == "done"
    assert outcome["error"] is None


def test_build_carousel_on_complete_persists_failure_when_run_itself_failed(client, carousel_env):
    on_complete = _post_and_get_on_complete(client)

    fake_record = {"id": "carrun1", "status": "failed", "error": "boom", "output": "boom"}
    on_complete(fake_record)

    assert db_module.list_bank_items(segment_type="tac_instagram_carousel") == []
    outcome = load_skill_run_outcome("tac-carousel-7")
    assert outcome["status"] == "failed"
    assert outcome["error"] == "boom"


def test_build_carousel_on_complete_persists_failure_when_script_file_missing(client, carousel_env):
    # CRITICAL regression test (code review, 27 Aug 2026): skill_runner marks
    # a run "done" on exit 0 + the CAROUSEL_BUILD_DONE marker ALONE - a run
    # can hit both without ever writing a script (the skill errored partway,
    # or just never wrote the file). The pre-fix on_complete just `return`ed
    # here with no observable trace, so pollTacCarouselRun's r.status ===
    # "done" toasted "saved to the Content Bank" on a run that saved nothing
    # - the exact silent-run failure class docs/bigconv-silent-run-report.md
    # records. This must persist an honest FAILURE outcome instead.
    on_complete = _post_and_get_on_complete(client)

    # No _CAROUSEL_SCRIPT.md ever written in the topic folder.
    fake_record = {"id": "carrun1", "status": "done", "output": "CAROUSEL_BUILD_DONE\n"}
    on_complete(fake_record)

    assert db_module.list_bank_items(segment_type="tac_instagram_carousel") == []
    outcome = load_skill_run_outcome("tac-carousel-7")
    assert outcome is not None
    assert outcome["status"] == "failed"
    assert "no carousel script file" in outcome["error"].lower()


def test_build_carousel_on_complete_persists_failure_when_script_file_truncation_shaped(client, carousel_env):
    # Truncation-shaped regression test: the ORIGINAL implementation parsed
    # the finished script out of the run's captured stdout, which
    # skill_runner keeps only the last 6000 chars of (_OUTPUT_TAIL_CHARS) -
    # a verbose run (curation notes, a cut list printed after the script,
    # exactly what the real live-acceptance run for this task produced)
    # could push the script's start marker out of that captured tail while
    # the completion marker at the very end survived, making a genuine drop
    # look identical to success. The fix reads the script back from a real
    # file instead of parsed stdout, so this proves that path stays honest
    # even when "output" is huge and the file itself is empty/unwritten -
    # never a silent "done".
    on_complete = _post_and_get_on_complete(client)

    script_path = carousel_env / "Sunday scaries" / "_CAROUSEL_SCRIPT.md"
    script_path.write_text("   \n\n  ", encoding="utf-8")  # written, but blank

    huge_verbose_output = "some curation note line\n" * 2000  # far past 6000 chars
    fake_record = {"id": "carrun1", "status": "done", "output": huge_verbose_output}
    on_complete(fake_record)

    assert db_module.list_bank_items(segment_type="tac_instagram_carousel") == []
    outcome = load_skill_run_outcome("tac-carousel-7")
    assert outcome["status"] == "failed"


def test_build_carousel_on_complete_persists_failure_when_save_bank_item_raises(client, carousel_env):
    on_complete = _post_and_get_on_complete(client)

    script_path = carousel_env / "Sunday scaries" / "_CAROUSEL_SCRIPT.md"
    script_path.write_text("Slide 1: hook", encoding="utf-8")

    fake_record = {"id": "carrun1", "status": "done", "output": "CAROUSEL_BUILD_DONE\n"}
    with patch("flatwhite.db.save_bank_item", side_effect=RuntimeError("db locked")):
        on_complete(fake_record)

    outcome = load_skill_run_outcome("tac-carousel-7")
    assert outcome["status"] == "failed"
    assert "db locked" in outcome["error"]


def test_build_carousel_status_returns_persisted_outcome(client, carousel_env):
    save_skill_run_outcome("tac-carousel-7", "carrun1", "tac-carousel-build",
                            "failed", "No carousel script file was found.")
    resp = client.get("/api/tac-instagram/build-carousel/7/status")
    assert resp.status_code == 200
    assert resp.json() == {"status": "failed", "error": "No carousel script file was found."}


def test_build_carousel_status_returns_nulls_when_never_run(client, carousel_env):
    resp = client.get("/api/tac-instagram/build-carousel/999/status")
    assert resp.status_code == 200
    assert resp.json() == {"status": None, "error": None}


# --- Code review round 2 (27 Aug 2026) -------------------------------------
# G2: a stale _CAROUSEL_SCRIPT.md from a PREVIOUS build of the same topic has
# no per-run name or freshness check. A rebuild whose model skips the write
# but still prints CAROUSEL_BUILD_DONE would otherwise have
# _read_carousel_script silently pick up the old file and re-save it as if
# it were this run's output. Fix: the route deletes the file (missing_ok)
# BEFORE calling start_run, so a file existing at on_complete time can only
# have been written by THIS run.
def test_build_carousel_deletes_stale_script_file_before_starting_run(client, carousel_env):
    script_path = carousel_env / "Sunday scaries" / "_CAROUSEL_SCRIPT.md"
    script_path.write_text("stale content from a previous build", encoding="utf-8")
    assert script_path.exists()

    captured = {}

    def fake_start_run(*args, **kwargs):
        # By the time start_run is called (i.e. before this run's `claude -p`
        # process even launches), the stale file must already be gone.
        captured["file_existed_at_start"] = script_path.exists()
        return ("carrun1", True)

    with patch(
        "flatwhite.dashboard.skill_runner.start_run", side_effect=fake_start_run
    ):
        resp = client.post("/api/tac-instagram/build-carousel/7")

    assert resp.status_code == 200
    assert captured["file_existed_at_start"] is False
    assert not script_path.exists()


# Round 3 (27 Aug 2026): the round-2 pre-delete above was unconditional, so
# two POSTs for the SAME topic could race - a second request's unlink could
# delete a still-running FIRST request's live file, or wipe one it had just
# finished writing right before its own on_complete read it. Fix: check
# skill_runner.get_active_by_key(run_key) BEFORE unlinking, and 429 without
# touching the file at all if a run for this topic is already in progress.
def test_build_carousel_429s_and_preserves_script_file_when_already_active(client, carousel_env):
    script_path = carousel_env / "Sunday scaries" / "_CAROUSEL_SCRIPT.md"
    script_path.write_text("output from the currently-running build", encoding="utf-8")
    assert script_path.exists()

    with patch(
        "flatwhite.dashboard.skill_runner.get_active_by_key",
        return_value={"id": "already-running-run", "status": "running"},
    ), patch("flatwhite.dashboard.skill_runner.start_run") as mock_start:
        resp = client.post("/api/tac-instagram/build-carousel/7")

    assert resp.status_code == 429
    assert "already in progress" in resp.json()["error"]
    mock_start.assert_not_called()
    # The live run's file must be untouched - not deleted out from under it.
    assert script_path.exists()
    assert script_path.read_text(encoding="utf-8") == "output from the currently-running build"


# G1: verifyTacCarouselSaved's decision logic (_tacCarouselFindNewMatch,
# index.html) is pure frontend JS with no browser/JS test harness in this
# repo, so it's pinned by running a small Node assertion script directly -
# this keeps it inside the normal `pytest` run (foreground, same command as
# every other test here) rather than a separate manual step someone has to
# remember to run. See tests/js/tac_carousel_frontend_test.js for the actual
# assertions (cross-topic contamination is the one that matters: a new
# Content Bank row from a DIFFERENT topic - possible because
# _MAX_CONCURRENT lets two builds run at once - must never be read as proof
# THIS topic's carousel saved).
def test_tac_carousel_frontend_js_pinning_tests_pass():
    import subprocess

    script = Path(__file__).parent / "js" / "tac_carousel_frontend_test.js"
    result = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (
        "tac_carousel_frontend_test.js failed:\n"
        + result.stdout + result.stderr
    )
    assert "all assertions passed" in result.stdout


# F3 (fix wave, 27 Aug 2026): same pattern as the carousel pinning test above
# - no browser/JS harness in this repo, so jsq()'s hardening (escape " and
# \n/\r, not just \ and ') is pinned by running a real Node assertion script
# that simulates a browser's HTML-attribute tokenizer + inline-handler
# compile step. See tests/js/tac_jsq_frontend_test.js for the assertions.
def test_tac_jsq_frontend_js_pinning_tests_pass():
    import subprocess

    script = Path(__file__).parent / "js" / "tac_jsq_frontend_test.js"
    result = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (
        "tac_jsq_frontend_test.js failed:\n"
        + result.stdout + result.stderr
    )
    assert "all assertions passed" in result.stdout
