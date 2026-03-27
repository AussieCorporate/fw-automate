from __future__ import annotations

"""Model router for Flat White LLM calls.

Supports Anthropic Claude, Google Gemini, and OpenAI GPT models. Each model
is called via its respective SDK. The route() function accepts an optional
model_override to let the dashboard user pick which model to use per section.
"""

import os
import time
from dotenv import load_dotenv

load_dotenv(override=True)

TEMPERATURE_BY_TASK: dict[str, float] = {
    "classification": 0.1,
    "scoring": 0.1,
    "tagging": 0.1,
    "anomaly_summary": 0.2,
    "editorial": 0.3,
    "summary": 0.3,
    "hook": 0.7,
    "big_conversation": 0.3,
    "signal_intelligence": 0.2,
}

DEFAULT_MODEL_BY_TASK: dict[str, str] = {
    "classification": "gemini-2.5-flash",
    "scoring": "gemini-2.5-flash",
    "tagging": "gemini-2.5-flash",
    "anomaly_summary": "gemini-2.5-flash",
    "editorial": "claude-sonnet-4-6",
    "summary": "claude-sonnet-4-6",
    "hook": "claude-sonnet-4-6",
    "big_conversation": "claude-sonnet-4-6",
    "signal_intelligence": "claude-haiku-4-5",
}

MODEL_REGISTRY: dict[str, dict] = {
    "gemini-2.5-flash":  {"provider": "gemini",    "label": "Gemini 2.5 Flash",  "env_key": "GEMINI_API_KEY"},
    "claude-opus-4-6":   {"provider": "anthropic", "label": "Claude Opus 4.6",   "env_key": "ANTHROPIC_API_KEY"},
    "claude-sonnet-4-6": {"provider": "anthropic", "label": "Claude Sonnet 4.6", "env_key": "ANTHROPIC_API_KEY"},
    "claude-haiku-4-5":  {"provider": "anthropic", "label": "Claude Haiku 4.5",  "env_key": "ANTHROPIC_API_KEY"},
    "gpt-5.4":           {"provider": "openai",    "label": "GPT-5.4",           "env_key": "OPENAI_API_KEY"},
    "gpt-5.4-pro":       {"provider": "openai",    "label": "GPT-5.4 pro",       "env_key": "OPENAI_API_KEY"},
    "gpt-5.4-mini":      {"provider": "openai",    "label": "GPT-5.4 mini",      "env_key": "OPENAI_API_KEY"},
    "gpt-5.4-nano":      {"provider": "openai",    "label": "GPT-5.4 nano",      "env_key": "OPENAI_API_KEY"},
    "gpt-5.2":           {"provider": "openai",    "label": "GPT-5.2",           "env_key": "OPENAI_API_KEY"},
    "gpt-5.1":           {"provider": "openai",    "label": "GPT-5.1",           "env_key": "OPENAI_API_KEY"},
}


def list_available_models() -> list[dict]:
    """Return models that have API keys configured."""
    available = []
    for model_id, info in MODEL_REGISTRY.items():
        if os.getenv(info["env_key"]):
            available.append({"id": model_id, "label": info["label"], "provider": info["provider"]})
    return available


def _call_gemini(prompt: str, system: str, temperature: float) -> str:
    """Call Gemini 2.5 Flash. Supports both google-genai and google-generativeai SDKs."""
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system if system else None,
                temperature=temperature,
            ),
        )
        return response.text
    except ImportError:
        pass

    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=system if system else None,
    )
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(temperature=temperature),
    )
    return response.text


def _call_claude(model_id: str, prompt: str, system: str, temperature: float) -> str:
    """Call Claude via Anthropic SDK."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    messages = [{"role": "user", "content": prompt}]
    response = client.messages.create(
        model=model_id,
        max_tokens=4096,
        system=system if system else "",
        messages=messages,
        temperature=temperature,
    )
    return response.content[0].text


def _call_openai(model_id: str, prompt: str, system: str, temperature: float) -> str:
    """Call an OpenAI model via the openai SDK."""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError(f"OpenAI model {model_id} returned no text content")
    return content


def _call_model(model_id: str, prompt: str, system: str, temperature: float) -> str:
    """Dispatch to the right provider based on model_id."""
    info = MODEL_REGISTRY.get(model_id)
    if not info:
        raise ValueError(f"Unknown model: {model_id}")

    api_key = os.getenv(info["env_key"])
    if not api_key:
        raise ValueError(f"No API key configured for {model_id} (set {info['env_key']})")

    if info["provider"] == "gemini":
        return _call_gemini(prompt, system, temperature)
    elif info["provider"] == "anthropic":
        return _call_claude(model_id, prompt, system, temperature)
    elif info["provider"] == "openai":
        return _call_openai(model_id, prompt, system, temperature)
    else:
        raise ValueError(f"Unknown provider: {info['provider']}")


def route(task_type: str, prompt: str, system: str = "", model_override: str | None = None) -> str:
    """Route an LLM task. Uses model_override if provided, otherwise default for task_type.

    Retries once on failure with 2s backoff.
    """
    if task_type not in TEMPERATURE_BY_TASK:
        raise ValueError(
            f"Unknown task_type: {task_type}. Must be one of: "
            f"{', '.join(TEMPERATURE_BY_TASK.keys())}."
        )

    temperature = TEMPERATURE_BY_TASK[task_type]
    model_id = model_override or DEFAULT_MODEL_BY_TASK.get(task_type, "gemini-2.5-flash")

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _call_model(model_id, prompt, system, temperature)
        except Exception as e:
            last_error = e
            if attempt == 0:
                print(f"LLM call failed ({model_id}: {e}), retrying in 2s...")
                time.sleep(2.0)

    raise last_error


def call_gemini_flash(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """Legacy wrapper. Calls Gemini 2.5 Flash with retry."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _call_gemini(prompt, system, temperature)
        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(2.0)
    raise last_error
