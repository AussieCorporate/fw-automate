# Off the Clock — Design Spec

**Date**: 2026-03-26
**Status**: Approved
**Scope**: New lifestyle section for the Flat White newsletter pipeline

## Overview

Off the Clock is a lifestyle section with five categories: Eating, Watching, Reading, Wearing, Going. The pipeline auto-surfaces the top 3 candidates per category from lifestyle sources. The editor picks one winner from each category and edits the one-liner. The final newsletter runs all 5 categories with one pick each.

The section humanises the Flat White brand. It signals that the newsletter is written by someone who has a life outside the office. Morning Brew's "Brew's Best" serves the same function.

## City Scope

Sydney and Melbourne are primary cities. Brisbane and Perth appear occasionally when something is strong enough. National items (streaming, books, fashion drops) have no city filter.

## Data Sources

### Eating (restaurants, cafes, new openings, food trends)

| Source | Type | City |
|--------|------|------|
| Broadsheet Sydney | RSS | Sydney |
| Broadsheet Melbourne | RSS | Melbourne |
| Concrete Playground food | RSS/scrape | Sydney + Melbourne |
| Good Food (SMH) | RSS | Sydney + national |
| Time Out Sydney | RSS/scrape | Sydney |
| Time Out Melbourne | RSS/scrape | Melbourne |
| Google News: "best new restaurant sydney" | Google News RSS | Sydney |
| Google News: "best new restaurant melbourne" | Google News RSS | Melbourne |
| r/sydney, r/melbourne | Reddit RSS (keyword filter: restaurant, food, cafe, opened) | Sydney, Melbourne |

### Watching (streaming, TV, film)

| Source | Type | City |
|--------|------|------|
| JustWatch AU trending | Scrape | National |
| Google News: "best show streaming australia" | Google News RSS | National |
| Google News: "netflix australia" | Google News RSS | National |
| Google Trends: TV show spikes AU | Google Trends API | National |
| r/australia entertainment posts | Reddit RSS (keyword filter) | National |

### Reading (books, articles, longform, newsletters)

| Source | Type | City |
|--------|------|------|
| Booktopia trending/bestsellers | Scrape | National |
| Google News: "best article this week australia" | Google News RSS | National |
| Google News: "must read longform" | Google News RSS | National |
| r/books, r/australia reading posts | Reddit RSS (keyword filter) | National |

### Wearing (fashion drops, new collections, workwear)

| Source | Type | City |
|--------|------|------|
| Broadsheet style section | RSS | National |
| Google News: "fashion drop australia" | Google News RSS | National |
| Google News: "new collection australia" | Google News RSS | National |
| r/AustralianMFA | Reddit RSS | National |

### Going (events, exhibitions, venues, experiences — not restaurants)

| Source | Type | City |
|--------|------|------|
| Broadsheet events Sydney | RSS/scrape | Sydney |
| Broadsheet events Melbourne | RSS/scrape | Melbourne |
| Concrete Playground events | RSS/scrape | Sydney + Melbourne |
| Time Out Sydney events | RSS/scrape | Sydney |
| Time Out Melbourne events | RSS/scrape | Melbourne |
| Google News: "things to do sydney this week" | Google News RSS | Sydney |
| Google News: "things to do melbourne this week" | Google News RSS | Melbourne |
| Eventbrite trending AU | API/scrape (if available) | Sydney + Melbourne |

## Architecture

### New Module: `flatwhite/editorial/off_the_clock.py`

Single entry point: `pull_off_the_clock() -> int`

Follows the same pattern as `rss_feeds.py` and `google_news_editorial.py`:
- Reads config from `config.yaml` under `off_the_clock` key
- Fetches from all enabled sources in parallel (ThreadPoolExecutor)
- Inserts into `raw_items` with `lane='lifestyle'`
- Returns count of newly inserted items

Source-specific fetch functions are private helpers within the module (e.g. `_fetch_broadsheet()`, `_fetch_google_news_lifestyle()`, `_fetch_reddit_lifestyle()`). If the module grows beyond ~300 lines, individual source fetchers can be extracted to separate files under `flatwhite/editorial/lifestyle/`.

### Config Block: `off_the_clock` in `config.yaml`

```yaml
off_the_clock:
  enabled: true
  categories:
    - eating
    - watching
    - reading
    - wearing
    - going
  candidates_per_category: 3
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
      - "longform article"
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
    - name: "Broadsheet Sydney"
      url: "https://www.broadsheet.com.au/sydney/food-and-drink/rss"
      category_hint: "eating"
      city: "sydney"
    - name: "Broadsheet Melbourne"
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
    eating: ["restaurant", "cafe", "food", "opened", "menu", "pasta", "ramen", "brunch", "dinner"]
    watching: ["netflix", "streaming", "show", "series", "movie", "film", "binge"]
    reading: ["book", "read", "article", "longread", "podcast"]
    wearing: ["fashion", "drop", "collection", "uniqlo", "clothing", "wear", "style"]
    going: ["event", "exhibition", "show", "festival", "pop-up", "gallery", "comedy", "gig", "market"]
  max_age_days: 10
  max_items_per_source: 10
```

