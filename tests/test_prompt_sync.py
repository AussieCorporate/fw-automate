"""The Big Conversation prompt exists in TWO copies. Keep them honest.

The copy that actually writes the pieces is the big-conversation SKILL's
`references/generate-prompt.md`, which lives in the Instagram screenshotter
repo. FW's `BIG_CONVERSATION_DRAFT_SYSTEM` is a fallback the dashboard's
frontend never calls.

They have already drifted once, badly: on 25 Aug 2026 a whole session's prompt
work went into FW's copy while the skill's copy - the one that ships - was
never touched, so the drafts did not change at all. The same duplication bug
had already bitten the Off the Clock prompt, where the preview endpoint's copy
had silently lost the bold marks.

Collapsing them into one file is not possible: the skill is a separate repo
that may not be checked out, and it cannot import Python. So this test is the
guard instead. It checks that every LOAD-BEARING rule is present in both, and
names which side is missing it when they diverge.

Where the skill is not on this machine, the skill-side checks skip rather than
fail - a CI box or a fresh clone should not go red for a repo it does not have.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.classify.prompts import BIG_CONVERSATION_DRAFT_SYSTEM as FW_PROMPT

_SKILL_DIR = (Path.home() / "Documents" / "MISC" / "instagram-dm-screenshotter" /
              "output" / ".claude" / "skills" / "big-conversation")
_GENERATE_PROMPT = _SKILL_DIR / "references" / "generate-prompt.md"

# Each rule: a label, plus what proves it is present on each side. Phrasing
# differs between the two files (one is prose, one is a Python string), so
# these are the distinguishing markers rather than shared sentences.
_LOAD_BEARING_RULES = [
    ("close on counsel, not an aphorism",
     lambda fw: "counsel" in fw.lower() and "permission" in fw.lower(),
     lambda sk: "close on counsel" in sk and "permission not to act" in sk),
    ("the emotional beat / removal of self-blame",
     lambda fw: "emotional" in fw.lower() and "self-blame" in fw.lower(),
     lambda sk: "self-blame" in sk),
    ("operational context only, not research for its own sake",
     lambda fw: "operational condition" in fw.lower(),
     lambda sk: "operational condition" in sk),
    ("name the community as the evidence",
     lambda fw: "name the community as the evidence" in fw.lower(),
     lambda sk: "name the community as the evidence" in sk),
    ("one release valve (a joke or ordinary idiom)",
     lambda fw: "release valve" in fw.lower(),
     lambda sk: "release valve" in sk),
    ("earn the length / decide the conclusion first",
     lambda fw: "earn the length" in fw.lower(),
     lambda sk: "earn the length" in sk),
    ("ordinary idiom over fresh coinage",
     lambda fw: "ordinary idiom" in fw.lower(),
     lambda sk: "ordinary idiom" in sk),
]


def _flat(text: str) -> str:
    """Collapse whitespace before matching. Both files are hard-wrapped prose,
    so a rule's phrase is regularly split across a line break - matching the
    raw text gives false "drift" on wrapping alone."""
    return " ".join(text.split()).lower()


def _skill_text() -> str | None:
    return _flat(_GENERATE_PROMPT.read_text()) if _GENERATE_PROMPT.is_file() else None


def test_every_load_bearing_rule_is_in_the_fw_prompt():
    missing = [name for name, in_fw, _ in _LOAD_BEARING_RULES if not in_fw(FW_PROMPT)]
    assert not missing, (
        "FW's BIG_CONVERSATION_DRAFT_SYSTEM is missing: " + ", ".join(missing))


def test_every_load_bearing_rule_is_in_the_skill_prompt():
    text = _skill_text()
    if text is None:
        return  # skill repo not on this machine
    missing = [name for name, _, in_skill in _LOAD_BEARING_RULES if not in_skill(text)]
    assert not missing, (
        "The SKILL's generate-prompt.md - the copy that actually writes the "
        "pieces - is missing: " + ", ".join(missing))


def test_the_two_copies_have_not_drifted():
    """Named separately so a failure says WHICH side fell behind."""
    text = _skill_text()
    if text is None:
        return
    drift = []
    for name, in_fw, in_skill in _LOAD_BEARING_RULES:
        fw_has, skill_has = in_fw(FW_PROMPT), in_skill(text)
        if fw_has != skill_has:
            behind = "the skill (which ships)" if fw_has else "FW's fallback"
            drift.append(f"{name}: only in {'FW' if fw_has else 'the skill'}, "
                         f"{behind} is behind")
    assert not drift, "Prompt copies have drifted -\n  " + "\n  ".join(drift)


def test_neither_copy_still_bans_the_published_closing():
    """The retired rule listed Victor's own 20 Jul closing as forbidden."""
    banned_shape = 'not a tidy "up to you" resolution'
    assert banned_shape not in FW_PROMPT
    text = _skill_text()
    if text is not None:
        # It may appear inside the correction note explaining what it used to
        # say; it must not survive as a live instruction in SKILL.md's step 4.
        skill_md = (_SKILL_DIR / "SKILL.md")
        if skill_md.is_file():
            assert banned_shape + " — see" not in skill_md.read_text()
