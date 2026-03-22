from __future__ import annotations

"""Classifies raw editorial items using Gemini 2.5 Flash via model_router.

Each item receives:
- A section assignment
- 5-dimension scores (relevance, novelty, reliability, tension, usefulness)
- A weighted composite score
- A confidence tag (whisper items only)
- A rewritten summary in Flat White tone
- Tags

Items classified as 'discard' are marked as classified=1 in raw_items
but are NOT inserted into curated_items.

Items where the LLM call fails are marked as classified=1 in raw_items
but are NOT inserted into curated_items.
"""

import json
import time
from flatwhite.model_router import route
from flatwhite.classify.prompts import CLASSIFICATION_SYSTEM, CLASSIFICATION_PROMPT
from flatwhite.classify.utils import _parse_llm_json, _calculate_weighted_composite
from flatwhite.db import get_connection, get_current_week_iso


VALID_SECTIONS: set[str] = {
    "whisper",
    "big_conversation_seed",
    "what_we_watching",
    "thread_candidate",
    "finds",
    "discard",
}


def classify_single_item(raw_item: dict) -> dict | None:
    """Classify one raw_item dict via Gemini 2.5 Flash.

    Input: dict with keys: id, title, body, source, url (from raw_items table).
    Output: validated dict matching Schema 3.1 + weighted_composite, or None on failure.
    Consumed by: classify_all_unclassified() in this file.

    Processing:
    1. Format CLASSIFICATION_PROMPT with item fields (body truncated to 1500 chars).
    2. Call route(task_type="classification") -> Gemini Flash.
    3. Parse response with _parse_llm_json().
    4. Validate and clamp all fields.
    5. Return validated dict, or None if parsing failed.
    """
    prompt = CLASSIFICATION_PROMPT.format(
        title=raw_item["title"],
        body=(raw_item["body"] or "")[:1500],
        source=raw_item["source"],
        url=raw_item["url"] or "",
    )

    try:
        response = route(
            task_type="classification",
            prompt=prompt,
            system=CLASSIFICATION_SYSTEM,
        )
    except Exception:
        return None

    result = _parse_llm_json(response)

    if result is None or not isinstance(result, dict):
        return None

    # Validate section — default to discard if invalid
    section = result.get("section", "discard")
    if section not in VALID_SECTIONS:
        section = "discard"
    result["section"] = section

    # Validate and clamp dimension scores to integers 1-5
    for dim in ("relevance", "novelty", "reliability", "tension", "usefulness"):
        val = result.get(dim, 3)
        if not isinstance(val, (int, float)):
            val = 3
        result[dim] = max(1, min(5, int(val)))

    # Calculate weighted composite
    result["weighted_composite"] = _calculate_weighted_composite(result)

    # Auto-discard items with very low composite scores or low relevance
    if section == "whisper":
        # Whispers get a lower floor but still need minimum quality
        if result["weighted_composite"] < 2.0 or result["relevance"] < 2 or result["tension"] < 2:
            result["section"] = "discard"
            section = "discard"
    elif result["weighted_composite"] < 2.5 or result["relevance"] < 3:
        result["section"] = "discard"
        section = "discard"

    # Validate confidence_tag — only whisper items get tags
    conf = result.get("confidence_tag")
    if conf not in ("green", "yellow", "red", None, "null"):
        conf = None
    if conf == "null":
        conf = None
    if section != "whisper":
        conf = None
    result["confidence_tag"] = conf

    # Validate summary — fallback to title if missing or too short
    summary = result.get("summary")
    if not isinstance(summary, str) or len(summary) < 5:
        summary = raw_item["title"]
    result["summary"] = summary

    # Validate tags — must be a list of strings
    tags = result.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    result["tags"] = [str(t) for t in tags]

    return result


BATCH_CLASSIFICATION_SYSTEM = (
    "You are a content classifier for Flat White, a weekly newsletter for "
    "Australian corporate professionals. You classify items into newsletter "
    "sections and score them on 5 dimensions. Output valid JSON only. "
    "No markdown fences. No explanation. No preamble."
)

