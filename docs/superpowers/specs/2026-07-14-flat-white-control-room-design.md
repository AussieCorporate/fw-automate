# Flat White Control Room — design spec

**Date:** 14 July 2026
**Status:** design agreed with Victor via clickable mockup (many rounds). Ready to turn into build plans.

## One line

Rebuild the Flat White dashboard into a control room that triggers every scattered producer (Instagram DM screenshotter, Trading Strategy research bank, the in-dash generators) and assembles the weekly edition from one screen — so Victor stops running five Claude CLIs and retyping the same weekly prompts. It stays its own app on port 8500, embedded in PS Dash's "Flat White" workspace.

## Why

Flat White production is scattered across projects, each triggered by hand-typed Claude prompts weekly. The dashboard already generates some segments in-dash but the real Big Conversation, Brains Trust, and screenshot sorting happen elsewhere, by hand. This unifies triggering + collecting + assembly, and builds a content bank in advance. Everything generated is benchmarked against the real published corpus (`data/beehiiv_fw_ground_truth.json`, 10 real editions), the same "measure against what we actually ship" discipline that fixed PS selection.

## Layout — master/detail, not tabs

- **Left: a white sidebar card = the edition's running order.** A vertical list of segments, each a row with a status dot (ready / not ready / manual) and drag handle. Drag to reorder (Big Conversation sits last by default). Below a divider: "Content bank" and "Sources" nav items. Bottom: an "Assemble to beehiiv" action.
- **Right: the selected section as its own full page.** Each section is a working surface: its inputs, a generate/process action, an editable output (textarea), a benchmark chip, and a "Mark ready" button. No accordions.
- **iOS-minimal styling**, matching PS Dash's token system (soft grey bg, one accent, white cards, hairline separators). Restrained copy: one short lead line per page, not a paragraph.

## The segments (each a page)

Default running order (draggable): Editorial intro · Brains Trust · PS Top Picks · Inside Track · Stress Index (Pulse) · Off the Clock · Thread of the Week · Big Conversation. (The real published order also carries template furniture — sponsor when present, Odd Picks, Feedback — handled at assembly, not as work pages.)

1. **Editorial intro** — writes LAST and is GATED: the "Write" action is disabled until every other segment is marked ready. Has a "big story of the week" input (the open hook Victor nominates). Structure: biggest-news-story hook -> the Big Conversation -> the three things covered. Uses the `flat-white-intro` skill (already built, from the 10 real intros). Output editable, then mark ready.

