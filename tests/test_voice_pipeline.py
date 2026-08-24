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


def test_brains_trust_shape_block_enforces_consequence_not_setup_opening():
    """The most load-bearing pinned Brains Trust rule (Victor's 27 Jul edit:
    lead on the consequence, not the setup fact) must be enforced by the
    SHAPE stage too, not just the GENERATE prompt - a draft that opens on
    the setup fact needs its consequence sentence promoted to P1."""
    low = vp.BRAINS_TRUST_SHAPE_BLOCK.lower()
    assert "consequence" in low and "setup" in low
    assert "promote" in low


def test_shape_to_published_rejects_unknown_segment():
    try:
        vp.shape_to_published("draft text", "some_other_segment")
        assert False, "should have raised"
    except ValueError as e:
        assert "big_conversation" in str(e) and "brains_trust" in str(e)


def test_strip_prompt_still_prefers_deletion_over_rewriting():
    """Victor lifted the absolute delete-only ban on 17 Aug 2026 (a
    cross-family rewrite on GPT is not Claude rewriting its own tell), but
    deletion stays the first move and rewriting stays the fallback. If this
    ever inverts, the stage starts polishing instead of cutting."""
    low = vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()
    assert "prefer deletion" in low
    assert "when both would work, delete" in low
    assert "rewriting is the fallback, not the default" in low


def test_strip_prompt_carries_the_veto_caution():
    """A flagged tell that could plausibly be Victor's own voice must be
    left in place and flagged, not silently deleted."""
    low = vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()
    assert "victor's own hand-edited voice" in low
    assert "flag it in your output instead of deleting it" in low


def test_tell_catalogue_has_all_26_entries():
    """22 structural patterns, entry 23 the stock-phrase vocabulary (17 Aug
    2026), plus entries 24-26 added 24 Aug 2026 from the draft-vs-published
    register diff (docs/big-conversation-published-spec.md)."""
    import re
    headings = re.findall(r"^\d+\. ", vp.CLAUDE_TELL_CATALOGUE, flags=re.MULTILINE)
    assert len(headings) == 26, f"expected 26 catalogue entries, found {len(headings)}"


def test_tell_catalogue_includes_findings_new_entries():
    low = vp.CLAUDE_TELL_CATALOGUE.lower()
    assert "announced wrap-up openers" in low
    assert "done properly" in low and "done the right way" in low
    assert "end-placed reader reassurance" in low


def test_tell_catalogue_carries_the_register_entries():
    """24 Aug 2026: the drafts' failure mode is over-engineering (every
    paragraph ends on a quotable line, coined phrases where idioms exist).
    The catalogue must name it, and the idiom substitution must be the
    required fix for entry 25 - it is Victor's own documented edit
    ('can't untell them' -> 'can't take it back')."""
    low = vp.CLAUDE_TELL_CATALOGUE.lower()
    assert "mic-drop paragraph closers" in low
    assert "clever coinage where an idiom exists" in low
    assert "wry-understatement tics" in low
    assert "can't take it back" in low


def test_idiom_replacement_is_the_allowed_exception_to_no_new_figures():
    """The rewrite guardrail bans fresh figures of speech but must allow the
    common spoken idiom as a replacement - the ordinary phrase is the house
    voice, and banning it would ban the exact edit Victor makes by hand."""
    low = vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()
    assert "common spoken idiom" in low
    assert "only fresh phrasing is banned" in low


def test_stock_list_no_longer_bans_victors_own_idioms():
    """'a double-edged sword' shipped in Victor's own 10 Aug intro. The stock
    list is essay filler only; spoken idiom must not be on it."""
    import re
    stock_entry = vp.CLAUDE_TELL_CATALOGUE.split("23. STOCK PHRASES")[1].split("24. ")[0]
    banned_lines = "\n".join(
        l for l in stock_entry.splitlines() if not l.strip().startswith("(Removed")
    )
    assert "double-edged sword" not in banned_lines.lower()


def test_allowed_repairs_are_narrow():
    system = vp.STRIP_CLAUDE_PHRASING_SYSTEM
    assert "ALLOWED MINIMAL REPAIRS" in system
    assert "change nothing" in system
    assert "Never add a fact" in system


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


# ─── Strip stage runs on GPT-5.4, never silently falls back to Claude ───────
# (18 Aug 2026, Victor's binding note: a Claude model can't reliably hear its
# own tells, so the strip pass must run on a different model family.)


