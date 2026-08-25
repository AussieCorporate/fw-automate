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

Built 17 Aug 2026. Wired 25 Aug 2026:
    - Big Conversation drafting (big_conversation.draft_big_conversation and
      the dashboard's _proceed_big_conversation) runs the full chain.
    - The skill-run path runs the strip via dashboard/strip_stage.py plus a
      mechanical length check with one automatic re-cut.
"""

from __future__ import annotations

import re
from typing import Callable

from flatwhite.model_router import route

# ─── LENGTH: mechanical, not a promise ─────────────────────────────────────
# Added 18 Aug 2026 on Victor's binding instruction: length is a first-class
# requirement, checked by plain code between stages, not left to a model's
# self-report. Numbers are the real published measurements from
# docs/voice-refresh-findings.md - do not loosen them from theory.

LENGTH_SPECS = {
    "big_conversation": {
        "word_target_min": 280,
        "word_target_max": 340,
        "word_hard_ceiling": 365,  # the observed maximum across the last 6 published pieces
        "paragraph_target_min": 4,
        "paragraph_target_max": 4,  # 5 only when the material genuinely needs it
        "paragraph_hard_ceiling": 5,  # 6 has never shipped
    },
    "brains_trust": {
        "word_target_min": 240,
        "word_target_max": 280,  # reality clusters at 225-262; 320 is headroom, not an aim
        "word_hard_ceiling": 340,  # Victor's own pinned ceiling, 27 Jul edit - unchanged
        "paragraph_target_min": 3,
        "paragraph_target_max": 4,
        "paragraph_hard_ceiling": 5,
    },
}


# The segment header a piece file opens with, and the bold declarative headline
# that follows it. Neither is body prose: the header is a label and the headline
# is furniture the published editions set apart from the paragraphs. Counting
# them inflated the Payrise Excuses piece to 6 paragraphs against a ceiling of
# 5 when it is really 4, and reported 347 words when the piece is 339 (caught
# 25 Aug 2026 - the piece was correct and the checker was wrong).
_SEGMENT_HEADER = re.compile(r"^\**\s*THE BIG CONVERSATION\s*\**$", re.IGNORECASE)
_BOLD_ONLY_LINE = re.compile(r"^\*\*[^*].*[^*]\*\*$")


def _strip_non_prose(text: str) -> str:
    """Drops chart placeholders, and - only in a piece FILE that opens with the
    segment header - that header and the headline line beneath it.

    The headline is only ever dropped when the header proves this is a piece
    file. A bare draft (the shape the API's own generator returns, which has no
    title by instruction) is left completely alone, so its first paragraph can
    never be mistaken for a headline and silently uncounted.
    """
    lines = [l for l in text.splitlines() if not l.strip().startswith("[CHART")]

    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first is None or not _SEGMENT_HEADER.match(lines[first].strip()):
        return "\n".join(lines)

    second = next((i for i in range(first + 1, len(lines)) if lines[i].strip()), None)
    drop = {first}
    if second is not None:
        # The headline sits alone between the header and the first paragraph.
        followed_by_blank = (second + 1 >= len(lines)) or not lines[second + 1].strip()
        if followed_by_blank:
            drop.add(second)
    return "\n".join(l for i, l in enumerate(lines) if i not in drop)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", _strip_non_prose(text)))


def _paragraph_count(text: str) -> int:
    """Heuristic: blank-line-separated blocks, excluding chart placeholders
    and lone pull-quote attribution lines ("- Jarden") which are not prose
    paragraphs. Good enough for a length check, not a publishing parser."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", _strip_non_prose(text)) if b.strip()]
    count = 0
    for b in blocks:
        lines = b.splitlines()
        if len(lines) == 1 and re.match(r"^-\s*\S+", lines[0].strip()):
            continue
        count += 1
    return count


