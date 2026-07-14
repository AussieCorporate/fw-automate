# FW Control Room Increment 6 — The Brains Trust (Economic Scoop), Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Brains Trust section page (Victor calls it "the Brains Trust" and "the Economic Scoop" — same segment, two names, never treat as separate). The dashboard surfaces recommended angles read from the Trading Strategy research bank across the **last 3 weeks**, Victor picks one, and the dash consolidates the relevant research and drafts the piece in Flat White's Brains Trust register. Output is editable and can be marked ready. The Friday research digest email (which already sends ~5 bulge-bracket picks drawn from the same research bank) is untouched.

**Architecture:** A new read-only reader module (`flatwhite/dashboard/brains_trust_research.py`) mirrors the exact reading pattern of Shell Bot 2's `pipeline/bulge_bracket.py` — glob `carousels/*/_candidates.json`, extract the embedded `YYYYMMDD` from the folder name (handling `backfill_YYYYMMDD`), defensively validate every JSON shape with `isinstance` guards, and optionally enrich with the read-only SQLite DB opened in `mode=ro`. Unlike `bulge_bracket.py` (which returns only the single newest folder), this reader returns **every** candidate from folders dated within the last 3 weeks, because the segment explicitly wants a multi-week pool (the EV tipping-point piece consolidated two weeks of research). A new generation function `_proceed_brains_trust` slots into FW's existing `proceed_fns` dispatch in `api.py` exactly like `_proceed_editorial`/`_proceed_off_the_clock` do — same `(data, model, custom_prompt) -> str` shape, same `route()` call, same `/api/proceed-section` and `/api/section-output/{section}` endpoints already used by every other segment (no new save/mark-ready plumbing needed). The only new endpoint is the read-only angle list (`GET /api/brains-trust/angles`). The frontend adds one `renderBrains(el)` page function using the exact same container-based calling convention (`renderX(el)`) every existing section renderer already uses, so it drops into whichever nav shell is live (see Sequencing note below).

**Tech Stack:** FastAPI (`flatwhite/dashboard/api.py`), single static HTML/CSS/JS frontend (no build step), `pytest` via FW's own venv. Reads (never writes) SQLite via Python's stdlib `sqlite3` URI read-only mode.

## Global Constraints

