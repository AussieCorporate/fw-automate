"""Assembles approved editor decisions and generated content into newsletter HTML.

render_newsletter() is the single entry point. It:
1. Reads approved items from editor_decisions.
2. Reads pulse data from pulse_history.
3. Calls Session 2 functions for driver bullets and big conversation draft.
4. Renders each section via HTML templates.
5. Returns a single HTML string for newsletter email content.

No Jinja2. No template engine. All rendering is string.format() on constants.
"""

import json
from flatwhite.db import get_connection, get_current_week_iso, get_pulse_history
from flatwhite.assemble.templates import (
    HOOK_TEMPLATE,
    PULSE_TEMPLATE,
    DRIVER_BULLET_TEMPLATE,
    BIG_CONVERSATION_TEMPLATE,
    WHISPERS_HEADER_TEMPLATE,
    WHISPER_ITEM_TEMPLATE,
    WHISPERS_FOOTER_TEMPLATE,
    WATCHING_SECTION_TEMPLATE,
    WATCHING_ITEM_TEMPLATE,
    THREAD_TEMPLATE,
    FINDS_HEADER_TEMPLATE,
    FINDS_ITEM_TEMPLATE,
    FINDS_FOOTER_TEMPLATE,
    POLL_TEMPLATE,
    POLL_OPTION_TEMPLATE,
    FOOTER_TEMPLATE,
)


def _get_approved_items_by_section(week_iso: str) -> dict[str, list[dict]]:
    """Read all approved editor_decisions for the given week, grouped by section_placed.

    Returns dict with keys: whisper, big_conversation_seed, what_we_watching, thread_candidate, finds.
    Each value is a list of dicts with keys from joined tables.
    Items within each section are sorted by weighted_composite descending.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT ed.section_placed, ci.summary, ci.confidence_tag, ci.tags,
                  ci.weighted_composite, ci.id as curated_item_id, ci.our_take,
                  ri.title, ri.url, ri.source, ri.subreddit
        FROM editor_decisions ed
        JOIN curated_items ci ON ed.curated_item_id = ci.id
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ed.decision = 'approved'
          AND ed.issue_week_iso = ?
        ORDER BY ci.weighted_composite DESC""",
        (week_iso,),
    ).fetchall()
    conn.close()

    sections: dict[str, list[dict]] = {
        "whisper": [],
        "big_conversation_seed": [],
        "what_we_watching": [],
        "thread_candidate": [],
        "finds": [],
    }

    for row in rows:
        d = dict(row)
        section = d.get("section_placed", "")
        if section in sections:
            sections[section].append(d)

    return sections


def _render_hook(hook_text: str) -> str:
    """Render the top line hook section.

    Input: hook_text (str) — editor-selected hook from Session 3.
    Output: HTML string.
    """
    if not hook_text or len(hook_text) < 5:
        hook_text = "Here's what's moving through the corridors this week."
    return HOOK_TEMPLATE.format(hook_text=hook_text)


SIGNAL_DISPLAY_NAMES: dict[str, str] = {
    "job_anxiety": "Job Anxiety",
    "career_mobility": "Career Mobility",
    "contractor_proxy": "Contractor Proxy",
    "market_hiring": "Market Hiring",
    "employer_hiring_breadth": "Employer Hiring Breadth",
    "employer_hiring_seek_validator": "Employer Hiring (SEEK)",
    "employer_req_freshness": "Employer Req Freshness",
    "employer_net_delta": "Employer Net Delta",
    "salary_pressure": "Salary Pressure",
    "layoff_news_velocity": "Layoff News",
    "consumer_confidence": "Consumer Confidence",
    "asx_volatility": "ASX Volatility",
    "asx_momentum": "ASX Momentum",
    "reddit_topic_velocity": "Reddit Topic Velocity",
    "resume_anxiety": "Resume Anxiety",
    "auslaw_velocity": "AusLaw Velocity",
}


def _format_signal_name(raw: str) -> str:
    """Convert a snake_case signal name to a human-readable display name."""
    return SIGNAL_DISPLAY_NAMES.get(raw, raw.replace("_", " ").title())


