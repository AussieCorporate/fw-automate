# Voice pipeline demo — stages 2 and 3 proven without firing a real generation

Built 17-18 Aug 2026. Victor's instruction was explicit: don't fire the pipeline again yet.
So nothing here calls the FW dashboard, no real screenshots or broker research were used,
and no LLM generation was fired against real data. This document proves the SHAPE TO
PUBLISHED and STRIP THE CLAUDE PHRASING stages work, using deliberately bad fixtures that
I (Claude) wrote and clearly label as test material.

## What actually executed for real, and what is simulated — read this first

**Executed for real (real code, real pytest run, no mocking of the thing being tested):**
- The mechanical word/paragraph counter (`check_length()` in `flatwhite/classify/voice_pipeline.py`) ran on every piece of text below. These are not estimates — they are the actual output of the same function the pipeline uses.
- The model-routing decision: `voice_strip` resolves to `gpt-5.4` / provider `openai`; `voice_shape` stays on `claude-sonnet-4-6` / provider `anthropic`. Proven by `tests/test_voice_pipeline.py::test_voice_strip_resolves_to_gpt_5_4_by_default`.
- The honest-stop path: with no `OPENAI_API_KEY` configured (confirmed — `.env` does not have one), a real, unmocked call to `model_router.route(task_type="voice_strip", ...)` raises, naming `gpt-5.4` and `OPENAI_API_KEY`, and never substitutes a Claude model. Proven by `test_voice_strip_raises_when_openai_key_missing_not_silently_routed_elsewhere`. `run_voice_chain()` catches that failure and returns `stage3_status="not_stripped"` with a plain-English `stage3_error`, never a crash and never a Claude-stripped piece. Proven by `test_run_voice_chain_stops_and_reports_when_strip_stage_unavailable_never_falls_back`.
- Run command and result:
  ```
  .venv/bin/python -m pytest tests/test_voice_pipeline.py -k "gpt_5_4 or openai_key_missing or strip_stage_unavailable" -v
  3 passed in 2.03s
  ```

**Simulated (no LLM API called):**
- Stage 1 (GENERATE) below is not a real generation. It's a fixture I wrote by hand, deliberately stuffed with catalogued tells, clearly labelled as such.
- Stage 2 (SHAPE TO PUBLISHED) below was performed by me, manually applying the exact `SHAPE_TO_PUBLISHED_SYSTEM` / `SHAPE_TO_PUBLISHED_PROMPT` instructions from `voice_pipeline.py` to the fixture, the same way the model that runs this stage in production (Claude, on `voice_shape`) would. This is a faithful stand-in since stage 2 already runs on Claude.
- Stage 3 (STRIP THE CLAUDE PHRASING) below was **also** performed by me, manually applying the `STRIP_CLAUDE_PHRASING_SYSTEM` / `CLAUDE_TELL_CATALOGUE` instructions. **This is explicitly NOT what the real pipeline does.** The real stage 3 runs on GPT-5.4, on purpose, because a Claude model checking its own tells is exactly the blind spot this stage exists to remove. Since GPT-5.4 requires `OPENAI_API_KEY` (not yet configured) and Victor said not to fire the pipeline, I cannot produce a genuine GPT-5.4 pass. What follows shows the delete-only *mechanics* the STRIP prompt enforces — a rehearsal of the rules, not the real check. **The real stage 3 run is pending Victor adding `OPENAI_API_KEY`.**

## How to read the two worked examples below

Two segments, because stages 2 and 3 are shared and this needs to prove they hold up for
both jobs, not just one. Word/paragraph counts are the real `check_length()` output at
every stage — the number in parentheses is `(words, paragraphs)`.

---

## Example 1 — THE BIG CONVERSATION

### Stage 1: GENERATE (fixture — deliberately bad, clearly labelled)

Topic: after-hours Slack messages. Not a real campaign topic; written to exercise the
pipeline, not to ship. Deliberately 6 paragraphs (over the 5-paragraph hard ceiling) and
stuffed with catalogued tells.

