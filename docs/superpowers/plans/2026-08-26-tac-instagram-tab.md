# TAC Instagram tab - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "TAC Instagram" workspace inside the Flat White dashboard: a Today/farm-loop screen, a Topic Bank of 118 topics, a Calendar, a Quarterly Planner, and a shared Content Bank - replacing Victor's spreadsheet as the place he actually works from. Design reference: `docs/superpowers/specs/2026-08-26-tac-instagram-tab.md`.

**Architecture:** Same app, same server, same database as the rest of FW. FastAPI backend `flatwhite/dashboard/api.py`, single static frontend `flatwhite/dashboard/static/index.html` (hand-rolled router, state object `S`, no build step), SQLite at `data/flatwhite.db` with schema in `flatwhite/db.py`'s `SCHEMA_SQL`. New Claude-skill runs go through the existing `flatwhite/dashboard/skill_runner.py` - no new subprocess code. New backend logic lives in a new module `flatwhite/dashboard/tac_instagram_state.py`, following the same pattern as `brains_trust_research.py` and `inside_track.py` (a plain-Python state/query module the API routes call into; no LLM calls inside it except where a task explicitly builds a skill_runner call).

**Tech stack:** Python 3.12 (FastAPI), vanilla JS frontend, `pytest` + `fastapi.testclient.TestClient`, `openpyxl` (already an installed dependency - verified 26 Aug 2026) for the one-time spreadsheet import.

**Source data:** `/Users/victornguyen/Downloads/TAC_Instagram_Content_Calendar_2026.xlsx` - confirmed real, 5 sheets: `📅 Calendar` (170 rows), `🗂️ Topic Bank` (118 topic rows), `📆 Quarterly Planner` (12 rows), `📦 Content Bank` (empty), `📋 How To Use` (rulebook, no data to import).

## Global Constraints

- Runs on FW's venv only: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python 3.9 breaks FW.
- Branch from `main`: `git checkout main && git checkout -b tac-instagram-tab`. Built and tested locally only; not merged or deployed without Victor (FW deploy is his call - see FW `CLAUDE.md`, the GCP VM is currently unreachable anyway, so this runs local-first like the rest of the dashboard).
- **FW test baseline:** run `.venv/bin/python -m pytest -q` before Task 1 and record the pass/fail counts. Another agent may be fixing pre-existing failures in a separate worktree at the same time - do not chase unrelated failures; only the counts introduced by this plan's own tasks matter. After every task, the delta in failures should be exactly what that task's own new tests contribute (all passing) - no regressions to existing passing tests.
- No em dashes (U+2014) anywhere, including code comments that are reader-facing (skill prompts, UI copy). Australian spelling in any UI-facing string.
- Do not touch the existing Flat White running-order code paths (`SEGMENTS`, `renderSidebar`, `_REAL_SEGMENTS`, any `renderX` for existing segments, any existing `/api/*` route). This build is additive: a new workspace switcher, new routes under `/api/tac-instagram/*`, new tables, new frontend render functions. Existing behaviour must work exactly as before after every task.
- Reuse `flatwhite/dashboard/skill_runner.py` for the one new headless run (Task 10). Do not write a second background-job engine.
- Local run for manual verification throughout: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500`, then `http://localhost:8500/`. Kill it (Ctrl-C) when done with each check.

---

### Task 1: Copy the source file in, add the three new tables, write the one-time importer

**Files:**
- Create: `flatwhite/data/tac_instagram/TAC_Instagram_Content_Calendar_2026.xlsx` (copy of the Downloads file - see step 1)
- Modify: `flatwhite/db.py` (append three `CREATE TABLE IF NOT EXISTS` blocks to `SCHEMA_SQL`)
- Create: `scripts/import_tac_instagram_calendar.py`
- Test: `tests/test_import_tac_instagram_calendar.py`

**Interfaces:**
- Consumes: nothing from other tasks (first task).
- Produces: three tables (`tac_topic_bank`, `tac_calendar`, `tac_quarterly_planner`) that every later task reads/writes; `import_tac_instagram_calendar.run(xlsx_path: str, db_path: str | None = None, force: bool = False) -> dict` returning row counts per table, used by the test and by manual re-import if Victor ever edits the source file again.

