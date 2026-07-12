# Flat White: model picker + OTC cap — implementation plan

> Execute with TDD. Each task: failing test first, run it, implement, re-run, commit.

**Goal:** Make the dashboard model picker actually apply the selected model, and cap Off the Clock candidates to the configured `candidates_per_category`.

**Spec:** `docs/superpowers/specs/2026-07-12-fw-model-picker-and-otc-cap-design.md`

## Global constraints

- Always use the venv python: `.venv/bin/python`. System python is 3.9 and breaks.
- Test command: `.venv/bin/python -m pytest -q`.
- No em dashes in any reader-facing string.
- Do NOT deploy (needs gcloud auth, is Victor's call). Do NOT push. Commit locally only. This is "fixed locally, NOT deployed."
- Do not change default models, the UI, Big Conversation, or decommission any segment. Only the two fixes below.
- Work on a branch: `git checkout -b fw-picker-and-otc-cap`.

---

### Task 1: the model picker applies the selected model

**Files:** `flatwhite/dashboard/api.py`; new `tests/test_model_picker.py`.

`flatwhite/model_router.py::route(task_type, prompt, system="", model_override=None)`
already honours `model_override`, but the `_proceed_*` functions never pass it.
`list_available_models()` returns models whose API key is configured.

- [ ] **Step 1 — failing test.** `tests/test_model_picker.py`:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.dashboard.api as api


def _capture(monkeypatch, available=("claude-opus-4-6", "claude-sonnet-4-6")):
    captured = {}
    def fake_route(task_type, prompt, system="", model_override=None):
        captured["model_override"] = model_override
        return "written segment"
    monkeypatch.setattr(api, "route", fake_route)
    monkeypatch.setattr(api, "list_available_models",
                        lambda: [{"id": m} for m in available])
    return captured


def test_selected_model_reaches_route(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_off_the_clock({}, "claude-opus-4-6")
    assert cap["model_override"] == "claude-opus-4-6"


def test_unknown_model_falls_back_to_default(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_off_the_clock({}, "not-a-real-model")
    assert cap["model_override"] is None


def test_model_with_no_api_key_falls_back(monkeypatch):
    cap = _capture(monkeypatch, available=("claude-sonnet-4-6",))
    api._proceed_off_the_clock({}, "gpt-5.4")   # not in available -> no key
    assert cap["model_override"] is None


def test_no_selection_uses_default(monkeypatch):
    cap = _capture(monkeypatch)
    api._proceed_off_the_clock({}, None)
    assert cap["model_override"] is None
    cap2 = _capture(monkeypatch)
    api._proceed_off_the_clock({}, "")
    assert cap2["model_override"] is None
```

Note: `_proceed_off_the_clock({}, ...)` with an empty data dict may need the
function to reach a `route` call. If the empty-dict path returns early before
`route`, pass the minimal `data` the function needs (read the function to see),
or target `_proceed_editorial`/`_proceed_finds` — pick whichever `_proceed_*`
reaches `route` with the least fixture. The assertion is the same: the captured
`model_override` equals the validated selection.

- [ ] **Step 2 — run, watch fail** (`route` called with no `model_override`, so
  `captured` stays empty → KeyError, or the helper doesn't exist).

- [ ] **Step 3 — implement.** In `flatwhite/dashboard/api.py`, add near the top
  (after imports; ensure `list_available_models` is imported from
  `flatwhite.model_router`):

```python
def _safe_override(model: str | None) -> str | None:
    """The picker's value, but only if it names a model with a configured API
    key. Blank/unknown/keyless -> None, so route() uses the task default instead
    of raising on an unusable model_id."""
    if not model:
        return None
    return model if model in {m["id"] for m in list_available_models()} else None
```

  Then in EVERY `_proceed_*` function (`_proceed_pulse`, `_proceed_big_conversation`,
  `_proceed_finds`, `_proceed_thread`, `_proceed_amp_finest`,
  `_proceed_off_the_clock`, `_proceed_editorial`, `_proceed_lobby`): add
  `override = _safe_override(model)` at the top and pass `model_override=override`
  to every `route(...)` call in that function (both the custom_prompt branch and
  the main branch). Change nothing else.

- [ ] **Step 4 — run, pass.**

- [ ] **Step 5 — commit.** `git add flatwhite/dashboard/api.py tests/test_model_picker.py && git commit -m "Apply the dashboard's selected model in every segment (was ignored)"`

---

### Task 2: cap Off the Clock candidates per category

**Files:** `flatwhite/dashboard/state.py`; new `tests/test_otc_cap.py`.

`load_otc_candidates` returns all rows grouped by category, already
`ORDER BY weighted_composite DESC` and deduped. Config
`off_the_clock.candidates_per_category` (default 3) is unread.

- [ ] **Step 1 — failing test.** `tests/test_otc_cap.py`. Follow `tests/conftest.py`
  for the temp-DB fixture. Seed one category (`otc_eating`) with 6 curated items
  at descending `weighted_composite`, and a second category (`otc_watching`) with
  2 items. Assert:

```python
def test_otc_capped_to_three_per_category(...):
    grouped = load_otc_candidates(week_iso=TEST_WEEK)
    assert len(grouped["otc_eating"]) == 3
    # the 3 kept are the 3 highest weighted_composite
    scores = [row["weighted_composite"] for row in grouped["otc_eating"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] >= scores[-1]

def test_cap_is_a_ceiling_not_a_floor(...):
    grouped = load_otc_candidates(week_iso=TEST_WEEK)
    assert len(grouped["otc_watching"]) == 2   # fewer than cap: unchanged
```

  Read `conftest.py` and an existing DB test (e.g. `tests/test_engagement_update.py`
  or `test_backfill.py`) to seed `raw_items` + `curated_items` correctly.

- [ ] **Step 2 — run, watch fail** (returns 6, not 3).

- [ ] **Step 3 — implement.** In `load_otc_candidates`, read the cap using the
  same config-path resolution `flatwhite/editorial/off_the_clock.py::_load_config`
  uses (do not hardcode a path), then truncate each category before returning:

```python
    cap = int(_otc_config().get("candidates_per_category", 3))
    ...
    return {section: items[:cap] for section, items in grouped.items()}
```

  Add a small `_otc_config()` reading `config.yaml`'s `off_the_clock` block, or
  reuse the existing loader if importable without a circular import. Default 3 if
  the key is absent.

- [ ] **Step 4 — run, pass.**

- [ ] **Step 5 — full suite.** `.venv/bin/python -m pytest -q`. Report the exact
  pass/fail count. Do not claim a clean run you have not seen. If any pre-existing
  test was already failing before this work, say so and distinguish it from
  anything caused here.

- [ ] **Step 6 — commit.** `git add flatwhite/dashboard/state.py tests/test_otc_cap.py && git commit -m "Enforce off_the_clock.candidates_per_category (was unread; list was uncapped)"`

---

## After both tasks

- Report the full-suite count and "fixed and committed locally on branch
  `fw-picker-and-otc-cap`, NOT deployed."
- Deploy is Victor's: `deploy/gcp_deploy.sh` to the GCP VM `flatwhite`, then cron.
