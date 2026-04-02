# Dashboard Redesign — Newsletter-First Editor Dashboard

**Date**: 2026-03-26
**Status**: Approved
**Scope**: Complete dashboard redesign. Replace pipeline-oriented tabs with newsletter-section tabs. Each section follows RUN → SELECT → PROCEED pattern.

## Core Concept

The dashboard sidebar maps 1:1 to newsletter sections. Every section is independent and self-contained. You can run any section without touching others. Every section that generates content follows the same three-step pattern:

- **RUN**: Pull/scrape data for this section. Shows progress. Button lives inside the section, not on a separate pipeline tab.
- **SELECT**: Editor picks which items/signals/themes to feature. Checkboxes, pick-one, or manual entry depending on the section.
- **PROCEED**: Generate the newsletter output in TAC voice using the selected items. Output appears in an editable text area. Re-generate button available.

A **model selector dropdown** appears next to every PROCEED button. Default is pre-set per section (Gemini 2.5 Flash for data/classification work, Claude Sonnet 4.6 for editorial voice generation). Editor can override to any configured model before generating.

## LLM Model Configuration

**Defaults by section:**
- Classification/scoring tasks: Gemini 2.5 Flash (cheapest, fast)
- Editorial voice generation: Claude Sonnet 4.6 (better writing quality)
- Override: dropdown next to every PROCEED button lets editor switch model

**Supported providers (via API keys in .env):**
- `GEMINI_API_KEY` — Gemini 2.5 Flash
- `ANTHROPIC_API_KEY` — Claude Sonnet 4.6, Claude Haiku 4.5
- Additional providers added as needed (no speculative integrations)

**model_router.py changes:**
- Add Claude Sonnet/Haiku support via Anthropic SDK
- `route()` function gains an optional `model_override` parameter
- API endpoints accept optional `model` field in POST body
- Frontend dropdown populated from a `/api/models` endpoint that returns available models based on which API keys are configured

## Sidebar Structure

Top to bottom, matching newsletter order:

1. **Editorial** (hook/intro)
2. **Pulse** (AusCorp Live Pulse)
3. **Big Conversation** (main editorial piece)
4. **Whispers** (manual entry)
5. **The Lobby** (employer hiring data)
6. **Finds** (curated news items)
7. **Thread of the Week** (Reddit thread pick)
8. **AMP's Finest** (manual chart + generated commentary)
9. **Off the Clock** (lifestyle picks)
10. **Events** (manual event entry)
11. **Salary Vault** (placeholder, greyed out, not built)
12. **Assemble** (final preview + export)

**Removed tabs:** Pipeline, Curation, Feedback, Extraction Health. Pipeline RUN controls move into each section. Extraction health becomes a collapsible panel inside The Lobby. Feedback is removed (not needed for MVP). Curation is replaced by the per-section SELECT workflow.

## Section Specifications

### 1. Editorial (Hook/Intro)

The opening paragraph — "Good morning AusCorp..." — ties together the week's biggest story, the Pulse, and the overall mood.

**Depends on**: Other sections being completed first. Shows a banner "Complete other sections first" if no content has been generated yet.

**Display:**
- Summary cards showing what's been generated in other sections: Pulse score + direction, Big Conversation headline, top Whisper, top Find headline. Cards are grey/empty if section not yet done.
- Editable text area for the hook.

**Workflow:**
- Write manually in the text area, OR
- Click PROCEED to auto-generate based on the week's generated content (Pulse data, Big Conv headline, selected Finds, etc.)
- Model dropdown (default: Claude Sonnet)

**No RUN button** — this section consumes output from other sections, not raw data.

### 2. Pulse (AusCorp Live Pulse)

**RUN:**
- Pulls all 18 signals in parallel groups (same as current `cmd_ingest` Group 1 + Group 3 + Group 4 logic)
- Progress shown per signal group: "Pulling SEEK... done", "Pulling Google Trends... done"
- Calculates composite score after all signals are in

**Display (after RUN):**
- Composite score gauge: big number (0-100), direction arrow, delta from last week
- Signal interactions: highlight cards for any detected patterns (e.g. "Defensive mobility", "Salary squeeze")
- Anomalies: flagged inline with the signal table
- Full signal table: all 18 signals with columns: signal name, raw value, normalised score (0-100), WoW delta, area (labour market / economic / corporate stress). Sortable. Anomalies highlighted in amber/red.

**SELECT:**
- Checkboxes next to each signal row and each interaction card
- Pre-checked: top 3 biggest movers + any detected interactions
- Editor unchecks signals they don't want discussed, checks ones they do

**PROCEED:**
- Generates the Pulse narrative (4-6 sentences) focusing on the selected signals and interactions
- Output in editable text area
- Also generates 3 driver bullet points
- Model dropdown (default: Claude Sonnet)

### 3. Big Conversation

**RUN:**
- Scans all ingested data across the system: editorial sources (already pulled by Finds/Thread RUN), pulse signals, Reddit threads
- Uses LLM to identify the top 5 most significant stories/themes of the week
- Each candidate shows: headline, source, 2-line pitch (why it matters), supporting data points (links to signal data or editorial items)

