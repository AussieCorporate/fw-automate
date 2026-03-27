from __future__ import annotations

import re
import time
import httpx
from bs4 import BeautifulSoup
from flatwhite.db import insert_signal, get_current_week_iso, get_recent_signals
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
_SALARY_RE = re.compile(r"Average Salary[\s:]*\$?([\d,]+)", re.IGNORECASE)


def _get_sector_salary(query: str, delay: float = 2.0) -> float | None:
    """Scrape average offered salary from Adzuna AU search page."""
    time.sleep(delay)
    url = f"https://www.adzuna.com.au/search?q={query}"
    response = httpx.get(url, headers=_HEADERS, timeout=15.0, follow_redirects=True)
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text()
    m = _SALARY_RE.search(text)
    if m:
        cleaned = m.group(1).replace(",", "")
        if cleaned.isdigit():
            return float(cleaned)
    return None


def pull_salary_pressure() -> float:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    salaries: list[float] = []
    for sector in config["adzuna_salary"]["sectors"]:
        try:
            salary = _get_sector_salary(sector["query"], delay=2.0)
            if salary is not None:
                salaries.append(salary)
        except Exception as e:
            print(f"  ⚠ salary_pressure: skipped {sector['name']} — {type(e).__name__}: {e}")

    week_iso = get_current_week_iso()

    if not salaries:
        # All sector fetches failed — exclude from composite rather than inserting a false "salaries collapsed" signal
        print("  ⚠ salary_pressure: all Adzuna fetches failed — signal excluded from composite this week")
        insert_signal(
            signal_name="salary_pressure",
            lane="pulse",
            area="labour_market",
            raw_value=0.0,
            normalised_score=50.0,
            source_weight=0.0,
            week_iso=week_iso,
        )
        return 50.0

    avg_salary = sum(salaries) / len(salaries)

    recent = get_recent_signals("salary_pressure", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = config["signal_reference_ranges"]["signals"]["salary_pressure"]
    normalised, source_weight = normalise_hybrid(
        raw_value=avg_salary,
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    insert_signal(
        signal_name="salary_pressure",
        lane="pulse",
        area="labour_market",
        raw_value=avg_salary,
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )
    return normalised
