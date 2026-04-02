# Signal UX, PROCEED Fixes & OTC Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the PROCEED crash that blocks all sections, correct signal delta colours, add signal table sorting and row-click selection, clarify pulse direction semantics, and redesign OTC selection as pill panels with none-selected default.

**Architecture:** The PROCEED crash is a missing DB layer — two functions (`save_section_output`, `load_all_section_outputs`) and a `section_outputs` table are referenced in `api.py` but never implemented in `db.py`. Once that is fixed and duplicate API routes removed, all remaining changes are frontend-only edits to `index.html`.

**Tech Stack:** Python/FastAPI, SQLite via `flatwhite/db.py`, Vanilla JS SPA (`flatwhite/dashboard/static/index.html`)

---

## File Map

| File | Changes |
|------|---------|
| `flatwhite/db.py` | Add `section_outputs` table in `migrate_db()`, add `save_section_output()`, add `load_all_section_outputs()` |
| `flatwhite/dashboard/api.py` | Remove 3 duplicate old routes (lines 890–944) that shadow correct new implementations |
| `flatwhite/dashboard/static/index.html` | Signal delta colours, pulse subtitle, signal sorting, row click-to-select, pulse none-selected, OTC pills redesign |
| `tests/test_section_outputs.py` | New test file for DB functions |

---

## Task 1: DB — section_outputs table and functions

**Files:**
- Modify: `flatwhite/db.py:324-338` (add table in `migrate_db()`)
- Modify: `flatwhite/db.py` (add two new functions after `migrate_db`)
- Create: `tests/test_section_outputs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_section_outputs.py
"""Tests for section_outputs DB functions."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def so_db(tmp_path: Path):
    db_path = tmp_path / "so_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def test_section_outputs_table_exists(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        conn = db_module.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "section_outputs" in tables


def test_save_and_load_section_output(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        db_module.save_section_output("2026-W13", "pulse", "Some pulse text", "claude-sonnet-4-6")
        outputs = db_module.load_all_section_outputs("2026-W13")
        assert "pulse" in outputs
        assert outputs["pulse"]["output_text"] == "Some pulse text"
        assert outputs["pulse"]["model_used"] == "claude-sonnet-4-6"


def test_save_replaces_existing_output(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        db_module.save_section_output("2026-W13", "pulse", "Old text", None)
        db_module.save_section_output("2026-W13", "pulse", "New text", "claude-haiku-4-5")
        outputs = db_module.load_all_section_outputs("2026-W13")
        assert outputs["pulse"]["output_text"] == "New text"
        assert len([k for k in outputs if k == "pulse"]) == 1


def test_load_returns_only_matching_week(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        db_module.save_section_output("2026-W13", "pulse", "W13 text", None)
        db_module.save_section_output("2026-W12", "pulse", "W12 text", None)
        outputs = db_module.load_all_section_outputs("2026-W13")
        assert outputs["pulse"]["output_text"] == "W13 text"
        w12 = db_module.load_all_section_outputs("2026-W12")
        assert w12["pulse"]["output_text"] == "W12 text"


def test_load_returns_empty_dict_for_unknown_week(so_db):
    with patch.object(db_module, "DB_PATH", so_db):
        outputs = db_module.load_all_section_outputs("2026-W99")
        assert outputs == {}
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_section_outputs.py -v 2>&1 | tail -15
```
Expected: all 5 FAIL with `ImportError: cannot import name 'save_section_output'`

- [ ] **Step 3: Add section_outputs table to migrate_db()**

In `flatwhite/db.py`, find the `# v3 signal_intelligence table` block (line ~324). Add immediately after the `signal_intelligence` table creation (before `conn.commit()`):

```python
    # v4 section_outputs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS section_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_iso TEXT NOT NULL,
            section TEXT NOT NULL,
            output_text TEXT NOT NULL,
            model_used TEXT,
            saved_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(week_iso, section)
        )
    """)
```

- [ ] **Step 4: Add save_section_output() and load_all_section_outputs() to db.py**

Add these two functions after `migrate_db()` (after line ~339, before `init_db`):