- **Runs on FW's venv only:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python 3.9 breaks FW. Never use another interpreter for FW.
- **Branch:** from `main`, `git checkout main && git checkout -b fw-control-room-brains-trust`. FW deploy is Victor's (GCP VM) — built and tested locally only, never merged/pushed/deployed without him.
- **FW test baseline (recorded 14 Jul 2026):** `.venv/bin/python -m pytest -q` → **124 passed, 8 failed** (pre-existing failures in `test_normalise.py` and `test_pipeline.py`, unrelated to this work — anomaly-detection/self-calibration tests, nothing to do with Brains Trust). After every task the failure count must stay at 8 and the pass count must only go up.
- No em dashes (U+2014) anywhere in reader-facing strings or prompts. Australian spelling. "percent" written as `%`, never spelled out.
- **Trading Strategy is READ-ONLY, unconditionally.** Its path (`/Users/victornguyen/Documents/MISC/Trading Strategy/data`), its `_candidates.json` files, and its `trading_strategy.db` are never written to, never imported from as a runnable dependency, never have their own code modified. The one DB read in this plan opens with SQLite's URI `mode=ro` so it is structurally impossible for that connection to write.
- **The Friday research digest email is untouched.** Nothing in this plan modifies `/Users/victornguyen/Documents/MISC/Trading Strategy/src/synthesis.py`, `src/cli.py`, `src/delivery.py`, or the `com.tradingstrategy.weekly-digest` launchd job. It keeps sending exactly as it does today.
- **Tests never make real Claude/network/DB-write calls.** Every test that would otherwise call `route()` monkeypatches `flatwhite.dashboard.api.route` (mirrors `tests/test_model_picker.py`). Every test that reads the Trading Strategy filesystem/DB points `root=` at a `tmp_path` fixture, never the real project path.
- Local run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`. Kill it when done.

## Decisions locked in during research (read before starting)

1. **Exact Trading Strategy path and read pattern.** The candidate folders live at `/Users/victornguyen/Documents/MISC/Trading Strategy/data/carousels/<YYYYMMDD or backfill_YYYYMMDD>/_candidates.json` (48 folders on disk today, e.g. `20260713`, `backfill_20260602`). Each `_candidates.json` is `{"candidates": [{"pitch": str, "angle": str, "why_tac": str, "source_pdf_ids": [int]}, ...]}` (confirmed against `.../carousels/20260713/_candidates.json`, 4 candidates). The read-only DB is `/Users/victornguyen/Documents/MISC/Trading Strategy/data/trading_strategy.db`, tables `pdfs(id, email_id)` and `emails(id, sender, subject, date_received, stream)`. Shell Bot 2's `pipeline/bulge_bracket.py` (`/Users/victornguyen/Movies/Shell Bot 2/pipeline/bulge_bracket.py`) already reads this exact structure read-only for a different desk; this plan's `brains_trust_research.py` is a straight port of its `_folder_date`/`isinstance`-guard defensiveness, widened from "the single newest folder" to "every folder inside a 3-week window", because Brains Trust explicitly wants a multi-week pool, not just this week.
2. **The digest's "top 5" is not a stored artifact — it's synthesised fresh by an LLM at send time.** Trading Strategy's `src/synthesis.py::generate_deep_dive_candidates()` builds the weekly digest's Top-5 by calling Claude over `_recent_carousel_pitches()` (the same `_candidates.json` pitches, filtered to `since = now - 7 days`) plus that week's macro/equity research text. Its output is markdown embedded straight into the emailed digest (or, when previewed locally, a throwaway `weekly_digest_preview_*.digest.md` file) — there is no persisted "these are this week's 5 picks" JSON to read. So the dash cannot literally mirror the email's five finished lines without either (a) re-running that same Claude call from FW — out of scope, duplicates Trading Strategy's own logic, and violates "no real Claude calls" in tests — or (b) reading a file that doesn't exist. This plan instead surfaces the **same underlying candidate pool** the digest draws from (every `_candidates.json` pitch/angle in the window), widened from the digest's 7-day window to 3 weeks per the spec. Victor sees a superset of what the email's Top-5 was drawn from, across a longer window, and picks the angle himself — consistent with "human picks, machine drafts."
3. **No legacy "economic flags/indicators" generator exists inside FW to retire.** Grepped `flatwhite/dashboard/api.py` and the whole FW repo for `economic`, `scoop`, `brains`, `flags`, `indicator` (case-insensitive): the only FW hits are Pulse's unrelated `area='economic'` signal category (labour market / corporate stress / economic, feeding the Stress Index) — nothing named Brains Trust or Economic Scoop, and no `_proceed_*` generator for it, has ever existed in FW's `_proceed_pulse` / `_proceed_big_conversation` / `_proceed_finds` / `_proceed_thread` / `_proceed_off_the_clock` / `_proceed_editorial` set. The "old auto economic flags/indicators form" Victor means (per `/Users/victornguyen/Documents/MISC/Trading Strategy/CLAUDE.md`) is Trading Strategy's own `generate_flat_white_scoop()` — a **different, read-only project's** function that Victor has already stopped using ("it doesn't change enough week to week") and which this plan does not touch, per the read-only constraint above. **There is nothing to delete in FW for this increment** — Task 1-3 below are pure additions.
4. **Benchmark chip is computed client-side, no new endpoint.** `data/beehiiv_fw_ground_truth.json`'s 10 real "THE BRAINS TRUST" / "THE ECONOMIC SCOOP" segments run 263-375 words (mean 316). Register: broker-research-led, cites specific figures and %, attributes direct quotes to the bank ("— UBS", "— Morgan Stanley Research"), objective/data-driven tone (not the Big Conversation's editorial voice), Australian spelling, no em dashes. Word count is trivial to compute in JS, so the benchmark chip needs no backend round trip — it is computed against a hardcoded range taken from these real numbers.
5. **Sequencing note — verified against the actual repo, not assumed.** As of 14 Jul 2026 the live `flatwhite/dashboard/static/index.html` still runs the **pre-redesign tab UI**: a flat `NAV_ITEMS` array (~line 395), `nav(page)` (~line 433), `loadPageData(page)` (~line 440), and `render()` (~line 593) switching on `S.page` to call `renderPulse(m)` / `renderBigConv(m)` / `renderOTC(m)` / `renderTopPicks(m)` / `renderEditorial(m)` into a single `$("content")` container. Increment 1's master/detail shell (`SEGMENTS` array, `selectSegment(id)`, `.page`/`.page-h`/`.page-b` frame, `toggleReady(id)`) has been **planned but not yet implemented** in this repo (confirmed: `grep -c "var SEGMENTS"` and `grep -c "function selectSegment"` both return 0 today). Task 5 below is written to detect whichever shell is live at execution time and wire into it accordingly — the new `renderBrains(el)` function itself, and every backend piece (Tasks 1-4), work identically either way, because every existing renderer already uses the same `renderX(el)`-into-a-container convention regardless of which nav shell calls it.

## File Structure

- Create: `flatwhite/dashboard/brains_trust_research.py` — read-only reader of the Trading Strategy candidate pool across a multi-week window.
- Create: `tests/test_brains_trust_research.py` — reader tests (mirrors `/Users/victornguyen/Movies/Shell Bot 2/tests/test_bulge_bracket.py`'s fixture style).
- Modify: `flatwhite/model_router.py` — register the `"brains_trust"` task type (temperature + default model).
- Modify: `flatwhite/classify/prompts.py` — add `BRAINS_TRUST_VOICE` system prompt constant.
- Modify: `flatwhite/dashboard/api.py` — add `GET /api/brains-trust/angles`; add `_proceed_brains_trust`; register it into `api_proceed_section`'s `proceed_fns` dict.
- Create: `tests/test_brains_trust_proceed.py` — generation + endpoint tests (mirrors `tests/test_model_picker.py` and `tests/test_backfill_api.py`'s calling conventions).
- Modify: `flatwhite/dashboard/static/index.html` — add `renderBrains(el)` and wire it into the live nav shell.

---

### Task 1: Read-only Trading Strategy reader — the angle pool

**Files:**
- Create: `flatwhite/dashboard/brains_trust_research.py`
- Test: `tests/test_brains_trust_research.py`

**Interfaces:**
- Produces: `load_angle_recommendations(root: str | None = None, weeks: int = 3, limit: int = 40) -> list[dict]`. Each dict: `{"id": str, "date_iso": "YYYY-MM-DD", "pitch": str, "angle": str, "why_tac": str, "source_pdf_ids": list[int], "source_pdf_date": str | None}`, newest folder first.
- Consumed by: Task 3's `GET /api/brains-trust/angles`.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/test_brains_trust_research.py
import os, json, sqlite3
from datetime import datetime
from unittest.mock import patch
import flatwhite.dashboard.brains_trust_research as bt


def _write_candidates(root, folder, candidates):
    d = os.path.join(root, "carousels", folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_candidates.json"), "w") as f:
        json.dump({"candidates": candidates}, f)


def _frozen_today(tmp_path, monkeypatch, iso_date):
    """Freeze bt's notion of 'now' so the 3-week window is deterministic."""
    fixed = datetime.strptime(iso_date, "%Y%m%d")
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed
    monkeypatch.setattr(bt, "datetime", _FixedDateTime)


def test_returns_empty_list_when_root_missing(tmp_path):
    assert bt.load_angle_recommendations(root=str(tmp_path / "nope")) == []


def test_returns_empty_list_when_no_carousels_dir(tmp_path):
    assert bt.load_angle_recommendations(root=str(tmp_path)) == []


def test_reads_candidates_within_the_3_week_window(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "20260713",
        [{"pitch": "This week's pitch", "angle": "A", "why_tac": "W", "source_pdf_ids": []}])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    assert len(rows) == 1
    assert rows[0]["pitch"] == "This week's pitch"
    assert rows[0]["date_iso"] == "2026-07-13"


def test_includes_folders_from_two_and_three_weeks_ago(tmp_path, monkeypatch):
    # The spec's own example: the EV piece consolidated TWO weeks of research.
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "20260713", [{"pitch": "Today", "angle": "", "why_tac": "", "source_pdf_ids": []}])
    _write_candidates(str(tmp_path), "20260629", [{"pitch": "2 weeks ago", "angle": "", "why_tac": "", "source_pdf_ids": []}])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    pitches = {r["pitch"] for r in rows}
    assert {"Today", "2 weeks ago"} <= pitches


def test_excludes_folders_older_than_the_window(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "20260713", [{"pitch": "Today", "angle": "", "why_tac": "", "source_pdf_ids": []}])
    _write_candidates(str(tmp_path), "20260501", [{"pitch": "Way too old", "angle": "", "why_tac": "", "source_pdf_ids": []}])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    pitches = {r["pitch"] for r in rows}
    assert "Way too old" not in pitches


def test_handles_backfill_prefixed_folder_names(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "backfill_20260702", [{"pitch": "Backfilled", "angle": "", "why_tac": "", "source_pdf_ids": []}])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    assert len(rows) == 1
    assert rows[0]["pitch"] == "Backfilled"
    assert rows[0]["date_iso"] == "2026-07-02"


def test_bad_json_in_one_folder_does_not_blank_the_others(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    bad_dir = tmp_path / "carousels" / "20260710"
    bad_dir.mkdir(parents=True)
    (bad_dir / "_candidates.json").write_text("{not json")
    _write_candidates(str(tmp_path), "20260713", [{"pitch": "Still readable", "angle": "", "why_tac": "", "source_pdf_ids": []}])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    assert len(rows) == 1
    assert rows[0]["pitch"] == "Still readable"


def test_fail_soft_on_top_level_list(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    d = tmp_path / "carousels" / "20260713"; d.mkdir(parents=True)
    (d / "_candidates.json").write_text(json.dumps([1, 2, 3]))
    assert bt.load_angle_recommendations(root=str(tmp_path), weeks=3) == []


def test_fail_soft_on_candidates_not_list(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    d = tmp_path / "carousels" / "20260713"; d.mkdir(parents=True)
    (d / "_candidates.json").write_text(json.dumps({"candidates": "oops"}))
    assert bt.load_angle_recommendations(root=str(tmp_path), weeks=3) == []


def test_candidate_missing_pitch_is_skipped_not_fatal(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "20260713", [
        {"angle": "no pitch here", "why_tac": "", "source_pdf_ids": []},
        {"pitch": "Has a pitch", "angle": "", "why_tac": "", "source_pdf_ids": []},
    ])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    assert len(rows) == 1 and rows[0]["pitch"] == "Has a pitch"


def _build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE emails(id INTEGER PRIMARY KEY, sender TEXT, subject TEXT, date_received TEXT, stream TEXT);"
        "CREATE TABLE pdfs(id INTEGER PRIMARY KEY, email_id INTEGER);"
        "INSERT INTO emails VALUES (10,'analyst@bank.com','Note','2026-07-10T05:00:00+00:00','bulge_bracket');"
        "INSERT INTO pdfs VALUES (555,10);")
    con.commit(); con.close()


def test_source_pdf_date_enriched_from_readonly_db(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "20260713",
        [{"pitch": "Enriched", "angle": "", "why_tac": "", "source_pdf_ids": [555]}])
    _build_db(str(tmp_path / "trading_strategy.db"))
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    assert rows[0]["source_pdf_date"].startswith("2026-07-10")


def test_absent_db_still_returns_rows(tmp_path, monkeypatch):
    _frozen_today(tmp_path, monkeypatch, "20260713")
    _write_candidates(str(tmp_path), "20260713",
        [{"pitch": "No DB needed", "angle": "", "why_tac": "", "source_pdf_ids": [1]}])
    rows = bt.load_angle_recommendations(root=str(tmp_path), weeks=3)
    assert len(rows) == 1
    assert rows[0]["source_pdf_date"] is None
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_brains_trust_research.py -v`
Expected: FAIL/ERROR on every test with `ModuleNotFoundError: No module named 'flatwhite.dashboard.brains_trust_research'`.

