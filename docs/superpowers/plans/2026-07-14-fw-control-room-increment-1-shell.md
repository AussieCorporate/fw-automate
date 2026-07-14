# FW Control Room Increment 1 — the Shell, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Flat White dashboard UI from its current sidebar-of-pages into the control-room master/detail layout: a left white sidebar holding the edition's running order (draggable segments with status dots), and a right pane showing the selected segment as its own working page. No behaviour of the existing generators changes yet; this is the frame.

**Architecture:** Flat White's dashboard is a single static HTML SPA (`flatwhite/dashboard/static/index.html`) with a hand-rolled router: a state object `S`, a `NAV_ITEMS` array, `nav(page)` -> `loadPageData(page)` -> `render()` which switches on `S.page` to a `renderX(el)` per section. This increment replaces the nav rendering and page frame with the running-order sidebar + detail pane, keeps every existing `renderX` working inside the new detail pane, adds drag-to-reorder and a per-segment ready/not-ready status, and restyles to the PS Dash iOS token system. Backend routes are untouched.

**Tech Stack:** single static HTML/CSS/JS (no build step, no framework), FastAPI (`flatwhite/dashboard/api.py`) unchanged, `pytest` via FW's own venv.

## Global Constraints

- **Runs on FW's venv only:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python 3.9 breaks FW. Never use another interpreter for FW.
- Branch: from `main`, `git checkout main && git checkout -b fw-control-room-shell`. FW deploy is Victor's (GCP VM); built + tested locally only, not merged/pushed/deployed.
- **FW test baseline:** run `.venv/bin/python -m pytest -q` first and record the exact pass/fail counts (recent runs: ~124 passed / ~8 pre-existing failures unrelated to the UI). After every task the non-pre-existing failure count must stay zero; UI-only changes should not move the Python suite at all.
- No em dashes (U+2014) in any reader-facing string. Australian spelling.
- Additive/surgical to `index.html`: do NOT change any `renderX(el)` section function's internal content or any `/api/*` call in this increment. Only the nav + page frame + styling change. The five kept segments (Pulse, Big Conversation, Off the Clock, Top Picks, Editorial) must still render and function exactly as before, now inside the detail pane.
- No JS build/test harness exists: verify via `curl` presence checks against the running dashboard + a manual click script, plus the Python suite staying at baseline.
- Local run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`. Kill it when done.

## Design reference

The agreed layout is in the mockup and the spec (`docs/superpowers/specs/2026-07-14-flat-white-control-room-design.md`). Visual target: PS Dash's iOS tokens — soft grey background `#f2f2f7`, one accent `#6c63ff`, white cards, hairline separators, `--r-card:14px`. Left sidebar is a WHITE card. Active segment highlights in soft accent. Restrained copy.

## Current-structure anchors (verify exact line numbers before editing)

- `flatwhite/dashboard/static/index.html` (~2518 lines). Key JS: state `S` (~line 270+), `NAV_ITEMS` array (~395-409), `nav(page)` (~411), `loadPageData(page)` (~418-477), `render()` (~573) with the `S.page` switch to `renderPulse/renderBigConv/renderOTC/renderTopPicks/renderEditorial` (~579-588). After the FW trim (already merged), `NAV_ITEMS` holds: `editorial, pulse, big_conversation, off_the_clock, top_picks, salary_vault` (salary_vault is a disabled stub).
- Root route serves the file: `flatwhite/dashboard/api.py` `serve_index()` (~line 125).

---

### Task 1: Introduce the iOS design tokens + page skeleton

**Files:** `flatwhite/dashboard/static/index.html`.

**Interfaces:** Produces the CSS custom properties consumed by Tasks 2-3, and the two-column `.layout` (`.side` + `.main`) skeleton.

