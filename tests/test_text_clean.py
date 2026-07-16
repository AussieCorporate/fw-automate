"""Reader-facing dash hygiene — Victor's absolute no-em-dash rule."""

from flatwhite.utils.text_clean import strip_reader_dashes


def test_spaced_em_dash_becomes_spaced_hyphen():
    assert strip_reader_dashes("soft patch — it is a slump") == "soft patch - it is a slump"


def test_glued_em_dash_becomes_spaced_hyphen():
    assert strip_reader_dashes("soft patch—it is") == "soft patch - it is"


def test_horizontal_bar_treated_as_em_dash():
    assert strip_reader_dashes("a ― b") == "a - b"


def test_numeric_en_dash_range_becomes_plain_hyphen():
    assert strip_reader_dashes("the 2010–2020 decade") == "the 2010-2020 decade"


def test_en_dash_punctuation_becomes_spaced_hyphen():
    assert strip_reader_dashes("yes – really") == "yes - really"


def test_no_dashes_unchanged():
    s = "A clean sentence with a normal-hyphen and nothing else."
    assert strip_reader_dashes(s) == s


def test_idempotent():
    once = strip_reader_dashes("soft patch—it is")
    assert strip_reader_dashes(once) == once


def test_empty_and_none_safe():
    assert strip_reader_dashes("") == ""
    assert strip_reader_dashes(None) is None


def test_multiple_em_dashes_all_replaced():
    out = strip_reader_dashes("one — two — three")
    assert "—" not in out
    assert out == "one - two - three"
