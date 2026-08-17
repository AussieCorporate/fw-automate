"""Voice pipeline: GENERATE -> SHAPE TO PUBLISHED -> STRIP THE CLAUDE PHRASING.

Three stages, run in order, each stage's output kept (never overwritten) so
Victor can see what stage 1 produced, what stage 2 cut/tightened, and what
stage 3 deleted before anything reaches him. This module holds stages 2 and 3
only. Stage 1 (GENERATE) is segment-specific and already lives where each
segment's generation already happens:
    - Big Conversation: flatwhite/classify/big_conversation.py
      (draft_big_conversation), or the interactive big-conversation Claude
      Code skill for the screenshot-sourced workflow.
    - Brains Trust: flatwhite/dashboard/api.py _proceed_brains_trust, using
      BRAINS_TRUST_VOICE from flatwhite/classify/prompts.py.

Why stages 2 and 3 live HERE, shared, rather than duplicated per segment or
copy-pasted into the big-conversation skill: they are the same job for both
segments (cut to the real shipped shape; delete AI tells) and duplicating
prompt text into two codebases is exactly the kind of drift this refresh was
built to fix. The big-conversation skill's SKILL.md points here instead of
carrying its own copy - see the note added to that skill's step 4.

Evidence source for every number and forbidden pattern below:
docs/voice-refresh-findings.md (17 Aug 2026, 6 published editions, 6 Jul -
10 Aug 2026, pulled live from beehiiv). Published editions outrank rule text.

Built 17 Aug 2026. Not yet wired into the dashboard - see
docs/voice-prompts-refresh-report.md for exactly where the runner must call
this once the dashboard's skill-run path (currently being repaired for a
separate bug) is fixed.
"""

from __future__ import annotations

from typing import Callable

from flatwhite.model_router import route

# ─── Real published exemplars (verbatim) ──────────────────────────────────
# Sourced from published-examples.md / brains-trust-current-format.md / the
# 17 Aug findings doc. These are pasted into the SHAPE prompt so the model
# calibrates against real text, not a description of real text.

BIG_CONVERSATION_EXEMPLARS = '''\
EXEMPLAR 1 - "A shared room is not a saving." (published 6 Jul 2026, 4 paragraphs, ~330 words)

Forcing colleagues to share a hotel room at a conference is far more common than most people realise. Banks, law firms, the big consulting shops, telcos and plenty of large companies do it, and a lot of them still do. The flights, the venue and the catering are more or less fixed, so the accommodation becomes the one number someone can halve by putting two adults in the one room. It's highly unlikely you're bunking together as a team bonding exercise.

A two-bedroom apartment with your own bathroom and a shared lounge is fine and same-gender pairing usually takes the edge off. Done the right way, people come home with a good story. A blanket "you're sharing" rule might be saving the business money but you're likely going to end up with more trouble. Almost always, the partners, the people-leaders and the executives who signed off on the travel budget almost always keep their own room.

A work conference tends to end with everyone a few drinks deep, and a shared-room policy just puts two people who barely know each other in a room with two beds and one door. One workers' comp claim, one harassment complaint, one phone left recording on a shelf, and the few hundred dollars saved is gone many times over, along with a chunk of someone's year. A second hotel room is probably cheaper in those circumstances.

The good news is that "required to attend" and "required to share" are not the same thing. You can say yes to the conference and ask for a single room for personal reasons. You'll usually get it because the general assumption is that most people won't ask. And that only works if the rooms fill up without anyone complaining.

EXEMPLAR 2 - "Three weeks was never a chance to improve." (published 30 Jun 2026, 4 paragraphs. Victor's own hand-rewrite of an AI draft - the single best calibration sample for what he keeps and what he cuts.)

Most performance plans run somewhere between 6 weeks and 3 months. There's a reason for that. You get given your target, and the whole process is like a second chance that assumes you're not capable of changing how you work in that time frame. A lot of these plans have stopped being about getting you back on track and started being about building a paper trail. Companies don't usually go to that effort for someone they're trying to keep.

For many, a performance incentive plan (PIP) is the opening move in a negotiation rather than a test. The company would rather you take a quiet exit with pay than drag everyone through the process and risk it getting messy. Once you see it that way, the PIP becomes leverage. The people who realise this early tend to walk away with a settlement and their reputation intact, while the ones who pour themselves into hitting impossible targets get the same outcome with none of the upside.

It's also worth being honest about what surviving one actually buys you. Overcoming a PIP just means you're now being watched and you've only just cleared the bar for a job you were already supposed to be doing. Plenty of people grind through, keep the job, and realise a few months later they've simply earned a worse version of the role they already had, with a manager that's mentally filed you as a risk.

None of which means your manager is the villain. A lot of managers get handed the framework by HR with the outcome already decided and they aren't allowed to tell you the truth. Don't blame them for being vague with their reasons, they're usually someone boxed in by Legal and trying to do what they can. But if you're ever stuck and wanting to fight through your PIP, get a straight answer on what success is meant to look like. A plan written in good faith holds up fine. Just make sure you've read the room.

OPENING PATTERN across the 6 most recent editions - 5 of 6 state the situation or mechanism directly in sentence one, no throat-clearing, no question:
"Turning down a team lunch shouldn't be a career decision, but plenty of people check themselves before they do it." (20 Jul)
"School holidays run about twelve weeks a year." (13 Jul)
"If you're dealing with a mental health issue at work, your own GP or psychologist is often more valuable than any program offered by your employer." (10 Aug)

CLOSING PATTERN - only 2 of the 6 most recent editions land the prescribed sharp, unresolved turn. These two DID land it - match these, not the softer ones:
"The fallout just reappears as tanking productivity, resentful exhausted parents, and a fractured workplace culture." (13 Jul)
"And that only works if the rooms fill up without anyone complaining." (6 Jul)
These four SOFTENED into reader-directed resolution or reassurance instead - this is the exact failure mode to cut when it appears in a stage-1 draft:
"Every team is different and workplace culture even more so, so it's just up to you to prioritise accordingly." (20 Jul - "up to you" resolution)
"You can't guarantee you'll get that though, so having support outside of work is the part you can actually count on." (10 Aug - reader reassurance)
"It's why a rejection for your job app isn't rigged against you and not because you 'aren't good enough'." (27 Jul - reader reassurance, also shipped with an uncorrected grammatical stumble)
"In the end, your experience at work often comes down to your manager more than the company itself." (10 Aug, final paragraph opener - the announced wrap-up "In the end," tell)
'''

