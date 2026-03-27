# Dashboard Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AU relevance scoring to classification, Pulse WoW delta visibility, Lobby trend analysis, OTC item selection, and a universal SCRAPE/PROCEED prompt review modal across the dashboard.

**Architecture:** Backend-first: DB migration → classifier → state/summary → API endpoints → frontend. All frontend changes are in a single `index.html` file. The PROCEED modal is a shared client-side component; each section's proceed function populates `S.proceedData[section]` then opens the modal, which fetches the rendered prompt from `/api/preview-prompt` and lets the user edit before firing.

**Tech Stack:** Python 3.12, FastAPI, SQLite (via `flatwhite.db`), vanilla JS (no new frontend deps), inline SVG for sparklines, pytest with `temp_db`/`populated_db`/`mock_gemini` fixtures in `tests/conftest.py`.

---

## File Map

| File | Change |
|------|--------|
| `flatwhite/db.py` | Add `au_relevance` migration to `migrate_db()` |
| `flatwhite/classify/prompts.py` | Add `au_relevance` field to `CLASSIFICATION_PROMPT` and `BATCH_CLASSIFICATION_PROMPT` |
| `flatwhite/classify/classifier.py` | Extract `au_relevance` in `_validate_single_result()`, store in `classify_all_unclassified()` INSERT |
| `flatwhite/dashboard/state.py` | Extend `load_signal_trends()` to return all-signal deltas; extend `load_otc_candidates()` to return all items (no cap) |
| `flatwhite/pulse/summary.py` | `generate_driver_bullets()` and `generate_pulse_summary()` include per-signal WoW delta |
| `flatwhite/classify/prompts.py` | Update `DRIVER_BULLETS_PROMPT` and `PULSE_SUMMARY_PROMPT` to use delta-formatted signal data |
| `flatwhite/dashboard/api.py` | `/api/lobby` returns 8-week history; new `GET /api/preview-prompt`; `/api/proceed-section` accepts `custom_prompt`; `_proceed_*` functions refactored to expose preview |
| `flatwhite/dashboard/static/index.html` | RUN→SCRAPE; PROCEED modal; Pulse category trend cards + sparklines; OTC multi-select; Finds AU badges + re-rank; Lobby WoW/MoM/sparkline columns |
| `tests/test_classify.py` | Add `au_relevance` assertions |
| `tests/test_pulse.py` | Add WoW delta assertions for `load_signal_trends()` |
| `tests/test_lobby.py` | New — test 8-week employer history + MoM delta |

---

## Task 1: DB Migration — add `au_relevance` column

**Files:**
- Modify: `flatwhite/db.py` (in `migrate_db()`, `simple_migrations` list)
- Test: `tests/test_classify.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_classify.py`:

```python
def test_au_relevance_column_exists(temp_db):
    """curated_items must have an au_relevance column after migration."""
    import flatwhite.db as db_module
    with patch.object(db_module, "DB_PATH", temp_db):
        import sqlite3
        conn = sqlite3.connect(temp_db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(curated_items)").fetchall()}
        conn.close()
        assert "au_relevance" in cols
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/pytest tests/test_classify.py::test_au_relevance_column_exists -v
```
Expected: FAIL — `assert "au_relevance" in cols`

- [ ] **Step 3: Add migration**

In `flatwhite/db.py`, inside `migrate_db()`, add to `simple_migrations`:

```python
simple_migrations = [
    "ALTER TABLE raw_items ADD COLUMN top_comments TEXT",
    "ALTER TABLE curated_items ADD COLUMN our_take TEXT",
    "ALTER TABLE raw_items ADD COLUMN post_score INTEGER",
    "ALTER TABLE raw_items ADD COLUMN comment_engagement INTEGER",
    "ALTER TABLE raw_items ADD COLUMN lifestyle_category TEXT",
    "ALTER TABLE curated_items ADD COLUMN au_relevance INTEGER",  # ← add this
]
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv/bin/pytest tests/test_classify.py::test_au_relevance_column_exists -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flatwhite/db.py tests/test_classify.py
git commit -m "feat: add au_relevance column to curated_items"
```

---

## Task 2: Classifier — add `au_relevance` to prompts and storage

**Files:**
- Modify: `flatwhite/classify/prompts.py`
- Modify: `flatwhite/classify/classifier.py`
- Test: `tests/test_classify.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_classify.py`:

```python
def test_classify_stores_au_relevance(populated_db, mock_gemini):
    """classify_all_unclassified should store au_relevance from the LLM response."""
    mock_gemini.return_value = json.dumps({
        "section": "finds",
        "relevance": 4,
        "novelty": 3,
        "reliability": 4,
        "tension": 3,
        "usefulness": 4,
        "summary": "A useful tool for corporate professionals.",
        "tags": ["tools"],
        "confidence_tag": None,
        "au_relevance": 8,
    })

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_all_unclassified
        from flatwhite.db import get_connection
        classify_all_unclassified()
        conn = get_connection()
        row = conn.execute(
            "SELECT au_relevance FROM curated_items LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 8


def test_classify_au_relevance_clamped(populated_db, mock_gemini):
    """au_relevance out of 0-10 range is clamped."""
    mock_gemini.return_value = json.dumps({
        "section": "finds",
        "relevance": 4, "novelty": 3, "reliability": 4, "tension": 3, "usefulness": 4,
        "summary": "A tool.", "tags": [], "confidence_tag": None,
        "au_relevance": 99,
    })

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_all_unclassified
        from flatwhite.db import get_connection
        classify_all_unclassified()
        conn = get_connection()
        row = conn.execute("SELECT au_relevance FROM curated_items LIMIT 1").fetchone()
        conn.close()
        assert row[0] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/pytest tests/test_classify.py::test_classify_stores_au_relevance tests/test_classify.py::test_classify_au_relevance_clamped -v
```
Expected: FAIL

- [ ] **Step 3: Update `CLASSIFICATION_PROMPT` in `flatwhite/classify/prompts.py`**

Replace the output keys line (near line 171):
```python
# Old:
"Output as a single JSON object with these exact keys:\n"
"section, relevance, novelty, reliability, tension, usefulness, confidence_tag, summary, tags\n"

# New:
"AU RELEVANCE (au_relevance 0-10): How directly relevant is this to Australian workers, "
"businesses, or markets? 0 = purely international with no Australian angle. "
"10 = specifically Australian. Global stories with direct AU market impact "
"(e.g. US tariffs affecting AU exports, global tech layoffs hitting AU offices) score 5-7. "
"US earnings, US politics, UK/EU news with no AU angle score 0-2.\n"
"\n"
"Output as a single JSON object with these exact keys:\n"
"section, relevance, novelty, reliability, tension, usefulness, confidence_tag, summary, tags, au_relevance\n"
```

Also update `BATCH_CLASSIFICATION_PROMPT` in `classifier.py` (the `Each object must have these exact keys:` line near line 168):
```python
# Old:
"Each object must have these exact keys:\n"
"section, relevance, novelty, reliability, tension, usefulness, confidence_tag, summary, tags\n"

# New:
"Each object must have these exact keys:\n"
"section, relevance, novelty, reliability, tension, usefulness, confidence_tag, summary, tags, au_relevance\n"
"\n"
"au_relevance (0-10): How directly relevant to Australian workers, businesses, or markets? "
"0 = purely international, 10 = specifically Australian.\n"
```

- [ ] **Step 4: Add `au_relevance` extraction in `_validate_single_result()` in `flatwhite/classify/classifier.py`**

