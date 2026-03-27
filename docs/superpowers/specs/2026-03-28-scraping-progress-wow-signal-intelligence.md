# Spec: Scraping Progress, WoW Backfill, Signal Intelligence & PROCEED Redesign
**Date:** 2026-03-28
**Status:** Approved

---

## Overview

Four interconnected improvements to the Flat White dashboard:

1. **Step-level scraping progress** — replace the bare spinner with a `3/9 · Step name` progress bar so the user knows exactly where a scrape is up to and doesn't leave the page thinking it's broken
2. **WoW delta backfill** — seed W12 data so week-on-week deltas appear immediately rather than waiting until W14
3. **Signal intelligence** — for each significant signal mover, auto-fetch supporting news articles and synthesise a short commentary; surface inline on Pulse and inject into PROCEED context
4. **PROCEED modal redesign + multi-LLM** — transparent context panel, editable prompt, model picker including GPT-5.4 family and full Claude/Gemini roster

---

## 1. Step-Level Scraping Progress

### Problem
The current scrape UX shows a small spinner and a toast — no indication of how many steps remain, what step is running, or how long to expect. Users leave the page or assume it's broken.

### Design

**Backend (`flatwhite/dashboard/api.py`)**

Replace every lambda-tuple in `_SECTION_RUNNERS` with an ordered list of `(label, callable)` pairs:

```python
_SECTION_RUNNERS: dict[str, list[tuple[str, Callable]]] = {
    "pulse": [
        ("Market hiring",       lambda: pull_market_hiring()),
        ("Salary pressure",     lambda: pull_salary_pressure()),
        ("News velocity",       lambda: pull_layoff_news_velocity()),
        ("Consumer confidence", lambda: pull_consumer_confidence()),
        ("ASX volatility",      lambda: pull_asx_volatility()),
        ("ASX momentum",        lambda: pull_asx_momentum()),
        ("Indeed hiring",       lambda: pull_indeed_hiring()),
        ("ASIC insolvency",     lambda: pull_asic_insolvency()),
        ("Signal intelligence", lambda: run_signal_intelligence()),
        ("Composite",           lambda: calculate_pulse()),
    ],
    "editorial": [
        ("Reddit RSS",          lambda: pull_reddit_editorial()),
        ("Google News",         lambda: pull_google_news_editorial()),
        ("RSS feeds",           lambda: pull_rss_feeds()),
        ("Podcast feeds",       lambda: pull_podcast_feeds()),
    ],
    "classify": [
        ("Classify items",      lambda: classify_all_unclassified()),
    ],
    "finds": [
        ("Reddit RSS",          lambda: pull_reddit_editorial()),
        ("Google News",         lambda: pull_google_news_editorial()),
        ("RSS feeds",           lambda: pull_rss_feeds()),
        ("Podcast feeds",       lambda: pull_podcast_feeds()),
        ("Classify",            lambda: classify_all_unclassified()),
    ],
    "lobby": [
        ("Employer snapshots",  lambda: pull_hiring_pulse()),
    ],
    "thread": [
        ("Reddit RSS",          lambda: pull_reddit_editorial()),
        ("Classify",            lambda: classify_all_unclassified()),
    ],
    "off_the_clock": [
        ("Off the Clock pull",  lambda: pull_off_the_clock()),
        ("Classify OTC",        lambda: classify_all_otc_unclassified()),
    ],
    "classify_otc": [
        ("Classify OTC",        lambda: classify_all_otc_unclassified()),
    ],
}
```

`_section_state` gains `step`, `total`, and `step_name` fields:

```python
# Initial state on start
_section_state[section] = {
    "running": True, "done": False, "error": None,
    "step": 0, "total": len(steps), "step_name": steps[0][0],
    "completed_at": None,
}

# Updated before each step
for i, (label, fn) in enumerate(steps):
    _section_state[section].update({"step": i, "step_name": label})
    fn()

# Final state
_section_state[section] = {
    "running": False, "done": True, "error": None,
    "step": len(steps), "total": len(steps), "step_name": "",
    "completed_at": time.strftime("%H:%M:%S"),
}
```

