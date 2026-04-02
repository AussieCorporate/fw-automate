# Scraping Progress, WoW Backfill, Signal Intelligence & PROCEED Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add step-level scrape progress bars, expose the existing backfill module via API/UI, build a signal intelligence layer that auto-researches significant WoW movers, and redesign the PROCEED modal with a transparent context panel and full multi-LLM support including GPT-5.4.

**Architecture:** The step-progress refactor converts flat lambda-tuple runners into ordered `(label, fn)` lists and enriches `_section_state` with `step/total/step_name`. The backfill API wraps the existing `run_backfill()` orchestrator and adds employer snapshot seeding. Signal intelligence runs as a post-signal step in the pulse runner, storing commentary in a new `signal_intelligence` table and injecting it into PROCEED prompts. The PROCEED modal gains a three-panel layout (context | prompt | model) driven by a new `context_breakdown` field from `/api/preview-prompt`.

**Tech Stack:** Python 3.11, FastAPI, SQLite, vanilla JS, `openai` SDK (new), `anthropic` SDK (existing), `yfinance` (existing), `feedparser` (existing)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `flatwhite/model_router.py` | Modify | Add OpenAI models + `_call_openai()`, add `claude-opus-4-6`, add `signal_intelligence` task type |
| `flatwhite/db.py` | Modify | Add `signal_intelligence` table in `migrate_db()` |
| `flatwhite/dashboard/api.py` | Modify | Remove duplicate `/api/lobby` (line 1013); refactor `_SECTION_RUNNERS` to step lists; update `_run_section_background`; add `/api/backfill`; add `/api/signal-intelligence/{week_iso}`; add `/api/signal-intelligence/refresh`; add `context_breakdown` to `/api/preview-prompt` |
| `flatwhite/signals/signal_intelligence.py` | Create | `run_signal_intelligence()` — queries Google News, synthesises commentary, stores to DB |
| `flatwhite/dashboard/static/index.html` | Modify | `renderSectionProgress()`; update `pollSectionStatus`; backfill button + cold-start UX; JS composite delta bugfix; signal intelligence drawer; three-panel PROCEED modal |
| `tests/test_model_router.py` | Create | Unit tests for OpenAI dispatch and signal_intelligence task routing |
| `tests/test_signal_intelligence.py` | Create | Unit tests for query generation, skip-when-cold, DB storage |
| `tests/test_backfill_api.py` | Create | Unit test for `/api/backfill` employer snapshot seeding |

---

## Task 1: Remove duplicate `/api/lobby` route and add OpenAI to model router

**Files:**
- Modify: `flatwhite/dashboard/api.py:1013-1060`
- Modify: `flatwhite/model_router.py`
- Create: `tests/test_model_router.py`

The old `/api/lobby` at line 1013 is the first registered route and wins over the correct implementation at line 1413. Remove lines 1013–1060.

- [ ] **Step 1: Write the failing model router test**

Create `tests/test_model_router.py`:

```python
"""Tests for model_router — provider dispatch and task type routing."""
from unittest.mock import patch, MagicMock
import pytest


def test_openai_models_in_registry():
    from flatwhite.model_router import MODEL_REGISTRY
    for model_id in ["gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.2", "gpt-5.1"]:
        assert model_id in MODEL_REGISTRY, f"{model_id} missing from MODEL_REGISTRY"
        assert MODEL_REGISTRY[model_id]["provider"] == "openai"
        assert MODEL_REGISTRY[model_id]["env_key"] == "OPENAI_API_KEY"


def test_claude_opus_in_registry():
    from flatwhite.model_router import MODEL_REGISTRY
    assert "claude-opus-4-6" in MODEL_REGISTRY
    assert MODEL_REGISTRY["claude-opus-4-6"]["provider"] == "anthropic"


def test_signal_intelligence_task_type():
    from flatwhite.model_router import TEMPERATURE_BY_TASK, DEFAULT_MODEL_BY_TASK
    assert "signal_intelligence" in TEMPERATURE_BY_TASK
    assert TEMPERATURE_BY_TASK["signal_intelligence"] == 0.2
    assert DEFAULT_MODEL_BY_TASK.get("signal_intelligence") == "claude-haiku-4-5"


def test_openai_dispatch_calls_openai_sdk():
    """route() should call _call_openai for an OpenAI model."""
    import os
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch("flatwhite.model_router._call_openai", return_value="result") as mock_openai:
            from flatwhite.model_router import route
            result = route("signal_intelligence", "test prompt", model_override="gpt-5.4")
            mock_openai.assert_called_once()
            assert result == "result"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/pytest tests/test_model_router.py -v
```

Expected: FAIL — `gpt-5.4 missing from MODEL_REGISTRY`, `signal_intelligence` not in `TEMPERATURE_BY_TASK`

- [ ] **Step 3: Add OpenAI to model_router.py**

In `flatwhite/model_router.py`, replace the `MODEL_REGISTRY` dict and `TEMPERATURE_BY_TASK` / `DEFAULT_MODEL_BY_TASK` with:

```python
TEMPERATURE_BY_TASK: dict[str, float] = {
    "classification": 0.1,
    "scoring": 0.1,
    "tagging": 0.1,
    "anomaly_summary": 0.2,
    "editorial": 0.3,
    "summary": 0.3,
    "hook": 0.7,
    "big_conversation": 0.3,
    "signal_intelligence": 0.2,
}

DEFAULT_MODEL_BY_TASK: dict[str, str] = {
    "classification": "gemini-2.5-flash",
    "scoring": "gemini-2.5-flash",
    "tagging": "gemini-2.5-flash",
    "anomaly_summary": "gemini-2.5-flash",
    "editorial": "claude-sonnet-4-6",
    "summary": "claude-sonnet-4-6",
    "hook": "claude-sonnet-4-6",
    "big_conversation": "claude-sonnet-4-6",
    "signal_intelligence": "claude-haiku-4-5",
}

MODEL_REGISTRY: dict[str, dict] = {
    "gemini-2.5-flash":  {"provider": "gemini",    "label": "Gemini 2.5 Flash",  "env_key": "GEMINI_API_KEY"},
    "claude-opus-4-6":   {"provider": "anthropic", "label": "Claude Opus 4.6",   "env_key": "ANTHROPIC_API_KEY"},
    "claude-sonnet-4-6": {"provider": "anthropic", "label": "Claude Sonnet 4.6", "env_key": "ANTHROPIC_API_KEY"},
    "claude-haiku-4-5":  {"provider": "anthropic", "label": "Claude Haiku 4.5",  "env_key": "ANTHROPIC_API_KEY"},
    "gpt-5.4":           {"provider": "openai",    "label": "GPT-5.4",           "env_key": "OPENAI_API_KEY"},
    "gpt-5.4-pro":       {"provider": "openai",    "label": "GPT-5.4 pro",       "env_key": "OPENAI_API_KEY"},
    "gpt-5.4-mini":      {"provider": "openai",    "label": "GPT-5.4 mini",      "env_key": "OPENAI_API_KEY"},
    "gpt-5.4-nano":      {"provider": "openai",    "label": "GPT-5.4 nano",      "env_key": "OPENAI_API_KEY"},
    "gpt-5.2":           {"provider": "openai",    "label": "GPT-5.2",           "env_key": "OPENAI_API_KEY"},
    "gpt-5.1":           {"provider": "openai",    "label": "GPT-5.1",           "env_key": "OPENAI_API_KEY"},
}
```

Then add `_call_openai` after `_call_claude`:

