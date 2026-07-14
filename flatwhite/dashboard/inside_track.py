"""Read-only access to the Instagram DM screenshotter's Inside Track folder.

The Instagram sort skill (control-room increment 3) routes GOSSIP and
REDUNDANCY submissions out of the Big Conversation pile into a folder inside
the screenshotter's own `output/` directory. This module only ever READS
that folder — nothing here writes, moves, renames, or deletes anything
under the screenshotter's tree. That project owns its own files.
"""
from __future__ import annotations

from pathlib import Path

# The folder name the rebuilt sort skill (increment 3) is expected to use
# for gossip/redundancy submissions. "Redundancies & Breaking News" is the
# CURRENT real folder under the screenshotter's output/ (pre-rebuild) — kept
# as a fallback so this section has something to show before increment 3
# ships. Checked in this order; the first one that exists wins.
INSIDE_TRACK_FOLDER_CANDIDATES: list[str] = [
    "_INSIDE_TRACK",
    "Redundancies & Breaking News",
]

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def find_inside_track_folder(base_dir: Path) -> Path | None:
    """Return the first candidate Inside Track folder that exists under base_dir.

    Fails soft: returns None if base_dir itself doesn't exist, or no
    candidate folder is found. Never raises for a missing filesystem path.
    """
    if not base_dir.is_dir():
        return None
    for name in INSIDE_TRACK_FOLDER_CANDIDATES:
        candidate = base_dir / name
        if candidate.is_dir():
            return candidate
    return None


def list_inside_track_submissions(base_dir: Path) -> list[dict]:
    """List image submissions directly inside the Inside Track folder.

    Returns [] (fails soft) if base_dir or the Inside Track folder inside it
    is missing. Only looks at direct children — the folder is flat, one
    screenshot per submitter, no per-submitter subfolders — sorted
    case-insensitively by filename for a stable, predictable order.
    """
    folder = find_inside_track_folder(base_dir)
    if folder is None:
        return []
    submissions = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
            submissions.append({"filename": path.name, "folder": folder.name})
    return submissions


def resolve_inside_track_image(base_dir: Path, filename: str) -> Path | None:
    """Resolve `filename` to a real image file inside the Inside Track folder.

    Returns None (never raises) if: the Inside Track folder doesn't exist,
    the resolved path escapes the folder (path traversal via "../",
    an absolute path, or a symlink), the file doesn't exist, or it isn't
    one of the accepted image extensions.
    """
    folder = find_inside_track_folder(base_dir)
    if folder is None:
        return None
    folder_real = folder.resolve()
    candidate = (folder / filename).resolve()
    if not candidate.is_relative_to(folder_real):
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() not in _IMAGE_EXTENSIONS:
        return None
    return candidate
