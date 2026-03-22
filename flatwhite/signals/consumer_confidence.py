from __future__ import annotations

from bs4 import BeautifulSoup
from flatwhite.utils.http import fetch_url
from flatwhite.db import insert_signal, get_current_week_iso

ROYMORGAN_URL = "https://www.roymorgan.com/morgan-poll/consumer-confidence-anz-roy-morgan-australian-cc-summary/"
FLOOR = 65.0    # Headroom for crisis — COVID low was ~60; current min is 73.4
CEILING = 95.0   # Calibrated so recent mean (~82.5) maps to ~58

def _parse_latest_index(html: str) -> float | None:
    """Parse the most recent weekly value from the ANZ-Roy Morgan summary table."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None
    # First table is the current year — find the last non-empty weekly average
    rows = tables[0].find_all("tr")
    last_value = None
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) >= 3 and cells[2] and cells[2] != "WEEKLY AVERAGE":
            try:
                last_value = float(cells[2])
            except ValueError:
                pass
    return last_value

def pull_consumer_confidence() -> float:
    is_fallback = False
    try:
        html = fetch_url(ROYMORGAN_URL, delay_seconds=2.0)
        raw_value = _parse_latest_index(html)
        if raw_value is None:
            raw_value = 85.0
            is_fallback = True
            print("  ⚠ Consumer confidence scrape matched no value — using fallback (85.0, weight 0.3)")
    except Exception as e:
        raw_value = 85.0
        is_fallback = True
        print(f"  ⚠ Consumer confidence scrape failed ({e}) — using fallback (85.0, weight 0.3)")

    normalised = ((raw_value - FLOOR) / (CEILING - FLOOR)) * 100.0
    normalised = max(0.0, min(100.0, normalised))

    source_weight = 0.3 if is_fallback else 1.0

    week_iso = get_current_week_iso()
    insert_signal(
        signal_name="consumer_confidence",
        lane="pulse",
        area="economic",
        raw_value=raw_value,
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )
    return normalised
