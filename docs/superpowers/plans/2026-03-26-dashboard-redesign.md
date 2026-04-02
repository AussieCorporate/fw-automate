# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pipeline-oriented dashboard with a newsletter-section-oriented dashboard where each section (Pulse, Big Conversation, Finds, etc.) has its own self-contained RUN → SELECT → PROCEED workflow with per-section model selection.

**Architecture:** Backend keeps all existing signal/editorial/classifier code. model_router.py gains Claude Sonnet support + model override. New `section_outputs`, `events`, `amp_finest` tables. New generic `/api/proceed-section` endpoint. Frontend is a complete rewrite of index.html — same single-file vanilla JS/CSS approach, but organised around newsletter sections instead of pipeline stages.

**Tech Stack:** Python, SQLite, FastAPI, Anthropic SDK (already installed v0.57.1), google-generativeai (already installed v0.8.5), vanilla HTML/JS/CSS

---

## File Structure

```
flatwhite/
  model_router.py              — MODIFY: add Claude support, model override, list_models()
  db.py                        — MODIFY: add events, amp_finest, section_outputs tables + migrations
  dashboard/
    api.py                     — MODIFY: add new endpoints, rewrite run-section, add proceed-section
    state.py                   — MODIFY: add section_outputs, events, amp_finest state functions
    static/
      index.html               — REWRITE: complete frontend rewrite (newsletter-section layout)
```

No new files created. All changes are modifications to existing files. The frontend rewrite replaces index.html entirely.

---

### Task 1: Model Router — Add Claude Support + Model Override

**Files:**
- Modify: `flatwhite/model_router.py`

- [ ] **Step 1: Rewrite model_router.py with multi-model support**

Replace the entire contents of `flatwhite/model_router.py` with:

```python
from __future__ import annotations

"""Model router for Flat White LLM calls.

Supports Gemini 2.5 Flash and Claude Sonnet/Haiku. Each model is called
via its respective SDK. The route() function accepts an optional model_override
to let the dashboard user pick which model to use per section.
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

TEMPERATURE_BY_TASK: dict[str, float] = {
    "classification": 0.1,
    "scoring": 0.1,
    "tagging": 0.1,
    "anomaly_summary": 0.2,
    "editorial": 0.3,
    "summary": 0.3,
    "hook": 0.7,
    "big_conversation": 0.3,
}

# Default model per task type — classification uses cheap/fast Gemini,
# editorial voice tasks use Claude Sonnet for better writing quality.
DEFAULT_MODEL_BY_TASK: dict[str, str] = {
    "classification": "gemini-2.5-flash",
    "scoring": "gemini-2.5-flash",
    "tagging": "gemini-2.5-flash",
    "anomaly_summary": "gemini-2.5-flash",
    "editorial": "claude-sonnet-4-6",
    "summary": "claude-sonnet-4-6",
    "hook": "claude-sonnet-4-6",
    "big_conversation": "claude-sonnet-4-6",
}

# All supported models and their providers
MODEL_REGISTRY: dict[str, dict] = {
    "gemini-2.5-flash": {"provider": "gemini", "label": "Gemini 2.5 Flash", "env_key": "GEMINI_API_KEY"},
    "claude-sonnet-4-6": {"provider": "anthropic", "label": "Claude Sonnet 4.6", "env_key": "ANTHROPIC_API_KEY"},
    "claude-haiku-4-5": {"provider": "anthropic", "label": "Claude Haiku 4.5", "env_key": "ANTHROPIC_API_KEY"},
}


def list_available_models() -> list[dict]:
    """Return models that have API keys configured."""
    available = []
    for model_id, info in MODEL_REGISTRY.items():
        if os.getenv(info["env_key"]):
            available.append({"id": model_id, "label": info["label"], "provider": info["provider"]})
    return available


def _call_gemini(prompt: str, system: str, temperature: float) -> str:
    """Call Gemini 2.5 Flash. Supports both google-genai and google-generativeai SDKs."""
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system if system else None,
                temperature=temperature,
            ),
        )
        return response.text
    except ImportError:
        pass

    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=system if system else None,
    )
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(temperature=temperature),
    )
    return response.text


def _call_claude(model_id: str, prompt: str, system: str, temperature: float) -> str:
    """Call Claude via Anthropic SDK."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    messages = [{"role": "user", "content": prompt}]
    response = client.messages.create(
        model=model_id,
        max_tokens=4096,
        system=system if system else "",
        messages=messages,
        temperature=temperature,
    )
    return response.content[0].text


def _call_model(model_id: str, prompt: str, system: str, temperature: float) -> str:
    """Dispatch to the right provider based on model_id."""
    info = MODEL_REGISTRY.get(model_id)
    if not info:
        raise ValueError(f"Unknown model: {model_id}")

    api_key = os.getenv(info["env_key"])
    if not api_key:
        raise ValueError(f"No API key configured for {model_id} (set {info['env_key']})")

    if info["provider"] == "gemini":
        return _call_gemini(prompt, system, temperature)
    elif info["provider"] == "anthropic":
        return _call_claude(model_id, prompt, system, temperature)
    else:
        raise ValueError(f"Unknown provider: {info['provider']}")


def route(task_type: str, prompt: str, system: str = "", model_override: str | None = None) -> str:
    """Route an LLM task. Uses model_override if provided, otherwise default for task_type.

    Retries once on failure with 2s backoff.
    """
    if task_type not in TEMPERATURE_BY_TASK:
        raise ValueError(
            f"Unknown task_type: {task_type}. Must be one of: "
            f"{', '.join(TEMPERATURE_BY_TASK.keys())}."
        )

    temperature = TEMPERATURE_BY_TASK[task_type]
    model_id = model_override or DEFAULT_MODEL_BY_TASK.get(task_type, "gemini-2.5-flash")

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _call_model(model_id, prompt, system, temperature)
        except Exception as e:
            last_error = e
            if attempt == 0:
                print(f"LLM call failed ({model_id}: {e}), retrying in 2s...")
                time.sleep(2.0)

    raise last_error


# Backwards compatibility — existing code calls call_gemini_flash() directly
def call_gemini_flash(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """Legacy wrapper. Calls Gemini 2.5 Flash with retry."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _call_gemini(prompt, system, temperature)
        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(2.0)
    raise last_error
```

