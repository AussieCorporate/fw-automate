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
