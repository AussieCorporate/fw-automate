# Bug Fixes, Last Scraped Date & OTC Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three crashing bugs (missing DB function, anomaly display, scrape pipeline), show last-scraped timestamps in section toolbars, and redesign OTC selection for multi-pick per category with a live-editable prompt preview.

**Architecture:** Track A bugs are fixed with one new DB function + two migration columns, one API field addition per endpoint, and two frontend line fixes. Track B is a pure frontend redesign of OTC state + render logic. No new API endpoints.

**Tech Stack:** Python/FastAPI, SQLite via `flatwhite/db.py`, Vanilla JS SPA (`flatwhite/dashboard/static/index.html`)

---

## File Map

| File | Changes |
|------|---------|
| `flatwhite/db.py` | Add `post_score`/`comment_engagement` columns in `migrate_db()`, add `update_raw_item_engagement()` |
| `flatwhite/dashboard/api.py` | Add `last_scraped_at` field to 6 load endpoints |
| `flatwhite/dashboard/static/index.html` | Fix anomaly display; add `S.lastScraped`; show date badges; OTC multi-select state + render + prompt |
| `tests/test_engagement_update.py` | New test file for DB function |

---

## Task 1: DB — engagement columns + update_raw_item_engagement

**Files:**
- Modify: `flatwhite/db.py` (lines ~219–230 for migrations, after line 352 for new function)
- Create: `tests/test_engagement_update.py`

**Background:** `flatwhite/editorial/reddit_rss.py` imports `update_raw_item_engagement` from `flatwhite.db` at line 4. The function does not exist. Python raises `ImportError` when `reddit_rss` is imported — which happens during every Big Conversations, Finds, and Threads scrape. The `raw_items` table also has no columns for engagement data yet.

- [ ] **Step 1: Write failing tests**

Create `tests/test_engagement_update.py`:

```python
"""Tests for update_raw_item_engagement DB function."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def eng_db(tmp_path: Path):
    db_path = tmp_path / "eng_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def _insert_item(db_path, title, url, week_iso="2026-W13"):
    with patch.object(db_module, "DB_PATH", db_path):
        conn = db_module.get_connection()
        conn.execute(
            "INSERT INTO raw_items (title, source, url, lane, pulled_at, week_iso) "
            "VALUES (?, 'r/auscorp', ?, 'editorial', datetime('now'), ?)",
            (title, url, week_iso),
        )
        conn.commit()
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return item_id


def test_engagement_columns_exist(eng_db):
    with patch.object(db_module, "DB_PATH", eng_db):
        conn = db_module.get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(raw_items)").fetchall()}
        conn.close()
        assert "post_score" in cols
        assert "comment_engagement" in cols


def test_update_raw_item_engagement(eng_db):
    item_id = _insert_item(eng_db, "Test post", "https://reddit.com/test1")
    with patch.object(db_module, "DB_PATH", eng_db):
        db_module.update_raw_item_engagement(item_id, post_score=42, comment_engagement=155)
        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT post_score, comment_engagement FROM raw_items WHERE id = ?", (item_id,)
        ).fetchone()
        conn.close()
        assert row["post_score"] == 42
        assert row["comment_engagement"] == 155


def test_update_engagement_does_not_affect_other_rows(eng_db):
    id1 = _insert_item(eng_db, "Post 1", "https://reddit.com/p1")
    id2 = _insert_item(eng_db, "Post 2", "https://reddit.com/p2")
    with patch.object(db_module, "DB_PATH", eng_db):
        db_module.update_raw_item_engagement(id1, post_score=10, comment_engagement=20)
        conn = db_module.get_connection()
        row2 = conn.execute(
            "SELECT post_score, comment_engagement FROM raw_items WHERE id = ?", (id2,)
        ).fetchone()
        conn.close()
        assert row2["post_score"] is None
        assert row2["comment_engagement"] is None


def test_update_engagement_with_zero_values(eng_db):
    item_id = _insert_item(eng_db, "Zero post", "https://reddit.com/zero")
    with patch.object(db_module, "DB_PATH", eng_db):
        db_module.update_raw_item_engagement(item_id, post_score=0, comment_engagement=0)
        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT post_score, comment_engagement FROM raw_items WHERE id = ?", (item_id,)
        ).fetchone()
        conn.close()
        assert row["post_score"] == 0
        assert row["comment_engagement"] == 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_engagement_update.py -v 2>&1 | tail -15
```

Expected: 4 FAIL — `AttributeError: module 'flatwhite.db' has no attribute 'update_raw_item_engagement'`

