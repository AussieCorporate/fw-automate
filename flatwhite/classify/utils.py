from __future__ import annotations

"""Shared utilities for the classification and editorial pipeline.

RULES:
- _parse_llm_json() is the ONLY function that parses LLM JSON output in the entire codebase.
- _calculate_weighted_composite() is the ONLY function that computes dimension-weighted scores.
- Do not add other functions to this file.
"""

import json


DIMENSION_WEIGHTS: dict[str, float] = {
    "relevance": 0.25,
    "novelty": 0.15,
    "reliability": 0.25,
    "tension": 0.20,
    "usefulness": 0.15,
}


def _parse_llm_json(response: str) -> dict | list | None:
    """Parse LLM response as JSON. Strips markdown code fences if present.

    Input: raw string response from an LLM call.
    Output: parsed dict or list on success, None on failure.

    Handles these cases:
    1. Clean JSON: '{"key": "value"}' -> {"key": "value"}
    2. Fenced JSON: '```json\n{"key": "value"}\n```' -> {"key": "value"}
    3. Fenced without lang: '```\n{"key": "value"}\n```' -> {"key": "value"}
    4. Invalid JSON: 'not json' -> None
    """
    cleaned = response.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ``` or ```JSON etc.)
        lines = lines[1:]
        # Remove last line if it is ``` (possibly with trailing whitespace)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _calculate_weighted_composite(scores: dict) -> float:
    """Calculate weighted composite from 5-dimension scores.

    Input: dict with keys from DIMENSION_WEIGHTS. Each value is an integer 1-5.
           Missing keys default to 3. Non-numeric values default to 3. Values clamped to 1-5.
    Output: float rounded to 2 decimal places. Range: 1.0 to 5.0.

    Example:
        scores = {"relevance": 5, "novelty": 3, "reliability": 4, "tension": 5, "usefulness": 2}
        result = 5*0.25 + 3*0.15 + 4*0.25 + 5*0.20 + 2*0.15 = 1.25 + 0.45 + 1.00 + 1.00 + 0.30 = 4.0
    """
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        score = scores.get(dim, 3)
        if not isinstance(score, (int, float)):
            score = 3
        score = max(1, min(5, int(score)))
        total += score * weight
    return round(total, 2)
