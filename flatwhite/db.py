from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_default_db_dir = Path(__file__).parent.parent / "data"
DB_PATH = Path(os.environ.get("FLATWHITE_DB_DIR", str(_default_db_dir))) / "flatwhite.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name TEXT NOT NULL,
    lane TEXT NOT NULL CHECK (lane IN ('pulse', 'editorial')),
    area TEXT NOT NULL CHECK (area IN ('labour_market', 'corporate_stress', 'economic')),
    raw_value REAL NOT NULL,
    normalised_score REAL NOT NULL CHECK (normalised_score >= 0 AND normalised_score <= 100),
    source_weight REAL NOT NULL DEFAULT 1.0,
    pulled_at TEXT NOT NULL,
    week_iso TEXT NOT NULL,
    UNIQUE(signal_name, week_iso)
);

CREATE TABLE IF NOT EXISTS pulse_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL UNIQUE,
    composite_score REAL NOT NULL CHECK (composite_score >= 0 AND composite_score <= 100),
    smoothed_score REAL NOT NULL CHECK (smoothed_score >= 0 AND smoothed_score <= 100),
    direction TEXT NOT NULL CHECK (direction IN ('up', 'down', 'stable')),
    drivers_json TEXT NOT NULL,
    summary_text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pulse_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    severity REAL NOT NULL,
    signals_involved TEXT NOT NULL,
    narrative TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_iso, pattern_name)
);

CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT,
    source TEXT NOT NULL,
    url TEXT,
    lane TEXT NOT NULL CHECK (lane IN ('pulse', 'editorial')),
    subreddit TEXT,
    pulled_at TEXT NOT NULL,
    week_iso TEXT NOT NULL,
    classified INTEGER NOT NULL DEFAULT 0,
    UNIQUE(title, source, week_iso)
);

CREATE TABLE IF NOT EXISTS curated_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_item_id INTEGER NOT NULL UNIQUE REFERENCES raw_items(id),
    section TEXT NOT NULL CHECK (section IN (
        'whisper', 'big_conversation_seed', 'what_we_watching',
        'thread_candidate', 'finds', 'discard'
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
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS editor_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    curated_item_id INTEGER NOT NULL REFERENCES curated_items(id),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected', 'reserve')),
    section_placed TEXT,
    click_rate REAL,
    issue_week_iso TEXT,
    decided_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS newsletters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL UNIQUE,
    beehiiv_post_id TEXT,
    rotation TEXT NOT NULL CHECK (rotation IN ('A', 'B')),
    published_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS employer_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_name TEXT NOT NULL UNIQUE,
    sector TEXT NOT NULL CHECK (sector IN (
        'big4', 'law', 'banking', 'tech', 'consulting',
        'insurance', 'resources', 'infrastructure', 'telco',
        'aviation', 'pharma', 'retail', 'super', 'government'
    )),
    careers_url TEXT NOT NULL,
    css_selector TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    ats_platform TEXT DEFAULT 'unknown',
    ats_endpoint TEXT,
    extraction_method TEXT DEFAULT 'html_scrape',
    country_filter TEXT,
    corporate_only INTEGER DEFAULT 0,
    seek_slug TEXT,
    consecutive_carry_forward_weeks INTEGER DEFAULT 0,
    last_successful_pull TEXT
);

CREATE TABLE IF NOT EXISTS employer_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES employer_watchlist(id),
    open_roles_count INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL,
    week_iso TEXT NOT NULL,
    extraction_method TEXT DEFAULT 'html_scrape',
    ats_platform TEXT DEFAULT 'unknown',
    new_roles_count INTEGER DEFAULT 0,
    stale_roles_count INTEGER DEFAULT 0,
    junior_count INTEGER DEFAULT 0,
    mid_count INTEGER DEFAULT 0,
    senior_count INTEGER DEFAULT 0,
    executive_count INTEGER DEFAULT 0,
    UNIQUE(employer_id, week_iso)
);

CREATE TABLE IF NOT EXISTS employer_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES employer_watchlist(id),
    title TEXT NOT NULL,
    location TEXT,
    department TEXT,
    seniority_bucket TEXT CHECK (seniority_bucket IN ('junior', 'mid', 'senior', 'executive', 'unknown')),
    posted_date TEXT,
    role_url TEXT,
    first_seen_week TEXT NOT NULL,
    last_seen_week TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    dedup_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS extraction_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES employer_watchlist(id),
    week_iso TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    ats_platform TEXT,
    roles_extracted INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    latency_ms INTEGER,
    pulled_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(employer_id, week_iso)
);

