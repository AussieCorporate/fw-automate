# FW Control Room Increment 5 — The Inside Track, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build The Inside Track as its own top-level section (position ~4 in the running order, NOT nested under Big Conversation): a page that lists the week's GOSSIP/REDUNDANCY screenshots (the ones the rebuilt sort skill, increment 3, routes out of the Big Conversation pile), lets Victor tick which ones run and jot a one-line note on each, then generates a short punchy write-up per selected item. Output is editable text; marking ready reuses the running-order header pill increment 1 already wires up for every segment.

**Architecture:** A small read-only Python module (`flatwhite/dashboard/inside_track.py`) finds the Inside Track folder inside the Instagram DM screenshotter's `output/` directory and lists its image files — never writing, moving, or deleting anything there. Two new FastAPI GET endpoints expose that listing and serve the actual PNG/JPG thumbnails, path-traversal-safe. A new `_proceed_inside_track` generator follows the exact shape of FW's other `_proceed_*` functions (e.g. `_proceed_off_the_clock`) and slots into the existing generic `/api/proceed-section` dispatch — no new POST route needed. The frontend adds one `renderInsideTrack(el)` page, reusing the existing generic `outputBox`/`fillOutput`/`saveOutput` editable-output widget already used by Off the Clock, and increment 1's per-segment header status pill for "Mark ready" (no new mark-ready mechanism invented).

**Tech Stack:** FastAPI (`flatwhite/dashboard/api.py`), single static HTML/CSS/JS dashboard (no build step), `pytest` via FW's own venv.

## What the real corpus actually shows (read before building the generator)

`data/beehiiv_fw_ground_truth.json` has a "THE INSIDE TRACK" segment in all 10 real editions. Two, read in full:

**2026-06-15 ("What if you're not a flight risk?"), word_count 219, 4 images:**
```
View image: (https://media.beehiiv.com/.../e6702acf.../image.png?t=...)
Caption:

View image: (https://media.beehiiv.com/.../e7b74720.../image.png?t=...)
Caption:

View image: (https://media.beehiiv.com/.../fbd42c4e.../image.png?t=...)
Caption:

View image: (https://media.beehiiv.com/.../afa79169.../image.png?t=...)
Caption:
```

**2026-06-08 ("Getting denied a payrise."), word_count 25, 1 image:**
```
View image: (https://media.beehiiv.com/.../5eb1476f.../FW_Big_Convo_SS__2_.png?t=...)
Caption:
```

**Finding:** in all 10 published editions, every "Caption:" is blank. The segment has never carried prose — it has only ever been 1-4 screenshots dropped straight into the block, no write-up. The reported word_counts (25-219) are almost entirely the "View image: (url)\nCaption:\n\n" markdown boilerplate repeated per image, not editorial copy.

This is a genuine gap between the corpus and this increment's brief: the spec and Victor's CLAUDE.md notes both explicitly ask for a "write it up" step producing "short punchy gossip/redundancy items", which is a real, deliberate upgrade over what has ever shipped, not something to benchmark word-for-word against past editions. Given that, this plan calibrates the generator to the spirit of the ask (one short, punchy 1-2 sentence line per selected item, no filler) rather than to a non-existent prose precedent, and keeps the block structure (one item per block, blank line between blocks) recognisably close to the real "one screenshot = one block" shape. **Flag this to Victor when reviewing:** the real Inside Track has never had captions; this increment adds that capability for the first time.

## Design decision: what counts as "this week's" submissions

The Instagram screenshotter's folders aren't date-stamped per file (filenames are just `SubmitterName_000N.png`), and there is no existing per-week subfolder structure to filter on. So "the current week's" Inside Track submissions, for this increment, means: **whatever is currently sitting in the found Inside Track folder right now.** There is no date filtering in `list_inside_track_submissions`. This mirrors how the Big Conversation topic bank works (a folder's contents ARE the batch; Victor/the archive action clears it out once used) — Increment 5 does not add an archive/clear action of its own (not asked for in this increment's scope), so once increment 3's sort skill starts routing new weeks into the same folder, old already-published items will keep showing until something clears them. Flag this to Victor: if he wants old Inside Track items to disappear automatically after being marked ready/published, that's an archive mechanism for a later increment, not this one.

