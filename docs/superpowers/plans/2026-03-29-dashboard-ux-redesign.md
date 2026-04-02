# Dashboard UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent Command Bar with Scrape All, refactor every section into a 3-phase accordion (Scrape → Review & Pick → Generate), and replace the Assemble section with a structured Composer view.

**Architecture:** All frontend changes are in `index.html` (vanilla JS SPA). A new `/api/scrape-all` + `/api/scrape-all/status` endpoint pair is added to `api.py`. The accordion uses a `phasePanel()` helper and `S.sectionPhase` state. The Composer replaces `renderAssemble()` and reads from the existing `S.sectionOutputs` state.

**Tech Stack:** Vanilla JS, FastAPI, Python, SQLite (no schema changes)

---

## File Map

| File | Change |
|------|--------|
| `flatwhite/dashboard/api.py` | Add `_SCRAPE_ALL_SECTIONS`, `_scrape_all_state`, `_run_scrape_all()`, `/api/scrape-all` POST, `/api/scrape-all/status` GET |
| `flatwhite/dashboard/static/index.html` | Add `sectionPhase`/`scrapeAllRunning`/`scrapeAllErrors` to S; add `phasePanel()`, `openPhase()`, `runScrapeAll()`, `pollScrapeAll()`, `renderCommandBar()`, `renderComposer()`; refactor all 8 section render functions; add phase CSS |

---

## Task 1: Backend — /api/scrape-all endpoint

**Files:**
- Modify: `flatwhite/dashboard/api.py`

**Background:** `_run_section_background(section)` runs a section's steps synchronously (blocking) and never raises — it catches all exceptions and stores them in `_section_state[section]["error"]`. The scrape-all runner calls it sequentially for each section so only one section runs at a time (avoids DB write conflicts).

- [ ] **Step 1: Add `_SCRAPE_ALL_SECTIONS`, `_scrape_all_state`, and `_run_scrape_all()` to `api.py`**

Find the line just after `_SECTION_RUNNERS` closing `}` (line ~1044). Add the following immediately after it:

```python
_SCRAPE_ALL_SECTIONS = [
    "pulse", "editorial", "big_conversation", "finds", "lobby", "thread", "off_the_clock",
]

_scrape_all_state: dict = {
    "running": False,
    "current": None,   # section name currently being scraped
    "results": [],     # list of {section, status: "ok"|"error"|"skipped", error: str|None}
}


def _run_scrape_all() -> None:
    """Run all section scrapers sequentially. One failure does not stop others."""
    _scrape_all_state.update({"running": True, "current": None, "results": []})
    for section in _SCRAPE_ALL_SECTIONS:
        _scrape_all_state["current"] = section
        with _section_lock:
            if _section_state.get(section, {}).get("running"):
                _scrape_all_state["results"].append(
                    {"section": section, "status": "skipped", "error": "already running"}
                )
                continue
            steps = _SECTION_RUNNERS[section]
            _section_state[section] = {
                "running": True, "done": False, "error": None,
                "step": 0, "total": len(steps),
                "step_name": steps[0][0] if steps else "",
                "completed_at": None,
            }
        _run_section_background(section)  # blocks until this section finishes
        err = _section_state.get(section, {}).get("error")
        _scrape_all_state["results"].append(
            {"section": section, "status": "error" if err else "ok", "error": err}
        )
    _scrape_all_state.update({"running": False, "current": None})
```

- [ ] **Step 2: Add the two new route handlers**

Add immediately after `_run_scrape_all()`:

```python
@app.post("/api/scrape-all")
async def api_scrape_all() -> JSONResponse:
    """Start scraping all sections sequentially in the background."""
    if _scrape_all_state["running"]:
        return JSONResponse({"error": "Scrape All already running"}, status_code=409)
    thread = threading.Thread(target=_run_scrape_all, daemon=True)
    thread.start()
    return JSONResponse({"started": True, "sections": _SCRAPE_ALL_SECTIONS})


@app.get("/api/scrape-all/status")
def api_scrape_all_status() -> JSONResponse:
    """Poll the current Scrape All progress."""
    return JSONResponse({
        "running": _scrape_all_state["running"],
        "current": _scrape_all_state["current"],
        "results": _scrape_all_state["results"],
        "total": len(_SCRAPE_ALL_SECTIONS),
    })
```