CREATE TABLE IF NOT EXISTS reddit_topic_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    topic_label TEXT NOT NULL,
    subreddit TEXT NOT NULL,
    post_count INTEGER NOT NULL,
    baseline_median REAL,
    velocity_score REAL NOT NULL,
    is_anomaly INTEGER NOT NULL DEFAULT 0,
    UNIQUE(topic_label, subreddit, week_iso)
);

CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL,
    week_iso TEXT NOT NULL,
    results_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_iso TEXT NOT NULL,
    section TEXT NOT NULL CHECK (section IN ('big_conversation', 'hook', 'custom')),
    headline TEXT,
    pitch TEXT,
    supporting_item_ids TEXT,
    draft_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'discarded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate_db() -> None:
    """Add columns introduced after initial schema creation.

    Safe to re-run: silently skips columns that already exist.
    Called automatically by init_db().
    """
    conn = get_connection()

    # v1 migrations
    simple_migrations = [
        "ALTER TABLE raw_items ADD COLUMN top_comments TEXT",
        "ALTER TABLE curated_items ADD COLUMN our_take TEXT",
        "ALTER TABLE curated_items ADD COLUMN au_relevance INTEGER",
    ]
    for sql in simple_migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # v2 employer_watchlist: recreate with expanded sector CHECK + new columns
    # Only runs if ats_platform column is absent (existing databases)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(employer_watchlist)").fetchall()}
    if "ats_platform" not in cols:
        # Disable FK checks for the duration of the table recreation
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DROP TABLE IF EXISTS employer_watchlist_new")
        conn.execute("""
            CREATE TABLE employer_watchlist_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_name TEXT NOT NULL UNIQUE,
                sector TEXT NOT NULL CHECK (sector IN (
                    'big4', 'law', 'banking', 'tech', 'consulting',
                    'insurance', 'resources', 'infrastructure', 'telco',
                    'aviation', 'pharma', 'retail', 'super', 'government'
                )),
                careers_url TEXT NOT NULL,
                css_selector TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                ats_platform TEXT DEFAULT 'unknown',
                ats_endpoint TEXT,
                extraction_method TEXT DEFAULT 'html_scrape',
                country_filter TEXT,
                corporate_only INTEGER DEFAULT 0,
                seek_slug TEXT,
                consecutive_carry_forward_weeks INTEGER DEFAULT 0,
                last_successful_pull TEXT
            )
        """)
        conn.execute("""
            INSERT INTO employer_watchlist_new
                (id, employer_name, sector, careers_url, css_selector, active)
            SELECT id, employer_name, sector, careers_url, css_selector, active
            FROM employer_watchlist
        """)
        conn.execute("DROP TABLE employer_watchlist")
        conn.execute("ALTER TABLE employer_watchlist_new RENAME TO employer_watchlist")
        conn.execute("PRAGMA foreign_keys=ON")

    # v2 employer_snapshots: add enriched columns
    snap_cols = {row[1] for row in conn.execute("PRAGMA table_info(employer_snapshots)").fetchall()}
    snapshot_migrations = [
        ("extraction_method", "ALTER TABLE employer_snapshots ADD COLUMN extraction_method TEXT DEFAULT 'html_scrape'"),
        ("ats_platform", "ALTER TABLE employer_snapshots ADD COLUMN ats_platform TEXT DEFAULT 'unknown'"),
        ("new_roles_count", "ALTER TABLE employer_snapshots ADD COLUMN new_roles_count INTEGER DEFAULT 0"),
        ("stale_roles_count", "ALTER TABLE employer_snapshots ADD COLUMN stale_roles_count INTEGER DEFAULT 0"),
        ("junior_count", "ALTER TABLE employer_snapshots ADD COLUMN junior_count INTEGER DEFAULT 0"),
        ("mid_count", "ALTER TABLE employer_snapshots ADD COLUMN mid_count INTEGER DEFAULT 0"),
        ("senior_count", "ALTER TABLE employer_snapshots ADD COLUMN senior_count INTEGER DEFAULT 0"),
        ("executive_count", "ALTER TABLE employer_snapshots ADD COLUMN executive_count INTEGER DEFAULT 0"),
    ]
    for col_name, sql in snapshot_migrations:
        if col_name not in snap_cols:
            conn.execute(sql)

    # Ensure UNIQUE index on employer_snapshots (may be missing on very old DBs)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_employer_snapshots_uniq "
        "ON employer_snapshots(employer_id, week_iso)"
    )

    # v2 new tables: employer_roles and extraction_health
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employer_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id INTEGER NOT NULL REFERENCES employer_watchlist(id),
            title TEXT NOT NULL,
            location TEXT,
            department TEXT,
            seniority_bucket TEXT CHECK (seniority_bucket IN ('junior', 'mid', 'senior', 'executive', 'unknown')),
            posted_date TEXT,
            role_url TEXT,
            first_seen_week TEXT NOT NULL,
            last_seen_week TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            dedup_key TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS extraction_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id INTEGER NOT NULL REFERENCES employer_watchlist(id),
            week_iso TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            ats_platform TEXT,
            roles_extracted INTEGER NOT NULL DEFAULT 0,
            success INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            latency_ms INTEGER,
            pulled_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(employer_id, week_iso)
        )
    """)

    conn.commit()
    conn.close()


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    migrate_db()


def insert_signal(
    signal_name: str,
    lane: str,
    area: str,
    raw_value: float,
    normalised_score: float,
    source_weight: float,
    week_iso: str,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR REPLACE INTO signals
        (signal_name, lane, area, raw_value, normalised_score, source_weight, pulled_at, week_iso)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
        (signal_name, lane, area, raw_value, normalised_score, source_weight, week_iso),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def insert_raw_item(
    title: str,
    body: str | None,
    source: str,
    url: str | None,
    lane: str,
    subreddit: str | None,
    week_iso: str,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO raw_items
        (title, body, source, url, lane, subreddit, pulled_at, week_iso)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
        (title, body, source, url, lane, subreddit, week_iso),
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


def insert_pulse(
    week_iso: str,
    composite_score: float,
    smoothed_score: float,
    direction: str,
    drivers_json: str,
    summary_text: str | None = None,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR REPLACE INTO pulse_history
        (week_iso, composite_score, smoothed_score, direction, drivers_json, summary_text)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (week_iso, composite_score, smoothed_score, direction, drivers_json, summary_text),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def insert_interaction(
    week_iso: str,
    pattern_name: str,
    severity: float,
    signals_involved: str,
    narrative: str,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT OR REPLACE INTO pulse_interactions
        (week_iso, pattern_name, severity, signals_involved, narrative, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (week_iso, pattern_name, severity, signals_involved, narrative),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_interactions(week_iso: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT pattern_name, severity, signals_involved, narrative
        FROM pulse_interactions
        WHERE week_iso = ?
        ORDER BY severity DESC""",
        (week_iso,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_signals(signal_name: str, weeks: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM signals
        WHERE signal_name = ? AND week_iso != ? AND week_iso < '9000'
        ORDER BY week_iso DESC
        LIMIT ?""",
        (signal_name, get_current_week_iso(), weeks),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pulse_history(weeks: int = 12) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM pulse_history
        ORDER BY week_iso DESC
        LIMIT ?""",
        (weeks,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pulse_history_before(week_iso: str, weeks: int = 3) -> list[dict]:
    """Get pulse history for weeks strictly before the given week_iso."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM pulse_history
        WHERE week_iso < ?
        ORDER BY week_iso DESC
        LIMIT ?""",
        (week_iso, weeks),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_current_week_iso() -> str:
    from datetime import date
    d = date.today()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def insert_employer_snapshot(
    employer_id: int,
    open_roles_count: int,
    week_iso: str,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO employer_snapshots
        (employer_id, open_roles_count, snapshot_date, week_iso)
        VALUES (?, ?, date('now'), ?)
        ON CONFLICT(employer_id, week_iso) DO UPDATE SET
            open_roles_count = excluded.open_roles_count,
            snapshot_date = excluded.snapshot_date""",
        (employer_id, open_roles_count, week_iso),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def seed_employer_watchlist(employers: list[dict]) -> None:
    conn = get_connection()
    for emp in employers:
        conn.execute(
            """INSERT INTO employer_watchlist (employer_name, sector, careers_url)
            VALUES (?, ?, ?)
            ON CONFLICT(employer_name) DO UPDATE SET
                careers_url = excluded.careers_url,
                sector = excluded.sector""",
            (emp["name"], emp["sector"], emp["careers_url"]),
        )
    conn.commit()
    conn.close()


def insert_draft(
    week_iso: str,
    section: str,
    draft_text: str,
    headline: str | None = None,
    pitch: str | None = None,
    supporting_item_ids: str | None = None,
    status: str = "draft",
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO drafts
        (week_iso, section, headline, pitch, supporting_item_ids, draft_text, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (week_iso, section, headline, pitch, supporting_item_ids, draft_text, status),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def update_draft_status(draft_id: int, status: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE drafts SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, draft_id),
    )
    conn.commit()
    conn.close()


def get_approved_draft(week_iso: str, section: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM drafts
        WHERE week_iso = ? AND section = ? AND status = 'approved'
        ORDER BY updated_at DESC LIMIT 1""",
        (week_iso, section),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