After the tags validation block (after line 225), add:

```python
    # Validate au_relevance — integer 0-10, default 5 if missing
    au_rel = result.get("au_relevance", 5)
    if not isinstance(au_rel, (int, float)):
        au_rel = 5
    result["au_relevance"] = max(0, min(10, int(au_rel)))
```

Also add the same block to `classify_single_item()` after its tags validation (after line 119):

```python
    # Validate au_relevance
    au_rel = result.get("au_relevance", 5)
    if not isinstance(au_rel, (int, float)):
        au_rel = 5
    result["au_relevance"] = max(0, min(10, int(au_rel)))
```

- [ ] **Step 5: Update the INSERT in `classify_all_unclassified()` in `flatwhite/classify/classifier.py`**

Replace the INSERT (around line 394):

```python
        # Old INSERT:
        conn.execute(
            """INSERT INTO curated_items
            (raw_item_id, section, summary, score_relevance, score_novelty,
             score_reliability, score_tension, score_usefulness, weighted_composite,
             tags, confidence_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_dict["id"],
                result["section"],
                result["summary"],
                result["relevance"],
                result["novelty"],
                result["reliability"],
                result["tension"],
                result["usefulness"],
                result["weighted_composite"],
                json.dumps(result["tags"]),
                result["confidence_tag"],
            ),
        )

        # New INSERT:
        conn.execute(
            """INSERT INTO curated_items
            (raw_item_id, section, summary, score_relevance, score_novelty,
             score_reliability, score_tension, score_usefulness, weighted_composite,
             tags, confidence_tag, au_relevance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_dict["id"],
                result["section"],
                result["summary"],
                result["relevance"],
                result["novelty"],
                result["reliability"],
                result["tension"],
                result["usefulness"],
                result["weighted_composite"],
                json.dumps(result["tags"]),
                result["confidence_tag"],
                result.get("au_relevance", 5),
            ),
        )
```

- [ ] **Step 6: Update `load_curated_items_by_section()` in `flatwhite/dashboard/state.py` to include `au_relevance`**

In the SELECT query (around line 311), add `ci.au_relevance` to the SELECT list:

```python
        SELECT
            ci.id, ci.raw_item_id, ci.section, ci.summary,
            ci.score_relevance, ci.score_novelty, ci.score_reliability,
            ci.score_tension, ci.score_usefulness,
            ci.weighted_composite, ci.tags, ci.confidence_tag, ci.created_at,
            ci.au_relevance,
            ri.title, ri.body, ri.source, ri.url, ri.subreddit,
            ed.decision, ed.id AS decision_id
```

- [ ] **Step 7: Run tests to verify they pass**

```
.venv/bin/pytest tests/test_classify.py -v
```
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add flatwhite/classify/prompts.py flatwhite/classify/classifier.py flatwhite/dashboard/state.py tests/test_classify.py
git commit -m "feat: add au_relevance scoring to classification pipeline"
```

---

## Task 3: Pulse — extend `load_signal_trends()` to return all-signal WoW deltas

**Files:**
- Modify: `flatwhite/dashboard/state.py` (`load_signal_trends()`)
- Test: `tests/test_pulse.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pulse.py`:

```python
def test_load_signal_trends_returns_all_signal_deltas(populated_db):
    """load_signal_trends should return WoW deltas for all signals, not just top 5."""
    import datetime
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.db import insert_signal

        # Insert signals for a second (previous) week
        week_iso = "2026-W11"
        test_signals = [
            ("job_anxiety", "pulse", "labour_market", 60.0, 70.0, 1.0),
            ("career_mobility", "pulse", "labour_market", 55.0, 40.0, 1.0),
            ("market_hiring", "pulse", "labour_market", 20000.0, 30.0, 1.0),
            ("employer_hiring_breadth", "pulse", "labour_market", 9000.0, 55.0, 1.0),
            ("salary_pressure", "pulse", "labour_market", 115000.0, 60.0, 1.0),
            ("layoff_news_velocity", "pulse", "corporate_stress", 64.0, 50.0, 1.0),
            ("contractor_proxy", "pulse", "corporate_stress", 10.0, 45.0, 1.0),
            ("consumer_confidence", "pulse", "economic", 82.0, 75.0, 1.0),
            ("asx_volatility", "pulse", "economic", 1.2, 50.0, 1.0),
            ("asx_momentum", "pulse", "economic", 2.5, 55.0, 1.0),
        ]
        for name, lane, area, raw, norm, sw in test_signals:
            insert_signal(name, lane, area, raw, norm, sw, week_iso)

        from flatwhite.dashboard.state import load_signal_trends
        result = load_signal_trends(n_weeks=6)

        # all_signal_deltas should have an entry for every signal in current week
        all_deltas = result.get("all_signal_deltas", {})
        assert "consumer_confidence" in all_deltas
        assert "job_anxiety" in all_deltas
        # consumer_confidence: current=57.0, prev=75.0 → delta=-18.0
        assert all_deltas["consumer_confidence"]["delta"] == pytest.approx(-18.0, abs=0.5)
        # Must return more than 5 signals (not just biggest_movers)
        assert len(all_deltas) >= 8
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/bin/pytest tests/test_pulse.py::test_load_signal_trends_returns_all_signal_deltas -v
```
Expected: FAIL — `all_signal_deltas` key missing

- [ ] **Step 3: Extend `load_signal_trends()` in `flatwhite/dashboard/state.py`**

After the `biggest_movers` computation (after line 125), add computation of `all_signal_deltas` and return it. Replace the return dict:

```python
    # All-signal deltas (not just top 5) — keyed by signal_name
    all_signal_deltas: dict[str, dict] = {}
    if prev_week:
        prev_map_all = {s["signal_name"]: s for s in by_week[prev_week]}
        for name, curr in {s["signal_name"]: s for s in by_week[current_week]}.items():
            prev = prev_map_all.get(name)
            delta = round(curr["normalised_score"] - prev["normalised_score"], 1) if prev else None
            all_signal_deltas[name] = {
                "score": round(curr["normalised_score"], 1),
                "prev_score": round(prev["normalised_score"], 1) if prev else None,
                "delta": delta,
                "area": curr["area"],
                "source_weight": curr["source_weight"],
            }

    return {
        "categories": categories,
        "biggest_movers": biggest_movers,
        "all_signal_deltas": all_signal_deltas,
        "composite_history": composite_history,
        "weeks_available": len(weeks_with_data),
    }
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv/bin/pytest tests/test_pulse.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/state.py tests/test_pulse.py
git commit -m "feat: return all-signal WoW deltas from load_signal_trends"
```

---

## Task 4: Pulse prompts — include WoW delta in driver bullets and summary

**Files:**
- Modify: `flatwhite/classify/prompts.py` (`DRIVER_BULLETS_PROMPT`, `DRIVER_BULLETS_SYSTEM`, `PULSE_SUMMARY_PROMPT`)
- Modify: `flatwhite/pulse/summary.py` (`generate_driver_bullets()`, `generate_pulse_summary()`)
- Test: `tests/test_pulse.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pulse.py`:

```python
def test_driver_bullets_prompt_includes_wow_delta(populated_db, mock_gemini):
    """generate_driver_bullets should pass WoW delta data to the LLM prompt."""
    import datetime
    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.db import insert_signal

        # Insert prev week signals so delta can be computed
        for name, lane, area, raw, norm, sw in [
            ("consumer_confidence", "pulse", "economic", 82.0, 75.0, 1.0),
            ("job_anxiety", "pulse", "labour_market", 60.0, 70.0, 1.0),
        ]:
            insert_signal(name, lane, area, raw, norm, sw, "2026-W11")

        mock_gemini.return_value = json.dumps([
            {"signal": "consumer_confidence", "direction": "down", "bullet": "Consumer confidence dropped sharply"},
            {"signal": "job_anxiety", "direction": "up", "bullet": "Job anxiety rising"},
            {"signal": "asx_momentum", "direction": "up", "bullet": "ASX holding firm"},
        ])

        from flatwhite.pulse.summary import generate_driver_bullets
        bullets = generate_driver_bullets()

        assert len(bullets) == 3
        # Verify the prompt passed to the LLM included delta info
        call_args = mock_gemini.call_args
        prompt_used = call_args[1].get("prompt", "") or call_args[0][0] if call_args[0] else ""
        assert "prev:" in prompt_used or "Δ:" in prompt_used or "delta" in prompt_used.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/bin/pytest tests/test_pulse.py::test_driver_bullets_prompt_includes_wow_delta -v
