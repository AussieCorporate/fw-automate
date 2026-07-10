"""Publish-date normalisation for ingested feed items.

RSS feeds hand us dates in two shapes: RFC 2822 ("Fri, 05 Jun 2026 03:00:00 GMT",
most classic RSS) and ISO 8601 ("2026-06-29T03:00:00Z", Atom and Reddit).

`raw_items.published_at` is a TEXT column, and `prune_stale_raw_items` compares it
against `datetime('now', '-N days')` — a *string* comparison. An RFC 2822 value
starts with a letter, which always sorts above "2026-...", so those rows never
compared as stale and never got pruned. Storing one canonical, sortable format
is what makes the freshness sweep work at all.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# SQLite's datetime() returns "YYYY-MM-DD HH:MM:SS"; match it so string
# comparison is also chronological comparison.
_SQLITE_FORMAT = "%Y-%m-%d %H:%M:%S"


def to_iso_utc(value: str | None) -> str | None:
    """Normalise a feed publish date to "YYYY-MM-DD HH:MM:SS" in UTC.

    Accepts ISO 8601 or RFC 2822. Returns None when the value is missing or
    unparseable, which callers treat as "no known publish date".
    """
    if not value:
        return None

    raw = value.strip()
    dt: datetime | None = None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).strftime(_SQLITE_FORMAT)
