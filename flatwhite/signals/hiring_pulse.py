"""
Hiring Pulse collector for employer ATS activity.

Pulls all 33 employer ATS portals, upserts roles, calculates three
derived Lane A signals:

  employer_hiring_breadth  (weight 0.05) — % employers adding vs cutting
  employer_req_freshness   (weight 0.04) — new roles / total active roles
  employer_net_delta       (weight 0.03) — aggregate WoW role count change

All SQLite access is synchronous and confined to pull_hiring_pulse().
The async layer (_pull_all_employers, pull_single_employer) is DB-free.
"""
from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from pathlib import Path

import yaml

from flatwhite.db import get_connection, get_current_week_iso, insert_signal
from flatwhite.signals.ats_extractors import (
    EmployerPull,
    RoleRecord,
    _make_dedup_key,
    extract_ashby,
    extract_atlassian,
    extract_avature,
    extract_ngasoft,
    extract_oracle_hcm,
    extract_phenom,
    extract_seek_fallback,
    extract_smartrecruiters,
    extract_successfactors,
    extract_taleo,
    extract_workday,
    is_australian_role,
    is_corporate_role,
    normalise_location,
)


CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

# Tier 1: JSON API extractors (fast, 2-5s each)
# Tier 2: HTML scraping extractors (slower, 5-15s each)
TIER1_PLATFORMS = {"workday", "smartrecruiters", "oracle_hcm", "ashby", "atlassian", "taleo"}
TIER2_PLATFORMS = {"successfactors", "phenom", "avature", "ngasoft"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _subtract_weeks(week_iso: str, n: int) -> str:
    """Subtract n weeks from an ISO week string like '2026-W12'."""
    year, week = int(week_iso[:4]), int(week_iso.split("W")[1])
    d = date.fromisocalendar(year, week, 1) - timedelta(weeks=n)
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def _upsert_roles(
    employer_id: int, roles: list[RoleRecord], week_iso: str, conn
) -> tuple[int, int]:
    """
    Upsert individual roles. Returns (new_count, stale_count).

    Snapshots existing dedup_keys BEFORE upserting — makes new-detection
    idempotent (re-running same week will produce same new_count).
    Only deactivates roles when role-level data was successfully extracted.
    """
    four_weeks_ago = _subtract_weeks(week_iso, 4)

    existing_rows = conn.execute(
        "SELECT dedup_key, first_seen_week FROM employer_roles WHERE employer_id = ?",
        (employer_id,),
    ).fetchall()
    existing_keys: set[str] = set()
    existing_first_seen: dict[str, str] = {}
    for row in existing_rows:
        existing_keys.add(row["dedup_key"])
        existing_first_seen[row["dedup_key"]] = row["first_seen_week"]

    new_count = 0
    stale_count = 0

    for role in roles:
        dedup_key = _make_dedup_key(employer_id, role.title, role.location)
        norm_loc = normalise_location(role.location)

        conn.execute(
            """INSERT INTO employer_roles
             (employer_id, title, location, department, seniority_bucket,
              posted_date, role_url, first_seen_week, last_seen_week, is_active, dedup_key)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
             ON CONFLICT(dedup_key) DO UPDATE SET
              last_seen_week = excluded.last_seen_week,
              is_active = 1,
              department = COALESCE(excluded.department, employer_roles.department),
              seniority_bucket = COALESCE(excluded.seniority_bucket, employer_roles.seniority_bucket)
            """,
            (
                employer_id, role.title, norm_loc, role.department,
                role.seniority_bucket, role.posted_date, role.url,
                week_iso, week_iso, dedup_key,
            ),
        )

        if dedup_key not in existing_keys:
            new_count += 1
        else:
            first_seen = existing_first_seen.get(dedup_key, week_iso)
            if first_seen <= four_weeks_ago:
                stale_count += 1

    # Deactivate roles not seen this week — only for role-level pulls
    if roles:
        conn.execute(
            "UPDATE employer_roles SET is_active = 0 "
            "WHERE employer_id = ? AND last_seen_week != ? AND is_active = 1",
            (employer_id, week_iso),
        )

    return new_count, stale_count


# ── Single-employer async pull (DB-free) ─────────────────────────────────────

async def pull_single_employer(emp: dict) -> EmployerPull:
    """
    Pull roles for one employer using platform-specific extractor.

    IMPORTANT: This function MUST NOT access the SQLite database.
    All DB reads/writes happen in the synchronous pull_hiring_pulse().
    """
    ats = emp["ats_platform"]
    endpoint = emp.get("ats_endpoint") or emp["careers_url"]
    eid = emp["id"]
    name = emp["employer_name"]
    sector = emp["sector"]

    pull: EmployerPull | None = None

    # Tier 1A: JSON API extractors
    if ats == "workday" and endpoint:
        # Endpoint may encode optional Workday facets as "url||json"
        # e.g. "https://...jobs||{"locationCountry":["<facet-id>"]}"
        workday_url = endpoint
        workday_facets: dict | None = None
        if "||" in endpoint:
            workday_url, facets_json = endpoint.split("||", 1)
            try:
                import json as _json
                workday_facets = _json.loads(facets_json)
            except Exception:
                pass
        pull = await extract_workday(workday_url, eid, name, sector, applied_facets=workday_facets)
    elif ats == "smartrecruiters" and endpoint:
        pull = await extract_smartrecruiters(endpoint, eid, name, sector)
    elif ats == "oracle_hcm" and endpoint:
        instance, site = endpoint.split("|")
        pull = await extract_oracle_hcm(instance, site, eid, name, sector)
    elif ats == "ashby" and endpoint:
        pull = await extract_ashby(endpoint, eid, name, sector)
    elif ats == "atlassian":
        pull = await extract_atlassian(eid, name, sector)
    elif ats == "taleo" and endpoint:
        parts = endpoint.split("|")
        pull = await extract_taleo(parts[0], parts[1], parts[2], eid, name, sector)

    # Tier 1B: HTML scraping extractors
    elif ats == "successfactors" and endpoint:
        au_filter = emp.get("country_filter") == "AU"
        pull = await extract_successfactors(endpoint, eid, name, sector, au_keyword_filter=au_filter)
    elif ats == "phenom" and endpoint:
        domain, locale = endpoint.split("|", 1)
        pull = await extract_phenom(domain, locale, eid, name, sector)
    elif ats == "avature" and endpoint:
        domain, path = endpoint.split("|", 1)
        pull = await extract_avature(domain, path, eid, name, sector)
    elif ats == "ngasoft" and endpoint:
        subdomain, board_id = endpoint.split("|", 1)
        pull = await extract_ngasoft(subdomain, board_id, eid, name, sector)

    # SEEK fallback — used when primary extractor failed, returned 0, or platform unknown
    if pull is None or not pull.success or pull.total_count == 0:
        seek_result = await extract_seek_fallback(
            name, eid, sector, seek_slug=emp.get("seek_slug")
        )
        if pull is None or (seek_result.success and seek_result.total_count > 0):
            pull = seek_result

    # Flag carry-forward if everything failed
    if not pull.success:
        pull.needs_carry_forward = True

    # Apply country filter for global employers
    pre_filter_count = pull.total_count
    if emp.get("country_filter") == "AU" and pull.roles:
        pull.roles = [r for r in pull.roles if is_australian_role(r)]
        pull.total_count = len(pull.roles)

    # Apply corporate-only filter
    if emp.get("corporate_only") and pull.roles:
        pull.roles = [r for r in pull.roles if is_corporate_role(r)]
        pull.total_count = len(pull.roles)

    # SEEK cross-check for AU-filtered employers: ATS portals often under-count
    # Australian roles (internal boards, separate portals, missing location data).
    # Use SEEK as authoritative count; keep ATS roles for seniority analysis.
    seek_slug = emp.get("seek_slug")
    if seek_slug and pull.success:
        needs_seek = False
        if pull.total_count == 0:
            needs_seek = True  # primary or filters returned 0
        elif emp.get("country_filter") == "AU":
            needs_seek = True  # AU employers always cross-check

        if needs_seek:
            seek_result = await extract_seek_fallback(
                name, eid, sector, seek_slug=seek_slug,
            )
            if seek_result.success and seek_result.total_count > 0:
                if pull.total_count == 0:
                    print(f"  ℹ {name}: primary returned 0 after filters — "
                          f"using SEEK count ({seek_result.total_count})")
                    pull = seek_result
                elif seek_result.total_count > pull.total_count:
                    print(f"  ℹ {name}: ATS has {pull.total_count} AU roles, "
                          f"SEEK has {seek_result.total_count} — using SEEK count")
                    # Keep ATS roles for detail, but use SEEK count for snapshot
                    pull.total_count = seek_result.total_count

    return pull


# ── Async orchestrator ────────────────────────────────────────────────────────

async def _pull_all_employers(
    employers: list[dict],
    concurrency: int = 10,
    timeout_seconds: float = 30.0,
) -> list:
    """
    Pull all employers with concurrency limit and per-employer timeout.

    Splits employers into Tier 1 (JSON API, fast) and Tier 2 (HTML scrape,
    slower), running Tier 1 first so fast results aren't blocked behind
    slow HTML scraping. Per-domain rate limiting is handled inside extractors.
    return_exceptions=True prevents one failure from cancelling all pulls.
    """
    sem = asyncio.Semaphore(concurrency)

    async def limited_pull(emp: dict) -> EmployerPull:
        async with sem:
            try:
                return await asyncio.wait_for(
                    pull_single_employer(emp),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                return EmployerPull(
                    employer_id=emp["id"],
                    employer_name=emp["employer_name"],
                    sector=emp["sector"],
                    extraction_method="timeout",
                    ats_platform=emp.get("ats_platform", "unknown"),
                    success=False,
                    error_message=f"Timed out after {timeout_seconds:.0f}s",
                    needs_carry_forward=True,
                )

    # Split into tiers: JSON API first, HTML scrape second
    tier1 = [e for e in employers if e.get("ats_platform", "") in TIER1_PLATFORMS]
    tier2 = [e for e in employers if e.get("ats_platform", "") in TIER2_PLATFORMS]
    # Anything not in tier1/tier2 (e.g. unknown platform) goes with tier2
    known = {e["id"] for e in tier1} | {e["id"] for e in tier2}
    tier2.extend(e for e in employers if e["id"] not in known)

    # Run Tier 1 first (fast), then Tier 2 (slow)
    results_t1 = await asyncio.gather(
        *[limited_pull(e) for e in tier1],
        return_exceptions=True,
    )
    results_t2 = await asyncio.gather(
        *[limited_pull(e) for e in tier2],
        return_exceptions=True,
    )

    return list(results_t1) + list(results_t2)


# ── Main entry point ──────────────────────────────────────────────────────────

def pull_hiring_pulse(week_iso: str | None = None) -> dict:
    """
    Main entry point. Pulls all employers, calculates three derived signals.
    All SQLite access happens here — async layer is DB-free.
    """
    if week_iso is None:
        week_iso = get_current_week_iso()

    # Load ATS config
    ats_cfg: dict = {}
    try:
        with open(CONFIG_PATH, "r") as f:
            ats_cfg = yaml.safe_load(f).get("ats_pull", {})
    except Exception:
        pass
    concurrency = ats_cfg.get("concurrency", 10)
    timeout_seconds = ats_cfg.get("timeout_seconds", 30.0)
    skip_threshold = ats_cfg.get("skip_after_consecutive_failures", 4)

    conn = get_connection()
    all_employers = [
        dict(e) for e in conn.execute(
            "SELECT * FROM employer_watchlist WHERE active = 1"
        ).fetchall()
    ]

    # Skip employers that have failed too many consecutive weeks
    employers: list[dict] = []
    skipped_pulls: list[EmployerPull] = []
    for emp in all_employers:
        consecutive_failures = emp.get("consecutive_carry_forward_weeks", 0)
        if consecutive_failures >= skip_threshold:
            print(
                f"  ⏭ Skipping {emp['employer_name']} "
                f"({consecutive_failures} consecutive failures) — using carry-forward"
            )
            skipped_pulls.append(EmployerPull(
                employer_id=emp["id"],
                employer_name=emp["employer_name"],
                sector=emp["sector"],
                extraction_method="skipped",
                ats_platform=emp.get("ats_platform", "unknown"),
                success=False,
                error_message=f"Skipped: {consecutive_failures} consecutive failures",
                needs_carry_forward=True,
            ))
        else:
            employers.append(emp)

    # Run employer pulls (DB-free async layer)
    start_time = time.time()
    pulls: list = asyncio.run(
        _pull_all_employers(employers, concurrency=concurrency, timeout_seconds=timeout_seconds)
    )
    elapsed = time.time() - start_time
    print(f"  ATS pull completed in {elapsed:.0f}s ({len(employers)} employers, concurrency={concurrency})")

    # Merge skipped employers back in
    pulls.extend(skipped_pulls)

    # Handle carry-forward in sync context (DB-safe)
    for pull in pulls:
        if isinstance(pull, Exception):
            continue
        if pull.needs_carry_forward:
            prev = conn.execute(
                """SELECT open_roles_count FROM employer_snapshots
                 WHERE employer_id = ? AND open_roles_count > 0
                 ORDER BY snapshot_date DESC LIMIT 1""",
                (pull.employer_id,),
            ).fetchone()
            if prev and prev["open_roles_count"] > 0:
                pull.total_count = prev["open_roles_count"]
                pull.success = True
                pull.ats_platform = "carry_forward"
                pull.error_message = "All extractors failed — carried forward previous count"
                conn.execute(
                    "UPDATE employer_watchlist "
                    "SET consecutive_carry_forward_weeks = consecutive_carry_forward_weeks + 1 "
                    "WHERE id = ?",
                    (pull.employer_id,),
                )

    # Aggregate metrics
    adding_count = cutting_count = flat_count = zero_count = 0
    total_roles_this_week = total_roles_last_week = 0
    total_new_roles = total_active_roles = total_stale_roles = 0
    seniority_totals: dict[str, int] = {
        "junior": 0, "mid": 0, "senior": 0, "executive": 0, "unknown": 0
    }
    sector_adding: dict[str, int] = {}
    sector_cutting: dict[str, int] = {}
    sector_total: dict[str, int] = {}
    employer_deltas: list[dict] = []
    freeze_count = 0
    employer_results: list[dict] = []

    for pull in pulls:
        if isinstance(pull, Exception):
            zero_count += 1
            continue

        # Record extraction health (upsert — preserves best result)
        conn.execute(
            """INSERT INTO extraction_health
             (employer_id, week_iso, extraction_method, ats_platform,
              roles_extracted, success, error_message)
             VALUES (?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(employer_id, week_iso) DO UPDATE SET
              roles_extracted = MAX(extraction_health.roles_extracted, excluded.roles_extracted),
              success = MAX(extraction_health.success, excluded.success),
              ats_platform = CASE
                WHEN excluded.roles_extracted > extraction_health.roles_extracted
                THEN excluded.ats_platform ELSE extraction_health.ats_platform END,
              error_message = CASE
                WHEN excluded.roles_extracted > extraction_health.roles_extracted
                THEN excluded.error_message ELSE extraction_health.error_message END
            """,
            (
                pull.employer_id, week_iso, pull.extraction_method, pull.ats_platform,
                pull.total_count, int(pull.success), pull.error_message,
            ),
        )

        if not pull.success or pull.total_count == 0:
            zero_count += 1
            freeze_count += 1
            employer_results.append({
                "name": pull.employer_name, "sector": pull.sector,
                "count": 0, "success": False,
            })
            continue

        # Reset carry-forward counter on real success
        if pull.ats_platform != "carry_forward":
            conn.execute(
                "UPDATE employer_watchlist SET consecutive_carry_forward_weeks = 0 WHERE id = ?",
                (pull.employer_id,),
            )

        # Upsert individual roles
        new_count = stale_count = 0
        if pull.roles:
            new_count, stale_count = _upsert_roles(pull.employer_id, pull.roles, week_iso, conn)
            for role in pull.roles:
                bucket = role.seniority_bucket or "unknown"
                seniority_totals[bucket] = seniority_totals.get(bucket, 0) + 1

        total_roles_this_week += pull.total_count
        total_new_roles += new_count
        total_active_roles += pull.total_count
        total_stale_roles += stale_count

        if pull.total_count == 0:
            freeze_count += 1

        # Compare with previous week — only when previous was a valid pull
        prev = conn.execute(
            """SELECT open_roles_count FROM employer_snapshots
             WHERE employer_id = ? AND week_iso != ? AND open_roles_count > 0
             ORDER BY snapshot_date DESC LIMIT 1""",
            (pull.employer_id, week_iso),
        ).fetchone()
        prev_count = prev["open_roles_count"] if prev else None

        if prev_count is not None:
            total_roles_last_week += prev_count
            delta = pull.total_count - prev_count
            if delta > 0:
                adding_count += 1
            elif delta < 0:
                cutting_count += 1
            else:
                flat_count += 1

            s = pull.sector
            sector_total[s] = sector_total.get(s, 0) + 1
            if delta > 0:
                sector_adding[s] = sector_adding.get(s, 0) + 1
            elif delta < 0:
                sector_cutting[s] = sector_cutting.get(s, 0) + 1

            delta_pct = ((delta / prev_count) * 100) if prev_count > 0 else 0.0
            employer_deltas.append({
                "name": pull.employer_name, "sector": pull.sector,
                "count": pull.total_count, "prev_count": prev_count,
                "delta": delta, "delta_pct": round(delta_pct, 1),
            })

        # Store enriched snapshot (upsert — idempotent)
        conn.execute(
            """INSERT INTO employer_snapshots
             (employer_id, open_roles_count, snapshot_date, week_iso,
              extraction_method, ats_platform, new_roles_count, stale_roles_count,
              junior_count, mid_count, senior_count, executive_count)
             VALUES (?, ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(employer_id, week_iso) DO UPDATE SET
              open_roles_count = excluded.open_roles_count,
              snapshot_date = excluded.snapshot_date,
              extraction_method = excluded.extraction_method,
              ats_platform = excluded.ats_platform,
              new_roles_count = excluded.new_roles_count,
              stale_roles_count = excluded.stale_roles_count,
              junior_count = excluded.junior_count,
              mid_count = excluded.mid_count,
              senior_count = excluded.senior_count,
              executive_count = excluded.executive_count
            """,
            (
                pull.employer_id, pull.total_count, week_iso,
                pull.extraction_method, pull.ats_platform,
                new_count, stale_count,
                sum(1 for r in pull.roles if r.seniority_bucket == "junior"),
                sum(1 for r in pull.roles if r.seniority_bucket == "mid"),
                sum(1 for r in pull.roles if r.seniority_bucket == "senior"),
                sum(1 for r in pull.roles if r.seniority_bucket == "executive"),
            ),
        )

        conn.execute(
            "UPDATE employer_watchlist SET last_successful_pull = datetime('now') WHERE id = ?",
            (pull.employer_id,),
        )
        employer_results.append({
            "name": pull.employer_name, "sector": pull.sector,
            "count": pull.total_count,
            "delta": (pull.total_count - prev_count) if prev_count is not None else None,
            "new": new_count, "stale": stale_count, "success": True,
        })

    conn.commit()

    # ── Calculate three derived signals ───────────────────────────────────────

    successful_employers = adding_count + cutting_count + flat_count
    MIN_EMPLOYERS_FOR_FULL_CONFIDENCE = 10

    # Signal 1: HIRING BREADTH — Bayesian shrinkage toward 50 when low n
    if successful_employers > 0:
        breadth_ratio = adding_count / successful_employers
        cutting_ratio = cutting_count / successful_employers
        breadth_raw = (breadth_ratio - cutting_ratio + 1) / 2
        breadth_score_raw = breadth_raw * 100.0
        confidence = min(1.0, successful_employers / MIN_EMPLOYERS_FOR_FULL_CONFIDENCE)
        breadth_score = 50.0 + (breadth_score_raw - 50.0) * confidence
        breadth_score = max(0.0, min(100.0, breadth_score))
    else:
        breadth_score = 50.0

    # Tension alert: breadth and delta contradict each other
    breadth_delta_divergence = False
    if total_roles_last_week > 0:
        aggregate_delta = total_roles_this_week - total_roles_last_week
        if breadth_score > 55.0 and aggregate_delta < 0:
            breadth_delta_divergence = True
        elif breadth_score < 45.0 and aggregate_delta > 0:
            breadth_delta_divergence = True

    # Signal 2: REQUISITION FRESHNESS — 4-week warmup, source_weight=0.0 until active
    weeks_with_role_data = conn.execute(
        "SELECT COUNT(DISTINCT last_seen_week) FROM employer_roles"
    ).fetchone()[0]
    FRESHNESS_WARMUP_WEEKS = 4

    if weeks_with_role_data < FRESHNESS_WARMUP_WEEKS:
        freshness_score = 50.0
        freshness_in_warmup = True
    elif total_active_roles > 0:
        freshness_ratio = total_new_roles / total_active_roles
        freshness_score = max(0.0, min(100.0, freshness_ratio * 250.0))
        freshness_in_warmup = False
    else:
        freshness_score = 50.0
        freshness_in_warmup = False

    # Signal 3: NET DELTA — aggregate WoW role count change, clamped at ±10%
    if total_roles_last_week > 0:
        delta_pct = (
            (total_roles_this_week - total_roles_last_week) / total_roles_last_week
        ) * 100
    else:
        delta_pct = 0.0

    if abs(delta_pct) > 10.0:
        print(
            f"  ⚠ Net delta {delta_pct:.1f}% exceeds 10% — "
            f"possible data quality issue, clamping to ±10%"
        )
        delta_pct = max(-10.0, min(10.0, delta_pct))

    net_delta_score = max(0.0, min(100.0, 50.0 + (delta_pct * 2.5)))

    # Source weight — decays with carry-forward ratio
    if successful_employers > 0:
        success_ratio = successful_employers / (successful_employers + zero_count)
        carry_forward_names = {
            p.employer_name
            for p in pulls
            if not isinstance(p, Exception) and p.ats_platform == "carry_forward"
        }
        carry_forward_count = sum(
            1 for e in employer_results
            if e.get("success") and e.get("name") in carry_forward_names
        )
        if carry_forward_count:
            decay_penalty = carry_forward_count * 0.5 / (successful_employers + zero_count)
            success_ratio = max(0.1, success_ratio - decay_penalty)
        source_weight = min(1.0, success_ratio / 0.7)
    else:
        source_weight = 0.1

    # Write signals to DB
    insert_signal(
        "employer_hiring_breadth", "pulse", "labour_market",
        float(adding_count), breadth_score, source_weight, week_iso,
    )
    insert_signal(
        "employer_req_freshness", "pulse", "labour_market",
        float(total_new_roles), freshness_score,
        0.0 if freshness_in_warmup else source_weight, week_iso,
    )
    insert_signal(
        "employer_net_delta", "pulse", "labour_market",
        float(total_roles_this_week), net_delta_score, source_weight, week_iso,
    )

    conn.close()

    # Build sector breadth summary
    sector_breadth: dict[str, dict] = {}
    for s in sector_total:
        total_s = sector_total[s]
        sector_breadth[s] = {
            "employers": total_s,
            "adding": sector_adding.get(s, 0),
            "cutting": sector_cutting.get(s, 0),
            "flat": total_s - sector_adding.get(s, 0) - sector_cutting.get(s, 0),
        }

    sorted_up = sorted(
        [d for d in employer_deltas if d["delta"] > 0],
        key=lambda x: x["delta_pct"], reverse=True,
    )[:3]
    sorted_down = sorted(
        [d for d in employer_deltas if d["delta"] < 0],
        key=lambda x: x["delta_pct"],
    )[:3]

    actual_employers_tracked = len(all_employers)
    actual_employers_successful = sum(1 for e in employer_results if e.get("success"))
    actual_employers_failed = actual_employers_tracked - actual_employers_successful

    return {
        "breadth_score": round(breadth_score, 1),
        "freshness_score": round(freshness_score, 1),
        "net_delta_score": round(net_delta_score, 1),
        "source_weight": round(source_weight, 2),
        "freshness_in_warmup": freshness_in_warmup,
        "employers_tracked": actual_employers_tracked,
        "employers_successful": actual_employers_successful,
        "employers_adding": adding_count,
        "employers_cutting": cutting_count,
        "employers_flat": flat_count,
        "employers_failed": actual_employers_failed,
        "employers_with_comparator": successful_employers,
        "total_roles": total_roles_this_week,
        "new_roles": total_new_roles,
        "stale_roles": total_stale_roles,
        "seniority_mix": seniority_totals,
        "employer_results": employer_results,
        "freeze_count": freeze_count,
        "sector_breadth": sector_breadth,
        "biggest_movers_up": sorted_up,
        "biggest_movers_down": sorted_down,
        "breadth_delta_divergence": breadth_delta_divergence,
    }