**API response** (`/api/section-status/{section}`):
```json
{
  "running": true,
  "done": false,
  "step": 3,
  "total": 10,
  "step_name": "ASIC insolvency",
  "error": null,
  "completed_at": null
}
```

**Frontend (`flatwhite/dashboard/static/index.html`)**

Replace the bare `<span class="ingest-spinner">` with an inline progress block rendered wherever `S.loading[section]` is true:

```
[████████░░░░░░░░░░░] 3/10 · ASIC insolvency
```

Helper function `renderSectionProgress(section)`:
- Reads `S.sectionProgress[section]` (populated on each poll response)
- Renders a narrow progress bar (amber fill, same `--amber` var), fraction, and step name
- Replaces the spinner entirely — no spinner needed separately

`pollSectionStatus` stores the full status response in `S.sectionProgress[section]` on each tick, triggering a `render()`.

---

## 2. WoW Backfill

### Problem
Only `2026-W13` exists in the database. All WoW deltas are `null`. The user needs at least W12 data to compare against W13 for writing.

### Design

**Two-phase backfill:**

**Phase A — Historical fetch (real W12 values)**

Add optional `week_iso` param to signal runners that have accessible historical data:

- `pull_asic_insolvency(week_iso=None)` — ASIC Series 1 page publishes the prior week count alongside current; parser targets row index `-2` when `week_iso` is a past week
- `pull_asx_volatility(week_iso=None)` — fetch OHLC from Yahoo Finance historical endpoint for the W12 date range
- `pull_asx_momentum(week_iso=None)` — same Yahoo Finance endpoint

These store results under the specified `week_iso` rather than `get_current_week_iso()`.

**Phase B — Seed baseline (zero-delta priming)**

A one-time SQL operation copies all `2026-W13` signal rows and employer snapshots as `2026-W12`:

```sql
-- Signals
INSERT OR IGNORE INTO signals (week_iso, signal_name, lane, area,
    raw_value, normalised_score, source_weight)
SELECT '2026-W12', signal_name, lane, area,
    raw_value, normalised_score, source_weight
FROM signals WHERE week_iso = '2026-W13';

-- Employer snapshots
INSERT OR IGNORE INTO employer_snapshots
    (employer_id, open_roles_count, snapshot_date, week_iso,
     extraction_method, ats_platform)
SELECT employer_id, open_roles_count, '2026-03-21', '2026-W12',
    extraction_method, ats_platform
FROM employer_snapshots WHERE week_iso = '2026-W13';
```

Phase A runs first (overwrites the seeded values for ASIC/ASX with real numbers). Phase B fills the rest with 0-delta placeholders.

**New endpoint:** `POST /api/backfill`

```json
{ "target_week": "2026-W12" }
```

Returns per-signal status: `{ "asic_insolvency": "real", "asx_volatility": "real", "market_hiring": "seeded", ... }`

**Frontend**

A "Backfill W12" button in the Pulse toolbar, visible only when `weeks_available < 2`. Clicking opens a confirmation dialog listing which signals will get real values vs seeded zeros. After completion, hides itself and triggers a trends reload.

**Cold-start UX**

When `weeks_available < 2` and no backfill has run, the signal table Delta column and category WoW cards show `"First week"` instead of `"—"` with a small note: *"WoW data available after backfill or next week's scrape."*

**JS bug fix**

`hist[hist.length - 2].value` → `hist[hist.length - 2].score` in the composite delta calculation (line ~561).

---

## 3. Signal Intelligence

### Problem
The quantitative signal deltas (e.g. ASIC insolvency +8.2) lack narrative support. The user needs to cite real-world events and analysis when writing about what drove changes.

### Design

**Trigger**

Runs as the penultimate step in the `pulse` runner (`run_signal_intelligence()`), after all signals are scraped and before `calculate_pulse()`. Processes only signals where `abs(WoW delta) >= 5.0`. If `weeks_available < 2`, skips gracefully.

**Search**

Google News RSS queries, one per significant mover. Pre-baked query templates per signal:

