# Dashboard Status Bar + Assemble Tab — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a status bar and Assemble tab to the editor dashboard so the editor never needs the CLI.

**Architecture:** Two new API endpoints (`GET /api/status`, `POST /api/assemble`) backed by existing `get_pipeline_status()` and `render_newsletter()`. Frontend gets a persistent status bar above all tabs and a new "Assemble" nav item that shows a pre-flight checklist, triggers assembly, and displays inline HTML preview with copy button.

**Tech Stack:** FastAPI (backend), vanilla JS (frontend), existing `flatwhite.orchestrate.status` and `flatwhite.assemble.renderer` modules.

---

### Task 1: Add `GET /api/status` endpoint

**Files:**
- Modify: `flatwhite/flatwhite/dashboard/api.py`

**Step 1: Add the endpoint**

After the existing `GET /api/draft` endpoint (line ~107), add:

```python
@app.get("/api/status")
def api_status() -> JSONResponse:
    """Return pipeline status for current week."""
    from flatwhite.orchestrate.status import get_pipeline_status
    status = get_pipeline_status()
    return JSONResponse(status)
```

**Step 2: Verify it works**

Run: `cd flatwhite && python -c "from flatwhite.orchestrate.status import get_pipeline_status; print(get_pipeline_status())"`
Expected: dict with keys week_iso, signals_count, curated_items_count, approved_items_count, etc.

---

### Task 2: Add `POST /api/assemble` endpoint

**Files:**
- Modify: `flatwhite/flatwhite/dashboard/api.py`

**Step 1: Add the endpoint**

After the `/api/status` endpoint, add:

```python
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
```

---

### Task 3: Add status bar to frontend

**Files:**
- Modify: `flatwhite/flatwhite/dashboard/static/index.html`

**Step 1: Add CSS for status bar**

Add after the existing `.health-dot.fail` rule (~line 222):

```css
.status-bar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 20px; margin-bottom: 24px; font-size: 13px;
}
.status-bar .sb-item { display: flex; align-items: center; gap: 6px; }
.status-bar .sb-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-bar .sb-dot.on { background: var(--green); }
.status-bar .sb-dot.off { background: var(--border); }
.status-bar .sb-dot.warn { background: var(--amber); }
.status-bar .sb-val { font-weight: 600; }
.status-bar .sb-lbl { color: var(--text-3); }
```

**Step 2: Add status state and loader**

In the state object `S`, add: `status: null`

Add a new loader function:

```javascript
function loadStatus() {
  return api("/api/status").then(function(d) { S.status = d; });
}
```

**Step 3: Add renderStatusBar() function**

```javascript
function renderStatusBar() {
  var s = S.status;
  if (!s) return "";
  var pulse = s.pulse_score != null;
  var dir = s.pulse_direction ? (" " + da(s.pulse_direction)) : "";
  var assembled = s.has_newsletter;
  return '<div class="status-bar">' +
    '<div class="sb-item"><span class="sb-dot ' + (s.signals_count > 0 ? "on" : "off") + '"></span><span class="sb-val">' + s.signals_count + '</span><span class="sb-lbl">Signals</span></div>' +
    '<div class="sb-item"><span class="sb-dot ' + (s.curated_items_count > 0 ? "on" : "off") + '"></span><span class="sb-val">' + s.curated_items_count + '</span><span class="sb-lbl">Classified</span></div>' +
    '<div class="sb-item"><span class="sb-dot ' + (s.approved_items_count > 0 ? "on" : "off") + '"></span><span class="sb-val">' + s.approved_items_count + '</span><span class="sb-lbl">Approved</span></div>' +
    (pulse ? '<div class="sb-item"><span class="sb-dot on"></span><span class="sb-val">' + s.pulse_score + dir + '</span><span class="sb-lbl">Pulse</span></div>' : '<div class="sb-item"><span class="sb-dot off"></span><span class="sb-lbl">No Pulse</span></div>') +
    '<div class="sb-item"><span class="sb-dot ' + (s.has_hooks ? "on" : "off") + '"></span><span class="sb-lbl">' + (s.has_hooks ? "Hooks ready" : "No hooks") + '</span></div>' +
    '<div class="sb-item"><span class="sb-dot ' + (assembled ? "on" : "off") + '"></span><span class="sb-lbl">' + (assembled ? "Assembled" : "Not assembled") + '</span></div>' +
    '<div class="sb-item" style="margin-left:auto;"><span class="sb-lbl">Rotation ' + esc(s.rotation) + '</span></div>' +
    '</div>';
}
```

**Step 4: Inject status bar into render()**

In the `render()` function, after `renderSidebar()` and before the page-specific render, set the main innerHTML to `renderStatusBar() + pageContent`.

