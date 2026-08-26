# TAC Instagram tab - design spec

**Date:** 26 August 2026
**Status:** Draft for Victor's review
**Repo:** FW (Flat White dashboard)

## One line

Rebuild Victor's TAC Instagram content-calendar spreadsheet as a third working screen inside the Flat White dashboard: a "what to do today" farm loop, a searchable bank of 118 content topics, and a week-by-week posting calendar with a quarterly survey/event planner behind it. It replaces the spreadsheet as the place Victor actually works from.

## Why

Victor showed the spreadsheet on 14 July 2026 and asked for it as an interactive tab (memory: `tac-instagram-content-calendar.md`). His stated problem with the spreadsheet: "not interactive, too many tabs/slides for one person to manage." The Flat White control room (the master/detail dashboard rebuild) shipped in July, which was the agreed blocker - this tab was parked until then. It is now unblocked.

The source spreadsheet is real and lives at:

`/Users/victornguyen/Downloads/TAC_Instagram_Content_Calendar_2026.xlsx`

Confirmed by opening it (26 Aug 2026): five tabs - Calendar (170 rows), Topic Bank (118 real topic rows), Quarterly Planner (12 real campaign/event rows across Q2/Q3 2026), Content Bank (currently empty, ready for use), How To Use (the plain-English rulebook the spec below is drawn from). This matches the memory file's description exactly, including the "118 topics" figure.

## Architecture - same shape as Flat White's control room

Same rules as the rest of the dashboard, spelled out plainly:

- One app, one server: FastAPI backend `flatwhite/dashboard/api.py`, one static single-page frontend `flatwhite/dashboard/static/index.html` (no build step, no framework - plain JS).
- One database: SQLite at `data/flatwhite.db`, schema defined in `flatwhite/db.py`'s single `SCHEMA_SQL` block (no separate migrations folder in this project - new tables just get added there behind `CREATE TABLE IF NOT EXISTS`).
- Master/detail layout: a white sidebar card on the left listing the screens in this workspace, the selected screen as a full working page on the right. Same CSS tokens already defined in `index.html`'s `:root` (soft grey background, one purple accent, white cards, hairline separators) - reused verbatim, no new visual language.
- Anything that needs a Claude *skill* (not a plain text box) runs headless through the existing `flatwhite/dashboard/skill_runner.py` - the same mechanism that already runs the Big Conversation and screenshot-sort skills for Flat White. No new subprocess/threading code gets written for this tab; it reuses that engine.
- Local-first, same as the rest of FW: runs on Victor's Mac at `.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500`. Nothing here needs the (currently unreachable) GCP VM.

**What's new, structurally:** today, opening the FW dashboard drops Victor straight into the Flat White running order - there is no top-level switcher inside the app itself (PS Dash, a separate project, provides an outer switcher between "PS Dash" and "Flat White" workspaces by embedding this app in an iframe). This spec adds a **second workspace inside the FW app itself**: a small switcher at the very top of the page, "Flat White | TAC Instagram". Clicking it swaps the left sidebar and right pane to a different set of screens, using the exact same `.side`/`.main`/`.page` layout classes the running order already uses. The Flat White running order's own code and behaviour do not change.

## The screens, in plain English

Opening "TAC Instagram" shows a left sidebar with five items: **Today**, **Calendar**, **Topic Bank**, **Quarterly Planner**, **Content Bank**. Clicking one shows that screen on the right.

### 1. Today (opens by default)

This is the "what do I do right now" screen - it exists so Victor never has to remember the weekly rhythm himself.

It shows today's date and day of the week, then a short checklist of what that day calls for, straight from the spreadsheet's own rulebook:

