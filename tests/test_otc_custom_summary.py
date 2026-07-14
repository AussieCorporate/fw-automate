"""_generate_otc_custom_summary must produce a SHORT RAW draft blurb for a
custom Off the Clock pick, not the final CATEGORY/title/[LINK] block that
_proceed_off_the_clock produces - that final formatting happens once, later,
when the combined Generate call runs all 5 categories together. Sending an
already-formatted block back through _proceed_off_the_clock a second time
(the bug this guards against) risks a garbled, redundant result.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.dashboard.api as api


def _capture(monkeypatch, available=("claude-opus-4-6", "claude-sonnet-4-6")):
    captured = {}

    def fake_route(task_type, prompt, system="", model_override=None):
        captured["task_type"] = task_type
        captured["prompt"] = prompt
        captured["system"] = system
        captured["model_override"] = model_override
        return "A tiny Marrickville wine bar just opened its doors."

    monkeypatch.setattr(api, "route", fake_route)
    monkeypatch.setattr(api, "list_available_models",
                        lambda: [{"id": m} for m in available])
    return captured


def test_prompt_references_pasted_content_and_category(monkeypatch):
    cap = _capture(monkeypatch)
    output = api._generate_otc_custom_summary(
        "otc_eating",
        "https://smallbusiness-example.com.au/wine-bar",
        "A new wine bar just opened in Marrickville with a tiny, all-Australian list.",
        "claude-opus-4-6",
    )
    assert output == "A tiny Marrickville wine bar just opened its doors."
    assert "Marrickville" in cap["prompt"]
    assert "Eating" in cap["prompt"]
    assert "https://smallbusiness-example.com.au/wine-bar" in cap["prompt"]
    assert cap["model_override"] == "claude-opus-4-6"


def test_prompt_does_not_ask_for_final_category_title_link_format(monkeypatch):
    """The prompt must be clearly distinct from _proceed_off_the_clock's, which
    asks for a CATEGORY header, a catchy title, and a [LINK](url) marker."""
    cap = _capture(monkeypatch)
    api._generate_otc_custom_summary(
        "otc_going", "https://example.com/gig", "A tiny venue is hosting a free gig.", None,
    )
    prompt = cap["prompt"]
    assert "[LINK]" not in prompt
    assert "CATEGORY (uppercase" not in prompt
    assert "catchy title" not in prompt
    # It should explicitly say NOT to produce the final format.
    assert "Do NOT include a category header" in prompt or "not the final" in prompt.lower()


def test_no_url_still_produces_a_prompt(monkeypatch):
    cap = _capture(monkeypatch)
    api._generate_otc_custom_summary("otc_reading", "", "A niche zine just published its third issue.", None)
    assert "A niche zine" in cap["prompt"]


def test_unknown_model_falls_back_to_default(monkeypatch):
    cap = _capture(monkeypatch)
    api._generate_otc_custom_summary("otc_wearing", "https://example.com", "A tiny label dropped a new run.", "not-a-real-model")
    assert cap["model_override"] is None
