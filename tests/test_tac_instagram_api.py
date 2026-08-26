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

import flatwhite.dashboard.api as api_module
from flatwhite.dashboard import tac_instagram_state as tis


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
    assert "bogus" in resp.json()["error"]


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
    assert "bogus" in resp.json()["error"]


def test_patch_calendar_404s_for_unknown_row(client):
    with patch.object(tis, "update_calendar_row", return_value=False):
        resp = client.patch("/api/tac-instagram/calendar/99999", json={"status": "Posted"})
    assert resp.status_code == 404


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
    assert "bogus" in resp.json()["error"]


def test_post_generate_survey_week_returns_created_row_ids(client):
    with patch.object(
        tis, "generate_survey_week_rows", return_value=[101, 102, 103, 104, 105]
    ) as mock_gen:
        resp = client.post("/api/tac-instagram/quarterly/3/generate-survey-week")
    assert resp.status_code == 200
    assert resp.json() == {"created_row_ids": [101, 102, 103, 104, 105]}
    mock_gen.assert_called_once_with(3)


def test_post_generate_survey_week_400s_on_value_error(client):
    with patch.object(
        tis,
        "generate_survey_week_rows",
        side_effect=ValueError("tac_quarterly_planner row 99999 not found"),
    ):
        resp = client.post("/api/tac-instagram/quarterly/99999/generate-survey-week")
    assert resp.status_code == 400
    assert "not found" in resp.json()["error"]


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