> Have you ever wondered why nobody logs off anymore? In the age of always-on connectivity, the boundary between work and home has quietly dissolved for millions of Australian corporate employees, and it happened so gradually that almost nobody agreed to it out loud.
>
> This isn't really about Slack notifications — it's about who gets to leverage your time after 6pm. Companies have built an entire infrastructure of low-grade urgency, and make no mistake, the after-hours message is rarely as urgent as it's framed to be.
>
> A message at 8pm isn't automatically a crisis, and a message at 8am isn't automatically a courtesy either. Ask yourself who benefits from the ambiguity. Ask yourself what's actually urgent about a calendar invite. Ask yourself whether your manager would accept the same message from you on a Sunday night. So, to be fair, some roles genuinely require after-hours contact - trading desks, deal teams, anything client-facing during a live transaction that can't simply wait until Monday.
>
> The pandemic was the trigger but it's not really the cause. There are the people who reply within minutes out of habit, there are the people who reply late out of guilt, and then there's the group that complicates the whole framing: the ones who've simply stopped noticing the notification at all, and somehow seem happier for it.
>
> If you've ever felt guilty ignoring a message on a Friday night, that instinct is not a personal failing, it's a design choice made somewhere above your pay grade. Of course, leverage is a circumstance and not a mindset, and someone with a mortgage and two kids doesn't have the same freedom to switch off as someone renting alone and unattached. Done properly, this arrangement solves the company's problem while creating one nobody saw coming for the employee on the other end of it.
>
> In the end, not every after-hours message is a red flag. Not worse. Just different. It won't always cost you your whole weekend. But it tells you exactly whose weekend it actually is. So the next time you wonder why nobody logs off anymore, look hard at who actually benefits when nobody does.

**Word/paragraph count (real, `check_length`): 355 words, 6 paragraphs.** Over the
5-paragraph hard ceiling; under the 365-word ceiling but nowhere near shaped.

**Tells deliberately planted** (catalogue numbers per `CLAUDE_TELL_CATALOGUE`): rhetorical-question + zoom-out opener (Big Conversation opening rule, not a numbered catalogue entry), #1 fake-profound reframe, #5 corporate/Latinate diction ("leverage", "infrastructure"), #6 scaffolding ("make no mistake"), #3 anaphora list ("Ask yourself..." x3), over-signposted concession ("So, to be fair,"), #10 trigger-vs-cause pivot, #13 archetype cataloguing, #14 announced transition, #11 reader-validation reach-through, #12 privilege-check pivot, #18 teeter-totter symmetry, #21 "Done properly," tic, #20 "In the end," wrap-up opener, #16 forced silver lining, #4 snap-closer aphorism, #15 full-circle callback.

### Stage 2: SHAPE TO PUBLISHED (Claude, manually applying the real prompt)

What I cut, and why, per `SHAPE_TO_PUBLISHED_SYSTEM` and `BIG_CONVERSATION_SHAPE_BLOCK`:

1. **Paragraph count 6 → 4.** Cut paragraph 3 ("A message at 8pm...") and paragraph 4
   ("The pandemic was the trigger...") whole — the two most repetitive angles (both restate
   "who's responsible for the ambiguity" already covered elsewhere), deleted entirely, not
   compressed, per the shape rule.
2. **Opening fix.** Deleted "Have you ever wondered why nobody logs off anymore? In the
   age of always-on connectivity, the" (rhetorical question + zoom-out) and capitalised the
   surviving clause: "The boundary between work and home has quietly dissolved..."