```python
def _call_openai(model_id: str, prompt: str, system: str, temperature: float) -> str:
    """Call an OpenAI model via the openai SDK."""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages: list[dict] = []
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

Update `_call_model` to dispatch OpenAI:

```python
def _call_model(model_id: str, prompt: str, system: str, temperature: float) -> str:
    info = MODEL_REGISTRY.get(model_id)
    if not info:
        raise ValueError(f"Unknown model: {model_id}")
    api_key = os.getenv(info["env_key"])
    if not api_key:
        raise ValueError(f"No API key configured for {model_id} (set {info['env_key']})")
    if info["provider"] == "gemini":
        return _call_gemini(prompt, system, temperature)
    elif info["provider"] == "anthropic":
        return _call_claude(model_id, prompt, system, temperature)
    elif info["provider"] == "openai":
        return _call_openai(model_id, prompt, system, temperature)
    else:
        raise ValueError(f"Unknown provider: {info['provider']}")
```

- [ ] **Step 4: Remove duplicate `/api/lobby` route from api.py**

Delete lines 1013–1060 in `flatwhite/dashboard/api.py` (the old `@app.get("/api/lobby")` with no MoM support). The correct implementation stays at its current position (~line 1413).

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_model_router.py tests/test_lobby.py -v
```

Expected: all PASS. The lobby tests now hit the correct implementation.

- [ ] **Step 6: Commit**

```bash
git add flatwhite/model_router.py flatwhite/dashboard/api.py tests/test_model_router.py
git commit -m "feat: add OpenAI GPT-5 models and remove duplicate /api/lobby route"
```

---

## Task 2: DB migration — signal_intelligence table

**Files:**
- Modify: `flatwhite/db.py`
- Test via existing `temp_db` fixture

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signal_intelligence.py` (create this file):

```python
"""Tests for signal_intelligence module and DB table."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def si_db(tmp_path: Path):
    db_path = tmp_path / "si_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def test_signal_intelligence_table_exists(si_db):
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "signal_intelligence" in tables


def test_signal_intelligence_unique_constraint(si_db):
    """Duplicate (signal_name, week_iso) should be replaced, not duplicated."""
    import json
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        articles = json.dumps([{"title": "Test", "url": "http://x.com", "published": "2026-03-20", "snippet": "foo"}])
        conn.execute(
            """INSERT INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "Commentary A"),
        )
        conn.commit()
        conn.execute(
            """INSERT OR REPLACE INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "Commentary B"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT commentary FROM signal_intelligence WHERE signal_name='asx_volatility' AND week_iso='2026-W13'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "Commentary B"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_signal_intelligence_table_exists -v
```

Expected: FAIL — `signal_intelligence` not in tables

- [ ] **Step 3: Add migration to db.py**

In `flatwhite/db.py`, add to `migrate_db()` before the final `conn.commit()`:

```python
    # v3 signal_intelligence table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_name TEXT NOT NULL,
            week_iso TEXT NOT NULL,
            delta REAL,
            articles TEXT NOT NULL,
            commentary TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            UNIQUE(signal_name, week_iso)
        )
    """)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py -v
```

Expected: both tests PASS

- [ ] **Step 5: Commit**

```bash
git add flatwhite/db.py tests/test_signal_intelligence.py
git commit -m "feat: add signal_intelligence table migration"
```

---

## Task 3: Step-level progress — backend

**Files:**
- Modify: `flatwhite/dashboard/api.py` (the `_SECTION_RUNNERS` dict and `_run_section_background` function)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signal_intelligence.py`:

```python
def test_section_state_has_step_fields():
    """After _run_section_background, state should have step/total/step_name."""
    from flatwhite.dashboard.api import _section_state, _run_section_background
    call_log = []

    import flatwhite.dashboard.api as api_module
    original_runners = api_module._SECTION_RUNNERS

    # Temporarily replace classify (1-step) runner with a controlled one
    api_module._SECTION_RUNNERS = {
        "test_section": [
            ("Step one", lambda: call_log.append("one")),
            ("Step two", lambda: call_log.append("two")),
        ]
    }

    _run_section_background("test_section")

    api_module._SECTION_RUNNERS = original_runners

    state = _section_state["test_section"]
    assert state["done"] is True
    assert state["running"] is False
    assert state["step"] == 2
    assert state["total"] == 2
    assert call_log == ["one", "two"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_section_state_has_step_fields -v
```

