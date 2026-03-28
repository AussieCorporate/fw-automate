# Bug Fixes, Last Scraped Date & OTC Redesign — Design Spec

## Goal

Fix three crashing bugs (`update_raw_item_engagement` missing, anomaly display, and the broken scrape pipeline), show a last-scraped timestamp in each section's toolbar, and redesign OTC selection to allow multiple picks per category with a live-editable prompt preview.

## Architecture

All changes are either backend DB additions (one missing function + two columns) or frontend edits to `index.html`. No new API endpoints are added for Track A bugs. Track A's last-scraped date requires a `last_scraped_at` field added to existing load endpoints. Track B is entirely frontend with no backend changes.

## Tech Stack

- Python/FastAPI backend (`flatwhite/dashboard/api.py`, `flatwhite/db.py`)
- Vanilla JS SPA frontend (`flatwhite/dashboard/static/index.html`)
- SQLite via `flatwhite/db.py`

---

## Track A — Bug Fixes + Last Scraped Date

### Bug 1: `update_raw_item_engagement` missing from db.py

**Root cause:** `flatwhite/editorial/reddit_rss.py` imports `update_raw_item_engagement` from `flatwhite.db` at line 4. The function does not exist. Python raises `ImportError` when `reddit_rss` is imported — which happens during any scrape that touches editorial content (Big Conversations, Finds, Threads all call reddit_rss). The `raw_items` table also has no columns for the engagement data.

**Fix:**
1. Add two columns to `raw_items` via `migrate_db()` — idempotent `ALTER TABLE … ADD COLUMN` (safe on existing DBs):
   - `post_score INTEGER`
   - `comment_engagement INTEGER`
2. Add `update_raw_item_engagement(item_id: int, post_score: int, comment_engagement: int) -> None` to `db.py` — a simple `UPDATE raw_items SET post_score=?, comment_engagement=? WHERE id=?`.

**Files:** `flatwhite/db.py`

---

### Bug 2: Anomaly display renders `[object Object]`

**Root cause:** Line ~635 of `index.html` renders anomalies as `esc(a.message || a)`. Anomaly dicts have no `.message` field — they have `signal`, `direction`, `current`, `confidence`, `deviation_mads`. The fallback `esc(a)` converts the whole object to `[object Object]`.

**Fix:** Replace the anomaly display expression with a meaningful string built from actual anomaly fields:

```js
esc(a.signal + ': score ' + (a.current != null ? a.current : '—') + ' (' + (a.direction || '') + ', ' + (a.confidence || '') + ' confidence)')
```

**Files:** `flatwhite/dashboard/static/index.html`

---

### Feature: Last scraped date in section toolbars

**Design:**
- Backend: each section load endpoint adds a `last_scraped_at` field to its JSON response:
  - Pulse (`/api/pulse`): `SELECT max(pulled_at) FROM signals WHERE week_iso = ?`
  - All editorial sections (`/api/items`, `/api/threads`, `/api/big-conversation-candidates`, `/api/off-the-clock`, `/api/lobby`): `SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?`
- Frontend: when each section loads, store `S.lastScraped[section] = response.last_scraped_at`. Display as a small grey timestamp badge to the right of the PROCEED button in each section's toolbar:
  - Format: `"Scraped 28 Mar 10:42am"` (Australian locale, no year)
  - If `S.lastScraped[section]` is null/absent: nothing shown

**State addition:** `S.lastScraped = {}` in the S initialisation block.

**Files:** `flatwhite/dashboard/api.py`, `flatwhite/dashboard/static/index.html`

---

## Track B — OTC Multi-select + Prompt Visibility

### State changes

| State key | Before | After |
|-----------|--------|-------|
| `S.otcPicks[cat]` | Single item id or `undefined` | Dict `{ [id]: true }` — multiple ids per category |
| `S.otcBlurbs` | `{ [cat]: text }` — one blurb per category | `{ [cat + "__" + id]: text }` — one blurb per picked item |
| `S.otcPrompt` | (new) | Editable string — the full prompt to send to LLM |

`S.otcPicks` starts as `{}`. All categories start with no picks.

---

### Pill UX — multi-select

Same pill panel per category as current redesign, but clicking a pill toggles it in/out of `S.otcPicks[cat]` as a key. Multiple pills per category can be active simultaneously (amber border + background). Clicking an active pill removes its key from `S.otcPicks[cat]`.

Below the pill row, for each selected item in that category, render a labeled blurb textarea:

```
Note for "[truncated title]":
[textarea — oninput updates S.otcBlurbs["cat__id"]]
```

Blurb textareas appear in the same order as the pills, only for selected items.

---

### Prompt preview panel

Below all category cards, a collapsible section labelled **"Prompt"** (collapsed by default, expands on click). Inside: a `<textarea>` pre-populated with the constructed prompt. Updates live whenever picks or blurbs change (rebuilt by `buildOTCPrompt()`).

**`buildOTCPrompt()` JS function** — mirrors the Python template in `_proceed_off_the_clock`:

```
Polish these Off the Clock blurbs for Flat White.

Category: [cat]
Title: [title]
Draft blurb: [blurb]

Category: [cat]
...

For each, rewrite the blurb in 1-2 sentences. Voice: dry, specific, opinionated. Not a review. A statement from someone who already knows. Australian English.

Output as: CATEGORY: BLURB (one per line)
```

If no picks: prompt textarea is empty and shows placeholder `"Select at least one item above to preview the prompt."`.

User may edit the textarea freely. `S.otcPrompt` is updated `oninput`.

---

### `pickOTC(cat, id)` — updated

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

---

### `proceedOTC()` — updated

Collects all active picks across all categories. Sends `custom_prompt = S.otcPrompt`. If `S.otcPrompt` is empty (no picks), the PROCEED button is disabled with tooltip `"Select at least one item"`.

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
  S.proceedData.off_the_clock = {
    section: "off_the_clock",
    model: model,
    data: { picks: picks },
    custom_prompt: S.otcPrompt || null,
  };
  openProceedModal("off_the_clock");
}
```

---

## Self-Review

**Spec coverage:**

| Requirement | Covered |
|-------------|---------|
| Fix `update_raw_item_engagement` ImportError | ✅ Bug 1 |
| Add `post_score` / `comment_engagement` columns to raw_items | ✅ Bug 1 |
| Fix anomaly `[object Object]` display | ✅ Bug 2 |
| Last scraped date in each section toolbar | ✅ Track A feature |
| OTC multi-select pills (multiple per category) | ✅ Track B |
| Per-item blurb textarea for each selected OTC item | ✅ Track B |
| Live prompt preview editable textarea | ✅ Track B |
| PROCEED sends custom_prompt | ✅ Track B |
| PROCEED disabled when zero picks | ✅ Track B |

**Placeholder scan:** None found.

**Internal consistency:**
- `S.otcBlurbs` key format `cat__id` used consistently in `pickOTC`, `renderOTC`, `buildOTCPrompt`, and `proceedOTC`.
- `last_scraped_at` returned from API and consumed in `S.lastScraped[section]`.
- `update_raw_item_engagement` signature matches the call site in `reddit_rss.py`.

**Scope:** Two independent implementation tasks — Track A (DB + API + minor frontend) and Track B (frontend only). Appropriate for one plan with clear task boundaries.

**Ambiguity resolved:**
- Multiple picks per category = each gets its own blurb textarea, all go into the LLM prompt
- `last_scraped_at` for lobby uses `raw_items.pulled_at` (same table as editorial)
- `S.otcPrompt` is rebuilt on every pick/blurb change (not debounced — data set is small)
