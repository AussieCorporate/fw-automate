# Flat White: make the model picker work, and cap Off the Clock — design

Date: 2026-07-12
Status: awaiting Victor's review

## Problem

Two bugs make every Flat White edition worse and force heavy manual editing.
Both verified in the code on 2026-07-12.

**1. The dashboard model picker does nothing.** `flatwhite/model_router.py::route`
accepts `model_override`, but every `route(...)` call inside the `_proceed_*`
functions in `flatwhite/dashboard/api.py` omits it. `/api/proceed-section`
(line 2125) reads the `model` field from the request and passes it into each
`_proceed_*`, and those functions carry it as an unused `model` parameter. So
whatever model Victor selects, the segment is always written by the hardcoded
default in `DEFAULT_MODEL_BY_TASK` (Sonnet 4.6 for editorial/summary/big
conversation, Gemini Flash for classification). This is the most likely meaning
of "the output sucks because we're using the wrong models": the choice was never
applied.

**2. Off the Clock selection is uncapped.** `config.yaml` sets
`off_the_clock.candidates_per_category: 3`, and no code reads it.
`flatwhite/dashboard/state.py::load_otc_candidates` says in its own docstring
"Returns all candidates (no cap)". The editor scrolls a dumping ground of every
scraped item across five categories instead of a ranked shortlist. This is the
"spits out too many, too broad" problem.

## Design

Two small, self-contained fixes. No behaviour changes beyond these two.

### Fix 1: apply the selected model

The untrusted value enters at the dashboard boundary, so validate it there.

Add one helper in `flatwhite/dashboard/api.py`:

```python
from flatwhite.model_router import list_available_models

def _safe_override(model: str | None) -> str | None:
    """The picker's value, but only if it names a model that actually has an API
    key. Anything else (blank, unknown, or a model whose key isn't set) falls
    back to the task default, because route() raises on an unusable model_id."""
    if not model:
        return None
    available = {m["id"] for m in list_available_models()}
    return model if model in available else None
```

Then in each `_proceed_*` function, compute `override = _safe_override(model)`
once at the top and pass `model_override=override` to every `route(...)` call in
that function. The functions and their route call-sites (from the code, 2026-07-12):
`_proceed_pulse` (1714, 1792), `_proceed_big_conversation` (1896, 1911),
`_proceed_finds` (1919, 1935), `_proceed_thread` (1943, 1959),
`_proceed_amp_finest` (1967, 1981) [being decommissioned separately; fix anyway
so it is not a landmine], `_proceed_off_the_clock` (1989, 2029),
`_proceed_editorial` (2037, 2051), `_proceed_lobby` (2059, 2120) [also
decommissioned separately].

Validating against `list_available_models()` (which filters `MODEL_REGISTRY` by
configured API key) means picking a model whose key is not set falls back to the
default rather than raising `ValueError: No API key configured` mid-segment.

**This does not change any default.** When Victor picks nothing, behaviour is
exactly as today. When he picks a valid model, that model writes the segment.

### Fix 2: cap Off the Clock candidates

In `load_otc_candidates`, read the configured cap and truncate each category.
The rows are already `ORDER BY weighted_composite DESC` and deduped by title, so
truncating keeps the top N per category.

```python
# read once, near the top of the function
import yaml
with open(_config_path()) as f:
    cap = int(yaml.safe_load(f).get("off_the_clock", {}).get("candidates_per_category", 3))
...
# after the dedup loop
return {section: items[:cap] for section, items in grouped.items()}
```

Use the same config-path resolution the rest of the package uses (e.g. the
pattern in `flatwhite/editorial/off_the_clock.py::_load_config`). The default of
3 matches the existing config value; if the key is missing, 3.

## Non-goals

- **No change to default models.** Once the picker works, Victor chooses per
  edition. Retuning the standing defaults is a separate decision he makes after
  he can finally compare models.
- **No UI change.** The dashboard already renders a model picker; this only makes
  its value take effect. (If the picker's option list is stale, that is a
  follow-up, not this.)
- **Big Conversation is untouched here.** Retiring Flat White's automated Big
  Conversation and wiring in the Instagram-screenshotter output is a separate,
  larger increment.
- **The Finds pool cap is deferred.** `load_curated_items_by_section` is also
  uncapped, but has no existing config key and no agreed number. Off the Clock
  is the worst offender and has a real configured cap, so it goes first. Finds
  is a fast follow, flagged here so it is not forgotten.
- **Decommissioning segments (Lobby, Whispers, AMP's Finest, Events) is a
  separate increment.** Fix 1 still touches their `_proceed_*` functions so the
  model bug is not left as a landmine if their removal slips.

## Verification

FW uses pytest via `.venv/bin/python -m pytest` (system python is 3.9 and
breaks — always the venv).

**Fix 1, no network:** monkeypatch `flatwhite.dashboard.api.route` to capture its
kwargs. Assert:
- `_proceed_off_the_clock(data, model="claude-opus-4-6")` calls `route` with
  `model_override="claude-opus-4-6"` (given the key is configured in the test
  env, or stub `list_available_models`).
- `model="not-a-real-model"` yields `model_override=None`.
- `model=None` yields `model_override=None`.
- `model=""` yields `model_override=None`.

**Fix 2:** seed a temp DB (follow `tests/conftest.py`) with 6 OTC items in one
category, assert `load_otc_candidates()` returns 3 for that category, and that
they are the 3 highest `weighted_composite`. Assert a category with 2 items
returns 2 (cap is a ceiling, not a floor).

**Manual, before calling it done:** fire up the dashboard
(`.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500`),
pick a distinct model on a segment, and confirm from the server log that the
chosen `model_id` is the one that ran. Confirm Off the Clock now shows at most 3
per category.

## Definition of done (per FW CLAUDE.md)

FW's real production is the GCP VM `flatwhite`. Per the project's own rule, a fix
that exists only locally is NOT done — it must be committed, pushed, deployed via
`deploy/gcp_deploy.sh`, and cron-enabled.

**I can build, test, and commit locally. I cannot deploy** (needs gcloud auth and
is Victor's call). This work will be reported as "fixed and committed locally,
NOT yet deployed," with the deploy handed to Victor. Do not report it as done
until it is on the VM.

## Risks

- **A picked model with no API key** would crash `route()` — mitigated by
  validating against `list_available_models()`, not just `MODEL_REGISTRY`.
- **Config path resolution** differs across the package; use the existing
  `off_the_clock` loader pattern so the cap reads from the same file the rest of
  the app uses, not a stray copy.
- **The cap is a product number.** 3 per category is the configured value and the
  default here. If Victor wants a different shortlist size it is a one-line
  config change, not a code change.

## Files touched

| File | Change |
|---|---|
| `flatwhite/dashboard/api.py` | add `_safe_override`; pass `model_override` in every `_proceed_*` route call |
| `flatwhite/dashboard/state.py` | read `candidates_per_category`, truncate each OTC category in `load_otc_candidates` |
| `tests/test_model_picker.py` | new: the model_override plumbing tests |
| `tests/test_otc_cap.py` | new: the per-category cap tests |
