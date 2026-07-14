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
from pathlib import Path

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


# Subfolder-name prefixes that mark a directory as a curated copy or working
# area rather than a store of original submissions. Verified empirically
# against the real output/ directory (see task-2-report.md, "Fix round 1"):
#   - "_" — internal working/asset dirs: _BIG_CONVERSATION_assets (the
#     piece's paragraph-mapped copies), plus other underscore-prefixed dirs
#     found in real sorted topics (e.g. "_EDITORIAL screenshots",
#     "_EDITORIAL_IMAGE_PACKS") that hold copies made after sorting, never
#     new submissions.
#   - "🔥" — curated "best of" pointer folders (RED HOT Top N, Top Picks,
#     Top Picks R3, ...). In every sampled real sorted topic (Kids in the
#     Office, Visa vs Resident Pay, Conference Room Sharing, Pay Negotiation,
#     and others), every file inside a "🔥"-prefixed folder is a renamed COPY
#     of a file that already exists at the topic root (topics with no tier
#     folders) or inside a Tier N folder (topics that use tiers) — never a
#     new, original submission. The "Pay Negotiation" topic's own curated
#     manifest confirms this in writing: "Originals untouched; these are
#     renamed copies in rank order." Counting a "🔥" folder's files in
#     addition to their tier/root originals double-counts real replies.
_EXCLUDED_SUBFOLDER_PREFIXES = ("_", "🔥")


def _count_images(folder: Path) -> int:
    """Count original submission images directly under `folder`, excluding
    any files inside a subfolder that is itself a curated copy or working
    area (see `_EXCLUDED_SUBFOLDER_PREFIXES`) rather than a store of new,
    original submissions."""
    count = 0
    for p in folder.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        dir_parts = p.relative_to(folder).parts[:-1]
        if any(part.startswith(_EXCLUDED_SUBFOLDER_PREFIXES) for part in dir_parts):
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
    try:
        entries = sorted(root.iterdir())
    except OSError:
        # Can't even list the root (e.g. permission denied) - fail soft per
        # this module's contract rather than raising.
        return []
    topics = []
    for entry in entries:
        try:
            if not entry.is_dir() or _is_excluded(entry.name):
                continue
            topics.append({
                "topic": entry.name,
                "reply_count": _count_images(entry),
                "processed": (entry / ASSETS_DIRNAME).is_dir(),
            })
        except OSError:
            # A specific topic folder is unreadable (e.g. PermissionError
            # partway through its tree) - skip just that topic rather than
            # failing the whole listing for every other topic.
            continue
    return topics
