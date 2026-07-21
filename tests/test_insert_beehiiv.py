"""Tests for the per-section beehiiv insert endpoint.

This is the shared final step that pushes every segment into the beehiiv draft
(`POST /api/section/{section}/insert-beehiiv`), and it previously had no test at
all. We mock the skill runner so nothing actually spawns `claude` or touches
beehiiv - we only assert the endpoint's routing, guards, and the arguments it
hands the runner (right heading, independent-session env strip, success marker).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import flatwhite.dashboard.api as api


@pytest.fixture
def client():
    return TestClient(api.app)


def _capture_start_run(captured):
    def _fn(kind, key, argv, **kwargs):
        captured["kind"] = kind
        captured["key"] = key
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return ("run_test_123", True)
    return _fn


def test_unknown_section_is_rejected(client):
    r = client.post("/api/section/not_a_real_section/insert-beehiiv")
    assert r.status_code == 400
    assert "Unknown section" in r.json()["error"]


def test_claude_unavailable_returns_503(client, monkeypatch):
    monkeypatch.setattr(api, "_claude_available", lambda: False)
    r = client.post("/api/section/top_picks/insert-beehiiv")
    assert r.status_code == 503


def test_no_saved_content_is_rejected(client, monkeypatch):
    monkeypatch.setattr(api, "_claude_available", lambda: True)
    monkeypatch.setattr(api, "load_all_section_outputs", lambda wk: {})
    r = client.post("/api/section/top_picks/insert-beehiiv")
    assert r.status_code == 400
    assert "no saved content" in r.json()["error"].lower()


def test_happy_path_targets_heading_and_strips_session(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(api, "_claude_available", lambda: True)
    monkeypatch.setattr(
        api, "load_all_section_outputs",
        lambda wk: {"top_picks": {"output_text": "Some picks. https://example.com"}},
    )
    monkeypatch.setattr(api._skill_runner, "start_run", _capture_start_run(captured))

    r = client.post("/api/section/top_picks/insert-beehiiv")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert body["section"] == "top_picks"

    # The prompt must instruct beehiiv to fill the CORRECT card heading.
    prompt = captured["argv"][2]  # [claude, -p, <prompt>, --permission-mode, ...]
    assert api._REAL_SEGMENT_HEADINGS["top_picks"] in prompt

    # The run must be launched as an INDEPENDENT session (session/API-key vars
    # removed, i.e. present in the override with value None) so the claude.ai
    # beehiiv connector attaches instead of being disabled.
    env = captured["kwargs"].get("env") or {}
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
                "ANTHROPIC_API_KEY"):
        assert var in env and env[var] is None

    # A run that never prints the marker must be treated as a failure.
    assert captured["kwargs"].get("success_marker") == "INSERT_OK"


def test_odd_picks_has_its_own_insertable_card():
    # Odd picks is built from the Top Picks screen but inserts as its own card.
    assert api._REAL_SEGMENT_HEADINGS.get("odd_picks") == "ODD PICKS FROM LAST WEEK"


def test_every_running_order_segment_has_a_heading():
    # Any segment the dashboard can insert must map to a beehiiv card heading.
    for section in ("editorial", "top_picks", "odd_picks", "brains_trust",
                    "off_the_clock", "thread", "insidetrack", "big_conversation"):
        assert section in api._REAL_SEGMENT_HEADINGS
