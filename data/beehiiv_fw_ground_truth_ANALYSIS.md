# Flat White ground truth: analysis of 10 real published editions (4 May - 6 July 2026)

Source: `beehiiv_fw_ground_truth.json` in this folder. 10/10 editions fetched and parsed cleanly from beehiiv (post_ids and dates as specified). Segment boundaries were taken directly from the `### **HEADER**` markers beehiiv's plain-text export actually contains, so header names below are what shipped, not the skill's idealised names.

## (a) Segment presence across the 10 editions

| Segment | Present in | Avg words | Word range |
|---|---|---|---|
| Editorial intro ("Good morning AusCorp") | 10/10 | 166 | 140-195 |
| THE BIG CONVERSATION | 10/10 | 418 | 299-505 |
| PICK & SCROLL / TOP PICKS (news roundup) | 10/10 | 175 | 58-275 |
| THE INSIDE TRACK (image block) | 10/10 | 91 | 25-219 |
| THREAD OF THE WEEK - r/AUSCORP | 10/10 | 178 | 125-210 |
| AUSCORP STRESS INDEX (the Pulse) | 10/10 | 154 | 94-213 |
| OFF THE CLOCK | 10/10 | 205 | 158-253 |
| AUSCORP EVENTS | 10/10 | 68 | 15-141 |
| ODD PICKS FROM LAST WEEK | 10/10 | 95 | 77-119 |
| FEEDBACK LOOP | 10/10 | 33 | 33-33 (boilerplate, identical every week) |
| THE BRAINS TRUST (economic feature) | 7/10 | 311 | 263-348 |
| MISSED LAST WEEK'S NEWSLETTER (footer link) | 7/10 | 13 | 10-17 |
| 2026 AusCorp Salary Survey (promo block) | 6/10 | 56 | 50-82 |
| Sponsor ("TOGETHER WITH ...") | 6/10 | 122 | 90-159 |
| THE ECONOMIC SCOOP (economic feature, old name) | 3/10 | 327 | 279-375 |

Note: THE BRAINS TRUST and THE ECONOMIC SCOOP are the same slot under two names (see drift below) - combined they run 10/10, confirming the economic feature has appeared in every single edition in this window.

## (b) Per-segment register/format notes

