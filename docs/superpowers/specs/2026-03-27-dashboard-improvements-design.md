# Dashboard Improvements Design
**Date:** 2026-03-27
**Status:** Approved

## Overview

Five targeted improvements to the Flat White editor dashboard:

1. Global SCRAPE / PROCEED modal — rename RUN to SCRAPE, add prompt review before generation
2. Pulse category trend cards + enhanced prompts with WoW deltas
3. Off the Clock item selection + prompt review modal
4. Finds AU relevance re-ranking
5. The Lobby multi-period trend analysis with sparklines

---

## Section 1 — Global: SCRAPE / PROCEED Modal

### Problem
"RUN" is ambiguous — users don't know it scrapes data. "PROCEED" fires the LLM blindly with no visibility into what prompt is being sent or which items are feeding it. There is no way to steer or adjust before generating.

### Design

**Rename:** "RUN" → "SCRAPE" on every section toolbar (Pulse, Big Conversation, Lobby, Finds, Off the Clock, Thread).

**PROCEED becomes two-step:**

1. Clicking PROCEED opens a modal overlay (shared component, reused across all sections).
2. Modal layout:
   - **Header:** "Generate [Section Name]"
   - **Editorial lean** (top): short free-text input — e.g. "Focus on white-collar anxiety this week." Injected at the top of the prompt.
   - **Items panel** (collapsible): checkboxes for the signals/items feeding the prompt. Pre-selected to current defaults. User can deselect items to exclude them.
   - **Prompt textarea**: full rendered prompt, pre-populated by calling `/api/preview-prompt` when the modal opens. Fully editable — user can change anything.
   - **Buttons:** Cancel | Confirm & Generate
3. On Confirm & Generate: POST to `/api/proceed-section` with `custom_prompt` (the edited prompt text) and `selected_item_ids` (from checkboxes). If `custom_prompt` is provided, the backend uses it verbatim instead of rendering the default.

### Backend changes

- New endpoint: `GET /api/preview-prompt?section=<name>` — renders and returns the default prompt for that section as a plain string (no LLM call). Used to pre-populate the modal textarea.
- `/api/proceed-section` — add optional `custom_prompt: str` field to the request body. When present, skip default prompt rendering and send `custom_prompt` directly to the LLM.

### Files affected
- `flatwhite/dashboard/static/index.html` — rename RUN→SCRAPE, add modal HTML/JS, wire up `/api/preview-prompt`
- `flatwhite/dashboard/api.py` — add `/api/preview-prompt` endpoint, update `/api/proceed-section` to accept `custom_prompt`
- Each section's proceed handler in `api.py` — pass `custom_prompt` through to LLM call if provided

---

## Section 2 — Pulse: Category Trends + Enhanced Prompts

### Problem
The disruption score is a single number with no visible breakdown. Category-level movements (e.g. a sharp drop in consumer confidence in the "economic" area) are invisible in the UI. The LLM summary prompt only receives raw normalised scores with no WoW delta context, so it can't identify or narrate what changed week-on-week.

### Design

**UI additions — Category Trend Cards:**

Add a "Category Trends" panel above the existing signals table. Three cards rendered horizontally:
- **Labour Market**
- **Financial & Economic**
- **Corporate Stress**

Each card contains:
- Category label + current weighted-average score (large, 0–100)
- WoW delta badge: "+3.2" (green) / "−5.1" (red) / "→ stable" (grey). Delta = current score minus previous week's weighted average for that category.
- 6-week SVG sparkline (inline SVG, ~120 × 40px, no JS chart library). Points from `/api/pulse/trends` → `categories[].history`.

The data already exists in the `/api/pulse/trends` response (`categories` array with `history`, `current_score`, `prev_score`, `delta`). This is a frontend rendering addition only.

**UI change — signal table deltas:**

Currently only signals in `biggest_movers` (top 5) show a WoW delta. Extend to show a delta for every signal by computing it client-side from `S.trends.biggest_movers` or by extending the `/api/pulse/trends` response to return all-signal deltas (not just top 5). Extend backend to return all-signal deltas, not just top 5.

**Prompt changes — `summary.py`:**

