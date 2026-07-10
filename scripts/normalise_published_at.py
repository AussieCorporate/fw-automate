"""One-off backfill: rewrite raw_items.published_at into a sortable UTC format.

Historic rows stored whatever the feed handed us, mostly RFC 2822
("Fri, 05 Jun 2026 03:00:00 GMT"). prune_stale_raw_items compares published_at
as a string against datetime('now', '-N days'), and a value starting with a
letter always sorts above "2026-...", so those rows were never pruned as stale.
That is why months-old listicles kept resurfacing in Off The Clock.

Ingest now normalises on the way in (flatwhite/utils/dates.to_iso_utc). This
fixes the rows already in the table.

Usage:
    .venv/bin/python scripts/normalise_published_at.py --dry-run
    .venv/bin/python scripts/normalise_published_at.py
"""

from __future__ import annotations

import argparse
import sqlite3

from flatwhite.db import DB_PATH
from flatwhite.utils.dates import to_iso_utc

# Already-normalised values start with a 4-digit year.
SORTABLE = "[0-9][0-9][0-9][0-9]-*"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        f"""SELECT id, published_at FROM raw_items
        WHERE published_at IS NOT NULL AND published_at NOT GLOB '{SORTABLE}'"""
    ).fetchall()

    fixed, unparseable = [], []
    for row in rows:
        iso = to_iso_utc(row["published_at"])
        if iso:
            fixed.append((iso, row["id"]))
        else:
            unparseable.append(row["published_at"])

    print(f"candidates: {len(rows)}")
    print(f"  parseable -> will rewrite: {len(fixed)}")
    print(f"  unparseable -> set NULL:   {len(unparseable)}")
    if unparseable[:3]:
        print(f"  e.g. {unparseable[:3]}")

    if args.dry_run:
        print("\ndry run — nothing written")
        conn.close()
        return

    conn.executemany("UPDATE raw_items SET published_at = ? WHERE id = ?", fixed)
    conn.execute(
        f"""UPDATE raw_items SET published_at = NULL
        WHERE published_at IS NOT NULL AND published_at NOT GLOB '{SORTABLE}'"""
    )
    conn.commit()

    remaining = conn.execute(
        f"""SELECT COUNT(*) FROM raw_items
        WHERE published_at IS NOT NULL AND published_at NOT GLOB '{SORTABLE}'"""
    ).fetchone()[0]
    conn.close()

    print(f"\nrewritten: {len(fixed)}")
    print(f"still unsortable: {remaining} (expected 0)")


if __name__ == "__main__":
    main()
