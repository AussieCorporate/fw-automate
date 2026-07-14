import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.model_router import TEMPERATURE_BY_TASK, DEFAULT_MODEL_BY_TASK


def test_brains_trust_task_type_is_registered():
    assert "brains_trust" in TEMPERATURE_BY_TASK
    assert 0.0 <= TEMPERATURE_BY_TASK["brains_trust"] <= 0.5  # data-led, not free-wheeling
    assert DEFAULT_MODEL_BY_TASK["brains_trust"] == "claude-sonnet-4-6"


def test_brains_trust_voice_exists_and_bans_em_dashes():
    from flatwhite.classify.prompts import BRAINS_TRUST_VOICE
    assert "Aussie Corporate" in BRAINS_TRUST_VOICE or "Flat White" in BRAINS_TRUST_VOICE
    assert "—" not in BRAINS_TRUST_VOICE  # the prompt itself must not contain an em dash
    assert "no em dash" in BRAINS_TRUST_VOICE.lower() or "em dash" in BRAINS_TRUST_VOICE.lower()


import json
from unittest.mock import patch
import flatwhite.dashboard.api as api


def _capture_route(monkeypatch):
    captured = {}
    def fake_route(task_type, prompt, system="", model_override=None):
        captured["task_type"] = task_type
        captured["prompt"] = prompt
        captured["system"] = system
        captured["model_override"] = model_override
        return "Drafted Brains Trust body."
    monkeypatch.setattr(api, "route", fake_route)
    monkeypatch.setattr(api, "list_available_models",
                         lambda: [{"id": "claude-sonnet-4-6"}])
    return captured


def test_proceed_brains_trust_calls_route_with_the_chosen_angle(monkeypatch):
    cap = _capture_route(monkeypatch)
    data = {
        "chosen_pitch": "Wholesale power prices at 5-year lows",
        "chosen_angle": "Households see no relief; an earnings cliff is coming for AGL/Origin.",
        "chosen_why_tac": "Energy bills matter to every reader.",
        "candidates_pool": [
            {"date_iso": "2026-07-13", "pitch": "Wholesale power prices at 5-year lows", "angle": "cliff coming"},
            {"date_iso": "2026-06-29", "pitch": "Unrelated pitch", "angle": "something else"},
        ],
    }
    out = api._proceed_brains_trust(data, "claude-sonnet-4-6")
    assert out == "Drafted Brains Trust body."
    assert cap["task_type"] == "brains_trust"
    assert "Wholesale power prices at 5-year lows" in cap["prompt"]
    assert "Unrelated pitch" in cap["prompt"]  # the whole pool is handed over for consolidation
    assert cap["model_override"] == "claude-sonnet-4-6"


def test_proceed_brains_trust_honours_custom_prompt(monkeypatch):
    cap = _capture_route(monkeypatch)
    out = api._proceed_brains_trust({}, None, custom_prompt="Write exactly this.")
    assert out == "Drafted Brains Trust body."
    assert cap["prompt"] == "Write exactly this."
    assert cap["task_type"] == "brains_trust"


def test_proceed_brains_trust_handles_missing_pool_gracefully(monkeypatch):
    cap = _capture_route(monkeypatch)
    out = api._proceed_brains_trust({"chosen_pitch": "Solo angle, no pool"}, None)
    assert out == "Drafted Brains Trust body."
    assert "Solo angle, no pool" in cap["prompt"]


def test_brains_trust_registered_in_proceed_fns():
    # api_proceed_section dispatches via a local dict; assert brains_trust
    # routes to the real generator rather than 400ing as "Unknown section".
    import inspect
    src = inspect.getsource(api.api_proceed_section)
    assert '"brains_trust": _proceed_brains_trust' in src or "'brains_trust': _proceed_brains_trust" in src


def test_angles_endpoint_returns_reader_output(monkeypatch):
    fake_rows = [{"id": "angle:abc", "date_iso": "2026-07-13", "pitch": "P", "angle": "A", "why_tac": "W", "source_pdf_ids": [], "source_pdf_date": None}]
    monkeypatch.setattr(
        "flatwhite.dashboard.brains_trust_research.load_angle_recommendations",
        lambda weeks=3: fake_rows,
    )
    result = api.api_brains_trust_angles()
    body = json.loads(result.body)
    assert body["angles"] == fake_rows


def test_angles_endpoint_fails_soft_on_reader_exception(monkeypatch):
    def _boom(weeks=3):
        raise RuntimeError("Trading Strategy dir unreadable")
    monkeypatch.setattr(
        "flatwhite.dashboard.brains_trust_research.load_angle_recommendations", _boom
    )
    result = api.api_brains_trust_angles()
    body = json.loads(result.body)
    assert body["angles"] == []