```python
def save_section_output(
    week_iso: str,
    section: str,
    output_text: str,
    model_used: str | None = None,
) -> None:
    """Persist a generated section output. Replaces existing for the same week/section."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO section_outputs (week_iso, section, output_text, model_used, saved_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        (week_iso, section, output_text, model_used),
    )
    conn.commit()
    conn.close()


def load_all_section_outputs(week_iso: str) -> dict[str, dict]:
    """Return all saved section outputs for a given week, keyed by section name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT section, output_text, model_used, saved_at FROM section_outputs WHERE week_iso = ?",
        (week_iso,),
    ).fetchall()
    conn.close()
    return {
        r["section"]: {
            "output_text": r["output_text"],
            "model_used": r["model_used"],
            "saved_at": r["saved_at"],
        }
        for r in rows
    }
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python -m pytest tests/test_section_outputs.py -v 2>&1 | tail -15
```
Expected: all 5 PASS

- [ ] **Step 6: Commit**

```bash
git add flatwhite/db.py tests/test_section_outputs.py
git commit -m "feat: add section_outputs table and save/load functions to db"
```

---

## Task 2: Remove duplicate API routes (fix PROCEED crash)

**Files:**
- Modify: `flatwhite/dashboard/api.py:890-944`

The old `api_section_outputs` (line 890), `api_save_section_output` (line 900), and `api_proceed_section` (line 909) all try to import `save_section_output` or `load_all_section_outputs` from `db.py`. Before Task 1 these didn't exist — causing every PROCEED call to crash with an `ImportError` that FastAPI returns as a plain-text 500. Even now that Task 1 has added the functions, these old handlers are still first-match and must be removed so the correct new implementations at lines 1667 and 2005 are used instead.

- [ ] **Step 1: Read lines 881–945 of api.py to confirm exact content**

Open `flatwhite/dashboard/api.py`. Confirm lines 881–945 look like:

```python
# ── New endpoints ─────────
@app.get("/api/models")          # line 883 — KEEP THIS
...
@app.get("/api/section-outputs") # line 890 — DELETE through line 944
...
@app.post("/api/proceed-section")  # line 909 (old, broken)
...                                 # ends around line 944
```

- [ ] **Step 2: Delete the three old route handlers**

Delete exactly these three route handlers from `api.py` (lines 890–944):
- `@app.get("/api/section-outputs")` at line 890 through line 896
- `@app.post("/api/section-output/{section}")` at line 899 through line 906
- `@app.post("/api/proceed-section")` at line 909 through line 944

Keep `@app.get("/api/models")` at line 883 — it is NOT a duplicate.

