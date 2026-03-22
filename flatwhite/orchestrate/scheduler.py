"""Scheduling helpers for the Flat White weekly pipeline.

Generates cron entries and provides the canonical schedule configuration.
Flat White publishes once per week. The default schedule is:
  - Wednesday 06:00 AEST (Tuesday 20:00 UTC) — full pipeline run
  - This gives the editor Wednesday–Thursday to review in Streamlit before
    a Friday morning send.

All times are in UTC for cron compatibility.
"""

import os


SCHEDULE_CONFIG = {
    "pipeline_day": "Wednesday",
    "pipeline_hour_aest": 6,
    "pipeline_hour_utc": 20,
    "pipeline_minute": 0,
    "cron_day_of_week": 2,  # 0=Sunday, 2=Tuesday (UTC day for Wed AEST)
    "review_window_hours": 48,
    "send_day": "Friday",
    "send_hour_aest": 7,
}


def get_schedule_config() -> dict:
    """Return the canonical schedule configuration.

    Output: dict with schedule parameters.
    Consumed by: cli.py cmd_schedule(), documentation.
    """
    return SCHEDULE_CONFIG.copy()


def generate_cron_entry() -> str:
    """Generate the crontab entry for the weekly pipeline run.

    Uses the flatwhite_weekly.sh wrapper script which:
    1. Activates the virtualenv (if present).
    2. Runs `flatwhite run` (steps 1-5, stops for editor review).
    3. Logs output to data/logs/.

    Output: string containing a single crontab line.
    Consumed by: cli.py cmd_schedule().
    """
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    script_path = os.path.join(project_dir, "cron", "flatwhite_weekly.sh")

    minute = SCHEDULE_CONFIG["pipeline_minute"]
    hour = SCHEDULE_CONFIG["pipeline_hour_utc"]
    dow = SCHEDULE_CONFIG["cron_day_of_week"]

    return f"{minute} {hour} * * {dow} {script_path} >> {project_dir}/data/logs/cron.log 2>&1"
