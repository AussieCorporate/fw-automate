# FW Control Room Increment 7 (FINAL) — Assembly + Content Bank, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the last piece of the control room: "Assemble to beehiiv" takes every segment marked ready in the current running order and turns it into beehiiv-ready HTML blocks, in order, with the template furniture (sponsor when present, Odd Picks, Feedback Loop) folded in; a Content Bank stores pieces produced ahead of time (Big Conversation, Brains Trust) and lets Victor pull one into the current edition; every assembled segment gets a benchmark chip against the real published corpus. This increment depends on Increments 1-6 existing (the shell, the five in-dash pages, the screenshot sort skill, Big Conversation, Inside Track, Brains Trust) — each of those is expected to persist its "mark ready" output the same way the pre-existing Editorial/Pulse/Big Conversation/Off the Clock pages already do today (`POST /api/section-output/{section}`, backed by the `section_outputs` SQLite table, keyed by `week_iso` + a canonical section id). This plan builds strictly on top of that contract; it does not change how any prior segment generates or saves its own output.

**Why this shape:** Two things were settled before this plan was written and constrain the whole design:

1. **Design B, not raw-API content-write.** beehiiv's v2 API `POST`/`PATCH /publications/{pub}/posts/{id}` content-write is Enterprise-gated (`403 SEND_API_NOT_ENTERPRISE_PLAN`) on FW's plan. So this increment does NOT call the beehiiv REST API to push content. Instead: FW's backend **formats** the assembled edition into HTML block fragments matching beehiiv's editor contract (confirmed via the beehiiv MCP's `learn_post_authoring` — `edit_post_content` accepts HTML fragments per block, matched against a live draft's block hashes read via `get_post_content(format="editor_html")`); a human (or the agent, on Victor's instruction, in a normal Claude session with the beehiiv MCP connected) does the actual insert by feeding the assembled HTML into `edit_post_content` against the target draft post. The dashboard's job stops at producing correct, ordered, copyable HTML — it does not hold beehiiv credentials or make beehiiv network calls itself, and neither do this increment's tests.
2. **`section_outputs` is the existing "ready" store; Content Bank is new.** `section_outputs` is a one-row-per-`(week_iso, section)` table — perfect for "this week's live draft of segment X" but wrong for a bank of many pieces produced ahead of time and not yet tied to a week. Reusing the existing `drafts` table was considered and rejected: it has a `CHECK (section IN ('big_conversation','hook','custom'))` constraint and a mandatory `week_iso`, both wrong for a cross-week, cross-type bank (and SQLite can't cheaply loosen a `CHECK` constraint — it requires a full table rebuild). This plan adds one new table, `content_bank`, decoupled from week, so it can hold Big Conversation pieces, Brains Trust drafts, and — per the spec's own note — later, TAC Instagram pieces, without redesign.

**Architecture:**
- **Backend, three new modules + one new table:**
  - `flatwhite/db.py` — add `content_bank` table + `save_bank_item` / `list_bank_items` / `archive_bank_item` / `get_bank_item` functions (same style as the existing `section_outputs` functions).
  - `flatwhite/assemble/benchmark.py` (new) — loads `data/beehiiv_fw_ground_truth.json` once, builds a per-FW-segment word-count profile (avg/min/max) by matching real segment header names, exposes `benchmark_segment(section_id, text) -> dict`.
  - `flatwhite/assemble/beehiiv_format.py` (new) — a small regex-based converter from FW's saved markdown-ish `output_text` (`**bold**`, `_italic_`, `[text](url)`, blank-line paragraphs) into beehiiv-editor-contract HTML fragments. No new dependency (FW has no `markdown` package installed and the existing `assemble/renderer.py` already does hand-rolled string templating rather than pull one in — this follows the same house style).
  - `flatwhite/dashboard/api.py` — add the assemble endpoint (`POST /api/assemble-edition`) and the content-bank CRUD endpoints.
- **Frontend, one new page + one page upgraded:** the `bank` placeholder page from Increment 1 becomes the real Content Bank page; a new `assemble` page is wired to the sidebar's "Assemble to beehiiv" action (a third `nav-lite` row under the existing Content Bank/Sources pair, per the spec's "Bottom: an Assemble to beehiiv action").

**Tech Stack:** FastAPI (`flatwhite/dashboard/api.py`), SQLite via `flatwhite/db.py`, single static HTML/CSS/JS (`flatwhite/dashboard/static/index.html`, no build step), `pytest` via FW's own venv.

## Global Constraints

- **Runs on FW's venv only:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python 3.9 breaks FW. Never use another interpreter for FW.
- **Branch:** from `main`, `git checkout main && git checkout -b fw-control-room-assembly`. FW deploy is Victor's (GCP VM `flatwhite`); this is built + tested locally only, not merged/pushed/deployed.
- **FW test baseline:** run `.venv/bin/python -m pytest -q` first and record the exact pass/fail counts. As of writing this plan: **124 passed, 8 failed** (the 8 are pre-existing, unrelated to this work — `test_normalise.py` x3 and `test_pipeline.py` x2 in the sample run, plus others already failing before this branch; do not try to fix them here). After every task the non-pre-existing failure count must stay at zero — every new test this plan adds must pass, and the 124 must stay 124 (or grow, never shrink for reasons unrelated to a task's own change).
- **No em dashes** (U+2014) in any reader-facing string or generated copy. Australian spelling. Write "percent" as `%`, never spell out "per cent"/"percent" in generated or template copy.
- **Design B is final for this increment:** no code in this plan calls beehiiv's v2 content-write endpoints (`POST`/`PATCH .../posts`). The assemble endpoint's job ends at producing HTML block fragments + an `assembled_html` string. Tests assert on the block **structure** the formatter produces (segment order, HTML tag shape, furniture placement, benchmark fields) — never a live beehiiv/network call. If any test in this plan imports `httpx`/`requests` against a beehiiv host or the beehiiv MCP, that test is wrong; stop and re-read this constraint.
- **Benchmark against the real corpus:** `benchmark_segment()` must read `data/beehiiv_fw_ground_truth.json` (or a monkeypatched path pointing at a small fixture with the same shape, for fast/deterministic unit tests) — never hardcoded word-count numbers copied out of `beehiiv_fw_ground_truth_ANALYSIS.md`. The analysis doc is human-written commentary and can drift from the underlying data; the corpus file is the source of truth.
- **Additive/surgical to `index.html`:** do not change any existing `renderX(el)` section function's internals, any existing `/api/*` call, or the Increment 1-6 sidebar/running-order mechanics. This increment only adds the `assemble` and `bank` pages and their supporting JS/CSS.
- **No JS build/test harness exists:** verify frontend work via `curl` presence checks against the running dashboard + a manual click script, plus the Python suite staying at baseline (same approach as Increment 1).
- **Local run:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`. Kill it when done with each verification.
- **This is the LAST increment.** Task 8 below is a whole-control-room smoke test, not just this increment's own feature — confirm the shell, the segment pages, and assembly all work together before declaring the rebuild done.

## Assumptions this plan makes about Increments 1-6 (verify before starting; adjust task steps if these have drifted)

1. The sidebar (Increment 1) holds a `SEGMENTS` JS array of `{id, name, status}` in this order by default: `editorial, brains, top_picks, insidetrack, pulse, off_the_clock, thread, big_conversation` — draggable, `status` one of `ready|notready|manual`.
2. Every segment page's "Mark ready" action, by the time its own increment lands, calls `POST /api/section-output/{id}` with the same `id` value used in `SEGMENTS` (this is already true today for `editorial`, `pulse`, `big_conversation`, `off_the_clock` — Increments 2-6 are expected to wire `top_picks`, `insidetrack`, `thread`, `brains` the same way; this is the established house pattern in `flatwhite/dashboard/state.py`/`api.py`, not a new invention of this plan).
3. `GET /api/section-outputs` returns `{"outputs": {<section_id>: {"output_text":..., "model_used":..., "saved_at":...}}, "week_iso": ...}` for the current week — already true today, used unchanged.
4. Readiness (the sidebar dot) and running order are **frontend state** (`SEGMENTS`), not yet persisted server-side as of Increment 1 — this plan does not change that. The assemble endpoint takes the current in-memory order + ready flags as part of its request body; it is only ever invoked while the dashboard is open, so this is sufficient and keeps this increment's surface small.

If any of these have changed by execution time (e.g. a later increment renamed a segment id, or persisted order server-side), adjust Task 5-7 to match the real interface rather than the assumption — do not silently keep both in sync by duplicating logic.

## File Structure

```
flatwhite/
  db.py                              # MODIFIED: + content_bank table, + 4 functions
  assemble/
    __init__.py
    renderer.py                      # unchanged (legacy per-week SQLite assembler, not touched)
    templates.py                     # unchanged
    benchmark.py                     # NEW: ground-truth word-count profiles + benchmark_segment()
    beehiiv_format.py                # NEW: markdown-ish text -> beehiiv editor HTML fragment
  dashboard/
    api.py                           # MODIFIED: + assemble + content-bank endpoints
    static/
      index.html                    # MODIFIED: + Assemble page, + real Content Bank page
tests/
  test_content_bank.py               # NEW
  test_benchmark.py                  # NEW
  test_beehiiv_format.py             # NEW
  test_assemble_edition.py           # NEW
```

---

### Task 1: `content_bank` table + storage functions

**Files:** `flatwhite/db.py`, `tests/test_content_bank.py` (new).

**Interfaces produced:** `save_bank_item(segment_type, title, body_text, source_note=None) -> int`, `list_bank_items(segment_type=None, status="active") -> list[dict]`, `archive_bank_item(bank_id) -> None`, `get_bank_item(bank_id) -> dict | None`. Consumed by Task 2's API endpoints.

- [ ] **Step 1: Write the failing tests first.** Create `tests/test_content_bank.py`:
```python
"""Tests for the content_bank table — pieces produced ahead of time (Big
Conversation, Brains Trust) that get pulled into a future edition. Decoupled
from week_iso, unlike section_outputs (see plan rationale: reusing `drafts`
would need a CHECK-constraint rebuild for no real benefit)."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def bank_db(tmp_path: Path):
    db_path = tmp_path / "bank_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def test_content_bank_table_exists(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        conn = db_module.get_connection()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "content_bank" in tables


def test_save_and_list_bank_item(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        bank_id = db_module.save_bank_item(
            segment_type="big_conversation",
            title="Return-to-office backlash",
            body_text="**A quiet mutiny.**\n\nMore teams are...",
            source_note="Instagram folder: rto-backlash-2026w29",
        )
        assert isinstance(bank_id, int)
        items = db_module.list_bank_items(segment_type="big_conversation")
        assert len(items) == 1
        assert items[0]["title"] == "Return-to-office backlash"
        assert items[0]["status"] == "active"


def test_list_filters_by_segment_type(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        db_module.save_bank_item("big_conversation", "Piece A", "text a")
        db_module.save_bank_item("brains_trust", "Piece B", "text b")
        bc = db_module.list_bank_items(segment_type="big_conversation")
        bt = db_module.list_bank_items(segment_type="brains_trust")
        assert [i["title"] for i in bc] == ["Piece A"]
        assert [i["title"] for i in bt] == ["Piece B"]


def test_list_all_segment_types_when_omitted(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        db_module.save_bank_item("big_conversation", "Piece A", "text a")
        db_module.save_bank_item("brains_trust", "Piece B", "text b")
        all_items = db_module.list_bank_items()
        assert len(all_items) == 2


def test_archive_hides_item_from_active_list(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        bank_id = db_module.save_bank_item("big_conversation", "Piece A", "text a")
        db_module.archive_bank_item(bank_id)
        active = db_module.list_bank_items(segment_type="big_conversation", status="active")
        archived = db_module.list_bank_items(segment_type="big_conversation", status="archived")
        assert active == []
        assert len(archived) == 1
        assert archived[0]["id"] == bank_id


def test_get_bank_item_returns_none_for_unknown_id(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        assert db_module.get_bank_item(99999) is None


def test_get_bank_item_returns_full_row(bank_db):
    with patch.object(db_module, "DB_PATH", bank_db):
        bank_id = db_module.save_bank_item("brains_trust", "EV uptake", "body text", "digest w28+w29")
        item = db_module.get_bank_item(bank_id)
        assert item["title"] == "EV uptake"
        assert item["body_text"] == "body text"
        assert item["source_note"] == "digest w28+w29"
```
Run: `.venv/bin/python -m pytest tests/test_content_bank.py -q` — confirm all fail (no `content_bank` table/functions yet).

- [ ] **Step 2: Add the table.** In `flatwhite/db.py`, find the `CREATE TABLE IF NOT EXISTS drafts (...)` block (around line 189, inside the schema string built at module scope) and add immediately after its closing `);`:
```sql
CREATE TABLE IF NOT EXISTS content_bank (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body_text TEXT NOT NULL,
    source_note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```
`segment_type` is deliberately NOT `CHECK`-constrained (unlike `drafts.section`) — the spec explicitly wants this table shared conceptually with a future TAC Instagram tab, so new segment types must be addable without a migration.

- [ ] **Step 3: Add the functions.** In `flatwhite/db.py`, immediately after `load_all_section_outputs()` (around line 445-460), add:
```python
def save_bank_item(
    segment_type: str,
    title: str,
    body_text: str,
    source_note: str | None = None,
) -> int:
    """Add a piece to the content bank (produced ahead of time, not yet used).

    Unlike save_section_output, this is NOT keyed by week_iso — bank items are
    produced ahead of a specific week and pulled in later via pull semantics
    in api.py (which copies body_text into that week's section_outputs row).
    """
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO content_bank (segment_type, title, body_text, source_note, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        (segment_type, title, body_text, source_note),
    )
    conn.commit()
    bank_id = cursor.lastrowid
    conn.close()
    return bank_id


def list_bank_items(segment_type: str | None = None, status: str = "active") -> list[dict]:
    """Return content_bank rows, newest first. Filters by segment_type if given.

    status: 'active' (default) or 'archived'. Pass status=None for both.
    """
    conn = get_connection()
    query = "SELECT * FROM content_bank WHERE 1=1"
    params: list = []
    if segment_type is not None:
        query += " AND segment_type = ?"
        params.append(segment_type)
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def archive_bank_item(bank_id: int) -> None:
    """Mark a bank item archived (done/published) without deleting it."""
    conn = get_connection()
    conn.execute(
        "UPDATE content_bank SET status = 'archived', updated_at = datetime('now') WHERE id = ?",
        (bank_id,),
    )
    conn.commit()
    conn.close()


def get_bank_item(bank_id: int) -> dict | None:
    """Return a single content_bank row by id, or None if it doesn't exist."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM content_bank WHERE id = ?", (bank_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
```

- [ ] **Step 4: Run + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest tests/test_content_bank.py -q     # all pass
.venv/bin/python -m pytest -q 2>&1 | tail -3                 # 124+7 passed, 8 pre-existing failed, nothing new broken
git add flatwhite/db.py tests/test_content_bank.py
git commit -m "FW assembly: content_bank table (pieces produced ahead of time, decoupled from week)"
```

---

### Task 2: Content-bank API endpoints (add / list / archive / pull-into-edition)

**Files:** `flatwhite/dashboard/api.py`, `tests/test_content_bank.py` (extend with API-level tests using FastAPI's `TestClient`).

**Interfaces produced:** `POST /api/content-bank`, `GET /api/content-bank`, `POST /api/content-bank/{id}/archive`, `POST /api/content-bank/{id}/pull`. The pull endpoint is the bridge back into the existing "ready" mechanism: it writes the bank item's `body_text` into `section_outputs` for the CURRENT week under the caller-chosen `target_section`, using the exact same `save_section_output()` function every other segment already uses — so after a pull, the target segment's page shows the pulled text in its output box exactly like any freshly-generated output, and Victor marks it ready the normal way.

- [ ] **Step 1: Extend `tests/test_content_bank.py`** with endpoint-level tests, monkeypatching `DB_PATH` (no real DB writes) and NOT touching any network:
```python
# --- append to tests/test_content_bank.py ---
from fastapi.testclient import TestClient


@pytest.fixture
def bank_client(tmp_path: Path):
    db_path = tmp_path / "bank_api_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        import flatwhite.dashboard.api as api_module
        yield TestClient(api_module.app)


def test_post_content_bank_creates_item(bank_client):
    resp = bank_client.post("/api/content-bank", json={
        "segment_type": "big_conversation",
        "title": "Return-to-office backlash",
        "body_text": "**A quiet mutiny.**",
        "source_note": "rto-backlash-2026w29",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] > 0


def test_get_content_bank_lists_active_items(bank_client):
    bank_client.post("/api/content-bank", json={
        "segment_type": "brains_trust", "title": "EV uptake", "body_text": "text",
    })
    resp = bank_client.get("/api/content-bank")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "EV uptake"


def test_get_content_bank_filters_by_segment_type(bank_client):
    bank_client.post("/api/content-bank", json={"segment_type": "big_conversation", "title": "A", "body_text": "a"})
    bank_client.post("/api/content-bank", json={"segment_type": "brains_trust", "title": "B", "body_text": "b"})
    resp = bank_client.get("/api/content-bank", params={"segment_type": "brains_trust"})
    items = resp.json()["items"]
    assert [i["title"] for i in items] == ["B"]


def test_post_content_bank_requires_fields(bank_client):
    resp = bank_client.post("/api/content-bank", json={"segment_type": "big_conversation"})
    assert resp.status_code == 400


def test_archive_endpoint(bank_client):
    created = bank_client.post("/api/content-bank", json={
        "segment_type": "big_conversation", "title": "A", "body_text": "a",
    }).json()
    resp = bank_client.post(f"/api/content-bank/{created['id']}/archive")
    assert resp.status_code == 200
    active = bank_client.get("/api/content-bank").json()["items"]
    assert active == []


def test_pull_writes_into_section_outputs_for_current_week(bank_client):
    import flatwhite.db as db_module
    created = bank_client.post("/api/content-bank", json={
        "segment_type": "big_conversation", "title": "A", "body_text": "**pulled text**",
    }).json()
    resp = bank_client.post(f"/api/content-bank/{created['id']}/pull", json={"target_section": "big_conversation"})
    assert resp.status_code == 200
    week_iso = db_module.get_current_week_iso()
    outputs = db_module.load_all_section_outputs(week_iso)
    assert outputs["big_conversation"]["output_text"] == "**pulled text**"
    assert outputs["big_conversation"]["model_used"] == "content_bank"


def test_pull_unknown_id_404s(bank_client):
    resp = bank_client.post("/api/content-bank/99999/pull", json={"target_section": "big_conversation"})
    assert resp.status_code == 404
```
Run: `.venv/bin/python -m pytest tests/test_content_bank.py -q` — the new endpoint tests fail (routes don't exist yet).

- [ ] **Step 2: Add the endpoints.** In `flatwhite/dashboard/api.py`, immediately after the existing `# ── Section outputs ──` block's `api_save_section_output` function (around line 1438), add:
```python
# ── Content bank ─────────────────────────────────────────────────────────────
# Pieces produced ahead of time (Big Conversation, Brains Trust), decoupled from
# any specific week. Pulling an item writes it into THIS week's section_outputs
# for a chosen target section, via the same save_section_output() every segment
# page already uses — so it shows up in that page's output box unchanged.

@app.post("/api/content-bank")
async def api_add_bank_item(request: Request) -> JSONResponse:
    """Add a piece to the content bank.

    Body: {"segment_type": str, "title": str, "body_text": str, "source_note": str?}
    """
    from flatwhite.db import save_bank_item

    body = await request.json()
    segment_type = (body.get("segment_type") or "").strip()
    title = (body.get("title") or "").strip()
    body_text = (body.get("body_text") or "").strip()
    if not segment_type or not title or not body_text:
        return JSONResponse(
            {"error": "segment_type, title, and body_text are required"}, status_code=400
        )
    bank_id = save_bank_item(
        segment_type=segment_type,
        title=title,
        body_text=body_text,
        source_note=body.get("source_note"),
    )
    return JSONResponse({"id": bank_id})


@app.get("/api/content-bank")
def api_list_bank_items(segment_type: str | None = None, status: str = "active") -> JSONResponse:
    """List content bank items. Optional ?segment_type=... filter. status defaults to 'active'."""
    from flatwhite.db import list_bank_items

    items = list_bank_items(segment_type=segment_type, status=status)
    return JSONResponse({"items": items})


@app.post("/api/content-bank/{bank_id}/archive")
def api_archive_bank_item(bank_id: int) -> JSONResponse:
    """Archive a bank item (mark done/published) without deleting it."""
    from flatwhite.db import archive_bank_item, get_bank_item

    if get_bank_item(bank_id) is None:
        return JSONResponse({"error": "Bank item not found"}, status_code=404)
    archive_bank_item(bank_id)
    return JSONResponse({"archived": True, "id": bank_id})


@app.post("/api/content-bank/{bank_id}/pull")
async def api_pull_bank_item(bank_id: int, request: Request) -> JSONResponse:
    """Pull a bank item into the current week's running order.

    Body: {"target_section": str}  — one of the running-order segment ids
    (e.g. "big_conversation", "brains"). Writes body_text into section_outputs
    for THIS week under target_section, exactly as if that segment had just
    generated it, so the segment's own page (and its Mark Ready flow) sees it.
    """
    from flatwhite.db import get_bank_item, save_section_output

    item = get_bank_item(bank_id)
    if item is None:
        return JSONResponse({"error": "Bank item not found"}, status_code=404)

    body = await request.json()
    target_section = (body.get("target_section") or "").strip()
    if not target_section:
        return JSONResponse({"error": "target_section is required"}, status_code=400)

    week_iso = get_current_week_iso()
    save_section_output(week_iso, target_section, item["body_text"], "content_bank")
    return JSONResponse({"pulled": True, "target_section": target_section, "week_iso": week_iso})
```

- [ ] **Step 3: Run + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest tests/test_content_bank.py -q     # all pass
.venv/bin/python -m pytest -q 2>&1 | tail -3                 # baseline preserved
git add flatwhite/dashboard/api.py tests/test_content_bank.py
git commit -m "FW assembly: content-bank API (add/list/archive/pull-into-edition)"
```

---

### Task 3: Benchmark helper (segment length/register vs the real corpus)

**Files:** `flatwhite/assemble/benchmark.py` (new), `tests/test_benchmark.py` (new).

**Interfaces produced:** `benchmark_segment(section_id: str, text: str) -> dict` returning `{"word_count": int, "target_avg": float, "target_min": int, "target_max": int, "status": "short"|"within"|"long", "n_editions": int}` (or `status: "no_data"` if the section id has no mapping in the corpus — e.g. a segment the corpus doesn't independently track). Consumed by Task 5's assemble endpoint (one benchmark object per assembled block) and reusable by earlier increments' own per-segment benchmark chips (already stubbed per the spec) if they want to switch to this shared implementation instead of duplicating the mapping.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_benchmark.py`:
```python
"""Tests for flatwhite/assemble/benchmark.py — checks a segment's word count
against the real published corpus (data/beehiiv_fw_ground_truth.json), never
against hardcoded numbers (the corpus can be re-fetched/extended later)."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from flatwhite.assemble import benchmark


# A tiny fixture with the same shape as the real corpus (list of editions,
# each with "segments": [{"name":..., "text":..., "word_count":...}]).
# Kept deliberately small/fast — the real-corpus check is a separate test.
_FIXTURE = [
    {
        "post_id": "post_fixture1", "date": "2026-01-05", "title": "t1",
        "segments": [
            {"name": "INTRO", "text": "word " * 150, "word_count": 150},
            {"name": "THE BIG CONVERSATION", "text": "word " * 400, "word_count": 400},
            {"name": "OFF THE CLOCK", "text": "word " * 200, "word_count": 200},
        ],
    },
    {
        "post_id": "post_fixture2", "date": "2026-01-12", "title": "t2",
        "segments": [
            {"name": "INTRO", "text": "word " * 170, "word_count": 170},
            {"name": "THE BIG CONVERSATION", "text": "word " * 440, "word_count": 440},
            {"name": "OFF THE CLOCK", "text": "word " * 220, "word_count": 220},
        ],
    },
]


@pytest.fixture
def fixture_corpus(tmp_path: Path):
    p = tmp_path / "fixture_ground_truth.json"
    p.write_text(json.dumps(_FIXTURE))
    with patch.object(benchmark, "GROUND_TRUTH_PATH", p):
        benchmark._load_profiles.cache_clear()
        yield p
    benchmark._load_profiles.cache_clear()


def test_editorial_within_range(fixture_corpus):
    result = benchmark.benchmark_segment("editorial", "word " * 160)
    assert result["status"] == "within"
    assert result["target_min"] == 150
    assert result["target_max"] == 170
    assert result["n_editions"] == 2


def test_editorial_too_short(fixture_corpus):
    result = benchmark.benchmark_segment("editorial", "word " * 50)
    assert result["status"] == "short"


def test_big_conversation_too_long(fixture_corpus):
    result = benchmark.benchmark_segment("big_conversation", "word " * 900)
    assert result["status"] == "long"


def test_unmapped_section_returns_no_data(fixture_corpus):
    result = benchmark.benchmark_segment("insidetrack_typo_id", "anything")
    assert result["status"] == "no_data"


def test_word_count_is_computed_not_assumed(fixture_corpus):
    result = benchmark.benchmark_segment("off_the_clock", "just three words")
    assert result["word_count"] == 3


def test_real_corpus_loads_and_maps_known_segments():
    """Integration check against the ACTUAL shipped corpus — no network, just
    confirms the segment-name matchers still line up with real header text."""
    benchmark._load_profiles.cache_clear()
    for section_id in ("editorial", "big_conversation", "top_picks", "insidetrack",
                        "thread", "pulse", "off_the_clock", "brains"):
        result = benchmark.benchmark_segment(section_id, "word " * 100)
        assert result["status"] != "no_data", f"{section_id} did not match any real segment name"
        assert result["n_editions"] >= 1
    benchmark._load_profiles.cache_clear()
```
Run: `.venv/bin/python -m pytest tests/test_benchmark.py -q` — fails (module doesn't exist).

- [ ] **Step 2: Write `flatwhite/assemble/benchmark.py`:**
```python
"""Benchmark an assembled segment's length against the real published corpus.

Reads data/beehiiv_fw_ground_truth.json (10 real Flat White editions,
segment-parsed) and, for a given FW dashboard section id, finds every real
segment across those editions whose header NAME matches, computes an average
+ min/max word count, and reports whether a candidate text's word count falls
short of / within / longer than that observed range.

Numbers are NEVER hardcoded here — always computed from the corpus file, so
re-fetching more editions automatically updates the benchmark. See
data/beehiiv_fw_ground_truth_ANALYSIS.md for the human-written commentary this
module deliberately does NOT copy numbers from (that doc can drift; the JSON
is the source of truth).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

GROUND_TRUTH_PATH = Path(__file__).parent.parent.parent / "data" / "beehiiv_fw_ground_truth.json"

# FW dashboard section id -> substrings that identify it in the real corpus's
# segment "name" field (case-insensitive "in" match). Ordered matchers checked
# in the order given; a name matching more than one FW section id (e.g. "ODD
# PICKS" contains "PICK") is guarded by the exclude list.
_SEGMENT_MATCHERS: dict[str, dict[str, list[str]]] = {
    "editorial":        {"include": ["INTRO"], "exclude": []},
    "big_conversation": {"include": ["THE BIG CONVERSATION"], "exclude": []},
    "top_picks":        {"include": ["PICK & SCROLL", "TOP PICKS FROM LAST WEEK"], "exclude": ["ODD PICKS"]},
    "insidetrack":      {"include": ["THE INSIDE TRACK"], "exclude": []},
    "thread":           {"include": ["THREAD OF THE WEEK"], "exclude": []},
    "pulse":            {"include": ["AUSCORP STRESS INDEX"], "exclude": []},
    "off_the_clock":    {"include": ["OFF THE CLOCK"], "exclude": []},
    # THE BRAINS TRUST and its older name THE ECONOMIC SCOOP are the same slot
    # (see ANALYSIS.md "structural drift" note) — both count toward "brains".
    "brains":           {"include": ["THE BRAINS TRUST", "THE ECONOMIC SCOOP"], "exclude": []},
}


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _matches(name: str, matcher: dict[str, list[str]]) -> bool:
    upper = name.upper()
    if any(ex in upper for ex in matcher["exclude"]):
        return False
    return any(inc in upper for inc in matcher["include"])


@lru_cache(maxsize=1)
def _load_profiles() -> dict[str, dict[str, Any]]:
    """Build {section_id: {avg, min, max, n}} from the ground truth corpus.

    lru_cache means a monkeypatch of GROUND_TRUTH_PATH in tests must call
    _load_profiles.cache_clear() first (see tests/test_benchmark.py fixture).
    """
    if not GROUND_TRUTH_PATH.exists():
        return {}
    editions = json.loads(GROUND_TRUTH_PATH.read_text())

    counts: dict[str, list[int]] = {sid: [] for sid in _SEGMENT_MATCHERS}
    for edition in editions:
        for seg in edition.get("segments", []):
            name = seg.get("name", "")
            wc = seg.get("word_count")
            if wc is None:
                wc = _word_count(seg.get("text", ""))
            for section_id, matcher in _SEGMENT_MATCHERS.items():
                if _matches(name, matcher):
                    counts[section_id].append(wc)

    profiles: dict[str, dict[str, Any]] = {}
    for section_id, values in counts.items():
        if not values:
            continue
        profiles[section_id] = {
            "avg": round(sum(values) / len(values), 1),
            "min": min(values),
            "max": max(values),
            "n": len(values),
        }
    return profiles


def benchmark_segment(section_id: str, text: str) -> dict[str, Any]:
    """Compare a candidate segment's word count to the real corpus.

    Returns dict with word_count, target_avg, target_min, target_max, status
    ("short"|"within"|"long"|"no_data"), n_editions.
    """
    profiles = _load_profiles()
    word_count = _word_count(text)

    profile = profiles.get(section_id)
    if profile is None:
        return {
            "word_count": word_count,
            "target_avg": None,
            "target_min": None,
            "target_max": None,
            "status": "no_data",
            "n_editions": 0,
        }

    if word_count < profile["min"]:
        status = "short"
    elif word_count > profile["max"]:
        status = "long"
    else:
        status = "within"

    return {
        "word_count": word_count,
        "target_avg": profile["avg"],
        "target_min": profile["min"],
        "target_max": profile["max"],
        "status": status,
        "n_editions": profile["n"],
    }
```

- [ ] **Step 3: Run + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest tests/test_benchmark.py -q     # all pass
.venv/bin/python -m pytest -q 2>&1 | tail -3               # baseline preserved
git add flatwhite/assemble/benchmark.py tests/test_benchmark.py
git commit -m "FW assembly: benchmark helper against the real beehiiv corpus"
```

---

### Task 4: beehiiv-editor HTML formatter (Design B block formatting)

**Files:** `flatwhite/assemble/beehiiv_format.py` (new), `tests/test_beehiiv_format.py` (new).

**Interfaces produced:** `md_to_editor_html(text: str) -> str` (inline markdown -> HTML fragment: `**bold**`, `_italic_`/`*italic*`, `[text](url)` links, blank-line-separated paragraphs); `format_segment_block(label: str, text: str, heading_level: str = "h3") -> str` (wraps a labelled heading + the converted body — this is one "block" in the assembled edition). No beehiiv network call anywhere in this module — it only produces HTML strings matching the contract described by the beehiiv MCP's `learn_post_authoring` (plain heading/paragraph/strong/em/link HTML, the shape `edit_post_content` parses).

- [ ] **Step 1: Write the failing tests.** Create `tests/test_beehiiv_format.py`:
```python
"""Tests for flatwhite/assemble/beehiiv_format.py — converts FW's saved
markdown-ish segment text into beehiiv-editor HTML fragments. Structure only;
no beehiiv MCP or network call is made anywhere in this module or these tests
(Design B: FW formats, a human/agent inserts via the beehiiv MCP separately)."""
from flatwhite.assemble.beehiiv_format import md_to_editor_html, format_segment_block


def test_bold_converts_to_strong():
    assert md_to_editor_html("**A quiet mutiny.**") == "<p><strong>A quiet mutiny.</strong></p>"


def test_italic_underscore_converts_to_em():
    assert "<em>share this</em>" in md_to_editor_html("people say _share this_ constantly")


def test_italic_asterisk_converts_to_em():
    assert "<em>share this</em>" in md_to_editor_html("people say *share this* constantly")


def test_link_converts_to_anchor():
    html = md_to_editor_html("Read the thread [here](https://reddit.com/r/auscorp/x)")
    assert '<a href="https://reddit.com/r/auscorp/x">here</a>' in html


def test_blank_line_splits_paragraphs():
    html = md_to_editor_html("First paragraph.\n\nSecond paragraph.")
    assert html == "<p>First paragraph.</p><p>Second paragraph.</p>"


def test_single_newline_stays_within_one_paragraph():
    html = md_to_editor_html("Line one.\nLine two.")
    assert html.count("<p>") == 1


def test_empty_text_returns_empty_string():
    assert md_to_editor_html("") == ""
    assert md_to_editor_html("   ") == ""


def test_h4_hyperlinked_thread_title_format():
    """Thread of the Week's real published shape per ground truth:
    '#### [_**title**_](url)' — bold-italic hyperlinked H4 title."""
    html = md_to_editor_html("#### [_**Bunking with a colleague**_](https://reddit.com/x)")
    assert "<h4>" in html
    assert '<a href="https://reddit.com/x">' in html
    assert "<strong><em>Bunking with a colleague</em></strong>" in html or \
           "<em><strong>Bunking with a colleague</strong></em>" in html


def test_format_segment_block_wraps_heading_and_body():
    block = format_segment_block("THE BIG CONVERSATION", "**A quiet mutiny.**\n\nMore teams are pushing back.")
    assert block.startswith("<h3>THE BIG CONVERSATION</h3>")
    assert "<strong>A quiet mutiny.</strong>" in block
    assert "More teams are pushing back." in block


def test_format_segment_block_custom_heading_level():
    block = format_segment_block("Odd Picks", "One quirky link.", heading_level="h4")
    assert block.startswith("<h4>Odd Picks</h4>")
```
Run: `.venv/bin/python -m pytest tests/test_beehiiv_format.py -q` — fails (module doesn't exist).

- [ ] **Step 2: Write `flatwhite/assemble/beehiiv_format.py`:**
```python
"""Convert FW's saved segment text (the markdown-ish prose Victor edits in
each segment's output box) into HTML fragments matching beehiiv's post editor
contract, confirmed via the beehiiv MCP's learn_post_authoring: plain
paragraph/heading/strong/em/link HTML, no beehiiv-specific wrapper needed for
this bounded conversion. This is Design B's "format server-side" half — the
other half (actually inserting into a draft via edit_post_content) is a human
or agent step outside this codebase; see the assemble endpoint's docstring
and the increment plan's Global Constraints for why.

Intentionally minimal: handles exactly the markdown FW segments actually use
(bold, italic, links, paragraph breaks, one heading level for Thread of the
Week's '#### [_**title**_](url)' shape) — not a general markdown engine. FW
has no markdown package installed; this follows the existing house style in
flatwhite/assemble/renderer.py (hand-rolled string templating, no template
engine).
"""
from __future__ import annotations

import html
import re

_BOLD_ITALIC = re.compile(r"\*\*_(.+?)_\*\*|_\*\*(.+?)\*\*_")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|_(.+?)_")
_LINK = re.compile(r"\[(.+?)\]\((.+?)\)")
_HEADING4 = re.compile(r"^####\s+(.*)$")


def _inline(text: str) -> str:
    """Apply inline marks (bold, italic, bold-italic, links) to one line/paragraph.

    Order matters: bold-italic combos first (so **_x_** doesn't get double
    processed by the plain bold/italic passes), then links, then bold, then
    italic. Text is HTML-escaped first so raw '<'/'>'/'&' in source prose
    can't break the output; marks are then reintroduced as real tags.
    """
    escaped = html.escape(text, quote=False)

    def _bi_sub(m: re.Match) -> str:
        inner = m.group(1) or m.group(2)
        return f"<strong><em>{inner}</em></strong>"

    escaped = _BOLD_ITALIC.sub(_bi_sub, escaped)
    escaped = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', escaped)
    escaped = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    escaped = _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", escaped)
    return escaped


def md_to_editor_html(text: str) -> str:
    """Convert FW markdown-ish text into a beehiiv-editor HTML fragment.

    Blank lines separate paragraphs. A line starting '#### ' becomes an <h4>
    (Thread of the Week's real published title format). Everything else is
    wrapped in <p>. Returns "" for empty/whitespace-only input.
    """
    text = text.strip()
    if not text:
        return ""

    paragraphs = re.split(r"\n\s*\n", text)
    parts: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        heading_match = _HEADING4.match(para)
        if heading_match:
            parts.append(f"<h4>{_inline(heading_match.group(1))}</h4>")
        else:
            # Collapse internal single newlines into spaces — one paragraph tag.
            collapsed = " ".join(line.strip() for line in para.split("\n") if line.strip())
            parts.append(f"<p>{_inline(collapsed)}</p>")
    return "".join(parts)


def format_segment_block(label: str, text: str, heading_level: str = "h3") -> str:
    """Wrap a labelled heading + converted body — one block in the assembled edition.

    label is used verbatim as the visible heading text (callers pass the real
    published header name, e.g. "THE BIG CONVERSATION", not the FW section id).
    """
    heading = f"<{heading_level}>{html.escape(label, quote=False)}</{heading_level}>"
    body = md_to_editor_html(text)
    return heading + body
```

- [ ] **Step 3: Run + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest tests/test_beehiiv_format.py -q     # all pass
.venv/bin/python -m pytest -q 2>&1 | tail -3                    # baseline preserved
git add flatwhite/assemble/beehiiv_format.py tests/test_beehiiv_format.py
git commit -m "FW assembly: markdown-ish text -> beehiiv editor HTML fragment converter"
```

---

### Task 5: The assemble endpoint

**Files:** `flatwhite/dashboard/api.py`, `tests/test_assemble_edition.py` (new).

**Interfaces produced:** `POST /api/assemble-edition`. Takes the CURRENT running order + ready flags (as held by the frontend's `SEGMENTS` array) plus furniture inputs (sponsor, Odd Picks), reads each ready segment's saved text from `section_outputs`, formats every one via Task 4's `format_segment_block`, benchmarks every one via Task 3's `benchmark_segment`, places furniture per the real corpus's observed positions (sponsor immediately before Thread of the Week when included — confirmed from every sponsor-present edition in `beehiiv_fw_ground_truth.json`; Odd Picks then the fixed Feedback Loop boilerplate appended last, matching the corpus's consistent tail position), and returns the ordered block list + a single concatenated `assembled_html` ready to hand to the beehiiv MCP.

**Real published header names used for the heading of each block** (so the assembled edition reads like a real one, not like FW's internal ids): `editorial -> "INTRO"`, `brains -> "THE BRAINS TRUST"`, `top_picks -> "PICK & SCROLL BY THE AUSSIE CORPORATE | LAST WEEK'S TOP PICKS"`, `insidetrack -> "THE INSIDE TRACK"`, `pulse -> "AUSCORP STRESS INDEX"`, `off_the_clock -> "OFF THE CLOCK"`, `thread -> "THREAD OF THE WEEK - r/AUSCORP"`, `big_conversation -> "THE BIG CONVERSATION"`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_assemble_edition.py`:
```python
"""Tests for POST /api/assemble-edition. Monkeypatches section_outputs storage
(tmp DB) and passes the running order directly in the request body — exactly
what the dashboard's in-memory SEGMENTS array sends. NO beehiiv/network call
anywhere: this asserts on the block STRUCTURE the endpoint returns, never a
live insert (Design B — see the plan's Global Constraints)."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def assemble_client(tmp_path: Path):
    db_path = tmp_path / "assemble_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        week_iso = db_module.get_current_week_iso()
        db_module.save_section_output(week_iso, "editorial", "**Good morning AusCorp.** " + "word " * 150, "m")
        db_module.save_section_output(week_iso, "big_conversation", "**A quiet mutiny.**\n\n" + "word " * 400, "m")
        db_module.save_section_output(week_iso, "thread", "#### [_**Bunking with a colleague**_](https://reddit.com/x)\n\nA thread.", "m")
        import flatwhite.dashboard.api as api_module
        from fastapi.testclient import TestClient
        yield TestClient(api_module.app), week_iso


_BASE_SEGMENTS = [
    {"id": "editorial", "status": "ready"},
    {"id": "brains", "status": "notready"},
    {"id": "top_picks", "status": "notready"},
    {"id": "insidetrack", "status": "notready"},
    {"id": "pulse", "status": "notready"},
    {"id": "off_the_clock", "status": "notready"},
    {"id": "thread", "status": "ready"},
    {"id": "big_conversation", "status": "ready"},
]


def test_assemble_returns_only_ready_segments_in_running_order(assemble_client):
    client, week_iso = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    assert resp.status_code == 200
    body = resp.json()
    ids_in_order = [b["section"] for b in body["blocks"] if b["section"] in
                    ("editorial", "brains", "top_picks", "insidetrack", "pulse",
                     "off_the_clock", "thread", "big_conversation")]
    assert ids_in_order == ["editorial", "thread", "big_conversation"]


def test_not_ready_segments_are_flagged_missing_not_silently_dropped(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    missing = resp.json()["missing_ready"]
    assert set(missing) == {"brains", "top_picks", "insidetrack", "pulse", "off_the_clock"}


def test_each_block_has_html_and_benchmark(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    blocks = resp.json()["blocks"]
    editorial_block = next(b for b in blocks if b["section"] == "editorial")
    assert "<h3>INTRO</h3>" in editorial_block["html"] or "<h3>" in editorial_block["html"]
    assert "benchmark" in editorial_block
    assert editorial_block["benchmark"]["status"] in ("short", "within", "long", "no_data")


def test_feedback_loop_boilerplate_always_appended_last(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    blocks = resp.json()["blocks"]
    assert blocks[-1]["section"] == "feedback_loop"
    assert "tally.so" in blocks[-1]["html"]


def test_odd_picks_included_only_when_provided(assemble_client):
    client, _ = assemble_client
    resp_without = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    sections_without = [b["section"] for b in resp_without.json()["blocks"]]
    assert "odd_picks" not in sections_without

    resp_with = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "odd_picks_text": "* A quirky link. [LINK](https://example.com)",
    })
    sections_with = [b["section"] for b in resp_with.json()["blocks"]]
    assert "odd_picks" in sections_with
    # Odd Picks sits after all running-order segments, before Feedback Loop.
    assert sections_with.index("odd_picks") == len(sections_with) - 2


def test_sponsor_included_only_when_toggled_on_and_placed_before_thread(assemble_client):
    client, _ = assemble_client
    resp_without = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    assert "sponsor" not in [b["section"] for b in resp_without.json()["blocks"]]

    resp_with = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "sponsor": {"include": True, "name": "Spaceship", "text": "Pitch text here."},
    })
    sections = [b["section"] for b in resp_with.json()["blocks"]]
    assert "sponsor" in sections
    assert sections.index("sponsor") == sections.index("thread") - 1


def test_sponsor_toggled_off_omits_even_if_text_given(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "sponsor": {"include": False, "name": "Spaceship", "text": "Pitch text here."},
    })
    assert "sponsor" not in [b["section"] for b in resp.json()["blocks"]]


def test_assembled_html_is_concatenation_of_block_html(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    body = resp.json()
    expected = "".join(b["html"] for b in body["blocks"])
    assert body["assembled_html"] == expected


def test_no_ready_segments_returns_empty_blocks_not_error(assemble_client):
    client, _ = assemble_client
    all_notready = [{"id": s["id"], "status": "notready"} for s in _BASE_SEGMENTS]
    resp = client.post("/api/assemble-edition", json={"segments": all_notready})
    assert resp.status_code == 200
    # Furniture (feedback loop) still present even with zero real segments.
    assert resp.json()["blocks"][-1]["section"] == "feedback_loop"
```
Run: `.venv/bin/python -m pytest tests/test_assemble_edition.py -q` — fails (route doesn't exist).

- [ ] **Step 2: Add the endpoint.** In `flatwhite/dashboard/api.py`, after Task 2's content-bank block, add:
```python
# ── Assemble to beehiiv (Design B: format here, insert via beehiiv MCP) ──────
# This endpoint does NOT call beehiiv. It reads each ready segment's saved text
# from section_outputs, formats it into beehiiv-editor HTML (Task 4's
# beehiiv_format), benchmarks it against the real corpus (Task 3's
# assemble/benchmark), and folds in the template furniture the spec calls out
# for assembly-time handling: sponsor (only ~6/10 real editions carry one),
# Odd Picks, and the fixed Feedback Loop boilerplate. The response is the
# ordered block list + a concatenated assembled_html string. Inserting that
# into an actual beehiiv draft is a separate, human-in-the-loop step: read the
# target draft with the beehiiv MCP's get_post_content(format="editor_html"),
# then call edit_post_content with an operation whose content is
# assembled_html (a whole-doc "replace", or per-block "insertAfter" against a
# template scaffold for finer control) — never beehiiv's v2 REST content-write
# endpoints, which are Enterprise-gated (403 SEND_API_NOT_ENTERPRISE_PLAN) on
# this plan.

_REAL_SEGMENT_HEADINGS: dict[str, str] = {
    "editorial": "INTRO",
    "brains": "THE BRAINS TRUST",
    "top_picks": "PICK & SCROLL BY THE AUSSIE CORPORATE | LAST WEEK'S TOP PICKS",
    "insidetrack": "THE INSIDE TRACK",
    "pulse": "AUSCORP STRESS INDEX",
    "off_the_clock": "OFF THE CLOCK",
    "thread": "THREAD OF THE WEEK - r/AUSCORP",
    "big_conversation": "THE BIG CONVERSATION",
}

# Identical every week per beehiiv_fw_ground_truth_ANALYSIS.md ("the only
# fully invariant segment word-for-word across all 10 editions") — no input
# needed, always appended last.
_FEEDBACK_LOOP_HTML = (
    "<h3>FEEDBACK LOOP | SHARE YOUR THOUGHTS</h3>"
    "<p>If you have want to provide more detailed feedback or have any topics "
    "that you want to hear more about, you can let us know "
    '<a href="https://tally.so/r/3xXb8k">HERE</a>.</p>'
)


@app.post("/api/assemble-edition")
async def api_assemble_edition(request: Request) -> JSONResponse:
    """Build the FW edition as beehiiv-ready HTML blocks, in the current
    running order, from every segment marked ready.

    Body: {
      "segments": [{"id": str, "status": str}, ...],   # the current SEGMENTS order
      "sponsor": {"include": bool, "name": str, "text": str}?,   # optional
      "odd_picks_text": str?,                                    # optional
    }
    Returns: {
      "week_iso": str,
      "blocks": [{"section": str, "label": str, "html": str, "benchmark": {...}}, ...],
      "assembled_html": str,     # concatenation of every block's html, in order
      "missing_ready": [str],    # running-order ids NOT marked ready (or with no saved output)
    }
    """
    from flatwhite.db import load_all_section_outputs
    from flatwhite.assemble.beehiiv_format import format_segment_block
    from flatwhite.assemble.benchmark import benchmark_segment

    body = await request.json()
    segments = body.get("segments") or []
    week_iso = get_current_week_iso()
    saved_outputs = load_all_section_outputs(week_iso)

    blocks: list[dict] = []
    missing_ready: list[str] = []

    for seg in segments:
        section_id = seg.get("id")
        if section_id not in _REAL_SEGMENT_HEADINGS:
            continue  # not a real-content running-order segment (ignore unknown ids defensively)
        is_ready = seg.get("status") == "ready"
        saved = saved_outputs.get(section_id)
        if not is_ready or not saved or not saved.get("output_text", "").strip():
            missing_ready.append(section_id)
            continue

        label = _REAL_SEGMENT_HEADINGS[section_id]
        text = saved["output_text"]
        blocks.append({
            "section": section_id,
            "label": label,
            "html": format_segment_block(label, text),
            "benchmark": benchmark_segment(section_id, text),
        })

        # Sponsor sits immediately before Thread of the Week in every
        # sponsor-present real edition (confirmed across all 6/10 sponsor
        # editions in beehiiv_fw_ground_truth.json).
        if section_id == "thread":
            sponsor = body.get("sponsor") or {}
            if sponsor.get("include"):
                sponsor_label = f"TOGETHER WITH {sponsor.get('name', '').upper()}".strip()
                sponsor_html = format_segment_block(sponsor_label, sponsor.get("text", ""))
                blocks.insert(len(blocks) - 1, {
                    "section": "sponsor",
                    "label": sponsor_label,
                    "html": sponsor_html,
                    "benchmark": {"status": "no_data", "word_count": None,
                                  "target_avg": None, "target_min": None,
                                  "target_max": None, "n_editions": 0},
                })

    # Odd Picks + Feedback Loop: handled at assembly, not as running-order work
    # pages (per spec). Odd Picks only when Victor supplied text; Feedback Loop
    # always, as fixed boilerplate.
    odd_picks_text = (body.get("odd_picks_text") or "").strip()
    if odd_picks_text:
        blocks.append({
            "section": "odd_picks",
            "label": "ODD PICKS FROM LAST WEEK",
            "html": format_segment_block("ODD PICKS FROM LAST WEEK", odd_picks_text),
            "benchmark": benchmark_segment("odd_picks", odd_picks_text),
        })

    blocks.append({
        "section": "feedback_loop",
        "label": "FEEDBACK LOOP | SHARE YOUR THOUGHTS",
        "html": _FEEDBACK_LOOP_HTML,
        "benchmark": {"status": "no_data", "word_count": None,
                      "target_avg": None, "target_min": None,
                      "target_max": None, "n_editions": 0},
    })

    assembled_html = "".join(b["html"] for b in blocks)

    return JSONResponse({
        "week_iso": week_iso,
        "blocks": blocks,
        "assembled_html": assembled_html,
        "missing_ready": missing_ready,
    })
```
Note: `benchmark_segment("odd_picks", ...)` and `("sponsor", ...)` correctly return `status: "no_data"` since Task 3's `_SEGMENT_MATCHERS` has no entry for either — Odd Picks and sponsor word counts are highly variable/inconsistent-presence furniture in the corpus (per `ANALYSIS.md`), not worth benchmarking the same way as the 8 real work segments.

- [ ] **Step 3: Run + commit.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m pytest tests/test_assemble_edition.py -q     # all pass
.venv/bin/python -m pytest -q 2>&1 | tail -3                      # baseline preserved
git add flatwhite/dashboard/api.py tests/test_assemble_edition.py
git commit -m "FW assembly: POST /api/assemble-edition — ready segments -> ordered beehiiv HTML blocks + furniture + benchmark"
```

---

### Task 6: The Assemble page (frontend)

**Files:** `flatwhite/dashboard/static/index.html`.

**Interfaces:** consumes Increment 1's `SEGMENTS`/`selectSegment`/page-render framework and this plan's `POST /api/assemble-edition`. Adds a third `nav-lite` row to the sidebar ("Assemble to beehiiv", below Content bank/Sources) and an `assemble` page in the detail pane: a live preview of which running-order segments are ready, sponsor toggle + name + pitch text inputs, an Odd Picks textarea, a "Build assembly" button, and — once built — the ordered block list with benchmark chips, a concatenated HTML preview, a "Copy assembled HTML" button, and a short static note on the MCP insertion path.

- [ ] **Step 1: Add the sidebar entry.** In the sidebar markup Increment 1 added (the `<div class="side">...</div>` block with `nl-bank`/`nl-sources`), add a second divider + third `nav-lite` row:
```html
<div class="navdiv"></div>
<div class="nav-lite" id="nl-assemble" onclick="selectSegment('assemble')">Assemble to beehiiv</div>
```

- [ ] **Step 2: Add the CSS** (small additions alongside the existing `.nav-lite`/`.stat` rules from Increments 1-2):
```css
.bench-chip{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;display:inline-block;margin-left:8px}
.bench-within{background:var(--green-soft);color:var(--green-ink)}
.bench-short,.bench-long{background:var(--amber-soft);color:var(--amber-ink)}
.bench-no_data{background:var(--track);color:var(--label2)}
.block-preview{border:1px solid var(--sep);border-radius:10px;padding:10px 14px;margin-bottom:10px}
.block-preview h4{margin:0 0 6px;font-size:13px;color:var(--label2);text-transform:uppercase;letter-spacing:.03em}
.assemble-missing{color:var(--label2);font-size:13px;margin:8px 0}
```

- [ ] **Step 3: Add the render function + wire it into the page dispatch.** In `render()`'s `S.page` switch (added by Increment 1 Task 3), add an `assemble` case calling a new `renderAssemble(el)`:
```javascript
function renderAssemble(el) {
  var missingCount = SEGMENTS.filter(function(s) { return s.status !== "ready"; }).length;
  var h = '<p class="lead">Builds the edition from every segment marked ready, in the running order shown on the left.</p>';

  h += '<div class="fb mb8"><label><input type="checkbox" id="asm-sponsor-on"' +
       (S.assembleSponsorOn ? ' checked' : '') + '> Include sponsor this week</label></div>';
  h += '<input class="input mb8" id="asm-sponsor-name" placeholder="Sponsor name (e.g. Spaceship)" value="' + esc(S.assembleSponsorName || "") + '">';
  h += '<textarea class="ta mb8" id="asm-sponsor-text" placeholder="Sponsor pitch text...">' + esc(S.assembleSponsorText || "") + '</textarea>';
  h += '<textarea class="ta mb8" id="asm-odd-picks" placeholder="Odd Picks from last week (optional, one per line)...">' + esc(S.assembleOddPicks || "") + '</textarea>';

  h += '<button class="btn btn-primary mb8" onclick="buildAssembly()">Build assembly</button>';

  if (S.assembly) {
    if (S.assembly.missing_ready.length) {
      h += '<p class="assemble-missing">Not ready / no saved output: ' + S.assembly.missing_ready.join(", ") + '</p>';
    }
    S.assembly.blocks.forEach(function(b) {
      var bm = b.benchmark;
      var chip = '';
      if (bm.status !== "no_data") {
        chip = '<span class="bench-chip bench-' + bm.status + '">' + bm.word_count + 'w vs ' + bm.target_min + '-' + bm.target_max + '</span>';
      }
      h += '<div class="block-preview"><h4>' + esc(b.label) + chip + '</h4>' + b.html + '</div>';
    });
    h += '<button class="btn btn-sm" onclick="copyAssembledHtml()">Copy assembled HTML</button>';
    h += '<p class="lead" style="margin-top:14px;">Design B: this dash formats the blocks only. To publish, open the beehiiv MCP in a Claude session, read the target draft with get_post_content, then insert this HTML with edit_post_content — raw-API content write is Enterprise-gated on our plan.</p>';
  }

  el.innerHTML = h;
}

function buildAssembly() {
  S.assembleSponsorOn = $("asm-sponsor-on").checked;
  S.assembleSponsorName = $("asm-sponsor-name").value;
  S.assembleSponsorText = $("asm-sponsor-text").value;
  S.assembleOddPicks = $("asm-odd-picks").value;

  api("/api/assemble-edition", { method: "POST", body: {
    segments: SEGMENTS.map(function(s) { return { id: s.id, status: s.status }; }),
    sponsor: { include: S.assembleSponsorOn, name: S.assembleSponsorName, text: S.assembleSponsorText },
    odd_picks_text: S.assembleOddPicks,
  }}).then(function(d) {
    S.assembly = d;
    render();
  }).catch(function(e) { showToast("Assemble failed: " + e.message, "error"); });
}

function copyAssembledHtml() {
  if (!S.assembly) return;
  navigator.clipboard.writeText(S.assembly.assembled_html).then(function() {
    showToast("Copied assembled HTML");
  }).catch(function() { showToast("Copy failed — select manually", "error"); });
}
```
Add `assemble` to the `S.page` switch: `case "assemble": renderAssemble(pageBodyEl); break;` (matching whatever exact switch structure Increment 1's Task 3 produced — the case body just calls `renderAssemble` the same way `pulse`/`big_conversation`/etc call their own renderers).

- [ ] **Step 4: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 1
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/         # 200
curl -s http://127.0.0.1:8500/ | grep -c 'nl-assemble'                  # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function renderAssemble'      # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function buildAssembly'       # 1
```
Manual: open `/`, mark editorial/thread/big_conversation ready in the sidebar (or any 3 segments with saved output from earlier work), click "Assemble to beehiiv" -> the Assemble page shows the sponsor toggle + Odd Picks box; toggle sponsor on, add a name + pitch, click "Build assembly" -> ordered blocks appear with benchmark chips, sponsor sits directly before Thread if Thread is ready, Feedback Loop is the last block; "Copy assembled HTML" copies without error. Kill server.

- [ ] **Step 5: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3
git add flatwhite/dashboard/static/index.html
git commit -m "FW assembly: Assemble to beehiiv page (sponsor toggle, Odd Picks, benchmark chips, copy HTML)"
```

---

### Task 7: The Content Bank page (frontend)

**Files:** `flatwhite/dashboard/static/index.html`.

**Interfaces:** replaces the `bank` placeholder page from Increment 1 with the real Content Bank: list grouped by `segment_type`, an "Add to bank" form (segment type, title, body text, optional source note), a "Pull into edition" action per item (choosing which running-order segment id to pull into), and an "Archive" action.

- [ ] **Step 1: Add the render function**, replacing Increment 1's placeholder body for `bank`:
```javascript
function renderBank(el) {
  var h = '<p class="lead">Pieces produced ahead of time. Pull one into this week\'s running order when needed.</p>';

  h += '<div class="fb mb8">';
  h += '<select class="input" id="bank-type"><option value="big_conversation">Big Conversation</option><option value="brains_trust">Brains Trust</option></select>';
  h += '<input class="input" id="bank-title" placeholder="Title">';
  h += '</div>';
  h += '<textarea class="ta mb8" id="bank-body" placeholder="Piece text..."></textarea>';
  h += '<input class="input mb8" id="bank-source" placeholder="Source note (optional, e.g. folder name)">';
  h += '<button class="btn btn-primary mb8" onclick="addBankItem()">Add to bank</button>';

  (S.bankItems || []).forEach(function(item) {
    h += '<div class="block-preview"><h4>' + esc(item.segment_type) + '</h4>';
    h += '<div style="font-weight:600;margin-bottom:4px;">' + esc(item.title) + '</div>';
    h += '<div style="color:var(--label2);font-size:13px;margin-bottom:8px;">' + esc((item.body_text || "").slice(0, 160)) + '...</div>';
    h += '<select class="input" id="pull-target-' + item.id + '">';
    ["editorial","brains","top_picks","insidetrack","pulse","off_the_clock","thread","big_conversation"].forEach(function(sid) {
      h += '<option value="' + sid + '">' + sid + '</option>';
    });
    h += '</select> ';
    h += '<button class="btn btn-sm" onclick="pullBankItem(' + item.id + ')">Pull into edition</button> ';
    h += '<button class="btn btn-sm" onclick="archiveBankItem(' + item.id + ')">Archive</button>';
    h += '</div>';
  });

  el.innerHTML = h;
}

function addBankItem() {
  var segmentType = $("bank-type").value;
  var title = $("bank-title").value.trim();
  var bodyText = $("bank-body").value.trim();
  var sourceNote = $("bank-source").value.trim();
  if (!title || !bodyText) { showToast("Title and body text are required", "error"); return; }

  api("/api/content-bank", { method: "POST", body: {
    segment_type: segmentType, title: title, body_text: bodyText, source_note: sourceNote || null,
  }}).then(function() {
    showToast("Added to bank");
    return loadBankItems();
  }).then(render).catch(function(e) { showToast("Error: " + e.message, "error"); });
}

function loadBankItems() {
  return api("/api/content-bank").then(function(d) { S.bankItems = d.items || []; });
}

function pullBankItem(bankId) {
  var target = $("pull-target-" + bankId).value;
  api("/api/content-bank/" + bankId + "/pull", { method: "POST", body: { target_section: target } })
    .then(function() {
      showToast("Pulled into " + target + " — open that page to review and mark ready");
    })
    .catch(function(e) { showToast("Pull failed: " + e.message, "error"); });
}

function archiveBankItem(bankId) {
  api("/api/content-bank/" + bankId + "/archive", { method: "POST" })
    .then(function() { return loadBankItems(); })
    .then(render)
    .catch(function(e) { showToast("Archive failed: " + e.message, "error"); });
}
```
Wire `bank` in `loadPageData(page)` (Increment 1's data-loading switch) to call `loadBankItems()` before render, and wire the `S.page` render switch's `bank` case to call `renderBank(pageBodyEl)` instead of Increment 1's placeholder.

- [ ] **Step 2: Verify.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 1
curl -s http://127.0.0.1:8500/ | grep -c 'function renderBank'   # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function pullBankItem' # 1
```
Manual: open `/`, click "Content bank", add an item (e.g. segment type Big Conversation, a title, some body text), confirm it appears in the list; choose a pull target and click "Pull into edition"; open that segment's own page and confirm its output box now shows the pulled text (via the existing `S.sectionOutputs`/`fillOutput` flow — reload `/api/section-outputs` if the page was already loaded before the pull); archive the item and confirm it disappears from the default (active) list. Kill server.

- [ ] **Step 3: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3
git add flatwhite/dashboard/static/index.html
git commit -m "FW assembly: Content Bank page (add/list/pull-into-edition/archive)"
```

---

### Task 8: Whole control-room smoke test (this is the LAST increment)

This is not a new feature — it is the final check that six-plus increments of work actually function together before calling the rebuild done. Do not skip it because Tasks 1-7 already passed their own tests; those tests are all mocked/monkeypatched by design (per this plan's own constraints) and have never together exercised a live dashboard end to end.

- [ ] **Step 1: Full baseline.** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m pytest -q 2>&1 | tail -5` — confirm the count is the Task 1 baseline plus every test this plan added (Tasks 1-5), and the same 8 pre-existing failures, nothing else.

- [ ] **Step 2: Boot once, walk the whole thing.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500
```
Open `http://127.0.0.1:8500/` and, in order:
1. **Shell renders** — white sidebar card, running order visible, drag reorders it, status dots present (Increment 1).
2. **Every real segment page renders and still works** — Editorial (Increment 2, including the gate: confirm its "Write" action stays disabled until every other segment is ready), Brains Trust (Increment 6), Top Picks (Increment 2, feature stories included), Inside Track (Increment 5), Pulse (existing), Off the Clock (Increment 2, 5 separate categories + swap + custom add), Thread of the Week (Increment 2, paste -> formatted block), Big Conversation (Increment 4, topic bank + paragraph-paired screenshots + viral pool).
3. **Mark every segment ready** (real content isn't required for this smoke test — placeholder text is fine as long as each segment's own "Mark ready" persists via `section_outputs`, confirmed by refreshing the page and seeing the status dot survive).
4. **Content Bank** — add one item, pull it into a segment, confirm that segment's output box picks it up.
5. **Assemble to beehiiv** — with every segment ready, click "Assemble to beehiiv": confirm the block list appears in the CURRENT running order (drag two segments in the sidebar first, rebuild, confirm the assembled order follows), sponsor toggle placed directly before Thread when on, Feedback Loop always last, benchmark chips show a colour per segment, "Copy assembled HTML" works.
6. Kill the server.

- [ ] **Step 3: Report.** State the exact pytest counts, and:

> "Built + tested locally on branch `fw-control-room-assembly`. NOT merged, NOT deployed (FW deploy is Victor's). Assembly is Design B: the dash formats beehiiv-ready HTML blocks and benchmarks them against the real corpus; actually inserting into a beehiiv draft still needs a human/agent step via the beehiiv MCP (`get_post_content` / `edit_post_content`) — raw beehiiv API content-write stays Enterprise-gated and this build never calls it."

## Manual verification (whole increment, before done)

Same as Task 8 Steps 1-2 above — this increment's "done" bar IS the whole-control-room smoke test, since it is the last piece.

## Notes / explicitly out of scope

- **AusCorp Events, Salary Survey promo, "Missed last week's newsletter" footer** — real furniture per the corpus but not named in this increment's brief; not built here. If Victor wants them, they slot into the same furniture-insertion pattern Task 5 established (a fixed/short-input block placed at a corpus-confirmed position).
- **Server-side persistence of running order / ready status** — still frontend-only (`SEGMENTS`), per Increment 1's design and this plan's stated assumption 4. Fine for a single live session; would need its own small increment if Victor wants the order to survive a dashboard restart independent of section_outputs presence.
- **Per-block insertAfter chaining against a beehiiv template scaffold** — Task 5/6 produce one concatenated `assembled_html` for a simple whole-doc replace op. Finer per-block `insertAfter` chaining (so re-assembling doesn't clobber manually-tweaked blocks already in a draft) is a reasonable future refinement, not required to satisfy this increment's brief.