- [ ] **Step 3: Write the implementation.**

```python
# flatwhite/dashboard/brains_trust_research.py
"""Read the Trading Strategy project's research candidates (READ ONLY) across
the last N weeks, for the Brains Trust / Economic Scoop segment's angle picker.

Mirrors Shell Bot 2's pipeline/bulge_bracket.py reading pattern (same folder
layout, same isinstance-guard defensiveness, same read-only DB access) but
widens it: bulge_bracket.py returns only the single newest folder; Brains
Trust explicitly wants angles spanning multiple weeks (the EV tipping-point
piece consolidated two weeks of research), so this returns every candidate
from every folder inside the window.

Fails soft everywhere: a missing folder, absent candidates file, bad JSON, a
malformed individual candidate, or a locked/absent SQLite DB all degrade
gracefully rather than raising - a research outage must never block Victor
picking an angle. Never writes to, imports from, or runs the Trading Strategy
project. The one DB read opens via sqlite3's URI ?mode=ro, so this connection
cannot write even by accident.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

_DEFAULT_ROOT = os.environ.get(
    "BRAINS_TRUST_ROOT", "/Users/victornguyen/Documents/MISC/Trading Strategy/data"
)


def _folder_date(candidates_path: str) -> str | None:
    """Extract the YYYYMMDD embedded in a candidate folder's name, or None.
    Real folders are named both '20260713' and 'backfill_20260602', so match
    the 8-digit run ANYWHERE in the name, not a whole-string match (mirrors
    bulge_bracket.py's _folder_date exactly)."""
    folder = os.path.basename(os.path.dirname(candidates_path))
    m = re.search(r"(\d{8})", folder)
    return m.group(1) if m else None


def _dir_date_iso(date_digits: str) -> str:
    return f"{date_digits[0:4]}-{date_digits[4:6]}-{date_digits[6:8]}"


def _candidate_paths_within_window(root: str, weeks: int) -> list[tuple[str, str]]:
    """[(YYYYMMDD, path), ...] for every _candidates.json whose folder date
    falls within the last `weeks` weeks of now, newest first. A folder with no
    parseable date is skipped - it can't be windowed, so it's excluded rather
    than guessed at (same principle as bulge_bracket.py's dateless-folders
    handling, just applied per-folder instead of only to the single pick)."""
    hits = glob.glob(os.path.join(root, "carousels", "*", "_candidates.json"))
    if not hits:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).strftime("%Y%m%d")
    dated = [(_folder_date(p), p) for p in hits]
    dated = [(d, p) for d, p in dated if d and d >= cutoff]
    dated.sort(key=lambda dp: dp[0], reverse=True)
    return dated


def _pdf_dates(root: str, pdf_ids: set[int]) -> dict[int, tuple[str, str]]:
    """pdf_id -> (date_received, sender), best-effort from the read-only DB.
    Opens the DB in SQLite's URI read-only mode so this connection can never
    write (mirrors bulge_bracket.py's _pdf_dates)."""
    db = os.path.join(root, "trading_strategy.db")
    if not pdf_ids or not os.path.exists(db):
        return {}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
        try:
            q = ("SELECT p.id, e.date_received, e.sender FROM pdfs p "
                 "JOIN emails e ON e.id = p.email_id WHERE p.id IN (%s)"
                 % ",".join("?" * len(pdf_ids)))
            return {row[0]: (row[1], row[2]) for row in con.execute(q, tuple(pdf_ids))}
        finally:
            con.close()
    except sqlite3.Error:
        return {}


def load_angle_recommendations(
    root: str | None = None, weeks: int = 3, limit: int = 40
) -> list[dict]:
    """Recommended Brains Trust angles from the Trading Strategy research
    bank, across the last `weeks` weeks (default 3). Newest first, capped at
    `limit` rows total. Never raises."""
    root = root or _DEFAULT_ROOT
    dated_paths = _candidate_paths_within_window(root, weeks)
    if not dated_paths:
        return []

    parsed: list[tuple[str, list[dict]]] = []
    all_pdf_ids: set[int] = set()
    for date_digits, path in dated_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        cands = data.get("candidates")
        if not isinstance(cands, list):
            continue
        good = [c for c in cands if isinstance(c, dict) and (c.get("pitch") or "").strip()]
        for c in good:
            for i in (c.get("source_pdf_ids") or []):
                if isinstance(i, int):
                    all_pdf_ids.add(i)
        parsed.append((date_digits, good))

    src_dates = _pdf_dates(root, all_pdf_ids)

    rows: list[dict] = []
    for date_digits, cands in parsed:
        for c in cands:
            pitch = c["pitch"].strip()
            src_date = ""
            for i in (c.get("source_pdf_ids") or []):
                if isinstance(i, int) and i in src_dates and src_dates[i][0]:
                    src_date = max(src_date, src_dates[i][0])
            key = hashlib.sha1(f"{date_digits}:{pitch}".encode("utf-8")).hexdigest()[:16]
            rows.append({
                "id": f"angle:{key}",
                "date_iso": _dir_date_iso(date_digits),
                "pitch": pitch,
                "angle": (c.get("angle") or "").strip(),
                "why_tac": (c.get("why_tac") or "").strip(),
                "source_pdf_ids": [i for i in (c.get("source_pdf_ids") or []) if isinstance(i, int)],
                "source_pdf_date": src_date or None,
            })
    return rows[:limit]
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_brains_trust_research.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit.**

```bash
git add flatwhite/dashboard/brains_trust_research.py tests/test_brains_trust_research.py
git commit -m "Brains Trust: read-only Trading Strategy angle pool across last 3 weeks"
```

---

### Task 2: Register the `brains_trust` model-router task type + voice

**Files:**
- Modify: `flatwhite/model_router.py`
- Modify: `flatwhite/classify/prompts.py`
- Test: `tests/test_brains_trust_proceed.py` (created here, extended in Task 3)

**Interfaces:**
- Consumes: nothing new.
- Produces: `flatwhite.model_router.TEMPERATURE_BY_TASK["brains_trust"]`, `DEFAULT_MODEL_BY_TASK["brains_trust"]`, and `flatwhite.classify.prompts.BRAINS_TRUST_VOICE` (str), both consumed by Task 3's `_proceed_brains_trust`.

- [ ] **Step 1: Write the failing test.**

```python
# tests/test_brains_trust_proceed.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.model_router import TEMPERATURE_BY_TASK, DEFAULT_MODEL_BY_TASK