`generate_driver_bullets()` and `generate_pulse_summary()` currently pass only `normalised_score` per signal. Update both functions:
1. Query the previous week's signals from the DB alongside the current week.
2. Compute `delta = current.normalised_score - prev.normalised_score` per signal.
3. Format signals in the prompt as: `"consumer_confidence: 42.1 (prev: 61.3, Δ: -19.2)"`.
4. If a signal has `source_weight < 1.0` (scraper fell back to a default value), annotate it: `"consumer_confidence: 85.0 [FALLBACK — data may be stale]"`.
5. Explicitly instruct the LLM in the system prompt to call out signals with large deltas (absolute Δ > 10) as key drivers.

### Files affected
- `flatwhite/dashboard/static/index.html` — add category trend cards, SVG sparkline renderer, fix all-signal deltas
- `flatwhite/dashboard/state.py` — extend `load_signal_trends()` to return all-signal deltas (not just top 5)
- `flatwhite/dashboard/api.py` — `/api/pulse/trends` response passes through extended movers list
- `flatwhite/pulse/summary.py` — `generate_driver_bullets()` and `generate_pulse_summary()` query prev-week signals and include delta + fallback annotation
- `flatwhite/classify/prompts.py` — update `DRIVER_BULLETS_SYSTEM`, `PULSE_SUMMARY_SYSTEM` to instruct LLM to highlight large movers

---

## Section 3 — Off the Clock: Item Selection + Prompt Review

### Problem
After SCRAPE, OTC shows only the top 3 candidates per category as radio buttons with no visibility into what else was scraped. There is no way to see or edit the prompt before PROCEED runs. The current flow also has two separate buttons (RUN and "Classify OTC") that are confusing.

### Design

**UI — item selection:**

After SCRAPE, render a multi-select checklist per category (not just top 3). Each item shows:
- Title (truncated to ~80 chars)
- Source tag badge (e.g. `otc_rss_broadsheet_sydney_food`)
- City badge if available (Sydney / Melbourne / National)

All classified items for the category are pre-selected. User deselects items they don't want fed into the prompt.

The existing radio-button "pick" flow (for selecting one final item to save as the OTC pick) remains. The new checklist is for selecting which items the LLM considers, not which one gets saved.

**UI — PROCEED modal (from Section 1):**

When PROCEED is clicked, the modal opens showing:
- Selected items per category (grouped)
- Full OTC prompt (editable)
- Editorial lean field (e.g. "Lean Sydney heavy this week, skip anything chain restaurant")

**Backend:**

- `/api/preview-prompt?section=off_the_clock` returns the OTC prompt formatted with current candidates
- `/api/proceed-section` for `off_the_clock`: accept `selected_item_ids` (dict keyed by category) and `custom_prompt`. Filter candidates to selected items before building the LLM context if `selected_item_ids` provided.
- "Classify OTC" button renamed to "Classify" and kept in toolbar — no behaviour change.

### Files affected
- `flatwhite/dashboard/static/index.html` — replace radio selector with multi-select checklist, wire modal
- `flatwhite/dashboard/api.py` — `/api/preview-prompt` for OTC, update OTC proceed handler to filter by `selected_item_ids`

---

## Section 4 — Finds: AU Relevance Re-ranking

### Problem
Finds surfaces too many US/global market stories that have no direct relevance to Australian workers, companies, or markets. The editorial classifier scores relevance/novelty/tension etc. but has no concept of geographic relevance.

### Design

**Classifier addition:**

Add `au_relevance` (integer 0–10) to the classification JSON output. Prompt addition in `CLASSIFICATION_PROMPT`:

> "au_relevance (0–10): How directly relevant is this to Australian workers, businesses, or markets? 0 = purely international with no Australian angle. 10 = specifically about Australia. Global stories with direct AU market impact (e.g. US tariffs affecting AU exports) score 5–7. US earnings, US politics with no AU angle score 0–2."

**DB migration:**

```sql
ALTER TABLE curated_items ADD COLUMN au_relevance INTEGER;
```

The classifier inserts `au_relevance` into `curated_items`. Existing rows default to NULL (treated as 5 / neutral for display).

