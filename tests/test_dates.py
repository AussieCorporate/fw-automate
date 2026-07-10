"""Publish dates must be stored in a format that sorts chronologically.

prune_stale_raw_items compares published_at as a *string* against
datetime('now','-7 days'). RFC 2822 values start with a weekday name, which
sorts above "2026-...", so stale items were never pruned and months-old
listicles kept resurfacing in Off The Clock.
"""

from flatwhite.utils.dates import to_iso_utc


def test_rfc_2822_becomes_sortable():
    # The format most classic RSS feeds emit, and the one that broke pruning.
    assert to_iso_utc("Fri, 05 Jun 2026 03:00:00 GMT") == "2026-06-05 03:00:00"


def test_iso_8601_with_z_is_normalised():
    assert to_iso_utc("2026-06-29T03:00:00Z") == "2026-06-29 03:00:00"


def test_offset_is_converted_to_utc():
    # +10:00 is Sydney; 09:30 local on the 29th is 23:30 UTC on the 28th.
    assert to_iso_utc("2026-06-29T09:30:00+10:00") == "2026-06-28 23:30:00"


def test_naive_datetime_is_treated_as_utc():
    assert to_iso_utc("2026-06-29T03:00:00") == "2026-06-29 03:00:00"


def test_missing_or_unparseable_returns_none():
    assert to_iso_utc(None) is None
    assert to_iso_utc("") is None
    assert to_iso_utc("last Tuesday") is None


def test_normalised_dates_sort_chronologically_as_strings():
    """The actual property pruning depends on."""
    old = to_iso_utc("Sat, 26 Apr 2026 14:00:00 GMT")
    new = to_iso_utc("2026-07-09T22:00:48Z")
    cutoff = "2026-07-03 00:00:00"
    assert old < cutoff < new