BATCH_CLASSIFICATION_PROMPT = (
    "Classify each of the following content items for the Flat White newsletter.\n"
    "\n"
    "ITEMS:\n"
    "{items_block}\n"
    "\n"
    "IMPORTANT RULES:\n"
    "- The source (reddit_rss, google_news_editorial, etc.) must NOT determine the section. "
    "A Reddit post can be a whisper, finds, what_we_watching, or discard. "
    "A news article can be a thread_candidate or discard. Judge by CONTENT, not source.\n"
    "- Be aggressive with discard. At least 20-30% of items should be discarded. "
    "If in doubt, discard.\n"
    "- Be strict with scores. A score of 5 should be rare (top 5% of items). "
    "Most items should score 2-3 on most dimensions. Only genuinely exceptional items "
    "score 4-5 on relevance or tension.\n"
    "- If relevance is 1 or 2, the item MUST be classified as discard.\n"
    "\n"
    "SECTIONS (choose exactly one per item):\n"
    "- whisper: insider chatter, rumours, or unconfirmed corporate intel about a SPECIFIC company\n"
    "- big_conversation_seed: genuinely significant topic for 200-300 word editorial commentary\n"
    "- what_we_watching: emerging topics, weak signals, issues gaining traction\n"
    "- thread_candidate: relatable personal community discussion with real workplace experiences\n"
    "- finds: lifestyle products, tools, apps, books, podcasts useful for corporate professionals\n"
    "- discard: not relevant, too old, too generic, too niche, or low quality\n"
    "\n"
    "SCORES (rate each 1-5 per item — be strict, most items should score 2-3):\n"
    "- relevance, novelty, reliability, tension, usefulness\n"
    "\n"
    "CONFIDENCE TAG (for whisper items only, null for all other sections):\n"
    "- green: confirmed / yellow: single credible report / red: unverified\n"
    "\n"
    "SUMMARY: Rewrite each item as a 1-2 sentence newsletter snippet. "
    "Voice: dry, observant, Australian corporate commentary. Calm, confident, slightly wry. "
    "No theatrical setups, no signposting phrases, no filler intensifiers. Australian English.\n"
    "\n"
    "Output a JSON array with one object per item, in the SAME ORDER as the items above.\n"
    "Each object must have these exact keys:\n"
    "section, relevance, novelty, reliability, tension, usefulness, confidence_tag, summary, tags\n"
    "\n"
    "Output ONLY the JSON array. Nothing else."
)


def _validate_single_result(result: dict, raw_item: dict) -> dict:
    """Validate and clamp a single classification result dict.

    Applies the same validation logic as classify_single_item.
    Returns the validated result dict.
    """
    # Validate section
    section = result.get("section", "discard")
    if section not in VALID_SECTIONS:
        section = "discard"
    result["section"] = section

    # Validate and clamp dimension scores
    for dim in ("relevance", "novelty", "reliability", "tension", "usefulness"):
        val = result.get(dim, 3)
        if not isinstance(val, (int, float)):
            val = 3
        result[dim] = max(1, min(5, int(val)))

    # Calculate weighted composite
    result["weighted_composite"] = _calculate_weighted_composite(result)

    # Auto-discard low-quality items
    if section == "whisper":
        if result["weighted_composite"] < 2.0 or result["relevance"] < 2 or result["tension"] < 2:
            result["section"] = "discard"
            section = "discard"
    elif result["weighted_composite"] < 2.5 or result["relevance"] < 3:
        result["section"] = "discard"
        section = "discard"

    # Validate confidence_tag
    conf = result.get("confidence_tag")
    if conf not in ("green", "yellow", "red", None, "null"):
        conf = None
    if conf == "null":
        conf = None
    if section != "whisper":
        conf = None
    result["confidence_tag"] = conf

    # Validate summary
    summary = result.get("summary")
    if not isinstance(summary, str) or len(summary) < 5:
        summary = raw_item["title"]
    result["summary"] = summary

    # Validate tags
    tags = result.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    result["tags"] = [str(t) for t in tags]

    return result