def check_length(text: str, segment: str) -> dict:
    """Plain-code word/paragraph count against LENGTH_SPECS - never a model
    judgement. Returns counts plus whether the text is inside the target
    band and whether it has breached a hard ceiling."""
    if segment not in LENGTH_SPECS:
        raise ValueError(f"Unknown segment: {segment!r}. Must be one of: {', '.join(LENGTH_SPECS)}.")
    spec = LENGTH_SPECS[segment]
    words = _word_count(text)
    paras = _paragraph_count(text)
    return {
        "word_count": words,
        "paragraph_count": paras,
        "within_word_target": spec["word_target_min"] <= words <= spec["word_target_max"],
        "over_word_hard_ceiling": words > spec["word_hard_ceiling"],
        "over_paragraph_hard_ceiling": paras > spec["paragraph_hard_ceiling"],
    }

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
    "1. LENGTH: cut toward the MIDDLE of the target word band given below, "
    "not the top of it. Stage 3 (which runs after you) deletes more text, "
    "so landing at the ceiling here means the piece finishes short of the "
    "band instead of inside it. Cut whole sentences and paragraphs before "
    "you trim words from inside a sentence you are keeping.\n"
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
    "sentence become the new opener - if that sentence already sits later "
    "in the draft (for example a Brains Trust draft that opened on a setup "
    "fact when the real consequence is a paragraph later), promote it to "
    "the opening position and demote the setup material to a later beat "
    "rather than deleting it, if it is still needed as context.\n"
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
    "Words: 280-340 is the target band - cut toward the MIDDLE (around "
    "310), not the top, because stage 3 shortens it further after you. 365 "
    "is the hard ceiling observed across the last 6 published pieces, not "
    "something to write toward. If the draft is already under 280, that is "
    "fine - do not pad it.\n"
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
    "Words: 240-280 is the target band - cut toward the MIDDLE (around "
    "260), not the top, because stage 3 shortens it further after you. "
    "Recent published editions land at 225-262 in practice. 320 is "
    "headroom, not an aim; 340 is Victor's own pinned hard ceiling from his "
    "27 Jul 2026 edit and should almost never be needed.\n"
    "Opening: sentence one states a number or event flat, not a conceptual "
    "or paradox frame. It must be the CONSEQUENCE (jobs, pay, prices, "
    "mortgages), not the setup (market size, a hardware or investment "
    "cycle, spend forecasts) - this is Victor's own 27 Jul 2026 edit and "
    "the most load-bearing rule in this segment. If P1 opens on a setup "
    "fact and the consequence finding already exists a paragraph or two "
    "later in the draft, promote that consequence sentence to be the new "
    "opener instead; demote the setup fact to a later beat, do not delete "
    "it outright if it is still needed as context.\n"
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
# Deletion is still the preferred fix: a shorter sentence is usually the right
# answer, and an AI asked to rewrite a flagged line tends to swap one
# engineered pattern for another.
#
# Victor amended the old delete-only rule on 17 Aug 2026. The rule was written
# against Claude rewriting its own tell, which is a genuinely bad idea. This
# stage runs on GPT-5.4, a different model family with different habits, and a
# cross-family rewrite is not the same risk. So rewriting is now allowed where
# deleting would break the sentence - under the guardrails in the system
# prompt below, and with every change listed so Victor can judge whether the
# rewrites beat the cuts.