- [ ] **Step 3: Add migration columns to migrate_db()**

In `flatwhite/db.py`, find the list of migration SQL strings in `migrate_db()` (around line 219). After the line:
```python
"ALTER TABLE raw_items ADD COLUMN top_comments TEXT",
```

Add:
```python
"ALTER TABLE raw_items ADD COLUMN post_score INTEGER",
"ALTER TABLE raw_items ADD COLUMN comment_engagement INTEGER",
```

(The migration runs these inside a loop that catches `OperationalError` for already-existing columns — safe to re-run on existing DBs.)

- [ ] **Step 4: Add update_raw_item_engagement() to db.py**

Read `flatwhite/db.py` to find the `update_draft_status` function (around line 606). Add the new function immediately before it, following the same pattern:

```python
def update_raw_item_engagement(
    item_id: int,
    post_score: int,
    comment_engagement: int,
) -> None:
    """Update Reddit engagement metrics for a raw item after fetch."""
    conn = get_connection()
    conn.execute(
        "UPDATE raw_items SET post_score = ?, comment_engagement = ? WHERE id = ?",
        (post_score, comment_engagement, item_id),
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_engagement_update.py -v 2>&1 | tail -10
```

Expected: 4 PASSED

- [ ] **Step 6: Confirm the import now works**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -c "from flatwhite.editorial.reddit_rss import *; print('OK')"
```

Expected: `OK` (no ImportError)

- [ ] **Step 7: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/db.py tests/test_engagement_update.py && git commit -m "fix: add update_raw_item_engagement and engagement columns to raw_items"
```

---

## Task 2: API — add last_scraped_at to load endpoints

**Files:**
- Modify: `flatwhite/dashboard/api.py`

Add a `last_scraped_at` field to each of 6 section load endpoints. For pulse, query `max(pulled_at)` from the `signals` table. For all other sections, query `max(pulled_at)` from `raw_items`.

- [ ] **Step 1: Read the 6 endpoints to see their current return statements**

Read `flatwhite/dashboard/api.py` around these lines:
- `/api/pulse` — line ~129
- `/api/items` — line ~153
- `/api/threads` — line ~174
- `/api/big-conversation-candidates` — line ~815
- `/api/off-the-clock` — line ~244
- `/api/lobby` — line ~1327

Confirm the exact `return JSONResponse({...})` structure for each.

- [ ] **Step 2: Add last_scraped_at to /api/pulse**

In the `api_pulse` handler, before the `return JSONResponse(...)`, add:

```python
    _conn = get_connection()
    _scraped_row = _conn.execute(
        "SELECT max(pulled_at) FROM signals WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _scraped_row[0] if _scraped_row else None
```

Then add `"last_scraped_at": last_scraped_at` to the JSONResponse dict.

Note: `get_connection` and `get_current_week_iso` are already imported at the top of `api.py`. Check that `week_iso` is already a local variable in this handler (it should be from `get_current_week_iso()`).

- [ ] **Step 3: Add last_scraped_at to /api/items (editorial)**

In the `api_items` handler, before `return JSONResponse(...)`, add:

```python
    _conn = get_connection()
    _scraped_row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _scraped_row[0] if _scraped_row else None
```

Add `"last_scraped_at": last_scraped_at` to the response dict.

- [ ] **Step 4: Add last_scraped_at to /api/threads**

Same pattern as Step 3 (raw_items query). Add `"last_scraped_at": last_scraped_at` to the response.

- [ ] **Step 5: Add last_scraped_at to /api/big-conversation-candidates**

Same pattern as Step 3. Add `"last_scraped_at": last_scraped_at` to the response.

- [ ] **Step 6: Add last_scraped_at to /api/off-the-clock**

Same pattern as Step 3. Add `"last_scraped_at": last_scraped_at` to the response.

- [ ] **Step 7: Add last_scraped_at to /api/lobby**

Read the lobby handler. If `week_iso` is available as a local variable, use the same raw_items pattern. If the handler doesn't use `week_iso`, add `week_iso = get_current_week_iso()` before the query. Add `"last_scraped_at": last_scraped_at` to the response.

- [ ] **Step 8: Verify server starts cleanly**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -c "from flatwhite.dashboard.api import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Verify /api/pulse returns last_scraped_at**

```bash
pkill -f "uvicorn flatwhite" 2>/dev/null; sleep 1
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500 &
sleep 2
curl -s http://localhost:8500/api/pulse | python3 -m json.tool | grep last_scraped
```

Expected: `"last_scraped_at": "2026-03-28 ..."` or `"last_scraped_at": null` (null is fine if no signals scraped yet)

