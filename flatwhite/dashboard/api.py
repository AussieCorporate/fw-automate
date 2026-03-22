"""Flat White editor dashboard — FastAPI backend.

Wraps the existing state.py DB functions as HTTP endpoints.
Serves the static frontend from dashboard/static/.
LLM-calling endpoints are gated behind POST requests.

Run:
    python -m uvicorn flatwhite.dashboard.api:app --port 8500 --reload
    OR via CLI: flatwhite review
"""

from __future__ import annotations

import hashlib
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
    load_curated_items_by_section,
    load_top_thread,
    load_top_threads,
    load_seed_items,
    save_editor_decision,
    save_big_conversation_draft,
    save_thread_our_take,
    load_saved_draft,
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
        _step("youtube_transcripts", lambda: __import__("flatwhite.editorial.youtube_transcripts", fromlist=["pull_youtube_transcripts"]).pull_youtube_transcripts())

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


@app.get("/api/run-log")
def api_run_log() -> JSONResponse:
    """Return the last 100 lines of the cron run log."""
    log_path = Path(__file__).parent.parent.parent / "data" / "logs" / "cron.log"
    if not log_path.exists():
        return JSONResponse({"lines": [], "exists": False})
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return JSONResponse({"lines": lines[-100:], "exists": True})


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
