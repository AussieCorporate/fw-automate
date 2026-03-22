from __future__ import annotations

import csv
import io

import httpx
import yaml
from pathlib import Path

from flatwhite.db import insert_signal, get_current_week_iso, get_recent_signals
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"

_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hiring-lab"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _fetch_csv(url: str) -> list[dict]:
    """Fetch a CSV from a URL and return rows as a list of dicts."""
    response = httpx.get(url, headers=_HEADERS, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)


def pull_indeed_hiring() -> dict:
    """Pull Indeed Hiring Lab signals: job postings index and remote work percentage."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    indeed_config = config.get("indeed_hiring", {})
    week_iso = get_current_week_iso()
    results: dict[str, float] = {}

    # --- Signal 1: indeed_job_postings ---
    try:
        job_postings_path = indeed_config.get(
            "job_postings_csv",
            "job_postings_tracker/master/AU/aggregate_job_postings_AU.csv",
        )
        job_postings_url = f"{_GITHUB_RAW_BASE}/{job_postings_path}"
        rows = _fetch_csv(job_postings_url)

        if not rows:
            raise ValueError("CSV returned no rows")

        # Filter for AU rows if multi-country file
        if "jobcountry" in rows[0]:
            rows = [r for r in rows if r.get("jobcountry") == "AU"]
            if not rows:
                raise ValueError("No AU rows found in job postings CSV")

        last_row = rows[-1]
        # Prefer seasonally adjusted index, fall back to first non-metadata column
        if "indeed_job_postings_index_SA" in last_row:
            index_value = float(last_row["indeed_job_postings_index_SA"])
        else:
            value_col = [col for col in last_row.keys() if col.lower() not in ("date", "jobcountry", "variable")]
            if not value_col:
                raise ValueError("No value column found in job postings CSV")
            index_value = float(last_row[value_col[0]])
        normalised = max(0.0, min(100.0, index_value / 2.0))

        insert_signal(
            signal_name="indeed_job_postings",
            lane="pulse",
            area="labour_market",
            raw_value=index_value,
            normalised_score=normalised,
            source_weight=1.0,
            week_iso=week_iso,
        )
        results["indeed_job_postings"] = normalised
        print(f"  indeed_job_postings: index={index_value:.1f} -> normalised={normalised:.1f}")

    except Exception as e:
        print(f"  ✗ indeed_job_postings FAILED: {e}")
        print(f"    URL attempted: {_GITHUB_RAW_BASE}/{indeed_config.get('job_postings_csv', '???')}")
        print(f"    This signal will be missing from this week's Pulse.")
        results["indeed_job_postings"] = None

    # --- Signal 2: indeed_remote_pct ---
    try:
        remote_path = indeed_config.get(
            "remote_tracker_csv",
            "remote-tracker/main/remote_postings.csv",
        )
        remote_url = f"{_GITHUB_RAW_BASE}/{remote_path}"
        rows = _fetch_csv(remote_url)

        if not rows:
            raise ValueError("CSV returned no rows")

        # Filter for AU rows — the combined file contains all countries
        if "jobcountry" in rows[0]:
            rows = [r for r in rows if r.get("jobcountry") == "AU"]
            if not rows:
                raise ValueError("No AU rows found in remote tracker CSV")

        last_row = rows[-1]
        # Prefer explicit remote_share_postings column, fall back to first non-metadata column
        if "remote_share_postings" in last_row:
            current_value = float(last_row["remote_share_postings"])
        else:
            value_col = [col for col in last_row.keys() if col.lower() not in ("date", "jobcountry")]
            if not value_col:
                raise ValueError("No value column found in remote tracker CSV")
            current_value = float(last_row[value_col[0]])

        # Hybrid normalisation
        recent = get_recent_signals("indeed_remote_pct", weeks=52)
        history = [r["raw_value"] for r in recent
                   if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

        ref = config.get("signal_reference_ranges", {}).get("signals", {}).get("indeed_remote_pct", {})
        normalised, source_weight = normalise_hybrid(
            raw_value=current_value,
            floor=ref.get("floor", 4.0),
            ceiling=ref.get("ceiling", 20.0),
            inverted=ref.get("inverted", False),
            history=history,
            min_weeks_warm=get_min_weeks_warm(config),
        )

        insert_signal(
            signal_name="indeed_remote_pct",
            lane="pulse",
            area="labour_market",
            raw_value=current_value,
            normalised_score=normalised,
            source_weight=source_weight,
            week_iso=week_iso,
        )
        results["indeed_remote_pct"] = normalised
        print(f"  indeed_remote_pct: value={current_value:.1f}% -> normalised={normalised:.1f} (weight={source_weight})")

    except Exception as e:
        print(f"  ✗ indeed_remote_pct FAILED: {e}")
        print(f"    URL attempted: {_GITHUB_RAW_BASE}/{indeed_config.get('remote_tracker_csv', '???')}")
        print(f"    This signal will be missing from this week's Pulse.")
        results["indeed_remote_pct"] = None

    return results
