"""Read the Trading Strategy project's research candidates (READ ONLY) across
the last N weeks, for the Brains Trust / Economic Scoop segment's angle picker.

Mirrors Shell Bot 2's pipeline/bulge_bracket.py reading pattern (same folder
layout, same isinstance-guard defensiveness, same read-only DB access) but
widens it: bulge_bracket.py returns only the single newest folder; Brains
Trust explicitly wants angles spanning multiple weeks (the EV tipping-point
piece consolidated two weeks of research), so this returns every candidate
from every folder inside the window.

Fails soft everywhere: a missing folder, absent candidates file, bad JSON, a
malformed individual candidate, or a locked/absent SQLite DB all degrade
gracefully rather than raising - a research outage must never block Victor
picking an angle. Never writes to, imports from, or runs the Trading Strategy
project. The one DB read opens via sqlite3's URI ?mode=ro, so this connection
cannot write even by accident.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

_DEFAULT_ROOT = os.environ.get(
    "BRAINS_TRUST_ROOT", "/Users/victornguyen/Documents/MISC/Trading Strategy/data"
)


def _folder_date(candidates_path: str) -> str | None:
    """Extract the YYYYMMDD embedded in a candidate folder's name, or None.
    Real folders are named both '20260713' and 'backfill_20260602', so match
    the 8-digit run ANYWHERE in the name, not a whole-string match (mirrors
    bulge_bracket.py's _folder_date exactly)."""
    folder = os.path.basename(os.path.dirname(candidates_path))
    m = re.search(r"(\d{8})", folder)
    return m.group(1) if m else None


def _dir_date_iso(date_digits: str) -> str:
    return f"{date_digits[0:4]}-{date_digits[4:6]}-{date_digits[6:8]}"


def _candidate_paths_within_window(root: str, weeks: int) -> list[tuple[str, str]]:
    """[(YYYYMMDD, path), ...] for every _candidates.json whose folder date
    falls within the last `weeks` weeks of now, newest first. A folder with no
    parseable date is skipped - it can't be windowed, so it's excluded rather
    than guessed at (same principle as bulge_bracket.py's dateless-folders
    handling, just applied per-folder instead of only to the single pick)."""
    hits = glob.glob(os.path.join(root, "carousels", "*", "_candidates.json"))
    if not hits:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).strftime("%Y%m%d")
    dated = [(_folder_date(p), p) for p in hits]
    dated = [(d, p) for d, p in dated if d and d >= cutoff]
    dated.sort(key=lambda dp: dp[0], reverse=True)
    return dated


def _pdf_dates(root: str, pdf_ids: set[int]) -> dict[int, tuple[str, str]]:
    """pdf_id -> (date_received, sender), best-effort from the read-only DB.
    Opens the DB in SQLite's URI read-only mode so this connection can never
    write (mirrors bulge_bracket.py's _pdf_dates)."""
    db = os.path.join(root, "trading_strategy.db")
    if not pdf_ids or not os.path.exists(db):
        return {}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
        try:
            q = ("SELECT p.id, e.date_received, e.sender FROM pdfs p "
                 "JOIN emails e ON e.id = p.email_id WHERE p.id IN (%s)"
                 % ",".join("?" * len(pdf_ids)))
            return {row[0]: (row[1], row[2]) for row in con.execute(q, tuple(pdf_ids))}
        finally:
            con.close()
    except sqlite3.Error:
        return {}


def load_angle_recommendations(
    root: str | None = None, weeks: int = 3, limit: int = 40
) -> list[dict]:
    """Recommended Brains Trust angles from the Trading Strategy research
    bank, across the last `weeks` weeks (default 3). Newest first, capped at
    `limit` rows total. Never raises."""
    root = root or _DEFAULT_ROOT
    dated_paths = _candidate_paths_within_window(root, weeks)
    if not dated_paths:
        return []

    parsed: list[tuple[str, list[dict]]] = []
    all_pdf_ids: set[int] = set()
    for date_digits, path in dated_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        cands = data.get("candidates")
        if not isinstance(cands, list):
            continue
        good = [c for c in cands if isinstance(c, dict) and (c.get("pitch") or "").strip()]
        for c in good:
            for i in (c.get("source_pdf_ids") or []):
                if isinstance(i, int):
                    all_pdf_ids.add(i)
        parsed.append((date_digits, good))

    src_dates = _pdf_dates(root, all_pdf_ids)

    rows: list[dict] = []
    for date_digits, cands in parsed:
        for c in cands:
            pitch = c["pitch"].strip()
            src_date = ""
            for i in (c.get("source_pdf_ids") or []):
                if isinstance(i, int) and i in src_dates and src_dates[i][0]:
                    src_date = max(src_date, src_dates[i][0])
            key = hashlib.sha1(f"{date_digits}:{pitch}".encode("utf-8")).hexdigest()[:16]
            rows.append({
                "id": f"angle:{key}",
                "date_iso": _dir_date_iso(date_digits),
                "pitch": pitch,
                "angle": (c.get("angle") or "").strip(),
                "why_tac": (c.get("why_tac") or "").strip(),
                "source_pdf_ids": [i for i in (c.get("source_pdf_ids") or []) if isinstance(i, int)],
                "source_pdf_date": src_date or None,
            })
    return rows[:limit]
