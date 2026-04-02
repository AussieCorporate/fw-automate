# Off the Clock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Off the Clock" lifestyle section to the Flat White pipeline that auto-surfaces top 3 candidates per category (Eating, Watching, Reading, Wearing, Going) from lifestyle sources, classified by LLM, with editor pick UI on the dashboard.

**Architecture:** New `lane='lifestyle'` flows through the existing `raw_items` -> `curated_items` -> `editor_decisions` pipeline with OTC-prefixed sections. A new editorial module `off_the_clock.py` pulls from Broadsheet RSS, Google News lifestyle queries, and Reddit lifestyle subreddits. A dedicated OTC classifier prompt scores on trendiness + shareability. Dashboard gets a new "Off the Clock" tab with pick-one-per-category UI.

**Tech Stack:** Python, SQLite, FastAPI, Gemini 2.5 Flash (classification), vanilla HTML/JS dashboard

---

### Task 1: Database Schema Changes

**Files:**
- Modify: `flatwhite/db.py:14` (raw_items lane CHECK), `flatwhite/db.py:63` (curated_items section CHECK), `flatwhite/db.py:189` (drafts section CHECK)
- Modify: `flatwhite/db.py:210-326` (migrate_db function)

- [ ] **Step 1: Update the raw_items lane CHECK constraint in SCHEMA_SQL**

In `flatwhite/db.py`, the `raw_items` CREATE TABLE has:
```python
lane TEXT NOT NULL CHECK (lane IN ('pulse', 'editorial')),
```
Change to:
```python
lane TEXT NOT NULL CHECK (lane IN ('pulse', 'editorial', 'lifestyle')),
```

- [ ] **Step 2: Update the curated_items section CHECK constraint in SCHEMA_SQL**

In `flatwhite/db.py`, the `curated_items` CREATE TABLE has:
```python
section TEXT NOT NULL CHECK (section IN (
    'whisper', 'big_conversation_seed', 'what_we_watching',
    'thread_candidate', 'finds', 'discard'
)),
```
Change to:
```python
section TEXT NOT NULL CHECK (section IN (
    'whisper', 'big_conversation_seed', 'what_we_watching',
    'thread_candidate', 'finds', 'discard',
    'otc_eating', 'otc_watching', 'otc_reading', 'otc_wearing', 'otc_going'
)),
```

- [ ] **Step 3: Update the drafts section CHECK constraint in SCHEMA_SQL**

In `flatwhite/db.py`, the `drafts` CREATE TABLE has:
```python
section TEXT NOT NULL CHECK (section IN ('big_conversation', 'hook', 'custom')),
```
Change to:
```python
section TEXT NOT NULL CHECK (section IN ('big_conversation', 'hook', 'custom', 'off_the_clock')),
```

- [ ] **Step 4: Add lifestyle_category column migration in migrate_db()**

Add to the `simple_migrations` list in `migrate_db()`:
```python
"ALTER TABLE raw_items ADD COLUMN lifestyle_category TEXT",
```

- [ ] **Step 5: Add migration to recreate raw_items with expanded lane CHECK**

SQLite cannot ALTER CHECK constraints. Add a migration block to `migrate_db()` that recreates the `raw_items` table with the new lane CHECK, similar to the existing `employer_watchlist` v2 migration pattern. Place this after the simple_migrations block:

```python
# v3 raw_items: expand lane CHECK to include 'lifestyle'
# Only runs if lifestyle_category column was just added (first migration)
# Check if the CHECK constraint allows 'lifestyle' by attempting a test
try:
    conn.execute(
        "INSERT INTO raw_items (title, body, source, url, lane, subreddit, pulled_at, week_iso) "
        "VALUES ('__test__', NULL, '__test__', NULL, 'lifestyle', NULL, datetime('now'), '__test__')"
    )
    # If it worked, clean up the test row
    conn.execute("DELETE FROM raw_items WHERE title = '__test__' AND source = '__test__'")
except sqlite3.IntegrityError:
    # CHECK constraint rejected 'lifestyle' — need to recreate table
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("""
        CREATE TABLE raw_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT,
            source TEXT NOT NULL,
            url TEXT,
            lane TEXT NOT NULL CHECK (lane IN ('pulse', 'editorial', 'lifestyle')),
            subreddit TEXT,
            pulled_at TEXT NOT NULL,
            week_iso TEXT NOT NULL,
            classified INTEGER NOT NULL DEFAULT 0,
            top_comments TEXT,
            post_score INTEGER,
            comment_engagement INTEGER,
            lifestyle_category TEXT,
            UNIQUE(title, source, week_iso)
        )
    """)
    conn.execute("""
        INSERT INTO raw_items_new
            (id, title, body, source, url, lane, subreddit, pulled_at, week_iso,
             classified, top_comments, post_score, comment_engagement, lifestyle_category)
        SELECT id, title, body, source, url, lane, subreddit, pulled_at, week_iso,
               classified, top_comments, post_score, comment_engagement, lifestyle_category
        FROM raw_items
    """)
    conn.execute("DROP TABLE raw_items")
    conn.execute("ALTER TABLE raw_items_new RENAME TO raw_items")
    conn.execute("PRAGMA foreign_keys=ON")
```

