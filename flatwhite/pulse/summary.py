"""Generates editorial text for the Pulse section using the two-model split.

- generate_pulse_summary(): Gemini 2.5 Flash (task_type="editorial") — 2 sentences.
  Stored in pulse_history.summary_text.

- generate_driver_bullets(): Gemini 2.5 Flash (task_type="classification") — top 3 drivers as JSON.
  Returned as list of dicts, not stored.

- generate_top_line_hooks(): Gemini 2.5 Flash (task_type="hook") — 3 candidate hooks.
  Returned as list of strings, not stored.
"""

import json
from flatwhite.model_router import route
from flatwhite.classify.prompts import (
    PULSE_SUMMARY_SYSTEM,
    PULSE_SUMMARY_PROMPT,
    DRIVER_BULLETS_SYSTEM,
    DRIVER_BULLETS_PROMPT,
    TOP_LINE_HOOKS_SYSTEM,
    TOP_LINE_HOOKS_PROMPT,
)
from flatwhite.classify.utils import _parse_llm_json
from flatwhite.db import get_connection, get_current_week_iso, get_pulse_history, get_interactions
from flatwhite.signals.macro_context import fetch_macro_headlines


def generate_pulse_summary() -> str:
    """Generate a 2-sentence Pulse summary via Gemini 2.5 Flash.

    Action:
    1. Read pulse_history for current and previous week.
    2. Format PULSE_SUMMARY_PROMPT with score data.
    3. Call route(task_type="editorial") -> Gemini 2.5 Flash.
    4. Store result in pulse_history.summary_text for current week.
    5. Return summary string.

    Output stored in: pulse_history.summary_text (UPDATE, not INSERT).
    Consumed by: cli.py cmd_summarise(), Session 3 Pulse page, Session 4 newsletter blocks.
    """
    week_iso = get_current_week_iso()
    history = get_pulse_history(weeks=2)

    if not history:
        return "Insufficient data for Pulse summary."

    current = history[0]
    prev_smoothed = history[1]["smoothed_score"] if len(history) > 1 else current["smoothed_score"]

    interactions = get_interactions(current["week_iso"])
    if interactions:
        interaction_lines = ["Signal interactions detected this week:"]
        for ix in interactions:
            interaction_lines.append(f"- {ix['pattern_name']} (severity {ix['severity']:.1f}): {ix['narrative']}")
        interactions_block = "\n" + "\n".join(interaction_lines) + "\n"
    else:
        interactions_block = ""

    macro_context = fetch_macro_headlines()

    prompt = PULSE_SUMMARY_PROMPT.format(
        smoothed=current["smoothed_score"],
        direction=current["direction"],
        drivers=current["drivers_json"],
        prev_smoothed=prev_smoothed,
        interactions_block=interactions_block,
        macro_context=macro_context,
    )

    try:
        summary = route(
            task_type="editorial",
            prompt=prompt,
            system=PULSE_SUMMARY_SYSTEM,
        )
    except Exception:
        return "Pulse summary generation failed."

    summary_text = summary.strip()

    # Store in pulse_history
    conn = get_connection()
    conn.execute(
        "UPDATE pulse_history SET summary_text = ? WHERE week_iso = ?",
        (summary_text, week_iso),
    )
    conn.commit()
    conn.close()

    return summary_text