BRAINS_TRUST_EXEMPLARS = '''\
EXEMPLAR - "Bunking with a colleague" edition Brains Trust (published 6 Jul 2026, 5 paragraphs, ~290 words, 3 charts)

Staff turnover across the ASX100 fell to a 5-year low of 12.3% in FY25, down from 12.7%. There's less to leave for, so people leave less. Nothing surprising in that.

[CHART - Source: ABS, Macquarie Research, June 2026]

The labour figures line up also. Employment rose 40,000 in May, but the 3-month average has slowed to about 6,000. UBS expects unemployment to drift toward 4.9% over the coming year.

Pay hasn't followed the market downwards though. The Fair Work Commission lifted award wages 4.75% from 1 July, ahead of headline inflation at 4.2% and the 3.3% pace of overall wage growth, covering around 2.8 million workers. Private-sector wages are running at 5.5% year-on-year.

[CHART - Source: Company data, Macquarie Research, June 2026]

The pressure is showing up in household budgets rather than pay packets. Macquarie's consumer team has household income growing 2.3% this year but spending just 1.5%, well short of the 3.5% pre-Covid norm, once higher mortgage repayments and tax come out. Savings rates are climbing as households stay cautious.

[CHART - Source: Company data, Macquarie Research, June 2026]

For companies, the low churn in staff is becoming a tailwind. Macquarie estimates that holding onto staff is worth 4-7% of the wage bill in avoided hiring and retraining. That is also why the job market can look like it points both ways at once. Fewer people are being hired, which normally suggests a soft economy. But fewer are leaving, too, so employers don't have to lift pay to keep the staff they already have.

OPENING PATTERN across the 6 most recent editions - sentence one states a number or event flat:
"Since the May budget changed the rules on negative gearing and capital gains tax, the number of people applying for home loans has fallen 25%." (10 Aug)
"Electric vehicles made up 50% of new car sales in June, up from 27% a year earlier." (13 Jul)

CLOSING PATTERN - only 2 of the 6 most recent editions genuinely land the economic mechanism (the 6 Jul example above is one of them). These closings SOFTENED instead - cut this shape when it shows up in a stage-1 draft:
"The big banks report their results in August, and what they say about how much they're lending will be the clearest sign yet of how bad the slowdown gets. If you own a place, are trying to buy, or have super sitting in the big banks, that's the next thing to keep an eye on." (10 Aug - forward watch-point, no mechanism explained)
"Australia added 76,000 jobs in June, but the underlying pace of hiring has more than halved over the past year, and underemployment is rising while forward indicators like job ads are softening." (27 Jul - stat pile, no "because")

REAL PULL QUOTE (published 3 Aug, correct shape - keep this pattern):
"'This would mean... taxing or banning excessive work; re-distributing more income and wealth, reducing the focus on competition and rivalry; spending more money on public goods such as parks; refocussing on community; limiting advertising to information to avoid creating demand for stuff we don't need; and regulating access to social media.'"
- Shane Oliver - AMP

BROKEN PULL QUOTE (published 20 Jul - the failure mode the rule now bans; the attribution trails off to nothing):
"'UBS previously expected dwelling prices to fall ~3-5% over the coming ~year, but now expect prices to fall over 5% year-on-year.'" -
'''