Similarly for `curated_items` to expand the section CHECK:
```python
# v3 curated_items: expand section CHECK to include OTC sections
try:
    conn.execute(
        "INSERT INTO curated_items (raw_item_id, section, summary, score_relevance, "
        "score_novelty, score_reliability, score_tension, score_usefulness, weighted_composite, tags) "
        "VALUES (0, 'otc_eating', '__test__', 1, 1, 1, 1, 1, 1.0, '[]')"
    )
    conn.execute("DELETE FROM curated_items WHERE summary = '__test__'")
except sqlite3.IntegrityError:
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("""
        CREATE TABLE curated_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_item_id INTEGER NOT NULL UNIQUE REFERENCES raw_items(id),
            section TEXT NOT NULL CHECK (section IN (
                'whisper', 'big_conversation_seed', 'what_we_watching',
                'thread_candidate', 'finds', 'discard',
                'otc_eating', 'otc_watching', 'otc_reading', 'otc_wearing', 'otc_going'
            )),
            summary TEXT NOT NULL,
            score_relevance INTEGER NOT NULL CHECK (score_relevance BETWEEN 1 AND 5),
            score_novelty INTEGER NOT NULL CHECK (score_novelty BETWEEN 1 AND 5),
            score_reliability INTEGER NOT NULL CHECK (score_reliability BETWEEN 1 AND 5),
            score_tension INTEGER NOT NULL CHECK (score_tension BETWEEN 1 AND 5),
            score_usefulness INTEGER NOT NULL CHECK (score_usefulness BETWEEN 1 AND 5),
            weighted_composite REAL NOT NULL,
            tags TEXT,
            confidence_tag TEXT CHECK (confidence_tag IN ('green', 'yellow', 'red')),
            our_take TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        INSERT INTO curated_items_new
            (id, raw_item_id, section, summary, score_relevance, score_novelty,
             score_reliability, score_tension, score_usefulness, weighted_composite,
             tags, confidence_tag, our_take, created_at)
        SELECT id, raw_item_id, section, summary, score_relevance, score_novelty,
               score_reliability, score_tension, score_usefulness, weighted_composite,
               tags, confidence_tag, our_take, created_at
        FROM curated_items
    """)
    conn.execute("DROP TABLE curated_items")
    conn.execute("ALTER TABLE curated_items_new RENAME TO curated_items")
    conn.execute("PRAGMA foreign_keys=ON")
```

- [ ] **Step 6: Test the migration**

Run: `python -c "from flatwhite.db import init_db; init_db(); print('OK')"`
Expected: `OK` (no errors)

Then verify the new lane works:
```bash
python -c "
from flatwhite.db import get_connection, init_db
init_db()
conn = get_connection()
conn.execute(\"INSERT INTO raw_items (title, source, url, lane, pulled_at, week_iso) VALUES ('test', 'test', NULL, 'lifestyle', datetime('now'), '2026-W13')\")
conn.execute(\"DELETE FROM raw_items WHERE title = 'test' AND source = 'test'\")
conn.commit()
conn.close()
print('lifestyle lane OK')
"
```
Expected: `lifestyle lane OK`

- [ ] **Step 7: Commit**

```bash
git add flatwhite/db.py
git commit -m "feat(db): add lifestyle lane and OTC sections to schema"
```

---

### Task 2: Config Block

**Files:**
- Modify: `config.yaml` (append `off_the_clock` block at end)

- [ ] **Step 1: Add the off_the_clock config block**

Append to the end of `config.yaml`:

```yaml
off_the_clock:
  enabled: true
  candidates_per_category: 3
  max_age_days: 30
  max_items_per_source: 10
  google_news_queries:
    eating:
      - "best new restaurant sydney"
      - "best new restaurant melbourne"
      - "new cafe opening sydney"
      - "new cafe opening melbourne"
    watching:
      - "best show streaming australia"
      - "netflix australia must watch"
      - "best new movie australia"
    reading:
      - "best article this week australia"
      - "must read book australia 2026"
      - "longform article australia"
    wearing:
      - "fashion drop australia"
      - "new collection australia"
      - "uniqlo australia"
    going:
      - "things to do sydney this week"
      - "things to do melbourne this week"
      - "exhibition opening sydney"
      - "exhibition opening melbourne"
  rss_feeds:
    - name: "Broadsheet Sydney Food"
      url: "https://www.broadsheet.com.au/sydney/food-and-drink/rss"
      category_hint: "eating"
      city: "sydney"
    - name: "Broadsheet Melbourne Food"
      url: "https://www.broadsheet.com.au/melbourne/food-and-drink/rss"
      category_hint: "eating"
      city: "melbourne"
    - name: "Broadsheet Sydney Events"
      url: "https://www.broadsheet.com.au/sydney/entertainment/rss"
      category_hint: "going"
      city: "sydney"
    - name: "Broadsheet Melbourne Events"
      url: "https://www.broadsheet.com.au/melbourne/entertainment/rss"
      category_hint: "going"
      city: "melbourne"
    - name: "Broadsheet Style"
      url: "https://www.broadsheet.com.au/national/style/rss"
      category_hint: "wearing"
      city: "national"
    - name: "Good Food"
      url: "https://www.goodfood.com.au/rss"
      category_hint: "eating"
      city: "national"
    - name: "Concrete Playground Sydney"
      url: "https://concreteplayground.com/sydney/feed"
      category_hint: null
      city: "sydney"
    - name: "Concrete Playground Melbourne"
      url: "https://concreteplayground.com/melbourne/feed"
      category_hint: null
      city: "melbourne"
  reddit_subreddits:
    - name: "sydney"
      url: "https://www.reddit.com/r/sydney/.rss"
      city: "sydney"
    - name: "melbourne"
      url: "https://www.reddit.com/r/melbourne/.rss"
      city: "melbourne"
    - name: "AustralianMFA"
      url: "https://www.reddit.com/r/AustralianMFA/.rss"
      city: "national"
      category_hint: "wearing"
  reddit_keyword_filters:
    eating: ["restaurant", "cafe", "food", "opened", "menu", "pasta", "ramen", "brunch", "dinner", "bar"]
    watching: ["netflix", "streaming", "show", "series", "movie", "film", "binge", "stan", "disney"]
    reading: ["book", "read", "article", "longread", "podcast", "newsletter"]
    wearing: ["fashion", "drop", "collection", "uniqlo", "clothing", "wear", "style", "sneaker"]
    going: ["event", "exhibition", "show", "festival", "pop-up", "gallery", "comedy", "gig", "market", "museum"]
```

- [ ] **Step 2: Verify config loads**