- [ ] **Step 1: Copy the source file into the repo.**
```bash
mkdir -p "/Users/victornguyen/Documents/MISC/FW/flatwhite/data/tac_instagram"
cp "/Users/victornguyen/Downloads/TAC_Instagram_Content_Calendar_2026.xlsx" \
   "/Users/victornguyen/Documents/MISC/FW/flatwhite/data/tac_instagram/TAC_Instagram_Content_Calendar_2026.xlsx"
```
This becomes the import's canonical source (Downloads is not durable - see spec open question 4). Confirm with Victor this is fine to keep in the repo; it holds no financial or personal data.

- [ ] **Step 2: Add the schema.** In `flatwhite/db.py`, append to `SCHEMA_SQL` (after the existing `content_bank` table definition):
```sql
CREATE TABLE IF NOT EXISTS tac_topic_bank (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_number INTEGER,
    topic TEXT NOT NULL,
    best_format TEXT,
    content_pillar TEXT,
    engagement_level TEXT,
    used INTEGER NOT NULL DEFAULT 0,
    used_date TEXT,
    angle_notes TEXT,
    community_question TEXT,
    tac_answer TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tac_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_date TEXT,
    day_of_week TEXT,
    post_type TEXT,
    content_pillar TEXT,
    caption_hook TEXT,
    story_cta_link TEXT,
    canva_project TEXT,
    visual_asset TEXT,
    collab_tag TEXT,
    publish_time TEXT,
    status TEXT NOT NULL DEFAULT 'Not Started',
    notes TEXT,
    week_label TEXT,
    topic_bank_id INTEGER REFERENCES tac_topic_bank(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tac_quarterly_planner (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number INTEGER,
    campaign_event TEXT NOT NULL,
    type TEXT,
    launch_date TEXT,
    close_event_date TEXT,
    results_publish TEXT,
    sponsor INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    quarter_label TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```
`status` free-text rather than a SQL `CHECK` constraint, matching how `content_bank.status` is the only checked enum in this schema and every other status-like column (e.g. `skill_run_state.status`) is left as plain text - keeps the importer and later edits simple.

- [ ] **Step 3: Write the failing test.** `tests/test_import_tac_instagram_calendar.py` - build a tiny fixture workbook in `tmp_path` with the same three sheet names/headers as the real file but 2-3 rows each, run `import_tac_instagram_calendar.run(fixture_path, db_path=tmp_db)`, assert the returned counts and that rows landed with the right column mapping (spot-check one full row per table against known fixture values). Also test `force=False` on an already-populated DB is a no-op (returns existing counts, does not duplicate rows) and `force=True` truncates and reloads.

