# Dashboard UX Redesign — Design Spec

## Goal

Three interconnected improvements to the Flat White dashboard:
1. A persistent **Command Bar** with Scrape All and per-section status pills
2. A consistent **accordion 3-phase layout** per section (Scrape → Review & Pick → Generate)
3. A **Composer view** (replacing Assemble) that shows all outputs in newsletter order for easy copy to Beehiiv

---

## Problem

The current dashboard has three compounding UX problems:
- **No global scrape action** — each section must be scraped individually with no visibility into which sections are ready
- **Unclear workflow** — within each section, buttons for scraping, picking, and generating are at the same visual level with no obvious order of operations
- **No unified output view** — outputs live inside individual sections; copying to Beehiiv requires navigating to each section and copying one at a time

---

## Architecture

All changes are confined to `flatwhite/dashboard/static/index.html` (frontend state + render functions) and `flatwhite/dashboard/api.py` (one new `/api/scrape-all` endpoint). No DB schema changes. No new files beyond the endpoint addition.

**Tech stack:** Vanilla JS SPA, FastAPI, existing `_SECTION_RUNNERS` dict, existing `S.sectionOutputs` state.

---

## 1. Command Bar

### Appearance
A persistent horizontal bar rendered at the top of the main content area (below the existing top nav, above the section content). Always visible regardless of active section.

### Contents
- **⚡ Scrape All** button (left side) — disabled with spinner while a scrape-all is running
- **Status pills** (right side) — one pill per scrapeable section in a fixed order: Pulse · Big Conv · Finds · Lobby · Thread · Off the Clock

### Pill states
| State | Colour | Label |
|-------|--------|-------|
| Not scraped this session | Grey | section name |
| Scrape running | Amber + spinner | "…" |
| Scraped, no output | Amber | section name |
| Output saved | Green | section name ✓ |
| Last scrape failed | Red | section name ✗ |

Hovering a red pill shows the error message as a tooltip.

Clicking a pill navigates to that section.

### Scrape All — frontend state
`S.scrapeAllRunning: false` — set to true while running, false when complete.
`S.scrapeAllErrors: {}` — map of `{ section: errorMessage }` for failures.
`S.lastScrapeError: {}` — same map, persisted per session for pill tooltips.

---

## 2. `/api/scrape-all` endpoint

```
POST /api/scrape-all
Body: {} (no params)
Returns: { "results": [ { "section": str, "status": "ok"|"error", "error": str|null } ] }
```

Runs each section's runner from `_SECTION_RUNNERS` in sequence:
`pulse → editorial → big_conversation → finds → lobby → thread → off_the_clock`

Each section is wrapped in try/except — a failure logs the error and moves to the next. Uses the existing `_run_section_background` logic but called synchronously in a single background thread (one section at a time to avoid DB write conflicts).

Frontend polls `/api/section-status/{section}` for each section while it runs, exactly as individual section scrapes do today.

After all sections complete, a toast shows: `"Scrape All done — N/7 succeeded"`. If any failed: `"· [Section] failed"` appended.

The endpoint returns a summary. The frontend does NOT need to wait for the response — it shows progress via existing section-status polling.

---

## 3. Per-section accordion phases

Every section render function is refactored to wrap its content in a consistent 3-phase accordion. The accordion is managed by `S.sectionPhase[section]` (int: 1, 2, or 3) — which phase is currently open.

### Phase structure

**Phase 1 — Scrape**
- Header: "① Scrape" + last scraped timestamp badge + section-specific RUN button
- Body: section-specific scrape controls + progress indicator (already exists per section)
- Auto-opens if the section has no data for the current week
- On scrape complete: auto-advances to Phase 2

**Phase 2 — Review & Pick**
- Header: "② Review & Pick"
- Body: all existing candidate lists, checkboxes, pickers, selectors for that section
- Locked (greyed, non-clickable header) until Phase 1 has data
- Auto-opens when Phase 1 completes
- Sections with no pick step (Events, Whispers, AMP's Finest data entry) skip Phase 2 entirely

**Phase 3 — Generate**
- Header: "③ Generate"
- Body: model selector + PROCEED button + output box (Copy + Save)
- Locked until Phase 2 has at least one selection (or Phase 1 for sections without Phase 2)
- Auto-opens when user navigates to it or when generation completes

### Accordion behaviour
- Only one phase open at a time
- Clicking a phase header opens it (if unlocked) and closes the current one
- Completed phases show a ✓ checkmark in their header

### `S.sectionPhase` initialisation
Default: `{}` — falls back to Phase 1 if key missing. Set on page load based on current data state:
- No data → Phase 1
- Has data, no output → Phase 2
- Has output → Phase 3

---

## 4. Composer (replaces Assemble)

The existing "Assemble" nav item is renamed to **Composer**. Its render function is replaced.

### Layout
Full-width column of section panels in newsletter order:

1. Pulse
2. Big Conversation
3. Finds
4. The Lobby
5. Thread
6. Off the Clock
7. AMP's Finest
8. Events

### Each panel
```
[SECTION NAME]  ·  Generated HH:MMam     [Copy]
─────────────────────────────────────────────
[output text — editable textarea]
```

- **Copy** button copies the panel's textarea content to clipboard
- Textarea is editable inline — changes are local only (not auto-saved; user can click Save to persist if needed, or just copy)
- Panels are always expanded (no collapse in Composer — this is the final review view)

### Missing output panels
Sections with no saved output render as:
```
⚠ [SECTION NAME] — No output yet
[Go to section →]
```
Amber border. "Go to section →" button navigates to that section (sets `S.page`).

### Top bar
```
Composer — Week 2026-W13       [Copy All]
N/8 sections ready
```

**Copy All** concatenates all panels that have output, separated by double newlines, with a `## SECTION NAME` header before each. Copies to clipboard.

---

## 5. General UX cleanup

### Consistent toolbar
Every section toolbar follows the same structure (left to right):
```
[Section Icon] [Section Title]   [Scraped badge]   [Model selector]   [Action buttons]
```
Existing toolbars that deviate from this are brought into line.

### Visual hierarchy
- Section headings: `font-size: 18px; font-weight: 700`
- Phase headers: `font-size: 13px; font-weight: 600`
- Supporting/meta text (timestamps, source names, counts): `font-size: 11px; color: var(--text-2)`
- Currently most text is the same weight — this creates visual noise

### Remove dead buttons
- Any leftover `_proceed_*` buttons not wired to the current proceed modal are removed
- Duplicate scrape controls (some sections have both a toolbar RUN and a body-level button) consolidated to Phase 1 only

### Sidebar
No structural changes. Progress bar at bottom already counts sections with output — keep as-is.

---

## Self-Review

**Spec coverage:**
- Command bar with Scrape All + status pills: ✅
- Scrape All runs independently per section, failures flagged: ✅
- Per-section accordion 3 phases: ✅
- Accordion auto-advances on completion: ✅
- Composer with per-section copy + Copy All + missing section warnings: ✅
- General UX cleanup (toolbar consistency, visual hierarchy): ✅

**Placeholders:** None.

**Ambiguity resolved:**
- Scrape All runs sequentially (not parallel) to avoid DB write conflicts
- Phase 2 is skipped for Events, Whispers, AMP's Finest (no pick step)
- Composer textareas are editable but not auto-saved — user copies directly to Beehiiv
- Status pills reflect session state (not persisted across page refresh) — scrape timestamp from DB determines initial state
- `S.sectionPhase` defaults to Phase 1 on fresh load; inferred from DB state (has data → Phase 2; has output → Phase 3)
