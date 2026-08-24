"""Brains Trust: several angles on one topic, drafted as a converged view.

Victor picks BY TOPIC - a handful of angles that are facets of the same story -
and wants the piece to find the view that reconciles them, with every angle he
ticked addressed. The old single-angle prompt could not express that, and its
"ignore anything unrelated" wording actively licensed the model to drop the
related angles sitting in the pool.

The legacy single-angle payload must keep working: tests/test_brains_trust_proceed.py
is left untouched and is the compatibility guarantee.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flatwhite.dashboard.api as api


def _capture_route(monkeypatch):
    # Stubs the whole 25-Aug voice-chain path: api.route captures the first
    # (GENERATE) call; voice_pipeline.route covers shape+strip; web_research
    # is stubbed so no test ever touches the live web.
    captured = {}

    def fake_route(task_type, prompt, system="", model_override=None):
        if "task_type" not in captured:
            captured["task_type"] = task_type
            captured["prompt"] = prompt
            captured["system"] = system
            captured["model_override"] = model_override
        return "Drafted Brains Trust body."

    import flatwhite.classify.voice_pipeline as vp
    import flatwhite.model_router as mr
    monkeypatch.setattr(api, "route", fake_route)
    monkeypatch.setattr(vp, "route",
                        lambda task_type, prompt, system="", model_override=None:
                        "Drafted Brains Trust body.")
    monkeypatch.setattr(mr, "web_research", lambda *a, **k: "NOTHING_FOUND")
    monkeypatch.setattr(api, "list_available_models",
                        lambda: [{"id": "claude-sonnet-4-6"}])
    return captured


_ANGLES = [
    {"date_iso": "2026-07-24", "pitch": "Job market is cooling",
     "angle": "76k jobs added but participation masks slack.",
     "why_tac": "Bargaining power at review time."},
    {"date_iso": "2026-07-23", "pitch": "Wesfarmers downgraded on weak spending",
     "angle": "Morgan Stanley cut on discretionary softness.",
     "why_tac": "Your spending is the signal."},
    {"date_iso": "2026-07-21", "pitch": "Home prices already down 3%",
     "angle": "Sydney and Melbourne falling, more to come.",
     "why_tac": "Mortgage and equity impact."},
]


def test_all_selected_angles_reach_the_prompt_in_tick_order(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": _ANGLES}, None)

    prompt = cap["prompt"]
    positions = [prompt.index(a["pitch"]) for a in _ANGLES]
    assert positions == sorted(positions), "angles must appear in tick order"


def test_first_pick_is_marked_as_the_anchor(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": _ANGLES}, None)

    prompt = cap["prompt"].lower()
    assert "anchor" in prompt


def test_multi_angle_prompt_asks_for_a_converged_view(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": _ANGLES}, None)

    prompt = cap["prompt"].lower()
    assert "converge" in prompt, "must ask for the view that reconciles the angles"


def test_multi_angle_prompt_requires_every_angle_be_addressed(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": _ANGLES}, None)

    prompt = cap["prompt"].lower()
    assert "every selected angle" in prompt


def test_multi_angle_prompt_forbids_inventing_a_link(monkeypatch):
    """If the picks do not converge, say so rather than manufacture a thread."""
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": _ANGLES}, None)

    prompt = cap["prompt"].lower()
    assert "do not invent" in prompt or "do not manufacture" in prompt


def test_multi_angle_prompt_bans_meta_commentary_about_the_selection(monkeypatch):
    """First real draft opened with "The three angles here converge cleanly on
    one thesis:" - the piece explaining itself, which the house voice bans.
    The convergence framing must guide the writing without appearing in it."""
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": _ANGLES}, None)

    prompt = cap["prompt"].lower()
    assert "never mention the angles" in prompt
    assert "not part of the piece" in prompt


def test_single_angle_gets_no_convergence_instruction(monkeypatch):
    """Nothing to converge with one angle - the instruction would be noise."""
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": [_ANGLES[0]]}, None)

    assert "converge" not in cap["prompt"].lower()
    assert _ANGLES[0]["pitch"] in cap["prompt"]


def test_legacy_single_angle_payload_still_builds_a_prompt(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({
        "chosen_pitch": "Legacy pitch",
        "chosen_angle": "Legacy angle",
        "chosen_why_tac": "Legacy why",
    }, None)

    assert "Legacy pitch" in cap["prompt"]
    assert "converge" not in cap["prompt"].lower()


def test_chosen_angles_wins_over_legacy_keys(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({
        "chosen_angles": [_ANGLES[0]],
        "chosen_pitch": "Stale legacy pitch",
    }, None)

    assert _ANGLES[0]["pitch"] in cap["prompt"]
    assert "Stale legacy pitch" not in cap["prompt"]


def test_malformed_entries_are_skipped(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({"chosen_angles": [
        "not a dict",
        {"pitch": "   "},
        {"angle": "no pitch at all"},
        _ANGLES[0],
    ]}, None)

    assert _ANGLES[0]["pitch"] in cap["prompt"]
    assert "no pitch at all" not in cap["prompt"]
    # only one usable angle survived, so no convergence instruction
    assert "converge" not in cap["prompt"].lower()


def test_all_malformed_falls_back_to_legacy_keys(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({
        "chosen_angles": ["nope", {"pitch": ""}],
        "chosen_pitch": "Fallback pitch",
        "chosen_angle": "Fallback angle",
    }, None)

    assert "Fallback pitch" in cap["prompt"]


def test_pool_still_travels_with_the_request(monkeypatch):
    cap = _capture_route(monkeypatch)
    api._proceed_brains_trust({
        "chosen_angles": _ANGLES[:1],
        "candidates_pool": [
            {"date_iso": "2026-07-10", "pitch": "Pool pitch", "angle": "pool angle"},
        ],
    }, None)

    assert "Pool pitch" in cap["prompt"]


def test_custom_prompt_still_bypasses_everything(monkeypatch):
    cap = _capture_route(monkeypatch)
    out = api._proceed_brains_trust(
        {"chosen_angles": _ANGLES}, None, custom_prompt="Write exactly this."
    )

    assert out == "Drafted Brains Trust body."
    assert cap["prompt"] == "Write exactly this."


# ── Source PDF pooling ────────────────────────────────────────────────────────

def test_pool_source_pdf_ids_dedupes_and_preserves_order():
    angles = [
        {"pitch": "a", "source_pdf_ids": [3, 1]},
        {"pitch": "b", "source_pdf_ids": [1, 7]},
        {"pitch": "c"},
        {"pitch": "d", "source_pdf_ids": []},
    ]
    assert api._pool_source_pdf_ids(angles) == [3, 1, 7]


def test_pool_source_pdf_ids_ignores_junk():
    angles = [
        "not a dict",
        {"pitch": "a", "source_pdf_ids": "nope"},
        {"pitch": "b", "source_pdf_ids": [2, "x", None, 5]},
    ]
    assert api._pool_source_pdf_ids(angles) == [2, 5]


def test_pool_source_pdf_ids_on_empty_input():
    assert api._pool_source_pdf_ids([]) == []
    assert api._pool_source_pdf_ids(None) == []
