# Big Conversation Top AU News Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 guaranteed top-of-week Australian business/economic news items to the Big Conversation candidate pool by running a dedicated broad-query Google News scraper that inserts directly as `big_conversation_seed` candidates.

**Architecture:** New `google_news_top_au.py` scraper runs 5 broad AU queries, deduplicates, takes first 5 unique items, inserts as `raw_items` + directly into `curated_items` as `big_conversation_seed`. A new `insert_curated_item()` DB function is needed (does not exist). A new `big_conversation` entry in `_SECTION_RUNNERS` wires the steps together. The frontend `runBigConv()` switches from polling `finds` to polling `big_conversation`.

**Tech Stack:** Python, SQLite via `flatwhite/db.py`, FastAPI `flatwhite/dashboard/api.py`, Vanilla JS `flatwhite/dashboard/static/index.html`

---

## File Map

| File | Change |
|------|--------|
| `flatwhite/db.py` | Add `insert_curated_item()` after line 620 |
| `flatwhite/editorial/google_news_top_au.py` | New — `pull_google_news_top_au()` scraper |
| `flatwhite/dashboard/api.py` | Add `"big_conversation"` to `_SECTION_RUNNERS` (after line 1038) |
| `flatwhite/dashboard/static/index.html` | Update `runBigConv()` lines 828 + 834 |
| `tests/test_insert_curated_item.py` | New — tests for `insert_curated_item()` |
| `tests/test_google_news_top_au.py` | New — tests for `pull_google_news_top_au()` |

---

## Task 1: DB — insert_curated_item()

**Files:**
- Modify: `flatwhite/db.py` (after line 620)
- Create: `tests/test_insert_curated_item.py`

**Background:** `curated_items` has a UNIQUE constraint on `raw_item_id`. The new function must use `INSERT OR IGNORE` to safely skip duplicates. The classifier already checks for existence before inserting, so this is safe to call from the scraper.

- [ ] **Step 1: Write failing tests**

Create `tests/test_insert_curated_item.py`:

```python
"""Tests for insert_curated_item DB function."""
from pathlib import Path
from unittest.mock import patch
import pytest
import flatwhite.db as db_module


@pytest.fixture
def ci_db(tmp_path: Path):
    db_path = tmp_path / "ci_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def _insert_raw(db_path, title, url, week_iso="2026-W13"):
    with patch.object(db_module, "DB_PATH", db_path):
        conn = db_module.get_connection()
        conn.execute(
            "INSERT INTO raw_items (title, source, url, lane, pulled_at, week_iso) "
            "VALUES (?, 'google_news_top_au', ?, 'editorial', datetime('now'), ?)",
            (title, url, week_iso),
        )
        conn.commit()
        raw_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return raw_id


def test_insert_curated_item_basic(ci_db):
    raw_id = _insert_raw(ci_db, "RBA raises rates", "https://abc.net.au/rba")
    with patch.object(db_module, "DB_PATH", ci_db):
        curated_id = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="RBA raises cash rate by 25bp.",
            score_relevance=4,
            score_novelty=4,
            score_reliability=4,
            score_tension=4,
            score_usefulness=4,
            weighted_composite=4.0,
            confidence_tag="yellow",
        )
        assert curated_id is not None
        conn = db_module.get_connection()
        row = conn.execute(
            "SELECT section, summary, weighted_composite, confidence_tag FROM curated_items WHERE id = ?",
            (curated_id,),
        ).fetchone()
        conn.close()
        assert row["section"] == "big_conversation_seed"
        assert row["weighted_composite"] == 4.0
        assert row["confidence_tag"] == "yellow"


def test_insert_curated_item_duplicate_returns_none(ci_db):
    raw_id = _insert_raw(ci_db, "ASX drops", "https://afr.com/asx")
    with patch.object(db_module, "DB_PATH", ci_db):
        first = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="ASX drops 2%.",
            score_relevance=4, score_novelty=4, score_reliability=4,
            score_tension=4, score_usefulness=4, weighted_composite=4.0,
        )
        second = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="ASX drops 2%.",
            score_relevance=4, score_novelty=4, score_reliability=4,
            score_tension=4, score_usefulness=4, weighted_composite=4.0,
        )
        assert first is not None
        assert second is None  # duplicate — INSERT OR IGNORE


def test_insert_curated_item_without_confidence_tag(ci_db):
    raw_id = _insert_raw(ci_db, "Budget surplus", "https://abc.net.au/budget")
    with patch.object(db_module, "DB_PATH", ci_db):
        curated_id = db_module.insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary="Government announces surplus.",
            score_relevance=4, score_novelty=4, score_reliability=4,
            score_tension=4, score_usefulness=4, weighted_composite=4.0,
        )
        assert curated_id is not None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_insert_curated_item.py -v 2>&1 | tail -10
```

