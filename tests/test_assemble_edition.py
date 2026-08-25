"""Tests for POST /api/assemble-edition. Monkeypatches section_outputs
storage (tmp DB) and passes the running order directly in the request body —
exactly what the dashboard's in-memory SEGMENTS array sends. NO beehiiv/network
call anywhere: this asserts on the block STRUCTURE the endpoint returns, never
a live insert (Design B — see the plan's Global Constraints).

NOTE: the real FW dashboard section id for the Brains Trust segment is
"brains_trust" (confirmed in flatwhite/dashboard/static/index.html's SEGMENTS
array and flatwhite/dashboard/api.py's proceed_fns dict, and already corrected
the same way in Task 3's flatwhite/assemble/benchmark.py) — NOT "brains".
"""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def assemble_client(tmp_path: Path):
    db_path = tmp_path / "assemble_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        week_iso = db_module.get_current_week_iso()
        db_module.save_section_output(week_iso, "editorial", "**Good morning AusCorp.** " + "word " * 150, "m")
        db_module.save_section_output(week_iso, "big_conversation", "**A quiet mutiny.**\n\n" + "word " * 400, "m")
        db_module.save_section_output(week_iso, "thread", "#### [_**Bunking with a colleague**_](https://reddit.com/x)\n\nA thread.", "m")
        import flatwhite.dashboard.api as api_module
        from fastapi.testclient import TestClient
        # The missed-last-week footer fetches the latest published edition
        # from beehiiv; tests never touch the network, so default to "fetch
        # failed" (None). Tests that want the footer patch this themselves.
        with patch.object(api_module, "_latest_published_edition", lambda: None):
            yield TestClient(api_module.app), week_iso


# "pulse" is absent on purpose: the AusCorp Stress Index was decommissioned
# 25 Aug 2026 and is no longer a running-order segment.
_BASE_SEGMENTS = [
    {"id": "editorial", "status": "ready"},
    {"id": "brains_trust", "status": "notready"},
    {"id": "top_picks", "status": "notready"},
    {"id": "insidetrack", "status": "notready"},
    {"id": "off_the_clock", "status": "notready"},
    {"id": "thread", "status": "ready"},
    {"id": "big_conversation", "status": "ready"},
]


def test_assemble_returns_only_ready_segments_in_running_order(assemble_client):
    client, week_iso = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    assert resp.status_code == 200
    body = resp.json()
    ids_in_order = [b["section"] for b in body["blocks"] if b["section"] in
                    ("editorial", "brains_trust", "top_picks", "insidetrack",
                     "off_the_clock", "thread", "big_conversation")]
    assert ids_in_order == ["editorial", "thread", "big_conversation"]


def test_not_ready_segments_are_flagged_missing_not_silently_dropped(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    missing = resp.json()["missing_ready"]
    assert set(missing) == {"brains_trust", "top_picks", "insidetrack", "off_the_clock"}


def test_each_block_has_html_and_benchmark(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    blocks = resp.json()["blocks"]
    editorial_block = next(b for b in blocks if b["section"] == "editorial")
    assert "<h3" in editorial_block["html"] and "<strong>INTRO</strong>" in editorial_block["html"]
    assert "benchmark" in editorial_block
    assert editorial_block["benchmark"]["status"] in ("short", "within", "long", "no_data")


def test_feedback_loop_boilerplate_always_appended_last(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    blocks = resp.json()["blocks"]
    assert blocks[-1]["section"] == "feedback_loop"
    assert "tally.so" in blocks[-1]["html"]


def test_odd_picks_included_only_when_provided(assemble_client):
    client, _ = assemble_client
    resp_without = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    sections_without = [b["section"] for b in resp_without.json()["blocks"]]
    assert "odd_picks" not in sections_without

    resp_with = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "odd_picks_text": "* A quirky link. [LINK](https://example.com)",
    })
    sections_with = [b["section"] for b in resp_with.json()["blocks"]]
    assert "odd_picks" in sections_with
    # Odd Picks sits after all running-order segments, before Feedback Loop.
    assert sections_with.index("odd_picks") == len(sections_with) - 2


def test_sponsor_included_only_when_toggled_on_and_placed_before_thread(assemble_client):
    client, _ = assemble_client
    resp_without = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    assert "sponsor" not in [b["section"] for b in resp_without.json()["blocks"]]

    resp_with = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "sponsor": {"include": True, "name": "Spaceship", "text": "Pitch text here."},
    })
    body = resp_with.json()
    sections = [b["section"] for b in body["blocks"]]
    assert "sponsor" in sections
    assert sections.index("sponsor") == sections.index("thread") - 1
    # Thread was ready, so the sponsor block genuinely made it into blocks.
    assert body["sponsor_included"] is True
    assert "sponsor" not in body["missing_ready"]


