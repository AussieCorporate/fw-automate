"""Tests for model_router — provider dispatch and task type routing."""
from unittest.mock import patch
import pytest


def test_openai_models_in_registry():
    from flatwhite.model_router import MODEL_REGISTRY
    for model_id in ["gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.2", "gpt-5.1"]:
        assert model_id in MODEL_REGISTRY, f"{model_id} missing from MODEL_REGISTRY"
        assert MODEL_REGISTRY[model_id]["provider"] == "openai"
        assert MODEL_REGISTRY[model_id]["env_key"] == "OPENAI_API_KEY"


def test_claude_opus_in_registry():
    from flatwhite.model_router import MODEL_REGISTRY
    assert "claude-opus-4-6" in MODEL_REGISTRY
    assert MODEL_REGISTRY["claude-opus-4-6"]["provider"] == "anthropic"


def test_signal_intelligence_task_type():
    from flatwhite.model_router import TEMPERATURE_BY_TASK, DEFAULT_MODEL_BY_TASK
    assert "signal_intelligence" in TEMPERATURE_BY_TASK
    assert TEMPERATURE_BY_TASK["signal_intelligence"] == 0.2
    assert DEFAULT_MODEL_BY_TASK.get("signal_intelligence") == "claude-haiku-4-5"


def test_openai_dispatch_calls_openai_sdk():
    """route() should call _call_openai for an OpenAI model."""
    import os
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch("flatwhite.model_router._call_openai", return_value="result") as mock_openai:
            from flatwhite.model_router import route
            result = route("signal_intelligence", "test prompt", model_override="gpt-5.4")
            mock_openai.assert_called_once()
            assert result == "result"
