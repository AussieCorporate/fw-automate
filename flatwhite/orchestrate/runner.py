"""End-to-end pipeline orchestrator for Flat White.

Chains all pipeline steps in order:
  ingest → pulse → classify → summarise → angles → assemble

Each step is executed via run_step() which captures timing, status, and errors.
The full pipeline is executed via run_full_pipeline() which returns a JSON-serialisable
run report. Assembly renders HTML locally to data/preview.html.
"""

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from flatwhite.db import get_connection, get_current_week_iso


def get_next_rotation() -> str:
    """Determine the next A/B rotation based on the last published newsletter.

    Logic:
    - Query newsletters table for the most recent entry ordered by week_iso DESC.
    - If no previous newsletter exists, return 'A'.
    - If last rotation was 'A', return 'B'.
    - If last rotation was 'B', return 'A'.

    Output: string, either 'A' or 'B'.
    Consumed by: run_full_pipeline().
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT rotation FROM newsletters ORDER BY week_iso DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return "A"
    return "B" if row["rotation"] == "A" else "A"


def run_step(step_name: str, step_fn: Callable[..., str | None], **kwargs) -> dict:
    """Execute a single pipeline step and capture its outcome.

    Input: step_name (str), step_fn (callable that returns a detail string or None).
    Output: dict with keys: name, status, duration_seconds, detail.

    If step_fn raises an exception, status is 'fail' and detail contains the error message.
    If step_fn returns None, detail is set to 'OK'.
    """
    start = time.time()
    try:
        detail = step_fn(**kwargs)
        elapsed = round(time.time() - start, 1)
        return {
            "name": step_name,
            "status": "pass",
            "duration_seconds": elapsed,
            "detail": detail if detail else "OK",
        }
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {
            "name": step_name,
            "status": "fail",
            "duration_seconds": elapsed,
            "detail": str(e),
        }


def run_full_pipeline(skip_assemble: bool = True) -> dict:
    """Execute the complete Flat White pipeline end-to-end.

    Steps executed in order:
    1. ingest    — pull all data sources (Lane A + Lane B)
    2. pulse     — calculate AusCorp Live Pulse score
    3. classify  — classify editorial items + rank threads
    4. summarise — generate summary, drivers, hooks
    5. angles    — generate Big Conversation angles
    6. assemble  — build newsletter HTML locally (skipped by default)

    By default, the pipeline stops after step 5 (angles). This is because step 6
    requires the editor to review and approve items in the dashboard first.
    Pass skip_assemble=False to include the assemble step.

    Recommended workflow:
      flatwhite run                          # Steps 1-5 only (default)
      <editor reviews in dashboard>
      flatwhite assemble --hook 'text'       # Step 6 separately
      flatwhite run --assemble               # Or steps 1-6 if items already approved

    Input:
    - skip_assemble (bool): If True, skip the assemble step. Default True.

    Output: dict containing full run report (see Section 3.1).
    Consumed by: cli.py cmd_run().
    """
    week_iso = get_current_week_iso()
    rotation = get_next_rotation()
    started_at = datetime.now(timezone.utc).isoformat()

    steps: list[dict] = []

    # ── Step 1: Ingest ────────────────────────────────────────────────────────

    def _ingest() -> str:
        from flatwhite.db import init_db
        init_db()

        from flatwhite.signals.google_trends import pull_all_google_trends
        gt = pull_all_google_trends()

        from flatwhite.signals.market_hiring import pull_market_hiring
        pull_market_hiring()

        from flatwhite.signals.hiring_pulse import pull_hiring_pulse
        pull_hiring_pulse()

        from flatwhite.signals.salary_pressure import pull_salary_pressure
        pull_salary_pressure()

        from flatwhite.signals.news_velocity import pull_layoff_news_velocity
        pull_layoff_news_velocity()

        from flatwhite.signals.consumer_confidence import pull_consumer_confidence
        pull_consumer_confidence()

        from flatwhite.signals.asx_volatility import pull_asx_volatility
        pull_asx_volatility()

        from flatwhite.signals.asx_momentum import pull_asx_momentum
        pull_asx_momentum()

        from flatwhite.signals.indeed_hiring import pull_indeed_hiring
        pull_indeed_hiring()

        from flatwhite.signals.asic_insolvency import pull_asic_insolvency
        pull_asic_insolvency()

        from flatwhite.signals.resume_anxiety import pull_resume_anxiety
        pull_resume_anxiety()

        from flatwhite.editorial.reddit_rss import pull_reddit_editorial
        reddit_count = pull_reddit_editorial()

        from flatwhite.editorial.google_news_editorial import pull_google_news_editorial
        news_count = pull_google_news_editorial()

        from flatwhite.signals.reddit_topic_velocity import pull_reddit_topic_velocity
        pull_reddit_topic_velocity()

        from flatwhite.signals.auslaw_velocity import pull_auslaw_velocity
        pull_auslaw_velocity()

        signal_count = len(gt) + 11  # gt dict + 11 individual signals
        return f"{signal_count} signals, {reddit_count + news_count} editorial items"

    steps.append(run_step("ingest", _ingest))

    # ── Step 2: Pulse ─────────────────────────────────────────────────────────

    def _pulse() -> str:
        from flatwhite.pulse.composite import calculate_pulse
        result = calculate_pulse()
        arrow = {"up": "↑", "down": "↓", "stable": "→"}[result["direction"]]
        return f"Pulse: {result['smoothed']:.0f} {arrow} {result['direction']}"

    steps.append(run_step("pulse", _pulse))

    # ── Step 3: Classify ──────────────────────────────────────────────────────

    def _classify() -> str:
        from flatwhite.classify.classifier import classify_all_unclassified
        count = classify_all_unclassified()

        from flatwhite.classify.thread_ranker import get_thread_of_the_week
        thread = get_thread_of_the_week()
        thread_msg = f", thread: {thread['title'][:40]}..." if thread else ", no thread"
        return f"{count} items classified{thread_msg}"

    steps.append(run_step("classify", _classify))

    # ── Step 4: Summarise ─────────────────────────────────────────────────────

    def _summarise() -> str:
        from flatwhite.pulse.summary import (
            generate_pulse_summary,
            generate_driver_bullets,
            generate_top_line_hooks,
        )
        summary = generate_pulse_summary()
        drivers = generate_driver_bullets()
        hooks = generate_top_line_hooks()
        return f"Summary ({len(summary)} chars), {len(drivers)} drivers, {len(hooks)} hooks"

    steps.append(run_step("summarise", _summarise))

    # ── Step 5: Angles ────────────────────────────────────────────────────────

    def _angles() -> str:
        from flatwhite.classify.big_conversation import generate_angles
        angles = generate_angles()
        return f"{len(angles)} angles generated"

    steps.append(run_step("angles", _angles))

    # ── Step 6: Assemble ──────────────────────────────────────────────────────

    if not skip_assemble:
        def _assemble() -> str:
            from flatwhite.assemble.renderer import render_newsletter
            from flatwhite.pulse.summary import generate_top_line_hooks
            from pathlib import Path

            hooks = generate_top_line_hooks()
            hook_text = hooks[0] if hooks else "Here's what's moving through the corridors this week."

            html = render_newsletter(hook_text, rotation)

            # Write preview file
            preview_path = Path(__file__).parent.parent.parent / "data" / "preview.html"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_text(f"<!DOCTYPE html><html><body>{html}</body></html>")

            return f"HTML written ({len(html)} chars)"

        steps.append(run_step("assemble", _assemble))
    else:
        steps.append({
            "name": "assemble",
            "status": "skip",
            "duration_seconds": 0,
            "detail": "Skipped — run editor review first, then use flatwhite assemble",
        })

    # ── Build run report ──────────────────────────────────────────────────────

    completed_at = datetime.now(timezone.utc).isoformat()
    has_failure = any(s["status"] == "fail" for s in steps)

    # If a step fails, mark all subsequent non-executed steps as 'skip'
    failed = False
    for step in steps:
        if failed and step["status"] != "skip":
            step["status"] = "skip"
            step["detail"] = "Skipped due to prior failure"
        if step["status"] == "fail":
            failed = True

    run_report = {
        "week_iso": week_iso,
        "rotation": rotation,
        "started_at": started_at,
        "steps": steps,
        "completed_at": completed_at,
        "overall_status": "fail" if has_failure else "pass",
    }

    return run_report