## Global Constraints

- **Runs on FW's venv only:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python is 3.9 and breaks FW; never use another interpreter.
- Branch: from `main`, `git checkout main && git checkout -b fw-control-room-inside-track`. FW deploy is Victor's (GCP VM `flatwhite`); this increment is built + tested locally only, not merged, not pushed, not deployed.
- **FW test baseline (recorded today, 2026-07-14):** `.venv/bin/python -m pytest -q` → **124 passed, 8 failed**. The 8 failures are pre-existing and unrelated to this work (`tests/test_normalise.py` cold-start/self-calibrating assertions, `tests/test_pipeline.py` anomaly detection assertions). After every task in this plan, re-run the full suite: the failing set must stay exactly those 8 (same names), and passed count must increase by exactly the number of new tests added in that task.
- No em dashes (U+2014) in any reader-facing string or generated prompt output. Australian English spelling throughout (e.g. "organise", "colour").
- **Read-only access to the Instagram screenshotter's tree.** `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/` is owned by that project. This increment only ever reads files from it — no code in this plan writes, moves, renames, or deletes anything under that path. Tests must never point at the real path; they use `tmp_path` fixtures only.
- **No real Claude/network calls in tests.** Every test that would otherwise call the LLM monkeypatches `flatwhite.dashboard.api.route` (or passes a `custom_prompt`, which still routes through the same patched function) and asserts on the prompt built / the mocked return value. Never hit `flatwhite.model_router._call_model` or a real provider in a test.
- No JS build/test harness exists for the frontend: verify the UI via `curl` presence checks against a running dashboard plus a manual click script. Do not invent a JS test framework.
- Local run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`. Kill it when done with each task's manual check.
- This increment depends on Increment 1 (the master/detail shell — `SEGMENTS`, `selectSegment`, the `render()` dispatcher, the `.page`/`.page-h`/`.page-b` frame, `toggleReady`) and Increment 3 (the rebuilt sort skill that populates the Inside Track folder with real gossip/redundancy screenshots) having been built first. If, at execution time, Increment 1's exact line numbers/function bodies differ from what's quoted here (they will have shifted), locate the equivalent `render()` switch / `loadPageData` switch / `SEGMENTS` array by name, not by line number, and edit those.
- Increment 4 (Big Conversation screenshot-serving) does not exist yet as a plan. This increment therefore **defines** the read-only, path-traversal-safe image-serving route pattern from scratch (Task 2). If Increment 4 is written after this one, it should reuse `flatwhite/dashboard/inside_track.py`'s `resolve_inside_track_image`-style safety check (resolve + `is_relative_to` the source folder) rather than inventing a second one.

## File Structure

- Create: `flatwhite/dashboard/inside_track.py` — read-only folder discovery, submission listing, path-traversal-safe image path resolution. No FastAPI/HTTP code here, so it's unit-testable without spinning up the app.
- Create: `tests/test_inside_track.py` — unit tests for the above, entirely against `tmp_path` fixtures.
- Modify: `flatwhite/dashboard/api.py` — add `_SCREENSHOTTER_OUTPUT_DIR` constant, two new GET endpoints (`/api/inside-track`, `/api/inside-track/image/{filename}`), one new `_proceed_inside_track` generator, one new entry in the `proceed_fns` dict inside `api_proceed_section`.
- Create: `tests/test_inside_track_api.py` — endpoint-level tests, monkeypatching `_SCREENSHOTTER_OUTPUT_DIR` to `tmp_path` and `route` to avoid network calls.
- Modify: `flatwhite/dashboard/static/index.html` — CSS for the thumbnail grid, three new state fields on `S`, a `loadPageData` case, a `render()` dispatch case, and `renderInsideTrack(el)` + its three small helper functions.

---

### Task 1: Read-only folder discovery + submission listing + path-traversal-safe image resolution

**Files:**
- Create: `flatwhite/dashboard/inside_track.py`
- Test: `tests/test_inside_track.py`

**Interfaces:**
- Produces: `INSIDE_TRACK_FOLDER_CANDIDATES: list[str]`, `find_inside_track_folder(base_dir: Path) -> Path | None`, `list_inside_track_submissions(base_dir: Path) -> list[dict]` (each dict has `"filename"` and `"folder"` keys), `resolve_inside_track_image(base_dir: Path, filename: str) -> Path | None`.
- Consumed by: Task 2's API endpoints (`base_dir` there is the module-level `_SCREENSHOTTER_OUTPUT_DIR` constant in `api.py`).

- [ ] **Step 1: Write the failing tests.**

Create `tests/test_inside_track.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_inside_track.py -v`
Expected: FAIL / ERROR — `flatwhite.dashboard.inside_track` does not exist yet (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation.**

Create `flatwhite/dashboard/inside_track.py`:

```python
"""Read-only access to the Instagram DM screenshotter's Inside Track folder.

The Instagram sort skill (control-room increment 3) routes GOSSIP and
REDUNDANCY submissions out of the Big Conversation pile into a folder inside
the screenshotter's own `output/` directory. This module only ever READS
that folder — nothing here writes, moves, renames, or deletes anything
under the screenshotter's tree. That project owns its own files.
"""
from __future__ import annotations