def generate_driver_bullets() -> list[dict]:
    """Generate top 3 Pulse driver bullets via Gemini 2.5 Flash.

    Action:
    1. Read all signals for current week where lane='pulse'.
    2. Format DRIVER_BULLETS_PROMPT with signal data as JSON.
    3. Call route(task_type="classification") -> Gemini Flash.
    4. Parse with _parse_llm_json().
    5. Validate each driver has signal, direction, bullet keys.
    6. Return list of up to 3 driver dicts.

    Output: list of dicts with keys: signal (str), direction (str), bullet (str).
    NOT stored in database — returned for display only.
    Consumed by: cli.py cmd_summarise(), Session 4 newsletter pulse block.
    """
    week_iso = get_current_week_iso()
    conn = get_connection()
    signals = conn.execute(
        "SELECT signal_name, normalised_score, raw_value FROM signals WHERE week_iso = ? AND lane = 'pulse'",
        (week_iso,),
    ).fetchall()
    conn.close()

    if not signals:
        return [{"signal": "no_data", "direction": "stable", "bullet": "No signal data available this week"}]

    signals_data = [dict(s) for s in signals]

    week_iso_current = get_current_week_iso()
    interactions = get_interactions(week_iso_current)
    if interactions:
        interaction_lines = ["Signal interactions detected this week:"]
        for ix in interactions:
            interaction_lines.append(f"- {ix['pattern_name']} (severity {ix['severity']:.1f}): {ix['narrative']}")
        interactions_block = "\n" + "\n".join(interaction_lines) + "\n"
    else:
        interactions_block = ""

    prompt = DRIVER_BULLETS_PROMPT.format(
        signals_json=json.dumps(signals_data, indent=2),
        interactions_block=interactions_block,
    )

    try:
        response = route(
            task_type="classification",
            prompt=prompt,
            system=DRIVER_BULLETS_SYSTEM,
        )
    except Exception:
        return [{"signal": "error", "direction": "stable", "bullet": "Driver generation failed"}]

    result = _parse_llm_json(response)

    if result is None or not isinstance(result, list):
        return [{"signal": "parse_error", "direction": "stable", "bullet": "Unable to parse driver data"}]

    # Validate each driver
    validated: list[dict] = []
    for driver in result[:3]:
        if not isinstance(driver, dict):
            continue
        validated.append({
            "signal": str(driver.get("signal", "unknown")),
            "direction": str(driver.get("direction", "stable")),
            "bullet": str(driver.get("bullet", "N/A")),
        })

    if not validated:
        return [{"signal": "empty", "direction": "stable", "bullet": "No drivers identified"}]

    return validated


def generate_top_line_hooks(top_items_text: str = "") -> list[str]:
    """Generate 3 Top Line hook candidates via Gemini 2.5 Flash.

    Input: top_items_text (str) — optional free-text description of top editorial items.
           If empty, uses default placeholder.
    Action:
    1. Read pulse_history for current week.
    2. Format TOP_LINE_HOOKS_PROMPT with pulse data and top items text.
    3. Call route(task_type="hook") -> Gemini 2.5 Flash.
    4. Parse with _parse_llm_json().
    5. Validate: result must be a list of strings.
    6. Return list of up to 3 hook strings.

    Output: list of strings (hook candidates).
    NOT stored in database — returned for display/selection.
    Consumed by: cli.py cmd_summarise(), Session 3 Big Conversation page.
    """
    history = get_pulse_history(weeks=1)
    if not history:
        return ["Insufficient data for hook generation."]

    current = history[0]

    items_text = top_items_text if top_items_text else "No editorial items classified yet."

    interactions = get_interactions(current["week_iso"])
    if interactions:
        interaction_lines = ["Signal interactions detected this week:"]
        for ix in interactions:
            interaction_lines.append(f"- {ix['pattern_name']} (severity {ix['severity']:.1f}): {ix['narrative']}")
        interactions_block = "\n" + "\n".join(interaction_lines) + "\n"
    else:
        interactions_block = ""

    macro_context = fetch_macro_headlines()

    prompt = TOP_LINE_HOOKS_PROMPT.format(
        smoothed=current["smoothed_score"],
        direction=current["direction"],
        drivers=current["drivers_json"],
        top_items=items_text,
        interactions_block=interactions_block,
        macro_context=macro_context,
    )

    try:
        response = route(
            task_type="hook",
            prompt=prompt,
            system=TOP_LINE_HOOKS_SYSTEM,
        )
    except Exception:
        return ["Hook generation failed."]

    result = _parse_llm_json(response)

    if result is None or not isinstance(result, list):
        # Fallback: return raw response as single hook
        return [response.strip()]

    # Validate: all items must be strings
    hooks: list[str] = []
    for item in result[:3]:
        if isinstance(item, str) and len(item) > 5:
            hooks.append(item)

    if not hooks:
        return [response.strip()]

    return hooks
