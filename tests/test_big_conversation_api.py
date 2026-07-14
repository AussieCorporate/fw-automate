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
