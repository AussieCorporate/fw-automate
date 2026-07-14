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
_EXCLUDED_PREFIXES = (".", "_", "DONE - ", "INCOMPLETE - ")


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


_VIRAL_RE = re.compile(r"red\s*hot|viral\s*extreme", re.IGNORECASE)
_TIER_RES = {
    "T1": re.compile(r"\bt(?:ier)?\s*1\b", re.IGNORECASE),
    "T2": re.compile(r"\bt(?:ier)?\s*2\b", re.IGNORECASE),
    "T3": re.compile(r"\bt(?:ier)?\s*3\b", re.IGNORECASE),
}


def classify_tier_folder(name: str) -> str | None:
    """Map a topic subfolder name to a screenshot pool bucket: "viral",
    "T1", "T2", "T3", or None (not a recognised tier folder — e.g. "Tier 4
    - Rubbish" or "_EDITORIAL screenshots" — never shown in either pool).

    Recognises both the CURRENT folder names ("\U0001F525 RED HOT Top 22",
    "Tier 1 - Viral", "Tier 2 - Strong", "Tier 3 - Ordinary") and the
    renamed buckets increment 3's rebuilt sort skill is expected to use
    ("VIRAL EXTREME", "T1", "T2", "T3"). If increment 3 lands with
    different folder names than either of these, update the two regex
    tables above — nothing else in this module needs to change.
    """
    if _VIRAL_RE.search(name):
        return "viral"
    for bucket, pattern in _TIER_RES.items():
        if pattern.search(name):
            return bucket
    return None


def asset_url(*parts: str) -> str:
    """Build the /api/big-conversation/assets/... URL for a file living at
    INSTAGRAM_OUTPUT_DIR/<parts joined by '/'>, URL-encoding each segment
    (topic and folder names may contain spaces, colons, or emoji)."""
    rel = "/".join(quote(p, safe="") for p in parts)
    return f"/api/big-conversation/assets/{rel}"


def list_pool_screenshots(topic: str) -> dict[str, list[dict]]:
    """Return {"viral": [...], "T1": [...], "T2": [...], "T3": [...]},
    each a list of {"file": str, "url": str} for images directly inside
    the matching tier subfolder(s) of `topic`. Empty (all buckets) if the
    topic folder or the Instagram output root is absent."""
    pools: dict[str, list[dict]] = {"viral": [], "T1": [], "T2": [], "T3": []}
    topic_dir = INSTAGRAM_OUTPUT_DIR / topic
    if not topic_dir.is_dir():
        return pools
    for sub in sorted(topic_dir.iterdir()):
        if not sub.is_dir():
            continue
        bucket = classify_tier_folder(sub.name)
        if not bucket:
            continue
        for img in sorted(sub.iterdir()):
            if img.is_file() and img.suffix.lower() in IMAGE_EXTENSIONS:
                pools[bucket].append({"file": img.name, "url": asset_url(topic, sub.name, img.name)})
    return pools


