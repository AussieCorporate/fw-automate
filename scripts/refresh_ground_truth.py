"""Refresh data/beehiiv_fw_ground_truth.json from every published Flat White
edition on beehiiv.

Why this exists: the corpus is what every length benchmark, the subject-line
calibration and the voice specs are measured against, and it was built by hand
once, covering 4 May - 6 Jul 2026. By 25 Aug it was seven editions stale and
nothing could refresh it, so "match the published length" was being checked
against a snapshot that no longer described the newsletter. Victor's standing
rule is that published editions outrank rule text - that only works if the
published editions are actually on hand.

Usage:
    .venv/bin/python -m scripts.refresh_ground_truth            # all editions
    .venv/bin/python -m scripts.refresh_ground_truth --limit 20 # newest 20

Writes the same shape the old file used, so benchmark.py needs no change:
    [{"post_id", "date", "title", "segments": [{"name", "text", "word_count"}]}]
Newest edition first.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "beehiiv_fw_ground_truth.json"

# Flat White. Deliberately a constant, not BEEHIIV_PUB_ID - that env var points
# at Pick & Scroll (it feeds the Top Picks scrape).
FW_PUB_ID = "pub_6210ff81-d440-4e09-916d-42fe436f0d05"

# Segment headings are H1-H3. H4 is NOT a boundary: Thread of the Week sets the
# reddit thread's own title as an H4 inside the segment, and treating that as a
# new segment renamed "THREAD OF THE WEEK" to the thread's title.
_HEADING = re.compile(r"^#{1,3}(?!#)\s*\*{0,2}(.+?)\*{0,2}\s*$")
# Furniture that is not a segment: the forwarded-to-you line, the divider rows
# and the plain-text footer beehiiv appends.
_FOOTER_MARKER = "You are reading a plain text version of this post"


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _fetch_posts(key: str, limit: int | None) -> list[dict]:
    posts: list[dict] = []
    for page in range(1, 20):
        r = requests.get(
            f"https://api.beehiiv.com/v2/publications/{FW_PUB_ID}/posts",
            headers={"Authorization": f"Bearer {key}"},
            params={"status": "confirmed", "limit": 50, "page": page,
                    "order_by": "publish_date", "direction": "desc"},
            timeout=30)
        r.raise_for_status()
        batch = r.json().get("data") or []
        if not batch:
            break
        posts += batch
        if limit and len(posts) >= limit:
            break
    return posts[:limit] if limit else posts


def _fetch_text(key: str, post_id: str) -> str:
    r = requests.get(
        f"https://api.beehiiv.com/v2/publications/{FW_PUB_ID}/posts/{post_id}",
        headers={"Authorization": f"Bearer {key}"},
        params={"expand[]": "free_email_content"}, timeout=30)
    r.raise_for_status()
    content = (r.json().get("data") or {}).get("content") or {}
    return (content.get("free") or {}).get("email") or ""


def _html_to_text(html: str) -> str:
    """Crude HTML -> plain text, enough for word counts and segment splits."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    # Keep headings recognisable as markdown, PRESERVING the level: segment
    # headings are h1-h3, while h4 is used inside a segment (the Thread of the
    # Week title) and must not read as a boundary.
    text = re.sub(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", r"\n\n### \1\n", text)
    text = re.sub(r"(?is)<h4[^>]*>(.*?)</h4>", r"\n\n#### \1\n", text)
    text = re.sub(r"(?is)<li[^>]*>", "\n* ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>|</div>|</tr>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#39;", "'").replace("&quot;", '"')
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&rsquo;", "’").replace("&ldquo;", "“")
                .replace("&rdquo;", "”"))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_segments(text: str) -> list[dict]:
    """Split an edition's plain text into {name, text, word_count} segments on
    its H3 headings. Everything before the first heading is the INTRO, matching
    how the original hand-built corpus was keyed."""
    if _FOOTER_MARKER in text:
        text = text.split(_FOOTER_MARKER)[0]

    lines = text.splitlines()
    segments: list[dict] = []
    current_name = "INTRO"
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            segments.append({"name": current_name, "text": body,
                             "word_count": _word_count(body)})

    for line in lines:
        stripped = line.strip()
        is_heading = stripped.startswith("#") and _HEADING.match(stripped)
        if is_heading:
            name = _HEADING.match(stripped).group(1).strip()
            # Ignore empty or divider-ish headings.
            if name and not set(name) <= {"-", "—", "*", " "}:
                flush()
                buf = []
                current_name = name
                continue
        buf.append(line)
    flush()
    return segments


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="only the newest N editions (default: all)")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)

    load_dotenv(str(ROOT / ".env"))
    key = os.getenv("BEEHIIV_API_KEY")
    if not key:
        print("BEEHIIV_API_KEY is not set; cannot refresh the corpus.", file=sys.stderr)
        return 1

    posts = _fetch_posts(key, args.limit)
    print(f"Fetched {len(posts)} published editions.")

    editions: list[dict] = []
    for i, p in enumerate(posts, 1):
        ts = p.get("publish_date")
        if not ts:
            continue
        date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()
        try:
            html = _fetch_text(key, p["id"])
        except Exception as exc:  # noqa: BLE001 - skip one bad edition, keep the rest
            print(f"  ! {date} {p.get('title','')[:40]}: {exc}")
            continue
        segments = parse_segments(_html_to_text(html))
        if not segments:
            print(f"  ! {date} {p.get('title','')[:40]}: no segments parsed, skipped")
            continue
        editions.append({"post_id": p["id"], "date": date,
                         "title": p.get("title", ""), "segments": segments})
        print(f"  {i:3d}. {date}  {len(segments):2d} segments  {p.get('title','')[:48]}")

    if not editions:
        print("Nothing parsed; leaving the existing corpus untouched.", file=sys.stderr)
        return 1

    Path(args.out).write_text(json.dumps(editions, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(editions)} editions to {args.out}")
    print(f"Range: {editions[-1]['date']} -> {editions[0]['date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