def _render_pulse_block(week_iso: str, driver_bullets: list[dict]) -> str:
    """Render the AusCorp Live Pulse block.

    Input: week_iso (str), driver_bullets (list of dicts from generate_driver_bullets()).
    Output: HTML string with pulse score, summary, and driver bullets.
    """
    history = get_pulse_history(weeks=1)
    if not history:
        return ""

    current = history[0]
    direction_map = {"up": "↑", "down": "↓", "stable": "→"}
    direction_arrow = direction_map.get(current["direction"], "→")
    summary_text = current.get("summary_text") or "Pulse summary not yet generated."

    bullets_html = ""
    for driver in driver_bullets[:3]:
        arrow = "▲" if driver.get("direction") == "up" else "▼" if driver.get("direction") == "down" else "●"
        signal_display = _format_signal_name(driver.get("signal", "unknown"))
        bullets_html += DRIVER_BULLET_TEMPLATE.format(
            arrow=arrow,
            signal=signal_display,
            bullet=driver.get("bullet", "N/A"),
        )

    return PULSE_TEMPLATE.format(
        smoothed_score=f"{current['smoothed_score']:.0f}",
        direction_arrow=direction_arrow,
        summary_text=summary_text,
        driver_bullets_html=bullets_html,
    )


def _render_big_conversation(sections: dict[str, list[dict]]) -> str:
    """Render the Big Conversation section.

    Input: sections dict containing 'big_conversation_seed' items.
    Output: HTML string.
    First checks the drafts table for an editor-approved draft (saved from Session 3 dashboard).
    If no saved draft exists, falls back to calling generate_angles() + draft_big_conversation().
    Returns empty string if no big conversation items approved and no saved draft.
    """
    from flatwhite.db import get_approved_draft, get_current_week_iso

    # Check for editor-saved draft first
    saved = get_approved_draft(get_current_week_iso(), "big_conversation")
    if saved:
        headline = saved.get("headline") or "This Week's Big Conversation"
        draft = saved.get("draft_text", "")
    else:
        # Fallback: generate fresh via LLM
        seeds = sections.get("big_conversation_seed", [])
        if not seeds:
            return ""

        from flatwhite.classify.big_conversation import generate_angles, draft_big_conversation

        angles = generate_angles()
        if not angles:
            return ""

        angle = angles[0]
        headline = angle.get("headline", "This Week's Big Conversation")
        pitch = angle.get("pitch", "")
        supporting_ids = angle.get("supporting_item_ids", [])

        draft = draft_big_conversation(headline, pitch, supporting_ids)

    if not draft or draft.startswith("[Draft generation failed"):
        return ""

    draft_paragraphs = draft.strip().split("\n\n")
    draft_html = ""
    for para in draft_paragraphs:
        para = para.strip()
        if para:
            draft_html += f'<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;line-height:1.6;margin:0 0 12px 0;">{para}</p>\n'

    return BIG_CONVERSATION_TEMPLATE.format(
        headline=headline,
        draft_html=draft_html,
    )


def _render_whispers(items: list[dict]) -> str:
    """Render the Whispers section.

    Input: list of approved whisper items.
    Output: HTML string. Returns empty string if no items.
    """
    if not items:
        return ""

    confidence_emojis = {
        "green": "🟢",
        "yellow": "🟡",
        "red": "🔴",
    }

    html = WHISPERS_HEADER_TEMPLATE
    for item in items[:5]:
        emoji = confidence_emojis.get(item.get("confidence_tag"), "🟡")
        url = item.get("url")
        if url:
            link_html = (
                f' <a href="{url}" style="color:#2c81e5;text-decoration:underline;'
                f'font-size:14px;">[Source]</a>'
            )
        else:
            link_html = ""
        html += WHISPER_ITEM_TEMPLATE.format(
            confidence_emoji=emoji,
            summary=item.get("summary", ""),
            link_html=link_html,
        )
    html += WHISPERS_FOOTER_TEMPLATE
    return html


def _render_what_we_watching(
    approved_items: list[dict],
    week_iso: str,
) -> str:
    """
    Render the What We're Watching section.
    Combines editor-approved editorial items with Reddit topic anomalies.
    Returns empty string if no content available.
    """
    from flatwhite.db import get_connection

    conn = get_connection()
    anomalies = conn.execute(
        """
        SELECT topic_label, post_count, velocity_score
        FROM reddit_topic_clusters
        WHERE week_iso = ? AND is_anomaly = 1
        ORDER BY velocity_score DESC
        LIMIT 3
        """,
        (week_iso,)
    ).fetchall()
    conn.close()

    watching_items = approved_items  # Editor-approved editorial items

    if not watching_items and not anomalies:
        return ""

    # Format topic label for display
    def _fmt(label: str) -> str:
        return label.replace("_", " ").title()

    items_html = ""

    # Reddit anomaly bullets first — data-driven lead indicators
    for a in anomalies:
        items_html += WATCHING_ITEM_TEMPLATE.format(
            label="📡 Reddit Signal",
            text=f"Unusual volume around <strong>{_fmt(a['topic_label'])}</strong> "
                 f"this week — {a['post_count']} posts, "
                 f"velocity score {a['velocity_score']:.0f}/100.",
            link_html="",
        )

    # Editorial items approved by editor
    for item in watching_items[:3]:
        url = item.get("url")
        if url:
            link_html = (
                f' <a href="{url}" style="color:#2c81e5;text-decoration:underline;'
                f'font-size:14px;">[Source]</a>'
            )
        else:
            link_html = ""
        items_html += WATCHING_ITEM_TEMPLATE.format(
            label="👁 Watching",
            text=item["summary"],
            link_html=link_html,
        )

    return WATCHING_SECTION_TEMPLATE.format(items=items_html)


