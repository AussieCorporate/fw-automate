# Brains Trust — draft from Victor's own pasted text

**Date:** 2026-08-03
**Status:** approved, not yet implemented

## Problem

`_proceed_brains_trust` (flatwhite/dashboard/api.py) only ever drafts from
angles picked out of the Trading Strategy research pool (`chosen_angles` +
`candidates_pool`). Victor sometimes already has his own story to write up —
he wants to paste that in and get the same house-voice, same-format Brains
Trust output the angle-picker path produces, without going through the
angle pool at all.

The existing generic "Proceed modal" (`openProceedModal`, `custom_prompt`)
already lets any section's whole prompt be hand-edited, but it isn't wired
into Brains Trust's UI, and using it would mean Victor editing a full
auto-built prompt blob by hand (finding and replacing the research-bank
section while keeping the surrounding instructions intact) — too fiddly for
a "paste my story in" ask. This needs a dedicated, simple second input path.

## What we are building

### Backend

In `_proceed_brains_trust` (flatwhite/dashboard/api.py), add one new `data`
key, `own_text`. When present and non-blank, it takes over the whole
drafting prompt (skips `_selected_angles`/pool entirely — "instead of the
research", not blended with it):

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

This sits after the existing `custom_prompt` early-return and before
`angles = _selected_angles(data)`, so `custom_prompt` (full manual override)
still wins if both are somehow present, and the angle-pick path is
completely unchanged when `own_text` is absent.

### Frontend

In `renderBrainsPicker()` (flatwhite/dashboard/static/index.html), below the
existing angle list and its "Draft from N angles" button, add a small
second block:

- A label: "Or paste your own story"
- A `<textarea>` bound to `S.brainsOwnText` (persisted in state like
  `S.brainsPicks`, not saved server-side — same lifetime as an in-progress
  pick)
- A button, "Draft from my text", enabled only when the textarea is
  non-blank, calling a new `draftBrainsTrustFromText()` function

`draftBrainsTrustFromText()` mirrors `draftBrainsTrust()`'s shape exactly
(same loading flag reused — `S.brainsDrafting` — since only one draft runs
at a time regardless of source), but posts `data: {own_text: S.brainsOwnText}`
and no `chosen_angles`/`candidates_pool`.

### Tracking which source produced the visible draft

`S.brainsUsedPicks` currently drives the "Drafted from N angle(s): ..."
line under the output. Add `S.brainsUsedSource` (`"angles" | "text" | null`),
set to `"angles"` by `draftBrainsTrust()` and `"text"` by
`draftBrainsTrustFromText()`. The existing render block becomes:

- `brainsUsedSource === "text"` → "Drafted from your own pasted text."
- `brainsUsedSource === "angles"` and `brainsUsedPicks.length` → existing
  "Drafted from N angle(s): ..." line, unchanged
- neither → existing "loaded from a previous session" fallback, unchanged

## Out of scope

- Any change to the angle-picker path itself, `_selected_angles`,
  `custom_prompt`, or the generic Proceed modal.
- Persisting `own_text` server-side or across page reloads — same
  ephemeral lifetime as an in-progress angle selection.
- Combining pasted text WITH picked angles in one draft (explicitly
  "instead of", per the ask).

## Testing

1. `_proceed_brains_trust` with `own_text` set and `chosen_angles` also
   present: `own_text` wins, no angle/pool text appears in the prompt sent
   to `route(...)`.
2. `_proceed_brains_trust` with `own_text` blank/whitespace-only: falls
   through to the existing angle-pick behaviour unchanged (regression
   guard on the existing tests already covering that path).
3. `_proceed_brains_trust` with both `custom_prompt` and `own_text` set:
   `custom_prompt` wins (existing early-return is untouched, sits before
   the new branch).