- [ ] **Step 2: Verify model router works**

```bash
python -c "
from flatwhite.model_router import list_available_models, route
models = list_available_models()
for m in models:
    print(f'{m[\"id\"]}: {m[\"label\"]} ({m[\"provider\"]})')
print(f'{len(models)} models available')
"
```

Expected: Lists available models based on which API keys are in .env

- [ ] **Step 3: Commit**

```bash
git add flatwhite/model_router.py
git commit -m "feat(model_router): add Claude support, model override, list_available_models"
```

---

### Task 2: Database — New Tables + Migrations

**Files:**
- Modify: `flatwhite/db.py`

- [ ] **Step 1: Add new tables to SCHEMA_SQL**

Add these CREATE TABLE statements to the end of the SCHEMA_SQL string in `flatwhite/db.py`, before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS section_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    section TEXT NOT NULL,
    output_text TEXT NOT NULL,
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_iso, section)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    event_date TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    time_range TEXT,
    price TEXT,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS amp_finest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    chart_image_path TEXT,
    data_description TEXT,
    notes TEXT,
    generated_commentary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_iso)
);
```

- [ ] **Step 2: Add helper functions for new tables**

Add to `flatwhite/db.py` after the existing helper functions:

```python
def save_section_output(week_iso: str, section: str, output_text: str, model_used: str | None = None) -> int:
    """Save or update generated output for a newsletter section."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR REPLACE INTO section_outputs
        (week_iso, section, output_text, model_used, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))""",
        (week_iso, section, output_text, model_used),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def load_section_output(week_iso: str, section: str) -> dict | None:
    """Load saved output for a newsletter section."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM section_outputs WHERE week_iso = ? AND section = ?",
        (week_iso, section),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def load_all_section_outputs(week_iso: str) -> dict[str, dict]:
    """Load all saved outputs for a week, keyed by section name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM section_outputs WHERE week_iso = ?",
        (week_iso,),
    ).fetchall()
    conn.close()
    return {r["section"]: dict(r) for r in rows}
