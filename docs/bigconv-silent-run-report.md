# Big Conversation "silent run" — root cause, fix, and verification

Victor ran the Big Conversation skill on "Offer Withdrawn After Negotiation".
The dashboard accepted the run (200 OK), but the topic page then showed "No
piece drafted yet" and the segment showed "Not ready" — indistinguishable
from never having run it at all.

## Root cause 1 (the actual bug): piece detection, not generation

The run genuinely succeeded. Direct evidence, found before any fix was made:

- `flatwhite/dashboard/skill_runner.py` keeps every run (including finished
  ones) in an in-memory dict for the life of the dashboard process. The
  dashboard process had been running continuously since Friday (no restart
  in between), so the original run record was still there. Querying it
  directly (`GET /api/skill-run/6789e89897b9`) showed `"status": "done"`
  with the full, real piece text in the output, ending in the required
  `BIG_CONVERSATION_DONE` marker.
- The piece file and its assets folder were both genuinely on disk:
  `~/Documents/MISC/instagram-dm-screenshotter/output/_Offer_Withdrawn_After_Negotiation_BIG_CONVERSATION.md`
  and `.../Offer Withdrawn After Negotiation/_BIG_CONVERSATION_assets/` with
  17 correctly renamed screenshots (`p1_1_...png` etc).

So the skill ran, wrote real output, and the dashboard still said nothing
existed. The break was in
`flatwhite/dashboard/big_conversation_bank.py:find_piece_markdown`, which
has to guess which `_*_BIG_CONVERSATION.md` file at the output root belongs
to a given topic folder (the skill picks its own abbreviated filename, e.g.
`_KIDS_OFFICE_BIG_CONVERSATION.md` for "Kids in the Office" — not derivable
from the folder name). The old heuristic searched the piece text for one
exact sentence: `` Assets in `<topic>/_BIG_CONVERSATION_assets/`. `` That
sentence is **not** part of the big-conversation skill's actual output
contract — `SKILL.md` step 6 only requires it in the skill's spoken reply,
not the file — and it is inconsistently emitted by the model. Checking all
8 real pieces on disk:

| Piece | Contains the sentence? |
|---|---|
| Kids in the Office | yes |
| Lunch w your team or not | yes |
| Manager Pet Names | yes |
| Mental Health at Big Companies | yes |
| PIP Term Length | yes |
| Return From Parental Leave | yes |
| Tight Jobs Market & HR Vetting | yes |
| **Conference Room Sharing** | **no** |
| **Offer Withdrawn After Negotiation** | **no** |

Two real, already-published-quality pieces were silently invisible to the
dashboard before this fix — not just today's topic.

A second, related format-drift bug was found during verification: the
piece's own `THE BIG CONVERSATION` header line is decorated inconsistently
across runs (plain text, `**bold**`, `# H1`, `# H1 — <topic suffix>`) — 6 of
8 real files use a form the old header-matching regex didn't recognise, so
the header line was mistaken for the headline, which shifted every real
paragraph out by one and silently dropped the actual last paragraph.

## Root cause 2 (the honesty gap): a finished run could still look silent

Independent of the detection bug, the run's outcome could vanish for
structural reasons even if detection worked perfectly:

- `skill_runner.get_active_by_key` only ever reports a run while its status
  is `queued`/`running`. The instant a run finishes (done *or* failed), it
  drops out of "active" and `/api/big-conversation/topic/{topic}/run-status`
  went back to reporting exactly the same shape as "never processed" —
  `{"active": false, "run_id": null, "status": null}`.
- The frontend (`pollBigConvRun` in `static/index.html`) compounded this: the
  moment the skill-run poll saw `status: "done"`, it immediately cleared
  `S.bigConvRun = null` and only *then* reloaded the topic detail. If
  detection failed (root cause 1) or any future edge case slipped through,
  there was no run state left to show anything other than the generic "No
  piece drafted yet" — even though a toast reading "Big Conversation ready"
  may have flashed moments earlier.