| Signal | Query template |
|--------|---------------|
| `asic_insolvency` | `"Australian corporate insolvency administration {month} {year}"` |
| `market_hiring` | `"Australian job market hiring white collar {month} {year}"` |
| `asx_volatility` | `"ASX market volatility week {month} {year}"` |
| `asx_momentum` | `"ASX market rally correction {month} {year}"` |
| `salary_pressure` | `"Australian salary wages pressure {month} {year}"` |
| `consumer_confidence` | `"Australian consumer confidence {month} {year}"` |
| `news_velocity` | `"Australian corporate layoffs redundancies {month} {year}"` |
| `indeed_hiring` | `"Australian job listings Indeed hiring {month} {year}"` |
| `contractor_proxy` | `"Australian contract work freelance market {month} {year}"` |

Fetches top 5 articles per signal: title, URL, published date, snippet. Uses existing `fetch_rss()` infrastructure.

**Synthesis**

One LLM call per signal (routed through `model_router.route()`, task type `"signal_intelligence"`, default Haiku for cost):

```
System: You are an analyst for an Australian corporate market newsletter.
User: Signal: {signal_name}
      WoW delta: {delta:+.1f} points ({direction})
      Articles:
      1. {title} ({published}) — {snippet}
      ...
      Write 2–3 sentences explaining what likely drove this movement
      and what it means for the Australian corporate market.
      Be specific. Cite the articles where relevant.
```

**Storage**

New table `signal_intelligence`:

```sql
CREATE TABLE IF NOT EXISTS signal_intelligence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name TEXT NOT NULL,
    week_iso TEXT NOT NULL,
    delta REAL,
    articles TEXT NOT NULL,   -- JSON: [{title, url, published, snippet}]
    commentary TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    UNIQUE(signal_name, week_iso)
);
```

**New endpoint:** `GET /api/signal-intelligence/{week_iso}`

Returns all intelligence records for the given week, keyed by signal name.

**Dashboard — Pulse page**

Signal table rows with intelligence gain:
- A small `≡` badge in a new "Evidence" column
- Clicking the row (or the badge) expands an inline drawer showing:
  - The 2–3 sentence commentary
  - Up to 3 article links (title + published date, URL)
- Signals without intelligence show nothing in that column

**PROCEED integration**

`/api/preview-prompt` for the Pulse section fetches signal intelligence for the current week and injects it into the context block before writing instructions:

```
SIGNAL INTELLIGENCE (significant movers this week):

ASIC insolvency (+8.2 pts, corporate_stress):
  Corporate insolvency rates climbed sharply in the week ending 21 March,
  with 47 companies entering external administration — the highest weekly
  count since Q3 2025. [commentary continues]. Sources: "ASIC data shows..."
  (AFR, 20 Mar), "Corporate failures accelerate..." (SMH, 19 Mar)

Market hiring (-6.1 pts, labour_market):
  [commentary]. Sources: ...
```

`/api/preview-prompt` also returns a `context_breakdown` object (see Section 4) that lists which intelligence records were included.

**On-demand refresh**

A "Refresh intelligence" button per signal in the expanded drawer, calling `POST /api/signal-intelligence/refresh` with `{ signal_name, week_iso }`. Useful if the initial articles were poor quality.

---

## 4. PROCEED Modal Redesign + Multi-LLM

### Problem
The current modal shows the assembled prompt in a textarea but gives no visibility into what data was injected into it. The model picker is in the toolbar rather than the modal. No OpenAI support.

### Design

**Modal layout — three panels:**

