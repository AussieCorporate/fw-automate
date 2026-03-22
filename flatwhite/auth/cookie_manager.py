import json
from datetime import datetime
from pathlib import Path

COOKIE_PATH = Path(__file__).parent.parent.parent / "data" / "google_cookies.json"
COOKIE_MAX_AGE_HOURS = 168  # 7 days — NID cookie is valid ~6 months; we refresh weekly

def _cookies_are_fresh() -> bool:
    if not COOKIE_PATH.exists():
        return False
    try:
        with open(COOKIE_PATH) as f:
            data = json.load(f)
        fetched_at = data.get("fetched_at")
        if not fetched_at:
            return False
        age_hours = (datetime.utcnow() - datetime.fromisoformat(fetched_at)).total_seconds() / 3600
        return age_hours < COOKIE_MAX_AGE_HOURS
    except Exception:
        return False

def _fetch_cookies_via_playwright() -> dict[str, str]:
    from playwright.sync_api import sync_playwright
    print("  Fetching Google cookies via Playwright (headless Chromium)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        page = context.new_page()
        # Visit Google Trends to acquire a full session cookie set
        page.goto("https://trends.google.com/trends/explore?geo=AU", wait_until="networkidle", timeout=30000)
        cookies = context.cookies()
        browser.close()

    cookie_dict = {c["name"]: c["value"] for c in cookies}
    print(f"  Acquired {len(cookie_dict)} cookies from Google Trends")
    return cookie_dict

def get_google_cookies(force_refresh: bool = False) -> dict[str, str]:
    """
    Return Google session cookies, auto-refreshing via Playwright if stale.
    Cookies are cached in data/google_cookies.json for up to 7 days.
    Pass force_refresh=True to force a new browser session immediately.
    """
    if not force_refresh and _cookies_are_fresh():
        with open(COOKIE_PATH) as f:
            return json.load(f)["cookies"]

    cookies = _fetch_cookies_via_playwright()
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_PATH, "w") as f:
        json.dump({
            "fetched_at": datetime.utcnow().isoformat(),
            "cookies": cookies,
        }, f, indent=2)
    return cookies

def invalidate_cookies() -> None:
    """Delete cached cookies to force a full refresh on next call."""
    if COOKIE_PATH.exists():
        COOKIE_PATH.unlink()
        print("  Google cookies cache cleared")