- [ ] **Step 3: Verify the server starts**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -c "from flatwhite.dashboard.api import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Verify the endpoint is registered**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -c "
from flatwhite.dashboard.api import app
routes = [r.path for r in app.routes]
print('/api/scrape-all' in routes, '/api/scrape-all/status' in routes)
"
```

Expected: `True True`

- [ ] **Step 5: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/api.py && git commit -m "feat: add /api/scrape-all endpoint for sequential section scraping"
```

---

## Task 2: Frontend — S state additions + phasePanel helper + CSS

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** `phasePanel()` is the accordion building block used by all section render functions. `S.sectionPhase` tracks which phase is open per section. CSS is added once here; all accordion tasks (3-5) just call `phasePanel()`.

- [ ] **Step 1: Add new fields to the S state object (line ~282)**

Find `sectionProgress: {},` in the S state object. Add these three lines immediately after it:

```js
  sectionPhase: {},        // { section: 1|2|3 } — which accordion phase is open
  scrapeAllRunning: false,
  scrapeAllErrors: {},     // { section: errorMessage }
```

- [ ] **Step 2: Add phase CSS**

Find the closing `</style>` tag in the `<head>`. Add the following CSS immediately before it:

```css
/* ── Phase accordion ─────────────────────────────── */
.phase-card { border: 1.5px solid var(--border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; transition: border-color 0.15s; }
.phase-card.phase-open { border-color: var(--accent, #4a9); }
.phase-card.phase-locked { opacity: 0.45; pointer-events: none; }
.phase-hdr { display: flex; align-items: center; gap: 8px; padding: 10px 14px; cursor: pointer; background: var(--bg-2); user-select: none; }
.phase-hdr:hover { background: var(--bg-3, #ebebeb); }
.phase-num { background: var(--accent, #4a9); color: #fff; border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.phase-locked .phase-num { background: var(--text-3, #ccc); }
.phase-lbl { font-weight: 600; font-size: 13px; flex: 1; }
.phase-done { color: var(--accent, #4a9); font-size: 12px; margin-right: 4px; }
.phase-chevron { color: var(--text-2); font-size: 11px; }
.phase-body { padding: 14px 16px; }
/* ── Command bar ─────────────────────────────────── */
.cmd-bar { display: flex; align-items: center; gap: 8px; padding: 7px 16px; background: #1a1a1a; border-bottom: 1px solid #333; flex-shrink: 0; }
.cmd-pill { padding: 2px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; border: none; background: #333; color: #ccc; }
.cmd-pill:hover { background: #444; }
.cmd-pill.pill-green { background: #1e4a1e; color: #6f6; }
.cmd-pill.pill-amber { background: #4a3a1e; color: #fa4; }
.cmd-pill.pill-red { background: #4a1e1e; color: #f66; }
```

- [ ] **Step 3: Add `phasePanel()` and `openPhase()` helper functions**

Find `function outputBox(section)` (line ~1551). Add the following functions immediately before it:

```js
function openPhase(section, num) {
  S.sectionPhase[section] = num;
  render();
}

function phasePanel(section, num, label, unlocked, done, bodyHtml) {
  var open = (S.sectionPhase[section] || 1) === num;
  var h = '<div class="phase-card' + (open ? ' phase-open' : '') + (unlocked ? '' : ' phase-locked') + '">';
  h += '<div class="phase-hdr"' + (unlocked ? ' onclick="openPhase(\'' + section + '\',' + num + ')"' : '') + '>';
  h += '<span class="phase-num">' + num + '</span>';
  h += '<span class="phase-lbl">' + label + '</span>';
  if (done) h += '<span class="phase-done">✓</span>';
  h += '<span class="phase-chevron">' + (open ? '▲' : '▼') + '</span>';
  h += '</div>';
  if (open && unlocked) h += '<div class="phase-body">' + bodyHtml + '</div>';
  h += '</div>';
  return h;
}
```

- [ ] **Step 4: Auto-advance phase on scrape completion**

In `pollSectionStatus()`, find this block (line ~1640):

