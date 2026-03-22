from __future__ import annotations

"""YouTube transcript editorial source — pulls auto-generated transcripts
from Australian business podcast channels, extracts key points via Gemini
Flash, and inserts them as editorial items.

Each channel is configured in config.yaml under youtube_transcripts.channels
with a name, channel_id, and source_tag. Channels with empty channel_ids
are skipped. Falls back to RSS description when transcript is unavailable.
"""

import re
import yaml
from pathlib import Path

from flatwhite.utils.http import fetch_rss
from flatwhite.db import insert_raw_item, get_current_week_iso
from flatwhite.model_router import route
from flatwhite.classify.utils import _parse_llm_json

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"

EXTRACTION_PROMPT = (
    "You are an editorial assistant for Flat White, a weekly newsletter "
    "for Australian corporate professionals (Big 4, law firms, banks, ASX-listed).\n\n"
    "Below is a transcript from an Australian business podcast episode.\n\n"
    "Extract the 3 most newsworthy points that are relevant to Australian "
    "corporate professionals. Focus on hiring, layoffs, corporate strategy, "
    "regulation, workplace culture, and career trends.\n\n"
    "Return ONLY a JSON array with exactly 3 objects, each with:\n"
    '- "headline": a concise headline (max 15 words)\n'
    '- "summary": a 2-3 sentence summary of the point\n\n'
    "If the transcript has fewer than 3 relevant points, return fewer objects.\n"
    "If nothing is relevant, return an empty array [].\n\n"
    "TRANSCRIPT:\n{transcript}"
)


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from a URL.

    Handles:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - URLs with additional query parameters

    Returns None if no video ID can be extracted.
    """
    # Match watch?v= format
    match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    if match:
        return match.group(1)

    # Match youtu.be/ format
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if match:
        return match.group(1)

    return None


def _get_transcript(video_id: str) -> str | None:
    """Fetch auto-generated transcript for a YouTube video.

    Uses youtube_transcript_api to get English transcript segments,
    joins them into a single string, and caps at 8000 characters.

    Returns None on any exception (video has no transcript, is private, etc.).
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt_api = YouTubeTranscriptApi()
        transcript_segments = ytt_api.fetch(video_id, languages=["en"])
        full_text = " ".join(snippet.text for snippet in transcript_segments)
        return full_text[:8000]
    except Exception as e:
        print(f"  Transcript unavailable for {video_id}: {e}")
        return None


def pull_youtube_transcripts() -> int:
    """Pull editorial items from YouTube podcast transcripts.

    For each configured channel:
    1. Fetch YouTube RSS feed
    2. For each video (up to max_episodes_per_channel):
       a. Try to get transcript via _get_transcript()
       b. If transcript exists: extract key points via Gemini and insert each as raw_item
       c. If transcript fails: fall back to RSS description as single raw_item

    Returns count of newly inserted items.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    yt_config = config.get("youtube_transcripts", {})
    if not yt_config.get("enabled", False):
        print("  YouTube transcripts disabled in config")
        return 0

    channels = yt_config.get("channels", [])
    max_episodes = yt_config.get("max_episodes_per_channel", 3)
    week_iso = get_current_week_iso()
    total_inserted = 0

    for channel in channels:
        name = channel.get("name", "unknown")
        channel_id = channel.get("channel_id", "")
        source_tag = channel.get("source_tag", "podcast_unknown")

        # Skip channels with empty or placeholder channel_id
        if not channel_id or channel_id.strip() == "":
            print(f"  SKIP: {name} — no channel_id configured")
            continue

        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            entries = fetch_rss(rss_url, delay_seconds=2.0)
        except Exception as e:
            print(f"  FAILED: {name} RSS fetch: {e}")
            continue

        channel_count = 0
        for entry in entries[:max_episodes]:
            video_url = entry.get("url", "")
            video_title = entry.get("title", "")
            video_id = _extract_video_id(video_url)

            if not video_id:
                # No valid video ID — fall back to RSS description
                insert_raw_item(
                    title=video_title[:200],
                    body=entry.get("body", "")[:2000] if entry.get("body") else None,
                    source=source_tag,
                    url=video_url,
                    lane="editorial",
                    subreddit=None,
                    week_iso=week_iso,
                )
                channel_count += 1
                continue

            transcript = _get_transcript(video_id)

            if transcript:
                # Send to Gemini for extraction
                try:
                    prompt = EXTRACTION_PROMPT.format(transcript=transcript)
                    response = route(task_type="classification", prompt=prompt)
                    parsed = _parse_llm_json(response)

                    if isinstance(parsed, list) and len(parsed) > 0:
                        for point in parsed:
                            headline = point.get("headline", video_title)
                            summary = point.get("summary", "")
                            insert_raw_item(
                                title=f"[{name}] {headline}"[:200],
                                body=summary[:2000] if summary else None,
                                source=source_tag,
                                url=video_url,
                                lane="editorial",
                                subreddit=None,
                                week_iso=week_iso,
                            )
                            channel_count += 1
                    else:
                        # LLM returned empty or unparseable — fall back to RSS description
                        print(f"  No points extracted from {video_title}, using RSS fallback")
                        insert_raw_item(
                            title=video_title[:200],
                            body=entry.get("body", "")[:2000] if entry.get("body") else None,
                            source=source_tag,
                            url=video_url,
                            lane="editorial",
                            subreddit=None,
                            week_iso=week_iso,
                        )
                        channel_count += 1
                except Exception as e:
                    # LLM call failed — fall back to RSS description
                    print(f"  LLM extraction failed for {video_title}: {e}")
                    insert_raw_item(
                        title=video_title[:200],
                        body=entry.get("body", "")[:2000] if entry.get("body") else None,
                        source=source_tag,
                        url=video_url,
                        lane="editorial",
                        subreddit=None,
                        week_iso=week_iso,
                    )
                    channel_count += 1
            else:
                # No transcript — fall back to RSS description
                insert_raw_item(
                    title=video_title[:200],
                    body=entry.get("body", "")[:2000] if entry.get("body") else None,
                    source=source_tag,
                    url=video_url,
                    lane="editorial",
                    subreddit=None,
                    week_iso=week_iso,
                )
                channel_count += 1

        total_inserted += channel_count
        print(f"  YouTube '{name}': {channel_count} items")

    return total_inserted
