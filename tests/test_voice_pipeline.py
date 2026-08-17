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
    """4 paragraphs / 280-340 words (365 hard ceiling) for Big Conversation;
    240-280 target (225-262 in practice) for Brains Trust - Victor's 18 Aug
    binding numbers, not the old 4-6 / 300-450 or 200-350 aspirational bands."""
    assert "4 is the real target" in vp.BIG_CONVERSATION_SHAPE_BLOCK
    assert "280-340" in vp.BIG_CONVERSATION_SHAPE_BLOCK
    assert "365" in vp.BIG_CONVERSATION_SHAPE_BLOCK
    assert "240-280" in vp.BRAINS_TRUST_SHAPE_BLOCK
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


# ─── Length: mechanical, plain-code checks (18 Aug 2026, Victor's binding note) ──


def test_length_specs_match_the_binding_numbers():
    """These numbers came from Victor directly, not from theory - pin them
    exactly so a future edit can't quietly loosen the band."""
    bc = vp.LENGTH_SPECS["big_conversation"]
    assert (bc["word_target_min"], bc["word_target_max"], bc["word_hard_ceiling"]) == (280, 340, 365)
    assert bc["paragraph_target_max"] == 4
    assert bc["paragraph_hard_ceiling"] == 5

    bt = vp.LENGTH_SPECS["brains_trust"]
    assert (bt["word_target_min"], bt["word_target_max"], bt["word_hard_ceiling"]) == (240, 280, 340)
    assert bt["paragraph_hard_ceiling"] == 5


def test_word_count_ignores_chart_placeholders():
    text = "One two three.\n\n[CHART - Source: ABS, June 2026]\n\nFour five six seven."
    assert vp._word_count(text) == 7


def test_paragraph_count_ignores_charts_and_lone_attribution_lines():
    text = (
        "Paragraph one here.\n\n"
        "[CHART - Source: ABS]\n\n"
        "Paragraph two here.\n\n"
        '"A pull quote."\n'
        "- Jarden\n\n"
        "Paragraph three here."
    )
    # 3 prose paragraphs + 1 quote block = 4 (the lone "- Jarden" attribution
    # line is excluded, but the quote text itself is still a block)
    assert vp._paragraph_count(text) == 4


def test_check_length_flags_over_hard_ceiling():
    over = " ".join(["word"] * 400)  # 400 words, over both segments' ceilings
    result = vp.check_length(over, "big_conversation")
    assert result["word_count"] == 400
    assert result["over_word_hard_ceiling"] is True
    assert result["within_word_target"] is False


def test_check_length_within_target():
    words = " ".join(["word"] * 300)  # inside 280-340 for big_conversation
    result = vp.check_length(words, "big_conversation")
    assert result["within_word_target"] is True
    assert result["over_word_hard_ceiling"] is False


def test_run_voice_chain_reports_word_and_paragraph_counts_for_every_stage(monkeypatch):
    def fake_route(task_type, prompt, system="", model_override=None):
        if task_type == "voice_shape":
            return " ".join(["word"] * 300)  # inside big_conversation's band
        if task_type == "voice_strip":
            return " ".join(["word"] * 300) + "\n---CHANGES---\nNo changes."
        raise AssertionError

    monkeypatch.setattr(vp, "route", fake_route)
    result = vp.run_voice_chain("big_conversation", generate_fn=lambda: "short stage 1 draft")

    assert result["word_counts"]["stage1"] == 4
    assert result["word_counts"]["stage2"] == 300
    assert result["word_counts"]["stage3"] == 300
    assert "paragraph_counts" in result
    assert result["length_warnings"] == []


def test_run_voice_chain_recuts_once_then_reports_if_still_over_ceiling(monkeypatch):
    over_ceiling = " ".join(["word"] * 400)  # over big_conversation's 365 ceiling
    shape_calls = {"n": 0}

    def fake_route(task_type, prompt, system="", model_override=None):
        if task_type == "voice_shape":
            shape_calls["n"] += 1
            if shape_calls["n"] == 2:
                assert "do not compress by rewriting" in prompt.lower()
            return over_ceiling  # stays over ceiling even after the re-cut pass
        if task_type == "voice_strip":
            return over_ceiling + "\n---CHANGES---\nNo changes."
        raise AssertionError

    monkeypatch.setattr(vp, "route", fake_route)
    result = vp.run_voice_chain("big_conversation", generate_fn=lambda: "draft")

    assert shape_calls["n"] == 2, "one initial shape call plus exactly one re-cut, never more"
    assert result["length_warnings"], "must report the overage plainly, not pass it through silently"
    assert any("hard ceiling" in w for w in result["length_warnings"])


def test_run_voice_chain_recut_success_clears_the_warning(monkeypatch):
    over_ceiling = " ".join(["word"] * 400)
    under_ceiling = " ".join(["word"] * 300)
    shape_calls = {"n": 0}

    def fake_route(task_type, prompt, system="", model_override=None):
        if task_type == "voice_shape":
            shape_calls["n"] += 1
            return over_ceiling if shape_calls["n"] == 1 else under_ceiling
        if task_type == "voice_strip":
            return under_ceiling + "\n---CHANGES---\nNo changes."
        raise AssertionError

    monkeypatch.setattr(vp, "route", fake_route)
    result = vp.run_voice_chain("big_conversation", generate_fn=lambda: "draft")

    assert shape_calls["n"] == 2
    assert result["length_warnings"] == []
    assert result["word_counts"]["stage2"] == 300


def test_shape_blocks_instruct_aiming_at_the_middle_of_the_band():
    assert "MIDDLE" in vp.BIG_CONVERSATION_SHAPE_BLOCK
    assert "MIDDLE" in vp.BRAINS_TRUST_SHAPE_BLOCK
    assert "middle of the target word band" in vp.SHAPE_TO_PUBLISHED_SYSTEM.lower()


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
