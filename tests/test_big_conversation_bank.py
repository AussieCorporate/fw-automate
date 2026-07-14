"""Tests for flatwhite/dashboard/big_conversation_bank.py — the read-only
filesystem layer over the Instagram DM screenshotter's output/ folder.

No real Claude/network calls: every test builds a fake directory tree
under tmp_path and monkeypatches
big_conversation_bank.INSTAGRAM_OUTPUT_DIR to point at it. The real
Instagram project directory is never read by these tests.
"""
from __future__ import annotations

from pathlib import Path

import flatwhite.dashboard.big_conversation_bank as bcb


def _make_topic(root: Path, name: str, n_pngs: int = 3, processed: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True)
    for i in range(n_pngs):
        (d / f"Person_{i}.png").write_bytes(b"fake")
    if processed:
        assets = d / bcb.ASSETS_DIRNAME
        assets.mkdir()
        (assets / "p1_1_Person_0.png").write_bytes(b"fake")
    return d


def test_list_topic_folders_returns_empty_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path / "does-not-exist")
    assert bcb.list_topic_folders() == []


def test_list_topic_folders_excludes_junk_and_utility_names(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office")
    _make_topic(tmp_path, "Rubbish")
    _make_topic(tmp_path, "MISC Stand alone")
    _make_topic(tmp_path, "Redundancies & Breaking News")
    _make_topic(tmp_path, "untitled folder")
    _make_topic(tmp_path, "DONE - Office Shoes")
    _make_topic(tmp_path, "INCOMPLETE - Office Attendance Bonus")
    (tmp_path / "_work").mkdir()
    (tmp_path / "_SPILLOVER hold").mkdir()

    names = {t["topic"] for t in bcb.list_topic_folders()}
    assert names == {"Kids in the Office"}


def test_list_topic_folders_counts_replies_and_processed_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office", n_pngs=5, processed=True)
    _make_topic(tmp_path, "Career Pivoting", n_pngs=8, processed=False)

    topics = {t["topic"]: t for t in bcb.list_topic_folders()}
    # The extra PNG copied into _BIG_CONVERSATION_assets must not be
    # double-counted as a separate submission.
    assert topics["Kids in the Office"]["reply_count"] == 5
    assert topics["Kids in the Office"]["processed"] is True
    assert topics["Career Pivoting"]["reply_count"] == 8
    assert topics["Career Pivoting"]["processed"] is False


def test_list_topic_folders_ignores_files_at_output_root(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office")
    (tmp_path / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text("piece text")
    (tmp_path / "_sort_session12_manifest.tsv").write_text("tsv")

    names = {t["topic"] for t in bcb.list_topic_folders()}
    assert names == {"Kids in the Office"}