def find_piece_markdown(topic: str) -> Path | None:
    """Find the `_<SHORTNAME>_BIG_CONVERSATION.md` file the skill wrote for
    `topic`, at the Instagram output root. The shortname is an AI-chosen
    abbreviation (e.g. "Kids in the Office" -> "_KIDS_OFFICE_BIG_CONVERSATION.md")
    that can't be derived from the folder name programmatically — instead
    this searches every `_*_BIG_CONVERSATION.md` at the output root for the
    one whose BUILD map references this topic's own assets folder, e.g.
    "Assets in `Kids in the Office/_BIG_CONVERSATION_assets/`."

    The skill always wraps that reference in backticks immediately before
    the topic name (no other text in between). Matching includes the
    leading backtick rather than a bare substring so a topic name that is
    a trailing fragment of a longer topic's name (e.g. "Office" or "the
    Office" inside "Kids in the Office") can't false-match it — the
    backtick only ever sits directly before the FULL topic name.

    Returns None (soft-fail, not an error) if the Instagram output root is
    absent or no matching piece has been written yet — the topic just
    isn't processed yet.
    """
    root = INSTAGRAM_OUTPUT_DIR
    if not root.is_dir():
        return None
    needle = f"`{topic}/{ASSETS_DIRNAME}".lower()
    for md in sorted(root.glob("_*_BIG_CONVERSATION.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text.lower():
            return md
    return None


def parse_piece_markdown(text: str) -> dict:
    """Split a `_<TOPIC>_BIG_CONVERSATION.md` file's finished-piece section
    into {"headline": str, "paragraphs": list[str]}.

    Per the big-conversation skill's own output shape: a
    `**THE BIG CONVERSATION**` header line, a one-line bold headline, then
    one paragraph per screenshot group (p1, p2, ...), then a `---` divider
    before the BUILD map. Only the text before the first such divider is
    the piece; everything after is the paragraph->screenshot map, read
    separately from the assets folder's own filenames (Task 5).
    """
    piece = text.split("\n---\n", 1)[0].strip()
    blocks = [b.strip() for b in re.split(r"\n\s*\n", piece) if b.strip()]
    if blocks and re.fullmatch(r"\*\*THE BIG CONVERSATION\*\*", blocks[0]):
        blocks = blocks[1:]
    headline = blocks[0] if blocks else ""
    paragraphs = blocks[1:]
    return {"headline": headline, "paragraphs": paragraphs}


_ASSET_NAME_RE = re.compile(r"^p(\d+)_(\d+|alt\d*)_.+\.(?:png|jpg|jpeg)$", re.IGNORECASE)


def _asset_rank(token: str) -> int:
    """Sort key for a screenshot's rank token. The skill's canonical
    convention is a plain numeric rank ("1", "2", "3", ... - see SKILL.md's
    "Emit outputs" example `p3_2_zucchinislice.png`), used by real topics
    like "PIP Term Length" and "Conference Room Sharing". An older/alternate
    convention ("1", "alt", "alt2", "alt3", ...) is already on disk for
    "Kids in the Office" and must keep working unchanged. Plain-numeric
    tokens sort by their own integer value (1, 2, 3, ...); "alt"-style
    tokens sort after all plain-numeric ranks, since "alt" denotes
    supplementary/backup picks in the topics that use it. "1" is shared by
    both conventions and always sorts first."""
    token = token.lower()
    if token.isdigit():
        return int(token)
    if token == "alt":
        return 1_000_000
    return 1_000_000 + int(token[3:])  # "alt2" -> 1_000_002, "alt3" -> 1_000_003


def list_paragraph_screenshots(topic: str) -> dict[int, list[dict]]:
    """Group `<topic>/_BIG_CONVERSATION_assets/*.png` files by paragraph
    number, using the skill's own naming convention
    `p<paragraph>_<rank>_<handle>.png`. Rank is either plain numeric
    ("1", "2", "3", ... - the skill's documented convention, see SKILL.md's
    "Emit outputs" step) or the older "1"/"alt"/"alt2"/"alt3" convention
    already on disk for some topics. Both are accepted since real topic
    folders on disk use either one and neither can be renamed. Returns {}
    if the assets folder is absent (topic not processed yet) or the
    Instagram output root is absent.
    """
    assets_dir = INSTAGRAM_OUTPUT_DIR / topic / ASSETS_DIRNAME
    if not assets_dir.is_dir():
        return {}
    by_paragraph: dict[int, list[dict]] = {}
    for img in assets_dir.iterdir():
        if not img.is_file():
            continue
        match = _ASSET_NAME_RE.match(img.name)
        if not match:
            continue
        paragraph = int(match.group(1))
        rank = _asset_rank(match.group(2))
        by_paragraph.setdefault(paragraph, []).append({
            "file": img.name,
            "rank": rank,
            "url": asset_url(topic, ASSETS_DIRNAME, img.name),
        })
    for shots in by_paragraph.values():
        shots.sort(key=lambda s: s["rank"])
    return dict(sorted(by_paragraph.items()))


def get_topic_detail(topic: str, pairing_overrides: dict[str, int] | None = None) -> dict:
    """Return the full Big Conversation working page for one topic: the
    drafted piece's headline + paragraphs, each paragraph's paired
    screenshots (with any drag-drop overrides applied), and the viral /
    T1 / T2 / T3 pools.

    `pairing_overrides` is {filename: paragraph_index}, loaded by the
    caller from FW's own DB (flatwhite.dashboard.state.load_pairing_overrides)
    — this module never persists anything itself; it only applies
    overrides handed to it, keeping filesystem reads and DB writes cleanly
    separated.

    Soft-fails when the topic isn't processed yet (no piece markdown, or
    no screenshots parsed from its assets folder): returns
    {"processed": False, "topic": topic, "pools": {...}} so the UI can show
    a "waiting for the skill to run" state instead of an error.
    """
    pairing_overrides = pairing_overrides or {}
    pools = list_pool_screenshots(topic)
    md_path = find_piece_markdown(topic)
    by_paragraph = list_paragraph_screenshots(topic)

    if md_path is None or not by_paragraph:
        return {"processed": False, "topic": topic, "pools": pools}

    # Parsed before regrouping so paragraph_count is available to bounds-check
    # overrides below (an override targeting a paragraph that doesn't exist
    # must not be able to silently disappear a screenshot from the response).
    parsed = parse_piece_markdown(md_path.read_text(encoding="utf-8", errors="replace"))
    paragraph_count = len(parsed["paragraphs"])

    if pairing_overrides:
        regrouped: dict[int, list[dict]] = {}
        for paragraph, shots in by_paragraph.items():
            for shot in shots:
                target = pairing_overrides.get(shot["file"], paragraph)
                if not (1 <= target <= paragraph_count):
                    # Stale or out-of-range override (piece reprocessed with a
                    # different paragraph count, or a bad index from the
                    # drag-drop UI): treat it as "no override for this shot",
                    # not "delete this shot" - fall back to its own paragraph.
                    target = paragraph
                regrouped.setdefault(target, []).append(shot)
        by_paragraph = regrouped

    paragraphs = [
        {"index": i, "text": text, "screenshots": by_paragraph.get(i, [])}
        for i, text in enumerate(parsed["paragraphs"], start=1)
    ]

    return {
        "processed": True,
        "topic": topic,
        "headline": parsed["headline"],
        "paragraphs": paragraphs,
        "pools": pools,
    }


def resolve_asset_path(rel_path: str) -> Path | None:
    """Resolve a `/api/big-conversation/assets/<rel_path>` request to a real
    file strictly inside INSTAGRAM_OUTPUT_DIR.

    Returns None (the caller responds 404) if: the Instagram output root is
    absent; `rel_path` is empty or absolute (an absolute path would make
    `root / rel_path` ignore `root` entirely - pathlib's own join
    behaviour); the resolved path escapes the root (covers `..` segments
    and symlinks that point outside); the extension isn't an allowed image
    type; or the file doesn't exist.
    """
    root = INSTAGRAM_OUTPUT_DIR
    if not root.is_dir():
        return None
    if not rel_path or Path(rel_path).is_absolute():
        return None
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / rel_path).resolve()
    except Exception:
        # This function's entire contract is "never raise for hostile or
        # malformed input, only return None". Path.resolve() can raise more
        # than OSError: embedded null bytes raise ValueError, symlink loops
        # raise RuntimeError, and pathlib has changed which exception it
        # raises for edge cases across Python versions before. A narrow
        # except list has to be kept in sync with pathlib's behaviour
        # forever to hold that contract; a blanket catch here is the
        # correct level of defensiveness for a security boundary that must
        # degrade to "reject the request" rather than "crash the server".
        return None
    if not candidate.is_relative_to(root_resolved):
        return None
    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    if not candidate.is_file():
        return None
    return candidate
