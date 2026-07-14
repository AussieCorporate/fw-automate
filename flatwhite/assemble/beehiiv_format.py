"""Convert FW's saved segment text (the markdown-ish prose Victor edits in
each segment's output box) into HTML fragments matching beehiiv's post editor
contract, confirmed via the beehiiv MCP's learn_post_authoring: plain
paragraph/heading/strong/em/link HTML, no beehiiv-specific wrapper needed for
this bounded conversion. This is Design B's "format server-side" half — the
other half (actually inserting into a draft via edit_post_content) is a human
or agent step outside this codebase; see the assemble endpoint's docstring
and the increment plan's Global Constraints for why.

Intentionally minimal: handles exactly the markdown FW segments actually use
(bold, italic, links, paragraph breaks, one heading level for Thread of the
Week's '#### [_**title**_](url)' shape) — not a general markdown engine. FW
has no markdown package installed; this follows the existing house style in
flatwhite/assemble/renderer.py (hand-rolled string templating, no template
engine).
"""
from __future__ import annotations

import html
import re

_BOLD_ITALIC = re.compile(r"\*\*_(.+?)_\*\*|_\*\*(.+?)\*\*_")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|_(.+?)_")
_LINK = re.compile(r"\[(.+?)\]\((.+?)\)")
_HEADING4 = re.compile(r"^####\s+(.*)$")

_LINK_PLACEHOLDER = "\x00LINK{0}\x00"


def _process_marks(escaped: str) -> str:
    """Apply inline marks (links, bold-italic, bold, italic) to already
    HTML-escaped text.

    Links are converted FIRST, but their generated '<a href="...">...</a>'
    HTML is stashed behind a placeholder token before bold-italic/bold/italic
    run, then restored afterwards. This stops the ITALIC pass's
    underscore-delimited alternative (`_(.+?)_`) from matching a substring of
    a raw URL sitting inside an href attribute (e.g. a Reddit URL slug with
    2+ underscores) and corrupting the link with a stray <em>. The link's
    DISPLAY TEXT is itself run back through _process_marks() (not re-escaped,
    since it's already an escaped substring of the input) before stashing, so
    bold/italic markup inside [text](url) (e.g. '[_**title**_](url)') still
    converts correctly.
    """
    placeholders: list[str] = []

    def _link_sub(m: re.Match) -> str:
        display = _process_marks(m.group(1))
        href = m.group(2)
        anchor = f'<a href="{href}">{display}</a>'
        placeholders.append(anchor)
        return _LINK_PLACEHOLDER.format(len(placeholders) - 1)

    escaped = _LINK.sub(_link_sub, escaped)

    def _bi_sub(m: re.Match) -> str:
        inner = m.group(1) or m.group(2)
        return f"<strong><em>{inner}</em></strong>"

    escaped = _BOLD_ITALIC.sub(_bi_sub, escaped)
    escaped = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    escaped = _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", escaped)

    for i, anchor in enumerate(placeholders):
        escaped = escaped.replace(_LINK_PLACEHOLDER.format(i), anchor)

    return escaped


def _inline(text: str) -> str:
    """Apply inline marks (bold, italic, bold-italic, links) to one line/paragraph.

    Text is HTML-escaped first so raw '<'/'>'/'&' in source prose can't break
    the output; marks are then reintroduced as real tags via _process_marks().
    """
    escaped = html.escape(text, quote=True)
    return _process_marks(escaped)


def md_to_editor_html(text: str) -> str:
    """Convert FW markdown-ish text into a beehiiv-editor HTML fragment.

    Blank lines separate paragraphs. A line starting '#### ' becomes an <h4>
    (Thread of the Week's real published title format). Everything else is
    wrapped in <p>. Returns "" for empty/whitespace-only input.
    """
    text = text.strip()
    if not text:
        return ""

    paragraphs = re.split(r"\n\s*\n", text)
    parts: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        heading_match = _HEADING4.match(para)
        if heading_match:
            parts.append(f"<h4>{_inline(heading_match.group(1))}</h4>")
        else:
            # Collapse internal single newlines into spaces — one paragraph tag.
            collapsed = " ".join(line.strip() for line in para.split("\n") if line.strip())
            parts.append(f"<p>{_inline(collapsed)}</p>")
    return "".join(parts)


def format_segment_block(label: str, text: str, heading_level: str = "h3") -> str:
    """Wrap a labelled heading + converted body — one block in the assembled edition.

    label is used verbatim as the visible heading text (callers pass the real
    published header name, e.g. "THE BIG CONVERSATION", not the FW section id).
    """
    heading = f"<{heading_level}>{html.escape(label, quote=True)}</{heading_level}>"
    body = md_to_editor_html(text)
    return heading + body
