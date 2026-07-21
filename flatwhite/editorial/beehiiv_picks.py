"""Fetch top-clicked links from Pick & Scroll News via Beehiiv API.

Pulls posts published in the last 7 days, aggregates click data across all
editions, and extracts the summary sentence adjacent to each link from the
newsletter HTML content.

Three API calls per post:
1. GET /posts (list recent posts)
2. GET /posts/{id}?expand[]=stats (click analytics per link)
3. Same call also returns content.free.web (HTML body for sentence extraction)

Output: list of dicts sorted by total_clicks descending, each with:
  url, summary, clicks, campaign_title, campaign_url, source_domain
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

BEEHIIV_API_KEY = os.getenv("BEEHIIV_API_KEY", "")
BEEHIIV_PUB_ID = os.getenv("BEEHIIV_PUB_ID", "")
BASE_URL = f"https://api.beehiiv.com/v2/publications/{BEEHIIV_PUB_ID}"

# URLs to exclude from top-clicks ranking (internal promos, subscribe links, etc.)
# theaussiecorporate.com and tally.so are our own blog and our own surveys/polls:
# they out-click editorial links but are self-promo, not a "top pick".
EXCLUDE_DOMAINS = {
    "beehiiv.com",
    "salaryvault.com.au",
    "theaussiecorporate.beehiiv.com",
    "theaussiecorporate.com",
    "tally.so",
    "facebook.com",
    "twitter.com",
    "threads.net",
    "linkedin.com",
    "instagram.com",
}


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {BEEHIIV_API_KEY}"}


def _domain(url: str) -> str:
    """Extract clean domain from URL."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _strip_utm(url: str) -> str:
    """Remove utm_* query params from a URL for cleaner display."""
    base = url.split("?")[0]
    return base


def _is_excluded(url: str) -> bool:
    """Check if a URL should be excluded from ranking."""
    domain = _domain(url)
    return any(excl in domain for excl in EXCLUDE_DOMAINS)


# Every Pick & Scroll STORY is republished to our own Shopify blog at
# theaussiecorporate.com/blogs/pickandscrollnews/<slug>, and that blog link is
# the story's link in the newsletter. That domain sits on the exclude list as
# self-promo, so the story links were being dropped from the ranking entirely -
# leaving only incidental in-article links. Detect our own story links so we
# rank THOSE (the real stories) by clicks, not the incidental ones.
_PS_STORY_PATH = "/blogs/pickandscrollnews/"


def _is_ps_story(url: str) -> bool:
    """True if the URL is one of our own Pick & Scroll story blog posts."""
    parsed = urlparse(url)
    host = (parsed.hostname or "")
    if host.startswith("www."):
        host = host[4:]
    return host.endswith("theaussiecorporate.com") and _PS_STORY_PATH in (parsed.path or "")


class _TextAroundLinkExtractor(HTMLParser):
    """Parse newsletter HTML to extract the sentence/paragraph around each link."""

    def __init__(self):
        super().__init__()
        self._link_map: dict[str, str] = {}  # base_url -> surrounding text
        self._current_block_text: list[str] = []
        self._current_block_links: list[str] = []
        self._in_p = False
        self._in_a = False
        self._anchor_text: list[str] = []
        self._last_anchor_label = ""

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._in_p = True
            self._current_block_text = []
            self._current_block_links = []
            self._last_anchor_label = ""
        if tag == "a":
            self._in_a = True
            self._anchor_text = []
            href = dict(attrs).get("href", "")
            if href and href.startswith("http"):
                self._current_block_links.append(href)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            self._last_anchor_label = " ".join("".join(self._anchor_text).split()).strip()
        if tag == "p" and self._in_p:
            self._in_p = False
            text = " ".join("".join(self._current_block_text).split()).strip()
            # The paragraph text includes the anchor's own label, and Pick & Scroll
            # ends every item with a link labelled "LINK". Left in, the summary reads
            # "... rates fall. LINK" and any consumer that appends its own hyperlink
            # renders the label twice. Drop the trailing label.
            label = self._last_anchor_label
            if label and text.endswith(label):
                text = text[: -len(label)].strip()
            if text and len(text) > 10:
                for link in self._current_block_links:
                    base = _strip_utm(link)
                    if base not in self._link_map:
                        self._link_map[base] = text

    def handle_data(self, data):
        if self._in_p:
            self._current_block_text.append(data)
        if self._in_a:
            self._anchor_text.append(data)

    def get_summaries(self) -> dict[str, str]:
        return dict(self._link_map)


# Section labels ("Editor's Pick:", "Doctor's Pick:", "Draft Pick:" — straight or
# curly apostrophe) and the daily edition's greeting, both of which lead the
# paragraph but are not part of the story sentence.
_PREFIX_RE = re.compile(r"^[A-Za-z]+(?:['’]s)?\s*Pick\s*[:–—-]\s*", re.I)
_GREETING_RE = re.compile(r"^Good morning[.!]\s*", re.I)


