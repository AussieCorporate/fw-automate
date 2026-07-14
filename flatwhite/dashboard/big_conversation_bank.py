"""Read-only filesystem layer over the Instagram DM screenshotter's
output/ folder — the real source of Big Conversation topic candidates and
their sorted screenshots.

CRITICAL: every function in this module is read-only with respect to
INSTAGRAM_OUTPUT_DIR. It never writes, renames, moves, or deletes anything
there — that project is owned and maintained separately. Victor's archive
flag and drag-drop pairing overrides live in FW's own DB instead (see
flatwhite/dashboard/state.py).

Every public function fails soft: if the Instagram output folder (or a
topic within it) is missing, functions return an empty/soft result rather
than raising, since this machine may not have that project checked out.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote

INSTAGRAM_OUTPUT_DIR = Path(
    os.environ.get(
        "FW_INSTAGRAM_OUTPUT_DIR",
        str(Path.home() / "Documents" / "MISC" / "instagram-dm-screenshotter" / "output"),
    )
)

ASSETS_DIRNAME = "_BIG_CONVERSATION_assets"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Folders at the output root that are never Big Conversation topic
# candidates: junk, work-in-progress scratch space, or routed to a
# different segment (The Inside Track).
_EXCLUDED_EXACT = {"Rubbish", "MISC Stand alone", "Redundancies & Breaking News", "untitled folder"}
_EXCLUDED_PREFIXES = ("_", "DONE - ", "INCOMPLETE - ")


def _is_excluded(name: str) -> bool:
    if name in _EXCLUDED_EXACT:
        return True
    return any(name.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def _count_images(folder: Path) -> int:
    """Count original submission images directly under `folder`, excluding
    any copies already placed in a _BIG_CONVERSATION_assets subfolder (those
    are duplicates of originals elsewhere in the same tree, not new
    submissions)."""
    count = 0
    for p in folder.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if ASSETS_DIRNAME in p.relative_to(folder).parts:
            continue
        count += 1
    return count


def list_topic_folders() -> list[dict]:
    """Return the Big Conversation topic bank: every sorted Instagram topic
    folder that isn't excluded as junk/utility/already-manually-archived.

    Each item: {"topic": str, "reply_count": int, "processed": bool}.
    "processed" is True once the skill has written a
    _BIG_CONVERSATION_assets/ folder inside it (i.e. a piece exists).
    Does not know about Victor's explicit archive flag — that is merged in
    by the API layer (Task 8) from FW's own DB, keeping this module a pure
    filesystem read.
    """
    root = INSTAGRAM_OUTPUT_DIR
    if not root.is_dir():
        return []
    topics = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or _is_excluded(entry.name):
            continue
        topics.append({
            "topic": entry.name,
            "reply_count": _count_images(entry),
            "processed": (entry / ASSETS_DIRNAME).is_dir(),
        })
    return topics