STRIP_CLAUDE_PHRASING_SYSTEM = (
    "You are doing ONE job: deleting AI-essay tells from a Flat White "
    "newsletter draft that has already been shaped to the right length and "
    "structure. You are not editing for quality, not improving prose, not "
    "adding anything. You are cutting scaffolding and closing up the gap.\n"
    "\n"
    "THE FIRST RULE: PREFER DELETION. Subtraction is the fix that works - "
    "delete the scaffolding, break the symmetry, end earlier. A shorter, "
    "rougher sentence is almost always better than a smoother replacement. "
    "Only touch a sentence if it matches an entry in the catalogue below - "
    "do not go hunting for prose you merely think could be better.\n"
    "\n"
    "REWRITE IS ALLOWED, SECOND: where deleting the tell would break the "
    "sentence or lose a load-bearing fact, rewrite it instead of leaving it "
    "in. Three guardrails bind every rewrite:\n"
    "- NO NEW FACT, name, number, quote, source or example. You may only "
    "re-say what the draft already says.\n"
    "- NO NEW FIGURE OF SPEECH. No fresh antithesis, no balanced pair, no "
    "aphorism, no em dash, no punchy closer. Replacing one engineered "
    "pattern with a cleverer one is the failure this stage exists to catch. "
    "The ONE exception: a common spoken idiom (the phrase everyone already "
    "says - 'take it back', 'dodged a bullet', 'red flag') is ALLOWED as a "
    "replacement, and for catalogue entry 25 it is the required fix. The "
    "ordinary idiom is the house voice; only FRESH phrasing is banned.\n"
    "- PLAIN ANGLO words in the plainest order that carries the meaning. If "
    "your rewrite is more elegant than the sentence it replaces, it is "
    "wrong - make it plainer.\n"
    "When both would work, delete. Rewriting is the fallback, not the "
    "default.\n"
    "\n"
    "ALLOWED MINIMAL REPAIRS (routine tidying, never counted as a rewrite):\n"
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
    "Beyond those repairs and the guardrailed rewrite above, change nothing. "
    "Never add a fact, a quote, a name, an example, or an image that was not "
    "already in the draft.\n"
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
    "THE STOCK PHRASE LIST IS EXEMPT FROM THAT CAUTION. The stock phrase "
    "entry in the catalogue below is off-the-shelf AI filler and is never "
    "Victor's own writing, so it is never his hand-edit and never load "
    "bearing. Fix every stock phrase on sight - delete it, or rewrite the "
    "clause around it under the guardrails - and never hold one back to "
    "flag it for him. The caution applies only to the structural patterns.\n"
    "\n"
    "OUTPUT FORMAT: first the stripped body text, then a line containing "
    "only '---CHANGES---', then a plain bullet list of every change you "
    "made. Start each bullet with 'Deleted' or 'Rewrote', quote the phrase "
    "you acted on (and for a rewrite, quote what it became), and name which "
    "catalogue entry it matched. Then if you flagged anything per the "
    "caution above, a line "
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

11. READER-VALIDATION REACH-THROUGH - empty flattery or comfort that carries no information: telling the reader they are not crazy, not alone, doing fine, that their feelings are valid.
    NARROWED HARD, 25 Aug 2026. This entry was wrong and was about to undo the whole substance fix. It used to read "comforting the reader directly, opening OR closing" and cited the 27 Jul line "It's why a rejection for your job app isn't rigged against you and not because you 'aren't good enough'" as a tell. That line is not a tell - it is REMOVAL OF SELF-BLAME, one of the five things Victor consistently ADDS in his own edit (17 Aug: "it's probably not because you fumbled on your words in the interview"). As written, this entry would have deleted the closing counsel that 6 of 6 published Big Conversations end on: "having support outside of work is the part you can actually count on" (10 Aug), "it's also okay to let this one go" (3 Aug), "it's just up to you to prioritise accordingly" (20 Jul).
    KEEP (never delete these): practical counsel at the close, permission not to act, and removal of self-blame that names a real cause ("not because you fumbled the interview" - the cause is the approval chain, which the piece explained).
    Deletion rule: delete ONLY comfort that asserts nothing and advises nothing - "you're not imagining it", "you're not alone in this", "and that's completely valid", "give yourself credit". If the sentence tells the reader what to do, gives them permission not to act, or takes the blame off them by naming what actually caused it, it stays. When in doubt on this entry, KEEP - the cost of deleting a published-shape close is far higher than leaving one soft line in.

12. THE PRIVILEGE-CHECK / EMPATHY PIVOT - a reflexive paragraph acknowledging the advice doesn't apply to people without options.
    Real example: "leverage is a circumstance, not a mindset."
    Deletion rule: cut the whole aside unless it changes what the reader should actually do; if kept elsewhere in the piece it must already be one plain sentence, not an eloquent set piece - if it is a set piece, delete down to one plain clause.

13. ARCHETYPE CATALOGUING - sorting people into three or more tidy hypothetical buckets.
    Real example: "the ones who bounce back... the ones who quietly regret it... then there's the group that complicates the whole framing."
    Deletion rule: delete the third (or later) bucket entirely; keep at most two.

14. ANNOUNCED TRANSITIONS - a sentence whose ONLY job is to announce the paragraph join.
    Real example: "Then there's the group that complicates the whole framing." (also "Then there's everyone who didn't choose it.")
    Deletion rule: delete the announcing sentence; the paragraph now opens directly with the information that followed it.
    NARROWED 25 Aug 2026 - this entry was over-firing. On the Cover Letters piece it deleted "The problem is what AI has done to the rest.", and Victor put a blunter version straight back in: "The real problem is AI." That sentence NAMES THE SUBJECT of the paragraph and carries a claim, so it is content, not scaffolding.
    The test: strip the sentence of its connective opener and ask whether anything is left being asserted. "Then there's the group that complicates the whole framing" asserts nothing about the world - it only tells the reader a paragraph is starting, so it goes. "The problem is what AI has done to the rest" asserts that AI is the problem, so it stays. When a sentence both announces AND asserts, keep the assertion and cut the announcing words in front of it ("Then there's the fact that X" -> "X").

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

22. END-PLACED READER REASSURANCE (Brains Trust ONLY - Big Conversation closes on counsel, see entry 11) - a closing sentence that comforts the reader INSTEAD OF landing the economic mechanism.
    NARROWED 25 Aug 2026: this used to read "comforts or advises", which contradicted BRAINS_TRUST_VOICE's own closing rule - that prompt sanctions closing on "the economic mechanism ... or the concrete practical implication that follows from them". A practical implication that FOLLOWS FROM the figures is the sanctioned close and stays.
    Deletion rule: delete comfort that REPLACES the explanation ("so there's no need to panic", "things will settle"). Keep a practical implication the figures actually support. If an earlier sentence in the same paragraph already explains the mechanism and the final one only soothes, end there instead.

23. STOCK PHRASES - off-the-shelf AI filler at the word and phrase level. Entries 1-22 are structural shapes; this entry is the vocabulary. NEVER Victor's own writing, so it is EXEMPT from the hand-edit caution: fix every instance on sight, never flag one instead of fixing it.
    Deletion rule: delete the phrase and close the gap. The sentence almost always reads correctly starting from the word after it - capitalise the new opening word and drop a now-orphaned conjunction. Only if deleting genuinely breaks the sentence, rewrite the clause in plain Anglo under the three guardrails. Never swap one stock phrase for another (do not turn "at the end of the day" into "ultimately").
    Real example (caught live on GPT-5.4, 17 Aug 2026): "It's not just about the tracking. In today's fast-paced corporate world, Teams and Slack monitoring has become increasingly common. At the end of the day, workers deserve to know. But here's the thing: employers have legitimate reasons too." -> "Teams and Slack monitoring has become increasingly common. Workers deserve to know. Employers have legitimate reasons too."

    OPENERS AND THROAT-CLEARING: "in today's fast-paced [world/environment/landscape]", "in an era where", "in the realm of", "when it comes to", "now more than ever", "more than ever before", "it goes without saying", "needless to say", "let's be clear", "let's be honest", "make no mistake", "the truth is", "the reality is", "here's the thing", "the thing is", "at the end of the day", "when all is said and done", "time and time again", "few things are as", "there's no denying".

    TRANSITIONS AND HEDGES: "moreover", "furthermore", "additionally", "that said", "that being said", "ultimately", "crucially", "notably", "importantly", "arguably", "it's worth noting", "it's important to note", "it's important to remember", "one might argue", "in essence", "in short", "simply put", "put simply".

    PSEUDO-ANALYTIC VERBS: "delve into", "dive into", "deep dive", "unpack", "explore the nuances", "navigate the landscape", "navigate the complexities", "underscores", "highlights the need for", "sheds light on", "serves as a reminder", "serves as a testament", "stands as a testament", "a testament to", "speaks volumes", "plays a crucial role", "plays a pivotal role", "plays a vital role", "raises important questions", "begs the question".

    ABSTRACTION NOUNS AND CORPORATE GLOSS: "landscape" (figurative), "ecosystem" (figurative), "tapestry", "myriad", "plethora", "realm", "journey" (figurative), "paradigm shift", "game-changer", "key takeaway", "actionable insights", "best-in-class", "seamless", "robust", "leverage" (verb), "foster", "boasts", "a stark reminder", "the elephant in the room", "a perfect storm".
    (Removed from this list 24 Aug 2026: "a double-edged sword" - Victor's own 10 Aug intro uses it. Spoken idiom is house voice; this list is essay filler only.)

24. MIC-DROP PARAGRAPH CLOSERS - a paragraph ending on a quotable reversal or wry compressed line. The single biggest draft-vs-published gap found 24 Aug 2026 (docs/big-conversation-published-spec.md): every drafted paragraph ended on one, no published paragraph does.
    Real examples (all from real drafts, none survived to print): "That's a favour rather than a policy, and it leaves when they do." / "It's a humiliating amount of admin for something an adult already said yes to." / "...this is the best behaviour they're capable of." / "The mistakes are the only part guaranteed a close read."
    Published endings for contrast: "None of it is personal." / "Sometimes the team simply needs another person." / "Both of those are true at the same time."
    Deletion rule: ONE such closer is allowed per piece - keep the best one (prefer the piece's final line). For every other occurrence, delete the closer and end the paragraph on the preceding plain sentence; if the fact in the closer is load-bearing, rewrite it as a plain statement of that fact under the guardrails.

25. CLEVER COINAGE WHERE AN IDIOM EXISTS - a freshly coined phrase or compression doing the job of an expression people actually say.
    Real example (Victor's own edit, 10 Aug): draft "You just can't untell them." shipped as "you can't take it back." Other draft examples that never shipped: "which manager you drew", "quietly reclassed as annual leave", "priced as something you pay for".
    Deletion rule: replace the coinage with the common idiom or plain phrase for the same fact. This is the ONE case where the replacement being an idiom (even a cliche) is correct - the ordinary phrase IS the house voice. Never replace it with a different fresh phrase.

26. WRY-UNDERSTATEMENT TICS - the "more often than it should / than you'd think / than anyone admits" family, "has a way of [verb]ing", and "quietly [verb]" as an atmosphere word ("quietly regret", "go quietly boring").
    Real examples (two drafts, same tic): "works more often than it should" / "beats the direct version more often than it should".
    Deletion rule: delete the tic clause; state the plain claim ("works", "beats the direct version") or, where frequency genuinely matters, say it flat ("usually works"). For "quietly", delete the word - the verb survives alone.
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


RECUT_PROMPT = (
    "This draft is {words_over} words over the {ceiling}-word hard ceiling "
    "for {segment_label} (it is currently {word_count} words).\n"
    "\n"
    "Cut approximately {words_over} words by deleting whole sentences or a "
    "whole paragraph. Do not compress by rewriting - do not shorten "
    "sentences by rephrasing them, only by removing them whole. Do not add "
    "anything.\n"
    "\n"
    "DRAFT:\n"
    "{draft}\n"
    "\n"
    "Output ONLY the cut body text."
)


def _recut_over_ceiling(draft: str, segment: str, word_count: int, *,
                         model_override: str | None = None) -> str:
    """One automatic re-cut pass when stage 2 lands over the hard ceiling.
    Called at most once per chain run - see run_voice_chain(). If the draft
    is still over the ceiling after this, the chain reports it rather than
    calling this again."""
    spec = LENGTH_SPECS[segment]
    segment_label = "THE BIG CONVERSATION" if segment == "big_conversation" else "THE BRAINS TRUST"
    prompt = RECUT_PROMPT.format(
        words_over=word_count - spec["word_hard_ceiling"],
        ceiling=spec["word_hard_ceiling"],
        word_count=word_count,
        segment_label=segment_label,
        draft=draft,
    )
    result = route(
        task_type="voice_shape",
        prompt=prompt,
        system=SHAPE_TO_PUBLISHED_SYSTEM,
        model_override=model_override,
    )
    return result.strip()


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


def _describe_strip_failure(exc: Exception) -> str:
    """Plain-English message for when the strip stage can't run. NEVER
    triggers a fallback to a Claude model - the whole point of this stage
    is that a Claude model cannot reliably hear its own tells, so a
    Claude-stripped piece is exactly the failure mode this exists to avoid.
    """
    msg = str(exc)
    if "No API key configured" in msg and "OPENAI_API_KEY" in msg:
        return (
            "The strip stage needs an OpenAI key (OPENAI_API_KEY) and none is "
            "configured. This stage runs on GPT-5.4 by design - a Claude model "
            "cannot reliably hear its own tells, so it never silently falls back "
            "to one. Add OPENAI_API_KEY to the .env and re-run. The piece below "
            "is exactly what stage 2 produced, unstripped - it has NOT been "
            "checked for Claude tells."
        )
    return (
        f"The strip stage failed ({msg}) and was not retried on a different "
        "model - a Claude model is never substituted for this check by design. "
        "The piece below is exactly what stage 2 produced, unstripped - it has "
        "NOT been checked for Claude tells."
    )


# ─── THE CHAIN ──────────────────────────────────────────────────────────────

def run_voice_chain(segment: str, generate_fn: Callable[[], str], *,
                     shape_model_override: str | None = None,
                     strip_model_override: str | None = None) -> dict:
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
        shape_model_override: optional model id for stage 2 only.
        strip_model_override: optional model id for stage 3 only. Deliberately
            a SEPARATE parameter from shape_model_override (never one shared
            override for both) - stage 3 defaults to GPT-5.4
            (model_router.DEFAULT_MODEL_BY_TASK["voice_strip"]) and must
            never be silently pulled onto a Claude model by a caller that
            only meant to override stage 2.

    Length is checked mechanically (plain code, LENGTH_SPECS above) between
    every stage, never left to a model's self-report. If stage 2 lands over
    the hard ceiling, ONE automatic re-cut pass runs; after that the chain
    reports the overage in "length_warnings" rather than looping again.

    If the strip stage (GPT-5.4) can't run for any reason - most likely no
    OPENAI_API_KEY configured - the chain does NOT fall back to a Claude
    model and does NOT crash. It stops the pipeline at stage 2, returns that
    output as "stage3_stripped" (unstripped, "stage3_status": "not_stripped"),
    and puts a plain-English explanation in "stage3_error".

    Returns a dict Victor can inspect stage by stage:
        {
            "segment": str,
            "stage1_generate": str,     # raw stage-1 draft
            "stage2_shaped": str,       # cut/tightened to real shape
            "stage3_stripped": str,     # tells deleted, body text only (or
                                         # stage 2's output, unchanged, if
                                         # stage3_status == "not_stripped")
            "stage3_status": str,       # "stripped" or "not_stripped"
            "stage3_error": str | None, # plain-English reason if not stripped
            "stage3_changes": str,      # what stage 3 deleted, as a list
            "stage3_flagged": str,      # anything left in for Victor's veto
            "word_counts": {"stage1": int, "stage2": int, "stage3": int},
            "paragraph_counts": {"stage1": int, "stage2": int, "stage3": int},
            "length_warnings": list[str],  # empty if everything landed inside spec
        }
    """
    warnings: list[str] = []

    stage1 = generate_fn()
    counts1 = check_length(stage1, segment)

    stage2 = shape_to_published(stage1, segment, model_override=shape_model_override)
    counts2 = check_length(stage2, segment)

    if counts2["over_word_hard_ceiling"]:
        stage2 = _recut_over_ceiling(stage2, segment, counts2["word_count"], model_override=shape_model_override)
        counts2 = check_length(stage2, segment)
        if counts2["over_word_hard_ceiling"]:
            ceiling = LENGTH_SPECS[segment]["word_hard_ceiling"]
            warnings.append(
                f"Stage 2 is still {counts2['word_count']} words after one automatic "
                f"re-cut pass, over the {ceiling}-word hard ceiling. Cut it by hand "
                "before shipping - the chain does not re-cut a second time."
            )

    stage3_status = "stripped"
    stage3_error: str | None = None
    try:
        stage3_raw = strip_claude_phrasing(stage2, model_override=strip_model_override)
        stage3_parts = split_strip_output(stage3_raw)
    except Exception as exc:  # noqa: BLE001 - any failure here must STOP and report, never fall back
        stage3_status = "not_stripped"
        stage3_error = _describe_strip_failure(exc)
        stage3_parts = {"body": stage2, "changes": "", "flagged": ""}

    counts3 = check_length(stage3_parts["body"], segment)
    stripped_note = "" if stage3_status == "stripped" else " (this piece was never stripped, see stage3_error)"

    if counts3["over_word_hard_ceiling"]:
        ceiling = LENGTH_SPECS[segment]["word_hard_ceiling"]
        warnings.append(
            f"Final piece is {counts3['word_count']} words, over the {ceiling}-word "
            f"hard ceiling{stripped_note}. Do not ship this silently."
        )
    if counts3["over_paragraph_hard_ceiling"]:
        ceiling = LENGTH_SPECS[segment]["paragraph_hard_ceiling"]
        warnings.append(
            f"Final piece has {counts3['paragraph_count']} paragraphs, over the "
            f"{ceiling}-paragraph ceiling{stripped_note}."
        )

    return {
        "segment": segment,
        "stage1_generate": stage1,
        "stage2_shaped": stage2,
        "stage3_stripped": stage3_parts["body"],
        "stage3_status": stage3_status,
        "stage3_error": stage3_error,
        "stage3_changes": stage3_parts["changes"],
        "stage3_flagged": stage3_parts["flagged"],
        "word_counts": {
            "stage1": counts1["word_count"],
            "stage2": counts2["word_count"],
            "stage3": counts3["word_count"],
        },
        "paragraph_counts": {
            "stage1": counts1["paragraph_count"],
            "stage2": counts2["paragraph_count"],
            "stage3": counts3["paragraph_count"],
        },
        "length_warnings": warnings,
    }
