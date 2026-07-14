"""Tests for flatwhite/dashboard/big_conversation_bank.py — the read-only
filesystem layer over the Instagram DM screenshotter's output/ folder.

No real Claude/network calls: every test builds a fake directory tree
under tmp_path and monkeypatches
big_conversation_bank.INSTAGRAM_OUTPUT_DIR to point at it. The real
Instagram project directory is never read by these tests.
"""
from __future__ import annotations

from pathlib import Path

import flatwhite.dashboard.big_conversation_bank as bcb


def _make_topic(root: Path, name: str, n_pngs: int = 3, processed: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True)
    for i in range(n_pngs):
        (d / f"Person_{i}.png").write_bytes(b"fake")
    if processed:
        assets = d / bcb.ASSETS_DIRNAME
        assets.mkdir()
        (assets / "p1_1_Person_0.png").write_bytes(b"fake")
    return d


def test_list_topic_folders_returns_empty_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path / "does-not-exist")
    assert bcb.list_topic_folders() == []


def test_list_topic_folders_excludes_junk_and_utility_names(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office")
    _make_topic(tmp_path, "Rubbish")
    _make_topic(tmp_path, "MISC Stand alone")
    _make_topic(tmp_path, "Redundancies & Breaking News")
    _make_topic(tmp_path, "untitled folder")
    _make_topic(tmp_path, "DONE - Office Shoes")
    _make_topic(tmp_path, "INCOMPLETE - Office Attendance Bonus")
    (tmp_path / "_work").mkdir()
    (tmp_path / "_SPILLOVER hold").mkdir()

    names = {t["topic"] for t in bcb.list_topic_folders()}
    assert names == {"Kids in the Office"}


def test_list_topic_folders_counts_replies_and_processed_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office", n_pngs=5, processed=True)
    _make_topic(tmp_path, "Career Pivoting", n_pngs=8, processed=False)

    topics = {t["topic"]: t for t in bcb.list_topic_folders()}
    # The extra PNG copied into _BIG_CONVERSATION_assets must not be
    # double-counted as a separate submission.
    assert topics["Kids in the Office"]["reply_count"] == 5
    assert topics["Kids in the Office"]["processed"] is True
    assert topics["Career Pivoting"]["reply_count"] == 8
    assert topics["Career Pivoting"]["processed"] is False


def test_list_topic_folders_ignores_files_at_output_root(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office")
    (tmp_path / "_KIDS_OFFICE_BIG_CONVERSATION.md").write_text("piece text")
    (tmp_path / "_sort_session12_manifest.tsv").write_text("tsv")

    names = {t["topic"] for t in bcb.list_topic_folders()}
    assert names == {"Kids in the Office"}


def test_count_images_excludes_curated_pointer_subfolder(tmp_path, monkeypatch):
    """Reproduces the real "Kids in the Office" / "Pay Negotiation" pattern
    that inflated 5 real root replies to a count of 121: a topic's tier
    folders hold the real, sorted originals, and a "🔥"-prefixed folder
    (RED HOT / Top Picks) holds RENAMED COPIES of a subset of those
    originals, not new submissions. Naive recursive counting minus only
    _BIG_CONVERSATION_assets double-counts every file the 🔥 folder copies.
    """
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    topic = _make_topic(tmp_path, "Kids in the Office", n_pngs=5)

    tier1 = topic / "Tier 1 - Viral"
    tier1.mkdir()
    (tier1 / "Person_A.png").write_bytes(b"fake")
    (tier1 / "Person_B.png").write_bytes(b"fake")

    tier2 = topic / "Tier 2 - Strong"
    tier2.mkdir()
    (tier2 / "Person_C.png").write_bytes(b"fake")

    # RED HOT is a renamed copy of a subset of the tier files above (real
    # curated folders rename with a rank prefix + descriptive slug, e.g.
    # "1_Kimberly_Roberts_silence-tactic.png" copying "Kimberly_Roberts_0002.png"
    # from a tier folder) - not a new, original submission.
    redhot = topic / "\U0001F525 RED HOT Top 2"
    redhot.mkdir()
    (redhot / "1_Person_A_wtf-quote.png").write_bytes(b"fake")
    (redhot / "2_Person_C_wtf-quote.png").write_bytes(b"fake")

    topics = {t["topic"]: t for t in bcb.list_topic_folders()}
    # 5 root (unsorted) + 2 Tier 1 + 1 Tier 2 = 8 true originals. RED HOT's
    # 2 renamed copies must not add to that.
    assert topics["Kids in the Office"]["reply_count"] == 8


def test_count_images_excludes_any_underscore_prefixed_subfolder(tmp_path, monkeypatch):
    """Reproduces the real "Visa vs Resident Pay" topic, which has an
    "_EDITORIAL screenshots" subfolder (paragraph-mapped copies made by the
    big-conversation skill, same idea as _BIG_CONVERSATION_assets but a
    different underscore-prefixed name). The exclusion must generalise to
    ANY underscore-prefixed subfolder, not just the literal ASSETS_DIRNAME
    string.
    """
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    topic = _make_topic(tmp_path, "Visa vs Resident Pay", n_pngs=9)

    editorial = topic / "_EDITORIAL screenshots"
    editorial.mkdir()
    (editorial / "1_HERO_Person_A.png").write_bytes(b"fake")

    topics = {t["topic"]: t for t in bcb.list_topic_folders()}
    assert topics["Visa vs Resident Pay"]["reply_count"] == 9


def test_list_topic_folders_skips_topic_that_raises_on_count(tmp_path, monkeypatch):
    """The module's docstring claims every public function fails soft. If
    counting one specific topic folder raises (e.g. PermissionError), that
    topic must be skipped, not propagate and crash the whole listing for
    every other topic.
    """
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    _make_topic(tmp_path, "Kids in the Office", n_pngs=5)
    _make_topic(tmp_path, "Career Pivoting", n_pngs=8)

    real_rglob = Path.rglob

    def flaky_rglob(self, pattern):
        if self.name == "Career Pivoting":
            raise PermissionError("simulated permission error")
        return real_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", flaky_rglob)

    topics = {t["topic"]: t for t in bcb.list_topic_folders()}
    assert "Career Pivoting" not in topics
    assert topics["Kids in the Office"]["reply_count"] == 5


def test_list_topic_folders_returns_empty_when_root_iterdir_raises(tmp_path, monkeypatch):
    """Same fail-soft contract at the root level: if the root itself can't
    be listed (e.g. PermissionError), return [] rather than raising.
    """
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)

    real_iterdir = Path.iterdir

    def flaky_iterdir(self):
        if self == tmp_path:
            raise PermissionError("simulated permission error")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", flaky_iterdir)

    assert bcb.list_topic_folders() == []


def test_classify_tier_folder_recognises_current_and_future_names():
    # Current real folder names (before increment 3's sort skill rebuild).
    assert bcb.classify_tier_folder("\U0001F525 RED HOT Top 22") == "viral"
    assert bcb.classify_tier_folder("Tier 1 - Viral") == "T1"
    assert bcb.classify_tier_folder("Tier 2 - Strong") == "T2"
    assert bcb.classify_tier_folder("Tier 3 - Ordinary") == "T3"
    assert bcb.classify_tier_folder("Tier 4 - Rubbish") is None
    # Names increment 3's rebuilt sort skill is expected to use.
    assert bcb.classify_tier_folder("VIRAL EXTREME") == "viral"
    assert bcb.classify_tier_folder("T1") == "T1"
    assert bcb.classify_tier_folder("T2") == "T2"
    assert bcb.classify_tier_folder("T3") == "T3"
    # Not a tier folder at all.
    assert bcb.classify_tier_folder("_EDITORIAL screenshots") is None
    assert bcb.classify_tier_folder("_BIG_CONVERSATION_assets") is None


def test_list_pool_screenshots_groups_by_bucket_and_drops_tier4(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    topic = tmp_path / "Kids in the Office"
    (topic / "\U0001F525 RED HOT Top 22").mkdir(parents=True)
    (topic / "\U0001F525 RED HOT Top 22" / "Erin_Lou_0001.png").write_bytes(b"x")
    (topic / "Tier 1 - Viral").mkdir()
    (topic / "Tier 1 - Viral" / "Someone_0001.png").write_bytes(b"x")
    (topic / "Tier 4 - Rubbish").mkdir()
    (topic / "Tier 4 - Rubbish" / "Junk_0001.png").write_bytes(b"x")

    pools = bcb.list_pool_screenshots("Kids in the Office")
    assert [s["file"] for s in pools["viral"]] == ["Erin_Lou_0001.png"]
    assert [s["file"] for s in pools["T1"]] == ["Someone_0001.png"]
    assert pools["T2"] == []
    assert pools["T3"] == []
    all_files = [s["file"] for shots in pools.values() for s in shots]
    assert "Junk_0001.png" not in all_files


def test_list_pool_screenshots_urls_point_at_the_asset_route(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    topic = tmp_path / "Kids in the Office"
    (topic / "Tier 1 - Viral").mkdir(parents=True)
    (topic / "Tier 1 - Viral" / "Someone_0001.png").write_bytes(b"x")

    pools = bcb.list_pool_screenshots("Kids in the Office")
    assert pools["T1"][0]["url"] == (
        "/api/big-conversation/assets/Kids%20in%20the%20Office/Tier%201%20-%20Viral/Someone_0001.png"
    )


def test_list_pool_screenshots_empty_when_topic_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb, "INSTAGRAM_OUTPUT_DIR", tmp_path)
    pools = bcb.list_pool_screenshots("Nonexistent Topic")
    assert pools == {"viral": [], "T1": [], "T2": [], "T3": []}