- All run history lived in memory only, so a dashboard restart (a real risk
  — per this repo's own CLAUDE.md, "The dashboard is NOT a service — it only
  runs while this process is alive") would erase every trace of a run that
  had, in fact, succeeded.

This is why the reported symptom ("looked ready, then went silent") matched
the log exactly: the browser polled `/api/skill-run/6789e89897b9` about 120
times while the real run was in progress, then simply moved on to the topic
page once it saw "done" — with nothing left to show for it once detection
came back empty.

## What was fixed

1. **`find_piece_markdown` rewritten to match by content, not one sentence**
   (`flatwhite/dashboard/big_conversation_bank.py`). It now reads the
   handles baked into `<topic>/_BIG_CONVERSATION_assets/`'s own renamed
   filenames (`p<n>_<rank>_<handle>.png`) and finds the `_*_BIG_CONVERSATION.md`
   that quotes back a majority of those handles — true regardless of which
   of the three real citation styles the model used. Verified against
   every real topic folder in the actual Instagram output directory: 13/13
   processed topics matched correctly, zero false cross-matches, and the two
   previously-invisible pieces (Offer Withdrawn After Negotiation,
   Conference Room Sharing) now detect correctly.
2. **`parse_piece_markdown` header matching loosened** to accept the header
   line with or without `**bold**`/`# H1` decoration and an optional
   `— <topic>` suffix, so the headline and paragraph split is correct for
   all 8 real pieces, not just the 2 that happened to use one exact form.
3. **Run outcomes are now persisted** (`flatwhite/dashboard/state.py`, new
   `skill_run_state` table, `save_skill_run_outcome` / `load_skill_run_outcome`,
   wired via the run's existing `on_complete` hook in `api.py`). The
   `run-status` endpoint now reports the last known outcome (`done` /
   `failed` + plain-English error) even after the run drops out of the
   in-memory active set, or the dashboard process restarts.
4. **Frontend now confirms before declaring success**
   (`flatwhite/dashboard/static/index.html`): `pollBigConvRun` loads the
   topic detail before clearing the run banner, and only shows "ready" if
   the piece was actually found. If a run finished but no piece was found
   (belt-and-braces, in case detection ever mismatches again), the UI shows
   a plain-English message — "The last run finished, but the dashboard
   couldn't find the piece it wrote for this topic..." — with a Try Again
   button, instead of the generic "No piece drafted yet" that is
   indistinguishable from never having tried. The same honest state is
   reconstructed when reopening a topic after navigating away (via the
   persisted outcome from #3).

One item flagged, not fixed: the `big_conversation_topic_state` DB table
Victor's earlier notes referenced a "processed" field on — it doesn't have
one. It only tracks `archived`/`archived_at`. "Deloitte Director of Purpose"
showing `archived=1` there is unrelated to piece-drafted state; that topic
genuinely has no `_BIG_CONVERSATION_assets/` folder on disk, so it correctly
shows unprocessed. No bug there — just a mislabelled field in the earlier
investigation notes.

## Verification performed

- **Root cause 1, against real production data** (no code changes to real
  files, read-only): `find_piece_markdown` and `parse_piece_markdown` now
  correctly detect and parse all 8 real pieces on disk, including the two
  that were previously invisible. Confirmed live through the running
  dashboard after restart: `GET /api/big-conversation/topic/Offer Withdrawn
  After Negotiation` now returns `processed: true`, the correct headline
  ("The offer was never approved."), 6 paragraph blocks with the right
  screenshots attached. **A real, already-drafted piece is now visible in
  the dashboard for this topic** — using the run Victor already paid for,
  no new generation triggered (per his instruction to hold off while the
  generation prompts are reworked).
- **Root cause 2 plumbing, via stub (no real Claude call)**: a scratch
  script drove the exact production endpoint functions
  (`api_run_big_conversation` → `api_skill_run_status` →
  `api_big_conversation_run_status` → `api_big_conversation_topic`) against
  a temporary DB and temporary output folder, with `_claude_bin` swapped for
  a local stub script.
  - **Success stub** (writes a piece + assets, prints the marker, exits 0):
    run accepted → `run-status` shows `active: true, status: running`
    immediately → skill-run reaches `done` → `run-status` still correctly
    reports `done` even after leaving the active set → topic detail shows
    `processed: true` with the right headline/paragraph/screenshot. Passed.
  - **Failure stub** (exits 1, no marker): run accepted → `run-status` shows
    `active: true, status: running` → skill-run reaches `failed` with
    "The skill run failed (exit code 1)..." → `run-status` still correctly
    reports `failed` with that reason after leaving the active set → topic
    detail correctly stays `processed: false`. Passed.
- **Automated tests**: added/updated in `tests/test_big_conversation_bank.py`,
  `tests/test_big_conversation_api.py`, `tests/test_big_conversation_state.py`
  (new regression tests reproducing both real bugs before the fix, all now
  passing). Full suite: `376 passed, 8 failed` — the 8 failures are
  pre-existing and unrelated (`test_normalise.py`, `test_pipeline.py`
  anomaly-detection tests), confirmed identical on `main` before any of
  this work via `git stash`.
- Dashboard confirmed running and healthy throughout and at the end:
  `curl localhost:8500` → `200`.

## Database changes

`data/flatwhite.db` backed up before the dashboard was restarted with the
new schema: `data/flatwhite.db.bak-2026-08-17-bigconv`. The only schema
change is one new table, `skill_run_state` (run outcome persistence,
described above) — no existing tables or data were altered. Confirmed empty
in production (`SELECT * FROM skill_run_state` → `[]`); no test/stub data
was left behind, all stub verification ran against a temporary DB in the
scratchpad, never `data/flatwhite.db`.

## What Victor needs to know / decide

- **The Offer Withdrawn piece Victor originally ran is real and now visible**
  in the dashboard — no need to re-run it. Open the topic and it should show
  the drafted piece with screenshots per paragraph.
- No real generation was triggered during this fix, per the instruction to
  hold off while the three-stage generation pipeline (generate → refine
  against published voice → strip AI phrasing) is being reworked. Once
  that's ready, "Process" on any topic will go through the same
  (now-honest) plumbing.
- The header-decoration and citation-style inconsistency in the skill's own
  markdown output (bold/H1/plain, sentence-present/absent) is a symptom of
  the generation itself being loosely specified — likely to be affected by
  the prompt rework already planned. The dashboard-side fix here is robust
  to whatever the new pipeline produces as long as screenshots keep the
  `p<n>_<rank>_<handle>` rename convention and the piece text still
  mentions those handles somewhere (which is the one part of the contract
  every real run has honoured).