Expected: FAIL — `_section_state` missing `step`/`total` keys (or test errors on import because runners aren't lists yet)

- [ ] **Step 3: Refactor _SECTION_RUNNERS in api.py**

Replace the `_SECTION_RUNNERS` dict (currently defined around line 1228) with:

```python
_SECTION_RUNNERS: dict[str, list[tuple[str, "Callable"]]] = {
    "pulse": [
        ("Market hiring",       lambda: __import__("flatwhite.signals.market_hiring",   fromlist=["pull_market_hiring"]).pull_market_hiring()),
        ("Salary pressure",     lambda: __import__("flatwhite.signals.salary_pressure", fromlist=["pull_salary_pressure"]).pull_salary_pressure()),
        ("News velocity",       lambda: __import__("flatwhite.signals.news_velocity",   fromlist=["pull_layoff_news_velocity"]).pull_layoff_news_velocity()),
        ("Consumer confidence", lambda: __import__("flatwhite.signals.consumer_confidence", fromlist=["pull_consumer_confidence"]).pull_consumer_confidence()),
        ("ASX volatility",      lambda: __import__("flatwhite.signals.asx_volatility",  fromlist=["pull_asx_volatility"]).pull_asx_volatility()),
        ("ASX momentum",        lambda: __import__("flatwhite.signals.asx_momentum",    fromlist=["pull_asx_momentum"]).pull_asx_momentum()),
        ("Indeed hiring",       lambda: __import__("flatwhite.signals.indeed_hiring",   fromlist=["pull_indeed_hiring"]).pull_indeed_hiring()),
        ("ASIC insolvency",     lambda: __import__("flatwhite.signals.asic_insolvency", fromlist=["pull_asic_insolvency"]).pull_asic_insolvency()),
        ("Signal intelligence", lambda: __import__("flatwhite.signals.signal_intelligence", fromlist=["run_signal_intelligence"]).run_signal_intelligence()),
        ("Composite",           lambda: __import__("flatwhite.pulse.composite",         fromlist=["calculate_pulse"]).calculate_pulse()),
    ],
    "editorial": [
        ("Reddit RSS",    lambda: __import__("flatwhite.editorial.reddit_rss",              fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News",   lambda: __import__("flatwhite.editorial.google_news_editorial",   fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("RSS feeds",     lambda: __import__("flatwhite.editorial.rss_feeds",               fromlist=["pull_rss_feeds"]).pull_rss_feeds()),
        ("Podcast feeds", lambda: __import__("flatwhite.editorial.podcast_feeds",           fromlist=["pull_podcast_feeds"]).pull_podcast_feeds()),
    ],
    "classify": [
        ("Classify items", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "finds": [
        ("Reddit RSS",    lambda: __import__("flatwhite.editorial.reddit_rss",            fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News",   lambda: __import__("flatwhite.editorial.google_news_editorial", fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("RSS feeds",     lambda: __import__("flatwhite.editorial.rss_feeds",             fromlist=["pull_rss_feeds"]).pull_rss_feeds()),
        ("Podcast feeds", lambda: __import__("flatwhite.editorial.podcast_feeds",         fromlist=["pull_podcast_feeds"]).pull_podcast_feeds()),
        ("Classify",      lambda: __import__("flatwhite.classify.classifier",             fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "lobby": [
        ("Employer snapshots", lambda: __import__("flatwhite.signals.hiring_pulse", fromlist=["pull_hiring_pulse"]).pull_hiring_pulse()),
    ],
    "thread": [
        ("Reddit RSS", lambda: __import__("flatwhite.editorial.reddit_rss",    fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Classify",   lambda: __import__("flatwhite.classify.classifier",     fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "off_the_clock": [
        ("Off the Clock", lambda: __import__("flatwhite.editorial.off_the_clock", fromlist=["pull_off_the_clock"]).pull_off_the_clock()),
        ("Classify OTC",  lambda: __import__("flatwhite.classify.classifier",     fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified()),
    ],
    "classify_otc": [
        ("Classify OTC", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified()),
    ],
}
```

- [ ] **Step 4: Update _run_section_background**

Replace the existing `_run_section_background` function:

```python
def _run_section_background(section: str) -> None:
    """Run a section's steps sequentially, updating _section_state after each step."""
    steps = _SECTION_RUNNERS[section]
    total = len(steps)
    try:
        for i, (label, fn) in enumerate(steps):
            _section_state[section].update({"step": i, "total": total, "step_name": label})
            fn()
        _section_state[section] = {
            "running": False, "done": True, "error": None,
            "step": total, "total": total, "step_name": "",
            "completed_at": _time.strftime("%H:%M:%S"),
        }
    except Exception as e:
        _section_state[section] = {
            "running": False, "done": True, "error": str(e),
            "step": _section_state[section].get("step", 0), "total": total, "step_name": "",
            "completed_at": _time.strftime("%H:%M:%S"),
        }
```

- [ ] **Step 5: Update api_run_section to set initial step state**

In `api_run_section`, change the initial state assignment:

```python
steps = _SECTION_RUNNERS[section]
_section_state[section] = {
    "running": True, "done": False, "error": None,
    "step": 0, "total": len(steps), "step_name": steps[0][0] if steps else "",
    "completed_at": None,
}
```

Also update the 409 check to use `_SECTION_RUNNERS[section]` instead of `_SECTION_RUNNERS`:

```python
if section not in _SECTION_RUNNERS:
    return JSONResponse(
        {"error": f"Unknown section: {section}. Available: {', '.join(_SECTION_RUNNERS.keys())}"},
        status_code=400,
    )
```

(This line already exists — just verify it still works with list values.)

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_section_state_has_step_fields -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat: step-level progress tracking in section runners"
```

---

## Task 4: Step-level progress — frontend

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add sectionProgress to S state**

Find the state initialisation block (where `S` object is defined, around `var S = {`). Add:

```js
sectionProgress: {},   // { section: {step, total, step_name} }
```

- [ ] **Step 2: Update pollSectionStatus to store progress**

Replace the inner `fetch` callback in `pollSectionStatus`:

```js
function pollSectionStatus(section) {
  var poll = setInterval(function() {
    fetch("/api/section-status/" + section).then(function(r) { return r.json(); }).then(function(d) {
      // Always store latest progress for render
      S.sectionProgress[section] = {
        step: d.step || 0,
        total: d.total || 0,
        step_name: d.step_name || ""
      };
      if (!d.running && d.done) {
        clearInterval(poll);
        S.loading[section] = false;
        delete S.sectionProgress[section];
        if (d.error) {
          showToast(section.replace(/_/g, " ") + " failed: " + d.error, "error");
        } else {
          showToast(section.replace(/_/g, " ") + " complete");
        }
        switch (section) {
          case "pulse": S.pulse = null; S.trends = null; break;
          case "finds": case "editorial": case "classify": S.items = null; S.bigConvCandidates = null; break;
          case "lobby": S.lobby = null; break;
          case "thread": S.threads = null; break;
          case "off_the_clock": case "classify_otc": S.otcData = null; break;
          case "big_conversation": S.bigConvCandidates = null; break;
        }
        var pageForSection = {pulse:"pulse", finds:"finds", editorial:"editorial", classify:"finds", lobby:"lobby", thread:"thread", off_the_clock:"off_the_clock", classify_otc:"off_the_clock", big_conversation:"big_conversation"};
        var relevantPage = pageForSection[section] || section;
        if (S.page === relevantPage) {
          loadPageData(S.page).then(function() { render(); });
        } else {
          render();
        }
      } else {
        render();
      }
    }).catch(function() { /* ignore poll errors */ });
  }, 2000);
}
```

- [ ] **Step 3: Add renderSectionProgress helper**

Add this function after the `sectionStatus` function:

```js
function renderSectionProgress(section) {
  var p = S.sectionProgress[section];
  if (!p || !S.loading[section]) return '<span class="ingest-spinner"></span>';
  var total = p.total || 1;
  var step = Math.min(p.step, total);
  var pct = Math.round((step / total) * 100);
  var label = esc(p.step_name || "Running...");
  return (
    '<span style="display:inline-flex;align-items:center;gap:8px;margin-left:8px;">' +
    '<span style="display:inline-block;width:120px;height:6px;background:var(--divider);border-radius:3px;overflow:hidden;">' +
    '<span style="display:block;height:100%;width:' + pct + '%;background:var(--amber);border-radius:3px;transition:width 0.4s ease;"></span>' +
    '</span>' +
    '<span style="font-size:12px;color:var(--text-2);">' + step + '/' + total + ' &middot; ' + label + '</span>' +
    '</span>'
  );
}
```

- [ ] **Step 4: Replace spinners with renderSectionProgress calls**

Find every occurrence of:
```js
if (S.loading.SECTION) h += ' <span class="ingest-spinner"></span>';
```

Replace each with:
```js
if (S.loading.SECTION) h += renderSectionProgress('SECTION');
```

Sections to update: `editorial`, `pulse`, `lobby`, `finds`, `thread`, `off_the_clock`. Do each one.

- [ ] **Step 5: Verify in browser**

Start the server (`! .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --port 8500`) and trigger any scrape. Confirm the progress bar appears and advances every 2s.

- [ ] **Step 6: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: step-level scraping progress bar in dashboard"
```

---

## Task 5: WoW backfill — API endpoint, employer seed, cold-start UX, JS bugfix

**Files:**
- Modify: `flatwhite/dashboard/api.py`
- Modify: `flatwhite/dashboard/static/index.html`
- Create: `tests/test_backfill_api.py`

The existing `run_backfill()` in `flatwhite/pulse/backfill.py` already handles ASX, consumer confidence, and Google Trends for N past weeks. We just need to: (a) expose it via API, (b) add employer snapshot seeding, (c) add a UI button, (d) fix the composite delta JS bug.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backfill_api.py`:

```python
"""Tests for /api/backfill endpoint — employer snapshot seeding."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import pytest
import flatwhite.db as db_module


@pytest.fixture
def backfill_db(tmp_path: Path):
    db_path = tmp_path / "backfill_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO employer_watchlist (employer_name, sector, careers_url) VALUES ('ANZ', 'banking', 'http://anz.com')"
        )
        emp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO employer_snapshots (employer_id, open_roles_count, snapshot_date, week_iso, extraction_method, ats_platform) VALUES (?, 150, '2026-03-27', '2026-W13', 'html_scrape', 'workday')",
            (emp_id,),
        )
        conn.commit()
        conn.close()
        yield db_path


def test_backfill_seeds_employer_snapshots(backfill_db):
    """POST /api/backfill should copy W13 employer snapshots as W12."""
    with patch.object(db_module, "DB_PATH", backfill_db):
        # Patch run_backfill to avoid real external calls
        with patch("flatwhite.pulse.backfill.run_backfill") as mock_rb:
            with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
                from flatwhite.dashboard.api import api_backfill
                import asyncio

                class FakeRequest:
                    async def json(self):
                        return {"target_week": "2026-W12"}

                result = asyncio.get_event_loop().run_until_complete(api_backfill(FakeRequest()))
                data = json.loads(result.body)
                assert data["seeded_employers"] > 0

                conn = db_module.get_connection()
                rows = conn.execute(
                    "SELECT * FROM employer_snapshots WHERE week_iso = '2026-W12'"
                ).fetchall()
                conn.close()
                assert len(rows) == 1
                assert rows[0]["open_roles_count"] == 150


def test_backfill_skips_existing_target_week(backfill_db):
    """If target_week already has employer snapshots, don't re-seed."""
    with patch.object(db_module, "DB_PATH", backfill_db):
        conn = db_module.get_connection()
        emp_id = conn.execute("SELECT id FROM employer_watchlist LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO employer_snapshots (employer_id, open_roles_count, snapshot_date, week_iso) VALUES (?, 140, '2026-03-21', '2026-W12')",
            (emp_id,),
        )
        conn.commit()
        conn.close()

        with patch("flatwhite.pulse.backfill.run_backfill"):
            with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
                from flatwhite.dashboard.api import api_backfill
                import asyncio

                class FakeRequest:
                    async def json(self):
                        return {"target_week": "2026-W12"}

                result = asyncio.get_event_loop().run_until_complete(api_backfill(FakeRequest()))
                data = json.loads(result.body)
                # seeded_employers should be 0 — already existed
                assert data["seeded_employers"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_backfill_api.py -v
```

Expected: FAIL — `api_backfill` not defined

- [ ] **Step 3: Add /api/backfill endpoint to api.py**

Add after the `/api/section-status/{section}` endpoint:

```python
@app.post("/api/backfill")
async def api_backfill(request: Request) -> JSONResponse:
    """Backfill historical signal data and seed employer snapshots for a past week.

    Body: {"target_week": str}  e.g. "2026-W12"
    Runs run_backfill(weeks=2) for signals, then seeds employer_snapshots via SQL copy.
    Returns: {"seeded_employers": int, "started_signal_backfill": bool}
    """
    body = await request.json()
    target_week = body.get("target_week", "")

    conn = get_connection()
    # Check if employer snapshots already exist for target_week
    existing = conn.execute(
        "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (target_week,)
    ).fetchone()[0]

    seeded = 0
    if existing == 0:
        # Copy current week's employer snapshots as target_week baseline
        current_week = get_current_week_iso()
        import datetime as _dt_local
        year, wn = int(target_week[:4]), int(target_week[6:])
        target_date = _dt_local.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u").strftime("%Y-%m-%d")
        conn.execute(
            f"""INSERT OR IGNORE INTO employer_snapshots
                (employer_id, open_roles_count, snapshot_date, week_iso, extraction_method, ats_platform)
                SELECT employer_id, open_roles_count, ?, ?, extraction_method, ats_platform
                FROM employer_snapshots WHERE week_iso = ?""",
            (target_date, target_week, current_week),
        )
        conn.commit()
        seeded = conn.execute(
            "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (target_week,)
        ).fetchone()[0]
    conn.close()

    # Run signal backfill in a background thread (slow — includes Google Trends)
    import threading
    def _do_signal_backfill():
        from flatwhite.pulse.backfill import run_backfill
        run_backfill(weeks=2)

    t = threading.Thread(target=_do_signal_backfill, daemon=True)
    t.start()

    return JSONResponse({
        "seeded_employers": seeded,
        "started_signal_backfill": True,
        "target_week": target_week,
    })
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_backfill_api.py -v
```

Expected: both PASS

- [ ] **Step 5: Fix JS composite delta bug**

In `index.html`, find (around line 561):
```js
delta = (p.smoothed_score || 0) - (hist[hist.length - 2].value || 0);
```
Replace with:
```js
delta = (p.smoothed_score || 0) - (hist[hist.length - 2].score || 0);
```

- [ ] **Step 6: Add cold-start UX and backfill button to Pulse toolbar**

In `renderPulse`, find:
```js
h += '<button class="btn btn-primary" onclick="runSection(\'pulse\')">SCRAPE</button>';
```
Replace with:
```js
h += '<button class="btn btn-primary" onclick="runSection(\'pulse\')">SCRAPE</button>';
if (S.trends && S.trends.weeks_available < 2) {
  h += ' <button class="btn btn-secondary" onclick="runBackfill()" style="font-size:11px;">Backfill W' + (new Date().getMonth() > 0 ? (new Date().getMonth() + 52) : 52) + '</button>';
  h += ' <span style="font-size:11px;color:var(--text-3);margin-left:4px;">No WoW data yet</span>';
}
```

Replace the dynamic week number with a simple label. Change to:
```js
h += '<button class="btn btn-primary" onclick="runSection(\'pulse\')">SCRAPE</button>';
if (S.trends && S.trends.weeks_available < 2) {
  h += ' <button class="btn btn-secondary" onclick="runBackfill()" style="font-size:11px;">Backfill prev week</button>';
}
```

Add `runBackfill` function:
```js
function runBackfill() {
  // Compute previous week ISO string
  var now = new Date();
  var prevWeek = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
  var iso = prevWeek.toISOString().slice(0, 10);
  // Use ISO week calculation
  var d = new Date(Date.UTC(prevWeek.getFullYear(), prevWeek.getMonth(), prevWeek.getDate()));
  var dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  var weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  var targetWeek = d.getUTCFullYear() + "-W" + String(weekNo).padStart(2, "0");

  showToast("Backfilling " + targetWeek + " — signal backfill runs in background (~6 min for Google Trends)");
  api("/api/backfill", { method: "POST", body: { target_week: targetWeek } })
    .then(function(d) {
      showToast("Backfill started: " + d.seeded_employers + " employer snapshots seeded. Signal data populating in background.");
      S.trends = null;
      loadPageData("pulse").then(function() { render(); });
    })
    .catch(function(e) { showToast("Backfill failed: " + e.message, "error"); });
}
```

Add cold-start messaging in the WoW delta cells. In `renderCategoryTrends`, change:
```js
var deltaText = delta == null ? "—" : ((delta > 0 ? "+" : "") + delta.toFixed(1));
```
To:
```js
var weeksAvail = S.trends && S.trends.weeks_available != null ? S.trends.weeks_available : 1;
var deltaText = delta == null ? (weeksAvail < 2 ? "first week" : "—") : ((delta > 0 ? "+" : "") + delta.toFixed(1));
```

In the signal table, change:
```js
var hasDelta = moverDeltas[name] != null;
```
No change needed — if no previous week, `moverDeltas` is empty and `hasDelta` is false, rendering "—". That's correct.

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/api.py flatwhite/dashboard/static/index.html tests/test_backfill_api.py
git commit -m "feat: WoW backfill API endpoint, employer seed, cold-start UX, composite delta bugfix"
```

---

## Task 6: Signal intelligence module

**Files:**
- Create: `flatwhite/signals/signal_intelligence.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_signal_intelligence.py`:

```python
def test_run_signal_intelligence_skips_when_cold(si_db):
    """run_signal_intelligence should no-op when only 1 week of signal data exists."""
    with patch.object(db_module, "DB_PATH", si_db):
        # Only insert signals for current week — no previous week
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.2, 60.0, 1.0, "2026-W13")

        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
            from flatwhite.signals.signal_intelligence import run_signal_intelligence
            run_signal_intelligence()  # Should not raise, should not write anything

            conn = db_module.get_connection()
            rows = conn.execute("SELECT * FROM signal_intelligence").fetchall()
            conn.close()
            assert len(rows) == 0


def test_run_signal_intelligence_generates_for_movers(si_db):
    """run_signal_intelligence should generate commentary for signals with abs(delta) >= 5."""
    with patch.object(db_module, "DB_PATH", si_db):
        # Insert W12 and W13 signals — asx_volatility moves +8 pts
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.2, 52.0, 1.0, "2026-W12")
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.8, 60.0, 1.0, "2026-W13")
        # market_hiring moves only +2 pts — should be skipped
        db_module.insert_signal("market_hiring",  "pulse", "labour_market", 20000.0, 55.0, 1.0, "2026-W12")
        db_module.insert_signal("market_hiring",  "pulse", "labour_market", 20500.0, 57.0, 1.0, "2026-W13")

        mock_articles = [{"title": "ASX swings wildly", "url": "http://afr.com/asx", "published": "2026-03-20", "snippet": "Markets volatile"}]

        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
            with patch("flatwhite.signals.signal_intelligence._fetch_articles", return_value=mock_articles):
                with patch("flatwhite.model_router.route", return_value="ASX rose sharply this week due to global risk sentiment."):
                    from flatwhite.signals.signal_intelligence import run_signal_intelligence
                    run_signal_intelligence()

        conn = db_module.get_connection()
        rows = conn.execute("SELECT signal_name, commentary FROM signal_intelligence").fetchall()
        conn.close()

        signal_names = [r["signal_name"] for r in rows]
        assert "asx_volatility" in signal_names
        assert "market_hiring" not in signal_names  # delta < 5
        asx_row = next(r for r in rows if r["signal_name"] == "asx_volatility")
        assert "ASX" in asx_row["commentary"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_run_signal_intelligence_skips_when_cold tests/test_signal_intelligence.py::test_run_signal_intelligence_generates_for_movers -v
```

Expected: FAIL — `flatwhite.signals.signal_intelligence` does not exist

- [ ] **Step 3: Create flatwhite/signals/signal_intelligence.py**

```python
"""Signal intelligence: auto-fetch supporting news for significant WoW movers.

After the pulse scrape, for each signal where abs(WoW delta) >= DELTA_THRESHOLD,
queries Google News RSS, fetches top articles, and synthesises a short commentary
via Claude Haiku. Stored in the signal_intelligence table.
"""
from __future__ import annotations

import json
import time
from urllib.parse import quote

from flatwhite.db import get_connection, get_current_week_iso
from flatwhite.model_router import route
from flatwhite.utils.http import fetch_rss

DELTA_THRESHOLD = 5.0

_QUERY_TEMPLATES: dict[str, str] = {
    "asic_insolvency":      "Australian corporate insolvency administration {month} {year}",
    "market_hiring":        "Australian job market hiring white collar {month} {year}",
    "asx_volatility":       "ASX market volatility week {month} {year}",
    "asx_momentum":         "ASX market rally correction {month} {year}",
    "salary_pressure":      "Australian salary wages pressure {month} {year}",
    "consumer_confidence":  "Australian consumer confidence {month} {year}",
    "layoff_news_velocity": "Australian corporate layoffs redundancies {month} {year}",
    "news_velocity":        "Australian corporate layoffs redundancies {month} {year}",
    "indeed_hiring":        "Australian job listings Indeed hiring {month} {year}",
    "contractor_proxy":     "Australian contract work freelance market {month} {year}",
    "job_anxiety":          "Australian job anxiety employment stress {month} {year}",
    "career_mobility":      "Australian career change job switching {month} {year}",
    "auslaw_velocity":      "Australian employment law tribunal {month} {year}",
    "reddit_topic_velocity": "Australian corporate workplace {month} {year}",
}

_SYSTEM_PROMPT = (
    "You are a data analyst for Flat White, an Australian corporate market newsletter. "
    "Be specific, concise, and authoritative. Australian English."
)


def _fetch_articles(signal_name: str, month: str, year: str) -> list[dict]:
    """Fetch top 5 Google News articles for the signal's query template."""
    template = _QUERY_TEMPLATES.get(signal_name)
    if not template:
        return []
    query = template.format(month=month, year=year)
    encoded = quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
    try:
        entries = fetch_rss(url, delay_seconds=1.0)
        articles = []
        for e in entries[:5]:
            articles.append({
                "title":     e.get("title", ""),
                "url":       e.get("url", ""),
                "published": e.get("published", ""),
                "snippet":   (e.get("body") or "")[:200],
            })
        return articles
    except Exception as e:
        print(f"  signal_intelligence: article fetch failed for {signal_name}: {e}")
        return []


def _synthesise(signal_name: str, delta: float, articles: list[dict]) -> str:
    """Call Claude Haiku to write 2-3 sentences explaining the signal movement."""
    direction = "up" if delta > 0 else "down"
    articles_text = "\n".join(
        f"{i+1}. {a['title']} ({a['published'][:16]}) — {a['snippet']}"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Signal: {signal_name}\n"
        f"WoW delta: {delta:+.1f} points ({direction})\n\n"
        f"Supporting articles:\n{articles_text or '(no articles found)'}\n\n"
        "Write 2-3 sentences explaining what likely drove this movement and what it means "
        "for the Australian corporate market. Be specific. Cite article titles where relevant. "
        "Do not use bullet points."
    )
    return route("signal_intelligence", prompt, system=_SYSTEM_PROMPT)


def run_signal_intelligence() -> None:
    """Main entry point — called as a step in the pulse runner.

    Skips gracefully if fewer than 2 weeks of signal data exist.
    """
    import datetime as _dt

    week_iso = get_current_week_iso()
    year, wn = int(week_iso[:4]), int(week_iso[6:])
    dt = _dt.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u")
    prev_week = (dt - _dt.timedelta(weeks=1)).strftime("%G-W%V")
    month = dt.strftime("%B")  # e.g. "March"

    conn = get_connection()
    prev_rows = conn.execute(
        "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (prev_week,),
    ).fetchall()

    if not prev_rows:
        print("  signal_intelligence: no previous week data — skipping")
        conn.close()
        return

    curr_rows = conn.execute(
        "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (week_iso,),
    ).fetchall()
    conn.close()

    prev_map = {r["signal_name"]: r["normalised_score"] for r in prev_rows}
    curr_map = {r["signal_name"]: r["normalised_score"] for r in curr_rows}

    movers = []
    for name, score in curr_map.items():
        prev = prev_map.get(name)
        if prev is not None:
            delta = score - prev
            if abs(delta) >= DELTA_THRESHOLD:
                movers.append((name, delta))

    if not movers:
        print("  signal_intelligence: no significant movers this week (threshold: ±5pts)")
        return

    print(f"  signal_intelligence: processing {len(movers)} movers: {[m[0] for m in movers]}")

    for signal_name, delta in movers:
        articles = _fetch_articles(signal_name, month, str(year))
        time.sleep(1.0)  # be polite to Google News
        commentary = _synthesise(signal_name, delta, articles)

        conn = get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO signal_intelligence
               (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (signal_name, week_iso, round(delta, 1), json.dumps(articles), commentary),
        )
        conn.commit()
        conn.close()
        print(f"  signal_intelligence: {signal_name} ({delta:+.1f}) — commentary stored")
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flatwhite/signals/signal_intelligence.py tests/test_signal_intelligence.py
git commit -m "feat: signal intelligence module — auto-research significant WoW movers"
```

---

## Task 7: Signal intelligence — API endpoints

**Files:**
- Modify: `flatwhite/dashboard/api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signal_intelligence.py`:

```python
def test_api_get_signal_intelligence(si_db):
    """GET /api/signal-intelligence/{week_iso} should return records keyed by signal."""
    import json as _json
    with patch.object(db_module, "DB_PATH", si_db):
        conn = db_module.get_connection()
        articles = _json.dumps([{"title": "Test", "url": "http://x.com", "published": "2026-03-20", "snippet": "foo"}])
        conn.execute(
            """INSERT INTO signal_intelligence (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("asx_volatility", "2026-W13", 8.2, articles, "ASX rose sharply."),
        )
        conn.commit()
        conn.close()

        from flatwhite.dashboard.api import api_get_signal_intelligence
        result = api_get_signal_intelligence("2026-W13")
        data = _json.loads(result.body)
        assert "asx_volatility" in data
        assert data["asx_volatility"]["commentary"] == "ASX rose sharply."
        assert isinstance(data["asx_volatility"]["articles"], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_api_get_signal_intelligence -v
```

Expected: FAIL — `api_get_signal_intelligence` not defined

- [ ] **Step 3: Add endpoints to api.py**

Add after the `/api/run-log` endpoint:

```python
@app.get("/api/signal-intelligence/{week_iso}")
def api_get_signal_intelligence(week_iso: str) -> JSONResponse:
    """Return signal intelligence records for a week, keyed by signal_name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT signal_name, delta, articles, commentary, generated_at FROM signal_intelligence WHERE week_iso = ?",
        (week_iso,),
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        import json as _json
        result[r["signal_name"]] = {
            "delta":        r["delta"],
            "articles":     _json.loads(r["articles"]) if r["articles"] else [],
            "commentary":   r["commentary"],
            "generated_at": r["generated_at"],
        }
    return JSONResponse(result)


@app.post("/api/signal-intelligence/refresh")
async def api_refresh_signal_intelligence(request: Request) -> JSONResponse:
    """Re-run signal intelligence for a single signal/week pair.

    Body: {"signal_name": str, "week_iso": str}
    """
    body = await request.json()
    signal_name = body.get("signal_name", "")
    week_iso = body.get("week_iso", "")

    conn = get_connection()
    row = conn.execute(
        "SELECT delta FROM signal_intelligence WHERE signal_name = ? AND week_iso = ?",
        (signal_name, week_iso),
    ).fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": "No existing record to refresh"}, status_code=404)

    import threading
    def _refresh():
        from flatwhite.signals.signal_intelligence import _fetch_articles, _synthesise
        import datetime as _dt
        import json as _json
        year, wn = int(week_iso[:4]), int(week_iso[6:])
        dt = _dt.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u")
        month = dt.strftime("%B")
        delta = row["delta"]
        articles = _fetch_articles(signal_name, month, str(year))
        commentary = _synthesise(signal_name, delta, articles)
        c = get_connection()
        c.execute(
            """INSERT OR REPLACE INTO signal_intelligence
               (signal_name, week_iso, delta, articles, commentary, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (signal_name, week_iso, delta, _json.dumps(articles), commentary),
        )
        c.commit()
        c.close()

    threading.Thread(target=_refresh, daemon=True).start()
    return JSONResponse({"refreshing": True, "signal_name": signal_name, "week_iso": week_iso})
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_api_get_signal_intelligence -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat: signal intelligence API endpoints (GET + refresh)"
```

---

## Task 8: Signal intelligence — frontend evidence drawer

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add signalIntelligence to S state and load it on Pulse init**

In the S state initialisation block, add:
```js
signalIntelligence: {},   // { signal_name: {delta, articles, commentary} }
```

In `loadPageData` (find the `case "pulse":` block), add a call to load signal intelligence after loading trends:

```js
case "pulse":
  return Promise.all([
    /* existing calls */
    api("/api/signal-intelligence/" + (S.weekIso || getCurrentWeekIso())).then(function(d) { S.signalIntelligence = d || {}; }).catch(function() { S.signalIntelligence = {}; }),
  ]);
```

(Wrap the existing Promise.all to include this additional fetch — add it as an extra item.)

Add a small helper for the current week ISO (or reuse `S.weekIso`):
```js
function getCurrentWeekIso() {
  var d = new Date();
  var dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  var weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return d.getUTCFullYear() + "-W" + String(weekNo).padStart(2, "0");
}
```

- [ ] **Step 2: Add evidence column to the signal table**

In `renderPulse`, find:
```js
h += '<table class="tbl"><thead><tr><th style="width:30px;"></th><th>Signal</th><th>Score</th><th>Delta</th><th>Category</th></tr></thead><tbody>';
```
Replace with:
```js
h += '<table class="tbl"><thead><tr><th style="width:30px;"></th><th>Signal</th><th>Score</th><th>Delta</th><th>Category</th><th style="width:60px;">Evidence</th></tr></thead><tbody>';
```

In the signal row render, add an evidence cell after the category cell:

```js
var intel = S.signalIntelligence[name];
var evidenceBadge = intel
  ? '<span class="chip chip-default" style="cursor:pointer;font-size:10px;" onclick="toggleSignalIntel(\'' + esc(name) + '\')" title="' + esc(intel.commentary.slice(0, 80)) + '...">≡ evidence</span>'
  : '';
h += '<td>' + evidenceBadge + '</td>';
```

Add `toggleSignalIntel` state to S:
```js
signalIntelExpanded: {},   // { signal_name: bool }
```

Add the toggle function:
```js
function toggleSignalIntel(name) {
  S.signalIntelExpanded[name] = !S.signalIntelExpanded[name];
  render();
}
```

- [ ] **Step 3: Render evidence drawer below signal row**

After closing the signal row `</tr>`, conditionally render a drawer:

```js
if (S.signalIntelExpanded[name] && intel) {
  h += '<tr><td colspan="6" style="background:var(--bg-2);padding:12px 16px;">';
  h += '<div style="font-size:13px;line-height:1.6;color:var(--text-1);margin-bottom:10px;">' + esc(intel.commentary) + '</div>';
  if (intel.articles && intel.articles.length) {
    h += '<div style="font-size:11px;color:var(--text-3);margin-bottom:6px;">Sources:</div>';
    intel.articles.slice(0, 3).forEach(function(a) {
      h += '<div style="font-size:12px;margin-bottom:4px;">';
      h += '<a href="' + esc(a.url) + '" target="_blank" style="color:var(--amber);">' + esc(a.title) + '</a>';
      if (a.published) h += ' <span style="color:var(--text-3);">(' + esc(a.published.slice(0, 10)) + ')</span>';
      h += '</div>';
    });
  }
  h += '<button class="btn btn-secondary" style="font-size:10px;margin-top:8px;" onclick="refreshSignalIntel(\'' + esc(name) + '\')">Refresh evidence</button>';
  h += '</td></tr>';
}
```

Add `refreshSignalIntel` function:
```js
function refreshSignalIntel(name) {
  var weekIso = S.weekIso || getCurrentWeekIso();
  showToast("Refreshing evidence for " + name + "...");
  api("/api/signal-intelligence/refresh", { method: "POST", body: { signal_name: name, week_iso: weekIso } })
    .then(function() {
      setTimeout(function() {
        api("/api/signal-intelligence/" + weekIso).then(function(d) {
          S.signalIntelligence = d || {};
          render();
          showToast("Evidence refreshed for " + name);
        });
      }, 3000);
    })
    .catch(function(e) { showToast("Refresh failed: " + e.message, "error"); });
}
```

- [ ] **Step 4: Verify in browser**

Reload the dashboard. On Pulse page with signal intelligence data, the Evidence column should show "≡ evidence" badges. Clicking one should expand a drawer with commentary and article links.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: signal intelligence evidence drawer in Pulse signal table"
```

---

## Task 9: PROCEED modal — context_breakdown in /api/preview-prompt

**Files:**
- Modify: `flatwhite/dashboard/api.py`

The `/api/preview-prompt` endpoint currently returns `{"prompt": str, "section": str}`. Add a `context_breakdown` object so the frontend can render Panel 1 (Context) separately from the prompt text.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signal_intelligence.py`:

```python
def test_preview_prompt_returns_context_breakdown(si_db):
    """POST /api/preview-prompt for pulse should return context_breakdown."""
    import json as _json
    import asyncio
    with patch.object(db_module, "DB_PATH", si_db):
        db_module.insert_signal("asx_volatility", "pulse", "economic", 1.2, 60.0, 1.0, "2026-W13")

        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W13"):
            with patch("flatwhite.signals.macro_context.fetch_macro_headlines", return_value=""):
                with patch("flatwhite.db.get_interactions", return_value=[]):
                    from flatwhite.dashboard.api import api_preview_prompt

                    class FakeRequest:
                        async def json(self):
                            return {"section": "pulse", "data": {}}

                    result = asyncio.get_event_loop().run_until_complete(api_preview_prompt(FakeRequest()))
                    data = _json.loads(result.body)
                    assert "context_breakdown" in data
                    assert "signals" in data["context_breakdown"]
                    assert "signal_intelligence" in data["context_breakdown"]
                    assert "composite" in data["context_breakdown"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_preview_prompt_returns_context_breakdown -v
```

Expected: FAIL — `context_breakdown` not in response

- [ ] **Step 3: Update api_preview_prompt for pulse section**

In the `api_preview_prompt` function, after building `signal_lines` for the pulse section, add:

```python
            # Build context_breakdown for the frontend Context panel
            week_iso_for_intel = week_iso
            intel_conn = get_connection()
            intel_rows = intel_conn.execute(
                "SELECT signal_name, delta, commentary, articles FROM signal_intelligence WHERE week_iso = ?",
                (week_iso_for_intel,),
            ).fetchall()
            intel_conn.close()

            import json as _json_local
            signal_intelligence_breakdown = [
                {
                    "signal_name": r["signal_name"],
                    "delta": r["delta"],
                    "commentary": r["commentary"],
                    "articles": _json_local.loads(r["articles"]) if r["articles"] else [],
                }
                for r in intel_rows
            ]

            context_breakdown = {
                "signals": [
                    {
                        "name": s["signal_name"],
                        "score": round(s["normalised_score"], 1) if s.get("normalised_score") is not None else None,
                        "delta": moverDeltas_for_breakdown.get(s["signal_name"]),
                        "area": s.get("area", ""),
                    }
                    for s in signals
                    if s["signal_name"] in selected_signals
                ],
                "signal_intelligence": signal_intelligence_breakdown,
                "composite": {
                    "score": pulse.get("smoothed_score") if pulse else None,
                    "direction": pulse.get("direction") if pulse else None,
                } if pulse else {},
            }
```

Where `moverDeltas_for_breakdown` is built from `prev_map` (already computed in that function):

```python
            moverDeltas_for_breakdown = {
                name: round(score - prev_map[name], 1)
                for name, score in {s["signal_name"]: s["normalised_score"] for s in signals}.items()
                if name in prev_map
            }
```

Add this before the `context_breakdown` dict. Then change the final return for the pulse section from:

```python
        return JSONResponse({"prompt": prompt, "section": section})
```

To:
```python
        return JSONResponse({"prompt": prompt, "section": section, "context_breakdown": context_breakdown})
```

For non-pulse sections, add minimal breakdown. Change the final `else` return and other section returns:

For `lobby` section, just before its `return JSONResponse(...)`:
```python
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": line} for line in employer_lines],
            }
```
Then: `return JSONResponse({"prompt": prompt, "section": section, "context_breakdown": context_breakdown})`

For `finds` section:
```python
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": item.get("title", ""), "score": item.get("weighted_composite")} for item in items],
            }
```

For `off_the_clock` section:
```python
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": p.get("title", ""), "category": p.get("category", "")} for p in picks],
            }
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_signal_intelligence.py::test_preview_prompt_returns_context_breakdown -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat: add context_breakdown to /api/preview-prompt response"
```

---

## Task 10: PROCEED modal — three-panel frontend redesign

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

Replace the current single-pane PROCEED modal with a three-panel layout: Context | Prompt | Model.

- [ ] **Step 1: Add modal model state to S**

In the S state block, add:
```js
proceedModel: {},    // { section: model_id } — persisted to localStorage
```

On `init()`, load persisted model selections:
```js
try { S.proceedModel = JSON.parse(localStorage.getItem("fw_proceedModel") || "{}"); } catch(e) {}
```

- [ ] **Step 2: Update openProceedModal to fetch context_breakdown**

Replace the existing `openProceedModal` function:

```js
function openProceedModal(section, items) {
  S.proceedModal = {
    open: true, section: section, prompt: "", lean: "",
    items: items || [], loading: true,
    contextBreakdown: null, excludedItems: {}
  };
  render();
  api("/api/preview-prompt", { method: "POST", body: { section: section, data: S.proceedData[section] || {} } })
    .then(function(d) {
      S.proceedModal.prompt = d.prompt || "";
      S.proceedModal.contextBreakdown = d.context_breakdown || null;
      S.proceedModal.loading = false;
      render();
    })
    .catch(function() {
      S.proceedModal.prompt = "(Could not load prompt preview)";
      S.proceedModal.loading = false;
      render();
    });
}
```

- [ ] **Step 3: Update confirmAndGenerate to pass model and excluded items**

Replace `confirmAndGenerate`:

```js
function confirmAndGenerate() {
  var modal = S.proceedModal;
  var section = modal.section;
  var lean = modal.lean.trim();
  var customPrompt = lean ? lean + "\n\n" + modal.prompt : modal.prompt;
  var model = S.proceedModel[section] || null;
  S.proceedModal.open = false;
  S.loading[section] = true;
  render();
  var body = Object.assign({}, S.proceedData[section] || {}, {
    section: section,
    custom_prompt: customPrompt,
    model: model,
    excluded: Object.keys(modal.excludedItems).filter(function(k) { return modal.excludedItems[k]; }),
  });
  api("/api/proceed-section", { method: "POST", body: body })
    .then(function(d) {
      S.sectionOutputs[section] = { output_text: d.output, model_used: d.model };
      S.loading[section] = false;
      render();
      showToast(section.replace(/_/g, " ") + " generated" + (d.model ? " · " + d.model : ""));
    })
    .catch(function(e) { S.loading[section] = false; render(); showToast("Error: " + e.message, "error"); });
}
```

- [ ] **Step 4: Replace renderProceedModal with three-panel layout**

Replace the existing `renderProceedModal` function:

```js
function renderProceedModal() {
  if (!S.proceedModal.open) return "";
  var modal = S.proceedModal;
  var section = modal.section;
  var availableModels = S.models || [];

  var h = '<div class="modal-overlay" onclick="if(event.target===this)closeProceedModal()">';
  h += '<div class="modal-box" style="max-width:900px;width:95vw;max-height:90vh;overflow:hidden;display:flex;flex-direction:column;">';
  h += '<h3 style="margin-bottom:12px;">Generate ' + esc(section.replace(/_/g, " ")) + '</h3>';

  // Three-panel tabs
  h += '<div style="display:flex;gap:0;border-bottom:1px solid var(--divider);margin-bottom:16px;">';
  ['context','prompt','model'].forEach(function(tab) {
    var active = (S.proceedModal._tab || 'prompt') === tab;
    h += '<div onclick="S.proceedModal._tab=\'' + tab + '\';render()" style="padding:8px 20px;font-size:13px;cursor:pointer;border-bottom:2px solid ' + (active ? 'var(--amber)' : 'transparent') + ';color:' + (active ? 'var(--text-1)' : 'var(--text-3)') + ';">';
    h += tab === 'context' ? 'Context' : tab === 'prompt' ? 'Prompt' : 'Model';
    h += '</div>';
  });
  h += '</div>';

  var activeTab = S.proceedModal._tab || 'prompt';

  // ── Context panel ──
  if (activeTab === 'context') {
    if (modal.loading) {
      h += '<div class="loading" style="padding:20px;">Loading context...</div>';
    } else if (modal.contextBreakdown) {
      var cb = modal.contextBreakdown;
      h += '<div style="overflow-y:auto;max-height:50vh;font-size:13px;">';

      // Signals
      if (cb.signals && cb.signals.length) {
        h += '<div style="font-weight:600;margin-bottom:8px;">Signals</div>';
        h += '<table class="tbl" style="margin-bottom:16px;"><thead><tr><th></th><th>Signal</th><th>Score</th><th>WoW</th><th>Area</th></tr></thead><tbody>';
        cb.signals.forEach(function(sig) {
          var key = "sig_" + sig.name;
          var checked = !modal.excludedItems[key];
          var d = sig.delta;
          var dc = d == null ? "" : (d > 0 ? "color:var(--red)" : d < 0 ? "color:var(--green)" : "");
          h += '<tr>';
          h += '<td><input type="checkbox"' + (checked ? " checked" : "") + ' onchange="S.proceedModal.excludedItems[' + "'" + key + "'" + ']=!this.checked;render()"></td>';
          h += '<td>' + esc(sig.name) + '</td>';
          h += '<td>' + (sig.score != null ? sig.score.toFixed(1) : "—") + '</td>';
          h += '<td style="' + dc + '">' + (d != null ? (d > 0 ? "+" : "") + d.toFixed(1) : "—") + '</td>';
          h += '<td><span class="chip chip-default">' + esc(sig.area) + '</span></td>';
          h += '</tr>';
        });
        h += '</tbody></table>';
      }

      // Signal intelligence
      if (cb.signal_intelligence && cb.signal_intelligence.length) {
        h += '<div style="font-weight:600;margin-bottom:8px;">Signal Intelligence</div>';
        cb.signal_intelligence.forEach(function(si) {
          var key = "intel_" + si.signal_name;
          var checked = !modal.excludedItems[key];
          h += '<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:10px;">';
          h += '<input type="checkbox"' + (checked ? " checked" : "") + ' onchange="S.proceedModal.excludedItems[' + "'" + key + "'" + ']=!this.checked;render()" style="margin-top:3px;">';
          h += '<div>';
          h += '<div style="font-weight:600;font-size:12px;">' + esc(si.signal_name) + ' (' + (si.delta > 0 ? "+" : "") + si.delta.toFixed(1) + ' pts)</div>';
          h += '<div style="color:var(--text-2);">' + esc(si.commentary) + '</div>';
          if (si.articles && si.articles.length) {
            si.articles.slice(0, 2).forEach(function(a) {
              h += '<div style="font-size:11px;color:var(--text-3);">' + esc(a.title) + '</div>';
            });
          }
          h += '</div></div>';
        });
      }

      // Items (finds/lobby/OTC)
      if (cb.items && cb.items.length) {
        h += '<div style="font-weight:600;margin-bottom:8px;">Items</div>';
        cb.items.forEach(function(item, idx) {
          var key = "item_" + idx;
          var checked = !modal.excludedItems[key];
          h += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">';
          h += '<input type="checkbox"' + (checked ? " checked" : "") + ' onchange="S.proceedModal.excludedItems[' + "'" + key + "'" + ']=!this.checked;render()">';
          h += '<span style="font-size:13px;">' + esc(item.name || item.category || "") + '</span>';
          if (item.score != null) h += ' <span style="font-size:11px;color:var(--text-3);">(' + item.score.toFixed(1) + ')</span>';
          h += '</div>';
        });
      }

      h += '</div>';
    } else {
      h += '<div style="color:var(--text-3);padding:20px 0;">No context breakdown available for this section.</div>';
    }
  }

  // ── Prompt panel ──
  if (activeTab === 'prompt') {
    h += '<div style="margin-bottom:8px;font-size:12px;color:var(--text-3);">Editorial lean (prepended to prompt)</div>';
    h += '<input class="form-input" style="margin-bottom:12px;" placeholder="e.g. Focus on Big 4 this week..." value="' + esc(modal.lean) + '" oninput="S.proceedModal.lean=this.value">';
    if (modal.loading) {
      h += '<div class="loading" style="padding:20px 0;">Loading prompt...</div>';
    } else {
      h += '<textarea class="form-input" rows="16" style="font-family:monospace;font-size:12px;" oninput="S.proceedModal.prompt=this.value">' + esc(modal.prompt) + '</textarea>';
    }
  }

  // ── Model panel ──
  if (activeTab === 'model') {
    var currentModel = S.proceedModel[section] || (availableModels.length ? availableModels[0].id : "");
    h += '<div style="font-size:13px;color:var(--text-2);margin-bottom:16px;">Select the model for this section\'s generation. Only models with a configured API key are shown.</div>';

    var byProvider = {};
    var providerOrder = [];
    availableModels.forEach(function(m) {
      if (!byProvider[m.provider]) { byProvider[m.provider] = []; providerOrder.push(m.provider); }
      byProvider[m.provider].push(m);
    });

    var providerLabels = { anthropic: "Anthropic", openai: "OpenAI", gemini: "Google" };
    providerOrder.forEach(function(prov) {
      h += '<div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;margin-top:12px;">' + (providerLabels[prov] || prov) + '</div>';
      byProvider[prov].forEach(function(m) {
        var active = m.id === currentModel;
        h += '<div onclick="S.proceedModel[\'' + section + '\']=\'' + m.id + '\';try{localStorage.setItem(\'fw_proceedModel\',JSON.stringify(S.proceedModel));}catch(e){}render()" ';
        h += 'style="padding:10px 14px;border-radius:6px;cursor:pointer;background:' + (active ? 'var(--amber-soft, rgba(255,180,0,0.12))' : 'transparent') + ';border:1px solid ' + (active ? 'var(--amber)' : 'var(--divider)') + ';margin-bottom:6px;display:flex;align-items:center;gap:10px;">';
        h += '<div style="width:10px;height:10px;border-radius:50%;background:' + (active ? 'var(--amber)' : 'var(--divider)') + ';flex-shrink:0;"></div>';
        h += '<div><div style="font-size:13px;font-weight:' + (active ? '600' : '400') + ';">' + esc(m.label) + '</div>';
        h += '<div style="font-size:11px;color:var(--text-3);">' + esc(m.id) + '</div></div>';
        h += '</div>';
      });
    });
  }

  h += '<div class="modal-footer" style="margin-top:16px;">';
  h += '<button class="btn btn-secondary" onclick="closeProceedModal()">Cancel</button>';
  h += '<button class="btn btn-success" onclick="confirmAndGenerate()" ' + (modal.loading ? 'disabled' : '') + '>Confirm & Generate</button>';
  h += '</div></div></div>';
  return h;
}
```

- [ ] **Step 5: Verify in browser**

Open any section's PROCEED. Modal should show three tabs: Context / Prompt / Model. Context tab should list signals with checkboxes. Model tab should show all available models grouped by provider. Confirm & Generate should work with the selected model.

- [ ] **Step 6: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: three-panel PROCEED modal with context breakdown and multi-LLM model picker"
```

---

## Self-Review

### Spec Coverage Check

| Spec requirement | Task |
|-----------------|------|
| Step-level progress bar (3/9 · Step name) | Tasks 3, 4 |
| `_SECTION_RUNNERS` as step lists | Task 3 |
| `/api/section-status` returns step/total/step_name | Task 3 |
| `renderSectionProgress()` replaces spinner | Task 4 |
| WoW backfill — signal runners (ASX, ASIC) | Existing `run_backfill()` covers ASX; Task 5 exposes it |
| WoW backfill — employer snapshot seed | Task 5 |
| `/api/backfill` endpoint | Task 5 |
| Cold-start "first week" UX | Task 5 |
| JS composite delta bugfix `.value` → `.score` | Task 5 |
| `signal_intelligence` DB table | Task 2 |
| `run_signal_intelligence()` module | Task 6 |
| Google News RSS query per signal | Task 6 |
| Claude Haiku synthesis per mover | Task 6 |
| `/api/signal-intelligence/{week_iso}` | Task 7 |
| `/api/signal-intelligence/refresh` | Task 7 |
| Evidence column + drawer in Pulse table | Task 8 |
| Signal intelligence injected into PROCEED | Task 9 (context_breakdown) |
| OpenAI GPT-5.4 family in model registry | Task 1 |
| `claude-opus-4-6` in model registry | Task 1 |
| `_call_openai()` | Task 1 |
| Duplicate `/api/lobby` route removed | Task 1 |
| `context_breakdown` in `/api/preview-prompt` | Task 9 |
| Three-panel PROCEED modal | Task 10 |
| Model picker in modal (grouped by provider) | Task 10 |
| Excludable context items | Task 10 |
| Model persisted to localStorage | Task 10 |

All spec requirements covered. ✓

### Type Consistency
- `_SECTION_RUNNERS` values are `list[tuple[str, Callable]]` in Task 3; `_run_section_background` iterates with `for i, (label, fn) in enumerate(steps)` ✓
- `signal_intelligence` table uses `INSERT OR REPLACE` in Task 6 and Task 7 ✓
- `context_breakdown.signals[].delta` is `float | None` in Task 9, accessed as `sig.delta` in Task 10 ✓
- `S.proceedModel[section]` is `str` (model_id), passed as `model` in `confirmAndGenerate` body ✓
- `_fetch_articles` signature `(signal_name, month, year) -> list[dict]` used consistently in Tasks 6 and 7 ✓
