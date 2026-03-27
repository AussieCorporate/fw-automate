from bs4 import BeautifulSoup
from flatwhite.utils.http import fetch_url_playwright
from flatwhite.db import insert_signal, get_current_week_iso, get_recent_signals
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid
import yaml
from pathlib import Path
import re

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

def _extract_listing_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    match = re.search(r"([\d,]+)\s+jobs?", text, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0

def pull_market_hiring() -> float:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    total_count = 0
    n_categories = len(config["seek"]["categories"])
    n_failed = 0
    for category in config["seek"]["categories"]:
        try:
            html = fetch_url_playwright(category["url"], delay_seconds=2.0, wait_seconds=5.0)
            count = _extract_listing_count(html)
            total_count += count
        except Exception as e:
            print(f"  ⚠ SEEK fetch failed for '{category['name']}': {e}")
            n_failed += 1
            continue

    week_iso = get_current_week_iso()

    # If all fetches failed, this is a scraper blockage — exclude from composite
    if n_failed == n_categories:
        print("  ⚠ market_hiring: all SEEK fetches failed — signal excluded from composite this week")
        insert_signal(
            signal_name="market_hiring",
            lane="pulse",
            area="labour_market",
            raw_value=0.0,
            normalised_score=50.0,
            source_weight=0.0,
            week_iso=week_iso,
        )
        return 50.0

    recent = get_recent_signals("market_hiring", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = config["signal_reference_ranges"]["signals"]["market_hiring"]
    normalised, source_weight = normalise_hybrid(
        raw_value=float(total_count),
        floor=ref["floor"],
        ceiling=ref["ceiling"],
        inverted=ref["inverted"],
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    insert_signal(
        signal_name="market_hiring",
        lane="pulse",
        area="labour_market",
        raw_value=float(total_count),
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )
    return normalised
