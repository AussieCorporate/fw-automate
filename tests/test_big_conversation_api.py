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
        "---\n\nAssets in `Kids in the Office/_BIG_CONVERSATION_assets/`.\n"
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
        "---\n\nAssets in `Kids in the Office/_BIG_CONVERSATION_assets/`.\n"
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