```
Expected: FAIL

- [ ] **Step 3: Update `generate_driver_bullets()` in `flatwhite/pulse/summary.py`**

Replace the signals query and prompt building (lines 114–138):

```python
def generate_driver_bullets() -> list[dict]:
    week_iso = get_current_week_iso()
    conn = get_connection()

    # Current week signals
    signals = conn.execute(
        "SELECT signal_name, normalised_score, raw_value, source_weight FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (week_iso,),
    ).fetchall()

    # Previous week signals for WoW delta
    import datetime
    year, wn = int(week_iso[:4]), int(week_iso[6:])
    dt = datetime.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u")
    prev_week_iso = (dt - datetime.timedelta(weeks=1)).strftime("%G-W%V")
    prev_signals = conn.execute(
        "SELECT signal_name, normalised_score, source_weight FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (prev_week_iso,),
    ).fetchall()
    conn.close()

    if not signals:
        return [{"signal": "no_data", "direction": "stable", "bullet": "No signal data available this week"}]

    prev_map = {s["signal_name"]: s["normalised_score"] for s in prev_signals}

    signals_data = []
    for s in signals:
        name = s["signal_name"]
        score = s["normalised_score"]
        prev = prev_map.get(name)
        delta = round(score - prev, 1) if prev is not None else None
        fallback = "[FALLBACK — data may be stale]" if s["source_weight"] < 1.0 else ""
        entry = {
            "signal": name,
            "score": round(score, 1),
            "prev_score": round(prev, 1) if prev is not None else None,
            "delta": delta,
        }
        if fallback:
            entry["note"] = fallback
        signals_data.append(entry)

    # ... rest of function unchanged (interactions_block, route call, etc.)
```

- [ ] **Step 4: Update `DRIVER_BULLETS_PROMPT` in `flatwhite/classify/prompts.py`**

Replace the prompt (around line 377):

```python
DRIVER_BULLETS_PROMPT = (
    "Given these Pulse signal scores for the week (score = current, prev_score = last week, delta = change):\n"
    "\n"
    "{signals_json}\n"
    "{interactions_block}"
    "\n"
    "Identify the top 3 signals that are most noteworthy this week — prioritise signals with "
    "large absolute deltas (|delta| > 10 is significant), and signals far from the neutral "
    "baseline of 50. A signal that barely moved this week is less interesting than one that "
    "dropped 18 points. If consumer_confidence, salary_pressure, or job_anxiety have large "
    "deltas, they MUST be included.\n"
    "For each, write a short bullet point (max 15 words) describing the movement and what it means.\n"
    "If signal interactions were detected, use them to add context.\n"
    "\n"
    "Output as a JSON array of 3 objects, each with keys: signal, direction, bullet\n"
    "where direction is 'up' or 'down'\n"
    "\n"
    "Output ONLY the JSON array. Nothing else."
)
```

- [ ] **Step 5: Update `generate_pulse_summary()` in `flatwhite/pulse/summary.py` to include delta-formatted drivers**

In `generate_pulse_summary()`, replace the `drivers` line in the prompt format call. Currently it uses `current["drivers_json"]` — update to also query and attach per-signal deltas. Add after the `macro_context` fetch:

```python
    # Build delta-annotated signal context for the summary prompt
    conn = get_connection()
    curr_signals = conn.execute(
        "SELECT signal_name, normalised_score, source_weight FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (week_iso,),
    ).fetchall()
    import datetime as _dt
    year_s, wn_s = int(week_iso[:4]), int(week_iso[6:])
    dt_s = _dt.datetime.strptime(f"{year_s}-W{wn_s:02d}-1", "%G-W%V-%u")
    prev_wk = (dt_s - _dt.timedelta(weeks=1)).strftime("%G-W%V")
    prev_signals_rows = conn.execute(
        "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (prev_wk,),
    ).fetchall()
    conn.close()
    prev_sig_map = {s["signal_name"]: s["normalised_score"] for s in prev_signals_rows}
    signal_lines = []
    for s in curr_signals:
        name = s["signal_name"]
        score = round(s["normalised_score"], 1)
        prev = prev_sig_map.get(name)
        if prev is not None:
            delta = round(score - prev, 1)
            flag = " [FALLBACK]" if s["source_weight"] < 1.0 else ""
            signal_lines.append(f"{name}: {score} (prev: {round(prev,1)}, Δ: {delta:+.1f}){flag}")
        else:
            signal_lines.append(f"{name}: {score}")
    drivers_with_delta = "\n".join(signal_lines)
