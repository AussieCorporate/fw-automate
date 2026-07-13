"""Tests guarding the FW dashboard trim (branch fw-trim-segments).

Victor's decision: keep only Pulse, Big Conversation, Off the Clock, Top
Picks, Editorial (plus the already-disabled Salary Vault stub). Remove the
tabs for The Lobby, Whispers, AMP's Finest, Events, Finds, Thread, Composer.

Whispers/Finds/Thread are TAB-ONLY removals: their classifier sections stay
in flatwhite/classify/classifier.py's VALID_SECTIONS because Big
Conversation's /api/big-conversation-candidates query depends on the shared
classify_all_unclassified() function that also produces them. The second
test below guards that entanglement directly.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

import flatwhite.db as db_module

_INDEX_HTML = Path(__file__).parent.parent / "flatwhite" / "dashboard" / "static" / "index.html"

_CUT_NAV_IDS = {"lobby", "whispers", "amp_finest", "events", "finds", "thread", "assemble"}
_KEPT_NAV_IDS = {"pulse", "big_conversation", "off_the_clock", "top_picks", "editorial"}


def _nav_item_ids() -> set[str]:
    """Extract the `id: "..."` values from the NAV_ITEMS array in index.html.

    NAV_ITEMS is plain JS in a static file, not importable from Python, so
    this parses it out of the source directly. Comment lines in that array
    (explaining why a section's classifier is left intact) do not contain
    `id: "..."` patterns, so a simple regex over the array's source slice is
    sufficient and won't pick up stray matches from the comments.
    """
    html = _INDEX_HTML.read_text()
    m = re.search(r"var NAV_ITEMS = \[(.*?)\n\];", html, re.DOTALL)
    assert m, "NAV_ITEMS array not found in index.html"
    block = m.group(1)
    return set(re.findall(r'id:\s*"([a-zA-Z_]+)"', block))


def test_cut_nav_items_are_absent():
    """The seven trimmed tabs must not appear in NAV_ITEMS."""
    ids = _nav_item_ids()
    present_cuts = ids & _CUT_NAV_IDS
    assert not present_cuts, f"Cut nav items still present: {present_cuts}"


def test_kept_nav_items_are_present():
    """The five kept tabs must still appear in NAV_ITEMS."""
    ids = _nav_item_ids()
    missing_kept = _KEPT_NAV_IDS - ids
    assert not missing_kept, f"Kept nav items missing: {missing_kept}"


@pytest.fixture
def big_conv_db(tmp_path: Path):
    """DB seeded with a 'finds'-classified item for the current test week.

    This is the entanglement guard: Whispers/Finds/Thread lost their tabs,
    but Big Conversation's candidate query still reads 'finds' (and
    'big_conversation_seed'/'what_we_watching') items via the SAME shared
    classifier left untouched by the trim. If a future change to the
    classifier or to load_curated_items_by_section broke that path, this
    test would catch it.
    """
    db_path = tmp_path / "big_conv_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        raw_id = db_module.insert_raw_item(
            title="Layoffs hit another Big 4 firm",
            body="Body text",
            source="reddit",
            url="https://example.com/story",
            lane="editorial",
            subreddit="auscorp",
            week_iso="2026-W28",
        )
        db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="finds",
            summary="A Big 4 firm cut roles this week.",
            score_relevance=4,
            score_novelty=3,
            score_reliability=4,
            score_tension=4,
            score_usefulness=3,
            weighted_composite=7.5,
        )
        yield db_path


def test_big_conversation_candidates_endpoint_still_works(big_conv_db):
    """/api/big-conversation-candidates must keep working after the trim.

    It must still surface 'finds'-classified items even though the Finds tab
    itself is gone, proving the shared classifier entanglement was preserved
    correctly.
    """
    with patch.object(db_module, "DB_PATH", big_conv_db):
        with patch("flatwhite.dashboard.api.get_current_week_iso", return_value="2026-W28"):
            from flatwhite.dashboard.api import api_big_conv_candidates
            import json

            result = api_big_conv_candidates()
            assert result.status_code == 200
            data = json.loads(result.body)
            assert data["week_iso"] == "2026-W28"
            titles = [c["title"] for c in data["candidates"]]
            assert "Layoffs hit another Big 4 firm" in titles
