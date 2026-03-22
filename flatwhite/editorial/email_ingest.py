"""Email newsletter ingest — pulls editorial content from labelled Gmail newsletters.

Polls Gmail for unread emails matching configured labels and sender filters,
parses HTML to extract headline + snippet pairs, and inserts each as a raw_item.

Sources: AFR Street Talk, AFR Rear Window, AFR Chanticleer, Crikey Worm,
Australasian Lawyer.

Requires Gmail API OAuth credentials at data/gmail_credentials.json.
Disabled by default — set email_ingest.enabled=true in config.yaml.
"""

from __future__ import annotations

import base64
import yaml
from pathlib import Path
from bs4 import BeautifulSoup

from flatwhite.db import insert_raw_item, get_current_week_iso

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _get_gmail_service() -> object:
    """Authenticate via Gmail API OAuth and return the service object.

    Looks for credentials at data/gmail_credentials.json and token at
    data/gmail_token.json. If token exists and is valid, uses it. If expired,
    refreshes. If no token, runs InstalledAppFlow to generate one.

    Returns a Gmail API service resource.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    email_config = config.get("email_ingest", {})
    credentials_path = DATA_DIR / email_config.get("credentials_path", "gmail_credentials.json")
    token_path = DATA_DIR / email_config.get("token_path", "gmail_token.json")

    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        pass
    elif creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _parse_headlines(html: str) -> list[dict]:
    """Parse newsletter HTML to extract headline + snippet pairs.

    Strategy 1: Find heading tags (h1-h4), grab next sibling paragraph as body,
    nearest <a href> as URL.

    Strategy 2 (fallback for table-based layouts): Find <strong> tags with 10+
    char text, look for body in parent's siblings.

    Returns list of {"title": str, "body": str, "url": str}, capped at 10 items.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # Strategy 1: heading-based extraction
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Find nearest <a href> for URL
        url = ""
        link = heading.find("a", href=True)
        if link:
            url = link["href"]
        else:
            # Check parent for a link wrapping the heading
            parent_link = heading.find_parent("a", href=True)
            if parent_link:
                url = parent_link["href"]

        # Grab next sibling paragraph as body
        body = ""
        sibling = heading.find_next_sibling()
        while sibling:
            if sibling.name == "p":
                body = sibling.get_text(strip=True)
                if not url:
                    sib_link = sibling.find("a", href=True)
                    if sib_link:
                        url = sib_link["href"]
                break
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                break
            sibling = sibling.find_next_sibling()

        results.append({"title": title, "body": body, "url": url})
        if len(results) >= 10:
            return results

    # Strategy 2 (fallback for table-based layouts): <strong> tags
    if not results:
        for strong in soup.find_all("strong"):
            title = strong.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            # Avoid picking up generic labels
            if title.lower() in ("read more", "click here", "unsubscribe", "view in browser"):
                continue

            url = ""
            link = strong.find("a", href=True)
            if link:
                url = link["href"]
            else:
                parent_link = strong.find_parent("a", href=True)
                if parent_link:
                    url = parent_link["href"]

            # Look for body text in parent's next siblings
            body = ""
            parent = strong.parent
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    body = sibling.get_text(strip=True)
                    if not url:
                        sib_link = sibling.find("a", href=True)
                        if sib_link:
                            url = sib_link["href"]

            results.append({"title": title, "body": body, "url": url})
            if len(results) >= 10:
                return results

    return results


def _get_label_id(service: object, label_name: str) -> str | None:
    """Look up a Gmail label ID by its full name (e.g. 'flatwhite/afr-street-talk').

    Returns the label ID string, or None if not found.
    """
    try:
        response = service.users().labels().list(userId="me").execute()  # type: ignore[union-attr]
        labels = response.get("labels", [])
        for label in labels:
            if label["name"] == label_name:
                return label["id"]
    except Exception as e:
        print(f"  WARN: Failed to look up label '{label_name}': {e}")
    return None


def _extract_html_body(message: dict) -> str:
    """Extract HTML body from a Gmail message, handling multipart and single-part formats."""
    payload = message.get("payload", {})

    # Check for multipart message
    parts = payload.get("parts", [])
    if parts:
        for part in parts:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            # Handle nested multipart
            nested_parts = part.get("parts", [])
            for nested in nested_parts:
                if nested.get("mimeType", "") == "text/html":
                    data = nested.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Single-part message
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return ""


def pull_email_newsletters() -> int:
    """Pull editorial items from labelled Gmail newsletters.

    For each configured source, queries Gmail for unread emails matching
    label + sender_filter, parses HTML body, extracts headlines, and inserts
    each as a raw_item. Marks emails as read after processing.

    Returns count of newly inserted items.
    Disabled by default — set email_ingest.enabled=true in config.yaml.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    email_config = config.get("email_ingest", {})
    if not email_config.get("enabled", False):
        print("  Email ingest disabled in config.yaml")
        return 0

    # Try to get Gmail service — if auth fails, return 0 gracefully
    try:
        service = _get_gmail_service()
    except Exception as e:
        print(f"  WARN: Gmail authentication failed — skipping email ingest: {e}")
        return 0

    sources = email_config.get("sources", [])
    if not sources:
        print("  No email sources configured in config.yaml")
        return 0

    week_iso = get_current_week_iso()
    total_inserted = 0

    for source_cfg in sources:
        label_name = source_cfg["label"]
        source_tag = source_cfg["source_tag"]
        sender_filter = source_cfg["sender_filter"]

        label_id = _get_label_id(service, label_name)
        if not label_id:
            print(f"  WARN: Gmail label '{label_name}' not found — skipping")
            continue

        try:
            # Query for unread emails with this label
            query = f"from:{sender_filter} is:unread"
            response = service.users().messages().list(  # type: ignore[union-attr]
                userId="me",
                labelIds=[label_id],
                q=query,
                maxResults=5,
            ).execute()

            messages = response.get("messages", [])
            if not messages:
                print(f"  {source_tag}: no unread emails")
                continue

            source_count = 0
            for msg_ref in messages:
                msg_id = msg_ref["id"]

                # Fetch full message
                message = service.users().messages().get(  # type: ignore[union-attr]
                    userId="me",
                    id=msg_id,
                    format="full",
                ).execute()

                # Extract HTML body
                html_body = _extract_html_body(message)
                if not html_body:
                    print(f"  WARN: No HTML body in message {msg_id} — skipping")
                    continue

                # Parse headlines
                headlines = _parse_headlines(html_body)
                for item in headlines:
                    title = item["title"][:200] if item["title"] else ""
                    body = item["body"][:2000] if item["body"] else ""
                    url = item["url"] or ""

                    if not title:
                        continue

                    insert_raw_item(
                        title=title,
                        body=body,
                        source=source_tag,
                        url=url,
                        lane="editorial",
                        subreddit=None,
                        week_iso=week_iso,
                    )
                    source_count += 1

                # Mark email as read
                service.users().messages().modify(  # type: ignore[union-attr]
                    userId="me",
                    id=msg_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()

            total_inserted += source_count
            print(f"  {source_tag}: {source_count} items from {len(messages)} emails")

        except Exception as e:
            print(f"  WARN: Failed to process {source_tag}: {e}")
            continue

    return total_inserted