- [ ] **Step 4: Run tests to verify they fail.**
Run: `.venv/bin/python -m pytest tests/test_import_tac_instagram_calendar.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'scripts.import_tac_instagram_calendar'` (or import error, since the module doesn't exist yet).

- [ ] **Step 5: Write the importer.** `scripts/import_tac_instagram_calendar.py` - reads the three sheets with `openpyxl`, skipping the title row and header row, and for the Calendar sheet carrying the last-seen `Date`/`Day`/week-band label forward onto blank-date follow-up rows within the same week block (the real sheet only fills `Date`/`Day` on a week's first row, per the confirmed sample data). Column mapping:
  - Topic Bank: `#`->`topic_number`, `Topic`->`topic`, `Best Format`->`best_format`, `Content Pillar`->`content_pillar`, `Eng. Level`->`engagement_level`, `Used?`->`used` (`"Yes"`->1 else 0), `Used Date`->`used_date`, `Angle / Notes`->`angle_notes`, `Community Question (Post This to Farm)`->`community_question`, `TAC Thought Leadership Answer (Use for Carousel)`->`tac_answer`.
  - Calendar: `Date`->`post_date` (carried forward), `Day`->`day_of_week` (carried forward), `Post Type`->`post_type`, `Content Pillar`->`content_pillar`, `Caption / Hook`->`caption_hook`, `Story CTA + Link`->`story_cta_link`, `Canva Project`->`canva_project`, `Visual / Asset`->`visual_asset`, `Collab / Tag`->`collab_tag`, `Publish Time`->`publish_time`, `Status`->`status`, `Notes`->`notes`; `week_label` set from the most recently seen `"WEEK n ... "` banner row.
  - Quarterly Planner: `#`->`item_number`, `Campaign / Event`->`campaign_event`, `Type`->`type`, `Launch Date`->`launch_date`, `Close / Event Date`->`close_event_date`, `Results Publish`->`results_publish`, `Sponsor?`->`sponsor` (`"Yes"`->1 else 0), `Notes`->`notes`; `quarter_label` from the most recently seen `"Qn 2026 ... "` banner row.

  A `run(xlsx_path, db_path=None, force=False) -> dict` function does the work using `flatwhite.db.get_connection`; a `if __name__ == "__main__":` block with `argparse` (`--force`) lets Victor re-run it by hand if he ever edits the source workbook again.

- [ ] **Step 6: Run tests to verify they pass.**
Run: `.venv/bin/python -m pytest tests/test_import_tac_instagram_calendar.py -v`
Expected: all passing.

- [ ] **Step 7: Run the real import and verify against the real numbers.**
```bash
.venv/bin/python scripts/import_tac_instagram_calendar.py \
  flatwhite/data/tac_instagram/TAC_Instagram_Content_Calendar_2026.xlsx
sqlite3 data/flatwhite.db "select count(*) from tac_topic_bank;"          # expect 118
sqlite3 data/flatwhite.db "select count(*) from tac_quarterly_planner;"   # expect 12
sqlite3 data/flatwhite.db "select count(*) from tac_calendar;"            # expect the real row count (~170 minus title/header/blank rows)
```

- [ ] **Step 8: Commit.**
```bash
git add flatwhite/db.py scripts/import_tac_instagram_calendar.py tests/test_import_tac_instagram_calendar.py flatwhite/data/tac_instagram/TAC_Instagram_Content_Calendar_2026.xlsx
git commit -m "TAC Instagram tab: add topic bank / calendar / quarterly planner tables + one-time importer"
```

---

### Task 2: `tac_instagram_state.py` - read/write functions the API will call

**Files:**
- Create: `flatwhite/dashboard/tac_instagram_state.py`
- Test: `tests/test_tac_instagram_state.py`

**Interfaces:**
- Consumes: the three tables from Task 1.
- Produces (all read from/write to `flatwhite.db.get_connection()`):
  - `list_topics(pillar=None, best_format=None, engagement_level=None, used=None) -> list[dict]`
  - `mark_topic_used(topic_id: int, used_date: str | None = None) -> bool`
  - `add_topic(topic: str, best_format=None, content_pillar=None, engagement_level=None, angle_notes=None, community_question=None, tac_answer=None) -> int` (returns new id)
  - `next_unused_topic(best_format_contains: str | None = None) -> dict | None` (oldest `topic_number` first, optionally filtered)
  - `list_calendar(week_label=None, status=None) -> list[dict]`
  - `add_calendar_row(**fields) -> int`
  - `update_calendar_row(row_id: int, **fields) -> bool`
  - `list_quarterly(quarter_label=None) -> list[dict]`
  - `add_quarterly_item(**fields) -> int`
  - `generate_survey_week_rows(quarterly_item_id: int) -> list[int]` - reads that quarterly row's `launch_date`, computes the Monday of that week, and inserts the five standard survey-week rows into `tac_calendar` (Mon launch carousel + story, Tue newsletter feature, Wed Big Conversation on the survey topic, Thu reminder meme, Fri Open Floor questions), each `content_pillar` set to `"Survey Campaign"` and `notes` referencing the campaign name; returns the new row ids. Raises `ValueError` if the quarterly item isn't found or has no `launch_date`.

- [ ] **Step 1: Write the failing tests.** Use `tmp_path`-based sqlite fixtures (monkeypatch `flatwhite.db.DB_PATH` or pass an explicit connection, matching whatever pattern `tests/test_brains_trust_refresh.py` / other existing dashboard-module tests already use in this repo - check `tests/conftest.py` first for a shared DB fixture and reuse it rather than inventing a new one). Cover: filtering combinations on `list_topics`, `next_unused_topic` returning the lowest unused `topic_number` and respecting the format filter, `mark_topic_used` setting both `used` and `used_date`, calendar CRUD round-trips, `generate_survey_week_rows` producing exactly 5 rows with correct dates relative to a frozen `launch_date`, and the `ValueError` cases.

- [ ] **Step 2: Run tests to verify they fail.**
Run: `.venv/bin/python -m pytest tests/test_tac_instagram_state.py -v`
Expected: FAIL - `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation.** Plain functions over `get_connection()`, mirroring the style already used in `flatwhite/dashboard/state.py` and `flatwhite/dashboard/inside_track.py` (parameterised queries, dict rows via `conn.row_factory = sqlite3.Row` then `dict(row)`, connections closed before returning). No LLM calls in this module.

- [ ] **Step 4: Run tests to verify they pass.**
Run: `.venv/bin/python -m pytest tests/test_tac_instagram_state.py -v`
Expected: all passing.

- [ ] **Step 5: Commit.**
```bash
git add flatwhite/dashboard/tac_instagram_state.py tests/test_tac_instagram_state.py
git commit -m "TAC Instagram tab: topic bank / calendar / quarterly planner read-write functions"
```

---

### Task 3: API routes for Topic Bank, Calendar, Quarterly Planner

**Files:**
- Modify: `flatwhite/dashboard/api.py` (new route group, e.g. after the existing Content Bank routes)
- Test: `tests/test_tac_instagram_api.py`

**Interfaces:**
- Consumes: Task 2's functions.
- Produces:
  - `GET /api/tac-instagram/topics?pillar=&best_format=&engagement_level=&used=` -> `{"topics": [...]}`
  - `POST /api/tac-instagram/topics` -> add a topic, body matches `add_topic` kwargs
  - `POST /api/tac-instagram/topics/{id}/mark-used` -> `{"ok": true}`
  - `GET /api/tac-instagram/calendar?week_label=&status=` -> `{"rows": [...]}`
  - `POST /api/tac-instagram/calendar` -> add a row
  - `PATCH /api/tac-instagram/calendar/{id}` -> partial update, body = fields to change
  - `GET /api/tac-instagram/quarterly?quarter_label=` -> `{"items": [...]}`
  - `POST /api/tac-instagram/quarterly` -> add an item
  - `POST /api/tac-instagram/quarterly/{id}/generate-survey-week` -> `{"created_row_ids": [...]}` (400 with a plain-English error if `generate_survey_week_rows` raises `ValueError`)

- [ ] **Step 1: Write the failing tests.** `fastapi.testclient.TestClient` against `api_module.app`, patching `flatwhite.dashboard.tac_instagram_state` functions the way `tests/test_brains_trust_refresh.py` patches `brains_trust_refresh` - one test per route, plus one integration-style test that hits Task 1's real imported data (skip/mark slow if the repo's test conventions separate those) to confirm the topic count really is 118 through the live endpoint.

- [ ] **Step 2: Run tests to verify they fail.**
Run: `.venv/bin/python -m pytest tests/test_tac_instagram_api.py -v`
Expected: FAIL - `404 Not Found` for each route.

- [ ] **Step 3: Write the routes.** Thin wrappers calling into `tac_instagram_state`, JSON in/out, following the existing error-handling shape in `api.py` (400 for missing required fields, matching e.g. the Content Bank `POST` route's validation style).

- [ ] **Step 4: Run tests to verify they pass.**
Run: `.venv/bin/python -m pytest tests/test_tac_instagram_api.py -v`
Expected: all passing.

- [ ] **Step 5: Commit.**
```bash
git add flatwhite/dashboard/api.py tests/test_tac_instagram_api.py
git commit -m "TAC Instagram tab: API routes for topics, calendar, quarterly planner"
```

---

### Task 4: "Today" backend - what does today call for

**Files:**
- Modify: `flatwhite/dashboard/tac_instagram_state.py` (add `today_actions`)
- Modify: `flatwhite/dashboard/api.py` (add `GET /api/tac-instagram/today`)
- Test: `tests/test_tac_instagram_state.py` (append), `tests/test_tac_instagram_api.py` (append)

**Interfaces:**
- Consumes: `next_unused_topic` (Task 2).
- Produces: `today_actions(today: date | None = None) -> list[dict]`, each item `{"time": "9:00 AM", "task": "...", "day": "Monday", "suggested_topic": {...} | None}`, built from a hardcoded weekly-cadence table (Mon/Tue/Wed/Thu/Fri, straight from the spreadsheet's own "How To Use" tab, reproduced in the spec) - no day is invented, Saturday/Sunday return an empty list. Wednesday's suggestion filters `next_unused_topic(best_format_contains="Big Conversation")`; Thursday filters `"Meme"`; Monday/Friday take the plain oldest-unused topic with no format filter.

- [ ] **Step 1: Write the failing tests.** Freeze "today" to a known Monday/Tuesday/.../Sunday (mirror the `_frozen_today` pattern already used in `tests/test_brains_trust_refresh.py`) and assert the right task list and topic-suggestion filtering per day, including the Saturday/Sunday empty case.

- [ ] **Step 2: Run tests to verify they fail.** Expected: `AttributeError`/`404`.

- [ ] **Step 3: Implement** `today_actions` in `tac_instagram_state.py` and wire the `GET /api/tac-instagram/today` route.

- [ ] **Step 4: Run tests to verify they pass.**

- [ ] **Step 5: Commit.**
```bash
git add flatwhite/dashboard/tac_instagram_state.py flatwhite/dashboard/api.py tests/test_tac_instagram_state.py tests/test_tac_instagram_api.py
git commit -m "TAC Instagram tab: Today screen backend (weekly cadence + topic suggestion)"
```

---

### Task 5: Frontend workspace switcher (Flat White | TAC Instagram)

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: nothing new from the backend yet (Task 6 wires real data into the pages this creates).
- Produces: `S.workspace` (`"flat_white"` default, `"tac_instagram"`), a small switcher rendered above `.layout`, and a second sidebar/page-routing branch that Tasks 6-9's `renderTac*` functions plug into. Does NOT touch `SEGMENTS`, `renderSidebar`, or any existing `render*` function for the Flat White side.

- [ ] **Step 1: Record baseline.** `.venv/bin/python -m pytest -q 2>&1 | tail -3`, note counts. Boot the dashboard, confirm `/` is 200 and the existing running order still works exactly as before.

- [ ] **Step 2: Add the switcher markup and CSS.** Above `<div class="layout">`:
```html
<div class="ws-switch">
  <button class="ws-btn" id="ws-flat-white" onclick="switchWorkspace('flat_white')">Flat White</button>
  <button class="ws-btn" id="ws-tac-instagram" onclick="switchWorkspace('tac_instagram')">TAC Instagram</button>
</div>
```
```css
.ws-switch{max-width:1120px;margin:14px auto 0;padding:0 20px;display:flex;gap:8px}
.ws-btn{padding:7px 16px;border-radius:999px;border:1px solid var(--sep);background:var(--card);color:var(--label2);font-weight:600;font-size:13px;cursor:pointer}
.ws-btn.active{background:var(--accent-soft);color:var(--accent);border-color:transparent}
```

- [ ] **Step 3: Add the JS switch.** `switchWorkspace(ws)` sets `S.workspace = ws`, toggles the `.active` class on the two buttons, and calls a new top-level `renderWorkspace()` that shows/hides two container divs (`#fw-layout` wrapping the existing `.layout`, `#tac-layout` a new sibling `.layout` with its own `.side`/`.main`) based on `S.workspace`. Wrap the existing `<div class="layout">...</div>` block in `<div id="fw-layout">` (no internal changes) and add `<div id="tac-layout" style="display:none"><div class="layout"><div class="side" id="tac-side">...</div><div class="main"><div class="page" id="tac-page"></div></div></div></div>` immediately after it, with the TAC sidebar's five static items (Today, Calendar, Topic Bank, Quarterly Planner, Content Bank) as plain `.nav-lite`-style rows (reuse that existing CSS class) calling `selectTacPage(id)`. `selectTacPage` sets `S.tacPage` and calls a `renderTacPage()` switch (stub bodies for now - "Coming in Task N" placeholder text - Tasks 6-9 fill each in).

- [ ] **Step 4: Verify.** Boot. Click "TAC Instagram" - sidebar changes to the five new items, right pane shows the stub text, no errors in the browser console. Click back to "Flat White" - running order behaves exactly as before. `.venv/bin/python -m pytest -q` unchanged from baseline (this task is frontend-only).

- [ ] **Step 5: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "TAC Instagram tab: workspace switcher + empty screen shells"
```

---

### Task 6: "Today" screen frontend

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `GET /api/tac-instagram/today` (Task 4), the workspace shell (Task 5).
- Produces: `renderTacToday()`, wired as the default `S.tacPage`.

- [ ] **Step 1: Implement `renderTacToday()`.** Fetches `/api/tac-instagram/today`, renders today's date/day heading, one card per action (`time`, `task`, a "Mark done" toggle stored in `localStorage` keyed by date+task since "done" here is a same-day UI convenience, not persisted state worth a DB column), and where `suggested_topic` is present: the topic name, its `community_question` text, and a "Copy" button (`navigator.clipboard.writeText`). Below the cards, the static Farm -> Collect -> Build -> Publish -> Repeat strip (plain text/icons, no interactivity needed here - the working action is the per-card Copy button and Task 10's Build-carousel button, added later without changing this task's markup shape).

- [ ] **Step 2: Verify manually.** Boot, open TAC Instagram -> Today. Confirm today's real day-of-week actions show (check against the actual weekday on the machine), the suggested topic text matches a real row from `tac_topic_bank`, and Copy actually populates the clipboard (paste into a text field to confirm).

- [ ] **Step 3: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "TAC Instagram tab: Today screen (weekly checklist + topic suggestion + copy)"
```

---

### Task 7: Topic Bank screen frontend

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `GET/POST /api/tac-instagram/topics`, `POST /api/tac-instagram/topics/{id}/mark-used` (Task 3).
- Produces: `renderTacTopicBank()`.

- [ ] **Step 1: Implement.** Filter row (four dropdowns: pillar, format, engagement, used), a list of topic rows (collapsed: number, topic, format, pillar, engagement; expanded on click: community question, TAC answer, "Mark used" button, angle notes), and an "Add topic" form at the bottom with the same fields as `add_topic`.

- [ ] **Step 2: Verify manually.** Confirm all 118 real topics load, filters narrow the list correctly, "Mark used" flips a row's Used flag and stamps today's date (check via `sqlite3 data/flatwhite.db "select topic, used, used_date from tac_topic_bank where id=...;"`), and a newly added topic appears without a page reload.

- [ ] **Step 3: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "TAC Instagram tab: Topic Bank screen (filter, mark used, add topic)"
```

---

### Task 8: Calendar screen frontend

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `GET/POST /api/tac-instagram/calendar`, `PATCH /api/tac-instagram/calendar/{id}` (Task 3).
- Produces: `renderTacCalendar()`.

- [ ] **Step 1: Implement.** Rows grouped under their `week_label` heading (matching the spreadsheet's "WEEK n" bands), each row showing all eleven columns from the spec, inline-editable (click a cell, edit, blur saves via `PATCH`), Status as a `<select>` with the five options and colour classes (`.status-not-started`, `.status-in-progress`, `.status-scheduled`, `.status-published`, `.status-skipped`) matching the spreadsheet's own colour legend (grey/yellow/blue/green/red). "Add row" opens a small form with three presets as quick-fill buttons (Breaking news bump, Partner promo, Event recap) that prefill `post_type`/`content_pillar`/`notes` per the ad-hoc rules in the spec, plus a fully blank option.

- [ ] **Step 2: Verify manually.** Confirm real imported rows show grouped by week, an inline edit persists (reload the page, confirm it stuck), status colour changes visibly, and each Add-row preset prefills correctly.

- [ ] **Step 3: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "TAC Instagram tab: Calendar screen (week groups, inline edit, status, ad-hoc presets)"
```

---

### Task 9: Quarterly Planner screen frontend + survey-week generation

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `GET/POST /api/tac-instagram/quarterly`, `POST /api/tac-instagram/quarterly/{id}/generate-survey-week` (Task 3).
- Produces: `renderTacQuarterly()`.

- [ ] **Step 1: Implement.** Items grouped under `quarter_label`, each row showing name/type/dates/sponsor flag/notes, a "Generate survey week" button on Survey Campaign rows that calls the endpoint and shows a toast naming the 5 created Calendar rows (e.g. "5 rows added to the Calendar for the week of 2 Jun"), and an add/edit form matching the columns.

- [ ] **Step 2: Verify manually.** Confirm the real 12 quarterly rows load grouped by quarter; click "Generate survey week" on a real Survey Campaign row (e.g. "Graduate Salary Survey", launch 2 Jun 2026) and confirm exactly 5 new rows appear in the Calendar screen for that week, with the right days/times/content pillars.

- [ ] **Step 3: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "TAC Instagram tab: Quarterly Planner screen + survey-week auto-populate"
```

---

### Task 10: "Build carousel" - headless community-carousel skill run

**Files:**
- Modify: `flatwhite/dashboard/api.py` (new route)
- Modify: `flatwhite/dashboard/static/index.html` (button + poll on the Today screen)
- Test: `tests/test_tac_instagram_api.py` (append)

**Interfaces:**
- Consumes: `flatwhite.dashboard.skill_runner.start_run` (existing), a topic's sorted screenshot folder under `~/Documents/MISC/instagram-dm-screenshotter/output/` (existing convention, same one Big Conversation already reads), `flatwhite.db.save_bank_item` (existing, used by Content Bank).
- Produces: `POST /api/tac-instagram/build-carousel/{topic_id}` -> builds the `claude -p` argv invoking the `community-carousel` skill against that topic's folder, `cwd` = the Instagram DM screenshotter project directory (same as the existing Big Conversation skill run), starts it via `skill_runner.start_run("tac-carousel-build", f"tac-carousel-{topic_id}", argv, cwd=..., on_complete=...)`. The `on_complete` callback parses the run's output and calls `save_bank_item(segment_type="tac_instagram_carousel", title=<topic name>, body_text=<carousel script>, source_note=f"Built {date}")`. Returns `{"run_id": ..., "started": ...}`; concurrency-cap `RuntimeError` maps to 429, exactly like the existing Big Conversation and Brains Trust refresh routes. Progress is polled via the pre-existing `GET /api/skill-run/{run_id}` - no new status endpoint.

- [ ] **Step 1: Write the failing tests.** Mirror `tests/test_brains_trust_refresh.py`'s endpoint tests: patch `skill_runner.start_run` to avoid a real Claude run, assert the argv/cwd/key shape, assert the 429 mapping, assert `on_complete` calls `save_bank_item` with the right `segment_type` when given a fake completed-run record.

- [ ] **Step 2: Run tests to verify they fail.** Expected: `404`.

- [ ] **Step 3: Implement the route.**

- [ ] **Step 4: Run tests to verify they pass.**

- [ ] **Step 5: Wire the frontend.** On the Today screen (Task 6), once a topic's card has been marked "farmed" (its local "Mark done" toggle for the Farm step), show a "Build carousel" button that calls the new endpoint and polls `GET /api/skill-run/{run_id}` exactly like the existing `pollBigConvRun`/`pollBrainsRefreshRun` functions do (same "Working..." -> done/failed pattern, same plain-English failure message, never a hung spinner).

- [ ] **Step 6: Verify LIVE against a real topic folder.** Pick a topic with a real sorted screenshot folder under the Instagram DM screenshotter output directory, click Build carousel, confirm it actually runs the skill (this takes a few minutes, matches the existing Big Conversation run time), and that a new Content Bank item appears with `segment_type="tac_instagram_carousel"` once done. This is the acceptance gate for this task - do not mark it complete on mocked tests alone.

- [ ] **Step 7: Commit.**
```bash
git add flatwhite/dashboard/api.py flatwhite/dashboard/static/index.html tests/test_tac_instagram_api.py
git commit -m "TAC Instagram tab: headless Build-carousel run via community-carousel skill"
```

---

### Task 11: Content Bank screen (reuse, filtered)

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: the existing `GET /api/content-bank?segment_type=...` route (already built for Flat White, unchanged).
- Produces: `renderTacContentBank()`.

- [ ] **Step 1: Implement.** Calls `GET /api/content-bank?segment_type=tac_instagram_carousel` (and any other `tac_instagram_*` segment types introduced later), renders using the same list/card pattern the existing Flat White Content Bank page already uses (reuse that rendering logic as a shared helper rather than copy-pasting the markup, if the existing code is already a separable function; otherwise adapt it directly here) - no new backend work.

- [ ] **Step 2: Verify manually.** After Task 10 has produced at least one real carousel, confirm it shows up here.

- [ ] **Step 3: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "TAC Instagram tab: Content Bank screen (reuses existing shared table)"
```

---

### Task 12: End-to-end verification against Victor's real data

**Files:** none (verification only).

- [ ] **Step 1:** `.venv/bin/python -m pytest -q` - confirm the full suite's failure count matches baseline plus only pre-existing/unrelated failures (per Global Constraints).
- [ ] **Step 2:** Boot the dashboard, walk every screen in order: Today (confirm today's real weekday actions and a real suggested topic), Topic Bank (confirm 118 topics, filters, mark-used), Calendar (confirm real imported weeks, an edit persists, an ad-hoc preset works), Quarterly Planner (confirm 12 real items, survey-week generation writes real Calendar rows), Content Bank (confirm the Task 10 carousel appears).
- [ ] **Step 3:** Confirm the Flat White workspace still works exactly as before (running order, drag-reorder, every existing segment) - this build must be additive only.
- [ ] **Step 4:** Grep the new frontend/backend code for em dashes (the U+2014 character, not a plain hyphen): `grep -n $'\xe2\x80\x94' flatwhite/dashboard/static/index.html flatwhite/dashboard/tac_instagram_state.py flatwhite/dashboard/api.py scripts/import_tac_instagram_calendar.py` - expect no matches in the new code (pre-existing matches elsewhere in the file are not this plan's concern).
- [ ] **Step 5:** Report to Victor: what works, what (if anything) needed fixing, and the three open questions from the spec (PS Dash's outer switcher, Calendar kanban board, "Mark used" enforcement) - his call on each, not assumed.
- [ ] **Step 6:** Stop the server. Tell Victor this is built and tested locally, not deployed anywhere else (there is nowhere else to deploy it to right now - see FW `CLAUDE.md`'s GCP VM note).

---

## Self-Review Notes

- **Spec coverage:** all five screens (Task 6-9, 11), the farm loop's Copy-to-clipboard convenience (Task 6), the one new headless skill run (Task 10), the shared Content Bank (Task 11), the workspace switcher (Task 5), the one-time import from the real spreadsheet (Task 1) - all covered. The spec's "cross-link, don't duplicate" rule for Wednesday/Big Conversation topics is implemented as a suggestion-only pointer in Task 4/6 (no second Big Conversation pipeline is built).
- **Out-of-scope items honoured:** no kanban board, no Instagram posting API, no Reel tooling, no PS Dash changes - none of the 12 tasks touch anything outside the FW repo or add posting/scheduling automation.
- **Type/interface consistency:** `tac_instagram_state.py`'s function signatures (Task 2) are used identically by the API routes (Task 3-4, 10) and by the frontend's expected JSON shapes (Task 6-9, 11).
- **No placeholders left unresolved:** Task 5's stub screens are explicitly filled by name in Tasks 6-9; nothing is left as "TODO" after Task 12.
