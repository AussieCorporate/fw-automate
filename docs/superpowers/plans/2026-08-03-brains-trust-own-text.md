# Brains Trust Own-Text Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Victor paste his own story into Brains Trust and draft it in the same house voice/format the angle-picker path produces, as a second, independent input path.

**Architecture:** One new early-return branch in the existing `_proceed_brains_trust` function (flatwhite/dashboard/api.py), keyed off a new `own_text` field in the request `data` dict. One new small UI block + button in the frontend that posts that field. No new endpoints, no new files.

**Tech Stack:** Python (FastAPI backend, unchanged endpoint), vanilla JS frontend, pytest.

## Global Constraints

- `own_text`, when present and non-blank, completely replaces the angle-pool prompt content — never blended with `chosen_angles`/`candidates_pool` in the same draft (spec: "instead of the research, not blended with it").
- The pre-existing `custom_prompt` full-override still takes precedence over `own_text` if both are somehow present — the new branch sits AFTER the existing `if custom_prompt:` early-return, never before it.
- The angle-picker path (`draftBrainsTrust`, `_selected_angles`, the existing prompt-building branch) is unchanged by this plan.

---

### Task 1: `_proceed_brains_trust` own-text branch

**Files:**
- Modify: `flatwhite/dashboard/api.py` (inside `_proceed_brains_trust`, ~line 2320, right after the existing `if custom_prompt:` block and before `angles = _selected_angles(data)`)
- Test: `tests/test_brains_trust_proceed.py` (append)

**Interfaces:**
- Consumes: nothing new from elsewhere; reads `data.get("own_text")`.
- Produces: nothing new consumed by later tasks — Task 2 only needs to know the field name is `"own_text"` on the `data` dict of the existing `/api/proceed-section` POST body (already documented in Task 2 directly, no cross-task type to track).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_brains_trust_proceed.py`:

```python
def test_proceed_brains_trust_drafts_from_own_text(monkeypatch):
    cap = _capture_route(monkeypatch)
    data = {"own_text": "Victor's own story about the RBA meeting."}
    out = api._proceed_brains_trust(data, "claude-sonnet-4-6")
    assert out == "Drafted Brains Trust body."
    assert cap["task_type"] == "brains_trust"
    assert "Victor's own story about the RBA meeting." in cap["prompt"]
    assert cap["model_override"] == "claude-sonnet-4-6"


def test_proceed_brains_trust_own_text_excludes_angle_pool(monkeypatch):
    cap = _capture_route(monkeypatch)
    data = {
        "own_text": "Victor's own story.",
        "chosen_pitch": "Some angle that must NOT appear",
        "candidates_pool": [{"date_iso": "2026-07-13", "pitch": "Pool pitch that must NOT appear", "angle": "x"}],
    }
    api._proceed_brains_trust(data, None)
    assert "Some angle that must NOT appear" not in cap["prompt"]
    assert "Pool pitch that must NOT appear" not in cap["prompt"]


def test_proceed_brains_trust_blank_own_text_falls_back_to_angles(monkeypatch):
    cap = _capture_route(monkeypatch)
    data = {"own_text": "   ", "chosen_pitch": "Solo angle, no pool"}
    api._proceed_brains_trust(data, None)
    assert "Solo angle, no pool" in cap["prompt"]  # fell through to the existing angle path


def test_proceed_brains_trust_custom_prompt_wins_over_own_text(monkeypatch):
    cap = _capture_route(monkeypatch)
    data = {"own_text": "Should be ignored"}
    out = api._proceed_brains_trust(data, None, custom_prompt="Write exactly this.")
    assert out == "Drafted Brains Trust body."
    assert cap["prompt"] == "Write exactly this."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_brains_trust_proceed.py -v -k own_text`
Expected: FAIL — `AttributeError`/assertion failures (the `own_text` branch doesn't exist yet, so `own_text` content never reaches the prompt and the fourth test would currently pass by coincidence since `custom_prompt` already wins — but the first three must fail).

- [ ] **Step 3: Write the implementation**

In `flatwhite/dashboard/api.py`, inside `_proceed_brains_trust`, immediately after the existing block:

```python
    if custom_prompt:
        return route(task_type="brains_trust", prompt=custom_prompt, system=BRAINS_TRUST_VOICE, model_override=override)
