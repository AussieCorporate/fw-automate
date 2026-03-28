# Big Conversation Top AU News Scraper — Design Spec

## Goal

Add 5 guaranteed top-of-week Australian business/economic news items to the Big Conversation candidate pool by running a dedicated broad-query Google News scraper that inserts directly as `big_conversation_seed` items, bypassing the classifier.

## Architecture

A new `google_news_top_au.py` module runs 5 broad AU business queries against Google News RSS, deduplicates results, takes the first 5 unique items, inserts them as `raw_items`, then inserts them directly into `curated_items` as `big_conversation_seed` (bypassing the classifier). A new `insert_curated_item()` function is added to `db.py` since it does not exist. A new `big_conversation` section is added to `_SECTION_RUNNERS` in `api.py`. The frontend `runBigConv()` switches from calling `section: "finds"` to `section: "big_conversation"`.

## Tech Stack

Python/FastAPI, SQLite via `flatwhite/db.py`, Vanilla JS SPA (`flatwhite/dashboard/static/index.html`), Google News RSS (same feed URL pattern as `google_news_editorial.py`)

---

## Problem

Big Conversation candidates currently come only from the `finds` classifier pipeline. Items only land in the pool if:
1. They match one of the 13 narrow editorial queries (Big 4 hiring, law firm, ASIC, etc.)
2. AND the AI classifier tags them `big_conversation_seed`

Major stories (RBA decisions, federal budget, large corporate collapses, ASX movements) that don't match those 13 queries are never scraped at all. The user needs a guaranteed set of the week's most prominent AU corporate/economic stories in the pool regardless of classifier judgement.

---

## New Queries

```python
TOP_AU_NEWS_QUERIES = [
    "australia business news",
    "australia economy news",
    "australia corporate news",
    "ASX news australia",
    "australia banking finance news",
]
```

Top 3 results per query (same pattern as `google_news_editorial.py`) → up to 15 raw items → deduplicated by URL → first 5 unique items kept.

---

## Direct Insertion as big_conversation_seed

The top 5 items are inserted into `curated_items` with:
- `section = "big_conversation_seed"`
- `summary` = article body truncated to 300 chars, falling back to title
- All 5 score columns = 4 (range is 1–5; 4 = solid but not dominating — classified items scored 4.5+ by the classifier will still rank above them)
- `weighted_composite = 4.0`
- `confidence_tag = "yellow"` (signal that this is auto-seeded, not AI-classified)

If a top-news raw_item has already been classified by the classifier (same URL deduplication via `UNIQUE(title, source, week_iso)`), the `INSERT OR IGNORE` on `curated_items` is used to avoid conflict.

---

## insert_curated_item() in db.py

New function:

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
```

Uses `INSERT OR IGNORE` to avoid UNIQUE constraint conflict on `raw_item_id`. Returns the inserted `id` or `None` if already exists.

---

## _SECTION_RUNNERS addition

```python
"big_conversation": [
    ("Reddit RSS",      lambda: pull_reddit_editorial()),
    ("Google News",     lambda: pull_google_news_editorial()),
    ("Top AU news",     lambda: pull_google_news_top_au()),
    ("Classify",        lambda: classify_all_unclassified()),
],
```

`pull_google_news_top_au()` runs after the editorial scrapers so newly inserted raw_items from Reddit/Google News editorial are available. The classifier step follows and handles everything. Top-news items that were already inserted into `curated_items` by `pull_google_news_top_au()` will be safely skipped by the classifier (UNIQUE constraint + classifier's existing existence check).

---

## Frontend change

`runBigConv()` currently calls `/api/run-section` with `section: "finds"`. Change to `section: "big_conversation"`.

---

## Self-Review

**Spec coverage:**
- Top 5 AU news items guaranteed in pool: ✅ (direct insert, bypasses classifier)
- Broad queries covering A (top business news) + B (editorial-adjacent prominence): ✅
- No disruption to existing finds/editorial pipeline: ✅ (big_conversation is a separate section)
- Classifier still handles Reddit + editorial Google News items: ✅

**Placeholders:** None.

**Ambiguity resolved:**
- "Top 5" = first 5 unique deduplicated results from the 5 queries (Google orders by relevance/recency)
- Composite score 4.0 = visible in list, does not dominate over well-classified items
- `confidence_tag = "yellow"` marks auto-seeded items for future reference; UI does not currently filter by this field
