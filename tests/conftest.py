"""Shared fixtures for the Flat White integration test suite.

Provides:
- temp_db: empty SQLite DB with full schema (patched DB_PATH).
- populated_db: DB with 10 test signals + 5 test raw_items.
- mock_gemini: patches model_router.route() to return controlled output.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import flatwhite.db as db_module


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a fresh, empty test database with the full schema.

    Patches flatwhite.db.DB_PATH so all DB functions use the temp database.
    The patch is active for the duration of the test.
    """
    db_path = tmp_path / "test_flatwhite.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()
        yield db_path


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """Create a test database pre-loaded with 10 signals and 5 raw_items.

    Signals are inserted for week '2026-W12' with realistic values.
    Raw items cover multiple sources and subreddits.
    """
    db_path = tmp_path / "test_flatwhite_populated.db"
    with patch.object(db_module, "DB_PATH", db_path):
        db_module.init_db()

        week_iso = "2026-W12"

        # 10 Lane A pulse signals
        test_signals = [
            ("job_anxiety", "pulse", "labour_market", 60.0, 40.0, 1.0),
            ("career_mobility", "pulse", "labour_market", 55.0, 55.0, 1.0),
            ("market_hiring", "pulse", "labour_market", 20000.0, 52.0, 1.0),
            ("employer_hiring_breadth", "pulse", "labour_market", 9000.0, 48.0, 1.0),
            ("salary_pressure", "pulse", "labour_market", 115000.0, 55.0, 1.0),
            ("layoff_news_velocity", "pulse", "corporate_stress", 64.0, 45.0, 1.0),
            ("contractor_proxy", "pulse", "corporate_stress", 10.0, 55.0, 1.0),
            ("consumer_confidence", "pulse", "economic", 82.0, 57.0, 1.0),
            ("asx_volatility", "pulse", "economic", 1.2, 60.0, 1.0),
            ("asx_momentum", "pulse", "economic", 2.5, 75.0, 1.0),
        ]
        for name, lane, area, raw, norm, sw in test_signals:
            db_module.insert_signal(name, lane, area, raw, norm, sw, week_iso)

        # 5 Lane B editorial raw_items
        test_items = [
            (
                "Big 4 firm axes 200 roles in advisory",
                "Deloitte is cutting 200 positions in its advisory arm.",
                "reddit_rss",
                "https://reddit.com/r/auscorp/1",
                "editorial",
                "auscorp",
            ),
            (
                "Banks quietly freezing graduate intakes",
                "Multiple banks reducing 2027 grad programs.",
                "reddit_rss",
                "https://reddit.com/r/AusFinance/2",
                "editorial",
                "AusFinance",
            ),
            (
                "ASX CEO pay up 15% while staff get 3%",
                "Analysis of ASX 200 executive pay vs median staff salary.",
                "google_news_editorial",
                "https://example.com/ceo-pay",
                "editorial",
                None,
            ),
            (
                "Is contracting dead in Australia?",
                "Long thread discussing contractor market downturn.",
                "reddit_rss",
                "https://reddit.com/r/auscorp/3",
                "editorial",
                "auscorp",
            ),
            (
                "Heard PwC is doing another round of cuts",
                None,
                "manual_whisper",
                None,
                "editorial",
                None,
            ),
        ]
        for title, body, source, url, lane, subreddit in test_items:
            db_module.insert_raw_item(title, body, source, url, lane, subreddit, week_iso)

        yield db_path


@pytest.fixture
def mock_gemini():
    """Patch model_router.route at every import site to avoid real API calls.

    Patches the route function in model_router and in all modules that do
    'from flatwhite.model_router import route'. The mock is yielded so tests
    can configure return_value or side_effect as needed.
    """
    with (
        patch("flatwhite.model_router.route") as mock_route,
        patch("flatwhite.classify.classifier.route", mock_route),
        patch("flatwhite.pulse.summary.route", mock_route),
    ):
        yield mock_route
