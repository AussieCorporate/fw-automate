# FW Control Room Increment 3 — Screenshot Sort Skill Rebuild, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to work this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Instagram DM screenshot-sorting rules that feed The Big Conversation and The Inside Track. The current "RED HOT / Tier 1-4" parameters are wrong: they treat the tiers as a quality ladder (best to worst) when the real job is to keep the VIRAL EXTREMES of each side of a topic, keep the CONSENSUS middle (not discard it as boring filler), and route GOSSIP/REDUNDANCY out to The Inside Track instead of into Big Conversation material. This increment is markdown only — no app code, no Python, no FW dashboard changes. It authors one new skill and recalibrates two existing files so that the next time anyone (or the FW control room, in Increment 4) runs a sort or a Big-Conversation process, it uses the corrected rubric.

**Architecture:** Three markdown files, no code. A brand-new skill, `screenshot-sort`, encodes the sort rubric and is meant to run FIRST on a freshly-scraped batch, before the existing `big-conversation` skill runs on a chosen topic folder. `big-conversation` already assigns sorted screenshots into the paragraphs of the written piece at process time (confirmed by inspecting a real output — see "Findings from exploration" below); what's wrong is the CRITERION it uses to pick which screenshots go where, not the paragraph-assignment mechanism itself. So this increment corrects the criterion in `big-conversation`'s existing Step 5, and pushes the sort rubric itself into the new `screenshot-sort` skill plus a rewritten "Standing sort rules" section in `output/CLAUDE.md`.

**Tech stack:** Markdown only (Claude Code skill files + a project CLAUDE.md). No build step, no pytest, no JS harness. "Tests" for this increment are: (a) a rubric self-check — grep the edited/new files for every corrected parameter's keyword and confirm it is present, (b) a dry run — apply the new rubric by eye to a real, already-sorted topic folder and write up whether the buckets would come out sensibly reclassified, (c) an em-dash grep on the files this increment touches.

## Global Constraints

- **No em dashes (U+2014)** in any content this increment WRITES or REWRITES: the full new `screenshot-sort/SKILL.md`, and the specific passages edited into `output/CLAUDE.md` and `big-conversation/SKILL.md`. Scope note: both existing files already contain roughly 20 em dashes in passages this increment does NOT touch (confirmed by `grep -c` during exploration) — those are pre-existing internal/operational documentation style, not reader-facing copy, and a full-file retroactive sweep is out of scope for this increment (it would be a much bigger, unrelated edit). Flag this scope decision to Victor; do not silently leave the impression the whole file is now em-dash-clean.
- **Australian spelling** throughout everything written (organise, colour, favour, recognise, etc.).
- **Do NOT touch `screenshot_dms.py`, `scraper.py`, `capture.py`, `browser.py`, `config.py`** or any other Python in `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter`. This increment is skill/rules markdown only.
- **The smart-dash trap** is documented in the scraper's own guide, `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/CLAUDE.md`: a pasted `--period` flag arrives as an em dash and fails with "unrecognized arguments." That file is NOT touched by this increment (it governs the scraper CLI, not sorting) — noted here only so a later increment wiring a sort trigger to the CLI doesn't reintroduce it.
- **Stay compatible with the existing folder/tier layout** the screenshotter already produces: `🔥 RED HOT Top N`, `Tier 1 - Viral` … `Tier 4 - Rubbish`, `MISC Stand alone`, `Rubbish`, `Junk`, `_SPILLOVER hold`, `Redundancies & Breaking News`, `_BIG_CONVERSATION_assets`, `_sort_session<N>_manifest.tsv`, `_undo_session<N>_sort.sh`. Existing already-sorted topic folders (Kids in the Office, Career Pivoting, PIP Term Length, Manager Pet Names, etc.) are **not retroactively re-sorted or renamed** by this increment — only the rubric and the folder-naming convention for sort sessions FROM NOW ON changes. Where a naming update is introduced (Gossip/Redundancy folder), the plan keeps the old name as a recognised synonym rather than mass-renaming existing folders.
- **No git repo at either location.** Confirmed: `git rev-parse --is-inside-work-tree` fails in both `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter` and `~/.claude/skills`. There is no branch and no commit step in this plan. Before overwriting any existing file, make a dated `.bak` copy alongside it — that backup is the only rollback path since there's no git history. Tell Victor exactly which files changed and that nothing is deployed anywhere: these are local markdown files, read the next time a sort or Big-Conversation session runs. Nothing in `/Users/victornguyen/Documents/MISC/FW` changes in this increment.
- No pytest / JS harness applies. Every verification step below is a `grep`, a manual read-through, or a short dry-run write-up — not an automated suite.

## File Structure

Files this increment creates or edits:

