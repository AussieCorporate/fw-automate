from __future__ import annotations

import httpx
import time

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
RSS_UA = "flatwhite/0.1 (by TAC)"

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


def fetch_reddit_comments(post_url: str, top_n: int = 3) -> dict:
    """Fetch top N comments and post score from a Reddit post using the public JSON API.

    No authentication required. Returns dict with 'post_score' and 'comments'
    (list of dicts with 'text' and 'score'), sorted by score descending.
    Skips deleted/removed comments.

    Input: post_url — full Reddit post URL (e.g. https://www.reddit.com/r/auscorp/comments/...)
    Output: {"post_score": int, "comments": [{"text": str, "score": int}, ...]}.
    Consumed by: classify/thread_ranker.py rank_thread_candidates(), dashboard API.
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
