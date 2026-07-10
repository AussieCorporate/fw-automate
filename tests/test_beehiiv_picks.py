"""Regression tests for Beehiiv top-picks extraction and ranking.

The HTML fixtures below are copied from real Pick & Scroll editions: every item
paragraph ends with an anchor labelled "LINK". Before the fix, the extracted
summary kept that label, so a consumer that appended its own hyperlink rendered
"... rates fall. LINK link".
"""

from flatwhite.editorial.beehiiv_picks import (
    _extract_summaries_from_html,
    _is_excluded,
)

# Shape taken verbatim from a published edition.
REAL_ITEM_HTML = (
    '<p>The RBA has warned Australia may need a period of low inflation and '
    'higher unemployment, with Deloitte forecasting joblessness near 5% by 2028 '
    'before interest rates fall. '
    '<a target="_blank" rel="noopener noreferrer nofollow" class="link" '
    'href="https://www.news.com.au/finance/economy/grim-forecast/">LINK</a></p>'
)


def test_trailing_link_label_is_stripped_from_summary():
    summaries = _extract_summaries_from_html(REAL_ITEM_HTML)
    (summary,) = summaries.values()
    assert summary.endswith("before interest rates fall.")
    assert "LINK" not in summary


def test_summary_survives_when_anchor_is_mid_sentence():
    """Only the anchor's own trailing label is dropped, not inline link text."""
    html = (
        '<p>Economists say <a href="https://example.com/report">the new report</a> '
        'shows the economy avoided a recession this quarter.</p>'
    )
    (summary,) = _extract_summaries_from_html(html).values()
    assert summary == (
        "Economists say the new report shows the economy avoided a recession "
        "this quarter."
    )


def test_anchor_label_stripped_regardless_of_case_and_markup():
    html = (
        '<p>Qantas arrived on time 87.16% of the time in June. '
        '<a href="https://example.com/qantas"><strong>Link</strong></a></p>'
    )
    (summary,) = _extract_summaries_from_html(html).values()
    assert summary == "Qantas arrived on time 87.16% of the time in June."


def test_utm_params_collapse_to_one_summary_key():
    html = (
        '<p>The excise cut drops from 32 cents per litre to 16 cents. '
        '<a href="https://michaelwest.com.au/fuel-costs/?utm_source=beehiiv">LINK</a></p>'
    )
    summaries = _extract_summaries_from_html(html)
    assert "https://michaelwest.com.au/fuel-costs/" in summaries


def test_own_blog_and_survey_domains_are_excluded_from_picks():
    """These out-click editorial links but are self-promo, not a top pick."""
    assert _is_excluded("https://theaussiecorporate.com/blogs/pickandscrollnews/x")
    assert _is_excluded("https://tally.so/r/J9eqvo")
    assert _is_excluded("https://pickandscrollnews.beehiiv.com/subscribe")
    # A genuine editorial link must still pass through.
    assert not _is_excluded("https://www.smartcompany.com.au/finance/asic-probe/")


def test_section_label_and_greeting_prefixes_are_stripped():
    html = (
        '<p>Doctor’s Pick: Leading causes of death in Australia. '
        '<a href="https://www.aihw.gov.au/reports/deaths">LINK</a></p>'
        '<p>Good morning. Coles has merged two staples into a single $14 bag. '
        '<a href="https://www.news.com.au/coles">LINK</a></p>'
    )
    summaries = _extract_summaries_from_html(html)
    assert summaries["https://www.aihw.gov.au/reports/deaths"] == (
        "Leading causes of death in Australia."
    )
    assert summaries["https://www.news.com.au/coles"] == (
        "Coles has merged two staples into a single $14 bag."
    )