**Step 5: Add loadStatus() to init**

Add `loadStatus()` to the `Promise.all([...])` init call. Also reload status after ingest completes and after assemble completes.

---

### Task 4: Add Assemble tab to frontend

**Files:**
- Modify: `flatwhite/flatwhite/dashboard/static/index.html`

**Step 1: Add nav item**

In the `pages` array inside `renderSidebar()`, add after `bigconv`:

```javascript
{ key: "assemble", label: "Assemble", icon: "\u2709" },
```

**Step 2: Add assemble state**

In the state object `S`, add:

```javascript
assemble: { loading: false, result: null, error: null, copied: false }
```

**Step 3: Add page route**

In `render()`, add:

```javascript
if (S.page === "assemble") { m.innerHTML = renderStatusBar() + renderAssemble(); }
```

**Step 4: Add renderAssemble() function**

Shows:
- Pre-flight checklist (hook selected?, items approved by section count, draft saved?, rotation)
- "Assemble Newsletter" button (disabled if no hook selected or no approved items)
- Loading state while assembling
- After assembly: subject line, preview text, inline HTML preview in a sandboxed iframe, "Copy HTML" button
- Error state if assembly fails

```javascript
function renderAssemble() {
  var hookText = S.selectedHook !== null ? S.hooks[S.selectedHook] : null;
  var approvedCount = Object.values(S.decisions).filter(function(d) { return d === "approved"; }).length;
  var threadCount = Object.values(S.threadDecisions).filter(function(d) { return d === "feature"; }).length;
  var totalApproved = approvedCount + threadCount;
  var rotation = S.status ? S.status.rotation : "A";
  var canAssemble = hookText && totalApproved > 0;
  var a = S.assemble;

  var h = '<div class="sh"><div><h2>\u2709 Assemble Newsletter</h2><div class="sub">Build final HTML from approved items</div></div></div>';

  // Pre-flight checklist
  h += '<div class="card mb24 fu"><div class="lu mb8">Pre-flight Checklist</div>';
  h += '<div class="fc" style="gap:8px;">';
  h += '<div class="fr g8"><span class="sb-dot ' + (hookText ? "on" : "off") + '" style="width:10px;height:10px;border-radius:50;display:inline-block;"></span><span>' + (hookText ? 'Hook: "' + esc(hookText.substring(0, 60)) + (hookText.length > 60 ? '...' : '') + '"' : 'No hook selected -- go to Pulse tab') + '</span></div>';
  h += '<div class="fr g8"><span class="sb-dot ' + (totalApproved > 0 ? "on" : "off") + '" style="width:10px;height:10px;border-radius:50;display:inline-block;"></span><span>' + totalApproved + ' items approved</span></div>';
  h += '<div class="fr g8"><span class="sb-dot ' + (S.draftSaved ? "on" : "off") + '" style="width:10px;height:10px;border-radius:50;display:inline-block;"></span><span>' + (S.draftSaved ? 'Big Conversation draft saved' : 'No draft saved (optional)') + '</span></div>';
  h += '<div class="fr g8"><span class="sb-dot on" style="width:10px;height:10px;border-radius:50;display:inline-block;"></span><span>Rotation ' + esc(rotation) + '</span></div>';
  h += '</div></div>';

  // Assemble button
  if (!a.result) {
    h += '<div style="margin-bottom:24px;">';
    if (a.loading) {
      h += '<button class="btn btn-primary" disabled><span class="ingest-spinner"></span> Assembling newsletter...</button>';
    } else if (a.error) {
      h += '<div style="color:var(--red);font-size:14px;margin-bottom:12px;">Assembly failed: ' + esc(a.error) + '</div>';
      h += '<button class="btn btn-primary" data-action="assemble"' + (canAssemble ? '' : ' disabled') + '>Retry Assembly</button>';
    } else {
      h += '<button class="btn btn-primary" data-action="assemble"' + (canAssemble ? '' : ' disabled') + '>Assemble Newsletter</button>';
      if (!canAssemble) h += '<span style="font-size:13px;color:var(--text-3);margin-left:12px;">' + (!hookText ? 'Select a hook first' : 'Approve some items first') + '</span>';
    }
    h += '</div>';
  }

  // Result
  if (a.result) {
    var r = a.result;
    h += '<div class="card mb16 fu"><div class="lu mb8">Newsletter Ready</div>';
    h += '<div class="fc" style="gap:8px;">';
    h += '<div><span class="sb-lbl">Subject:</span> <strong>' + esc(r.subject) + '</strong></div>';
    h += '<div><span class="sb-lbl">Preview:</span> ' + esc(r.preview_text) + '</div>';
    h += '<div><span class="sb-lbl">Rotation:</span> ' + esc(r.rotation) + ' <span class="sb-lbl" style="margin-left:12px;">Length:</span> ' + (r.char_count || 0).toLocaleString() + ' chars</div>';
    h += '</div>';
    h += '<div class="fr g6 mt20 pt16 bt">';
    h += '<button class="btn btn-primary" data-action="copy-html">' + (a.copied ? '\u2713 Copied!' : 'Copy HTML') + '</button>';
    h += '<button class="btn btn-secondary" data-action="assemble">Reassemble</button>';
    h += '</div></div>';

    // Inline preview
    h += '<div class="fu fu1"><div class="lu">Preview</div>';
    h += '<div class="card" style="padding:0;overflow:hidden;border-radius:10px;">';
    h += '<iframe id="preview-frame" style="width:100%;min-height:600px;border:none;background:#fff;" sandbox="allow-same-origin"></iframe>';
    h += '</div></div>';
  }

  return h;
}
```

