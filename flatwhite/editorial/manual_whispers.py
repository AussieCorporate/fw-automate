from flatwhite.db import insert_raw_item, get_current_week_iso

def add_whisper(text: str, confidence: str = "yellow") -> int:
    week_iso = get_current_week_iso()
    row_id = insert_raw_item(
        title=text,
        body=None,
        source="manual_whisper",
        url=None,
        lane="editorial",
        subreddit=None,
        week_iso=week_iso,
    )
    return row_id