Note: RSS URLs above are best-guess. Each URL must be verified during implementation. Non-working feeds should be disabled and replaced with Google News query fallbacks or Playwright scraping.

### Database Changes

**Option A (chosen): Reuse existing tables with new lane and section values.**

No new tables. Lifestyle items flow through the same `raw_items` -> `curated_items` -> `editor_decisions` pipeline:

- `raw_items`: inserted with `lane='lifestyle'`. The `subreddit` column is repurposed as a general `source_detail` field (already stores subreddit name for Reddit items; for lifestyle, stores city tag like "sydney", "melbourne", "national").
- `curated_items`: classified with `section` values: `otc_eating`, `otc_watching`, `otc_reading`, `otc_wearing`, `otc_going`, or `discard`.
- `editor_decisions`: editor picks stored with `decision='approved'` and `section_placed` matching the OTC section.

New column on `raw_items`:
- `lifestyle_category TEXT` — nullable, set at ingest time if the source has a `category_hint`. Null for sources that need LLM classification to determine category.

Migration: `ALTER TABLE raw_items ADD COLUMN lifestyle_category TEXT;`

### Classification

New prompt in `flatwhite/classify/prompts.py`: `OTC_CLASSIFICATION_SYSTEM` and `OTC_CLASSIFICATION_PROMPT`.

Lifestyle items are classified separately from corporate editorial items. The classifier runs after ingest, same as the existing `classify` command but filtered to `lane='lifestyle'`.

**Input**: title, body, source, url, city, category_hint (if any)

**Output** (JSON):
- `category`: eating / watching / reading / wearing / going / discard
- `trendiness` (1-5): Is this happening right now? Will people talk about it this week?
- `shareability` (1-5): Would a corporate professional mention this to a colleague unprompted?
- `city`: sydney / melbourne / brisbane / perth / national
- `summary`: 1-2 sentence blurb rewritten in TAC voice. Dry, specific, opinionated. Not a review. Not a recommendation. A statement from someone who already knows.

**Weighted composite**: `0.5 * trendiness + 0.5 * shareability` (simpler than the 5-dimension corporate scoring — lifestyle picks are about "is this the thing right now" and "would you actually tell someone about it").

**Auto-discard rules**:
- trendiness < 2 AND shareability < 2 -> discard
- Duplicate detection: same restaurant/show/book title within the same week -> keep highest scored
- Items older than `max_age_days` (10 days) -> discard at ingest, not classification

**Category assignment logic**:
1. If `category_hint` from config is set and confidence is high, use it
2. Otherwise, LLM assigns category based on content
3. If the item doesn't fit any category cleanly, discard

### Dashboard

New tab/panel: "Off the Clock" on the existing FastAPI dashboard.

**Layout**: 5 sections (one per category), each showing:
- Category header with emoji (e.g. "Eating", "Watching")
- Top 3 candidates sorted by weighted composite DESC
- Each candidate shows:
  - Title (linked to source URL)
  - Source name + city tag
  - Trendiness + Shareability scores (small badges)
  - Auto-generated one-liner (TAC voice summary from classification)
- "Pick" button on each candidate
- Once picked, the one-liner becomes an editable text field
- "Save" commits the editor's final version

**State functions** in `flatwhite/dashboard/state.py`:
- `load_otc_candidates(week_iso) -> dict[str, list[dict]]` — returns candidates grouped by category
- `save_otc_pick(category, curated_item_id, editor_blurb, week_iso) -> int` — saves editor selection
- `load_otc_picks(week_iso) -> list[dict]` — returns saved picks for assembly

**API endpoints** in `flatwhite/dashboard/api.py`:
- `GET /api/off-the-clock` — returns candidates grouped by category for current week
- `POST /api/off-the-clock/pick` — saves editor pick for a category
- `GET /api/off-the-clock/picks` — returns saved picks for newsletter assembly

### CLI Integration

The `ingest` command gains a new parallel group:
- Group 2 (editorial sources) is extended to include `pull_off_the_clock()`
- Or: new Group 6 that runs in parallel with Group 2 (lifestyle sources are independent of editorial sources)

The `classify` command is extended to also classify `lane='lifestyle'` items using the OTC prompt.

### Newsletter Assembly

Off the Clock renders as a single block in the newsletter:

```
Off the Clock

Eating — [one-liner]
Watching — [one-liner]
Reading — [one-liner]
Wearing — [one-liner]
Going — [one-liner]
```

Each one-liner is the editor-approved blurb from the dashboard. No further LLM processing at assembly time.

## What This Does NOT Include

- LLM-generated one-liners as final output (editor writes/edits these)
- Automated publishing to Beehiiv (existing assembly pipeline handles that when built)
- Podcast picks (these stay in the existing editorial lane unless explicitly moved later)
- Price tracking or affiliate links
- User-submitted recommendations (future feature)
- A/B testing of picks

## Implementation Order

1. Config block in `config.yaml`
2. DB migration (add `lifestyle_category` column)
3. `off_the_clock.py` ingest module (source fetchers)
4. OTC classification prompt + classifier integration
5. Dashboard state functions
6. Dashboard API endpoints
7. Dashboard frontend (Off the Clock tab)
8. CLI integration (wire into `ingest` and `classify` commands)
9. Newsletter assembly block
