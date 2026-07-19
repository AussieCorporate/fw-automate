"""Flat White editor dashboard — FastAPI backend.

Wraps the existing state.py DB functions as HTTP endpoints.
Serves the static frontend from dashboard/static/.
LLM-calling endpoints are gated behind POST requests.

Run:
    python -m uvicorn flatwhite.dashboard.api:app --port 8500 --reload
    OR via CLI: flatwhite review
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import json
import os
import secrets
import threading
import time as _time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from flatwhite.db import (
    init_db, get_connection, get_current_week_iso,
    load_all_section_outputs, get_edition_draft, set_edition_draft,
)
from flatwhite.model_router import route, list_available_models
from flatwhite.utils.text_clean import strip_reader_dashes
from flatwhite.pulse.anomaly import detect_all_anomalies
from flatwhite.dashboard.state import (
    load_pulse_state,
    load_signals_this_week,
    load_signal_trends,
    load_reddit_comparison,
    load_curated_items_by_section,
    load_top_thread,
    load_top_threads,
    load_seed_items,
    save_editor_decision,
    save_big_conversation_draft,
    save_thread_our_take,
    load_saved_draft,
    load_otc_candidates,
    save_otc_pick,
    load_otc_picks,
    OTC_CATEGORY_LABELS,
)

def _safe_override(model: str | None) -> str | None:
    """The picker's value, but only if it names a model with a configured API
    key. Blank/unknown/keyless -> None, so route() uses the task default instead
    of raising on an unusable model_id."""
    if not model:
        return None
    return model if model in {m["id"] for m in list_available_models()} else None


_STATIC_DIR = Path(__file__).parent / "static"
_SCREENSHOTTER_OUTPUT_DIR = Path(
    os.environ.get(
        "FW_SCREENSHOTTER_OUTPUT_DIR",
        str(Path.home() / "Documents" / "MISC" / "instagram-dm-screenshotter" / "output"),
    )
)
_AUTH_PASSWORD = os.environ.get("FLATWHITE_PASSWORD", "")
_AUTH_TOKEN = hashlib.sha256((_AUTH_PASSWORD + "flatwhite").encode()).hexdigest()[:32] if _AUTH_PASSWORD else ""

app = FastAPI(title="Flat White Editor Dashboard")

_LOGIN_HTML = """<!DOCTYPE html>
<html><head><title>Flat White — Login</title>
<style>
  body { font-family: system-ui; background: #faf8f5; display: flex;
         justify-content: center; align-items: center; height: 100vh; margin: 0; }
  .card { background: #fff; padding: 2.5rem; border-radius: 12px;
          box-shadow: 0 2px 12px rgba(0,0,0,0.08); text-align: center; max-width: 340px; }
  h2 { margin: 0 0 1.5rem; color: #3d2e1e; }
  input { width: 100%; padding: 0.7rem; border: 1px solid #ddd; border-radius: 6px;
          font-size: 1rem; box-sizing: border-box; }
  button { margin-top: 1rem; width: 100%; padding: 0.7rem; background: #6b4f36;
           color: #fff; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; }
  button:hover { background: #8b6f56; }
  .err { color: #c0392b; margin-top: 0.5rem; font-size: 0.9rem; }
</style></head>
<body><div class="card">
  <h2>Flat White</h2>
  <form method="POST" action="/login">
    <input type="password" name="password" placeholder="Password" autofocus />
    <button type="submit">Enter</button>
  </form>
  {error}
</div></body></html>"""


@app.post("/login")
async def login(request: Request):
    """Validate password and set auth cookie."""
    form = await request.form()
    password = form.get("password", "")
    if password == _AUTH_PASSWORD:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("fw_auth", _AUTH_TOKEN, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
        return response
    html = _LOGIN_HTML.replace("{error}", '<p class="err">Wrong password</p>')
    return HTMLResponse(html, status_code=401)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Block unauthenticated requests when FLATWHITE_PASSWORD is set."""
    if _AUTH_PASSWORD:
        path = request.url.path
        if path != "/login" and not path.startswith("/static/"):
            cookie = request.cookies.get("fw_auth", "")
            if cookie != _AUTH_TOKEN:
                html = _LOGIN_HTML.replace("{error}", "")
                return HTMLResponse(html, status_code=401)
    return await call_next(request)


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def _startup() -> None:
    """Ensure database is initialised on server start."""
    init_db()


# ── Static frontend ─────────────────────────────────────────────────────────

@app.get("/")
def serve_index() -> FileResponse:
    """Serve the single-page frontend.

    No-cache headers so a browser (or the PS Dash iframe embedding this page)
    never shows a stale copy after a deploy - the recurring "I still see the old
    version" confusion. The page is tiny; always fetching fresh costs nothing.
    """
    return FileResponse(
        _STATIC_DIR / "index.html", media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                 "Pragma": "no-cache", "Expires": "0"},
    )


# ── READ endpoints (GET) ────────────────────────────────────────────────────

@app.get("/api/pulse")
def api_pulse() -> JSONResponse:
    """Return pulse state + signals for current week."""
    pulse = load_pulse_state()
    signals = load_signals_this_week()
    anomalies = detect_all_anomalies()
    week_iso = get_current_week_iso()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM signals WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({
        "pulse": pulse,
        "signals": signals,
        "anomalies": anomalies,
        "week_iso": week_iso,
        "last_scraped_at": last_scraped_at,
    })


@app.get("/api/pulse/trends")
def api_pulse_trends() -> JSONResponse:
    """Return category-level WoW movements and biggest signal movers."""
    return JSONResponse(load_signal_trends(n_weeks=6))


@app.get("/api/reddit/compare")
def api_reddit_compare(week: str | None = None) -> JSONResponse:
    """Return Crowd vs Editorial comparison for r/auscorp posts."""
    return JSONResponse(load_reddit_comparison(week_iso=week))


@app.get("/api/items")
def api_items() -> JSONResponse:
    """Return curated items grouped by section for current week."""
    items = load_curated_items_by_section()
    week_iso = get_current_week_iso()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({"items": items, "week_iso": week_iso, "last_scraped_at": last_scraped_at})


@app.get("/api/thread")
def api_thread() -> JSONResponse:
    """Return top thread candidate for current week."""
    thread = load_top_thread()
    return JSONResponse({"thread": thread, "week_iso": get_current_week_iso()})


@app.get("/api/threads")
def api_threads(limit: int = 10, weeks: int = 1) -> JSONResponse:
    """Return top thread candidates, optionally spanning multiple weeks.

    Query params:
        limit: max threads to return (default 10).
        weeks: 1 = this week, 2 = fortnight (default 1).
    """
    limit = max(1, min(limit, 50))
    weeks = max(1, min(weeks, 4))
    threads = load_top_threads(limit=limit, weeks=weeks)
    week_iso = get_current_week_iso()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({"threads": threads, "week_iso": week_iso, "last_scraped_at": last_scraped_at})


@app.get("/api/seeds")
def api_seeds() -> JSONResponse:
    """Return Big Conversation seed items for current week."""
    seeds = load_seed_items()
    return JSONResponse({"seeds": seeds, "week_iso": get_current_week_iso()})


@app.get("/api/seed-items")
def api_seed_items() -> JSONResponse:
    """Return all non-discarded curated items for angle generation input.

    Each item includes id, title, source, tags, weighted_composite, and section.
    Used by the seed selection UI before generating angles.
    """
    week_iso = get_current_week_iso()
    conn = get_connection()
    items = conn.execute(
        """SELECT ci.id, ci.section, ci.summary, ci.weighted_composite,
                  ci.tags, ri.title, ri.source
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ? AND ci.section != 'discard'
        ORDER BY ci.weighted_composite DESC""",
        (week_iso,),
    ).fetchall()
    conn.close()
    return JSONResponse({"items": [dict(i) for i in items], "week_iso": week_iso})


@app.get("/api/seed-tags")
def api_seed_tags() -> JSONResponse:
    """Return deduplicated tags from this week's curated items, sorted by frequency.

    Used by the topic steering UI to show clickable tag chips.
    """
    week_iso = get_current_week_iso()
    conn = get_connection()
    rows = conn.execute(
        """SELECT ci.tags
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ? AND ci.section != 'discard'""",
        (week_iso,),
    ).fetchall()
    conn.close()

    tag_counts: dict[str, int] = {}
    for row in rows:
        raw_tags = row["tags"] or "[]"
        try:
            tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    tag_counts[tag.strip().lower()] = tag_counts.get(tag.strip().lower(), 0) + 1

    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    return JSONResponse({"tags": [{"tag": t, "count": c} for t, c in sorted_tags]})


@app.get("/api/off-the-clock")
def api_off_the_clock() -> JSONResponse:
    """Return Off the Clock candidates grouped by category for current week."""
    candidates = load_otc_candidates()
    picks = load_otc_picks()
    week_iso = get_current_week_iso()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({
        "candidates": candidates,
        "picks": picks,
        "week_iso": week_iso,
        "last_scraped_at": last_scraped_at,
    })


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


@app.get("/api/inside-track/image/{filename}", response_model=None)
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


@app.get("/api/draft")
def api_draft() -> JSONResponse:
    """Return saved Big Conversation draft for current week."""
    draft = load_saved_draft("big_conversation")
    return JSONResponse({"draft": draft, "week_iso": get_current_week_iso()})


@app.get("/api/status")
def api_status() -> JSONResponse:
    """Return pipeline status for current week."""
    from flatwhite.orchestrate.status import get_pipeline_status
    status = get_pipeline_status()
    return JSONResponse(status)


# ── WRITE endpoints (POST) ──────────────────────────────────────────────────

@app.post("/api/decision")
async def api_save_decision(request: Request) -> JSONResponse:
    """Save an editor decision (approve/reject/reserve) for a curated item.

    Body: {"curated_item_id": int, "decision": str, "section_placed": str}
    """
    body = await request.json()
    week_iso = get_current_week_iso()
    row_id = save_editor_decision(
        curated_item_id=body["curated_item_id"],
        decision=body["decision"],
        section_placed=body.get("section_placed"),
        issue_week_iso=week_iso,
    )
    return JSONResponse({"id": row_id, "week_iso": week_iso})


@app.post("/api/undo-decision")
async def api_undo_decision(request: Request) -> JSONResponse:
    """Delete an editor decision for a curated item.

    Body: {"curated_item_id": int}
    """
    body = await request.json()
    week_iso = get_current_week_iso()
    conn = get_connection()
    conn.execute(
        "DELETE FROM editor_decisions WHERE curated_item_id = ? AND issue_week_iso = ?",
        (body["curated_item_id"], week_iso),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"deleted": True, "week_iso": week_iso})


@app.post("/api/add-whisper")
async def api_add_whisper(request: Request) -> JSONResponse:
    """Quick-add a manual whisper directly into curated_items, bypassing classification.

    Body: {"text": str, "confidence": "green"|"yellow"|"red"}
    """
    body = await request.json()
    text = body.get("text", "").strip()
    confidence = body.get("confidence", "yellow")
    if not text:
        return JSONResponse({"error": "Whisper text is required"}, status_code=400)
    if confidence not in ("green", "yellow", "red"):
        confidence = "yellow"

    week_iso = get_current_week_iso()

    # Insert into raw_items first (source tracking)
    from flatwhite.db import insert_raw_item
    raw_id = insert_raw_item(
        title=text,
        body=None,
        source="manual_whisper",
        url=None,
        lane="editorial",
        subreddit=None,
        week_iso=week_iso,
    )

    # Mark as classified and insert directly into curated_items
    conn = get_connection()
    conn.execute("UPDATE raw_items SET classified = 1 WHERE id = ?", (raw_id,))
    cursor = conn.execute(
        """INSERT INTO curated_items
        (raw_item_id, section, summary, score_relevance, score_novelty,
         score_reliability, score_tension, score_usefulness, weighted_composite,
         tags, confidence_tag)
        VALUES (?, 'whisper', ?, 4, 4, 2, 4, 3, 3.5, '[]', ?)""",
        (raw_id, text, confidence),
    )
    conn.commit()
    curated_id = cursor.lastrowid
    conn.close()

    return JSONResponse({"id": curated_id, "raw_id": raw_id, "week_iso": week_iso})


@app.post("/api/off-the-clock/pick")
async def api_otc_pick(request: Request) -> JSONResponse:
    """Save an editor's Off the Clock pick for a category.

    Body: {"curated_item_id": int, "category": str, "blurb": str}
    """
    body = await request.json()
    curated_item_id = body.get("curated_item_id")
    category = body.get("category")
    blurb = body.get("blurb", "")

    if not isinstance(curated_item_id, int):
        return JSONResponse({"error": "curated_item_id must be an integer"}, status_code=400)
    if category not in ("otc_eating", "otc_watching", "otc_reading", "otc_wearing", "otc_going"):
        return JSONResponse({"error": "Invalid category"}, status_code=400)
    if not blurb.strip():
        return JSONResponse({"error": "blurb is required"}, status_code=400)

    row_id = save_otc_pick(
        category=category,
        curated_item_id=curated_item_id,
        editor_blurb=blurb,
    )
    return JSONResponse({"id": row_id, "week_iso": get_current_week_iso()})


@app.post("/api/save-draft")
async def api_save_draft(request: Request) -> JSONResponse:
    """Save a Big Conversation draft.

    Body: {"headline": str, "pitch": str, "supporting_item_ids": list[int], "draft_text": str}
    """
    body = await request.json()
    row_id = save_big_conversation_draft(
        headline=body["headline"],
        pitch=body["pitch"],
        supporting_item_ids=body.get("supporting_item_ids", []),
        draft_text=body["draft_text"],
    )
    return JSONResponse({"id": row_id, "week_iso": get_current_week_iso()})


@app.post("/api/fetch-thread-comments")
async def api_fetch_thread_comments(request: Request) -> JSONResponse:
    """Fetch Reddit comments for a thread candidate on demand.

    Body: {"curated_item_id": int}
    Fetches top 3 comments from Reddit and persists to raw_items.top_comments.
    Returns the fetched comments.
    """
    body = await request.json()
    curated_item_id = body.get("curated_item_id")
    if not isinstance(curated_item_id, int):
        return JSONResponse({"error": "curated_item_id must be an integer"}, status_code=400)

    conn = get_connection()
    row = conn.execute(
        """SELECT ri.id AS raw_id, ri.url, ri.top_comments
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ci.id = ?""",
        (curated_item_id,),
    ).fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": "Thread not found"}, status_code=404)

    url = row["url"]
    if not url:
        return JSONResponse({"comments": [], "error": "No URL for this thread"})

    from flatwhite.utils.http import fetch_reddit_comments
    result = fetch_reddit_comments(url, top_n=5)
    comments = result.get("comments", [])
    post_score = result.get("post_score", 0)

    if comments:
        conn = get_connection()
        conn.execute(
            "UPDATE raw_items SET top_comments = ? WHERE id = ?",
            (json.dumps(comments), row["raw_id"]),
        )
        conn.commit()
        conn.close()

    return JSONResponse({"comments": comments, "post_score": post_score, "curated_item_id": curated_item_id})


@app.post("/api/thread-take")
async def api_thread_take(request: Request) -> JSONResponse:
    """Save the editor's revised 'Our Take' text for a thread candidate.

    Body: {"curated_item_id": int, "our_take": str}
    """
    body = await request.json()
    curated_item_id = body.get("curated_item_id")
    our_take = body.get("our_take") or ""
    if not isinstance(curated_item_id, int):
        return JSONResponse({"error": "curated_item_id must be an integer"}, status_code=400)
    save_thread_our_take(curated_item_id=curated_item_id, our_take=our_take)
    return JSONResponse({"saved": True, "curated_item_id": curated_item_id})


# ── LLM endpoints (POST, triggered by button clicks) ────────────────────────

@app.post("/api/generate-summary")
async def api_generate_summary() -> JSONResponse:
    """Generate Pulse summary, driver bullets, and top-line hooks.

    Calls the same functions as `flatwhite summarise` CLI command.
    """
    try:
        from flatwhite.pulse.summary import (
            generate_pulse_summary,
            generate_driver_bullets,
            generate_top_line_hooks,
        )

        summary = generate_pulse_summary()
        drivers = generate_driver_bullets()
        hooks = generate_top_line_hooks()
        return JSONResponse({
            "summary": summary,
            "drivers": drivers,
            "hooks": hooks,
        })
    except Exception as e:
        return JSONResponse(
            {"summary": "", "drivers": [], "hooks": [], "error": str(e)},
            status_code=500,
        )


@app.post("/api/generate-hooks")
async def api_generate_hooks() -> JSONResponse:
    """Generate top-line hooks via Claude Haiku.

    Reads the top curated items for the current week and generates 3 hook options.
    """
    try:
        from flatwhite.pulse.summary import generate_top_line_hooks

        week_iso = get_current_week_iso()
        conn = get_connection()
        top_rows = conn.execute(
            """SELECT ci.summary, ri.title, ri.source
               FROM curated_items ci
               JOIN raw_items ri ON ci.raw_item_id = ri.id
               WHERE ri.week_iso = ?
                 AND ci.section != 'discard'
               ORDER BY ci.weighted_composite DESC
               LIMIT 5""",
            (week_iso,),
        ).fetchall()
        conn.close()

        top_items_text = (
            "\n".join(
                f"- [{r['source']}] {r['title']}: {r['summary']}"
                for r in top_rows
            )
            if top_rows
            else "No items classified yet."
        )

        hooks = generate_top_line_hooks(top_items_text=top_items_text)
        return JSONResponse({"hooks": hooks})
    except Exception as e:
        return JSONResponse({"hooks": [], "error": str(e)}, status_code=500)


@app.post("/api/generate-angles")
async def api_generate_angles(request: Request) -> JSONResponse:
    """Generate Big Conversation angle candidates via Gemini 2.5 Flash.

    Body (all optional): {
        "editorial_direction": str,
        "selected_item_ids": list[int]
    }
    """
    try:
        from flatwhite.classify.big_conversation import generate_angles

        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass

        angles = generate_angles(
            editorial_direction=body.get("editorial_direction", ""),
            selected_item_ids=body.get("selected_item_ids"),
        )
        if not angles:
            # Check whether the DB actually has classified items this week
            week_iso = get_current_week_iso()
            conn = get_connection()
            item_count = conn.execute(
                "SELECT COUNT(*) FROM curated_items ci JOIN raw_items ri ON ci.raw_item_id = ri.id WHERE ri.week_iso = ? AND ci.section != 'discard'",
                (week_iso,),
            ).fetchone()[0]
            conn.close()
            if item_count == 0:
                return JSONResponse(
                    {"angles": [], "error": "No classified items found for this week — run Reingest first."},
                    status_code=400,
                )
        return JSONResponse({"angles": angles})
    except Exception as e:
        print(f"[API] /api/generate-angles failed: {e}")
        return JSONResponse({"angles": [], "error": str(e)}, status_code=500)


@app.post("/api/generate-draft")
async def api_generate_draft(request: Request) -> JSONResponse:
    """Generate a Big Conversation editorial draft via Gemini 2.5 Flash.

    Body: {"headline": str, "pitch": str, "supporting_item_ids": list[int]}
    """
    try:
        from flatwhite.classify.big_conversation import draft_big_conversation

        body = await request.json()
        draft = draft_big_conversation(
            headline=body["headline"],
            pitch=body["pitch"],
            supporting_item_ids=body.get("supporting_item_ids", []),
        )
        return JSONResponse({"draft": draft})
    except Exception as e:
        return JSONResponse({"draft": "", "error": str(e)}, status_code=500)


# ── Assemble (build newsletter HTML) ──────────────────────────────────────

@app.post("/api/assemble")
async def api_assemble(request: Request) -> JSONResponse:
    """Assemble newsletter HTML from approved items.

    Body: {"hook_text": str, "rotation": "A"|"B"}
    Returns: {"html": str, "subject": str, "preview_text": str, "rotation": str}
    """
    from pathlib import Path
    from flatwhite.assemble.renderer import render_newsletter
    from flatwhite.orchestrate.runner import get_next_rotation
    from flatwhite.db import get_pulse_history
    from flatwhite.model_router import route
    from flatwhite.assemble.templates import (
        SUBJECT_LINE_SYSTEM, SUBJECT_LINE_PROMPT,
        PREVIEW_TEXT_SYSTEM, PREVIEW_TEXT_PROMPT,
    )

    body = await request.json()
    hook_text = body.get("hook_text", "").strip()
    rotation = body.get("rotation") or get_next_rotation()

    if not hook_text:
        return JSONResponse({"error": "hook_text is required"}, status_code=400)

    week_iso = get_current_week_iso()

    try:
        # 1. Render newsletter HTML
        content_html = render_newsletter(hook_text, rotation)

        # 2. Gather metadata for subject/preview generation
        history = get_pulse_history(weeks=1)
        smoothed_score = history[0]["smoothed_score"] if history else 50.0
        direction = history[0]["direction"] if history else "stable"

        conn = get_connection()
        approved = conn.execute(
            """SELECT ci.summary, ed.section_placed
            FROM editor_decisions ed
            JOIN curated_items ci ON ed.curated_item_id = ci.id
            WHERE ed.decision = 'approved' AND ed.issue_week_iso = ?
            ORDER BY ci.weighted_composite DESC LIMIT 5""",
            (week_iso,),
        ).fetchall()

        big_convo_headline = "This week in AusCorp"
        top_whisper = "No whispers this week"
        thread_title = "No thread selected"
        top_items_summary = ""

        for item in approved:
            d = dict(item)
            section = d.get("section_placed", "")
            summary = d.get("summary", "")
            if section == "big_conversation_seed" and big_convo_headline == "This week in AusCorp":
                big_convo_headline = summary[:80]
            elif section == "whisper" and top_whisper == "No whispers this week":
                top_whisper = summary[:80]
            elif section == "thread_candidate" and thread_title == "No thread selected":
                thread_title = summary[:80]
            if top_items_summary:
                top_items_summary += "; "
            top_items_summary += summary[:60]

        if not top_items_summary:
            top_items_summary = "This week's corporate pulse and editorial highlights."

        # 3. Generate subject line
        try:
            subject = route(
                task_type="editorial",
                prompt=SUBJECT_LINE_PROMPT.format(
                    smoothed_score=f"{smoothed_score:.0f}",
                    direction=direction,
                    big_conversation_headline=big_convo_headline,
                    top_whisper=top_whisper,
                    thread_title=thread_title,
                ),
                system=SUBJECT_LINE_SYSTEM,
            )
            subject = subject.strip().strip('"').strip("'")
            if len(subject) > 60:
                subject = subject[:57] + "..."
            if len(subject) < 5:
                subject = "Flat White -- This Week in AusCorp"
        except Exception:
            subject = "Flat White -- This Week in AusCorp"

        # 4. Generate preview text
        try:
            preview_text = route(
                task_type="hook",
                prompt=PREVIEW_TEXT_PROMPT.format(
                    subject_line=subject,
                    smoothed_score=f"{smoothed_score:.0f}",
                    direction=direction,
                    top_items_summary=top_items_summary[:200],
                ),
                system=PREVIEW_TEXT_SYSTEM,
            )
            preview_text = preview_text.strip().strip('"').strip("'")
            if len(preview_text) > 120:
                preview_text = preview_text[:117] + "..."
            if len(preview_text) < 5:
                preview_text = "The weekly pulse on Australian corporate life."
        except Exception:
            preview_text = "The weekly pulse on Australian corporate life."

        # 5. Write HTML to data/preview.html
        preview_path = Path(__file__).parent.parent / "data" / "preview.html"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(f"<!DOCTYPE html><html><body>{content_html}</body></html>")

        # 6. Store in newsletters table
        conn.execute(
            """INSERT OR REPLACE INTO newsletters (week_iso, beehiiv_post_id, rotation, published_at)
            VALUES (?, NULL, ?, NULL)""",
            (week_iso, rotation),
        )
        conn.commit()
        conn.close()

        return JSONResponse({
            "html": content_html,
            "subject": subject,
            "preview_text": preview_text,
            "rotation": rotation,
            "week_iso": week_iso,
            "char_count": len(content_html),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── New endpoints ────────────────────────────────────────────────────────────

@app.get("/api/models")
def api_models() -> JSONResponse:
    """Return available LLM models based on configured API keys."""
    from flatwhite.model_router import list_available_models
    return JSONResponse({"models": list_available_models()})



@app.get("/api/big-conversation-candidates")
def api_big_conv_candidates() -> JSONResponse:
    """Return top 5 Big Conversation candidates from all ingested data."""
    week_iso = get_current_week_iso()
    conn = get_connection()

    rows = conn.execute(
        """SELECT ci.id, ci.section, ci.summary, ci.weighted_composite,
                  ci.score_relevance, ci.score_tension, ci.score_novelty,
                  ri.title, ri.source, ri.url
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ?
          AND ci.section IN ('big_conversation_seed', 'what_we_watching', 'finds')
        ORDER BY (COALESCE(ri.post_score, 0) * 0.5 + COALESCE(ri.comment_engagement, 0) * 0.3 + (ci.score_relevance * 0.3 + ci.score_tension * 0.4 + ci.score_novelty * 0.3) * 20) DESC
        LIMIT 5""",
        (week_iso,),
    ).fetchall()
    conn.close()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({"candidates": [dict(r) for r in rows], "week_iso": week_iso, "last_scraped_at": last_scraped_at})


# ── Reingest (background pipeline refresh) ─────────────────────────────────

_ingest_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "completed_at": None,
    "step": "",
    "error": None,
}
_ingest_lock = threading.Lock()


def _run_ingest_background() -> None:
    """Run the full ingest pipeline in a background thread.

    Runs independent signal groups in parallel for faster execution:
      Group 1 (parallel): Fast Lane A signals
      Group 2 (parallel): Editorial sources
      Group 3 (parallel): Slow signals (Google Trends)
      Group 4 (after 1+2): Derived signals (depend on editorial data)
      Group 5 (after all): Pulse calculation + Classification

    Each signal is wrapped individually so one failure doesn't stop the rest.
    """
    from concurrent.futures import ThreadPoolExecutor

    global _ingest_state
    errors: list[str] = []

    def _step(name: str, fn: callable) -> None:
        _ingest_state["step"] = name
        try:
            fn()
        except Exception as e:
            msg = f"{name}: {type(e).__name__}: {e}"
            print(f"  ⚠ reingest skip — {msg}")
            errors.append(msg)

    def _run_group1() -> None:
        """Group 1: Fast Lane A signals."""
        _step("market_hiring", lambda: __import__("flatwhite.signals.market_hiring", fromlist=["pull_market_hiring"]).pull_market_hiring())
        _step("hiring_pulse", lambda: __import__("flatwhite.signals.hiring_pulse", fromlist=["pull_hiring_pulse"]).pull_hiring_pulse())
        _step("layoff_news", lambda: __import__("flatwhite.signals.news_velocity", fromlist=["pull_layoff_news_velocity"]).pull_layoff_news_velocity())
        _step("consumer_confidence", lambda: __import__("flatwhite.signals.consumer_confidence", fromlist=["pull_consumer_confidence"]).pull_consumer_confidence())
        _step("asx_volatility", lambda: __import__("flatwhite.signals.asx_volatility", fromlist=["pull_asx_volatility"]).pull_asx_volatility())
        _step("asx_momentum", lambda: __import__("flatwhite.signals.asx_momentum", fromlist=["pull_asx_momentum"]).pull_asx_momentum())
        _step("indeed_hiring", lambda: __import__("flatwhite.signals.indeed_hiring", fromlist=["pull_indeed_hiring"]).pull_indeed_hiring())
        _step("asic_insolvency", lambda: __import__("flatwhite.signals.asic_insolvency", fromlist=["pull_asic_insolvency"]).pull_asic_insolvency())

    def _run_group2() -> None:
        """Group 2: Editorial sources."""
        _step("reddit_editorial", lambda: __import__("flatwhite.editorial.reddit_rss", fromlist=["pull_reddit_editorial"]).pull_reddit_editorial())
        _step("google_news", lambda: __import__("flatwhite.editorial.google_news_editorial", fromlist=["pull_google_news_editorial"]).pull_google_news_editorial())
        _step("twitter", lambda: __import__("flatwhite.editorial.twitter_rss", fromlist=["pull_twitter_editorial"]).pull_twitter_editorial())
        _step("rss_feeds", lambda: __import__("flatwhite.editorial.rss_feeds", fromlist=["pull_rss_feeds"]).pull_rss_feeds())
        _step("linkedin_newsletters", lambda: __import__("flatwhite.editorial.linkedin_rss", fromlist=["pull_linkedin_newsletters"]).pull_linkedin_newsletters())
        _step("email_newsletters", lambda: __import__("flatwhite.editorial.email_ingest", fromlist=["pull_email_newsletters"]).pull_email_newsletters())
        _step("podcast_feeds", lambda: __import__("flatwhite.editorial.podcast_feeds", fromlist=["pull_podcast_feeds"]).pull_podcast_feeds())
        _step("off_the_clock", lambda: __import__("flatwhite.editorial.off_the_clock", fromlist=["pull_off_the_clock"]).pull_off_the_clock())

    def _run_group3() -> None:
        """Group 3: Slow signals (Google Trends — rate limited)."""
        _step("google_trends", lambda: __import__("flatwhite.signals.google_trends", fromlist=["pull_all_google_trends"]).pull_all_google_trends())
        _step("resume_anxiety", lambda: __import__("flatwhite.signals.resume_anxiety", fromlist=["pull_resume_anxiety"]).pull_resume_anxiety())

    try:
        # Groups 1, 2, 3 run in parallel
        _ingest_state["step"] = "groups_1_2_3_parallel"
        with ThreadPoolExecutor(max_workers=3) as executor:
            f1 = executor.submit(_run_group1)
            f2 = executor.submit(_run_group2)
            f3 = executor.submit(_run_group3)
            f1.result()
            f2.result()
            f3.result()

        # Group 4: Derived signals (depend on editorial data from group 2)
        _ingest_state["step"] = "group_4_derived"
        _step("reddit_velocity", lambda: __import__("flatwhite.signals.reddit_topic_velocity", fromlist=["pull_reddit_topic_velocity"]).pull_reddit_topic_velocity())
        _step("auslaw_velocity", lambda: __import__("flatwhite.signals.auslaw_velocity", fromlist=["pull_auslaw_velocity"]).pull_auslaw_velocity())

        # Group 5: Pulse calculation + Classification (depend on all prior groups)
        _ingest_state["step"] = "group_5_pulse_classify"
        _step("pulse", lambda: __import__("flatwhite.pulse.composite", fromlist=["calculate_pulse"]).calculate_pulse())
        _step("classify", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified())
        _step("classify_otc", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified())

        _ingest_state["step"] = "done"
        if errors:
            _ingest_state["error"] = f"{len(errors)} signal(s) failed: {errors[0]}"
        else:
            _ingest_state["error"] = None
    except Exception as e:
        _ingest_state["error"] = str(e)
    finally:
        _ingest_state["running"] = False
        _ingest_state["completed_at"] = _time.strftime("%Y-%m-%d %H:%M:%S")


@app.post("/api/reingest")
async def api_reingest() -> JSONResponse:
    """Start a full data reingest in the background.

    Returns immediately. Poll GET /api/reingest-status for progress.
    """
    with _ingest_lock:
        if _ingest_state["running"]:
            return JSONResponse(
                {"started": False, "message": "Ingest already running", "step": _ingest_state["step"]},
                status_code=409,
            )
        _ingest_state["running"] = True
        _ingest_state["started_at"] = _time.strftime("%Y-%m-%d %H:%M:%S")
        _ingest_state["completed_at"] = None
        _ingest_state["step"] = "starting"
        _ingest_state["error"] = None

    thread = threading.Thread(target=_run_ingest_background, daemon=True)
    thread.start()
    return JSONResponse({"started": True, "message": "Ingest started"})


@app.get("/api/reingest-status")
def api_reingest_status() -> JSONResponse:
    """Return current ingest status for polling."""
    return JSONResponse({
        "running": _ingest_state["running"],
        "step": _ingest_state["step"],
        "started_at": _ingest_state["started_at"],
        "completed_at": _ingest_state["completed_at"],
        "error": _ingest_state["error"],
    })


# ── Background section runner ─────────────────────────────────────────────
# Each section RUN fires a background thread and returns immediately.
# Frontend polls /api/section-status/{section} for progress.

_section_state: dict[str, dict] = {}
_section_lock = threading.Lock()

_SECTION_RUNNERS: dict[str, list[tuple[str, "Callable"]]] = {
    "pulse": [
        ("Market hiring",       lambda: __import__("flatwhite.signals.market_hiring",   fromlist=["pull_market_hiring"]).pull_market_hiring()),
        ("News velocity",       lambda: __import__("flatwhite.signals.news_velocity",   fromlist=["pull_layoff_news_velocity"]).pull_layoff_news_velocity()),
        ("Consumer confidence", lambda: __import__("flatwhite.signals.consumer_confidence", fromlist=["pull_consumer_confidence"]).pull_consumer_confidence()),
        ("ASX volatility",      lambda: __import__("flatwhite.signals.asx_volatility",  fromlist=["pull_asx_volatility"]).pull_asx_volatility()),
        ("ASX momentum",        lambda: __import__("flatwhite.signals.asx_momentum",    fromlist=["pull_asx_momentum"]).pull_asx_momentum()),
        ("Indeed hiring",       lambda: __import__("flatwhite.signals.indeed_hiring",   fromlist=["pull_indeed_hiring"]).pull_indeed_hiring()),
        ("ASIC insolvency",     lambda: __import__("flatwhite.signals.asic_insolvency", fromlist=["pull_asic_insolvency"]).pull_asic_insolvency()),
        ("Signal intelligence", lambda: __import__("flatwhite.signals.signal_intelligence", fromlist=["run_signal_intelligence"]).run_signal_intelligence()),
        ("Composite",           lambda: __import__("flatwhite.pulse.composite",         fromlist=["calculate_pulse"]).calculate_pulse()),
    ],
    "editorial": [
        ("Reddit RSS",    lambda: __import__("flatwhite.editorial.reddit_rss",              fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News",   lambda: __import__("flatwhite.editorial.google_news_editorial",   fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("RSS feeds",     lambda: __import__("flatwhite.editorial.rss_feeds",               fromlist=["pull_rss_feeds"]).pull_rss_feeds()),
        ("Podcast feeds", lambda: __import__("flatwhite.editorial.podcast_feeds",           fromlist=["pull_podcast_feeds"]).pull_podcast_feeds()),
        ("Prune stale",   lambda: __import__("flatwhite.db", fromlist=["prune_stale_raw_items"]).prune_stale_raw_items(max_age_days=7)),
        ("Classify",      lambda: __import__("flatwhite.classify.classifier",               fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "classify": [
        ("Classify items", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "finds": [
        ("Reddit RSS",    lambda: __import__("flatwhite.editorial.reddit_rss",            fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News",   lambda: __import__("flatwhite.editorial.google_news_editorial", fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("RSS feeds",     lambda: __import__("flatwhite.editorial.rss_feeds",             fromlist=["pull_rss_feeds"]).pull_rss_feeds()),
        ("Podcast feeds", lambda: __import__("flatwhite.editorial.podcast_feeds",         fromlist=["pull_podcast_feeds"]).pull_podcast_feeds()),
        ("Prune stale",   lambda: __import__("flatwhite.db", fromlist=["prune_stale_raw_items"]).prune_stale_raw_items(max_age_days=7)),
        ("Classify",      lambda: __import__("flatwhite.classify.classifier",             fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "thread": [
        ("Reddit RSS",  lambda: __import__("flatwhite.editorial.reddit_rss", fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Prune stale", lambda: __import__("flatwhite.db", fromlist=["prune_stale_raw_items"]).prune_stale_raw_items(max_age_days=7)),
        ("Classify",    lambda: __import__("flatwhite.classify.classifier",  fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "linkedin_insights": [
        ("LinkedIn Insights", lambda: __import__("flatwhite.signals.linkedin_insights", fromlist=["scrape_all_company_insights"]).scrape_all_company_insights()),
    ],
    "off_the_clock": [
        ("Off the Clock", lambda: __import__("flatwhite.editorial.off_the_clock", fromlist=["pull_off_the_clock"]).pull_off_the_clock()),
        ("Prune stale",   lambda: __import__("flatwhite.db", fromlist=["prune_stale_raw_items"]).prune_stale_raw_items(max_age_days=7)),
        ("Classify OTC",  lambda: __import__("flatwhite.classify.classifier",     fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified()),
    ],
    "classify_otc": [
        ("Classify OTC", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified()),
    ],
    "big_conversation": [
        ("Reddit RSS",  lambda: __import__("flatwhite.editorial.reddit_rss",             fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News", lambda: __import__("flatwhite.editorial.google_news_editorial",  fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("Top AU news", lambda: __import__("flatwhite.editorial.google_news_top_au",     fromlist=["pull_google_news_top_au"]).pull_google_news_top_au()),
        ("Prune stale", lambda: __import__("flatwhite.db", fromlist=["prune_stale_raw_items"]).prune_stale_raw_items(max_age_days=7)),
        ("Classify",    lambda: __import__("flatwhite.classify.classifier",              fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
}

_SCRAPE_ALL_SECTIONS = [
    # "thread" intentionally excluded: its tab is hidden (Victor's decision) and
    # its scraper steps (Reddit RSS + Classify) largely duplicate what "finds"
    # and "editorial" already do here, so thread_candidate items still get
    # classified via those. thread_candidate stays in classify/classifier.py's
    # VALID_SECTIONS untouched.
    "pulse", "editorial", "big_conversation", "finds", "off_the_clock",
]

_scrape_all_state: dict = {
    "running": False,
    "current": None,   # section name currently being scraped
    "results": [],     # list of {section, status: "ok"|"error"|"skipped", error: str|None}
}
_scrape_all_lock = threading.Lock()


def _run_scrape_all() -> None:
    """Run all section scrapers sequentially. One failure does not stop others."""
    _scrape_all_state.update({"current": None, "results": []})
    for section in _SCRAPE_ALL_SECTIONS:
        _scrape_all_state["current"] = section
        with _section_lock:
            if _section_state.get(section, {}).get("running"):
                _scrape_all_state["results"].append(
                    {"section": section, "status": "skipped", "error": "already running"}
                )
                continue
            steps = _SECTION_RUNNERS[section]
            _section_state[section] = {
                "running": True, "done": False, "error": None,
                "step": 0, "total": len(steps),
                "step_name": steps[0][0] if steps else "",
                "completed_at": None,
            }
        _run_section_background(section)  # blocks until this section finishes
        err = _section_state.get(section, {}).get("error")
        _scrape_all_state["results"].append(
            {"section": section, "status": "error" if err else "ok", "error": err}
        )
    _scrape_all_state.update({"running": False, "current": None})


@app.post("/api/scrape-all")
async def api_scrape_all() -> JSONResponse:
    """Start scraping all sections sequentially in the background."""
    with _scrape_all_lock:
        if _scrape_all_state["running"]:
            return JSONResponse({"error": "Scrape All already running"}, status_code=409)
        _scrape_all_state["running"] = True  # set under lock before releasing
    thread = threading.Thread(target=_run_scrape_all, daemon=True)
    thread.start()
    return JSONResponse({"started": True, "sections": _SCRAPE_ALL_SECTIONS})


@app.get("/api/scrape-all/status")
def api_scrape_all_status() -> JSONResponse:
    """Poll the current Scrape All progress."""
    return JSONResponse({
        "running": _scrape_all_state["running"],
        "current": _scrape_all_state["current"],
        "results": _scrape_all_state["results"],
        "total": len(_SCRAPE_ALL_SECTIONS),
    })


def _run_section_background(section: str) -> None:
    """Run a section's steps sequentially, updating _section_state after each step.

    `step` is the 0-based index of the step currently running (not the count of completed steps).
    On completion, step == total (sentinel for "all done"). Frontend should render step/total as
    "N of M" by treating step as "currently on step N+1" while running, and "all done" when step==total.
    """
    from flatwhite.utils.timing import timed_step

    steps = _SECTION_RUNNERS[section]
    total = len(steps)
    try:
        for i, (label, fn) in enumerate(steps):
            _section_state[section].update({"step": i, "total": total, "step_name": label})
            with timed_step(section, label):
                fn()
        _section_state[section] = {
            "running": False, "done": True, "error": None,
            "step": total, "total": total, "step_name": "",
            "completed_at": _time.strftime("%H:%M:%S"),
        }
    except Exception as e:
        _section_state[section] = {
            "running": False, "done": True, "error": str(e),
            "step": _section_state[section].get("step", 0), "total": total, "step_name": "",
            "completed_at": _time.strftime("%H:%M:%S"),
        }


@app.post("/api/run-section")
async def api_run_section(request: Request) -> JSONResponse:
    """Start a section RUN in the background. Returns immediately.

    Body: {"section": str}
    Poll /api/section-status/{section} for progress.
    """
    body = await request.json()
    section = body.get("section", "")

    if section not in _SECTION_RUNNERS:
        return JSONResponse(
            {"error": f"Unknown section: {section}. Available: {', '.join(_SECTION_RUNNERS.keys())}"},
            status_code=400,
        )

    with _section_lock:
        state = _section_state.get(section, {})
        if state.get("running"):
            return JSONResponse({"started": False, "message": f"{section} already running"}, status_code=409)
        steps = _SECTION_RUNNERS[section]
        _section_state[section] = {
            "running": True, "done": False, "error": None,
            "step": 0, "total": len(steps), "step_name": steps[0][0] if steps else "",
            "completed_at": None,
        }

    thread = threading.Thread(target=_run_section_background, args=(section,), daemon=True)
    thread.start()
    return JSONResponse({"started": True, "section": section})


@app.get("/api/section-status/{section}")
def api_section_status(section: str) -> JSONResponse:
    """Poll for section RUN status."""
    state = _section_state.get(section, {"running": False, "done": False, "error": None})
    return JSONResponse(state)


@app.post("/api/backfill")
async def api_backfill(request: Request) -> JSONResponse:
    """Backfill historical signal data and seed employer snapshots for a past week.

    Body: {"target_week": str}  e.g. "2026-W12"
    Runs run_backfill(weeks=2) for signals, then seeds employer_snapshots via SQL copy.
    Returns: {"seeded_employers": int, "started_signal_backfill": bool}
    """
    body = await request.json()
    target_week = body.get("target_week", "")

    if not re.match(r"^\d{4}-W\d{2}$", target_week):
        return JSONResponse({"error": "Invalid target_week format. Expected YYYY-Www (e.g. 2026-W12)"}, status_code=400)

    conn = get_connection()
    # Check if employer snapshots already exist for target_week
    existing = conn.execute(
        "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (target_week,)
    ).fetchone()[0]

    seeded = 0
    if existing == 0:
        # Copy current week's employer snapshots as target_week baseline
        current_week = get_current_week_iso()
        year, wn = int(target_week[:4]), int(target_week[6:])
        target_date = _dt.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u").strftime("%Y-%m-%d")
        conn.execute(
            f"""INSERT OR IGNORE INTO employer_snapshots
                (employer_id, open_roles_count, snapshot_date, week_iso, extraction_method, ats_platform)
                SELECT employer_id, open_roles_count, ?, ?, extraction_method, ats_platform
                FROM employer_snapshots WHERE week_iso = ?""",
            (target_date, target_week, current_week),
        )
        conn.commit()
        seeded = conn.execute(
            "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (target_week,)
        ).fetchone()[0]
    conn.close()

    # Run signal backfill in a background thread (slow — includes Google Trends)
    def _do_signal_backfill():
        from flatwhite.pulse.backfill import run_backfill
        run_backfill(weeks=2)

    t = threading.Thread(target=_do_signal_backfill, daemon=True)
    t.start()

    return JSONResponse({
        "seeded_employers": seeded,
        "started_signal_backfill": True,
        "target_week": target_week,
    })


@app.get("/api/run-log")
def api_run_log() -> JSONResponse:
    """Return the last 100 lines of the cron run log."""
    log_path = Path(__file__).parent.parent.parent / "data" / "logs" / "cron.log"
    if not log_path.exists():
        return JSONResponse({"lines": [], "exists": False})
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return JSONResponse({"lines": lines[-100:], "exists": True})


# ── Signal Intelligence endpoints ─────────────────────────────────────────

@app.get("/api/signal-intelligence/{week_iso}")
def api_get_signal_intelligence(week_iso: str) -> JSONResponse:
    """Return signal intelligence records for a week, keyed by signal_name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT signal_name, delta, articles, commentary, generated_at FROM signal_intelligence WHERE week_iso = ?",
        (week_iso,),
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        result[r["signal_name"]] = {
            "delta":        r["delta"],
            "articles":     json.loads(r["articles"]) if r["articles"] else [],
            "commentary":   r["commentary"],
            "generated_at": r["generated_at"],
        }
    return JSONResponse(result)


@app.post("/api/signal-intelligence/refresh")
async def api_refresh_signal_intelligence(request: Request) -> JSONResponse:
    """Re-run signal intelligence for a single signal/week pair.

    Body: {"signal_name": str, "week_iso": str}
    """
    body = await request.json()
    signal_name = body.get("signal_name", "").strip()
    week_iso = body.get("week_iso", "").strip()

    if not signal_name or not week_iso:
        return JSONResponse({"error": "Missing required fields: signal_name, week_iso"}, status_code=400)
    if not re.match(r"^\d{4}-W\d{2}$", week_iso):
        return JSONResponse({"error": f"Invalid week_iso format: {week_iso}. Expected YYYY-Www"}, status_code=400)

    conn = get_connection()
    row = conn.execute(
        "SELECT delta FROM signal_intelligence WHERE signal_name = ? AND week_iso = ?",
        (signal_name, week_iso),
    ).fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": "No existing record to refresh"}, status_code=404)

    def _refresh():
        try:
            from flatwhite.signals.signal_intelligence import _fetch_articles, _synthesise
            year, wn = int(week_iso[:4]), int(week_iso[6:])
            dt = _dt.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u")
            month = dt.strftime("%B")
            delta = row["delta"]
            articles = _fetch_articles(signal_name, month, str(year))
            commentary = _synthesise(signal_name, delta, articles)
            c = get_connection()
            c.execute(
                """INSERT OR REPLACE INTO signal_intelligence
                   (signal_name, week_iso, delta, articles, commentary, generated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (signal_name, week_iso, delta, json.dumps(articles), commentary),
            )
            c.commit()
            c.close()
            print(f"  signal_intelligence refresh: {signal_name} ({week_iso}) — done")
        except Exception as e:
            print(f"  signal_intelligence refresh FAILED: {signal_name} ({week_iso}): {e}")

    threading.Thread(target=_refresh, daemon=True).start()
    return JSONResponse({"refreshing": True, "signal_name": signal_name, "week_iso": week_iso})


# ── Extraction Health & Feedback endpoints ────────────────────────────────

@app.get("/api/extraction-health")
def get_extraction_health() -> JSONResponse:
    """Return employer extraction health for current week."""
    conn = get_connection()
    week_iso = get_current_week_iso()

    health = conn.execute(
        """SELECT eh.employer_id, ew.employer_name, ew.sector, ew.ats_platform,
                  eh.roles_extracted, eh.success, eh.error_message,
                  ew.consecutive_carry_forward_weeks
           FROM extraction_health eh
           JOIN employer_watchlist ew ON eh.employer_id = ew.id
           WHERE eh.week_iso = ?
           ORDER BY eh.success ASC, ew.employer_name ASC""",
        (week_iso,),
    ).fetchall()

    missing = conn.execute(
        """SELECT id, employer_name, sector, ats_platform, consecutive_carry_forward_weeks
           FROM employer_watchlist
           WHERE active = 1
           AND id NOT IN (SELECT employer_id FROM extraction_health WHERE week_iso = ?)""",
        (week_iso,),
    ).fetchall()

    conn.close()

    return JSONResponse({
        "week_iso": week_iso,
        "results": [dict(r) for r in health],
        "not_pulled": [dict(r) for r in missing],
        "total_employers": len(health) + len(missing),
        "successful": sum(1 for r in health if r["success"]),
    })


@app.get("/api/feedback")
def get_feedback_data() -> JSONResponse:
    """Return editor decision stats and performance data."""
    conn = get_connection()

    stats = conn.execute(
        """SELECT issue_week_iso, decision, COUNT(*) as cnt
           FROM editor_decisions
           GROUP BY issue_week_iso, decision
           ORDER BY issue_week_iso DESC
           LIMIT 40""",
    ).fetchall()

    click_rates = conn.execute(
        """SELECT issue_week_iso, AVG(click_rate) as avg_click_rate,
                  COUNT(*) as total_decisions
           FROM editor_decisions
           WHERE click_rate IS NOT NULL
           GROUP BY issue_week_iso
           ORDER BY issue_week_iso DESC""",
    ).fetchall()

    conn.close()

    return JSONResponse({
        "decision_stats": [dict(s) for s in stats],
        "click_rates": [dict(c) for c in click_rates],
    })


@app.post("/api/manual-feedback")
async def save_manual_feedback(request: Request) -> JSONResponse:
    """Save manual performance feedback for a newsletter week."""
    data = await request.json()
    week_iso = data.get("week_iso")
    open_rate = data.get("open_rate")
    click_rate = data.get("click_rate")
    notes = data.get("notes", "")

    if not week_iso:
        return JSONResponse({"error": "week_iso required"}, status_code=400)

    from flatwhite.publish.local_feedback import record_feedback
    result = record_feedback(
        week_iso=week_iso,
        open_rate=float(open_rate) if open_rate else None,
        click_rate=float(click_rate) if click_rate else None,
        notes=notes,
    )

    return JSONResponse(result)



# ── Pulse trends ─────────────────────────────────────────────────────────────

@app.get("/api/pulse/trends")
def api_pulse_trends() -> JSONResponse:
    """Return category-level WoW movements and biggest signal movers."""
    return JSONResponse(load_signal_trends(n_weeks=6))


# ── Reddit compare ────────────────────────────────────────────────────────────

@app.get("/api/reddit/compare")
def api_reddit_compare(week: str | None = None) -> JSONResponse:
    """Return Crowd vs Editorial comparison for r/auscorp posts."""
    return JSONResponse(load_reddit_comparison(week_iso=week))


# ── Off the Clock ─────────────────────────────────────────────────────────────

@app.get("/api/off-the-clock")
def api_off_the_clock() -> JSONResponse:
    """Return Off the Clock candidates grouped by category for current week."""
    candidates = load_otc_candidates()
    picks = load_otc_picks()
    week_iso = get_current_week_iso()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({
        "candidates": candidates,
        "picks": picks,
        "week_iso": week_iso,
        "last_scraped_at": last_scraped_at,
    })


@app.post("/api/off-the-clock/pick")
async def api_otc_pick(request: Request) -> JSONResponse:
    """Save an editor's Off the Clock pick for a category.

    Body: {"curated_item_id": int, "category": str, "blurb": str}
    """
    body = await request.json()
    curated_item_id = body.get("curated_item_id")
    category = body.get("category")
    blurb = body.get("blurb", "")

    if not isinstance(curated_item_id, int):
        return JSONResponse({"error": "curated_item_id must be an integer"}, status_code=400)
    if category not in ("otc_eating", "otc_watching", "otc_reading", "otc_wearing", "otc_going"):
        return JSONResponse({"error": "Invalid category"}, status_code=400)
    if not blurb.strip():
        return JSONResponse({"error": "blurb is required"}, status_code=400)

    row_id = save_otc_pick(
        category=category,
        curated_item_id=curated_item_id,
        editor_blurb=blurb,
    )
    return JSONResponse({"id": row_id, "week_iso": get_current_week_iso()})


# ── Section outputs ───────────────────────────────────────────────────────────

@app.get("/api/section-outputs")
def api_section_outputs() -> JSONResponse:
    """Return all saved section outputs for current week."""
    from flatwhite.db import load_all_section_outputs
    week_iso = get_current_week_iso()
    outputs = load_all_section_outputs(week_iso)
    return JSONResponse({"outputs": {k: v for k, v in outputs.items()}, "week_iso": week_iso})


@app.post("/api/section-output/{section}")
async def api_save_section_output(section: str, request: Request) -> JSONResponse:
    """Save edited output for a section."""
    from flatwhite.db import save_section_output
    body = await request.json()
    week_iso = get_current_week_iso()
    save_section_output(week_iso, section, body.get("output_text", ""), body.get("model_used"))
    return JSONResponse({"saved": True, "section": section})


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
    (e.g. "big_conversation", "brains_trust"). Writes body_text into section_outputs
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

# NOTE: the real FW dashboard section id for the Brains Trust segment is
# "brains_trust" (see flatwhite/dashboard/static/index.html's SEGMENTS array
# and flatwhite/dashboard/api.py's proceed_fns dict) — NOT "brains". Task 3's
# flatwhite/assemble/benchmark.py was corrected the same way; kept consistent
# here so benchmark_segment("brains_trust", ...) actually matches a profile.
_REAL_SEGMENT_HEADINGS: dict[str, str] = {
    "editorial": "INTRO",
    "brains_trust": "THE BRAINS TRUST",
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
      "missing_ready": [str],    # running-order ids NOT marked ready (or with no saved output);
                                 # also includes "sponsor" when sponsor.include was True but the
                                 # sponsor block was never inserted (e.g. Thread wasn't ready)
      "sponsor_included": bool,  # True only when a sponsor block was actually appended to blocks
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
    sponsor_included = False

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
                sponsor_included = True

    # A wanted sponsor placement (include=True) that never made it into blocks
    # is a dropped paid placement, not a "no sponsor this week": most commonly
    # Thread of the Week wasn't ready, so the loop above hit its missing-ready
    # continue before ever reaching the sponsor-insertion step. Surface this
    # through the same missing_ready signal the frontend already checks,
    # rather than a second warning channel nothing consumes yet.
    sponsor_wanted = bool((body.get("sponsor") or {}).get("include"))
    if sponsor_wanted and not sponsor_included:
        missing_ready.append("sponsor")

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
        "sponsor_included": sponsor_included,
    })


# ── Brains Trust angle pool (read-only Trading Strategy research bank) ──────

@app.get("/api/brains-trust/angles")
def api_brains_trust_angles() -> JSONResponse:
    """Read-only: recommended Brains Trust angles from the Trading Strategy
    research bank across the last 3 weeks. Never writes to that project;
    fails soft to an empty list on any error (missing folder, bad JSON,
    locked DB, or anything else) so a research-bank outage never blocks
    Victor picking an angle from whatever else is available."""
    from flatwhite.dashboard.brains_trust_research import load_angle_recommendations
    try:
        angles = load_angle_recommendations(weeks=3)
    except Exception:
        angles = []
    return JSONResponse({"angles": angles})


# ── Big Conversation candidates ───────────────────────────────────────────────

@app.get("/api/big-conversation-candidates")
def api_big_conv_candidates() -> JSONResponse:
    """Return top 5 Big Conversation candidates from all ingested data."""
    week_iso = get_current_week_iso()
    conn = get_connection()

    rows = conn.execute(
        """SELECT ci.id, ci.section, ci.summary, ci.weighted_composite,
                  ci.score_relevance, ci.score_tension, ci.score_novelty,
                  ri.title, ri.source, ri.url
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ?
          AND ci.section IN ('big_conversation_seed', 'what_we_watching', 'finds')
        ORDER BY (COALESCE(ri.post_score, 0) * 0.5 + COALESCE(ri.comment_engagement, 0) * 0.3 + (ci.score_relevance * 0.3 + ci.score_tension * 0.4 + ci.score_novelty * 0.3) * 20) DESC
        LIMIT 5""",
        (week_iso,),
    ).fetchall()
    conn.close()
    _conn = get_connection()
    _row = _conn.execute(
        "SELECT max(pulled_at) FROM raw_items WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    _conn.close()
    last_scraped_at = _row[0] if _row else None
    return JSONResponse({"candidates": [dict(r) for r in rows], "week_iso": week_iso, "last_scraped_at": last_scraped_at})


# ── Section proceed helpers ──────────────────────────────────────────────────

def _proceed_pulse(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import PULSE_SUMMARY_SYSTEM, PULSE_SUMMARY_PROMPT
    from flatwhite.dashboard.state import load_pulse_state, load_signals_this_week
    from flatwhite.db import get_interactions
    from flatwhite.signals.macro_context import fetch_macro_headlines
    from flatwhite.pulse.summary import _fetch_editorial_evidence

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="summary", prompt=custom_prompt, system=PULSE_SUMMARY_SYSTEM, model_override=override)

    pulse = load_pulse_state()
    signals = load_signals_this_week()

    week_iso = get_current_week_iso()
    conn = get_connection()
    year_s, wn_s = int(week_iso[:4]), int(week_iso[6:])
    dt_s = _dt.datetime.strptime(f"{year_s}-W{wn_s:02d}-1", "%G-W%V-%u")
    prev_wk = (dt_s - _dt.timedelta(weeks=1)).strftime("%G-W%V")
    prev_rows = conn.execute(
        "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (prev_wk,),
    ).fetchall()
    conn.close()
    prev_map = {s["signal_name"]: s["normalised_score"] for s in prev_rows}

    # Respect selected signals from the dashboard checkboxes
    selected_signals = data.get("selected_signals", [s["signal_name"] for s in signals])

    from flatwhite.pulse.summary import _format_signal_name, INVERTED_SIGNALS

    signal_lines = []
    for s in signals:
        name = s["signal_name"]
        if name not in selected_signals:
            continue
        display = _format_signal_name(name)
        score = round(s["normalised_score"], 1)
        prev = prev_map.get(name)
        inv_tag = " [INVERTED]" if name in INVERTED_SIGNALS else ""
        if prev is not None:
            delta = round(score - prev, 1)
            signal_lines.append(f"{display}: {score}/100 (prev: {round(prev, 1)}, Δ: {delta:+.1f}){inv_tag}")
        else:
            signal_lines.append(f"{display}: {score}/100{inv_tag}")

    interactions = get_interactions(week_iso)
    interactions_block = ""
    if interactions:
        interactions_block = "\nSignal interactions detected:\n" + "\n".join(
            f"- {ix['pattern_name']}: {ix['narrative']}" for ix in interactions
        ) + "\n"

    macro_context = ""
    try:
        macro_context = fetch_macro_headlines()
    except Exception:
        pass

    editorial_evidence = _fetch_editorial_evidence(week_iso)

    # Include signal intelligence commentary for selected signals
    intel_conn = get_connection()
    intel_rows = intel_conn.execute(
        "SELECT signal_name, commentary, articles FROM signal_intelligence WHERE week_iso = ?",
        (week_iso,),
    ).fetchall()
    intel_conn.close()
    intel_lines = []
    for r in intel_rows:
        if r["signal_name"] in selected_signals and r["commentary"]:
            intel_lines.append(f"- {r['signal_name']}: {r['commentary']}")
    if intel_lines:
        editorial_evidence += (
            "\nSignal evidence (analyst commentary on key movers):\n"
            + "\n".join(intel_lines) + "\n"
        )

    prompt = PULSE_SUMMARY_PROMPT.format(
        smoothed=f"{pulse['smoothed_score']:.0f}" if pulse else "50",
        direction=pulse["direction"] if pulse else "stable",
        prev_smoothed=f"{pulse.get('smoothed_score', 50):.0f}" if pulse else "50",
        drivers="\n".join(signal_lines[:10]),
        interactions_block=interactions_block,
        macro_context=macro_context,
        editorial_evidence=editorial_evidence,
    )
    return route(task_type="summary", prompt=prompt, system=PULSE_SUMMARY_SYSTEM, model_override=override)


def _load_big_conv_evidence(
    headline: str, pitch: str,
    supporting_ids: list[int], supporting_summaries: list[str],
    data: dict,
) -> str:
    """Load full article bodies and find related articles for Big Conversation.

    Returns a formatted text block with:
    1. The selected article's full body text
    2. Explicitly provided supporting items (with bodies)
    3. Auto-discovered related articles from the same week matching the topic
    """
    conn = get_connection()
    week_iso = get_current_week_iso()
    evidence_parts: list[str] = []

    # 1. Load supporting items by ID with full body text
    loaded_ids: set[int] = set()
    if supporting_ids:
        for sid in supporting_ids:
            row = conn.execute(
                """SELECT ci.id, ci.summary, ri.title, ri.source, ri.url, ri.body
                FROM curated_items ci JOIN raw_items ri ON ci.raw_item_id = ri.id
                WHERE ci.id = ?""",
                (sid,),
            ).fetchone()
            if row:
                loaded_ids.add(row["id"])
                body = (row["body"] or "")[:3000]
                # Skip bodies that are just HTML redirect links
                if body.startswith("<a href=") or len(body) < 30:
                    body = ""
                body_block = f"\n  Full text: {body}" if body else ""
                evidence_parts.append(
                    f"- {row['title']} ({row['source']})\n"
                    f"  Summary: {row['summary']}{body_block}"
                )
                if row["url"]:
                    evidence_parts[-1] += f"\n  URL: {row['url']}"

    # 2. Add pre-formatted supporting summaries (from frontend)
    for s in supporting_summaries:
        if s not in [e.split("\n")[0].lstrip("- ") for e in evidence_parts]:
            evidence_parts.append(f"- {s}")

    # 3. If still no summaries, try custom topic data
    if not evidence_parts and data.get("supporting_data"):
        evidence_parts.append(f"- {data['supporting_data']}")

    # 4. Auto-discover related articles from same week
    # Extract key words from headline for matching
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "for", "of", "to", "in", "and", "or", "on", "at", "by", "its", "has", "have", "with", "this", "that", "from"}
    keywords = [w.lower() for w in re.sub(r"[^\w\s]", "", headline).split() if len(w) > 3 and w.lower() not in stop_words]

    if keywords:
        # Find articles with matching keywords in title or body
        all_items = conn.execute(
            """SELECT ci.id, ci.summary, ci.section, ri.title, ri.source, ri.url, ri.body
            FROM curated_items ci JOIN raw_items ri ON ci.raw_item_id = ri.id
            WHERE ri.week_iso = ? AND ci.section != 'discard' AND ci.id NOT IN ({})
            ORDER BY ci.weighted_composite DESC""".format(
                ",".join("?" for _ in loaded_ids) if loaded_ids else "0"
            ),
            (week_iso, *loaded_ids),
        ).fetchall()

        related: list[dict] = []
        for item in all_items:
            title_lower = (item["title"] or "").lower()
            body_lower = (item["body"] or "").lower()
            text = title_lower + " " + body_lower
            match_count = sum(1 for kw in keywords if kw in text)
            if match_count >= 2:  # At least 2 keyword matches
                related.append(dict(item))

        if related:
            evidence_parts.append("")
            evidence_parts.append("RELATED ARTICLES on the same topic from this week:")
            for r in related[:5]:
                body = (r["body"] or "")[:2000]
                if body.startswith("<a href=") or len(body) < 30:
                    body = ""
                body_block = f"\n  Full text: {body}" if body else ""
                evidence_parts.append(
                    f"- {r['title']} ({r['source']})\n"
                    f"  Summary: {r['summary']}{body_block}"
                )

    conn.close()

    if not evidence_parts:
        return "(no supporting items)"

    return "\n".join(evidence_parts)


def _proceed_big_conversation(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import EDITORIAL_VOICE, BIG_CONVERSATION_DRAFT_SYSTEM, BIG_CONVERSATION_DRAFT_PROMPT

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE, model_override=override)

    # Accept both field name variants (frontend sends title/summary, custom form sends headline/pitch)
    headline = data.get("headline") or data.get("title", "")
    pitch = data.get("pitch") or data.get("summary", "")
    supporting_ids = data.get("supporting_item_ids", [])
    supporting_summaries = data.get("supporting_summaries") or []

    items_block = _load_big_conv_evidence(headline, pitch, supporting_ids, supporting_summaries, data)

    prompt = BIG_CONVERSATION_DRAFT_PROMPT.format(
        headline=headline,
        pitch=pitch,
        supporting_items=items_block,
    )
    return route(task_type="editorial", prompt=prompt, system=BIG_CONVERSATION_DRAFT_SYSTEM, model_override=override)


def _proceed_finds(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE, model_override=override)

    items = data.get("selected_items", [])
    items_block = "\n\n".join(
        f"Title: {item.get('title', '')}\nURL: {item.get('url', '')}\nSummary: {item.get('summary', '')}"
        for item in items
    )

    prompt = (
        "Write the Finds section for this week's Flat White newsletter.\n\n"
        f"Selected items:\n{items_block}\n\n"
        "For each item, write a headline and a 2-3 sentence blurb. Voice: dry, observant, "
        "Australian corporate commentary. Each blurb should tell the reader why this matters "
        "to someone in corporate Australia. End each with 'Read more' on its own line.\n\n"
        "Output each find as: HEADLINE\\nBLURB\\nRead more\\n\\n"
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=override)


def _proceed_thread(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import THREAD_OUR_TAKE_SYSTEM, THREAD_OUR_TAKE_PROMPT

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=THREAD_OUR_TAKE_SYSTEM, model_override=override)

    title = data.get("title", "")
    body = data.get("body", data.get("summary", ""))
    top_comments = data.get("top_comments", [])
    comments_block = "\n".join(
        f"- {c['text'] if isinstance(c, dict) else c}" for c in top_comments[:5]
    ) if top_comments else "(no comments)"
    editorial_frame = data.get("editorial_frame", "")

    prompt = THREAD_OUR_TAKE_PROMPT.format(
        title=title,
        body=body,
        top_comments=comments_block,
        editorial_frame=editorial_frame,
    )
    return route(task_type="editorial", prompt=prompt, system=THREAD_OUR_TAKE_SYSTEM, model_override=override)


def _proceed_off_the_clock(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE, model_override=override)

    picks = data.get("picks", [])
    picks_block = "\n\n".join(
        "Category: {}\nTitle: {}{}".format(
            p.get("category", ""),
            p.get("title", ""),
            ("\nURL: " + p["url"]) if p.get("url") else "",
        ) + "\nDraft blurb: {}".format(p.get("blurb", ""))
        for p in picks
    )

    prompt = (
        "Write the Off the Clock entries for Flat White.\n\n"
        f"{picks_block}\n\n"
        "For each item, write EXACTLY this format:\n\n"
        "CATEGORY (uppercase, one word: EATING, WATCHING, READING, WEARING, or GOING)\n"
        "A catchy title (4-8 words, sentence case, no period)\n\n"
        "One sentence that is dry, specific, fun and engaging. Not a review. A statement from "
        "someone who already knows. Australian English. No filler intensifiers. The sentence "
        "should make you want to click. End with LINK\n\n"
        "EXAMPLES OF THE RIGHT OUTPUT:\n\n"
        "EATING\n"
        "The dinner with no commute costs\n\n"
        "Melbourne's Elpiet Group is covering your transport costs to get you through the door "
        "of their Italian restaurants, which, given fuel prices, is either generous hospitality "
        "or very good marketing. LINK\n\n"
        "WATCHING\n"
        "The Office spin-off dropped last week\n\n"
        "The Office spin-off drops this week, so if you were planning to be productive on Friday "
        "afternoon, now you have a reason not to be. LINK\n\n"
        "READING\n"
        "Should you keep your holiday flights?\n\n"
        "With the Iran conflict escalating, here's a practical rundown for Australian travellers "
        "trying to work out whether their upcoming flights are still worth keeping. LINK\n\n"
        "---\n\n"
        "Replace LINK with [LINK](url) using the URL provided for each item.\n"
        "One entry per item. Blank line between category header and blurb. "
        "Blank line between entries."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=override)


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


def _generate_otc_custom_summary(category: str, url: str, content: str, model: str | None) -> str:
    """Write a short, RAW draft blurb for a custom Off the Clock pick.

    Deliberately produces only a 1-2 sentence draft summary (matching the shape
    of candidate.summary for scraped picks) - NOT the final CATEGORY/title/
    one-liner/[LINK] block that _proceed_off_the_clock produces. That final
    formatting still happens once, later, when all 5 categories are combined
    in a single _proceed_off_the_clock call. Producing the final format here
    would mean the combined call runs an already-formatted block back through
    the formatter a second time, garbling it.
    """
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    override = _safe_override(model)
    label = OTC_CATEGORY_LABELS.get(category, category)

    prompt = (
        f"Write a short draft blurb for the Off the Clock '{label}' category.\n\n"
        f"Pasted content:\n{content}\n\n"
        + (f"URL: {url}\n\n" if url else "")
        + "Write ONLY a 1-2 sentence draft summary of this pick, dry, specific and "
        "engaging. Australian English. No filler intensifiers.\n\n"
        "Do NOT include a category header, a title, or a markdown link - this is a "
        "raw draft summary only, not the final formatted entry. The final "
        "category header, title and link formatting is produced later, in a separate step."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=override)


def _proceed_editorial(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.classify.prompts import EDITORIAL_INTRO_SYSTEM, EDITORIAL_INTRO_PROMPT

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_INTRO_SYSTEM, model_override=override)

    big_story = (data.get("big_story") or "").strip()
    big_conversation_text = (data.get("big_conversation_output") or "").strip()
    other_segments = data.get("other_segments", [])

    other_block = "\n\n".join(
        f"{seg.get('label', seg.get('id', ''))}:\n{seg.get('output_text', '')}"
        for seg in other_segments
        if seg.get("output_text")
    ) or "(no other segment output supplied)"

    prompt = EDITORIAL_INTRO_PROMPT.format(
        big_story=big_story or "(no big story of the week nominated)",
        big_conversation_text=big_conversation_text or "(no Big Conversation output supplied)",
        other_segments=other_block,
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_INTRO_SYSTEM, model_override=override)


def _proceed_brains_trust(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    """Consolidate the angle Victor picked plus the surfaced 3-week research
    pool into a Brains Trust draft. Same (data, model, custom_prompt) -> str
    shape as every other _proceed_* function, so it plugs into proceed_fns
    unchanged.

    data: {
        "chosen_pitch": str,             # the angle Victor picked
        "chosen_angle": str,             # its supporting angle summary
        "chosen_why_tac": str,           # optional, why it matters to readers
        "candidates_pool": list[dict],   # the full window shown on screen,
                                          # each {date_iso, pitch, angle}
    }
    """
    from flatwhite.classify.prompts import BRAINS_TRUST_VOICE

    override = _safe_override(model)

    if custom_prompt:
        return route(task_type="brains_trust", prompt=custom_prompt, system=BRAINS_TRUST_VOICE, model_override=override)

    chosen_pitch = (data.get("chosen_pitch") or "").strip()
    chosen_angle = (data.get("chosen_angle") or "").strip()
    chosen_why = (data.get("chosen_why_tac") or "").strip()
    pool = data.get("candidates_pool") or []

    pool_lines = [
        f"- ({p.get('date_iso', '')}) {p.get('pitch', '')} - {p.get('angle', '')}"
        for p in pool if isinstance(p, dict) and p.get("pitch")
    ]
    pool_block = "\n".join(pool_lines) if pool_lines else "(no additional research pool supplied)"

    prompt = (
        "Write this week's Brains Trust (also called the Economic Scoop) section "
        "for the Flat White newsletter.\n\n"
        f"CHOSEN ANGLE:\n{chosen_pitch}\n{chosen_angle}\n"
        + (f"Why it matters to readers: {chosen_why}\n" if chosen_why else "")
        + "\n"
        "RESEARCH BANK FROM THE LAST 3 WEEKS (consolidate whatever is relevant "
        "to the chosen angle above; ignore anything unrelated):\n"
        f"{pool_block}\n\n"
        "Output ONLY the Brains Trust body text. No title. No sign-off. "
        "Ground every claim in the research bank; do not invent figures."
    )
    return route(task_type="brains_trust", prompt=prompt, system=BRAINS_TRUST_VOICE, model_override=override)


# ── Proceed section endpoint ──────────────────────────────────────────────────

@app.post("/api/proceed-section")
async def api_proceed_section(request: Request) -> JSONResponse:
    """Call the LLM proceed function for a given newsletter section.

    Body: {
        "section": str,
        "model": str | None,
        "data": dict (section-specific context),
        "custom_prompt": str | None (if provided, sent verbatim to LLM)
    }
    Returns: {"section": str, "output": str, "week_iso": str}
    """
    body = await request.json()
    section = body.get("section", "")
    model = body.get("model") or None
    data = body.get("data", {})
    custom_prompt = body.get("custom_prompt") or None

    proceed_fns = {
        "pulse": _proceed_pulse,
        "big_conversation": _proceed_big_conversation,
        "finds": _proceed_finds,
        # "thread" intentionally excluded: its tab is hidden (Victor's
        # decision), so there is no UI path left to call it. _proceed_thread
        # is left defined (unreferenced) rather than deleted, to keep this
        # change minimal.
        "off_the_clock": _proceed_off_the_clock,
        "editorial": _proceed_editorial,
        "insidetrack": _proceed_inside_track,
        "brains_trust": _proceed_brains_trust,
    }

    if section not in proceed_fns:
        return JSONResponse({"error": f"Unknown section: {section}"}, status_code=400)

    import asyncio
    loop = asyncio.get_event_loop()
    week_iso = get_current_week_iso()
    try:
        output = await loop.run_in_executor(
            None, proceed_fns[section], data, model, custom_prompt
        )
        output = strip_reader_dashes(output)
        return JSONResponse({"section": section, "output": output, "model": model, "week_iso": week_iso})
    except Exception as e:
        return JSONResponse({"section": section, "error": str(e)}, status_code=500)


@app.post("/api/otc-custom-summary")
async def api_otc_custom_summary(request: Request) -> JSONResponse:
    """Write a short RAW draft blurb for a custom (URL + pasted content) Off the
    Clock pick, WITHOUT the final CATEGORY/title/[LINK] formatting.

    Body: {"category": str, "url": str, "content": str, "model": str | None}
    Returns: {"output": str}

    This is deliberately separate from /api/proceed-section's off_the_clock
    dispatch (_proceed_off_the_clock), which produces the fully formatted
    entry block. Sending a custom pick through _proceed_off_the_clock here
    and then again in the final combined Generate call would run an
    already-formatted block through the formatter a second time.
    """
    body = await request.json()
    category = body.get("category", "")
    url = body.get("url", "")
    content = body.get("content", "")
    model = body.get("model") or None

    if not content or not content.strip():
        return JSONResponse({"error": "content is required"}, status_code=400)

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        output = await loop.run_in_executor(
            None, _generate_otc_custom_summary, category, url, content, model
        )
        output = strip_reader_dashes(output)
        return JSONResponse({"output": output})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/preview-prompt")
async def api_preview_prompt(request: Request) -> JSONResponse:
    """Render and return the default LLM prompt for a section without calling the LLM.

    Body: {"section": str, "data": dict (optional)}
    Returns: {"prompt": str, "section": str, "context_breakdown": dict}
    """
    body = await request.json()
    section = body.get("section", "")
    data = body.get("data", {})

    try:
        if section == "pulse":
            from flatwhite.classify.prompts import PULSE_SUMMARY_PROMPT
            from flatwhite.dashboard.state import load_pulse_state, load_signals_this_week
            from flatwhite.db import get_interactions
            from flatwhite.signals.macro_context import fetch_macro_headlines
            pulse = load_pulse_state()
            signals = load_signals_this_week()

            week_iso = get_current_week_iso()
            conn = get_connection()
            year_s, wn_s = int(week_iso[:4]), int(week_iso[6:])
            dt_s = _dt.datetime.strptime(f"{year_s}-W{wn_s:02d}-1", "%G-W%V-%u")
            prev_wk = (dt_s - _dt.timedelta(weeks=1)).strftime("%G-W%V")
            prev_rows = conn.execute(
                "SELECT signal_name, normalised_score FROM signals WHERE week_iso = ? AND lane = 'pulse'",
                (prev_wk,),
            ).fetchall()
            conn.close()
            prev_map = {s["signal_name"]: s["normalised_score"] for s in prev_rows}
            from flatwhite.pulse.summary import _format_signal_name, INVERTED_SIGNALS
            selected_signals = data.get("selected_signals", [s["signal_name"] for s in signals])
            signal_lines = []
            for s in signals:
                if s["signal_name"] in selected_signals:
                    name = s["signal_name"]
                    display = _format_signal_name(name)
                    score = round(s["normalised_score"], 1)
                    prev = prev_map.get(name)
                    inv_tag = " [INVERTED]" if name in INVERTED_SIGNALS else ""
                    if prev is not None:
                        delta = round(score - prev, 1)
                        signal_lines.append(f"{display}: {score}/100 (prev: {round(prev,1)}, Δ: {delta:+.1f}){inv_tag}")
                    else:
                        signal_lines.append(f"{display}: {score}/100{inv_tag}")

            interactions = get_interactions(week_iso)
            interactions_block = ""
            if interactions:
                interactions_block = "\nSignal interactions detected:\n" + "\n".join(
                    f"- {ix['pattern_name']}: {ix['narrative']}" for ix in interactions
                ) + "\n"
            macro_context = ""
            try:
                macro_context = fetch_macro_headlines()
            except Exception:
                pass

            from flatwhite.pulse.summary import _fetch_editorial_evidence
            editorial_evidence = _fetch_editorial_evidence(week_iso)

            # Include signal intelligence for selected signals
            intel_conn2 = get_connection()
            intel_rows2 = intel_conn2.execute(
                "SELECT signal_name, commentary FROM signal_intelligence WHERE week_iso = ?",
                (week_iso,),
            ).fetchall()
            intel_conn2.close()
            intel_lines2 = []
            for r2 in intel_rows2:
                if r2["signal_name"] in selected_signals and r2["commentary"]:
                    intel_lines2.append(f"- {r2['signal_name']}: {r2['commentary']}")
            if intel_lines2:
                editorial_evidence += (
                    "\nSignal evidence (analyst commentary on key movers):\n"
                    + "\n".join(intel_lines2) + "\n"
                )

            # Fetch previous week's smoothed score for accurate WoW comparison
            prev_pulse_conn = get_connection()
            prev_pulse_row = prev_pulse_conn.execute(
                "SELECT smoothed_score FROM pulse_history WHERE week_iso = ?",
                (prev_wk,),
            ).fetchone()
            prev_pulse_conn.close()
            prev_smoothed_val = prev_pulse_row["smoothed_score"] if prev_pulse_row else (pulse.get("smoothed_score", 50) if pulse else 50)

            prompt = PULSE_SUMMARY_PROMPT.format(
                smoothed=f"{pulse['smoothed_score']:.0f}" if pulse else "50",
                direction=pulse["direction"] if pulse else "stable",
                prev_smoothed=f"{prev_smoothed_val:.0f}",
                drivers="\n".join(signal_lines[:10]),
                interactions_block=interactions_block,
                macro_context=macro_context,
                editorial_evidence=editorial_evidence,
            )

            # Build moverDeltas for context_breakdown
            moverDeltas_for_breakdown = {
                name: round(score - prev_map[name], 1)
                for name, score in {s["signal_name"]: s["normalised_score"] for s in signals}.items()
                if name in prev_map
            }

            # Fetch signal_intelligence records for this week
            intel_conn = get_connection()
            intel_rows = intel_conn.execute(
                "SELECT signal_name, delta, commentary, articles FROM signal_intelligence WHERE week_iso = ?",
                (week_iso,),
            ).fetchall()
            intel_conn.close()

            signal_intelligence_breakdown = [
                {
                    "signal_name": r["signal_name"],
                    "delta": r["delta"],
                    "commentary": r["commentary"],
                    "articles": json.loads(r["articles"]) if r["articles"] else [],
                }
                for r in intel_rows
            ]

            context_breakdown = {
                "signals": [
                    {
                        "name": s["signal_name"],
                        "score": round(s["normalised_score"], 1) if s.get("normalised_score") is not None else None,
                        "delta": moverDeltas_for_breakdown.get(s["signal_name"]),
                        "area": s.get("area", ""),
                    }
                    for s in signals
                    if s["signal_name"] in selected_signals
                ],
                "signal_intelligence": signal_intelligence_breakdown,
                "composite": {
                    "score": pulse.get("smoothed_score") if pulse else None,
                    "direction": pulse.get("direction") if pulse else None,
                } if pulse else {},
            }

            return JSONResponse({"prompt": prompt, "section": section, "context_breakdown": context_breakdown})

        elif section == "big_conversation":
            from flatwhite.classify.prompts import BIG_CONVERSATION_DRAFT_PROMPT
            headline = data.get("headline") or data.get("title", "")
            pitch = data.get("pitch") or data.get("summary", "")
            supporting_ids = data.get("supporting_item_ids", [])
            supporting_summaries = data.get("supporting_summaries", [])

            items_with_bodies = _load_big_conv_evidence(headline, pitch, supporting_ids, supporting_summaries, data)

            prompt = BIG_CONVERSATION_DRAFT_PROMPT.format(
                headline=headline,
                pitch=pitch,
                supporting_items=items_with_bodies,
            )
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": line[:80]} for line in items_with_bodies.split("\n") if line.strip().startswith("-")],
            }

        elif section == "off_the_clock":
            picks = data.get("picks", [])
            picks_block = "\n\n".join(
                "Category: {}\nTitle: {}{}".format(
                    p.get("category", ""),
                    p.get("title", ""),
                    ("\nURL: " + p["url"]) if p.get("url") else "",
                ) + "\nDraft blurb: {}".format(p.get("blurb", ""))
                for p in picks
            )
            prompt = (
                "Write the Off the Clock entries for Flat White.\n\n"
                f"{picks_block}\n\n"
                "For each item, output EXACTLY this format:\n\n"
                "CATEGORY (uppercase: EATING, WATCHING, READING, WEARING, or GOING)\n"
                "A catchy title (4-8 words, sentence case)\n\n"
                "One dry, specific, fun sentence. Not a review. Australian English. End with [LINK](url).\n\n"
                "Blank line between entries."
            )
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": p.get("title", ""), "category": p.get("category", "")} for p in picks],
            }

        elif section == "finds":
            items = data.get("selected_items", [])
            items_block = "\n\n".join(
                f"Title: {item.get('title', '')}\nURL: {item.get('url', '')}\nSummary: {item.get('summary', '')}"
                for item in items
            )
            prompt = (
                "Write the Finds section for this week's Flat White newsletter.\n\n"
                f"Selected items:\n{items_block}\n\n"
                "For each item, write a headline and a 2-3 sentence blurb. Voice: dry, observant, "
                "Australian corporate commentary. Each blurb should tell the reader why this matters "
                "to someone in corporate Australia. End each with 'Read more' on its own line.\n\n"
                "Output each find as: HEADLINE\\nBLURB\\nRead more\\n\\n"
            )
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": item.get("title", ""), "score": item.get("weighted_composite")} for item in items],
            }

        else:
            return JSONResponse({"error": f"Preview not supported for section: {section}"}, status_code=400)

        return JSONResponse({"prompt": prompt, "section": section, "context_breakdown": context_breakdown})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Topic Heat (Big Conversation engagement signals) ─────────────────────────

# Cache for Google rising queries (expensive to fetch — store per session)
_rising_queries_cache: dict[str, Any] = {"data": None, "fetched_at": None}


@app.get("/api/topic-heat")
def api_topic_heat() -> JSONResponse:
    """Return current topic heat data: Reddit anomalies + cached rising queries."""
    from flatwhite.signals.topic_heat import fetch_reddit_topic_heat
    week_iso = get_current_week_iso()
    reddit = fetch_reddit_topic_heat(week_iso)
    return JSONResponse({
        "reddit_heat": reddit,
        "rising_queries": _rising_queries_cache["data"] or [],
        "rising_queries_fetched_at": _rising_queries_cache["fetched_at"],
        "week_iso": week_iso,
    })


@app.post("/api/topic-heat/fetch-trends")
async def api_fetch_rising_trends() -> JSONResponse:
    """Fetch Google Trends rising queries for AusCorp seed keywords.

    Expensive call (~5 min due to rate limits). Results are cached in memory
    and automatically injected into Big Conversation angle generation.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        from flatwhite.signals.topic_heat import fetch_google_rising_queries
        queries = await loop.run_in_executor(None, fetch_google_rising_queries)
        now = _dt.datetime.utcnow().isoformat() + "Z"
        _rising_queries_cache["data"] = queries
        _rising_queries_cache["fetched_at"] = now
        return JSONResponse({
            "rising_queries": queries,
            "fetched_at": now,
        })
    except Exception as e:
        return JSONResponse({"rising_queries": [], "error": str(e)}, status_code=500)


# ── Top Picks (Beehiiv Pick & Scroll) ────────────────────────────────────────

# In-memory cache so we don't re-scrape on every page load
_top_picks_cache: dict[str, Any] = {"data": None, "scraped_at": None}


@app.get("/api/top-picks")
def api_top_picks() -> JSONResponse:
    """Return cached Top Picks data (Beehiiv click rankings).

    Returns cached results if available, otherwise returns empty list.
    Frontend must POST /api/top-picks/scrape to trigger a fresh fetch.
    """
    return JSONResponse({
        "picks": _top_picks_cache["data"] or [],
        "scraped_at": _top_picks_cache["scraped_at"],
        "week_iso": get_current_week_iso(),
    })


@app.post("/api/top-picks/scrape")
async def api_top_picks_scrape(request: Request) -> JSONResponse:
    """Scrape last 7 days of Pick & Scroll click data from Beehiiv.

    Body (optional): {"days": int}  — defaults to 7
    Returns: {"picks": [...], "scraped_at": str}
    """
    import asyncio

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    days = body.get("days", 7)

    loop = asyncio.get_event_loop()
    try:
        from flatwhite.editorial.beehiiv_picks import scrape_top_picks
        picks = await loop.run_in_executor(None, scrape_top_picks, days, 20)
        now = _dt.datetime.utcnow().isoformat() + "Z"
        _top_picks_cache["data"] = picks
        _top_picks_cache["scraped_at"] = now
        return JSONResponse({
            "picks": picks,
            "scraped_at": now,
            "week_iso": get_current_week_iso(),
        })
    except Exception as e:
        return JSONResponse({"picks": [], "error": str(e)}, status_code=500)


@app.get("/api/top-picks/recent-posts")
def api_top_picks_recent_posts() -> JSONResponse:
    """Return recent Pick & Scroll edition posts (title + link) so Victor can
    flag which ones were FEATURE stories.

    A feature has no click-tracked link (the story runs inline, not as an
    external link), so it never shows up in /api/top-picks/scrape's
    click-ranked list - the "top clicks" that DO show for a feature edition
    are just the OTHER links in that same article, not the feature itself.
    """
    from flatwhite.editorial.beehiiv_picks import fetch_recent_posts
    try:
        posts = fetch_recent_posts(days=7)
        return JSONResponse({"posts": posts})
    except Exception as e:
        return JSONResponse({"posts": [], "error": str(e)}, status_code=500)


# ── Big Conversation (Instagram DM screenshotter pipeline) ─────────────────
# Increment 4: the produced piece + screenshots live in the Instagram DM
# screenshotter project's output/ folder (read-only from FW's side — the
# `big-conversation` skill that writes them runs Claude-side, outside this
# process; FW only prepares + reads). See
# flatwhite/dashboard/big_conversation_bank.py for the filesystem logic.

from flatwhite.dashboard import big_conversation_bank as _bcb
from flatwhite.dashboard import skill_runner as _skill_runner
from flatwhite.dashboard.state import (
    load_topic_archive_state,
    set_topic_archived,
    load_pairing_overrides,
    save_pairing_override,
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

    FW cannot call the Claude `big-conversation` skill itself - there is no
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


# ── Run skills headless from the dashboard (no separate Claude session) ───────
# The dashboard launches the REAL skill via `claude -p` in the Instagram DM
# screenshotter project, tracks it as a background job, and reads back the files
# the skill writes. See docs/superpowers/specs/2026-07-17-dashboard-runs-skills-
# headless.md. The claude CLI must be installed + logged in on this machine
# (local-first; degrades to the old handoff instruction if it isn't).

def _claude_bin() -> str:
    import shutil
    return shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")


def _claude_available() -> bool:
    return Path(_claude_bin()).exists()


# The skill run uses bypassPermissions: a headless agent that stops to ask about
# every file write and screenshot copy would just hang. This is a deliberate,
# documented escalation - it runs Victor's OWN trusted skill, cwd'd into his own
# Instagram output folder, only on an explicit button click. Originals are never
# moved (the skill copies, per its own contract).
def _skill_argv(prompt: str, add_dir: str) -> list[str]:
    return [_claude_bin(), "-p", prompt,
            "--permission-mode", "bypassPermissions",
            "--add-dir", add_dir]


@app.get("/api/big-conversation/topic/{topic}/run-status")
def api_big_conversation_run_status(topic: str) -> JSONResponse:
    """Is this topic currently being processed? Lets the UI reconnect to a run
    in progress after navigating away, instead of showing a blank Process button."""
    r = _skill_runner.get_active_by_key(f"bigconv:{topic}")
    return JSONResponse({"active": bool(r), "run_id": r["id"] if r else None,
                         "status": r["status"] if r else None})


@app.post("/api/skill-run/big-conversation/{topic}")
def api_run_big_conversation(topic: str) -> JSONResponse:
    """Run the big-conversation skill on a topic headless; return a run id to poll."""
    folder = _bcb.INSTAGRAM_OUTPUT_DIR / topic
    if not folder.is_dir():
        return JSONResponse({"error": f"Topic folder not found: {topic}"}, status_code=404)
    if not _claude_available():
        return JSONResponse(
            {"error": "Claude Code isn't installed on this machine, so the "
                      "dashboard can't run the skill. Run it in a Claude session "
                      "instead."}, status_code=503)
    out_dir = str(_bcb.INSTAGRAM_OUTPUT_DIR)
    prompt = (
        f'Use the big-conversation skill to process the topic "{topic}". '
        f'The topic folders are in the current directory ({out_dir}). Follow the '
        f'skill exactly from start to finish: build the deepdive fuel if missing, '
        f'draft THE BIG CONVERSATION in the house voice, select and map the '
        f'screenshots, and emit the output files (_{topic.replace(" ", "_")}'
        f'_BIG_CONVERSATION.md at the output root and the topic\'s '
        f'_BIG_CONVERSATION_assets folder). Do not ask me any questions; '
        f'complete the whole skill and finish.'
    )
    try:
        run_id, started = _skill_runner.start_run(
            "big-conversation", f"bigconv:{topic}",
            _skill_argv(prompt, out_dir), cwd=out_dir)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=429)
    return JSONResponse({"run_id": run_id, "started": started, "topic": topic})


@app.post("/api/skill-run/sort")
def api_run_screenshot_sort() -> JSONResponse:
    """Run the screenshot-sort skill on the freshly-scraped DM screenshots headless.

    Sorts the loose screenshots at the Instagram output root into the Big
    Conversation topic/tier folders and the Inside Track folder - the prerequisite
    for Big Conversation. Same headless engine as the Big Conversation run.
    """
    if not _claude_available():
        return JSONResponse(
            {"error": "Claude Code isn't installed on this machine, so the "
                      "dashboard can't run the sort. Run it in a Claude session "
                      "instead."}, status_code=503)
    out_dir = str(_bcb.INSTAGRAM_OUTPUT_DIR)
    prompt = (
        "Use the screenshot-sort skill to sort the freshly-scraped Instagram DM "
        f"screenshots sitting loose at the output root ({out_dir}, the current "
        "directory). Follow the skill exactly from start to finish: gather the new "
        "screenshots, classify them (fan out subagents for volume), verify the RED "
        "HOT picks verbatim, move each screenshot into its topic/tier or Inside "
        "Track folder, and write the _SORT_SESSION report. Do not ask me any "
        "questions; complete the whole sort and finish."
    )
    try:
        run_id, started = _skill_runner.start_run(
            "screenshot-sort", "sort", _skill_argv(prompt, out_dir), cwd=out_dir)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=429)
    return JSONResponse({"run_id": run_id, "started": started})


@app.get("/api/skill-run/{run_id}")
def api_skill_run_status(run_id: str) -> JSONResponse:
    """Poll a headless skill run's status."""
    r = _skill_runner.get_run(run_id)
    if not r:
        return JSONResponse({"error": "Unknown run"}, status_code=404)
    return JSONResponse({
        "id": r["id"], "kind": r["kind"], "status": r["status"],
        "error": r["error"], "output_tail": (r["output"] or "")[-1500:],
    })


# ── Per-section insert into the beehiiv edition draft ─────────────────────────
_FW_PUBLICATION_ID = "pub_6210ff81-d440-4e09-916d-42fe436f0d05"


def _parse_draft_id(output: str) -> str | None:
    """Pull the 'FW_DRAFT_ID: post_...' marker every insert run prints."""
    m = re.search(r"FW_DRAFT_ID:\s*(post_[0-9a-f-]+)", output or "")
    return m.group(1) if m else None


def _wip_draft_title(today: "_dt.date | None" = None) -> str:
    """The consistent name of this edition's work-in-progress beehiiv draft.

    Named by the Monday of the current week so it's obvious to the team which
    draft is live ("[WIP] Flat White - w/c 20 Jul") and, crucially, so the
    insert run can find the SAME draft every time by name and never duplicate
    twice. Plain hyphen, not an em dash (house rule), even on this internal label.
    """
    d = today or _dt.date.today()
    monday = d - _dt.timedelta(days=d.weekday())
    return f"[WIP] Flat White - w/c {monday.day} {monday.strftime('%b')}"


@app.post("/api/section/{section}/insert-beehiiv")
def api_insert_section_beehiiv(section: str) -> JSONResponse:
    """Insert one ready section into this edition's beehiiv WIP draft, headless.

    The draft is identified by a CONSISTENT NAME (_wip_draft_title). The run
    finds that draft by name and inserts; only if no draft with that name exists
    does it duplicate last week's edition and rename the copy to that name. So it
    is impossible to duplicate twice for one edition, and the team can see at a
    glance which draft is live. Re-inserting a section REPLACES its block.
    """
    if section not in _REAL_SEGMENT_HEADINGS:
        return JSONResponse({"error": f"Unknown section: {section}"}, status_code=400)
    if not _claude_available():
        return JSONResponse(
            {"error": "Claude Code isn't installed on this machine, so the "
                      "dashboard can't insert into beehiiv. Do it in a Claude "
                      "session instead."}, status_code=503)

    week_iso = get_current_week_iso()
    saved = load_all_section_outputs(week_iso).get(section) or {}
    text = (saved.get("output_text") or "").strip()
    if not text:
        return JSONResponse(
            {"error": "This section has no saved content yet. Generate and mark "
                      "it ready first."}, status_code=400)

    from flatwhite.assemble.beehiiv_format import md_to_editor_html
    heading = _REAL_SEGMENT_HEADINGS[section]
    body_html = md_to_editor_html(text)
    wip_title = _wip_draft_title()

    prompt = (
        f"Use the beehiiv MCP for the Flat White publication "
        f"({_FW_PUBLICATION_ID}). We build this week's edition in ONE draft named "
        f"exactly \"{wip_title}\".\n"
        f"STEP 1 - find or create that draft, do NOT create a second copy:\n"
        f"  - List the publication's draft posts and look for one titled EXACTLY "
        f"\"{wip_title}\".\n"
        f"  - If it already exists, use it as the target. Do NOT duplicate.\n"
        f"  - If and ONLY if none exists, duplicate the most recent PUBLISHED "
        f"edition into a new draft and set the new draft's title to EXACTLY "
        f"\"{wip_title}\".\n"
        f"Print one line exactly: FW_DRAFT_ID: <the target draft's post id>\n"
        f"STEP 2 - fill in the section, KEEPING ITS CARD. Read the draft with "
        f"get_post_content (format editor_html). Find the bordered section CARD "
        f"(the node-section block, class=\"node-section\") whose heading is "
        f"\"{heading}\". Do NOT delete or unwrap that card, and do NOT touch its "
        f"heading. INSIDE that same card, directly under the heading, place this "
        f"content:\n\n{body_html}\n\n"
        f"Keep the card's border and keep any images, buttons, sponsor content or "
        f"footer that are already inside the card. If the card already holds "
        f"editorial body content under the heading from an earlier insert (as "
        f"opposed to the original template furniture), REPLACE that old body "
        f"content with the new content above so nothing is duplicated. The final "
        f"card must look like every other section: bordered card, heading, then "
        f"this content underneath. Use edit_post_content. Change no other section. "
        f"Print INSERT_OK when done."
    )

    def _on_done(record):
        # Record which draft is current for this edition (the name is the real
        # guard; this is a convenience record for the dashboard).
        if record and record.get("status") == "done":
            new_id = _parse_draft_id(record.get("output", ""))
            if new_id:
                set_edition_draft(week_iso, new_id)

    argv = [_claude_bin(), "-p", prompt, "--permission-mode", "bypassPermissions"]
    try:
        run_id, started = _skill_runner.start_run(
            "beehiiv-insert", f"insert:{week_iso}:{section}", argv,
            cwd=str(Path.cwd()), on_complete=_on_done,
            # beehiiv is a claude.ai connector that doesn't always attach to a
            # background run. Require the run to actually print INSERT_OK;
            # otherwise it's a failure, not a silent "done".
            success_marker="INSERT_OK",
            marker_fail_error=(
                "Couldn't insert into beehiiv from the dashboard: the beehiiv "
                "connection wasn't available to this background run (it's a "
                "claude.ai connector that doesn't always attach). The section is "
                "ready. Ask Claude to insert this section for you, or try again."))
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=429)
    return JSONResponse({"run_id": run_id, "started": started, "section": section})


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