def test_brains_trust_task_type_is_registered():
    assert "brains_trust" in TEMPERATURE_BY_TASK
    assert 0.0 <= TEMPERATURE_BY_TASK["brains_trust"] <= 0.5  # data-led, not free-wheeling
    assert DEFAULT_MODEL_BY_TASK["brains_trust"] == "claude-sonnet-4-6"


def test_brains_trust_voice_exists_and_bans_em_dashes():
    from flatwhite.classify.prompts import BRAINS_TRUST_VOICE
    assert "Aussie Corporate" in BRAINS_TRUST_VOICE or "Flat White" in BRAINS_TRUST_VOICE
    assert "—" not in BRAINS_TRUST_VOICE  # the prompt itself must not contain an em dash
    assert "no em dash" in BRAINS_TRUST_VOICE.lower() or "em dash" in BRAINS_TRUST_VOICE.lower()
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_brains_trust_proceed.py -v`
Expected: FAIL — `KeyError`/`AssertionError` (task type not registered), `ImportError` (voice constant doesn't exist).

- [ ] **Step 3: Add the task type to `flatwhite/model_router.py`.**

Edit the two dicts (currently at lines 42-52 and 54-64):

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
    "brains_trust": 0.3,
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
    "brains_trust": "claude-sonnet-4-6",
}
```