```bash
python -c "
import yaml
from pathlib import Path
config = yaml.safe_load(Path('config.yaml').read_text())
otc = config['off_the_clock']
print(f'Enabled: {otc[\"enabled\"]}')
print(f'Categories: {list(otc[\"google_news_queries\"].keys())}')
print(f'RSS feeds: {len(otc[\"rss_feeds\"])}')
print(f'Reddit subs: {len(otc[\"reddit_subreddits\"])}')
"
```
Expected:
```
Enabled: True
Categories: ['eating', 'watching', 'reading', 'wearing', 'going']
RSS feeds: 8
Reddit subs: 3
```

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "feat(config): add off_the_clock lifestyle section config"
```

---

### Task 3: Ingest Module

**Files:**
- Create: `flatwhite/editorial/off_the_clock.py`

- [ ] **Step 1: Create the off_the_clock.py module**

```python
"""Off the Clock lifestyle ingest — pulls content from Broadsheet, Google News,
Reddit, and other lifestyle sources across 5 categories: Eating, Watching,
Reading, Wearing, Going.

Each source is configured in config.yaml under off_the_clock. Items are
inserted into raw_items with lane='lifestyle' and lifestyle_category set
where determinable from config (category_hint or keyword match).

Follows the same pattern as rss_feeds.py: parallel fetch, per-source error
handling, returns total inserted count.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from flatwhite.utils.http import fetch_rss
from flatwhite.db import get_connection, get_current_week_iso
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import re

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

OTC_CATEGORIES = {"eating", "watching", "reading", "wearing", "going"}


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f).get("off_the_clock", {})


def _is_recent(entry: dict, max_age_days: int) -> bool:
    """Return True if the article was published within max_age_days, or has no date.

    Default max_age_days is 30 (one month). Lifestyle content must be topical
    but not necessarily breaking — a restaurant that opened 3 weeks ago is still
    a valid pick if people are still talking about it.
    """
    pub = entry.get("published", "")
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        return dt.replace(tzinfo=None) >= cutoff
    except Exception:
        return True


def _insert_lifestyle_item(
    title: str,
    body: str | None,
    source: str,
    url: str | None,
    city: str | None,
    category_hint: str | None,
    week_iso: str,
) -> int:
    """Insert a lifestyle item into raw_items with lane='lifestyle'.

    Uses the subreddit column to store city (sydney/melbourne/national).
    Sets lifestyle_category if a category_hint is provided.
    Returns the row id.
    """
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO raw_items
        (title, body, source, url, lane, subreddit, pulled_at, week_iso, lifestyle_category)
        VALUES (?, ?, ?, ?, 'lifestyle', ?, datetime('now'), ?, ?)""",
        (title, body, source, url, city, week_iso, category_hint),
    )
    conn.commit()
    row_id = cursor.lastrowid
    if row_id == 0:
        existing = conn.execute(
            "SELECT id FROM raw_items WHERE title = ? AND source = ? AND week_iso = ?",
            (title, source, week_iso),
        ).fetchone()
        conn.close()
        return existing["id"] if existing else 0
    conn.close()
    return row_id


def _match_reddit_category(title: str, body: str | None, keyword_filters: dict) -> str | None:
    """Match a Reddit post to an OTC category using keyword filters.

    Returns the first matching category, or None if no match.
    """
    text = (title + " " + (body or "")).lower()
    for category, keywords in keyword_filters.items():
        if any(kw in text for kw in keywords):
            return category
    return None


