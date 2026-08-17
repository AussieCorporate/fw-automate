# Flat White voice prompts refresh — report

18 Aug 2026. Covers the three-stage prompt refresh (GENERATE → SHAPE TO PUBLISHED → STRIP
THE CLAUDE PHRASING) built against `docs/voice-refresh-findings.md` (research pass over the
6 most recent published editions, 6 Jul – 10 Aug 2026, pulled live from beehiiv on
17 Aug 2026), plus two mid-flight binding instructions from Victor: length is now a
first-class, mechanically-checked requirement, and the strip stage must run on GPT-5.4, not
Claude. Nothing was fired against the real pipeline — Victor said not to yet.

---

## 1. What was NOT changed, and why (his pinned rules)

The findings doc labelled three things "drift." Two are Victor's deliberate 27 Jul 2026
edit, already correctly encoded in `BRAINS_TRUST_VOICE`
(`flatwhite/classify/prompts.py`) and pinned line-by-line by `tests/test_brains_trust_voice.py`.
I verified this by reading the prompt before touching it and left both untouched:

- **"You"/contractions where the implication is personal.** `BRAINS_TRUST_VOICE` already
  says "Address the reader as 'you' where the implication is personal" and "Use
  contractions: isn't, it's, there's" — this is his own edit, not something the FW prompt
  got wrong.
- **Pull quotes, in his prescribed shape.** `BRAINS_TRUST_VOICE` already instructs lifting a
  quotable line out as a standalone block, attributed with a plain hyphen and house name on
  its own line, no introduction — again, his own edit, already correct.

What WAS stale was the **tac-newsletter-segments SKILL.md** (a separate file, not FW's
prompt), which said "zero instances of 'you'", "third-person... throughout", and "pull
quotes... dropped... since early June" — all three now contradicted by 4/6 and 2/6 of the
last 6 editions respectively. Corrected in section 3 below, citing his 27 Jul edit as the
source of truth, not reverting the actual generation rule (which was never wrong).

## 2. The genuine drift fixed, with evidence

All changes are additive to `BRAINS_TRUST_VOICE` — nothing his edit produced was deleted or
weakened; `tests/test_brains_trust_voice.py` grew from 13 to 22 tests, all passing,
including the original 13 unchanged.

| Fix | Evidence | Where |
|---|---|---|
| Closings must land the mechanism, not a stat pile or forward watch-point | Only 2/6 Brains Trust and 2/6 Big Conversation closings did this | `BRAINS_TRUST_VOICE` CLOSING section; `generate-prompt.md` CLOSING section |
| Fake-profound reframe banned in Brains Trust too | Reached print once, 27 Jul: "AI in Australia isn't producing mass layoffs. It's producing slower hiring..." | Both prompts' BANNED/FORBID lists |
| "Done properly," / "Done the right way," tic | Used twice in 6 editions (13 Jul, 6 Jul) | Both prompts; flagged for veto, see section 5 |
| "In the end," announced wrap-up opener | Shipped 10 Aug, final paragraph | Both prompts; flagged for veto, see section 5 |
| Broken pull-quote attribution (dash, nothing after it) | Shipped 20 Jul | `BRAINS_TRUST_VOICE` THE PULL QUOTE section — "worse than no pull quote at all" |
| Real word/paragraph counts, not aspirational ones | BT: 225-262 words in practice vs stated 200-350; BC: 4 paragraphs / 266-364 words vs stated 4-6 / 300-450 | `BRAINS_TRUST_VOICE` LENGTH; `generate-prompt.md`, `voice-guide.md`, both SKILL.md files |

## 3. Mid-flight instruction 1 — length is first-class, mechanically checked

Victor's exact numbers (not derived from theory):

- **Big Conversation:** 4 paragraphs target (5 only if genuinely needed, never 6). **280-340
  words target, 365 hard ceiling** (the observed max across the last 6 pieces). Retires the
  old 300-450 range.
- **Brains Trust:** kept his pinned 240-320/340 band untouched (tests still assert
  `"240-320"` is present), but the working **target is now 240-280**, noting 320 is
  headroom, not an aim. 3-5 paragraphs, 5 is the ceiling.
- Both: cut, don't pad, when in doubt.

