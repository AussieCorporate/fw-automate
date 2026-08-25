"""The SUBSTANCE half of the Big Conversation voice rules.

Evidence: all six draft/published pairs, 13 Jul - 24 Aug 2026, diffed for what
Victor ADDS rather than what he cuts. The 24 Aug register work covered "drafts
are too clever"; this covers the other half, "drafts are too thin".

These tests exist because a previous refresh wrote a closing rule FROM THEORY
that banned Victor's own published closing sentence ("it's just up to you to
prioritise accordingly", published 20 Jul) and called four of six published
closings a "failure mode". Published editions outrank rule text. Pin the
evidence so that cannot happen again.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.classify.prompts import BIG_CONVERSATION_DRAFT_SYSTEM as PROMPT

_SKILL_REFS = (Path.home() / "Documents" / "MISC" / "instagram-dm-screenshotter" /
               "output" / ".claude" / "skills" / "big-conversation" / "references")


def test_prompt_requires_counsel_at_the_close_not_an_aphorism():
    """6/6 published pieces end on advice or permission; every draft ended on
    a clever line that got cut."""
    low = PROMPT.lower()
    assert "counsel" in low
    assert "permission" in low


def test_prompt_requires_the_emotional_beat():
    """The most consistently missing ingredient across all six drafts."""
    low = PROMPT.lower()
    assert "emotional" in low
    assert "self-blame" in low


def test_prompt_requires_operational_context_but_warns_against_research_for_its_own_sake():
    """Victor ADDS the condition that changes the reader's next move and CUTS
    abstract/legal context (the 17 Aug contract-law paragraph was cut)."""
    low = PROMPT.lower()
    assert "operational condition" in low
    assert "changes what the reader should do" in low
    assert "do not add research for its own sake" in low


def test_prompt_allows_naming_the_community_but_never_an_individual():
    low = PROMPT.lower()
    assert "name the community as the evidence" in low
    assert "never" in low and "individual" in low


def test_prompt_requires_one_joke_or_idiom():
    low = PROMPT.lower()
    assert "release valve" in low
    assert "dodged a bullet" in low


def test_prompt_no_longer_bans_the_published_closing():
    """The retired rule listed this verbatim published sentence as forbidden."""
    assert "up to you to prioritise accordingly" in PROMPT
    # ...and it appears as an EXAMPLE TO FOLLOW, not in a banned list.
    idx = PROMPT.index("up to you to prioritise accordingly")
    window = PROMPT[max(0, idx - 400):idx].lower()
    assert "do not close" not in window
    assert "banned" not in window


def test_prompt_still_carries_the_register_rules_from_the_24_aug_work():
    """The substance addition must not have displaced the register half."""
    low = PROMPT.lower()
    assert "ordinary idiom over fresh phrasing" in low
    assert "aphorism budget" in low


# ─── The skill's own copy - the one that actually ships ────────────────────

def _skill_file(name: str) -> str | None:
    p = _SKILL_REFS / name
    return p.read_text() if p.is_file() else None


def test_skill_closing_rule_was_corrected_if_the_skill_is_on_this_machine():
    text = _skill_file("generate-prompt.md")
    if text is None:
        return  # skill lives in a separate repo; skip where it isn't checked out
    assert "WHAT THE PIECE MUST CARRY" in text, "substance section missing from the skill prompt"
    # The banned-closing rule must be gone, not merely softened.
    assert "the old rule banned Victor's own published closings" in text


def test_skill_cardinal_rule_allows_the_aggregate_community():
    text = _skill_file("voice-guide.md")
    if text is None:
        return
    assert "never retell an INDIVIDUAL submission" in text
    assert "when we put the question to the community" in text.lower()


def test_announced_transitions_entry_distinguishes_scaffolding_from_a_claim():
    """The strip deleted "The problem is what AI has done to the rest." from the
    Cover Letters piece and Victor put a blunter version back ("The real problem
    is AI."). A sentence that ASSERTS something is content, not scaffolding."""
    from flatwhite.classify.voice_pipeline import CLAUDE_TELL_CATALOGUE as CAT
    entry = CAT.split("14. ANNOUNCED TRANSITIONS")[1].split("15. ")[0]
    assert "over-firing" in entry
    assert "The real problem is AI" in entry
    assert "asserts" in entry.lower()
