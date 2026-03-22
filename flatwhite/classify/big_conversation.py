"""Generates Big Conversation angles and drafts using Gemini 2.5 Flash.

generate_angles(): Analyses this week's classified items, proposes 3 editorial angles.
draft_big_conversation(): Given a selected angle, writes a 200-300 word editorial.

Both functions use task_type="big_conversation" which routes to Gemini 2.5 Flash.
"""

from __future__ import annotations

import json
from flatwhite.model_router import route
from flatwhite.classify.prompts import (
    BIG_CONVERSATION_ANGLES_SYSTEM,
    BIG_CONVERSATION_ANGLES_PROMPT,
    BIG_CONVERSATION_DRAFT_SYSTEM,
    BIG_CONVERSATION_DRAFT_PROMPT,
)
from flatwhite.classify.utils import _parse_llm_json
from flatwhite.db import get_connection, get_current_week_iso


def generate_angles(
    editorial_direction: str = "",
    selected_item_ids: list[int] | None = None,
) -> list[dict]:
    """Generate 3 Big Conversation angle candidates via Gemini 2.5 Flash.

    Args:
        editorial_direction: Optional free-text editorial steering (e.g. "focus on
            return-to-office, avoid AI"). Injected into the LLM prompt.
        selected_item_ids: Optional list of curated_item IDs to use as input.
            If None, falls back to top 30 non-discarded items for the current week.

    Output: list of dicts with keys: theme (str), headline (str), pitch (str),
            supporting_item_ids (list[int]).
    Consumed by: cli.py cmd_angles() (Step 8), Session 3 Big Conversation page.
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    if selected_item_ids:
        placeholders = ",".join("?" for _ in selected_item_ids)
        items = conn.execute(
            f"""SELECT ci.id, ci.section, ci.summary, ci.score_relevance, ci.score_tension,
                      ci.weighted_composite, ci.tags, ri.title, ri.source
            FROM curated_items ci
            JOIN raw_items ri ON ci.raw_item_id = ri.id
            WHERE ci.id IN ({placeholders}) AND ci.section != 'discard'
            ORDER BY ci.weighted_composite DESC""",
            selected_item_ids,
        ).fetchall()
    else:
        items = conn.execute(
            """SELECT ci.id, ci.section, ci.summary, ci.score_relevance, ci.score_tension,
                      ci.weighted_composite, ci.tags, ri.title, ri.source
            FROM curated_items ci
            JOIN raw_items ri ON ci.raw_item_id = ri.id
            WHERE ri.week_iso = ? AND ci.section != 'discard'
            ORDER BY ci.weighted_composite DESC
            LIMIT 30""",
            (week_iso,),
        ).fetchall()
    conn.close()

    if not items:
        return []

    items_data = [dict(i) for i in items]

    direction_block = ""
    if editorial_direction.strip():
        direction_block = (
            f"EDITORIAL DIRECTION: {editorial_direction.strip()}\n"
            "Use this direction to guide your theme selection and angle framing. "
            "Prioritise items and themes that align with this direction.\n\n"
        )

    prompt = BIG_CONVERSATION_ANGLES_PROMPT.format(
        items_json=json.dumps(items_data, indent=2),
        editorial_direction=direction_block,
    )

    try:
        response = route(
            task_type="big_conversation",
            prompt=prompt,
            system=BIG_CONVERSATION_ANGLES_SYSTEM,
        )
    except Exception as e:
        print(f"[generate_angles] LLM call failed: {e}")
        raise

    result = _parse_llm_json(response)

    if result is None or not isinstance(result, list):
        print(f"[generate_angles] LLM returned unparseable response: {response[:500]}")
        raise ValueError("LLM returned invalid JSON — expected a list of angles")

    # Validate each angle
    validated: list[dict] = []
    for angle in result[:3]:
        if not isinstance(angle, dict):
            continue
        headline = angle.get("headline")
        pitch = angle.get("pitch")
        theme = angle.get("theme", "")
        ids = angle.get("supporting_item_ids", [])
        if not isinstance(headline, str) or not isinstance(pitch, str):
            continue
        if not isinstance(theme, str):
            theme = ""
        if not isinstance(ids, list):
            ids = []
        validated.append({
            "theme": theme,
            "headline": headline,
            "pitch": pitch,
            "supporting_item_ids": ids,
        })

    return validated


def draft_big_conversation(headline: str, pitch: str, supporting_item_ids: list[int]) -> str:
    """Draft a 200-300 word Big Conversation editorial via Gemini 2.5 Flash.

    Input: headline (str), pitch (str), supporting_item_ids (list of curated_item IDs).
    Action:
    1. Read supporting items from curated_items joined with raw_items.
    2. Format supporting items as bullet text.
    3. Send to Gemini 2.5 Flash via route(task_type="big_conversation").
    4. Return raw draft text.

    Output: string containing editorial text (200-300 words).
    Consumed by: Session 3 Big Conversation page, Session 4 newsletter assembler.
    """
    conn = get_connection()
    items: list[dict] = []
    for item_id in supporting_item_ids:
        row = conn.execute(
            """SELECT ci.summary, ci.tags, ri.title, ri.source
            FROM curated_items ci
            JOIN raw_items ri ON ci.raw_item_id = ri.id
            WHERE ci.id = ?""",
            (item_id,),
        ).fetchone()
        if row:
            items.append(dict(row))
    conn.close()

    if items:
        supporting_text = "\n".join(
            f"- {item['title']} ({item['source']}): {item['summary']}"
            for item in items
        )
    else:
        supporting_text = "No supporting items available."

    prompt = BIG_CONVERSATION_DRAFT_PROMPT.format(
        headline=headline,
        pitch=pitch,
        supporting_items=supporting_text,
    )

    try:
        draft = route(
            task_type="big_conversation",
            prompt=prompt,
            system=BIG_CONVERSATION_DRAFT_SYSTEM,
        )
    except Exception as e:
        print(f"[draft_big_conversation] LLM call failed: {e}")
        raise

    return draft.strip()
