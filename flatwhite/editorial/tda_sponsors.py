"""Scrape The Daily Aus (Beehiiv) newsletter for sponsor/advertiser data.

Two-phase approach:
1. Scrape the archive page (JS-rendered SPA) via Playwright to get all post slugs
2. Navigate to each post in a single Playwright page and extract rendered HTML
   (TDA is Cloudflare-protected, so plain HTTP returns 403 — Playwright required)

Detection methods:
- UTM: links with utm_medium containing "paid", "sponsored", "ad" etc.
- Text: sections containing "sponsored by", "brought to you by", etc.

Output: list of dicts with sponsor_name, sponsor_url, slug, edition_url, detection.
"""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlparse

BASE_URL = "https://www.newsletter.thedailyaus.com.au"

IGNORE_DOMAINS = {
    "beehiiv.com",
    "thedailyaus.com.au",
    "newsletter.thedailyaus.com.au",
    "facebook.com",
    "twitter.com",
    "x.com",
    "threads.net",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "apple.com",
    "apps.apple.com",
    "play.google.com",
}

PAID_UTM_KEYWORDS = {"paid", "sponsored", "sponsor", "ad", "ads", "promo"}

SPONSOR_TEXT_PATTERNS = [
    re.compile(r"sponsor(?:ed|s)?\s+by", re.IGNORECASE),
    re.compile(r"brought\s+to\s+you\s+by", re.IGNORECASE),
    re.compile(r"presented\s+by", re.IGNORECASE),
    re.compile(r"today[''']?s\s+sponsor", re.IGNORECASE),
    re.compile(r"thanks?\s+to\s+our\s+(?:partner|sponsor)", re.IGNORECASE),
    re.compile(r"in\s+partnership\s+with", re.IGNORECASE),
    re.compile(r"a\s+message\s+from\s+our", re.IGNORECASE),
    re.compile(r"from\s+our\s+sponsor", re.IGNORECASE),
]