Expected: 3 FAIL — `AttributeError: module 'flatwhite.db' has no attribute 'insert_curated_item'`

- [ ] **Step 3: Add insert_curated_item() to db.py**

In `flatwhite/db.py`, find the end of `update_raw_item_engagement` (around line 620). Add the new function immediately after it (before `update_draft_status`):

```python
def insert_curated_item(
    raw_item_id: int,
    section: str,
    summary: str,
    score_relevance: int,
    score_novelty: int,
    score_reliability: int,
    score_tension: int,
    score_usefulness: int,
    weighted_composite: float,
    confidence_tag: str | None = None,
    tags: str | None = None,
) -> int | None:
    """Insert a curated item, ignoring duplicates. Returns inserted id or None if already exists."""
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO curated_items
           (raw_item_id, section, summary, score_relevance, score_novelty,
            score_reliability, score_tension, score_usefulness, weighted_composite,
            confidence_tag, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (raw_item_id, section, summary, score_relevance, score_novelty,
         score_reliability, score_tension, score_usefulness, weighted_composite,
         confidence_tag, tags),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM curated_items WHERE raw_item_id = ?", (raw_item_id,)
    ).fetchone()
    # If INSERT OR IGNORE skipped (duplicate), row still exists — return None to signal no-op
    inserted_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    # last_insert_rowid() returns 0 if INSERT was ignored
    return inserted_id if inserted_id else None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_insert_curated_item.py -v 2>&1 | tail -10
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/db.py tests/test_insert_curated_item.py && git commit -m "feat: add insert_curated_item() to db"
```

---

## Task 2: New scraper — google_news_top_au.py

**Files:**
- Create: `flatwhite/editorial/google_news_top_au.py`
- Create: `tests/test_google_news_top_au.py`

**Background:** Mirrors `google_news_editorial.py` in structure. Runs 5 broad AU business queries, takes top 3 per query, deduplicates by URL, keeps first 5 unique, inserts each as a `raw_item` then directly as a `curated_item` with `section="big_conversation_seed"` and fixed scores of 4.

- [ ] **Step 1: Write failing tests**

Create `tests/test_google_news_top_au.py`:

```python
"""Tests for pull_google_news_top_au scraper."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import flatwhite.db as db_module
import flatwhite.editorial.google_news_top_au as top_au_module


@pytest.fixture
def top_db(tmp_path: Path):
    db_path = tmp_path / "top_au_test.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


def _fake_entries(n=3, prefix="Story"):
    return [
        {
            "title": f"{prefix} {i}",
            "body": f"Body of story {i}",
            "url": f"https://example.com/story-{prefix}-{i}",
            "published": "",
        }
        for i in range(n)
    ]


def test_inserts_up_to_5_items(top_db):
    # 5 queries × 3 entries = 15 raw, but only 5 unique picked
    fake_fetch = MagicMock(return_value=_fake_entries(3))
    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", fake_fetch):
        count = top_au_module.pull_google_news_top_au()
    assert count == 5


def test_deduplicates_by_url(top_db):
    # All queries return the same 3 entries — only 3 unique URLs total
    same_entries = _fake_entries(3, prefix="Same")
    fake_fetch = MagicMock(return_value=same_entries)
    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", fake_fetch):
        count = top_au_module.pull_google_news_top_au()
    assert count == 3  # capped at unique URLs (3 here)


def test_items_inserted_as_big_conversation_seed(top_db):
    fake_fetch = MagicMock(return_value=_fake_entries(3))
    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", fake_fetch):
        top_au_module.pull_google_news_top_au()
    with patch.object(db_module, "DB_PATH", top_db):
        conn = db_module.get_connection()
        rows = conn.execute(
            "SELECT section, confidence_tag FROM curated_items"
        ).fetchall()
        conn.close()
    assert all(r["section"] == "big_conversation_seed" for r in rows)
    assert all(r["confidence_tag"] == "yellow" for r in rows)


def test_fetch_error_on_one_query_does_not_abort(top_db):
    # First query raises, rest succeed
    def side_effect(url, **kwargs):
        if "australia+business+news" in url:
            raise Exception("network error")
        return _fake_entries(3, prefix="Ok")

    with patch.object(db_module, "DB_PATH", top_db), \
         patch.object(top_au_module, "fetch_rss", side_effect=side_effect):
        count = top_au_module.pull_google_news_top_au()
    assert count > 0  # at least some items from other queries
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_google_news_top_au.py -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError: No module named 'flatwhite.editorial.google_news_top_au'`

