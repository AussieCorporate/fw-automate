"""Tests for the voice pipeline (stages 2 and 3, and the chain runner).

No real LLM calls: route() is monkeypatched. These tests pin (a) that the
prompt text carries the real evidence from docs/voice-refresh-findings.md,
(b) that the chain calls all three stages in order and keeps every output,
and (c) that stage 3's output is parsed correctly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.classify import voice_pipeline as vp


def test_shape_prompt_forbids_adding_new_material():
    assert "cutting and tightening" in vp.SHAPE_TO_PUBLISHED_SYSTEM.lower()
    assert "never add" in vp.SHAPE_TO_PUBLISHED_SYSTEM.lower() or "you never add" in vp.SHAPE_TO_PUBLISHED_SYSTEM.lower()
    assert "you do not verify facts, invent sources" in vp.SHAPE_TO_PUBLISHED_SYSTEM.lower()


def test_shape_exemplars_are_real_published_text():
    assert "Forcing colleagues to share a hotel room" in vp.BIG_CONVERSATION_EXEMPLARS
    assert "Staff turnover across the ASX100 fell to a 5-year low" in vp.BRAINS_TRUST_EXEMPLARS


def test_shape_blocks_encode_real_bands_not_aspirational_ones():
    """4 paragraphs / 270-365 words for Big Conversation; 225-262 working
    range for Brains Trust - the real numbers from the findings doc, not the
    old 4-6 / 300-450 or 200-350 aspirational bands."""
    assert "4 is the real target" in vp.BIG_CONVERSATION_SHAPE_BLOCK
    assert "270-365" in vp.BIG_CONVERSATION_SHAPE_BLOCK
    assert "225-262" in vp.BRAINS_TRUST_SHAPE_BLOCK


def test_shape_to_published_rejects_unknown_segment():
    try:
        vp.shape_to_published("draft text", "some_other_segment")
        assert False, "should have raised"
    except ValueError as e:
        assert "big_conversation" in str(e) and "brains_trust" in str(e)


def test_strip_prompt_carries_the_binding_delete_rule():
    assert "DELETING" in vp.STRIP_CLAUDE_PHRASING_SYSTEM
    assert "never by writing a" in vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower() or "never by" in vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()


def test_strip_prompt_carries_the_veto_caution():
    """A flagged tell that could plausibly be Victor's own voice must be
    left in place and flagged, not silently deleted."""
    low = vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()
    assert "victor's own hand-edited voice" in low
    assert "flag it in your output instead of deleting it" in low


def test_tell_catalogue_has_all_22_entries():
    import re
    headings = re.findall(r"^\d+\. ", vp.CLAUDE_TELL_CATALOGUE, flags=re.MULTILINE)
    assert len(headings) == 22, f"expected 22 catalogue entries, found {len(headings)}"


def test_tell_catalogue_includes_findings_new_entries():
    low = vp.CLAUDE_TELL_CATALOGUE.lower()
    assert "announced wrap-up openers" in low
    assert "done properly" in low and "done the right way" in low
    assert "end-placed reader reassurance" in low


def test_allowed_repairs_are_narrow():
    system = vp.STRIP_CLAUDE_PHRASING_SYSTEM
    assert "ALLOWED MINIMAL REPAIRS" in system
    assert "Never write a new sentence" in system


def test_split_strip_output_with_changes_and_flagged():
    raw = (
        "Body text here.\n"
        "---CHANGES---\n"
        "- deleted 'In the end,' (entry 20)\n"
        "---FLAGGED FOR VICTOR---\n"
        "- kept 'make no mistake' - plausibly his own line\n"
    )
    parts = vp.split_strip_output(raw)
    assert parts["body"] == "Body text here."
    assert "deleted 'In the end,'" in parts["changes"]
    assert "plausibly his own line" in parts["flagged"]


def test_split_strip_output_no_changes_no_flag():
    raw = "Just the body, nothing else."
    parts = vp.split_strip_output(raw)
    assert parts["body"] == "Just the body, nothing else."
    assert parts["changes"] == ""
    assert parts["flagged"] == ""


def test_run_voice_chain_calls_all_three_stages_in_order_and_keeps_every_output(monkeypatch):
    calls = []

    def fake_route(task_type, prompt, system="", model_override=None):
        calls.append(task_type)
        if task_type == "voice_shape":
            return "SHAPED DRAFT"
        if task_type == "voice_strip":
            return "STRIPPED BODY\n---CHANGES---\n- deleted something"
        raise AssertionError(f"unexpected task_type {task_type}")

    monkeypatch.setattr(vp, "route", fake_route)

    result = vp.run_voice_chain("big_conversation", generate_fn=lambda: "RAW STAGE 1 DRAFT")

    assert calls == ["voice_shape", "voice_strip"], "shape must run before strip"
    assert result["stage1_generate"] == "RAW STAGE 1 DRAFT"
    assert result["stage2_shaped"] == "SHAPED DRAFT"
    assert result["stage3_stripped"] == "STRIPPED BODY"
    assert "deleted something" in result["stage3_changes"]
    assert result["segment"] == "big_conversation"


def test_run_voice_chain_never_collapses_stages_even_when_strip_makes_no_changes(monkeypatch):
    def fake_route(task_type, prompt, system="", model_override=None):
        if task_type == "voice_shape":
            return "SHAPED"
        if task_type == "voice_strip":
            return "SHAPED\n---CHANGES---\nNo changes - draft was already clean."
        raise AssertionError

    monkeypatch.setattr(vp, "route", fake_route)
    result = vp.run_voice_chain("brains_trust", generate_fn=lambda: "GENERATED")

    # All three stages are still present and distinct keys, even when stage 3
    # made no edits - the chain never silently drops a stage's output.
    assert result["stage1_generate"] == "GENERATED"
    assert result["stage2_shaped"] == "SHAPED"
    assert result["stage3_stripped"] == "SHAPED"