**Panel 1: Context (what's going in)**

A collapsible read-only breakdown of the data assembled for the section:

- For Pulse: signal scores + WoW deltas table; signal intelligence records (titles + commentary snippets); composite score + direction
- For editorial/finds: curated items list (title, score, tags, section assignment)
- For lobby: employer list with role counts and deltas
- For thread/OTC: relevant items

Each item has a checkbox — unchecking removes it from the assembled prompt when generating. The frontend tracks excluded item IDs in `S.proceedModal.excluded` and passes them in the `/api/proceed-section` request body so the backend can omit them from context assembly. The context panel answers "what does the model actually know about this week?" before committing.

**Panel 2: Prompt**

The full assembled prompt in a monospace editable textarea. Structured with visible section labels:

```
── SYSTEM ──────────────────────────────────────
[system instructions text]

── DATA CONTEXT ────────────────────────────────
[signal data, signal intelligence, items]

── EDITORIAL LEAN ──────────────────────────────
[user's lean text if set]

── WRITING INSTRUCTIONS ────────────────────────
[the actual writing prompt]
```

The seams are visible so the user can edit any part — or replace the whole thing.

**Panel 3: Model & Settings**

Model picker dropdown (replaces the toolbar picker, scoped to this section's generation):

```
── Anthropic ───────────────────
  Claude Opus 4.6
  Claude Sonnet 4.6   ← default
  Claude Haiku 4.5
── OpenAI ──────────────────────
  GPT-5.4
  GPT-5.4 pro
  GPT-5.4 mini
  GPT-5.4 nano
  GPT-5.2
  GPT-5.1
── Google ──────────────────────
  Gemini 2.5 Flash
```

Only models with a configured API key are shown. Selection persists per section in `localStorage`.

**Backend changes**

`/api/preview-prompt` response gains `context_breakdown`:

```json
{
  "prompt": "...",
  "context_breakdown": {
    "signals": [...],
    "signal_intelligence": [...],
    "items": [...],
    "composite": {...}
  }
}
```

`/api/proceed-section` already accepts a `model` param; this is now set from the modal picker rather than the toolbar.

**`flatwhite/model_router.py` — OpenAI additions**

```python
MODEL_REGISTRY additions:
  "gpt-5.4":       {"provider": "openai", "label": "GPT-5.4",       "env_key": "OPENAI_API_KEY"},
  "gpt-5.4-pro":   {"provider": "openai", "label": "GPT-5.4 pro",   "env_key": "OPENAI_API_KEY"},
  "gpt-5.4-mini":  {"provider": "openai", "label": "GPT-5.4 mini",  "env_key": "OPENAI_API_KEY"},
  "gpt-5.4-nano":  {"provider": "openai", "label": "GPT-5.4 nano",  "env_key": "OPENAI_API_KEY"},
  "gpt-5.2":       {"provider": "openai", "label": "GPT-5.2",       "env_key": "OPENAI_API_KEY"},
  "gpt-5.1":       {"provider": "openai", "label": "GPT-5.1",       "env_key": "OPENAI_API_KEY"},
  "claude-opus-4-6": {"provider": "anthropic", "label": "Claude Opus 4.6", "env_key": "ANTHROPIC_API_KEY"},
```

New `_call_openai()` function using the `openai` SDK:

```python
def _call_openai(model_id: str, prompt: str, system: str, temperature: float) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content
```

`TEMPERATURE_BY_TASK` gains `"signal_intelligence": 0.2`.

---

## Files Affected

| File | Changes |
|------|---------|
| `flatwhite/dashboard/api.py` | Step-list runners; `_section_state` step fields; `/api/backfill`; `/api/signal-intelligence/{week_iso}`; `/api/signal-intelligence/refresh`; duplicate `/api/lobby` route removed (line 1013); `context_breakdown` in `/api/preview-prompt` |
| `flatwhite/dashboard/static/index.html` (cont.) | JS bug fix: `hist[last-2].value` → `.score` |
| `flatwhite/dashboard/static/index.html` | `renderSectionProgress()`; backfill button; signal intelligence drawer; PROCEED modal panels 1–3; model picker moved to modal |
| `flatwhite/model_router.py` | OpenAI models in registry; `_call_openai()`; `claude-opus-4-6`; `signal_intelligence` task type |
| `flatwhite/signals/asic_insolvency.py` | `week_iso` param |
| `flatwhite/signals/asx_volatility.py` | `week_iso` param |
| `flatwhite/signals/asx_momentum.py` | `week_iso` param |
| `flatwhite/signals/signal_intelligence.py` | New file: `run_signal_intelligence()` |
| `flatwhite/db.py` | `signal_intelligence` table migration |

---

## Out of Scope

- Backfilling signals other than ASIC/ASX with real historical data (sources don't expose it)
- Signal intelligence for non-Pulse sections (editorial, lobby) — future work
- Saving model preference server-side (localStorage is sufficient)