def _render_thread(items: list[dict]) -> str:
    """Render the Thread of the Week section.

    Input: list of approved thread_candidate items (uses first only).
    Output: HTML string. Returns empty string if no items.
    Uses our_take from curated_items if available, falls back to summary.
    """
    if not items:
        return ""

    thread = items[0]
    title = thread.get("title", "This week's thread")
    url = thread.get("url", "#")
    subreddit = thread.get("subreddit", "auscorp")

    # Prefer editor-approved Our Take, fall back to summary
    editorial_frame = thread.get("our_take") or thread.get("summary", "A discussion that caught our eye this week.")

    return THREAD_TEMPLATE.format(
        editorial_frame=editorial_frame,
        url=url,
        title=title,
        subreddit=subreddit,
    )


def _render_finds(items: list[dict]) -> str:
    """Render the Finds section.

    Input: list of approved finds items.
    Output: HTML string. Returns empty string if no items.
    """
    if not items:
        return ""

    html = FINDS_HEADER_TEMPLATE
    for item in items[:4]:
        url = item.get("url")
        if url:
            link_html = (
                f' <a href="{url}" style="color:#2c81e5;text-decoration:underline;'
                f'font-size:14px;">[Link]</a>'
            )
        else:
            link_html = ""
        html += FINDS_ITEM_TEMPLATE.format(
            summary=item.get("summary", ""),
            link_html=link_html,
        )
    html += FINDS_FOOTER_TEMPLATE
    return html


def _render_poll(week_iso: str) -> str:
    """Render the Poll section.

    Input: week_iso (str) — current week.
    Output: HTML string. Returns empty string if no poll exists for the week.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT question, options_json FROM polls WHERE week_iso = ? ORDER BY created_at DESC LIMIT 1",
        (week_iso,),
    ).fetchone()
    conn.close()

    if not row:
        return ""

    question = row["question"]
    try:
        options = json.loads(row["options_json"])
    except (json.JSONDecodeError, TypeError):
        return ""

    if not isinstance(options, list) or not options:
        return ""

    options_html = ""
    for option in options:
        if isinstance(option, str):
            options_html += POLL_OPTION_TEMPLATE.format(option=option)

    return POLL_TEMPLATE.format(
        question=question,
        options_html=options_html,
    )


def render_newsletter(hook_text: str, rotation: str) -> str:
    """Assemble full newsletter HTML from approved items and generated content.

    Input:
        hook_text (str): Editor-selected hook from Session 3 dashboard.
        rotation (str): 'A' or 'B' — determines section order.

    Output: Single HTML string for newsletter email content.

    Section order:
        Rotation A: Hook → Big Conversation → Pulse → Whispers → What We're Watching → Thread → Finds → Poll → Footer
        Rotation B: Hook → Pulse → Big Conversation → Whispers → What We're Watching → Thread → Finds → Poll → Footer

    Sections with no approved items are silently omitted.
    """
    week_iso = get_current_week_iso()
    sections = _get_approved_items_by_section(week_iso)

    from flatwhite.pulse.summary import generate_driver_bullets
    driver_bullets = generate_driver_bullets()

    hook_html = _render_hook(hook_text)
    pulse_html = _render_pulse_block(week_iso, driver_bullets)
    big_convo_html = _render_big_conversation(sections)
    whispers_html = _render_whispers(sections.get("whisper", []))
    watching_html = _render_what_we_watching(sections.get("what_we_watching", []), week_iso)
    thread_html = _render_thread(sections.get("thread_candidate", []))
    finds_html = _render_finds(sections.get("finds", []))
    poll_html = _render_poll(week_iso)
    footer_html = FOOTER_TEMPLATE

    if rotation == "A":
        body = (
            hook_html
            + big_convo_html
            + pulse_html
            + whispers_html
            + watching_html
            + thread_html
            + finds_html
            + poll_html
            + footer_html
        )
    else:
        body = (
            hook_html
            + pulse_html
            + big_convo_html
            + whispers_html
            + watching_html
            + thread_html
            + finds_html
            + poll_html
            + footer_html
        )

    return body