- [ ] **Step 4: Add `BRAINS_TRUST_VOICE` to `flatwhite/classify/prompts.py`** (append after `EDITORIAL_VOICE`'s block, before `BIG_CONVERSATION_ANGLES_SYSTEM` at line 219):

```python
# ─── BRAINS TRUST / ECONOMIC SCOOP VOICE ──────────────────────────────────────
# Same segment, two names - never treat as two segments. Calibrated against
# data/beehiiv_fw_ground_truth.json's 10 real "THE BRAINS TRUST" / "THE
# ECONOMIC SCOOP" segments: 263-375 words (mean 316), broker-research-led,
# NOT the Big Conversation's editorial voice.

BRAINS_TRUST_VOICE = (
    "You are writing THE BRAINS TRUST (also called THE ECONOMIC SCOOP - same "
    "segment, two names) for The Aussie Corporate's Flat White newsletter.\n"
    "\n"
    "CORE VOICE:\n"
    "Data-led and specific, not editorial. You are consolidating real broker "
    "and economic research into a single readable narrative for a time-poor "
    "Australian corporate reader. Every claim traces to a real figure, quote, "
    "or dated data point from the research bank you were given. Never invent "
    "a number, a bank name, or a quote that isn't in the source material.\n"
    "\n"
    "STRUCTURE:\n"
    "Open with the single sharpest, most concrete finding, not a scene-setting "
    "sentence. Build the piece across 3-5 short paragraphs, each grounded in "
    "specific figures (percentages, dollar amounts, dates). Where the research "
    "bank includes a standout analyst quote, use it verbatim, attributed like "
    "'- UBS' or '- Morgan Stanley Research' on its own line, using a plain "
    "hyphen, never an em dash. Close on the practical implication for the "
    "reader, not a summary restating what was just said.\n"
    "\n"
    "LENGTH: roughly 260-380 words.\n"
    "\n"
    "LANGUAGE RULES:\n"
    "- Australian English throughout\n"
    "- No em dashes anywhere, including in quote attribution - use a plain "
    "hyphen instead (this deviates from some older published editions that "
    "used an em dash for attribution; the hyphen is the current house rule)\n"
    "- Write 'percent' as %, never spelled out\n"
    "- No filler intensifiers like 'genuinely', 'really', 'actually'\n"
    "- No theatrical framing: 'the twist', 'here's the thing', 'and that's "
    "the point'\n"
    "- No hedging: 'may', 'could possibly' - state what the research says\n"
    "\n"
    "Output ONLY the Brains Trust body text. No title. No sign-off."
)
```

- [ ] **Step 5: Run the tests to verify they pass.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_brains_trust_proceed.py -v`
Expected: 2 passed.

- [ ] **Step 6: Full-suite regression check + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -3
```
Expected: 126 passed, 8 failed (baseline 124 + these 2 new; same 8 pre-existing failures, unchanged).

```bash
git add flatwhite/model_router.py flatwhite/classify/prompts.py tests/test_brains_trust_proceed.py
git commit -m "Brains Trust: register brains_trust model-router task type + voice prompt"
```

---

### Task 3: `_proceed_brains_trust` + the angle-list endpoint

**Files:**
- Modify: `flatwhite/dashboard/api.py`
- Test: `tests/test_brains_trust_proceed.py` (append)

**Interfaces:**
- Consumes: `flatwhite.dashboard.brains_trust_research.load_angle_recommendations` (Task 1), `flatwhite.classify.prompts.BRAINS_TRUST_VOICE` (Task 2), `flatwhite.model_router.route`/`list_available_models` (already imported in `api.py`), `_safe_override` (already defined in `api.py`).
- Produces:
  - `_proceed_brains_trust(data: dict, model: str | None, custom_prompt: str | None = None) -> str` — registered into `api_proceed_section`'s `proceed_fns` dict under key `"brains_trust"`, callable via the existing `POST /api/proceed-section` with `{"section": "brains_trust", ...}` — no new generation endpoint.
  - `GET /api/brains-trust/angles -> {"angles": [...]}` — the only new HTTP route.
  - Mark-ready/edit reuses the **existing, unmodified** `GET /api/section-outputs` and `POST /api/section-output/brains_trust` (already generic across every section — no change needed here).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_brains_trust_proceed.py`):

```python
import json
from unittest.mock import patch
import flatwhite.dashboard.api as api


def _capture_route(monkeypatch):
    captured = {}
    def fake_route(task_type, prompt, system="", model_override=None):
        captured["task_type"] = task_type
        captured["prompt"] = prompt
        captured["system"] = system
        captured["model_override"] = model_override
        return "Drafted Brains Trust body."
    monkeypatch.setattr(api, "route", fake_route)
    monkeypatch.setattr(api, "list_available_models",
                         lambda: [{"id": "claude-sonnet-4-6"}])
    return captured


def test_proceed_brains_trust_calls_route_with_the_chosen_angle(monkeypatch):
    cap = _capture_route(monkeypatch)
    data = {
        "chosen_pitch": "Wholesale power prices at 5-year lows",
        "chosen_angle": "Households see no relief; an earnings cliff is coming for AGL/Origin.",
        "chosen_why_tac": "Energy bills matter to every reader.",
        "candidates_pool": [
            {"date_iso": "2026-07-13", "pitch": "Wholesale power prices at 5-year lows", "angle": "cliff coming"},
            {"date_iso": "2026-06-29", "pitch": "Unrelated pitch", "angle": "something else"},
        ],
    }
    out = api._proceed_brains_trust(data, "claude-sonnet-4-6")
    assert out == "Drafted Brains Trust body."
    assert cap["task_type"] == "brains_trust"
    assert "Wholesale power prices at 5-year lows" in cap["prompt"]
    assert "Unrelated pitch" in cap["prompt"]  # the whole pool is handed over for consolidation
    assert cap["model_override"] == "claude-sonnet-4-6"


def test_proceed_brains_trust_honours_custom_prompt(monkeypatch):
    cap = _capture_route(monkeypatch)
    out = api._proceed_brains_trust({}, None, custom_prompt="Write exactly this.")
    assert out == "Drafted Brains Trust body."
    assert cap["prompt"] == "Write exactly this."
    assert cap["task_type"] == "brains_trust"


def test_proceed_brains_trust_handles_missing_pool_gracefully(monkeypatch):
    cap = _capture_route(monkeypatch)
    out = api._proceed_brains_trust({"chosen_pitch": "Solo angle, no pool"}, None)
    assert out == "Drafted Brains Trust body."
    assert "Solo angle, no pool" in cap["prompt"]


def test_brains_trust_registered_in_proceed_fns():
    # api_proceed_section dispatches via a local dict; assert brains_trust
    # routes to the real generator rather than 400ing as "Unknown section".
    import inspect
    src = inspect.getsource(api.api_proceed_section)
    assert '"brains_trust": _proceed_brains_trust' in src or "'brains_trust': _proceed_brains_trust" in src


def test_angles_endpoint_returns_reader_output(monkeypatch):
    fake_rows = [{"id": "angle:abc", "date_iso": "2026-07-13", "pitch": "P", "angle": "A", "why_tac": "W", "source_pdf_ids": [], "source_pdf_date": None}]
    monkeypatch.setattr(
        "flatwhite.dashboard.brains_trust_research.load_angle_recommendations",
        lambda weeks=3: fake_rows,
    )
    result = api.api_brains_trust_angles()
    body = json.loads(result.body)
    assert body["angles"] == fake_rows


def test_angles_endpoint_fails_soft_on_reader_exception(monkeypatch):
    def _boom(weeks=3):
        raise RuntimeError("Trading Strategy dir unreadable")
    monkeypatch.setattr(
        "flatwhite.dashboard.brains_trust_research.load_angle_recommendations", _boom
    )
    result = api.api_brains_trust_angles()
    body = json.loads(result.body)
    assert body["angles"] == []
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_brains_trust_proceed.py -v`
Expected: FAIL — `AttributeError: module 'flatwhite.dashboard.api' has no attribute '_proceed_brains_trust'` / `api_brains_trust_angles`.

- [ ] **Step 3: Add `_proceed_brains_trust` to `flatwhite/dashboard/api.py`**, directly after `_proceed_editorial` (currently ending at line 1804, before the `# ── Proceed section endpoint ──` comment at line 1807):

```python
def _proceed_brains_trust(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    """Consolidate the angle Victor picked plus the surfaced 3-week research
    pool into a Brains Trust draft. Same (data, model, custom_prompt) -> str
    shape as every other _proceed_* function, so it plugs into proceed_fns
    unchanged.

    data: {
        "chosen_pitch": str,             # the angle Victor picked
        "chosen_angle": str,             # its supporting angle summary
        "chosen_why_tac": str,           # optional, why it matters to readers
        "candidates_pool": list[dict],   # the full window shown on screen,
                                          # each {date_iso, pitch, angle}
    }
    """
    from flatwhite.classify.prompts import BRAINS_TRUST_VOICE

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="brains_trust", prompt=custom_prompt, system=BRAINS_TRUST_VOICE, model_override=override)

    chosen_pitch = (data.get("chosen_pitch") or "").strip()
    chosen_angle = (data.get("chosen_angle") or "").strip()
    chosen_why = (data.get("chosen_why_tac") or "").strip()
    pool = data.get("candidates_pool") or []

    pool_lines = [
        f"- ({p.get('date_iso', '')}) {p.get('pitch', '')} - {p.get('angle', '')}"
        for p in pool if isinstance(p, dict) and p.get("pitch")
    ]
    pool_block = "\n".join(pool_lines) if pool_lines else "(no additional research pool supplied)"

    prompt = (
        "Write this week's Brains Trust (also called the Economic Scoop) section "
        "for the Flat White newsletter.\n\n"
        f"CHOSEN ANGLE:\n{chosen_pitch}\n{chosen_angle}\n"
        + (f"Why it matters to readers: {chosen_why}\n" if chosen_why else "")
        + "\n"
        "RESEARCH BANK FROM THE LAST 3 WEEKS (consolidate whatever is relevant "
        "to the chosen angle above; ignore anything unrelated):\n"
        f"{pool_block}\n\n"
        "Output ONLY the Brains Trust body text. No title. No sign-off. "
        "Ground every claim in the research bank; do not invent figures."
    )
    return route(task_type="brains_trust", prompt=prompt, system=BRAINS_TRUST_VOICE, model_override=override)
```

- [ ] **Step 4: Register it in `proceed_fns`** (currently lines 1827-1837):

```python
    proceed_fns = {
        "pulse": _proceed_pulse,
        "big_conversation": _proceed_big_conversation,
        "finds": _proceed_finds,
        # "thread" intentionally excluded: its tab is hidden (Victor's
        # decision), so there is no UI path left to call it. _proceed_thread
        # is left defined (unreferenced) rather than deleted, to keep this
        # change minimal.
        "off_the_clock": _proceed_off_the_clock,
        "editorial": _proceed_editorial,
        "brains_trust": _proceed_brains_trust,
    }
```

- [ ] **Step 5: Add the read-only angle-list endpoint**, directly after `# ── Section outputs ──` block's two routes (currently ending at line 1438, before the model-picker section):

```python
# ── Brains Trust angle pool (read-only Trading Strategy research bank) ──────

@app.get("/api/brains-trust/angles")
def api_brains_trust_angles() -> JSONResponse:
    """Read-only: recommended Brains Trust angles from the Trading Strategy
    research bank across the last 3 weeks. Never writes to that project;
    fails soft to an empty list on any error (missing folder, bad JSON,
    locked DB, or anything else) so a research-bank outage never blocks
    Victor picking an angle from whatever else is available."""
    from flatwhite.dashboard.brains_trust_research import load_angle_recommendations
    try:
        angles = load_angle_recommendations(weeks=3)
    except Exception:
        angles = []
    return JSONResponse({"angles": angles})
```

- [ ] **Step 6: Run the tests to verify they pass.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_brains_trust_proceed.py -v`
Expected: 8 passed (2 from Task 2 + 6 new).

- [ ] **Step 7: Full-suite regression check + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -3
```
Expected: 132 passed, 8 failed (same pre-existing 8, unchanged).

```bash
git add flatwhite/dashboard/api.py tests/test_brains_trust_proceed.py
git commit -m "Brains Trust: _proceed_brains_trust generator + GET /api/brains-trust/angles"
```

---

### Task 4: Frontend — the Brains Trust page

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `GET /api/brains-trust/angles`, `POST /api/proceed-section` (`section: "brains_trust"`), `GET /api/section-outputs`, `POST /api/section-output/brains_trust` — all already live after Tasks 1-3.
- Produces: `renderBrains(el)` — draws the full Brains Trust page into whatever container element it is passed, using the same signature every existing section renderer uses (`renderPulse(m)`, `renderEditorial(m)`, etc).

- [ ] **Step 1: Detect which nav shell is live before editing.**

```bash
cd /Users/victornguyen/Documents/MISC/FW
grep -c "var SEGMENTS" flatwhite/dashboard/static/index.html
grep -c "var NAV_ITEMS" flatwhite/dashboard/static/index.html
```
- If `var SEGMENTS` returns `1`: Increment 1's master/detail shell has landed. Wire `renderBrains` into its `S.page -> renderX` map (the `brains` id is already reserved there as a placeholder per Increment 1's plan) and delete that placeholder's "coming in a later increment" branch for `brains`.
- If `var NAV_ITEMS` returns `1` and `var SEGMENTS` returns `0` (the state confirmed on 14 Jul 2026): follow Step 2 below, which adds a nav entry to the current tab UI. Either way, `renderBrains(el)` itself (Step 3) is identical.