# ─── STAGE 2: SHAPE TO PUBLISHED ───────────────────────────────────────────

SHAPE_TO_PUBLISHED_SYSTEM = (
    "You are the shaping editor for The Aussie Corporate's Flat White "
    "newsletter. You take a first draft and bring it to the exact shape that "
    "actually ships, using the real published editions below as your "
    "calibration - not a description of the house style, the house style "
    "itself.\n"
    "\n"
    "YOUR ONLY TOOLS ARE CUTTING AND TIGHTENING. You never add a flourish, a "
    "new sentence, a new clause, a new fact, a new figure, or a new quote. "
    "Every word in your output must already exist in the draft you were "
    "given, EXCEPT the small connective words needed to rejoin a sentence "
    "after you delete part of it (capitalising a new sentence start, fixing "
    "a comma into a full stop, and so on). If the draft is missing something "
    "the real shape needs (for example it never lands a turn at all), you "
    "cut toward the closest thing already in the draft that resembles one - "
    "you do not invent a replacement ending.\n"
    "\n"
    "You do not verify facts, invent sources, or add anything that was not "
    "asserted in the draft. If the draft names a stat, bank or company, "
    "leave it exactly as stated - do not correct, round, or embellish it.\n"
    "\n"
    "WHAT TO SHAPE, IN ORDER:\n"
    "1. LENGTH: cut to the real word band for this segment (given below), "
    "not the draft's current length. Cut whole sentences and paragraphs "
    "before you trim words from inside a sentence you are keeping.\n"
    "2. PARAGRAPH COUNT: cut to the real paragraph target. If the draft has "
    "more paragraphs than the real target, the weakest or most repetitive "
    "paragraph is deleted whole, not compressed into a shorter version of "
    "itself.\n"
    "3. OPENING: the first sentence must match the real opening pattern "
    "shown in the exemplars below - state the situation, mechanism, number "
    "or event directly, no throat-clearing, no rhetorical question, no "
    "scene-setting zoom-out. If the draft's opening already does this, "
    "leave it. If it does not, cut the throat-clearing sentence(s) in front "
    "of the real opening line and let the draft's own strongest direct "
    "sentence become the new opener.\n"
    "4. CLOSING: the final paragraph must land the prescribed close for this "
    "segment (given below) - a sharp, slightly unresolved turn, or the "
    "economic mechanism, never a tidy resolved lesson, a forward-looking "
    "stat pile, or reader reassurance. If the draft's actual closing "
    "sentence already does this, keep it. If the draft's closing softens "
    "into resolution or reassurance, and an earlier sentence in that same "
    "final paragraph already lands harder, cut down to that sentence and "
    "end there. Never write a new closing line.\n"
    "\n"
    "Output ONLY the shaped body text. No title, no sign-off, no commentary "
    "about what you changed - the caller logs your output against the input "
    "separately."
)

SHAPE_TO_PUBLISHED_PROMPT = (
    "SEGMENT: {segment_label}\n"
    "\n"
    "REAL SHAPE FOR THIS SEGMENT (evidence: docs/voice-refresh-findings.md, "
    "6 published editions, 6 Jul-10 Aug 2026):\n"
    "{shape_block}\n"
    "\n"
    "REAL PUBLISHED EXEMPLARS - match these, not a description of them:\n"
    "{exemplars}\n"
    "\n"
    "DRAFT TO SHAPE:\n"
    "{draft}\n"
    "\n"
    "Cut and tighten this draft to the real shape above. Follow your system "
    "instructions exactly - cutting and tightening only, nothing added."
)

