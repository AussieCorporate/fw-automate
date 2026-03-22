"""LinkedIn newsletter editorial source — self-hosted RSS converter.

Starts a local linkedin-newsletter-rss server (Cloudflare Worker) on demand,
fetches newsletter feeds, then shuts down the server. No background service needed.

Requires: linkedin-rss-local/ directory at project root with npm dependencies installed.
See: https://github.com/chrisns/linkedin-newsletter-rss
"""
from __future__ import annotations

import subprocess
import time
import yaml
from pathlib import Path

import httpx

from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # FW Automate/
LINKEDIN_RSS_DIR = PROJECT_ROOT / "linkedin-rss-local"
LOCAL_PORT = 8787
LOCAL_BASE = f"http://localhost:{LOCAL_PORT}"


def _start_server() -> subprocess.Popen | None:
    """Start the linkedin-newsletter-rss local server.

    Returns the process handle, or None if the server directory doesn't exist.
    """
    if not (LINKEDIN_RSS_DIR / "package.json").exists():
        print("    linkedin-rss-local/ not found — skipping LinkedIn newsletters")
        print("    To set up: cd to project root and run:")
        print("      git clone https://github.com/chrisns/linkedin-newsletter-rss.git linkedin-rss-local")
        print("      cd linkedin-rss-local && npm install")
        return None

    # Check if server is already running
    try:
        resp = httpx.get(f"{LOCAL_BASE}/health", timeout=2.0)
        if resp.status_code < 500:
            return None  # Already running externally — don't manage it
    except Exception:
        pass  # Not running — we'll start it

    proc = subprocess.Popen(
        ["npx", "wrangler", "dev", "--port", str(LOCAL_PORT)],
        cwd=str(LINKEDIN_RSS_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to be ready
    for _ in range(10):
        time.sleep(1)
        try:
            httpx.get(f"{LOCAL_BASE}/7026423261823475712", timeout=3.0)
            return proc
        except Exception:
            continue

    print("    LinkedIn RSS server failed to start within 10s")
    proc.kill()
    return None


def _stop_server(proc: subprocess.Popen | None) -> None:
    """Stop the local server if we started it."""
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def pull_linkedin_newsletters() -> int:
    """Pull LinkedIn newsletter content via self-hosted local RSS converter.

    Starts the server, fetches feeds, stops the server. No background service needed.
    Returns count of newly inserted items.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    ln_config = config.get("linkedin_newsletters", {})
    if not ln_config.get("enabled", False):
        print("    LinkedIn newsletters disabled in config")
        return 0

    newsletters = ln_config.get("newsletters", [])
    week_iso = get_current_week_iso()
    delay = ln_config.get("delay_between_pulls_seconds", 3)
    max_items = ln_config.get("max_items_per_newsletter", 5)

    # Start local server
    proc = _start_server()
    if proc is None and not (LINKEDIN_RSS_DIR / "package.json").exists():
        return 0

    total_inserted = 0
    try:
        for nl in newsletters:
            name = nl.get("name", "unknown")
            url = nl.get("url", "")

            if "{id}" in url:
                print(f"    {name}: skipped — placeholder URL")
                continue

            try:
                entries = fetch_rss(url, delay_seconds=delay)
                count = 0
                for entry in entries[:max_items]:
                    insert_raw_item(
                        title=entry["title"][:200],
                        body=entry["body"][:2000] if entry["body"] else None,
                        source=nl["source_tag"],
                        url=entry["url"],
                        lane="editorial",
                        subreddit=None,
                        week_iso=week_iso,
                    )
                    count += 1
                total_inserted += count
                print(f"    {name}: {count} items")
            except Exception as e:
                print(f"    {name}: FAILED — {e}")
                continue
    finally:
        _stop_server(proc)

    return total_inserted