Implemented as **plain code**, not a model's self-report:
`flatwhite/classify/voice_pipeline.py` — `LENGTH_SPECS`, `check_length()`,
`_word_count()`, `_paragraph_count()`. `run_voice_chain()` now:
1. Counts every stage's output mechanically.
2. If stage 2 lands over the hard ceiling, runs **one** automatic re-cut pass
   (`_recut_over_ceiling()`, explicit "cut N words... do not compress by rewriting"
   instruction) — never loops a second time.
3. Returns `word_counts`, `paragraph_counts`, `length_warnings` in the result dict so an
   over-ceiling piece is reported plainly, never shipped silently.

Stage 2's prompt (`SHAPE_TO_PUBLISHED_SYSTEM`) now explicitly instructs aiming at the
**middle** of the target band, not the top — because stage 3 (strip) deletes more text
afterward, so landing at the ceiling in stage 2 means the final piece finishes short of the
band instead of inside it.

**A gap the demo surfaced and fixed:** `BRAINS_TRUST_SHAPE_BLOCK` originally only checked
that P1 states a number/event flat — not which one. That let a draft open on the setup fact
(chip demand, market size) and still pass, exactly the shape Victor's own 27 Jul edit
banned. Fixed: stage 2 now promotes the real consequence sentence to P1 when it exists
later in the draft, demoting the setup fact to a later beat rather than deleting it. See
`docs/voice-pipeline-demo.md` Example 2 for this working end to end.

Tests: `tests/test_voice_pipeline.py` — `test_length_specs_match_the_binding_numbers`,
`test_check_length_flags_over_hard_ceiling`, `test_run_voice_chain_recuts_once_then_reports_if_still_over_ceiling`,
`test_run_voice_chain_recut_success_clears_the_warning`, and 6 more.

## 4. Mid-flight instruction 2 — strip stage runs on GPT-5.4, never falls back to Claude

Reasoning (Victor's, and it's correct): a Claude model checking its own output for Claude's
tells is exactly the blind spot the strip stage exists to remove.

- `flatwhite/model_router.py`: `DEFAULT_MODEL_BY_TASK["voice_strip"] = "gpt-5.4"` (plain,
  not `-pro` or `-mini`). `voice_shape` and the generate tasks stay on Claude.
- `run_voice_chain()` now takes **separate** `shape_model_override` / `strip_model_override`
  params — never one shared override that could accidentally pull the strip stage onto
  Claude.
- If the strip stage fails for **any** reason (missing key above all), the chain does not
  retry on a different model and does not crash. It returns
  `stage3_status="not_stripped"`, `stage3_error` (plain English), and `stage3_stripped`
  set to exactly stage 2's untouched output.

**Two real blockers, both need Victor, neither papered over:**
1. The `openai` Python package was not installed in the FW venv (only `anthropic` was).
   Installed it (`openai` 1.x+) and added `"openai>=1.0.0"` to `pyproject.toml`.