def classify_batch(items: list[dict], batch_size: int = 8) -> list[dict | None]:
    """Classify a list of raw_item dicts in batches via a single Gemini call per batch.

    Groups items into batches of batch_size. For each batch, sends all items in one
    Gemini call and parses the response as a JSON array. If parsing fails for a batch,
    falls back to classify_single_item() for each item in that batch.

    Sleeps 2 seconds between batches to avoid rate limits.

    Returns a list of validated result dicts (or None for failed items), one per input item.
    """
    all_results: list[dict | None] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start:batch_start + batch_size]

        if batch_start > 0:
            time.sleep(2)

        # Build numbered items block
        items_block_lines: list[str] = []
        for i, item in enumerate(batch, 1):
            items_block_lines.append(
                f"[{i}] Title: {item['title']}\n"
                f"    Body: {(item['body'] or '')[:1500]}\n"
                f"    Source: {item['source']}\n"
                f"    URL: {item['url'] or ''}"
            )
        items_block = "\n\n".join(items_block_lines)

        prompt = BATCH_CLASSIFICATION_PROMPT.format(items_block=items_block)

        batch_results: list[dict | None] | None = None
        try:
            response = route(
                task_type="classification",
                prompt=prompt,
                system=BATCH_CLASSIFICATION_SYSTEM,
            )
            parsed = _parse_llm_json(response)

            if isinstance(parsed, list) and len(parsed) == len(batch):
                batch_results = []
                for idx, result in enumerate(parsed):
                    if isinstance(result, dict):
                        validated = _validate_single_result(result, batch[idx])
                        batch_results.append(validated)
                    else:
                        batch_results.append(None)
            else:
                batch_results = None
        except Exception:
            batch_results = None

        # Fallback: if batch parsing failed, classify individually
        if batch_results is None:
            print(f"  Batch parse failed — falling back to per-item classification")
            batch_results = []
            for item in batch:
                result = classify_single_item(item)
                batch_results.append(result)

        all_results.extend(batch_results)

    return all_results


def classify_all_unclassified() -> dict:
    """Classify all unclassified Lane B (editorial) raw_items for the current week.

    Action:
    1. Read all raw_items WHERE classified=0 AND lane='editorial' AND week_iso=current.
    2. Filter out items that already have curated entries (duplicate guard).
    3. Classify items in batches using classify_batch() for efficiency.
    4. If result is None (LLM failed): set classified=1 in raw_items. Do NOT insert curated_items.
    5. If result section is 'discard': set classified=1 in raw_items. Do NOT insert curated_items.
    6. Otherwise: INSERT into curated_items with all fields. Set classified=1 in raw_items.

    Output stored in: curated_items table, raw_items.classified flag.
    Consumed by: cli.py cmd_classify() (Step 8).
    Returns: dict with keys: total, curated, discarded, failed, skipped,
             discarded_items (list of titles), failed_items (list of titles).
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    unclassified = conn.execute(
        "SELECT * FROM raw_items WHERE classified = 0 AND lane = 'editorial' AND week_iso = ?",
        (week_iso,),
    ).fetchall()
    conn.close()

    stats: dict = {
        "total": 0,
        "curated": 0,
        "discarded": 0,
        "failed": 0,
        "skipped": 0,
        "discarded_items": [],
        "failed_items": [],
    }

    # First pass: filter out already-curated items and build the batch list
    items_to_classify: list[dict] = []
    for item in unclassified:
        item_dict = dict(item)
        stats["total"] += 1

        # Guard: skip if this raw_item already has a curated entry (prevents duplicates)
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM curated_items WHERE raw_item_id = ?",
            (item_dict["id"],),
        ).fetchone()
        conn.close()
        if existing:
            conn = get_connection()
            conn.execute(
                "UPDATE raw_items SET classified = 1 WHERE id = ?",
                (item_dict["id"],),
            )
            conn.commit()
            conn.close()
            stats["skipped"] += 1
            continue

        items_to_classify.append(item_dict)

    if not items_to_classify:
        return stats

    # Classify in batches
    print(f"  Classifying {len(items_to_classify)} items in batches of 8...")
    batch_results = classify_batch(items_to_classify, batch_size=8)

    # Process results
    for item_dict, result in zip(items_to_classify, batch_results):
        conn = get_connection()

        if result is None:
            # LLM call failed — mark classified, do NOT insert into curated_items
            conn.execute(
                "UPDATE raw_items SET classified = 1 WHERE id = ?",
                (item_dict["id"],),
            )
            conn.commit()
            conn.close()
            stats["failed"] += 1
            stats["failed_items"].append(item_dict["title"])
            continue

        if result["section"] == "discard":
            # Discard — mark classified, do NOT insert into curated_items
            conn.execute(
                "UPDATE raw_items SET classified = 1 WHERE id = ?",
                (item_dict["id"],),
            )
            conn.commit()
            conn.close()
            stats["discarded"] += 1
            stats["discarded_items"].append(item_dict["title"])
            continue

        # Valid classification — insert into curated_items and mark classified
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
        conn.execute(
            "UPDATE raw_items SET classified = 1 WHERE id = ?",
            (item_dict["id"],),
        )
        conn.commit()
        conn.close()
        stats["curated"] += 1

    return stats
