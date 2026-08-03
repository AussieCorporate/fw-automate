# Brains Trust — manual "Refresh" button for the angle pool

**Date:** 2026-08-03
**Status:** approved, not yet implemented

## Problem

The Brains Trust angle list (`GET /api/brains-trust/angles`) always reads live
from `data/carousels/*/_candidates.json` in the Trading Strategy project — that
part is not broken. The candidate files themselves stopped getting new entries:
the `tac-carousels` launchd job that generates them was retired 20 Jul 2026
(see Trading Strategy `CLAUDE.md`), when carousel-making moved to the Pick &
Scroll Instagram desk. Brains Trust was quietly depending on that job's
by-product (the `_candidates.json` files) without anyone deciding to keep it
running for that reason.

A one-off manual run of `scripts/backfill_tac_carousels.py --days N` on 27 Jul
caught the pool up through 24 Jul. Nothing has topped it up since, so as of
3 Aug the pool is ~10 days stale with no way to fix it from the dashboard.

Victor decided (3 Aug 2026): keep the overnight job OFF, do not resume its
email. Instead, add a manual "Refresh" button to the Brains Trust screen that
runs the same safe catch-up on demand.

## What we are building

### Backend

New module `flatwhite/dashboard/brains_trust_refresh.py`:

- `_days_behind(root) -> int`: scans `data/carousels/*/_candidates.json` under
  the Trading Strategy root (same root env var as `brains_trust_research.py`,
  `BRAINS_TRUST_ROOT`) for the newest folder date (any prefix — `YYYYMMDD` or
  `backfill_YYYYMMDD`, matches `brains_trust_research._folder_date`'s regex),
  returns `(today - that date).days`. No folder found at all -> treat as 21
  (the cap) so a first-ever run doesn't try to reach back indefinitely.
- `run_refresh() -> dict`: computes days-behind, capped at 21 (three weeks —
  matches the angle pool's own window, and bounds worst-case Anthropic API
  spend per click). If the cap-clamped days-behind is `<= 0`, returns
  `{"ran": False, "reason": "up_to_date"}` without spawning a process.
  Otherwise runs, from the Trading Strategy project directory:
  ```
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
      scripts/backfill_tac_carousels.py --days <N>
  ```
  (same interpreter the retired launchd job used — the project's local
  `.venv` is missing a dependency the script needs, so it is not used here).
  Captures stdout/stderr and return code. This script never sends email — it
  only writes `data/carousels/backfill_YYYYMMDD/` folders, exactly as it did
  for the 27 Jul catch-up. Returns
  `{"ran": True, "ok": bool, "days_requested": N, "newest_date_iso": str|None, "stderr_tail": str|None}`.
  `newest_date_iso` is recomputed after the run by re-scanning folders, so the
  frontend can show what date the pool now reaches without a second angles
  fetch race.

State + concurrency: module-level dict + `threading.Lock`, same shape as the
existing `_scrape_all_state` / `_scrape_all_lock` in `api.py` — one refresh
running at a time, a second click while running is a no-op that just reports
the in-progress state.

New endpoints in `api.py`, next to the existing `/api/brains-trust/*` routes:

- `POST /api/brains-trust/refresh` — starts the background thread if not
  already running. Returns `{"started": true}` or `{"started": false, "already_running": true}`.
- `GET /api/brains-trust/refresh/status` — returns
  `{"running": bool, "last_result": {...} | null}`.

### Frontend

In `renderBrainsPicker()`, next to the "Recommended angles (last 3 weeks)"
label: a small "Refresh" button, mirroring the existing `runScrapeAll()` /
`pollScrapeAll()` pattern (`S.scrapeAllRunning` et al.) already used for the
command bar's Scrape All button:

- Click -> `S.brainsRefreshing = true`, `POST /api/brains-trust/refresh`,
  then poll `GET /api/brains-trust/refresh/status` every 3s.
- While running: button reads "Refreshing…" and is disabled.
- On completion: `S.brainsRefreshing = false`; if `last_result.ran` and `ok`,
  clear `S.brainsAngles = null` and re-fetch `/api/brains-trust/angles`, then
  `render()`. Toast: `"Pulled research through " + newest_date_iso + " — " + angles.length + " angles now available"`.
- If `last_result.reason === "up_to_date"`: toast "Already up to date" — no
  refetch needed.
- If `ok` is false: toast `"Refresh failed: " + stderr_tail` (or a generic
  message if `stderr_tail` is empty), styled as an error toast. The existing
  list is left exactly as it was — a failed refresh never clears
  `S.brainsAngles`.

## Out of scope

- Re-enabling the `tac-carousels` launchd job or its email. Explicitly staying
  off per Victor's 3 Aug decision.
- Auto-refreshing on page load or on a timer. Manual click only.
- Reaching back further than 21 days in one click. If the pool is ever more
  stale than that, Victor clicks Refresh again (a second click after the
  first completes will pick up the next chunk, since `_days_behind` re-scans
  from whatever the newest folder is at that point).
- Any change to `brains_trust_research.py`'s read path — it already reads
  fresh from disk every call; nothing there needs to change for this feature.

## Testing

1. `_days_behind`: newest folder today -> 0; newest folder N days ago -> N;
   no folders at all -> capped value (21); mixed `YYYYMMDD` and
   `backfill_YYYYMMDD` folders -> correctly picks the numerically newest date
   regardless of prefix.
2. `run_refresh()` with days-behind `<= 0` never spawns a subprocess.
3. `run_refresh()` clamps a large gap to 21 before building the command.
4. Subprocess failure (non-zero exit) surfaces `ok: False` and a non-empty
   `stderr_tail`, and does not raise out of `run_refresh()`.
5. `/api/brains-trust/refresh` while already running returns
   `{"started": false, "already_running": true}` and does not start a second
   thread (lock behaviour, mirrors the existing scrape-all test if one
   exists).
6. `/api/brains-trust/refresh/status` before any refresh has ever run returns
   `{"running": false, "last_result": null}`.
