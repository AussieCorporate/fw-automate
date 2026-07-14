"""Tests for flatwhite/assemble/beehiiv_format.py — converts FW's saved
markdown-ish segment text into beehiiv-editor HTML fragments. Structure only;
no beehiiv MCP or network call is made anywhere in this module or these tests
(Design B: FW formats, a human/agent inserts via the beehiiv MCP separately)."""
from flatwhite.assemble.beehiiv_format import md_to_editor_html, format_segment_block


def test_bold_converts_to_strong():
    assert md_to_editor_html("**A quiet mutiny.**") == "<p><strong>A quiet mutiny.</strong></p>"


def test_italic_underscore_converts_to_em():
    assert "<em>share this</em>" in md_to_editor_html("people say _share this_ constantly")


def test_italic_asterisk_converts_to_em():
    assert "<em>share this</em>" in md_to_editor_html("people say *share this* constantly")


def test_link_converts_to_anchor():
    html = md_to_editor_html("Read the thread [here](https://reddit.com/r/auscorp/x)")
    assert '<a href="https://reddit.com/r/auscorp/x">here</a>' in html


def test_blank_line_splits_paragraphs():
    html = md_to_editor_html("First paragraph.\n\nSecond paragraph.")
    assert html == "<p>First paragraph.</p><p>Second paragraph.</p>"


def test_single_newline_stays_within_one_paragraph():
    html = md_to_editor_html("Line one.\nLine two.")
    assert html.count("<p>") == 1


def test_empty_text_returns_empty_string():
    assert md_to_editor_html("") == ""
    assert md_to_editor_html("   ") == ""


def test_h4_hyperlinked_thread_title_format():
    """Thread of the Week's real published shape per ground truth:
    '#### [_**title**_](url)' — bold-italic hyperlinked H4 title."""
    html = md_to_editor_html("#### [_**Bunking with a colleague**_](https://reddit.com/x)")
    assert "<h4>" in html
    assert '<a href="https://reddit.com/x">' in html
    assert "<strong><em>Bunking with a colleague</em></strong>" in html or \
           "<em><strong>Bunking with a colleague</strong></em>" in html


def test_format_segment_block_wraps_heading_and_body():
    block = format_segment_block("THE BIG CONVERSATION", "**A quiet mutiny.**\n\nMore teams are pushing back.")
    assert block.startswith("<h3>THE BIG CONVERSATION</h3>")
    assert "<strong>A quiet mutiny.</strong>" in block
    assert "More teams are pushing back." in block


def test_format_segment_block_custom_heading_level():
    block = format_segment_block("Odd Picks", "One quirky link.", heading_level="h4")
    assert block.startswith("<h4>Odd Picks</h4>")


def test_link_with_multiple_underscores_in_url_not_corrupted():
    """Real-world Thread of the Week input: a Reddit URL whose slug has 2+
    underscores (e.g. /comments/abc123/my_thread_title_here/). If the LINK
    regex runs before ITALIC, the underscore-delimited italic alternative
    (_(.+?)_) can match a substring of the raw URL text sitting inside the
    href="..." attribute and wrap it in <em>, corrupting the link. Confirms
    the href attribute survives completely intact."""
    url = "https://www.reddit.com/r/AusCorp/comments/abc123/my_thread_title_here/"
    html = md_to_editor_html(f"[here]({url})")
    assert f'href="{url}"' in html
    assert "<em>" not in html
    assert "</em>" not in html


def test_url_with_quote_char_prevents_attribute_injection():
    """Verify that a URL containing a literal double-quote character does not
    break out of the href attribute and inject new HTML attributes. All quotes
    must be escaped to &quot; so the href attribute closes properly."""
    html = md_to_editor_html('[here](https://reddit.com/x" onmouseover="alert(1))')
    # The dangerous input has unescaped quotes. After the fix, those quotes
    # must be escaped as &quot; inside the href attribute value.
    # The markdown regex stops at the first ), so the captured URL is:
    # https://reddit.com/x&quot; onmouseover=&quot;alert(1
    assert 'href="https://reddit.com/x&quot; onmouseover=&quot;alert(1' in html
    # Verify the link still renders
    assert '>here</a>' in html
    # Critical: confirm no unescaped quote breaks out of the href attribute.
    # If the injection worked, we'd see: href="short_url" onmouseover="alert(1)">
    # That pattern is ABSENT, proving the quotes are escaped and contained.
    assert 'href="https://reddit.com/x" ' not in html  # Would indicate breakout