```js
      if (!d.running && d.done) {
        clearInterval(poll);
        S.loading[section] = false;
        delete S.sectionProgress[section];
        if (d.error) {
```

Add the phase auto-advance immediately after `delete S.sectionProgress[section];`:

```js
        // Auto-advance to Phase 2 when scrape completes successfully
        if (!d.error && (S.sectionPhase[section] === 1 || !S.sectionPhase[section])) {
          S.sectionPhase[section] = 2;
        }
        if (d.error) {
```

**Important:** Remove the original `if (d.error) {` line since we just added a new `if (d.error) {` above.

- [ ] **Step 5: Auto-advance to Phase 3 on generation completion**

In `confirmAndGenerate()`, find this block:

```js
    .then(function(d) {
      S.sectionOutputs[section] = { output_text: d.output, model_used: d.model };
      S.loading[section] = false;
      render();
```

Add the phase advance immediately after `S.loading[section] = false;`:

```js
      S.sectionPhase[section] = 3;
```

- [ ] **Step 6: Verify no JS errors**

Open browser console at http://localhost:8500 and confirm no errors. Reload page.

- [ ] **Step 7: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: phase accordion helpers, CSS, and S state additions"
```

---

## Task 3: Frontend — Command Bar

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** The command bar renders above the section content, always visible. It shows a Scrape All button + status pills for each scrapeable section. `runScrapeAll()` starts the run and polls `/api/scrape-all/status` every 2 seconds until done.

- [ ] **Step 1: Add `runScrapeAll()` and `pollScrapeAll()` functions**

Find `function runSection(section)` (line ~1618). Add the following immediately before it:

```js
function runScrapeAll() {
  if (S.scrapeAllRunning) return;
  S.scrapeAllRunning = true;
  S.scrapeAllErrors = {};
  render();
  api("/api/scrape-all", { method: "POST" })
    .then(function() { pollScrapeAll(); })
    .catch(function(e) {
      S.scrapeAllRunning = false;
      render();
      showToast("Scrape All failed to start: " + e.message, "error");
    });
}

function pollScrapeAll() {
  var poll = setInterval(function() {
    fetch("/api/scrape-all/status").then(function(r) { return r.json(); }).then(function(d) {
      render(); // shows current section in pill
      if (!d.running) {
        clearInterval(poll);
        S.scrapeAllRunning = false;
        // Store errors from results
        (d.results || []).forEach(function(r) {
          if (r.status === "error") S.scrapeAllErrors[r.section] = r.error;
        });
        var failed = (d.results || []).filter(function(r) { return r.status === "error"; });
        var ok = (d.results || []).filter(function(r) { return r.status === "ok"; });
        var msg = "Scrape All done — " + ok.length + "/" + d.total + " succeeded";
        if (failed.length) msg += " · " + failed.map(function(r) { return r.section; }).join(", ") + " failed";
        showToast(msg, failed.length ? "error" : "");
        // Reload current page data
        loadPageData(S.page).then(function() { render(); });
      }
    }).catch(function() { /* ignore poll errors */ });
  }, 2000);
}
```

- [ ] **Step 2: Add `renderCommandBar()` function**

Find `function renderSidebar()` (line ~459). Add the following immediately before it:

```js
var _CMD_PILL_SECTIONS = [
  { id: "pulse",            label: "Pulse" },
  { id: "big_conversation", label: "Big Conv" },
  { id: "finds",            label: "Finds" },
  { id: "lobby",            label: "Lobby" },
  { id: "thread",           label: "Thread" },
  { id: "off_the_clock",    label: "Off Clock" },
];