- [ ] **Step 3: Create google_news_top_au.py**

Create `flatwhite/editorial/google_news_top_au.py`:

```python
"""Scraper: top Australian business/economic news for Big Conversation seeding.

Runs 5 broad AU-focused Google News queries, deduplicates by URL, keeps the
first 5 unique items, and inserts them directly as big_conversation_seed
curated items (bypassing the classifier).
"""
from urllib.parse import quote
from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, insert_curated_item, get_current_week_iso

TOP_AU_NEWS_QUERIES = [
    "australia business news",
    "australia economy news",
    "australia corporate news",
    "ASX news australia",
    "australia banking finance news",
]

MAX_ITEMS = 5
RESULTS_PER_QUERY = 3
_FIXED_SCORES = dict(
    score_relevance=4,
    score_novelty=4,
    score_reliability=4,
    score_tension=4,
    score_usefulness=4,
    weighted_composite=4.0,
    confidence_tag="yellow",
)


def pull_google_news_top_au() -> int:
    """Fetch top AU news items and seed them directly as big_conversation_seed candidates.

    Returns the number of items successfully inserted into curated_items.
    """
    week_iso = get_current_week_iso()
    seen_urls: set[str] = set()
    candidates: list[dict] = []

    for query in TOP_AU_NEWS_QUERIES:
        if len(candidates) >= MAX_ITEMS:
            break
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
        try:
            entries = fetch_rss(url, delay_seconds=2.0)
            for entry in entries[:RESULTS_PER_QUERY]:
                item_url = entry.get("url", "")
                if item_url in seen_urls:
                    continue
                seen_urls.add(item_url)
                candidates.append(entry)
                if len(candidates) >= MAX_ITEMS:
                    break
        except Exception:
            continue

    inserted = 0
    for entry in candidates:
        body = entry.get("body") or ""
        summary = body[:300].strip() if body else (entry.get("title", "")[:300])
        raw_id = insert_raw_item(
            title=entry["title"],
            body=body[:2000] if body else None,
            source="google_news_top_au",
            url=entry.get("url"),
            lane="editorial",
            subreddit=None,
            week_iso=week_iso,
        )
        if raw_id is None:
            continue
        result = insert_curated_item(
            raw_item_id=raw_id,
            section="big_conversation_seed",
            summary=summary or entry["title"][:300],
            **_FIXED_SCORES,
        )
        if result is not None:
            inserted += 1

    return inserted
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_google_news_top_au.py -v 2>&1 | tail -10
```

Expected: 4 PASSED

- [ ] **Step 5: Check insert_raw_item return value**

`insert_raw_item` might return `None` on duplicate (INSERT OR IGNORE). Verify by reading `flatwhite/db.py` — search for `def insert_raw_item`. If it returns the row `id` or `None`, the Task 2 code is correct. If it returns a count or raises, adjust accordingly.

```bash
grep -n "def insert_raw_item" /Users/victornguyen/Documents/MISC/FW/flatwhite/db.py
```

Then read that function and confirm its return value. If it returns `None` on duplicate, the `if raw_id is None: continue` guard in `pull_google_news_top_au` is correct.

- [ ] **Step 6: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/editorial/google_news_top_au.py tests/test_google_news_top_au.py && git commit -m "feat: google_news_top_au scraper for big conversation seeding"
```

---

## Task 3: API — big_conversation section runner

**Files:**
- Modify: `flatwhite/dashboard/api.py` (after line 1038)

- [ ] **Step 1: Add big_conversation to _SECTION_RUNNERS**

In `flatwhite/dashboard/api.py`, find the closing `}` of `_SECTION_RUNNERS` at line 1038. Add a new entry before the closing brace:

```python
    "big_conversation": [
        ("Reddit RSS",    lambda: __import__("flatwhite.editorial.reddit_rss",              fromlist=["pull_reddit_editorial"]).pull_reddit_editorial()),
        ("Google News",   lambda: __import__("flatwhite.editorial.google_news_editorial",   fromlist=["pull_google_news_editorial"]).pull_google_news_editorial()),
        ("Top AU news",   lambda: __import__("flatwhite.editorial.google_news_top_au",      fromlist=["pull_google_news_top_au"]).pull_google_news_top_au()),
        ("Classify",      lambda: __import__("flatwhite.classify.classifier",               fromlist=["classify_all_unclassified"]).classify_all_unclassified()),
    ],