```

- [ ] **Step 3: Test migration**

```bash
python -c "from flatwhite.db import init_db; init_db(); print('OK')"
python -c "
from flatwhite.db import save_section_output, load_section_output, get_current_week_iso
w = get_current_week_iso()
save_section_output(w, 'pulse', 'Test output', 'gemini-2.5-flash')
r = load_section_output(w, 'pulse')
print(f'Section: {r[\"section\"]}, Model: {r[\"model_used\"]}')
# Clean up
from flatwhite.db import get_connection
conn = get_connection()
conn.execute('DELETE FROM section_outputs WHERE output_text = ?', ('Test output',))
conn.commit()
conn.close()
print('DB OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add flatwhite/db.py
git commit -m "feat(db): add section_outputs, events, amp_finest tables"
```

---

### Task 3: API — New Endpoints

**Files:**
- Modify: `flatwhite/dashboard/api.py`

- [ ] **Step 1: Add /api/models endpoint**

```python
@app.get("/api/models")
def api_models() -> JSONResponse:
    """Return available LLM models based on configured API keys."""
    from flatwhite.model_router import list_available_models
    return JSONResponse({"models": list_available_models()})
```

- [ ] **Step 2: Add /api/proceed-section endpoint**

This is the generic "generate output" endpoint. Each section sends its selected data + model choice, and this endpoint dispatches to the right generation function.

```python
@app.post("/api/proceed-section")
async def api_proceed_section(request: Request) -> JSONResponse:
    """Generate output for a newsletter section.

    Body: {
        "section": str,
        "model": str (optional, model_id override),
        "data": dict (section-specific payload)
    }
    """
    from flatwhite.model_router import route
    from flatwhite.db import save_section_output

    body = await request.json()
    section = body.get("section", "")
    model = body.get("model") or None
    data = body.get("data", {})
    week_iso = get_current_week_iso()

    try:
        if section == "pulse":
            output = _proceed_pulse(data, model)
        elif section == "big_conversation":
            output = _proceed_big_conversation(data, model)
        elif section == "lobby":
            output = _proceed_lobby(data, model)
        elif section == "finds":
            output = _proceed_finds(data, model)
        elif section == "thread":
            output = _proceed_thread(data, model)
        elif section == "amp_finest":
            output = _proceed_amp_finest(data, model)
        elif section == "off_the_clock":
            output = _proceed_off_the_clock(data, model)
        elif section == "editorial":
            output = _proceed_editorial(data, model)
        else:
            return JSONResponse({"error": f"Unknown section: {section}"}, status_code=400)

        save_section_output(week_iso, section, output, model)
        return JSONResponse({"section": section, "output": output, "model": model, "week_iso": week_iso})
    except Exception as e:
        return JSONResponse({"section": section, "error": str(e)}, status_code=500)
```

- [ ] **Step 3: Add section proceed helper functions**

Add these helper functions in `api.py` (above the proceed-section endpoint):

```python
def _proceed_pulse(data: dict, model: str | None) -> str:
    """Generate Pulse narrative from selected signals."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import PULSE_SUMMARY_SYSTEM, PULSE_SUMMARY_PROMPT
    from flatwhite.dashboard.state import load_pulse_state, load_signals_this_week

    pulse = load_pulse_state()
    signals = load_signals_this_week()
    selected_signals = data.get("selected_signals", [])

    # Build signal summary for selected signals
    signal_lines = []
    for s in signals:
        if s["signal_name"] in selected_signals or not selected_signals:
            signal_lines.append(f"{s['signal_name']}: {s['normalised_score']:.0f}/100")

    interactions = data.get("interactions", [])
    interactions_block = ""
    if interactions:
        interactions_block = "\nSignal interactions detected:\n" + "\n".join(f"- {ix}" for ix in interactions) + "\n"

    prompt = PULSE_SUMMARY_PROMPT.format(
        smoothed=f"{pulse['smoothed_score']:.0f}" if pulse else "50",
        direction=pulse["direction"] if pulse else "stable",
        prev_smoothed=f"{pulse.get('smoothed_score', 50):.0f}" if pulse else "50",
        drivers=", ".join(signal_lines[:5]),
        interactions_block=interactions_block,
        macro_context=data.get("macro_context", ""),
    )

    return route(task_type="summary", prompt=prompt, system=PULSE_SUMMARY_SYSTEM, model_override=model)


def _proceed_big_conversation(data: dict, model: str | None) -> str:
    """Generate Big Conversation editorial from selected topic."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import BIG_CONVERSATION_DRAFT_SYSTEM, BIG_CONVERSATION_DRAFT_PROMPT

    prompt = BIG_CONVERSATION_DRAFT_PROMPT.format(
        headline=data.get("headline", ""),
        pitch=data.get("pitch", ""),
        supporting_items=data.get("supporting_items", "No supporting data provided."),
    )
    return route(task_type="big_conversation", prompt=prompt, system=BIG_CONVERSATION_DRAFT_SYSTEM, model_override=model)


def _proceed_lobby(data: dict, model: str | None) -> str:
    """Generate The Lobby narrative from selected employers."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    selected = data.get("selected_employers", [])
    employer_lines = "\n".join(f"- {e}" for e in selected) if selected else "No employers selected."

    prompt = (
        "Write The Lobby section for this week's Flat White newsletter.\n\n"
        f"Selected employer movements:\n{employer_lines}\n\n"
        "Write 2-3 paragraphs analysing these hiring movements. What do they signal about "
        "the corporate job market? Are companies restructuring, expanding, or pulling back? "
        "Connect the dots for someone working in Big 4, law, banking, or tech.\n\n"
        "Output ONLY the commentary text. No title. No sign-off."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=model)


def _proceed_finds(data: dict, model: str | None) -> str:
    """Generate Finds write-ups for selected items."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

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
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=model)