BIG_CONVERSATION_SHAPE_BLOCK = (
    "Paragraphs: 4 is the real target. A 5th is an occasional stretch only "
    "if the draft has a genuinely distinct 5th angle worth keeping - do not "
    "stretch to 5 just to preserve length. 6 has never shipped; if the draft "
    "has 6, two are being cut, not trimmed.\n"
    "Words: 270-365 total. If the draft is under 265 words, that is fine - "
    "do not pad it. If it is over 365, cut a whole paragraph or sentence, "
    "not a trim across all of them.\n"
    "Opening: P1 states the situation or mechanism plainly in sentence one. "
    "No rhetorical question, no scene-setting zoom-out ('Somewhere between "
    "X and Y...', 'These days...').\n"
    "Closing: the final paragraph ends on a short, slightly unresolved turn "
    "- never 'it's up to you', never direct reassurance to the reader, "
    "never a tidy resolved lesson. If the final sentence does this, an "
    "earlier sentence in the same paragraph should become the new ending."
)

BRAINS_TRUST_SHAPE_BLOCK = (
    "Paragraphs: 3-5 short paragraphs. Treat 5 as the ceiling, not the "
    "target.\n"
    "Words: 225-262 is the real working range in practice. 320 is generous "
    "headroom, 340 is a hard ceiling that should almost never be needed. If "
    "the draft is already under 262, do not pad it up toward 320.\n"
    "Opening: sentence one states a number or event flat, not a conceptual "
    "or paradox frame.\n"
    "Closing: the final paragraph lands the economic mechanism - the reason "
    "the figures look contradictory, or the concrete practical implication "
    "that follows from them. Not a bare forward-looking watch-point, not a "
    "stat pile with no 'because' attached, not a values statement.\n"
    "Pull quote: keep it only if the draft already has one AND its "
    "attribution is a complete house name on its own line ('- Jarden'). A "
    "pull quote with a broken or empty attribution gets folded back into "
    "plain prose, or cut, never left broken."
)


def shape_to_published(draft: str, segment: str, *, model_override: str | None = None) -> str:
    """Stage 2. Cuts/tightens `draft` to the real shipped shape for `segment`.

    segment: "big_conversation" or "brains_trust".
    """
    if segment == "big_conversation":
        segment_label = "THE BIG CONVERSATION"
        shape_block = BIG_CONVERSATION_SHAPE_BLOCK
        exemplars = BIG_CONVERSATION_EXEMPLARS
    elif segment == "brains_trust":
        segment_label = "THE BRAINS TRUST (also called THE ECONOMIC SCOOP)"
        shape_block = BRAINS_TRUST_SHAPE_BLOCK
        exemplars = BRAINS_TRUST_EXEMPLARS
    else:
        raise ValueError(f"Unknown segment: {segment!r}. Must be 'big_conversation' or 'brains_trust'.")

    prompt = SHAPE_TO_PUBLISHED_PROMPT.format(
        segment_label=segment_label,
        shape_block=shape_block,
        exemplars=exemplars,
        draft=draft,
    )
    result = route(
        task_type="voice_shape",
        prompt=prompt,
        system=SHAPE_TO_PUBLISHED_SYSTEM,
        model_override=model_override,
    )
    return result.strip()


# ─── STAGE 3: STRIP THE CLAUDE PHRASING ────────────────────────────────────
# Binding rule from Victor: fix a tell by DELETING the scaffolding, never by
# generating a cleverer replacement line - AI rewrites of AI tells reintroduce
# the same patterns. This stage is mechanical and surgical by design.

