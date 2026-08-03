"""Decide whether the Brains Trust angle pool needs topping up, and build the
command that would do it.

The angle pool (brains_trust_research.py) reads data/carousels/*/_candidates.json
from the Trading Strategy project. Those files are normally written by the
tac-carousels launchd job — but that job was deliberately retired 20 Jul 2026
(carousel-making moved to the Pick & Scroll Instagram desk) and Victor decided
3 Aug 2026 to keep it off rather than resume its separate email. This module
is the manual alternative: it runs a catch-up script
(scripts/backfill_tac_carousels.py) covering the same underlying pipeline
that job used to run, on demand, capped so a stale pool can't turn into an
unbounded Anthropic API bill in one click.

Read-only until build_refresh_command's caller actually runs the returned
command - this module itself never spawns a process or writes a file.
"""
from __future__ import annotations

import glob
import os
import re
from datetime import datetime, timezone

# Same env var and default as brains_trust_research.py - both modules must
# agree on where the research bank lives.
_DEFAULT_DATA_ROOT = os.environ.get(
    "BRAINS_TRUST_ROOT", "/Users/victornguyen/Documents/MISC/Trading Strategy/data"
)

# The retired tac-carousels launchd job's interpreter. The Trading Strategy
# project's own .venv is missing python-dotenv (verified 3 Aug 2026), so it
# can't run the backfill script - this is the one that actually has the deps.
_PYTHON_BIN = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

# Three weeks - matches the angle pool's own read window (weeks=3) and bounds
# how much a single click can spend on the Anthropic API.
_MAX_DAYS_PER_REFRESH = 21


def _folder_date(candidates_path: str) -> str | None:
    """Extract the YYYYMMDD embedded in a candidate folder's name, or None.
    Deliberately mirrors brains_trust_research._folder_date's regex (same
    real folder-naming quirk: 'YYYYMMDD' and 'backfill_YYYYMMDD' both occur)
    rather than importing that private helper across module boundaries."""
    folder = os.path.basename(os.path.dirname(candidates_path))
    m = re.search(r"(\d{8})", folder)
    return m.group(1) if m else None


def _newest_known_date(data_root: str) -> str | None:
    hits = glob.glob(os.path.join(data_root, "carousels", "*", "_candidates.json"))
    dates = [d for d in (_folder_date(p) for p in hits) if d]
    return max(dates) if dates else None


def build_refresh_command(
    data_root: str | None = None,
) -> tuple[list[str], str, int] | None:
    """(argv, cwd, days_requested) to catch the angle pool up, or None if it's
    already current. days_requested is capped at _MAX_DAYS_PER_REFRESH; a pool
    with no research at all yet is treated as fully stale (the cap).

    The target script (scripts/backfill_tac_carousels.py) deliberately skips
    "today" - it only ever fills in yesterday and earlier. So a pool whose
    newest folder is already yesterday is fully caught up as far as this
    script can ever get it, even though (today - yesterday) is nominally 1
    day. Subtract that day before clamping to zero, or every click would
    re-run an already-covered day forever and "already up to date" would
    never be reachable."""
    root = data_root or _DEFAULT_DATA_ROOT
    newest = _newest_known_date(root)
    if newest is None:
        days = _MAX_DAYS_PER_REFRESH
    else:
        newest_date = datetime.strptime(newest, "%Y%m%d").date()
        today = datetime.now(timezone.utc).date()
        days_behind = (today - newest_date).days - 1
        days = min(max(0, days_behind), _MAX_DAYS_PER_REFRESH)

    if days <= 0:
        return None

    project_root = os.path.dirname(root.rstrip(os.sep))
    argv = [_PYTHON_BIN, "-m", "scripts.backfill_tac_carousels", "--days", str(days)]
    return argv, project_root, days
