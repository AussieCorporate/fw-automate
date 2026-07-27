# Brains Trust — select several angles, write the converged view

**Date:** 2026-07-27
**Status:** approved, not yet implemented

## Problem

The Brains Trust picker is single-select. `S.brainsChosen` holds one angle
object; clicking a row replaces it. `_proceed_brains_trust` then builds a prompt
around that one angle and hands the rest of the 3-week pool over with the
instruction to "consolidate whatever is relevant to the chosen angle above;
ignore anything unrelated".

That does not match how Victor works. He picks **by topic**: several angles from
the research bank that are facets of the same story. He wants a piece that finds
the view reconciling them and writes that, with every angle he ticked addressed.

Today he cannot express that. He can pick exactly one angle and hope the model
notices the related ones sitting in the pool — and "ignore anything unrelated"
explicitly licenses it to drop them.

## What we are building

Multi-select with ordered picks, and a drafting prompt that synthesises rather
than sequences.

### Picking

Clicking an angle toggles it. Selected rows carry a number badge showing tick
order; removing one renumbers the rest. The first pick is the **anchor** — the
angle closest to the point Victor is chasing — and emphasis follows the order.

The anchor is *not* automatically the opener. The opener is the converged
finding, which may sit across two angles rather than in any one of them.

### Drafting

`_proceed_brains_trust` takes an ordered list of chosen angles and asks for one
narrative built on the view that reconciles them:

- Open on the **converged finding**, not on the anchor angle restated.
- Address **every** selected angle. This replaces today's "ignore anything
  unrelated", which applied to the pool and let selected material be dropped.
- Lean the synthesis toward the anchor; later picks carry less weight.
- The 3-week pool still travels with the request as grounding, and *that* is
  where "use what's relevant, ignore the rest" still applies.

### Non-convergence safeguard

If the selected angles share no genuine thesis — a housing angle and an airline
angle — the draft must say so plainly rather than manufacture a connective
thread. Inventing a link produces exactly the reframe-and-pivot filler the house
voice rules ban, and it would be worse than an honest "these don't converge".

The model is instructed to lead with that statement, name the topics it was
given, and then write the strongest single piece it can from the anchor alone.
Victor sees immediately that his selection was the problem, and still gets
something usable.

### Source PDFs

The "email me the source research" button pools `source_pdf_ids` across all
selected angles, deduplicated and order-preserving. The button's count shows the
combined total. The email's subject line uses the anchor angle's pitch.

### Length

Unchanged: the house format is 3-5 paragraphs, 260-380 words. Two or three
angles fit comfortably; five would give each roughly 70 words and read thin.
This is guidance for Victor, not a code limit — the existing word-count chip
already shows when a draft runs long. Do not silently widen the format.

## Compatibility

`_proceed_brains_trust` must keep accepting the current single-angle payload
(`chosen_pitch`, `chosen_angle`, `chosen_why_tac`). Both shapes normalise to one
ordered list internally. This keeps `tests/test_brains_trust_proceed.py` passing
unchanged and means a stale browser tab cannot break drafting.

The `data` contract becomes:

```
{
  "chosen_angles": [                  # NEW, ordered, anchor first
    {"pitch": str, "angle": str, "why_tac": str, "date_iso": str}
  ],
  "chosen_pitch": str,                # legacy single-angle form, still accepted
  "chosen_angle": str,
  "chosen_why_tac": str,
  "candidates_pool": [ ... ]          # unchanged
}
```

When `chosen_angles` is present and non-empty it wins; otherwise the legacy keys
are used to build a one-item list.

## Testing

1. **Legacy payload still works.** The existing single-angle tests pass with no
   edits — this is the compatibility guarantee, so they must not be modified.
2. **Ordered multi-angle prompt.** All selected pitches appear in the prompt, in
   tick order, with the anchor marked as such.
3. **Every angle is required, not optional.** The prompt instructs that each
   selected angle be addressed, and does not carry the old "ignore anything
   unrelated" wording over the *selected* angles.
4. **Convergence instruction present** whenever more than one angle is selected,
   and absent for a single angle (nothing to converge).
5. **Malformed entries are skipped**: non-dicts, and entries with a blank or
   missing `pitch`, never reach the prompt. An all-malformed list falls back to
   the legacy keys rather than producing an empty prompt.
6. **PDF pooling** deduplicates across angles, preserves order, and survives
   angles that carry no ids.
7. **UI toggle behaviour**: clicking an unpicked angle appends it, clicking a
   picked one removes it and renumbers, and the draft button is hidden at zero
   picks.

## Out of scope

- Drag-to-reorder picks. Tick order is the ordering mechanism; untick and
  re-tick to change it.
- Widening the 260-380 word house format.
- Any change to the angle *source* — that is the separate weekly-research-angles
  work in the Trading Strategy project.
- Persisting selections across page reloads.