**Finds display re-ranking:**

Client-side display order:
```
display_score = weighted_composite * 0.7 + (au_relevance / 10.0) * 3.0
```
Items sorted descending by `display_score`.

Visual badges in the Finds item cards:
- `au_relevance >= 7`: green "AU" chip
- `au_relevance < 4` (and not null): grey "low AU" chip — item stays visible, editor decides

### Files affected
- `flatwhite/classify/prompts.py` — add `au_relevance` to classification prompt schema
- `flatwhite/classify/classifier.py` — extract and store `au_relevance` from LLM JSON response
- `flatwhite/db.py` — DB migration: add `au_relevance` column to `curated_items`
- `flatwhite/dashboard/state.py` — include `au_relevance` in `load_curated_items_by_section()` query
- `flatwhite/dashboard/static/index.html` — re-rank Finds display, add AU/low-AU badges

---

## Section 5 — The Lobby: Trend Analysis

### Problem
The Lobby table shows current role count, previous week count, and delta. This is a single point-in-time comparison. There is no way to see whether a delta is a one-week blip or part of a sustained trend. Monthly change is invisible.

### Design

**Backend — extended employer history:**

Extend `load_lobby_state()` in `state.py` to query the last 8 weeks of employer role count snapshots.

Per employer, compute and return:
- `open_roles_count`: current week
- `prev_week_count`: 1 week ago
- `wow_delta`: `current - prev_week` (existing)
- `month_ago_count`: 4 weeks ago (or nearest available week)
- `mom_delta`: `current - month_ago`
- `history`: array of last 6 weekly counts (oldest first) for sparkline rendering

If fewer than 4 weeks of data exist for an employer, `mom_delta` is `null` and displayed as "—".

**UI — table:**

Updated columns: **Employer | Sector | Roles | WoW | MoM | Trend**

- WoW and MoM: coloured deltas (green = up, red = down, grey = 0)
- Trend: inline 6-bar SVG sparkline (~80 × 28px). Same inline SVG approach as Pulse category cards. Bars sized relative to the employer's own min/max over the 6 weeks (not cross-employer normalised).

**UI — Top Movers cards:**

Add a second line below the WoW delta: "4-wk: +18" or "4-wk: —" in smaller text.

**PROCEED prompt:**

Include per-employer trend narrative in the lobby prompt context:
```
Deloitte: 145 roles (+12 WoW, -8 MoM) — gaining weekly but softening over the month
CBA: 89 roles (-3 WoW, -22 MoM) — sustained contraction
```
The LLM is instructed to identify employers showing sustained trends (same direction for 3+ weeks) vs one-week spikes.

### Files affected
- `flatwhite/dashboard/state.py` — extend `load_lobby_state()` with 8-week history per employer, compute `mom_delta` and `history`
- `flatwhite/dashboard/api.py` — `/api/lobby` passes through extended employer objects
- `flatwhite/dashboard/static/index.html` — update table columns, add MoM column, add sparkline renderer, update Top Movers cards, update `proceedLobby()` to include trend data in PROCEED prompt context

---

## Data Flow Summary

```
SCRAPE button → /api/run-section (background) → polls /api/section-status
                                                        ↓ done
                                               data loads into UI

PROCEED button → /api/preview-prompt → renders prompt → modal opens
                                                              ↓
                                              user edits prompt / selects items
                                                              ↓
                                         /api/proceed-section (custom_prompt) → LLM → output box
```

---

## Implementation Order

1. DB migration (`au_relevance` column) — no risk, additive only
2. Classifier: add `au_relevance` field
3. State.py: extend signal trends (all-signal deltas) + lobby 8-week history
4. Prompts + summary.py: add WoW delta context to Pulse prompts
5. Backend: `/api/preview-prompt` endpoint + `custom_prompt` support in `/api/proceed-section`
6. Frontend: SCRAPE rename + PROCEED modal (global)
7. Frontend: Pulse category trend cards + sparklines
8. Frontend: OTC multi-select checklist
9. Frontend: Finds AU badge display + re-ranking
10. Frontend: Lobby WoW/MoM columns + sparklines