from pathlib import Path

# The folder name the rebuilt sort skill (increment 3) is expected to use
# for gossip/redundancy submissions. "Redundancies & Breaking News" is the
# CURRENT real folder under the screenshotter's output/ (pre-rebuild) — kept
# as a fallback so this section has something to show before increment 3
# ships. Checked in this order; the first one that exists wins.
INSIDE_TRACK_FOLDER_CANDIDATES: list[str] = [
    "_INSIDE_TRACK",
    "Redundancies & Breaking News",
]

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def find_inside_track_folder(base_dir: Path) -> Path | None:
    """Return the first candidate Inside Track folder that exists under base_dir.

    Fails soft: returns None if base_dir itself doesn't exist, or no
    candidate folder is found. Never raises for a missing filesystem path.
    """
    if not base_dir.is_dir():
        return None
    for name in INSIDE_TRACK_FOLDER_CANDIDATES:
        candidate = base_dir / name
        if candidate.is_dir():
            return candidate
    return None


def list_inside_track_submissions(base_dir: Path) -> list[dict]:
    """List image submissions directly inside the Inside Track folder.

    Returns [] (fails soft) if base_dir or the Inside Track folder inside it
    is missing. Only looks at direct children — the folder is flat, one
    screenshot per submitter, no per-submitter subfolders — sorted
    case-insensitively by filename for a stable, predictable order.
    """
    folder = find_inside_track_folder(base_dir)
    if folder is None:
        return []
    submissions = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
            submissions.append({"filename": path.name, "folder": folder.name})
    return submissions


