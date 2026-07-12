import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.dashboard.api as api


def _capture(monkeypatch, available=("claude-opus-4-6", "claude-sonnet-4-6")):
    captured = {}
    def fake_route(task_type, prompt, system="", model_override=None):
        captured["model_override"] = model_override
        return "written segment"
    monkeypatch.setattr(api, "route", fake_route)
    monkeypatch.setattr(api, "list_available_models",
                        lambda: [{"id": m} for m in available])
    return captured


def test_selected_model_reaches_route(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_off_the_clock({}, "claude-opus-4-6")
    assert cap["model_override"] == "claude-opus-4-6"


def test_unknown_model_falls_back_to_default(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_off_the_clock({}, "not-a-real-model")
    assert cap["model_override"] is None


def test_model_with_no_api_key_falls_back(monkeypatch):
    cap = _capture(monkeypatch, available=("claude-sonnet-4-6",))
    api._proceed_off_the_clock({}, "gpt-5.4")   # not in available -> no key
    assert cap["model_override"] is None


def test_no_selection_uses_default(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_off_the_clock({}, None)
    assert cap["model_override"] is None
    cap2 = _capture(monkeypatch)
    api._proceed_off_the_clock({}, "")
    assert cap2["model_override"] is None
