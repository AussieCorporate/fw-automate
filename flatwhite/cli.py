"""Flat White CLI — main entry point for all commands.

Session 1 commands: init, ingest, pulse, add-whisper
Session 2 commands: classify, summarise, angles
Session 3 commands: (Streamlit — no CLI additions)
Session 4 commands: assemble
Session 5 commands: run, status, schedule

Usage: python -m flatwhite.cli <command>
       flatwhite <command>  (if installed via pip install -e .)
"""

import sys
import json
import sqlite3
from flatwhite.db import init_db, get_current_week_iso, get_connection, insert_interaction
from flatwhite.pulse.interactions import evaluate_patterns


def cmd_init() -> None:
    """Initialise the database. Creates all tables if they do not exist."""
    init_db()
    print("Database initialised at data/flatwhite.db")


def _needs_backfill() -> bool:
    """Check if this is a fresh install with no pulse history."""
    from flatwhite.db import get_connection
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM pulse_history").fetchone()
    conn.close()
    return row["cnt"] == 0


def cmd_ingest() -> None:
    """Pull all data sources. Lane A: Pulse signals. Lane B: Editorial sources.

    Runs independent signal groups in parallel for faster execution:
      Group 1 (parallel): Fast Lane A signals
      Group 2 (parallel): Editorial sources
      Group 3 (parallel): Slow signals (Google Trends)
      Group 4 (after 1+2): Derived signals (depend on editorial data)
      Group 5 (after all): Pulse calculation + Classification
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    init_db()

    # Auto-backfill on first run — populates 12 weeks of historical data
    # so anomaly detection and EMA smoothing work from day 1.
    if _needs_backfill():
        print("First ingest detected — backfilling 12 weeks of historical data...\n")
        from flatwhite.pulse.backfill import run_backfill
        run_backfill(weeks=12)
        print()

    pipeline_start = time.time()

    # ── Group 1: Fast Lane A signals ─────────────────────────────────────────
    def _run_group1() -> None:
        g_start = time.time()
        print("=== GROUP 1: Fast Lane A Signals ===")

        from flatwhite.signals.market_hiring import pull_market_hiring
        print("Pulling market hiring (SEEK categories)...")
        mh = pull_market_hiring()
        print(f"  market_hiring: {mh:.1f}")

        from flatwhite.signals.hiring_pulse import pull_hiring_pulse
        print("Pulling Hiring Pulse (33 employers)...")
        hp = pull_hiring_pulse()
        print(f"  employer_hiring_breadth: {hp['breadth_score']:.1f}")
        print(f"  employer_req_freshness: {hp['freshness_score']:.1f}", end="")
        if hp["freshness_in_warmup"]:
            print(" (warmup — excluded from composite)")
        else:
            print()
        print(f"  employer_net_delta: {hp['net_delta_score']:.1f}")
        print(f"  source_weight: {hp['source_weight']:.2f}")
        print(f"  Employers: {hp['employers_successful']}/{hp['employers_tracked']} successful")
        print(f"  Adding: {hp['employers_adding']}, Cutting: {hp['employers_cutting']}, Flat: {hp['employers_flat']}")
        if hp["employers_failed"] > 0:
            print(f"  ⚠ {hp['employers_failed']} employers failed — carry-forward applied")
        if hp["freeze_count"] > 0:
            print(f"  🧊 Freeze Index: {hp['freeze_count']}/{hp['employers_tracked']} with zero roles")
        if hp["breadth_delta_divergence"]:
            print(f"  ⚡ TENSION: Breadth and delta diverge — review individual employer data")
        if hp["biggest_movers_up"]:
            print(f"  📈 Biggest adders:")
            for m in hp["biggest_movers_up"]:
                print(f"    {m['name']}: +{m['delta']} roles ({m['delta_pct']:+.1f}%)")
        if hp["biggest_movers_down"]:
            print(f"  📉 Biggest cutters:")
            for m in hp["biggest_movers_down"]:
                print(f"    {m['name']}: {m['delta']} roles ({m['delta_pct']:+.1f}%)")

        from flatwhite.signals.salary_pressure import pull_salary_pressure
        print("Pulling salary pressure (Adzuna avg salaries)...")
        sp = pull_salary_pressure()
        print(f"  salary_pressure: {sp:.1f}")

        from flatwhite.signals.news_velocity import pull_layoff_news_velocity
        print("Pulling layoff news velocity...")
        news = pull_layoff_news_velocity()
        print(f"  layoff_news_velocity: {news:.1f}")

        from flatwhite.signals.consumer_confidence import pull_consumer_confidence
        print("Pulling consumer confidence...")
        conf = pull_consumer_confidence()
        print(f"  consumer_confidence: {conf:.1f}")

        from flatwhite.signals.asx_volatility import pull_asx_volatility
        print("Pulling ASX volatility...")
        vol = pull_asx_volatility()
        print(f"  asx_volatility: {vol:.1f}")

        from flatwhite.signals.asx_momentum import pull_asx_momentum
        print("Pulling ASX momentum...")
        mom = pull_asx_momentum()
        print(f"  asx_momentum: {mom:.1f}")

        from flatwhite.signals.indeed_hiring import pull_indeed_hiring
        print("Pulling Indeed Hiring Lab...")
        indeed = pull_indeed_hiring()
        print(f"  indeed_job_postings: {indeed['indeed_job_postings']:.1f}")
        print(f"  indeed_remote_pct: {indeed['indeed_remote_pct']:.1f}")

        from flatwhite.signals.asic_insolvency import pull_asic_insolvency
        print("Pulling ASIC insolvency data...")
        asic = pull_asic_insolvency()
        print(f"  asic_insolvency: {asic:.1f}")

        g_elapsed = time.time() - g_start
        print(f"  [Group 1 done in {g_elapsed:.0f}s]")

    # ── Group 2: Editorial sources ───────────────────────────────────────────
    def _run_group2() -> None:
        g_start = time.time()
        print("\n=== GROUP 2: Editorial Sources ===")

        from flatwhite.editorial.reddit_rss import pull_reddit_editorial
        print("Pulling Reddit (r/auscorp, r/AusFinance, r/australia, r/auslaw)...")
        reddit_count = pull_reddit_editorial()
        print(f"  {reddit_count} posts ingested")

        from flatwhite.editorial.google_news_editorial import pull_google_news_editorial
        print("Pulling Google News editorial...")
        news_count = pull_google_news_editorial()
        print(f"  {news_count} articles ingested")

        from flatwhite.editorial.twitter_rss import pull_twitter_editorial
        print("Pulling Twitter/X editorial (secondary — lead indicators)...")
        twitter_count = pull_twitter_editorial()
        print(f"  {twitter_count} tweets ingested")

        from flatwhite.editorial.rss_feeds import pull_rss_feeds
        print("Pulling RSS feeds (think tanks, business media, RBA, courts)...")
        rss_count = pull_rss_feeds()
        print(f"  {rss_count} items from RSS feeds")

        from flatwhite.editorial.linkedin_rss import pull_linkedin_newsletters
        print("Pulling LinkedIn newsletters...")
        li_count = pull_linkedin_newsletters()
        print(f"  {li_count} items from LinkedIn newsletters")

        from flatwhite.editorial.email_ingest import pull_email_newsletters
        print("Pulling email newsletters (AFR, Crikey)...")
        email_count = pull_email_newsletters()
        print(f"  {email_count} items from email newsletters")

        from flatwhite.editorial.youtube_transcripts import pull_youtube_transcripts
        print("Pulling YouTube transcripts (podcasts)...")
        yt_count = pull_youtube_transcripts()
        print(f"  {yt_count} items from YouTube transcripts")

        g_elapsed = time.time() - g_start
        print(f"  [Group 2 done in {g_elapsed:.0f}s]")

    # ── Group 3: Slow signals ────────────────────────────────────────────────
    def _run_group3() -> None:
        g_start = time.time()
        print("\n=== GROUP 3: Slow Signals (Google Trends) ===")

        from flatwhite.signals.google_trends import pull_all_google_trends
        print("Pulling Google Trends (job_anxiety, career_mobility, contractor_proxy)...")
        gt_results = pull_all_google_trends()
        for k, v in gt_results.items():
            print(f"  {k}: {v:.1f}")

        from flatwhite.signals.resume_anxiety import pull_resume_anxiety
        print("Pulling resume anxiety (trip wire)...")
        ra = pull_resume_anxiety()
        print(f"  resume_anxiety: {ra:.1f}")

        g_elapsed = time.time() - g_start
        print(f"  [Group 3 done in {g_elapsed:.0f}s]")

    # ── Run groups 1, 2, 3 in parallel ───────────────────────────────────────
    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(_run_group1)
        f2 = executor.submit(_run_group2)
        f3 = executor.submit(_run_group3)

        # Wait for all to complete and re-raise any exceptions
        f1.result()
        f2.result()
        f3.result()

    # ── Group 4: Derived signals (depend on editorial data from group 2) ─────
    g4_start = time.time()
    print("\n=== GROUP 4: Derived Signals ===")

    from flatwhite.signals.reddit_topic_velocity import pull_reddit_topic_velocity
    print("Analysing Reddit topic velocity...")
    rtv = pull_reddit_topic_velocity()
    print(f"  reddit_topic_velocity: {rtv:.1f}")

    from flatwhite.signals.auslaw_velocity import pull_auslaw_velocity
    print("Analysing r/auslaw legal velocity...")
    alv = pull_auslaw_velocity()
    print(f"  auslaw_velocity: {alv:.1f}")

    g4_elapsed = time.time() - g4_start
    print(f"  [Group 4 done in {g4_elapsed:.0f}s]")

    # ── Group 5: Pulse + Classification (depend on all prior groups) ─────────
    g5_start = time.time()
    print("\n=== GROUP 5: Pulse + Classification ===")

    from flatwhite.pulse.composite import calculate_pulse
    result = calculate_pulse()
    arrow = {"up": "↑", "down": "↓", "stable": "→"}[result["direction"]]
    print(f"  Pulse: {result['smoothed']:.0f} {arrow} (raw: {result['composite']:.1f})")

    from flatwhite.classify.classifier import classify_all_unclassified
    stats = classify_all_unclassified()
    print(f"  Classified: {stats['total']} total, {stats['curated']} curated, "
          f"{stats['discarded']} discarded, {stats['failed']} failed")

    g5_elapsed = time.time() - g5_start
    print(f"  [Group 5 done in {g5_elapsed:.0f}s]")

    elapsed = time.time() - pipeline_start
    print(f"\n=== INGEST COMPLETE ({elapsed:.0f}s) ===")


def cmd_pulse() -> None:
    """Calculate AusCorp Live Pulse score from ingested signals."""
    from flatwhite.pulse.composite import calculate_pulse
    result = calculate_pulse()
    arrow = {"up": "↑", "down": "↓", "stable": "→"}[result["direction"]]
    print(f"\nAusCorp Live Pulse: {result['smoothed']:.0f} {arrow}")
    print(f"  Raw composite: {result['composite']:.1f}")
    print(f"  Top drivers:")
    for d in result["top_drivers"]:
        print(f"    {d['signal']}: {d['score']:.0f} (weight {d['weight']})")

    from flatwhite.pulse.anomaly import detect_all_anomalies
    anomalies = detect_all_anomalies()
    if anomalies:
        print(f"\n  ⚠ Anomalies detected:")
        for a in anomalies:
            print(f"    {a['signal']}: {a['deviation_mads']:.1f} MADs {a['direction']} median")
    else:
        print(f"\n  No anomalies detected.")

    # --- Signal interactions ---
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    signal_rows = conn.execute(
        """SELECT signal_name, normalised_score FROM signals
        WHERE week_iso = ? AND lane = 'pulse'""",
        (result["week_iso"],),
    ).fetchall()
    conn.close()
    scores = {r["signal_name"]: r["normalised_score"] for r in signal_rows}

    interactions = evaluate_patterns(scores)
    if interactions:
        print(f"\n  Signal interactions detected:")
        for ix in interactions:
            insert_interaction(
                week_iso=result["week_iso"],
                pattern_name=ix["name"],
                severity=ix["severity"],
                signals_involved=ix["signals_involved"],
                narrative=ix["narrative"],
            )
            print(f"    {ix['name']} (severity {ix['severity']:.2f})")
            print(f"      {ix['narrative']}")
    else:
        print(f"\n  No signal interactions detected.")


def cmd_classify() -> None:
    """Classify all unclassified editorial items using 5-dimension scoring."""
    from flatwhite.classify.classifier import classify_all_unclassified
    count = classify_all_unclassified()
    print(f"Classified {count} items.")

    # Section breakdown
    from flatwhite.db import get_connection
    conn = get_connection()
    week_iso = get_current_week_iso()
    sections = conn.execute(
        """SELECT ci.section, COUNT(*) as cnt
        FROM curated_items ci
        JOIN raw_items ri ON ci.raw_item_id = ri.id
        WHERE ri.week_iso = ?
        GROUP BY ci.section
        ORDER BY cnt DESC""",
        (week_iso,),
    ).fetchall()
    conn.close()

    if sections:
        print("Section breakdown:")
        for s in sections:
            print(f"  {s['section']}: {s['cnt']}")

    # Thread of the Week
    from flatwhite.classify.thread_ranker import get_thread_of_the_week
    thread = get_thread_of_the_week()
    if thread:
        print(f"\nThread of the Week: {thread['title']}")
        print(f"  Score: {thread['composite']:.2f}")
        print(f"  Frame: {thread['editorial_frame']}")
    else:
        print("\nNo thread candidates found.")


def cmd_summarise() -> None:
    """Generate Pulse summary, driver bullets, and top-line hooks."""
    from flatwhite.pulse.summary import (
        generate_pulse_summary,
        generate_driver_bullets,
        generate_top_line_hooks,
    )

    print("Generating Pulse summary...")
    summary = generate_pulse_summary()
    print(f"\nSummary:\n{summary}")

    print("\nGenerating driver bullets...")
    drivers = generate_driver_bullets()
    for d in drivers:
        arrow = "↑" if d["direction"] == "up" else "↓"
        print(f"  {arrow} {d['signal']}: {d['bullet']}")

    print("\nGenerating top-line hooks...")
    hooks = generate_top_line_hooks()
    for i, hook in enumerate(hooks, 1):
        print(f"  [{i}] {hook}")


def cmd_angles() -> None:
    """Generate Big Conversation angle candidates."""
    from flatwhite.classify.big_conversation import generate_angles
    angles = generate_angles()

    if not angles:
        print("No angles generated. Ensure items are classified first.")
        return

    for i, angle in enumerate(angles, 1):
        print(f"\n--- Angle {i} ---")
        print(f"  Headline: {angle['headline']}")
        print(f"  Pitch: {angle['pitch']}")
        print(f"  Supporting items: {angle['supporting_item_ids']}")


def cmd_review() -> None:
    """Launch the Flat White editor dashboard (FastAPI web UI)."""
    import uvicorn
    print("\n  Flat White Editor Dashboard")
    print("  http://localhost:8500")
    print("  Press Ctrl+C to stop.\n")
    uvicorn.run(
        "flatwhite.dashboard.api:app",
        host="0.0.0.0",
        port=8500,
        log_level="warning",
    )


def cmd_preview() -> None:
    """Preview the most recent assembled newsletter status."""
    from flatwhite.db import get_connection
    conn = get_connection()
    week_iso = get_current_week_iso()
    row = conn.execute(
        "SELECT * FROM newsletters WHERE week_iso = ? ORDER BY created_at DESC LIMIT 1",
        (week_iso,),
    ).fetchone()
    conn.close()

    if not row:
        print("No newsletter assembled for this week. Run: flatwhite assemble --hook 'text'")
        return

    d = dict(row)
    print(f"Week: {d['week_iso']}")
    print(f"Rotation: {d['rotation']}")
    print(f"  Preview: data/preview.html")
    print(f"Published: {d.get('published_at') or 'not yet'}")
    print(f"Created: {d['created_at']}")


def cmd_assemble() -> None:
    """Assemble the newsletter HTML from approved items and render to local preview."""
    from pathlib import Path
    from flatwhite.orchestrate.runner import get_next_rotation
    from flatwhite.assemble.renderer import render_newsletter
    from flatwhite.db import get_connection, get_pulse_history
    from flatwhite.model_router import route
    from flatwhite.assemble.templates import (
        SUBJECT_LINE_SYSTEM, SUBJECT_LINE_PROMPT,
        PREVIEW_TEXT_SYSTEM, PREVIEW_TEXT_PROMPT,
    )

    week_iso = get_current_week_iso()
    rotation = get_next_rotation()

    hook_text = ""

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--hook" and i + 1 < len(args):
            hook_text = args[i + 1]
            i += 2
        elif args[i] == "--rotation" and i + 1 < len(args):
            rotation = args[i + 1]
            i += 2
        else:
            i += 1

    if not hook_text:
        print("Usage: flatwhite assemble --hook 'Your hook text' [--rotation A|B]")
        sys.exit(1)

    print(f"Assembling newsletter (rotation {rotation})...")

    # 1. Render newsletter HTML
    content_html = render_newsletter(hook_text, rotation)

    # 2. Gather metadata for subject/preview generation
    history = get_pulse_history(weeks=1)
    smoothed_score = history[0]["smoothed_score"] if history else 50.0
    direction = history[0]["direction"] if history else "stable"

    conn = get_connection()
    approved = conn.execute(
        """SELECT ci.summary, ed.section_placed
        FROM editor_decisions ed
        JOIN curated_items ci ON ed.curated_item_id = ci.id
        WHERE ed.decision = 'approved' AND ed.issue_week_iso = ?
        ORDER BY ci.weighted_composite DESC LIMIT 5""",
        (week_iso,),
    ).fetchall()

    big_convo_headline = "This week in AusCorp"
    top_whisper = "No whispers this week"
    thread_title = "No thread selected"
    top_items_summary = ""

    for item in approved:
        d = dict(item)
        section = d.get("section_placed", "")
        summary = d.get("summary", "")

        if section == "big_conversation_seed" and big_convo_headline == "This week in AusCorp":
            big_convo_headline = summary[:80]
        elif section == "whisper" and top_whisper == "No whispers this week":
            top_whisper = summary[:80]
        elif section == "thread_candidate" and thread_title == "No thread selected":
            thread_title = summary[:80]

        if top_items_summary:
            top_items_summary += "; "
        top_items_summary += summary[:60]

    if not top_items_summary:
        top_items_summary = "This week's corporate pulse and editorial highlights."

    # 3. Generate subject line
    subject_prompt = SUBJECT_LINE_PROMPT.format(
        smoothed_score=f"{smoothed_score:.0f}",
        direction=direction,
        big_conversation_headline=big_convo_headline,
        top_whisper=top_whisper,
        thread_title=thread_title,
    )
    try:
        subject = route(task_type="editorial", prompt=subject_prompt, system=SUBJECT_LINE_SYSTEM)
        subject = subject.strip().strip('"').strip("'")
        if len(subject) > 60:
            subject = subject[:57] + "..."
        if len(subject) < 5:
            subject = "Flat White — This Week in AusCorp"
    except Exception:
        subject = "Flat White — This Week in AusCorp"

    # 4. Generate preview text
    preview_prompt = PREVIEW_TEXT_PROMPT.format(
        subject_line=subject,
        smoothed_score=f"{smoothed_score:.0f}",
        direction=direction,
        top_items_summary=top_items_summary[:200],
    )
    try:
        preview_text = route(task_type="hook", prompt=preview_prompt, system=PREVIEW_TEXT_SYSTEM)
        preview_text = preview_text.strip().strip('"').strip("'")
        if len(preview_text) > 120:
            preview_text = preview_text[:117] + "..."
        if len(preview_text) < 5:
            preview_text = "The weekly pulse on Australian corporate life."
    except Exception:
        preview_text = "The weekly pulse on Australian corporate life."

    # 5. Write HTML to data/preview.html
    preview_path = Path(__file__).parent.parent / "data" / "preview.html"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(f"<!DOCTYPE html><html><body>{content_html}</body></html>")

    # 6. Store in newsletters table
    conn.execute(
        """INSERT OR REPLACE INTO newsletters (week_iso, beehiiv_post_id, rotation, published_at)
        VALUES (?, NULL, ?, NULL)""",
        (week_iso, rotation),
    )
    conn.commit()
    conn.close()

    print(f"  Subject: {subject}")
    print(f"  Preview: {preview_text}")
    print(f"  Rotation: {rotation}")
    print(f"  HTML length: {len(content_html)} chars")
    print(f"  Output: {preview_path}")


def cmd_add_whisper(text: str, confidence: str = "yellow") -> None:
    """Add a manual whisper to the editorial pipeline."""
    from flatwhite.editorial.manual_whispers import add_whisper
    row_id = add_whisper(text, confidence)
    print(f"Whisper added (id={row_id}, confidence={confidence})")


def cmd_run(skip_assemble: bool = True) -> None:
    """Run the full pipeline end-to-end.

    By default, stops after angles (steps 1-5) so the editor can review in Streamlit.
    Pass --assemble to include step 6 (local HTML assembly).
    """
    from flatwhite.orchestrate.runner import run_full_pipeline

    if skip_assemble:
        mode = "INGEST → ANGLES (editor review needed before assembly)"
    else:
        mode = "FULL PIPELINE"
    print(f"=== FLAT WHITE PIPELINE — {mode} ===\n")

    report = run_full_pipeline(skip_assemble=skip_assemble)

    # Print step results
    for step in report["steps"]:
        icon = {"pass": "✓", "fail": "✗", "skip": "–"}[step["status"]]
        print(f"  {icon} {step['name']:12s} [{step['duration_seconds']:>6.1f}s] {step['detail']}")

    print(f"\n  Week: {report['week_iso']}  Rotation: {report['rotation']}")
    print(f"  Status: {report['overall_status'].upper()}")
    print(f"  Duration: {report['started_at']} → {report['completed_at']}")

    # Print full report as JSON for logging
    print(f"\n--- RUN REPORT ---")
    print(json.dumps(report, indent=2))


def cmd_status() -> None:
    """Show current pipeline status for this week."""
    from flatwhite.orchestrate.status import get_pipeline_status
    status = get_pipeline_status()

    print(f"=== FLAT WHITE STATUS — {status['week_iso']} ===\n")
    print(f"  Rotation:       {status['rotation']}")
    print(f"  Signals:        {status['signals_count']}")
    print(f"  Raw items:      {status['raw_items_count']}")
    print(f"  Curated items:  {status['curated_items_count']}")
    print(f"  Approved items: {status['approved_items_count']}")

    if status["pulse_score"] is not None:
        arrow = {"up": "↑", "down": "↓", "stable": "→"}.get(status["pulse_direction"], "?")
        print(f"  Pulse:          {status['pulse_score']} {arrow}")
    else:
        print(f"  Pulse:          not calculated")

    print(f"  Summary:        {'✓' if status['has_summary'] else '✗'}")
    print(f"  Hooks:          {'✓' if status['has_hooks'] else '✗'}")
    print(f"  Newsletter:     {'✓' if status['has_newsletter'] else '✗'}")
    print(f"  Last published: {status['last_published'] or 'never'}")

    # Extraction health warnings
    from flatwhite.db import get_connection
    conn = get_connection()
    carry_forward = conn.execute(
        """SELECT ew.employer_name, ew.consecutive_carry_forward_weeks
         FROM employer_watchlist ew
         WHERE ew.consecutive_carry_forward_weeks > 0 AND ew.active = 1
         ORDER BY ew.consecutive_carry_forward_weeks DESC"""
    ).fetchall()
    conn.close()

    if carry_forward:
        print("\nExtraction health warnings:")
        for emp in carry_forward:
            weeks = emp["consecutive_carry_forward_weeks"]
            print(f"  ⚠ {emp['employer_name']}: carry-forward for {weeks} week{'s' if weeks > 1 else ''}")


def cmd_schedule() -> None:
    """Show the scheduling configuration and cron entry."""
    from flatwhite.orchestrate.scheduler import get_schedule_config, generate_cron_entry

    config = get_schedule_config()
    print("=== FLAT WHITE SCHEDULE ===\n")
    print(f"  Pipeline runs:  {config['pipeline_day']} {config['pipeline_hour_aest']:02d}:00 AEST")
    print(f"  Review window:  {config['review_window_hours']} hours")
    print(f"  Send day:       {config['send_day']} {config['send_hour_aest']:02d}:00 AEST")
    print(f"\nCrontab entry (UTC):")
    print(f"  {generate_cron_entry()}")
    print(f"\nTo install, run:")
    print(f"  (crontab -l 2>/dev/null; echo '{generate_cron_entry()}') | crontab -")


def cmd_notify() -> None:
    """Send a pipeline-ready email notification to the editor."""
    from flatwhite.publish.notify import send_pipeline_ready_email
    from flatwhite.orchestrate.status import get_pipeline_status

    print("Sending pipeline notification email...")
    status = get_pipeline_status()
    pulse_score = status.get("pulse_score")
    items_count = status.get("curated_items_count", 0)
    send_pipeline_ready_email(
        pulse_score=pulse_score,
        items_count=items_count,
    )


def cmd_ats_check() -> None:
    """Test ATS extraction for a single employer without writing to the database.

    Usage: flatwhite ats-check --employer "Xero"
    """
    import asyncio
    from flatwhite.db import get_connection
    from flatwhite.signals.hiring_pulse import pull_single_employer

    employer_name = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--employer" and i + 1 < len(args):
            employer_name = args[i + 1]
            i += 2
        else:
            i += 1

    if not employer_name:
        print("Usage: flatwhite ats-check --employer 'Employer Name'")
        sys.exit(1)

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM employer_watchlist WHERE employer_name = ? AND active = 1",
        (employer_name,),
    ).fetchone()
    conn.close()

    if not row:
        print(f"Employer not found: {employer_name}")
        print("Use 'flatwhite status' to see active employers.")
        sys.exit(1)

    emp = dict(row)
    print(f"Testing {emp['employer_name']} ({emp['ats_platform']})...")
    print(f"  Endpoint: {emp.get('ats_endpoint') or emp['careers_url']}")

    pull = asyncio.run(pull_single_employer(emp))

    if pull.success and pull.total_count > 0:
        print(f"  Status: 200 OK")
        print(f"  Jobs found: {pull.total_count}")
        if pull.roles:
            print(f"  Sample titles:")
            for r in pull.roles[:3]:
                print(f"    {r.title}")
        print(f"  PASS — {pull.extraction_method} method working")
    else:
        print(f"  FAIL — {pull.error_message or 'no roles returned'}")
        sys.exit(1)


def cmd_audit() -> None:
    """Audit classifier accuracy for current week's classifications."""
    from flatwhite.classify.audit import audit_classifications, print_audit_report

    week_iso = get_current_week_iso()
    section = None

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--week" and i + 1 < len(args):
            week_iso = args[i + 1]
            i += 2
        elif args[i] == "--section" and i + 1 < len(args):
            section = args[i + 1]
            i += 2
        else:
            i += 1

    result = audit_classifications(week_iso=week_iso, section=section)
    print_audit_report(result)


