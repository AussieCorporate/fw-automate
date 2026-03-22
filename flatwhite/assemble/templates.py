"""HTML templates and LLM prompts for Flat White newsletter assembly.

Every template is a string constant using Python str.format() placeholders.
Templates produce clean block-level HTML compatible with email newsletter format.
No Jinja2. No template engine. No dynamic template generation.

Brand: Flat White — #fffefc background, #2D2D2D text, #fff2d5 accent.
Font: System font stack (San Francisco, Segoe UI, Roboto, Helvetica Neue).
"""

# ─── SECTION: TOP LINE HOOK ──────────────────────────────────────────────────

HOOK_TEMPLATE = (
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:16px;'
    'line-height:1.6;margin:0 0 20px 0;">'
    "<b>Good morning AusCorp.</b> {hook_text}</p>\n"
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
)

# ─── SECTION: PULSE BLOCK ────────────────────────────────────────────────────

PULSE_TEMPLATE = (
    '<div style="background-color:#fff2d5;border-radius:8px;padding:20px;margin:20px 0;">\n'
    '<h2 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:20px;'
    'margin:0 0 12px 0;">AusCorp Live Pulse: {smoothed_score} {direction_arrow}</h2>\n'
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 12px 0;">{summary_text}</p>\n'
    '{driver_bullets_html}\n'
    '</div>\n'
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
)

DRIVER_BULLET_TEMPLATE = (
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:14px;'
    'line-height:1.5;margin:0 0 4px 0;">{arrow} <b>{signal}</b>: {bullet}</p>\n'
)

# ─── SECTION: BIG CONVERSATION ───────────────────────────────────────────────

BIG_CONVERSATION_TEMPLATE = (
    '<h2 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:20px;'
    'margin:0 0 12px 0;">The Big Conversation</h2>\n'
    '<h3 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:17px;'
    'font-style:italic;margin:0 0 12px 0;">{headline}</h3>\n'
    '<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.6;margin:0 0 20px 0;">{draft_html}</div>\n'
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
)

# ─── SECTION: WHISPERS ───────────────────────────────────────────────────────

WHISPERS_HEADER_TEMPLATE = (
    '<h2 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:20px;'
    'margin:0 0 12px 0;">Whispers</h2>\n'
)

WHISPER_ITEM_TEMPLATE = (
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 12px 0;">'
    '{confidence_emoji} {summary}{link_html}'
    '</p>\n'
)

WHISPERS_FOOTER_TEMPLATE = (
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
)

# ─── SECTION: WHAT WE'RE WATCHING ────────────────────────────────────────────

WATCHING_SECTION_TEMPLATE = """
<h3>👁 What We're Watching</h3>
<p><em>Signals gaining traction before they make the news.</em></p>
{items}
<hr/>
"""

WATCHING_ITEM_TEMPLATE = """
<p><strong>{label}:</strong> {text}{link_html}</p>
"""

# ─── SECTION: THREAD OF THE WEEK ─────────────────────────────────────────────

THREAD_TEMPLATE = (
    '<h2 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:20px;'
    'margin:0 0 12px 0;">Thread of the Week</h2>\n'
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 8px 0;font-style:italic;">{editorial_frame}</p>\n'
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 8px 0;">'
    '<b><a href="{url}" style="color:#2c81e5;text-decoration:underline;">'
    '{title}</a></b> — r/{subreddit}</p>\n'
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
)

# ─── SECTION: FINDS ──────────────────────────────────────────────────────────

FINDS_HEADER_TEMPLATE = (
    '<h2 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:20px;'
    'margin:0 0 12px 0;">Finds</h2>\n'
)

FINDS_ITEM_TEMPLATE = (
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 12px 0;">'
    '{summary}'
    '{link_html}'
    '</p>\n'
)

FINDS_FOOTER_TEMPLATE = (
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
)

# ─── SECTION: POLL ────────────────────────────────────────────────────────────

POLL_TEMPLATE = (
    '<div style="background-color:#fff2d5;border-radius:8px;padding:20px;margin:20px 0;">\n'
    '<h2 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:20px;'
    'margin:0 0 12px 0;">Poll</h2>\n'
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 12px 0;font-weight:bold;">{question}</p>\n'
    '{options_html}\n'
    '</div>\n'
)

POLL_OPTION_TEMPLATE = (
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:15px;'
    'line-height:1.5;margin:0 0 6px 0;">• {option}</p>\n'
)

# ─── SECTION: FOOTER CTA ─────────────────────────────────────────────────────

FOOTER_TEMPLATE = (
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0;">\n'
    '<p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2D2D2D;font-size:14px;'
    'line-height:1.5;text-align:center;margin:20px 0;">'
    '<i>Was this email forwarded to you? '
    '<a href="https://theaussiecorporate.beehiiv.com/subscribe" '
    'style="color:#2c81e5;text-decoration:underline;">Sign up here</a>.</i></p>\n'
)

# ─── LLM PROMPTS: SUBJECT LINE ───────────────────────────────────────────────

SUBJECT_LINE_SYSTEM = (
    "You are the editor of Flat White, a weekly newsletter for Australian "
    "corporate professionals. You write punchy, curiosity-driven email subject lines. "
    "Voice: dry, confident, slightly wry. Australian English. "
    "Max 60 characters. No clickbait. No emojis. No ALL CAPS. "
    "No theatrical setups or filler intensifiers. "
    "Output ONLY the subject line text. Nothing else."
)

SUBJECT_LINE_PROMPT = (
    "Write an email subject line for this week's Flat White newsletter.\n"
    "\n"
    "Pulse score: {smoothed_score} ({direction})\n"
    "Big Conversation headline: {big_conversation_headline}\n"
    "Top whisper: {top_whisper}\n"
    "Thread of the Week: {thread_title}\n"
    "\n"
    "Write exactly ONE subject line, max 60 characters. "
    "The subject line should tease the most compelling item this week. "
    "Output ONLY the subject line. Nothing else."
)

# ─── LLM PROMPTS: PREVIEW TEXT ────────────────────────────────────────────────

PREVIEW_TEXT_SYSTEM = (
    "You are the editor of Flat White, a weekly newsletter for Australian "
    "corporate professionals. You write email preview text that complements "
    "the subject line. Voice: dry, confident, direct. Australian English. "
    "Max 120 characters. No theatrical setups or filler intensifiers. "
    "Output ONLY the preview text. Nothing else."
)

PREVIEW_TEXT_PROMPT = (
    "Write email preview text for this week's Flat White newsletter.\n"
    "\n"
    "Subject line: {subject_line}\n"
    "Pulse score: {smoothed_score} ({direction})\n"
    "Top 3 items: {top_items_summary}\n"
    "\n"
    "Write exactly ONE preview sentence, max 120 characters. "
    "It should add new information beyond the subject line. "
    "Output ONLY the preview text. Nothing else."
)
