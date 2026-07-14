# FW (Flat White newsletter) — Project Guide

FastAPI dashboard + scrapers for the Flat White newsletter.

## "Fire up the FW dashboard" means exactly

```bash
cd /Users/victornguyen/Documents/MISC/FW
.venv/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500
```

then give Victor **http://localhost:8500/**. (Same as double-clicking `Start Flat White.command`.) The dashboard is NOT a service — it only runs while this process is alive; if "the dash isn't running", that's why. Use the venv python explicitly (system python is 3.9 and breaks).

## Scrapers

- OTC ("Off The Clock"): `flatwhite/editorial/off_the_clock.py`
- Pulse: `flatwhite/pulse/` package
- Reddit: `flatwhite/editorial/reddit_rss.py` and `flatwhite/signals/reddit_topic_velocity.py`
- All triggered via `python -m flatwhite.cli <run|ingest|pulse|notify>` (venv python).

## Standing decisions (do not re-propose)

- Reddit "script app" OAuth is broken — never build on it or scaffold it again.
- Reddit links are excluded from OTC.

## Definition of done for pipeline fixes

Committed + pushed + deployed (GCP VM `flatwhite`, `us-central1-a`, via `deploy/gcp_deploy.sh`) + cron enabled. A fix that exists only locally must be reported as "fixed locally, NOT deployed" — never as done.

## Known broken config

`cron/com.flatwhite.weekly.plist` hardcodes a dead path (`/Users/TAC/Desktop/AntiGravity/...`). The weekly launchd job cannot work from this repo location until those paths are fixed — check this first when the Wednesday run doesn't happen.

## Sponsor analytics

beehiiv reports (e.g. Sharesight placements) use the beehiiv MCP tools: audience, opens, raw vs verified clicks, per-edition breakdown.

## FW editorial intro — no skill exists yet (13 Jul 2026, from Victor)

The Flat White editorial introduction skill now EXISTS: ~/.claude/skills/flat-white-intro/SKILL.md (built 13 Jul 2026 from the real published format — source: data/beehiiv_fw_ground_truth.json, 10 real editions, segment-parsed). The dash's _proceed_editorial should be recalibrated against that skill + corpus before being trusted.

## Flat White weekly cadence + segment production — CORRECTED (13-14 Jul 2026, from Victor)