**Display:**
- 5 candidate cards, ranked by significance
- "Add Custom" button at the top — opens a form to paste your own topic, data, links, and context

**SELECT:**
- Pick exactly one candidate (radio buttons), OR use the custom entry

**PROCEED:**
- Generates 3-4 paragraphs of editorial commentary in TAC voice
- Editable text area with re-generate button
- Model dropdown (default: Claude Sonnet)

### 4. Whispers

**Fully manual. No RUN or PROCEED.**

**Display:**
- List of whispers for this week. Each shows: text, confidence tag (green/yellow/red), edit/delete buttons.
- "Add Whisper" form at top: text area + confidence dropdown + Add button

**Output:** Whispers go directly into the newsletter as written. No LLM processing.

### 5. The Lobby

**RUN:**
- Pulls ATS data from 33 employers (same as current `pull_hiring_pulse()`)
- Progress shown per employer or as overall progress bar
- Shows extraction health inline: green dot = success, red dot = failed, with error detail on hover

**Display (after RUN):**
- **Auto-surfaced top movers** (top of section): 5 cards showing biggest gains and biggest cuts with delta percentages and context
- **Full employer table** (below): all 33 employers with columns: employer name, sector, ATS platform, role count, WoW delta, WoW delta %, seniority mix (junior/mid/senior/exec), new roles, stale roles. Sortable columns.
- **Extraction health panel** (collapsible): per-employer success/failure, carry-forward weeks, error messages

**SELECT:**
- Checkboxes on employer rows and top mover cards
- Pre-checked: auto-surfaced top 5 movers
- Editor picks 3-4 to feature

**PROCEED:**
- Generates The Lobby narrative based on selected employers and their movements
- Editable text area
- Model dropdown (default: Claude Sonnet)

### 6. Finds

**RUN:**
- Pulls editorial sources: Google News, RSS feeds, LinkedIn newsletters, podcasts, Reddit editorial
- Shows count of items pulled per source
- Classifies all pulled items (section assignment + 5-dimension scoring)

**Display (after RUN):**
- All non-discarded items sorted by weighted composite score
- Each item shows: title (linked to source URL), source tag, 1-line summary, relevance/novelty/tension scores as small badges
- Filter/sort controls: by section, by score, by source

**SELECT:**
- Checkboxes — pick 3-5 items to feature
- Each selected item gets an editable blurb field (pre-filled with the classified summary)

**PROCEED:**
- Generates polished Finds write-ups for each selected item in TAC voice
- Each write-up: headline + 2-3 sentence blurb + "Read more" link
- Editable text areas per item
- Model dropdown (default: Gemini Flash for blurbs)

### 7. Thread of the Week

**RUN:**
- Pulls Reddit threads from r/auscorp (may already be pulled by Finds RUN — if so, shows "Already pulled" and skips)
- Ranks threads by: relatability, shareability, discussion quality, comment engagement
- Fetches top comments for the top 5 threads

**Display:**
- Top 5 thread candidates with: title, subreddit, comment count, engagement score, top 3 comments preview, auto-generated editorial frame

**SELECT:**
- Pick one thread (radio buttons)

**PROCEED:**
- Generates Thread of the Week write-up: editorial frame + narrative + highlighted quote from comments + "Read the full thread" link
- Editable text area
- Model dropdown (default: Claude Sonnet)

### 8. AMP's Finest

**Fully manual input. PROCEED for commentary only.**

**Display:**
- Image upload/paste area for chart
- Text area: "Paste your data description or source notes here"
- Text area: "Any specific points you want the commentary to cover"

**PROCEED:**
- Generates 2-3 paragraphs of editorial commentary around the provided chart/data
- References the data points you provided
- Editable text area
- Model dropdown (default: Claude Sonnet)

### 9. Off the Clock

**RUN:**
- Pulls lifestyle sources: Broadsheet RSS (Sydney + Melbourne food, events, style), Google News lifestyle queries, Reddit lifestyle subs
- Shows count of items pulled per category
- Classifies items into: Eating, Watching, Reading, Wearing, Going (using OTC classifier)

**Display (after RUN):**
- 5 category blocks: Eating, Watching, Reading, Wearing, Going
- Each shows top 3 candidates with: title, source, city tag, trendiness score, shareability score, auto-generated blurb

**SELECT:**
- Pick one per category. Editable blurb field for each pick (pre-filled with classified summary).

**PROCEED:**
- Polishes the 5 blurbs in TAC voice
- Editable text areas per category
- Model dropdown (default: Gemini Flash)

### 10. Events

**Fully manual. No RUN or PROCEED.**

**Display:**
- List of events for this week's issue. Each shows: date, title, location, time, price, description.
- Edit/delete/reorder buttons per event.
- "Add Event" form: date picker, title, location, time, price, description textarea, Add button.

**Output:** Events go directly into the newsletter as entered. No LLM processing.

### 11. Salary Vault

**Placeholder.** Greyed out in sidebar with "Coming Soon" label. Not clickable. No implementation.

### 12. Assemble