- [ ] **Step 10: Commit**

```bash
pkill -f "uvicorn flatwhite" 2>/dev/null
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/api.py && git commit -m "feat: add last_scraped_at to section load endpoints"
```

---

## Task 3: Frontend — anomaly fix + last_scraped_at display

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

Two changes: fix the `[object Object]` anomaly display, and show a `"Scraped DD Mon"` badge in each section's toolbar.

- [ ] **Step 1: Fix the anomaly display**

Find line ~635 in `index.html`:
```js
h += '<div class="anomaly"><span style="font-size:18px;">⚠</span><span>' + esc(a.message || a) + '</span></div>';
```

Replace with:
```js
h += '<div class="anomaly"><span style="font-size:18px;">⚠</span><span>' + esc(a.signal + ': score ' + (a.current != null ? a.current : '—') + ' (' + (a.direction || '') + ', ' + (a.confidence || '') + ' confidence)') + '</span></div>';
```

- [ ] **Step 2: Add lastScraped to S state**

Find the `var S = {` block (around line 249). After `otcBlurbs: {},` add:
```js
  lastScraped: {},
```

- [ ] **Step 3: Add a formatScrapedDate helper function**

Find a good place near the top of the script (near other utility functions like `esc()`). Add:

```js
function formatScrapedDate(isoStr) {
  if (!isoStr) return null;
  var d = new Date(isoStr.replace(" ", "T") + "Z");
  var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return d.getDate() + " " + months[d.getMonth()];
}
```

- [ ] **Step 4: Populate S.lastScraped from each section's load response**

Search `index.html` for where each section's API response is stored into S state. Look for patterns like `S.signals = d.signals` or `S.pulse = d.pulse`. For each one found, add `S.lastScraped['section'] = d.last_scraped_at || null` immediately after.

Sections and their state keys to search for:
- pulse: search `S.signals = ` or `S.pulse = ` — add `S.lastScraped.pulse = d.last_scraped_at || null`
- editorial/items: search `S.items = ` — add `S.lastScraped.editorial = d.last_scraped_at || null`
- threads: search `S.threads = ` — add `S.lastScraped.threads = d.last_scraped_at || null`
- big conversation: search `S.bigConvCandidates = ` — add `S.lastScraped.big_conversation = d.last_scraped_at || null`
- off the clock: search `S.otcData = ` — add `S.lastScraped.off_the_clock = d.last_scraped_at || null`
- lobby: search `S.lobby = ` — add `S.lastScraped.lobby = d.last_scraped_at || null`

- [ ] **Step 5: Add scraped date badge to each section's toolbar**

Add a helper snippet inside each section's `render*` function, immediately after the PROCEED button and before the closing `h += '</div>';` of the toolbar div.

For **renderPulse** (find `onclick="proceedPulse()"` in the toolbar):
```js
var _pulseScraped = formatScrapedDate(S.lastScraped.pulse);
if (_pulseScraped) h += '<span style="font-size:11px;color:var(--text-3);margin-left:8px;">Scraped ' + _pulseScraped + '</span>';
```

Repeat for each section's render function, using the appropriate `S.lastScraped` key:
- `renderEditorial` → `S.lastScraped.editorial`
- `renderThreads` → `S.lastScraped.threads`
- `renderBigConversation` → `S.lastScraped.big_conversation`
- `renderOTC` → `S.lastScraped.off_the_clock`
- `renderLobby` → `S.lastScraped.lobby`

(Search for each render function by name. The toolbar div always ends with `h += '</div>';` just before `if (S.loading.*)`. Insert the badge before the closing `</div>`.)

- [ ] **Step 6: Verify anomaly fix**

```bash
grep -n "a.signal.*confidence" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html
```
Expected: 1 hit on the updated anomaly line.

- [ ] **Step 7: Verify lastScraped in state**

```bash
grep -n "lastScraped" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html | head -15
```
Expected: hits for state init, each section's load handler assignment, and each render function's badge.

- [ ] **Step 8: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "fix: anomaly display and add last-scraped date badges to section toolbars"
```

---

## Task 4: OTC multi-select + prompt preview

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

Replace single-pick OTC behaviour with multi-pick per category. Each picked item gets its own blurb textarea. A collapsible prompt preview textarea shows the full LLM prompt, updating live as picks/blurbs change.

**State change summary:**
- `S.otcPicks[cat]` — was: single id or `undefined`. Now: `{}` dict of `{ [id]: true }` for each selected item in that category.
- `S.otcBlurbs` — was: `{ [cat]: text }`. Now: `{ ["cat__id"]: text }` — one blurb per selected item.
- `S.otcPrompt` (new) — the editable prompt string, rebuilt on every pick/blurb change.
- `S.otcPromptExpanded` (new) — boolean, whether the prompt panel is open.

- [ ] **Step 1: Add otcPrompt and otcPromptExpanded to S state**

Find the S state block (around line 249). After `otcBlurbs: {},` add:
```js
  otcPrompt: "",
  otcPromptExpanded: false,