_HREF_RE = re.compile(r'href="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_ignored(url: str) -> bool:
    d = _domain(url)
    return any(ig in d for ig in IGNORE_DOMAINS)


def _detect_sponsors(html: str) -> list[dict]:
    """Run UTM and text-based sponsor detection on a page's HTML."""
    found: dict[str, dict] = {}

    for raw_url in _HREF_RE.findall(html):
        url = raw_url.replace("&amp;", "&")
        if _is_ignored(url):
            continue
        qs = parse_qs(urlparse(url).query)
        utm_medium = qs.get("utm_medium", [""])[0].lower()
        if any(kw in utm_medium for kw in PAID_UTM_KEYWORDS):
            d = _domain(url)
            if d and d not in found:
                found[d] = {
                    "sponsor_name": d,
                    "sponsor_url": url.split("?")[0],
                    "detection": "utm",
                    "detail": f"utm_medium={utm_medium}",
                }

    text = _TAG_RE.sub(" ", html)
    text = " ".join(text.split())
    for pat in SPONSOR_TEXT_PATTERNS:
        m = pat.search(text)
        if m:
            snippet = text[max(0, m.start() - 30):m.end() + 150].strip()
            start = max(0, m.start() - 200)
            end = min(len(html), m.end() + 1000)
            nearby_html = html[start:end]
            for url in _HREF_RE.findall(nearby_html):
                url = url.replace("&amp;", "&")
                if not _is_ignored(url):
                    d = _domain(url)
                    if d and d not in found:
                        found[d] = {
                            "sponsor_name": d,
                            "sponsor_url": url.split("?")[0],
                            "detection": "text",
                            "detail": snippet[:200],
                        }

    return list(found.values())


_URL_RE = re.compile(r"https?://[^\"\\]+")


def _detect_sponsors_from_json(content_str: str) -> list[dict]:
    """Detect sponsors from serialized Remix context JSON (TDA's content format)."""
    found: dict[str, dict] = {}

    # UTM-based
    for url_m in _URL_RE.finditer(content_str):
        url = url_m.group().replace("\\u0026", "&")
        if _is_ignored(url) or url.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            continue
        qs = parse_qs(urlparse(url).query)
        utm_medium = qs.get("utm_medium", [""])[0].lower()
        if any(kw in utm_medium for kw in PAID_UTM_KEYWORDS):
            d = _domain(url)
            if d and d not in found:
                found[d] = {
                    "sponsor_name": d,
                    "sponsor_url": url.split("?")[0],
                    "detection": "utm",
                }

    # Text-based: extract text nodes from JSON
    text_nodes = re.findall(r'"text":"([^"]+)"', content_str)
    full_text = " ".join(text_nodes)
    for pat in SPONSOR_TEXT_PATTERNS:
        m = pat.search(full_text)
        if m:
            snippet = full_text[max(0, m.start() - 30):m.end() + 150].strip()
            json_pos = content_str.find(m.group())
            if json_pos > 0:
                nearby = content_str[max(0, json_pos - 500):json_pos + 2000]
                for url_m in _URL_RE.finditer(nearby):
                    url = url_m.group().replace("\\u0026", "&")
                    if (not _is_ignored(url)
                            and not url.endswith((".png", ".jpg", ".gif", ".svg", ".webp"))):
                        d = _domain(url)
                        if d and d not in found:
                            found[d] = {
                                "sponsor_name": d,
                                "sponsor_url": url.split("?")[0],
                                "detection": "text",
                                "detail": snippet[:200],
                            }

    return list(found.values())


def _scrape_archive_slugs() -> list[str]:
    """Scrape all post slugs from the TDA archive page via Playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/archive", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        prev_count = 0
        for _ in range(200):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            html = page.content()
            slugs = set(re.findall(r"/p/([\w-]+)", html))
            if len(slugs) == prev_count:
                try:
                    btn = page.query_selector("text=Load more")
                    if btn:
                        btn.click()
                        page.wait_for_timeout(2000)
                        html = page.content()
                        slugs = set(re.findall(r"/p/([\w-]+)", html))
                except Exception:
                    pass
                if len(slugs) == prev_count:
                    break
            prev_count = len(slugs)

        html = page.content()
        browser.close()

    return sorted(set(re.findall(r"/p/([\w-]+)", html)))


def _extract_post_content_js() -> str:
    """JS snippet to extract rendered post content from the DOM."""
    return '''() => {
        const el = document.querySelector('[class*="post"] [class*="content"]')
            || document.querySelector('article')
            || document.querySelector('main');
        return el ? el.innerHTML : "";
    }'''


def scrape_tda_sponsors() -> list[dict]:
    """Scrape all TDA editions for sponsor data.

    Uses Playwright throughout (Cloudflare blocks plain HTTP).
    Returns list of dicts:
        sponsor_name, sponsor_url, slug, edition_url, detection, detail
    """
    from playwright.sync_api import sync_playwright

    print("  Collecting TDA archive slugs (Playwright)...")
    slugs = _scrape_archive_slugs()
    # Filter to valid-looking slugs (contain a hyphen and >8 chars)
    slugs = [s for s in slugs if "-" in s and len(s) > 8]
    print(f"  Found {len(slugs)} valid posts. Scanning for sponsors (headed browser)...")

    results: list[dict] = []
    errors = 0

    with sync_playwright() as p:
        # Headed mode required — Cloudflare Turnstile blocks headless browsers
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        for i, slug in enumerate(slugs):
            url = f"{BASE_URL}/p/{slug}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_function(
                    "() => window.__remixContext !== undefined", timeout=10000
                )

                content_str = page.evaluate('''() => {
                    const data = window.__remixContext.state
                        .loaderData['routes/p/$slug'];
                    return JSON.stringify(
                        data?.page?.viewable_page_version?.content || {}
                    );
                }''')

                if content_str and len(content_str) > 100:
                    for sp in _detect_sponsors_from_json(content_str):
                        results.append({**sp, "slug": slug, "edition_url": url})
                else:
                    errors += 1
            except Exception:
                errors += 1

            if (i + 1) % 50 == 0:
                print(f"    {i + 1}/{len(slugs)} posts scanned, "
                      f"{len(results)} sponsor hits, {errors} errors")

        browser.close()

    seen = {r["sponsor_name"] for r in results}
    print(f"  TDA sponsors: scanned {len(slugs)} editions, "
          f"found {len(results)} placements across {len(seen)} unique sponsors "
          f"({errors} errors)")

    return results


def summarise_sponsors(sponsors: list[dict]) -> list[dict]:
    """Deduplicate and summarise sponsor appearances by domain."""
    by_name: dict[str, dict] = {}
    for sp in sponsors:
        name = sp["sponsor_name"]
        if name not in by_name:
            by_name[name] = {
                "sponsor_name": name,
                "sponsor_url": sp["sponsor_url"],
                "editions": [],
            }
        slug = sp["slug"]
        if slug not in by_name[name]["editions"]:
            by_name[name]["editions"].append(slug)

    result = []
    for entry in by_name.values():
        result.append({
            "sponsor_name": entry["sponsor_name"],
            "sponsor_url": entry["sponsor_url"],
            "edition_count": len(entry["editions"]),
            "editions": entry["editions"],
        })
    result.sort(key=lambda x: x["edition_count"], reverse=True)
    return result


if __name__ == "__main__":
    sponsors = scrape_tda_sponsors()
    if not sponsors:
        print("\nNo sponsors detected.")
    else:
        summary = summarise_sponsors(sponsors)
        print(f"\n{'=' * 60}")
        print(f"Unique sponsors: {len(summary)}")
        print(f"{'=' * 60}")
        for s in summary:
            print(f"\n  {s['sponsor_name']}")
            print(f"    URL: {s['sponsor_url']}")
            print(f"    Editions: {s['edition_count']}")
