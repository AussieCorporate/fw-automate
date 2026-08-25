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
    # A complete bordered section card (not a bare heading) so an inserted
    # section matches every other section's card.
    assert 'class="node-section"' in block and 'data-type="section"' in block
    assert "<strong>THE BIG CONVERSATION</strong>" in block  # styled heading
    assert "#002b87" in block                                 # FW brand blue heading
    assert "<strong>A quiet mutiny.</strong>" in block        # body under the heading
    assert "More teams are pushing back." in block


def test_format_segment_block_custom_heading_level():
    block = format_segment_block("Odd Picks", "One quirky link.", heading_level="h4")
    assert "<h4" in block and "<strong>Odd Picks</strong>" in block
    assert 'class="node-section"' in block


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


def test_javascript_scheme_link_is_not_clickable():
    """A saved segment containing [here](javascript:alert(1)) must not produce
    a live javascript: anchor -- this HTML gets injected raw into the
    dashboard's DOM via innerHTML, so a javascript: href would actually fire
    on click. The dangerous scheme must never reach an href attribute; the
    bracketed markdown should render as plain escaped text instead."""
    html = md_to_editor_html("[here](javascript:alert(1))")
    assert "href=" not in html
    # The original markdown survives as visible plain text (nothing silently
    # disappears), just not as a clickable link.
    assert "here" in html
    assert "javascript:alert(1)" in html


def test_data_scheme_link_is_not_clickable():
    """data: URLs are another common XSS vector for anchor/href attacks
    (e.g. data:text/html,<script>...). Must not become a real href."""
    html = md_to_editor_html("[here](data:text/html,<script>alert(1)</script>)")
    assert "href=" not in html


def test_https_link_still_works_after_scheme_validation():
    """Regression guard: a normal https:// link must still convert to a real,
    clickable anchor after the scheme allowlist is added."""
    html = md_to_editor_html("Read the thread [here](https://reddit.com/r/auscorp/x)")
    assert '<a href="https://reddit.com/r/auscorp/x">here</a>' in html


def test_relative_link_still_allowed():
    """A schemeless, same-site-relative URL isn't dangerous (no scheme to
    execute) and should still render as a real link, not be over-restricted
    to only http/https/mailto."""
    html = md_to_editor_html("See [the archive](/archive/2026-07-10)")
    assert '<a href="/archive/2026-07-10">the archive</a>' in html


def test_scheme_relative_link_is_not_clickable():
    """A protocol-relative URL ("//host/path") has no explicit scheme but
    silently sends the reader to a different, unvalidated host -- treated
    as unsafe, same as an explicit dangerous scheme."""
    html = md_to_editor_html("[here](//evil.example.com/phish)")
    assert "href=" not in html


# ─── 25 Aug 2026 formatting audit: shapes from the published editions ────────


def test_bullet_lines_become_a_real_list():
    html = md_to_editor_html("* **Coles took its site offline**, after a viral post. [LINK](https://x.com/a)\n* **Aldi is cutting range**, as profit fell. [LINK](https://x.com/b)")
    assert html.startswith("<ul><li><p>")
    assert html.count("<li>") == 2
    assert "<strong>Coles took its site offline</strong>" in html
    assert '<a href="https://x.com/a">LINK</a>' in html
    assert "* " not in html  # no literal asterisks survive


def test_hyphen_lines_are_not_bullets_because_pull_quote_attribution():
    html = md_to_editor_html('"A quotable line."\n\n- Jarden')
    assert "<ul>" not in html
    assert "<p>- Jarden</p>" in html


def test_divider_line_survives_as_published_em_dash_furniture():
    html = md_to_editor_html("First entry. [LINK](https://x.com)\n\n———————————————————————————\n\nSecond entry.")
    assert '<div data-type="horizontalRule"><hr></div>' in html
    # And the dash stripper still runs on prose around it.
    assert " - " not in html.split("</p>")[0]


def test_plain_hyphen_divider_also_recognised():
    html = md_to_editor_html("Top\n\n---\n\nBottom")
    assert '<div data-type="horizontalRule"><hr></div>' in html


def test_single_newlines_inside_a_block_become_br():
    # The published Off the Clock shape: bold category line + bold title line.
    html = md_to_editor_html("**GOING**\n**A one-night show under the bridge**\n\nThe blurb sentence. [LINK](https://x.com)")
    assert "<p><strong>GOING</strong><br><strong>A one-night show under the bridge</strong></p>" in html


def test_blockquote_for_thread_top_comment():
    html = md_to_editor_html('> _"We\'ve come full circle."_ - Top Comment')
    assert html.startswith("<blockquote><p>")
    assert "<em>" in html and "Top Comment" in html


def test_prose_em_dashes_still_stripped_inside_paragraphs():
    html = md_to_editor_html("A soft patch — it is what it is.")
    assert "—" not in html
    assert "soft patch - it is" in html


def test_screenshot_marker_renders_as_an_obvious_placeholder_not_prose():
    html_out = md_to_editor_html("[Screenshot: IMG_1928.jpg]\n\nThe punchy line about it.")
    assert "Screenshot goes here: IMG_1928.jpg" in html_out
    assert "<em>" in html_out
    assert "<p>The punchy line about it.</p>" in html_out


def test_chart_marker_keeps_its_source_caption():
    html_out = md_to_editor_html("Beef prices are climbing.\n\n[CHART - Source: MLA, Morgan Stanley Research]\n\nProtein too.")
    assert "Chart goes here - Source: MLA, Morgan Stanley Research" in html_out
    # The prose around it is untouched.
    assert "<p>Beef prices are climbing.</p>" in html_out
    assert "<p>Protein too.</p>" in html_out


def test_full_off_the_clock_block_round_trips_to_published_shape():
    """End-to-end on the real published Off the Clock shape."""
    text = ("**GOING**\n**23 splendid things to do this September**\n\n"
            "Sydney is putting on a show for spring. [LINK](https://secretsydney.com/x)\n\n"
            "———————————————————————————\n\n"
            "**EATING**\n**A tiny trattoria in Marrickville**\n\n"
            "Twelve seats and no bookings. [LINK](https://example.com/y)")
    html_out = md_to_editor_html(text)
    assert "<strong>GOING</strong><br><strong>23 splendid things to do this September</strong>" in html_out
    assert '<a href="https://secretsydney.com/x">LINK</a>' in html_out
    assert '<a href="https://example.com/y">LINK</a>' in html_out
    assert '<div data-type="horizontalRule"><hr></div>' in html_out
    assert "**" not in html_out  # no raw markdown survives
