# Signal UX, PROCEED Fixes & OTC Redesign — Design Spec

## Goal

Fix critical PROCEED crashes, correct signal delta colouring, clarify pulse direction semantics, add signal table sorting and row selection, redesign OTC selection to pill-based UX, and apply none-selected defaults to pulse and OTC.

## Architecture

All changes are frontend-only except for the PROCEED crash fix which requires two new DB functions and removal of duplicate API routes. No new API endpoints. No schema changes beyond a new `section_outputs` table.

## Tech Stack

- Python/FastAPI backend (`flatwhite/dashboard/api.py`, `flatwhite/db.py`)
- Vanilla JS SPA frontend (`flatwhite/dashboard/static/index.html`)
- SQLite via `flatwhite/db.py`

---

## Problem Inventory

### Bug 1: PROCEED crashes on all sections (BLOCKING)

**Root cause:** The old `api_proceed_section` handler at line 909 of `api.py` does `from flatwhite.db import save_section_output` as the first line inside the function — before reading the request body, before any try/except. `save_section_output` does not exist in `db.py`. The `ImportError` propagates unhandled; uvicorn returns a plain-text `"Internal Server Error"` (Content-Type: text/plain). The frontend `api()` helper calls `r.json()` on the text response and throws a JSON parse error (`Unexpected token 'I', "Internal Server Error" is not valid JSON`), which surfaces as a toast error on every PROCEED attempt.

The same issue affects `GET /api/section-outputs` (line 890) and `POST /api/section-output/{section}` (line 900), which also reference `load_all_section_outputs` and `save_section_output` respectively — both missing from `db.py`.

The new correct implementations exist at lines 2005 (`api_proceed_section`) and 1667 (`api_section_outputs`) but are never reached because FastAPI uses first-match routing.

**Fix:**
1. Add `section_outputs` table to DB (in `migrate_db()`)
2. Add `save_section_output(week_iso, section, output_text, model_used)` to `db.py`
3. Add `load_all_section_outputs(week_iso) -> dict` to `db.py`
4. Remove the duplicate old routes at lines 890–944 (`api_section_outputs`, `api_save_section_output`, `api_proceed_section`)

### Bug 2: Signal intelligence drawer crashes on null delta

`si.delta.toFixed(1)` is called without a null guard in the PROCEED modal's Context tab and in the evidence drawer. If a `signal_intelligence` DB row has `NULL` for delta, this throws a TypeError.

**Fix:** guard with `si.delta != null ? (si.delta > 0 ? "+" : "") + si.delta.toFixed(1) + " pts" : "—"` in both locations.

### Bug 3: Signal delta colours inverted

Current logic: positive delta = red, negative delta = green. This is wrong for almost every signal.

**How the backend works:** adverse signals (`layoff_news_velocity`, `asic_insolvency`, `job_anxiety`, `reddit_topic_velocity`, `auslaw_velocity`) are normalised with `inverted=True` — so a positive normalised_score delta means the *raw* adverse count went *down* (good news). Non-inverted signals (`consumer_confidence`, `market_hiring`, `employer_hiring_breadth`, etc.) have positive delta = more hiring/confidence = good news.

**Rule (reader perspective — good news = green):**
- All signals: positive delta = green, negative delta = red
- Exception: `asx_volatility` — positive delta = more market volatility = red

**Fix:** Replace the single inverted rule with a `SIGNAL_INVERTED_DISPLAY` set containing only `"asx_volatility"`.

---

## Pulse Index Direction Clarity

Higher disruption score = more market stress = worse for workers. A score of 70 = high disruption (layoffs, insolvencies, low consumer confidence). A score of 30 = healthy market. "Rising" = conditions deteriorating.

**Current UI problems:**
- Direction pill (`↑ rising`) has no semantic colour — looks neutral whether rising or falling
- No label explains what high/low scores mean

**Design:**
- Direction pill coloured: rising = amber/red, falling = green, stable = neutral text-3
- Add a subtitle below the score value: `"Lower is healthier"` (one line, text-3, font-size 11px)

---

## Signal Table UX

### Sorting

Column headers become clickable. State: `S.signalSort = { col: null, dir: "desc" }`.

Sortable columns and their sort keys:
- **Signal** → alphabetical by `signal_name`
- **Score** → `normalised_score` descending/ascending
- **Delta** → absolute delta (`Math.abs(delta)`) descending/ascending (largest movers first)
- **Category** → alphabetical by `area`
- **Evidence** → signals with intel first, then without

Clicking a column that is already the active sort toggles direction. Clicking a new column sets it descending. Active column shows `▼` / `▲` indicator.

### Row click-to-select

`<tr onclick="togglePulseCheck('name', !S.pulseChecked['name']); render()">` on every row. The Evidence cell gets `onclick="event.stopPropagation(); toggleSignalIntel('name')"` to prevent row toggle when clicking evidence.

`<tr>` gets `style="cursor:pointer"` and a hover background via CSS class `tr-hover`.

### None selected by default for Pulse

Remove the `S._pulseInitChecked` auto-select-all block (lines ~612–615 of index.html). `S.pulseChecked` starts as `{}` (empty). Users select signals before PROCEED.

---

## OTC Selection Redesign

### Current UX problems
- Checkbox selects for context inclusion + separate radio "Pick this one" = two separate concepts that confuse users
- All items selected by default (cluttered)
- "Pick this one" appears inline after each checkbox item (hard to scan)

### New design: pill panels

One card per category. Inside each card:
- Category label header
- Horizontal flex-wrap row of pill buttons, one per candidate
- Each pill shows: truncated title (max ~40 chars) + optional city chip
- Clicking a pill: selects it as the pick for that category (amber border + background)
- Clicking the active pill again: deselects it
- Only one pill active per category (radio behaviour as pills)
- None selected on initial load
- When a pill is selected, a compact blurb textarea appears **below the pill row** for that category (not inline per item)

### State changes
- Remove `S.otcSelected` (no longer needed — selection and pick are unified)
- `S.otcPicks[cat.key]` = selected item id or `undefined` (unchanged concept, simplified init)
- `S.otcBlurbs[cat.key]` = blurb text (unchanged)

### PROCEED
`proceedOTC()` builds picks from `S.otcPicks` only. Categories with no pick are omitted. If zero picks, PROCEED button is disabled with tooltip "Select at least one item".

---

## Self-Review

**Spec coverage:** All 8 issues from the user's feedback are addressed.

**Placeholder scan:** None found.

**Internal consistency:** Signal direction map uses the same `SIGNAL_INVERTED_DISPLAY` constant in both the signal table delta cell and the PROCEED modal context tab. DB functions are defined before the routes that import them.

**Scope:** Appropriate for one implementation plan. All changes are either backend DB/route fixes or frontend JS/HTML edits in one file.

**Ambiguity resolved:**
- "None selected by default" for OTC = `S.otcPicks` starts empty (no pre-selection)
- "None selected by default" for Pulse = remove auto-check-all init block
- OTC pill selection = one pick per category (not multi-select for context, just one pick per category for generate)
- Disruption score overlap = fix direction pill colour + add subtitle, no layout restructure needed