2. **The Brains Trust (= Economic Scoop, one segment, two names)** — surfaces recommended ANGLES from the Trading Strategy research bank across the LAST 3 WEEKS (not just this week; the EV piece used two weeks). Victor picks an angle; it consolidates the relevant research and drafts. Human picks, machine drafts. The Friday research digest email is KEPT (its ~5 bulge-bracket picks are what's used); the dash surfaces those same picks on screen. The old auto "economic flags/indicators" form is retired.

3. **PS Top Picks** — FIX the current gap: it excludes FEATURE STORIES (a feature has no click-link since the story is inline, so it never shows in click data, and the "top clicks" are just other links in the article). Must scrape EVERYTHING into a SELECTABLE list, INCLUDE feature stories (manually flagged/included), let Victor tick what makes the cut, then format into the previous Flat White Top Picks block. Source: beehiiv click data + the PS feature stories from Shell Bot.

4. **The Inside Track** — its OWN section. SELECT from the folder of GOSSIP / REDUNDANCY screenshots (routed out of the Big Conversation sort). Tick which run, then write them up.

5. **Stress Index (Pulse)** — already generates in-dash. Editable output + regenerate + mark ready.

6. **Off the Clock** — REBUILD as the 5 SEPARATE categories (Eat/Watch/Read/Wear/Go), not consolidated into one. Each shows one pick; the AI scraped 3 per category — "Swap" chooses another; plus a custom add (URL + content -> it writes that category's blurb). Sourcing biased to NICHE small businesses that benefit from coverage, not big outlets (Concrete Playground) that already get mass coverage.

7. **Thread of the Week** — retire only the dead Reddit SCRAPE; KEEP the segment. Victor pastes a thread (title, url, preview, top comment); the dash formats it into the real FW block: an H4 bold-italic HYPERLINKED title `#### [_**title**_](url)`, the preview, then the quoted top comment. Marks ready and inserts to the draft.

8. **The Big Conversation** — LAST (submissions close Saturday 9am after Friday's campaign). Flow:
   - Topic BANK: folders the AI sorted and NAMED, not yet published. Archive action for done ones.
   - Pick a topic -> PROCESS: runs the `big-conversation` skill on that folder, using the past published editions as corpus, writing the piece FIRST.
   - THEN screenshots appear, ALREADY AUTO-PAIRED into the paragraphs of the written piece (the AI assigns the tier-sorted screenshots to paragraphs at process time — confirm the skill does this, build it if not). Each paragraph shows its paired screenshots; the extreme supports/hooks that paragraph.
   - Only the VIRAL EXTREME pool is shown by default (to catch anything compelling the paragraphs missed). T1/T2/T3 are hidden behind a "show tier pool" toggle, used only when a paragraph pick isn't compelling enough.

## The screenshot pipeline (Instagram DM screenshotter)

- Weekly: (1) scrape all Instagram DM screenshots (Friday campaign, submissions close Sat 9am, 24h story window); (2) AI first-pass sorts against the Friday campaign's 3 questions into: VIRAL EXTREME, T1, T2, T3, and routes GOSSIP/REDUNDANCY to the Inside Track folder; (3) folders become Big Conversation topic candidates (AI-named) or add to the bank.
- The SORT SKILL needs REBUILDING — current "red hot / tier 1-4" parameters are wrong. Correct intent: keep the VIRAL/"wtf, share this" EXTREMES; keep the neutral CONSENSUS (it forms the view of consensus); for a chosen Big Conversation view, pair screenshots that are the EXTREME OF EACH END of that view's spectrum + the consensus middle; route gossip/redundancy to Inside Track. At Big-Conversation process time, the AI assigns the sorted screenshots into the written paragraphs.
- Displaying the actual screenshot PNGs is worth it because the AI sorts first (the time-saver); the dash serves the PNGs and Victor drags to correct.

## Sources (the control panel)

One page listing every producer, each triggerable + collectable here:
- Instagram DM screenshotter (Big Conversation + Inside Track; Fri campaign -> Sat 9am close).
- Trading Strategy research bank (Brains Trust; banks across weeks; Friday digest email kept; surfaces top-5 picks).
- Flat White in-dash (Pulse / Off the Clock / Top Picks / Editorial; model picker live).
- Reddit scraper — dead, retire the job; Thread stays manual.

## Content Bank

Pieces produced ahead of time (Big Conversation pieces, Brains Trust drafts), pulled into a future edition when needed. Shared with the future TAC Instagram tab.

## Assembly

"Assemble to beehiiv" builds the daily FW draft in the current running order. Same block-level insert approach proven for PS (Design B: the dash formats the blocks and the Claude/beehiiv integration inserts them; raw-API content write is Enterprise-gated). Every generated segment is benchmarked against `data/beehiiv_fw_ground_truth.json` for length/register.

## Skills

- **`flat-white-intro`** — BUILT (from 10 real intros). Needs one calibration tweak to the biggest-news-hook-then-preview structure Victor confirmed.
- **Screenshot sort skill** — REBUILD per the parameters above (viral extremes + consensus + spectrum-extreme paragraph pairing + gossip routing). Self-contained, unblocks the Big Conversation pipeline.

## Cadence

Research banks all week (Brains Trust ongoing). Most segments Friday afternoon. Big Conversation last, after Saturday's submissions. Nothing auto-publishes; Victor selects and assembles.

## What we reuse

- FW's existing `_proceed_*` generators (Pulse, Big Conversation-in-dash [legacy, see note], Finds/Top Picks, Off the Clock, Editorial) and the now-working model picker.
- The real published corpus `data/beehiiv_fw_ground_truth.json` for benchmarking + skill calibration.
- Integration surfaces from the survey: Trading Strategy `data/carousels/<YYYYMMDD>/_candidates.json` + `trading_strategy.db` (read-only); Instagram screenshotter `output/` folders + `big-conversation` skill; beehiiv MCP for assembly.

**Naming trap:** FW's own `_proceed_big_conversation` generates from FW's Reddit/GNews `curated_items`, which is NOT what ships. The published Big Conversation comes from the Instagram `big-conversation` skill. The control room routes Big Conversation to the Instagram pipeline, not FW's legacy generator.

## Build order (each its own plan)

1. **Shell** — rebuild `flatwhite/dashboard` as the master/detail running-order layout (left sidebar draggable + status, right per-section page), iOS styling, replacing the current tab nav. Sections render existing content as pages.
2. **The five in-dash section pages** — Editorial (gated + big-story), Off the Clock (5 cats + swap + custom), Top Picks (features + selectable list), Pulse (edit), Thread (paste -> FW block). Each generate/process -> edit -> mark ready.
3. **Screenshot sort skill rebuild** (self-contained; unblocks 4/5).
4. **Big Conversation pipeline** — topic bank (AI-named, archivable), process runs the skill, screenshots auto-paired to paragraphs, viral pool + tier toggle, serve PNGs.
5. **Inside Track** — gossip/redundancy folder selection -> write up.
6. **Brains Trust / research bank** — surface multi-week angles, pick -> consolidate + draft; keep digest email.
7. **Assembly + Content Bank** — assemble running order to beehiiv (Design B), produce-ahead bank.

## Cross-cutting

- No em dashes in reader-facing copy; Australian spelling; "percent" as %.
- FW deploy is Victor's (GCP VM `flatwhite`); every increment built + tested locally on a branch, not merged/deployed without him.
- Runs on FW's venv (`.venv/bin/python`, system 3.9 breaks it). Tests with FW's pytest.

## Out of scope (separate builds)

- The TAC Instagram content calendar (third top tab): the farm loop, 118-topic bank, quarterly planner. Documented in memory `tac-instagram-content-calendar.md`. Build AFTER this.
- Rebuilding the external producers' internals (they're triggered/read, not rebuilt).