Also delete the dead code old `_proceed_*` functions that take only 2 args (they're above the `# ── New endpoints` comment around lines 763–878). Check if any function in that range is NOT defined again later; if it is redefined at line 1775+, delete the old version.

To be safe: search for all function definitions between lines 763–878 and verify each one is redefined at lines 1775–2001 before deleting.

```bash
grep -n "^def _proceed_" flatwhite/dashboard/api.py
```

Expected output (each function should appear twice — old at <900 and new at >1775):
```
763:def _proceed_editorial(...)   # OLD — delete
...
1835:def _proceed_big_conversation(...)  # NEW — keep
```

Delete all `_proceed_*` function definitions in lines 763–878. Keep all `_proceed_*` definitions at lines 1775+.

- [ ] **Step 3: Verify PROCEED now returns JSON**

Restart the server (kill and re-run):
```bash
pkill -f "uvicorn flatwhite" 2>/dev/null; sleep 1
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500 &
sleep 2
curl -s -X POST http://localhost:8500/api/proceed-section \
  -H "Content-Type: application/json" \
  -d '{"section":"pulse","model":null,"data":{},"custom_prompt":"test","excluded":[]}' | python3 -m json.tool
```

Expected: JSON response `{"section": "pulse", "output": "...", ...}` — NOT "Internal Server Error"

- [ ] **Step 4: Verify section-outputs returns JSON**

```bash
curl -s http://localhost:8500/api/section-outputs | python3 -m json.tool
```
Expected: `{"outputs": {}, "week_iso": "..."}` (may be empty if no outputs saved yet)

- [ ] **Step 5: Run existing tests to check nothing regressed**

```bash
python -m pytest tests/test_section_outputs.py tests/test_signal_intelligence.py tests/test_backfill_api.py -v 2>&1 | tail -20
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "fix: remove duplicate API routes that caused PROCEED ImportError crash"
```

---

## Task 3: Signal delta colours + si.delta null fix

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Background:** The current delta colour logic (`positive=red, negative=green`) is backwards for readers. The backend already inverts adverse signals during normalisation — so a positive delta in `normalised_score` always means conditions *improved* for AusCorp readers, with one exception: `asx_volatility` where a higher score = more market stress = bad.

The signal intelligence drawer also calls `si.delta.toFixed(1)` without checking if `si.delta` is null, which crashes the drawer.

- [ ] **Step 1: Add SIGNAL_INVERTED_DISPLAY constant after the `var OTC_CATS` declaration**

Find the `var OTC_CATS` array in index.html (around line 240). Immediately after it, add:

```js
// Signals where a positive WoW delta = BAD news for readers (higher score = more disruption).
// All other signals: positive delta = good news (higher score = better conditions).
var SIGNAL_INVERTED_DISPLAY = new Set(["asx_volatility"]);
```

- [ ] **Step 2: Replace the delta colour logic in the signal table (renderPulse)**

Find this line in `renderPulse` (around line 629):
```js
        var dc = dv > 0 ? 'color:var(--red)' : (dv < 0 ? 'color:var(--green)' : 'color:var(--text-3)');
```

Replace with:
```js
        var dc = !hasDelta ? 'color:var(--text-3)' : (SIGNAL_INVERTED_DISPLAY.has(name)
          ? (dv > 0 ? 'color:var(--red)' : 'color:var(--green)')
          : (dv > 0 ? 'color:var(--green)' : 'color:var(--red)'));
```

- [ ] **Step 3: Fix si.delta null crash in evidence drawer (renderPulse)**

Find this line in the signal intelligence evidence drawer (around line 644):
```js
          h += '<div style="font-size:13px;line-height:1.6;color:var(--text-1);margin-bottom:10px;">' + esc(intel.commentary) + '</div>';
```

The drawer renders the commentary fine, but the PROCEED modal's Context tab also renders signal intelligence. Find this line in `renderProceedModal` (around line 1606):
```js
          h += '<div style="font-weight:600;font-size:12px;">' + esc(si.signal_name) + ' (' + (si.delta > 0 ? "+" : "") + si.delta.toFixed(1) + ' pts)</div>';
```

Replace with:
```js
          h += '<div style="font-weight:600;font-size:12px;">' + esc(si.signal_name) + (si.delta != null ? ' (' + (si.delta > 0 ? "+" : "") + si.delta.toFixed(1) + ' pts)' : '') + '</div>';
```

- [ ] **Step 4: Verify in browser**

Open http://localhost:8500, navigate to Pulse. Check:
- Consumer confidence: if it fell week-over-week, delta should now be RED (not green)
- Hiring breadth: if negative, delta should be RED
- ASX volatility: if positive, delta should be RED; if negative, GREEN
- Other signals: positive delta = GREEN, negative delta = RED

Open the PROCEED modal on any section (if evidence data exists), click Context tab — confirm no crash if `delta` is null.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "fix: correct signal delta colours (positive=good for all except asx_volatility) and null-guard si.delta"
```

---

## Task 4: Pulse card — "Lower is healthier" subtitle

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

The disruption score card needs a one-liner explaining the scale, so readers always know which direction is good. The `gauge-num` also has `margin-top: -12px` which pulls it up into the label — fix that overlap.

- [ ] **Step 1: Fix gauge-num margin**

Find in the CSS section (line ~113):
```css
.gauge-num { font-family: var(--font-sans); font-size: 60px; font-weight: 700; letter-spacing: -3px; margin-top: -12px; line-height: 1; }
```

Replace with:
```css
.gauge-num { font-family: var(--font-sans); font-size: 60px; font-weight: 700; letter-spacing: -3px; margin-top: 4px; line-height: 1; }
```

- [ ] **Step 2: Add "Lower is healthier" subtitle below the direction pill**

Find in `renderPulse` (around line 592):
```js
    h += '<div style="margin-top:10px;"><span class="dir-pill ' + dirClass + '">' + arrow + ' ' + esc(dir) + (delta ? ' (' + (delta > 0 ? "+" : "") + delta.toFixed(1) + ')' : '') + '</span></div>';
    h += '</div>';
```

Replace with:
```js
    h += '<div style="margin-top:10px;"><span class="dir-pill ' + dirClass + '">' + arrow + ' ' + esc(dir) + (delta ? ' (' + (delta > 0 ? "+" : "") + delta.toFixed(1) + ')' : '') + '</span></div>';
    h += '<div style="margin-top:8px;font-size:11px;color:var(--text-3);">Lower score = healthier market</div>';
    h += '</div>';
```

- [ ] **Step 3: Verify in browser**

Open http://localhost:8500 → Pulse. The disruption score card should show:
- `DISRUPTION SCORE` label
- Large score number (not clipped into the label above it)
- Direction pill (↑ red if rising, ↓ green if falling)
- "Lower score = healthier market" subtitle in small grey text

- [ ] **Step 4: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "fix: pulse card gauge spacing and add 'lower is healthier' subtitle"
```

---

## Task 5: Signal table — sorting

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add signalSort to S state**

Find the S state block (around line 272). After `pulseChecked: {},` add:
```js
  signalSort: { col: null, dir: "desc" },  // { col: "name"|"score"|"delta"|"area"|"evidence", dir: "asc"|"desc" }
```

- [ ] **Step 2: Add sortSignals() and getSortedSignals() helper functions**

Add these two functions immediately before `function renderPulse(el)` (around line 561):

```js
function sortSignals(col) {
  if (S.signalSort.col === col) {
    S.signalSort.dir = S.signalSort.dir === "desc" ? "asc" : "desc";
  } else {
    S.signalSort.col = col;
    S.signalSort.dir = "desc";
  }
  render();
}

function getSortedSignals(signals, moverDeltas) {
  var sort = S.signalSort;
  if (!sort.col) return signals.slice();
  return signals.slice().sort(function(a, b) {
    var na = a.signal_name || a.name || "";
    var nb = b.signal_name || b.name || "";
    var val = 0;
    if (sort.col === "name") {
      val = na.localeCompare(nb);
    } else if (sort.col === "score") {
      val = (a.normalised_score || 0) - (b.normalised_score || 0);
    } else if (sort.col === "delta") {
      val = Math.abs(moverDeltas[na] || 0) - Math.abs(moverDeltas[nb] || 0);
    } else if (sort.col === "area") {
      val = (a.area || "").localeCompare(b.area || "");
    } else if (sort.col === "evidence") {
      val = (S.signalIntelligence[na] ? 1 : 0) - (S.signalIntelligence[nb] ? 1 : 0);
    }
    return sort.dir === "desc" ? -val : val;
  });
}
```

- [ ] **Step 3: Replace static table header with sortable headers**

In `renderPulse`, find:
```js
      h += '<table class="tbl"><thead><tr><th style="width:30px;"></th><th>Signal</th><th>Score</th><th>Delta</th><th>Category</th><th style="width:60px;">Evidence</th></tr></thead><tbody>';
```

Replace with:
```js
      function thSort(col, label, width) {
        var active = S.signalSort.col === col;
        var arrow = active ? (S.signalSort.dir === "desc" ? " ▼" : " ▲") : "";
        var style = 'cursor:pointer;user-select:none;' + (width ? 'width:' + width + ';' : '');
        return '<th onclick="sortSignals(\'' + col + '\')" style="' + style + '">' + label + arrow + '</th>';
      }
      h += '<table class="tbl"><thead><tr>';
      h += '<th style="width:30px;"></th>';
      h += thSort("name", "Signal");
      h += thSort("score", "Score");
      h += thSort("delta", "Delta");
      h += thSort("area", "Category");
      h += thSort("evidence", "Evidence", "60px");
      h += '</tr></thead><tbody>';
```

- [ ] **Step 4: Apply sorting before the forEach loop**

Find in `renderPulse` (around line 624):
```js
      S.signals.forEach(function(sig) {
```

Replace with:
```js
      getSortedSignals(S.signals, moverDeltas).forEach(function(sig) {
```

- [ ] **Step 5: Verify in browser**

Open Pulse. Click "Signal" column header → rows sort A–Z. Click again → Z–A. Click "Delta" → largest absolute movers first. Click "Evidence" → signals with intel badges sort to top.

- [ ] **Step 6: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: sortable signal table columns (name, score, delta, category, evidence)"
```

---

## Task 6: Signal row click-to-select + pulse none-selected default

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Remove pulse auto-select-all on first load**

Find in `renderPulse` (around line 609):
```js
      // Pre-check top 3 movers on first load
      if (!S._pulseInitChecked && S.signals.length) {
        S._pulseInitChecked = true;
        S.signals.forEach(function(sig) { S.pulseChecked[sig.signal_name || sig.name] = true; });
      }
```

Delete those 4 lines entirely. `S.pulseChecked` starts as `{}` — nothing pre-selected.

- [ ] **Step 2: Add row onclick and stop-propagation on evidence cell**

Find the signal row rendering (around line 630):
```js
        h += '<tr>';
        h += '<td><input type="checkbox"' + checked + ' onchange="togglePulseCheck(\'' + esc(name) + '\',this.checked)"></td>';
        h += '<td>' + esc(name) + '</td>';
        h += '<td>' + esc(sig.normalised_score != null ? sig.normalised_score.toFixed(1) : "—") + '</td>';
        h += '<td style="font-weight:600;' + dc + '">' + (hasDelta ? ((dv > 0 ? "+" : "") + dv.toFixed(1)) : "—") + '</td>';
        h += '<td><span class="chip chip-default">' + esc(sig.area || "") + '</span></td>';
        var intel = S.signalIntelligence[name];
        var evidenceBadge = intel
          ? '<span class="chip chip-default" style="cursor:pointer;font-size:10px;" onclick="toggleSignalIntel(\'' + esc(name) + '\')" title="' + esc((intel.commentary || "").slice(0, 80)) + '...">&#8801; evidence</span>'
          : '';
        h += '<td>' + evidenceBadge + '</td>';
        h += '</tr>';
```

Replace with:
```js
        h += '<tr style="cursor:pointer;" onclick="togglePulseCheck(\'' + esc(name) + '\',!S.pulseChecked[\'' + esc(name) + '\']);render()">';
        h += '<td onclick="event.stopPropagation()"><input type="checkbox"' + checked + ' onchange="togglePulseCheck(\'' + esc(name) + '\',this.checked)"></td>';
        h += '<td>' + esc(name) + '</td>';
        h += '<td>' + esc(sig.normalised_score != null ? sig.normalised_score.toFixed(1) : "—") + '</td>';
        h += '<td style="font-weight:600;' + dc + '">' + (hasDelta ? ((dv > 0 ? "+" : "") + dv.toFixed(1)) : "—") + '</td>';
        h += '<td><span class="chip chip-default">' + esc(sig.area || "") + '</span></td>';
        var intel = S.signalIntelligence[name];
        var evidenceBadge = intel
          ? '<span class="chip chip-default" style="cursor:pointer;font-size:10px;" onclick="toggleSignalIntel(\'' + esc(name) + '\')" title="' + esc((intel.commentary || "").slice(0, 80)) + '...">&#8801; evidence</span>'
          : '';
        h += '<td onclick="event.stopPropagation()">' + evidenceBadge + '</td>';
        h += '</tr>';
```

- [ ] **Step 3: Add tr-hover CSS**

Find the `.tbl tbody tr` CSS (search for `tbody tr` in the `<style>` block). If no hover rule exists, add after the `.tbl` block:

```css
.tbl tbody tr:hover { background: var(--bg-2); }
```

- [ ] **Step 4: Verify in browser**

Open Pulse → signal table. On page load: all checkboxes unchecked. Click anywhere on a signal row (not the evidence badge) → checkbox toggles. Click again → unchecks. Clicking the evidence badge opens/closes the drawer without toggling the checkbox.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: signal row click-to-select; pulse signals none-selected by default"
```

---

## Task 7: OTC selection — pill panels redesign

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

Replace the confusing checkbox + radio "Pick this one" UX with per-category pill panels. Each pill = one candidate. Click to select as the category pick (amber highlight). Click again to deselect. None selected by default. Blurb textarea appears below pills when a pick is active.

- [ ] **Step 1: Update pickOTC() to toggle**

Find:
```js
function pickOTC(cat, id) {
  S.otcPicks[cat] = id;
  render();
}
```

Replace with:
```js
function pickOTC(cat, id) {
  if (S.otcPicks[cat] === id) {
    delete S.otcPicks[cat];
  } else {
    S.otcPicks[cat] = id;
  }
  render();
}
```

- [ ] **Step 2: Remove toggleOtcSelect() function (no longer needed)**

Find and delete:
```js
function toggleOtcSelect(cat, id, val) {
  if (!S.otcSelected[cat]) S.otcSelected[cat] = {};
  S.otcSelected[cat][id] = val;
  if (!val && S.otcPicks[cat] === id) {
    delete S.otcPicks[cat];
  }
  render();
}
```

- [ ] **Step 3: Remove otcSelected from S state**

Find in the S state block:
```js
  otcSelected: {},
```
Delete that line.

- [ ] **Step 4: Replace the OTC candidates rendering in renderOTC()**

Find the entire `} else {` block inside the `OTC_CATS.forEach` that currently renders checkboxes + radio:

```js
      } else {
        // Initialise all selected on first render
        if (!S.otcSelected[cat.key]) {
          S.otcSelected[cat.key] = {};
          candidates.forEach(function(c) { S.otcSelected[cat.key][c.id] = true; });
        }
        candidates.forEach(function(c) {
          var checked = S.otcSelected[cat.key][c.id] ? " checked" : "";
          var city = c.city ? '<span class="chip chip-default" style="font-size:10px;">' + esc(c.city) + '</span> ' : "";
          var src = '<span style="font-size:11px;color:var(--text-3);">' + esc(c.source || "") + '</span>';
          h += '<div class="fr mb8" style="align-items:flex-start;gap:8px;">';
          h += '<input type="checkbox"' + checked + ' onchange="toggleOtcSelect(\'' + cat.key + '\',' + c.id + ',this.checked)" style="margin-top:2px;flex-shrink:0;">';
          h += '<div style="flex:1;">';
          h += '<div style="font-size:13px;">' + esc(c.title || c.summary) + '</div>';
          h += '<div style="margin-top:2px;">' + city + src + '</div>';
          h += '</div></div>';
          // Radio pick (existing behaviour — kept for final pick selection)
          var sel = S.otcPicks[cat.key] === c.id;
          if (S.otcSelected[cat.key][c.id]) {
            h += '<div style="margin-left:26px;margin-bottom:6px;">';
            h += '<label style="font-size:11px;cursor:pointer;">';
            h += '<input type="radio" name="otc-pick-' + cat.key + '" ' + (sel ? "checked" : "") + ' onchange="pickOTC(\'' + cat.key + '\',' + c.id + ')">';
            h += ' Pick this one';
            h += '</label>';
            if (sel) {
              h += '<textarea class="form-input" id="otc-blurb-' + c.id + '" rows="2" placeholder="Blurb..." style="margin-top:4px;" onchange="updateOTCBlurb(\'' + cat.key + '\',this.value)">' + esc(S.otcBlurbs[cat.key] || "") + '</textarea>';
            }
            h += '</div>';
          }
        });
      }
```

Replace with:

```js
      } else {
        // Pill row — one pill per candidate, click to pick (radio behaviour)
        var selectedId = S.otcPicks[cat.key];
        h += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">';
        candidates.forEach(function(c) {
          var active = selectedId === c.id;
          var pillStyle = active
            ? 'background:rgba(255,180,0,0.12);border:1.5px solid var(--amber);color:var(--text-1);font-weight:600;'
            : 'background:var(--bg-2);border:1.5px solid var(--divider);color:var(--text-2);';
          var label = (c.title || c.summary || "").slice(0, 44) + ((c.title || c.summary || "").length > 44 ? "…" : "");
          h += '<button onclick="pickOTC(\'' + cat.key + '\',' + c.id + ')" ';
          h += 'title="' + esc(c.title || c.summary || "") + '" ';
          h += 'style="' + pillStyle + 'padding:6px 12px;border-radius:20px;cursor:pointer;font-size:12px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">';
          h += esc(label);
          if (c.city) h += ' <span style="font-size:10px;opacity:0.65;">(' + esc(c.city) + ')</span>';
          h += '</button>';
        });
        h += '</div>';
        // Blurb textarea below pills — only when a pick is active
        if (selectedId != null) {
          h += '<textarea class="form-input" rows="2" placeholder="Optional blurb for this pick..." style="margin-top:4px;" oninput="updateOTCBlurb(\'' + cat.key + '\',this.value)">' + esc(S.otcBlurbs[cat.key] || "") + '</textarea>';
        }
      }
```

- [ ] **Step 5: Update proceedOTC() to not reference otcSelected**

Find `proceedOTC()`:
```js
function proceedOTC() {
  var model = getModel("model-otc");
  var picks = [];
  var selectedByCategory = {};
  OTC_CATS.forEach(function(cat) {
    if (S.otcPicks[cat.key]) {
      picks.push({ category: cat.key, curated_item_id: S.otcPicks[cat.key], blurb: S.otcBlurbs[cat.key] || "" });
    }
    // Collect selected item IDs for this category
    var sel = S.otcSelected[cat.key] || {};
    selectedByCategory[cat.key] = Object.keys(sel).filter(function(id) { return sel[id]; }).map(Number);
  });
  S.proceedData.off_the_clock = {
    section: "off_the_clock",
    model: model,
    data: { picks: picks, selected_by_category: selectedByCategory },
  };
```

Replace with:
```js
function proceedOTC() {
  var model = getModel("model-otc");
  var picks = [];
  OTC_CATS.forEach(function(cat) {
    var id = S.otcPicks[cat.key];
    if (id != null) {
      var candidates = (S.otcData && S.otcData.candidates && S.otcData.candidates[cat.key]) || [];
      var item = candidates.find(function(c) { return c.id === id; });
      picks.push({
        category: cat.key,
        curated_item_id: id,
        title: item ? (item.title || item.summary || "") : "",
        blurb: S.otcBlurbs[cat.key] || "",
      });
    }
  });
  S.proceedData.off_the_clock = {
    section: "off_the_clock",
    model: model,
    data: { picks: picks },
  };
```

- [ ] **Step 6: Verify in browser**

Open Off the Clock. With scraped data loaded:
- Each category card shows a horizontal row of pill buttons
- No pre-selected pills on first load
- Clicking a pill highlights it amber and shows blurb textarea below
- Clicking the same pill again deselects it (no pill selected)
- Only one pill can be active per category
- PROCEED sends only categories with an active pick

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: OTC selection redesign — pill panels per category, none selected by default"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|-----------------|------|
| Fix PROCEED crash (`save_section_output` missing) | Tasks 1, 2 |
| `section_outputs` DB table + functions | Task 1 |
| Remove duplicate old API routes | Task 2 |
| Signal delta colour — positive=green (all signals except asx_volatility) | Task 3 |
| si.delta null guard in PROCEED modal | Task 3 |
| Pulse "Lower is healthier" subtitle | Task 4 |
| Gauge-num overlap fix (margin-top -12px → 4px) | Task 4 |
| Signal table column sorting | Task 5 |
| Signal row click-to-select | Task 6 |
| Pulse none-selected by default | Task 6 |
| OTC pill panel redesign | Task 7 |
| OTC none-selected by default | Task 7 |
| OTC pick toggle (deselect on second click) | Task 7 |

### Placeholder scan

None found — all steps contain complete code.

### Type consistency

- `save_section_output(week_iso, section, output_text, model_used)` — used in Task 1 and referenced by existing `api_save_section_output` handler that survives deletion.
- `load_all_section_outputs(week_iso) -> dict[str, dict]` — returns dict with keys `output_text`, `model_used`, `saved_at` matching what `api_section_outputs` returns to the frontend.
- `S.otcSelected` removed from state in Task 7 Step 3; `toggleOtcSelect` removed in Task 7 Step 2; `proceedOTC` updated in Task 7 Step 5 — no dangling references.
- `SIGNAL_INVERTED_DISPLAY` defined before `renderPulse` and used only within `renderPulse` — consistent scope.