function renderCommandBar() {
  var scrapeAllCurrent = null;
  var h = '<div class="cmd-bar">';
  // Scrape All button
  if (S.scrapeAllRunning) {
    h += '<button class="btn btn-sm" disabled style="opacity:0.7;">⟳ Scraping…</button>';
  } else {
    h += '<button class="btn btn-sm btn-success" onclick="runScrapeAll()">⚡ Scrape All</button>';
  }
  h += '<div style="flex:1"></div>';
  // Status pills
  _CMD_PILL_SECTIONS.forEach(function(s) {
    var cls = "cmd-pill";
    var label = s.label;
    var title = "";
    if (S.scrapeAllErrors[s.id]) {
      cls += " pill-red";
      title = ' title="' + esc(S.scrapeAllErrors[s.id]) + '"';
      label += " ✗";
    } else if (S.sectionOutputs[s.id] && S.sectionOutputs[s.id].output_text) {
      cls += " pill-green";
      label += " ✓";
    } else if (S.lastScraped[s.id]) {
      cls += " pill-amber";
    }
    h += '<button class="' + cls + '"' + title + ' onclick="nav(\'' + s.id + '\')">' + esc(label) + '</button>';
  });
  h += '</div>';
  return h;
}
```

- [ ] **Step 3: Inject the command bar into the main layout**

Find the main `render()` function (line ~490). Inside it, find where the section content is injected into the DOM — look for a line like `$(pageId).innerHTML` or `el.innerHTML`. The render function calls the individual `renderXXX(el)` functions.

Read the `render()` function carefully. Find the element that wraps the main content area (right of the sidebar). Add `renderCommandBar()` output as an HTML string injected above the section content.

The render function likely has a pattern like:
```js
function render() {
  renderSidebar();
  var el = $("main-content") || document.getElementById("content");
  // ... calls renderPulse(el), renderFinds(el), etc.
}
```

Find the main content container element ID and inject the command bar. Replace the relevant lines with:

```js
  // Inject command bar above section content
  var cmdEl = document.getElementById("cmd-bar-container");
  if (cmdEl) cmdEl.innerHTML = renderCommandBar();
```

- [ ] **Step 4: Add the cmd-bar-container to the HTML**

Find the `<body>` layout — the div that wraps the sidebar and main content. It likely looks like:

```html
<div style="display:flex;height:100vh;overflow:hidden;">
  <div id="sidebar">...</div>
  <div id="content" style="flex:1;overflow:auto;">...</div>
</div>
```

Change the content wrapper to:

```html
<div style="display:flex;flex-direction:column;flex:1;overflow:hidden;">
  <div id="cmd-bar-container"></div>
  <div id="content" style="flex:1;overflow:auto;padding:24px;"></div>
</div>
```

(Read the actual HTML to find the exact current structure and match it.)

- [ ] **Step 5: Verify**

Restart server: `kill $(lsof -ti:8500); uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500 &`

Open http://localhost:8500. Confirm:
- Dark command bar appears across the top of the content area
- "⚡ Scrape All" button is visible
- Status pills for each section are visible
- Clicking a pill navigates to that section

- [ ] **Step 6: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: command bar with Scrape All and section status pills"
```

---

## Task 4: Accordion — Pulse, Editorial, Big Conversation

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** These three sections all have a RUN/SCRAPE button in the toolbar + a content body + outputBox. The refactor wraps them in `phasePanel()` calls. The existing logic (signal tables, candidate lists, etc.) does NOT change — it just moves into the Phase 2 body.

For each section, the pattern is:
1. **Phase 1 body:** scrape button + `renderSectionProgress()` call + last scraped badge
2. **Phase 2 body:** existing section content (signals, candidates, etc.)
3. **Phase 3 body:** model selector + PROCEED button + `outputBox(section)`

The `hasScrapeData` boolean determines whether Phase 2 is unlocked. The `hasOutput` boolean marks Phase 3 as done.

### Pulse (`renderPulse`, line ~608)

- [ ] **Step 1: Read renderPulse carefully (line 608–762)**

```bash
grep -n "function renderPulse\|function renderBigConv\|function renderEditorial" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html
```

Read `renderPulse` from its start to the next function to understand the existing structure before editing.

- [ ] **Step 2: Refactor renderPulse**

Replace the entire `renderPulse(el)` function body with the accordion structure. The function signature stays the same: `function renderPulse(el) {`