def test_sponsor_toggled_off_omits_even_if_text_given(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "sponsor": {"include": False, "name": "Spaceship", "text": "Pitch text here."},
    })
    body = resp.json()
    assert "sponsor" not in [b["section"] for b in body["blocks"]]
    # Sponsor wasn't wanted at all this week -- this is the normal "no sponsor"
    # case, not a dropped paid placement, so no entry should land in
    # missing_ready.
    assert body["sponsor_included"] is False
    assert "sponsor" not in body["missing_ready"]


def test_sponsor_wanted_but_thread_not_ready_is_flagged_not_silently_dropped(assemble_client):
    """Reproduces the Task 5 bug: sponsor.include=True but the Thread of the
    Week segment isn't 'ready' (its documented default is 'manual', and it can
    also be 'notready' before Victor has pasted/formatted the thread). The
    sponsor-insertion code only runs inside the 'thread' branch of the ready
    loop, so if Thread never reaches 'ready' the paid sponsor block was
    previously dropped with zero signal in the response. It must now show up
    as sponsor_included=False AND "sponsor" in missing_ready."""
    client, _ = assemble_client
    segments_thread_manual = [
        {"id": s["id"], "status": ("manual" if s["id"] == "thread" else s["status"])}
        for s in _BASE_SEGMENTS
    ]
    resp = client.post("/api/assemble-edition", json={
        "segments": segments_thread_manual,
        "sponsor": {"include": True, "name": "Spaceship", "text": "Pitch text here."},
    })
    body = resp.json()
    assert "sponsor" not in [b["section"] for b in body["blocks"]]
    assert body["sponsor_included"] is False
    assert "sponsor" in body["missing_ready"]

    # Also true when Thread is "notready" rather than "manual".
    segments_thread_notready = [
        {"id": s["id"], "status": ("notready" if s["id"] == "thread" else s["status"])}
        for s in _BASE_SEGMENTS
    ]
    resp2 = client.post("/api/assemble-edition", json={
        "segments": segments_thread_notready,
        "sponsor": {"include": True, "name": "Spaceship", "text": "Pitch text here."},
    })
    body2 = resp2.json()
    assert "sponsor" not in [b["section"] for b in body2["blocks"]]
    assert body2["sponsor_included"] is False
    assert "sponsor" in body2["missing_ready"]