- **Monday** - post a submission-question story at 9am to farm the week's theme.
- **Tuesday** - 9am newsletter story with the Flat White link, 2pm a follow-up farm question, 2:10pm The Inside Track carousel, 2:30pm the best community submissions carousel.
- **Wednesday** - 11am Big Conversation carousel on the most topical issue.
- **Thursday** - 12pm a meme/relatable carousel, kept light, for shares.
- **Friday** - three Open Floor story questions at 9:00/9:05/9:10am (three angles on the week's theme), plus compiling last Friday's best replies into an 11:30am carousel.

Each checklist item is a card: a plain description of the task, a "Mark done" toggle, and - where the task needs a topic - the next unused topic from the Topic Bank, picked automatically (oldest topic number first, matching format where the slot calls for one, e.g. Wednesday only suggests topics whose Best Format includes "Big Conversation"). The card shows that topic's ready-to-post Community Question text with a "Copy" button, so Victor can paste it straight into an Instagram story with no retyping.

Below the checklist sits the five-step farm loop as a plain reminder strip: **Farm -> Collect -> Build -> Publish -> Repeat.** Once a topic has been marked "farmed" this week, a "Build carousel" button appears (see "What runs headless" below) - this is the one piece of real automation on this screen; everything else here is a checklist and a copy button, not a bot that posts things.

### 2. Topic Bank

A searchable list of all 118 topics. Filters across the top: Content Pillar (Work-Life Balance, Money & Salary, DEI & Fairness, Workplace Culture, Career & Progression, Recruitment & Hiring, Office Life, Leadership & Management, Tech & Future of Work), Best Format, Engagement Level, and Used? (yes/no).

Each row shows the topic name, format, pillar and engagement level. Clicking a row expands it to show the Community Question (the exact text to post as the farm prompt) and the TAC Thought Leadership Answer (the drafted carousel copy, already written for most of the 118). A "Mark used" button sets Used = Yes and stamps today's date - the same manual step the spreadsheet's "Repeat" step describes. An "Add topic" form at the bottom lets Victor add new ones as he thinks of them, in the same shape as the existing 118.

### 3. Calendar

A week-by-week list, grouped exactly like the spreadsheet's "WEEK 1 · 11 May – 15 May 2026" bands. Each row: date, day, post type, content pillar, caption/hook, story CTA + link, Canva project name, visual/asset note, collab/tag, publish time, status, notes - the same columns as the spreadsheet, editable inline.

Status is a dropdown with five options and the spreadsheet's own colour meaning kept: **Not Started** (grey - nothing planned yet), **In Progress** (yellow - caption or Canva design underway), **Scheduled** (blue - loaded into the scheduling tool), **Published** (green - live; add the engagement note here), **Skipped** (red - decided not to post, note why).

An "Add row" button covers the ad-hoc cases the spreadsheet's rulebook already names: breaking news (bumps Wednesday's Big Conversation, moves the planned piece to next week), partner promo (a new row on any day, Collab column holds the partner handle), event recap (a Reel row within 48 hours of the event, plus 2-3 promo story rows two weeks before it, timed off the Quarterly Planner).

First build ships this as a plain filterable list, not a drag-and-drop board - the memory notes a kanban-style board as a future ambition; that's flagged as a later enhancement below, not in scope for the first version, so the first working screen ships sooner.

### 4. Quarterly Planner

Campaigns and events grouped by quarter ("Q2 2026 · APR – JUN"), each with: name, type (Survey Campaign / Event), launch date, close/event date, results-publish date, a sponsor yes/no flag, and notes. Add/edit form matches those columns.

Any row of type "Survey Campaign" gets a **"Generate survey week"** button. Clicking it reads that row's launch date and writes the standard five-row playbook straight into the Calendar for that week: Monday launch carousel + story, Tuesday newsletter feature, Wednesday Big Conversation tied to the survey topic, Thursday reminder meme, Friday Open Floor questions farming supporting stories. This is the one piece of auto-population in the tab - it exists so Victor doesn't retype the same five rows by hand every time a survey launches, which the spreadsheet's own "How To Use" tab calls out as the standing rule ("Full survey week playbook is in Quarterly Planner tab").

### 5. Content Bank

Reuses the Content Bank Flat White's control room already built - same database table, same screen pattern, just filtered to TAC Instagram's own pieces (built-ahead carousels, evergreen topics). This was already promised as shared in the control-room design spec ("Shared with the future TAC Instagram tab"), so this build honours that rather than duplicating a second content bank.

## How the farm loop actually works, day to day

Walking Victor's own week end to end, in the words of the spreadsheet's rulebook:

1. **Farm** - Monday or Friday, post a question story. The topic comes from the Topic Bank tab (the Today screen suggests it automatically).
2. **Collect** - over the next 24-48 hours, DM responses and story replies come in. This uses the exact same Instagram DM screenshotter pipeline Flat White's Big Conversation and Inside Track already use (`~/Documents/MISC/instagram-dm-screenshotter/`), including its screenshot-sort skill that already runs headless through `skill_runner.py`. Nothing new gets built for collection - TAC Instagram just reads the same sorted output folders.
3. **Build** - a carousel gets built from the best submissions. This is next week's Tuesday or Wednesday content. This is where the new headless run happens (below).
4. **Publish** - post the carousel by hand in Instagram, caption drives to the newsletter ("link in bio"). If it's evergreen, add it to the Content Bank.
5. **Repeat** - mark the topic Used = Yes on the Topic Bank, pick the next one, cycle continues.