def _fetch_rss_feed(feed: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch and insert items from a single RSS feed.

    Returns a dict with keys: name, count, error.
    """
    name = feed["name"]
    url = feed["url"]
    category_hint = feed.get("category_hint")
    city = feed.get("city")
    source_tag = f"otc_rss_{name.lower().replace(' ', '_')}"

    try:
        entries = fetch_rss(url, delay_seconds=0)
        count = 0
        for entry in entries[:max_items]:
            if not _is_recent(entry, max_age_days):
                continue
            _insert_lifestyle_item(
                title=entry["title"],
                body=entry["body"][:2000] if entry["body"] else None,
                source=source_tag,
                url=entry["url"],
                city=city,
                category_hint=category_hint,
                week_iso=week_iso,
            )
            count += 1
        return {"name": name, "count": count, "error": None}
    except Exception as e:
        return {"name": name, "count": 0, "error": str(e)}


def _fetch_google_news_lifestyle(queries_by_category: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch lifestyle items from Google News RSS for all categories.

    Returns a dict with keys: count, errors.
    """
    total = 0
    errors = []

    for category, queries in queries_by_category.items():
        for query in queries:
            encoded = quote(query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-AU&gl=AU&ceid=AU:en"
            try:
                entries = fetch_rss(url, delay_seconds=2.0)
                for entry in entries[:max_items]:
                    if not _is_recent(entry, max_age_days):
                        continue
                    _insert_lifestyle_item(
                        title=entry["title"],
                        body=entry["body"][:2000] if entry["body"] else None,
                        source="otc_google_news",
                        url=entry["url"],
                        city=None,
                        category_hint=category,
                        week_iso=week_iso,
                    )
                    total += 1
            except Exception as e:
                errors.append(f"Google News '{query}': {e}")

    return {"count": total, "errors": errors}


def _fetch_reddit_lifestyle(subreddits: list, keyword_filters: dict, max_items: int, max_age_days: int, week_iso: str) -> dict:
    """Fetch lifestyle-relevant posts from Reddit, filtered by keyword.

    Returns a dict with keys: count, errors.
    """
    total = 0
    errors = []

    for sub in subreddits:
        try:
            entries = fetch_rss(sub["url"], delay_seconds=3.0)
            city = sub.get("city")
            sub_category_hint = sub.get("category_hint")

            for entry in entries[:max_items * 3]:  # fetch more, filter down
                if not _is_recent(entry, max_age_days):
                    continue

                # Determine category: subreddit hint > keyword match
                category = sub_category_hint or _match_reddit_category(
                    entry["title"], entry["body"], keyword_filters
                )
                if category is None:
                    continue  # Skip posts that don't match any lifestyle category

                _insert_lifestyle_item(
                    title=entry["title"],
                    body=entry["body"][:2000] if entry["body"] else None,
                    source=f"otc_reddit_r/{sub['name']}",
                    url=entry["url"],
                    city=city,
                    category_hint=category,
                    week_iso=week_iso,
                )
                total += 1

                if total >= max_items * len(subreddits):
                    break
        except Exception as e:
            errors.append(f"Reddit r/{sub['name']}: {e}")

    return {"count": total, "errors": errors}


def pull_off_the_clock() -> int:
    """Pull lifestyle items from all configured Off the Clock sources.

    Fetches RSS feeds in parallel, then Google News and Reddit sequentially.
    Returns count of newly inserted items.
    """
    config = _load_config()

    if not config.get("enabled", False):
        print("  Off the Clock is disabled in config")
        return 0

    week_iso = get_current_week_iso()
    max_items = config.get("max_items_per_source", 10)
    max_age_days = config.get("max_age_days", 10)
    total_inserted = 0

    # 1. RSS feeds in parallel
    rss_feeds = config.get("rss_feeds", [])
    if rss_feeds:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(_fetch_rss_feed, feed, max_items, max_age_days, week_iso): feed
                for feed in rss_feeds
            }
            for future in as_completed(futures):
                result = future.result()
                if result["error"]:
                    print(f"  FAILED: {result['name']}: {result['error']}")
                else:
                    total_inserted += result["count"]
                    if result["count"]:
                        print(f"  {result['name']}: {result['count']} items")

    # 2. Google News lifestyle queries
    gn_queries = config.get("google_news_queries", {})
    if gn_queries:
        gn_result = _fetch_google_news_lifestyle(gn_queries, max_items, max_age_days, week_iso)
        total_inserted += gn_result["count"]
        if gn_result["count"]:
            print(f"  Google News lifestyle: {gn_result['count']} items")
        for err in gn_result["errors"]:
            print(f"  FAILED: {err}")

    # 3. Reddit lifestyle posts
    reddit_subs = config.get("reddit_subreddits", [])
    keyword_filters = config.get("reddit_keyword_filters", {})
    if reddit_subs:
        reddit_result = _fetch_reddit_lifestyle(reddit_subs, keyword_filters, max_items, max_age_days, week_iso)
        total_inserted += reddit_result["count"]
        if reddit_result["count"]:
            print(f"  Reddit lifestyle: {reddit_result['count']} items")
        for err in reddit_result["errors"]:
            print(f"  FAILED: {err}")

    return total_inserted
```

- [ ] **Step 2: Verify the module imports and loads config**

```bash
python -c "
from flatwhite.editorial.off_the_clock import _load_config
config = _load_config()
print(f'Enabled: {config.get(\"enabled\")}')
print(f'RSS feeds: {len(config.get(\"rss_feeds\", []))}')
print('Module loads OK')
"
```
Expected: `Module loads OK`

- [ ] **Step 3: Commit**

```bash
git add flatwhite/editorial/off_the_clock.py
git commit -m "feat(editorial): add off_the_clock lifestyle ingest module"
```

---

### Task 4: OTC Classification Prompt

**Files:**
- Modify: `flatwhite/classify/prompts.py` (append OTC prompts)

- [ ] **Step 1: Add OTC classification prompts to prompts.py**

Append to the end of `flatwhite/classify/prompts.py`:

```python
# ─── OFF THE CLOCK CLASSIFICATION (consumed by classifier.py) ────────────────

OTC_CLASSIFICATION_SYSTEM = (
    "You are a lifestyle content curator for Flat White, a weekly newsletter for "
    "Australian corporate professionals. You classify lifestyle items into one of "
    "five categories and score them on trendiness and shareability. "
    "Output valid JSON only. No markdown fences. No explanation. No preamble."
)

OTC_CLASSIFICATION_PROMPT = (
    "Classify this lifestyle item for the Off the Clock section of Flat White.\n"
    "\n"
    "ITEM:\n"
    "Title: {title}\n"
    "Body: {body}\n"
    "Source: {source}\n"
    "URL: {url}\n"
    "City hint: {city}\n"
    "Category hint: {category_hint}\n"
    "\n"
    "AUDIENCE:\n"
    "Australian corporate professionals (Big 4, law, banking, consulting, tech) "
    "aged 25-45. They live in Sydney or Melbourne, earn well, eat out regularly, "
    "watch prestige TV, read longform, dress well for work, and go to exhibitions "
    "and events on weekends. Think: someone who reads Broadsheet, has a Criterion "
    "Channel subscription, owns at least one Uniqlo U piece, and knows which new "
    "restaurant to suggest for a client dinner.\n"
    "\n"
    "CATEGORIES (choose exactly one):\n"
    "- eating: restaurants, cafes, new openings, food trends, bars. "
    "Must be a specific place or specific food trend, not generic food news.\n"
    "- watching: streaming shows, films, TV series, documentaries. "
    "Must be currently available or just released. Not old content.\n"
    "- reading: books, articles, longform pieces, newsletters worth reading. "
    "Must be something passing around professional circles right now.\n"
    "- wearing: fashion drops, new collections, workwear, style trends. "
    "Must be specific (a brand, a drop, a collection), not generic fashion advice.\n"
    "- going: events, exhibitions, festivals, comedy, pop-ups, venues, experiences. "
    "Not restaurants (those go in eating). Must be current or upcoming.\n"
    "- discard: not relevant to the audience, older than one month, too generic, "
    "clickbait, or not specific enough to recommend. Content must be from the "
    "last 30 days to qualify — anything older is discard regardless of quality.\n"
    "\n"
    "SCORES (rate each 1-5, be strict):\n"
    "- trendiness: Is this THE thing right now? "
    "(1=old or generic, 2=somewhat current, 3=timely, 4=trending this week, "
    "5=everyone will be talking about it)\n"
    "- shareability: Would a corporate professional mention this to a colleague? "
    "(1=never, 2=maybe, 3=probably, 4=definitely, "
    "5=they would actively bring it up at lunch)\n"
    "\n"
    "CITY: Assign one of: sydney, melbourne, brisbane, perth, national. "
    "Use the city hint if provided, but override if the content clearly indicates "
    "a different city. Use 'national' for streaming, books, and fashion drops "
    "available everywhere.\n"
    "\n"
    "SUMMARY: Write a 1-2 sentence blurb in Flat White voice. Dry, specific, "
    "opinionated. Not a review. Not a recommendation. A statement from someone "
    "who already knows. Examples:\n"
    "- 'Ragazzi has opened a second location in Surry Hills and the cacio e pepe "
    "is already sold out by 7pm most nights. If you haven't been, put it on the list.'\n"
    "- 'Four episodes, each filmed in a single continuous take. It is British, "
    "it is heavy and it is the best thing on streaming right now.'\n"
    "- 'The Christophe Lemaire-designed line is back for autumn. The oversized "
    "wool blend coat will sell out.'\n"
    "\n"
    "Output as a single JSON object with these exact keys:\n"
    "category, trendiness, shareability, city, summary\n"
    "\n"
    "Output ONLY the JSON object. Nothing else."
)
```

- [ ] **Step 2: Verify the prompts load**

```bash
python -c "
from flatwhite.classify.prompts import OTC_CLASSIFICATION_SYSTEM, OTC_CLASSIFICATION_PROMPT
print(f'System prompt: {len(OTC_CLASSIFICATION_SYSTEM)} chars')
print(f'Classification prompt: {len(OTC_CLASSIFICATION_PROMPT)} chars')
print('OK')
"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flatwhite/classify/prompts.py
git commit -m "feat(classify): add Off the Clock lifestyle classification prompts"
```

---

### Task 5: OTC Classifier

**Files:**
- Modify: `flatwhite/classify/classifier.py` (add OTC classification functions)

- [ ] **Step 1: Add OTC-specific valid sections and classifier function**

Add these constants and functions to `flatwhite/classify/classifier.py`, after the existing `classify_all_unclassified()` function:

```python
OTC_VALID_SECTIONS: set[str] = {
    "otc_eating", "otc_watching", "otc_reading", "otc_wearing", "otc_going", "discard",
}

# Map from LLM output category names to DB section names
_OTC_CATEGORY_TO_SECTION: dict[str, str] = {
    "eating": "otc_eating",
    "watching": "otc_watching",
    "reading": "otc_reading",
    "wearing": "otc_wearing",
    "going": "otc_going",
    "discard": "discard",
}


def _otc_weighted_composite(trendiness: int, shareability: int) -> float:
    """Calculate weighted composite for OTC items: 0.5 * trendiness + 0.5 * shareability."""
    return round(0.5 * trendiness + 0.5 * shareability, 2)


def classify_single_otc_item(raw_item: dict) -> dict | None:
    """Classify one lifestyle raw_item via Gemini 2.5 Flash.

    Input: dict with keys: id, title, body, source, url, subreddit (city), lifestyle_category.
    Output: validated dict with section, trendiness, shareability, city, summary, weighted_composite.
    Returns None on LLM failure.
    """
    from flatwhite.classify.prompts import OTC_CLASSIFICATION_SYSTEM, OTC_CLASSIFICATION_PROMPT

    prompt = OTC_CLASSIFICATION_PROMPT.format(
        title=raw_item["title"],
        body=(raw_item["body"] or "")[:1500],
        source=raw_item["source"],
        url=raw_item["url"] or "",
        city=raw_item.get("subreddit") or "unknown",
        category_hint=raw_item.get("lifestyle_category") or "none",
    )

    try:
        response = route(
            task_type="classification",
            prompt=prompt,
            system=OTC_CLASSIFICATION_SYSTEM,
        )
    except Exception:
        return None

    result = _parse_llm_json(response)
    if result is None or not isinstance(result, dict):
        return None

    # Map category to section
    category = result.get("category", "discard")
    section = _OTC_CATEGORY_TO_SECTION.get(category, "discard")
    result["section"] = section

    # Validate and clamp scores
    for dim in ("trendiness", "shareability"):
        val = result.get(dim, 3)
        if not isinstance(val, (int, float)):
            val = 3
        result[dim] = max(1, min(5, int(val)))

    # Calculate weighted composite
    result["weighted_composite"] = _otc_weighted_composite(result["trendiness"], result["shareability"])

    # Auto-discard: both scores below 2
    if result["trendiness"] < 2 and result["shareability"] < 2:
        result["section"] = "discard"

    # Validate city
    city = result.get("city", "national")
    if city not in ("sydney", "melbourne", "brisbane", "perth", "national"):
        city = "national"
    result["city"] = city

    # Validate summary
    summary = result.get("summary")
    if not isinstance(summary, str) or len(summary) < 5:
        summary = raw_item["title"]
    result["summary"] = summary

    # Map trendiness/shareability into the standard 5-dimension columns for DB storage
    # We repurpose: relevance=trendiness, tension=shareability, others set to 3
    result["relevance"] = result["trendiness"]
    result["novelty"] = result["trendiness"]
    result["reliability"] = 3
    result["tension"] = result["shareability"]
    result["usefulness"] = result["shareability"]

    result["tags"] = []
    result["confidence_tag"] = None

    return result


def classify_all_otc_unclassified() -> dict:
    """Classify all unclassified lifestyle raw_items for the current week.

    Same flow as classify_all_unclassified() but for lane='lifestyle' using OTC prompts.
    Returns: dict with keys: total, curated, discarded, failed, skipped.
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    unclassified = conn.execute(
        "SELECT * FROM raw_items WHERE classified = 0 AND lane = 'lifestyle' AND week_iso = ?",
        (week_iso,),
    ).fetchall()
    conn.close()

    stats: dict = {
        "total": 0,
        "curated": 0,
        "discarded": 0,
        "failed": 0,
        "skipped": 0,
    }

    for item in unclassified:
        item_dict = dict(item)
        stats["total"] += 1

        # Guard: skip if already curated
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM curated_items WHERE raw_item_id = ?",
            (item_dict["id"],),
        ).fetchone()
        conn.close()
        if existing:
            conn = get_connection()
            conn.execute("UPDATE raw_items SET classified = 1 WHERE id = ?", (item_dict["id"],))
            conn.commit()
            conn.close()
            stats["skipped"] += 1
            continue

        result = classify_single_otc_item(item_dict)

        conn = get_connection()

        if result is None:
            conn.execute("UPDATE raw_items SET classified = 1 WHERE id = ?", (item_dict["id"],))
            conn.commit()
            conn.close()
            stats["failed"] += 1
            continue

        if result["section"] == "discard":
            conn.execute("UPDATE raw_items SET classified = 1 WHERE id = ?", (item_dict["id"],))
            conn.commit()
            conn.close()
            stats["discarded"] += 1
            continue

        conn.execute(
            """INSERT INTO curated_items
            (raw_item_id, section, summary, score_relevance, score_novelty,
             score_reliability, score_tension, score_usefulness, weighted_composite,
             tags, confidence_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_dict["id"],
                result["section"],
                result["summary"],
                result["relevance"],
                result["novelty"],
                result["reliability"],
                result["tension"],
                result["usefulness"],
                result["weighted_composite"],
                json.dumps(result["tags"]),
                result["confidence_tag"],
            ),
        )
        conn.execute("UPDATE raw_items SET classified = 1 WHERE id = ?", (item_dict["id"],))
        conn.commit()
        conn.close()
        stats["curated"] += 1

        # Rate limit: 1s between LLM calls
        time.sleep(1)

    return stats
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
python -c "
from flatwhite.classify.classifier import classify_all_otc_unclassified, OTC_VALID_SECTIONS
print(f'OTC sections: {OTC_VALID_SECTIONS}')
print('OK')
"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flatwhite/classify/classifier.py
git commit -m "feat(classify): add OTC lifestyle classifier and classify_all_otc_unclassified"
```

---

### Task 6: Dashboard State Functions

**Files:**
- Modify: `flatwhite/dashboard/state.py` (add OTC state functions)

- [ ] **Step 1: Add OTC state functions to state.py**

Append to the end of `flatwhite/dashboard/state.py`:

```python
OTC_SECTIONS = ["otc_eating", "otc_watching", "otc_reading", "otc_wearing", "otc_going"]

