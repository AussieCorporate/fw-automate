import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.model_router import TEMPERATURE_BY_TASK, DEFAULT_MODEL_BY_TASK


def test_brains_trust_task_type_is_registered():
    assert "brains_trust" in TEMPERATURE_BY_TASK
    assert 0.0 <= TEMPERATURE_BY_TASK["brains_trust"] <= 0.5  # data-led, not free-wheeling
    assert DEFAULT_MODEL_BY_TASK["brains_trust"] == "claude-sonnet-4-6"


def test_brains_trust_voice_exists_and_bans_em_dashes():
    from flatwhite.classify.prompts import BRAINS_TRUST_VOICE
    assert "Aussie Corporate" in BRAINS_TRUST_VOICE or "Flat White" in BRAINS_TRUST_VOICE
    assert "—" not in BRAINS_TRUST_VOICE  # the prompt itself must not contain an em dash
    assert "no em dash" in BRAINS_TRUST_VOICE.lower() or "em dash" in BRAINS_TRUST_VOICE.lower()