Nothing in this tab posts to Instagram automatically. There is no Instagram posting API wired up, and none is proposed - Victor still opens the Instagram app and posts by hand. The dashboard's job is telling him what today calls for, holding the topic bank and calendar so nothing gets forgotten, and doing the two genuinely slow manual jobs (drafting carousel copy, running the survey-week rows) for him.

## What runs headless via skill_runner (and what's already built vs. new)

- **Already built, reused as-is:** the screenshot-sort skill that sorts Instagram DM screenshots into viral-extreme/tier pools and routes gossip/redundancy out - this already runs headless for Flat White's Big Conversation and Inside Track segments. TAC Instagram's "Collect" step reads the same sorted folders; no changes needed here.
- **Already built, cross-linked not duplicated:** for a Wednesday-slot topic (Big Conversation format), the Today screen points Victor at Flat White's own Big Conversation screen for that topic rather than re-running that pipeline inside TAC Instagram. One Big Conversation pipeline, not two.
- **New:** the "Build carousel" action on the Today screen runs the `community-carousel` skill (`~/.claude/skills/community-carousel/SKILL.md`) headless through `skill_runner.py`, pointed at the topic's sorted screenshot folder. It writes back an ordered slide-by-slide carousel script (hook slide, A/B contrast pairs, a closing ambiguous pair) as editable text - the same "process, wait, read back the real skill's output" pattern already proven for Big Conversation. Victor edits the text, then builds the actual visual carousel in Canva by hand - Canva stays fully manual, matching how every other segment in this dashboard already treats it (the Calendar's own "Canva Project" column is a name, not a link to an automated builder).

## What's shared with the rest of the dashboard

- **Instagram DM submission source** - same screenshotter project and output folders as Flat White's Big Conversation and Inside Track.
- **Content Bank** - same SQLite table (`content_bank`) and API (`POST/GET /api/content-bank`) Flat White already built, just a new `segment_type` value for TAC Instagram's pieces.
- **Design tokens** - same CSS custom properties already defined in `index.html`.
- **skill_runner.py** - same background-run engine, same polling endpoint (`GET /api/skill-run/{run_id}`) the frontend already knows how to poll.

## Cross-cutting rules

- No em dashes anywhere in the UI copy or generated text (house rule, all reader-facing and Victor-facing text).
- Australian spelling.
- Local-first: everything in this spec runs on Victor's Mac, same as the rest of FW. No dependency on the GCP VM.
- Every screen description above is written in plain English on purpose - Victor runs businesses, not code, and this tab is a working tool for him, not a technical console.

## Out of scope for this build

- A drag-and-drop kanban board for the Calendar (memory floats this as an ambition; the first build ships a filterable list with a status dropdown instead, to keep the build in small working pieces - this can be a later enhancement).
- Any Instagram posting/scheduling API integration. Posting stays manual, same as today.
- Video/Reel creation or editing tools. Reels are tracked as Calendar rows only.
- Rebuilding PS Dash (Shell Bot 2)'s outer workspace switcher to add a third top-level button. That is a different repository; see open questions.
- Rebuilding the screenshot-sort or Big Conversation pipelines. Both are reused exactly as Flat White already built them.

## Open questions

1. **PS Dash's outer switcher.** PS Dash (Shell Bot 2, a separate project on port 8080) is the "front door" Victor actually opens, and it currently embeds this FW app as its "Flat White" workspace via an iframe. This spec adds a switcher *inside* the FW app for "Flat White | TAC Instagram", which works today without touching PS Dash. Whether Victor also wants a third top-level button in PS Dash's own switcher (so "TAC Instagram" is reachable without first clicking into the Flat White iframe) is a Shell Bot 2 change, not covered by this spec or its plan.
2. **Calendar kanban board.** Scoped out of the first build (see above). Confirm the week-list-with-status-dropdown version is good enough day to day before a kanban rebuild gets planned.
3. **"Mark used" enforcement.** The spreadsheet runs on the honour system - nothing stops Victor marking a topic used before it's actually posted. This spec keeps that honour-system behaviour rather than adding an enforcement rule (e.g. requiring a matching Published Calendar row) that isn't in the original design. Flag if a harder rule is wanted.
4. **The source spreadsheet's home.** It currently lives in `~/Downloads`, which is not durable storage (files there get cleared). The plan below copies it into the FW repo's `data/` folder as the one-time import's canonical source. Confirm that's fine to keep in the repo (it contains no financial or personal data, just content planning text).
