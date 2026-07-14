"""Tests for flatwhite/assemble/benchmark.py — checks a segment's word count
against the real published corpus (data/beehiiv_fw_ground_truth.json), never
against hardcoded numbers (the corpus can be re-fetched/extended later)."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from flatwhite.assemble import benchmark


# A tiny fixture with the same shape as the real corpus (list of editions,
# each with "segments": [{"name":..., "text":..., "word_count":...}]).
# Kept deliberately small/fast — the real-corpus check is a separate test.
_FIXTURE = [
    {
        "post_id": "post_fixture1", "date": "2026-01-05", "title": "t1",
        "segments": [
            {"name": "INTRO", "text": "word " * 150, "word_count": 150},
            {"name": "THE BIG CONVERSATION", "text": "word " * 400, "word_count": 400},
            {"name": "OFF THE CLOCK", "text": "word " * 200, "word_count": 200},
        ],
    },
    {
        "post_id": "post_fixture2", "date": "2026-01-12", "title": "t2",
        "segments": [
            {"name": "INTRO", "text": "word " * 170, "word_count": 170},
            {"name": "THE BIG CONVERSATION", "text": "word " * 440, "word_count": 440},
            {"name": "OFF THE CLOCK", "text": "word " * 220, "word_count": 220},
        ],
    },
]


@pytest.fixture
def fixture_corpus(tmp_path: Path):
    p = tmp_path / "fixture_ground_truth.json"
    p.write_text(json.dumps(_FIXTURE))
    with patch.object(benchmark, "GROUND_TRUTH_PATH", p):
        benchmark._load_profiles.cache_clear()
        yield p
    benchmark._load_profiles.cache_clear()


def test_editorial_within_range(fixture_corpus):
    result = benchmark.benchmark_segment("editorial", "word " * 160)
    assert result["status"] == "within"
    assert result["target_min"] == 150
    assert result["target_max"] == 170
    assert result["n_editions"] == 2


def test_editorial_too_short(fixture_corpus):
    result = benchmark.benchmark_segment("editorial", "word " * 50)
    assert result["status"] == "short"


def test_big_conversation_too_long(fixture_corpus):
    result = benchmark.benchmark_segment("big_conversation", "word " * 900)
    assert result["status"] == "long"


def test_unmapped_section_returns_no_data(fixture_corpus):
    result = benchmark.benchmark_segment("insidetrack_typo_id", "anything")
    assert result["status"] == "no_data"


def test_word_count_is_computed_not_assumed(fixture_corpus):
    result = benchmark.benchmark_segment("off_the_clock", "just three words")
    assert result["word_count"] == 3


def test_real_corpus_loads_and_maps_known_segments():
    """Integration check against the ACTUAL shipped corpus — no network, just
    confirms the segment-name matchers still line up with real header text."""
    benchmark._load_profiles.cache_clear()
    for section_id in ("editorial", "big_conversation", "top_picks", "insidetrack",
                        "thread", "pulse", "off_the_clock", "brains_trust"):
        result = benchmark.benchmark_segment(section_id, "word " * 100)
        assert result["status"] != "no_data", f"{section_id} did not match any real segment name"
        assert result["n_editions"] >= 1
    benchmark._load_profiles.cache_clear()