OTC_CATEGORY_LABELS = {
    "otc_eating": "Eating",
    "otc_watching": "Watching",
    "otc_reading": "Reading",
    "otc_wearing": "Wearing",
    "otc_going": "Going",
}


def load_otc_candidates(week_iso: str | None = None, candidates_per_category: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Return Off the Clock candidates grouped by category for the editor pick UI.

    Each category contains up to candidates_per_category items sorted by weighted_composite DESC.
    Joins curated_items with raw_items for content fields.
    Excludes items that have already been picked (have an approved editor_decision).

    Output: dict with keys 'otc_eating', 'otc_watching', etc. Each value is a list of dicts
    with: id, summary, weighted_composite, score_relevance (trendiness), score_tension (shareability),
    title, source, url, city (from subreddit column), decision, decision_id.
    """
    conn = get_connection()
    w = week_iso or get_current_week_iso()

    rows = conn.execute(
        """
        SELECT
            ci.id, ci.section, ci.summary, ci.weighted_composite,
            ci.score_relevance, ci.score_tension,
            ri.title, ri.source, ri.url, ri.subreddit AS city,
            ri.lifestyle_category,
            ed.decision, ed.id AS decision_id
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        LEFT JOIN editor_decisions ed
            ON ed.curated_item_id = ci.id AND ed.issue_week_iso = ?
        WHERE ri.week_iso = ?
          AND ci.section IN ('otc_eating', 'otc_watching', 'otc_reading', 'otc_wearing', 'otc_going')
        ORDER BY ci.weighted_composite DESC
        """,
        (w, w),
    ).fetchall()
    conn.close()

    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in OTC_SECTIONS}
    for row in rows:
        d = dict(row)
        section = d["section"]
        if section in grouped and len(grouped[section]) < candidates_per_category:
            grouped[section].append(d)

    return grouped


def save_otc_pick(
    category: str,
    curated_item_id: int,
    editor_blurb: str,
    week_iso: str | None = None,
) -> int:
    """Save an editor's Off the Clock pick for a category.

    Approves the chosen curated_item and stores the editor's blurb as our_take.
    Any previous OTC pick for this category+week is rejected.

    Returns the editor_decisions row id.
    """
    w = week_iso or get_current_week_iso()
    conn = get_connection()

    # Reject any previous pick for this category this week
    conn.execute(
        """UPDATE editor_decisions SET decision = 'rejected'
        WHERE issue_week_iso = ? AND section_placed = ?
        AND decision = 'approved'""",
        (w, category),
    )

    # Approve the new pick
    cursor = conn.execute(
        """INSERT INTO editor_decisions (curated_item_id, decision, section_placed, issue_week_iso)
        VALUES (?, 'approved', ?, ?)""",
        (curated_item_id, category, w),
    )

    # Store the editor's blurb
    conn.execute(
        "UPDATE curated_items SET our_take = ? WHERE id = ?",
        (editor_blurb.strip(), curated_item_id),
    )

    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def load_otc_picks(week_iso: str | None = None) -> list[dict[str, Any]]:
    """Return saved Off the Clock picks for newsletter assembly.

    Returns approved OTC items with their editor blurbs, one per category.
    Output: list of dicts with: section, label, summary (editor blurb from our_take),
    title, source, url, city.
    """
    w = week_iso or get_current_week_iso()
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            ci.section, ci.summary, ci.our_take,
            ri.title, ri.url, ri.subreddit AS city
        FROM editor_decisions ed
        JOIN curated_items ci ON ed.curated_item_id = ci.id
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ed.issue_week_iso = ?
          AND ed.decision = 'approved'
          AND ci.section IN ('otc_eating', 'otc_watching', 'otc_reading', 'otc_wearing', 'otc_going')
        ORDER BY ci.section
        """,
        (w,),
    ).fetchall()
    conn.close()

    return [
        {
            **dict(r),
            "label": OTC_CATEGORY_LABELS.get(r["section"], r["section"]),
            "blurb": r["our_take"] or r["summary"],
        }
        for r in rows
    ]