- [ ] **Step 1: Record baseline.** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -3` — note the counts. Boot the dashboard and confirm it loads today (`curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/` -> 200).

- [ ] **Step 2: Add the token block** at the top of the existing `<style>`:
```css
:root{--bg:#f2f2f7;--card:#fff;--sep:rgba(60,60,67,.11);--label:#1c1c1e;--label2:#8e8e93;--label3:#b7b7c0;
--accent:#6c63ff;--accent-soft:rgba(108,99,255,.09);--green:#34c759;--green-soft:rgba(52,199,89,.13);--green-ink:#248a3d;
--amber-soft:rgba(255,159,10,.15);--amber-ink:#b25e00;--track:#ececf1;--r-card:14px;--r-btn:10px;}
body{background:var(--bg);color:var(--label)}
```
Do not delete existing rules; the new layout classes (Task 2) will use these tokens and the detail pane keeps the existing section styles.

- [ ] **Step 3: Add the layout skeleton CSS** (the master/detail frame + sidebar card + page):
```css
.layout{max-width:1120px;margin:0 auto;padding:0 20px 90px;display:flex;gap:18px;align-items:flex-start}
.side{width:264px;flex:none;position:sticky;top:14px;background:var(--card);border:1px solid var(--sep);border-radius:var(--r-card);padding:14px 12px}
.main{flex:1;min-width:0}
.page{background:var(--card);border-radius:var(--r-card);border:1px solid var(--sep);overflow:hidden}
.page-h{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:.5px solid var(--sep)}
.page-h h2{margin:0;font-size:18px;font-weight:700;flex:1}
.page-b{padding:18px 20px}
@media(max-width:820px){.layout{flex-direction:column}.side{width:100%;position:static}}
```

- [ ] **Step 4: Verify + commit.** Boot, confirm `/` still 200 and renders (the old UI may look transitional here since Task 2 wires the layout). `.venv/bin/python -m pytest -q` unchanged.
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "FW control room shell: iOS design tokens + master/detail layout skeleton"
```

---

### Task 2: The running-order sidebar (draggable + status)

**Files:** `flatwhite/dashboard/static/index.html`.

**Interfaces:**
- Consumes the tokens/skeleton from Task 1.
- Produces JS: a `SEGMENTS` array `[{id, name, status}]` (status in `ready|notready|manual`), `renderSidebar()`, `selectSegment(id)`, and drag handlers `dragStart/dragOver/drop/dragEnd`. `id` values map to the existing section keys (`editorial, brains? , pulse, big_conversation, off_the_clock, top_picks`) plus new-but-inert placeholders for segments that arrive in later increments (`brains, insidetrack, thread`) which for now render a simple "coming next" page.
- The default order (draggable): `editorial, brains, top_picks, insidetrack, pulse, off_the_clock, thread, big_conversation`.

- [ ] **Step 1: Add the sidebar CSS:**
```css
.side-cap{color:var(--label3);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin:2px 6px 9px;display:flex;justify-content:space-between}
.navlist{display:flex;flex-direction:column;gap:3px}
.nav-card{border-radius:10px;display:flex;align-items:center;gap:10px;padding:9px 11px;cursor:pointer}
.nav-card:hover{background:rgba(0,0,0,.035)}
.nav-card.active{background:var(--accent-soft)}
.nav-card.active .n-name{color:var(--accent)}
.nav-card.dragging{opacity:.45}.nav-card.dragover{box-shadow:0 0 0 2px var(--accent)}
.handle{cursor:grab;color:var(--label3);font-size:13px;opacity:0}
.nav-card:hover .handle,.nav-card.active .handle{opacity:1}
.nord{width:18px;color:var(--label3);font-size:11px;font-weight:700;text-align:center}
.ndot{width:8px;height:8px;border-radius:50%}
.n-ready{background:var(--green)}.n-notready{background:var(--label3)}.n-manual{background:#ff9f0a}
.n-name{font-weight:600;font-size:14px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.navdiv{height:1px;background:var(--sep);margin:14px 6px}
.nav-lite{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:10px;cursor:pointer;color:var(--label2);font-size:14px}
.nav-lite:hover{background:rgba(0,0,0,.035)}.nav-lite.active{background:var(--accent-soft);color:var(--accent);font-weight:600}
```

- [ ] **Step 2: Add the sidebar markup** in `<body>` — wrap the existing content so the app is `<div class="layout"><div class="side">…</div><div class="main"><div class="page" id="page"></div></div></div>`. The sidebar:
```html
<div class="side">
  <div class="side-cap"><span>Running order</span><span id="readyStat"></span></div>
  <div class="navlist" id="navlist"></div>
  <div class="navdiv"></div>
  <div class="nav-lite" id="nl-bank" onclick="selectSegment('bank')">Content bank</div>
  <div class="nav-lite" id="nl-sources" onclick="selectSegment('sources')">Sources</div>
</div>
```

- [ ] **Step 3: Add the JS.** Define `SEGMENTS` (default order above, statuses default `notready` except `pulse` if it already has content), `renderSidebar()` producing the `.nav-card`s with drag attributes, and the HTML5 drag handlers that reorder `SEGMENTS` and re-render. `selectSegment(id)` sets `S.page = id` (reuse the existing state var) and calls the existing `loadPageData`/`render` path (Task 3 adapts `render` to draw into `#page`). Status dot class from `n-<status>`. `readyStat` shows `<n ready>/<total>`.

- [ ] **Step 4: Verify.** Boot. `curl -s http://127.0.0.1:8500/ | grep -c 'class="navlist"'` -> 1; `grep -c 'function renderSidebar'` -> 1. Manual: the left sidebar shows the running order; clicking a segment selects it (Task 3 makes the right pane render it); dragging a card by the handle reorders the list. Kill server.

- [ ] **Step 5: Commit.**
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "FW control room shell: running-order sidebar with drag-reorder + status dots"
```

---

### Task 3: Route each segment's existing renderer into the detail page

**Files:** `flatwhite/dashboard/static/index.html`.

**Interfaces:** consumes Task 2's `selectSegment`/`SEGMENTS`. Produces the detail-pane render: each existing `renderX(el)` now draws inside `#page` under a `.page-h` header (segment name + a status pill), and the new placeholder segments render a minimal "coming in a later increment" page.

- [ ] **Step 1: Adapt `render()`** so that instead of the old page container it targets `#page`, wrapping each section in `<div class="page"><div class="page-h"><h2>{name}</h2><span class="stat" onclick="toggleReady('{id}')">{status}</span></div><div class="page-b">…existing renderX output…</div></div>`. Map `S.page` id -> the existing renderer: `editorial->renderEditorial`, `pulse->renderPulse`, `big_conversation->renderBigConv`, `off_the_clock->renderOTC`, `top_picks->renderTopPicks`. For `brains`, `insidetrack`, `thread`, `bank`, `sources`: render a simple placeholder page ("This section arrives in a later increment.") so the nav is complete without breaking. Do NOT modify the bodies of the existing `renderX` functions — call them into the `.page-b`.
- [ ] **Step 2: Add the status pill CSS + `toggleReady`:**
```css
.stat{font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;cursor:pointer}
.s-ready{background:var(--green-soft);color:var(--green-ink)}.s-notready{background:var(--track);color:var(--label2)}.s-manual{background:var(--amber-soft);color:var(--amber-ink)}
```
`toggleReady(id)` flips the segment's status in `SEGMENTS` between `ready`/`notready` and re-renders the sidebar + header.
- [ ] **Step 3: Default selection.** On load, `selectSegment(SEGMENTS[0].id)` (editorial) so the app opens on a real page. Confirm exactly one segment is active.
- [ ] **Step 4: Verify (presence + manual).** Boot.
```bash
curl -s http://127.0.0.1:8500/ | grep -c 'id="page"'        # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function toggleReady' # 1
```
Manual click script: open `/`; the left sidebar lists the running order and the right pane shows the Editorial page; click Pulse -> the existing Pulse content renders inside the detail pane and still works (its Proceed/generate still functions); click Big Conversation / Off the Clock / Top Picks -> each existing section renders in the pane unchanged; click a placeholder (Brains Trust) -> the "coming later" page; toggle a status pill -> the sidebar dot updates; drag to reorder -> order persists. Kill server.
- [ ] **Step 5: Python suite unchanged + commit.** `.venv/bin/python -m pytest -q` (baseline). 
```bash
git add flatwhite/dashboard/static/index.html
git commit -m "FW control room shell: render each segment as a detail page; status toggle; default selection"
```

---

## Manual verification (whole increment, before done)

1. `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`.
2. Left = white sidebar card with the running order; right = the selected segment's page.
3. The five real segments (Editorial, Pulse, Big Conversation, Off the Clock, Top Picks) each render in the detail pane and STILL generate/function exactly as before (nothing about their logic changed).
4. Drag reorders the running order; status pills flip ready/not-ready and update the sidebar dots; Content bank / Sources open placeholder pages.
5. FW Python suite at baseline (no new failures).

Report the FW suite counts and "built locally on branch `fw-control-room-shell`, NOT merged, NOT deployed (FW deploy is Victor's)."

## Notes for later increments (not this plan)

- Increment 2 turns the five detail pages into the generate/process -> edit -> mark-ready pattern (Editorial gating + big-story, OTC 5-cat + swap + custom, Top Picks features + selectable, Pulse edit, Thread paste->format block).
- The placeholder segments (Brains Trust, Inside Track) get real pages in increments 5-6; Big Conversation's topic-bank/screenshot flow is increment 4; the embed in PS Dash already exists (it iframes port 8500), so this new UI shows there automatically once merged.
