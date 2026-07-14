# FW Control Room Increment 2 — Section Pages, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the five in-dash segment detail pages that Increment 1 rendered as passthrough wrappers (Editorial, Off the Clock, PS Top Picks, Stress Index / Pulse, Thread of the Week) into the real generate/process → editable output → "Mark ready" pattern, with the specific behaviours Victor confirmed: Editorial is gated on every other segment being ready and takes a "big story of the week" hook; Off the Clock becomes 5 separate categories with swap + custom add; PS Top Picks fixes the feature-story gap with a selectable list; Stress Index gets a proper Regenerate + Mark ready; Thread of the Week drops its dead scrape and becomes a paste-and-format tool.

**Architecture:** Same single-file SPA (`flatwhite/dashboard/static/index.html`) and FastAPI backend (`flatwhite/dashboard/api.py`) as Increment 1. Increment 1 introduced the `SEGMENTS` array, `toggleReady(id)`, and the `.page`/`.page-h`/`.page-b` detail-pane frame; this increment builds ON that frame. Task 1 adds one shared JS helper (a gating check + a "Mark ready" button wired into the existing `outputBox()` helper) consumed by all five segment tasks. Each segment task then rewrites its `renderX`/`proceedX` body, and where the segment's own writing logic needs to change (Editorial's prompt, Off the Clock's niche sourcing, Top Picks' feature-story gap), the matching Python is extended — never the shared classifier (`flatwhite/classify/classifier.py`) and never `flatwhite/assemble/renderer.py`.

**Tech Stack:** single static HTML/CSS/JS (no build step, no framework), FastAPI (`flatwhite/dashboard/api.py`), `pytest` via FW's own venv.

## Global Constraints

