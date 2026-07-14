"""Tests for flatwhite.dashboard.inside_track — read-only access to the
Instagram screenshotter's Inside Track (gossip/redundancy) folder.

These tests never touch the real screenshotter path; every fixture builds
its own tmp_path tree.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from flatwhite.dashboard.inside_track import (
    INSIDE_TRACK_FOLDER_CANDIDATES,
    find_inside_track_folder,
    list_inside_track_submissions,
    resolve_inside_track_image,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG-ish bytes, content unused


def test_find_inside_track_folder_prefers_new_name(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "a.png")
    _touch(tmp_path / "Redundancies & Breaking News" / "b.png")
    found = find_inside_track_folder(tmp_path)
    assert found == tmp_path / "_INSIDE_TRACK"


def test_find_inside_track_folder_falls_back_to_legacy_name(tmp_path):
    _touch(tmp_path / "Redundancies & Breaking News" / "b.png")
    found = find_inside_track_folder(tmp_path)
    assert found == tmp_path / "Redundancies & Breaking News"


def test_find_inside_track_folder_none_when_absent(tmp_path):
    _touch(tmp_path / "Some Other Topic" / "c.png")
    assert find_inside_track_folder(tmp_path) is None


def test_find_inside_track_folder_none_when_base_dir_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert find_inside_track_folder(missing) is None


def test_list_inside_track_submissions_returns_sorted_images_only(tmp_path):
    folder = tmp_path / "_INSIDE_TRACK"
    _touch(folder / "Zoe_0002.png")
    _touch(folder / "adam_0001.jpg")
    _touch(folder / "notes.txt")  # not an image — excluded
    (folder / "subdir").mkdir()   # a directory — excluded, not a file
    subs = list_inside_track_submissions(tmp_path)
    filenames = [s["filename"] for s in subs]
    assert filenames == ["adam_0001.jpg", "Zoe_0002.png"]  # case-insensitive sort
    assert all(s["folder"] == "_INSIDE_TRACK" for s in subs)


def test_list_inside_track_submissions_empty_when_folder_missing(tmp_path):
    assert list_inside_track_submissions(tmp_path) == []


def test_resolve_inside_track_image_returns_path_for_valid_file(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "Zoe_0002.png")
    resolved = resolve_inside_track_image(tmp_path, "Zoe_0002.png")
    assert resolved == (tmp_path / "_INSIDE_TRACK" / "Zoe_0002.png").resolve()


def test_resolve_inside_track_image_blocks_path_traversal(tmp_path):
    secret = tmp_path / "secret.png"
    _touch(secret)
    _touch(tmp_path / "_INSIDE_TRACK" / "a.png")
    assert resolve_inside_track_image(tmp_path, "../secret.png") is None
    assert resolve_inside_track_image(tmp_path, "../../etc/passwd") is None
    assert resolve_inside_track_image(tmp_path, "/etc/passwd") is None


def test_resolve_inside_track_image_none_for_missing_file(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "a.png")
    assert resolve_inside_track_image(tmp_path, "does-not-exist.png") is None


def test_resolve_inside_track_image_none_for_non_image_file(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "readme.txt")
    assert resolve_inside_track_image(tmp_path, "readme.txt") is None
