#!/usr/bin/env python3
"""One-time backfill: seed employer_snapshots for the past N weeks from current data.

Since ATS career pages don't expose historical role counts, we copy the current
week's live scrape into past week slots as a baseline. This gives MoM comparisons
a starting point — real deltas will accumulate from the next weekly scrape onwards.

Usage:
    python scripts/backfill_lobby.py            # seeds past 4 weeks (default)
    python scripts/backfill_lobby.py --weeks 6  # seeds past 6 weeks
    python scripts/backfill_lobby.py --dry-run  # preview without writing
"""
import argparse
import datetime
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from flatwhite.db import get_connection, get_current_week_iso


def prev_week_iso(week_iso: str, n: int) -> str:
    year, wn = int(week_iso[:4]), int(week_iso[6:])
    dt = datetime.datetime.strptime(f"{year}-W{wn:02d}-1", "%G-W%V-%u")
    return (dt - datetime.timedelta(weeks=n)).strftime("%G-W%V")


def backfill(weeks: int = 4, dry_run: bool = False) -> None:
    current_week = get_current_week_iso()
    conn = get_connection()

    current_count = conn.execute(
        "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (current_week,)
    ).fetchone()[0]

    if current_count == 0:
        print(f"No employer snapshots found for {current_week}. Run the Lobby scrape first.")
        conn.close()
        return

    print(f"Current week {current_week}: {current_count} employer snapshots found.")
    print()

    for n in range(1, weeks + 1):
        target = prev_week_iso(current_week, n)
        year, wn = int(target[:4]), int(target[6:])
        target_date = datetime.datetime.strptime(
            f"{year}-W{wn:02d}-1", "%G-W%V-%u"
        ).strftime("%Y-%m-%d")

        existing = conn.execute(
            "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (target,)
        ).fetchone()[0]

        if existing > 0:
            print(f"  {target}: already has {existing} rows — skipping")
            continue

        if dry_run:
            print(f"  {target}: would seed {current_count} rows (dry run)")
            continue

        conn.execute(
            """INSERT OR IGNORE INTO employer_snapshots
               (employer_id, open_roles_count, snapshot_date, week_iso,
                extraction_method, ats_platform,
                new_roles_count, stale_roles_count,
                junior_count, mid_count, senior_count, executive_count)
               SELECT employer_id, open_roles_count, ?, ?,
                      extraction_method, ats_platform,
                      new_roles_count, stale_roles_count,
                      junior_count, mid_count, senior_count, executive_count
               FROM employer_snapshots WHERE week_iso = ?""",
            (target_date, target, current_week),
        )
        seeded = conn.execute(
            "SELECT COUNT(*) FROM employer_snapshots WHERE week_iso = ?", (target,)
        ).fetchone()[0]
        print(f"  {target}: seeded {seeded} rows")

    if not dry_run:
        conn.commit()
        print()
        print("Done. MoM comparisons will now show 0 for backfilled weeks (expected).")
        print("Real month-on-month changes will appear after 4 weekly scrapes.")
    else:
        print()
        print("Dry run complete — no data written.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill employer snapshots for past weeks.")
    parser.add_argument("--weeks", type=int, default=4, help="Number of past weeks to seed (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    backfill(weeks=args.weeks, dry_run=args.dry_run)