def resolve_inside_track_image(base_dir: Path, filename: str) -> Path | None:
    """Resolve `filename` to a real image file inside the Inside Track folder.

    Returns None (never raises) if: the Inside Track folder doesn't exist,
    the resolved path escapes the folder (path traversal via "../",
    an absolute path, or a symlink), the file doesn't exist, or it isn't
    one of the accepted image extensions.
    """
    folder = find_inside_track_folder(base_dir)
    if folder is None:
        return None
    folder_real = folder.resolve()
    candidate = (folder / filename).resolve()
    if not candidate.is_relative_to(folder_real):
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() not in _IMAGE_EXTENSIONS:
        return None
    return candidate
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_inside_track.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 5: Full suite + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest -q 2>&1 | tail -5
```
Expected: `133 passed, 8 failed` (124 + 9 new; same 8 pre-existing failures as baseline).

```bash
git add flatwhite/dashboard/inside_track.py tests/test_inside_track.py
git commit -m "Inside Track: read-only folder discovery + submission listing"
```

---

### Task 2: API endpoints — list submissions + serve images

**Files:**
- Modify: `flatwhite/dashboard/api.py`
- Test: `tests/test_inside_track_api.py`

**Interfaces:**
- Consumes: Task 1's `find_inside_track_folder`, `list_inside_track_submissions`, `resolve_inside_track_image`.
- Produces: module-level constant `_SCREENSHOTTER_OUTPUT_DIR: Path` in `api.py`; `GET /api/inside-track` → `{"folder_found": bool, "folder_name": str | None, "submissions": [{"filename": str, "thumb_url": str}], "week_iso": str}`; `GET /api/inside-track/image/{filename}` → the image file, or `{"error": "not found"}` with a 404.

- [ ] **Step 1: Write the failing tests.**

Create `tests/test_inside_track_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_inside_track_api.py -v`
Expected: FAIL — `api_module` has no attribute `_SCREENSHOTTER_OUTPUT_DIR` / `api_inside_track` / `api_inside_track_image`.

- [ ] **Step 3: Add the constant and endpoints to `flatwhite/dashboard/api.py`.**

Add this constant right after the existing `_STATIC_DIR = Path(__file__).parent / "static"` line (around line 58):

```python
_SCREENSHOTTER_OUTPUT_DIR = Path(
    os.environ.get(
        "FW_SCREENSHOTTER_OUTPUT_DIR",
        str(Path.home() / "Documents" / "MISC" / "instagram-dm-screenshotter" / "output"),
    )
)
```

Add these two endpoints in the "READ endpoints (GET)" section, near the other simple GET endpoints (e.g. after `api_off_the_clock`):

```python
@app.get("/api/inside-track")
def api_inside_track() -> JSONResponse:
    """List this week's Inside Track (gossip/redundancy) screenshot submissions.

    Reads the Instagram DM screenshotter's output folder READ-ONLY (never
    writes to it). Fails soft: if the screenshotter output dir or the
    Inside Track folder inside it doesn't exist yet, returns an empty list
    rather than erroring, so the page still renders.
    """
    from flatwhite.dashboard.inside_track import find_inside_track_folder, list_inside_track_submissions

    folder = find_inside_track_folder(_SCREENSHOTTER_OUTPUT_DIR)
    submissions = list_inside_track_submissions(_SCREENSHOTTER_OUTPUT_DIR)
    return JSONResponse({
        "folder_found": folder is not None,
        "folder_name": folder.name if folder else None,
        "submissions": [
            {"filename": s["filename"], "thumb_url": "/api/inside-track/image/" + s["filename"]}
            for s in submissions
        ],
        "week_iso": get_current_week_iso(),
    })


@app.get("/api/inside-track/image/{filename}")
def api_inside_track_image(filename: str) -> FileResponse | JSONResponse:
    """Serve one Inside Track screenshot, read-only and path-traversal-safe.

    `filename` is validated by resolve_inside_track_image against the
    Inside Track folder (resolve + is_relative_to check) before anything is
    read off disk; any traversal attempt or missing file returns a 404.
    """
    from flatwhite.dashboard.inside_track import resolve_inside_track_image

    path = resolve_inside_track_image(_SCREENSHOTTER_OUTPUT_DIR, filename)
    if path is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type)
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_inside_track_api.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Manual curl check against the real dashboard (with a fake folder).**

```bash
cd /Users/victornguyen/Documents/MISC/FW
mkdir -p /tmp/fw_it_check/_INSIDE_TRACK
cp flatwhite/dashboard/static/index.html /tmp/fw_it_check/_INSIDE_TRACK/fake.png 2>/dev/null || touch /tmp/fw_it_check/_INSIDE_TRACK/fake.png
FW_SCREENSHOTTER_OUTPUT_DIR=/tmp/fw_it_check .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/api/inside-track
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/api/inside-track/image/fake.png
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8500/api/inside-track/image/..%2F..%2Fetc%2Fpasswd"
kill %1
rm -rf /tmp/fw_it_check
```
Expected: first curl shows `"folder_found":true,"folder_name":"_INSIDE_TRACK"` with one submission; second curl → `200`; third curl → `404`.

