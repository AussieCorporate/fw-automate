"""Brains Trust voice rules, derived from Victor's edit of a real draft.

On 27 Jul 2026 Victor edited a live Brains Trust draft (AI hiring + the AI
laptop refresh) down from 346 words to 244 and sent both versions back. Every
rule asserted here comes from a specific difference between the two, so the
prompt encodes his edit rather than a general theory of good writing.

What he cut, in his own edit:
- the setup-fact opener (laptop chips) in favour of the consequence (jobs)
- "The practical question is what happens when..."      posed-question device
- "Morgan Stanley's AlphaWise research provides the answer"  announced pivot
- "The employment data sharpens the picture further."   announced pivot
- "The convergence matters."                            meta-commentary
- "The hardware cycle and the hiring cycle are now running in the same
   direction."                                          summary restating the link
- "what the research calls 'graduate-ladder compression'"  coined jargon
- stacked source chains, in favour of "Jarden estimates" / "Gartner expects"
- third person, in favour of "you"
- "167,200", in favour of "roughly 167,000"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.classify.prompts import BRAINS_TRUST_VOICE

_V = BRAINS_TRUST_VOICE.lower()


def test_leads_on_consequence_not_setup():
    """He moved the jobs story to the top and demoted the hardware cycle."""
    assert "consequence" in _V
    assert "context" in _V


def test_bans_announced_pivots():
    """Sentences whose only job is to announce the join between paragraphs."""
    assert "announce" in _V
    assert "sharpens the picture" in _V, "name the real example so it is unmistakable"
    assert "provides the answer" in _V


def test_bans_posed_question_device():
    assert "the practical question is" in _V


def test_bans_meta_commentary_about_assembly():
    """'The convergence matters.' - the piece narrating its own construction."""
    assert "the convergence matters" in _V


def test_bans_summary_line_restating_the_link():
    assert "running in the same direction" in _V


def test_bans_coined_jargon_in_quotes():
    assert "graduate-ladder compression" in _V


def test_attribution_is_bank_plus_plain_verb():
    assert "jarden estimates" in _V or "gartner expects" in _V
    assert "alphawise" in _V, "the stacked product/report name he cut"


def test_attribution_ban_is_a_pattern_not_one_phrase():
    """First fix banned the literal phrase 'AlphaWise research provides', and
    the next draft simply wrote 'AlphaWise research finds'. The rule has to
    catch the shape, not the wording."""
    assert "never name a research product" in _V
    assert "whatever verb follows" in _V


def test_pull_quote_must_be_a_standalone_block():
    """The draft buried 'changing shape, not size' inside a sentence and added
    a comment about the framing, instead of setting it as the pull quote."""
    assert "do not bury a quotable line" in _V
    assert "changing shape, not size" in _V
    assert "without introduction" in _V


def test_register_requires_contractions_and_second_person():
    assert "contraction" in _V
    assert "isn't" in _V and "it's" in _V, "name the contractions explicitly"
    assert "reader as 'you'" in _V
    assert "cohort beneath you" in _V, "his own phrasing, as the worked example"


def test_requires_rounded_numbers():
    assert "167,200" in _V and "167,000" in _V


def test_length_target_matches_his_edit():
    """His edit landed at 244 words; the old 260-380 band let drafts hit 400+."""
    assert "240" in BRAINS_TRUST_VOICE
    assert "380" not in BRAINS_TRUST_VOICE, "the old ceiling must be gone"


def test_existing_house_rules_survive():
    """The rules that were already right must not be lost in the rewrite."""
    assert "australian english" in _V
    assert "em dash" in _V
    assert "—" not in BRAINS_TRUST_VOICE, "the prompt itself must contain no em dash"
    assert "invent" in _V, "never invent a figure or a bank"


# ─── 17 Aug 2026 refresh — docs/voice-refresh-findings.md ───────────────────
# These pin the genuine drift found across the 6 most recent published
# editions. They EXTEND the 27 Jul rules above; none of those assertions were
# weakened to add these.


def test_you_and_pull_quote_rules_were_not_weakened_by_the_refresh():
    """CONTROLLER RULING: the research flagged 'you' and pull quotes as
    'drift' but they are Victor's deliberate 27 Jul calling, already encoded
    here and pinned by the tests above. This refresh must not touch them."""
    assert "reader as 'you'" in _V
    assert "do not bury a quotable line" in _V


def test_bans_fake_profound_reframe():
    """Reached print once already in a Brains Trust piece (27 Jul, AI hiring):
    'AI in Australia isn't producing mass layoffs. It's producing slower
    hiring...' - the tell list now covers this segment too."""
    assert "fake-profound reframe" in _V
    assert "isn't producing mass layoffs" in _V


def test_bans_done_properly_tic():
    """'Done properly,' / 'Done the right way,' used twice in six recent
    editions - a calcifying house tic, not house voice."""
    assert "done properly" in _V
    assert "done the right way" in _V


def test_bans_in_the_end_wrapup_opener():
    assert "in the end" in _V


def test_requires_closing_to_land_the_mechanism():
    """Only 2 of 6 recent closings explained the contradiction rather than
    piling up a stat or a forward-looking watch-point."""
    assert "land the closing paragraph on the economic mechanism" in _V
    assert "here's what to watch next" in _V


def test_pull_quote_is_optional_and_broken_attribution_is_banned():
    """One recent edition (20 Jul) shipped a pull quote with a broken, empty
    attribution ('- UBS previously expected... ' with a dash and nothing
    after it). The rule must say that's worse than skipping the quote."""
    assert "optional, not mandatory" in _V
    assert "broken or empty attribution" in _V


def test_length_working_range_reflects_what_actually_ships():
    """Recent editions run 225-262 words, nowhere near the 320-340 ceiling."""
    assert "225 and 262" in _V
    assert "240" in BRAINS_TRUST_VOICE, "the stated band floor must still be present"
    assert "380" not in BRAINS_TRUST_VOICE, "the old ceiling must still be gone"


def test_length_target_is_tightened_below_the_pinned_ceiling():
    """Victor's 27 Jul edit pinned 240-320 words / 340 ceiling - that band is
    NOT weakened here. But length is now a first-class, mechanically checked
    requirement: the real TARGET inside that band is 240-280, and 320 is
    ceiling headroom, not something to write toward."""
    assert "240-280" in _V
    assert "320 is a ceiling, not" in _V
    assert "240-320" in BRAINS_TRUST_VOICE, "the pinned band itself must still be stated"


def test_paragraph_ceiling_is_explicit():
    assert "5 is the ceiling, not the target" in _V