STRIP_CLAUDE_PHRASING_SYSTEM = (
    "You are doing ONE job: deleting AI-essay tells from a Flat White "
    "newsletter draft that has already been shaped to the right length and "
    "structure. You are not editing for quality, not improving prose, not "
    "adding anything. You are cutting scaffolding and closing up the gap.\n"
    "\n"
    "THE BINDING RULE: fix a tell by DELETING it, never by writing a "
    "cleverer replacement line. Asking an AI to rewrite a flagged sentence "
    "reliably swaps one engineered pattern for another - a fresh em dash, a "
    "fresh antithesis, a fresh imperative punch closer. The only reliable "
    "fix is subtraction: delete the scaffolding, break the symmetry, end "
    "earlier. Only touch a sentence if it matches an entry in the catalogue "
    "below - do not go hunting for prose you merely think could be better.\n"
    "\n"
    "ALLOWED MINIMAL REPAIRS (the only editing beyond straight deletion):\n"
    "- Rejoin a sentence after deleting a clause: capitalise the new "
    "sentence start, turn a now-dangling comma into a full stop, delete a "
    "now-orphaned conjunction ('but', 'though', 'so') at a paragraph start.\n"
    "- Swap ONE flagged corporate/Latinate word for the plain Anglo word "
    "Victor's own edits have already used in its place (see the diction "
    "entry below) - never rewrite the sentence around it.\n"
    "- Convert an em dash used for rhetorical drama into a full stop or "
    "comma, whichever the sentence already reads as without the dash.\n"
    "- Delete a whole sentence and let the sentence before it stand as the "
    "new paragraph ending.\n"
    "Nothing else. Never write a new sentence. Never add a fact, a quote, a "
    "name, an example, or an image that was not already in the draft.\n"
    "\n"
    "THE FULL TELL CATALOGUE (pattern -> deletion rule):\n"
    "{tell_catalogue}\n"
    "\n"
    "A CAUTION YOU MUST OBSERVE: some sentences that resemble a tell may be "
    "Victor's own hand-edited voice, not AI output - he edits before "
    "publishing, and the fake-profound reframe that reached print on 27 Jul "
    "shipped in the very edition style he edits by hand. If a flagged "
    "sentence is plausible as his own phrasing rather than a generation "
    "artefact, and deleting it would lose a load-bearing fact rather than "
    "just scaffolding, leave it in place and flag it in your output instead "
    "of deleting it.\n"
    "\n"
    "OUTPUT FORMAT: first the stripped body text, then a line containing "
    "only '---CHANGES---', then a plain bullet list of every deletion you "
    "made (quote the deleted phrase and name which catalogue entry it "
    "matched), then if you flagged anything per the caution above, a line "
    "'---FLAGGED FOR VICTOR---' followed by those items and why you left "
    "them in. If you made no changes, say so explicitly rather than omitting "
    "the section."
)