```

- [ ] **Step 2: Verify imports**

```bash
python -c "
from flatwhite.dashboard.state import load_otc_candidates, save_otc_pick, load_otc_picks
print('State functions OK')
"
```
Expected: `State functions OK`

- [ ] **Step 3: Commit**

```bash
git add flatwhite/dashboard/state.py
git commit -m "feat(dashboard): add OTC state functions for candidates, picks, and assembly"
```

---

### Task 7: Dashboard API Endpoints

**Files:**
- Modify: `flatwhite/dashboard/api.py` (add OTC endpoints)

- [ ] **Step 1: Add imports to api.py**

Add to the imports block at the top of `flatwhite/dashboard/api.py`, after the existing state imports:

```python
from flatwhite.dashboard.state import (
    load_otc_candidates,
    save_otc_pick,
    load_otc_picks,
)
```

Note: merge these into the existing `from flatwhite.dashboard.state import (...)` block.

- [ ] **Step 2: Add GET /api/off-the-clock endpoint**

Add before the `# ── WRITE endpoints` section:

```python
@app.get("/api/off-the-clock")
def api_off_the_clock() -> JSONResponse:
    """Return Off the Clock candidates grouped by category for current week."""
    candidates = load_otc_candidates()
    picks = load_otc_picks()
    return JSONResponse({
        "candidates": candidates,
        "picks": picks,
        "week_iso": get_current_week_iso(),
    })
```

