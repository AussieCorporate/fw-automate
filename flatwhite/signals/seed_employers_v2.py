"""
One-time migration script: seed all 33 v2 employers into employer_watchlist.

Run once after schema migrations complete:
    python -m flatwhite.signals.seed_employers_v2

Safe to re-run: uses upsert on employer_name. Does not modify existing
employer_snapshots or employer_roles data.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flatwhite.db import get_connection


# All 33 confirmed employers — March 2026 ATS research pass
EMPLOYERS_V2: list[dict] = [
    # ── Tier 1A: Workday CXS (13 employers) ─────────────────────────────────
    {
        "employer_name": "CBA",
        "sector": "banking",
        "careers_url": "https://cba.wd3.myworkdayjobs.com/wday/cxs/cba/CommBank_Careers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://cba.wd3.myworkdayjobs.com/wday/cxs/cba/CommBank_Careers/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "commonwealth-bank",
    },
    {
        "employer_name": "NAB",
        "sector": "banking",
        "careers_url": "https://nab.wd3.myworkdayjobs.com/wday/cxs/nab/nab_careers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://nab.wd3.myworkdayjobs.com/wday/cxs/nab/nab_careers/jobs",
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "nab",
    },
    {
        "employer_name": "Telstra",
        "sector": "telco",
        "careers_url": "https://telstra.wd3.myworkdayjobs.com/wday/cxs/telstra/Telstra_Careers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://telstra.wd3.myworkdayjobs.com/wday/cxs/telstra/Telstra_Careers/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "telstra",
    },
    {
        "employer_name": "Lendlease",
        "sector": "infrastructure",
        "careers_url": "https://lendlease.wd3.myworkdayjobs.com/wday/cxs/lendlease/lendleasecareers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://lendlease.wd3.myworkdayjobs.com/wday/cxs/lendlease/lendleasecareers/jobs",
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "lendlease",
    },
    {
        "employer_name": "Transurban",
        "sector": "infrastructure",
        "careers_url": "https://transurban.wd3.myworkdayjobs.com/wday/cxs/transurban/TU_AU/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://transurban.wd3.myworkdayjobs.com/wday/cxs/transurban/TU_AU/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
    {
        "employer_name": "Allens",
        "sector": "law",
        "careers_url": "https://allens.wd3.myworkdayjobs.com/wday/cxs/allens/Allens/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://allens.wd3.myworkdayjobs.com/wday/cxs/allens/Allens/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "allens",
    },
    {
        "employer_name": "Clayton Utz",
        "sector": "law",
        "careers_url": "https://claytonutz.wd3.myworkdayjobs.com/wday/cxs/claytonutz/Claytonutz1/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://claytonutz.wd3.myworkdayjobs.com/wday/cxs/claytonutz/Claytonutz1/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "clayton-utz",
    },
    {
        "employer_name": "REA Group",
        "sector": "tech",
        "careers_url": "https://reagroup.wd3.myworkdayjobs.com/wday/cxs/reagroup/reacareers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://reagroup.wd3.myworkdayjobs.com/wday/cxs/reagroup/reacareers/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "rea-group",
    },
    {
        "employer_name": "QBE Insurance",
        "sector": "insurance",
        "careers_url": "https://qbe.wd3.myworkdayjobs.com/wday/cxs/qbe/QBE-Careers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://qbe.wd3.myworkdayjobs.com/wday/cxs/qbe/QBE-Careers/jobs",
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "qbe-insurance",
    },
    {
        "employer_name": "Qantas",
        "sector": "aviation",
        "careers_url": "https://qantas.wd3.myworkdayjobs.com/wday/cxs/qantas/Qantas_Careers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://qantas.wd3.myworkdayjobs.com/wday/cxs/qantas/Qantas_Careers/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 1,
        "seek_slug": "qantas",
    },
    {
        "employer_name": "Accenture",
        "sector": "consulting",
        "careers_url": "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs",
        "ats_platform": "workday",
        # AU country facet ID (d903bb3...) filters to 234 AU roles at query time.
        # Needed because the global site returns blank locations — post-fetch AU
        # filtering would exclude all roles. Facet ID from locationCountry facet.
        "ats_endpoint": 'https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs||{"locationCountry":["d903bb3fedad45039383f6de334ad4db"]}',
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "accenture",
    },
    {
        "employer_name": "CSL",
        "sector": "pharma",
        "careers_url": "https://csl.wd1.myworkdayjobs.com/wday/cxs/csl/CSL_External/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://csl.wd1.myworkdayjobs.com/wday/cxs/csl/CSL_External/jobs",
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "csl",
    },
    {
        "employer_name": "King & Wood Mallesons",
        "sector": "law",
        "careers_url": "https://kwm.wd105.myworkdayjobs.com/wday/cxs/kwm/careers_kwm/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://kwm.wd105.myworkdayjobs.com/wday/cxs/kwm/careers_kwm/jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "king-wood-mallesons",
    },
    # ── Tier 1A: SmartRecruiters (3 employers) ───────────────────────────────
    {
        "employer_name": "Canva",
        "sector": "tech",
        "careers_url": "https://api.smartrecruiters.com/v1/companies/Canva/postings",
        "ats_platform": "smartrecruiters",
        "ats_endpoint": "Canva",
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "canva",
    },
    {
        "employer_name": "KPMG Australia",
        "sector": "big4",
        "careers_url": "https://api.smartrecruiters.com/v1/companies/KPMGAustralia1/postings",
        "ats_platform": "smartrecruiters",
        "ats_endpoint": "KPMGAustralia1",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "kpmg",
    },
    {
        "employer_name": "Rio Tinto",
        "sector": "resources",
        "careers_url": "https://riotinto.wd3.myworkdayjobs.com/wday/cxs/riotinto/RioTinto_Careers/jobs",
        "ats_platform": "workday",
        "ats_endpoint": "https://riotinto.wd3.myworkdayjobs.com/wday/cxs/riotinto/RioTinto_Careers/jobs",
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 1,
        "seek_slug": "rio-tinto",
    },
    # ── Tier 1A: Oracle Cloud HCM REST (2 employers) ─────────────────────────
    {
        "employer_name": "Westpac",
        "sector": "banking",
        "careers_url": "https://ebuu.fa.ap1.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "ats_platform": "oracle_hcm",
        "ats_endpoint": "ebuu.fa.ap1.oraclecloud.com|CX",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "westpac",
    },
    {
        "employer_name": "AustralianSuper",
        "sector": "super",
        "careers_url": "https://ejjl.fa.ap1.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "ats_platform": "oracle_hcm",
        "ats_endpoint": "ejjl.fa.ap1.oraclecloud.com|CX_1",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
    # ── Tier 1A: Ashby HQ (1 employer) ────────────────────────────────────────
    {
        "employer_name": "Xero",
        "sector": "tech",
        "careers_url": "https://api.ashbyhq.com/posting-api/job-board/xero",
        "ats_platform": "ashby",
        "ats_endpoint": "xero",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
    # ── Tier 1A: Atlassian custom (1 employer) ─────────────────────────────────
    {
        "employer_name": "Atlassian",
        "sector": "tech",
        "careers_url": "https://www.atlassian.com/endpoint/careers/listings",
        "ats_platform": "atlassian",
        "ats_endpoint": None,
        "extraction_method": "json_api",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "atlassian",
    },
    # ── Tier 1A: Oracle Taleo REST (1 employer) ────────────────────────────────
    {
        "employer_name": "NSW Government",
        "sector": "government",
        "careers_url": "https://iworkfornsw.taleo.net/careersection/all_jobs/jobsearch.ftl",
        "ats_platform": "taleo",
        "ats_endpoint": "iworkfornsw.taleo.net|2160143997|all_jobs",
        "extraction_method": "json_api",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
    # ── Tier 1B: SuccessFactors CSB (5 employers) ──────────────────────────────
    {
        "employer_name": "Deloitte Australia",
        "sector": "big4",
        "careers_url": "https://jobs.deloitte.com.au/search/",
        "ats_platform": "successfactors",
        "ats_endpoint": "jobs.deloitte.com.au",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "deloitte",
    },
    {
        "employer_name": "EY Australia",
        "sector": "big4",
        "careers_url": "https://careers.ey.com/search/",
        "ats_platform": "successfactors",
        "ats_endpoint": "careers.ey.com",
        "extraction_method": "html_scrape",
        "country_filter": "AU",
        "corporate_only": 0,
        "seek_slug": "ernst-young",
    },
    {
        "employer_name": "ANZ",
        "sector": "banking",
        "careers_url": "https://careers.anz.com/search/",
        "ats_platform": "successfactors",
        "ats_endpoint": "careers.anz.com",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "anz",
    },
    {
        "employer_name": "BHP",
        "sector": "resources",
        "careers_url": "https://careers.bhp.com/search/",
        "ats_platform": "successfactors",
        "ats_endpoint": "careers.bhp.com",
        "extraction_method": "html_scrape",
        "country_filter": "AU",
        "corporate_only": 1,
        "seek_slug": "bhp",
    },
    {
        "employer_name": "MinterEllison",
        "sector": "law",
        "careers_url": "https://careers.minterellison.com/search/",
        "ats_platform": "successfactors",
        "ats_endpoint": "careers.minterellison.com",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
    # ── Tier 1B: Phenom People (4 employers) ───────────────────────────────────
    {
        "employer_name": "PwC Australia",
        "sector": "big4",
        "careers_url": "https://jobs-au.pwc.com/au/en/search-results",
        "ats_platform": "phenom",
        "ats_endpoint": "jobs-au.pwc.com|au/en",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "pwc",
    },
    {
        "employer_name": "IAG",
        "sector": "insurance",
        "careers_url": "https://careers.iag.com.au/global/en/search-results",
        "ats_platform": "phenom",
        "ats_endpoint": "careers.iag.com.au|global/en",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
    {
        "employer_name": "Herbert Smith Freehills",
        "sector": "law",
        "careers_url": "https://careers.hsfkramer.com/global/en/search-results",
        "ats_platform": "phenom",
        "ats_endpoint": "careers.hsfkramer.com|global/en",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "herbert-smith-freehills",
    },
    {
        "employer_name": "Coles Group",
        "sector": "retail",
        "careers_url": "https://colescareers.com.au/au/en/search-results",
        "ats_platform": "phenom",
        "ats_endpoint": "colescareers.com.au|au/en",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 1,
        "seek_slug": "coles",
    },
    # ── Tier 1B: Avature (2 employers) ─────────────────────────────────────────
    {
        "employer_name": "Macquarie Group",
        "sector": "banking",
        "careers_url": "https://recruitment.macquarie.com/en_US/careers/SearchJobs",
        "ats_platform": "avature",
        "ats_endpoint": "recruitment.macquarie.com|/en_US/careers/SearchJobs",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": "macquarie",
    },
    {
        "employer_name": "Woolworths Group",
        "sector": "retail",
        "careers_url": "https://careers.woolworthsgroup.com.au/en_GB/apply/search-jobs",
        "ats_platform": "avature",
        "ats_endpoint": "careers.woolworthsgroup.com.au|/en_GB/apply/search-jobs",
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 1,
        "seek_slug": "woolworths",
    },
    # ── Tier 1B: NGA.NET ColdFusion (1 employer) ───────────────────────────────
    {
        "employer_name": "ATO",
        "sector": "government",
        "careers_url": "https://ato.nga.net.au/cp/index.cfm",
        "ats_platform": "ngasoft",
        "ats_endpoint": "ato|ATO",  # subdomain|board_id — confirm board_id from live site
        "extraction_method": "html_scrape",
        "country_filter": None,
        "corporate_only": 0,
        "seek_slug": None,
    },
]


def seed_employers() -> None:
    """Upsert all 33 v2 employers into employer_watchlist."""
    conn = get_connection()

    for emp in EMPLOYERS_V2:
        conn.execute(
            """INSERT INTO employer_watchlist
             (employer_name, sector, careers_url, active,
              ats_platform, ats_endpoint, extraction_method,
              country_filter, corporate_only, seek_slug)
             VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(employer_name) DO UPDATE SET
              sector = excluded.sector,
              careers_url = excluded.careers_url,
              ats_platform = excluded.ats_platform,
              ats_endpoint = excluded.ats_endpoint,
              extraction_method = excluded.extraction_method,
              country_filter = excluded.country_filter,
              corporate_only = excluded.corporate_only,
              seek_slug = excluded.seek_slug,
              active = 1
            """,
            (
                emp["employer_name"],
                emp["sector"],
                emp["careers_url"],
                emp["ats_platform"],
                emp["ats_endpoint"],
                emp["extraction_method"],
                emp["country_filter"],
                emp["corporate_only"],
                emp["seek_slug"],
            ),
        )

    # Deactivate v1 employers not in v2 watchlist
    v2_names = {e["employer_name"] for e in EMPLOYERS_V2}
    all_employers = conn.execute(
        "SELECT employer_name FROM employer_watchlist"
    ).fetchall()
    for row in all_employers:
        if row["employer_name"] not in v2_names:
            conn.execute(
                "UPDATE employer_watchlist SET active = 0 WHERE employer_name = ?",
                (row["employer_name"],),
            )
            print(f"  Deactivated v1-only employer: {row['employer_name']}")

    conn.commit()

    total = conn.execute(
        "SELECT COUNT(*) FROM employer_watchlist WHERE active = 1"
    ).fetchone()[0]
    unknown = conn.execute(
        "SELECT COUNT(*) FROM employer_watchlist WHERE ats_platform = 'unknown' AND active = 1"
    ).fetchone()[0]
    print(f"Seeded {len(EMPLOYERS_V2)} employers. Active: {total}. Unknown ATS: {unknown}")
    conn.close()


if __name__ == "__main__":
    seed_employers()