- [ ] **Step 2 (current-tab-UI branch): add the nav entry, load case, and dispatch case.**

Add to `NAV_ITEMS` (currently lines 395-431), after the `editorial` entry:

```javascript
  { id: "brains_trust", icon: "📈", label: "Brains Trust" },
```

Add a `loadPageData` case (currently the `switch` at line 440-499), after the `editorial` case:

```javascript
    case "brains_trust":
      if (S.brainsAngles) return Promise.resolve();
      return api("/api/brains-trust/angles").then(function(d) {
        S.brainsAngles = d.angles || [];
      }).catch(function() { S.brainsAngles = []; });
```

Add a dispatch case in `render()`'s switch (currently lines 598-604), after the `editorial` case:

```javascript
    case "brains_trust": renderBrains(m); break;
```

- [ ] **Step 3: Write `renderBrains(el)`.** Add this function block after `renderEditorial` (search for the end of the Editorial section, which closes with the render dispatch table above it):

```javascript
/* ═══════════════════════════════════════════════════════════════════════
   SECTION: THE BRAINS TRUST (= THE ECONOMIC SCOOP, one segment, two names)
   ═══════════════════════════════════════════════════════════════════════ */
var BRAINS_WORD_RANGE = [230, 390]; // padded around the 10 real editions' 263-375 word range

function _brainsBenchmarkChip(text) {
  var words = (text || "").trim().length ? text.trim().split(/\s+/).length : 0;
  var lo = BRAINS_WORD_RANGE[0], hi = BRAINS_WORD_RANGE[1];
  var inRange = words >= lo && words <= hi;
  var cls = inRange ? "chip chip-green" : "chip chip-amber";
  var label = words + " words (target " + lo + "-" + hi + ")";
  return '<span class="' + cls + '">' + esc(label) + '</span>';
}

function pickBrainsAngle(idx) {
  S.brainsChosen = S.brainsAngles[idx];
  render();
}

function draftBrainsTrust() {
  if (!S.brainsChosen) return;
  S.brainsDrafting = true;
  render();
  api("/api/proceed-section", {
    method: "POST",
    body: {
      section: "brains_trust",
      model: getModel("brains-model-select"),
      data: {
        chosen_pitch: S.brainsChosen.pitch,
        chosen_angle: S.brainsChosen.angle,
        chosen_why_tac: S.brainsChosen.why_tac,
        candidates_pool: S.brainsAngles,
      },
    },
  }).then(function(r) {
    S.brainsDrafting = false;
    if (r.output) {
      S.sectionOutputs.brains_trust = { output_text: r.output, model_used: r.model };
    }
    render();
  }).catch(function() {
    S.brainsDrafting = false;
    render();
    toast("Draft failed. Try again.", "error");
  });
}

function renderBrains(el) {
  var h = '<div class="page-lead">Pick an angle from the last 3 weeks of research. The dash consolidates it and drafts the piece.</div>';

  h += '<div class="card mb20"><div style="font-size:13px;color:var(--text-2);margin-bottom:10px;font-weight:600;">Recommended angles (last 3 weeks)</div>';
  var angles = S.brainsAngles || [];
  if (!angles.length) {
    h += '<div class="empty-state">No angles found in the research bank right now. The Friday digest email still runs independently of this list.</div>';
  } else {
    angles.forEach(function(a, i) {
      var chosen = S.brainsChosen && S.brainsChosen.id === a.id;
      h += '<div class="pick-row' + (chosen ? " picked" : "") + '" onclick="pickBrainsAngle(' + i + ')">';
      h += '<div class="pick-date">' + esc(a.date_iso) + '</div>';
      h += '<div class="pick-body"><div class="pick-pitch">' + esc(a.pitch) + '</div>';
      if (a.angle) h += '<div class="pick-angle">' + esc(a.angle) + '</div>';
      h += '</div></div>';
    });
  }
  h += '</div>';

  if (S.brainsChosen) {
    h += '<div class="card mb20"><div style="font-size:13px;color:var(--text-2);margin-bottom:10px;font-weight:600;">Chosen angle</div>';
    h += '<div class="pick-pitch">' + esc(S.brainsChosen.pitch) + '</div>';
    h += '<div style="display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap;">';
    h += modelSelect("brains-model-select");
    h += '<button class="btn btn-primary" onclick="draftBrainsTrust()"' + (S.brainsDrafting ? " disabled" : "") + '>' + (S.brainsDrafting ? "Drafting…" : "Draft") + '</button>';
    h += '</div></div>';
  }

  var out = S.sectionOutputs.brains_trust;
  if (out && out.output_text) {
    h += '<div class="card"><div style="font-size:13px;color:var(--text-2);margin-bottom:10px;font-weight:600;">Draft</div>';
    h += '<textarea id="ta-brains_trust" class="edit-textarea" rows="14">' + esc(out.output_text) + '</textarea>';
    h += '<div style="display:flex;align-items:center;gap:10px;margin-top:10px;">';
    h += '<button class="btn btn-sm btn-success" onclick="saveOutput(\'brains_trust\')">Save</button>';
    h += _brainsBenchmarkChip(out.output_text);
    h += '</div></div>';
  }

  el.innerHTML = h;
}
```

