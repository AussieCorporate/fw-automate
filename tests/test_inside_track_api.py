"""Endpoint tests for the Inside Track section. No real Claude/network calls:
every LLM-calling test monkeypatches flatwhite.dashboard.api.route.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import flatwhite.dashboard.api as api_module


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")


def test_api_inside_track_lists_submissions(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "adam_0001.jpg")
    _touch(tmp_path / "_INSIDE_TRACK" / "Zoe_0002.png")
    with patch.object(api_module, "_SCREENSHOTTER_OUTPUT_DIR", tmp_path):
        with patch("flatwhite.dashboard.api.get_current_week_iso", return_value="2026-W28"):
            result = api_module.api_inside_track()
            data = json.loads(result.body)
    assert data["folder_found"] is True
    assert data["folder_name"] == "_INSIDE_TRACK"
    assert data["week_iso"] == "2026-W28"
    filenames = [s["filename"] for s in data["submissions"]]
    assert filenames == ["adam_0001.jpg", "Zoe_0002.png"]
    assert data["submissions"][0]["thumb_url"] == "/api/inside-track/image/adam_0001.jpg"


def test_api_inside_track_fails_soft_when_folder_absent(tmp_path):
    with patch.object(api_module, "_SCREENSHOTTER_OUTPUT_DIR", tmp_path):
        result = api_module.api_inside_track()
        data = json.loads(result.body)
    assert data["folder_found"] is False
    assert data["folder_name"] is None
    assert data["submissions"] == []


def test_api_inside_track_image_serves_valid_file(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "adam_0001.jpg")
    with patch.object(api_module, "_SCREENSHOTTER_OUTPUT_DIR", tmp_path):
        result = api_module.api_inside_track_image("adam_0001.jpg")
    assert result.status_code == 200
    assert result.media_type == "image/jpeg"


def test_api_inside_track_image_404s_on_traversal(tmp_path):
    _touch(tmp_path / "secret.png")
    _touch(tmp_path / "_INSIDE_TRACK" / "a.png")
    with patch.object(api_module, "_SCREENSHOTTER_OUTPUT_DIR", tmp_path):
        result = api_module.api_inside_track_image("../secret.png")
    assert result.status_code == 404


def test_api_inside_track_image_404s_on_missing_file(tmp_path):
    _touch(tmp_path / "_INSIDE_TRACK" / "a.png")
    with patch.object(api_module, "_SCREENSHOTTER_OUTPUT_DIR", tmp_path):
        result = api_module.api_inside_track_image("nope.png")
    assert result.status_code == 404


def test_proceed_inside_track_builds_prompt_from_selected_items():
    from flatwhite.dashboard.api import _proceed_inside_track

    captured = {}

    def fake_route(task_type, prompt, system="", model_override=None):
        captured["task_type"] = task_type
        captured["prompt"] = prompt
        captured["system"] = system
        return "[Screenshot: adam_0001.jpg]\nA VP got redeployed into their own old job at half the title."

    with patch("flatwhite.dashboard.api.route", fake_route):
        data = {"selected": [{"filename": "adam_0001.jpg", "note": "VP demoted back into old role"}]}
        output = _proceed_inside_track(data, model=None)

    assert captured["task_type"] == "editorial"
    assert "adam_0001.jpg" in captured["prompt"]
    assert "VP demoted back into old role" in captured["prompt"]
    assert "No em dashes" in captured["prompt"]
    assert output.startswith("[Screenshot: adam_0001.jpg]")


def test_proceed_inside_track_handles_missing_note():
    from flatwhite.dashboard.api import _proceed_inside_track

    captured = {}

    def fake_route(task_type, prompt, system="", model_override=None):
        captured["prompt"] = prompt
        return "output"

    with patch("flatwhite.dashboard.api.route", fake_route):
        data = {"selected": [{"filename": "Zoe_0002.png", "note": ""}]}
        _proceed_inside_track(data, model=None)

    assert "(no note given)" in captured["prompt"]


def test_proceed_inside_track_custom_prompt_bypasses_default():
    from flatwhite.dashboard.api import _proceed_inside_track

    with patch("flatwhite.dashboard.api.route", return_value="custom output") as mock_route:
        output = _proceed_inside_track({}, model=None, custom_prompt="Just write this exact thing.")

    assert output == "custom output"
    mock_route.assert_called_once()
    assert mock_route.call_args.kwargs["prompt"] == "Just write this exact thing."


def test_proceed_section_endpoint_routes_insidetrack():
    from flatwhite.dashboard.api import api_proceed_section

    class FakeRequest:
        async def json(self):
            return {
                "section": "insidetrack",
                "model": None,
                "data": {"selected": [{"filename": "adam_0001.jpg", "note": "VP demoted"}]},
                "custom_prompt": None,
            }

    with patch("flatwhite.dashboard.api.route", return_value="[Screenshot: adam_0001.jpg]\nSomething punchy."):
        with patch("flatwhite.dashboard.api.get_current_week_iso", return_value="2026-W28"):
            result = asyncio.get_event_loop().run_until_complete(api_proceed_section(FakeRequest()))
            data = json.loads(result.body)

    assert data["section"] == "insidetrack"
    assert data["output"] == "[Screenshot: adam_0001.jpg]\nSomething punchy."
    assert data["week_iso"] == "2026-W28"