- [ ] **Step 3: Add POST /api/off-the-clock/pick endpoint**

Add after the other POST endpoints:

```python
@app.post("/api/off-the-clock/pick")
async def api_otc_pick(request: Request) -> JSONResponse:
    """Save an editor's Off the Clock pick for a category.

    Body: {"curated_item_id": int, "category": str, "blurb": str}
    """
    body = await request.json()
    curated_item_id = body.get("curated_item_id")
    category = body.get("category")
    blurb = body.get("blurb", "")

    if not isinstance(curated_item_id, int):
        return JSONResponse({"error": "curated_item_id must be an integer"}, status_code=400)
    if category not in ("otc_eating", "otc_watching", "otc_reading", "otc_wearing", "otc_going"):
        return JSONResponse({"error": "Invalid category"}, status_code=400)
    if not blurb.strip():
        return JSONResponse({"error": "blurb is required"}, status_code=400)

    row_id = save_otc_pick(
        category=category,
        curated_item_id=curated_item_id,
        editor_blurb=blurb,
    )
    return JSONResponse({"id": row_id, "week_iso": get_current_week_iso()})
```

- [ ] **Step 4: Add OTC to the reingest background pipeline**

In the `_run_ingest_background()` function, add to the `_run_group2()` function (editorial sources group):

```python
_step("off_the_clock", lambda: __import__("flatwhite.editorial.off_the_clock", fromlist=["pull_off_the_clock"]).pull_off_the_clock())
```

And in the `_run_group5()` section (after the existing classify step), add:

```python
_step("classify_otc", lambda: __import__("flatwhite.classify.classifier", fromlist=["classify_all_otc_unclassified"]).classify_all_otc_unclassified())
```

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/api.py
git commit -m "feat(api): add Off the Clock endpoints and wire into reingest pipeline"
```

---

### Task 8: CLI Integration

**Files:**
- Modify: `flatwhite/cli.py`

- [ ] **Step 1: Add off_the_clock to cmd_ingest Group 2**

In the `_run_group2()` function inside `cmd_ingest()`, add after the podcast feeds block (around line 175):

```python
from flatwhite.editorial.off_the_clock import pull_off_the_clock
print("Pulling Off the Clock lifestyle sources...")
otc_count = pull_off_the_clock()
print(f"  {otc_count} lifestyle items ingested")
```

- [ ] **Step 2: Add OTC classification to Group 5**

In the Group 5 section of `cmd_ingest()`, after the existing classify block (around line 239):

```python
from flatwhite.classify.classifier import classify_all_otc_unclassified
otc_stats = classify_all_otc_unclassified()
print(f"  OTC classified: {otc_stats['total']} total, {otc_stats['curated']} curated, "
      f"{otc_stats['discarded']} discarded, {otc_stats['failed']} failed")
```

- [ ] **Step 3: Update cmd_classify to also classify OTC items**

In `cmd_classify()`, after the existing classification call (around line 300):

```python
# OTC lifestyle classification
from flatwhite.classify.classifier import classify_all_otc_unclassified
otc_stats = classify_all_otc_unclassified()
print(f"\nOTC lifestyle: {otc_stats['total']} total, {otc_stats['curated']} curated, "
      f"{otc_stats['discarded']} discarded")
```

- [ ] **Step 4: Commit**

```bash
git add flatwhite/cli.py
git commit -m "feat(cli): wire Off the Clock into ingest and classify commands"
```

---

### Task 9: Dashboard Frontend — Off the Clock Tab

**Files:**
- Modify: `flatwhite/dashboard/static/index.html`

- [ ] **Step 1: Add Off the Clock tab to the navigation**

Find the existing tab navigation in `index.html` and add a new tab button:

```html
<button class="tab-btn" data-tab="otc">Off the Clock</button>
```

- [ ] **Step 2: Add the Off the Clock panel HTML**

Add a new tab panel div alongside the existing ones:

```html
<div id="tab-otc" class="tab-panel" style="display:none">
  <h2>Off the Clock</h2>
  <p class="subtitle">Pick one winner per category. Edit the blurb before saving.</p>
  <div id="otc-categories"></div>
  <div id="otc-picks" style="margin-top:2rem"></div>
</div>
```

- [ ] **Step 3: Add the JavaScript to fetch and render OTC candidates**

Add to the `<script>` section:

```javascript
const OTC_LABELS = {
  otc_eating: {label: 'Eating', emoji: '🍷'},
  otc_watching: {label: 'Watching', emoji: '📺'},
  otc_reading: {label: 'Reading', emoji: '📖'},
  otc_wearing: {label: 'Wearing', emoji: '👔'},
  otc_going: {label: 'Going', emoji: '🎭'},
};

