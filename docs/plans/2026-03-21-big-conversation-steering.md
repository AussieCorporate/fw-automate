# Big Conversation Steering & Editing Improvements

**Date:** 2026-03-21
**Status:** Implementing

## Problem

The Big Conversation angle generation is fully automated — editor has no way to steer topics, filter input items, or edit drafts inline. All 3 angles come from the same theme cluster.

## Design

### 1. Topic Steering (UI + Backend)
- Text input with placeholder: "e.g. focus on return-to-office, avoid AI"
- Clickable tag chips below the input (most frequent tags from this week's curated items, deduped)
- Clicking a chip appends it to the text input
- Steering text injected into LLM prompt as `EDITORIAL DIRECTION: {direction}`

### 2. Seed Item Selection (UI + Backend)
- Show all non-discarded curated items for current week, sorted by weighted_composite DESC
- Each item: checkbox (checked by default) + title + source + tags + score
- Select All / Deselect All toggle
- Only checked items sent to LLM for angle generation

### 3. Diverse Themes (Backend)
- Prompt changed from "single strongest theme" to "2 angles from strongest theme + 1 wildcard from a different theme"
- Each angle gets a `theme` field (short label) displayed as a chip on the angle card

### 4. Draft Editing (UI)
- Draft renders in editable textarea (styled to match current serif display)
- Word count updates live as you type
- Save Draft saves textarea content (including manual edits)
- Regenerate replaces textarea content

### 5. Draft Word Count (Backend)
- Draft prompt changes from "200-300 words" to "approximately 300 words"

## Files Modified

- `flatwhite/classify/prompts.py` — angles prompt + draft prompt
- `flatwhite/classify/big_conversation.py` — generate_angles() signature + item filtering
- `flatwhite/dashboard/api.py` — /api/generate-angles accepts body, new /api/seed-tags endpoint
- `flatwhite/dashboard/static/index.html` — steering UI, seed selection, editable draft, theme chips