```

- [ ] **Step 2: Add buildOTCPrompt() function**

Add this function immediately before `function pickOTC` (around line 1246):

```js
function buildOTCPrompt() {
  var lines = [];
  OTC_CATS.forEach(function(cat) {
    var catPicks = S.otcPicks[cat.key] || {};
    Object.keys(catPicks).forEach(function(id) {
      var candidates = (S.otcData && S.otcData.candidates && S.otcData.candidates[cat.key]) || [];
      var item = candidates.find(function(c) { return c.id === Number(id); });
      if (!item) return;
      var blurb = S.otcBlurbs[cat.key + "__" + id] || "";
      lines.push("Category: " + cat.key + "\nTitle: " + (item.title || item.summary || "") + "\nDraft blurb: " + blurb);
    });
  });
  if (!lines.length) return "";
  return (
    "Polish these Off the Clock blurbs for Flat White.\n\n" +
    lines.join("\n\n") +
    "\n\nFor each, rewrite the blurb in 1-2 sentences. Voice: dry, specific, opinionated. " +
    "Not a review. A statement from someone who already knows. Australian English.\n\n" +
    "Output as: CATEGORY: BLURB (one per line)"
  );
}
```

- [ ] **Step 3: Replace pickOTC() with multi-select version**

Find the current `pickOTC` function (lines 1246–1253):
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

Replace with:
```js
function pickOTC(cat, id) {
  if (!S.otcPicks[cat]) S.otcPicks[cat] = {};
  if (S.otcPicks[cat][id]) {
    delete S.otcPicks[cat][id];
    delete S.otcBlurbs[cat + "__" + id];
  } else {
    S.otcPicks[cat][id] = true;
  }
  S.otcPrompt = buildOTCPrompt();
  render();
}
```

- [ ] **Step 4: Update updateOTCBlurb() for per-item key**

Find the current `updateOTCBlurb` function (search for `function updateOTCBlurb`). It currently takes `(cat, value)`. Replace with:

```js
function updateOTCBlurb(key, value) {
  S.otcBlurbs[key] = value;
  S.otcPrompt = buildOTCPrompt();
  // Update prompt preview in-place without full re-render
  var el = document.getElementById("otc-prompt-preview");
  if (el) el.value = S.otcPrompt;
}
```

- [ ] **Step 5: Add toggleOtcPrompt() function**

Immediately after `updateOTCBlurb`, add:

```js
function toggleOtcPrompt() {
  S.otcPromptExpanded = !S.otcPromptExpanded;
  render();
}
```

- [ ] **Step 6: Replace the renderOTC candidates block**

Find the `} else {` block inside `OTC_CATS.forEach` in `renderOTC()` (lines ~1207–1239). It currently renders single-pick pills with one blurb textarea per category. Replace the entire `} else { ... }` block with:

```js
      } else {
        // Multi-pick pills — any number of items per category can be selected
        var catPicks = S.otcPicks[cat.key] || {};
        h += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">';
        candidates.forEach(function(c) {
          var active = !!catPicks[c.id];
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
        // Per-item blurb textareas — one for each selected pill
        candidates.forEach(function(c) {
          if (!catPicks[c.id]) return;
          var blurbKey = cat.key + "__" + c.id;
          var shortTitle = (c.title || c.summary || "").slice(0, 50);
          h += '<div style="margin-bottom:8px;">';
          h += '<div style="font-size:11px;color:var(--text-3);margin-bottom:3px;">Note for "' + esc(shortTitle) + '"</div>';
          h += '<textarea class="form-input" rows="2" placeholder="Optional blurb..." style="font-size:12px;" oninput="updateOTCBlurb(\'' + blurbKey + '\',this.value)">' + esc(S.otcBlurbs[blurbKey] || "") + '</textarea>';
          h += '</div>';
        });
      }
```

- [ ] **Step 7: Add prompt preview panel after OTC_CATS.forEach loop**

In `renderOTC`, find where the `OTC_CATS.forEach` loop ends and `h += '</div>';` closes the `otc-cats` div. After that closing div, add the prompt preview panel:

```js
    // Prompt preview panel (collapsible)
    var totalPicks = OTC_CATS.reduce(function(n, cat) {
      return n + Object.keys(S.otcPicks[cat.key] || {}).length;
    }, 0);
    h += '<div style="margin-top:16px;">';
    h += '<button onclick="toggleOtcPrompt()" style="background:none;border:none;cursor:pointer;font-size:12px;color:var(--text-2);padding:0;">';
    h += (S.otcPromptExpanded ? '▲' : '▼') + ' Prompt preview';
    if (totalPicks === 0) h += ' <span style="color:var(--text-3);">(select items above)</span>';
    h += '</button>';
    if (S.otcPromptExpanded) {
      h += '<textarea id="otc-prompt-preview" class="form-input" rows="10" oninput="S.otcPrompt=this.value" ';
      h += 'placeholder="Select at least one item above to preview the prompt." ';
      h += 'style="margin-top:8px;font-size:12px;font-family:monospace;">';
      h += esc(S.otcPrompt);
      h += '</textarea>';
    }
    h += '</div>';
```

- [ ] **Step 8: Replace proceedOTC() with multi-pick version**

Find `function proceedOTC()` (lines 1257–1284). Replace the entire function with:

```js
function proceedOTC() {
  var model = getModel("model-otc");
  var picks = [];
  OTC_CATS.forEach(function(cat) {
    var catPicks = S.otcPicks[cat.key] || {};
    Object.keys(catPicks).forEach(function(id) {
      var idNum = Number(id);
      var candidates = (S.otcData && S.otcData.candidates && S.otcData.candidates[cat.key]) || [];
      var item = candidates.find(function(c) { return c.id === idNum; });
      picks.push({
        category: cat.key,
        curated_item_id: idNum,
        title: item ? (item.title || item.summary || "") : "",
        blurb: S.otcBlurbs[cat.key + "__" + id] || "",
      });
    });
  });
  if (!picks.length) {
    toast("Select at least one item before proceeding.", "error");
    return;
  }
  S.proceedData.off_the_clock = {
    section: "off_the_clock",
    model: model,
    data: { picks: picks },
    custom_prompt: S.otcPrompt || null,
  };
  openProceedModal("off_the_clock");
}
```

- [ ] **Step 9: Verify no references to old single-pick otcPicks pattern remain**

```bash
grep -n "S\.otcPicks\[cat\] ==\|S\.otcPicks\[cat\.key\] ==\|selectedId = S\.otcPicks" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html
```

Expected: 0 hits (all replaced with the dict pattern).

- [ ] **Step 10: Verify buildOTCPrompt and toggleOtcPrompt exist**

```bash
grep -n "function buildOTCPrompt\|function toggleOtcPrompt\|function updateOTCBlurb" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html
```

Expected: 3 hits.

- [ ] **Step 11: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: OTC multi-select per category with per-item blurbs and live prompt preview"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|-------------|------|
| `update_raw_item_engagement` missing ImportError fix | Task 1 |
| `post_score` / `comment_engagement` columns added | Task 1 |
| Anomaly `[object Object]` display fix | Task 3 |
| `last_scraped_at` in each section API response | Task 2 |
| `"Scraped DD Mon"` badge in each section toolbar | Task 3 |
| OTC multi-select pills (multiple per category) | Task 4 |
| Per-item blurb textarea for each selected OTC pick | Task 4 |
| Live prompt preview editable textarea | Task 4 |
| PROCEED sends `custom_prompt` | Task 4 |
| PROCEED disabled/toasted when zero picks | Task 4 |

### Placeholder scan

None found — all steps contain complete code.

### Type consistency

- `update_raw_item_engagement(item_id, post_score, comment_engagement)` — matches call site in `reddit_rss.py` which passes `(item_id, post_score, comment_engagement)` as positional args.
- `S.otcBlurbs["cat__id"]` key format used consistently in `pickOTC` (delete on deselect), `updateOTCBlurb` (update), `buildOTCPrompt` (read), `renderOTC` (textarea oninput), and `proceedOTC` (read).
- `S.otcPicks[cat][id]` dict pattern used consistently in `pickOTC`, `buildOTCPrompt`, `renderOTC`, and `proceedOTC`.
- `formatScrapedDate` defined in Task 3 Step 3, used in Task 3 Step 5.
- `toast("...", "error")` — check that `toast()` function exists and accepts two args in index.html before using it. If the second arg isn't supported, use `toast("Select at least one item before proceeding.")` with one arg.