- **Editorial intro**: 2-3 short paragraphs. Opens "Good morning AusCorp." then one strong observation/hook sentence on the lead story, then a paragraph previewing 2-4 other stories in the edition ("In this week's edition, we're..."). Second-person, dry, understated humour. Consistently 140-195 words - tighter than the skill doc implies.
- **THE BIG CONVERSATION**: Longest segment by far (avg 418, up to 505 words). 4-6 paragraphs, each paired with a community screenshot image between them. Bold declarative title as a full stop statement, sometimes with a "#### " subheading variant. Second-person, direct address ("You ask for more money..."), argumentative/persuasive register building to a grounded closing paragraph. Matches the skill's documented format closely - no direct community quoting inside the prose, screenshots carry the voice.
- **PICK & SCROLL / TOP PICKS**: A bulleted list of 4-6 one-line news items, each bolded lead-in + link, followed by a short Pick & Scroll cross-promo blurb ("Flat White lands every week. The news doesn't..."). In the 4 oldest editions (4/11/18/25 May) this cross-promo blurb and the bullet list were TWO separate segments ("PICK & SCROLL...BY THE AUSSIE CORPORATE" then "TOP PICKS FROM LAST WEEK"); from 1 June onward they were merged under one combined header. Register: flat news-brief, third person, no editorialising.
- **THE INSIDE TRACK**: Pure image block (screenshots/photos), no or minimal caption text - hence very low/variable word counts (25-219, where higher counts are outliers from stray caption text). Essentially a visual interlude, not a prose segment.
- **Sponsor ("TOGETHER WITH ...")**: Named sponsor per edition (Spaceship, Sharesight, Kraken rotate). 2 short paragraphs pitching the product, ends in a bold CTA link ("Explore Spaceship Super", "Get started before June 30"). Clearly delineated ad voice, never blended with editorial - matches skill rule.
- **THREAD OF THE WEEK - r/AUSCORP**: A Reddit thread excerpt (question/rant) followed by the top comment in quotes, sometimes with a short added editorial line, then "Read the thread ->" link. Conversational, informal, sweary in places (uncensored quotes from Reddit). Consistent ~125-210 words.
- **THE BRAINS TRUST / THE ECONOMIC SCOOP**: The data-heavy economic feature. 3-5 paragraphs (263-375 words, at the high end of the skill's stated 200-350 word target), 2-3 charts interspersed with bare "Source: ..." captions, analyst quotes attributed inline (UBS, Macquarie, Morgan Stanley, Jarden), third-person explainer register with no "you" - matches skill doc closely. Renamed from "THE ECONOMIC SCOOP" to "THE BRAINS TRUST" partway through the window (see drift below).
- **AUSCORP STRESS INDEX**: A number + delta ("45.5 (+1.0 from last week)"), a standing italic explainer line about what the index tracks, then 1 paragraph of market/hiring commentary. Register shifts between decisive analyst voice and more casual asides. Fairly stable 94-213 words.
- **OFF THE CLOCK**: Lifestyle links under EATING/WATCHING/READING/WEARING/GOING sub-headers (order and count of categories vary edition to edition, e.g. WEARING sometimes appears before GOING or is dropped). Each is a bolded one-line hook + one sentence of wry commentary + link. Consistently light, magazine-style voice.
- **AUSCORP EVENTS**: Bulleted list of upcoming AusCorp social/sport events, often "Coming Soon" placeholders rather than confirmed events. Highly variable length (15-141 words) depending on how many events are confirmed.
- **ODD PICKS FROM LAST WEEK**: A short bulleted list (4-5 items) of quirky/offbeat links, one sentence each, dry deadpan voice.
- **FEEDBACK LOOP**: A single boilerplate sentence with a feedback-form link. Identical wording (33 words) in every edition - the only fully static segment.
- **MISSED LAST WEEK'S NEWSLETTER**: One-line footer link to the prior edition. Present only from 25 May onward.
- **2026 AusCorp Salary Survey (promo)**: Short promo block driving anonymous salary-data submissions. Present only from 1 June onward (explicitly "brought back" that week per the intro text of that edition).

## (c) Structural drift across the 10 weeks

1. **Economic feature renamed mid-window.** "THE ECONOMIC SCOOP" (used 4/11/18 May) became "THE BRAINS TRUST" from 25 May onward and stayed that name through 6 July. Confirms the tac-newsletter-segments skill's note that the published name is "THE BRAINS TRUST" - the skill is current, but the rename happened only ~7 weeks before this snapshot.
2. **PICK & SCROLL cross-promo blurb and the TOP PICKS bullet list merged.** Two separate segments in the 4 oldest editions became one combined segment (one header, bullets then blurb) from 1 June onward.
3. **Salary Survey promo block introduced/reintroduced 1 June.** Absent in the 4 oldest editions, present in all 6 since - the 1 June edition explicitly says "we're bringing back our flagship Salary Survey."
4. **"MISSED LAST WEEK'S NEWSLETTER" footer link introduced 25 May.** Absent in the 3 oldest editions, present in all 7 since.
5. **Sponsor section presence is inconsistent, not fully weekly.** A full "TOGETHER WITH X" content section (not just a logo) appears in only 6/10 editions - missing entirely from 1 June, 25 May, 11 May and 4 May. The 25 May edition has a sponsor logo in the top banner ("Together with" Kraken) but no dedicated sponsor content section further down, so sponsor presence is genuinely patchy week to week, not a fixed weekly slot.
6. **AUSCORP STRESS INDEX position moved.** In the 4 oldest editions (4 May - 25 May) the Stress Index runs right after the intro, near the top. From 1 June onward it moved to its now-familiar position after THE BRAINS TRUST, near the end - i.e. the running order itself shifted partway through the window.
7. **OFF THE CLOCK sub-category set is not fixed.** EATING/WATCHING/READING/WEARING/GOING all appear but in varying order and count (some editions have 4 categories, some 5; WEARING and GOING swap position frequently).

## (d) Surprises versus the skill's documented 13-part structure

- The skill lists 13 numbered segments in a fixed order; the real editions show the running order is not fixed - the Stress Index alone moved position partway through the window, and two segments (Salary Survey, Missed-last-week link) were added mid-stream rather than being present from the start.
- The skill implies one weekly sponsor slot ("TOGETHER WITH <sponsor>"); in practice a full sponsor section appears in only 6 of 10 editions - 4 editions ran with no dedicated sponsor content at all.
- The skill names the economic segment "THE BRAINS TRUST" only; the real corpus shows it was called "THE ECONOMIC SCOOP" as recently as 18 May 2026, i.e. the rename is very recent relative to this snapshot and older automation or prompts referencing "Economic Scoop" would be citing a retired header.
- THE BIG CONVERSATION runs longer in practice (avg 418 words, up to 505) than the skill's "4-5 paragraphs" framing suggests - it is consistently the single longest segment in every edition, more feature-length than the other prose blocks.
- PICK & SCROLL's cross-promo blurb and the news bullet list were originally two distinct segments and were merged into one only from 1 June - anyone building a template from only the most recent editions would miss that this was ever two blocks.
- FEEDBACK LOOP is the only fully invariant segment word-for-word across all 10 editions - useful as a canary: if a generated edition's Feedback Loop text differs from the fixed boilerplate, something upstream has drifted.