3. **Closing fix.** Deleted the "In the end, " announced wrap-up opener. Deleted the final
   full-circle-callback sentence ("So the next time you wonder why nobody logs off
   anymore...") because it mirrors the opening instead of landing a turn, per the closing
   rule ("an earlier sentence in the same paragraph should become the new ending") — the
   paragraph now ends on "But it tells you exactly whose weekend it actually is."
4. **Nothing added.** No new sentence, fact, or flourish anywhere.

> The boundary between work and home has quietly dissolved for millions of Australian corporate employees, and it happened so gradually that almost nobody agreed to it out loud.
>
> This isn't really about Slack notifications — it's about who gets to leverage your time after 6pm. Companies have built an entire infrastructure of low-grade urgency, and make no mistake, the after-hours message is rarely as urgent as it's framed to be.
>
> If you've ever felt guilty ignoring a message on a Friday night, that instinct is not a personal failing, it's a design choice made somewhere above your pay grade. Of course, leverage is a circumstance and not a mindset, and someone with a mortgage and two kids doesn't have the same freedom to switch off as someone renting alone and unattached. Done properly, this arrangement solves the company's problem while creating one nobody saw coming for the employee on the other end of it.
>
> Not every after-hours message is a red flag. Not worse. Just different. It won't always cost you your whole weekend. But it tells you exactly whose weekend it actually is.

**Word/paragraph count (real, `check_length`): 183 words, 4 paragraphs.** Paragraph count
is correct (4). Word count lands under the 280-340 target band — **that is the correct,
expected outcome, not an error.** This fixture is dense with tells, not dense with
substance; once the weakest paragraphs are cut whole, there isn't 280 words of real
content left, and the SHAPE prompt explicitly forbids padding to hit a number ("If the
draft is already under 280, that is fine — do not pad it"). A real GENERATE-stage draft,
written against the 280-340 target from the start, would not have this problem — this
fixture exists to exercise the cutting/opening/closing mechanics, not to calibrate the
target band.

### Stage 3: STRIP THE CLAUDE PHRASING (illustrative only — see caveat above; real run needs GPT-5.4)

Reproducing the real output format (body, then `---CHANGES---`, then `---FLAGGED FOR
VICTOR---` if anything was deliberately left in):

> The boundary between work and home has quietly dissolved for millions of Australian corporate employees, and it happened so gradually that almost nobody agreed to it out loud.
>
> Companies get to use your time after 6pm. The after-hours message is rarely as urgent as it's framed to be.
>
> This arrangement solves the company's problem while creating one nobody saw coming for the employee on the other end of it.
>
> Not every after-hours message is a red flag. It won't always cost you your whole weekend.

**---CHANGES---**
- Deleted "This isn't really about Slack notifications — it's about" and rejoined into a direct statement — catalogue #1, fake-profound reframe.
- Swapped "leverage" → "use" — catalogue #5, corporate/Latinate diction, minimal word-swap repair only.
- Deleted "Companies have built an entire infrastructure of low-grade urgency, and make no mistake," and rejoined — catalogue #5 (infrastructure) + #6 (scaffolding "make no mistake"), bundled in one clause.
- Deleted "If you've ever felt guilty ignoring a message on a Friday night, that instinct is not a personal failing, it's a design choice made somewhere above your pay grade." — catalogue #11, reader-validation reach-through.
- Deleted "Of course, leverage is a circumstance and not a mindset, and someone with a mortgage and two kids doesn't have the same freedom to switch off as someone renting alone and unattached." — catalogue #12, privilege-check pivot (a set piece, not one plain sentence, and doesn't change what the reader should do).
- Deleted "Done properly, " and capitalised "This" — catalogue #21.
- Deleted "Not worse. Just different." — catalogue #16, forced silver lining.
- Deleted "But it tells you exactly whose weekend it actually is." — catalogue #4, snap-closer aphorism (the "X. But Y." mini-reversal — kept the plainer first half, cut the polished second half).

**Left alone, on purpose:** "This arrangement solves the company's problem while creating
one nobody saw coming for the employee on the other end of it." matches catalogue #18
(teeter-totter symmetry) but is the **only** occurrence in this piece — the rule allows one
per piece and only intervenes on the second or later occurrence. Not deleted.

**An honest limitation surfaced by this pass:** cutting the snap-closer aphorism's second
half leaves "It won't always cost you your whole weekend." as the actual final sentence —
flatter than the original, engineered ending. That is the correct trade-off, not a defect:
the alternative (asking a model to write a fresher, punchier closer) is precisely how a
second AI tell gets substituted for the first one, which is the exact failure mode Victor's
delete-only rule exists to prevent. A human pass can still sharpen the ending further; what
this stage guarantees is that it will not quietly reintroduce a new engineered line while
doing it.

**Word/paragraph count (real, `check_length`): 85 words, 4 paragraphs.**

| Stage | Words | Paragraphs |
|---|---|---|
| Stage 1 (bad draft) | 355 | 6 |
| Stage 2 (shaped) | 183 | 4 |
| Stage 3 (stripped) | 85 | 4 |

---

## Example 2 — THE BRAINS TRUST

### Stage 1: GENERATE (fixture — deliberately bad, clearly labelled)

Topic: AI-driven graduate hiring slowdown. Not real broker research; written to exercise
the pipeline. Deliberately opens on the setup fact instead of the consequence (the exact
shape of Victor's own 27 Jul 2026 edit), and stacks in several more banned constructions.

> Global demand for enterprise AI chips grew 340% over the past two years, driven by hyperscale data centre buildouts across the United States and Asia Pacific.
>
> The employment data sharpens the picture further. Morgan Stanley's AlphaWise research provides the answer: graduate hiring across banking, insurance and professional services has fallen sharply as automation absorbs the tasks juniors used to do. The convergence matters.
>
> The practical question is what happens when a generation of workers never gets the entry-level experience the ones above them took for granted. Jarden's research, drawing on Deloitte Access Economics and the government's own workforce projections, finds that 167,200 entry-level roles have disappeared from the professional services pipeline since 2023, in what the research calls "graduate-ladder compression".
>
> This isn't really a hiring slowdown, it's a structural reset of how professional careers begin. Jarden's framing is precise: the labour market is "changing shape, not size". Done properly, firms could redesign the graduate pathway around fewer, more senior-adjacent roles.
>
> "This would mean re-thinking the first five years of a professional career entirely." -
>
> In the end, the firms that report their graduate intake numbers in August will be the ones to watch for how deep this goes.

**Word/paragraph count (real, `check_length`): 198 words, 6 paragraphs.** Already under
the word target — the problem here is paragraph count and shape, not length, a
deliberately different failure mode from Example 1.

**Tells deliberately planted:** setup-fact opener instead of consequence (Victor's own 27
Jul rule), "The employment data sharpens the picture further." / "The convergence matters."
(catalogue #14, announced transitions), stacked attribution ("Morgan Stanley's AlphaWise
research provides the answer"), posed-question device ("The practical question is..."),
chained sourcing ("Jarden's research, drawing on Deloitte Access Economics and..."), false
precision ("167,200"), coined jargon in quotes ("graduate-ladder compression"), #1
fake-profound reframe, buried pull quote ("Jarden's framing is precise: the labour market
is 'changing shape, not size'"), #21 "Done properly," tic, a broken pull-quote attribution
(dash with nothing after it), #20 "In the end," wrap-up opener, and a forward-watch-point
close instead of the prescribed economic mechanism.

### Stage 2: SHAPE TO PUBLISHED (Claude, manually applying the real prompt)

1. **Opening fix — consequence, not setup (the load-bearing rule).** P1 opened on the chip-demand
   setup fact. The real consequence sentence was buried in P2. Promoted it to the new P1,
   cutting its throat-clearing lead-in ("The employment data sharpens the picture further."
   / "Morgan Stanley's AlphaWise research provides the answer:") and trailing meta-commentary
   ("The convergence matters.") as scaffolding in front of / around the real opening line.
   Demoted the old setup fact (chip demand) to P2 — kept as supporting context, not deleted,
   per the shape rule ("demote... rather than deleting it, if it is still needed as
   context").
2. **Pull quote fix.** The broken pull-quote block (dash, nothing after it) was cut
   entirely — the shape rule says a broken attribution "gets folded back into plain prose,
   or cut, never left broken"; folding it back in would mean writing new connective prose,
   which this stage cannot do, so it was cut. Paragraph count 6 → 5.
3. **Closing fix, partial.** Deleted "In the end, " from the final paragraph.
4. **A genuine limitation, flagged rather than papered over:** even after removing "In the
   end,", the closing paragraph is still a bare forward-looking watch-point with no
   economic mechanism attached — the shape stage can trim the announced-wrap-up phrasing
   but cannot invent the missing "because" without adding new material, which it is
   forbidden to do. **This closing still needs a GENERATE-stage re-run or Victor's own
   edit — it is not fixed by this pass, and should not be treated as fixed.**

> Graduate hiring across banking, insurance and professional services has fallen sharply as automation absorbs the tasks juniors used to do.
>
> Global demand for enterprise AI chips grew 340% over the past two years, driven by hyperscale data centre buildouts across the United States and Asia Pacific.
>
> The practical question is what happens when a generation of workers never gets the entry-level experience the ones above them took for granted. Jarden's research, drawing on Deloitte Access Economics and the government's own workforce projections, finds that 167,200 entry-level roles have disappeared from the professional services pipeline since 2023, in what the research calls "graduate-ladder compression".
>
> This isn't really a hiring slowdown, it's a structural reset of how professional careers begin. Jarden's framing is precise: the labour market is "changing shape, not size". Done properly, firms could redesign the graduate pathway around fewer, more senior-adjacent roles.
>
> The firms that report their graduate intake numbers in August will be the ones to watch for how deep this goes.

**Word/paragraph count (real, `check_length`): 165 words, 5 paragraphs.** Paragraph count
at the ceiling (5, allowed). Word count under the 240-280 target band — again the correct,
expected outcome for a tell-dense rather than substance-dense fixture; no padding was
added.

### Stage 3: STRIP THE CLAUDE PHRASING (illustrative only — see caveat above; real run needs GPT-5.4)

> Graduate hiring across banking, insurance and professional services has fallen sharply as automation absorbs the tasks juniors used to do.
>
> Global demand for enterprise AI chips grew 340% over the past two years, driven by hyperscale data centre buildouts across the United States and Asia Pacific.
>
> The practical question is what happens when a generation of workers never gets the entry-level experience the ones above them took for granted. Jarden's research, drawing on Deloitte Access Economics and the government's own workforce projections, finds that 167,200 entry-level roles have disappeared from the professional services pipeline since 2023, in what the research calls "graduate-ladder compression".
>
> It's a structural reset of how professional careers begin. Jarden's framing is precise: the labour market is "changing shape, not size". Firms could redesign the graduate pathway around fewer, more senior-adjacent roles.
>
> The firms that report their graduate intake numbers in August will be the ones to watch for how deep this goes.

**---CHANGES---**
- Deleted "This isn't really a hiring slowdown, it's" and rejoined into a direct statement — catalogue #1, fake-profound reframe. Result: "It's a structural reset of how professional careers begin."
- Deleted "Done properly, " and capitalised "Firms" — catalogue #21.

**Left unchanged — deliberately, and this is the important finding:** paragraph 3's posed
question ("The practical question is what happens when..."), chained attribution ("Jarden's
research, drawing on Deloitte Access Economics and the government's own workforce
projections"), false precision ("167,200"), and coined jargon in quotes
("graduate-ladder compression"), plus paragraph 4's buried pull quote ("Jarden's framing is
precise: the labour market is 'changing shape, not size'") — **none of these match an entry
in the shared `CLAUDE_TELL_CATALOGUE`.** They are real problems, but they are
Brains-Trust-specific banned constructions that `BRAINS_TRUST_VOICE` already forbids at
GENERATE time (with tests pinning every one of them). The strip stage's binding
instruction is "only touch a sentence if it matches an entry in the catalogue below — do
not go hunting for prose you merely think could be better," so it correctly leaves them
alone rather than overreaching into GENERATE's job.

**This is a genuine, useful finding, not a bug:** this fixture deliberately bypassed
GENERATE (per Victor's instruction not to fire the pipeline), so it ships with violations
that a real GENERATE pass — governed by `BRAINS_TRUST_VOICE`, tested by
`test_brains_trust_voice.py` — would not have produced in the first place. STRIP staying
disciplined to its own catalogue, rather than reaching into BRAINS_TRUST_VOICE's remit, is
the pipeline working as designed: two layers, two jobs, no overlap that would let either
one quietly cover for the other's gaps.

**Word/paragraph count (real, `check_length`): 157 words, 5 paragraphs.**

| Stage | Words | Paragraphs |
|---|---|---|
| Stage 1 (bad draft) | 198 | 6 |
| Stage 2 (shaped) | 165 | 5 |
| Stage 3 (stripped, illustrative) | 157 | 5 |

---

## Findings this demo surfaced (fed back into the prompts, already committed)

1. **`BRAINS_TRUST_SHAPE_BLOCK` was missing the "consequence, not setup" check** — it only
   verified P1 states a number/event flat, not WHICH one. Fixed (see
   `docs/voice-prompts-refresh-report.md`) before this demo was finalised, and exercised
   directly in Example 2's stage 2.
2. **Some tells are correctly out of STRIP's scope.** Posed-question devices, chained
   attribution, false precision, and buried pull quotes are Brains-Trust-specific
   constructions already governed by `BRAINS_TRUST_VOICE` at GENERATE time. STRIP does not
   duplicate them, and should not — see Example 2's stage 3 for why that boundary matters.
3. **Delete-only sometimes leaves a flatter ending than the original.** Example 1's stage 3
   shows this directly (the snap-closer aphorism's punchier half is gone). This is the
   correct trade-off given the binding rule, not a defect to fix by generating a new closer.
4. **Not every closing flaw is fixable by SHAPE alone.** Example 2's stage 2 flags a closing
   that still lacks an economic mechanism after the mechanical "In the end," cut — SHAPE can
   trim the announced-wrap-up phrasing but cannot invent the missing "because" without
   adding new material, which it is forbidden to do. That gap needs a GENERATE-stage re-run
   or a human edit, not a silent pass.

## What's still pending

- **`OPENAI_API_KEY`** needs to be added to `.env` before stage 3 can run for real, on
  GPT-5.4, on real content. See `docs/voice-prompts-refresh-report.md` for the exact line.
- The demo above shows the STRIP *rules* working correctly by hand; it does not and cannot
  show what GPT-5.4 will actually produce, since a different model may catch things a
  human/Claude pass misses or vice versa — which is the entire point of using a second
  model family for this check.