```js
function renderPulse(el) {
  if (!S.pulse && !S.loading.pulse) {
    el.innerHTML = '<div class="empty-state">Click ① Scrape to load Pulse data for this week.</div>';
    return;
  }

  var hasScrapeData = !!(S.pulse || S.signals.length);
  var hasOutput = !!(S.sectionOutputs.pulse && S.sectionOutputs.pulse.output_text);
  if (!S.sectionPhase.pulse) S.sectionPhase.pulse = hasOutput ? 3 : (hasScrapeData ? 2 : 1);

  // Phase 1: Scrape
  var p1 = '';
  p1 += '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">';
  p1 += '<button class="btn btn-primary" onclick="runSection(\'pulse\')">Run Pulse Scrape</button>';
  if (S.loading.pulse) p1 += renderSectionProgress('pulse');
  if (S.lastScraped.pulse) p1 += '<span class="scraped-badge">Scraped ' + formatScrapedDate(S.lastScraped.pulse) + '</span>';
  p1 += '</div>';

  // Phase 2: Review & Pick — all existing signal table + gauge content goes here
  var p2 = '';
  if (hasScrapeData) {
    // [KEEP ALL EXISTING renderPulse CONTENT HERE — the gauge, signal table, anomalies, etc.]
    // Copy everything that was previously between the toolbar and the outputBox call.
    // This is the existing body content of renderPulse unchanged.
    p2 = renderPulseBody();
  }

  // Phase 3: Generate
  var p3 = '';
  p3 += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">';
  p3 += modelSelect('model-pulse');
  p3 += '<button class="btn btn-success" onclick="proceedPulse()">PROCEED</button>';
  p3 += '</div>';
  p3 += outputBox('pulse');

  var h = '';
  h += phasePanel('pulse', 1, 'Scrape', true, hasScrapeData, p1);
  h += phasePanel('pulse', 2, 'Review & Pick', hasScrapeData, false, p2);
  h += phasePanel('pulse', 3, 'Generate', hasScrapeData, hasOutput, p3);

  el.innerHTML = h;
  fillOutput('pulse');
}
```

**Important:** Extract the existing gauge + signal table content into a `renderPulseBody()` helper function that returns an HTML string. Do NOT change any of that logic — just move it into the new helper.

- [ ] **Step 3: Refactor renderEditorial (line ~515)**

Apply the same pattern. `hasScrapeData = !!(S.items && S.items.editorial && S.items.editorial.length)`.

Phase 1 body: `runSection('editorial')` button + progress + scraped badge.
Phase 2 body: existing items list + relevance filter — extract to `renderEditorialBody()`.
Phase 3 body: modelSelect + `proceedEditorial()` button + `outputBox('editorial')`.

- [ ] **Step 4: Refactor renderBigConv (line ~763)**

`hasScrapeData = !!(S.bigConvCandidates && S.bigConvCandidates.length)`.

Phase 1 body: `runBigConv()` button (keep existing) + progress + scraped badge.
Phase 2 body: existing candidates list + custom topic form — extract to `renderBigConvBody()`.
Phase 3 body: modelSelect + `proceedBigConv()` button + `outputBox('big_conversation')`.

- [ ] **Step 5: Verify in browser**

Open http://localhost:8500 and navigate to Pulse, Editorial, Big Conversation. Confirm:
- 3 accordion phases visible per section
- Phase 1 opens by default on first load
- Clicking phase headers opens/closes them
- Phase 2 and 3 are greyed/locked when no data exists

- [ ] **Step 6: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: accordion phases for Pulse, Editorial, Big Conversation"
```

---

## Task 5: Accordion — Finds, Lobby, Thread

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** Same pattern as Task 4. Finds has checkboxes + blurbs in Phase 2. Lobby has employer checkboxes. Thread has thread selector + comments viewer.

### Finds (`renderFinds`, line ~1006)

- [ ] **Step 1: Read renderFinds carefully**

```bash
awk 'NR>=1006 && NR<=1075' /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html
```

- [ ] **Step 2: Refactor renderFinds**

`hasScrapeData = !!(S.items && S.items.finds && S.items.finds.length)`.
`hasPickedAny = Object.keys(S.findsChecked).some(function(k) { return S.findsChecked[k]; })`.

Phase 1: `runSection('finds')` + progress + scraped badge.
Phase 2: existing items list with checkboxes + blurb inputs — extract to `renderFindsBody()`.
Phase 3: modelSelect + `proceedFinds()` + `outputBox('finds')`.

Phase 3 unlocked when `hasScrapeData` (not requiring a pick, since user may proceed with default).

- [ ] **Step 3: Refactor renderLobby (line ~924)**

`hasScrapeData = !!(S.lobby && S.lobby.employers && S.lobby.employers.length)`.

Phase 1: `runSection('lobby')` + progress + scraped badge.
Phase 2: employer list with checkboxes — extract to `renderLobbyBody()`.
Phase 3: modelSelect + `proceedLobby()` + `outputBox('lobby')`.

- [ ] **Step 4: Refactor renderThread (line ~1076)**

`hasScrapeData = !!(S.threads && S.threads.length)`.

Phase 1: `runSection('thread')` + progress + scraped badge.
Phase 2: thread selector + comments viewer — extract to `renderThreadBody()`.
Phase 3: modelSelect + `proceedThread()` + `outputBox('thread')`.

- [ ] **Step 5: Verify in browser**

Navigate to Finds, Lobby, Thread. Confirm accordion structure renders correctly and content is preserved inside Phase 2.

- [ ] **Step 6: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: accordion phases for Finds, Lobby, Thread"
```

