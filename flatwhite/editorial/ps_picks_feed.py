"""Read the FW picks feed that PS (Shell Bot 2) writes each newsletter run.

PS appends one edition record per run to fw_picks_feed.jsonl: the business news
(url/title/summary/category/is_feature) and the odd picks (url/title/summary).
This is the ONLY place feature stories' one-sentence summaries reach Flat White
- features ship to beehiiv as inline deep-dives with no click-link, so FW's
click-based Top Picks can't see them. Read-only, fail-open (a missing or corrupt
feed just yields empty lists, and FW falls back to click-only).
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os

# PS writes the feed here; overridable so this repo can point elsewhere / be
# tested. Same read-only cross-project pattern FW uses for Trading Strategy.
_DEFAULT_FEED = _os.path.expanduser(
    "~/Movies/Shell Bot 2/state_store_root/state/fw_picks_feed.jsonl"
)


def _feed_path() -> str:
    return _os.environ.get("FW_PS_PICKS_FEED", _DEFAULT_FEED)


def _parse_iso(s: str | None):
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def read_feed(days: int = 7, *, now: _dt.datetime | None = None,
              path: str | None = None) -> dict:
    """The last `days` editions of picks, as {'business': [...], 'odd': [...]}.

    Deduped by URL with the NEWEST edition's version winning (a story re-run in a
    later edition shows its latest summary/feature status). Fail-open: empty
    lists on any missing/corrupt feed.
    """
    path = path or _feed_path()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=days)

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
    except OSError:
        return {"business": [], "odd": []}

    records = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = _json.loads(line)
        except (ValueError, TypeError):
            continue
        ed = _parse_iso(rec.get("edition_date"))
        if ed is None or ed < cutoff:
            continue
        records.append((ed, rec))

    # Oldest first so a later edition overwrites an earlier one on dedupe.
    records.sort(key=lambda pair: pair[0])

    business_by_url: dict[str, dict] = {}
    odd_by_key: dict[str, dict] = {}
    for _, rec in records:
        for b in rec.get("business", []):
            url = (b.get("url") or "").strip()
            if url:
                business_by_url[url] = b
        for o in rec.get("odd", []):
            key = (o.get("url") or o.get("title") or "").strip()
            if key:
                odd_by_key[key] = o

    return {"business": list(business_by_url.values()),
            "odd": list(odd_by_key.values())}