# The tell catalogue: voice-guide.md's full list, plus the findings' new
# entries, each with the real example (where one exists) and the deletion
# rule. Kept as a separate constant so it can be reused or extended without
# touching the surrounding instructions.
CLAUDE_TELL_CATALOGUE = '''\
1. FAKE-PROFOUND REFRAME - "X isn't doing A, it's doing B." / "the honest question isn't whether X. It's whether Y."
   Real example (shipped, Brains Trust, 27 Jul): "AI in Australia isn't producing mass layoffs. It's producing slower hiring, and specifically the removal of the entry-level roles..."
   Deletion rule: delete the "isn't A, it's B" framing clause; keep only the direct assertion of B. Rejoin: "AI in Australia is producing slower hiring, and specifically..."

2. PAIRED PARALLEL NEGATIONS - two negations built to mirror each other.
   Real example: "isn't automatically a stitch-up... isn't automatically kinder either."
   Deletion rule: delete the second negation clause entirely; keep the first plain point.

3. ANAPHORA LISTS - three or more sentences/clauses opening the same way.
   Real example: "Ask for... Ask what... Ask for..."
   Deletion rule: delete the repeated openers on the 2nd and 3rd items; merge the content into one flowing sentence with varied verbs.

4. SNAP-CLOSER APHORISM - a neat "X. But Y." mini-reversal ending a piece.
   Real example: "It won't always save the job. But it tells you which one you're in."
   Deletion rule: delete the "But Y" half; end on the plainer first sentence, or if that sentence is also engineered, delete the whole pair and end one sentence earlier.

5. CORPORATE / LATINATE DICTION - "infrastructure", "leverage" (as verb), "invest in", "construct", "ensure the outcome", "facilitate", "robust".
   Real example (Victor's own edit): "PIP infrastructure" -> "go to that effort".
   Deletion rule: swap the flagged word for its established plain-Anglo replacement (leverage->use, robust->solid/strong, facilitate->help/let, "X infrastructure"->delete the word "infrastructure" and keep the concrete noun). Do not rewrite the rest of the sentence.

6. WRITING-CLASS SCAFFOLDING - "sounds [adjective] right up until...", "there's a quiet X to it", "make no mistake", "the uncomfortable truth is".
   Deletion rule: delete the scaffolding phrase whole; the sentence usually reads fine starting from the clause after it.

7. OVER-SIGNPOSTED CONCESSIONS - "So, to be fair, a short timeline isn't automatically..."
   Deletion rule: delete the throat-clearing lead-in ("So, to be fair,"); keep the concession content that follows.

8. EM-DASH DRAMA - three or more em dashes in a paragraph doing rhetorical lifting.
   Deletion rule: convert em dashes to a full stop or comma per the allowed-repair list. Flat White prose uses none at all - convert every one found, not just the excess.

9. THE ZOOM-OUT ENDING - closing a personal/local topic with a sweeping systemic takeaway.
   Real example (banned shape): "...until the information asymmetry is removed structurally..."
   Deletion rule: delete the final sweeping sentence; end on the prior concrete, local line.

10. THE TRIGGER-VS-CAUSE PIVOT - "X was the trigger but it's not really the cause."
    Real example (shipped, Brains Trust, 22 Jun): "The Middle East conflict was the trigger but it's not really the cause."
    Deletion rule: delete the announcing sentence; let the facts that follow it stand on their own without the pivot being named.

11. READER-VALIDATION REACH-THROUGH - comforting the reader directly, opening OR closing.
    Real example (shipped, Big Conversation closing, 27 Jul): "It's why a rejection for your job app isn't rigged against you and not because you 'aren't good enough'."
    Deletion rule: delete the reassurance clause/sentence; end the piece on the prior factual line instead.

12. THE PRIVILEGE-CHECK / EMPATHY PIVOT - a reflexive paragraph acknowledging the advice doesn't apply to people without options.
    Real example: "leverage is a circumstance, not a mindset."
    Deletion rule: cut the whole aside unless it changes what the reader should actually do; if kept elsewhere in the piece it must already be one plain sentence, not an eloquent set piece - if it is a set piece, delete down to one plain clause.

13. ARCHETYPE CATALOGUING - sorting people into three or more tidy hypothetical buckets.
    Real example: "the ones who bounce back... the ones who quietly regret it... then there's the group that complicates the whole framing."
    Deletion rule: delete the third (or later) bucket entirely; keep at most two.

14. ANNOUNCED TRANSITIONS - a sentence whose only job is to announce the paragraph join.
    Real example: "Then there's the group that complicates the whole framing."
    Deletion rule: delete the announcing sentence; the paragraph now opens directly with the information that followed it.

15. THE FULL-CIRCLE CALLBACK - ending by mirroring the opening phrase or image.
    Deletion rule: delete the mirrored final sentence/clause; end on the line before it.

16. THE FORCED SILVER LINING - "Not worse. Just different." / finding growth in every setback.
    Deletion rule: delete the silver-lining sentence; let the negative reading stand as the last line if that's what the draft actually supports.

17. APHORISM-AFTER-COLLOQUIALISM - a messy colloquial phrase immediately translated into a balanced bumper-sticker line.
    Real example: colloquialism followed by "Pushing your luck until it pushes back."
    Deletion rule: delete the translated aphorism; keep the colloquialism that came before it.

18. TEETER-TOTTER SYMMETRY - a sentence balanced perfectly on its hinge, twice or more in one piece.
    Real example: "solved the problem they had and created one they didn't see coming."
    Deletion rule: on the second (or later) occurrence, delete the second, more-polished half of the sentence and let the first half stand shorter and rougher. One such sentence per piece is allowed and left alone.

19. THE SAFE-CONTRARIAN HOOK - an opener engineered to sound edgy-but-corporate-approved, not earned by a specific fact.
    Real example (this one IS earned and should be kept, for contrast): "'No budget' is almost always a deflection" - kept because the next sentence gives the concrete mechanism.
    Deletion rule: if the hook is not followed within the paragraph by a specific fact or observation that earns it, delete the hook sentence and let the piece open on the next sentence instead. If deleting it leaves no viable opening sentence at all, do not invent one - flag it for Victor instead.

20. ANNOUNCED WRAP-UP OPENERS - "In the end, ..." opening the final paragraph.
    Real example (shipped, Big Conversation, 10 Aug): "In the end, your experience at work often comes down to your manager more than the company itself."
    Deletion rule: delete "In the end," and capitalise the next word; the paragraph opens with the actual point instead of announcing that a summary is coming.

21. THE "DONE PROPERLY," / "DONE THE RIGHT WAY," TIC - a concession opener repeating near-verbatim across editions.
    Real examples (both shipped): "Done properly, visiting your parents' place of work can be a good thing." (13 Jul) / "Done the right way, people come home with a good story." (6 Jul)
    Deletion rule: delete the phrase and capitalise the word that follows; the concession content survives without the formula in front of it.

22. END-PLACED READER REASSURANCE (Brains Trust) - a closing sentence that comforts or advises the reader directly instead of landing the economic mechanism.
    Deletion rule: delete the reassurance clause; if an earlier sentence in the same paragraph already explains the mechanism, end there instead.
'''

