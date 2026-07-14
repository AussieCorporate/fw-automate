"""Tests for the content_bank table — pieces produced ahead of time (Big
Conversation, Brains Trust) that get pulled into a future edition. Decoupled
from week_iso, unlike section_outputs (see plan rationale: reusing `drafts`
would need a CHECK-constraint rebuild for no real benefit)."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def bank_db(tmp_path: Path):
    db_path = tmp_path / "bank_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def test_content_bank_table_exists(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        conn = db_module.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "content_bank" in tables


def test_save_and_list_bank_item(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        bank_id = db_module.save_bank_item(
            segment_type="big_conversation",
            title="Return-to-office backlash",
            body_text="**A quiet mutiny.**\n\nMore teams are...",
            source_note="Instagram folder: rto-backlash-2026w29",
        )
        assert isinstance(bank_id, int)
        items = db_module.list_bank_items(segment_type="big_conversation")
        assert len(items) == 1
        assert items[0]["title"] == "Return-to-office backlash"
        assert items[0]["status"] == "active"


def test_list_filters_by_segment_type(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        db_module.save_bank_item("big_conversation", "Piece A", "text a")
        db_module.save_bank_item("brains_trust", "Piece B", "text b")
        bc = db_module.list_bank_items(segment_type="big_conversation")
        bt = db_module.list_bank_items(segment_type="brains_trust")
        assert [i["title"] for i in bc] == ["Piece A"]
        assert [i["title"] for i in bt] == ["Piece B"]


def test_list_all_segment_types_when_omitted(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        db_module.save_bank_item("big_conversation", "Piece A", "text a")
        db_module.save_bank_item("brains_trust", "Piece B", "text b")
        all_items = db_module.list_bank_items()
        assert len(all_items) == 2


def test_archive_hides_item_from_active_list(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        bank_id = db_module.save_bank_item("big_conversation", "Piece A", "text a")
        db_module.archive_bank_item(bank_id)
        active = db_module.list_bank_items(segment_type="big_conversation", status="active")
        archived = db_module.list_bank_items(segment_type="big_conversation", status="archived")
        assert active == []
        assert len(archived) == 1
        assert archived[0]["id"] == bank_id


def test_get_bank_item_returns_none_for_unknown_id(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        assert db_module.get_bank_item(99999) is None


def test_get_bank_item_returns_full_row(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        bank_id = db_module.save_bank_item("brains_trust", "EV uptake", "body text", "digest w28+w29")
        item = db_module.get_bank_item(bank_id)
        assert item["title"] == "EV uptake"
        assert item["body_text"] == "body text"
        assert item["source_note"] == "digest w28+w29"


# --- append to tests/test_content_bank.py ---
from fastapi.testclient import TestClient


@pytest.fixture
def bank_client(tmp_path: Path):
    db_path = tmp_path / "bank_api_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import flatwhite.dashboard.api as api_module
        yield TestClient(api_module.app)


def test_post_content_bank_creates_item(bank_client):
    resp = bank_client.post("/api/content-bank", json={
        "segment_type": "big_conversation",
        "title": "Return-to-office backlash",
        "body_text": "**A quiet mutiny.**",
        "source_note": "rto-backlash-2026w29",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] > 0


def test_get_content_bank_lists_active_items(bank_client):
    bank_client.post("/api/content-bank", json={
        "segment_type": "brains_trust", "title": "EV uptake", "body_text": "text",
    })
    resp = bank_client.get("/api/content-bank")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "EV uptake"


def test_get_content_bank_filters_by_segment_type(bank_client):
    bank_client.post("/api/content-bank", json={"segment_type": "big_conversation", "title": "A", "body_text": "a"})
    bank_client.post("/api/content-bank", json={"segment_type": "brains_trust", "title": "B", "body_text": "b"})
    resp = bank_client.get("/api/content-bank", params={"segment_type": "brains_trust"})
    items = resp.json()["items"]
    assert [i["title"] for i in items] == ["B"]


def test_post_content_bank_requires_fields(bank_client):
    resp = bank_client.post("/api/content-bank", json={"segment_type": "big_conversation"})
    assert resp.status_code == 400


def test_archive_endpoint(bank_client):
    created = bank_client.post("/api/content-bank", json={
        "segment_type": "big_conversation", "title": "A", "body_text": "a",
    }).json()
    resp = bank_client.post(f"/api/content-bank/{created['id']}/archive")
    assert resp.status_code == 200
    active = bank_client.get("/api/content-bank").json()["items"]
    assert active == []


def test_pull_writes_into_section_outputs_for_current_week(bank_client):
    import flatwhite.db as db_module
    created = bank_client.post("/api/content-bank", json={
        "segment_type": "big_conversation", "title": "A", "body_text": "**pulled text**",
    }).json()
    resp = bank_client.post(f"/api/content-bank/{created['id']}/pull", json={"target_section": "big_conversation"})
    assert resp.status_code == 200
    week_iso = db_module.get_current_week_iso()
    outputs = db_module.load_all_section_outputs(week_iso)
    assert outputs["big_conversation"]["output_text"] == "**pulled text**"
    assert outputs["big_conversation"]["model_used"] == "content_bank"


def test_pull_unknown_id_404s(bank_client):
    resp = bank_client.post("/api/content-bank/99999/pull", json={"target_section": "big_conversation"})
    assert resp.status_code == 404
