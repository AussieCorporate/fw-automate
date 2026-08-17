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
    """The piece is everything before the first `---` divider - the same
    split `big_conversation_bank.parse_piece_markdown` uses."""
    return text.split("\n---\n", 1)[0].strip()


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
    return {"status": "failed", "error": error, "path": None,
            "changes": "", "flagged": "", "change_count": 0}


def strip_piece_file(piece_path: Path, *, strip_fn=None) -> dict:
    """Strip `piece_path`'s prose and write the result beside it.

    Returns {"status": "stripped"|"failed", "error": str|None, "path": str|None,
    "changes": str, "flagged": str, "change_count": int}.

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

    fn = strip_fn if strip_fn is not None else vp.strip_claude_phrasing
    try:
        raw = fn(prose)
    except Exception as exc:  # noqa: BLE001 - reported, never retried on Claude
        return _failure(vp._describe_strip_failure(exc))

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
    if parts["flagged"]:
        body += ["", "---FLAGGED FOR VICTOR---", parts["flagged"]]
    out_path.write_text("\n".join(body) + "\n")

    return {"status": "stripped", "error": None, "path": str(out_path),
            "changes": parts["changes"], "flagged": parts["flagged"],
            "change_count": _count_changes(parts["changes"])}


# Last strip outcome per topic, for the topic page. Success is read back off
# disk (the stripped file itself), so only failures need remembering - and a
# remembered failure is better than a silent gap until the next run.
_LAST_RESULT: dict[str, dict] = {}


def strip_topic_after_run(topic: str, record: dict | None, *,
                          find_piece=None, strip_fn=None) -> dict:
    """Run the strip for `topic` once its big-conversation run has finished.

    Wired in as the run's on_complete callback so the stage cannot be skipped,
    improvised, or "done by hand" on Claude by the writing agent.

    A run that did not finish is skipped entirely: there is no finished piece
    to strip, and stripping a half-written file would leave behind an artefact
    that reads as "this was checked".
    """
    if not record or record.get("status") != "done":
        result = {"status": "skipped", "error": None, "path": None,
                  "changes": "", "flagged": "", "change_count": 0}
        _LAST_RESULT[topic] = result
        return result

    finder = find_piece if find_piece is not None else _find_piece_markdown
    piece = finder(topic)
    if piece is None:
        result = _failure(
            f'The run for "{topic}" finished but no piece file was found for '
            "it, so there was nothing to strip.")
    else:
        result = strip_piece_file(piece, strip_fn=strip_fn)
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
