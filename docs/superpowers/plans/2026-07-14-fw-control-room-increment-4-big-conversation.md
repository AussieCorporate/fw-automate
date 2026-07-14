# FW Control Room Increment 4 — The Big Conversation Pipeline, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Big Conversation detail page's full backend + UI: a topic bank of AI-named, AI-sorted Instagram DM screenshot folders (archivable), a "Process" flow that hands off to the Claude-side `big-conversation` skill and reads back what it wrote, a paragraph-by-paragraph view of the drafted piece with its auto-paired screenshots, a always-shown viral-extreme safety-net pool, and a hidden-by-default T1/T2/T3 tier pool for swapping in a better shot. Screenshot PNGs are served read-only from the Instagram DM screenshotter's `output/` folder through a path-traversal-safe route.

**Architecture:** This increment does NOT make FW call Claude or the `big-conversation` skill — FW has no server-side mechanism to invoke a Claude skill, and this plan does not invent one. The skill runs Claude-side, in a separate Claude session Victor drives, exactly as it does today (see `output/.claude/skills/big-conversation/SKILL.md`). FW's job is: (1) list and archive topic candidates from the Instagram project's `output/` folder (read-only filesystem scan), (2) on "Process", confirm the folder is ready and hand back the exact instruction to run the skill (the honest "prepare" step — mirrors PS Dash's "Design B": the dash prepares + reads, generation happens outside it), (3) once the skill has written `_<TOPIC>_BIG_CONVERSATION.md` + `<topic>/_BIG_CONVERSATION_assets/*.png` into that same folder, read those artifacts back, parse the piece into paragraphs, and pair each paragraph with the screenshots the skill already renamed into `p<paragraph>_<rank>_<handle>.png` order. Victor's drag-drop reassignments and topic archive state are the only things FW writes anywhere, and they are written to FW's OWN SQLite database — never into the read-only Instagram project. A new FastAPI route serves the PNGs directly from the Instagram output folder, resolved and checked against path traversal on every request.

**Tech Stack:** FastAPI (`flatwhite/dashboard/api.py`), a new pure-filesystem module (`flatwhite/dashboard/big_conversation_bank.py`), FW's existing SQLite DB (`flatwhite/db.py`, `flatwhite/dashboard/state.py`) for archive/pairing state, the existing static HTML/JS SPA (`flatwhite/dashboard/static/index.html`, no build step), `pytest` via FW's own venv.

## Global Constraints

- **Runs on FW's venv only:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python 3.9 breaks FW. Never use another interpreter for FW.
- **Branch:** `fw-control-room-bigconv`. This increment depends on increment 1 (the master/detail shell — `SEGMENTS`, `selectSegment`, the `#page` detail pane, `renderBigConv` already wired into the router) and increment 3 (the sort skill rebuild — the topic folders' tier subfolder names may change from `🔥 RED HOT Top N` / `Tier 1 - Viral` to something like `VIRAL EXTREME` / `T1`). Branch from whichever branch/commit already has increments 1 and 3 applied (nominally `git checkout fw-control-room-shell && git checkout -b fw-control-room-bigconv`, adjusted to the real base if increments 1/3 landed on `main` or a different branch by the time this runs).
- **FW test baseline:** run `.venv/bin/python -m pytest -q` first and record the exact pass/fail counts. Confirmed at plan-writing time: **124 passed / 8 pre-existing failures** (all in `test_normalise.py` and `test_pipeline.py`, unrelated to this work). After every task the non-pre-existing failure count must stay at zero.
- No em dashes (U+2014) in any reader-facing string. Australian spelling.
- **Read-only on the Instagram DM screenshotter project.** `flatwhite/dashboard/big_conversation_bank.py` may only ever `read_text` / `iterdir` / `glob` / open-for-read inside `INSTAGRAM_OUTPUT_DIR`. Never write, rename, move, or delete anything there. Archive flags and drag-drop pairing overrides are stored in FW's own SQLite DB instead (new tables, Task 1).
- **Fail soft if the Instagram output folder is absent** (e.g. this machine doesn't have that project checked out, or the path moved): every read function returns an empty/soft result (`[]`, `{}`, `None`, or `{"processed": false}`), never raises, never 500s.
- **The image-serving route must be path-traversal-safe:** resolve the requested path, reject absolute paths and anything that resolves outside `INSTAGRAM_OUTPUT_DIR`, and only serve `.png`/`.jpg`/`.jpeg` files that actually exist.
- **No server-side Claude/skill invocation.** Do not add code that shells out to `claude`, calls an Anthropic API, or otherwise tries to run the `big-conversation` skill from FW. The "Process" action prepares + hands back instructions; a human runs the skill in a Claude session; the dash reads the result back.
- FW deploy is Victor's (GCP VM `flatwhite`); this increment is built + tested locally only, not merged/pushed/deployed.
- No JS build/test harness exists: verify the UI via `curl` presence checks against the running dashboard plus a manual click script, alongside the Python suite for everything else.
- Local run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`. Kill it when done.

## Design reference

Spec: `docs/superpowers/specs/2026-07-14-flat-white-control-room-design.md`, "The segments" item 8 (Big Conversation) and "The screenshot pipeline". `CLAUDE.md`'s "FW control-room — detailed segment mechanics" and "ROUND 4" sections carry the exact UI behaviour Victor confirmed (viral pool always shown, T1/T2/T3 behind a toggle, paragraphs are the primary view after processing).

## The real data this increment reads (reference, not fixtures)

`/Users/victornguyen/Documents/MISC/instagram-dm-screenshotter/output/` currently contains, among others:
- Topic candidates not yet archived: `AI Usage`, `AML CTF New Requirements`, `BO and Perfume`, `Career Pivoting`, `KPMG Sentiment`, `Lunch w your team or not`, `Manager Pet Names`, `Office Shoes`, `Parental Leave`, `Pay Negotiation`, `Payrise Excuses`, `Pregnancy Protection`, `Redeployment After Hire`, `Shit boss series`, `Teams:Slack Monitoring`, `Toilet Series`, `Visa vs Resident Pay`, `Wellness Reimbursement`, `Worst Interview Experiences`.
- Already-processed real examples (each has a `_BIG_CONVERSATION_assets/` folder plus a root-level `_<SHORTNAME>_BIG_CONVERSATION.md`): `Kids in the Office` (-> `_KIDS_OFFICE_BIG_CONVERSATION.md`), `Conference Room Sharing` (-> `_CONFROOM_BIG_CONVERSATION.md`), `PIP Term Length` (-> `_PIP_BIG_CONVERSATION.md`). These three are real, already-finished pieces — useful for manually eyeballing the finished UI against genuine data (see the whole-increment verification section).
- Utility/junk folders that must NEVER appear in the topic bank: `_work`, `_SPILLOVER hold`, `_PAYNEG_editorial_visuals`, `Rubbish`, `MISC Stand alone`, `Redundancies & Breaking News` (routes to The Inside Track, a different segment), `untitled folder`, and anything prefixed `DONE - ` or `INCOMPLETE - ` (Victor's own manual folder-rename convention for topics he's already handled outside the dash).
- The screenshot naming convention the skill already uses when it processes a topic (confirmed from the real `Kids in the Office/_BIG_CONVERSATION_assets/` folder): `p<paragraph>_<rank>_<handle>.png`, e.g. `p1_1_Katie_Moloney.png`, `p1_alt_IMG_7962.jpg`, `p1_alt2_Emma_Ainley.png`, `p2_1_IMG_7955.jpg`. Rank `1` is the primary pick; `alt`, `alt2`, `alt3` are ranked alternates.
- The piece file's own shape (confirmed from `_KIDS_OFFICE_BIG_CONVERSATION.md`): a `**THE BIG CONVERSATION**` header, a one-line bold headline, one paragraph per screenshot group, then a `---` divider before the `BUILD: paragraph -> screenshot map`. That BUILD section states the assets path in prose, e.g. `` Assets in `Kids in the Office/_BIG_CONVERSATION_assets/`. `` — this is how the code finds the right MD file for a topic, since the MD filename's shortname (`KIDS_OFFICE`) is an AI-chosen abbreviation that can't be derived from the folder name (`Kids in the Office`) programmatically.

---

### Task 1: Archive + drag-drop pairing state (FW's own DB, never the Instagram folder)

**Files:**
- Modify: `flatwhite/db.py` (add to `migrate_db()`, ~line 422, just before the final `conn.commit(); conn.close()`)
- Modify: `flatwhite/dashboard/state.py` (append new functions)
- Test: `tests/test_big_conversation_state.py` (new)

**Interfaces:**
- Produces: `load_topic_archive_state() -> dict[str, bool]`, `set_topic_archived(topic: str, archived: bool) -> None`, `load_pairing_overrides(topic: str) -> dict[str, int]`, `save_pairing_override(topic: str, filename: str, paragraph_index: int) -> None`. Consumed by Task 9's API endpoints and Task 6's `get_topic_detail`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_big_conversation_state.py`:
```python
"""Tests for Big Conversation topic archive + drag-drop pairing state.

Both are stored in FW's own SQLite DB (never in the read-only Instagram
output folder) — see flatwhite/dashboard/state.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import flatwhite.db as db_module


def test_archive_state_round_trips(tmp_path: Path):
    db_path = tmp_path / "bc_state_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        from flatwhite.dashboard.state import load_topic_archive_state, set_topic_archived

        assert load_topic_archive_state() == {}
        set_topic_archived("Kids in the Office", True)
        assert load_topic_archive_state() == {"Kids in the Office": True}
        set_topic_archived("Kids in the Office", False)
        assert load_topic_archive_state() == {}


def test_pairing_overrides_round_trip(tmp_path: Path):
    db_path = tmp_path / "bc_pairing_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        from flatwhite.dashboard.state import load_pairing_overrides, save_pairing_override

        assert load_pairing_overrides("Kids in the Office") == {}
        save_pairing_override("Kids in the Office", "p1_1_Katie_Moloney.png", 3)
        assert load_pairing_overrides("Kids in the Office") == {"p1_1_Katie_Moloney.png": 3}
        # Moving it again overwrites, does not duplicate.
        save_pairing_override("Kids in the Office", "p1_1_Katie_Moloney.png", 2)
        assert load_pairing_overrides("Kids in the Office") == {"p1_1_Katie_Moloney.png": 2}


def test_pairing_overrides_are_scoped_per_topic(tmp_path: Path):
    db_path = tmp_path / "bc_pairing_scope_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        from flatwhite.dashboard.state import load_pairing_overrides, save_pairing_override

        save_pairing_override("Kids in the Office", "shot.png", 1)
        save_pairing_override("Career Pivoting", "shot.png", 4)
        assert load_pairing_overrides("Kids in the Office") == {"shot.png": 1}
        assert load_pairing_overrides("Career Pivoting") == {"shot.png": 4}
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_state.py -v
```
Expected: FAIL — `ImportError: cannot import name 'load_topic_archive_state'`.

- [ ] **Step 3: Add the DB tables.** In `flatwhite/db.py`, inside `migrate_db()`, immediately before the closing `conn.commit()\n    conn.close()` (currently ~line 424), add:
```python
    # v7 Big Conversation control-room state (increment 4): archive flag +
    # drag-drop paragraph/screenshot pairing overrides. Both keyed by the
    # Instagram output topic folder NAME (not an id) since that folder name
    # is the only stable identifier the read-only Instagram project exposes.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS big_conversation_topic_state (
            topic TEXT PRIMARY KEY,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS big_conversation_pairing_override (
            topic TEXT NOT NULL,
            filename TEXT NOT NULL,
            paragraph_index INTEGER NOT NULL,
            PRIMARY KEY (topic, filename)
        )
    """)
```

- [ ] **Step 4: Add the state functions.** Append to `flatwhite/dashboard/state.py`:
```python
def load_topic_archive_state() -> dict[str, bool]:
    """Return {topic: True} for every Big Conversation topic Victor has
    archived. Topics absent from the dict are treated as not archived.
    Read-only lookup used to filter the topic bank list."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT topic FROM big_conversation_topic_state WHERE archived = 1"
    ).fetchall()
    conn.close()
    return {r["topic"]: True for r in rows}


def set_topic_archived(topic: str, archived: bool) -> None:
    """Archive or unarchive a Big Conversation topic bank entry."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO big_conversation_topic_state (topic, archived, archived_at)
           VALUES (?, ?, CASE WHEN ? THEN datetime('now') ELSE NULL END)
           ON CONFLICT(topic) DO UPDATE SET
             archived = excluded.archived,
             archived_at = excluded.archived_at""",
        (topic, 1 if archived else 0, 1 if archived else 0),
    )
    conn.commit()
    conn.close()


def load_pairing_overrides(topic: str) -> dict[str, int]:
    """Return {filename: paragraph_index} drag-drop overrides Victor has
    saved for one Big Conversation topic. Empty if none have been made."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT filename, paragraph_index FROM big_conversation_pairing_override WHERE topic = ?",
        (topic,),
    ).fetchall()
    conn.close()
    return {r["filename"]: r["paragraph_index"] for r in rows}


def save_pairing_override(topic: str, filename: str, paragraph_index: int) -> None:
    """Record that Victor dragged `filename` into `paragraph_index` for this
    topic. Persisted in FW's own DB — the Instagram output folder this
    filename actually lives in is never written to."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO big_conversation_pairing_override (topic, filename, paragraph_index)
           VALUES (?, ?, ?)
           ON CONFLICT(topic, filename) DO UPDATE SET paragraph_index = excluded.paragraph_index""",
        (topic, filename, paragraph_index),
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 5: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_state.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Full suite + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
git add flatwhite/db.py flatwhite/dashboard/state.py tests/test_big_conversation_state.py
git commit -m "Big Conversation: archive flag + drag-drop pairing state in FW's own DB"
```
Expected: 127 passed / 8 pre-existing failures (124 + 3 new).

---

### Task 2: Topic bank listing (read-only filesystem scan)

**Files:**
- Create: `flatwhite/dashboard/big_conversation_bank.py`
- Test: `tests/test_big_conversation_bank.py` (new — this file grows across Tasks 2-7)

**Interfaces:**
- Produces: module constants `INSTAGRAM_OUTPUT_DIR`, `ASSETS_DIRNAME`, `IMAGE_EXTENSIONS`; function `list_topic_folders() -> list[dict]` where each dict is `{"topic": str, "reply_count": int, "processed": bool}`.
- Consumed by: Task 8's `/api/big-conversation/topics` endpoint.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_big_conversation_bank.py`:
```python
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
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'flatwhite.dashboard.big_conversation_bank'`.

- [ ] **Step 3: Create the module.** Create `flatwhite/dashboard/big_conversation_bank.py`:
```python
"""Read-only filesystem layer over the Instagram DM screenshotter's
output/ folder — the real source of Big Conversation topic candidates and
their sorted screenshots.

CRITICAL: every function in this module is read-only with respect to
INSTAGRAM_OUTPUT_DIR. It never writes, renames, moves, or deletes anything
there — that project is owned and maintained separately. Victor's archive
flag and drag-drop pairing overrides live in FW's own DB instead (see
flatwhite/dashboard/state.py).

Every public function fails soft: if the Instagram output folder (or a
topic within it) is missing, functions return an empty/soft result rather
than raising, since this machine may not have that project checked out.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote

INSTAGRAM_OUTPUT_DIR = Path(
    os.environ.get(
        "FW_INSTAGRAM_OUTPUT_DIR",
        str(Path.home() / "Documents" / "MISC" / "instagram-dm-screenshotter" / "output"),
    )
)

ASSETS_DIRNAME = "_BIG_CONVERSATION_assets"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Folders at the output root that are never Big Conversation topic
# candidates: junk, work-in-progress scratch space, or routed to a
# different segment (The Inside Track).
_EXCLUDED_EXACT = {"Rubbish", "MISC Stand alone", "Redundancies & Breaking News", "untitled folder"}
_EXCLUDED_PREFIXES = ("_", "DONE - ", "INCOMPLETE - ")


def _is_excluded(name: str) -> bool:
    if name in _EXCLUDED_EXACT:
        return True
    return any(name.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def _count_images(folder: Path) -> int:
    """Count original submission images directly under `folder`, excluding
    any copies already placed in a _BIG_CONVERSATION_assets subfolder (those
    are duplicates of originals elsewhere in the same tree, not new
    submissions)."""
    count = 0
    for p in folder.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if ASSETS_DIRNAME in p.relative_to(folder).parts:
            continue
        count += 1
    return count


def list_topic_folders() -> list[dict]:
    """Return the Big Conversation topic bank: every sorted Instagram topic
    folder that isn't excluded as junk/utility/already-manually-archived.

    Each item: {"topic": str, "reply_count": int, "processed": bool}.
    "processed" is True once the skill has written a
    _BIG_CONVERSATION_assets/ folder inside it (i.e. a piece exists).
    Does not know about Victor's explicit archive flag — that is merged in
    by the API layer (Task 8) from FW's own DB, keeping this module a pure
    filesystem read.
    """
    root = INSTAGRAM_OUTPUT_DIR
    if not root.is_dir():
        return []
    topics = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or _is_excluded(entry.name):
            continue
        topics.append({
            "topic": entry.name,
            "reply_count": _count_images(entry),
            "processed": (entry / ASSETS_DIRNAME).is_dir(),
        })
    return topics
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
git add flatwhite/dashboard/big_conversation_bank.py tests/test_big_conversation_bank.py
git commit -m "Big Conversation: read-only topic bank listing from Instagram output/"
```

---

### Task 3: Viral-extreme + T1/T2/T3 tier pool discovery

**Files:**
- Modify: `flatwhite/dashboard/big_conversation_bank.py`
- Modify: `tests/test_big_conversation_bank.py`

**Interfaces:**
- Consumes: `INSTAGRAM_OUTPUT_DIR`, `IMAGE_EXTENSIONS` from Task 2.
- Produces: `classify_tier_folder(name: str) -> str | None` (returns `"viral"`, `"T1"`, `"T2"`, `"T3"`, or `None`), `asset_url(*parts: str) -> str`, `list_pool_screenshots(topic: str) -> dict[str, list[dict]]` (keys `"viral"`, `"T1"`, `"T2"`, `"T3"`, each a list of `{"file": str, "url": str}`). Consumed by Task 6's `get_topic_detail` and Task 8's topic-detail endpoint.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_big_conversation_bank.py`:
```python
def test_classify_tier_folder_recognises_current_and_future_names():
    # Current real folder names (before increment 3's sort skill rebuild).
    assert bcb.classify_tier_folder("\U0001F525 RED HOT Top 22") == "viral"
    assert bcb.classify_tier_folder("Tier 1 - Viral") == "T1"
    assert bcb.classify_tier_folder("Tier 2 - Strong") == "T2"
    assert bcb.classify_tier_folder("Tier 3 - Ordinary") == "T3"
    assert bcb.classify_tier_folder("Tier 4 - Rubbish") is None
    # Names increment 3's rebuilt sort skill is expected to use.
    assert bcb.classify_tier_folder("VIRAL EXTREME") == "viral"
    assert bcb.classify_tier_folder("T1") == "T1"
    assert bcb.classify_tier_folder("T2") == "T2"
    assert bcb.classify_tier_folder("T3") == "T3"
    # Not a tier folder at all.
    assert bcb.classify_tier_folder("_EDITORIAL screenshots") is None
    assert bcb.classify_tier_folder("_BIG_CONVERSATION_assets") is None


def test_list_pool_screenshots_groups_by_bucket_and_drops_tier4(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    topic = tmp_path / "Kids in the Office"
    (topic / "\U0001F525 RED HOT Top 22").mkdir(parents=True)
    (topic / "\U0001F525 RED HOT Top 22" / "Erin_Lou_0001.png").write_bytes(b"x")
    (topic / "Tier 1 - Viral").mkdir()
    (topic / "Tier 1 - Viral" / "Someone_0001.png").write_bytes(b"x")
    (topic / "Tier 4 - Rubbish").mkdir()
    (topic / "Tier 4 - Rubbish" / "Junk_0001.png").write_bytes(b"x")

    pools = bcb.list_pool_screenshots("Kids in the Office")
    assert [s["file"] for s in pools["viral"]] == ["Erin_Lou_0001.png"]
    assert [s["file"] for s in pools["T1"]] == ["Someone_0001.png"]
    assert pools["T2"] == []
    assert pools["T3"] == []
    all_files = [s["file"] for shots in pools.values() for s in shots]
    assert "Junk_0001.png" not in all_files


def test_list_pool_screenshots_urls_point_at_the_asset_route(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    topic = tmp_path / "Kids in the Office"
    (topic / "Tier 1 - Viral").mkdir(parents=True)
    (topic / "Tier 1 - Viral" / "Someone_0001.png").write_bytes(b"x")

    pools = bcb.list_pool_screenshots("Kids in the Office")
    assert pools["T1"][0]["url"] == (
        "/api/big-conversation/assets/Kids%20in%20the%20Office/Tier%201%20-%20Viral/Someone_0001.png"
    )


def test_list_pool_screenshots_empty_when_topic_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    pools = bcb.list_pool_screenshots("Nonexistent Topic")
    assert pools == {"viral": [], "T1": [], "T2": [], "T3": []}
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v -k "tier or pool"
```
Expected: FAIL — `AttributeError: module 'flatwhite.dashboard.big_conversation_bank' has no attribute 'classify_tier_folder'`.

- [ ] **Step 3: Implement.** Append to `flatwhite/dashboard/big_conversation_bank.py`:
```python
_VIRAL_RE = re.compile(r"red\s*hot|viral\s*extreme", re.IGNORECASE)
_TIER_RES = {
    "T1": re.compile(r"\bt(?:ier)?\s*1\b", re.IGNORECASE),
    "T2": re.compile(r"\bt(?:ier)?\s*2\b", re.IGNORECASE),
    "T3": re.compile(r"\bt(?:ier)?\s*3\b", re.IGNORECASE),
}


def classify_tier_folder(name: str) -> str | None:
    """Map a topic subfolder name to a screenshot pool bucket: "viral",
    "T1", "T2", "T3", or None (not a recognised tier folder — e.g. "Tier 4
    - Rubbish" or "_EDITORIAL screenshots" — never shown in either pool).

    Recognises both the CURRENT folder names ("\U0001F525 RED HOT Top 22",
    "Tier 1 - Viral", "Tier 2 - Strong", "Tier 3 - Ordinary") and the
    renamed buckets increment 3's rebuilt sort skill is expected to use
    ("VIRAL EXTREME", "T1", "T2", "T3"). If increment 3 lands with
    different folder names than either of these, update the two regex
    tables above — nothing else in this module needs to change.
    """
    if _VIRAL_RE.search(name):
        return "viral"
    for bucket, pattern in _TIER_RES.items():
        if pattern.search(name):
            return bucket
    return None


def asset_url(*parts: str) -> str:
    """Build the /api/big-conversation/assets/... URL for a file living at
    INSTAGRAM_OUTPUT_DIR/<parts joined by '/'>, URL-encoding each segment
    (topic and folder names may contain spaces, colons, or emoji)."""
    rel = "/".join(quote(p, safe="") for p in parts)
    return f"/api/big-conversation/assets/{rel}"


def list_pool_screenshots(topic: str) -> dict[str, list[dict]]:
    """Return {"viral": [...], "T1": [...], "T2": [...], "T3": [...]},
    each a list of {"file": str, "url": str} for images directly inside
    the matching tier subfolder(s) of `topic`. Empty (all buckets) if the
    topic folder or the Instagram output root is absent."""
    pools: dict[str, list[dict]] = {"viral": [], "T1": [], "T2": [], "T3": []}
    topic_dir = INSTAGRAM_OUTPUT_DIR / topic
    if not topic_dir.is_dir():
        return pools
    for sub in sorted(topic_dir.iterdir()):
        if not sub.is_dir():
            continue
        bucket = classify_tier_folder(sub.name)
        if not bucket:
            continue
        for img in sorted(sub.iterdir()):
            if img.is_file() and img.suffix.lower() in IMAGE_EXTENSIONS:
                pools[bucket].append({"file": img.name, "url": asset_url(topic, sub.name, img.name)})
    return pools
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: 8 passed (4 from Task 2 + 4 new).

- [ ] **Step 5: Commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
git add flatwhite/dashboard/big_conversation_bank.py tests/test_big_conversation_bank.py
git commit -m "Big Conversation: viral-extreme + T1/T2/T3 tier pool discovery"
```

---

### Task 4: Find and parse the produced piece markdown

**Files:**
- Modify: `flatwhite/dashboard/big_conversation_bank.py`
- Modify: `tests/test_big_conversation_bank.py`

**Interfaces:**
- Produces: `find_piece_markdown(topic: str) -> Path | None`, `parse_piece_markdown(text: str) -> dict` (`{"headline": str, "paragraphs": list[str]}`). Consumed by Task 6's `get_topic_detail`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_big_conversation_bank.py`:
```python
_FIXTURE_MD = """**THE BIG CONVERSATION**

Nobody decided kids should be in the office.

First paragraph text here about the arithmetic of school holidays.

Second paragraph about it not being easy on everyone else.

Third paragraph about the upside and the insurance risk.

Fourth paragraph about companies that already sorted it.

---

# BUILD: paragraph -> screenshot map

Assets in `Kids in the Office/_BIG_CONVERSATION_assets/`.

**P1 -- the arithmetic**
1. `p1_1_Katie_Moloney.png` -- some note.
"""


def test_find_piece_markdown_matches_by_assets_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    (tmp_path / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text(_FIXTURE_MD)
    (tmp_path / "_OTHER_TOPIC_BIG_CONVERSATION.md").write_text(
        "Assets in `Some Other Topic/_BIG_CONVERSATION_assets/`.\n"
    )
    found = bcb.find_piece_markdown("Kids in the Office")
    assert found == tmp_path / "_KIDS_OFFICE_BIG_CONVERSATION.md"


def test_find_piece_markdown_returns_none_when_unprocessed(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assert bcb.find_piece_markdown("Kids in the Office") is None


def test_find_piece_markdown_returns_none_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path / "does-not-exist")
    assert bcb.find_piece_markdown("Kids in the Office") is None


def test_parse_piece_markdown_splits_headline_and_paragraphs():
    parsed = bcb.parse_piece_markdown(_FIXTURE_MD)
    assert parsed["headline"] == "Nobody decided kids should be in the office."
    assert len(parsed["paragraphs"]) == 4
    assert parsed["paragraphs"][0].startswith("First paragraph")
    assert parsed["paragraphs"][3].startswith("Fourth paragraph")
    # The BUILD map after the --- divider must not leak into paragraphs.
    assert not any("BUILD" in p for p in parsed["paragraphs"])
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v -k "markdown"
```
Expected: FAIL — `AttributeError: ... has no attribute 'find_piece_markdown'`.

- [ ] **Step 3: Implement.** Append to `flatwhite/dashboard/big_conversation_bank.py`:
```python
def find_piece_markdown(topic: str) -> Path | None:
    """Find the `_<SHORTNAME>_BIG_CONVERSATION.md` file the skill wrote for
    `topic`, at the Instagram output root. The shortname is an AI-chosen
    abbreviation (e.g. "Kids in the Office" -> "_KIDS_OFFICE_BIG_CONVERSATION.md")
    that can't be derived from the folder name programmatically — instead
    this searches every `_*_BIG_CONVERSATION.md` at the output root for the
    one whose BUILD map references this topic's own assets folder, e.g.
    "Assets in `Kids in the Office/_BIG_CONVERSATION_assets/`."

    Returns None (soft-fail, not an error) if the Instagram output root is
    absent or no matching piece has been written yet — the topic just
    isn't processed yet.
    """
    root = INSTAGRAM_OUTPUT_DIR
    if not root.is_dir():
        return None
    needle = f"{topic}/{ASSETS_DIRNAME}".lower()
    for md in sorted(root.glob("_*_BIG_CONVERSATION.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text.lower():
            return md
    return None


def parse_piece_markdown(text: str) -> dict:
    """Split a `_<TOPIC>_BIG_CONVERSATION.md` file's finished-piece section
    into {"headline": str, "paragraphs": list[str]}.

    Per the big-conversation skill's own output shape: a
    `**THE BIG CONVERSATION**` header line, a one-line bold headline, then
    one paragraph per screenshot group (p1, p2, ...), then a `---` divider
    before the BUILD map. Only the text before the first such divider is
    the piece; everything after is the paragraph->screenshot map, read
    separately from the assets folder's own filenames (Task 5).
    """
    piece = text.split("\n---\n", 1)[0].strip()
    blocks = [b.strip() for b in re.split(r"\n\s*\n", piece) if b.strip()]
    if blocks and re.fullmatch(r"\*\*THE BIG CONVERSATION\*\*", blocks[0]):
        blocks = blocks[1:]
    headline = blocks[0] if blocks else ""
    paragraphs = blocks[1:]
    return {"headline": headline, "paragraphs": paragraphs}
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: 12 passed.

- [ ] **Step 5: Commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
git add flatwhite/dashboard/big_conversation_bank.py tests/test_big_conversation_bank.py
git commit -m "Big Conversation: find + parse the produced _*_BIG_CONVERSATION.md piece"
```

---

### Task 5: Paragraph-to-screenshot pairing from the skill's own filename convention

**Files:**
- Modify: `flatwhite/dashboard/big_conversation_bank.py`
- Modify: `tests/test_big_conversation_bank.py`

**Interfaces:**
- Produces: `list_paragraph_screenshots(topic: str) -> dict[int, list[dict]]` (keys are 1-based paragraph numbers, values are `{"file": str, "rank": int, "url": str}` sorted by rank). Consumed by Task 6's `get_topic_detail`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_big_conversation_bank.py`:
```python
def test_list_paragraph_screenshots_groups_and_ranks(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assets = tmp_path / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    for fname in [
        "p1_1_Katie_Moloney.png", "p1_alt_IMG_7962.jpg", "p1_alt2_Emma_Ainley.png",
        "p2_1_IMG_7955.jpg",
    ]:
        (assets / fname).write_bytes(b"x")

    grouped = bcb.list_paragraph_screenshots("Kids in the Office")
    assert [s["file"] for s in grouped[1]] == [
        "p1_1_Katie_Moloney.png", "p1_alt_IMG_7962.jpg", "p1_alt2_Emma_Ainley.png",
    ]
    assert [s["file"] for s in grouped[2]] == ["p2_1_IMG_7955.jpg"]


def test_list_paragraph_screenshots_ignores_non_matching_files(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assets = tmp_path / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"x")
    (assets / ".DS_Store").write_bytes(b"junk")
    (assets / "notes.txt").write_text("not an image")

    grouped = bcb.list_paragraph_screenshots("Kids in the Office")
    assert list(grouped.keys()) == [1]
    assert len(grouped[1]) == 1


def test_list_paragraph_screenshots_empty_when_not_processed(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assert bcb.list_paragraph_screenshots("Kids in the Office") == {}
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v -k "paragraph_screenshots"
```
Expected: FAIL — `AttributeError: ... has no attribute 'list_paragraph_screenshots'`.

- [ ] **Step 3: Implement.** Append to `flatwhite/dashboard/big_conversation_bank.py`:
```python
_ASSET_NAME_RE = re.compile(r"^p(\d+)_(1|alt\d*)_.+\.(?:png|jpg|jpeg)$", re.IGNORECASE)


def _asset_rank(token: str) -> int:
    """Sort key for a screenshot's rank token: "1" (primary) sorts first,
    then "alt", then "alt2", "alt3", ... in order."""
    token = token.lower()
    if token == "1":
        return 0
    if token == "alt":
        return 1
    return int(token[3:])  # "alt2" -> 2, "alt3" -> 3


def list_paragraph_screenshots(topic: str) -> dict[int, list[dict]]:
    """Group `<topic>/_BIG_CONVERSATION_assets/*.png` files by paragraph
    number, using the skill's own naming convention
    `p<paragraph>_<rank>_<handle>.png` (rank is "1" for the primary pick,
    "alt"/"alt2"/"alt3" for ranked alternates — see SKILL.md's "Emit
    outputs" step). Returns {} if the assets folder is absent (topic not
    processed yet) or the Instagram output root is absent.
    """
    assets_dir = INSTAGRAM_OUTPUT_DIR / topic / ASSETS_DIRNAME
    if not assets_dir.is_dir():
        return {}
    by_paragraph: dict[int, list[dict]] = {}
    for img in assets_dir.iterdir():
        if not img.is_file():
            continue
        match = _ASSET_NAME_RE.match(img.name)
        if not match:
            continue
        paragraph = int(match.group(1))
        rank = _asset_rank(match.group(2))
        by_paragraph.setdefault(paragraph, []).append({
            "file": img.name,
            "rank": rank,
            "url": asset_url(topic, ASSETS_DIRNAME, img.name),
        })
    for shots in by_paragraph.values():
        shots.sort(key=lambda s: s["rank"])
    return dict(sorted(by_paragraph.items()))
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: 15 passed.

- [ ] **Step 5: Commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
git add flatwhite/dashboard/big_conversation_bank.py tests/test_big_conversation_bank.py
git commit -m "Big Conversation: paragraph->screenshot pairing from the skill's filename convention"
```

---

### Task 6: Combine into one topic detail response, with pairing overrides applied

**Files:**
- Modify: `flatwhite/dashboard/big_conversation_bank.py`
- Modify: `tests/test_big_conversation_bank.py`

**Interfaces:**
- Consumes: everything from Tasks 2-5 in this module.
- Produces: `get_topic_detail(topic: str, pairing_overrides: dict[str, int] | None = None) -> dict`. Unprocessed shape: `{"processed": False, "topic": str, "pools": {...}}`. Processed shape: `{"processed": True, "topic": str, "headline": str, "paragraphs": [{"index": int, "text": str, "screenshots": [...]}], "pools": {...}}`. Consumed by Task 8's topic-detail endpoint, which supplies `pairing_overrides` from `state.load_pairing_overrides(topic)`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_big_conversation_bank.py`:
```python
def _seed_processed_topic(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    (tmp_path / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text(_FIXTURE_MD)
    assets = tmp_path / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"x")
    (assets / "p2_1_IMG_7955.jpg").write_bytes(b"x")


def test_get_topic_detail_soft_fails_when_not_processed(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    detail = bcb.get_topic_detail("Kids in the Office")
    assert detail == {
        "processed": False,
        "topic": "Kids in the Office",
        "pools": {"viral": [], "T1": [], "T2": [], "T3": []},
    }


def test_get_topic_detail_returns_paragraphs_with_paired_screenshots(tmp_path, monkeypatch):
    _seed_processed_topic(tmp_path, monkeypatch)
    detail = bcb.get_topic_detail("Kids in the Office")
    assert detail["processed"] is True
    assert detail["headline"] == "Nobody decided kids should be in the office."
    assert len(detail["paragraphs"]) == 4
    assert detail["paragraphs"][0]["index"] == 1
    assert [s["file"] for s in detail["paragraphs"][0]["screenshots"]] == ["p1_1_Katie_Moloney.png"]
    assert [s["file"] for s in detail["paragraphs"][1]["screenshots"]] == ["p2_1_IMG_7955.jpg"]
    assert detail["paragraphs"][2]["screenshots"] == []


def test_get_topic_detail_applies_pairing_overrides(tmp_path, monkeypatch):
    _seed_processed_topic(tmp_path, monkeypatch)
    overrides = {"p1_1_Katie_Moloney.png": 2}
    detail = bcb.get_topic_detail("Kids in the Office", pairing_overrides=overrides)
    assert detail["paragraphs"][0]["screenshots"] == []
    files_in_p2 = {s["file"] for s in detail["paragraphs"][1]["screenshots"]}
    assert files_in_p2 == {"p1_1_Katie_Moloney.png", "p2_1_IMG_7955.jpg"}
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v -k "topic_detail"
```
Expected: FAIL — `AttributeError: ... has no attribute 'get_topic_detail'`.

- [ ] **Step 3: Implement.** Append to `flatwhite/dashboard/big_conversation_bank.py`:
```python
def get_topic_detail(topic: str, pairing_overrides: dict[str, int] | None = None) -> dict:
    """Return the full Big Conversation working page for one topic: the
    drafted piece's headline + paragraphs, each paragraph's paired
    screenshots (with any drag-drop overrides applied), and the viral /
    T1 / T2 / T3 pools.

    `pairing_overrides` is {filename: paragraph_index}, loaded by the
    caller from FW's own DB (flatwhite.dashboard.state.load_pairing_overrides)
    — this module never persists anything itself; it only applies
    overrides handed to it, keeping filesystem reads and DB writes cleanly
    separated.

    Soft-fails when the topic isn't processed yet (no piece markdown, or
    no screenshots parsed from its assets folder): returns
    {"processed": False, "topic": topic, "pools": {...}} so the UI can show
    a "waiting for the skill to run" state instead of an error.
    """
    pairing_overrides = pairing_overrides or {}
    pools = list_pool_screenshots(topic)
    md_path = find_piece_markdown(topic)
    by_paragraph = list_paragraph_screenshots(topic)

    if md_path is None or not by_paragraph:
        return {"processed": False, "topic": topic, "pools": pools}

    if pairing_overrides:
        regrouped: dict[int, list[dict]] = {p: [] for p in by_paragraph}
        for paragraph, shots in by_paragraph.items():
            for shot in shots:
                target = pairing_overrides.get(shot["file"], paragraph)
                regrouped.setdefault(target, []).append(shot)
        by_paragraph = regrouped

    parsed = parse_piece_markdown(md_path.read_text(encoding="utf-8", errors="replace"))
    paragraphs = [
        {"index": i, "text": text, "screenshots": by_paragraph.get(i, [])}
        for i, text in enumerate(parsed["paragraphs"], start=1)
    ]

    return {
        "processed": True,
        "topic": topic,
        "headline": parsed["headline"],
        "paragraphs": paragraphs,
        "pools": pools,
    }
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: 18 passed.

- [ ] **Step 5: Commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
git add flatwhite/dashboard/big_conversation_bank.py tests/test_big_conversation_bank.py
git commit -m "Big Conversation: combined topic detail (piece + paired screenshots + pools)"
```

---

### Task 7: Path-traversal-safe asset path resolver

**Files:**
- Modify: `flatwhite/dashboard/big_conversation_bank.py`
- Modify: `tests/test_big_conversation_bank.py`

**Interfaces:**
- Produces: `resolve_asset_path(rel_path: str) -> Path | None`. Consumed by Task 8's static image route.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_big_conversation_bank.py`:
```python
def test_resolve_asset_path_serves_file_inside_root(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assets = tmp_path / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    img = assets / "p1_1_Katie_Moloney.png"
    img.write_bytes(b"fake-png-bytes")

    resolved = bcb.resolve_asset_path("Kids in the Office/_BIG_CONVERSATION_assets/p1_1_Katie_Moloney.png")
    assert resolved == img.resolve()


def test_resolve_asset_path_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    (tmp_path / "topic").mkdir()
    outside = tmp_path.parent / "secret.png"
    outside.write_bytes(b"nope")
    assert bcb.resolve_asset_path("../secret.png") is None
    assert bcb.resolve_asset_path("topic/../../secret.png") is None


def test_resolve_asset_path_rejects_absolute_path(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assert bcb.resolve_asset_path("/etc/passwd") is None


def test_resolve_asset_path_rejects_non_image_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    (tmp_path / "topic.md").write_text("not an image")
    assert bcb.resolve_asset_path("topic.md") is None


def test_resolve_asset_path_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    assert bcb.resolve_asset_path("topic/_BIG_CONVERSATION_assets/missing.png") is None


def test_resolve_asset_path_soft_fails_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path / "nope")
    assert bcb.resolve_asset_path("topic/x.png") is None
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v -k "resolve_asset_path"
```
Expected: FAIL — `AttributeError: ... has no attribute 'resolve_asset_path'`.

- [ ] **Step 3: Implement.** Append to `flatwhite/dashboard/big_conversation_bank.py`:
```python
def resolve_asset_path(rel_path: str) -> Path | None:
    """Resolve a `/api/big-conversation/assets/<rel_path>` request to a real
    file strictly inside INSTAGRAM_OUTPUT_DIR.

    Returns None (the caller responds 404) if: the Instagram output root is
    absent; `rel_path` is empty or absolute (an absolute path would make
    `root / rel_path` ignore `root` entirely — pathlib's own join
    behaviour); the resolved path escapes the root (covers `..` segments
    and symlinks that point outside); the extension isn't an allowed image
    type; or the file doesn't exist.
    """
    root = INSTAGRAM_OUTPUT_DIR
    if not root.is_dir():
        return None
    if not rel_path or Path(rel_path).is_absolute():
        return None
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / rel_path).resolve()
    except OSError:
        return None
    if not candidate.is_relative_to(root_resolved):
        return None
    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    if not candidate.is_file():
        return None
    return candidate
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_bank.py -v
```
Expected: 24 passed.

- [ ] **Step 5: Full module test file + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
git add flatwhite/dashboard/big_conversation_bank.py tests/test_big_conversation_bank.py
git commit -m "Big Conversation: path-traversal-safe screenshot asset resolver"
```
Expected: 151 passed / 8 pre-existing failures (127 + 24 new).

---

### Task 8: Read endpoints — topic list, topic detail, screenshot serving

**Files:**
- Modify: `flatwhite/dashboard/api.py` (add near the end, after the existing "New endpoints" section, ~line 766)
- Test: `tests/test_big_conversation_api.py` (new — grows across Tasks 8-9)

**Interfaces:**
- Consumes: `flatwhite.dashboard.big_conversation_bank` (Tasks 2-7), `flatwhite.dashboard.state.load_topic_archive_state` and `load_pairing_overrides` (Task 1).
- Produces routes: `GET /api/big-conversation/topics`, `GET /api/big-conversation/topic/{topic}`, `GET /api/big-conversation/assets/{rel_path:path}`. Consumed by Task 10-11's UI.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_big_conversation_api.py`:
```python
"""Tests for the Big Conversation API endpoints (increment 4).

Both the DB (archive + pairing state) and the filesystem
(big_conversation_bank.INSTAGRAM_OUTPUT_DIR) are monkeypatched — no real
Claude/network calls, and the real Instagram output folder is never read
by these tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import flatwhite.db as db_module
import flatwhite.dashboard.big_conversation_bank as bcb


@pytest.fixture
def bc_env(tmp_path, monkeypatch):
    """A temp Instagram output/ tree + a temp FW DB, both isolated from the
    real filesystem/DB. Yields the fake output/ root."""
    db_path = tmp_path / "bc_api_test.db"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", output_dir)
        yield output_dir


def test_topics_endpoint_lists_unprocessed_topic(bc_env):
    topic = bc_env / "Kids in the Office"
    topic.mkdir()
    (topic / "Person_0.png").write_bytes(b"x")
    from flatwhite.dashboard.api import api_big_conversation_topics

    result = api_big_conversation_topics()
    data = json.loads(result.body)
    assert data["root_exists"] is True
    topics = {t["topic"]: t for t in data["topics"]}
    assert topics["Kids in the Office"]["reply_count"] == 1
    assert topics["Kids in the Office"]["archived"] is False
    assert topics["Kids in the Office"]["processed"] is False


def test_topics_endpoint_soft_fails_when_root_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "bc_api_missing.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path / "does-not-exist")
        from flatwhite.dashboard.api import api_big_conversation_topics

        result = api_big_conversation_topics()
        data = json.loads(result.body)
        assert data["topics"] == []
        assert data["root_exists"] is False


def test_topic_detail_endpoint_soft_fails_when_not_processed(bc_env):
    (bc_env / "Kids in the Office").mkdir()
    from flatwhite.dashboard.api import api_big_conversation_topic

    result = api_big_conversation_topic("Kids in the Office")
    data = json.loads(result.body)
    assert data["processed"] is False


def test_topic_detail_endpoint_returns_paragraphs_when_processed(bc_env):
    (bc_env / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text(
        "**THE BIG CONVERSATION**\n\n"
        "Nobody decided kids should be in the office.\n\n"
        "First paragraph text.\n\n"
        "---\n\nAssets in `Kids in the Office/_BIG_CONVERSATION_assets/`.\n"
    )
    assets = bc_env / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"x")
    from flatwhite.dashboard.api import api_big_conversation_topic

    result = api_big_conversation_topic("Kids in the Office")
    data = json.loads(result.body)
    assert data["processed"] is True
    assert data["paragraphs"][0]["screenshots"][0]["file"] == "p1_1_Katie_Moloney.png"


def test_asset_route_serves_file(bc_env):
    assets = bc_env / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"fake-bytes")
    from flatwhite.dashboard.api import api_big_conversation_asset

    result = api_big_conversation_asset("Kids in the Office/_BIG_CONVERSATION_assets/p1_1_Katie_Moloney.png")
    assert result.status_code == 200


def test_asset_route_404s_on_traversal(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_asset

    result = api_big_conversation_asset("../../etc/passwd")
    assert result.status_code == 404


def test_asset_route_404s_on_missing_file(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_asset

    result = api_big_conversation_asset("Kids in the Office/_BIG_CONVERSATION_assets/missing.png")
    assert result.status_code == 404
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_api.py -v
```
Expected: FAIL — `ImportError: cannot import name 'api_big_conversation_topics'`.

- [ ] **Step 3: Add the routes.** In `flatwhite/dashboard/api.py`, after the existing `/api/big-conversation-candidates` block (the legacy DB-driven endpoint stays untouched — it belongs to increments not yet built, and other code paths may still reference it), add:
```python
# ── Big Conversation (Instagram DM screenshotter pipeline) ─────────────────
# Increment 4: the produced piece + screenshots live in the Instagram DM
# screenshotter project's output/ folder (read-only from FW's side — the
# `big-conversation` skill that writes them runs Claude-side, outside this
# process; FW only prepares + reads). See
# flatwhite/dashboard/big_conversation_bank.py for the filesystem logic.

from flatwhite.dashboard import big_conversation_bank as _bcb
from flatwhite.dashboard.state import (
    load_topic_archive_state,
    load_pairing_overrides,
)


@app.get("/api/big-conversation/topics")
def api_big_conversation_topics() -> JSONResponse:
    """Return the Big Conversation topic bank: every sorted Instagram topic
    folder not excluded as junk/utility, each with its reply (screenshot)
    count, whether the skill has already produced a piece for it, and
    whether Victor has archived it. Fails soft (empty list, root_exists:
    false) if the Instagram output folder isn't present on this machine."""
    archived = load_topic_archive_state()
    topics = _bcb.list_topic_folders()
    for t in topics:
        t["archived"] = archived.get(t["topic"], False)
    return JSONResponse({"topics": topics, "root_exists": _bcb.INSTAGRAM_OUTPUT_DIR.is_dir()})


@app.get("/api/big-conversation/topic/{topic}")
def api_big_conversation_topic(topic: str) -> JSONResponse:
    """Return the produced piece (if any) + paragraph->screenshot pairing +
    viral/tier pools for one topic. `processed: false` means the skill
    hasn't written its output yet — not an error."""
    overrides = load_pairing_overrides(topic)
    detail = _bcb.get_topic_detail(topic, pairing_overrides=overrides)
    return JSONResponse(detail)


@app.get("/api/big-conversation/assets/{rel_path:path}")
def api_big_conversation_asset(rel_path: str):
    """Serve one screenshot PNG/JPG from the Instagram output folder,
    read-only and path-traversal-safe (only ever inside
    big_conversation_bank.INSTAGRAM_OUTPUT_DIR)."""
    resolved = _bcb.resolve_asset_path(rel_path)
    if resolved is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(resolved)
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_api.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Full suite + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
git add flatwhite/dashboard/api.py tests/test_big_conversation_api.py
git commit -m "Big Conversation: topics list, topic detail, and asset-serving endpoints"
```
Expected: 157 passed / 8 pre-existing failures (151 + 6 new).

---

### Task 9: Write endpoints — archive, prepare, drag-drop pairing

**Files:**
- Modify: `flatwhite/dashboard/api.py`
- Modify: `tests/test_big_conversation_api.py`

**Interfaces:**
- Consumes: `state.set_topic_archived`, `state.save_pairing_override` (Task 1); `_bcb.get_topic_detail` (Task 6).
- Produces routes: `POST /api/big-conversation/archive`, `POST /api/big-conversation/topic/{topic}/prepare`, `POST /api/big-conversation/topic/{topic}/pairing`. Consumed by Task 10-11's UI.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_big_conversation_api.py`:
```python
import asyncio


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def test_archive_round_trips_through_topics_endpoint(bc_env):
    (bc_env / "Kids in the Office").mkdir()
    from flatwhite.dashboard.api import api_big_conversation_archive, api_big_conversation_topics

    asyncio.get_event_loop().run_until_complete(
        api_big_conversation_archive(FakeRequest({"topic": "Kids in the Office", "archived": True}))
    )
    data = json.loads(api_big_conversation_topics().body)
    topics = {t["topic"]: t for t in data["topics"]}
    assert topics["Kids in the Office"]["archived"] is True

    asyncio.get_event_loop().run_until_complete(
        api_big_conversation_archive(FakeRequest({"topic": "Kids in the Office", "archived": False}))
    )
    data = json.loads(api_big_conversation_topics().body)
    topics = {t["topic"]: t for t in data["topics"]}
    assert topics["Kids in the Office"]["archived"] is False


def test_archive_requires_topic(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_archive

    result = asyncio.get_event_loop().run_until_complete(
        api_big_conversation_archive(FakeRequest({"archived": True}))
    )
    assert result.status_code == 400


def test_prepare_endpoint_returns_instruction_for_existing_folder(bc_env):
    (bc_env / "Kids in the Office").mkdir()
    from flatwhite.dashboard.api import api_big_conversation_prepare

    result = api_big_conversation_prepare("Kids in the Office")
    data = json.loads(result.body)
    assert "big-conversation" in data["instruction"]
    assert "Kids in the Office" in data["instruction"]
    assert data["folder_path"].endswith("Kids in the Office")


def test_prepare_endpoint_404s_for_missing_folder(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_prepare

    result = api_big_conversation_prepare("Does Not Exist")
    assert result.status_code == 404


def test_pairing_endpoint_moves_screenshot_and_persists(bc_env):
    (bc_env / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text(
        "**THE BIG CONVERSATION**\n\n"
        "Headline here.\n\n"
        "Paragraph one.\n\nParagraph two.\n\n"
        "---\n\nAssets in `Kids in the Office/_BIG_CONVERSATION_assets/`.\n"
    )
    assets = bc_env / "Kids in the Office" / bcb.ASSETS_DIRNAME
    assets.mkdir(parents=True)
    (assets / "p1_1_Katie_Moloney.png").write_bytes(b"x")
    from flatwhite.dashboard.api import api_big_conversation_pairing, api_big_conversation_topic

    asyncio.get_event_loop().run_until_complete(
        api_big_conversation_pairing(
            "Kids in the Office",
            FakeRequest({"filename": "p1_1_Katie_Moloney.png", "paragraph_index": 2}),
        )
    )
    data = json.loads(api_big_conversation_topic("Kids in the Office").body)
    assert data["paragraphs"][0]["screenshots"] == []
    assert data["paragraphs"][1]["screenshots"][0]["file"] == "p1_1_Katie_Moloney.png"


def test_pairing_endpoint_requires_filename_and_int_paragraph(bc_env):
    from flatwhite.dashboard.api import api_big_conversation_pairing

    result = asyncio.get_event_loop().run_until_complete(
        api_big_conversation_pairing("Kids in the Office", FakeRequest({"filename": "x.png"}))
    )
    assert result.status_code == 400
```

- [ ] **Step 2: Run and confirm the failure.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_api.py -v -k "archive or prepare or pairing"
```
Expected: FAIL — `ImportError: cannot import name 'api_big_conversation_archive'`.

- [ ] **Step 3: Add the routes.** In `flatwhite/dashboard/api.py`, update the import block added in Task 8 and add the three write routes:
```python
from flatwhite.dashboard.state import (
    load_topic_archive_state,
    set_topic_archived,
    load_pairing_overrides,
    save_pairing_override,
)


@app.post("/api/big-conversation/archive")
async def api_big_conversation_archive(request: Request) -> JSONResponse:
    """Archive or unarchive a topic bank entry.

    Body: {"topic": str, "archived": bool}
    """
    body = await request.json()
    topic = body.get("topic", "")
    if not topic:
        return JSONResponse({"error": "topic is required"}, status_code=400)
    archived = bool(body.get("archived", True))
    set_topic_archived(topic, archived)
    return JSONResponse({"topic": topic, "archived": archived})


@app.post("/api/big-conversation/topic/{topic}/prepare")
def api_big_conversation_prepare(topic: str) -> JSONResponse:
    """Prepare a topic for processing.

    FW cannot call the Claude `big-conversation` skill itself — there is no
    server-side Claude/skill invocation in this app. This confirms the
    topic folder is ready and hands back the exact instruction to run the
    skill in a Claude session, mirroring PS Dash's "Design B" pattern (the
    dash prepares + reads; generation happens Claude-side). Once the skill
    has run, GET /api/big-conversation/topic/{topic} picks up what it wrote.
    """
    folder = _bcb.INSTAGRAM_OUTPUT_DIR / topic
    if not folder.is_dir():
        return JSONResponse({"error": f"Topic folder not found: {topic}"}, status_code=404)
    instruction = (
        f'Run the big-conversation skill on "{topic}" from '
        f'{_bcb.INSTAGRAM_OUTPUT_DIR} (a Claude session in the Instagram '
        f'DM screenshotter project), then come back here and click Refresh.'
    )
    return JSONResponse({"topic": topic, "folder_path": str(folder), "instruction": instruction})


@app.post("/api/big-conversation/topic/{topic}/pairing")
async def api_big_conversation_pairing(topic: str, request: Request) -> JSONResponse:
    """Record a drag-drop: move one screenshot to a different paragraph.

    Body: {"filename": str, "paragraph_index": int}
    Persisted in FW's own DB; never written into the Instagram output
    folder the screenshot actually lives in.
    """
    body = await request.json()
    filename = body.get("filename", "")
    paragraph_index = body.get("paragraph_index")
    if not filename or not isinstance(paragraph_index, int):
        return JSONResponse(
            {"error": "filename and paragraph_index (int) are required"}, status_code=400
        )
    save_pairing_override(topic, filename, paragraph_index)
    return JSONResponse({"topic": topic, "filename": filename, "paragraph_index": paragraph_index})
```

- [ ] **Step 4: Run and confirm the pass.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest tests/test_big_conversation_api.py -v
```
Expected: 12 passed.

- [ ] **Step 5: Full suite + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5
git add flatwhite/dashboard/api.py tests/test_big_conversation_api.py
git commit -m "Big Conversation: archive, prepare, and drag-drop pairing endpoints"
```
Expected: 163 passed / 8 pre-existing failures (157 + 6 new).

---

### Task 10: UI — the topic bank page

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`:
  - `<style>` block: insert new CSS rules just before `</style>` (currently line 258)
  - `S` state object (~line 270-315): add fields
  - `loadPageData()`, the `case "big_conversation":` block (currently ~lines 455-469)
  - `esc()` helper area (~line 369-374): add `jsq()` alongside it
  - Delete the legacy Big Conversation block (currently lines 982-1134: `renderBigConvBody`, `renderBigConv`, `selectBigConv`, `toggleCustomBigConv`, `useCustomBigConv`, `runBigConv`, `proceedBigConv`) and replace with the new implementation. **Verify these exact line numbers in the working tree before editing** — increment 1's shell changes may have shifted them.

**Interfaces:**
- Consumes: `GET /api/big-conversation/topics`, `POST /api/big-conversation/archive` (Tasks 8-9); increment 1's `SEGMENTS`/`selectSegment`/`toggleReady`/design tokens (`--card`, `--sep`, `--label2`, `--label3`, `--accent-soft`, `--r-card`).
- Produces: `renderBigConv(el)` (same name/signature increment 1 wires into the router — do not rename), `renderBigConvBank()`, `openBigConvTopic(topic)`, `archiveBigConvTopic(topic)`, `jsq(s)`. `S.bigConvTopics`, `S.bigConvRootExists`, `S.bigConvSelectedTopic` are consumed by Task 11.

- [ ] **Step 1: Record baseline + verify current line numbers.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest -q 2>&1 | tail -3
grep -n "function renderBigConv\|function selectBigConv\|function runBigConv\|function proceedBigConv\|function toggleCustomBigConv\|function useCustomBigConv\|case \"big_conversation\":" flatwhite/dashboard/static/index.html
```
Note the exact current line numbers before editing (increment 1's shell work may have shifted them from this plan's numbers).

- [ ] **Step 2: Add the `jsq()` helper** next to `esc()` (~line 374 in the pre-increment-1 file; find `function esc(s) {` and add immediately after its closing brace):
```javascript
function jsq(s) {
  // A JS single-quoted string literal, safe to embed inside a
  // double-quoted HTML attribute (e.g. onclick="fn(' + jsq(x) + ')").
  // Topic names can contain colons/spaces (e.g. "Teams:Slack Monitoring")
  // so plain concatenation is not safe here.
  return "'" + String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
}
```

- [ ] **Step 3: Add new `S` state fields.** In the `var S = { ... }` object, add (anywhere among the existing fields, e.g. near `bigConvCandidates`):
```javascript
  bigConvTopics: null,
  bigConvRootExists: true,
  bigConvSelectedTopic: null,
  bigConvDetail: null,
  bigConvPrepare: null,
  bigConvShowTierPool: false,
```

- [ ] **Step 4: Replace the `case "big_conversation":` block in `loadPageData()`.** Replace the existing block (topic-heat + legacy candidates loading) with:
```javascript
    case "big_conversation":
      return api("/api/big-conversation/topics").then(function(d) {
        S.bigConvTopics = d.topics || [];
        S.bigConvRootExists = d.root_exists;
      });
```

- [ ] **Step 5: Delete the legacy Big Conversation render block and replace it.** Delete `renderBigConvBody`, `renderBigConv`, `selectBigConv`, `toggleCustomBigConv`, `useCustomBigConv`, `runBigConv`, `proceedBigConv` in their entirety (the block bounded by `/* ═══... SECTION: OFF THE CLOCK ═══... */` immediately after it — stop before that comment). Replace with:
```javascript
function renderBigConv(el) {
  var h = '<div class="sh"><div><h2>Big Conversation</h2><div class="sub">Topic bank sorted from the Instagram DM campaign</div></div></div>';
  if (!S.bigConvRootExists) {
    h += '<div class="card"><p style="color:var(--label2);font-size:13px;">Instagram screenshotter output folder not found on this machine. Nothing to show yet.</p></div>';
    el.innerHTML = h;
    return;
  }
  if (S.bigConvSelectedTopic) {
    h += renderBigConvTopicDetail();
  } else {
    h += renderBigConvBank();
  }
  el.innerHTML = h;
}

function renderBigConvBank() {
  var topics = (S.bigConvTopics || []).filter(function(t) { return !t.archived; });
  if (!topics.length) return '<div class="card"><p style="color:var(--label2);font-size:13px;">No unarchived topics in the bank.</p></div>';
  var h = '<div class="bc-bank">';
  topics.forEach(function(t) {
    h += '<div class="bc-topic-card">';
    h += '<div class="bc-topic-name">' + esc(t.topic) + '</div>';
    h += '<div class="bc-topic-meta">' + t.reply_count + ' submissions' + (t.processed ? ' &middot; piece drafted' : '') + '</div>';
    h += '<div class="bc-topic-actions">';
    h += '<button class="btn btn-sm btn-primary" onclick="openBigConvTopic(' + jsq(t.topic) + ')">Open</button>';
    h += '<button class="btn btn-sm btn-secondary" onclick="archiveBigConvTopic(' + jsq(t.topic) + ')">Archive</button>';
    h += '</div></div>';
  });
  h += '</div>';
  return h;
}

function openBigConvTopic(topic) {
  S.bigConvSelectedTopic = topic;
  S.bigConvDetail = null;
  S.bigConvPrepare = null;
  S.bigConvShowTierPool = false;
  render();
  loadBigConvTopicDetail(topic);
}

function closeBigConvTopic() {
  S.bigConvSelectedTopic = null;
  S.bigConvDetail = null;
  render();
}

function loadBigConvTopicDetail(topic) {
  api("/api/big-conversation/topic/" + encodeURIComponent(topic)).then(function(d) {
    S.bigConvDetail = d;
    render();
  });
}

function archiveBigConvTopic(topic) {
  api("/api/big-conversation/archive", { method: "POST", body: { topic: topic, archived: true } })
    .then(function() {
      (S.bigConvTopics || []).forEach(function(t) { if (t.topic === topic) t.archived = true; });
      render();
      showToast("Archived");
    })
    .catch(function(e) { showToast("Error: " + e.message, "error"); });
}
```
(`renderBigConvTopicDetail`, `prepareBigConvTopic`, `refreshBigConvTopic`, `toggleBigConvTierPool`, and the drag handlers are added in Task 11 — until then, `renderBigConvTopicDetail` is referenced but not yet defined, so Step 6 stubs it.)

- [ ] **Step 6: Add a temporary stub so the page doesn't break before Task 11 runs.** Immediately after `closeBigConvTopic()`:
```javascript
function renderBigConvTopicDetail() {
  // Replaced with the full paragraph/screenshot detail view in Task 11.
  return '<div class="card"><p>Loading topic detail…</p></div>';
}
```

- [ ] **Step 7: Add the bank CSS.** In the `<style>` block, just before the closing `</style>`, add:
```css
.bc-bank{display:flex;flex-direction:column;gap:10px}
.bc-topic-card{border:1px solid var(--sep);border-radius:var(--r-card);padding:12px 14px;display:flex;align-items:center;gap:14px}
.bc-topic-name{font-weight:600;flex:1}
.bc-topic-meta{color:var(--label2);font-size:12px}
.bc-topic-actions{display:flex;gap:8px}
```

- [ ] **Step 8: Verify (presence + manual).** Boot the dashboard:
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/
curl -s http://127.0.0.1:8500/ | grep -c 'function renderBigConvBank'
curl -s http://127.0.0.1:8500/ | grep -c 'function jsq'
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8500/api/big-conversation/topics"
```
Expected: `200`, `1`, `1`, `200`. Manual: open `/`, click into the Big Conversation segment. If the real Instagram project is present on this machine, the topic bank shows real folders (e.g. `Career Pivoting`, `AI Usage`, `Parental Leave` — see "The real data this increment reads" above) with their submission counts; `Kids in the Office` / `Conference Room Sharing` / `PIP Term Length` show "piece drafted" since they already have `_BIG_CONVERSATION_assets/`. Click Archive on one — it disappears from the list. Kill the server: `kill %1`.

- [ ] **Step 9: Python suite unchanged + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -3
git add flatwhite/dashboard/static/index.html
git commit -m "Big Conversation UI: topic bank list, open, and archive"
```
Expected: unchanged from Task 9 (163 passed / 8 pre-existing) — this task only touches the static frontend.

---

### Task 11: UI — the topic detail page (paragraphs, screenshot pools, drag-drop, process/refresh)

**Files:**
- Modify: `flatwhite/dashboard/static/index.html` (replace the `renderBigConvTopicDetail` stub from Task 10; add supporting functions + CSS).

**Interfaces:**
- Consumes: `GET /api/big-conversation/topic/{topic}`, `POST /api/big-conversation/topic/{topic}/prepare`, `POST /api/big-conversation/topic/{topic}/pairing` (Tasks 8-9); `jsq()`, `esc()`, `toggleReady()` (increment 1); `S.bigConvSelectedTopic`, `S.bigConvDetail`, `S.bigConvPrepare`, `S.bigConvShowTierPool` (Task 10 / this task).

- [ ] **Step 1: Replace the stub with the real detail renderer.** Replace the `renderBigConvTopicDetail` function added in Task 10 Step 6 with:
```javascript
function renderBigConvTopicDetail() {
  var topic = S.bigConvSelectedTopic;
  var h = '<div class="bc-detail-head">';
  h += '<button class="btn btn-sm btn-secondary" onclick="closeBigConvTopic()">&larr; Back to bank</button>';
  h += '<span class="bc-detail-title">' + esc(topic) + '</span>';
  h += '</div>';

  var d = S.bigConvDetail;
  if (!d) return h + '<div class="card"><p>Loading…</p></div>';

  if (!d.processed) {
    h += '<div class="card">';
    h += '<p style="font-size:13px;color:var(--label2);">No piece drafted yet for this topic.</p>';
    h += '<button class="btn btn-primary" onclick="prepareBigConvTopic(' + jsq(topic) + ')">Process</button>';
    if (S.bigConvPrepare && S.bigConvPrepare.topic === topic) {
      h += '<div class="bc-instruction">' + esc(S.bigConvPrepare.instruction) + '</div>';
      h += '<button class="btn btn-sm btn-secondary" onclick="refreshBigConvTopic()">Refresh</button>';
    }
    h += '</div>';
    h += renderBigConvViralPool(d.pools);
    return h;
  }

  h += '<div class="bc-headline">' + esc(d.headline) + '</div>';
  (d.paragraphs || []).forEach(function(p) {
    h += '<div class="bc-paragraph" ondragover="bcDragOver(event)" ondrop="bcDrop(event,' + p.index + ')">';
    h += '<div class="bc-p-text">' + esc(p.text) + '</div>';
    h += '<div class="bc-shots">';
    (p.screenshots || []).forEach(function(s) {
      h += '<img class="bc-shot" src="' + s.url + '" draggable="true" ondragstart="bcDragStart(event,' + jsq(s.file) + ')" title="' + esc(s.file) + '">';
    });
    h += '</div></div>';
  });

  h += renderBigConvViralPool(d.pools);
  h += '<div class="bc-tier-toggle"><button class="btn btn-sm btn-secondary" onclick="toggleBigConvTierPool()">' + (S.bigConvShowTierPool ? 'Hide' : 'Show') + ' tier pool</button></div>';
  if (S.bigConvShowTierPool) h += renderBigConvTierPools(d.pools);

  h += '<div style="margin-top:16px;"><button class="btn btn-success" onclick="toggleReady(\'big_conversation\')">Mark ready</button></div>';
  return h;
}

function renderBigConvViralPool(pools) {
  var shots = (pools && pools.viral) || [];
  var h = '<div class="bc-pool"><div class="bc-pool-label">Viral extreme (always shown, in case a paragraph pick missed something compelling)</div><div class="bc-shots" ondragover="bcDragOver(event)" ondrop="bcDrop(event,0)">';
  shots.forEach(function(s) {
    h += '<img class="bc-shot" src="' + s.url + '" draggable="true" ondragstart="bcDragStart(event,' + jsq(s.file) + ')" title="' + esc(s.file) + '">';
  });
  h += '</div></div>';
  return h;
}

function renderBigConvTierPools(pools) {
  var h = '<div class="bc-tier-pools">';
  ["T1", "T2", "T3"].forEach(function(tier) {
    var shots = (pools && pools[tier]) || [];
    h += '<div class="bc-pool"><div class="bc-pool-label">' + tier + '</div><div class="bc-shots">';
    shots.forEach(function(s) {
      h += '<img class="bc-shot" src="' + s.url + '" draggable="true" ondragstart="bcDragStart(event,' + jsq(s.file) + ')" title="' + esc(s.file) + '">';
    });
    h += '</div></div>';
  });
  h += '</div>';
  return h;
}
```
Note: dropping a screenshot onto the viral pool's row calls `bcDrop(event, 0)` — paragraph index `0` is a reserved "unassigned / viral pool" bucket, not a real paragraph (paragraphs are 1-based). This lets Victor drag a paragraph's screenshot back out to the safety-net pool without it belonging to any paragraph.

- [ ] **Step 2: Add the supporting load/action/drag functions.** Immediately after the functions from Step 1:
```javascript
function refreshBigConvTopic() {
  if (S.bigConvSelectedTopic) loadBigConvTopicDetail(S.bigConvSelectedTopic);
}

function prepareBigConvTopic(topic) {
  api("/api/big-conversation/topic/" + encodeURIComponent(topic) + "/prepare", { method: "POST" })
    .then(function(d) {
      S.bigConvPrepare = d;
      render();
    })
    .catch(function(e) { showToast("Error: " + e.message, "error"); });
}

function toggleBigConvTierPool() {
  S.bigConvShowTierPool = !S.bigConvShowTierPool;
  render();
}

var _bcDragFile = null;
function bcDragStart(e, filename) {
  _bcDragFile = filename;
  e.dataTransfer.effectAllowed = "move";
}
function bcDragOver(e) { e.preventDefault(); }
function bcDrop(e, paragraphIndex) {
  e.preventDefault();
  if (!_bcDragFile || !S.bigConvSelectedTopic) return;
  var filename = _bcDragFile;
  _bcDragFile = null;
  api("/api/big-conversation/topic/" + encodeURIComponent(S.bigConvSelectedTopic) + "/pairing", {
    method: "POST",
    body: { filename: filename, paragraph_index: paragraphIndex },
  }).then(function() {
    loadBigConvTopicDetail(S.bigConvSelectedTopic);
  }).catch(function(e) { showToast("Error: " + e.message, "error"); });
}
```

- [ ] **Step 3: Add the detail-page CSS.** In the `<style>` block, just before `</style>`, add (alongside Task 10's `.bc-*` rules):
```css
.bc-detail-head{display:flex;align-items:center;gap:14px;margin-bottom:14px}
.bc-detail-title{font-weight:700;font-size:15px}
.bc-headline{font-weight:700;font-size:16px;margin-bottom:14px}
.bc-paragraph{border-top:.5px solid var(--sep);padding:14px 0}
.bc-p-text{font-size:14px;line-height:1.5;margin-bottom:10px}
.bc-shots{display:flex;gap:8px;flex-wrap:wrap;min-height:64px}
.bc-shot{width:72px;height:72px;object-fit:cover;border-radius:8px;cursor:grab;border:1px solid var(--sep)}
.bc-pool{margin-top:16px}
.bc-pool-label{font-size:11px;font-weight:700;color:var(--label3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
.bc-tier-toggle{margin-top:12px}
.bc-instruction{background:var(--accent-soft);border-radius:8px;padding:10px;font-size:12px;margin-top:10px;font-family:monospace}
```

- [ ] **Step 4: Verify (presence + manual, using the real Instagram data if present).**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/
curl -s http://127.0.0.1:8500/ | grep -c 'function bcDrop'
curl -s http://127.0.0.1:8500/ | grep -c 'function renderBigConvViralPool'
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8500/api/big-conversation/topic/Kids%20in%20the%20Office"
kill %1
```
Expected: `200`, `1`, `1`, `200`.

Manual click script (use the real `Kids in the Office` topic if this machine has the Instagram project checked out — it is already processed and gives a genuine end-to-end check):
1. Open `/`, go to Big Conversation, click "Open" on `Kids in the Office`.
2. The detail page shows the headline "Nobody decided kids should be in the office." and four paragraphs, each with its own row of screenshot thumbnails below it (e.g. paragraph 1 shows `p1_1_Katie_Moloney.png` and its two alternates).
3. Below the paragraphs, a "Viral extreme" pool row is always visible.
4. "Show tier pool" is present and, until clicked, T1/T2/T3 are NOT visible; clicking it reveals them; clicking again hides them.
5. Drag a screenshot thumbnail from one paragraph's row and drop it onto a different paragraph's row — it moves there and stays moved after a page refresh (persisted via the pairing endpoint).
6. Click "Mark ready" — the sidebar's Big Conversation status dot flips to ready (increment 1's `toggleReady`).
7. Click "Back to bank" — returns to the topic list. Open a topic with no piece yet (e.g. `Career Pivoting`) — shows "No piece drafted yet" + a "Process" button; clicking it shows the copy-paste instruction to run the skill in a Claude session, plus a "Refresh" button.

- [ ] **Step 5: Python suite unchanged + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -3
git add flatwhite/dashboard/static/index.html
git commit -m "Big Conversation UI: paragraph/screenshot detail page, tier toggle, drag-drop, process/refresh"
```
Expected: unchanged from Task 10 (163 passed / 8 pre-existing).

---

## Manual verification (whole increment, before done)

1. `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`, open `http://127.0.0.1:8500/`.
2. Big Conversation's topic bank lists the real sorted Instagram folders (if the Instagram project is present at `~/Documents/MISC/instagram-dm-screenshotter/output/`), excluding junk/utility folders and anything prefixed `DONE - ` / `INCOMPLETE - `.
3. Archiving a topic hides it from the bank; it is not deleted anywhere, and the Instagram output folder is untouched (`ls -la` the folder before/after to confirm nothing changed there).
4. Opening `Kids in the Office` (or `Conference Room Sharing` / `PIP Term Length` — all three are already processed in the real data) shows the drafted piece split into paragraphs, each with its paired screenshots displayed as real images (not broken image icons — confirms the asset route works).
5. Only the viral-extreme pool shows by default; T1/T2/T3 require the toggle.
6. Dragging a screenshot to a different paragraph persists across a refresh.
7. Opening an unprocessed topic (e.g. `Career Pivoting`) shows "No piece drafted yet" and, after clicking Process, a copy-pasteable instruction naming the topic and the Instagram output path — never a claim that FW itself generated anything.
8. Confirm path-traversal safety directly:
```bash
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8500/api/big-conversation/assets/..%2F..%2F..%2Fetc%2Fpasswd"
```
Expected: `404`.
9. Confirm soft-fail when the Instagram folder is absent:
```bash
FW_INSTAGRAM_OUTPUT_DIR=/tmp/does-not-exist-$$ .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8501 &
sleep 2
curl -s http://127.0.0.1:8501/api/big-conversation/topics
kill %1
```
Expected: `{"topics": [], "root_exists": false}`, no 500.
10. `.venv/bin/python -m pytest -q` — full suite at 163 passed / 8 pre-existing failures (same 8 as the recorded baseline; +39 new tests total across Tasks 1-9: 3 + 24 + 12).

Report the FW suite counts and "built locally on branch `fw-control-room-bigconv`, NOT merged, NOT deployed (FW deploy is Victor's)."

## Notes for later increments (not this plan)

- The piece's paragraph text is read-only in this increment (no textarea edit). If Victor wants to tweak wording before assembly, that's an editable-output pass for a later increment, alongside the "Assemble to beehiiv" work (build order item 7).
- The Inside Track (gossip/redundancy folder selection) is its own increment (build order item 5) and reads the `Redundancies & Breaking News` folder this plan explicitly excludes from the Big Conversation bank.
- If increment 3's rebuilt sort skill renames the tier folders differently than either the current names or the `VIRAL EXTREME`/`T1`/`T2`/`T3` guess this plan hard-codes, update only `classify_tier_folder`'s two regex tables in `flatwhite/dashboard/big_conversation_bank.py` — everything else in the pipeline is agnostic to the exact folder name.