**Timing (earliest each segment can run):**
- Whole edition can't really start before FRIDAY AFTERNOON, except Brains Trust (runs as broker research comes in, ongoing/multi-week).
- BIG CONVERSATION is LAST. It runs off topics that are part of a CAMPAIGN run every FRIDAY; final community submissions come in SATURDAY MORNING (24-hour Instagram story window). Only then: sort the screenshots, pick one of the topics, produce.
- Off the Clock: can be done Friday (it's just finding stories).
- Thread of the Week: stays MANUAL (Reddit scrape is dead/403, don't rebuild).

**Segment order in the row/kanban (Big Conversation last).** Victor wants the dashboard to show each newsletter segment as a COLUMN, with rows/cards he can mark ready / not-ready and DRAG up and down like a KANBAN board to reorder. Each segment aligned as its own column.

**THE INSIDE TRACK — segment to ADD.** Community DM submissions aren't only Big-Conversation material: people also submit GOSSIP and REDUNDANCY news from the week. Those get sorted OUT of the Big Conversation pile and INTO "The Inside Track" (the gossip / redundancies segment). So screenshot sorting has (at least) three destinations: Big Conversation (views/extremes/consensus), The Inside Track (gossip + redundancies), and junk.

**OFF THE CLOCK — improve the sourcing.** Currently pulls from MAJOR outlets (Concrete Playground etc). Those businesses already get mass coverage. Victor would rather the segment do NICHE research: find SMALLER businesses that would actually benefit from our coverage. Niche but quality. (Design/skill change: bias OTC discovery away from big-outlet aggregation toward small/under-covered venues.)

**EDITORIAL INTRO — structure (like PS but two-part).** Take LAST WEEK's top story to cover/recap first (the way PS recaps), THEN the "this week we cover X" preview. So the intro = brief callback to last week's lead + this week's 3-item preview. (Update ~/.claude/skills/flat-white-intro/SKILL.md to reflect the last-week-recap opening once confirmed against real editions.)

## Screenshot sorting skill — needs REBUILD (13-14 Jul, from Victor)

The current tier system ("RED HOT" / "Tier 1..4") parameters are WRONG per Victor. Correct sorting intent for the Instagram DM screenshots (source: ~/Documents/MISC/instagram-dm-screenshotter/output/, its sort rules + big-conversation skill):
- VIRAL / SHARE-BAIT: content with potential to go viral - makes people go "wtf" and share to their mates. EXTREMES of the situation. This is the top-tier keep.
- CONSENSUS / NORMAL: the neutral, normal submissions - kept because they help FORM the view of what the consensus actually is (not discarded as boring).
- For a Big Conversation VIEW/angle: the accompanying screenshots should not merely SUPPORT the view - they should ideally be the EXTREME OF EACH END of the spectrum of that view (both poles), plus the consensus middle. So a produced piece pairs: the thought-leadership view (existing big-conversation MD skill) + screenshots that are the extremes of each side + consensus.
- GOSSIP / REDUNDANCIES: routed to The Inside Track, not Big Conversation.
- Rebuild the sort skill's rubric around these (viral/wtf, spectrum-extremes, consensus, gossip-routing) rather than the current tier labels.

## FW control-room — detailed segment mechanics (14 Jul 2026, from Victor) — supersedes earlier notes where they conflict

### The Inside Track
- Its OWN top-level section, ~position 4 in the running order. NOT nested under Big Conversation. (Sorting produces Inside Track material, but the segment stands alone.)

### Screenshot submissions + sorting (Instagram DM)
- Weekly workflow: (1) re-run/scrape all Instagram DM screenshots; (2) sort by the THREE QUESTIONS posted to the Friday campaign; (3) organise into THREE FOLDERS; (4) one folder becomes NEXT WEEK's Big Conversation topic, or adds to the topic bank.
- The dashboard should let Victor SEE and ORGANISE the submissions (the AI does the first-pass sort; Victor reviews/adjusts). Displaying the actual screenshot PNGs is worth it IF the AI sorts first (that's the time-saver). Backend = serve the PNGs + a sort endpoint that runs the AI classification; moderate work, real value.
- Sort buckets wanted, at least for the top of each:
  - VIRAL EXTREME (the "wtf, share this" pole - may become the hook)
  - T1 / T2 / T3 (the existing tier system - KEEP these labels, just fix what feeds them)
  - an INTAKE / unsorted holding form, with cards draggable across buckets.
- CRITICAL Big Conversation structure: a chosen topic folder is organised into PARAGRAPHS. Each paragraph pairs a couple of screenshots as its SUPPORTING element, and the EXTREME of that paragraph supports the paragraph being written. So screenshots are grouped BY PARAGRAPH of the Big Conversation piece, not just by tier. The viral extreme may be the hook; the rest are organised per the paragraph/submission they support.

### The Big Conversation section (dashboard behaviour)
- The card pops out into the BANK of potential topics (folders sorted but not yet used). Each topic is AI-named from its sorted folder.
- Need an ARCHIVE action to hide a topic already published.
- Click a topic -> its SCREENSHOTS come out (grouped by paragraph, per above) + the ANGLE that will be written -> "Process" -> runs the big-conversation skill on that folder, using past published editions as corpus.
- Do NOT show screenshots at the segment level; only inside a chosen topic. Choosing the topic is done BASED ON the screenshots in each folder.

### Off the Clock
- Currently WRONGLY consolidates Eat/Watch/Read/Wear/Go into one. REBUILD as the 5 SEPARATE categories.
- Sourcing: bias to NICHE small businesses that benefit from coverage, not big outlets (Concrete Playground) that already get mass coverage.

### PS Top Picks (real gap)
- Currently LEAVES OUT the FEATURE STORIES we publish: a feature has no click-link (readers get the full story inline), so it never shows in click data, and the "top clicks" that do show are just the OTHER links in the article, not the feature. We lose most of what people actually engage with.
- Fix: Top Picks must INCLUDE feature stories (not only click-tracked links). Need to scrape ALL of it into a SELECTABLE list, pick as we go, and process/copy into the required previous Flat White format. (Functionality not built yet - this is the FW dash build.)

### Editorial intro — CHANGED AGAIN (this supersedes "last week recap"):
- START with a NEW/BIGGEST NEWS STORY of the week as the OPEN hook (the thing that makes people open the email). THEN reference the Big Conversation, THEN the three things we cover. So: biggest-news hook -> Big Conversation -> 3-item preview. (Update ~/.claude/skills/flat-white-intro/SKILL.md accordingly; confirm exact shape with Victor against a real example.)

## FW mechanics ROUND 4 (14 Jul, from Victor) — screenshot flow, OTC swap, Inside Track

### Big Conversation screenshots — tiers vs paragraphs (do NOT show both)
- The topic BANK/folder is sorted into TIERS (Viral extreme / T1 / T2 / T3). But when the Big Conversation is PROCESSED, the AI should auto-assign the tiered screenshots INTO the relevant PARAGRAPHS of the written piece (check the current big-conversation skill does this; if not, build it to).
- So after processing we do NOT need to see the tiered sort columns - the paragraphs are the primary view (each paragraph shows its paired screenshots).
- The ONLY tier pool we show by default is VIRAL EXTREME - so Victor can check nothing compelling was MISSED from the paragraphs (the viral extreme may be a hook, or a "did we miss this" safety net).
- T1/T2/T3 are HIDDEN by default. Victor only opens them on demand, when he thinks the AI didn't pick compelling enough screenshots for the paragraphs and wants to swap in from the tier pool. So: paragraphs + viral-extreme pool always; T1/T2/T3 behind a "show tier pool" toggle.

### Off the Clock — swap + custom add
- Each of the 5 categories shows ONE picked item, but the AI scraped THREE per category. "Swap" must open the OTHER TWO (the three scraped) to choose from.
- Also allow a CUSTOM add: Victor enters a URL + content, and the dash PROCESSES/writes that category's blurb from it. So each category: picked item + Swap (from 3 scraped) + Add custom (URL+content → generate the write-up).

### The Inside Track — pull from the gossip/redundancy folder
- Inside Track content is SELECTED from the folder of GOSSIP / REDUNDANCY screenshots (the ones the Instagram sort routed out of Big Conversation). The section must show those sorted gossip/redundancy submissions for Victor to select which run. (Same source as the DM sort's gossip routing.)

## FW mechanics ROUND 5 (14 Jul, from Victor)

### Editorial intro — hard dependency
- The intro CANNOT be written until ALL other segments are marked ready. It needs every topic AND the nominated BIG STORY OF THE WEEK (the hook that gets people to open). So: editorial's "Write" is gated/disabled until the rest of the running order is ready, and there must be a way to NOMINATE the big story of the week that becomes the hook.

### Thread of the Week — retire the SCRAPE only, keep the segment + formatting
- We are retiring only the Reddit SCRAPE (it's dead), NOT the segment. The segment stays and still runs.
- Real published format (confirmed from beehiiv_fw_ground_truth.json, "THREAD OF THE WEEK - r/AUSCORP"): an H4 with the thread TITLE as a bold-italic HYPERLINK to the reddit thread, then the post PREVIEW/excerpt, then a TOP COMMENT quoted (italic in a quote). e.g. `#### [_**Thread title**_](reddit-url)` + preview paragraphs + a quoted top comment.
- Workflow: Victor PASTES the thread content (title + url + preview + top comment) into the Thread of the Week section; the dash FORMATS it into that block (hyperlinked title + preview + top comment) so it marks ready and can be inserted into the FW draft. Do NOT show a "retire segment" action - the segment is kept.

### UI
- The left running-order rail should sit on a WHITE CARD background (like a proper sidebar panel), not transparent items floating on grey - it looked disjointed.