```

Then update the `prompt = PULSE_SUMMARY_PROMPT.format(...)` call to pass `drivers=drivers_with_delta` instead of `drivers=current["drivers_json"]`.

- [ ] **Step 6: Run tests to verify they pass**

```
.venv/bin/pytest tests/test_pulse.py -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add flatwhite/classify/prompts.py flatwhite/pulse/summary.py tests/test_pulse.py
git commit -m "feat: include WoW signal deltas in Pulse summary and driver prompts"
```

---

## Task 5: Lobby API — 8-week history, MoM delta, sparkline data

**Files:**
- Modify: `flatwhite/dashboard/api.py` (`api_lobby()`, `_proceed_lobby()`)
- Create: `tests/test_lobby.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lobby.py`:

```python
"""Tests for the Lobby employer trend data."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def lobby_db(tmp_path: Path) -> Path:
    """DB with employer snapshots across 8 weeks for trend testing."""
    db_path = tmp_path / "lobby_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import sqlite3
        conn = sqlite3.connect(db_path)
        # Insert employer
        conn.execute(
            """INSERT INTO employer_watchlist (employer_name, sector, careers_url)
            VALUES ('Deloitte Australia', 'big4', 'https://seek.com.au/deloitte')"""
        )
        emp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Insert 8 weeks of snapshots: role counts 100,105,110,108,112,115,118,120
        import datetime
        week = datetime.datetime.strptime("2026-W05-1", "%G-W%V-%u")
        counts = [100, 105, 110, 108, 112, 115, 118, 120]
        for i, count in enumerate(counts):
            w_iso = (week + datetime.timedelta(weeks=i)).strftime("%G-W%V")
            conn.execute(
                """INSERT INTO employer_snapshots (employer_id, open_roles_count, snapshot_date, week_iso)
                VALUES (?, ?, date('now'), ?)""",
                (emp_id, count, w_iso),
            )
        conn.commit()
        conn.close()
        yield db_path


def test_lobby_returns_mom_delta(lobby_db):
    """api_lobby should return mom_delta (current - 4 weeks ago)."""
    with patch.object(db_module, "DB_PATH", lobby_db):
        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W12"):
            from flatwhite.dashboard.api import api_lobby
            import asyncio
            result = api_lobby()
            data = result.body
            import json
            d = json.loads(data)
            emp = d["employers"][0]
            # current=120, 4wk ago=112 → mom_delta=+8
            assert emp["mom_delta"] == 8


def test_lobby_returns_history_array(lobby_db):
    """api_lobby employer objects should include a history array of last 6 week counts."""
    with patch.object(db_module, "DB_PATH", lobby_db):
        with patch("flatwhite.db.get_current_week_iso", return_value="2026-W12"):
            from flatwhite.dashboard.api import api_lobby
            import json
            result = api_lobby()
            d = json.loads(result.body)
            emp = d["employers"][0]
            assert "history" in emp
            assert len(emp["history"]) == 6
            assert emp["history"][-1] == 120  # most recent
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/pytest tests/test_lobby.py -v
```
Expected: FAIL — `mom_delta` and `history` keys missing

- [ ] **Step 3: Extend `api_lobby()` in `flatwhite/dashboard/api.py`**

Replace the entire `api_lobby()` function:

```python
@app.get("/api/lobby")
def api_lobby() -> JSONResponse:
    """Return employer hiring data with 8-week trend history."""
    import datetime as _dt
    conn = get_connection()
    week_iso = get_current_week_iso()

    # Build last 8 ISO weeks (oldest first, current last)
    year, week_num = int(week_iso[:4]), int(week_iso[6:])
    dt = _dt.datetime.strptime(f"{year}-W{week_num:02d}-1", "%G-W%V-%u")
    week_isos = [(dt - _dt.timedelta(weeks=i)).strftime("%G-W%V") for i in range(7, -1, -1)]
    # week_isos[0] = 8 weeks ago, week_isos[-1] = current
    prev_week = week_isos[-2]
    month_ago_week = week_isos[-5]  # ~4 weeks ago

    placeholders = ",".join("?" for _ in week_isos)
    all_snaps = conn.execute(
        f"""SELECT es.employer_id, es.open_roles_count, es.week_iso,
                   ew.employer_name, ew.sector
            FROM employer_snapshots es
            JOIN employer_watchlist ew ON es.employer_id = ew.id
            WHERE es.week_iso IN ({placeholders})
            ORDER BY ew.employer_name, es.week_iso""",
        week_isos,
    ).fetchall()
    conn.close()

    # Group by employer
    from collections import defaultdict
    snap_by_emp: dict[int, dict] = defaultdict(lambda: {"name": "", "sector": "", "weeks": {}})
    for r in all_snaps:
        e = snap_by_emp[r["employer_id"]]
        e["name"] = r["employer_name"]
        e["sector"] = r["sector"]
        e["weeks"][r["week_iso"]] = r["open_roles_count"]

    employers = []
    for emp_id, emp in snap_by_emp.items():
        weeks = emp["weeks"]
        current_count = weeks.get(week_iso)
        if current_count is None:
            continue  # No data this week — skip

        prev_count = weeks.get(prev_week)
        month_ago_count = weeks.get(month_ago_week)

        wow_delta = current_count - prev_count if prev_count is not None else None
        mom_delta = current_count - month_ago_count if month_ago_count is not None else None
        wow_pct = round(wow_delta / prev_count * 100, 1) if prev_count and wow_delta is not None else None

        # History: last 6 weeks of counts (oldest first), None-filled if missing
        history_weeks = week_isos[-6:]
        history = [weeks.get(w) for w in history_weeks]

        employers.append({
            "employer_id": emp_id,
            "employer_name": emp["name"],
            "sector": emp["sector"],
            "open_roles_count": current_count,
            "prev_roles": prev_count,
            "delta": wow_delta,
            "delta_pct": wow_pct,
            "mom_delta": mom_delta,
            "history": history,
        })

    employers.sort(key=lambda e: e["employer_name"])

    movers = sorted(
        [e for e in employers if e["delta"] is not None],
        key=lambda x: abs(x["delta"]),
        reverse=True,
    )

    return JSONResponse({
        "employers": employers,
        "top_movers": movers[:10],
        "week_iso": week_iso,
    })
```

- [ ] **Step 4: Update `_proceed_lobby()` to include trend narrative**

Replace `_proceed_lobby()` in `flatwhite/dashboard/api.py`:

```python
def _proceed_lobby(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE, model_override=model)

    selected = data.get("selected_employers", [])
    employer_lines = []
    for e in selected:
        name = e.get("employer_name", str(e)) if isinstance(e, dict) else str(e)
        if isinstance(e, dict):
            current = e.get("open_roles_count", "?")
            wow = e.get("delta")
            mom = e.get("mom_delta")
            wow_str = f"+{wow}" if wow and wow > 0 else str(wow) if wow is not None else "—"
            mom_str = f"+{mom}" if mom and mom > 0 else str(mom) if mom is not None else "—"
            employer_lines.append(f"- {name}: {current} roles (WoW: {wow_str}, MoM: {mom_str})")
        else:
            employer_lines.append(f"- {name}")

    employer_block = "\n".join(employer_lines) if employer_lines else "No employers selected."

    prompt = (
        "Write The Lobby section for this week's Flat White newsletter.\n\n"
        f"Employer hiring movements this week:\n{employer_block}\n\n"
        "Analyse these hiring movements. What do they signal about the corporate job market? "
        "Are companies restructuring, expanding, or pulling back? Identify employers with "
        "sustained trends (same direction for multiple weeks) vs one-week anomalies. "
        "Connect the dots for someone working in Big 4, law, banking, or tech.\n\n"
        "Output ONLY the commentary text. No title. No sign-off."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=model)
```

- [ ] **Step 5: Run tests to verify they pass**

```
.venv/bin/pytest tests/test_lobby.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add flatwhite/dashboard/api.py tests/test_lobby.py
git commit -m "feat: extend Lobby API with 8-week history, MoM delta, and sparkline data"
```

---

## Task 6: Backend — `/api/preview-prompt` endpoint + `custom_prompt` support

**Files:**
- Modify: `flatwhite/dashboard/api.py`

- [ ] **Step 1: Refactor `_proceed_*` functions to accept `custom_prompt` parameter**

Each `_proceed_*` function needs to accept `custom_prompt: str | None = None`. When it's provided, skip prompt rendering and call route directly.

Update signature and add early-return for each. Template to apply to all functions:

```python
def _proceed_pulse(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import PULSE_SUMMARY_SYSTEM, PULSE_SUMMARY_PROMPT
    from flatwhite.dashboard.state import load_pulse_state, load_signals_this_week

    if custom_prompt:
        return route(task_type="summary", prompt=custom_prompt, system=PULSE_SUMMARY_SYSTEM, model_override=model)

    # ... existing implementation unchanged ...
```

Apply the same pattern to: `_proceed_big_conversation`, `_proceed_finds`, `_proceed_thread`, `_proceed_amp_finest`, `_proceed_off_the_clock`, `_proceed_editorial`. (Task 5 already did `_proceed_lobby`.)

- [ ] **Step 2: Update `api_proceed_section` to pass `custom_prompt` through**

In `api_proceed_section()`, extract `custom_prompt` from the body and pass it to the proceed function:

```python
@app.post("/api/proceed-section")
async def api_proceed_section(request: Request) -> JSONResponse:
    from flatwhite.db import save_section_output

    body = await request.json()
    section = body.get("section", "")
    model = body.get("model") or None
    data = body.get("data", {})
    custom_prompt = body.get("custom_prompt") or None
    week_iso = get_current_week_iso()

    proceed_fns = { ... }  # unchanged

    if section not in proceed_fns:
        return JSONResponse({"error": f"Unknown section: {section}"}, status_code=400)

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        output = await loop.run_in_executor(
            None, proceed_fns[section], data, model, custom_prompt
        )
        save_section_output(week_iso, section, output, model)
        return JSONResponse({"section": section, "output": output, "model": model, "week_iso": week_iso})
    except Exception as e:
        return JSONResponse({"section": section, "error": str(e)}, status_code=500)
```

- [ ] **Step 3: Add `/api/preview-prompt` POST endpoint**

Add after the `/api/proceed-section` handler in `flatwhite/dashboard/api.py`:

```python
@app.post("/api/preview-prompt")
async def api_preview_prompt(request: Request) -> JSONResponse:
    """Render and return the default LLM prompt for a section without calling the LLM.

    Body: {"section": str, "data": dict (optional)}
    Returns: {"prompt": str, "section": str}
    """
    body = await request.json()
    section = body.get("section", "")
    data = body.get("data", {})

    try:
        if section == "pulse":
            from flatwhite.classify.prompts import PULSE_SUMMARY_PROMPT
            from flatwhite.dashboard.state import load_pulse_state, load_signals_this_week
            from flatwhite.db import get_interactions
            from flatwhite.signals.macro_context import fetch_macro_headlines
            pulse = load_pulse_state()
            signals = load_signals_this_week()

            # Compute delta-annotated signal lines (same logic as _proceed_pulse)
            import datetime as _dt
            week_iso = get_current_week_iso()
            conn = get_connection()
            year_s, wn_s = int(week_iso[:4]), int(week_iso[6:])
            dt_s = _dt.datetime.strptime(f"{year_s}-W{wn_s:02d}-1", "%G-W%V-%u")
            prev_wk = (dt_s - _dt.timedelta(weeks=1)).strftime("%G-W%V")
            prev_rows = conn.execute(
                "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
                (prev_wk,),
            ).fetchall()
            conn.close()
            prev_map = {s["signal_name"]: s["normalised_score"] for s in prev_rows}
            selected_signals = data.get("selected_signals", [s["signal_name"] for s in signals])
            signal_lines = []
            for s in signals:
                if s["signal_name"] in selected_signals:
                    name = s["signal_name"]
                    score = round(s["normalised_score"], 1)
                    prev = prev_map.get(name)
                    if prev is not None:
                        delta = round(score - prev, 1)
                        signal_lines.append(f"{name}: {score} (prev: {round(prev,1)}, Δ: {delta:+.1f})")
                    else:
                        signal_lines.append(f"{name}: {score}")

            interactions = get_interactions(week_iso)
            interactions_block = ""
            if interactions:
                interactions_block = "\nSignal interactions detected:\n" + "\n".join(
                    f"- {ix['pattern_name']}: {ix['narrative']}" for ix in interactions
                ) + "\n"
            macro_context = ""
            try:
                macro_context = fetch_macro_headlines()
            except Exception:
                pass

            prompt = PULSE_SUMMARY_PROMPT.format(
                smoothed=f"{pulse['smoothed_score']:.0f}" if pulse else "50",
                direction=pulse["direction"] if pulse else "stable",
                prev_smoothed=f"{pulse.get('smoothed_score', 50):.0f}" if pulse else "50",
                drivers="\n".join(signal_lines[:10]),
                interactions_block=interactions_block,
                macro_context=macro_context,
            )

        elif section == "lobby":
            selected = data.get("selected_employers", [])
            employer_lines = []
            for e in selected:
                name = e.get("employer_name", str(e)) if isinstance(e, dict) else str(e)
                if isinstance(e, dict):
                    current = e.get("open_roles_count", "?")
                    wow = e.get("delta")
                    mom = e.get("mom_delta")
                    wow_str = f"+{wow}" if wow and wow > 0 else str(wow) if wow is not None else "—"
                    mom_str = f"+{mom}" if mom and mom > 0 else str(mom) if mom is not None else "—"
                    employer_lines.append(f"- {name}: {current} roles (WoW: {wow_str}, MoM: {mom_str})")
                else:
                    employer_lines.append(f"- {name}")
            employer_block = "\n".join(employer_lines) if employer_lines else "No employers selected."
            prompt = (
                "Write The Lobby section for this week's Flat White newsletter.\n\n"
                f"Employer hiring movements this week:\n{employer_block}\n\n"
                "Analyse these hiring movements. What do they signal about the corporate job market? "
                "Are companies restructuring, expanding, or pulling back? Identify employers with "
                "sustained trends (same direction for multiple weeks) vs one-week anomalies. "
                "Connect the dots for someone working in Big 4, law, banking, or tech.\n\n"
                "Output ONLY the commentary text. No title. No sign-off."
            )

        elif section == "off_the_clock":
            picks = data.get("picks", [])
            picks_block = "\n\n".join(
                f"Category: {p.get('category', '')}\nTitle: {p.get('title', '')}\nDraft blurb: {p.get('blurb', '')}"
                for p in picks
            )
            prompt = (
                "Polish these Off the Clock blurbs for Flat White.\n\n"
                f"{picks_block}\n\n"
                "For each, rewrite the blurb in 1-2 sentences. Voice: dry, specific, opinionated. "
                "Not a review. A statement from someone who already knows. Australian English.\n\n"
                "Output as: CATEGORY: BLURB (one per line)"
            )

        elif section == "finds":
            items = data.get("selected_items", [])
            items_block = "\n\n".join(
                f"Title: {item.get('title', '')}\nURL: {item.get('url', '')}\nSummary: {item.get('summary', '')}"
                for item in items
            )
            prompt = (
                "Write the Finds section for this week's Flat White newsletter.\n\n"
                f"Selected items:\n{items_block}\n\n"
                "For each item, write a headline and a 2-3 sentence blurb. Voice: dry, observant, "
                "Australian corporate commentary. Each blurb should tell the reader why this matters "
                "to someone in corporate Australia. End each with 'Read more' on its own line.\n\n"
                "Output each find as: HEADLINE\\nBLURB\\nRead more\\n\\n"
            )

        else:
            return JSONResponse({"error": f"Preview not supported for section: {section}"}, status_code=400)

        return JSONResponse({"prompt": prompt, "section": section})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

- [ ] **Step 4: Restart server and verify manually**

```bash
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500
```

In another terminal:
```bash
curl -s -X POST http://localhost:8500/api/preview-prompt \
  -H "Content-Type: application/json" \
  -d '{"section": "lobby", "data": {"selected_employers": []}}' | python3 -m json.tool
```
Expected: JSON with `"prompt"` key containing the lobby prompt text.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat: add /api/preview-prompt endpoint and custom_prompt support in proceed-section"
```

---

## Task 7: Frontend — SCRAPE rename + PROCEED modal

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

This task renames all RUN buttons to SCRAPE, adds the modal component, and rewires each section's proceed function to open the modal instead of firing immediately.

- [ ] **Step 1: Rename all RUN buttons to SCRAPE**

In `index.html`, replace all occurrences of `>RUN</button>` with `>SCRAPE</button>`. There are 7 instances (pulse, lobby, finds, thread, off_the_clock, big_conversation × 2). Also update the toast message in `runSection()` from `"started..."` to `"scraping..."`.

Specific replacements (use replace_all):
- `onclick="runSection('pulse')">RUN</button>` → `onclick="runSection('pulse')">SCRAPE</button>`
- `onclick="runSection('lobby')">RUN</button>` → `onclick="runSection('lobby')">SCRAPE</button>`
- `onclick="runSection('finds')">RUN</button>` → `onclick="runSection('finds')">SCRAPE</button>`
- `onclick="runSection('thread')">RUN</button>` → `onclick="runSection('thread')">SCRAPE</button>`
- `onclick="runSection('off_the_clock')">RUN</button>` → `onclick="runSection('off_the_clock')">SCRAPE</button>`
- `onclick="runBigConv()">RUN</button>` → `onclick="runBigConv()">SCRAPE</button>`
- `onclick="runSection('editorial')">RUN</button>` → `onclick="runSection('editorial')">SCRAPE</button>`

- [ ] **Step 2: Add modal state to `S`**

In the `S` state object (around line 232), add:

```javascript
  proceedModal: { open: false, section: null, prompt: "", lean: "", items: [], loading: false },
  proceedData: {},
```

- [ ] **Step 3: Add modal CSS**

In the `<style>` block, add:

```css
.modal-overlay { position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:1000;display:flex;align-items:flex-start;justify-content:center;padding-top:60px; }
.modal-box { background:var(--bg-2);border-radius:12px;padding:28px;width:720px;max-width:95vw;max-height:80vh;overflow-y:auto;box-shadow:0 8px 40px rgba(0,0,0,0.3); }
.modal-box h3 { margin:0 0 16px;font-size:18px; }
.modal-section-label { font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-3);margin:16px 0 6px; }
.modal-footer { display:flex;gap:10px;justify-content:flex-end;margin-top:20px; }
```

- [ ] **Step 4: Add modal render function and open/close/confirm logic**

Add this JavaScript block before the `/* ═══ INIT ═══ */` comment:

```javascript
/* ═══════════════════════════════════════════════════════════════════════
   PROCEED MODAL
   ═══════════════════════════════════════════════════════════════════════ */
function openProceedModal(section, items) {
  S.proceedModal = { open: true, section: section, prompt: "", lean: "", items: items || [], loading: true };
  render();
  api("/api/preview-prompt", { method: "POST", body: { section: section, data: S.proceedData[section] || {} } })
    .then(function(d) {
      S.proceedModal.prompt = d.prompt || "";
      S.proceedModal.loading = false;
      render();
    })
    .catch(function() {
      S.proceedModal.prompt = "(Could not load prompt preview)";
      S.proceedModal.loading = false;
      render();
    });
}

function closeProceedModal() {
  S.proceedModal = { open: false, section: null, prompt: "", lean: "", items: [], loading: false };
  render();
}

function confirmAndGenerate() {
  var modal = S.proceedModal;
  var section = modal.section;
  var lean = modal.lean.trim();
  var customPrompt = lean ? lean + "\n\n" + modal.prompt : modal.prompt;
  S.proceedModal.open = false;
  S.loading[section] = true;
  render();
  var body = Object.assign({}, S.proceedData[section] || {}, {
    section: section,
    custom_prompt: customPrompt,
  });
  api("/api/proceed-section", { method: "POST", body: body })
    .then(function(d) {
      S.sectionOutputs[section] = { output_text: d.output, model_used: d.model };
      S.loading[section] = false;
      render();
      showToast(section.replace(/_/g, " ") + " generated");
    })
    .catch(function(e) {
      S.loading[section] = false;
      render();
      showToast("Error: " + e.message, "error");
    });
}

function renderProceedModal() {
  if (!S.proceedModal.open) return "";
  var modal = S.proceedModal;
  var h = '<div class="modal-overlay" onclick="if(event.target===this)closeProceedModal()">';
  h += '<div class="modal-box">';
  h += '<h3>Generate ' + esc(modal.section.replace(/_/g, " ")) + '</h3>';
  h += '<div class="modal-section-label">Editorial lean (optional)</div>';
  h += '<input class="form-input" style="margin-bottom:12px;" placeholder="e.g. Focus on Big 4 this week..." value="' + esc(modal.lean) + '" oninput="S.proceedModal.lean=this.value">';
  h += '<div class="modal-section-label">Prompt</div>';
  if (modal.loading) {
    h += '<div class="loading" style="padding:20px 0;">Loading prompt...</div>';
  } else {
    h += '<textarea class="form-input" rows="14" style="font-family:monospace;font-size:12px;" oninput="S.proceedModal.prompt=this.value">' + esc(modal.prompt) + '</textarea>';
  }
  h += '<div class="modal-footer">';
  h += '<button class="btn btn-secondary" onclick="closeProceedModal()">Cancel</button>';
  h += '<button class="btn btn-success" onclick="confirmAndGenerate()" ' + (modal.loading ? 'disabled' : '') + '>Confirm & Generate</button>';
  h += '</div></div></div>';
  return h;
}
```

- [ ] **Step 5: Render modal in the main `render()` function**

In the `render()` function, after the `m.innerHTML = html;` call, add:

```javascript
  // Render modal overlay (outside main content)
  var modalEl = document.getElementById("modal-root");
  if (modalEl) modalEl.innerHTML = renderProceedModal();
```

Add `<div id="modal-root"></div>` just before `</body>` in the HTML.

- [ ] **Step 6: Rewire proceed functions to use modal**

Replace `proceedPulse()`:

```javascript
function proceedPulse() {
  var model = getModel("model-pulse");
  var checked = Object.keys(S.pulseChecked).filter(function(k) { return S.pulseChecked[k]; });
  S.proceedData.pulse = { section: "pulse", model: model, data: { selected_signals: checked, pulse: S.pulse, signals: S.signals, anomalies: S.anomalies } };
  openProceedModal("pulse");
}
```

Replace `proceedLobby()`:

```javascript
function proceedLobby() {
  var model = getModel("model-lobby");
  var checked = Object.keys(S.lobbyChecked).filter(function(k) { return S.lobbyChecked[k]; });
  var selected = S.lobby && S.lobby.employers ? S.lobby.employers.filter(function(e) { return checked.indexOf(e.employer_name) >= 0; }) : [];
  S.proceedData.lobby = { section: "lobby", model: model, data: { selected_employers: selected, top_movers: S.lobby ? S.lobby.top_movers : [] } };
  openProceedModal("lobby");
}
```

Replace `proceedFinds()`:

```javascript
function proceedFinds() {
  var model = getModel("model-finds");
  var checked = Object.keys(S.findsChecked).filter(function(k) { return S.findsChecked[k]; });
  var items = (S.items && S.items.finds) || [];
  var selected = items.filter(function(i) { return checked.indexOf(String(i.id)) >= 0; });
  S.proceedData.finds = { section: "finds", model: model, data: { selected_items: selected } };
  openProceedModal("finds");
}
```

Replace `proceedOTC()` (the core part — before the save picks logic):

```javascript
function proceedOTC() {
  var model = getModel("model-otc");
  var picks = [];
  OTC_CATS.forEach(function(cat) {
    if (S.otcPicks[cat.key]) {
      picks.push({ category: cat.key, curated_item_id: S.otcPicks[cat.key], blurb: S.otcBlurbs[cat.key] || "" });
    }
  });
  S.proceedData.off_the_clock = { section: "off_the_clock", model: model, data: { picks: picks } };
  // Save picks first, then open modal
  var savePromises = picks.map(function(p) {
    return api("/api/off-the-clock/pick", { method: "POST", body: p }).catch(function() {});
  });
  Promise.all(savePromises).then(function() {
    openProceedModal("off_the_clock");
  });
}
```

- [ ] **Step 7: Verify in browser**

Restart server. Navigate to Pulse → click PROCEED → modal opens with prompt loaded. Edit the prompt → Confirm & Generate → output appears. Close modal with Cancel or backdrop click.

- [ ] **Step 8: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: rename RUN to SCRAPE, add PROCEED prompt review modal"
```

---

## Task 8: Frontend — Pulse category trend cards + sparklines

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add shared sparkline helper function**

Add this JavaScript function (near the other utility functions, before the section renderers):

```javascript
function sparkline(values, width, height) {
  var clean = values.filter(function(v) { return v != null; });
  if (clean.length < 2) return '<svg width="' + width + '" height="' + height + '"></svg>';
  var min = Math.min.apply(null, clean);
  var max = Math.max.apply(null, clean);
  var range = max - min || 1;
  var w = width / (clean.length - 1);
  var points = clean.map(function(v, i) {
    var x = Math.round(i * w);
    var y = Math.round(height - ((v - min) / range * (height - 4)) - 2);
    return x + "," + y;
  }).join(" ");
  return '<svg width="' + width + '" height="' + height + '" style="vertical-align:middle">'
    + '<polyline points="' + points + '" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
    + '</svg>';
}
```

- [ ] **Step 2: Add CSS for category trend cards**

In the `<style>` block:

```css
.cat-trends { display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px; }
@media(max-width:700px){.cat-trends{grid-template-columns:1fr;}}
.cat-card { background:var(--bg-2);border-radius:10px;padding:16px; }
.cat-card-label { font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-3);margin-bottom:8px; }
.cat-card-score { font-size:28px;font-weight:700;color:var(--text-1); }
.cat-card-delta { display:inline-block;font-size:13px;font-weight:600;padding:2px 8px;border-radius:20px;margin-top:4px; }
.cat-card-delta.up { background:#d4edda;color:#155724; }
.cat-card-delta.down { background:#f8d7da;color:#721c24; }
.cat-card-delta.stable { background:var(--bg-3);color:var(--text-3); }
```

- [ ] **Step 3: Add `renderCategoryTrends()` function**

```javascript
function renderCategoryTrends() {
  if (!S.trends || !S.trends.categories) return "";
  var h = '<div class="cat-trends">';
  S.trends.categories.forEach(function(cat) {
    var score = cat.current_score != null ? cat.current_score.toFixed(1) : "—";
    var delta = cat.delta;
    var deltaClass = delta == null ? "stable" : (delta > 2 ? "up" : (delta < -2 ? "down" : "stable"));
    var deltaText = delta == null ? "—" : ((delta > 0 ? "+" : "") + delta.toFixed(1));
    var histScores = (cat.history || []).map(function(h) { return h.score; });
    h += '<div class="cat-card">';
    h += '<div class="cat-card-label">' + esc(cat.label) + '</div>';
    h += '<div class="cat-card-score">' + esc(score) + '</div>';
    h += '<div><span class="cat-card-delta ' + deltaClass + '">' + esc(deltaText) + ' WoW</span></div>';
    if (histScores.length >= 2) {
      h += '<div style="margin-top:10px;">' + sparkline(histScores, 120, 36) + '</div>';
    }
    h += '</div>';
  });
  h += '</div>';
  return h;
}
```

- [ ] **Step 4: Call `renderCategoryTrends()` in `renderPulse()`**

In `renderPulse()`, after the gauge card (`h += '</div>';` closing the gauge card, around line 494), insert:

```javascript
    h += renderCategoryTrends();
```

- [ ] **Step 5: Extend signal table deltas to use `all_signal_deltas`**

In `renderPulse()`, replace the `moverDeltas` construction (around line 515):

```javascript
      // Build delta lookup from all_signal_deltas (full set) with biggest_movers as fallback
      var moverDeltas = {};
      if (S.trends && S.trends.all_signal_deltas) {
        Object.keys(S.trends.all_signal_deltas).forEach(function(name) {
          moverDeltas[name] = S.trends.all_signal_deltas[name].delta || 0;
        });
      } else if (S.trends && S.trends.biggest_movers) {
        S.trends.biggest_movers.forEach(function(m) { moverDeltas[m.signal_name || m.name] = m.delta || 0; });
      }
```

- [ ] **Step 6: Verify in browser**

Restart server → Pulse page → confirm three category cards appear with scores, WoW delta badges, and sparklines. Confirm all signals in the table now show deltas (not just top 5).

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: add Pulse category trend cards with sparklines and all-signal WoW deltas"
```

---

## Task 9: Frontend — Off the Clock multi-select item checklist

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`
- Modify: `flatwhite/dashboard/state.py` (remove `candidates_per_category` cap in `load_otc_candidates`)

- [ ] **Step 1: Remove the candidate cap in `load_otc_candidates()`**

In `flatwhite/dashboard/state.py`, update `load_otc_candidates()`. Change the grouping logic (around line 624) to remove the `< candidates_per_category` limit:

```python
    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in OTC_SECTIONS}
    for row in rows:
        d = dict(row)
        section = d["section"]
        if section in grouped:
            grouped[section].append(d)  # removed: and len(grouped[section]) < candidates_per_category
```

- [ ] **Step 2: Add `otcSelected` state to `S`**

In the `S` state object, add:

```javascript
  otcSelected: {},   // { "otc_eating": { 123: true, 456: false }, ... }
```

- [ ] **Step 3: Replace the OTC candidates rendering in `renderOTC()`**

Replace the `OTC_CATS.forEach` block that renders candidates (lines 995–1015) with:

```javascript
    OTC_CATS.forEach(function(cat) {
      var candidates = S.otcData.candidates[cat.key] || [];
      h += '<div class="card otc-cat-card">';
      h += '<div class="otc-cat-title">' + esc(cat.label) + ' ';
      h += '<span style="font-size:11px;color:var(--text-3);">' + candidates.length + ' items</span></div>';
      if (!candidates.length) {
        h += '<p style="font-size:12px;color:var(--text-3);">No candidates</p>';
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
      h += '</div>';
    });
```

- [ ] **Step 4: Add `toggleOtcSelect` function**

```javascript
function toggleOtcSelect(cat, id, val) {
  if (!S.otcSelected[cat]) S.otcSelected[cat] = {};
  S.otcSelected[cat][id] = val;
  render();
}
```

- [ ] **Step 5: Update `proceedOTC()` to include selected item IDs in `proceedData`**

Update the `proceedOTC()` function (from Task 7 Step 6) to also attach the selected items per category:

```javascript
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
  var savePromises = picks.map(function(p) {
    return api("/api/off-the-clock/pick", { method: "POST", body: p }).catch(function() {});
  });
  Promise.all(savePromises).then(function() {
    openProceedModal("off_the_clock");
  });
}
```

- [ ] **Step 6: Verify in browser**

OTC page → after SCRAPE, all items show as checkboxes with city + source. Deselect some. Click PROCEED → modal shows the prompt with only selected items listed per category.

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/static/index.html flatwhite/dashboard/state.py
git commit -m "feat: OTC multi-select item checklist with prompt review in PROCEED modal"
```

---

## Task 10: Frontend — Finds AU relevance badges + re-ranking

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add AU badge CSS**

In the `<style>` block:

```css
.chip-au { background:#d4edda;color:#155724; }
.chip-low-au { background:var(--bg-3);color:var(--text-3); }
```

- [ ] **Step 2: Update Finds display sort in `renderFinds()`**

In `renderFinds()`, after loading `var items = (S.items && S.items.finds) || [];`, add sort:

```javascript
    // Re-rank: AU relevance counts for 30% of display score
    items = items.slice().sort(function(a, b) {
      var da = (a.weighted_composite || 0) * 0.7 + ((a.au_relevance != null ? a.au_relevance : 5) / 10.0) * 3.0;
      var db = (b.weighted_composite || 0) * 0.7 + ((b.au_relevance != null ? b.au_relevance : 5) / 10.0) * 3.0;
      return db - da;
    });
```

- [ ] **Step 3: Add AU badges to each Finds item card**

In `renderFinds()`, in the item card rendering loop, add badge logic after the existing title/score output. Find the section that renders each finds item (look for `weighted_composite` display in the finds loop) and add:

```javascript
        // AU relevance badge
        var auRel = item.au_relevance != null ? item.au_relevance : null;
        if (auRel != null) {
          if (auRel >= 7) {
            h += '<span class="chip chip-au" style="font-size:10px;">AU</span> ';
          } else if (auRel < 4) {
            h += '<span class="chip chip-low-au" style="font-size:10px;">low AU</span> ';
          }
        }
```

- [ ] **Step 4: Verify in browser**

Finds page → items with `au_relevance >= 7` show green AU badge. Items with `au_relevance < 4` show grey "low AU" badge. Sort order prioritises AU items.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: Finds AU relevance re-ranking and badges"
```

---

## Task 11: Frontend — Lobby WoW/MoM columns + sparklines

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add bar sparkline helper**

Add after the `sparkline()` function from Task 8:

```javascript
function barSparkline(values, width, height) {
  var clean = values.filter(function(v) { return v != null; });
  if (!clean.length) return '<svg width="' + width + '" height="' + height + '"></svg>';
  var max = Math.max.apply(null, clean) || 1;
  var barW = Math.max(2, Math.floor(width / clean.length) - 1);
  var bars = clean.map(function(v, i) {
    var h2 = Math.max(2, Math.round((v / max) * height));
    var x = i * (barW + 1);
    var y = height - h2;
    return '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + h2 + '" fill="var(--accent)" opacity="0.7" rx="1"/>';
  }).join("");
  return '<svg width="' + width + '" height="' + height + '" style="vertical-align:middle">' + bars + '</svg>';
}
```

- [ ] **Step 2: Update Lobby table headers**

In `renderLobby()`, replace:

```javascript
    h += '<table class="tbl"><thead><tr><th style="width:30px;"></th><th>Employer</th><th>Sector</th><th>Roles</th><th>Prev</th><th>Delta</th></tr></thead><tbody>';
```

With:

```javascript
    h += '<table class="tbl"><thead><tr><th style="width:30px;"></th><th>Employer</th><th>Sector</th><th>Roles</th><th>WoW</th><th>MoM</th><th>Trend</th></tr></thead><tbody>';
```

- [ ] **Step 3: Update Lobby table row rendering**

Replace the existing `S.lobby.employers.forEach` block:

```javascript
    S.lobby.employers.forEach(function(e) {
      var name = e.employer_name || "";
      var checked = S.lobbyChecked[name] ? " checked" : "";
      var wow = e.delta != null ? e.delta : null;
      var mom = e.mom_delta != null ? e.mom_delta : null;
      var wowStyle = wow == null ? 'color:var(--text-3)' : (wow > 0 ? 'color:var(--green);font-weight:600' : (wow < 0 ? 'color:var(--red);font-weight:600' : 'color:var(--text-3)'));
      var momStyle = mom == null ? 'color:var(--text-3)' : (mom > 0 ? 'color:var(--green);font-weight:600' : (mom < 0 ? 'color:var(--red);font-weight:600' : 'color:var(--text-3)'));
      var wowText = wow == null ? "—" : (wow > 0 ? "+" : "") + wow;
      var momText = mom == null ? "—" : (mom > 0 ? "+" : "") + mom;
      var hist = e.history || [];
      h += '<tr>';
      h += '<td><input type="checkbox"' + checked + ' onchange="toggleLobbyCheck(\'' + esc(name).replace(/'/g, "\\'") + '\',this.checked)"></td>';
      h += '<td><strong>' + esc(name) + '</strong></td>';
      h += '<td>' + esc(e.sector || "") + '</td>';
      h += '<td>' + esc(e.open_roles_count || 0) + '</td>';
      h += '<td style="' + wowStyle + '">' + wowText + '</td>';
      h += '<td style="' + momStyle + '">' + momText + '</td>';
      h += '<td>' + barSparkline(hist, 64, 24) + '</td>';
      h += '</tr>';
    });
```

- [ ] **Step 4: Update Top Movers cards to show MoM**

In the `top_movers` card rendering block, after the `mc-detail` div, add:

```javascript
        var mom = m.mom_delta != null ? m.mom_delta : null;
        if (mom != null) {
          var momSign = mom > 0 ? "+" : "";
          var momCls = mom > 0 ? "color:var(--green)" : (mom < 0 ? "color:var(--red)" : "color:var(--text-3)");
          h += '<div style="font-size:11px;' + momCls + '">4-wk: ' + momSign + mom + '</div>';
        }
```

- [ ] **Step 5: Verify in browser**

Lobby page → table now has WoW, MoM, Trend columns. Top Movers cards show 4-week delta line. Sparklines render as bar charts.

- [ ] **Step 6: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat: Lobby WoW/MoM columns and sparklines"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| RUN → SCRAPE rename | Task 7 Step 1 |
| PROCEED modal with prompt preview | Task 7 Steps 2–6 |
| Editorial lean field in modal | Task 7 Step 4 |
| Item selection in modal | Task 7 Step 6 / Task 9 Step 5 |
| `/api/preview-prompt` endpoint | Task 6 Step 3 |
| `custom_prompt` in `/api/proceed-section` | Task 6 Steps 1–2 |
| Pulse category trend cards | Task 8 Steps 3–4 |
| 6-week sparklines on Pulse cards | Task 8 Step 3 |
| All-signal WoW deltas in Pulse table | Task 8 Step 5 |
| WoW deltas in Pulse LLM prompts | Task 4 Steps 3–5 |
| Fallback signal annotation in Pulse prompt | Task 4 Step 5 |
| `au_relevance` DB column | Task 1 |
| `au_relevance` in classification | Task 2 |
| Finds AU/low-AU badges | Task 10 Step 3 |
| Finds display re-ranking | Task 10 Step 2 |
| OTC multi-select checklist | Task 9 Steps 3–4 |
| OTC removes 3-item cap | Task 9 Step 1 |
| Lobby 8-week history | Task 5 Step 3 |
| Lobby MoM delta | Task 5 Step 3 |
| Lobby sparklines | Task 11 Steps 1–3 |
| Lobby Top Movers MoM line | Task 11 Step 4 |
| Lobby PROCEED prompt includes trend data | Task 5 Step 4 |

All spec requirements covered.

**Placeholder scan:** No TBDs or vague steps — all steps include actual code.

**Type consistency:** `mom_delta` used consistently in api.py (Task 5) and index.html (Task 11). `au_relevance` is `INTEGER` in DB, `int` in Python, and accessed as `item.au_relevance` in JS. `all_signal_deltas` dict keyed by `signal_name` (string) matches usage in Task 8. `custom_prompt` is `str | None` throughout.