def _clean_summary(text: str) -> str:
    """Strip leading section labels / greetings from an extracted summary."""
    text = _PREFIX_RE.sub("", text.strip())
    return _GREETING_RE.sub("", text).strip()


def _extract_summaries_from_html(html: str) -> dict[str, str]:
    """Extract link -> surrounding paragraph text from newsletter HTML."""
    parser = _TextAroundLinkExtractor()
    parser.feed(html)
    return {url: _clean_summary(text) for url, text in parser.get_summaries().items()}


def fetch_recent_posts(days: int = 7, start=None, end=None) -> list[dict]:
    """Fetch posts published in a date window from Beehiiv API.

    By default the last N days. Pass timezone-aware ``start``/``end`` datetimes
    to bound an explicit window (the calendar range on the Top Picks screen).

    Returns list of post metadata dicts (id, title, slug, publish_date, web_url).
    """
    now = datetime.now(timezone.utc)
    lo = start or (now - timedelta(days=days))
    hi = end or now

    posts: list[dict] = []
    page = 1

    while True:
        resp = httpx.get(
            f"{BASE_URL}/posts",
            headers=_headers(),
            params={
                "status": "confirmed",
                "order_by": "publish_date",
                "direction": "desc",
                "limit": 10,
                "page": page,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        for post in data.get("data", []):
            pub_ts = post.get("publish_date", 0)
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
            if pub_dt < lo:
                return posts          # desc order: nothing older will qualify
            if pub_dt > hi:
                continue              # newer than the window: skip, keep scanning
            posts.append({
                "id": post["id"],
                "title": post.get("title", ""),
                "slug": post.get("slug", ""),
                "publish_date": pub_dt.isoformat(),
                "web_url": post.get("web_url", ""),
            })

        if page >= data.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.5)

    return posts


def fetch_post_clicks_and_content(post_id: str) -> dict:
    """Fetch click analytics and HTML content for a single post.

    Returns dict with keys: clicks (list), html (str), title (str), web_url (str).
    """
    resp = httpx.get(
        f"{BASE_URL}/posts/{post_id}",
        headers=_headers(),
        params={"expand[]": ["stats", "free_web_content"]},
        timeout=30.0,
    )
    resp.raise_for_status()
    post = resp.json().get("data", {})

    clicks = post.get("stats", {}).get("clicks", [])
    html = post.get("content", {}).get("free", {}).get("web", "")

    return {
        "clicks": clicks,
        "html": html,
        "title": post.get("title", ""),
        "web_url": post.get("web_url", ""),
        "slug": post.get("slug", ""),
    }


def scrape_top_picks(days: int = 7, limit: int = 20, start=None, end=None) -> list[dict]:
    """Main entry point: fetch a window of Pick & Scroll editions and rank links by clicks.

    Our own PS story links are TAGGED (is_ps_story=True) and always kept even
    with zero clicks (their self-promo domain is otherwise excluded), so callers
    can rank the real stories rather than incidental in-article links.

    Returns list of dicts sorted by verified clicks descending, each with:
        url, summary, clicks, verified_clicks, is_ps_story, edition_date,
        campaign_title, campaign_url, source_domain
    """
    posts = fetch_recent_posts(days=days, start=start, end=end)
    if not posts:
        return []

    # Aggregate clicks across all posts
    # Key: clean base URL -> aggregated data
    link_agg: dict[str, dict] = {}

    for post in posts:
        time.sleep(0.5)  # rate-limit courtesy
        try:
            data = fetch_post_clicks_and_content(post["id"])
        except Exception as e:
            print(f"  Warning: failed to fetch post {post['id']}: {e}")
            continue

        summaries = _extract_summaries_from_html(data["html"])

        for click_entry in data["clicks"]:
            raw_url = click_entry.get("url", "")
            base_url = click_entry.get("base_url", "") or _strip_utm(raw_url)
            total = click_entry.get("total_clicks", 0)
            # Raw clicks count bot and scanner opens; verified clicks are the honest
            # signal (a real link can show 54 raw / 32 verified, and pure-bot links
            # show 0 verified). Rank on verified, keep raw for display.
            verified = (click_entry.get("email") or {}).get("verified_clicks", 0) or 0

            is_ours = _is_ps_story(raw_url) or _is_ps_story(base_url)
            # Our own story links are self-hosted (on the exclude list) but must
            # be kept; everything else on the exclude list is genuine self-promo.
            if not is_ours and (_is_excluded(raw_url) or _is_excluded(base_url)):
                continue

            if base_url not in link_agg:
                # Try to find summary for this URL
                summary = summaries.get(base_url, "")
                if not summary:
                    # Try matching without trailing slash
                    for surl, stxt in summaries.items():
                        if surl.rstrip("/") == base_url.rstrip("/"):
                            summary = stxt
                            break

                link_agg[base_url] = {
                    "url": base_url,
                    "summary": summary,
                    "clicks": 0,
                    "verified_clicks": 0,
                    "is_ps_story": is_ours,
                    "edition_date": post.get("publish_date", ""),
                    "campaign_title": data["title"],
                    "campaign_url": data["web_url"],
                    "source_domain": _domain(base_url),
                    "campaigns": [],
                }

            link_agg[base_url]["clicks"] += total
            link_agg[base_url]["verified_clicks"] += verified
            link_agg[base_url]["campaigns"].append({
                "title": data["title"],
                "url": data["web_url"],
                "clicks_in_campaign": total,
            })

        # A story can draw ZERO clicks, and beehiiv may not list a zero-click
        # link in stats at all. So sweep the edition's HTML links directly and
        # add any of our own stories we haven't already captured.
        for surl, stext in summaries.items():
            b = _strip_utm(surl)
            if not _is_ps_story(b) or b in link_agg:
                continue
            link_agg[b] = {
                "url": b,
                "summary": stext,
                "clicks": 0,
                "verified_clicks": 0,
                "is_ps_story": True,
                "edition_date": post.get("publish_date", ""),
                "campaign_title": data["title"],
                "campaign_url": data["web_url"],
                "source_domain": _domain(b),
                "campaigns": [],
            }

    # Sort by verified clicks descending, falling back to raw for ties
    ranked = sorted(
        link_agg.values(),
        key=lambda x: (x["verified_clicks"], x["clicks"]),
        reverse=True,
    )

    return ranked[:limit]


# ── ONE MORE SCROLL (odd picks) ──────────────────────────────────────────────
# The "one more scroll" segment of each PS edition holds the editorial odd picks
# (Editor's Pick / Draft Pick / Doctor's Pick etc.): a bold label, a summary
# sentence, and an external link. Unlike click-ranked news these are chosen by
# the editor, so we read them straight out of the newsletter HTML rather than
# from click data.
_OMS_STOPS = ("TRIVIA", "OUR SOCIALS", "ANSWERS", "TOGETHER WITH", "CHART OF THE DAY")
# Each odd pick starts with a bold label CONTAINING the word "pick" (Editor's
# Pick / Draft Pick / Doctor's Pick / ...). Split on these, NOT on any <b> - a
# bolded word inside a pick's own text used to truncate it mid-sentence.
_PICK_LABEL_RE = re.compile(r"(?is)<b>\s*([^<]*?pick[^<]*?)\s*</b>")


def _shorten_odd(text: str, cap: int = 130) -> str:
    """Tighten an odd-pick summary to the published One More Scroll style: drop
    the trailing 'LINK' anchor label, keep the first sentence, and cap length so
    the rambly narrative picks don't dwarf the punchy ones."""
    text = re.sub(r"\s*\bLINK\b\s*$", "", text).strip()
    m = re.match(r"(.{20,}?[.!?])(?:\s|$)", text)   # first real sentence
    if m:
        text = m.group(1).strip()
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return text.strip()


def scrape_one_more_scroll(days: int = 7, start=None, end=None) -> list[dict]:
    """Odd picks from the 'One More Scroll' segment across the editions in the
    window. [{label, summary, url, edition_date}, ...], newest edition first,
    deduped. Never raises for a single bad edition."""
    posts = fetch_recent_posts(days=days, start=start, end=end)
    out: list[dict] = []
    seen: set[str] = set()
    for p in posts:
        try:
            html = fetch_post_clicks_and_content(p["id"])["html"]
        except Exception:  # noqa: BLE001 - one bad edition must not kill the list
            continue
        idx = html.upper().find("ONE MORE SCROLL")
        if idx < 0:
            continue
        section = re.sub(r"(?is)<style.*?</style>", " ", html[idx:])  # kill CSS bleed
        for stop in _OMS_STOPS:
            j = section.upper().find(stop, 30)
            if j > 0:
                section = section[:j]
                break
        labels = list(_PICK_LABEL_RE.finditer(section))
        for i, m in enumerate(labels):
            label = re.sub(r"<[^>]+>", "", m.group(1)).strip().rstrip(":")
            body = section[m.end():(labels[i + 1].start() if i + 1 < len(labels) else len(section))]
            um = re.search(r'href="([^"]+)"', body)
            url = _strip_utm(um.group(1)) if um else ""
            text = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip())
            text = _shorten_odd(text)
            if not text:
                continue
            key = url or text[:60]
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "label": label,
                "summary": text,
                "url": url,
                "edition_date": p["publish_date"][:10],
            })
    return out
