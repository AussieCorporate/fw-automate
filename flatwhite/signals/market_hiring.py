from bs4 import BeautifulSoup
from flatwhite.db import insert_signal, get_current_week_iso, get_recent_signals
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid
import yaml
from pathlib import Path
import re
import time

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

def _extract_listing_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    match = re.search(r"([\d,]+)\s+jobs?", text, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0

def pull_market_hiring() -> float:
    from playwright.sync_api import sync_playwright

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    total_count = 0
    n_categories = len(config["seek"]["categories"])
    n_failed = 0

    # Single browser instance for all SEEK fetches
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for category in config["seek"]["categories"]:
            try:
                time.sleep(1.0)
                # domcontentloaded, not networkidle: SEEK is JS-heavy and often
                # never goes fully idle, so networkidle would burn the entire
                # timeout on every category. The job count is in the initial DOM.
                page.goto(category["url"], wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                html = page.content()
                count = _extract_listing_count(html)
                total_count += count
            except Exception as e:
                print(f"  ⚠ SEEK fetch failed for '{category['name']}': {e}")
                n_failed += 1
                continue

        browser.close()

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