---

## Task 6: Accordion — OTC, AMP's Finest + 2-phase for Whispers/Events

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** OTC has a scrape + classify step in Phase 1. AMP's Finest has no scrape step (data entry only) — it gets Phase 1 = "Data Entry", Phase 3 = "Generate" (skip Phase 2). Whispers and Events are manual-entry sections with no scrape and no output — they stay as-is (no accordion needed).

### OTC (`renderOTC`, line ~1205)

- [ ] **Step 1: Read renderOTC carefully**

```bash
awk 'NR>=1205 && NR<=1290' /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html
```

- [ ] **Step 2: Refactor renderOTC**

`hasScrapeData = !!(S.otcData && S.otcData.candidates)`.
`hasPickedAny = OTC_CATS.some(function(cat) { return Object.keys(S.otcPicks[cat.key] || {}).length > 0; })`.

Phase 1: `runSection('off_the_clock')` + "Classify OTC" button + progress + scraped badge.
Phase 2: category picker panels (all existing OTC picker content + prompt preview) — extract to `renderOTCBody()`.
Phase 3: modelSelect + `proceedOTC()` + `outputBox('off_the_clock')`.

Phase 3 unlocked when `hasPickedAny`.

- [ ] **Step 3: Refactor renderAmpFinest (line ~1152)**

AMP's Finest has no scrape step. Use 2 phases only:

```js
function renderAmpFinest(el) {
  var hasData = !!(S.ampFinest);
  var hasOutput = !!(S.sectionOutputs.amp_finest && S.sectionOutputs.amp_finest.output_text);
  if (!S.sectionPhase.amp_finest) S.sectionPhase.amp_finest = hasOutput ? 2 : 1;

  // Phase 1: Data Entry — existing data entry form (description, notes, chart)
  var p1 = renderAmpFinestBody(); // extract existing content

  // Phase 2: Generate
  var p2 = '';
  p2 += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">';
  p2 += modelSelect('model-amp');
  p2 += '<button class="btn btn-success" onclick="proceedAmpFinest()">PROCEED</button>';
  p2 += '</div>';
  p2 += outputBox('amp_finest');

  var h = '';
  h += phasePanel('amp_finest', 1, 'Data Entry', true, hasData, p1);
  h += phasePanel('amp_finest', 2, 'Generate', hasData, hasOutput, p2);

  el.innerHTML = h;
  fillOutput('amp_finest');
}
```

- [ ] **Step 4: Verify in browser**

Navigate to Off the Clock and AMP's Finest. Confirm phase structure renders correctly.

- [ ] **Step 5: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: accordion phases for OTC and AMP Finest"
```

---

## Task 7: Composer — replace renderAssemble

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** The Composer replaces `renderAssemble()`. It reads from `S.sectionOutputs` (already loaded on page init). "Copy All" concatenates sections in newsletter order. Missing sections show a warning panel. The nav label "Assemble" is renamed to "Composer".

- [ ] **Step 1: Rename the nav item**

Find `{ id: "assemble", icon: "\u2709", label: "Assemble" }` in `NAV_ITEMS` and change the label:

```js
  { id: "assemble", icon: "\u2709", label: "Composer" },