```

Insert this immediately before the closing `}` of `_SECTION_RUNNERS`.

- [ ] **Step 2: Verify import works**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -c "from flatwhite.dashboard.api import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify big_conversation is in the runners**

```bash
python -c "
from flatwhite.dashboard.api import _SECTION_RUNNERS
print('big_conversation' in _SECTION_RUNNERS)
print([step[0] for step in _SECTION_RUNNERS['big_conversation']])
"
```

Expected:
```
True
['Reddit RSS', 'Google News', 'Top AU news', 'Classify']
```

- [ ] **Step 4: Run existing tests**

```bash
cd /Users/victornguyen/Documents/MISC/FW && python -m pytest tests/test_section_outputs.py tests/test_engagement_update.py tests/test_insert_curated_item.py tests/test_google_news_top_au.py -v 2>&1 | tail -15
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/api.py && git commit -m "feat: add big_conversation section runner with top AU news step"
```

---

## Task 4: Frontend — update runBigConv() to use big_conversation section

**Files:**
- Modify: `flatwhite/dashboard/static/index.html` (lines 828, 834)

Two string changes in `runBigConv()`:
1. Change `section: "finds"` → `section: "big_conversation"` in the `/api/run-section` call
2. Change `/api/section-status/finds` → `/api/section-status/big_conversation"` in the poll URL

- [ ] **Step 1: Update runBigConv()**

Find in `flatwhite/dashboard/static/index.html`:
```js
  api("/api/run-section", { method: "POST", body: { section: "finds" } })
```
Replace with:
```js
  api("/api/run-section", { method: "POST", body: { section: "big_conversation" } })
```

Then find:
```js
        fetch("/api/section-status/finds").then(function(r) { return r.json(); }).then(function(st) {
```
Replace with:
```js
        fetch("/api/section-status/big_conversation").then(function(r) { return r.json(); }).then(function(st) {
```

Also update the toast message on line 831 for clarity:
```js
      showToast("Pulling editorial sources for Big Conversation...");
```
Replace with:
```js
      showToast("Pulling Big Conversation sources (incl. top AU news)...");
```

- [ ] **Step 2: Verify**

```bash
grep -n "section.*finds\|section-status/finds" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html | grep -i "bigconv\|runBigConv\|big_conv"
```

Better check — confirm `big_conversation` appears in `runBigConv`:
```bash
grep -n "big_conversation" /Users/victornguyen/Documents/MISC/FW/flatwhite/dashboard/static/index.html | grep -E "run-section|section-status"
```

Expected: 2 hits — the `/api/run-section` call and the `/api/section-status/` poll URL.

- [ ] **Step 3: Commit**

```bash
cd /Users/victornguyen/Documents/MISC/FW && git add flatwhite/dashboard/static/index.html && git commit -m "feat: runBigConv() uses dedicated big_conversation section runner"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|-------------|------|
| 5 broad top AU news queries | Task 2 |
| Deduplication by URL, keep first 5 | Task 2 |
| Direct insert as `big_conversation_seed` | Tasks 1 + 2 |
| `insert_curated_item()` with INSERT OR IGNORE | Task 1 |
| `big_conversation` section in `_SECTION_RUNNERS` | Task 3 |
| Frontend polls `big_conversation` not `finds` | Task 4 |

### Placeholder scan

None — all steps have complete code.

### Type consistency

- `insert_curated_item(raw_item_id, section, summary, score_relevance, ..., confidence_tag, tags)` — signature defined in Task 1, called in Task 2 via `**_FIXED_SCORES` spread. `_FIXED_SCORES` keys match the parameter names exactly.
- `insert_raw_item()` return value check: Task 2 Step 5 explicitly verifies this before trusting the `if raw_id is None` guard.
- `_SECTION_RUNNERS["big_conversation"]` step labels: `"Reddit RSS"`, `"Google News"`, `"Top AU news"`, `"Classify"` — consistent with how other sections name their steps.