```

add:

```python
    own_text = (data.get("own_text") or "").strip()
    if own_text:
        prompt = (
            "Write this week's Brains Trust (also called the Economic Scoop) "
            "section for the Flat White newsletter.\n\n"
            "SOURCE MATERIAL (write from this; it replaces the research bank "
            "for this piece):\n"
            f"{own_text}\n\n"
            "Output ONLY the Brains Trust body text. No title. No sign-off. "
            "Ground every claim in the source material above; do not invent "
            "figures."
        )
        return route(task_type="brains_trust", prompt=prompt, system=BRAINS_TRUST_VOICE, model_override=override)

```

(before the existing `angles = _selected_angles(data)` line, which is unchanged.)

Also update the function's docstring `data:` block to document the new key:

```python
        "own_text": str,                 # if non-blank, drafts from this
                                          # text instead of chosen_angles/pool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_brains_trust_proceed.py -v`
Expected: all tests in the file pass (existing tests + 4 new ones), no regressions.

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/api.py tests/test_brains_trust_proceed.py
git commit -m "Brains Trust: draft from Victor's own pasted text, bypassing the angle pool"
```

---

### Task 2: Frontend "paste your own story" block

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

**Interfaces:**
- Consumes: `POST /api/proceed-section` with `section: "brains_trust"`, `data: {own_text: string}` (Task 1, unchanged endpoint).
- Produces: nothing consumed by later tasks (final task in this plan).

- [ ] **Step 1: Add state fields**

In the `S` object literal, right after the existing `brainsUsedPicks` block (~line 364-368):

```js
  brainsUsedPicks: null,     // pitches behind the CURRENTLY DISPLAYED draft, so
                             // a stale server-loaded output can't be mistaken
                             // for one made from the current selection
  brainsUsedSource: null,    // "angles" | "text" | null - which input path
                             // produced the CURRENTLY DISPLAYED draft
  brainsOwnText: "",         // Victor's pasted story, ephemeral (not saved server-side)
```

- [ ] **Step 2: Add the own-text block + button to the picker**

In `renderBrainsPicker()` (flatwhite/dashboard/static/index.html), find the end of the function — right before its final `return h;` (after the existing `if (picks.length) { ... }` block that renders the "Draft from N angles" button) — append:

```js
  h += '<div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--divider);">';
  h += '<div style="font-size:13px;color:var(--text-2);font-weight:600;margin-bottom:6px;">Or paste your own story</div>';
  h += '<textarea id="brains-own-text" rows="6" style="width:100%;font-size:13px;" placeholder="Paste your own story here to draft Brains Trust from it directly, instead of picking angles above." oninput="S.brainsOwnText = this.value;">' + esc(S.brainsOwnText || '') + '</textarea>';
  h += '<div style="margin-top:8px;">';
  h += '<button class="btn btn-primary" onclick="draftBrainsTrustFromText()"' + (S.brainsDrafting || !(S.brainsOwnText || '').trim() ? ' disabled' : '') + '>' + (S.brainsDrafting ? "Drafting…" : "Draft from my text") + '</button>';
  h += '</div>';
  h += '</div>';
