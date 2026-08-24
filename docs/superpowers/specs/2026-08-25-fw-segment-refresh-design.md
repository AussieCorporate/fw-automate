# FW segment refresh — design (25 Aug 2026)

Approved by Victor in chat, 25 Aug 2026. Decisions locked in:
- Finish line stays PER-SEGMENT "Insert into beehiiv" (no whole-edition button —
  standing decision in CLAUDE.md).
- Brains Trust outside research = live web research at draft time (broker PDFs
  stay the anchor).
- Questions ruling: natural thinking-out-loud questions ship; the
  announce-the-next-topic question device stays banned (CLAUDE.md).

Calibration corpus: `data/beehiiv_fw_ground_truth.json` (10 editions,
May–Jul 2026) + the 24 Aug edition "Cover letter, yes or no?"
(post_d00778fe-0798-4d8a-a372-d236d928bbd8), whose Brains Trust Victor rated the
best in a while — 4 short paragraphs, each anchored on a chart with a Source
caption, consequence-first opener, broker research blended with outside sources
(ABS, Nielsen, Fitch, UK whey prices, a named nutrition researcher), tangible
reader hooks ("the portugese chicken shop near your office").

## Phase 1 — finish the Big Conversation patch

1. `flatwhite/classify/prompts.py` `BIG_CONVERSATION_DRAFT_SYSTEM`: replace the
   stale 21 Jul rules with the register spec
   (`docs/big-conversation-published-spec.md`): 280–340 words, 4 paragraphs
   (5 stretch, never 6), natural questions allowed / announce-device banned,
   ordinary idioms over coinage, max one mic-drop paragraph closer, no stacked
   attribution.
2. Wire stage 2 (SHAPE) — currently dead code: `draft_big_conversation()` runs
   `run_voice_chain()` (shape + GPT-5.4 strip) instead of returning the raw
   stage-1 draft. Skill-run path keeps its existing post-run strip
   (`strip_stage.py`) and additionally gets a mechanical length check with
   `_recut_over_ceiling` on breach.
3. Ready plumbing: when a skill run's strip completes, save the final draft into
   `section_outputs` for the current week under `big_conversation`, so the
   segment can go green and the editorial intro can unlock. Content-bank pull
   path unchanged.

## Phase 2 — Brains Trust to the 24 Aug standard

1. Wire shape + GPT-5.4 strip into `_proceed_brains_trust` (all three input
   paths: angles, own_text, custom_prompt). Length 240–320, hard 340,
   mechanically enforced via `check_length` + recut. No silent Claude fallback
   for strip (same honest-stop as Big Conversation).
2. New enrichment step before drafting: web research on the chosen angle
   (official stats, price/consumption data, studies, recent news; named
   institutions only, no invented figures). Merged into the prompt context as
   OUTSIDE RESEARCH alongside the broker pool; the prompt requires at least one
   woven-in outside source when available and plain-verb attribution.
3. Draft output includes chart suggestions: per paragraph, which chart from the
   source PDFs (or which outside dataset) to place, with a Source caption line —
   suggestions only, Victor places images in beehiiv.
4. UI: stale-pool warning when the newest `_candidates.json` folder is >7 days
   old (pool is refreshable via the existing Refresh button).
5. Extend the register rules (idioms over coinage, one mic-drop max) to the
   Brains Trust prompt — same evidence base, Victor's 24 Aug ruling.

## Phase 3 — Off the Clock re-sourcing

Root cause: intake is mass outlets, so the existing niche-first ranking has
nothing niche to rank. Per category (`config.yaml off_the_clock:`):

- **watching**: streaming charts + new-on-streaming sources (what's newly on /
  top on Netflix, Binge, Stan; film/TV culture press). Remove games-trade
  feeds (ScreenHub).
- **reading**: NEW sourcing for upskilling + health (career, money, psychology,
  health books and long reads). Currently zero sources for this brief.
- **wearing**: what's trending now (drops, viral pieces, street-style movement),
  not evergreen listicles.
- **eating/going**: add niche/independent + suburb-level sources so small venues
  actually enter the pool; keep the mass-outlet demotion.
- Classifier prompt (`OTC_CLASSIFICATION_PROMPT`): score "culturally cool /
  notable / new"; hard-penalise round-up listicles ("23 things to do…", "best
  X of 2026") and anything already mass-covered.
- Bug fix: persist picks via the existing (never-called) `POST
  /api/off-the-clock/pick` so a page refresh doesn't lose selections.
- Dedupe the near-identical OTC write-up prompt that is inlined twice in
  `api.py`.

## Phase 4 — fill the missing segments

- **AusCorp Events**: editable saved card (persisted in `section_outputs`),
  simple bullet format matching published editions.
- **Salary Survey promo**: reusable stored block, toggle on/off per week.
- **"Missed last week's newsletter" footer**: auto-filled from the most recent
  published edition (title + URL from beehiiv ground-truth refresh or manual
  paste fallback).
- **Subject line + preview text**: generation on the live path (currently only
  in the dead Composer), calibrated on the 10 real titles.

## Out of scope (standing decisions)

- Thread of the Week: stays manual paste + formatting. No scrape rebuild.
- No whole-edition one-click. No Reddit OAuth.

## Testing

- Existing suites extended: `tests/test_voice_pipeline.py`,
  `tests/test_brains_trust_voice.py` pin new prompt rules to the evidence.
- New: ready-plumbing test (skill run → section_outputs), OTC pick persistence
  test, classifier listicle-penalty fixture test against real 24 Aug picks
  (Vogue handbags listicle must rank below a niche candidate).
- Word-count checks run against `data/beehiiv_fw_ground_truth.json`, never
  hardcoded (existing `benchmark.py` convention).

## Deploy note

Dashboard + Big Conversation run locally on Victor's Mac (skill + Claude CLI
are local-only; VM returns 503 by design). Scraper/ingest changes (OTC config,
classifier) ship to the GCP VM via `deploy/gcp_deploy.sh` per the definition of
done. Report local-only vs deployed explicitly at the end.