- `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md` — **NEW.** The rebuilt sort skill (full content in Task 2).
- `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md` — **EDIT.** "Standing sort rules" section rewritten to the corrected buckets + a pointer to the new skill.
- `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md` — **EDIT.** Front-matter description, Step 2 ("Ensure fuel exists"), Step 5 ("Select & map the screenshots"), and the "Inputs & conventions" tier-folder line, recalibrated to the corrected pools (extremes-of-each-end + consensus middle, not "complementary POV").
- `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/_work/screenshot_sort_dryrun_2026-07-14.md` — **NEW.** This increment's dry-run evidence report, written into the project's existing `_work/` convention (its own CLAUDE.md already says sub-agent intermediates belong there, never `/tmp`).
- Backups created before editing: `output/CLAUDE.md.bak-20260714` and `output/.claude/skills/big-conversation/SKILL.md.bak-20260714`.
- **Not touched:** anything under `/Users/victornguyen/Documents/MISC/FW` (the control room reads/invokes this skill starting in Increment 4), anything under `instagram_profile/`, and every Python file in the screenshotter repo.

## Findings from exploration (recorded so the plan doesn't re-litigate them)

1. **There is no existing dedicated sort skill.** Today's sorting is ad hoc: whoever runs a sort session reads `output/CLAUDE.md`'s four-line "Standing sort rules" (tier folder names, the redundancy-gets-its-own-folder rule, copy-never-move, RED HOT verbatim verification) and repeats the pattern visible in the ~12 past `_SORT_SESSION_N_REPORT.md` write-ups. There is no single rubric document defining what "RED HOT" or "Tier 3" are actually FOR. This increment turns that tribal knowledge into an actual skill.
2. **`big-conversation` already assigns sorted screenshots into paragraphs at process time.** Verified against a real produced piece, `output/_KIDS_OFFICE_BIG_CONVERSATION.md`: its Step 5 already outputs a `BUILD: paragraph → screenshot map` with one primary pick plus 2-3 ranked alternates per paragraph, and copies the chosen files into `<topic>/_BIG_CONVERSATION_assets/` renamed `p<paragraph>_<rank>_<handle>.png`. **So the mechanism the spec asks to "confirm or build" already exists** — what's wrong is the SELECTION CRITERION it applies (current rule: "complementary POV, not an echo"), which is not the "extreme of each end + consensus middle" framework Victor wants. This increment corrects the criterion inside the existing mechanism; it does not need to invent paragraph-pairing from scratch.
3. **Published output confirms roughly one screenshot per paragraph ships.** `data/beehiiv_fw_ground_truth.json`'s "THE BIG CONVERSATION" segment for a real edition shows one image between each paragraph of prose — useful calibration for how many of a paragraph's ranked options actually get used versus offered as alternates.
4. **A real, already-sorted, recent topic folder exists for the dry run:** `output/Kids in the Office/` (sorted 10 Jul 2026, already has a produced `_KIDS_OFFICE_BIG_CONVERSATION.md`). Its current tier counts: `🔥 RED HOT Top 22` = 17 files, `Tier 1 - Viral` = 14, `Tier 2 - Strong` = 34, `Tier 3 - Ordinary` = 26, `Tier 4 - Rubbish` = 3, plus 5 loose PNGs at the topic-folder root.

---

### Task 1: Baseline + backups

**Files:** none written yet; this task only reads and copies.

- [ ] **Step 1: Confirm current file shapes match this plan's assumptions.**
```bash
wc -l "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md"
# expect 18
wc -l "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md"
# expect 145
```
If the counts differ materially, re-read the file before editing — someone else may have touched it since this plan was written.

- [ ] **Step 2: Confirm no git repo at either location** (so backups, not commits, are the rollback path):
```bash
git -C "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter" rev-parse --is-inside-work-tree
git -C "/Users/victornguyen/.claude/skills" rev-parse --is-inside-work-tree
```
Both expected to print `fatal: not a git repository...` — confirmed during planning exploration.

- [ ] **Step 3: Make dated backups before touching anything:**
```bash
cp "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md" \
   "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md.bak-20260714"
cp "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md" \
   "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md.bak-20260714"
```

---

### Task 2: Write the new screenshot-sort skill

**Files:** `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md` (new directory + file).

**Interfaces:** consumed by whoever (or, from Increment 4, whatever FW dashboard endpoint) runs a sort session on freshly-scraped screenshots, before the `big-conversation` skill runs on a chosen topic. Produces the sorted folder layout `big-conversation` (Task 4) expects.

- [ ] **Step 1: Create the directory and file** with this exact content:

```markdown
---
name: screenshot-sort
description: Use when Victor has a freshly-scraped batch of Instagram DM screenshots in output/ that need first-pass classification, before any Big Conversation drafting happens. Sorts each screenshot into one of three destinations - Big Conversation topic/tier folders, The Inside Track (gossip and redundancy), or junk - and tags viral-extreme picks with which pole of the topic's spectrum they represent. Run this BEFORE the big-conversation skill.
---

# Instagram DM screenshot sort

Classifies one Instagram DM campaign's scraped screenshots (one message per PNG, dropped
loose at the `output/` root) into the folders that feed THE BIG CONVERSATION and THE INSIDE
TRACK. Run this skill FIRST, on every freshly-scraped batch, before touching the
`big-conversation` skill - that skill drafts the piece and pairs paragraphs from folders this
skill has already sorted.

## The three destinations

Every screenshot goes to exactly one of three places:

1. **Big Conversation material** - filed into a topic folder (one per campaign question),
   then tiered inside that folder (see "The tiers" below). Genuine community commentary that
   answers one of the week's campaign questions.
2. **The Inside Track** - gossip and redundancy. Routed to `Inside Track - Gossip & Redundancy`
   (see "Gossip vs redundancy" below).
3. **Junk** - `Rubbish`, `Junk` (moved to macOS Trash, recoverable), `MISC Stand alone`
   (on-topic-ish but a one-off with no folder to sit in), `_SPILLOVER hold` (genuinely
   ambiguous between two open topics). Unchanged from current practice.

## The tiers inside a Big Conversation topic folder (corrected 14 Jul 2026)

The old parameters treated the tiers as a quality ladder, best to worst. That throws away
the two things a Big Conversation piece needs most: the extremes, and the consensus. The
corrected criterion for each tier:

- **`RED HOT Top N` = VIRAL EXTREME.** Not "the best written" - the ones that make a
  stranger go "wtf, you have to see this" and forward it to a mate. This is the far pole (or
  poles - see "Tag the pole" below) of THIS topic's range, not a generic virality score. A
  screenshot lands here because it is the most extreme version of one side of the argument,
  not because it is the most eloquent.
- **`Tier 1 - Viral` and `Tier 2 - Strong`** = one register down from the viral extreme.
  Individually compelling, clearly a strong instance of one side, but not the single most
  extreme thing in the folder. Useful as a backup pole pick when the RED HOT pick for a pole
  is already used elsewhere in the piece.
- **`Tier 3 - Ordinary` = CONSENSUS, not filler.** The single most important correction. Tier
  3 is not "the boring ones kept for completeness" - it is the pool that shows what most
  people actually think. A topic's Tier 3 shows what "normal" looks like for this question,
  and normal is exactly what a Big Conversation needs as its anchor before it argues either
  extreme. Never route a Tier 3 screenshot to Rubbish just because it isn't quotable alone;
  keep it if it is representative of the median response.
- **`Tier 4 - Rubbish`** = genuinely low-value: generic ("this happened to me too" with no
  detail), unreadable, or a pure duplicate of a sentiment three other shots already cover.
  Unchanged from before.

### Tag the pole

Most workplace topics split into two sides (e.g. "kids in the office": fine/charming vs
disruptive/liability; "PIP term length": fair-process vs stitch-up). When sorting a
screenshot into `RED HOT Top N` (or Tier 1/2), tag which pole it represents in the sort
manifest and the session report - e.g. `(pole: pro)` / `(pole: con)`. If a topic genuinely
only has one side (nobody is defending it), say so explicitly in the session report rather
than forcing a fake second pole.

## Gossip vs redundancy - both go to The Inside Track, not Big Conversation

- **Gossip**: names a specific company, team or person and trades in drama, scandal or
  speculation rather than answering the campaign's question (e.g. "X consulting firm's whole
  leadership team just got walked out"). Not evidence for a Big Conversation angle - it is
  its own story.
- **Redundancy**: a repost of breaking news already covered elsewhere (a screenshotted
  article, a LinkedIn post about a layoff round, etc.) rather than original DM commentary.
- Both route to the SAME folder: `Inside Track - Gossip & Redundancy`. This is the same
  folder and job as the earlier `Redundancies & Breaking News` name, widened to make explicit
  that gossip belongs here too. Existing topic folders that still say `Redundancies &
  Breaking News` do not need renaming - treat both names as the same bucket.
- This folder is never touched by the `big-conversation` skill. It is a separate work queue
  for The Inside Track segment, where a human picks which items to write up.

## Process (do these in order)

### 1. Gather
- List the loose PNGs scraped since the last sort session (the newest scrape's files,
  dropped at the `output/` root) - check the scrape's timestamp against the last
  `_SORT_SESSION_N_REPORT.md`'s date.
- Note the Friday campaign's three questions for this batch (Victor supplies these). Every
  screenshot gets checked against them first.

### 2. Classify (fan out for volume)
For a large batch, fan out parallel Explore/general-purpose sub-agents over slices of roughly
20-30 screenshots each (matches existing practice - `_SORT_SESSION_12_REPORT.md` used "8
parallel sonnet readers, ~30 each"). Each reader returns, per screenshot: filename, verbatim
quote, which of the three destinations it belongs to, and if Big Conversation material: which
topic question, which tier, and, if RED HOT/Tier 1/2, which pole.

Classification order per screenshot:
1. Is this gossip or redundancy (names names or trades in drama, or reposts news already
   known)? -> `Inside Track - Gossip & Redundancy`.
2. Is this junk (blank, unreadable, spam, wildly off-topic)? -> `Rubbish` / `Junk`.
3. Otherwise it is Big Conversation material for one of the batch's topic questions. Which
   pole, or is it consensus?
   - The extreme version of one side -> `RED HOT Top N`, tag the pole.
   - Strong but not the most extreme -> `Tier 1 - Viral` or `Tier 2 - Strong`, tag the pole.
   - Ordinary, representative, "this is just what happened to me" -> `Tier 3 - Ordinary`
     (the consensus pool - keep it, do not discard it as boring).
   - Low value or duplicate -> `Tier 4 - Rubbish`.
4. Doesn't fit an open topic question but is clearly a real workplace story on some topic ->
   `MISC Stand alone`, or `_SPILLOVER hold` if genuinely ambiguous between two open topics.

### 3. Verify RED HOT picks verbatim
Same standing rule as before: before finalising the `RED HOT Top N` folder, read the actual
image for each pick and confirm the quote used in the session report matches what the image
says. Drop and flag any mismatch (`_SORT_SESSION_12_REPORT.md` has a worked example of a
caught hallucination - the pattern to watch for).

### 4. Move into folders
Screenshots MOVE from the `output/` root into the topic/tier folders during sorting. Copies
only happen later, inside the `big-conversation` skill's paragraph-mapping step, which COPIES
into `_BIG_CONVERSATION_assets/`. Use the manifest TSV + undo script pattern already
established (`_sort_session<N>_manifest.tsv`, `_undo_session<N>_sort.sh`) - every sort session
must stay reversible.

### 5. Report
Write `_SORT_SESSION_<N>_REPORT.md` at the output root, same shape as past reports, with two
additions:
- State each RED HOT/Tier 1/2 pick's pole tag (`pro` / `con`) next to it.
- A one-line count of how many screenshots landed in `Inside Track - Gossip & Redundancy`
  this session, split gossip vs redundancy if the distinction was clear.

## Rubric coverage checklist (self-check before calling a sort session done)

- [ ] VIRAL EXTREME (not "generic best-of") drives what enters `RED HOT Top N`.
- [ ] CONSENSUS is explicitly kept in `Tier 3 - Ordinary`, not treated as near-rubbish.
- [ ] Both poles of the topic's spectrum are represented somewhere in RED HOT/Tier 1/2 when
      the topic has two sides, or the report explains why not.
- [ ] Gossip AND redundancy both route to `Inside Track - Gossip & Redundancy`, never into a
      topic's tiers.
- [ ] Tier folder labels (`RED HOT`, `Tier 1` - `Tier 4`) are unchanged, for compatibility
      with the existing screenshotter output.
- [ ] Every RED HOT/Tier 1/2 pick is verified verbatim against the actual PNG.
- [ ] A session report, manifest and undo script are produced, matching the existing pattern.
- [ ] No em dashes anywhere in the session report prose.

## Notes
- This skill sorts. The sibling `big-conversation` skill drafts the piece and pairs the
  sorted screenshots into paragraphs - run that one second, once a topic is chosen from the
  bank.
- Screenshots MOVE during this skill's sort (root to topic/tier folders); they only get
  COPIED later when `big-conversation` builds `_BIG_CONVERSATION_assets/`. Do not change that
  copy-vs-move split.
- Sub-agent hygiene: parallel classification sub-agents write all intermediate TSVs and notes
  inside `output/_work/`, never `/tmp` - matches the project's standing rule.
```

