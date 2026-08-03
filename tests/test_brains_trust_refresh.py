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
    # Newest folder is "today" by naive subtraction, which is already <= 0
    # after the -1 day-math fix (the script would never produce a "today"
    # folder anyway - see test_folder_dated_yesterday_is_already_up_to_date
    # below for the more realistic case).
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260803")
    assert btr.build_refresh_command(data_root=data_root) is None


def test_folder_dated_yesterday_is_already_up_to_date(tmp_path, monkeypatch):
    # Regression test for the day-math off-by-one: scripts/backfill_tac_carousels.py
    # deliberately skips "today" and only ever fills in yesterday and earlier, so
    # a pool whose newest folder is already yesterday is fully caught up as far
    # as this script can ever get it - even though (today - yesterday) is
    # nominally 1 day. This must return None, not a command requesting --days 1
    # (which would just regenerate the same "yesterday" folder forever and make
    # "already up to date" unreachable in real production use).
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260802")  # exactly yesterday relative to frozen "today"
    assert btr.build_refresh_command(data_root=data_root) is None


def test_returns_command_for_days_behind(tmp_path, monkeypatch):
    data_root = str(tmp_path / "data")
    _frozen_today(monkeypatch, "20260803")
    _write_candidates(data_root, "20260729")  # naively 5 days behind, but the
    # script skips "today" so the correct request is one less: 4.
    result = btr.build_refresh_command(data_root=data_root)
    assert result is not None
    argv, cwd, days = result
    assert days == 4
    assert argv == [btr._PYTHON_BIN, "-m", "scripts.backfill_tac_carousels", "--days", "4"]
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
    assert days == 4  # counted from 20260729 (naively 5 days behind, minus 1
    # for the script's "skip today" behavior), not 20260710


from unittest.mock import patch
from fastapi.testclient import TestClient
import flatwhite.dashboard.api as api_module


def test_refresh_endpoint_reports_up_to_date():
    with patch(
        "flatwhite.dashboard.brains_trust_refresh.build_refresh_command",
        return_value=None,
    ), patch(
        # Unused guard: the endpoint short-circuits before reaching start_run
        # when build_refresh_command returns None. Patching it anyway stops a
        # future refactor from silently launching the real subprocess during
        # pytest if that short-circuit ever regresses.
        "flatwhite.dashboard.skill_runner.start_run",
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
        ["echo", "hi"], cwd="/tmp", timeout=3600,
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


def test_refresh_status_endpoint_reports_inactive_when_no_run():
    with patch(
        "flatwhite.dashboard.skill_runner.get_active_by_key",
        return_value=None,
    ):
        client = TestClient(api_module.app)
        resp = client.get("/api/brains-trust/refresh/status")
    assert resp.status_code == 200
    assert resp.json() == {"active": False, "run_id": None, "status": None}


def test_refresh_status_endpoint_reports_active_run():
    with patch(
        "flatwhite.dashboard.skill_runner.get_active_by_key",
        return_value={"id": "run123", "status": "running"},
    ):
        client = TestClient(api_module.app)
        resp = client.get("/api/brains-trust/refresh/status")
    assert resp.status_code == 200
    assert resp.json() == {"active": True, "run_id": "run123", "status": "running"}
