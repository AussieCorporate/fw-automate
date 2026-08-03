# Brains Trust Refresh Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Refresh" button to the Brains Trust screen that pulls new research into the angle pool on demand, without turning the retired overnight `tac-carousels` job back on and without sending any email.

**Architecture:** A new pure-logic module (`brains_trust_refresh.py`) decides *whether* a refresh is needed and *what command* would run it, by scanning the same `data/carousels/*/_candidates.json` folders `brains_trust_research.py` already reads. The actual subprocess execution is delegated to the dashboard's existing generic background-job engine, `flatwhite/dashboard/skill_runner.py` (already used for the Big Conversation and screenshot-sort skill runs) — this plan adds **zero** new process-management code, it only builds the argv/cwd and wires up one POST endpoint. The frontend reuses the existing `GET /api/skill-run/{run_id}` polling endpoint verbatim; no new status endpoint is needed.

**Tech Stack:** Python 3.12 (FastAPI dashboard backend), vanilla JS (no framework) frontend in `flatwhite/dashboard/static/index.html`, pytest + `fastapi.testclient.TestClient`.

## Global Constraints

- Never modify `flatwhite/dashboard/brains_trust_research.py`'s read path — it already reads fresh from disk on every call and needs no changes (spec: "Any change to `brains_trust_research.py`'s read path" is out of scope).
- Never re-enable the `com.tradingstrategy.tac-carousels` launchd job or its email send. This plan only invokes `scripts/backfill_tac_carousels.py`, which never sends email (per its own docstring) and is unrelated to the launchd job's registration state.
- Cap any single refresh at 21 days behind (three weeks — matches the angle pool's own read window and bounds Anthropic API spend per click). A gap larger than that requires clicking Refresh more than once.
- Reuse `flatwhite/dashboard/skill_runner.py` for all subprocess/background-thread/dedupe logic. Do not write a second bespoke `_state`/`_lock` pair (the codebase already has one precedent for that, `_scrape_all_state` in `api.py`; the newer `skill_runner` engine, used for Big Conversation and screenshot-sort, is the more general and better-tested tool and is what this feature should build on).
- The interpreter for the subprocess call is the exact one the retired `tac-carousels` launchd job used: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`. The Trading Strategy project's own `.venv` is missing `python-dotenv` (verified 3 Aug 2026), so it cannot run `scripts/backfill_tac_carousels.py`.

---

### Task 1: `brains_trust_refresh.py` — decide if/what to refresh

**Files:**
- Create: `flatwhite/dashboard/brains_trust_refresh.py`
- Test: `tests/test_brains_trust_refresh.py`

**Interfaces:**
- Consumes: nothing from other tasks (this is the first task).
- Produces: `build_refresh_command(data_root: str | None = None) -> tuple[list[str], str, int] | None`, used by Task 2's endpoint. Returns `None` when already up to date; otherwise `(argv, cwd, days_requested)` where `argv` is a full command list ready for `subprocess`/`skill_runner.start_run`, `cwd` is the Trading Strategy project directory (a string), and `days_requested` is the (possibly capped) integer passed as `--days`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_brains_trust_refresh.py`:

```python
import os, json
from datetime import datetime
import flatwhite.dashboard.brains_trust_refresh as btr


def _write_candidates(data_root, folder):
    d = os.path.join(data_root, "carousels", folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "_candidates.json"), "w") as f:
        json.dump({"candidates": []}, f)


def _frozen_today(monkeypatch, iso_date):
    """Freeze btr's notion of 'now' so day-math is deterministic. Mirrors
    tests/test_brains_trust_research.py's _frozen_today helper."""
    fixed = datetime.strptime(iso_date, "%Y%m%d")

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed

    monkeypatch.setattr(btr, "datetime", _FixedDateTime)


def test_up_to_date_returns_none(tmp_path, monkeypatch):
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260803")
    assert btr.build_refresh_command(data_root=data_root) is None


def test_returns_command_for_days_behind(tmp_path, monkeypatch):
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260729")  # 5 days behind
    result = btr.build_refresh_command(data_root=data_root)
    assert result is not None
    argv, cwd, days = result
    assert days == 5
    assert argv == [btr._PYTHON_BIN, "scripts/backfill_tac_carousels.py", "--days", "5"]
    assert cwd == str(tmp_path)  # parent of the data root


def test_caps_at_max_days(tmp_path, monkeypatch):
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260101")  # far more than the cap
    _, _, days = btr.build_refresh_command(data_root=data_root)
    assert days == btr._MAX_DAYS_PER_REFRESH


def test_no_folders_at_all_defaults_to_cap(tmp_path, monkeypatch):
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    os.makedirs(data_root, exist_ok=True)
    _, _, days = btr.build_refresh_command(data_root=data_root)
    assert days == btr._MAX_DAYS_PER_REFRESH


def test_missing_carousels_dir_defaults_to_cap(tmp_path, monkeypatch):
    _frozen_today(monkeypatch, "20260803")
    _, _, days = btr.build_refresh_command(data_root=str(tmp_path / "nope"))
    assert days == btr._MAX_DAYS_PER_REFRESH


def test_mixed_prefix_folders_picks_newest_regardless_of_prefix(tmp_path, monkeypatch):
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260710")
    _write_candidates(data_root, "backfill_20260729")  # newer, backfill-prefixed
    _, _, days = btr.build_refresh_command(data_root=data_root)
    assert days == 5  # counted from 20260729, not 20260710
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_brains_trust_refresh.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'flatwhite.dashboard.brains_trust_refresh'`

- [ ] **Step 3: Write the implementation**

Create `flatwhite/dashboard/brains_trust_refresh.py`:

```python
"""Decide whether the Brains Trust angle pool needs topping up, and build the
command that would do it.

The angle pool (brains_trust_research.py) reads data/carousels/*/_candidates.json
from the Trading Strategy project. Those files are normally written by the
tac-carousels launchd job — but that job was deliberately retired 20 Jul 2026
(carousel-making moved to the Pick & Scroll Instagram desk) and Victor decided
3 Aug 2026 to keep it off rather than resume its separate email. This module
is the manual alternative: it runs the same catch-up script
(scripts/backfill_tac_carousels.py) the retired job used, on demand, capped so
a stale pool can't turn into an unbounded Anthropic API bill in one click.

Read-only until build_refresh_command's caller actually runs the returned
command - this module itself never spawns a process or writes a file.
"""
from __future__ import annotations

import glob
import os
import re
from datetime import datetime, timezone

# Same env var and default as brains_trust_research.py - both modules must
# agree on where the research bank lives.
_DEFAULT_DATA_ROOT = os.environ.get(
    "BRAINS_TRUST_ROOT", "/Users/victornguyen/Documents/MISC/Trading Strategy/data"
)

# The retired tac-carousels launchd job's interpreter. The Trading Strategy
# project's own .venv is missing python-dotenv (verified 3 Aug 2026), so it
# can't run the backfill script - this is the one that actually has the deps.
_PYTHON_BIN = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

# Three weeks - matches the angle pool's own read window (weeks=3) and bounds
# how much a single click can spend on the Anthropic API.
_MAX_DAYS_PER_REFRESH = 21


def _folder_date(candidates_path: str) -> str | None:
    """Extract the YYYYMMDD embedded in a candidate folder's name, or None.
    Deliberately mirrors brains_trust_research._folder_date's regex (same
    real folder-naming quirk: 'YYYYMMDD' and 'backfill_YYYYMMDD' both occur)
    rather than importing that private helper across module boundaries."""
    folder = os.path.basename(os.path.dirname(candidates_path))
    m = re.search(r"(\d{8})", folder)
    return m.group(1) if m else None


def _newest_known_date(data_root: str) -> str | None:
    hits = glob.glob(os.path.join(data_root, "carousels", "*", "_candidates.json"))
    dates = [d for d in (_folder_date(p) for p in hits) if d]
    return max(dates) if dates else None


def build_refresh_command(
    data_root: str | None = None,
) -> tuple[list[str], str, int] | None:
    """(argv, cwd, days_requested) to catch the angle pool up, or None if it's
    already current. days_requested is capped at _MAX_DAYS_PER_REFRESH; a pool
    with no research at all yet is treated as fully stale (the cap)."""
    root = data_root or _DEFAULT_DATA_ROOT
    newest = _newest_known_date(root)
    if newest is None:
        days = _MAX_DAYS_PER_REFRESH
    else:
        newest_date = datetime.strptime(newest, "%Y%m%d").date()
        today = datetime.now(timezone.utc).date()
        days = min(max(0, (today - newest_date).days), _MAX_DAYS_PER_REFRESH)

    if days <= 0:
        return None

    project_root = os.path.dirname(root.rstrip(os.sep))
    argv = [_PYTHON_BIN, "scripts/backfill_tac_carousels.py", "--days", str(days)]
    return argv, project_root, days
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_brains_trust_refresh.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/brains_trust_refresh.py tests/test_brains_trust_refresh.py
git commit -m "Brains Trust: build the on-demand research catch-up command"
```

---

### Task 2: `POST /api/brains-trust/refresh` endpoint

**Files:**
- Modify: `flatwhite/dashboard/api.py` (add route immediately after the existing `api_brains_trust_angles` function, ~line 1770, in the "Brains Trust angle pool" section)
- Test: `tests/test_brains_trust_refresh.py` (append)

**Interfaces:**
- Consumes: `brains_trust_refresh.build_refresh_command` (Task 1); `flatwhite.dashboard.skill_runner.start_run(kind: str, key: str, argv: list[str], cwd: str, *, timeout: int = 900) -> tuple[str, bool]` and the existing `GET /api/skill-run/{run_id}` endpoint (both already exist in this codebase, unchanged).
- Produces: `POST /api/brains-trust/refresh` — JSON responses of three shapes:
  - `{"ran": False, "reason": "up_to_date"}` (200) — nothing to do.
  - `{"ran": True, "run_id": str, "started": bool, "days_requested": int}` (200) — a catch-up is running (or already was, if `started` is False from a double-click).
  - `{"error": str}` (429) — the global skill-run concurrency cap was hit (mirrors the existing Big Conversation endpoint's handling of the same `RuntimeError`).
  Poll progress via the pre-existing `GET /api/skill-run/{run_id}`, which already returns `{"id", "kind", "status", "error", "output_tail"}` — no new status endpoint is added.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_brains_trust_refresh.py`:

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
import flatwhite.dashboard.api as api_module


def test_refresh_endpoint_reports_up_to_date():
    with patch(
        "flatwhite.dashboard.brains_trust_refresh.build_refresh_command",
        return_value=None,
    ):
        client = TestClient(api_module.app)
        resp = client.post("/api/brains-trust/refresh")
    assert resp.status_code == 200
    assert resp.json() == {"ran": False, "reason": "up_to_date"}


def test_refresh_endpoint_starts_a_run():
    with patch(
        "flatwhite.dashboard.brains_trust_refresh.build_refresh_command",
        return_value=(["echo", "hi"], "/tmp", 5),
    ), patch(
        "flatwhite.dashboard.skill_runner.start_run",
        return_value=("run123", True),
    ) as mock_start:
        client = TestClient(api_module.app)
        resp = client.post("/api/brains-trust/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ran": True, "run_id": "run123", "started": True, "days_requested": 5}
    mock_start.assert_called_once_with(
        "brains-trust-refresh", "brains-trust-refresh",
        ["echo", "hi"], cwd="/tmp", timeout=1800,
    )


def test_refresh_endpoint_429s_when_concurrency_cap_hit():
    with patch(
        "flatwhite.dashboard.brains_trust_refresh.build_refresh_command",
        return_value=(["echo", "hi"], "/tmp", 5),
    ), patch(
        "flatwhite.dashboard.skill_runner.start_run",
        side_effect=RuntimeError("Another skill run is already in progress."),
    ):
        client = TestClient(api_module.app)
        resp = client.post("/api/brains-trust/refresh")
    assert resp.status_code == 429
    assert "already in progress" in resp.json()["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_brains_trust_refresh.py -v -k refresh_endpoint`
Expected: FAIL — `404 Not Found` (route doesn't exist yet)

- [ ] **Step 3: Write the implementation**

In `flatwhite/dashboard/api.py`, immediately after the existing `api_brains_trust_angles` function (ends ~line 1770, right before the `api_brains_trust_email_sources` route):

```python
@app.post("/api/brains-trust/refresh")
def api_brains_trust_refresh() -> JSONResponse:
    """Manually catch the angle pool up with new research, in the background.
    Never turns the retired tac-carousels launchd job back on and never sends
    email - it only runs the same catch-up script that job used to run.
    Poll progress via the existing GET /api/skill-run/{run_id}."""
    from flatwhite.dashboard import brains_trust_refresh as _btr

    built = _btr.build_refresh_command()
    if built is None:
        return JSONResponse({"ran": False, "reason": "up_to_date"})
    argv, cwd, days = built
    try:
        run_id, started = _skill_runner.start_run(
            "brains-trust-refresh", "brains-trust-refresh", argv,
            cwd=cwd, timeout=1800,
        )
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=429)
    return JSONResponse({
        "ran": True, "run_id": run_id, "started": started, "days_requested": days,
    })
```

Note: `_skill_runner` is already imported at module level elsewhere in `api.py` (`from flatwhite.dashboard import skill_runner as _skill_runner`, ~line 2946) — Python resolves this fine since the whole module finishes loading before any request is served, so no new import is needed here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_brains_trust_refresh.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/api.py tests/test_brains_trust_refresh.py
git commit -m "Brains Trust: add POST /api/brains-trust/refresh endpoint"
```

---

### Task 3: Frontend "Refresh" button

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `POST /api/brains-trust/refresh` and `GET /api/skill-run/{run_id}` (Task 2, and pre-existing respectively).
- Produces: nothing consumed by later tasks (final task in this plan).

- [ ] **Step 1: Add refresh-run state**

In the `S` object literal, right after the existing `brainsAngles` line (~line 364):

```js
  brainsAngles: null,        // [{id, date_iso, pitch, angle, why_tac}, ...] from the research bank
  brainsRefreshRun: null,    // {status: "queued"|"running"|"failed", run_id, error} while a manual refresh is in flight
```

- [ ] **Step 2: Add the button to the picker header**

In `renderBrainsPicker()` (~line 1168), replace:

```js
  h += '<div style="font-size:13px;color:var(--text-2);margin-bottom:4px;font-weight:600;">Recommended angles (last 3 weeks)</div>';
```

with:

```js
  var _refreshing = S.brainsRefreshRun && (S.brainsRefreshRun.status === "queued" || S.brainsRefreshRun.status === "running");
  h += '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px;">';
  h += '<div style="font-size:13px;color:var(--text-2);font-weight:600;">Recommended angles (last 3 weeks)</div>';
  h += '<button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;" onclick="runBrainsRefresh()"' + (_refreshing ? ' disabled' : '') + '>' + (_refreshing ? "Refreshing…" : "Refresh") + '</button>';
  h += '</div>';
  if (S.brainsRefreshRun && S.brainsRefreshRun.status === "failed") {
    h += '<div style="font-size:11px;color:var(--warn,#b26a00);margin-bottom:8px;">Refresh failed: ' + esc(S.brainsRefreshRun.error || "unknown error") + '</div>';
  }
```

- [ ] **Step 3: Add the run + poll functions**

Immediately after the existing `pollBigConvRun` function (~line 1809), add:

```js
function runBrainsRefresh() {
  S.brainsRefreshRun = { status: "queued", run_id: null, error: null };
  render();
  api("/api/brains-trust/refresh", { method: "POST" })
    .then(function(d) {
      if (!d.ran) {
        S.brainsRefreshRun = null;
        render();
        showToast("Already up to date", "success");
        return;
      }
      S.brainsRefreshRun = { status: "running", run_id: d.run_id, error: null };
      render();
      pollBrainsRefreshRun(d.run_id);
    })
    .catch(function(e) {
      S.brainsRefreshRun = { status: "failed", run_id: null, error: e.message };
      render();
    });
}

function pollBrainsRefreshRun(runId) {
  api("/api/skill-run/" + encodeURIComponent(runId))
    .then(function(r) {
      if (!S.brainsRefreshRun) return;  // user navigated away
      if (r.status === "done") {
        S.brainsRefreshRun = null;
        S.brainsAngles = null;
        loadPageData("brains_trust").then(function() {
          var angles = S.brainsAngles || [];
          var newest = angles.length ? angles[0].date_iso : null;
          showToast(
            newest
              ? "Pulled research through " + newest + " — " + angles.length + " angle" + (angles.length === 1 ? "" : "s") + " now available"
              : "Refreshed, but no angles found",
            "success"
          );
          render();
        });
      } else if (r.status === "failed") {
        S.brainsRefreshRun = { status: "failed", run_id: runId, error: r.error };
        render();
      } else {
        setTimeout(function() { pollBrainsRefreshRun(runId); }, 3000);
      }
    })
    .catch(function() {
      setTimeout(function() { pollBrainsRefreshRun(runId); }, 4000);  // transient, keep polling
    });
}
```

- [ ] **Step 4: Manual verification**

Run: `cd ~/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500`

Open http://localhost:8500/, navigate to Brains Trust, and confirm:
1. A "Refresh" button appears next to "Recommended angles (last 3 weeks)".
2. Clicking it shows "Refreshing…" (disabled) and the button re-enables once the backend responds `done` or `failed`.
3. `curl -s -X POST http://localhost:8500/api/brains-trust/refresh | python3 -m json.tool` returns either `{"ran": false, "reason": "up_to_date"}` or a `run_id` — confirm it matches the actual state of `~/Documents/MISC/Trading\ Strategy/data/carousels/`.
4. If a real run is triggered, tail `~/Documents/MISC/Trading Strategy/data/carousels/` and confirm new `backfill_YYYYMMDD` folders appear, and that `GET /api/brains-trust/angles` reflects them once the run reports `done`.

Stop the server (Ctrl-C) when done.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "Brains Trust: add manual Refresh button, polls the new catch-up run"
```

---

## Self-Review Notes

- **Spec coverage:** `_days_behind` logic (Task 1), background run + no-email guarantee (Tasks 1-2, via reusing `skill_runner` + the pre-existing email-free `backfill_tac_carousels.py`), 21-day cap (Task 1), button + polling + toasts + failure handling (Task 3), "already up to date" short-circuit (Tasks 1-3) — all covered. The spec's own `GET /api/brains-trust/refresh/status` endpoint was superseded during planning by reusing the pre-existing generic `GET /api/skill-run/{run_id}` (discovered while mapping the file structure) — same information, no new endpoint to maintain, and it already handles reconnect-after-navigation via `skill_runner`'s dedupe-by-key.
- **Type consistency:** `build_refresh_command` return shape (`tuple[list[str], str, int] | None`) is used identically in Task 1's tests, Task 2's endpoint, and Task 2's tests.
- **No placeholders:** all steps contain complete, runnable code.
