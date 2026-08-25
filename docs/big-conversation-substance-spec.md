# THE BIG CONVERSATION - the substance spec (25 Aug 2026)

The 24 Aug register spec (`big-conversation-published-spec.md`) found that drafts are
TOO CLEVER: Victor's edits go from clever to ordinary. That was half the problem.

This is the other half. **Drafts are also TOO THIN.** Evidence: all six draft/published
pairs from 13 Jul to 24 Aug 2026, diffed for what Victor ADDS rather than what he cuts,
plus the 23 Jun career-pivot piece (which is gold example 1 in the skill's own reference
file, and which the pipeline still failed to match when re-run on 25 Aug).

| Draft in bank | Published as | Date |
|---|---|---|
| _KIDS_OFFICE_BIG_CONVERSATION.md | Kids in the office, yay or nay? | 13 Jul |
| _Lunch_w_your_team_or_not_... | Do you have to have lunch with your team? | 20 Jul |
| _Manager_Pet_Names_... | When your boss calls you 'babe' | 3 Aug |
| _Mental_Health_at_Big_Companies_... | To tell or not to tell | 10 Aug |
| _Offer_Withdrawn_After_Negotiation_... | Verbal offers don't mean jack | 17 Aug |
| _Cover_Letters_BIG_CONVERSATION.md | Cover letter, yes or no? | 24 Aug |

## The core finding: drafts analyse, published pieces counsel

Six times out of six, the draft closed on a clever resolved aphorism and Victor replaced
it with the reader being told what to do, or given permission not to act.

Drafts cut before print: "Just pay it on purpose." / "The mistakes are the only part
guaranteed a close read." / "A company where nobody rings the EAP reads, in a board pack,
exactly like a company where nobody needed to."

Published: "it's just up to you to prioritise accordingly" (20 Jul) / "having support
outside of work is the part you can actually count on" (10 Aug) / "it's also okay to let
this one go" (3 Aug) / "attach a cover letter if they ask for one. Keep it to half a
page" (24 Aug).

## The rule that was actively causing this

The skill's `generate-prompt.md` CLOSING section required "a short, memorable turn that is
at least slightly unresolved" and listed as a BANNED example the phrase *"it's just up to
you to prioritise accordingly"* - which is, verbatim, the published closing sentence of
the 20 Jul edition. It also described four of the six most recent published closings as
"the single most common failure mode in this segment".

They were not failures. They are the house voice. That rule was written from theory
against the standing principle that **published editions outrank rule text**, and it was
steering every draft away from what actually ships. Rewritten 25 Aug 2026.

## The five things Victor consistently ADDS

1. **Counsel, not analysis, at the close.** 6/6. Second person, plain. An edge or
   unresolved note may follow the advice, but the advice must be there.
2. **The emotional and identity beat, and the removal of self-blame.** The most
   consistently missing ingredient. "living rent-free in your head" (3 Aug), "your pride a
   little hurt ... you dodged a bullet" and "it's probably not because you fumbled on your
   words in the interview" (17 Aug), "feeling like a grad all over again ... that loss of
   competence hurts your pride more than the smaller paycheque" (23 Jun).
3. **The operational condition the reader is living in.** Office-attendance mandates
   (13 Jul, restored twice even though the draft's own notes said not to name them), the
   approval chain and background checks (17 Aug), what AI has done to the applicant pool
   (24 Aug), how EAP is funded and capped (10 Aug), "AI thinning out the junior rungs"
   (23 Jun). **Not** research for its own sake: the 17 Aug draft's contract-formation-law
   paragraph was CUT. Macro earns its place only when it changes the reader's next move,
   and pure-culture topics (team lunch, nicknames) ship with no external facts at all.
4. **Naming the community as the evidence, and reading the aggregate as data.** "When we
   put the question to the community, there was a line right down the middle" (24 Aug),
   "Based on what we're seeing" (24 Aug). Sharpest form is the survivorship read: "the
   people it didn't work out for are far less likely to be the ones telling you about it"
   (23 Jun) - present in published text, absent from all six drafts.
5. **One release valve per piece** - a joke or an ordinary idiom. "gives you the ick",
   "throw the cat amongst the pigeons" (3 Aug), "dodged a bullet" (17 Aug), "most learn
   pretty quick their parents aren't saving lives" (13 Jul). Zero equivalents in any draft.

Runner-up: **both-sidesing.** Drafts pick a villain; Victor adds the concession that stops
the piece reading as employer-bashing, then addresses the other half of the readership
("Both of those are true at the same time.", 13 Jul).

## Sourcing split (published pieces)

| Piece | From submissions | From outside |
|---|---|---|
| Kids in the office (13 Jul) | ~50% | ~50% |
| Team lunch (20 Jul) | ~85% | ~15% (no external facts) |
| Boss calls you 'babe' (3 Aug) | ~90% | ~10% (no external facts) |
| To tell or not to tell (10 Aug) | ~50% | ~50% |
| Verbal offers (17 Aug) | ~45% | ~55% |
| Cover letter (24 Aug) | ~75% | ~25% |

The more procedural the topic, the more outside knowledge goes in. Pure-culture topics get
their depth from the emotional beat and the release valve instead.

## The cardinal rule was also wrong

`voice-guide.md` said the piece "never refers to the screenshots, the responses, or the
people who sent them". Published editions name the community as the evidence base
regularly. Narrowed 25 Aug 2026: the AGGREGATE community is nameable and wanted; an
INDIVIDUAL submission is still never retold or named.

## Where this is enforced

- GENERATE (the copy that actually ships): the skill's
  `references/generate-prompt.md` - new "WHAT THE PIECE MUST CARRY" section and a
  rewritten CLOSING section.
- `references/voice-guide.md` - narrowed cardinal rule, amended "no tidy lesson" rule.
- FW fallback prompt: `BIG_CONVERSATION_DRAFT_SYSTEM` in `flatwhite/classify/prompts.py` -
  mirrored SUBSTANCE section.
- Pinned by `tests/test_big_conversation_substance.py`, including a test asserting the
  published closing is no longer banned.

## Standing risk

The generate prompt exists in TWO copies - the skill's (which ships) and FW's (a fallback
the frontend never calls). They have already drifted once. Same failure as the Off the
Clock prompt that had two hand-maintained copies. Either collapse them to one source or
keep changing both together.
