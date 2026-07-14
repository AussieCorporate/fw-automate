"""The editorial intro must follow the flat-white-intro skill's shape:
'Good morning AusCorp.' bold hook (built from the nominated big story of the
week) bridging into the Big Conversation, then a preview of the other
segments. Before this fix, _proceed_editorial used a generic prompt with no
relationship to the skill or its hard rules (no em dashes, Australian
spelling, specific numbers)."""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.dashboard.api as api


def _capture(monkeypatch):
    captured = {}
    def fake_route(task_type, prompt, system="", model_override=None):
        captured["prompt"] = prompt
        captured["system"] = system
        captured["task_type"] = task_type
        return "**Good morning AusCorp.** written intro"
    monkeypatch.setattr(api, "route", fake_route)
    return captured


def test_prompt_includes_big_story_big_conversation_and_other_segments(monkeypatch):
    cap = _capture(monkeypatch)
    data = {
        "big_story": "Optiver paid an average $1.4 million per employee last year.",
        "big_conversation_output": "The three-week PIP has become a way to show someone the door.",
        "other_segments": [
            {"id": "pulse", "label": "Stress Index", "output_text": "Market pulse is calm this week."},
        ],
    }
    api._proceed_editorial(data, None)
    assert "Optiver paid an average $1.4 million per employee last year." in cap["prompt"]
    assert "The three-week PIP has become a way to show someone the door." in cap["prompt"]
    assert "Market pulse is calm this week." in cap["prompt"]


def test_system_prompt_encodes_the_flat_white_intro_skill_shape(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_editorial({"big_story": "x", "big_conversation_output": "y", "other_segments": []}, None)
    assert "Good morning AusCorp." in cap["system"]
    assert "em dash" in cap["system"].lower()
    assert "Oxford comma" in cap["system"] or "oxford comma" in cap["system"].lower()


def test_missing_big_story_uses_placeholder_not_a_crash(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_editorial({"other_segments": []}, None)
    assert "no big story of the week nominated" in cap["prompt"]