def cmd_feedback() -> None:
    """Record newsletter performance or show feedback history.

    Usage:
      flatwhite feedback --history
      flatwhite feedback --open-rate 0.45 --click-rate 0.12 [--week 2026-W12] [--notes "text"]
    """
    from flatwhite.publish.local_feedback import record_feedback, get_feedback_history

    args = sys.argv[2:]

    # Parse flags
    open_rate: float | None = None
    click_rate: float | None = None
    week: str | None = None
    notes: str | None = None
    show_history = False

    i = 0
    while i < len(args):
        if args[i] == "--history":
            show_history = True
            i += 1
        elif args[i] == "--open-rate" and i + 1 < len(args):
            open_rate = float(args[i + 1])
            i += 2
        elif args[i] == "--click-rate" and i + 1 < len(args):
            click_rate = float(args[i + 1])
            i += 2
        elif args[i] == "--week" and i + 1 < len(args):
            week = args[i + 1]
            i += 2
        elif args[i] == "--notes" and i + 1 < len(args):
            notes = args[i + 1]
            i += 2
        else:
            i += 1

    # No args at all → show history
    if not args or show_history:
        history = get_feedback_history()
        if not history:
            print("No feedback history found.")
            return
        print(f"{'Week':<12} {'Avg Click Rate':>15} {'Total':>6} {'Approved':>9} {'Rejected':>9}")
        print("-" * 55)
        for row in history:
            cr = f"{row['avg_click_rate']:.2%}" if row["avg_click_rate"] is not None else "—"
            print(
                f"{row['week_iso']:<12} {cr:>15} {row['total_decisions']:>6} "
                f"{row['approved_count']:>9} {row['rejected_count']:>9}"
            )
        return

    # Must have at least one rate to record
    if open_rate is None and click_rate is None:
        print("Usage: flatwhite feedback --open-rate N --click-rate N [--week W] [--notes 'text']")
        print("       flatwhite feedback --history")
        sys.exit(1)

    result = record_feedback(
        week_iso=week,
        open_rate=open_rate,
        click_rate=click_rate,
        notes=notes,
    )
    print(f"Feedback recorded for {result['week_iso']}:")
    if result["open_rate"] is not None:
        print(f"  Open rate:  {result['open_rate']:.2%}")
    if result["click_rate"] is not None:
        print(f"  Click rate: {result['click_rate']:.2%}")
    print(f"  Editor decisions updated: {result['decisions_updated']}")