- [ ] **Step 6: Full suite + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
```
Expected: `138 passed, 8 failed`.

```bash
git add flatwhite/dashboard/api.py tests/test_inside_track_api.py
git commit -m "Inside Track: list-submissions + image-serving endpoints"
```

---

### Task 3: The write-up generator (`_proceed_inside_track`)

**Files:**
- Modify: `flatwhite/dashboard/api.py`
- Test: `tests/test_inside_track_api.py` (append)

**Interfaces:**
- Consumes: `_safe_override`, `route` (from `flatwhite.model_router`), `EDITORIAL_VOICE` (from `flatwhite.classify.prompts`) — all already imported/available in `api.py`.
- Produces: `_proceed_inside_track(data: dict, model: str | None, custom_prompt: str | None = None) -> str`, registered in `api_proceed_section`'s `proceed_fns` dict under the key `"insidetrack"` (matching the segment id increment 1's `SEGMENTS` array uses for this section — no id-mapping layer between sidebar id and API section key).
- `data` shape expected: `{"selected": [{"filename": str, "note": str}, ...]}`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_inside_track_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_inside_track_api.py -v -k inside_track`
Expected: FAIL — `_proceed_inside_track` doesn't exist yet, and `"insidetrack"` isn't in `proceed_fns` (the last test gets a 400 "Unknown section" response instead of the expected output).

- [ ] **Step 3: Add `_proceed_inside_track` to `flatwhite/dashboard/api.py`**, next to the other `_proceed_*` functions (e.g. immediately after `_proceed_off_the_clock`):

```python
def _proceed_inside_track(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE, model_override=override)

    selected = data.get("selected", [])
    items_block = "\n\n".join(
        "Screenshot: {}\nWhat it shows: {}".format(
            item.get("filename", ""), item.get("note", "") or "(no note given)"
        )
        for item in selected
    )

    prompt = (
        "Write THE INSIDE TRACK section for this week's Flat White newsletter.\n\n"
        "THE INSIDE TRACK carries short gossip and redundancy/breaking-news items "
        "submitted by the community, each paired with a screenshot. Write ONE short, "
        "punchy line per item, 1-2 sentences, a plain statement of what happened, not "
        "a review. Dry, observant, Australian corporate commentary. No filler "
        "intensifiers. No em dashes. Australian English.\n\n"
        f"Items:\n{items_block}\n\n"
        "Output EXACTLY this format, one block per item, with a blank line between "
        "blocks, and nothing else:\n\n"
        "[Screenshot: <filename>]\n"
        "<your punchy line>"
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=override)
```

Then add `"insidetrack": _proceed_inside_track,` to the `proceed_fns` dict inside `api_proceed_section` (alongside `"pulse"`, `"big_conversation"`, `"finds"`, `"off_the_clock"`, `"editorial"`).

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_inside_track_api.py -v`
Expected: all 9 tests in this file PASS (5 from Task 2 + 4 new).

- [ ] **Step 5: Full suite + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
```
Expected: `142 passed, 8 failed`.

```bash
git add flatwhite/dashboard/api.py tests/test_inside_track_api.py
git commit -m "Inside Track: write-up generator wired into /api/proceed-section"
```

---

### Task 4: Frontend — the Inside Track page (list, tick, note, write up, edit, mark ready)

**Files:** `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: increment 1's `SEGMENTS`/`selectSegment`/`render()` dispatcher and `.page`/`.page-h`/`.page-b`/`toggleReady` frame; the existing generic `S.sectionOutputs`, `outputBox(section)`, `fillOutput(section)`, `saveOutput(section)`, `copyOutput(section)`, `modelSelect(id)`, `getModel(id)`, `esc(s)`, `api(path, opts)`, `showToast(msg, type)` helpers already used by Off the Clock (`renderOTC`).
- Produces: `renderInsideTrack(el)`, `toggleInsideTrackPick(filename)`, `updateInsideTrackNote(filename, value)`, `proceedInsideTrack()`; new `S` fields `insideTrack`, `insideTrackPicked`, `insideTrackNotes`; a `loadPageData` case for `"insidetrack"`; a `render()` dispatch case for `"insidetrack"`.

- [ ] **Step 1: Add state fields.** In the `S` state object literal (alongside `otcData`, `topPicks`, `topPicksChecked`), add:

```js
  insideTrack: null,        // { folder_found, folder_name, submissions, week_iso }
  insideTrackPicked: {},     // { filename: true }
  insideTrackNotes: {},      // { filename: note text }
```

- [ ] **Step 2: Add the `loadPageData` case.** In the `loadPageData(page)` switch, add (before `default:`):

```js
    case "insidetrack":
      if (S.insideTrack) return Promise.resolve();
      return api("/api/inside-track").then(function(d) { S.insideTrack = d; S.weekIso = d.week_iso; });
