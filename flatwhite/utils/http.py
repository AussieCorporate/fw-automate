from __future__ import annotations

import httpx
import time

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
RSS_UA = "flatwhite/0.1 (by TAC)"

# Reddit's unauthenticated .json API has been 403-blocked from non-residential
# IPs since 2023, and the script-app password grant on oauth.reddit.com is
# effectively broken too — so we only use the public /top/.rss feed, which
# still serves engagement-ordered post titles without auth.
REDDIT_PUBLIC_HOST = "https://www.reddit.com"

DEFAULT_HEADERS = {
    "User-Agent": BROWSER_UA,
}

def fetch_url(url: str, delay_seconds: float = 1.0) -> str:
    time.sleep(delay_seconds)
    response = httpx.get(url, headers=DEFAULT_HEADERS, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


def fetch_url_playwright(url: str, delay_seconds: float = 1.0, wait_seconds: float = 5.0) -> str:
    """Fetch a URL using Playwright browser.

    Use this instead of fetch_url() for sites protected by Cloudflare's JS challenge
    (e.g. SEEK). Runs headless by default to avoid visible browser windows popping up.
    """
    from playwright.sync_api import sync_playwright

    time.sleep(delay_seconds)
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
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Wait for Cloudflare JS challenge to resolve
        page.wait_for_timeout(int(wait_seconds * 1000))
        html = page.content()
        browser.close()

    return html

def get_json(url: str, headers: dict | None = None, delay_seconds: float = 1.0) -> dict:
    """Fetch JSON from a URL with optional headers."""
    time.sleep(delay_seconds)
    h = {**DEFAULT_HEADERS, **(headers or {})}
    response = httpx.get(url, headers=h, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def fetch_rss(url: str, delay_seconds: float = 1.0) -> list[dict]:
    import feedparser
    time.sleep(delay_seconds)
    # Fetch via httpx so we control the User-Agent (Reddit blocks browser UAs on RSS)
    response = httpx.get(url, headers={"User-Agent": RSS_UA}, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    entries = []
    for entry in feed.entries:
        entries.append({
            "title": entry.get("title", ""),
            "body": entry.get("summary", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", ""),
        })
    return entries


def fetch_reddit_top_posts(subreddit: str, time_filter: str = "week", limit: int = 25, delay_seconds: float = 2.0) -> list[dict]:
    """Top posts in a subreddit, engagement-ranked, via the public RSS feed.

    Reddit's .json API is 403-blocked unauthenticated and the script-app
    OAuth grant is broken — /top/.rss?t=<filter> is the only path that
    still works. RSS doesn't carry score or num_comments, so we synthesise
    a position-based score (#1 -> limit, #2 -> limit-1, ...) which keeps
    downstream `ORDER BY post_score` consistent with engagement order.
    num_comments stays 0.

    Returns list of dicts: {title, body, url, published, score, num_comments, created_utc}.
    """
    import feedparser
    from datetime import datetime, timezone

    time.sleep(delay_seconds)
    url = f"{REDDIT_PUBLIC_HOST}/r/{subreddit}/top/.rss?t={time_filter}"
    response = httpx.get(
        url,
        headers={"User-Agent": RSS_UA},
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.text)

    entries = list(feed.entries)[:limit]
    n = len(entries)
    posts: list[dict] = []
    for i, entry in enumerate(entries):
        synthetic_score = n - i  # #1 gets n, last gets 1; preserves engagement order

        created_utc = 0.0
        pub = entry.get("published", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                created_utc = dt.timestamp()
            except Exception:
                created_utc = 0.0

        posts.append({
            "title": entry.get("title", ""),
            "body": entry.get("summary", ""),
            "url": entry.get("link", ""),
            "published": pub,
            "score": synthetic_score,
            "num_comments": 0,
            "created_utc": created_utc,
        })
    return posts


def fetch_reddit_comments(post_url: str, top_n: int = 3) -> dict:
    """Fetch top N comments and post score from a Reddit post via the public .json.

    Currently 403-blocked (Reddit lockdown), so this almost always returns the
    empty failure sentinel {"post_score": 0, "comments": []}. Callers should
    treat that as "no data available" rather than "zero engagement" — see
    editorial/reddit_rss.py::_enrich_one for the guard pattern.

    Consumed by: editorial/reddit_rss.py _enrich_one, dashboard /api/fetch-thread-comments.
    """
    json_url = post_url.rstrip("/") + ".json"
    time.sleep(2.0)
    try:
        response = httpx.get(
            json_url,
            headers={"User-Agent": RSS_UA},
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"fetch_reddit_comments: request failed for {post_url}: {e}")
        return {"post_score": 0, "comments": []}

    if not isinstance(data, list) or len(data) < 2:
        return {"post_score": 0, "comments": []}

    # Extract post score from the first listing
    post_score = 0
    post_children = data[0].get("data", {}).get("children", [])
    if post_children:
        post_score = post_children[0].get("data", {}).get("score") or 0

    children = data[1].get("data", {}).get("children", [])
    scored: list[tuple[int, str]] = []
    for child in children:
        if child.get("kind") != "t1":
            continue
        body: str = child.get("data", {}).get("body", "")
        score: int = child.get("data", {}).get("score") or 0
        if body and body not in ("[deleted]", "[removed]"):
            scored.append((score, body))

    scored.sort(key=lambda x: x[0], reverse=True)
    return {
        "post_score": post_score,
        "comments": [{"text": body, "score": score} for score, body in scored[:top_n]],
    }
