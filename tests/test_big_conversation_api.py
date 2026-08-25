"""Tests for the Big Conversation API endpoints (increment 4).

Both the DB (archive + pairing state) and the filesystem
(big_conversation_bank.INSTAGRAM_OUTPUT_DIR) are monkeypatched — no real
Claude/network calls, and the real Instagram output folder is never read
by these tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import flatwhite.db as db_module
import flatwhite.dashboard.big_conversation_bank as bcb


@pytest.fixture
def bc_env(tmp_path, monkeypatch):
    """A temp Instagram output/ tree + a temp FW DB, both isolated from the
    real filesystem/DB. Yields the fake output/ root."""
    db_path = tmp_path / "bc_api_test.db"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", output_dir)
        yield output_dir


def test_topics_endpoint_lists_unprocessed_topic(bc_env):
    topic = bc_env / "Kids in the Office"
    topic.mkdir()
    (topic / "Person_0.png").write_bytes(b"x")
    from flatwhite.dashboard.api import api_big_conversation_topics

    result = api_big_conversation_topics()
    data = json.loads(result.body)
    assert data["root_exists"] is True
    topics = {t["topic"]: t for t in data["topics"]}
    assert topics["Kids in the Office"]["reply_count"] == 1
    assert topics["Kids in the Office"]["archived"] is False
    assert topics["Kids in the Office"]["processed"] is False


def test_topics_endpoint_soft_fails_when_root_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "bc_api_missing.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path / "does-not-exist")
        from flatwhite.dashboard.api import api_big_conversation_topics

        result = api_big_conversation_topics()
        data = json.loads(result.body)
        assert data["topics"] == []
        assert data["root_exists"] is False


def test_topic_detail_endpoint_soft_fails_when_not_processed(bc_env):
    (bc_env / "Kids in the Office").mkdir()
    from flatwhite.dashboard.api import api_big_conversation_topic

    result = api_big_conversation_topic("Kids in the Office")
    data = json.loads(result.body)
    assert data["processed"] is False


def test_topic_detail_endpoint_returns_paragraphs_when_processed(bc_env):
    (bc_env / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text(
        "**THE BIG CONVERSATION**\n\n"
        "Nobody decided kids should be in the office.\n\n"
        "First paragraph text.\n\n"
        "---\n\nAssets in `Kids in the Office/_BIG_CONVERSATION_assets/`.\n\n"
        "**P1** - `p1_1_Katie_Moloney.png` - some note.\n"
    )
    assets = bc_env / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"x")
    from flatwhite.dashboard.api import api_big_conversation_topic

    result = api_big_conversation_topic("Kids in the Office")
    data = json.loads(result.body)
    assert data["processed"] is True
    assert data["paragraphs"][0]["screenshots"][0]["file"] == "p1_1_Katie_Moloney.png"


def test_asset_route_serves_file(bc_env):
    assets = bc_env / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"fake-bytes")
    from flatwhite.dashboard.api import api_big_conversation_asset

    result = api_big_conversation_asset("Kids in the Office/_BIG_CONVERSATION_assets/p1_1_Katie_Moloney.png")
    assert result.status_code == 200


def test_asset_route_404s_on_traversal(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_asset

    result = api_big_conversation_asset("../../etc/passwd")
    assert result.status_code == 404


def test_asset_route_404s_on_missing_file(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_asset

    result = api_big_conversation_asset("Kids in the Office/_BIG_CONVERSATION_assets/missing.png")
    assert result.status_code == 404


import asyncio


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def test_archive_round_trips_through_topics_endpoint(bc_env):
    (bc_env / "Kids in the Office").mkdir()
    from flatwhite.dashboard.api import api_big_conversation_archive, api_big_conversation_topics

    asyncio.get_event_loop().run_until_complete(
        api_big_conversation_archive(FakeRequest({"topic": "Kids in the Office", "archived": True}))
    )
    data = json.loads(api_big_conversation_topics().body)
    topics = {t["topic"]: t for t in data["topics"]}
    assert topics["Kids in the Office"]["archived"] is True

    asyncio.get_event_loop().run_until_complete(
        api_big_conversation_archive(FakeRequest({"topic": "Kids in the Office", "archived": False}))
    )
    data = json.loads(api_big_conversation_topics().body)
    topics = {t["topic"]: t for t in data["topics"]}
    assert topics["Kids in the Office"]["archived"] is False


def test_archive_requires_topic(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_archive

    result = asyncio.get_event_loop().run_until_complete(
        api_big_conversation_archive(FakeRequest({"archived": True}))
    )
    assert result.status_code == 400


def test_prepare_endpoint_returns_instruction_for_existing_folder(bc_env):
    (bc_env / "Kids in the Office").mkdir()
    from flatwhite.dashboard.api import api_big_conversation_prepare

    result = api_big_conversation_prepare("Kids in the Office")
    data = json.loads(result.body)
    assert "big-conversation" in data["instruction"]
    assert "Kids in the Office" in data["instruction"]
    assert data["folder_path"].endswith("Kids in the Office")


def test_prepare_endpoint_404s_for_missing_folder(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_prepare

    result = api_big_conversation_prepare("Does Not Exist")
    assert result.status_code == 404


def test_pairing_endpoint_moves_screenshot_and_persists(bc_env):
    (bc_env / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text(
        "**THE BIG CONVERSATION**\n\n"
        "Headline here.\n\n"
        "Paragraph one.\n\nParagraph two.\n\n"
        "---\n\nAssets in `Kids in the Office/_BIG_CONVERSATION_assets/`.\n\n"
        "**P1** - `p1_1_Katie_Moloney.png` - some note.\n"
    )
    assets = bc_env / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"x")
    from flatwhite.dashboard.api import api_big_conversation_pairing, api_big_conversation_topic

    asyncio.get_event_loop().run_until_complete(
        api_big_conversation_pairing(
            "Kids in the Office",
            FakeRequest({"filename": "p1_1_Katie_Moloney.png", "paragraph_index": 2}),
        )
    )
    data = json.loads(api_big_conversation_topic("Kids in the Office").body)
    assert data["paragraphs"][0]["screenshots"] == []
    assert data["paragraphs"][1]["screenshots"][0]["file"] == "p1_1_Katie_Moloney.png"


def test_pairing_endpoint_requires_filename_and_int_paragraph(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_pairing

    result = asyncio.get_event_loop().run_until_complete(
        api_big_conversation_pairing("Kids in the Office", FakeRequest({"filename": "x.png"}))
    )
    assert result.status_code == 400


def test_run_status_is_honest_null_when_never_run(bc_env):
    # A topic that was never processed AND never had a run attempted must be
    # reported as such - null, not "false"-shaped like a finished run.
    from flatwhite.dashboard.api import api_big_conversation_run_status

    result = api_big_conversation_run_status("Never Run Topic")
    data = json.loads(result.body)
    assert data == {"active": False, "run_id": None, "status": None, "error": None}


def test_run_status_reports_a_finished_run_even_after_it_drops_out_of_active_set(bc_env):
    # Real bug (13 Aug 2026): once a headless run left skill_runner's
    # in-memory "active" set, /run-status went back to reporting exactly the
    # same shape as a topic that was never processed - a genuinely finished
    # run became invisible. This is the fix: the terminal outcome is
    # persisted (save_skill_run_outcome, called from the run's on_complete
    # hook) and /run-status must surface it. See
    # docs/bigconv-silent-run-report.md.
    from flatwhite.dashboard.api import api_big_conversation_run_status
    from flatwhite.dashboard.state import save_skill_run_outcome

    save_skill_run_outcome("bigconv:Offer Withdrawn After Negotiation", "run123",
                            "big-conversation", "done", None)
    result = api_big_conversation_run_status("Offer Withdrawn After Negotiation")
    data = json.loads(result.body)
    assert data["active"] is False
    assert data["run_id"] == "run123"
    assert data["status"] == "done"


def test_run_status_reports_a_failed_run_with_its_plain_english_reason(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_run_status
    from flatwhite.dashboard.state import save_skill_run_outcome

    save_skill_run_outcome("bigconv:Some Topic", "run456", "big-conversation",
                            "failed", "Claude Code isn't logged in on this Mac.")
    result = api_big_conversation_run_status("Some Topic")
    data = json.loads(result.body)
    assert data["status"] == "failed"
    assert data["error"] == "Claude Code isn't logged in on this Mac."


# ─── No repeats: already-published topic detection (25 Aug 2026) ────────────
# The bank offered "Career Pivoting" as the top untouched topic when it had
# shipped on 23 Jun as "What a career pivot actually costs." The `processed`
# flag only looks for a local assets folder, so anything published without
# leaving one behind reads as brand new.

def test_published_match_catches_the_career_pivoting_repeat():
    import flatwhite.dashboard.api as api
    editions = [{"title": "What a career pivot actually costs.", "url": "https://x/1"},
                {"title": "Cover letter, yes or no?", "url": "https://x/2"}]
    m = api._published_match("Career Pivoting", editions)
    assert m is not None and "career pivot" in m["title"].lower()


def test_published_match_handles_plurals_and_word_forms():
    import flatwhite.dashboard.api as api
    editions = [{"title": "Cover letter, yes or no?", "url": "https://x/2"}]
    assert api._published_match("Cover Letters", editions) is not None


def test_unrelated_topic_is_not_falsely_flagged():
    import flatwhite.dashboard.api as api
    editions = [{"title": "What a career pivot actually costs.", "url": "https://x/1"},
                {"title": "Cover letter, yes or no?", "url": "https://x/2"}]
    for topic in ("Payrise Excuses", "BO and Perfume", "Wellness Reimbursement"):
        assert api._published_match(topic, editions) is None, topic


def test_one_shared_COMMON_word_is_not_enough_to_flag():
    """One overlap only counts when the shared word is DISTINCTIVE - rare
    across the published run. 'career' appears in several titles, so sharing
    it alone must not flag a topic as already published."""
    import flatwhite.dashboard.api as api
    editions = [
        {"title": "Best career advice you ever got", "url": "https://x/3"},
        {"title": "The career ladder is a myth", "url": "https://x/4"},
        {"title": "Career break, career suicide?", "url": "https://x/5"},
    ]
    assert api._published_match("Career Pivoting", editions) is None


def test_one_shared_DISTINCTIVE_word_is_enough_to_flag():
    """The two-word bar missed 'Payrise Excuses' -> 'Getting denied a
    payrise.' and nearly shipped a repeat. 'payrise' is rare, so it decides."""
    import flatwhite.dashboard.api as api
    editions = [
        {"title": "Getting denied a payrise.", "url": "https://x/6"},
        {"title": "Best career advice you ever got", "url": "https://x/3"},
        {"title": "The career ladder is a myth", "url": "https://x/4"},
    ]
    m = api._published_match("Payrise Excuses", editions)
    assert m is not None and "payrise" in m["title"].lower()


def test_lookup_failure_never_hides_the_bank():
    """A beehiiv outage must leave every topic usable, just unflagged."""
    import flatwhite.dashboard.api as api
    assert api._published_match("Career Pivoting", []) is None