```

- [ ] **Step 3: Add the `render()` dispatch case.** In the `render()` function's `switch (S.page)` block (established by increment 1 to draw into the detail pane), add a case that replaces the placeholder for this segment:

```js
    case "insidetrack": renderInsideTrack(m); break;
```

- [ ] **Step 4: Add the CSS.** Append to the `<style>` block:

```css
.it-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.it-card{border:1px solid var(--sep);border-radius:10px;overflow:hidden;background:var(--card)}
.it-card.picked{box-shadow:0 0 0 2px var(--accent)}
.it-thumb{width:100%;height:140px;object-fit:cover;display:block;cursor:pointer;background:var(--track)}
.it-body{padding:8px 10px}
.it-fname{font-size:11px;color:var(--label2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:6px}
.it-note{width:100%;font-size:12px;border:1px solid var(--sep);border-radius:6px;padding:6px;resize:vertical;font-family:inherit;box-sizing:border-box}
.it-empty{color:var(--label2);font-size:13px;padding:8px 0}
```

- [ ] **Step 5: Add `renderInsideTrack(el)` and its three helpers.** Place near the other section renderers (e.g. after `renderOTC`):

```js
/* ═══════════════════════════════════════════════════════════════════════
   SECTION: THE INSIDE TRACK
   ═══════════════════════════════════════════════════════════════════════ */
function toggleInsideTrackPick(filename) {
  if (S.insideTrackPicked[filename]) delete S.insideTrackPicked[filename];
  else S.insideTrackPicked[filename] = true;
  render();
}

function updateInsideTrackNote(filename, value) {
  S.insideTrackNotes[filename] = value;
}

function proceedInsideTrack() {
  var picked = Object.keys(S.insideTrackPicked);
  if (!picked.length) { alert("Tick at least one submission before writing up."); return; }
  var selected = picked.map(function(f) { return { filename: f, note: S.insideTrackNotes[f] || "" }; });
  var model = getModel("model-insidetrack");
  S.loading.insidetrack = true;
  render();
  api("/api/proceed-section", { method: "POST", body: { section: "insidetrack", model: model, data: { selected: selected } } })
    .then(function(d) {
      S.sectionOutputs.insidetrack = { output_text: d.output, model_used: d.model };
      S.loading.insidetrack = false;
      render();
      showToast("Inside Track written up");
    })
    .catch(function(e) {
      S.loading.insidetrack = false;
      render();
      showToast("Error: " + e.message, "error");
    });
}

function renderInsideTrack(el) {
  var d = S.insideTrack;
  var pickedCount = Object.keys(S.insideTrackPicked).length;

  var h = '';
  h += '<p style="color:var(--label2);font-size:13px;margin:0 0 14px;">Tick the gossip and redundancy screenshots to run, add a one-line note on what each shows, then write them up.</p>';

  if (!d || !d.submissions || !d.submissions.length) {
    var msg = (d && d.folder_found === false)
      ? 'No Inside Track folder found yet in the screenshotter output. Run the sort skill first.'
      : 'No gossip/redundancy submissions this week.';
    h += '<div class="it-empty">' + msg + '</div>';
  } else {
    h += '<div class="it-grid">';
    d.submissions.forEach(function(s) {
      var picked = !!S.insideTrackPicked[s.filename];
      var safeName = esc(s.filename).replace(/'/g, "\\'");
      h += '<div class="it-card' + (picked ? ' picked' : '') + '">';
      h += '<img class="it-thumb" src="' + esc(s.thumb_url) + '" onclick="toggleInsideTrackPick(\'' + safeName + '\')" title="Click to ' + (picked ? 'un-tick' : 'tick') + '"/>';
      h += '<div class="it-body">';
      h += '<div class="it-fname">' + esc(s.filename) + '</div>';
      if (picked) {
        h += '<textarea class="it-note" rows="2" placeholder="What does this show?" oninput="updateInsideTrackNote(\'' + safeName + '\', this.value)">' + esc(S.insideTrackNotes[s.filename] || '') + '</textarea>';
      }
      h += '</div></div>';
    });
    h += '</div>';
  }

  h += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">';
  h += modelSelect("model-insidetrack");
  h += '<button class="btn btn-success" onclick="proceedInsideTrack()"' + (S.loading.insidetrack ? ' disabled' : '') + '>';
  h += (S.loading.insidetrack ? 'Writing up…' : 'Write up selected (' + pickedCount + ')');
  h += '</button></div>';

  h += outputBox('insidetrack');

  el.innerHTML = h;
  fillOutput('insidetrack');
}
```

- [ ] **Step 6: Verify (presence checks + manual).** Boot the dashboard:

```bash
cd /Users/victornguyen/Documents/MISC/FW
mkdir -p /tmp/fw_it_check2/_INSIDE_TRACK
touch /tmp/fw_it_check2/_INSIDE_TRACK/sample1.png /tmp/fw_it_check2/_INSIDE_TRACK/sample2.jpg
FW_SCREENSHOTTER_OUTPUT_DIR=/tmp/fw_it_check2 .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c 'function renderInsideTrack'   # 1
curl -s http://127.0.0.1:8500/ | grep -c 'case "insidetrack"'           # 2 (loadPageData + render dispatch)
curl -s http://127.0.0.1:8500/api/inside-track                          # 2 submissions, folder_found true
kill %1
rm -rf /tmp/fw_it_check2
```

Manual click script: open `http://127.0.0.1:8500/`, select The Inside Track from the running order. Confirm: the two sample thumbnails show in a grid; clicking a thumbnail ticks it (accent ring appears) and reveals a note textarea; typing a note and clicking "Write up selected (N)" shows "Writing up…" then either real output (if `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` is set) or a toast error (fine either way — this proves the wiring, not the LLM call); the output textarea (from the shared `outputBox`) is editable and has Copy/Save buttons; clicking the segment's header status pill (from increment 1) toggles it ready/not-ready. Kill the server.

- [ ] **Step 7: Full Python suite unchanged + commit.**

```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
```
Expected: still `142 passed, 8 failed` (this task is frontend-only; no Python test count changes).

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "Inside Track: frontend page — tick submissions, note, write up, edit, mark ready"
```

---

## Manual verification (whole increment, before done)

1. `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`.
2. The Inside Track appears as its OWN item in the running order (position ~4), not nested under Big Conversation.
3. With `FW_SCREENSHOTTER_OUTPUT_DIR` unset (pointing at the real screenshotter path): if `_INSIDE_TRACK` or the legacy `Redundancies & Breaking News` folder exists with real screenshots, they show as thumbnails; if neither exists yet, the page shows the fail-soft empty message rather than erroring.
4. Ticking submissions and adding notes, then "Write up selected", produces editable output in the shared output box; Copy and Save both work; the segment's header status pill marks it ready.
5. `curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8500/api/inside-track/image/..%2F..%2Fetc%2Fpasswd"` → `404` (path traversal blocked).
6. FW Python suite: `.venv/bin/python -m pytest -q` → `142 passed, 8 failed` (same 8 pre-existing failures as the recorded baseline; no regressions).
7. Confirm nothing under `/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/` was created, modified, or deleted by any step above (`git -C /Users/victornguyen/Documents/MISC/instagram-dm-screenshotter status` if that tree is a git repo, or a manual `ls -la` diff otherwise).

Report the FW suite counts and: **"built locally on branch `fw-control-room-inside-track`, NOT merged, NOT deployed (FW deploy is Victor's)."**

## Notes for later increments (not this plan)

- Assembly (increment 7) is responsible for turning this section's `[Screenshot: <filename>]` markers into real beehiiv `View image: (asset_url)` markdown once the screenshots are uploaded as beehiiv assets — Increment 5 stops at editable FW-formatted text + marking ready, same as every other segment's textarea.
- If increment 3's rebuilt sort skill ends up using a different folder name than `_INSIDE_TRACK`, add it to `INSIDE_TRACK_FOLDER_CANDIDATES` in `flatwhite/dashboard/inside_track.py` rather than changing the lookup logic.
- If increment 4 (Big Conversation screenshot serving) is built after this one, point it at `resolve_inside_track_image`'s safety pattern (resolve + `is_relative_to` the source folder) instead of writing a second path-traversal check.
