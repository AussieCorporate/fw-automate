# FW Top Picks: two lists (Odd + Business) with feature-story summaries

**Date:** 2026-07-19
**Status:** Approved (Victor, in conversation)

## Problem

FW's Top Picks scrape (`flatwhite/editorial/beehiiv_picks.py`) pulls top-CLICKED
links from published PS beehiiv editions (last 7 days). Two gaps:
1. **Feature stories never appear.** A PS feature is an inline deep-dive with no
   click-link, so it has no click data and the scrape can't see it. Victor can't
   pick individual features - he only sees the 5 editions.
2. **Odd and business are merged** into one click-ranked list.

The one-sentence summaries of feature stories ARE generated in PS but are NOT
published to beehiiv (the feature ships as the full deep-dive), so FW cannot get
them from beehiiv. They must be stored by PS.

## What Victor wants

FW Top Picks produces TWO selectable lists; he picks the top 5 from each:
- **Odd picks** - quirky non-business stories (for "one more scroll" / editorial
  intro).
- **Business picks** - Australian + Company news (with click counts) PLUS the
  feature-story one-sentence summaries (no clicks), in ONE list with features
  tagged (Victor's choice).

## Design

### Part A - PS (Shell Bot 2) writes a picks feed  (additive; NO change to output)
After each newsletter run, in `_do_ready_generate`, append one record per edition
to `state/fw_picks_feed.jsonl` (a rolling log; FW filters to last 7 days):
```
{ "edition_date": "<iso>",
  "business": [ {url, title, summary, category, is_feature} ... ],   # from sections_data.articles; is_feature = title has a deep_dive
  "odd":      [ {url, title, summary} ... ] }                        # from sections_data.picks.odd
```
Data is exactly what PS already computed (sections_data.articles carry
title/url/summary/category COMPANY|AUS|GLOBAL; deep_dives carry the feature
titles; picks.odd carries the odd stories). Writing the feed changes NOTHING
about what PS publishes. Fail-open: a feed-write error never breaks the run.

### Part B - FW reads the feed + merges with beehiiv clicks
`scrape_top_picks` (or a wrapper) returns `{"odd": [...], "business": [...]}`:
- **Business list**: start from the PS feed's business items (each carries its
  one-sentence summary + category + is_feature). Join beehiiv click counts by URL
  (utm-stripped) so clicked news shows its clicks; feature items have no clicks
  and are tagged `is_feature: true`. Sort: clicked items by clicks desc, features
  (no clicks) grouped at the top (they're the ones Victor most needs to see).
- **Odd list**: the PS feed's odd items (last 7 days), deduped by URL.
- Fall back to today's click-only behaviour if the PS feed is missing (so FW
  still works before PS starts writing it).

### FW dashboard UI
Top Picks screen shows TWO selectable lists (Odd / Business), each row a
checkbox + summary (+ click count or a `feature` tag). Victor ticks up to 5 in
each; the chosen items feed the FW `top_picks` (business) and the odd-picks
section.

## Cross-project path
PS writes `~/Movies/Shell Bot 2/state_store_root/state/fw_picks_feed.jsonl`
(via its state_store). FW reads it READ-ONLY at a configurable path
(`FW_PS_PICKS_FEED`, default that path) - same read-only cross-project pattern
FW already uses for Trading Strategy (Brains Trust).

## Out of scope
- No change to what PS publishes or how the PS newsletter looks.
- No change to how features/summaries are generated - only STORING them.
- Click analytics stay beehiiv-sourced for the business items that have links.

## Verification
- PS: run generates a feed line with business (summaries+category+is_feature) and
  odd items; verify against a real run.
- FW: scrape returns two lists; features appear in business tagged, with no
  clicks; odd list populated; falls back cleanly when the feed is absent.