- **Runs on FW's venv only:** `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python ...`. System python 3.9 breaks FW. Never use another interpreter for FW.
- **Branch:** off the Increment 1 branch, not off `main`: `git checkout fw-control-room-shell && git checkout -b fw-control-room-sections`. If `fw-control-room-shell` does not exist locally yet (Increment 1 not yet executed), stop and flag this before branching — do not silently branch from `main`.
- FW deploy is Victor's (GCP VM). Built + tested locally only, not merged/pushed/deployed.
- **FW test baseline, recorded 14 Jul 2026 on `main`:** `.venv/bin/python -m pytest -q` → **124 passed, 8 failed**. The 8 failures are pre-existing and unrelated to this work (`tests/test_normalise.py::test_cold_start_absolute_floor`, `test_cold_start_absolute_ceiling`, `test_cold_start_absolute_clamped`, `test_cold_start_inverted`, `test_self_calibrating_above_median`, `test_self_calibrating_inverted`, `tests/test_pipeline.py::test_anomaly_detection_with_enough_data`, `test_anomaly_detection_varied_baseline`). Re-run this command on the `fw-control-room-sections` branch before Task 1 to confirm the same 124/8 split, then hold it: after every task the count of NEW failures must be zero.
- No em dashes (U+2014) in any reader-facing string, prompt copy, or generated content. Australian spelling. "percent" as `%`.
- **Do not change `flatwhite/classify/classifier.py`** (the shared classifier `classify_all_unclassified()` — Finds/Whisper/Thread-candidate sections it produces are load-bearing for Big Conversation's candidate pool, per the Increment 1 trim). **Do not change `flatwhite/assemble/renderer.py`** or `flatwhite/assemble/templates.py` (legacy assembly path still invoked by `flatwhite/cli.py` and `orchestrate/runner.py`).
- Each existing `_proceed_*` function in `flatwhite/dashboard/api.py` (`_proceed_pulse`, `_proceed_big_conversation`, `_proceed_finds`, `_proceed_thread`, `_proceed_off_the_clock`, `_proceed_editorial`) may be extended (new data fields, new prompt) but its existing callers (the `/api/proceed-section` dispatch, `_safe_override`, the `custom_prompt` escape hatch) must keep working exactly as before for the sections this plan does not touch (`pulse` behaviour itself, `big_conversation`, `finds`).
- No JS build/test harness exists: verify UI changes via `curl` presence checks against the running dashboard, a manual click script, and the Python suite staying at baseline. Verify backend/prompt logic changes with real `pytest` unit tests (monkeypatching `route()`, following the pattern in `tests/test_model_picker.py`).
- Local run: `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`. Kill it when done with each task's manual check.
- **Out of scope for this increment** (do not build): the "benchmark chip" against `data/beehiiv_fw_ground_truth.json` (that is Increment 7, Assembly), the Big Conversation screenshot pipeline (Increment 3/4), Inside Track (Increment 5), Brains Trust (Increment 6). Where a segment page references sibling segments (e.g. Editorial reading other segments' status), read only what Increment 1's `SEGMENTS` array and existing `S.sectionOutputs` already expose — do not build new cross-segment plumbing.

## Current-structure anchors (verify exact line numbers before editing — Increment 1 changes surrounding layout/CSS but not these bodies)

- `flatwhite/dashboard/static/index.html` (1938 lines pre-Increment-1). State object `S` at line 270. `outputBox(section)` at line 1388, `fillOutput` 1414, `saveOutput` 1421 — all three are shared across segments and are what Task 1 extends. `render()` dispatch (pre-Increment-1: `switch (S.page)` at line 598; post-Increment-1: the `S.page`→renderer map Increment 1 Task 3 introduces inside the new `.page-b` wrapper). `renderEditorial`/`renderEditorialBody` 614-669, `renderPulse`/`renderPulseBody` 729-901, `renderOTCBody`/`renderOTC`/`OTC_DEFAULT_INSTRUCTION`/`buildOTCPrompt`/`pickOTC`/`updateOTCBlurb`/`updateOTCInstruction`/`toggleOtcPrompt`/`proceedOTC` 1151-1363 (`OTC_CATS` constant at 1139, unchanged by this plan), `renderTopPicksBody`/`renderTopPicks`/`toggleTopPick`/`copyTopPicks`/`scrapeTopPicks` 1768-1910.
- `flatwhite/dashboard/api.py`: `_proceed_pulse` 1474, `_proceed_big_conversation` 1661, `_proceed_finds` 1685, `_proceed_thread` 1710 (defined but excluded from `proceed_fns` since the Thread tab was hidden in the trim — stays excluded; this plan does NOT re-add it, see Task 6), `_proceed_off_the_clock` 1735, `_proceed_editorial` 1784, `/api/proceed-section` dispatch 1809-1851 (its `proceed_fns` dict at 1827 already keys `"off_the_clock"` and `"editorial"` — unchanged by this plan; the dispatch is section-name-agnostic and takes whatever `data` dict Task 2/3 supply). `/api/top-picks` 2120, `/api/top-picks/scrape` 2134 (last route in the file — Task 4 appends the new route directly after it). Generic save/load already used by every segment: `/api/section-output/{section}` (api.py:1432, calls `flatwhite/db.py:save_section_output`) and `/api/section-outputs` (api.py:1423, calls `load_all_section_outputs`) — both are keyed by an arbitrary `section` string, so Thread (Task 6) and Top Picks (Task 4) reuse them with no backend change.
- `flatwhite/dashboard/state.py`: `load_otc_candidates` (line 633) already caps at `config.yaml`'s `off_the_clock.candidates_per_category` (= 3, confirmed in `config.yaml:516` — no config change needed). Task 3 adds a niche-outlet re-rank inside this function, before the existing `[:cap]` slice.
- `flatwhite/classify/prompts.py` (667 lines): `EDITORIAL_VOICE` (line 10, shared by all editorial prompts — do not change its text, only append new constants), `BIG_CONVERSATION_DRAFT_PROMPT` ends at line 291 with the closing `)`. Task 2 inserts new constants immediately after line 291, before the `# ─── PULSE SUMMARY` comment at line 293.
- `flatwhite/editorial/beehiiv_picks.py`: `fetch_recent_posts(days=7)` (line 152) already returns `[{id, title, slug, publish_date, web_url}, ...]` for recent Pick & Scroll editions — Task 4 exposes this via a new route, no change to this file.
- Skill: `~/.claude/skills/flat-white-intro/SKILL.md` — the exact shape (`Good morning AusCorp.` bold hook same line, 70-120 words, preview paragraph with 3 mini-hooks, no em dashes, no Oxford commas, numbers stay specific) that Task 2's new prompt constants must encode.
- `tests/conftest.py` provides the `temp_db` fixture (empty schema, `DB_PATH` patched) used by Task 3's test. `tests/test_model_picker.py` is the pattern for monkeypatching `api.route` to capture prompts without calling a real LLM, used by Task 2's test.

---

### Task 1: Shared helper — segment-ready gating + "Mark ready" button

**Files:**
- Modify: `flatwhite/dashboard/static/index.html` (state object `S` ~line 270-315; `outputBox(section)` ~line 1388-1398)

**Interfaces:**
- Consumes: Increment 1's `SEGMENTS` array (`[{id, name, status}]`, `status` one of `ready|notready|manual`) and `renderSidebar()`.
- Produces: `allSegmentsReadyExcept(excludeId)` → bool, `markReady(section)` → void (saves the output textarea if it has content, then sets that segment's status to `"ready"` and re-renders the sidebar). Both are consumed by Tasks 2-6.

- [ ] **Step 1: Confirm the Increment 1 branch exists and record the baseline.**
```bash
cd /Users/victornguyen/Documents/MISC/FW
git rev-parse --verify fw-control-room-shell   # must resolve; if it errors, stop and flag Increment 1 is not built yet
git checkout fw-control-room-shell
git checkout -b fw-control-room-sections
.venv/bin/python -m pytest -q 2>&1 | tail -3   # expect: 124 passed, 8 failed
```

- [ ] **Step 2: Add `markReady` and `allSegmentsReadyExcept`.** Add directly after Increment 1's `toggleReady(id)` function (search `grep -n "function toggleReady" flatwhite/dashboard/static/index.html` to find it):
```js
function markReady(section) {
  var ta = $("output-" + section);
  if (ta && ta.value && ta.value.trim()) {
    saveOutput(section);
  }
  var seg = SEGMENTS.find(function(s) { return s.id === section; });
  if (seg) seg.status = "ready";
  renderSidebar();
  showToast(section.replace(/_/g, " ") + " marked ready");
}

function allSegmentsReadyExcept(excludeId) {
  return SEGMENTS.every(function(seg) {
    return seg.id === excludeId || seg.status === "ready";
  });
}
```

- [ ] **Step 3: Extend `outputBox(section)` with the Mark ready button.** Replace the function at line 1388:
```js
function outputBox(section) {
  var h = '<div class="output-box">';
  h += '<div class="fb mb8"><span style="font-weight:600;font-size:13px;">Output</span>';
  h += '<div style="display:flex;gap:6px;">';
  h += '<button class="btn btn-sm" onclick="copyOutput(\'' + section + '\')" id="copy-btn-' + section + '">Copy</button>';
  h += '<button class="btn btn-sm btn-success" onclick="saveOutput(\'' + section + '\')">Save</button>';
  h += '<button class="btn btn-sm btn-success" onclick="markReady(\'' + section + '\')">Mark ready</button>';
  h += '</div></div>';
  h += '<textarea id="output-' + section + '" placeholder="Generated output will appear here..."></textarea>';
  h += '</div>';
  return h;
}
```

- [ ] **Step 4: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c 'function markReady'               # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function allSegmentsReadyExcept' # 1
curl -s http://127.0.0.1:8500/ | grep -c 'onclick="markReady'              # 1 (inside outputBox template)
kill %1
```
Manual: open `/`, go to Pulse (the only segment with a working output box before this plan's other tasks land) — confirm a third "Mark ready" button now sits next to Copy/Save; click it — the Pulse row's status dot in the sidebar turns green (ready).

- [ ] **Step 5: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3   # still 124 passed, 8 failed
git add flatwhite/dashboard/static/index.html
git commit -m "FW control room sections: shared segment-ready gate + Mark ready button"
```

---

### Task 2: Editorial intro — gated Write + big story of the week + skill-aligned prompt

**Files:**
- Modify: `flatwhite/classify/prompts.py` (insert after line 291, before line 293)
- Modify: `flatwhite/dashboard/api.py` (`_proceed_editorial`, lines 1784-1804)
- Modify: `flatwhite/dashboard/static/index.html` (state `S` ~line 270-315; `renderEditorialBody`/`renderEditorial`/`proceedEditorial`, lines 614-669)
- Test: `tests/test_editorial_intro.py` (new)

**Interfaces:**
- Consumes: Task 1's `allSegmentsReadyExcept('editorial')` and `SEGMENTS` (for `s.name`/`s.status`); existing `S.sectionOutputs` (any segment's saved output text).
- Produces: `_proceed_editorial(data, model, custom_prompt=None)` now expects `data = {"big_story": str, "big_conversation_output": str, "other_segments": [{"id": str, "label": str, "output_text": str}, ...]}` (old `data["selected_items"]` contract is dropped — no other caller depends on it, confirmed by grep).

- [ ] **Step 1: Write the failing test.** Create `tests/test_editorial_intro.py`:
```python
"""The editorial intro must follow the flat-white-intro skill's shape:
'Good morning AusCorp.' bold hook (built from the nominated big story of the
week) bridging into the Big Conversation, then a preview of the other
segments. Before this fix, _proceed_editorial used a generic prompt with no
relationship to the skill or its hard rules (no em dashes, Australian
spelling, specific numbers)."""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.dashboard.api as api


def _capture(monkeypatch):
    captured = {}
    def fake_route(task_type, prompt, system="", model_override=None):
        captured["prompt"] = prompt
        captured["system"] = system
        captured["task_type"] = task_type
        return "**Good morning AusCorp.** written intro"
    monkeypatch.setattr(api, "route", fake_route)
    return captured


def test_prompt_includes_big_story_big_conversation_and_other_segments(monkeypatch):
    cap = _capture(monkeypatch)
    data = {
        "big_story": "Optiver paid an average $1.4 million per employee last year.",
        "big_conversation_output": "The three-week PIP has become a way to show someone the door.",
        "other_segments": [
            {"id": "pulse", "label": "Stress Index", "output_text": "Market pulse is calm this week."},
        ],
    }
    api._proceed_editorial(data, None)
    assert "Optiver paid an average $1.4 million per employee last year." in cap["prompt"]
    assert "The three-week PIP has become a way to show someone the door." in cap["prompt"]
    assert "Market pulse is calm this week." in cap["prompt"]


def test_system_prompt_encodes_the_flat_white_intro_skill_shape(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_editorial({"big_story": "x", "big_conversation_output": "y", "other_segments": []}, None)
    assert "Good morning AusCorp." in cap["system"]
    assert "em dash" in cap["system"].lower()
    assert "Oxford comma" in cap["system"] or "oxford comma" in cap["system"].lower()


def test_missing_big_story_uses_placeholder_not_a_crash(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_editorial({"other_segments": []}, None)
    assert "no big story of the week nominated" in cap["prompt"]
```

- [ ] **Step 2: Run to confirm it fails.**
```bash
.venv/bin/python -m pytest tests/test_editorial_intro.py -v
```
Expected: FAIL — `_proceed_editorial` still builds the old generic "Write the editorial section..." prompt, so none of the new assertions match.

- [ ] **Step 3: Add the new prompt constants.** In `flatwhite/classify/prompts.py`, insert immediately after line 291 (the `)` closing `BIG_CONVERSATION_DRAFT_PROMPT`) and before the blank line + `# ─── PULSE SUMMARY` comment at line 293:
```python

# ─── EDITORIAL INTRO (consumed by dashboard/api.py _proceed_editorial) ───────
# Shape confirmed against data/beehiiv_fw_ground_truth.json (10 real editions)
# and ~/.claude/skills/flat-white-intro/SKILL.md. Written LAST, once every
# other segment is ready, so it can bridge into the actual Big Conversation
# output rather than guess at it.

EDITORIAL_INTRO_SYSTEM = (
    EDITORIAL_VOICE + "\n\n"
    "STRUCTURE FOR THE EDITORIAL INTRO (the 'Good morning AusCorp.' opener):\n"
    "This is the top-of-edition hook, not a full piece. Two paragraphs, "
    "occasionally three. Roughly 70-120 words of prose total.\n"
    "\n"
    "Paragraph 1: Open with the exact bold phrase 'Good morning AusCorp.' "
    "with the hook starting in the SAME line, no line break after it. The "
    "hook is 1-2 sentences built from the BIG STORY OF THE WEEK supplied "
    "below, then a bridge into the Big Conversation angle supplied below. "
    "Use a reframe, a specific number, or a found fact - never a vague tease.\n"
    "Paragraph 2: The preview paragraph. Opens with a variant of 'In this "
    "week's edition, we...' and lists the OTHER SEGMENTS supplied below as "
    "three mini-hooks, not section names. Vary the verb across editions: "
    "'we discuss / we're unpacking / we're looking into / we're asking "
    "whether / we cover'. Each item teases, it does not summarise.\n"
    "\n"
    "HARD RULES (from the flat-white-intro skill):\n"
    "- Open with '**Good morning AusCorp.**' verbatim, bold, hook on the same line.\n"
    "- No em dashes. Use '-' instead.\n"
    "- No Oxford commas. Australian spelling. 'percent' as %.\n"
    "- The hook never repeats the edition's subject-line wording.\n"
    "- Second person where natural ('your right to stay').\n"
    "- Numbers stay specific (13%, $1.4 million), never rounded to vague terms.\n"
    "- No signposting ('Here's the thing'), no reader-validation ('If you've "
    "ever...'), no zoom-out endings, no rule-of-three drumbeats, no announced "
    "punchlines.\n"
    "\n"
    "Output ONLY the intro prose (the two or three paragraphs). No headings, "
    "no commentary, no image or boilerplate blocks."
)

EDITORIAL_INTRO_PROMPT = (
    "Write this week's Flat White editorial intro.\n"
    "\n"
    "BIG STORY OF THE WEEK (the open hook Victor nominated - this is what "
    "makes people open the email):\n"
    "{big_story}\n"
    "\n"
    "THE BIG CONVERSATION (bridge into this after the hook):\n"
    "{big_conversation_text}\n"
    "\n"
    "OTHER SEGMENTS THIS WEEK (pick three as mini-hooks for the preview "
    "paragraph; if fewer than three are supplied, use what is here):\n"
    "{other_segments}\n"
    "\n"
    "Follow the structure and hard rules from your system prompt exactly."
)
```

- [ ] **Step 4: Rewrite `_proceed_editorial`.** Replace the function at `flatwhite/dashboard/api.py:1784-1804`:
```python
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
```

- [ ] **Step 5: Run to confirm it passes.**
```bash
.venv/bin/python -m pytest tests/test_editorial_intro.py -v
```
Expected: PASS (3 tests).

- [ ] **Step 6: Add the big-story input and the gate to the frontend.** Add a new state field to `S` (index.html ~line 270): find `customBigConv: null,` and add directly after it: `editorialBigStory: "",`. Then replace `renderEditorialBody` (line 614-625):
```js
function renderEditorialBody() {
  var h = '';
  h += '<div class="card mb20"><div style="font-size:13px;color:var(--text-2);margin-bottom:10px;font-weight:600;">Other segments</div>';
  SEGMENTS.filter(function(s) { return s.id !== "editorial"; }).forEach(function(s) {
    var ready = s.status === "ready";
    h += '<div class="fr mb8"><span style="width:10px;height:10px;border-radius:50%;background:' + (ready ? "var(--green)" : "var(--border)") + ';"></span> <span style="font-size:13px;">' + esc(s.name) + '</span></div>';
  });
  h += '</div>';
  h += '<div class="card mb20">';
  h += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">Big story of the week</div>';
  h += '<p style="font-size:12px;color:var(--text-3);margin:0 0 8px 0;">The open hook - the thing that makes people open the email.</p>';
  h += '<textarea class="form-input" id="editorial-big-story" rows="3" placeholder="e.g. Optiver paid an average $1.4 million per employee last year..." oninput="S.editorialBigStory=this.value">' + esc(S.editorialBigStory) + '</textarea>';
  h += '</div>';
  return h;
}
```
Replace `renderEditorial` (line 627-659):
```js
function renderEditorial(el) {
  var hasScrapeData = !!(S.lastScraped && S.lastScraped.editorial);
  var hasOutput = !!(S.sectionOutputs.editorial && S.sectionOutputs.editorial.output_text);
  if (!S.sectionPhase.editorial) S.sectionPhase.editorial = hasOutput ? 3 : (hasScrapeData ? 2 : 1);

  var p1 = '';
  p1 += '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">';
  p1 += '<button class="btn btn-primary" onclick="runSection(\'editorial\')">SCRAPE</button>';
  if (S.loading.editorial) p1 += renderSectionProgress('editorial');
  var _ps = formatScrapedDate(S.lastScraped.editorial);
  if (_ps) p1 += '<span class="scraped-badge">Scraped ' + _ps + '</span>';
  p1 += '</div>';

  var p2 = renderEditorialBody();

  var gated = !allSegmentsReadyExcept('editorial');
  var p3 = '';
  if (gated) {
    p3 += '<p style="font-size:12px;color:var(--amber-ink);background:var(--amber-soft);padding:8px 12px;border-radius:8px;margin-bottom:12px;">Write is locked until every other segment is marked ready.</p>';
  }
  p3 += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">';
  p3 += modelSelect('model-editorial');
  p3 += '<button class="btn btn-success" onclick="proceedEditorial()"' + (gated ? ' disabled' : '') + '>Write</button>';
  p3 += '</div>';
  p3 += outputBox('editorial');

  var h = '<div class="sh"><div><h2>GM Editorial</h2><div class="sub">Hook / intro paragraph. Written last, once every other segment is ready.</div></div></div>';
  h += phasePanel('editorial', 1, 'Scrape', true, hasScrapeData, p1);
  h += phasePanel('editorial', 2, 'Big story + segments', true, false, p2);
  h += phasePanel('editorial', 3, 'Write', true, hasOutput, p3);

  el.innerHTML = h;
  fillOutput('editorial');
}

function proceedEditorial() {
  if (!allSegmentsReadyExcept('editorial')) { showToast("Mark every other segment ready first", "error"); return; }
  var bigStory = (S.editorialBigStory || "").trim();
  if (!bigStory) { showToast("Add the big story of the week first", "error"); return; }
  var model = getModel("model-editorial");
  var otherSegments = SEGMENTS.filter(function(s) { return s.id !== "editorial"; }).map(function(s) {
    return { id: s.id, label: s.name, output_text: (S.sectionOutputs[s.id] && S.sectionOutputs[s.id].output_text) || "" };
  });
  var bigConv = (S.sectionOutputs.big_conversation && S.sectionOutputs.big_conversation.output_text) || "";
  S.loading.editorial = true; render();
  var data = { big_story: bigStory, big_conversation_output: bigConv, other_segments: otherSegments };
  api("/api/proceed-section", { method: "POST", body: { section: "editorial", model: model, data: data } })
    .then(function(d) { S.sectionOutputs.editorial = { output_text: d.output, model_used: d.model }; S.loading.editorial = false; render(); fillOutput('editorial'); showToast("Editorial written"); })
    .catch(function(e) { S.loading.editorial = false; render(); showToast("Error: " + e.message, "error"); });
}
```

- [ ] **Step 7: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c 'id="editorial-big-story"'   # 1
curl -s http://127.0.0.1:8500/ | grep -c '>Write<'                    # 1
kill %1
```
Manual: with at least one other segment `notready`, open Editorial — the amber "Write is locked" banner shows and the Write button is disabled. Toggle every other segment's status pill to ready — the banner disappears and Write becomes clickable. Type a big story, click Write — the output textarea fills, is editable, Save persists it, Mark ready turns Editorial's sidebar dot green.

- [ ] **Step 8: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3   # 127 passed (124 + 3 new), 8 failed
git add flatwhite/classify/prompts.py flatwhite/dashboard/api.py flatwhite/dashboard/static/index.html tests/test_editorial_intro.py
git commit -m "FW control room sections: gated Editorial intro with big story of the week, skill-aligned prompt"
```

---

### Task 3: Off the Clock — 5 categories, swap, custom add, niche sourcing bias

**Files:**
- Modify: `flatwhite/dashboard/state.py` (`load_otc_candidates`, line 633-680)
- Modify: `flatwhite/dashboard/static/index.html` (state `S`; `renderOTCBody`/`renderOTC`/`OTC_DEFAULT_INSTRUCTION`/`buildOTCPrompt`/`pickOTC`/`updateOTCBlurb`/`updateOTCInstruction`/`toggleOtcPrompt`/`proceedOTC`, lines 1151-1363)
- Test: `tests/test_otc_niche_bias.py` (new)

**Interfaces:**
- Consumes: existing `/api/off-the-clock` response shape (`{candidates: {otc_eating: [...], ...}, picks, week_iso, last_scraped_at}`, each candidate already capped to 3 by `config.yaml`'s `off_the_clock.candidates_per_category`); existing `_proceed_off_the_clock(data, model, custom_prompt)` which accepts `data = {"picks": [{category, title, url, blurb}, ...]}` and formats one entry per pick — reused unchanged, called once per page-load "Generate" (5 picks) and once per "Generate blurb" custom add (1 pick).
- Produces: no new backend contract; `load_otc_candidates` still returns the same shape, only the ranking within each category changes.

- [ ] **Step 1: Write the failing test.** Create `tests/test_otc_niche_bias.py`:
```python
"""Off the Clock should surface niche small businesses over mass outlets
(Concrete Playground, Time Out, the Guardian, SMH, Gourmet Traveller) that
already get mass coverage. Before this fix, load_otc_candidates ranked
purely on weighted_composite, so a mass-outlet story with a slightly higher
score always crowded out an equally-relevant niche one.
"""
from __future__ import annotations

from unittest.mock import patch

import flatwhite.db as db_module
from flatwhite.dashboard.state import load_otc_candidates

TEST_WEEK = "2026-W28"


def _seed_item(db_path, title, url, category, weighted_composite, week_iso=TEST_WEEK):
    with patch.object(db_module, "DB_PATH", db_path):
        raw_id = db_module.insert_raw_item(
            title=title,
            body="A round-up.",
            source="otc_rss_test",
            url=url,
            lane="lifestyle",
            subreddit=None,
            week_iso=week_iso,
        )
        db_module.insert_curated_item(
            raw_item_id=raw_id,
            section=category,
            summary=f"Summary for {title}",
            score_relevance=4,
            score_novelty=4,
            score_reliability=4,
            score_tension=4,
            score_usefulness=4,
            weighted_composite=weighted_composite,
        )


def test_mass_outlet_ranks_below_niche_at_equal_score(temp_db):
    _seed_item(
        temp_db, "New Sydney opening at Concrete Playground",
        "https://concreteplayground.com/sydney/new-opening", "otc_eating", 6.0,
    )
    _seed_item(
        temp_db, "A tiny Marrickville sandwich shop opened",
        "https://smallbusiness-example.com.au/marrickville-sandwiches", "otc_eating", 6.0,
    )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    titles = [row["title"] for row in grouped["otc_eating"]]
    assert titles[0] == "A tiny Marrickville sandwich shop opened"
    assert titles[1] == "New Sydney opening at Concrete Playground"


def test_mass_outlet_still_surfaces_if_nothing_niche_beats_it(temp_db):
    _seed_item(
        temp_db, "Only item this week, from Concrete Playground",
        "https://concreteplayground.com/melbourne/only-item", "otc_going", 5.0,
    )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    assert len(grouped["otc_going"]) == 1
    assert grouped["otc_going"][0]["title"] == "Only item this week, from Concrete Playground"


def test_cap_still_applies_after_niche_rerank(temp_db):
    # 6 niche items with descending scores; still capped to 3, still ordered by score.
    for i in range(6):
        _seed_item(
            temp_db, f"Niche eating item {i}",
            f"https://example.com/eating-{i}", "otc_eating", 6.0 - i,
        )
    with patch.object(db_module, "DB_PATH", temp_db):
        grouped = load_otc_candidates(week_iso=TEST_WEEK)
    assert len(grouped["otc_eating"]) == 3
    scores = [row["weighted_composite"] for row in grouped["otc_eating"]]
    assert scores == [6.0, 5.0, 4.0]
```

- [ ] **Step 2: Run to confirm it fails.**
```bash
.venv/bin/python -m pytest tests/test_otc_niche_bias.py -v
```
Expected: FAIL on `test_mass_outlet_ranks_below_niche_at_equal_score` (both items tie on `weighted_composite`, so the Concrete Playground item's SQL insertion order currently wins, or the assertion order does not hold).

- [ ] **Step 3: Add the niche re-rank.** In `flatwhite/dashboard/state.py`, insert directly above `def load_otc_candidates` (line 633):
```python
# Domains that already get mass press coverage; Off the Clock is meant to
# surface niche small businesses that BENEFIT from being featured, not
# outlets that already reach a huge audience on their own. Candidates from
# these domains are ranked BEHIND equally- or lower-scored niche candidates,
# not excluded outright - a genuinely standout mass-outlet story can still
# surface if nothing niche beats it this week.
_MASS_OUTLET_DOMAINS = {
    "concreteplayground.com",
    "timeout.com",
    "theguardian.com",
    "smh.com.au",
    "gourmettraveller.com.au",
}


def _is_mass_outlet(url: str | None) -> bool:
    if not url or "//" not in url:
        return False
    domain = url.split("/")[2].lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return any(domain == d or domain.endswith("." + d) for d in _MASS_OUTLET_DOMAINS)


def _niche_rank_key(row: dict) -> tuple:
    """Sort key: niche domains (0) before mass outlets (1); within each tier,
    highest weighted_composite first."""
    return (1 if _is_mass_outlet(row.get("url")) else 0, -(row.get("weighted_composite") or 0))
```
Then change the return statement at the end of `load_otc_candidates` from:
```python
    return {section: items[:cap] for section, items in grouped.items()}
```
to:
```python
    for items in grouped.values():
        items.sort(key=_niche_rank_key)

    return {section: items[:cap] for section, items in grouped.items()}
```

- [ ] **Step 4: Run to confirm it passes.**
```bash
.venv/bin/python -m pytest tests/test_otc_niche_bias.py tests/test_otc_cap.py -v
```
Expected: PASS (all 3 new tests, and the pre-existing `test_otc_cap.py` tests still pass since their fixtures use `example.com`, which is not in `_MASS_OUTLET_DOMAINS`).

- [ ] **Step 5: Rebuild the Off the Clock page — 5 categories, one pick each, swap, custom add.** Add new state fields to `S` (index.html ~line 270): find `otcPromptExpanded: false,` and replace the six lines from `otcPicks: {},` through `otcPromptExpanded: false,` with:
```js
  otcSelection: {},   // { category: {mode:"candidate"|"custom", candidateIndex, swapOpen, customUrl, customContent, blurb, generating} }
```
Replace the entire block from `function renderOTCBody() {` (line 1151) through the closing `}` of `proceedOTC()` (line 1363) — everything up to but not including the `/* ═══ SHARED: Output box... */` comment at line 1365 — with:
```js
function _otcSel(cat) {
  if (!S.otcSelection[cat]) {
    S.otcSelection[cat] = { mode: "candidate", candidateIndex: 0, swapOpen: false, customUrl: "", customContent: "", blurb: "", generating: false };
  }
  return S.otcSelection[cat];
}

function _otcCandidate(cat, idx) {
  var list = (S.otcData && S.otcData.candidates && S.otcData.candidates[cat]) || [];
  return list[idx] || null;
}

function renderOTCBody() {
  var h = '';
  if (!S.otcData || !S.otcData.candidates) {
    h += '<div class="card"><p class="loading">No data yet. Click SCRAPE to pull lifestyle sources.</p></div>';
    return h;
  }
  h += '<div class="otc-cats">';
  OTC_CATS.forEach(function(cat) {
    var sel = _otcSel(cat.key);
    var candidates = S.otcData.candidates[cat.key] || [];
    h += '<div class="card otc-cat-card">';
    h += '<div class="otc-cat-title">' + esc(cat.label) + '</div>';

    if (!candidates.length && sel.mode !== "custom") {
      h += '<p style="font-size:12px;color:var(--text-3);">No candidates scraped for this category.</p>';
      h += '<button class="btn btn-sm btn-secondary" onclick="toggleOTCCustom(\'' + cat.key + '\')">Add custom</button>';
      h += '</div>';
      return;
    }

    if (sel.mode === "candidate") {
      var current = _otcCandidate(cat.key, sel.candidateIndex) || candidates[0];
      var title = (current && (current.title || current.summary)) || "";
      h += '<div style="font-weight:600;font-size:14px;margin-bottom:4px;">' + esc(title) + '</div>';
      if (current && current.city) h += '<div style="font-size:11px;color:var(--text-3);margin-bottom:6px;">' + esc(current.city) + '</div>';
      h += '<textarea class="form-input" rows="2" placeholder="Blurb for this pick..." oninput="updateOTCBlurb(\'' + cat.key + '\',this.value)">' + esc(sel.blurb || (current ? current.summary : "") || "") + '</textarea>';
      h += '<div style="display:flex;gap:8px;margin-top:8px;">';
      h += '<button class="btn btn-sm btn-secondary" onclick="toggleOTCSwap(\'' + cat.key + '\')">Swap</button>';
      h += '<button class="btn btn-sm" onclick="toggleOTCCustom(\'' + cat.key + '\')">Add custom</button>';
      h += '</div>';
      if (sel.swapOpen) {
        h += '<div style="margin-top:8px;display:flex;flex-direction:column;gap:6px;">';
        candidates.forEach(function(c, idx) {
          if (idx === sel.candidateIndex) return;
          var label = (c.title || c.summary || "").slice(0, 60);
          h += '<button class="btn btn-sm" style="text-align:left;" onclick="pickOTCCandidate(\'' + cat.key + '\',' + idx + ')">' + esc(label) + '</button>';
        });
        h += '</div>';
      }
    } else {
      h += '<div style="font-size:11px;color:var(--text-3);margin-bottom:4px;">Custom pick</div>';
      h += '<input class="form-input" placeholder="URL" style="margin-bottom:6px;" value="' + esc(sel.customUrl) + '" oninput="updateOTCCustomField(\'' + cat.key + '\',\'customUrl\',this.value)">';
      h += '<textarea class="form-input" rows="3" placeholder="Paste the article/venue content..." oninput="updateOTCCustomField(\'' + cat.key + '\',\'customContent\',this.value)">' + esc(sel.customContent) + '</textarea>';
      h += '<div style="display:flex;gap:8px;margin-top:8px;">';
      h += '<button class="btn btn-sm btn-success" onclick="generateOTCCustomBlurb(\'' + cat.key + '\')"' + (sel.generating ? ' disabled' : '') + '>' + (sel.generating ? 'Generating…' : 'Generate blurb') + '</button>';
      h += '<button class="btn btn-sm btn-secondary" onclick="toggleOTCCustom(\'' + cat.key + '\')">Back to scraped picks</button>';
      h += '</div>';
      if (sel.blurb) {
        h += '<textarea class="form-input" rows="2" style="margin-top:8px;" oninput="updateOTCBlurb(\'' + cat.key + '\',this.value)">' + esc(sel.blurb) + '</textarea>';
      }
    }
    h += '</div>';
  });
  h += '</div>';
  return h;
}

function toggleOTCSwap(cat) {
  var sel = _otcSel(cat);
  sel.swapOpen = !sel.swapOpen;
  render();
}

function pickOTCCandidate(cat, idx) {
  var sel = _otcSel(cat);
  sel.candidateIndex = idx;
  sel.swapOpen = false;
  var next = _otcCandidate(cat, idx);
  sel.blurb = next ? (next.summary || "") : "";
  render();
}

function toggleOTCCustom(cat) {
  var sel = _otcSel(cat);
  sel.mode = sel.mode === "custom" ? "candidate" : "custom";
  render();
}

function updateOTCCustomField(cat, field, value) {
  _otcSel(cat)[field] = value;
}

function updateOTCBlurb(cat, value) {
  _otcSel(cat).blurb = value;
}

function generateOTCCustomBlurb(cat) {
  var sel = _otcSel(cat);
  if (!sel.customContent || !sel.customContent.trim()) {
    showToast("Paste the content to write from first", "error");
    return;
  }
  sel.generating = true; render();
  var model = getModel("model-otc");
  var pick = { category: cat, title: sel.customContent.split("\n")[0].slice(0, 80), url: sel.customUrl || "", blurb: sel.customContent };
  api("/api/proceed-section", { method: "POST", body: { section: "off_the_clock", model: model, data: { picks: [pick] } } })
    .then(function(d) { sel.blurb = d.output; sel.generating = false; render(); showToast("Blurb generated for " + cat.replace("otc_", "")); })
    .catch(function(e) { sel.generating = false; render(); showToast("Error: " + e.message, "error"); });
}

function renderOTC(el) {
  var hasScrapeData = !!(S.otcData && S.otcData.candidates);
  var hasOutput = !!(S.sectionOutputs.off_the_clock && S.sectionOutputs.off_the_clock.output_text);
  if (!S.sectionPhase.off_the_clock) S.sectionPhase.off_the_clock = hasOutput ? 3 : (hasScrapeData ? 2 : 1);

  var p1 = '';
  p1 += '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">';
  p1 += '<button class="btn btn-primary" onclick="runSection(\'off_the_clock\')">SCRAPE</button>';
  p1 += '<button class="btn btn-sm btn-secondary" onclick="runSection(\'classify_otc\')">Classify OTC</button>';
  if (S.loading.off_the_clock) p1 += renderSectionProgress('off_the_clock');
  var _ps = formatScrapedDate(S.lastScraped && S.lastScraped.off_the_clock);
  if (_ps) p1 += '<span class="scraped-badge">Scraped ' + _ps + '</span>';
  p1 += '</div>';

  var p2 = hasScrapeData ? renderOTCBody() : '';

  var p3 = '';
  p3 += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">';
  p3 += modelSelect("model-otc");
  p3 += '<button class="btn btn-success" onclick="proceedOTC()">' + (hasOutput ? 'Regenerate' : 'Generate') + '</button>';
  p3 += '</div>';
  p3 += outputBox("off_the_clock");

  var h = '<div class="sh"><div><h2>Off the Clock</h2><div class="sub">Eat, watch, read, wear, go - one pick per category.</div></div></div>';
  h += phasePanel('off_the_clock', 1, 'Scrape', true, hasScrapeData, p1);
  h += phasePanel('off_the_clock', 2, 'Pick each category', hasScrapeData, false, p2);
  h += phasePanel('off_the_clock', 3, 'Generate', hasScrapeData, hasOutput, p3);

  el.innerHTML = h;
  fillOutput('off_the_clock');
}

function proceedOTC() {
  var model = getModel("model-otc");
  var picks = [];
  OTC_CATS.forEach(function(cat) {
    var sel = _otcSel(cat.key);
    if (sel.mode === "custom") {
      if (!sel.blurb) return;
      picks.push({ category: cat.key, title: sel.customContent.split("\n")[0].slice(0, 80), url: sel.customUrl || "", blurb: sel.blurb });
    } else {
      var current = _otcCandidate(cat.key, sel.candidateIndex);
      if (!current) return;
      picks.push({ category: cat.key, title: current.title || current.summary || "", url: current.url || "", blurb: sel.blurb || current.summary || "" });
    }
  });
  if (!picks.length) { showToast("Pick at least one category before generating.", "error"); return; }
  S.loading.off_the_clock = true; render();
  api("/api/proceed-section", { method: "POST", body: { section: "off_the_clock", model: model, data: { picks: picks } } })
    .then(function(d) { S.sectionOutputs.off_the_clock = { output_text: d.output, model_used: d.model }; S.loading.off_the_clock = false; render(); fillOutput('off_the_clock'); showToast("Off the Clock generated"); })
    .catch(function(e) { S.loading.off_the_clock = false; render(); showToast("Error: " + e.message, "error"); });
}
```

- [ ] **Step 6: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c 'function generateOTCCustomBlurb'  # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function pickOTCCandidate'       # 1
kill %1
```
Manual: run SCRAPE on Off the Clock (or seed test data), open the page — 5 category cards each show ONE pick with a blurb textarea; click Swap on one — the other (up to) 2 scraped candidates appear as buttons; click one — it becomes the shown pick and the blurb resets to its summary; click "Add custom" — a URL + content form appears; paste content and click "Generate blurb" — a blurb appears for that category only; click "Generate" at the bottom — a combined 5-entry block appears in the output box; edit it; Mark ready turns the sidebar dot green.

- [ ] **Step 7: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3   # 130 passed (127 + 3 new), 8 failed
git add flatwhite/dashboard/state.py flatwhite/dashboard/static/index.html tests/test_otc_niche_bias.py
git commit -m "FW control room sections: Off the Clock rebuilt as 5 categories with swap + custom add + niche sourcing bias"
```

---

### Task 4: PS Top Picks — feature stories + selectable list + Mark ready

**Files:**
- Modify: `flatwhite/dashboard/api.py` (append new route after line 2163, the last line in the file)
- Modify: `flatwhite/dashboard/static/index.html` (state `S`; `renderTopPicksBody`/`renderTopPicks`/`copyTopPicks`, lines 1768-1910)
- Test: `tests/test_top_picks_recent_posts.py` (new)

**Interfaces:**
- Consumes: `flatwhite.editorial.beehiiv_picks.fetch_recent_posts(days=7)` (unchanged, returns `[{id, title, slug, publish_date, web_url}, ...]`); existing `/api/top-picks/scrape` click-ranked `picks` list; Task 1's `outputBox`/`markReady`.
- Produces: new route `GET /api/top-picks/recent-posts` → `{"posts": [...]}`; frontend `_allTopPicks()` → merged array of click-ranked picks + manually-flagged feature picks (`{url, summary, clicks: null, is_feature: true, campaign_title, campaign_url, source_domain: "feature"}`), consumed by both the render list and `copyTopPicks`/`buildTopPicksOutput`.
- **Two output paths, both reading from the same merged+selected list, doing different jobs:** `copyTopPicks()` (unchanged, line 1820) is already the exact "prior Flat White Top Picks block" format — rich HTML `<ul><li><p><strong>lead clause</strong> rest. <a>LINK</a></p></li></ul>`, copied straight to the clipboard for pasting into beehiiv. `buildTopPicksOutput()` (new) fills the plain-text `outputBox('top_picks')` textarea so Top Picks has the same editable-output-then-Mark-ready pattern as every other segment (none of the other segments' output boxes hold rich HTML either — they are all plain/markdown-ish text). Both stay available: Copy Selected for the actual beehiiv paste, Build block + Mark ready for tracking the segment as done in the running order.

- [ ] **Step 1: Write the failing test.** Create `tests/test_top_picks_recent_posts.py`:
```python
"""PS Top Picks currently only shows click-ranked links, so a FEATURE story
(no click-link, since the story runs inline in the newsletter) never
appears - the click data that does show is just the OTHER links in that
same article. This exposes the raw list of recent editions so Victor can
manually flag which ones were features and include them.
"""
from __future__ import annotations

import json

import flatwhite.editorial.beehiiv_picks as beehiiv_picks


def test_recent_posts_endpoint_returns_editions_for_feature_flagging(monkeypatch):
    fake_posts = [
        {
            "id": "p1",
            "title": "Why 'no budget' is a cop-out when negotiating pay",
            "slug": "no-budget-cop-out",
            "publish_date": "2026-07-10T00:00:00+00:00",
            "web_url": "https://thepickandscroll.beehiiv.com/p/no-budget-cop-out",
        },
    ]
    monkeypatch.setattr(beehiiv_picks, "fetch_recent_posts", lambda days=7: fake_posts)

    from flatwhite.dashboard.api import api_top_picks_recent_posts
    result = api_top_picks_recent_posts()
    data = json.loads(result.body)
    assert data["posts"] == fake_posts


def test_recent_posts_endpoint_survives_fetch_error(monkeypatch):
    def _raise(days=7):
        raise RuntimeError("beehiiv API down")
    monkeypatch.setattr(beehiiv_picks, "fetch_recent_posts", _raise)

    from flatwhite.dashboard.api import api_top_picks_recent_posts
    result = api_top_picks_recent_posts()
    assert result.status_code == 500
    data = json.loads(result.body)
    assert data["posts"] == []
```

- [ ] **Step 2: Run to confirm it fails.**
```bash
.venv/bin/python -m pytest tests/test_top_picks_recent_posts.py -v
```
Expected: FAIL — `api_top_picks_recent_posts` does not exist yet (`ImportError`).

- [ ] **Step 3: Add the route.** Append to the end of `flatwhite/dashboard/api.py` (after the `/api/top-picks/scrape` handler, line 2163):
```python


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
```

- [ ] **Step 4: Run to confirm it passes.**
```bash
.venv/bin/python -m pytest tests/test_top_picks_recent_posts.py -v
```
Expected: PASS (2 tests).

- [ ] **Step 5: Add feature-flagging + Mark ready to the frontend.** Add new state fields to `S` (index.html ~line 270): find `topPicksChecked: {},` and add directly after it:
```js
  topPicksRecentPosts: null,
  topPicksFeatureDrafts: {},   // { post_id: draftBlurbText }
  topPicksFeatureAdds: {},     // { post_id: {title, url, blurb} } — confirmed features merged into the list
```
Add a merge helper directly above `renderTopPicksBody` (line 1768):
```js
function _allTopPicks() {
  var clickPicks = (S.topPicks && S.topPicks.picks) || [];
  var features = Object.keys(S.topPicksFeatureAdds).map(function(id) {
    var f = S.topPicksFeatureAdds[id];
    return {
      url: f.url, summary: f.blurb, clicks: null, is_feature: true,
      campaign_title: f.title, campaign_url: f.url, source_domain: "feature",
    };
  });
  return clickPicks.concat(features);
}

function loadTopPicksRecentPosts() {
  S.loading.top_picks_features = true; render();
  api("/api/top-picks/recent-posts")
    .then(function(d) { S.topPicksRecentPosts = d.posts || []; S.loading.top_picks_features = false; render(); })
    .catch(function(e) { S.loading.top_picks_features = false; render(); showToast("Could not load recent editions: " + e.message, "error"); });
}

function toggleTopPicksFeatureDraft(id, checked) {
  if (checked) {
    if (S.topPicksFeatureDrafts[id] === undefined) S.topPicksFeatureDrafts[id] = "";
  } else {
    delete S.topPicksFeatureDrafts[id];
    delete S.topPicksFeatureAdds[id];
  }
  render();
}

function updateTopPicksFeatureBlurb(id, value) {
  S.topPicksFeatureDrafts[id] = value;
}

function addTopPicksFeature(id) {
  var post = (S.topPicksRecentPosts || []).find(function(p) { return p.id === id; });
  var blurb = (S.topPicksFeatureDrafts[id] || "").trim();
  if (!post || !blurb) { showToast("Write the feature's blurb first", "error"); return; }
  S.topPicksFeatureAdds[id] = { title: post.title, url: post.web_url, blurb: blurb };
  showToast("Added feature: " + post.title);
  render();
}

function renderTopPicksFeaturesPanel() {
  var h = '<div class="card mb20">';
  h += '<div style="font-weight:600;margin-bottom:8px;">Feature stories</div>';
  h += '<p style="font-size:12px;color:var(--text-3);margin:0 0 10px 0;">Features run inline with no click-tracked link, so they never show up in the click-ranked list above. Flag the ones that ran this week and write their own blurb so they can make the cut.</p>';
  if (!S.topPicksRecentPosts) {
    h += '<button class="btn btn-sm btn-secondary" onclick="loadTopPicksRecentPosts()"' + (S.loading.top_picks_features ? ' disabled' : '') + '>' + (S.loading.top_picks_features ? 'Loading…' : 'Load recent editions') + '</button>';
    h += '</div>';
    return h;
  }
  if (!S.topPicksRecentPosts.length) {
    h += '<p style="font-size:12px;color:var(--text-3);">No recent editions found.</p></div>';
    return h;
  }
  S.topPicksRecentPosts.forEach(function(post) {
    var added = S.topPicksFeatureAdds[post.id];
    h += '<div class="fr mb8" style="align-items:flex-start;gap:8px;">';
    h += '<input type="checkbox"' + (added ? " checked" : "") + ' onchange="toggleTopPicksFeatureDraft(\'' + esc(post.id) + '\',this.checked)">';
    h += '<div style="flex:1;">';
    h += '<div style="font-size:13px;font-weight:600;">' + esc(post.title) + '</div>';
    h += '<div style="font-size:11px;color:var(--text-3);margin-bottom:4px;"><a href="' + esc(post.web_url) + '" target="_blank">' + esc(post.web_url) + '</a></div>';
    if (S.topPicksFeatureDrafts[post.id] !== undefined) {
      h += '<textarea class="form-input" rows="2" placeholder="Write this feature\'s blurb..." oninput="updateTopPicksFeatureBlurb(\'' + esc(post.id) + '\',this.value)">' + esc(S.topPicksFeatureDrafts[post.id] || "") + '</textarea>';
      h += '<button class="btn btn-sm btn-success" style="margin-top:6px;" onclick="addTopPicksFeature(\'' + esc(post.id) + '\')">Add to list</button>';
    }
    h += '</div></div>';
  });
  h += '</div>';
  return h;
}

function buildTopPicksOutput() {
  var picks = _allTopPicks();
  var selected = picks.filter(function(p, i) { return S.topPicksChecked && S.topPicksChecked[i]; });
  if (!selected.length) { showToast("Select at least one pick first", "error"); return; }
  var lines = selected.map(function(p) {
    var summary = (p.summary || "").replace(/\s+/g, " ").trim();
    if (!/[.!?]$/.test(summary)) summary += ".";
    return summary + " " + (p.url || "");
  });
  var ta = $("output-top_picks");
  if (ta) ta.value = lines.join("\n\n");
}
```
Now replace `renderTopPicksBody`'s first line (`var picks = (S.topPicks && S.topPicks.picks) || [];`, line 1769) with `var picks = _allTopPicks();`, and inside its per-item loop replace the clicks display block:
```js
    h += '<div style="text-align:center;flex-shrink:0;min-width:60px;">';
    h += '<div style="font-size:24px;font-weight:700;color:var(--amber);">' + clicks + '</div>';
    h += '<div style="font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:0.5px;">clicks</div>';
    h += '</div>';
```
with:
```js
    if (p.is_feature) {
      h += '<div style="text-align:center;flex-shrink:0;min-width:60px;"><span class="chip chip-amber" style="font-size:10px;">FEATURE</span></div>';
    } else {
      h += '<div style="text-align:center;flex-shrink:0;min-width:60px;">';
      h += '<div style="font-size:24px;font-weight:700;color:var(--amber);">' + clicks + '</div>';
      h += '<div style="font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:0.5px;">clicks</div>';
      h += '</div>';
    }
```
In `copyTopPicks()` (line 1820), replace `var picks = (S.topPicks && S.topPicks.picks) || [];` (line 1821) with `var picks = _allTopPicks();`. Finally replace `renderTopPicks` (line 1891-1910):
```js
function renderTopPicks(el) {
  var hasPicks = !!(S.topPicks && S.topPicks.picks && S.topPicks.picks.length);
  var hasOutput = !!(S.sectionOutputs.top_picks && S.sectionOutputs.top_picks.output_text);
  if (!S.sectionPhase.top_picks) S.sectionPhase.top_picks = hasOutput ? 3 : (hasPicks ? 2 : 1);

  var p1 = '';
  p1 += '<div class="card mb20">';
  p1 += '<p style="font-size:13px;color:var(--text-2);margin:0 0 12px 0;">Fetches the last 7 days of Pick &amp; Scroll editions from Beehiiv and ranks all links by total click count.</p>';
  p1 += '<button class="btn btn-primary" onclick="scrapeTopPicks()">SCRAPE BEEHIIV</button>';
  if (S.loading.top_picks) p1 += ' <span class="ingest-spinner"></span>';
  if (S.lastScraped.top_picks) p1 += '<span style="font-size:11px;color:var(--text-3);margin-left:10px;">Last scraped: ' + esc(S.lastScraped.top_picks) + '</span>';
  p1 += '</div>';
  p1 += renderTopPicksFeaturesPanel();

  var p2 = renderTopPicksBody();
  p2 += '<div style="margin-top:12px;"><button class="btn btn-sm btn-secondary" onclick="buildTopPicksOutput()">Build block from selected</button></div>';

  var h = '';
  h += phasePanel('top_picks', 1, 'Scrape + flag features', true, hasPicks, p1);
  h += phasePanel('top_picks', 2, 'Select & Copy', true, false, p2);
  h += phasePanel('top_picks', 3, 'Output', true, hasOutput, outputBox('top_picks'));

  el.innerHTML = h;
  fillOutput('top_picks');
}
```

- [ ] **Step 6: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c 'function _allTopPicks'          # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function renderTopPicksFeaturesPanel'  # 1
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8500/api/top-picks/recent-posts   # 200 (or 500 if beehiiv creds absent locally — both prove the route exists)
kill %1
```
Manual: open Top Picks, click "Load recent editions" — the week's PS posts list appears with checkboxes; tick one, write its blurb, click "Add to list" — it appears in the selectable list above tagged FEATURE instead of a click count; tick it plus a couple of click-ranked picks; click "Build block from selected" — the output textarea fills with the combined block; edit it; Mark ready turns the sidebar dot green.

- [ ] **Step 7: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3   # 132 passed (130 + 2 new), 8 failed
git add flatwhite/dashboard/api.py flatwhite/dashboard/static/index.html tests/test_top_picks_recent_posts.py
git commit -m "FW control room sections: PS Top Picks includes manually-flagged feature stories, selectable list, Mark ready"
```

---

### Task 5: Stress Index (Pulse) — Regenerate label + Mark ready wiring

**Files:**
- Modify: `flatwhite/dashboard/static/index.html` (`renderPulse`, lines 836-871)

**Interfaces:**
- Consumes: Task 1's extended `outputBox('pulse')` (already called at line 862 — the Mark ready button appears automatically, no change needed there). Existing `proceedPulse()`/`openProceedModal`/`confirmAndGenerate` flow is unchanged (Pulse already generates via the context/prompt/model modal — this task only fixes the button's label).

- [ ] **Step 1: Replace the PROCEED button with a Generate/Regenerate label.** In `renderPulse` (line 836-871), replace:
```js
  p3 += '<button class="btn btn-success" onclick="proceedPulse()">PROCEED</button>';
```
with:
```js
  p3 += '<button class="btn btn-success" onclick="proceedPulse()">' + (hasOutput ? 'Regenerate' : 'Generate') + '</button>';
```
(`hasOutput` is already computed at the top of `renderPulse`, line 838 — no new variable needed.)

- [ ] **Step 2: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c "hasOutput ? 'Regenerate' : 'Generate'"   # 1
curl -s http://127.0.0.1:8500/ | grep -c 'onclick="markReady'                     # 1 (from Task 1, confirms Pulse's output box carries it)
kill %1
```
Manual: open Pulse before it has ever generated output — button reads "Generate". Run it once (through the existing prompt-preview modal, unchanged) — the button now reads "Regenerate". The output textarea is editable, Save persists edits, Mark ready turns the sidebar dot green.

- [ ] **Step 3: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3   # 132 passed, 8 failed (no Python touched this task)
git add flatwhite/dashboard/static/index.html
git commit -m "FW control room sections: Stress Index (Pulse) Generate/Regenerate label"
```

---

### Task 6: Thread of the Week — retire the scrape, paste-and-format

**Files:**
- Modify: `flatwhite/dashboard/static/index.html` (state `S`; new `renderThread`, wired into the `S.page` → renderer map)

**Interfaces:**
- Consumes: Task 1's `outputBox('thread')` / `markReady('thread')`; the existing generic `/api/section-output/thread` save path (no backend change — `save_section_output`/`load_all_section_outputs` are section-name-agnostic).
- Produces: `formatThreadBlock(draft)` → the exact FW block string; `renderThread(el)`. Does NOT re-enable `_proceed_thread` in `flatwhite/dashboard/api.py:1710` or add `"thread"` back to the `proceed_fns` dict at `api.py:1827` — per CLAUDE.md, this is pure deterministic formatting of what Victor pastes, not an LLM rewrite, so no backend call is needed at all.

- [ ] **Step 1: Add the Thread state and formatter.** Add to `S` (index.html ~line 270): find `editorialBigStory: "",` (added in Task 2) and add directly after it:
```js
  threadDraft: { title: "", url: "", preview: "", topComment: "" },
```
Add near the other pure-formatting helpers (directly below `formatScrapedDate`, ~line 381):
```js
function formatThreadBlock(d) {
  var title = (d.title || "").trim();
  var url = (d.url || "").trim();
  var preview = (d.preview || "").trim();
  var topComment = (d.topComment || "").trim();
  var lines = [];
  lines.push("#### [_**" + title + "**_](" + url + ")");
  lines.push("");
  if (preview) lines.push(preview);
  if (topComment) {
    lines.push("");
    lines.push("> _" + topComment + "_");
  }
  return lines.join("\n");
}
```

- [ ] **Step 2: Add `renderThread`.** Add directly after `formatThreadBlock`:
```js
function renderThread(el) {
  var d = S.threadDraft;
  var hasOutput = !!(S.sectionOutputs.thread && S.sectionOutputs.thread.output_text);

  var p1 = '';
  p1 += '<div style="margin-bottom:10px;"><label style="font-size:12px;color:var(--text-2);">Thread title</label>';
  p1 += '<input class="form-input" value="' + esc(d.title) + '" oninput="S.threadDraft.title=this.value"></div>';
  p1 += '<div style="margin-bottom:10px;"><label style="font-size:12px;color:var(--text-2);">Reddit URL</label>';
  p1 += '<input class="form-input" value="' + esc(d.url) + '" oninput="S.threadDraft.url=this.value"></div>';
  p1 += '<div style="margin-bottom:10px;"><label style="font-size:12px;color:var(--text-2);">Preview / excerpt</label>';
  p1 += '<textarea class="form-input" rows="3" oninput="S.threadDraft.preview=this.value">' + esc(d.preview) + '</textarea></div>';
  p1 += '<div style="margin-bottom:10px;"><label style="font-size:12px;color:var(--text-2);">Top comment</label>';
  p1 += '<textarea class="form-input" rows="2" oninput="S.threadDraft.topComment=this.value">' + esc(d.topComment) + '</textarea></div>';
  p1 += '<button class="btn btn-success" onclick="formatThread()">Format</button>';

  var h = '<div class="sh"><div><h2>Thread of the Week</h2><div class="sub">Paste the thread; the dash formats it into the FW block.</div></div></div>';
  h += phasePanel('thread', 1, 'Paste thread', true, false, p1);
  h += phasePanel('thread', 2, 'Output', true, hasOutput, outputBox('thread'));

  el.innerHTML = h;
  fillOutput('thread');
}

function formatThread() {
  if (!S.threadDraft.title.trim() || !S.threadDraft.url.trim()) {
    showToast("Add a title and URL first", "error");
    return;
  }
  var block = formatThreadBlock(S.threadDraft);
  var ta = $("output-thread");
  if (ta) ta.value = block;
  showToast("Thread formatted");
}
```

- [ ] **Step 3: Wire `thread` into the segment renderer map.** Find the placeholder Increment 1 introduced for the `thread`/`brains`/`insidetrack`/`bank`/`sources` ids:
```bash
grep -n "coming in a later increment\|coming later" flatwhite/dashboard/static/index.html
```
In that mapping, change the `thread` branch from the generic placeholder call to `renderThread(el)` (leave `brains`, `insidetrack`, `bank`, `sources` as the placeholder — those are later increments). If the map is a `switch` statement, add `case "thread": renderThread(el); break;` above the placeholder `default`; if it is an object/dictionary map of id → function, add `thread: renderThread` and remove `thread` from whatever placeholder-id set/list gates the "coming later" branch.

- [ ] **Step 4: Verify.** Boot the dashboard.
```bash
cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500 &
sleep 2
curl -s http://127.0.0.1:8500/ | grep -c 'function formatThreadBlock'   # 1
curl -s http://127.0.0.1:8500/ | grep -c 'function renderThread'       # 1
curl -s http://127.0.0.1:8500/ | grep -c '#### \[_\*\*'                # 1 (the literal template pattern)
kill %1
```
Manual: open Thread of the Week — no scrape button anywhere on the page (confirming the dead Reddit scrape stays retired), only the paste form. Fill in title `Anyone else told to "just be grateful"`, url `https://www.reddit.com/r/AusCorp/comments/abc123`, a preview paragraph, and a top comment. Click Format — the output textarea shows exactly:
```
#### [_**Anyone else told to "just be grateful"**_](https://www.reddit.com/r/AusCorp/comments/abc123)

<preview text>

> _<top comment text>_
```
Edit it if needed, click Mark ready — the sidebar dot for Thread of the Week turns green.

- [ ] **Step 5: Python suite unchanged + commit.**
```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3   # 132 passed, 8 failed (no Python touched this task)
git add flatwhite/dashboard/static/index.html
git commit -m "FW control room sections: Thread of the Week retires the dead scrape, pastes and formats the real FW block"
```

---

## Manual verification (whole increment, before done)

1. `cd /Users/victornguyen/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 127.0.0.1 --port 8500`.
2. **Editorial:** with any other segment not-ready, Write is disabled with a visible reason. Mark every other segment ready, add a big story of the week, click Write — output is skill-shaped ("Good morning AusCorp." bold hook → Big Conversation bridge → 3-item preview), editable, Mark ready works.
3. **Off the Clock:** 5 separate category cards, each with exactly one shown pick; Swap reveals the other scraped candidates; Add custom takes a URL + pasted content and generates that category's own blurb; Generate produces one combined block from whichever 5 picks are current; sourcing favours niche domains over Concrete Playground/Time Out/Guardian/SMH/Gourmet Traveller at equal relevance.
4. **PS Top Picks:** click-ranked list still works; "Load recent editions" surfaces the week's PS posts so a feature story with no click-link can be manually flagged, blurbed, and added; the merged selectable list, Build block, edit, and Mark ready all work.
5. **Stress Index (Pulse):** Generate the first time, Regenerate afterwards; output editable; Mark ready works (unchanged generation logic, only the label + Mark ready wiring changed).
6. **Thread of the Week:** no scrape action anywhere on the page; pasting title/url/preview/top comment and clicking Format produces the exact `#### [_**title**_](url)` + preview + quoted italic top comment block; editable; Mark ready works.
7. FW Python suite: `132 passed` (124 baseline + 3 Task 2 + 3 Task 3 + 2 Task 4), `8` pre-existing failures unchanged, `0` new failures.

Report the FW suite counts and "built locally on branch `fw-control-room-sections` (off `fw-control-room-shell`), NOT merged, NOT deployed (FW deploy is Victor's)."

## Notes for later increments (not this plan)

- The "benchmark chip" against `data/beehiiv_fw_ground_truth.json` lands with Assembly (Increment 7), applied to every segment's output at once, not per-page here.
- Brains Trust and Inside Track stay Increment 1's placeholder pages until Increments 5/6. Big Conversation's screenshot pipeline (topic bank, paragraph pairing, viral/tier pools) is Increments 3/4 and is untouched by this plan; `renderBigConv`/`_proceed_big_conversation` are not modified here.