def _proceed_thread(data: dict, model: str | None) -> str:
    """Generate Thread of the Week write-up."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import THREAD_OUR_TAKE_SYSTEM, THREAD_OUR_TAKE_PROMPT

    prompt = THREAD_OUR_TAKE_PROMPT.format(
        title=data.get("title", ""),
        body=data.get("body", ""),
        top_comments=data.get("top_comments", ""),
        editorial_frame=data.get("editorial_frame", ""),
    )
    return route(task_type="editorial", prompt=prompt, system=THREAD_OUR_TAKE_SYSTEM, model_override=model)


def _proceed_amp_finest(data: dict, model: str | None) -> str:
    """Generate AMP's Finest commentary from provided data."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

    prompt = (
        "Write the AMP's Finest section for this week's Flat White newsletter.\n\n"
        f"Data/Chart description: {data.get('data_description', '')}\n"
        f"Notes: {data.get('notes', '')}\n\n"
        "Write 2-3 paragraphs of editorial commentary around this data. Explain what the data "
        "shows, what it means for the audience (corporate professionals in Australia), and one "
        "insight they wouldn't get from just looking at the chart.\n\n"
        "Output ONLY the commentary text. No title. No sign-off."
    )
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=model)


def _proceed_off_the_clock(data: dict, model: str | None) -> str:
    """Polish Off the Clock blurbs."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE

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
    return route(task_type="editorial", prompt=prompt, system=EDITORIAL_VOICE, model_override=model)


def _proceed_editorial(data: dict, model: str | None) -> str:
    """Generate the newsletter hook/intro."""
    from flatwhite.model_router import route
    from flatwhite.classify.prompts import EDITORIAL_VOICE
    from flatwhite.db import load_all_section_outputs

    week_iso = get_current_week_iso()
    outputs = load_all_section_outputs(week_iso)

    context_parts = []
    if "pulse" in outputs:
        context_parts.append(f"Pulse summary: {outputs['pulse']['output_text'][:200]}")
    if "big_conversation" in outputs:
        context_parts.append(f"Big Conversation: {outputs['big_conversation']['output_text'][:200]}")
    if "finds" in outputs:
        context_parts.append(f"Top Find: {outputs['finds']['output_text'][:150]}")

    context = "\n".join(context_parts) if context_parts else "No sections completed yet."

    prompt = (
        "Write the opening paragraph for this week's Flat White newsletter.\n\n"
        f"This week's content:\n{context}\n\n"
        f"Additional context from editor: {data.get('editor_notes', '')}\n\n"
        "Write 2-4 sentences. Start with 'Good morning AusCorp.' Lead with the biggest story "
        "of the week. Mention the Pulse direction. Tease what's below. "
        "Voice: dry, informed, slightly conspiratorial. Like a colleague who always knows what's happening.\n\n"
        "Output ONLY the paragraph. No title. No sign-off."
    )
    return route(task_type="hook", prompt=prompt, system=EDITORIAL_VOICE, model_override=model)
```

- [ ] **Step 4: Add events CRUD endpoints**

```python
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


@app.get("/api/section-outputs")
def api_section_outputs() -> JSONResponse:
    """Return all saved section outputs for current week."""
    from flatwhite.db import load_all_section_outputs
    week_iso = get_current_week_iso()
    outputs = load_all_section_outputs(week_iso)
    return JSONResponse({"outputs": {k: v for k, v in outputs.items()}, "week_iso": week_iso})


@app.post("/api/section-output/{section}")
async def api_save_section_output(section: str, request: Request) -> JSONResponse:
    """Save edited output for a section (manual edit by editor)."""
    from flatwhite.db import save_section_output
    body = await request.json()
    week_iso = get_current_week_iso()
    save_section_output(week_iso, section, body.get("output_text", ""), body.get("model_used"))
    return JSONResponse({"saved": True, "section": section})


@app.get("/api/lobby")
def api_lobby() -> JSONResponse:
    """Return employer hiring data + top movers for current week."""
    conn = get_connection()
    week_iso = get_current_week_iso()

    # Get current and previous week snapshots
    import datetime
    year, week_num = int(week_iso[:4]), int(week_iso[6:])
    dt = datetime.datetime.strptime(f"{year}-W{week_num:02d}-1", "%G-W%V-%u")
    prev_week = (dt - datetime.timedelta(weeks=1)).strftime("%G-W%V")

    current = conn.execute(
        """SELECT es.*, ew.employer_name, ew.sector, ew.ats_platform
        FROM employer_snapshots es
        JOIN employer_watchlist ew ON es.employer_id = ew.id
        WHERE es.week_iso = ?
        ORDER BY ew.employer_name""",
        (week_iso,),
    ).fetchall()

    previous = conn.execute(
        """SELECT employer_id, open_roles_count FROM employer_snapshots WHERE week_iso = ?""",
        (prev_week,),
    ).fetchall()
    conn.close()

    prev_map = {r["employer_id"]: r["open_roles_count"] for r in previous}

    employers = []
    for r in current:
        d = dict(r)
        prev_count = prev_map.get(d["employer_id"])
        d["prev_roles"] = prev_count
        d["delta"] = d["open_roles_count"] - prev_count if prev_count is not None else None
        d["delta_pct"] = round(d["delta"] / prev_count * 100, 1) if prev_count and prev_count > 0 and d["delta"] is not None else None
        employers.append(d)

    # Top movers: sort by absolute delta
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
```

- [ ] **Step 5: Add Big Conversation candidates endpoint**

```python
@app.get("/api/big-conversation-candidates")
def api_big_conv_candidates() -> JSONResponse:
    """Return top 5 Big Conversation candidates from all ingested data."""
    week_iso = get_current_week_iso()
    conn = get_connection()

    # Get highest-scored editorial items across all sections
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
```

- [ ] **Step 6: Verify all endpoints**

```bash
python -c "
from flatwhite.dashboard.api import app
routes = sorted(set(r.path for r in app.routes if hasattr(r, 'path')))
for r in routes:
    if r.startswith('/api/'):
        print(r)
"
```

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat(api): add proceed-section, events, lobby, amp-finest, models endpoints"
```

---

### Task 4: Frontend — Complete Rewrite

**Files:**
- Rewrite: `flatwhite/dashboard/static/index.html`

This is the largest task. The new index.html is a complete rewrite. Rather than showing the full ~2000 lines here, this task describes the structure and key sections. The implementation should write the complete file.

- [ ] **Step 1: Write the new index.html**

The new file must include:

**CSS (top of file):**
- Same colour variables as current but `--font-serif` and `--font-sans` both set to `Arial, Helvetica, sans-serif`
- Same sidebar layout (200px fixed left sidebar)
- Reuse existing utility classes: `.card`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-sm`, `.chip`, `.chip-green`, `.chip-red`, `.chip-amber`, `.fr`, `.fb`, `.fc`, `.mb16`, etc.
- New `.section-header` class with RUN + PROCEED buttons right-aligned
- New `.status-badge` for section status (empty/pulled/selected/done)
- Keep `.gauge-num`, `.gauge-dir`, `.dir-pill` for Pulse display
- Keep `.ingest-spinner` animation

**HTML body structure:**
```html
<div class="sidebar" id="sidebar"></div>
<div class="main" id="main"></div>
<div id="toast" class="toast"></div>
```

**JavaScript state object:**
```javascript
var S = {
  page: "pulse",
  weekIso: "",
  models: [],
  // Per-section data (loaded on demand when tab is opened)
  pulse: null,        // {pulse, signals, anomalies, interactions}
  items: null,        // curated items
  threads: null,      // thread candidates
  lobby: null,        // employer data
  otcData: null,      // off the clock candidates
  bigConvCandidates: null,
  ampFinest: null,
  events: null,
  sectionOutputs: {}, // saved outputs per section
  // Editor selections per section
  selections: {
    pulse: [],        // selected signal names
    bigconv: null,    // selected candidate or custom
    lobby: [],        // selected employer ids
    finds: [],        // selected item ids
    thread: null,     // selected thread id
    otc: {},          // picks per category
  },
  whispers: [],       // manually entered whispers
};
```

**Sidebar — 12 items matching newsletter order:**
```javascript
var pages = [
  {key: "editorial", label: "Editorial", icon: "GM"},
  {key: "pulse", label: "Pulse", icon: "\u25C9"},
  {key: "bigconv", label: "Big Conversation", icon: "\u00B6"},
  {key: "whispers", label: "Whispers", icon: "\uD83D\uDC41"},
  {key: "lobby", label: "The Lobby", icon: "\uD83D\uDCCA"},
  {key: "finds", label: "Finds", icon: "\uD83D\uDD25"},
  {key: "thread", label: "Thread", icon: "\u00A7"},
  {key: "amp", label: "AMP's Finest", icon: "\uD83D\uDCC8"},
  {key: "otc", label: "Off the Clock", icon: "\uD83C\uDF77"},
  {key: "events", label: "Events", icon: "\uD83D\uDCC5"},
  {key: "salary", label: "Salary Vault", icon: "\uD83D\uDCB0", disabled: true},
  {key: "assemble", label: "Assemble", icon: "\u2709"},
];
```

**Each section follows the same UI pattern:**

```
┌─────────────────────────────────────────────────┐
│ Section Header                    [RUN] [MODEL▼]│
│ Subtitle                          [PROCEED]     │
├─────────────────────────────────────────────────┤
│                                                 │
│ Content area (candidates, tables, forms)        │
│ Checkboxes / radio buttons for SELECT           │
│                                                 │
├─────────────────────────────────────────────────┤
│ Generated output (editable textarea)            │
│ [Save] [Re-generate]                            │
└─────────────────────────────────────────────────┘
```

**Key render functions (one per section):**

1. `renderEditorial()` — summary cards of other sections + hook textarea + PROCEED
2. `renderPulse()` — RUN button → gauge + signal table with checkboxes → PROCEED → editable output
3. `renderBigConv()` — RUN (uses existing editorial data) → 5 candidate cards + "Add Custom" → PROCEED → editable output
4. `renderWhispers()` — add form + list of whispers. No RUN or PROCEED.
5. `renderLobby()` — RUN button → top movers + full employer table with checkboxes → PROCEED → editable output
6. `renderFinds()` — RUN button → scored items with checkboxes → PROCEED → editable output per item
7. `renderThread()` — RUN button → top 5 threads with radio select → PROCEED → editable output
8. `renderAmp()` — paste form (data description + notes) → PROCEED → editable output
9. `renderOTC()` — RUN button → 5 categories with candidates → pick one per category → PROCEED → editable blurbs
10. `renderEvents()` — add form + event list. No RUN or PROCEED.
11. `renderSalary()` — "Coming Soon" placeholder
12. `renderAssemble()` — section status cards + full preview + Export HTML + Copy

**Model selector dropdown (shared component):**
```javascript
function modelDropdown(sectionKey) {
  if (!S.models.length) return '';
  var h = '<select id="model-' + sectionKey + '" class="model-select">';
  S.models.forEach(function(m) {
    h += '<option value="' + m.id + '">' + m.label + '</option>';
  });
  h += '</select>';
  return h;
}
```

**Generic PROCEED handler:**
```javascript
function proceed(section, data) {
  var modelEl = document.getElementById('model-' + section);
  var model = modelEl ? modelEl.value : null;
  var statusEl = document.getElementById('status-' + section);
  var outputEl = document.getElementById('output-' + section);

  if (statusEl) statusEl.innerHTML = '<span class="ingest-spinner"></span> Generating...';

  api('/api/proceed-section', {
    method: 'POST',
    body: {section: section, model: model, data: data}
  }).then(function(d) {
    if (outputEl) outputEl.value = d.output;
    S.sectionOutputs[section] = d.output;
    if (statusEl) statusEl.innerHTML = '<span class="chip chip-green">Done</span>';
    showToast(section + ' generated');
  }).catch(function(e) {
    if (statusEl) statusEl.innerHTML = '<span class="chip chip-red">Failed: ' + e + '</span>';
  });
}
```

**Generic RUN handler:**
```javascript
function runSection(section, btn) {
  var orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Running...';
  var statusEl = document.getElementById('status-' + section);
  if (statusEl) statusEl.innerHTML = '<span class="ingest-spinner"></span> Pulling data...';

  api('/api/run-section', {method: 'POST', body: {section: section}})
    .then(function(d) {
      btn.disabled = false;
      btn.textContent = orig;
      if (statusEl) statusEl.innerHTML = '<span class="chip chip-green">Data pulled</span>';
      showToast(section + ' data pulled');
      // Reload section data
      loadSectionData(section).then(render);
    })
    .catch(function(e) {
      btn.disabled = false;
      btn.textContent = orig;
      if (statusEl) statusEl.innerHTML = '<span class="chip chip-red">Failed</span>';
    });
}
```

- [ ] **Step 2: Verify the dashboard loads**

```bash
# Restart dashboard
lsof -ti:8500 | xargs kill -9 2>/dev/null
sleep 1
python -c "import uvicorn; uvicorn.run('flatwhite.dashboard.api:app', host='0.0.0.0', port=8500, log_level='warning')" &
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:8500/
```

Expected: `200`

- [ ] **Step 3: Test each section renders without errors**

Open http://localhost:8500 in browser. Click through each sidebar item. Verify:
- Each section shows its header, RUN button (where applicable), model dropdown, PROCEED button
- No JS console errors
- Sidebar shows all 12 items with correct labels
- Salary Vault shows "Coming Soon" and is not clickable

- [ ] **Step 4: Test RUN → SELECT → PROCEED flow on Pulse**

1. Click Pulse in sidebar
2. Click RUN — should pull signals and show the signal table
3. Check/uncheck signals
4. Select model from dropdown
5. Click PROCEED — should generate Pulse narrative in the output textarea
6. Edit the text — should be editable
7. Click Save — should persist

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat(dashboard): complete frontend rewrite — newsletter-section layout with RUN/SELECT/PROCEED"
```

---

### Task 5: Wire Existing Endpoints Into New Frontend

**Files:**
- Modify: `flatwhite/dashboard/api.py` (ensure /api/run-section covers all sections)

- [ ] **Step 1: Update /api/run-section to cover all section RUN operations**

Replace the existing `runners` dict in `api_run_section()` with:

```python
runners = {
    "pulse": lambda: (
        __import__("flatwhite.signals.market_hiring", fromlist=["pull_market_hiring"]).pull_market_hiring(),
        __import__("flatwhite.signals.hiring_pulse", fromlist=["pull_hiring_pulse"]).pull_hiring_pulse(),
        __import__("flatwhite.signals.salary_pressure", fromlist=["pull_salary_pressure"]).pull_salary_pressure(),
        __import__("flatwhite.signals.news_velocity", fromlist=["pull_layoff_news_velocity"]).pull_layoff_news_velocity(),
        __import__("flatwhite.signals.consumer_confidence", fromlist=["pull_consumer_confidence"]).pull_consumer_confidence(),
        __import__("flatwhite.signals.asx_volatility", fromlist=["pull_asx_volatility"]).pull_asx_volatility(),
        __import__("flatwhite.signals.asx_momentum", fromlist=["pull_asx_momentum"]).pull_asx_momentum(),
        __import__("flatwhite.signals.indeed_hiring", fromlist=["pull_indeed_hiring"]).pull_indeed_hiring(),
        __import__("flatwhite.signals.asic_insolvency", fromlist=["pull_asic_insolvency"]).pull_asic_insolvency(),
        __import__("flatwhite.pulse.composite", fromlist=["calculate_pulse"]).calculate_pulse(),
    ),
    "editorial": lambda: (
        __import__("flatwhite.editorial.reddit_rss", fromlist=["pull_reddit_editorial"]).pull_reddit_editorial(),
        __import__("flatwhite.editorial.google_news_editorial", fromlist=["pull_google_news_editorial"]).pull_google_news_editorial(),
        __import__("flatwhite.editorial.rss_feeds", fromlist=["pull_rss_feeds"]).pull_rss_feeds(),
        __import__("flatwhite.editorial.podcast_feeds", fromlist=["pull_podcast_feeds"]).pull_podcast_feeds(),
        __import__("flatwhite.editorial.linkedin_rss", fromlist=["pull_linkedin_newsletters"]).pull_linkedin_newsletters(),
    ),
    "classify": lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified(),
    "finds": lambda: (
        __import__("flatwhite.editorial.reddit_rss", fromlist=["pull_reddit_editorial"]).pull_reddit_editorial(),
        __import__("flatwhite.editorial.google_news_editorial", fromlist=["pull_google_news_editorial"]).pull_google_news_editorial(),
        __import__("flatwhite.editorial.rss_feeds", fromlist=["pull_rss_feeds"]).pull_rss_feeds(),
        __import__("flatwhite.editorial.podcast_feeds", fromlist=["pull_podcast_feeds"]).pull_podcast_feeds(),
        __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified(),
    ),
    "lobby": lambda: __import__("flatwhite.signals.hiring_pulse", fromlist=["pull_hiring_pulse"]).pull_hiring_pulse(),
    "thread": lambda: (
        __import__("flatwhite.editorial.reddit_rss", fromlist=["pull_reddit_editorial"]).pull_reddit_editorial(),
        __import__("flatwhite.classify.classifier", fromlist=["classify_all_unclassified"]).classify_all_unclassified(),
    ),
    "off_the_clock": lambda: __import__("flatwhite.editorial.off_the_clock", fromlist=["pull_off_the_clock"]).pull_off_the_clock(),
    "classify_otc": lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified(),
}
```

- [ ] **Step 2: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat(api): expand run-section to cover all newsletter sections"
```

---

### Task 6: End-to-End Smoke Test

- [ ] **Step 1: Restart dashboard and verify all endpoints respond**

```bash
lsof -ti:8500 | xargs kill -9 2>/dev/null; sleep 1
python -c "import uvicorn; uvicorn.run('flatwhite.dashboard.api:app', host='0.0.0.0', port=8500, log_level='warning')" &
sleep 2

# Test key endpoints
curl -s http://localhost:8500/api/models | python -m json.tool | head -5
curl -s http://localhost:8500/api/pulse | python -m json.tool | head -5
curl -s http://localhost:8500/api/off-the-clock | python -m json.tool | head -5
curl -s http://localhost:8500/api/lobby | python -m json.tool | head -5
curl -s http://localhost:8500/api/events | python -m json.tool | head -5
curl -s http://localhost:8500/api/section-outputs | python -m json.tool | head -5
```

- [ ] **Step 2: Test the full workflow for one section (Off the Clock)**

1. Open http://localhost:8500
2. Click "Off the Clock" in sidebar
3. Click RUN — should pull lifestyle sources
4. Wait for candidates to appear
5. Pick one per category, edit blurbs
6. Select model from dropdown
7. Click PROCEED — should polish blurbs
8. Verify output appears in editable text area

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete newsletter-first dashboard redesign"
```