**Display:**
- Section status overview: each newsletter section shown as a card with status indicator:
  - Green (done): content generated and reviewed
  - Amber (in progress): RUN completed but no PROCEED yet
  - Grey (empty): nothing done
- Live preview of the full newsletter assembled from all completed sections, in order
- Each section block in the preview is collapsible

**Actions:**
- "Export HTML" button — generates and downloads the full newsletter HTML
- "Copy to Clipboard" — copies the rendered newsletter for pasting into Beehiiv
- Per-section "Edit" links that jump to that section's tab

## Database Changes

**New table: `otc_picks`** — not needed, reuses `editor_decisions` with OTC section values (already built).

**New table: `events`:**
```sql
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    event_date TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    time_range TEXT,
    price TEXT,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**New table: `amp_finest`:**
```sql
CREATE TABLE IF NOT EXISTS amp_finest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    chart_image_path TEXT,
    data_description TEXT,
    notes TEXT,
    generated_commentary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_iso)
);
```

**New table: `section_outputs`** — stores the generated text per section per week:
```sql
CREATE TABLE IF NOT EXISTS section_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    section TEXT NOT NULL,
    output_text TEXT NOT NULL,
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_iso, section)
);
```
Sections: `editorial`, `pulse`, `big_conversation`, `lobby`, `finds`, `thread`, `amp_finest`, `off_the_clock`.

## API Changes

**New endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/models` | List available models based on configured API keys |
| POST | `/api/run-section` | Run a specific section's data pull (already exists, extend) |
| POST | `/api/proceed-section` | Generate output for a section with selected items + model choice |
| GET | `/api/section-output/{section}` | Get saved output for a section this week |
| POST | `/api/section-output/{section}` | Save edited output for a section |
| GET | `/api/events` | List events for current week |
| POST | `/api/events` | Add an event |
| PUT | `/api/events/{id}` | Edit an event |
| DELETE | `/api/events/{id}` | Delete an event |
| GET | `/api/amp-finest` | Get AMP's Finest data for current week |
| POST | `/api/amp-finest` | Save AMP's Finest data (chart path, description, notes) |
| POST | `/api/amp-finest/proceed` | Generate commentary for AMP's Finest |
| GET | `/api/lobby` | Get employer data + top movers for current week |
| POST | `/api/lobby/proceed` | Generate Lobby narrative from selected employers |
| GET | `/api/assemble-preview` | Get full newsletter preview assembled from all section outputs |
| POST | `/api/assemble-export` | Export final newsletter HTML |

**Modified endpoints:**
- `POST /api/run-section` — already exists, ensure all section RUN operations are covered
- Existing Pulse, Items, Thread endpoints remain but are consumed by the new section views

## Frontend Architecture

**Single-page app** (same as current). One HTML file with vanilla JS. No framework.

**State object** gains per-section state:
```javascript
S.sections = {
  editorial: { status: 'empty', output: '' },
  pulse: { status: 'empty', output: '', signals: [], interactions: [], selected: [] },
  big_conversation: { status: 'empty', output: '', candidates: [], selected: null, custom: null },
  whispers: { items: [] },
  lobby: { status: 'empty', output: '', employers: [], topMovers: [], selected: [] },
  finds: { status: 'empty', output: '', items: [], selected: [] },
  thread: { status: 'empty', output: '', candidates: [], selected: null },
  amp_finest: { status: 'empty', output: '', chartPath: '', description: '', notes: '' },
  off_the_clock: { status: 'empty', output: '', candidates: {}, picks: {} },
  events: { items: [] },
};
```

Status values: `empty` → `pulled` (after RUN) → `selected` (after SELECT) → `done` (after PROCEED + review).

## What Gets Deleted

- The entire current sidebar navigation structure (Pipeline, Curation, Thread, Big Conv, Assemble, Health, Feedback tabs)
- `renderCuration()`, `renderPipeline()`, `renderHealth()`, `renderFeedback()` and their associated JS
- The `autoFetchComments` auto-trigger (comments fetched on-demand in Thread section only)
- The separate reingest background pipeline (replaced by per-section RUN buttons)

## What Gets Kept

- All existing backend: signal extractors, editorial pullers, classifiers, ATS scrapers, pulse calculation
- Database schema (extended, not replaced)
- FastAPI server structure
- Authentication (password gate)
- model_router.py (extended with Claude support + model override)

## Implementation Order

This is a large redesign. Recommended decomposition into sub-projects:

1. **Sub-project 1: model_router + Claude support + /api/models endpoint**
2. **Sub-project 2: section_outputs table + generic proceed/save API**
3. **Sub-project 3: Frontend rewrite — sidebar + section shells + RUN/SELECT/PROCEED pattern**
4. **Sub-project 4: Pulse section (complete workflow)**
5. **Sub-project 5: Big Conversation section**
6. **Sub-project 6: Finds section**
7. **Sub-project 7: Thread of the Week section**
8. **Sub-project 8: The Lobby section**
9. **Sub-project 9: Off the Clock section (adapt existing)**
10. **Sub-project 10: Manual sections (Whispers, AMP's Finest, Events)**
11. **Sub-project 11: Editorial (hook) section**
12. **Sub-project 12: Assemble (preview + export)**