async function loadOTC() {
  const resp = await fetch('/api/off-the-clock');
  const data = await resp.json();
  const container = document.getElementById('otc-categories');
  const picksContainer = document.getElementById('otc-picks');

  let html = '';
  for (const [section, meta] of Object.entries(OTC_LABELS)) {
    const items = data.candidates[section] || [];
    const existingPick = data.picks.find(p => p.section === section);

    html += `<div class="otc-category" style="margin-bottom:1.5rem;padding:1rem;background:#faf8f5;border-radius:8px">`;
    html += `<h3>${meta.emoji} ${meta.label}</h3>`;

    if (existingPick) {
      html += `<div style="padding:0.75rem;background:#e8f5e9;border-radius:6px;margin-bottom:0.5rem">`;
      html += `<strong>Picked:</strong> ${existingPick.blurb}`;
      html += `</div>`;
    }

    if (items.length === 0) {
      html += `<p style="color:#999">No candidates this week</p>`;
    } else {
      for (const item of items) {
        const isPicked = item.decision === 'approved';
        html += `<div style="padding:0.75rem;border:1px solid #e0d6cc;border-radius:6px;margin-bottom:0.5rem;${isPicked ? 'border-color:#4caf50;background:#f1f8e9' : ''}">`;
        html += `<div><a href="${item.url || '#'}" target="_blank" style="color:#3d2e1e;font-weight:600">${item.title}</a></div>`;
        html += `<div style="font-size:0.85rem;color:#888;margin:0.25rem 0">${item.source} · ${item.city || 'national'} · T:${item.score_relevance} S:${item.score_tension}</div>`;
        html += `<div style="font-size:0.9rem;margin:0.5rem 0">${item.summary}</div>`;
        html += `<div style="display:flex;gap:0.5rem;align-items:center">`;
        html += `<textarea id="otc-blurb-${item.id}" rows="2" style="flex:1;padding:0.4rem;border:1px solid #ddd;border-radius:4px;font-size:0.85rem">${item.summary}</textarea>`;
        html += `<button onclick="pickOTC('${section}', ${item.id})" style="padding:0.4rem 1rem;background:#6b4f36;color:#fff;border:none;border-radius:4px;cursor:pointer">${isPicked ? 'Update' : 'Pick'}</button>`;
        html += `</div></div>`;
      }
    }
    html += `</div>`;
  }
  container.innerHTML = html;

  // Show saved picks summary
  if (data.picks.length > 0) {
    let picksHtml = '<h3>Saved Picks</h3>';
    for (const pick of data.picks) {
      picksHtml += `<p><strong>${pick.label}:</strong> ${pick.blurb}</p>`;
    }
    picksContainer.innerHTML = picksHtml;
  }
}

async function pickOTC(category, curatedItemId) {
  const blurb = document.getElementById(`otc-blurb-${curatedItemId}`).value.trim();
  if (!blurb) { alert('Write a blurb first'); return; }

  const resp = await fetch('/api/off-the-clock/pick', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({curated_item_id: curatedItemId, category: category, blurb: blurb}),
  });
  if (resp.ok) {
    loadOTC();
  } else {
    const err = await resp.json();
    alert(err.error || 'Failed to save pick');
  }
}
```

- [ ] **Step 4: Wire tab switching to load OTC data**

In the existing tab switching logic, add:

```javascript
if (tabId === 'otc') loadOTC();
```

- [ ] **Step 5: Commit**

```bash
git add flatwhite/dashboard/static/index.html
git commit -m "feat(dashboard): add Off the Clock tab with pick UI"
```

---

### Task 10: Smoke Test End-to-End

**Files:** None (testing only)

- [ ] **Step 1: Run init to apply migrations**

```bash
python -m flatwhite.cli init
```
Expected: `Database initialised at data/flatwhite.db` (no errors)

- [ ] **Step 2: Verify lifestyle lane works in DB**

```bash
python -c "
from flatwhite.db import get_connection, init_db
init_db()
conn = get_connection()
# Test lifestyle insert
conn.execute(
    \"INSERT OR IGNORE INTO raw_items (title, source, url, lane, subreddit, pulled_at, week_iso, lifestyle_category) \"
    \"VALUES ('Test pasta spot', 'otc_test', NULL, 'lifestyle', 'sydney', datetime('now'), '2026-W13', 'eating')\"
)
# Test OTC section insert
row = conn.execute('SELECT id FROM raw_items WHERE title = ? AND source = ?', ('Test pasta spot', 'otc_test')).fetchone()
conn.execute(
    \"INSERT OR IGNORE INTO curated_items (raw_item_id, section, summary, score_relevance, score_novelty, \"
    \"score_reliability, score_tension, score_usefulness, weighted_composite, tags) \"
    \"VALUES (?, 'otc_eating', 'Test blurb', 4, 4, 3, 4, 4, 4.0, '[]')\",
    (row['id'],)
)
conn.commit()
# Clean up
conn.execute('DELETE FROM curated_items WHERE summary = ?', ('Test blurb',))
conn.execute('DELETE FROM raw_items WHERE source = ?', ('otc_test',))
conn.commit()
conn.close()
print('DB smoke test PASSED')
"
```
Expected: `DB smoke test PASSED`

- [ ] **Step 3: Test the ingest module can pull at least one source**

```bash
python -c "
from flatwhite.editorial.off_the_clock import pull_off_the_clock
count = pull_off_the_clock()
print(f'Ingested {count} lifestyle items')
"
```
Expected: Some number > 0 (at least Google News should return results)

- [ ] **Step 4: Test the API endpoint**

Start the dashboard, then test the endpoint:
```bash
python -c "
from flatwhite.dashboard.state import load_otc_candidates
candidates = load_otc_candidates()
for section, items in candidates.items():
    print(f'{section}: {len(items)} candidates')
print('API state functions OK')
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete Off the Clock lifestyle section pipeline"
```