2. **`OPENAI_API_KEY` is not in `.env`.** It currently has `ANTHROPIC_API_KEY`,
   `GEMINI_API_KEY`, `BEEHIIV_API_KEY`, and SMTP keys only. Add this line to `.env`
   (Victor's own key, not invented or logged here):
   ```
   OPENAI_API_KEY=sk-...
   ```
   Until that's added, the strip stage will correctly report `not_stripped` rather than
   run — verified live with a real, unmocked `route()` call (see `docs/voice-pipeline-demo.md`,
   top section).

**Cost note:** the Claude stages (generate, shape) run on Victor's claude.ai subscription.
The strip stage on GPT-5.4 bills his **OpenAI account** as real API dollars per run — small
for a ~300-word piece, but a different pot of money than the Claude stages.

Tests: `test_voice_strip_resolves_to_gpt_5_4_by_default`,
`test_voice_strip_raises_when_openai_key_missing_not_silently_routed_elsewhere` (a real,
unmocked `route()` call), `test_run_voice_chain_stops_and_reports_when_strip_stage_unavailable_never_falls_back`.

## 5. Flagged tells that might be Victor's own voice — awaiting his veto

Per the brief's caution: some flagged sentences may be his own hand-edited lines, not raw
AI output, since he edits before publishing. I did NOT hard-ban these without noting the
ambiguity:

1. **The 27 Jul fake-profound reframe itself** ("AI in Australia isn't producing mass
   layoffs. It's producing slower hiring...") — it's in the very edition style he hand-edits.
   Banned in both prompts as a pattern (it structurally matches the banned shape exactly),
   but if Victor deliberately wrote or kept this line, he should say so and the ban can
   carry an exception for his own phrasing specifically, not the pattern generally.
2. **"Done properly," / "Done the right way,"** — could be a deliberate stylistic habit he
   likes and reuses (a real concession-opener voice), not necessarily an AI artefact.
   Flagged in both prompts as a "calcifying tic," banned as a pattern — his call on whether
   it's a tic to kill or a signature to keep.
3. **"In the end,"** wrap-up opener (10 Aug) — could be his own transition device for
   closing a thought, not necessarily drift. Banned as a pattern in this refresh.
4. **The reader-reassurance closings** (10 Aug: "the part you can actually count on"; 27
   Jul: "isn't rigged against you... 'aren't good enough'") — on sensitive topics (mental
   health, job rejection) deliberate warmth may be the right editorial call, not softening.
   Banned as a general pattern here; worth checking with him on topic-sensitive exceptions.

The STRIP prompt's own system instructions (`STRIP_CLAUDE_PHRASING_SYSTEM`) carry this same
caution operationally: if a flagged sentence is plausibly his own phrasing and deleting it
would lose a load-bearing fact rather than scaffolding, the strip stage is instructed to
leave it in place and flag it in a `---FLAGGED FOR VICTOR---` section rather than delete it
outright.

## 6. Files changed

### FW repo (branch `voice-prompts-refresh`, 5 commits on top of `main` @ `a982e08`)

| File | What changed |
|---|---|
| `flatwhite/classify/prompts.py` | `BRAINS_TRUST_VOICE` extended: CLOSING section, fake-profound/"Done properly,"/"In the end," bans, pull-quote optionality + broken-attribution ban, tightened length target. Nothing removed. |
| `flatwhite/classify/voice_pipeline.py` | New. Stages 2 (SHAPE TO PUBLISHED) and 3 (STRIP THE CLAUDE PHRASING), shared across both segments. `LENGTH_SPECS`, `check_length()`, the 22-entry `CLAUDE_TELL_CATALOGUE`, `run_voice_chain()`. |
| `flatwhite/model_router.py` | Two new task types (`voice_shape`, `voice_strip`); `voice_strip` defaults to `gpt-5.4`/openai. |
| `pyproject.toml` | Added `openai>=1.0.0` dependency. |
| `tests/test_brains_trust_voice.py` | 13 → 22 tests. All original 13 untouched and passing. |
| `tests/test_voice_pipeline.py` | New, 26 tests. |
| `docs/voice-refresh-findings.md` | The research doc (committed as the evidence trail this refresh is built on). |
| `docs/voice-pipeline-demo.md` | Deliverable D — the before/after demonstration. |
| `docs/voice-prompts-refresh-report.md` | This file. |

Commits: `852a6df` (Brains Trust extend + pipeline stages 2/3), `4a9a58e` (length
mechanics), `c6cd40e` (GPT-5.4 routing + honest-stop), `b5d8221` (consequence-not-setup
shape fix), `1c03756` (demo doc). Branch not merged, per instruction.

### Big Conversation skill (`~/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/`) — NOT a git repo, confirmed (`git status` → "not a git repository"). Files written directly, no commit possible.

| File | What changed |
|---|---|
| `references/generate-prompt.md` | New. The standalone GENERATE prompt for Big Conversation, supersedes `voice-guide.md`'s old shape numbers. |
| `references/voice-guide.md` | Shape section corrected (4 paragraphs / 280-340 words / 365 ceiling; closing rule sharpened); 3 new tells added to the "AI tells to strip" list, pointing to the canonical catalogue in FW's `voice_pipeline.py` rather than duplicating it. |
| `references/published-examples.md` | Refreshed: 5 newer editions' verbatim opens/closes added (from the findings doc — full body text wasn't captured for these 5, noted honestly); stated structure numbers corrected. |
| `SKILL.md` | Step 4 now points to `generate-prompt.md`; added the shape/strip stage note (GPT-5.4, mechanical length checks, where the chain lives). |

### `~/.claude/skills/tac-newsletter-segments/` — NOT a git repo, confirmed. Files written directly.

| File | What changed |
|---|---|
| `SKILL.md` | Corrected the "zero you" / "third-person" / "pull quotes dropped" claims, citing Victor's 27 Jul edit as the source of truth. Updated Brains Trust and Big Conversation shape numbers to match the refresh. |
| `references/brains-trust-current-format.md` | Overwritten: new 6-edition shape table (words/"you"/pull-quote/closing-mechanism per edition), the two wrong claims from the 13 Jul refresh explicitly called out and corrected, verbatim opens/closes/pull quotes (correct and broken) added for the 5 newest editions. The original 3 full-text samples (6 Jul, 29 Jun, 22 Jun) kept, relabelled "pre-27-Jul-edit... still useful for paragraph rhythm and register" rather than deleted, since they remain genuinely useful for sentence-level calibration. |

**Not touched, out of this refresh's explicit scope:** `~/.claude/skills/tac-editorial-voice/references/published-corpus-2026H1-part1/2.md` and its own `published-examples.md` — the brief named `brains-trust-current-format.md` and the big-conversation skill's `published-examples.md` specifically; `tac-editorial-voice`'s own separate corpus files are a different skill's references and weren't in the named list.

## 7. Where the chain is wired, and what still must call it

**Not wired into the dashboard.** Per instruction, I did not edit `flatwhite/dashboard/api.py`
or `flatwhite/dashboard/skill_runner.py` — those were mid-repair for a separate silent-failure
bug (confirmed: `api.py` had uncommitted changes when I started, since landed as commit
`a982e08` "Fix Big Conversation silent-run bug and add run observability").

**Exactly where the runner must call it, once that repair is done:**
- Brains Trust: `flatwhite/dashboard/api.py`, function `_proceed_brains_trust()` (around
  line 2340). It currently calls `route(task_type="brains_trust", prompt=prompt,
  system=BRAINS_TRUST_VOICE, model_override=override)` **directly and returns the raw
  string** — this is stage 1 only. It should instead call
  `voice_pipeline.run_voice_chain("brains_trust", generate_fn=lambda: route(...))` and
  return/store the resulting dict (`stage1_generate`, `stage2_shaped`, `stage3_stripped`,
  `stage3_status`, `length_warnings`, etc.) so Victor sees all three stages, not just stage 1.
- Big Conversation: `flatwhite/classify/big_conversation.py`, function
  `draft_big_conversation()`. Same pattern —
  `voice_pipeline.run_voice_chain("big_conversation", generate_fn=lambda:
  draft_big_conversation(...))`.
- The interactive (non-automated) Big Conversation workflow: the big-conversation skill's
  `SKILL.md` step 4 already documents calling `shape_to_published()` /
  `strip_claude_phrasing()` / `run_voice_chain()` from `voice_pipeline.py` directly, or
  applying the two prompts by hand if the FW pipeline isn't wired up in that session.

## 8. Test suite status

`tests/test_brains_trust_voice.py` and `tests/test_voice_pipeline.py`: **48/48 passing.**
Full FW suite: 411 passing, 8 pre-existing failures in `tests/test_normalise.py` and
`tests/test_pipeline.py` — verified these predate this work entirely (reproduced by
stashing every file this refresh touched and re-running; identical 8 failures, unrelated to
pulse/normalisation code this refresh never touched).

## 9. Concerns / open items for Victor

- The 4 flagged-tell items in section 5 need his explicit veto or confirmation — they were
  banned as patterns in this refresh, but each has a plausible "that's actually my own
  voice" reading.
- The GPT-5.4 strip stage cannot be exercised for real until `OPENAI_API_KEY` is added — see
  section 4. `docs/voice-pipeline-demo.md` shows the rules working by hand as a stand-in,
  clearly labelled as such.
- The dashboard wiring (section 7) is documented, not built — whoever finishes the
  silent-failure repair on `api.py` should pick this up next.
- Both worked demo fixtures land under their target word band after cutting, because they
  were written dense with tells rather than dense with substance — explained in
  `docs/voice-pipeline-demo.md`, not a defect in the shape logic itself.