- [ ] **Step 2: Verify the file was written correctly.**
```bash
ls -la "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md"
head -5 "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md"
```
Confirm the front matter (`name: screenshot-sort`) is present and the file is non-empty.

---

### Task 3: Rewrite `output/CLAUDE.md`'s standing sort rules

**Files:** `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md`.

**Interfaces:** this is the file every sort session (and the `big-conversation` skill's own opening line) currently points to as "the standing rules." Task 4 relies on this file's corrected wording matching what it references.

- [ ] **Step 1: Replace the full file.** Current content (back it up per Task 1 before this edit):

Old (full file, 18 lines):
```markdown
# DM screenshots workspace — weekly editorial pipeline

This folder holds the sorted screenshot batches and the weekly "THE BIG CONVERSATION" work. The editorial workflow itself is encoded in the `big-conversation` skill (`.claude/skills/big-conversation/`) — invoke it for analysis/drafting/screenshot mapping; don't re-derive the process.

## Standing sort rules (apply during EVERY classification/sort run)

- Tier folders: `Tier 1 - Viral` … `Tier 4 - Rubbish`, plus JUNK / UNREADABLE / SPILLOVER as used in past batches; `🔥 RED HOT Top N` holds the verified best.
- **Redundancy and breaking-news submissions get their OWN folder**, separate from the week's question folders — every batch contains some, and they must not be mixed into topic tiers.
- Screenshots are COPIED, never moved, when mapping to editorial paragraphs.
- RED HOT picks must be verified verbatim against the actual images, not filenames.

## Sub-agent hygiene

Parallel classification sub-agents must write ALL intermediate outputs (TSVs, notes) inside this project folder (e.g. a `_work/` subfolder), never to /tmp — /tmp writes hit permission denials and stall the whole batch.

## Voice reminders (full rules live in the skill's references)

Never reference that the community "wrote in" or mention screenshots in prose; screenshots complement the prose with a different POV, never restate it; no em dashes.
```

New (full file, replaces the above):
```markdown
# DM screenshots workspace - weekly editorial pipeline

This folder holds the sorted screenshot batches and the weekly "THE BIG CONVERSATION" work.
Sorting is encoded in the `screenshot-sort` skill (`.claude/skills/screenshot-sort/`) - run it
FIRST on every freshly-scraped batch. The editorial workflow that turns a sorted topic into
the finished piece is encoded in the `big-conversation` skill
(`.claude/skills/big-conversation/`) - invoke it second, once a topic is chosen.

## Standing sort rules (apply during EVERY classification/sort run)

**Full rubric: `.claude/skills/screenshot-sort/SKILL.md`.**

- Tier folders: `Tier 1 - Viral` ... `Tier 4 - Rubbish`, plus JUNK / UNREADABLE / SPILLOVER as
  used in past batches. Corrected criteria (14 Jul 2026 rebuild, full detail in the skill):
  - `RED HOT Top N` = the VIRAL EXTREME pole(s) of the topic's spectrum, not simply "the best
    written." Tag which pole (`pro` / `con`) each pick represents.
  - `Tier 3 - Ordinary` = the CONSENSUS pool. Kept deliberately, not discarded as boring - it
    shows what most people actually think.
  - `Tier 1 - Viral` / `Tier 2 - Strong` = strong but not the most extreme; backup pole picks.
  - `Tier 4 - Rubbish` = genuinely low value, unreadable or duplicate.
- **Gossip and redundancy submissions get their OWN folder, `Inside Track - Gossip &
  Redundancy`** (same folder as the earlier `Redundancies & Breaking News` name - existing
  topic folders keep that older name, no rename needed there), separate from the week's
  question folders. Every batch contains some, and they must not be mixed into topic tiers -
  they feed The Inside Track segment, never a Big Conversation piece.
- Screenshots are MOVED into topic/tier folders during sorting, then COPIED (never moved
  again) when the `big-conversation` skill maps them to editorial paragraphs.
- RED HOT and Tier 1/2 picks must be verified verbatim against the actual images, not
  filenames.

## Sub-agent hygiene

Parallel classification sub-agents must write ALL intermediate outputs (TSVs, notes) inside
this project folder (e.g. a `_work/` subfolder), never to /tmp - /tmp writes hit permission
denials and stall the whole batch.

## Voice reminders (full rules live in the skill's references)

Never reference that the community "wrote in" or mention screenshots in prose; screenshots
complement the prose with a different POV, never restate it; no em dashes.
```

- [ ] **Step 2: Verify.**
```bash
diff "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md.bak-20260714" \
     "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md"
```
Confirm the diff shows only the intended rewrite (title dash, standing-rules section, the new pointer line) and nothing else moved or was deleted (the "Sub-agent hygiene" and "Voice reminders" headings/content should be present and otherwise unchanged apart from the dash-to-plain-word normalisation already in those sections).

---

### Task 4: Recalibrate `big-conversation/SKILL.md`'s screenshot selection

**Files:** `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md`.

**Interfaces:** consumes the corrected tier meanings from Task 2/3. This is the file that actually performs the paragraph-assignment the spec asks about - confirmed already built (see "Findings from exploration" #2) - so this task recalibrates its SELECTION CRITERION, it does not rebuild the assignment mechanism.

- [ ] **Step 1: Front-matter description.** Replace:

Old:
```
description: Use when Victor wants to turn a sorted Instagram-DM campaign topic folder into a "THE BIG CONVERSATION" community thought-leadership post — analyses the responses for trends/angles across all sides, drafts the piece in the exact house voice, and selects + maps + copies the red-hot screenshots that sit under each paragraph as community submissions. Invoke with a topic folder name (e.g. "Career Pivoting").
```

New:
```
description: Use when Victor wants to turn a sorted Instagram-DM campaign topic folder into a "THE BIG CONVERSATION" community thought-leadership post, once the screenshot-sort skill has already sorted it. Analyses the responses for trends/angles across all sides, drafts the piece in the exact house voice, and selects + maps + copies screenshots (the extreme of each end of each paragraph's angle, plus a consensus middle pick) that sit under each paragraph as community submissions. Invoke with a topic folder name (e.g. "Career Pivoting").
```

- [ ] **Step 2: Step 2's "Ensure fuel exists" bullet.** Replace:

Old:
```
  - Prefer the RED HOT + Tier 1/Tier 2 screenshots as the core; pull from lower tiers only to
    round out an angle.
```

New:
```
  - Pull from ALL tiers deliberately, not just the top: the RED HOT/Tier 1/2 pool gives you
    the viral-extreme poles, and Tier 3 gives you the consensus middle. A fuel file that only
    quotes RED HOT material will be all-extreme and will miss the consensus view the
    screenshot-sort skill has already identified in Tier 3 - include it.
```

- [ ] **Step 3: Replace the entire Step 5 section.** Old text:

```
### 5. Select & map the screenshots
For **each paragraph**, pick the 1–3 submissions that sit under it as community evidence.

- **Complementary POV, not an echo (the key rule).** The screenshot must NOT just restate
  the paragraph's takeaway — that's redundant and flat. Pick a shot that adds a *different
  angle* to the same theme: the lived/visceral version of a structural claim, the hidden
  motive behind it, the insider/manager's chair, the human aftermath, the one dissenting
  voice, the concrete outcome. The editorial argues; the shot shows a facet the prose
  deliberately left for the image to carry.
  - e.g. paragraph says "a short PIP is really a paper trail" → don't pick another "3 weeks
    is too short" quote; pick the one naming the *motive* ("they're running out of work and
    need to reduce numbers before year end").
  - e.g. paragraph says "surviving it just buys you a worse version of the role" → pick the
    *aftermath* ("still have ptsd"), not someone re-explaining the relationship damage.
- Because of this, the strongest shots are often NOT the most on-the-nose ones. The pure
  "confirms the thesis" quotes (e.g. four HR people all saying "3 months is best practice")
  usually get dropped — one is plenty as an authority anchor; the rest just echo.
- Prefer the `🔥 RED HOT Top N` picks and Tier 1/2, but reach into lower tiers or the main
  folder when a less-hot shot offers a better *angle*. Angle beats heat for this job.
- **Verify each quote verbatim against the actual image** (Read the PNG) before using it —
  the fuel quotes are agent transcriptions and can drift. Drop anything you can't confirm.
- Spread shots across paragraphs; don't stack them all on paragraph one.
- Produce a `BUILD:`-style map (like the carousel outline): for each paragraph, the
  filenames + handles in rank order, each with a one-line note on *what POV it adds*.
```

New text (replaces the above in full):
```
### 5. Select & map the screenshots
For **each paragraph**, pick the submissions that sit under it as community evidence. The
target shape per paragraph is the paragraph's own mini-spectrum: the extreme of each end of
whatever this paragraph's angle splits into, plus one consensus anchor from the middle. Not
just supporting evidence - the poles and the centre.

- **Extremes of each end + the consensus middle (the key rule, corrected 14 Jul 2026).** If
  the paragraph argues a view with two sides (most do), pick:
  1. the pole-tagged `RED HOT Top N` / Tier 1/2 pick that best represents ONE extreme of this
     specific paragraph's angle (`pole: pro` in the sort manifest),
  2. the pole-tagged pick that best represents the OPPOSITE extreme (`pole: con`), if the
     paragraph's angle genuinely has an opposing pole - not every paragraph will,
  3. one `Tier 3 - Ordinary` (consensus) pick as the anchor - what most people actually said,
     sitting between the two extremes.
  A paragraph that only pulls quotes from the same side, all "confirms the thesis," is not
  done - go back to the folder's other pole or the consensus pool.
  - e.g. a paragraph arguing "a short PIP is really a paper trail" pairs: the extreme cynical
    take naming the *motive* ("they're running out of work and need to reduce numbers before
    year end") as one pole, a genuine "mine was handled fairly and I learned from it" as the
    opposite pole if one exists in the folder, and an ordinary "3 weeks felt tight but doable"
    as the consensus anchor.
  - e.g. "surviving it just buys you a worse version of the role" pairs the extreme aftermath
    quote ("still have ptsd") against, if present, an extreme "came out better, got promoted
    within a year" counter-pole, plus an ordinary "it was rough but I'm fine now" consensus
    pick.
- The screenshot must still not just restate the paragraph's takeaway word for word - even
  the consensus pick should be the median REAL reply, not a paraphrase of the prose.
- Draw the poles from `RED HOT Top N` first, Tier 1/2 as backup if a pole's RED HOT pick is
  already used elsewhere in the piece. Draw the consensus anchor from `Tier 3 - Ordinary` -
  that is now the consensus pool by design (see `../screenshot-sort/SKILL.md`), not a last
  resort.
- **Verify each quote verbatim against the actual image** (Read the PNG) before using it -
  the fuel quotes are agent transcriptions and can drift. Drop anything you can't confirm.
- Spread shots across paragraphs; don't stack them all on paragraph one.
- Produce a `BUILD:`-style map (like the carousel outline): for each paragraph, the filenames
  and handles in rank order, each labelled `pole: pro` / `pole: con` / `consensus`, with a
  one-line note on what it adds. Published Flat White typically runs about one screenshot per
  paragraph (see `data/beehiiv_fw_ground_truth.json`); the ranked list here is the option set
  Victor picks the actual one from, not all of which ship.
```

- [ ] **Step 4: "Inputs & conventions" tier-folder line.** Replace:

Old:
```
- A topic folder usually contains a `🔥 RED HOT Top N` subfolder (the best, pre-verified
  submissions), tier folders (`Tier 1 - Viral` … `Tier 4 - Rubbish`), and sometimes
  `_EDITORIAL screenshots` / `_EDITORIAL_IMAGE_PACKS`. Screenshots are one message per PNG.
```

New:
```
- A topic folder usually contains a `RED HOT Top N` subfolder (the VIRAL EXTREME pole picks,
  pole-tagged, pre-verified), tier folders (`Tier 1 - Viral` and `Tier 2 - Strong` as backup
  pole picks, `Tier 3 - Ordinary` as the CONSENSUS pool, `Tier 4 - Rubbish` as low value), and
  sometimes `_EDITORIAL screenshots` / `_EDITORIAL_IMAGE_PACKS`. Screenshots are one message
  per PNG. Full sort rubric: `../screenshot-sort/SKILL.md` (run before this skill, for every
  batch).
```

- [ ] **Step 5: Verify.**
```bash
diff "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md.bak-20260714" \
     "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md"
```
Confirm the diff touches only the four passages above (front matter, Step 2 bullet, Step 5, "Inputs & conventions" tier line) and that Steps 1, 3, 4, 6 and the "Notes" section are byte-identical to before.

---

### Task 5: Rubric self-check (test a)

**Files:** none written; reads Tasks 2-4's output.

- [ ] **Step 1: Walk the corrected-parameters list from the brief and confirm each is textually present** in the new/edited files:

| Corrected parameter | Must appear in |
|---|---|
| VIRAL EXTREME defined as the "wtf, share this" pole, not generic best-of | `screenshot-sort/SKILL.md`, `output/CLAUDE.md` |
| CONSENSUS / Tier 3 kept deliberately, not discarded as boring | `screenshot-sort/SKILL.md`, `output/CLAUDE.md`, `big-conversation/SKILL.md` |
| Extreme of EACH END of a view's spectrum, not just supporting evidence | `screenshot-sort/SKILL.md` (pole tagging), `big-conversation/SKILL.md` Step 5 |
| Gossip AND redundancy routed to The Inside Track, not Big Conversation | `screenshot-sort/SKILL.md`, `output/CLAUDE.md` |
| T1/T2/T3 labels kept as a secondary pool, only the feeding criteria fixed | `screenshot-sort/SKILL.md`, `output/CLAUDE.md`, `big-conversation/SKILL.md` |
| Paragraph assignment at Big-Conversation process time, confirmed existing and now using the corrected criterion | `big-conversation/SKILL.md` Step 5 |

Run a grep per row, e.g.:
```bash
grep -n -i "viral extreme" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md"
grep -n -i "consensus" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md"
grep -n -i "inside track" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md"
grep -n -i "pole" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md"
```
Every grep must return at least one hit in each listed file. If any row comes back empty, go back and add the missing wording before proceeding - this is the "test" for a markdown skill: does the rubric actually say the thing, not just imply it.

- [ ] **Step 2: Confirm the tier LABELS themselves are unchanged** (folder-naming compatibility):
```bash
grep -c "Tier 1 - Viral\|Tier 2 - Strong\|Tier 3 - Ordinary\|Tier 4 - Rubbish" \
  "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md"
```
Expect all four label strings present.

---

### Task 6: Dry-run validation against a real folder (test b)

**Files:** `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/_work/screenshot_sort_dryrun_2026-07-14.md` (new).

**Interfaces:** consumes the real, already-sorted `output/Kids in the Office/` folder (17 RED HOT, 14 Tier 1, 34 Tier 2, 26 Tier 3, 3 Tier 4, per the exploration findings) and the already-produced `_KIDS_OFFICE_BIG_CONVERSATION.md` as the comparison point. This is NOT a re-sort of the folder (existing sorted folders are not touched, per Global Constraints) - it is a sample-and-reclassify check that the NEW rubric would have produced sensible buckets, done by reading a sample of the actual PNGs.

- [ ] **Step 1: Sample the folder.** Read a spread of roughly 15-20 screenshots across the existing tiers: 5 from `🔥 RED HOT Top 22`, 4 from `Tier 1 - Viral`, 4 from `Tier 2 - Strong`, 4 from `Tier 3 - Ordinary`, 2 from `Tier 4 - Rubbish`.

- [ ] **Step 2: Re-classify each sampled screenshot by eye against the new rubric.** For each: does it read as a VIRAL EXTREME pole (and if so, which pole - pro "kids belong at work" or con "this is a liability/disruption"), a CONSENSUS/ordinary reply, backup-tier strong-but-not-extreme, or genuinely low value? Would it have landed in the same bucket the old sort put it in, or a different one under the corrected criteria?

- [ ] **Step 3: Cross-check against the already-produced piece.** Read `_KIDS_OFFICE_BIG_CONVERSATION.md`'s `BUILD: paragraph → screenshot map` (already has real content - 4 paragraphs, each with a primary pick + 2-3 alternates). For at least 2 of its 4 paragraphs, check whether the current primary + alternates already happen to include something extreme-leaning and something consensus-leaning (some may, by luck, since "complementary POV" sometimes converges with pole/consensus logic), or whether the new Step 5 rubric would have picked differently - e.g. would it have pulled in an opposite-pole shot the old "complementary POV, not an echo" logic skipped past.

- [ ] **Step 4: Write up the findings.** Write `_work/screenshot_sort_dryrun_2026-07-14.md`:
  - One line per sampled screenshot: filename, old tier, new classification (pole/consensus/backup/low-value), agree or disagree with the old placement.
  - A short verdict: does the corrected rubric produce sensible buckets on this real folder, or does anything in the rubric text need adjusting before it's trusted (e.g. if the "kids in the office" topic turns out to have no genuine con-pole material in the sampled RED HOT/Tier 1/2 shots, note that as a finding rather than forcing one).
  - For the 2 cross-checked paragraphs: whether the new pole/consensus criterion would change the pick, and if so, name the alternate that should replace the current primary.
  - Australian spelling, no em dashes, under roughly 400 words.

- [ ] **Step 5: Verify the file exists and is non-trivial.**
```bash
wc -w "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/_work/screenshot_sort_dryrun_2026-07-14.md"
```
Expect a non-zero, non-tiny word count (a real write-up, not a stub).

---

### Task 7: No-em-dash check (test c)

**Files:** all four touched/created files.

- [ ] **Step 1: Grep the new file for em dashes (must be zero).**
```bash
grep -c $'—' "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/screenshot-sort/SKILL.md"
```
Expect `0`.

- [ ] **Step 2: Grep the dry-run report (must be zero).**
```bash
grep -c $'—' "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/_work/screenshot_sort_dryrun_2026-07-14.md"
```
Expect `0`.

- [ ] **Step 3: Grep the two edited legacy files and confirm the count did not INCREASE** (scope decision from Global Constraints: pre-existing em dashes elsewhere in these files are out of scope for this increment; the check here is that nothing new was introduced):
```bash
grep -c $'—' "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/CLAUDE.md"
grep -c $'—' "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/big-conversation/SKILL.md"
```
`output/CLAUDE.md`: expect `0` (the full-file replacement in Task 3 removed all of them - the old file had 3, the new file has none, since the whole file was rewritten). `big-conversation/SKILL.md`: expect strictly less than the pre-edit count of 20 (the four rewritten passages should not reintroduce any) - if it is still 20 or more, re-check the four passages from Task 4 for a missed dash.

---

## Whole-increment verification

1. `ls "/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/.claude/skills/"` shows both `big-conversation/` and the new `screenshot-sort/`.
2. Task 5's rubric-coverage table: every row's grep returned a hit.
3. Task 6's dry-run report exists, is a real write-up (not a stub), and states a clear verdict on whether the corrected rubric produces sensible buckets on a real folder.
4. Task 7's em-dash checks: `0` in the two new files, and no increase in the two edited legacy files.
5. `output/CLAUDE.md.bak-20260714` and `big-conversation/SKILL.md.bak-20260714` exist as the rollback path (no git repo at either location).
6. Nothing under `/Users/victornguyen/Documents/MISC/FW` changed. Nothing in `screenshot_dms.py`, `scraper.py`, `capture.py`, `browser.py`, `config.py` changed.
7. Report to Victor in plain terms: which three files changed (new sort skill, updated sort-rules memory, recalibrated Big Conversation paragraph-pairing), that nothing is deployed or pushed anywhere (no git repo, no server involved), that the existing already-sorted topic folders were left untouched, and that the dry run against "Kids in the Office" is the evidence the new rules make sense before the FW control room starts calling this skill automatically in Increment 4.

## Notes for later increments (not this plan)

- Increment 4 (Big Conversation pipeline) is what actually calls `screenshot-sort` and `big-conversation` from the FW dashboard, serves the sorted PNGs, and shows the topic bank + paragraph groupings on screen. This increment only makes the rules those calls will follow correct.
- Increment 5 (The Inside Track) is what builds the UI to select from `Inside Track - Gossip & Redundancy` and write items up - this increment only makes sure that folder is fed correctly and consistently named going forward.
