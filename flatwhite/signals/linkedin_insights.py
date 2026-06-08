"""Scrape LinkedIn company insights for employer watchlist companies.

Uses a Playwright browser session with stored LinkedIn cookies to visit
each company's public insights page and extract:
- Total employee count
- Headcount growth % (6-month and 1-year)
- Median tenure
- New hires (last 6 months)
- Notable departures signal (hiring vs attrition ratio)
- Top hiring functions/departments

Runs once per week during the Lobby scrape phase. Results are stored in
the linkedin_insights table and merged into the Lobby prompt.

RATE LIMITING: 60-90 second delays between page loads to mimic human browsing.
Maximum ~30 page loads per session (16 companies × 1-2 pages each).
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from flatwhite.db import get_connection, get_current_week_iso

COOKIE_PATH = Path(__file__).parent.parent.parent / "data" / "linkedin_cookies.json"

# LinkedIn company slug mapping — matches employer_watchlist names
COMPANY_SLUGS: dict[str, str] = {
    "Deloitte Australia": "deloitte",
    "PwC Australia": "pwcau",
    "EY Australia": "ernstandyoung",
    "KPMG Australia": "kpmg",
    "King & Wood Mallesons": "king-&-wood-mallesons",
    "Allens": "allabordallenslinklaters",
    "Herbert Smith Freehills": "herbert-smith-freehills",
    "Clayton Utz": "clayton-utz",
    "CBA": "commonwealth-bank",
    "NAB": "national-australia-bank",
    "Westpac": "westpac",
    "ANZ": "anz",
    "Macquarie Group": "macquarie-group",
    "Canva": "canva",
    "Atlassian": "atlassian",
    "REA Group": "reagroup",
    "Accenture": "accenture",
    "BHP": "bhp",
    "Telstra": "telstra",
    "Rio Tinto": "rio-tinto",
    "CSL": "csl",
    "Xero": "xero",
    "Coles Group": "coles-group",
    "IAG": "iabordalag",
    "Lendlease": "lendlease",
    "Transurban": "transurban",
    "QBE Insurance": "qbe-insurance",
    "AustralianSuper": "australiansuper",
    "MinterEllison": "mabordalinterellison",
    "NSW Government": "new-south-wales-government",
    "ATO": "australian-taxation-office",
}


def _get_linkedin_cookies() -> list[dict]:
    """Load stored LinkedIn session cookies."""
    if not COOKIE_PATH.exists():
        raise FileNotFoundError(
            f"LinkedIn cookies not found at {COOKIE_PATH}. "
            "Run: flatwhite linkedin-login to authenticate."
        )
    with open(COOKIE_PATH) as f:
        data = json.load(f)
    return data.get("cookies", [])


def save_linkedin_cookies(cookies: list[dict]) -> None:
    """Save LinkedIn session cookies from a Playwright browser context."""
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_PATH, "w") as f:
        json.dump({
            "cookies": cookies,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)
    print(f"  Saved {len(cookies)} LinkedIn cookies to {COOKIE_PATH}")


def linkedin_login_interactive() -> None:
    """Open a visible browser for the user to log into LinkedIn manually.

    After login, cookies are saved for future headless use.
    """
    from playwright.sync_api import sync_playwright

    print("\n  Opening LinkedIn login page...")
    print("  Log in manually, then press Enter in this terminal when done.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="networkidle")

        input("  Press Enter after you have logged in... ")

        cookies = context.cookies()
        save_linkedin_cookies(cookies)
        browser.close()

    print("  LinkedIn session saved. You can now run the insights scraper.")


def _scrape_company_page(page, slug: str) -> dict | None:
    """Scrape a single company's LinkedIn insights page.

    Returns dict with extracted data, or None on failure.
    """
    url = f"https://www.linkedin.com/company/{slug}/insights/"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for content to render
        time.sleep(3)

        # Get the full page text for parsing
        body_text = page.inner_text("body")
        html = page.content()

        # Extract structured data from the page
        result = {
            "slug": slug,
            "url": url,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "raw_text": body_text[:5000],  # Keep first 5k chars for LLM parsing
            "employee_count": None,
            "headcount_growth_6m": None,
            "headcount_growth_1y": None,
            "median_tenure": None,
            "new_hires_6m": None,
            "top_functions": [],
        }

        # Try to extract specific data points from page text
        import re

        # Employee count — usually displayed prominently
        emp_match = re.search(r'([\d,]+)\s+employees', body_text)
        if emp_match:
            result["employee_count"] = int(emp_match.group(1).replace(",", ""))

        # Growth percentages
        growth_matches = re.findall(r'([+-]?\d+\.?\d*)%\s*(?:employee|headcount|growth)', body_text, re.IGNORECASE)
        if growth_matches:
            result["headcount_growth_pct"] = growth_matches[0]

        # Median tenure
        tenure_match = re.search(r'median\s+tenure[:\s]+(\d+\.?\d*)\s*(?:years?|yrs?)', body_text, re.IGNORECASE)
        if tenure_match:
            result["median_tenure"] = float(tenure_match.group(1))

        # New hires
        hires_match = re.search(r'([\d,]+)\s+new\s+hires?', body_text, re.IGNORECASE)
        if hires_match:
            result["new_hires_6m"] = int(hires_match.group(1).replace(",", ""))

        return result

    except Exception as e:
        print(f"  Warning: failed to scrape {slug}: {e}")
        return None


def scrape_all_company_insights(
    company_names: list[str] | None = None,
    delay_range: tuple[int, int] = (60, 90),
) -> list[dict]:
    """Scrape LinkedIn insights for all (or specified) watchlist companies.

    Args:
        company_names: Optional list of employer names to scrape.
            If None, scrapes all companies in COMPANY_SLUGS.
        delay_range: (min_seconds, max_seconds) between page loads.

    Returns list of result dicts, one per company.
    """
    from playwright.sync_api import sync_playwright

    cookies = _get_linkedin_cookies()
    targets = company_names or list(COMPANY_SLUGS.keys())

    results: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-AU",
            timezone_id="Australia/Sydney",
            viewport={"width": 1440, "height": 900},
        )
        # Restore LinkedIn session
        context.add_cookies(cookies)

        page = context.new_page()

        for i, name in enumerate(targets):
            slug = COMPANY_SLUGS.get(name)
            if not slug:
                print(f"  Skipping {name} — no LinkedIn slug configured")
                continue

            print(f"  [{i+1}/{len(targets)}] Scraping {name} ({slug})...")
            result = _scrape_company_page(page, slug)

            if result:
                result["employer_name"] = name
                results.append(result)

            # Human-like delay between companies
            if i < len(targets) - 1:
                delay = random.randint(*delay_range)
                print(f"  Waiting {delay}s before next company...")
                time.sleep(delay)

        # Save refreshed cookies
        updated_cookies = context.cookies()
        save_linkedin_cookies(updated_cookies)
        browser.close()

    # Store results in DB
    _store_insights(results)

    return results


def _store_insights(results: list[dict]) -> None:
    """Store scraped LinkedIn insights in the database."""
    conn = get_connection()
    week_iso = get_current_week_iso()

    for r in results:
        conn.execute(
            """INSERT OR REPLACE INTO linkedin_insights
            (employer_name, week_iso, employee_count, headcount_growth_pct,
             median_tenure, new_hires_6m, raw_text, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.get("employer_name", ""),
                week_iso,
                r.get("employee_count"),
                r.get("headcount_growth_pct"),
                r.get("median_tenure"),
                r.get("new_hires_6m"),
                r.get("raw_text", "")[:5000],
                r.get("scraped_at", ""),
            ),
        )

    conn.commit()
    conn.close()
    print(f"  Stored {len(results)} LinkedIn insights for {week_iso}")


def load_linkedin_insights(week_iso: str | None = None) -> dict[str, dict]:
    """Load LinkedIn insights for the given week, keyed by employer_name."""
    w = week_iso or get_current_week_iso()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM linkedin_insights WHERE week_iso = ?",
        (w,),
    ).fetchall()
    conn.close()

    return {r["employer_name"]: dict(r) for r in rows}


def format_insights_for_prompt(insights: dict[str, dict]) -> str:
    """Format LinkedIn insights into a text block for the Lobby LLM prompt."""
    if not insights:
        return ""

    lines = [
        "LinkedIn Company Insights (headcount trends, tenure, new hires):"
    ]
    for name, data in sorted(insights.items()):
        parts = [name]
        if data.get("employee_count"):
            parts.append(f"{data['employee_count']:,} employees")
        if data.get("headcount_growth_pct"):
            parts.append(f"headcount growth {data['headcount_growth_pct']}%")
        if data.get("median_tenure"):
            parts.append(f"median tenure {data['median_tenure']}y")
        if data.get("new_hires_6m"):
            parts.append(f"{data['new_hires_6m']:,} new hires (6m)")
        lines.append("- " + " · ".join(parts))

    return "\n".join(lines) + "\n"