```

(Reusing `S.brainsDrafting` so a draft-in-flight from either path disables both buttons — only one draft runs at a time regardless of source.)

- [ ] **Step 3: Add `draftBrainsTrustFromText()`**

Immediately after the existing `draftBrainsTrust()` function (ends ~line 1153), add:

```js
function draftBrainsTrustFromText() {
  var text = (S.brainsOwnText || "").trim();
  if (!text) return;
  S.brainsDrafting = true;
  render();
  api("/api/proceed-section", {
    method: "POST",
    body: {
      section: "brains_trust",
      model: getModel("model-brains_trust"),
      data: { own_text: text },
    },
  }).then(function(d) {
    S.brainsDrafting = false;
    S.brainsUsedSource = "text";
    S.brainsUsedPicks = null;
    S.sectionOutputs.brains_trust = { output_text: d.output, model_used: d.model };
    S.sectionPhase.brains_trust = 2;
    render();
    fillOutput('brains_trust');
    showToast("Brains Trust drafted from your text");
  }).catch(function(e) {
    S.brainsDrafting = false;
    render();
    showToast("Error: " + e.message, "error");
  });
}
```

- [ ] **Step 4: Set `brainsUsedSource` on the existing angle-pick draft path too**

In the existing `draftBrainsTrust()` function, find this line:

```js
    S.brainsUsedPicks = (S.brainsPicks || []).map(function(p) { return p.pitch; });
```

and add immediately after it:

```js
    S.brainsUsedSource = "angles";
```

- [ ] **Step 5: Update the "drafted from" display line**

In `renderBrains(el)`, find:

```js
  if (hasOutput) {
    var used = S.brainsUsedPicks || [];
    p2 += '<div style="font-size:12px;color:var(--text-3);margin-bottom:8px;">';
    p2 += used.length
      ? 'Drafted from ' + used.length + ' angle' + (used.length > 1 ? 's' : '') + ': ' + esc(used.join('  |  '))
      : 'This draft was loaded from a previous session, so the angles behind it are not recorded. Re-draft to be sure it matches your current selection.';
```

Replace the `p2 += used.length ? ... : ...;` ternary with:

```js
    p2 += S.brainsUsedSource === "text"
      ? 'Drafted from your own pasted text.'
      : used.length
        ? 'Drafted from ' + used.length + ' angle' + (used.length > 1 ? 's' : '') + ': ' + esc(used.join('  |  '))
        : 'This draft was loaded from a previous session, so the angles/text behind it are not recorded. Re-draft to be sure it matches your current selection.';
```

(The trailing `p2 += '</div>';` and everything after stays unchanged.)

- [ ] **Step 6: Manual verification**

Run: `cd ~/Documents/MISC/FW && .venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8600` (port 8600, not 8500, to avoid colliding with Victor's real running dashboard).

Open http://localhost:8600/, navigate to Brains Trust, and confirm:
1. A "Or paste your own story" textarea + "Draft from my text" button appear below the angle list, in a card visually consistent with the rest of the phase-1 panel.
2. The button is disabled when the textarea is empty, enabled once text is typed.
3. Typing text and clicking Draft calls `/api/proceed-section` with `data: {own_text: "..."}` (confirm via the Network tab if available, or `curl -s -X POST http://localhost:8600/api/proceed-section -H "Content-Type: application/json" -d '{"section":"brains_trust","data":{"own_text":"A short test story about interest rates."}}' | python3 -m json.tool` — this makes a REAL Claude API call, small and cheap, confirm it returns Brains-Trust-shaped body text).
4. After drafting from text, the output panel shows "Drafted from your own pasted text." (not an angle count).
5. Picking angles and drafting via the existing button still shows "Drafted from N angle(s): ..." as before (no regression).

Stop the server (Ctrl-C) when done.

- [ ] **Step 7: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "Brains Trust: add paste-your-own-story input path to the frontend"
```

---

## Self-Review Notes

- **Spec coverage:** own_text branch + precedence over angle pool (Task 1), custom_prompt still wins (Task 1), UI block + button (Task 2), used-source tracking/display (Task 2) — all covered.
- **Type consistency:** `own_text` is a plain string key on the same `data` dict both tasks reference; no shape mismatch between what Task 1's backend reads and what Task 2's frontend sends.
- **No placeholders:** all steps contain complete, runnable code.