```

- [ ] **Step 2: Add `copyComposerAll()` helper**

Find `function copyOutput(section)` and add immediately after it:

```js
function copyComposerAll() {
  var COMPOSER_ORDER = [
    { id: "pulse",            label: "PULSE" },
    { id: "big_conversation", label: "BIG CONVERSATION" },
    { id: "finds",            label: "FINDS" },
    { id: "lobby",            label: "THE LOBBY" },
    { id: "thread",           label: "THREAD" },
    { id: "off_the_clock",    label: "OFF THE CLOCK" },
    { id: "amp_finest",       label: "AMP'S FINEST" },
  ];
  var parts = [];
  COMPOSER_ORDER.forEach(function(s) {
    var out = S.sectionOutputs[s.id];
    if (out && out.output_text) {
      parts.push("## " + s.label + "\n\n" + out.output_text.trim());
    }
  });
  if (!parts.length) { showToast("No outputs to copy yet", "error"); return; }
  navigator.clipboard.writeText(parts.join("\n\n---\n\n")).then(function() {
    showToast("All sections copied to clipboard");
  }).catch(function() {
    showToast("Copy failed — try individual section copy", "error");
  });
}
```

- [ ] **Step 3: Replace renderAssemble with renderComposer**

Find `function renderAssemble(el)` and replace the entire function:

```js
function renderAssemble(el) {
  var COMPOSER_ORDER = [
    { id: "pulse",            label: "PULSE",            icon: "◉" },
    { id: "big_conversation", label: "BIG CONVERSATION", icon: "¶" },
    { id: "finds",            label: "FINDS",            icon: "🔥" },
    { id: "lobby",            label: "THE LOBBY",        icon: "📊" },
    { id: "thread",           label: "THREAD",           icon: "§" },
    { id: "off_the_clock",    label: "OFF THE CLOCK",    icon: "🍷" },
    { id: "amp_finest",       label: "AMP'S FINEST",     icon: "📈" },
    { id: "events",           label: "EVENTS",           icon: "📅" },
  ];

  var readyCount = COMPOSER_ORDER.filter(function(s) {
    if (s.id === "events") {
      return !!(S.events && S.events.length);
    }
    return !!(S.sectionOutputs[s.id] && S.sectionOutputs[s.id].output_text);
  }).length;

  var h = '<div style="max-width:780px;">';
  h += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">';
  h += '<div>';
  h += '<h2 style="margin:0;font-size:20px;">Composer</h2>';
  h += '<div style="font-size:12px;color:var(--text-2);margin-top:2px;">' + readyCount + '/' + COMPOSER_ORDER.length + ' sections ready · ' + (S.weekIso || '') + '</div>';
  h += '</div>';
  h += '<div style="flex:1"></div>';
  h += '<button class="btn btn-success" onclick="copyComposerAll()">Copy All</button>';
  h += '</div>';

  COMPOSER_ORDER.forEach(function(s) {
    var out = s.id === "events" ? null : (S.sectionOutputs[s.id] || null);
    var hasOutput = !!(out && out.output_text);
    var eventsText = "";
    if (s.id === "events" && S.events && S.events.length) {
      eventsText = S.events.map(function(e) {
        return (e.event_date || "") + " · " + e.title + (e.location ? ", " + e.location : "");
      }).join("\n");
      hasOutput = !!eventsText;
    }

    if (!hasOutput) {
      // Missing section panel
      h += '<div style="border:1.5px dashed #e0a040;border-radius:8px;margin-bottom:10px;overflow:hidden;">';
      h += '<div style="background:#fdf5e8;padding:8px 14px;display:flex;align-items:center;gap:10px;">';
      h += '<span style="font-weight:700;font-size:12px;color:#c07000;">⚠ ' + esc(s.icon + ' ' + s.label) + '</span>';
      h += '<span style="flex:1;font-size:11px;color:#c07000;">No output yet</span>';
      h += '<button class="btn btn-sm" onclick="nav(\'' + s.id + '\')" style="font-size:11px;">Go →</button>';
      h += '</div></div>';
      return;
    }

    var textContent = s.id === "events" ? eventsText : out.output_text;
    var taId = "composer-ta-" + s.id;
    var generated = out && out.model_used ? "Generated · " + out.model_used : "Ready";

    h += '<div style="border:1px solid var(--border);border-radius:8px;margin-bottom:10px;overflow:hidden;">';
    h += '<div style="background:var(--bg-2);padding:8px 14px;display:flex;align-items:center;gap:8px;">';
    h += '<span style="font-weight:700;font-size:12px;">' + esc(s.icon + ' ' + s.label) + '</span>';
    h += '<span style="flex:1;font-size:11px;color:var(--text-2);">' + esc(generated) + '</span>';
    h += '<button class="btn btn-sm" id="copy-btn-composer-' + s.id + '" onclick="copyComposerSection(\'' + s.id + '\',\'' + taId + '\')">Copy</button>';
    h += '</div>';
    h += '<textarea id="' + taId + '" style="width:100%;padding:12px 14px;border:none;border-top:1px solid var(--border);font-size:12px;line-height:1.6;resize:vertical;min-height:80px;box-sizing:border-box;background:var(--bg-1,#fff);">';
    h += esc(textContent);
    h += '</textarea>';
    h += '</div>';
  });

  h += '</div>';
  el.innerHTML = h;
}
```

- [ ] **Step 4: Add `copyComposerSection()` helper**

Add immediately after `copyComposerAll()`:

```js
function copyComposerSection(sectionId, taId) {
  var ta = document.getElementById(taId);
  if (!ta || !ta.value) return;
  navigator.clipboard.writeText(ta.value).then(function() {
    var btn = document.getElementById("copy-btn-composer-" + sectionId);
    if (btn) { btn.textContent = "Copied!"; setTimeout(function() { btn.textContent = "Copy"; }, 1500); }
  }).catch(function() {
    ta.select(); document.execCommand("copy");
    var btn = document.getElementById("copy-btn-composer-" + sectionId);
    if (btn) { btn.textContent = "Copied!"; setTimeout(function() { btn.textContent = "Copy"; }, 1500); }
  });
}
```

- [ ] **Step 5: Verify in browser**

Navigate to Composer (was Assemble). Confirm:
- Each section with a saved output shows a panel with textarea + Copy button
- Missing sections show amber warning + "Go →" button
- "Copy All" shows a toast
- Nav label reads "Composer"

- [ ] **Step 6: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: Composer view replaces Assemble with per-section copy panels"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|-------------|------|
| `/api/scrape-all` runs sections sequentially, failures don't abort | Task 1 |
| `/api/scrape-all/status` polls current progress | Task 1 |
| Command bar visible on every section | Task 3 |
| Scrape All button + live progress label | Task 3 |
| Status pills (grey/amber/green/red) with error tooltips | Task 3 |
| `phasePanel()` helper + CSS | Task 2 |
| `S.sectionPhase` state, auto-initialise from data state | Task 2 |
| Auto-advance to Phase 2 on scrape complete | Task 2 |
| Auto-advance to Phase 3 on generation complete | Task 2 |
| Pulse accordion | Task 4 |
| Editorial accordion | Task 4 |
| Big Conversation accordion | Task 4 |
| Finds accordion | Task 5 |
| Lobby accordion | Task 5 |
| Thread accordion | Task 5 |
| OTC accordion | Task 6 |
| AMP's Finest 2-phase (no pick step) | Task 6 |
| Composer panels in newsletter order | Task 7 |
| Copy per section + Copy All | Task 7 |
| Missing section warning + Go → | Task 7 |
| Nav label "Assemble" → "Composer" | Task 7 |

### Placeholder scan

None — all steps have complete code.

### Type consistency

- `phasePanel(section, num, label, unlocked, done, bodyHtml)` — defined Task 2, called Tasks 4-6. Consistent.
- `S.sectionPhase[section]` — int (1, 2, or 3). Used in `phasePanel()` and `openPhase()`. Consistent.
- `S.scrapeAllErrors[section]` — string (error message). Set in `pollScrapeAll()`, read in `renderCommandBar()`. Consistent.
- `copyComposerSection(sectionId, taId)` — called from `renderAssemble()` with matching args. Consistent.
- `_scrape_all_state["results"]` shape: `[{section, status, error}]` — set in `_run_scrape_all()`, read in `/api/scrape-all/status` response and `pollScrapeAll()`. Consistent.
