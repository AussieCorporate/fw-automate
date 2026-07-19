"""Run a Claude skill headless from the dashboard, as a tracked background job.

The control-room lets Victor trigger Claude *skills* (big-conversation,
screenshot-sort) and beehiiv-MCP actions from the FW dashboard instead of
opening a separate Claude session. This module is the shared engine: it spawns
`claude -p "<prompt>"` via subprocess in a background thread, tracks the run in
an in-memory registry, and exposes status for the frontend to poll.

Generic on purpose: callers pass the full argv, so it is testable with a fake
command (echo/false) and never hard-codes the claude invocation. Endpoints in
api.py build the argv and the human-facing prompt.

Failure is always LOUD and CLEAN: a missing CLI, a non-zero exit, or a timeout
marks the run "failed" with a plain-English error and the captured output tail,
never a hung spinner.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid

# At most this many skill runs at once. Each is a full Claude agent (the
# big-conversation skill even fans out its own subagents), so a click storm
# must not spawn a fleet.
_MAX_CONCURRENT = 2

# Hard ceiling per run. The skill reads dozens of screenshots and drafts, so
# minutes are normal; this only catches a genuinely stuck run.
_DEFAULT_TIMEOUT_SEC = 900

# Keep only the tail of output so the registry stays small.
_OUTPUT_TAIL_CHARS = 6000

_runs: dict[str, dict] = {}
_lock = threading.Lock()


def _active_count_locked() -> int:
    return sum(1 for r in _runs.values() if r["status"] in ("queued", "running"))


def _find_active_for_key_locked(key: str) -> str | None:
    for run_id, r in _runs.items():
        if r["key"] == key and r["status"] in ("queued", "running"):
            return run_id
    return None


def start_run(kind: str, key: str, argv: list[str], cwd: str,
              *, timeout: int = _DEFAULT_TIMEOUT_SEC, env: dict | None = None,
              on_complete=None, success_marker: str | None = None,
              marker_fail_error: str | None = None, now: float | None = None) -> tuple[str, bool]:
    """Start a background run. Returns (run_id, started_new).

    - Dedupes by ``key``: if a run for this key is already active, returns that
      run's id with started_new=False (a double-click just re-attaches).
    - Raises RuntimeError if the global concurrency cap is hit.
    - ``on_complete(record)`` (optional) is called with the final run record once
      the run finishes (done or failed), so a caller can react to the output
      (e.g. parse a printed draft id). Never raises into the run thread.
    """
    now = now if now is not None else time.time()
    with _lock:
        existing = _find_active_for_key_locked(key)
        if existing:
            return existing, False
        if _active_count_locked() >= _MAX_CONCURRENT:
            raise RuntimeError(
                "Another skill run is already in progress. Wait for it to finish, "
                "then try again."
            )
        run_id = uuid.uuid4().hex[:12]
        _runs[run_id] = {
            "id": run_id, "kind": kind, "key": key, "status": "queued",
            "started_at": now, "ended_at": None, "output": "",
            "error": None, "returncode": None,
        }
    thread = threading.Thread(
        target=_execute,
        args=(run_id, argv, cwd, timeout, env, on_complete,
              success_marker, marker_fail_error),
        daemon=True)
    thread.start()
    return run_id, True


def _set(run_id: str, **fields) -> None:
    with _lock:
        if run_id in _runs:
            _runs[run_id].update(fields)


def _execute(run_id: str, argv: list[str], cwd: str, timeout: int,
             env: dict | None, on_complete=None,
             success_marker: str | None = None,
             marker_fail_error: str | None = None) -> None:
    try:
        _execute_inner(run_id, argv, cwd, timeout, env)
        # A run can exit 0 having reasoned to a clean stop WITHOUT doing the
        # work (e.g. the beehiiv connector wasn't attached, so the insert never
        # happened). If a success marker is required and it's absent, the run
        # did NOT succeed - flip it to failed with a plain-English reason so the
        # dashboard never shows a false "done".
        if success_marker:
            r = get_run(run_id)
            if r and r["status"] == "done" and success_marker not in (r["output"] or ""):
                _set(run_id, status="failed",
                     error=marker_fail_error or "The run finished without completing the task.")
    finally:
        if on_complete is not None:
            try:
                on_complete(get_run(run_id))
            except Exception:  # noqa: BLE001 - a callback must never break the run thread
                pass


def _execute_inner(run_id: str, argv: list[str], cwd: str, timeout: int,
                   env: dict | None) -> None:
    _set(run_id, status="running")
    run_env = {**os.environ, **(env or {})}
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=run_env,
        )
    except FileNotFoundError:
        _set(run_id, status="failed", ended_at=time.time(),
             error="Claude Code (the `claude` command) was not found on this "
                   "Mac, so the dashboard can't run the skill for you.")
        return
    except Exception as exc:  # noqa: BLE001
        _set(run_id, status="failed", ended_at=time.time(), error=str(exc))
        return

    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        _set(run_id, status="failed", ended_at=time.time(),
             error=f"The run took longer than {timeout // 60} minutes and was "
                   "stopped. Try again, or run the skill by hand.",
             output=(out or "")[-_OUTPUT_TAIL_CHARS:])
        return

    rc = proc.returncode
    tail = (out or "")[-_OUTPUT_TAIL_CHARS:]
    if rc == 0:
        _set(run_id, status="done", ended_at=time.time(), returncode=0, output=tail)
    else:
        # A non-zero exit with "not logged in" / auth wording surfaces plainly.
        low = tail.lower()
        if "not logged in" in low or "unauthor" in low or "authentication" in low:
            msg = ("Claude Code isn't logged in on this Mac, so the run couldn't "
                   "start. Log in (claude) and try again.")
        else:
            msg = f"The skill run failed (exit code {rc}). See the details below."
        _set(run_id, status="failed", ended_at=time.time(), returncode=rc,
             error=msg, output=tail)


def get_run(run_id: str) -> dict | None:
    """Snapshot of a run for polling, or None if unknown."""
    with _lock:
        r = _runs.get(run_id)
        return dict(r) if r else None


def get_active_by_key(key: str) -> dict | None:
    """The active (queued/running) run for a key, or None. Lets the frontend
    reconnect to a job still in progress after the user navigated away and back,
    so it never looks like the run 'disappeared'."""
    with _lock:
        for r in _runs.values():
            if r["key"] == key and r["status"] in ("queued", "running"):
                return dict(r)
    return None


def _reset_for_tests() -> None:
    with _lock:
        _runs.clear()
