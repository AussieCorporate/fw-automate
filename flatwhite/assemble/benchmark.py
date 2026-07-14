"""Benchmark an assembled segment's length against the real published corpus.

Reads data/beehiiv_fw_ground_truth.json (10 real Flat White editions,
segment-parsed) and, for a given FW dashboard section id, finds every real
segment across those editions whose header NAME matches, computes an average
+ min/max word count, and reports whether a candidate text's word count falls
short of / within / longer than that observed range.

Numbers are NEVER hardcoded here — always computed from the corpus file, so
re-fetching more editions automatically updates the benchmark. See
data/beehiiv_fw_ground_truth_ANALYSIS.md for the human-written commentary this
module deliberately does NOT copy numbers from (that doc can drift; the JSON
is the source of truth).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

GROUND_TRUTH_PATH = Path(__file__).parent.parent.parent / "data" / "beehiiv_fw_ground_truth.json"

# FW dashboard section id -> substrings that identify it in the real corpus's
# segment "name" field (case-insensitive "in" match). Ordered matchers checked
# in the order given; a name matching more than one FW section id (e.g. "ODD
# PICKS" contains "PICK") is guarded by the exclude list.
#
# Note: the FW dashboard's real section id for this segment is "brains_trust"
# (see flatwhite/dashboard/static/index.html SEGMENTS array and
# flatwhite/dashboard/api.py proceed_fns / task_type="brains_trust") — NOT
# "brains". Using the wrong id here would make Task 5's assemble endpoint
# silently get status: "no_data" forever for this segment.
_SEGMENT_MATCHERS: dict[str, dict[str, list[str]]] = {
    "editorial":        {"include": ["INTRO"], "exclude": []},
    "big_conversation": {"include": ["THE BIG CONVERSATION"], "exclude": []},
    "top_picks":        {"include": ["PICK & SCROLL", "TOP PICKS FROM LAST WEEK"], "exclude": ["ODD PICKS"]},
    "insidetrack":      {"include": ["THE INSIDE TRACK"], "exclude": []},
    "thread":           {"include": ["THREAD OF THE WEEK"], "exclude": []},
    "pulse":            {"include": ["AUSCORP STRESS INDEX"], "exclude": []},
    "off_the_clock":    {"include": ["OFF THE CLOCK"], "exclude": []},
    # THE BRAINS TRUST and its older name THE ECONOMIC SCOOP are the same slot
    # (see ANALYSIS.md "structural drift" note) — both count toward
    # "brains_trust", the real FW dashboard section id for this segment.
    "brains_trust":     {"include": ["THE BRAINS TRUST", "THE ECONOMIC SCOOP"], "exclude": []},
}


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _matches(name: str, matcher: dict[str, list[str]]) -> bool:
    upper = name.upper()
    if any(ex in upper for ex in matcher["exclude"]):
        return False
    return any(inc in upper for inc in matcher["include"])


@lru_cache(maxsize=1)
def _load_profiles() -> dict[str, dict[str, Any]]:
    """Build {section_id: {avg, min, max, n}} from the ground truth corpus.

    lru_cache means a monkeypatch of GROUND_TRUTH_PATH in tests must call
    _load_profiles.cache_clear() first (see tests/test_benchmark.py fixture).
    """
    if not GROUND_TRUTH_PATH.exists():
        return {}
    editions = json.loads(GROUND_TRUTH_PATH.read_text())

    counts: dict[str, list[int]] = {sid: [] for sid in _SEGMENT_MATCHERS}
    for edition in editions:
        for seg in edition.get("segments", []):
            name = seg.get("name", "")
            wc = seg.get("word_count")
            if wc is None:
                wc = _word_count(seg.get("text", ""))
            for section_id, matcher in _SEGMENT_MATCHERS.items():
                if _matches(name, matcher):
                    counts[section_id].append(wc)

    profiles: dict[str, dict[str, Any]] = {}
    for section_id, values in counts.items():
        if not values:
            continue
        profiles[section_id] = {
            "avg": round(sum(values) / len(values), 1),
            "min": min(values),
            "max": max(values),
            "n": len(values),
        }
    return profiles


def benchmark_segment(section_id: str, text: str) -> dict[str, Any]:
    """Compare a candidate segment's word count to the real corpus.

    Returns dict with word_count, target_avg, target_min, target_max, status
    ("short"|"within"|"long"|"no_data"), n_editions.
    """
    profiles = _load_profiles()
    word_count = _word_count(text)

    profile = profiles.get(section_id)
    if profile is None:
        return {
            "word_count": word_count,
            "target_avg": None,
            "target_min": None,
            "target_max": None,
            "status": "no_data",
            "n_editions": 0,
        }

    if word_count < profile["min"]:
        status = "short"
    elif word_count > profile["max"]:
        status = "long"
    else:
        status = "within"

    return {
        "word_count": word_count,
        "target_avg": profile["avg"],
        "target_min": profile["min"],
        "target_max": profile["max"],
        "status": status,
        "n_editions": profile["n"],
    }