STRIP_CLAUDE_PHRASING_PROMPT = (
    "DRAFT TO STRIP (already shaped to the right length and structure - do "
    "not change length, paragraph count, or facts, only strip tells):\n"
    "{draft}\n"
    "\n"
    "Find every match to the tell catalogue in your system instructions and "
    "delete it per that entry's deletion rule. Follow the output format "
    "exactly."
)


def strip_claude_phrasing(draft: str, *, model_override: str | None = None) -> str:
    """Stage 3. Deletes catalogued AI tells from `draft`. Shared across both
    segments - the tells and the delete-only rule are identical for both.

    Returns the raw model output, which includes the stripped body text
    followed by a '---CHANGES---' section and (if anything was left in
    deliberately) a '---FLAGGED FOR VICTOR---' section. Callers that need
    just the body text should split on '---CHANGES---' themselves so the
    change log is never silently discarded.
    """
    system = STRIP_CLAUDE_PHRASING_SYSTEM.format(tell_catalogue=CLAUDE_TELL_CATALOGUE)
    prompt = STRIP_CLAUDE_PHRASING_PROMPT.format(draft=draft)
    result = route(
        task_type="voice_strip",
        prompt=prompt,
        system=system,
        model_override=model_override,
    )
    return result.strip()


def split_strip_output(raw: str) -> dict:
    """Splits strip_claude_phrasing()'s raw output into its three parts.

    Returns {"body": str, "changes": str, "flagged": str}. "flagged" is ""
    if the model made no flag-instead-of-delete calls.
    """
    flagged = ""
    rest = raw
    if "---FLAGGED FOR VICTOR---" in rest:
        rest, flagged = rest.split("---FLAGGED FOR VICTOR---", 1)
    body, changes = (rest.split("---CHANGES---", 1) + [""])[:2] if "---CHANGES---" in rest else (rest, "")
    return {"body": body.strip(), "changes": changes.strip(), "flagged": flagged.strip()}


# ─── THE CHAIN ──────────────────────────────────────────────────────────────

def run_voice_chain(segment: str, generate_fn: Callable[[], str], *,
                     model_override: str | None = None) -> dict:
    """Runs GENERATE -> SHAPE TO PUBLISHED -> STRIP THE CLAUDE PHRASING in
    order, keeping every stage's output. Never collapses the three calls
    into one - each stage is a separate, inspectable step.

    Args:
        segment: "big_conversation" or "brains_trust".
        generate_fn: zero-arg callable returning the stage-1 draft text.
            The caller supplies this so stage 1 stays exactly where it
            already lives (draft_big_conversation(), or the
            _proceed_brains_trust() prompt/route() call) rather than being
            duplicated here.
        model_override: optional model id applied to stages 2 and 3.

    Returns a dict Victor can inspect stage by stage:
        {
            "segment": str,
            "stage1_generate": str,     # raw stage-1 draft
            "stage2_shaped": str,       # cut/tightened to real shape
            "stage3_stripped": str,     # tells deleted, body text only
            "stage3_changes": str,      # what stage 3 deleted, as a list
            "stage3_flagged": str,      # anything left in for Victor's veto
        }
    """
    stage1 = generate_fn()
    stage2 = shape_to_published(stage1, segment, model_override=model_override)
    stage3_raw = strip_claude_phrasing(stage2, model_override=model_override)
    stage3_parts = split_strip_output(stage3_raw)
    return {
        "segment": segment,
        "stage1_generate": stage1,
        "stage2_shaped": stage2,
        "stage3_stripped": stage3_parts["body"],
        "stage3_changes": stage3_parts["changes"],
        "stage3_flagged": stage3_parts["flagged"],
    }