`saveOutput('brains_trust')` and the sidebar's ready/not-ready status dot for `brains_trust` are already generic (Step 4 confirms this): `saveOutput` (line 1421) already calls `POST /api/section-output/{section}` for whatever section id it is passed, and `sectionStatus`/the ready-count footer already key off `S.sectionOutputs[id].output_text` for whatever id is in `NAV_ITEMS` (or `SEGMENTS`, if Increment 1 has landed). No changes needed there for either shell.

- [ ] **Step 4: Add the two small CSS classes this page introduces** (append to the existing `<style>` block; `chip`/`chip-green`/`chip-amber` and `pick-row` do not exist yet — confirm with `grep -c "\.pick-row" flatwhite/dashboard/static/index.html` returning `0` before adding, to avoid a duplicate rule):

```css
.pick-row{display:flex;gap:12px;padding:10px 12px;border-radius:10px;cursor:pointer;border:1px solid transparent;margin-bottom:6px}
.pick-row:hover{background:rgba(0,0,0,.03)}
.pick-row.picked{border-color:var(--accent,#6c63ff);background:rgba(108,99,255,.06)}
.pick-date{width:84px;flex:none;color:var(--text-2);font-size:12px;padding-top:2px}
.pick-pitch{font-weight:600;font-size:14px}
.pick-angle{color:var(--text-2);font-size:13px;margin-top:2px}
.chip{font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px}
.chip-green{background:rgba(52,199,89,.13);color:#248a3d}
.chip-amber{background:rgba(255,159,10,.15);color:#b25e00}
```