def test_voice_strip_resolves_to_gpt_5_4_by_default():
    from flatwhite import model_router as mr
    assert mr.DEFAULT_MODEL_BY_TASK["voice_strip"] == "gpt-5.4"
    assert mr.MODEL_REGISTRY["gpt-5.4"]["provider"] == "openai"
    # voice_shape stays on Claude - only the strip stage moves providers.
    assert mr.MODEL_REGISTRY[mr.DEFAULT_MODEL_BY_TASK["voice_shape"]]["provider"] == "anthropic"


def test_voice_strip_raises_when_openai_key_missing_not_silently_routed_elsewhere(monkeypatch):
    """route() itself must not substitute a different provider - it should
    fail on the exact model_id the task type maps to (gpt-5.4), never quietly
    call Claude instead."""
    from flatwhite import model_router as mr
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(mr, "MODEL_REGISTRY", mr.MODEL_REGISTRY)  # no-op, documents intent
    try:
        mr.route(task_type="voice_strip", prompt="x", system="y")
        assert False, "should have raised - no OPENAI_API_KEY configured"
    except Exception as e:
        assert "OPENAI_API_KEY" in str(e)
        assert "gpt-5.4" in str(e)


def test_run_voice_chain_stops_and_reports_when_strip_stage_unavailable_never_falls_back(monkeypatch):
    """The chain must not crash and must not quietly strip with Claude. It
    stops at stage 2's output, marks stage 3 'not_stripped', and explains
    why in plain English."""
    def fake_route(task_type, prompt, system="", model_override=None):
        if task_type == "voice_shape":
            return " ".join(["word"] * 300)  # inside band, no recut needed
        if task_type == "voice_strip":
            raise ValueError("No API key configured for gpt-5.4 (set OPENAI_API_KEY)")
        raise AssertionError(f"unexpected task_type {task_type}")

    monkeypatch.setattr(vp, "route", fake_route)
    result = vp.run_voice_chain("big_conversation", generate_fn=lambda: "stage 1 draft")

    assert result["stage3_status"] == "not_stripped"
    assert result["stage3_error"] is not None
    assert "OPENAI_API_KEY" in result["stage3_error"]
    assert "never" in result["stage3_error"].lower() or "not silently" in result["stage3_error"].lower() \
        or "by design" in result["stage3_error"].lower()
    # The unstripped piece returned is EXACTLY stage 2's output - not
    # re-generated, not touched by any other model.
    assert result["stage3_stripped"] == result["stage2_shaped"]
    assert result["stage3_changes"] == ""


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


# ─── Stock-phrase blocklist + constrained rewrite ───────────────────────────
# (17 Aug 2026, Victor: the catalogue was 22 structural patterns and almost
# nothing at the word level, so stock AI filler slipped through. He also
# reversed the delete-only rule for this stage specifically: GPT may rewrite,
# because a cross-family rewrite is not the same risk as Claude rewriting its
# own tell.)


def test_stock_phrase_blocklist_carries_the_real_ai_filler_kit():
    cat = vp.CLAUDE_TELL_CATALOGUE.lower()
    for phrase in [
        "in today's fast-paced",
        "at the end of the day",
        "here's the thing",
        "it's worth noting",
        "a testament to",
        "navigate the landscape",
        "delve into",
        "underscores",
        "serves as a reminder",
        "sheds light on",
        "when it comes to",
        "plays a crucial role",
    ]:
        assert phrase in cat, f"stock phrase missing from catalogue: {phrase}"


def test_stock_phrases_are_fixed_on_sight_not_flagged_for_victor():
    """The hand-edit caution exists because a structural tell may be Victor's
    own line. Stock filler never is, so it must be exempt from that caution."""
    sys_prompt = vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()
    assert "stock phrase" in sys_prompt
    assert "exempt" in sys_prompt
    assert "never victor" in sys_prompt or "never his" in sys_prompt


def test_strip_may_rewrite_under_guardrails_not_delete_only():
    """Victor reversed the delete-only rule for this stage on 17 Aug 2026.
    Deletion is still preferred; rewriting is allowed where deleting breaks
    the sentence, under three guardrails."""
    sys_prompt = vp.STRIP_CLAUDE_PHRASING_SYSTEM.lower()
    assert "rewrite is allowed" in sys_prompt
    assert "prefer deletion" in sys_prompt
    assert "no new fact" in sys_prompt
    assert "no new figure of speech" in sys_prompt
    assert "plain anglo" in sys_prompt
