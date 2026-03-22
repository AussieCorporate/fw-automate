from __future__ import annotations

"""Model router for Flat White LLM calls.

All tasks route through Gemini 2.5 Flash via call_gemini_flash().
Retry once with exponential backoff on failure.
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

# Temperature overrides by task type — classification needs determinism,
# editorial tasks benefit from slightly more creativity.
TEMPERATURE_BY_TASK: dict[str, float] = {
    "classification": 0.1,
    "scoring": 0.1,
    "tagging": 0.1,
    "anomaly_summary": 0.2,
    "editorial": 0.3,
    "summary": 0.3,
    "hook": 0.7,
    "big_conversation": 0.3,
}


def call_gemini_flash(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """Call Gemini 2.5 Flash with one retry on failure.

    First attempt uses the given temperature. If it fails, waits 2 seconds
    and retries once. If the retry also fails, raises the exception.
    """
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system if system else None,
                    temperature=temperature,
                ),
            )
            return response.text
        except Exception as e:
            last_error = e
            if attempt == 0:
                wait = 2.0
                print(f"LLM call failed ({e}), retrying in {wait}s...")
                time.sleep(wait)

    raise last_error


def route(task_type: str, prompt: str, system: str = "") -> str:
    """Route an LLM task to Gemini 2.5 Flash.

    Supported task_types: classification, scoring, tagging, anomaly_summary,
    editorial, summary, hook, big_conversation.
    Uses task-specific temperature from TEMPERATURE_BY_TASK.
    """
    if task_type not in TEMPERATURE_BY_TASK:
        raise ValueError(
            f"Unknown task_type: {task_type}. Must be one of: "
            f"{', '.join(TEMPERATURE_BY_TASK.keys())}."
        )

    temperature = TEMPERATURE_BY_TASK[task_type]
    return call_gemini_flash(prompt, system, temperature=temperature)
