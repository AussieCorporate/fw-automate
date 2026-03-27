"""Integration tests for the classify pipeline: section routing, discard logic, weighted composite."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import flatwhite.db as db_module
from flatwhite.classify.classifier import VALID_SECTIONS
from flatwhite.classify.utils import _calculate_weighted_composite, _parse_llm_json


def test_classify_routes_to_valid_section(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """classify_single_item should return a section from VALID_SECTIONS when the LLM responds correctly."""
    mock_gemini.return_value = json.dumps({
        "section": "big_conversation_seed",
        "relevance": 5,
        "novelty": 4,
        "reliability": 4,
        "tension": 5,
        "usefulness": 3,
        "summary": "Big 4 firm slashes 200 advisory roles as cost-cutting accelerates.",
        "tags": ["big4", "layoffs", "advisory"],
        "confidence_tag": None,
    })

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_single_item

        item = {
            "id": 1,
            "title": "Big 4 firm axes 200 roles in advisory",
            "body": "Deloitte is cutting 200 positions in its advisory arm.",
            "source": "reddit_rss",
            "url": "https://reddit.com/r/auscorp/1",
        }

        result = classify_single_item(item)

        assert result is not None
        assert result["section"] in VALID_SECTIONS
        assert result["section"] == "big_conversation_seed"


def test_classify_invalid_section_defaults_to_discard(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """If the LLM returns an invalid section, it should default to discard."""
    mock_gemini.return_value = json.dumps({
        "section": "completely_invalid_section",
        "relevance": 4,
        "novelty": 3,
        "reliability": 4,
        "tension": 3,
        "usefulness": 3,
        "summary": "Some content.",
        "tags": [],
        "confidence_tag": None,
    })

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_single_item

        item = {
            "id": 1,
            "title": "Test item",
            "body": "Test body",
            "source": "reddit_rss",
            "url": None,
        }

        result = classify_single_item(item)
        assert result is not None
        assert result["section"] == "discard"


def test_low_relevance_auto_discards(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """Items with relevance < 3 should be auto-discarded (for non-whisper sections)."""
    mock_gemini.return_value = json.dumps({
        "section": "finds",
        "relevance": 2,
        "novelty": 3,
        "reliability": 3,
        "tension": 3,
        "usefulness": 3,
        "summary": "Somewhat relevant content.",
        "tags": ["misc"],
        "confidence_tag": None,
    })

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_single_item

        item = {
            "id": 2,
            "title": "Low relevance item",
            "body": "Not very relevant to AusCorp audience.",
            "source": "google_news_editorial",
            "url": "https://example.com/low",
        }

        result = classify_single_item(item)
        assert result is not None
        assert result["section"] == "discard"


def test_llm_failure_returns_none(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """If the LLM call raises an exception, classify_single_item should return None."""
    mock_gemini.side_effect = Exception("API rate limit exceeded")

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_single_item

        item = {
            "id": 1,
            "title": "Test item",
            "body": "Body text",
            "source": "reddit_rss",
            "url": None,
        }

        result = classify_single_item(item)
        assert result is None


def test_weighted_composite_in_range() -> None:
    """_calculate_weighted_composite should produce values between 1.0 and 5.0."""
    # Minimum scores (all 1s)
    min_scores = {
        "relevance": 1,
        "novelty": 1,
        "reliability": 1,
        "tension": 1,
        "usefulness": 1,
    }
    assert _calculate_weighted_composite(min_scores) == 1.0

    # Maximum scores (all 5s)
    max_scores = {
        "relevance": 5,
        "novelty": 5,
        "reliability": 5,
        "tension": 5,
        "usefulness": 5,
    }
    assert _calculate_weighted_composite(max_scores) == 5.0

    # Mixed scores
    mixed_scores = {
        "relevance": 4,
        "novelty": 2,
        "reliability": 5,
        "tension": 3,
        "usefulness": 4,
    }
    result = _calculate_weighted_composite(mixed_scores)
    assert 1.0 <= result <= 5.0


def test_weighted_composite_missing_keys() -> None:
    """Missing dimension keys should default to 3."""
    partial_scores: dict = {"relevance": 5}
    result = _calculate_weighted_composite(partial_scores)
    # relevance=5*0.25 + 3*0.15 + 3*0.25 + 3*0.20 + 3*0.15 = 1.25 + 0.45 + 0.75 + 0.60 + 0.45 = 3.5
    assert result == 3.5


def test_parse_llm_json_clean() -> None:
    """_parse_llm_json should handle clean JSON."""
    raw = '{"section": "finds", "relevance": 4}'
    result = _parse_llm_json(raw)
    assert result is not None
    assert result["section"] == "finds"


def test_parse_llm_json_fenced() -> None:
    """_parse_llm_json should strip markdown code fences."""
    raw = '```json\n{"section": "whisper"}\n```'
    result = _parse_llm_json(raw)
    assert result is not None
    assert result["section"] == "whisper"


def test_parse_llm_json_invalid() -> None:
    """_parse_llm_json should return None for invalid JSON."""
    result = _parse_llm_json("this is not json at all")
    assert result is None


def test_whisper_low_tension_auto_discards(
    populated_db: Path,
    mock_gemini: MagicMock,
) -> None:
    """Whisper items with tension < 2 should be auto-discarded."""
    mock_gemini.return_value = json.dumps({
        "section": "whisper",
        "relevance": 4,
        "novelty": 3,
        "reliability": 3,
        "tension": 1,
        "usefulness": 3,
        "summary": "Mild whisper without tension.",
        "tags": ["rumour"],
        "confidence_tag": "yellow",
    })

    with patch.object(db_module, "DB_PATH", populated_db):
        from flatwhite.classify.classifier import classify_single_item

        item = {
            "id": 5,
            "title": "Low tension whisper",
            "body": None,
            "source": "manual_whisper",
            "url": None,
        }

        result = classify_single_item(item)
        assert result is not None
        assert result["section"] == "discard"


def test_au_relevance_column_exists(temp_db):
    """curated_items must have an au_relevance column after migration."""
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(curated_items)").fetchall()}
    conn.close()
    assert "au_relevance" in cols
