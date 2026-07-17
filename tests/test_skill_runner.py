"""Headless skill runner: status transitions, dedupe, concurrency, failure."""

import time

import flatwhite.dashboard.skill_runner as sr


def setup_function():
    sr._reset_for_tests()


def _wait(run_id, want=("done", "failed"), timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        r = sr.get_run(run_id)
        if r and r["status"] in want:
            return r
        time.sleep(0.02)
    return sr.get_run(run_id)


def test_successful_run_reports_done_with_output():
    run_id, started = sr.start_run("test", "k1", ["echo", "hello-skill"], cwd=".")
    assert started
    r = _wait(run_id)
    assert r["status"] == "done"
    assert r["returncode"] == 0
    assert "hello-skill" in r["output"]
    assert r["error"] is None


def test_nonzero_exit_reports_failed():
    run_id, _ = sr.start_run("test", "k2", ["false"], cwd=".")
    r = _wait(run_id)
    assert r["status"] == "failed"
    assert r["returncode"] != 0
    assert "failed" in r["error"].lower()


def test_missing_command_fails_cleanly():
    run_id, _ = sr.start_run("test", "k3", ["this-command-does-not-exist-xyz"], cwd=".")
    r = _wait(run_id)
    assert r["status"] == "failed"
    assert "claude" in r["error"].lower() or "not found" in r["error"].lower()


def test_timeout_marks_failed():
    run_id, _ = sr.start_run("test", "k4", ["sleep", "5"], cwd=".", timeout=1)
    r = _wait(run_id, timeout=6)
    assert r["status"] == "failed"
    assert "minute" in r["error"].lower() or "stopped" in r["error"].lower()


def test_dedupe_by_key_returns_same_run():
    # A long-running command so the first run is still active on the second call.
    r1, started1 = sr.start_run("test", "same-key", ["sleep", "2"], cwd=".")
    r2, started2 = sr.start_run("test", "same-key", ["sleep", "2"], cwd=".")
    assert started1 is True
    assert started2 is False  # re-attached, not a new run
    assert r1 == r2


def test_concurrency_cap_raises():
    sr.start_run("test", "a", ["sleep", "2"], cwd=".")
    sr.start_run("test", "b", ["sleep", "2"], cwd=".")
    try:
        sr.start_run("test", "c", ["sleep", "2"], cwd=".")
        raised = False
    except RuntimeError as exc:
        raised = "progress" in str(exc).lower()
    assert raised  # third concurrent run is rejected


def test_get_unknown_run_returns_none():
    assert sr.get_run("nope") is None


def test_auth_failure_message_is_plain(monkeypatch):
    # Simulate a non-zero exit whose output looks like an auth failure.
    run_id, _ = sr.start_run(
        "test", "auth",
        ["sh", "-c", "echo 'Error: not logged in'; exit 1"], cwd=".")
    r = _wait(run_id)
    assert r["status"] == "failed"
    assert "logged in" in r["error"].lower()
