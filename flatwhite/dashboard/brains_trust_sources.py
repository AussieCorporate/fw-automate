"""Email Victor the source research PDFs behind a chosen Brains Trust angle.

When Victor picks a Brains Trust angle in the dashboard, that angle carries the
`source_pdf_ids` of the broker-research PDFs it was built from (surfaced by
brains_trust_research.py). This module turns those ids into a plain-English
email: for each PDF, its filename, who sent it, when, a link that opens the
original research email (so Victor can grab the charts), and the local file
path as a fallback.

READ-ONLY against the Trading Strategy research DB (SQLite ?mode=ro), exactly
like brains_trust_research.py. Never imports from or writes to that project.
Sends via the SHARED Gmail login (Gmail API, not SMTP — Workspace blocks SMTP
app passwords), the same token used by PS sends and TS ingest.
"""
from __future__ import annotations

import base64
import os
import sqlite3
from email.mime.text import MIMEText

_DEFAULT_ROOT = os.environ.get(
    "BRAINS_TRUST_ROOT", "/Users/victornguyen/Documents/MISC/Trading Strategy/data"
)
# Shared Gmail login (full scope: read + modify + send).
_TOKEN_PATH = os.environ.get(
    "SHARED_GMAIL_TOKEN",
    "/Users/victornguyen/Documents/MISC/Trading Strategy/credentials/token.json",
)
_CREDS_PATH = os.environ.get(
    "SHARED_GMAIL_CREDENTIALS",
    "/Users/victornguyen/Documents/MISC/Trading Strategy/credentials/credentials.json",
)
# The FULL scope set of the shared token, even though this module only sends.
# Loading it with a narrower list and then writing the refreshed credentials
# back (see _gmail_service) rewrites the shared token.json down to those
# scopes, which breaks the Trading Strategy research ingest and the TAC
# carousel job that also read it. That happened on 20 Jul 2026 and starved
# Brains Trust of fresh research; keep this identical to that project's
# src/gmail_client.py SCOPES.
_SHARED_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
# Where the email is sent. Victor reads the linked research emails while logged
# into general@pickandscrollnews.com.au (where the research lands).
DEFAULT_TO = os.environ.get("BRAINS_TRUST_SOURCES_TO", "victor@dogasydney.com.au")


def _strip_email_name(sender: str) -> str:
    """'Jim McClure <x@y.com>' -> 'Jim McClure'; bare addresses untouched."""
    import re
    m = re.match(r"^(.*?)\s*<", sender or "")
    return m.group(1).strip() if m else (sender or "")


def resolve_source_pdfs(pdf_ids: list[int], root: str | None = None) -> list[dict]:
    """[{filename, sender, subject, date, gmail_url, file_path}, ...] for the
    given PDF ids, from the read-only research DB. Missing ids are skipped;
    any DB problem yields []. Newest email first."""
    root = root or _DEFAULT_ROOT
    ids = [i for i in (pdf_ids or []) if isinstance(i, int)]
    db = os.path.join(root, "trading_strategy.db")
    if not ids or not os.path.exists(db):
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        try:
            q = (
                "SELECT p.id, p.filename, p.content_hash, e.sender, e.subject, "
                "e.date_received, e.gmail_id "
                "FROM pdfs p JOIN emails e ON e.id = p.email_id "
                "WHERE p.id IN (%s)" % ",".join("?" * len(ids))
            )
            fetched = con.execute(q, tuple(ids)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []

    rows = []
    for _pid, filename, content_hash, sender, subject, date_received, gmail_id in fetched:
        file_path = os.path.join(root, "pdfs", f"{content_hash}.pdf") if content_hash else ""
        gmail_url = (
            f"https://mail.google.com/mail/u/0/#all/{gmail_id}" if gmail_id else ""
        )
        rows.append({
            "filename": filename or "(unnamed PDF)",
            "sender": _strip_email_name(sender),
            "subject": subject or "",
            "date": str(date_received or "")[:10],
            "gmail_url": gmail_url,
            "file_path": file_path if os.path.exists(file_path) else "",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def build_email_html(pitch: str, rows: list[dict]) -> str:
    """Plain, readable HTML listing each source PDF with a link to its email."""
    font = ("font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
            "Helvetica,Arial,sans-serif;")
    parts = [
        f'<div style="{font}font-size:15px;color:#111;line-height:1.5;">',
        f'<p>Brains Trust angle you selected:</p>',
        f'<p style="font-weight:600;">{_esc(pitch)}</p>',
        f'<p>It drew on these broker-research PDFs. Open each email to grab the '
        f'charts (you\'ll need to be signed in as '
        f'general@pickandscrollnews.com.au):</p>',
        '<ol style="padding-left:20px;">',
    ]
    for r in rows:
        line = f'<li style="margin-bottom:12px;">'
        line += f'<span style="font-weight:600;">{_esc(r["filename"])}</span><br>'
        meta = []
        if r["sender"]:
            meta.append(_esc(r["sender"]))
        if r["date"]:
            meta.append(_esc(r["date"]))
        if meta:
            line += f'<span style="color:#555;font-size:13px;">{" &middot; ".join(meta)}</span><br>'
        if r["subject"]:
            line += f'<span style="color:#555;font-size:13px;">{_esc(r["subject"])}</span><br>'
        if r["gmail_url"]:
            line += (f'<a href="{_esc(r["gmail_url"])}" '
                     f'style="color:#1a56db;">Open the research email &rarr;</a>')
        if r["file_path"]:
            line += (f'<br><span style="color:#888;font-size:12px;">File: '
                     f'{_esc(r["file_path"])}</span>')
        line += '</li>'
        parts.append(line)
    parts.append('</ol></div>')
    return "\n".join(parts)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _gmail_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(_TOKEN_PATH, _SHARED_SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def send_source_pdf_email(pitch: str, pdf_ids: list[int], to: str | None = None,
                          root: str | None = None) -> dict:
    """Resolve the PDFs for `pitch`/`pdf_ids` and email them to Victor.
    Returns {ok, count, to, message}. Never raises for expected failures."""
    to = to or DEFAULT_TO
    rows = resolve_source_pdfs(pdf_ids, root=root)
    if not rows:
        return {"ok": False, "count": 0, "to": to,
                "message": "No source PDFs found for this angle."}
    html = build_email_html(pitch, rows)
    subject = f"Brains Trust source research: {(pitch or '').strip()[:80]}"
    msg = MIMEText(html, "html")
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service = _gmail_service()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"ok": True, "count": len(rows), "to": to,
            "message": f"Sent {len(rows)} source PDF(s) to {to}."}