**Step 5: Add event bindings**

In the `bind()` function, add handlers for `data-action="assemble"` and `data-action="copy-html"`:

```javascript
// Assemble button
document.querySelectorAll('[data-action="assemble"]').forEach(function(el) {
  el.onclick = function() {
    var hookText = S.selectedHook !== null ? S.hooks[S.selectedHook] : null;
    if (!hookText) return;
    var rotation = S.status ? S.status.rotation : "A";
    S.assemble = { loading: true, result: null, error: null, copied: false };
    render();
    api("/api/assemble", { method: "POST", body: { hook_text: hookText, rotation: rotation } })
      .then(function(d) {
        if (d.error) {
          S.assemble = { loading: false, result: null, error: d.error, copied: false };
        } else {
          S.assemble = { loading: false, result: d, error: null, copied: false };
        }
        loadStatus().then(function() { render(); writePreviewFrame(); });
      })
      .catch(function(e) {
        S.assemble = { loading: false, result: null, error: e.message || "Failed", copied: false };
        render();
      });
  };
});

// Copy HTML button
document.querySelectorAll('[data-action="copy-html"]').forEach(function(el) {
  el.onclick = function() {
    if (!S.assemble.result) return;
    var html = "<!DOCTYPE html><html><body>" + S.assemble.result.html + "</body></html>";
    navigator.clipboard.writeText(html).then(function() {
      S.assemble.copied = true;
      render();
      setTimeout(function() { S.assemble.copied = false; render(); }, 2000);
    });
  };
});
```

**Step 6: Add writePreviewFrame() helper**

```javascript
function writePreviewFrame() {
  setTimeout(function() {
    var frame = document.getElementById("preview-frame");
    if (frame && S.assemble.result) {
      var doc = frame.contentDocument || frame.contentWindow.document;
      doc.open();
      doc.write("<!DOCTYPE html><html><body>" + S.assemble.result.html + "</body></html>");
      doc.close();
      // Auto-resize iframe to content height
      setTimeout(function() {
        try { frame.style.height = doc.body.scrollHeight + 40 + "px"; } catch(e) {}
      }, 200);
    }
  }, 50);
}
```

---

### Task 5: Update render() to show status bar on all pages + route assemble

**Files:**
- Modify: `flatwhite/flatwhite/dashboard/static/index.html`

**Step 1: Modify render() function**

Change the render function so that:
1. It renders the sidebar
2. It builds the status bar string
3. Each page render prepends the status bar
4. Add the assemble page route

**Step 2: Update progress tracking**

In `getProgress()`, add assemble tracking:
```javascript
p.assemble = S.assemble.result ? "done" : null;
```

Update the sidebar progress denominator from 4 to 5 and add assemble to the filter array.

**Step 3: Update init**

Add `loadStatus()` to the `Promise.all([...])` init call.

Also reload status after ingest completes (in the `pollIngest` done callback).

---

### Task 6: Test end-to-end

**Step 1: Start dashboard**

Run: `cd flatwhite && python -m uvicorn flatwhite.dashboard.api:app --port 8500 --reload`

**Step 2: Verify status endpoint**

Run: `curl http://localhost:8500/api/status`
Expected: JSON with pipeline status counts

**Step 3: Verify status bar renders**

Open http://localhost:8500 in browser. Status bar should appear above Pulse content with signal/classified/approved counts.

**Step 4: Verify Assemble tab**

Click "Assemble" in sidebar nav. Should show pre-flight checklist. Button disabled if no hook selected.

**Step 5: Commit**

```bash
git add flatwhite/flatwhite/dashboard/api.py flatwhite/flatwhite/dashboard/static/index.html
git commit -m "feat: dashboard status bar + assemble tab — no CLI needed for full workflow"
```
