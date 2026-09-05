"""Run stage 3 (STRIP THE CLAUDE PHRASING) over a finished Big Conversation
piece, from the dashboard, without asking the writing agent to do it.

Why this module exists: the big-conversation skill describes the three-stage
voice pipeline in prose but never gave the agent a command to run, so on both
17 Aug 2026 runs the agent improvised and did the strip "by hand" on Claude -
the exact thing the stage exists to prevent, since a Claude model cannot
reliably hear its own tells. Describing a step is not the same as enforcing
it. So the dashboard now runs the strip itself once the skill has written the
piece, and reports loudly when it can't.

Only the prose is ever sent to the model. The BUILD map below the first `---`
divider is tables, filenames and Victor's publishing flags; handing that to a
stripper would invite it to "tidy" the screenshot mapping.

The skill's own draft is never overwritten. The stripped version lands beside
it as a separate file so both can be read side by side.
"""
from __future__ import annotations

from pathlib import Path

from ..classify import voice_pipeline as vp

STRIPPED_SUFFIX = "_STRIPPED.md"


def stripped_path_for(piece_path: Path) -> Path:
    """`_X_BIG_CONVERSATION.md` -> `_X_BIG_CONVERSATION_STRIPPED.md`."""
    return piece_path.with_name(piece_path.stem + STRIPPED_SUFFIX)


def _prose_only(text: str) -> str:
    """Just the piece prose - the same section `parse_piece_markdown` shows.

    Imported lazily so this module stays importable without the Instagram
    output directory existing (same reason as `_find_piece_markdown`).

    This used to be `text.split("\\n---\\n", 1)[0]`, i.e. "everything before
    the first divider". A piece written with a build header ABOVE it then fed
    the header to the stripper instead of the prose, which came back "no
    changes" - a strip that reads as done on prose it never saw.
    """
    from . import big_conversation_bank as bcb
    return bcb.extract_piece_section(text)


def _count_changes(changes: str) -> int:
    """Count only bullets that report an actual edit.

    The strip prompt requires every change bullet to open with "Deleted" or
    "Rewrote". Counting every bullet instead reported "1 change" for a piece
    whose log said "- No changes made." - a false positive that makes an
    untouched piece look checked.
    """
    return sum(1 for line in changes.splitlines()
               if line.strip().lower().startswith(("- deleted", "- rewrote")))


def _failure(error: str) -> dict:
    return {"status": "failed", "error": error, "path": None, "body": "",
            "changes": "", "flagged": "", "change_count": 0,
            "length_warnings": []}


def strip_piece_file(piece_path: Path, *, strip_fn=None, recut_fn=None, shape_fn=None) -> dict:
    """Strip `piece_path`'s prose and write the result beside it.

    Returns {"status": "stripped"|"failed", "error": str|None, "path": str|None,
    "body": str, "changes": str, "flagged": str, "change_count": int,
    "length_warnings": list[str]}.

    Length is checked mechanically before the strip (added 25 Aug 2026): the
    skill's own generation has no code-enforced word ceiling, so an
    over-ceiling piece gets ONE automatic re-cut pass (whole sentences deleted,
    never rephrased) before stripping. Still over after that, it is reported in
    length_warnings, never silently shipped.

    On failure NO file is written. A half-written or unstripped file sitting
    at the stripped path would read as "this was checked" when it wasn't,
    which is the silent-run failure all over again.
    """
    piece_path = Path(piece_path)
    if not piece_path.is_file():
        return _failure(f"Piece file not found: {piece_path}")

    prose = _prose_only(piece_path.read_text())
    if not prose:
        return _failure(f"No piece prose found in {piece_path.name} (nothing before the first '---').")

    length_warnings: list[str] = []
    spec = vp.LENGTH_SPECS["big_conversation"]
    counts = vp.check_length(prose, "big_conversation")

    # SHAPE (stage 2), run CONDITIONALLY - added 26 Aug 2026.
    #
    # Stage 2 was never wired into this path. Wiring it unconditionally would
    # be worse than leaving it out: the skill shapes its own draft and the two
    # real runs both landed inside the band (339 and 331 words, 4 paragraphs),
    # so an unconditional Claude cutting pass would rewrite good pieces for no
    # gain. It runs only when the mechanical check says the piece is genuinely
    # out of shape - too long, or too many paragraphs. SHAPE only ever cuts, so
    # it is not run on a piece that is UNDER the band; nothing it does could
    # help there.
    too_long = counts["word_count"] > spec["word_target_max"]
    too_many = counts["paragraph_count"] > spec["paragraph_target_max"]
    if too_long or too_many:
        shaper = shape_fn if shape_fn is not None else vp.shape_to_published
        try:
            shaped = shaper(prose, "big_conversation").strip()
            if shaped:
                prose = shaped
                counts = vp.check_length(prose, "big_conversation")
        except Exception as exc:  # noqa: BLE001 - shaping is a repair, not a gate
            length_warnings.append(f"Shape pass failed ({exc}); piece left as drafted.")

    if counts["over_word_hard_ceiling"]:
        cutter = recut_fn if recut_fn is not None else vp._recut_over_ceiling
        try:
            prose = cutter(prose, "big_conversation", counts["word_count"]).strip()
        except Exception as exc:  # noqa: BLE001 - a failed re-cut is a warning, not a dead stop
            length_warnings.append(f"Automatic re-cut failed ({exc}); piece is unshortened.")
        counts = vp.check_length(prose, "big_conversation")
        if counts["over_word_hard_ceiling"]:
            ceiling = spec["word_hard_ceiling"]
            length_warnings.append(
                f"Piece is {counts['word_count']} words, over the {ceiling}-word "
                "hard ceiling even after one automatic re-cut. Cut it by hand "
                "before shipping.")

    fn = strip_fn if strip_fn is not None else vp.strip_claude_phrasing
    try:
        raw = fn(prose)
    except Exception as exc:  # noqa: BLE001 - reported, never retried on Claude
        failure = _failure(vp._describe_strip_failure(exc))
        failure["length_warnings"] = length_warnings
        return failure

    parts = vp.split_strip_output(raw)
    out_path = stripped_path_for(piece_path)
    body = [
        f"# STRIPPED - {piece_path.name}",
        "",
        "Stage 3 of the voice pipeline (strip the Claude phrasing), run on "
        "GPT-5.4 by the dashboard, not by the writing agent. The original "
        "draft is untouched and sits next to this file.",
        "",
        parts["body"],
        "",
        "---CHANGES---",
        parts["changes"] or "- none",
    ]
    if length_warnings:
        body += ["", "---LENGTH WARNINGS---"] + [f"- {w}" for w in length_warnings]
    if parts["flagged"]:
        body += ["", "---FLAGGED FOR VICTOR---", parts["flagged"]]
    out_path.write_text("\n".join(body) + "\n")

    return {"status": "stripped", "error": None, "path": str(out_path),
            "body": parts["body"],
            "changes": parts["changes"], "flagged": parts["flagged"],
            "change_count": _count_changes(parts["changes"]),
            "length_warnings": length_warnings}