def test_assembled_html_is_concatenation_of_block_html(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    body = resp.json()
    expected = "".join(b["html"] for b in body["blocks"])
    assert body["assembled_html"] == expected


def test_no_ready_segments_returns_empty_blocks_not_error(assemble_client):
    client, _ = assemble_client
    all_notready = [{"id": s["id"], "status": "notready"} for s in _BASE_SEGMENTS]
    resp = client.post("/api/assemble-edition", json={"segments": all_notready})
    assert resp.status_code == 200
    # Furniture (feedback loop) still present even with zero real segments.
    assert resp.json()["blocks"][-1]["section"] == "feedback_loop"


# ─── 25 Aug 2026 additions: salary survey, missed-last-week, events ─────────


def test_salary_survey_included_only_when_toggled_on(assemble_client):
    client, _ = assemble_client
    resp_without = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    assert "salary_survey" not in [b["section"] for b in resp_without.json()["blocks"]]

    resp_with = client.post("/api/assemble-edition", json={
        "segments": _BASE_SEGMENTS,
        "salary_survey": {"include": True, "text": "Submit your salary [HERE](https://tally.so/r/J9eqvo)."},
    })
    sections = [b["section"] for b in resp_with.json()["blocks"]]
    assert "salary_survey" in sections
    survey_block = next(b for b in resp_with.json()["blocks"] if b["section"] == "salary_survey")
    assert "2026 AUSCORP SALARY SURVEY" in survey_block["label"]


def test_missed_last_week_footer_auto_built_from_latest_edition(assemble_client, monkeypatch):
    client, _ = assemble_client
    import flatwhite.dashboard.api as api_module
    monkeypatch.setattr(api_module, "_latest_published_edition",
                        lambda: {"title": "Cover letter, yes or no?",
                                 "url": "https://theaussiecorporate.beehiiv.com/p/cover-letter-yes-or-no"})
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    body = resp.json()
    assert body["missed_last_week_included"] is True
    assert body["blocks"][-1]["section"] == "missed_last_week"
    assert "Cover letter, yes or no?" in body["blocks"][-1]["html"]


def test_missed_last_week_fetch_failure_is_reported_not_silent(assemble_client):
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    body = resp.json()
    assert body["missed_last_week_included"] is False
    assert "missed_last_week" not in [b["section"] for b in body["blocks"]]


def test_auscorp_events_is_a_real_running_order_segment(assemble_client):
    client, week_iso = assemble_client
    db_module.save_section_output(week_iso, "auscorp_events",
                                  "* **AusCorp Runs | Sydney | Coming Soon**", "manual")
    segments = _BASE_SEGMENTS + [{"id": "auscorp_events", "status": "ready"}]
    resp = client.post("/api/assemble-edition", json={"segments": segments})
    blocks = resp.json()["blocks"]
    events = next((b for b in blocks if b["section"] == "auscorp_events"), None)
    assert events is not None
    assert "AUSCORP EVENTS" in events["label"]


def test_forwarded_header_is_always_the_first_block(assemble_client):
    """10/10 published editions open with it, verbatim. Standing furniture."""
    client, _ = assemble_client
    resp = client.post("/api/assemble-edition", json={"segments": _BASE_SEGMENTS})
    blocks = resp.json()["blocks"]
    assert blocks[0]["section"] == "forwarded_header"
    assert "Was this email forwarded to you?" in blocks[0]["html"]
    assert "next Tuesday" in blocks[0]["html"]


def test_top_picks_carries_the_pick_and_scroll_promo(assemble_client, monkeypatch):
    """The promo closes Top Picks in 10/10 editions; only its link changes."""
    client, week_iso = assemble_client
    import flatwhite.dashboard.api as api_module
    monkeypatch.setattr(api_module, "_latest_ps_edition",
                        lambda: {"title": "Pointless",
                                 "url": "https://pickandscrollnews.beehiiv.com/p/pointless"})
    db_module.save_section_output(week_iso, "top_picks", "* **A pick**, with detail. [LINK](https://x.com)", "m")
    segments = [dict(s, status="ready") if s["id"] == "top_picks" else s for s in _BASE_SEGMENTS]
    resp = client.post("/api/assemble-edition", json={"segments": segments})
    tp = next(b for b in resp.json()["blocks"] if b["section"] == "top_picks")
    assert "Flat White lands every week. The news doesn&#x27;t." in tp["html"] or "Flat White lands every week" in tp["html"]
    assert "pickandscrollnews.beehiiv.com/p/pointless" in tp["html"]
    assert "This morning&#x27;s newsletter" in tp["html"] or "This morning" in tp["html"]


def test_ps_promo_still_ships_without_the_link_if_lookup_fails(assemble_client, monkeypatch):
    client, week_iso = assemble_client
    import flatwhite.dashboard.api as api_module
    monkeypatch.setattr(api_module, "_latest_ps_edition", lambda: None)
    db_module.save_section_output(week_iso, "top_picks", "* **A pick.** [LINK](https://x.com)", "m")
    segments = [dict(s, status="ready") if s["id"] == "top_picks" else s for s in _BASE_SEGMENTS]
    resp = client.post("/api/assemble-edition", json={"segments": segments})
    tp = next(b for b in resp.json()["blocks"] if b["section"] == "top_picks")
    assert "Flat White lands every week" in tp["html"]
    assert "This morning" not in tp["html"]  # no dead link
