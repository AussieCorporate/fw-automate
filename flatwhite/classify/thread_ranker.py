from __future__ import annotations

"""Ranks thread_candidate items for Thread of the Week selection.

Only r/auscorp threads are eligible (subreddit filter in SQL).

Uses Gemini 2.5 Flash (task_type="scoring") to score each thread on 3 dimensions:
relatability, shareability, discussion_quality.

Composite = 0.4 * relatability + 0.4 * shareability + 0.2 * discussion_quality.

For the top 3 ranked threads:
- Fetches top comments from Reddit JSON API
- Generates a 2-3 sentence "Our Take" editorial via Gemini Flash
- Persists top_comments to raw_items.top_comments (JSON)
- Persists our_take to curated_items.our_take

Returns ranked list, highest composite first.
"""

import json

from flatwhite.model_router import route
from flatwhite.classify.prompts import (
    THREAD_RANKING_SYSTEM,
    THREAD_RANKING_PROMPT,
    THREAD_OUR_TAKE_SYSTEM,
    THREAD_OUR_TAKE_PROMPT,
)
from flatwhite.classify.utils import _parse_llm_json
from flatwhite.db import get_connection, get_current_week_iso
from flatwhite.utils.http import fetch_reddit_comments


def rank_thread_candidates() -> list[dict]:
    """Rank all r/auscorp thread_candidate items for the current week via Gemini Flash.

    Action:
    1. Read all curated_items with section='thread_candidate' AND subreddit='auscorp'
       for current week, joined with raw_items for title/body/subreddit/url.
    2. For each candidate, call route(task_type="scoring") with THREAD_RANKING_PROMPT.
    3. Parse with _parse_llm_json(), validate scores 1-5.
    4. Calculate composite = 0.4*relatability + 0.4*shareability + 0.2*discussion_quality.
    5. For top 3 ranked: fetch Reddit comments, generate Our Take, persist both to DB.
    6. Return list sorted by composite descending.

    Output: list of dicts with keys: curated_id, raw_item_id, title, url, subreddit,
            summary, relatability, shareability, discussion_quality, composite,
            editorial_frame, top_comments (list), our_take (str).
    Consumed by: get_thread_of_the_week() in this file, dashboard state.py.
    """
    conn = get_connection()
    week_iso = get_current_week_iso()

    candidates = conn.execute(
        """SELECT ci.id AS curated_id, ci.summary, ci.weighted_composite,
                  ri.id AS raw_item_id, ri.title, ri.body, ri.subreddit, ri.url
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ci.section = 'thread_candidate'
          AND ri.week_iso = ?
          AND ri.subreddit = 'auscorp'
        ORDER BY ci.weighted_composite DESC""",
        (week_iso,),
    ).fetchall()
    conn.close()

    ranked: list[dict] = []

    for candidate in candidates:
        c = dict(candidate)

        prompt = THREAD_RANKING_PROMPT.format(
            title=c["title"],
            body=(c["body"] or "")[:1000],
            subreddit=c["subreddit"] or "auscorp",
        )

        try:
            response = route(
                task_type="scoring",
                prompt=prompt,
                system=THREAD_RANKING_SYSTEM,
            )
        except Exception as e:
            print(f"thread_ranker: scoring failed for '{c['title']}': {e}")
            continue

        scores = _parse_llm_json(response)

        if scores is None or not isinstance(scores, dict):
            continue

        for dim in ("relatability", "shareability", "discussion_quality"):
            val = scores.get(dim, 3)
            if not isinstance(val, (int, float)):
                val = 3
            scores[dim] = max(1, min(5, int(val)))

        composite = round(
            scores["relatability"] * 0.4
            + scores["shareability"] * 0.4
            + scores["discussion_quality"] * 0.2,
            2,
        )

        frame = scores.get("editorial_frame", "")
        if not isinstance(frame, str):
            frame = ""

        ranked.append({
            "curated_id": c["curated_id"],
            "raw_item_id": c["raw_item_id"],
            "title": c["title"],
            "url": c["url"],
            "subreddit": c["subreddit"],
            "body": c["body"],
            "summary": c["summary"],
            "relatability": scores["relatability"],
            "shareability": scores["shareability"],
            "discussion_quality": scores["discussion_quality"],
            "composite": composite,
            "editorial_frame": frame,
            "top_comments": [],
            "our_take": "",
        })

    ranked.sort(key=lambda x: x["composite"], reverse=True)

    # Fallback: if LLM scoring failed for some/all candidates, fill top 3 from
    # classifier's weighted_composite so comments still get fetched.
    if len(ranked) < 3:
        ranked_ids = {r["curated_id"] for r in ranked}
        for candidate in candidates:
            if len(ranked) >= 3:
                break
            c = dict(candidate)
            if c["curated_id"] in ranked_ids:
                continue
            ranked.append({
                "curated_id": c["curated_id"],
                "raw_item_id": c["raw_item_id"],
                "title": c["title"],
                "url": c["url"],
                "subreddit": c["subreddit"],
                "body": c["body"],
                "summary": c["summary"],
                "relatability": 0,
                "shareability": 0,
                "discussion_quality": 0,
                "composite": c["weighted_composite"],
                "editorial_frame": "",
                "top_comments": [],
                "our_take": "",
            })
        print(f"thread_ranker: LLM scored {len(ranked_ids)}/{len(candidates)} candidates, "
              f"filled to {len(ranked)} using classifier fallback")

    # For top 3: fetch comments and generate Our Take, persist to DB
    conn = get_connection()
    try:
        for item in ranked[:3]:
            # Fetch top comments from Reddit (returns dict with post_score and comments)
            result = {"post_score": 0, "comments": []}
            if item["url"]:
                try:
                    result = fetch_reddit_comments(item["url"])
                except Exception as e:
                    print(f"thread_ranker: comment fetch failed for {item['url']}: {e}")
            comments = result.get("comments", [])

            # Persist top_comments to raw_items
            conn.execute(
                "UPDATE raw_items SET top_comments = ? WHERE id = ?",
                (json.dumps(comments), item["raw_item_id"]),
            )

            # Generate Our Take via LLM
            comment_texts = [c["text"] for c in comments] if comments else []
            our_take = ""
            try:
                take_prompt = THREAD_OUR_TAKE_PROMPT.format(
                    title=item["title"],
                    body=(item["body"] or "")[:500],
                    top_comments="\n".join(f"- {c}" for c in comment_texts) if comment_texts else "(no comments available)",
                    editorial_frame=item["editorial_frame"],
                )
                our_take = route(
                    task_type="editorial",
                    prompt=take_prompt,
                    system=THREAD_OUR_TAKE_SYSTEM,
                ).strip()
            except Exception as e:
                print(f"thread_ranker: Our Take generation failed for '{item['title']}': {e}")
                our_take = item["editorial_frame"]

            # Persist our_take to curated_items
            conn.execute(
                "UPDATE curated_items SET our_take = ? WHERE id = ?",
                (our_take, item["curated_id"]),
            )

            item["top_comments"] = comments
            item["our_take"] = our_take

        conn.commit()
    finally:
        conn.close()

    return ranked


def get_thread_of_the_week() -> dict | None:
    """Return the highest-ranked r/auscorp thread candidate, or None if none exist.

    Action: Calls rank_thread_candidates() and returns first result.
    Output: Single dict with thread details (see rank_thread_candidates), or None.
    Consumed by: cli.py cmd_classify() (Step 8), assemble/renderer.py _render_thread().
    """
    ranked = rank_thread_candidates()
    if not ranked:
        return None
    return ranked[0]