# Last strip outcome per topic, for the topic page. Success is read back off
# disk (the stripped file itself), so only failures need remembering - and a
# remembered failure is better than a silent gap until the next run.
_LAST_RESULT: dict[str, dict] = {}


def _save_to_section_outputs(body_text: str) -> None:
    """Default save hook: the finished, stripped piece becomes this week's
    big_conversation section output, so the segment can go ready on the board
    (and unlock the editorial intro) without a content-bank round-trip.
    Added 25 Aug 2026 - before this, a skill-run piece never reached
    section_outputs and the segment could never go green."""
    from flatwhite.db import get_current_week_iso, save_section_output

    save_section_output(get_current_week_iso(), "big_conversation", body_text,
                        "big-conversation-skill + gpt-5.4 strip")


def strip_topic_after_run(topic: str, record: dict | None, *,
                          find_piece=None, strip_fn=None, save_fn=None,
                          shape_fn=None) -> dict:
    """Run the strip for `topic` once its big-conversation run has finished.

    Wired in as the run's on_complete callback so the stage cannot be skipped,
    improvised, or "done by hand" on Claude by the writing agent.

    On a successful strip the final body is also saved as this week's
    big_conversation section output (see _save_to_section_outputs). A failed
    or skipped strip saves nothing - an unstripped Claude piece must never
    silently become the week's ready output.

    A run that did not finish is skipped entirely: there is no finished piece
    to strip, and stripping a half-written file would leave behind an artefact
    that reads as "this was checked".
    """
    if not record or record.get("status") != "done":
        result = {"status": "skipped", "error": None, "path": None, "body": "",
                  "changes": "", "flagged": "", "change_count": 0,
                  "length_warnings": []}
        _LAST_RESULT[topic] = result
        return result

    finder = find_piece if find_piece is not None else _find_piece_markdown
    piece = finder(topic)
    if piece is None:
        result = _failure(
            f'The run for "{topic}" finished but no piece file was found for '
            "it, so there was nothing to strip.")
    else:
        result = strip_piece_file(piece, strip_fn=strip_fn, shape_fn=shape_fn)

    if result["status"] == "stripped" and result["body"]:
        saver = save_fn if save_fn is not None else _save_to_section_outputs
        try:
            saver(result["body"])
        except Exception as exc:  # noqa: BLE001 - the strip itself succeeded; report, don't lose it
            result["error"] = f"Stripped fine, but saving to the week's section outputs failed: {exc}"

    _LAST_RESULT[topic] = result
    return result


def strip_status_for_topic(topic: str, *, find_piece=None) -> dict:
    """What the topic page shows about stage 3 for `topic`.

    Success is read back off disk, so it survives a dashboard restart - the
    stripped file IS the evidence. A failure is only in memory, but reporting
    a remembered failure beats showing nothing, which is how a skipped strip
    went unnoticed twice.
    """
    finder = find_piece if find_piece is not None else _find_piece_markdown
    piece = finder(topic)
    if piece is not None:
        out_path = stripped_path_for(Path(piece))
        if out_path.is_file():
            text = out_path.read_text()
            changes = text.split("---CHANGES---", 1)[1] if "---CHANGES---" in text else ""
            changes = changes.split("---FLAGGED FOR VICTOR---", 1)[0]
            return {"status": "stripped", "error": None, "path": str(out_path),
                    "change_count": _count_changes(changes)}

    remembered = _LAST_RESULT.get(topic)
    if remembered and remembered["status"] == "failed":
        return {"status": "failed", "error": remembered["error"],
                "path": None, "change_count": 0}
    return {"status": "not_run", "error": None, "path": None, "change_count": 0}


def _find_piece_markdown(topic: str):
    """Imported lazily so this module stays importable (and testable) without
    the Instagram output directory existing."""
    from . import big_conversation_bank as bcb
    return bcb.find_piece_markdown(topic)
