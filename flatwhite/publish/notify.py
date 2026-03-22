from __future__ import annotations

"""Pipeline completion email notification.

Sends a brief summary email to the editor after each weekly pipeline run,
prompting them to open the dashboard and review items before assembly.

SMTP credentials are read from .env:
    NOTIFY_SMTP_HOST     — SMTP server hostname (e.g. smtp.gmail.com)
    NOTIFY_SMTP_PORT     — SMTP port (default 587)
    NOTIFY_SMTP_USER     — Login username / sending address
    NOTIFY_SMTP_PASSWORD — Login password or app password
    NOTIFY_TO_EMAIL      — Recipient address (default: flatwhite@theaussiecorporate.com)
    NOTIFY_DASHBOARD_URL — Dashboard URL shown in email (default: http://localhost:8500)
"""

import os
import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


def _build_email_body(pulse_score: int | None, items_count: int, errors: list[str]) -> str:
    """Build plain-text email body for the pipeline ready notification."""
    dashboard_url = os.getenv("NOTIFY_DASHBOARD_URL", "http://localhost:8500")
    week = datetime.now(timezone.utc).strftime("%Y-W%W")

    pulse_line = f"Pulse score: {pulse_score}" if pulse_score is not None else "Pulse score: not yet calculated"
    error_section = ""
    if errors:
        error_section = "\nWarnings during this run:\n" + "\n".join(f"  - {e}" for e in errors) + "\n"

    return f"""Flat White pipeline finished — {week}

{pulse_line}
Items queued for review: {items_count}
{error_section}
Open the editor dashboard to review, approve, and assemble this week's newsletter:
{dashboard_url}

Steps to complete:
  1. Review curated items (Approve / Reject / Reserve)
  2. Pick your hook line
  3. Refine the Big Conversation draft
  4. Run: flatwhite assemble --hook 'your hook text'

—
Flat White automation
"""


def send_pipeline_ready_email(
    pulse_score: int | None = None,
    items_count: int = 0,
    errors: list[str] | None = None,
) -> bool:
    """Send a pipeline-ready notification email to the editor.

    Input:
      pulse_score  — current week pulse score (int or None if not calculated)
      items_count  — number of curated items queued for review
      errors       — list of error/warning strings from the pipeline run

    Output: True if email sent successfully, False otherwise.
    Consumed by: cli.py cmd_notify(), cron/flatwhite_weekly.sh (via CLI).
    """
    smtp_host = os.getenv("NOTIFY_SMTP_HOST", "")
    smtp_port = int(os.getenv("NOTIFY_SMTP_PORT", "587"))
    smtp_user = os.getenv("NOTIFY_SMTP_USER", "")
    smtp_password = os.getenv("NOTIFY_SMTP_PASSWORD", "")
    to_email = os.getenv("NOTIFY_TO_EMAIL", "flatwhite@theaussiecorporate.com")

    if not smtp_host or not smtp_user or not smtp_password:
        print("WARN: NOTIFY_SMTP_HOST / NOTIFY_SMTP_USER / NOTIFY_SMTP_PASSWORD not set — skipping email")
        return False

    if errors is None:
        errors = []

    week = datetime.now(timezone.utc).strftime("%Y-W%W")
    subject = f"[Flat White] Pipeline ready — {week}"
    body = _build_email_body(pulse_score, items_count, errors)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        print(f"  Notification sent → {to_email}")
        return True
    except (smtplib.SMTPException, OSError, socket.timeout) as e:
        print(f"WARN: Failed to send notification email: {e}")
        return False