def cmd_backfill() -> None:
    """Backfill historical pulse signals and pulse_history."""
    weeks = 12  # default
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--weeks" and i + 1 < len(args):
            weeks = int(args[i + 1])
            i += 2
        else:
            i += 1

    from flatwhite.pulse.backfill import run_backfill
    run_backfill(weeks=weeks)


def main() -> None:
    """CLI entry point. Dispatches to command functions based on sys.argv[1]."""
    if len(sys.argv) < 2:
        print("Usage: flatwhite <command>")
        print("")
        print("Commands:")
        print("  init          Initialise the database")
        print("  ingest        Pull all data sources (Lane A + Lane B)")
        print("  pulse         Calculate AusCorp Live Pulse score")
        print("  classify      Classify editorial items (5-dimension scoring)")
        print("  summarise     Generate Pulse summary, drivers, and hooks")
        print("  angles        Generate Big Conversation angle candidates")
        print("  review        Launch Streamlit editor dashboard")
        print("  assemble      Build newsletter HTML from approved items")
        print("  preview       Show status of most recent newsletter")
        print("  add-whisper   Manually add a whisper item")
        print("  run           Run pipeline (steps 1-5 by default, --assemble for full)")
        print("  status        Show pipeline status for current week")
        print("  schedule      Show schedule config and cron entry")
        print("  backfill      Backfill historical pulse data (--weeks N, default 12)")
        print("  notify        Send pipeline-ready email to editor")
        print("  audit         Review classifier accuracy (--week W --section S)")
        print("  ats-check     Test ATS extraction for one employer (--employer 'Name')")
        print("  feedback      Record newsletter performance (--open-rate N --click-rate N)")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        cmd_init()
    elif command == "ingest":
        cmd_ingest()
    elif command == "pulse":
        cmd_pulse()
    elif command == "classify":
        cmd_classify()
    elif command == "summarise":
        cmd_summarise()
    elif command == "angles":
        cmd_angles()
    elif command == "assemble":
        cmd_assemble()
    elif command == "review":
        cmd_review()
    elif command == "preview":
        cmd_preview()
    elif command == "add-whisper":
        if len(sys.argv) < 3:
            print("Usage: flatwhite add-whisper 'text' [--confidence green|yellow|red]")
            sys.exit(1)
        text = sys.argv[2]
        confidence = "yellow"
        if "--confidence" in sys.argv:
            idx = sys.argv.index("--confidence")
            if idx + 1 < len(sys.argv):
                confidence = sys.argv[idx + 1]
        cmd_add_whisper(text, confidence)
    elif command == "run":
        skip_assemble = "--assemble" not in sys.argv
        cmd_run(skip_assemble=skip_assemble)
    elif command == "status":
        cmd_status()
    elif command == "schedule":
        cmd_schedule()
    elif command == "backfill":
        cmd_backfill()
    elif command == "notify":
        cmd_notify()
    elif command == "audit":
        cmd_audit()
    elif command == "ats-check":
        cmd_ats_check()
    elif command == "feedback":
        cmd_feedback()
    else:
        print(f"Unknown command: {command}")
        print("Run 'flatwhite' with no arguments to see available commands.")
        sys.exit(1)
