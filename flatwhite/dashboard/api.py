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

from flatwhite.db import init_db, get_connection, get_current_week_iso
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
)

_STATIC_DIR = Path(__file__).parent / "static"
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
    """Serve the single-page frontend."""
    return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")


# ── READ endpoints (GET) ────────────────────────────────────────────────────

@app.get("/api/pulse")
def api_pulse() -> JSONResponse:
    """Return pulse state + signals for current week."""
    pulse = load_pulse_state()
    signals = load_signals_this_week()
    anomalies = detect_all_anomalies()
    return JSONResponse({
        "pulse": pulse,
        "signals": signals,
        "anomalies": anomalies,
        "week_iso": get_current_week_iso(),
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
    return JSONResponse({"items": items, "week_iso": get_current_week_iso()})


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
    return JSONResponse({"threads": threads, "week_iso": get_current_week_iso()})


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
    return JSONResponse({
        "candidates": candidates,
        "picks": picks,
        "week_iso": get_current_week_iso(),
    })


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


@app.get("/api/events")
def api_events() -> JSONResponse:
    """Return events for current week."""
    conn = get_connection()
    week_iso = get_current_week_iso()
    rows = conn.execute(
        "SELECT * FROM events WHERE week_iso = ? ORDER BY sort_order, event_date",
        (week_iso,),
    ).fetchall()
    conn.close()
    return JSONResponse({"events": [dict(r) for r in rows], "week_iso": week_iso})


@app.post("/api/events")
async def api_add_event(request: Request) -> JSONResponse:
    """Add an event."""
    body = await request.json()
    week_iso = get_current_week_iso()
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO events (week_iso, event_date, title, location, time_range, price, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (week_iso, body.get("event_date", ""), body.get("title", ""), body.get("location"),
         body.get("time_range"), body.get("price"), body.get("description")),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return JSONResponse({"id": row_id})


@app.delete("/api/events/{event_id}")
async def api_delete_event(event_id: int) -> JSONResponse:
    """Delete an event."""
    conn = get_connection()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"deleted": True})


@app.get("/api/amp-finest")
def api_amp_finest() -> JSONResponse:
    """Return AMP's Finest data for current week."""
    conn = get_connection()
    week_iso = get_current_week_iso()
    row = conn.execute("SELECT * FROM amp_finest WHERE week_iso = ?", (week_iso,)).fetchone()
    conn.close()
    return JSONResponse({"data": dict(row) if row else None, "week_iso": week_iso})


@app.post("/api/amp-finest")
async def api_save_amp_finest(request: Request) -> JSONResponse:
    """Save AMP's Finest data."""
    body = await request.json()
    week_iso = get_current_week_iso()
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO amp_finest (week_iso, data_description, notes, chart_image_path)
        VALUES (?, ?, ?, ?)""",
        (week_iso, body.get("data_description", ""), body.get("notes", ""), body.get("chart_image_path")),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"saved": True})


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
        ORDER BY (ci.score_relevance * 0.3 + ci.score_tension * 0.4 + ci.score_novelty * 0.3) DESC
        LIMIT 5""",
        (week_iso,),
    ).fetchall()
    conn.close()

    return JSONResponse({"candidates": [dict(r) for r in rows], "week_iso": week_iso})


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
        _step("salary_pressure", lambda: __import__("flatwhite.signals.salary_pressure", fromlist=["pull_salary_pressure"]).pull_salary_pressure())
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
        ("Salary pressure",     lambda: __import__("flatwhite.signals.salary_pressure", fromlist=["pull_salary_pressure"]).pull_salary_pressure()),
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
    ],
    "classify": [
        ("Classify items", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "finds": [
        ("Reddit RSS",    lambda: __import__("flatwhite.editorial.reddit_rss",            fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News",   lambda: __import__("flatwhite.editorial.google_news_editorial", fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("RSS feeds",     lambda: __import__("flatwhite.editorial.rss_feeds",             fromlist=["pull_rss_feeds"]).pull_rss_feeds()),
        ("Podcast feeds", lambda: __import__("flatwhite.editorial.podcast_feeds",         fromlist=["pull_podcast_feeds"]).pull_podcast_feeds()),
        ("Classify",      lambda: __import__("flatwhite.classify.classifier",             fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "lobby": [
        ("Employer snapshots", lambda: __import__("flatwhite.signals.hiring_pulse", fromlist=["pull_hiring_pulse"]).pull_hiring_pulse()),
    ],
    "thread": [
        ("Reddit RSS", lambda: __import__("flatwhite.editorial.reddit_rss",    fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Classify",   lambda: __import__("flatwhite.classify.classifier",     fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
    "off_the_clock": [
        ("Off the Clock", lambda: __import__("flatwhite.editorial.off_the_clock", fromlist=["pull_off_the_clock"]).pull_off_the_clock()),
        ("Classify OTC",  lambda: __import__("flatwhite.classify.classifier",     fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified()),
    ],
    "classify_otc": [
        ("Classify OTC", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified()),
    ],
}


def _run_section_background(section: str) -> None:
    """Run a section's steps sequentially, updating _section_state after each step.

    `step` is the 0-based index of the step currently running (not the count of completed steps).
    On completion, step == total (sentinel for "all done"). Frontend should render step/total as
    "N of M" by treating step as "currently on step N+1" while running, and "all done" when step==total.
    """
    steps = _SECTION_RUNNERS[section]
    total = len(steps)
    try:
        for i, (label, fn) in enumerate(steps):
            _section_state[section].update({"step": i, "total": total, "step_name": label})
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


# ── Lobby (employer hiring trends) ──────────────────────────────────────────

@app.get("/api/lobby")
def api_lobby() -> JSONResponse:
    """Return employer hiring data with 8-week trend history."""
    conn = get_connection()
    week_iso = get_current_week_iso()

    # Build last 8 ISO weeks (oldest first, current last)
    year, week_num = int(week_iso[:4]), int(week_iso[6:])
    dt = _dt.datetime.strptime(f"{year}-W{week_num:02d}-1", "%G-W%V-%u")
    week_isos = [(dt - _dt.timedelta(weeks=i)).strftime("%G-W%V") for i in range(7, -1, -1)]
    # week_isos[0] = 8 weeks ago, week_isos[-1] = current
    prev_week = week_isos[-2]
    month_ago_week = week_isos[-5]  # 4 weeks ago

    placeholders = ",".join("?" for _ in week_isos)
    all_snaps = conn.execute(
        f"""SELECT es.employer_id, es.open_roles_count, es.week_iso,
                   ew.employer_name, ew.sector
            FROM employer_snapshots es
            JOIN employer_watchlist ew ON es.employer_id = ew.id
            WHERE es.week_iso IN ({placeholders})
            ORDER BY ew.employer_name, es.week_iso""",
        week_isos,
    ).fetchall()
    conn.close()

    # Group by employer
    from collections import defaultdict
    snap_by_emp: dict[int, dict] = defaultdict(lambda: {"name": "", "sector": "", "weeks": {}})
    for r in all_snaps:
        e = snap_by_emp[r["employer_id"]]
        e["name"] = r["employer_name"]
        e["sector"] = r["sector"]
        e["weeks"][r["week_iso"]] = r["open_roles_count"]

    employers = []
    for emp_id, emp in snap_by_emp.items():
        weeks = emp["weeks"]
        current_count = weeks.get(week_iso)
        if current_count is None:
            continue  # No data this week — skip

        prev_count = weeks.get(prev_week)
        month_ago_count = weeks.get(month_ago_week)

        wow_delta = current_count - prev_count if prev_count is not None else None
        mom_delta = current_count - month_ago_count if month_ago_count is not None else None
        wow_pct = round(wow_delta / prev_count * 100, 1) if prev_count and wow_delta is not None else None

        # History: last 6 weeks of counts (oldest first), None-filled if missing
        history_weeks = week_isos[-6:]
        history = [weeks.get(w) for w in history_weeks]

        employers.append({
            "employer_id": emp_id,
            "employer_name": emp["name"],
            "sector": emp["sector"],
            "open_roles_count": current_count,
            "prev_roles": prev_count,
            "delta": wow_delta,
            "delta_pct": wow_pct,
            "mom_delta": mom_delta,
            "history": history,
        })

    employers.sort(key=lambda e: e["employer_name"])

    movers = sorted(
        [e for e in employers if e["delta"] is not None],
        key=lambda x: abs(x["delta"]),
        reverse=True,
    )

    return JSONResponse({
        "employers": employers,
        "top_movers": movers[:10],
        "week_iso": week_iso,
    })


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
    return JSONResponse({
        "candidates": candidates,
        "picks": picks,
        "week_iso": get_current_week_iso(),
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


# ── Events ────────────────────────────────────────────────────────────────────

@app.get("/api/events")
def api_events() -> JSONResponse:
    """Return events for current week."""
    conn = get_connection()
    week_iso = get_current_week_iso()
    rows = conn.execute(
        "SELECT * FROM events WHERE week_iso = ? ORDER BY sort_order, event_date",
        (week_iso,),
    ).fetchall()
    conn.close()
    return JSONResponse({"events": [dict(r) for r in rows], "week_iso": week_iso})


@app.post("/api/events")
async def api_add_event(request: Request) -> JSONResponse:
    """Add an event."""
    body = await request.json()
    week_iso = get_current_week_iso()
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO events (week_iso, event_date, title, location, time_range, price, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (week_iso, body.get("event_date", ""), body.get("title", ""), body.get("location"),
         body.get("time_range"), body.get("price"), body.get("description")),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return JSONResponse({"id": row_id})


@app.delete("/api/events/{event_id}")
async def api_delete_event(event_id: int) -> JSONResponse:
    """Delete an event."""
    conn = get_connection()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"deleted": True})


# ── AMP's Finest ──────────────────────────────────────────────────────────────

@app.get("/api/amp-finest")
def api_amp_finest() -> JSONResponse:
    """Return AMP's Finest data for current week."""
    conn = get_connection()
    week_iso = get_current_week_iso()
    row = conn.execute("SELECT * FROM amp_finest WHERE week_iso = ?", (week_iso,)).fetchone()
    conn.close()
    return JSONResponse({"data": dict(row) if row else None, "week_iso": week_iso})


@app.post("/api/amp-finest")
async def api_save_amp_finest(request: Request) -> JSONResponse:
    """Save AMP's Finest data."""
    body = await request.json()
    week_iso = get_current_week_iso()
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO amp_finest (week_iso, data_description, notes, chart_image_path)
        VALUES (?, ?, ?, ?)""",
        (week_iso, body.get("data_description", ""), body.get("notes", ""), body.get("chart_image_path")),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"saved": True})


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
        ORDER BY (ci.score_relevance * 0.3 + ci.score_tension * 0.4 + ci.score_novelty * 0.3) DESC
        LIMIT 5""",
        (week_iso,),
    ).fetchall()
    conn.close()

    return JSONResponse({"candidates": [dict(r) for r in rows], "week_iso": week_iso})


# ── Section proceed helpers ──────────────────────────────────────────────────

def _proceed_pulse(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import PULSE_SUMMARY_SYSTEM, PULSE_SUMMARY_PROMPT
    from flatwhite.dashboard.state import load_pulse_state, load_signals_this_week
    from flatwhite.db import get_interactions
    from flatwhite.signals.macro_context import fetch_macro_headlines

    if custom_prompt:
        return route(task_type="summary", prompt=custom_prompt, system=PULSE_SUMMARY_SYSTEM)

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

    signal_lines = []
    for s in signals:
        name = s["signal_name"]
        score = round(s["normalised_score"], 1)
        prev = prev_map.get(name)
        if prev is not None:
            delta = round(score - prev, 1)
            signal_lines.append(f"{name}: {score} (prev: {round(prev, 1)}, Δ: {delta:+.1f})")
        else:
            signal_lines.append(f"{name}: {score}")

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

    prompt = PULSE_SUMMARY_PROMPT.format(
        smoothed=f"{pulse['smoothed_score']:.0f}" if pulse else "50",
        direction=pulse["direction"] if pulse else "stable",
        prev_smoothed=f"{pulse.get('smoothed_score', 50):.0f}" if pulse else "50",
        drivers="\n".join(signal_lines[:10]),
        interactions_block=interactions_block,
        macro_context=macro_context,
    )
    return route(task_type="summary", prompt=prompt, system=PULSE_SUMMARY_SYSTEM)


def _proceed_big_conversation(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE, BIG_CONVERSATION_DRAFT_SYSTEM, BIG_CONVERSATION_DRAFT_PROMPT

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE)

    headline = data.get("headline", "")
    pitch = data.get("pitch", "")
    supporting_summaries = data.get("supporting_summaries", [])
    items_block = "\n".join(f"- {s}" for s in supporting_summaries) if supporting_summaries else "(no supporting items)"

    prompt = BIG_CONVERSATION_DRAFT_PROMPT.format(
        headline=headline,
        pitch=pitch,
        supporting_items=items_block,
    )
    return route(task_type="editorial", prompt=prompt, system=BIG_CONVERSATION_DRAFT_SYSTEM)


def _proceed_finds(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE)

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
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE)


def _proceed_thread(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import THREAD_OUR_TAKE_SYSTEM, THREAD_OUR_TAKE_PROMPT

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=THREAD_OUR_TAKE_SYSTEM)

    title = data.get("title", "")
    body = data.get("body", data.get("summary", ""))
    top_comments = data.get("top_comments", [])
    comments_block = "\n".join(f"- {c}" for c in top_comments[:5]) if top_comments else "(no comments)"
    editorial_frame = data.get("editorial_frame", "")

    prompt = THREAD_OUR_TAKE_PROMPT.format(
        title=title,
        body=body,
        top_comments=comments_block,
        editorial_frame=editorial_frame,
    )
    return route(task_type="editorial", prompt=prompt, system=THREAD_OUR_TAKE_SYSTEM)


def _proceed_amp_finest(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE)

    items = data.get("selected_items", [])
    items_block = "\n\n".join(
        f"Title: {item.get('title', '')}\nSummary: {item.get('summary', '')}"
        for item in items
    )

    prompt = (
        "Write the AMP's Finest section for this week's Flat White newsletter.\n\n"
        f"Selected items:\n{items_block}\n\n"
        "Curate these into a short, pointed section. Voice: dry Australian corporate sardony. "
        "Each item gets one punchy sentence. Output ONLY the commentary. No title. No sign-off."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE)


def _proceed_off_the_clock(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE)

    picks = data.get("picks", [])
    picks_block = "\n\n".join(
        f"Category: {p.get('category', '')}\nTitle: {p.get('title', '')}\nDraft blurb: {p.get('blurb', '')}"
        for p in picks
    )

    prompt = (
        "Polish these Off the Clock blurbs for Flat White.\n\n"
        f"{picks_block}\n\n"
        "For each, rewrite the blurb in 1-2 sentences. Voice: dry, specific, opinionated. "
        "Not a review. A statement from someone who already knows. Australian English.\n\n"
        "Output as: CATEGORY: BLURB (one per line)"
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE)


def _proceed_editorial(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE)

    items = data.get("selected_items", [])
    items_block = "\n\n".join(
        f"Title: {item.get('title', '')}\nSummary: {item.get('summary', '')}"
        for item in items
    )

    prompt = (
        "Write the editorial section for this week's Flat White newsletter.\n\n"
        f"Selected items:\n{items_block}\n\n"
        "Voice: dry, specific, opinionated. Australian corporate commentary. "
        "Output ONLY the editorial text. No title. No sign-off."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE)


def _proceed_lobby(data: dict, model: str | None, custom_prompt: str | None = None) -> str:
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    if custom_prompt:
        return route(task_type="editorial", prompt=custom_prompt, system=EDITORIAL_VOICE)

    selected = data.get("selected_employers", [])
    employer_lines = []
    for e in selected:
        name = e.get("employer_name", str(e)) if isinstance(e, dict) else str(e)
        if isinstance(e, dict):
            current = e.get("open_roles_count", "?")
            wow = e.get("delta")
            mom = e.get("mom_delta")
            wow_str = f"+{wow}" if wow and wow > 0 else str(wow) if wow is not None else "—"
            mom_str = f"+{mom}" if mom and mom > 0 else str(mom) if mom is not None else "—"
            employer_lines.append(f"- {name}: {current} roles (WoW: {wow_str}, MoM: {mom_str})")
        else:
            employer_lines.append(f"- {name}")

    employer_block = "\n".join(employer_lines) if employer_lines else "No employers selected."

    prompt = (
        "Write The Lobby section for this week's Flat White newsletter.\n\n"
        f"Employer hiring movements this week:\n{employer_block}\n\n"
        "Analyse these hiring movements. What do they signal about the corporate job market? "
        "Are companies restructuring, expanding, or pulling back? Identify employers with "
        "sustained trends (same direction for multiple weeks) vs one-week anomalies. "
        "Connect the dots for someone working in Big 4, law, banking, or tech.\n\n"
        "Output ONLY the commentary text. No title. No sign-off."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE)


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
        "thread": _proceed_thread,
        "amp_finest": _proceed_amp_finest,
        "off_the_clock": _proceed_off_the_clock,
        "editorial": _proceed_editorial,
        "lobby": _proceed_lobby,
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
        return JSONResponse({"section": section, "output": output, "model": model, "week_iso": week_iso})
    except Exception as e:
        return JSONResponse({"section": section, "error": str(e)}, status_code=500)


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
            selected_signals = data.get("selected_signals", [s["signal_name"] for s in signals])
            signal_lines = []
            for s in signals:
                if s["signal_name"] in selected_signals:
                    name = s["signal_name"]
                    score = round(s["normalised_score"], 1)
                    prev = prev_map.get(name)
                    if prev is not None:
                        delta = round(score - prev, 1)
                        signal_lines.append(f"{name}: {score} (prev: {round(prev,1)}, Δ: {delta:+.1f})")
                    else:
                        signal_lines.append(f"{name}: {score}")

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

            prompt = PULSE_SUMMARY_PROMPT.format(
                smoothed=f"{pulse['smoothed_score']:.0f}" if pulse else "50",
                direction=pulse["direction"] if pulse else "stable",
                prev_smoothed=f"{pulse.get('smoothed_score', 50):.0f}" if pulse else "50",
                drivers="\n".join(signal_lines[:10]),
                interactions_block=interactions_block,
                macro_context=macro_context,
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

        elif section == "lobby":
            selected = data.get("selected_employers", [])
            employer_lines = []
            for e in selected:
                name = e.get("employer_name", str(e)) if isinstance(e, dict) else str(e)
                if isinstance(e, dict):
                    current = e.get("open_roles_count", "?")
                    wow = e.get("delta")
                    mom = e.get("mom_delta")
                    wow_str = f"+{wow}" if wow and wow > 0 else str(wow) if wow is not None else "—"
                    mom_str = f"+{mom}" if mom and mom > 0 else str(mom) if mom is not None else "—"
                    employer_lines.append(f"- {name}: {current} roles (WoW: {wow_str}, MoM: {mom_str})")
                else:
                    employer_lines.append(f"- {name}")
            employer_block = "\n".join(employer_lines) if employer_lines else "No employers selected."
            prompt = (
                "Write The Lobby section for this week's Flat White newsletter.\n\n"
                f"Employer hiring movements this week:\n{employer_block}\n\n"
                "Analyse these hiring movements. What do they signal about the corporate job market? "
                "Are companies restructuring, expanding, or pulling back? Identify employers with "
                "sustained trends (same direction for multiple weeks) vs one-week anomalies. "
                "Connect the dots for someone working in Big 4, law, banking, or tech.\n\n"
                "Output ONLY the commentary text. No title. No sign-off."
            )
            context_breakdown = {
                "signals": [], "signal_intelligence": [],
                "composite": {},
                "items": [{"name": line} for line in employer_lines],
            }

        elif section == "off_the_clock":
            picks = data.get("picks", [])
            picks_block = "\n\n".join(
                f"Category: {p.get('category', '')}\nTitle: {p.get('title', '')}\nDraft blurb: {p.get('blurb', '')}"
                for p in picks
            )
            prompt = (
                "Polish these Off the Clock blurbs for Flat White.\n\n"
                f"{picks_block}\n\n"
                "For each, rewrite the blurb in 1-2 sentences. Voice: dry, specific, opinionated. "
                "Not a review. A statement from someone who already knows. Australian English.\n\n"
                "Output as: CATEGORY: BLURB (one per line)"
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
