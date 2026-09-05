"""Tests for the dashboard-enforced strip stage.

Both Big Conversation runs on 17 Aug 2026 finished without the strip stage
ever running: the skill describes the pipeline in prose but gives the agent
no command, so the agent improvised and "did the pass by hand" on Claude -
exactly the failure mode the stage exists to prevent. The fix takes it out of
the agent's hands: once the skill has written the piece, the dashboard runs
the strip itself.

No real LLM calls - the strip function is injected.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flatwhite.dashboard import strip_stage


PIECE = """**THE BIG CONVERSATION**

Nobody is reading your Teams chat until they have a reason to.

At the end of the day, most large employers have monitoring switched on.

Almost nothing happens when you get flagged.

---

## BUILD: paragraph to screenshot map

| Rank | File | Handle |
|---|---|---|
| 1 | `p1_1_Tom.png` | Tom |
"""


def _piece_file(tmp_path):
    p = tmp_path / "_Teams:Slack_Monitoring_BIG_CONVERSATION.md"
    p.write_text(PIECE)
    return p


def test_writes_stripped_file_beside_the_piece_and_leaves_the_original_alone(tmp_path):
    piece = _piece_file(tmp_path)

    def fake_strip(draft):
        return ("Nobody is reading your Teams chat until they have a reason to.\n\n"
                "Most large employers have monitoring switched on.\n\n"
                "Almost nothing happens when you get flagged.\n"
                "---CHANGES---\n"
                "- Deleted \"At the end of the day,\" (stock phrase)")

    result = strip_stage.strip_piece_file(piece, strip_fn=fake_strip)

    stripped = tmp_path / "_Teams:Slack_Monitoring_BIG_CONVERSATION_STRIPPED.md"
    assert result["status"] == "stripped"
    assert stripped.exists()
    text = stripped.read_text()
    assert "Most large employers have monitoring switched on." in text
    assert "At the end of the day" in text  # only inside the change log
    assert "CHANGES" in text
    # The draft the skill wrote is never overwritten.
    assert piece.read_text() == PIECE


def test_only_the_prose_is_sent_to_the_stripper_never_the_build_map(tmp_path):
    """The build map is tables, filenames and Victor's flags. Sending it would
    invite the model to 'strip' rows out of the screenshot mapping."""
    piece = _piece_file(tmp_path)
    seen = {}

    def fake_strip(draft):
        seen["draft"] = draft
        return draft + "\n---CHANGES---\n- none"

    strip_stage.strip_piece_file(piece, strip_fn=fake_strip)

    assert "Nobody is reading your Teams chat" in seen["draft"]
    assert "BUILD" not in seen["draft"]
    assert "p1_1_Tom.png" not in seen["draft"]


def test_counts_the_changes_so_the_topic_page_can_show_them(tmp_path):
    piece = _piece_file(tmp_path)

    def fake_strip(draft):
        return ("body\n"
                "---CHANGES---\n"
                "- Deleted \"At the end of the day,\" (stock phrase)\n"
                "- Rewrote \"it's worth noting that\" (stock phrase)")

    result = strip_stage.strip_piece_file(piece, strip_fn=fake_strip)

    assert result["change_count"] == 2


def test_failure_is_loud_and_writes_no_file_that_could_pass_as_stripped(tmp_path):
    """A missing key must never leave behind a file that looks like a
    stripped piece - that is how the silent-run bug happened the first time."""
    piece = _piece_file(tmp_path)

    def fake_strip(draft):
        raise ValueError("No API key configured for gpt-5.4 (set OPENAI_API_KEY)")

    result = strip_stage.strip_piece_file(piece, strip_fn=fake_strip)

    stripped = tmp_path / "_Teams:Slack_Monitoring_BIG_CONVERSATION_STRIPPED.md"
    assert result["status"] == "failed"
    assert "OPENAI_API_KEY" in result["error"]
    assert not stripped.exists()


def test_missing_piece_file_is_reported_not_crashed(tmp_path):
    result = strip_stage.strip_piece_file(tmp_path / "nope.md", strip_fn=lambda d: d)
    assert result["status"] == "failed"
    assert "not found" in result["error"].lower()


# ─── Wiring: the dashboard runs the strip when a run finishes ───────────────


def test_strip_runs_automatically_when_a_big_conversation_run_succeeds(tmp_path):
    piece = _piece_file(tmp_path)
    result = strip_stage.strip_topic_after_run(
        "Teams:Slack Monitoring", {"status": "done"},
        find_piece=lambda topic: piece,
        strip_fn=lambda d: d + "\n---CHANGES---\n- Deleted \"At the end of the day,\" (entry 23)",
        save_fn=lambda body: None)
    assert result["status"] == "stripped"
    assert result["change_count"] == 1
    assert strip_stage.stripped_path_for(piece).exists()


def test_a_stripped_piece_is_saved_as_the_weeks_section_output(tmp_path):
    """The plumbing bug this fixes: a skill-run piece never reached
    section_outputs, so Big Conversation could never go ready and the
    editorial intro stayed locked forever."""
    piece = _piece_file(tmp_path)
    saved = []
    strip_stage.strip_topic_after_run(
        "Teams:Slack Monitoring", {"status": "done"},
        find_piece=lambda topic: piece,
        strip_fn=lambda d: d + "\n---CHANGES---\n- none",
        save_fn=saved.append)
    assert len(saved) == 1
    assert "Nobody is reading your Teams chat" in saved[0]
    # Only the prose is saved - never the BUILD map.
    assert "p1_1_Tom.png" not in saved[0]


def test_a_failed_strip_saves_nothing_to_section_outputs(tmp_path):
    """An unstripped Claude piece must never silently become the week's
    ready output - that is the house rule the strip stage exists for."""
    piece = _piece_file(tmp_path)
    saved = []
    strip_stage.strip_topic_after_run(
        "Teams:Slack Monitoring", {"status": "done"},
        find_piece=lambda topic: piece,
        strip_fn=lambda d: (_ for _ in ()).throw(ValueError("boom")),
        save_fn=saved.append)
    assert saved == []


def test_an_over_ceiling_piece_gets_one_automatic_recut_before_the_strip(tmp_path):
    """The skill's own generation has no code-enforced word ceiling, so the
    dashboard checks mechanically and re-cuts once (25 Aug 2026)."""
    long_prose = "\n\n".join("word " * 150 for _ in range(4))  # 600 words, over 365
    p = tmp_path / "_Long_Topic_BIG_CONVERSATION.md"
    p.write_text(long_prose + "\n\n---\n\n## BUILD\n")
    recut_calls = []

    def fake_recut(draft, segment, word_count):
        recut_calls.append((segment, word_count))
        return "\n\n".join("word " * 80 for _ in range(4))  # 320 words, inside band

    # shape_fn is a passthrough so this test stays offline and still exercises
    # the re-cut path with the original 600-word draft.
    result = strip_stage.strip_piece_file(
        p, strip_fn=lambda d: d + "\n---CHANGES---\n- none", recut_fn=fake_recut,
        shape_fn=lambda d, seg: d)

    assert recut_calls == [("big_conversation", 600)]
    assert result["status"] == "stripped"
    assert result["length_warnings"] == []


def test_still_over_ceiling_after_recut_is_a_loud_warning_not_a_silent_ship(tmp_path):
    long_prose = "\n\n".join("word " * 150 for _ in range(4))
    p = tmp_path / "_Long_Topic_BIG_CONVERSATION.md"
    p.write_text(long_prose + "\n\n---\n\n## BUILD\n")

    result = strip_stage.strip_piece_file(
        p, strip_fn=lambda d: d + "\n---CHANGES---\n- none",
        recut_fn=lambda d, s, w: d,   # re-cut achieves nothing
        shape_fn=lambda d, seg: d)    # nor does shaping

    assert result["status"] == "stripped"
    assert len(result["length_warnings"]) == 1
    assert "hard ceiling" in result["length_warnings"][0]
    assert "LENGTH WARNINGS" in (tmp_path / "_Long_Topic_BIG_CONVERSATION_STRIPPED.md").read_text()


def test_strip_is_not_attempted_when_the_run_failed(tmp_path):
    """A failed run has no finished piece. Stripping whatever half-file is on
    disk would manufacture a 'checked' artefact for work that never finished."""
    piece = _piece_file(tmp_path)
    called = []
    result = strip_stage.strip_topic_after_run(
        "Teams:Slack Monitoring", {"status": "failed"},
        find_piece=lambda topic: piece,
        strip_fn=lambda d: called.append(d) or d)
    assert result["status"] == "skipped"
    assert called == []
    assert not strip_stage.stripped_path_for(piece).exists()


def test_missing_piece_after_a_done_run_is_reported_in_plain_english(tmp_path):
    result = strip_stage.strip_topic_after_run(
        "Teams:Slack Monitoring", {"status": "done"},
        find_piece=lambda topic: None,
        strip_fn=lambda d: d)
    assert result["status"] == "failed"
    assert "Teams:Slack Monitoring" in result["error"]


# ─── Status for the topic page ─────────────────────────────────────────────


def test_status_reads_success_back_off_disk_so_it_survives_a_restart(tmp_path):
    piece = _piece_file(tmp_path)
    strip_stage.strip_piece_file(
        piece,
        strip_fn=lambda d: d + "\n---CHANGES---\n- Deleted \"x\" (entry 23)\n- Rewrote \"y\" (entry 23)")
    strip_stage._LAST_RESULT.clear()  # simulate a dashboard restart

    status = strip_stage.strip_status_for_topic("Teams:Slack Monitoring",
                                                find_piece=lambda t: piece)
    assert status["status"] == "stripped"
    assert status["change_count"] == 2


def test_status_reports_a_remembered_failure_rather_than_silence(tmp_path):
    piece = _piece_file(tmp_path)
    strip_stage.strip_topic_after_run(
        "Teams:Slack Monitoring", {"status": "done"},
        find_piece=lambda t: piece,
        strip_fn=lambda d: (_ for _ in ()).throw(
            ValueError("No API key configured for gpt-5.4 (set OPENAI_API_KEY)")))

    status = strip_stage.strip_status_for_topic("Teams:Slack Monitoring",
                                                find_piece=lambda t: piece)
    assert status["status"] == "failed"
    assert "OPENAI_API_KEY" in status["error"]


def test_status_is_not_run_when_nothing_has_happened_yet(tmp_path):
    strip_stage._LAST_RESULT.clear()
    piece = _piece_file(tmp_path)
    status = strip_stage.strip_status_for_topic("Teams:Slack Monitoring",
                                                find_piece=lambda t: piece)
    assert status["status"] == "not_run"


def test_a_no_changes_bullet_is_not_counted_as_a_change(tmp_path):
    """The model reports "no changes" as a bullet like any other. Counting it
    told the topic page "1 change" on a piece it had not touched (caught live
    on the Phone Etiquette piece, 17 Aug 2026)."""
    piece = _piece_file(tmp_path)
    result = strip_stage.strip_piece_file(
        piece, strip_fn=lambda d: "body\n---CHANGES---\n- No changes made.")
    assert result["change_count"] == 0


def test_only_deleted_and_rewrote_bullets_count_as_changes(tmp_path):
    piece = _piece_file(tmp_path)
    result = strip_stage.strip_piece_file(
        piece,
        strip_fn=lambda d: ("body\n---CHANGES---\n"
                            "- Deleted \"at the end of the day\" (entry 23)\n"
                            "- Rewrote \"it's worth noting that x\" as \"x\" (entry 23)\n"
                            "- Nothing else matched the catalogue."))
    assert result["change_count"] == 2


# ─── SHAPE runs only when the piece is actually out of shape (26 Aug 2026) ──

def _long_piece(tmp_path, paragraphs, words_each):
    p = tmp_path / "_Long_BIG_CONVERSATION.md"
    body = "\n\n".join("word " * words_each for _ in range(paragraphs))
    p.write_text(body + "\n\n---\n\n## BUILD\n")
    return p


def test_shape_is_skipped_when_the_piece_is_already_in_band(tmp_path):
    """The skill shapes its own draft; both real runs landed in band. Running
    a Claude cutting pass on a good piece would rewrite it for no gain."""
    p = _long_piece(tmp_path, 4, 80)  # 320 words, 4 paragraphs = in band
    called = []
    strip_stage.strip_piece_file(
        p, strip_fn=lambda d: d + "\n---CHANGES---\n- none",
        shape_fn=lambda d, s: called.append(s) or d)
    assert called == [], "shape must not run on a piece already inside the band"


def test_shape_runs_when_the_piece_is_over_the_word_target(tmp_path):
    p = _long_piece(tmp_path, 4, 100)  # 400 words, over the 340 target
    called = []

    def fake_shape(draft, segment):
        called.append(segment)
        return "\n\n".join("word " * 80 for _ in range(4))

    r = strip_stage.strip_piece_file(
        p, strip_fn=lambda d: d + "\n---CHANGES---\n- none", shape_fn=fake_shape)
    assert called == ["big_conversation"]
    assert r["status"] == "stripped"
    assert r["length_warnings"] == []


def test_shape_runs_when_there_are_too_many_paragraphs(tmp_path):
    p = _long_piece(tmp_path, 6, 40)  # 240 words but 6 paragraphs
    called = []
    strip_stage.strip_piece_file(
        p, strip_fn=lambda d: d + "\n---CHANGES---\n- none",
        shape_fn=lambda d, s: called.append(s) or "\n\n".join("word " * 70 for _ in range(4)))
    assert called == ["big_conversation"]


def test_a_failed_shape_is_a_warning_not_a_dead_stop(tmp_path):
    p = _long_piece(tmp_path, 4, 100)

    def boom(draft, segment):
        raise RuntimeError("shape model unavailable")

    r = strip_stage.strip_piece_file(
        p, strip_fn=lambda d: d + "\n---CHANGES---\n- none",
        shape_fn=boom, recut_fn=lambda d, s, w: "\n\n".join("word " * 80 for _ in range(4)))
    assert r["status"] == "stripped"
    assert any("Shape pass failed" in w for w in r["length_warnings"])


def test_prose_only_skips_a_build_header_above_the_piece():
    """4 Sep 2026: the skill wrote its build notes ABOVE the piece, so the
    stripper was handed the notes and answered "no changes" - a strip that
    reads as done on prose it never saw."""
    text = (
        "# _Topic_ — THE BIG CONVERSATION\n\n"
        "Stage-1 GENERATE draft, 340 words.\n\n"
        "**Stage 3 (STRIP THE CLAUDE PHRASING) has NOT been run**.\n\n"
        "---\n\n"
        "**THE BIG CONVERSATION**\n\n"
        "Switching languages was never private.\n\n"
        "Nobody minds two colleagues speaking a language they don't understand.\n\n"
        "---\n\n"
        "## BUILD: paragraph → screenshot map\n\n"
        "| # | File |\n"
    )
    prose = strip_stage._prose_only(text)
    assert prose.startswith("**THE BIG CONVERSATION**")
    assert "Stage-1 GENERATE draft" not in prose
    assert "BUILD: paragraph" not in prose