- [ ] **Step 5: Verify (presence + manual).** Boot the dashboard:

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/                         # 200
curl -s http://127.0.0.1:8500/ | grep -c 'function renderBrains'                        # 1
curl -s http://127.0.0.1:8500/ | grep -c "brains_trust"                                 # >=1
curl -s http://127.0.0.1:8500/api/brains-trust/angles                                   # {"angles": [...]} — real Trading Strategy data if present, [] if not
```

Manual click script: open `http://127.0.0.1:8500/`; click into Brains Trust (tab or sidebar row depending on which shell is live); the page shows a lead line, then a list of angles dated across roughly the last 3 weeks (real data from `/Users/victornguyen/Documents/MISC/Trading Strategy/data/carousels`, if that machine has it mounted — otherwise the "no angles found" empty state, which must not error); click an angle to select it (highlights); "Draft" calls the model and shows a "Drafting…" state, then an editable textarea with the drafted text and a word-count benchmark chip (green inside 230-390 words, amber outside); "Save" persists it; reloading the page and revisiting Brains Trust still shows the saved draft (via `/api/section-outputs`) and the segment's status dot/pill reflects it, using the exact same generic mechanism every other segment already uses. Kill the server: `kill %1`.

- [ ] **Step 6: Python suite unchanged + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -3
```
Expected: 132 passed, 8 failed (same as end of Task 3 — this task is UI-only, no Python behaviour changes).

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "Brains Trust: angle-picker + draft + edit + benchmark chip page"
```

---

## Manual verification (whole increment, before done)

1. `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`.
2. Open Brains Trust. It shows recommended angles spanning roughly the last 3 weeks (not just the current week), read from the Trading Strategy research bank — confirm at least one angle from more than 7 days ago appears if the real data has one that old (mirrors the EV piece's real two-week consolidation).
3. Pick an angle, click Draft: a Brains Trust piece is generated in the data-led register (figures, %, attributed quotes where the source pool has them), editable in a textarea, with a word-count benchmark chip.
4. Save persists the edited text; it survives a page reload; the segment's ready/status indicator reflects it, via the same generic `section_outputs` mechanism every other segment uses (no bespoke Brains Trust storage).
5. Confirm nothing under `/Users/victornguyen/Documents/MISC/Trading Strategy/` changed: `git -C "/Users/victornguyen/Documents/MISC/Trading Strategy" status --short` shows no modifications (that repo has its own git history — this increment must show zero diff there).
6. Confirm the Friday digest is untouched: `git status --short` inside FW shows no changes to any file outside `flatwhite/dashboard/`, `flatwhite/model_router.py`, `flatwhite/classify/prompts.py`, and `tests/`; the Trading Strategy `com.tradingstrategy.weekly-digest` launchd job and its plist are untouched.
7. `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q` → 132 passed, 8 failed (same 8 pre-existing failures as the recorded baseline; net +8 passing tests from this increment, zero regressions).

Report the FW suite counts and: **"Built locally on branch `fw-control-room-brains-trust`, NOT merged, NOT deployed (FW deploy is Victor's). The Friday research digest email was not touched and keeps sending exactly as before."**
