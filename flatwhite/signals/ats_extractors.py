"""
ATS-aware employer hiring extractors — all httpx, no Playwright.

Tier 1A: JSON API (Workday, SmartRecruiters, Oracle HCM, Ashby, Atlassian, Taleo)
Tier 1B: HTML scraping (SuccessFactors CSB, Phenom, Avature, NGA.NET)
Tier 99: SEEK fallback (count-only, last resort)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import httpx
from bs4 import BeautifulSoup


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class RoleRecord:
    """A single job posting extracted from an employer's ATS."""

    title: str
    location: str | None = None
    department: str | None = None
    posted_date: str | None = None  # ISO date string if available
    url: str | None = None
    seniority_bucket: str | None = None  # 'junior', 'mid', 'senior', 'executive', 'unknown'


@dataclass
class EmployerPull:
    """Result of pulling one employer's careers data."""

    employer_id: int
    employer_name: str
    sector: str
    extraction_method: str  # 'json_api' or 'html_scrape'
    ats_platform: str
    roles: list[RoleRecord] = field(default_factory=list)
    total_count: int = 0
    success: bool = False
    error_message: str | None = None
    pulled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    needs_carry_forward: bool = False


# ── Per-domain rate limiting ──────────────────────────────────────────────────

_domain_last_request: dict[str, float] = defaultdict(float)
_domain_lock = asyncio.Lock()


async def _rate_limit_domain(url: str, min_interval: float = 3.0) -> None:
    """Ensure minimum interval between requests to the same domain."""
    domain = urlparse(url).netloc
    async with _domain_lock:
        elapsed = time.monotonic() - _domain_last_request[domain]
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        _domain_last_request[domain] = time.monotonic()


# ── Retry helper ──────────────────────────────────────────────────────────────

async def _retry_on_transient(coro_factory, max_retries: int = 1, backoff: float = 5.0):
    """Retry a coroutine factory on transient 429/503 errors."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503) and attempt < max_retries:
                last_exc = e
                retry_after = float(e.response.headers.get("Retry-After", backoff))
                await asyncio.sleep(min(retry_after, 30.0))
                continue
            raise
    raise last_exc  # type: ignore[misc]


# ── Australia location filter ─────────────────────────────────────────────────

AU_LOCATION_KEYWORDS = {
    "sydney", "melbourne", "brisbane", "perth", "adelaide",
    "canberra", "hobart", "darwin", "gold coast", "newcastle",
    "wollongong", "geelong", "cairns", "townsville", "toowoomba",
    "new south wales", "victoria", "queensland",
    "western australia", "south australia", "tasmania",
    "northern territory", "australia",
    "parramatta", "north sydney", "macquarie park", "chatswood",
    "barangaroo", "docklands", "southbank", "surry hills",
}

# Short state/country abbreviations — must match as whole words to avoid
# false positives (e.g. "wa" in "Warsaw", "sa" in "Sao Paulo").
_AU_SHORT_KEYWORDS = {"nsw", "vic", "qld", "wa", "sa", "tas", "act", "nt", "au"}
_AU_SHORT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _AU_SHORT_KEYWORDS) + r")\b"
)


def is_australian_role(role: RoleRecord) -> bool:
    """Check if a role is located in Australia."""
    loc = (role.location or "").lower()
    if not loc:
        return False
    if any(kw in loc for kw in AU_LOCATION_KEYWORDS):
        return True
    return bool(_AU_SHORT_RE.search(loc))


# ── Seniority classifier ──────────────────────────────────────────────────────

SENIORITY_PATTERNS: dict[str, list[str]] = {
    "executive": [
        r"\b(?:chief|ceo|cfo|cto|coo|cio|cpo|managing\s+director|md|partner|"
        r"general\s+manager|gm|vice\s+president|vp|svp|evp|head\s+of|"
        r"executive\s+director|country\s+head|regional\s+head|"
        r"national\s+(?:head|leader|director)|group\s+executive|"
        r"chief\s+(?:risk|legal|people|data|digital)\s+officer|"
        r"company\s+secretary|ses\s*(?:band)?\s*[123]?)\b"
    ],
    "senior": [
        r"\b(?:director|senior\s+manager|associate\s+director|"
        r"principal|lead|staff|senior\s+(?:engineer|developer|analyst|"
        r"consultant|advisor|associate|designer|architect|solicitor|"
        r"legal\s+counsel|risk\s+analyst|auditor)|"
        r"special\s+counsel|practice\s+(?:leader|director)|"
        r"team\s+lead(?:er)?|chapter\s+lead|tribe\s+lead|"
        r"associate\s+(?:partner|director)|el\s*2)\b"
    ],
    "mid": [
        r"\b(?:manager|consultant|engineer|developer|"
        r"advisor|designer|architect|specialist|coordinator|"
        r"solicitor|legal\s+counsel|auditor|underwriter|"
        r"risk\s+analyst|compliance\s+(?:officer|analyst)|"
        r"business\s+analyst|scrum\s+master|product\s+owner|"
        r"el\s*1|aps\s*[456])\b"
    ],
    "junior": [
        r"\b(?:graduate|grad\b|intern|trainee|junior|entry\s+level|"
        r"assistant|cadet|clerk|"
        r"paralegal|law\s+clerk|vacation\s+clerk|"
        r"graduate\s+(?:program|analyst|consultant|accountant|engineer)|"
        r"junior\s+(?:solicitor|auditor|analyst)|"
        r"aps\s*[123])\b"
    ],
}

# Priority order is the contract: executive → senior → mid → junior. First match wins.
# Do not reorder without verifying no collisions are introduced.


def classify_seniority(title: str) -> str:
    """Classify a job title into a seniority bucket. First match wins."""
    title_lower = title.lower()
    for bucket, patterns in SENIORITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, title_lower):
                return bucket
    return "unknown"


# ── Location normalisation and dedup key ─────────────────────────────────────

def normalise_location(loc: str | None) -> str:
    """Normalise location strings for dedup."""
    if not loc:
        return ""
    loc = loc.lower().strip()
    for suffix in [", australia", ", au", " australia", " au"]:
        if loc.endswith(suffix):
            loc = loc[: -len(suffix)]
    loc = re.sub(r"[,\-/]", " ", loc)
    loc = re.sub(r"\s+", " ", loc).strip()
    return loc


def _make_dedup_key(employer_id: int, title: str, location: str | None) -> str:
    """Compute dedup key for employer_roles UNIQUE constraint."""
    norm_title = title.strip().lower()
    norm_loc = normalise_location(location)
    return f"{employer_id}::{norm_title}::{norm_loc}"


# ── Corporate role filter ─────────────────────────────────────────────────────

CORPORATE_DEPARTMENTS: set[str] = {
    "finance", "legal", "people", "hr", "human resources", "technology",
    "digital", "data", "strategy", "marketing", "corporate affairs",
    "risk", "compliance", "audit", "treasury", "investor relations",
    "corporate", "head office", "group", "commercial", "transformation",
    "governance", "company secretary", "communications", "public affairs",
}

CORPORATE_TITLE_KEYWORDS: set[str] = {
    "manager", "director", "analyst", "engineer", "counsel",
    "advisor", "specialist", "lead", "architect", "consultant",
    "officer", "head of", "partner", "principal", "executive",
    "strategist", "auditor", "accountant", "developer", "designer",
}


def is_corporate_role(role: RoleRecord) -> bool:
    """Filter to corporate/professional roles for retail/resources/aviation employers."""
    dept = (role.department or "").lower()
    title = (role.title or "").lower()
    if any(d in dept for d in CORPORATE_DEPARTMENTS):
        return True
    if any(kw in title for kw in CORPORATE_TITLE_KEYWORDS):
        return True
    return False


# ── Workday CXS extractor ─────────────────────────────────────────────────────

MAX_WORKDAY_PAGES = 50  # Safety valve: 50 pages × 20 = 1,000 roles max


async def extract_workday(
    endpoint: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from a Workday CXS endpoint.

    Endpoint format:
    https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{siteId}/jobs
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="json_api", ats_platform="workday",
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload: dict = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    all_roles: list[RoleRecord] = []
    total: int | None = None
    page_count = 0
    owns_client = client is None

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0)

        while True:
            page_count += 1
            if page_count > MAX_WORKDAY_PAGES:
                break

            await _rate_limit_domain(endpoint)

            async def _do_request(_p=payload.copy(), _c=client, _e=endpoint):
                resp = await _c.post(_e, json=_p, headers=headers)
                resp.raise_for_status()
                return resp

            resp = await _retry_on_transient(_do_request)
            data = resp.json()

            if total is None:
                total = data.get("total", 0)

            postings = data.get("jobPostings", [])
            if not postings:
                break

            for posting in postings:
                location = posting.get("locationsText")
                if not location:
                    # Some Workday instances omit locationsText — extract
                    # from externalPath (format: /job/{Location-Slug}/...)
                    ext_path = posting.get("externalPath", "")
                    path_match = re.match(r"/job/([^/]+)/", ext_path)
                    if path_match:
                        location = path_match.group(1).replace("-", " ")
                if not location:
                    # Last resort: first bulletField that isn't a job ID
                    for bf in posting.get("bulletFields", []):
                        if bf and not re.match(r"^[A-Z]{0,4}[-_]?\d{4,}$", bf.strip()):
                            location = bf
                            break
                role = RoleRecord(
                    title=posting.get("title", ""),
                    location=location,
                    posted_date=posting.get("postedOn", None),
                    url=posting.get("externalPath", None),
                )
                role.seniority_bucket = classify_seniority(role.title)
                all_roles.append(role)

            payload["offset"] += len(postings)
            if payload["offset"] >= (total or 0):
                break

        pull.roles = all_roles
        pull.total_count = total or len(all_roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── SmartRecruiters extractor ─────────────────────────────────────────────────

async def extract_smartrecruiters(
    company_slug: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from SmartRecruiters public API.

    GET https://api.smartrecruiters.com/v1/companies/{slug}/postings
    No authentication required. Returns paginated JSON.
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="json_api", ats_platform="smartrecruiters",
    )
    base_url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings"
    owns_client = client is None
    offset = 0
    limit = 100
    total = 0

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0)

        while True:
            await _rate_limit_domain(base_url)
            url = f"{base_url}?limit={limit}&offset={offset}"

            async def _do_request(_u=url, _c=client):
                resp = await _c.get(_u)
                resp.raise_for_status()
                return resp

            resp = await _retry_on_transient(_do_request)
            data = resp.json()

            postings = data.get("content", [])
            total = data.get("totalFound", 0)

            for posting in postings:
                location = posting.get("location", {})
                loc_str = location.get("city") or location.get("country")
                role = RoleRecord(
                    title=posting.get("name", ""),
                    location=loc_str,
                    department=posting.get("department", {}).get("label"),
                    url=posting.get("ref"),
                )
                role.seniority_bucket = classify_seniority(role.title)
                pull.roles.append(role)

            offset += len(postings)
            if offset >= total or not postings:
                break

        pull.total_count = total
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── Oracle Cloud HCM REST extractor ──────────────────────────────────────────

async def extract_oracle_hcm(
    instance: str,
    site_number: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from Oracle Cloud HCM Recruiting REST API.

    GET https://{instance}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    No authentication required for public candidate experience endpoints.
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="json_api", ats_platform="oracle_hcm",
    )
    base_url = f"https://{instance}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    owns_client = client is None
    offset = 0
    limit = 25
    total: int | None = None

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0)

        while True:
            await _rate_limit_domain(base_url)
            params = (
                f"onlyData=true&expand=requisitionList"
                f"&finder=findReqs;siteNumber={site_number},limit={limit},offset={offset}"
                f",sortBy=POSTING_DATES_DESC"
            )
            url = f"{base_url}?{params}"

            async def _do_request(_u=url, _c=client):
                resp = await _c.get(_u, headers={"Accept": "application/json"})
                resp.raise_for_status()
                return resp

            resp = await _retry_on_transient(_do_request)
            data = resp.json()

            if total is None:
                total = data.get("TotalJobsCount", 0)

            items = data.get("items", [])
            req_list: list[dict] = []
            for item in items:
                req_list.extend(item.get("requisitionList", []))

            if not req_list:
                break

            for req in req_list:
                role = RoleRecord(
                    title=req.get("Title", ""),
                    location=req.get("PrimaryLocation"),
                    posted_date=req.get("PostedDate"),
                )
                role.seniority_bucket = classify_seniority(role.title)
                pull.roles.append(role)

            offset += len(req_list)
            if offset >= (total or 0):
                break

        pull.total_count = total or len(pull.roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── Ashby extractor ───────────────────────────────────────────────────────────

async def extract_ashby(
    slug: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """Extract roles from Ashby HQ public job board API."""
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="json_api", ats_platform="ashby",
    )
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    owns_client = client is None

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0)
        await _rate_limit_domain(url)

        async def _do_request(_u=url, _c=client):
            resp = await _c.get(_u)
            resp.raise_for_status()
            return resp

        resp = await _retry_on_transient(_do_request)
        body = resp.json()
        # Ashby returns {"jobs": [...], "apiVersion": "..."} or a flat list
        postings = body.get("jobs", body) if isinstance(body, dict) else body

        for posting in postings:
            if not isinstance(posting, dict):
                continue
            location = posting.get("location", "")
            role = RoleRecord(
                title=posting.get("title", ""),
                location=location,
                department=posting.get("department"),
                posted_date=posting.get("publishedDate"),
                url=posting.get("jobUrl"),
            )
            role.seniority_bucket = classify_seniority(role.title)
            pull.roles.append(role)

        pull.total_count = len(pull.roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── Atlassian custom extractor ────────────────────────────────────────────────

async def extract_atlassian(
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """Extract roles from Atlassian custom careers API."""
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="json_api", ats_platform="atlassian",
    )
    url = "https://www.atlassian.com/endpoint/careers/listings"
    owns_client = client is None

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0)
        await _rate_limit_domain(url)

        async def _do_request(_u=url, _c=client):
            resp = await _c.get(_u)
            resp.raise_for_status()
            return resp

        resp = await _retry_on_transient(_do_request)
        postings = resp.json()

        for posting in postings:
            locations = posting.get("locations", [])
            loc_str = ", ".join(locations) if locations else None
            role = RoleRecord(
                title=posting.get("title", ""),
                location=loc_str,
                department=posting.get("category"),
                posted_date=posting.get("updatedDate"),
                url=posting.get("applyUrl"),
            )
            role.seniority_bucket = classify_seniority(role.title)
            pull.roles.append(role)

        pull.total_count = len(postings)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── Oracle Taleo REST extractor ───────────────────────────────────────────────

async def extract_taleo(
    instance: str,
    portal_id: str,
    career_section: str,
    employer_id: int,
    employer_name: str,
    sector: str,
) -> EmployerPull:
    """
    Extract roles from Oracle Taleo REST API.

    Two-step: GET job search page for session cookie, then POST to REST endpoint.
    The tz and Origin headers are critical — without them the API returns 500.
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="json_api", ats_platform="taleo",
    )
    base_url = f"https://{instance}"
    session_url = f"{base_url}/careersection/{career_section}/jobsearch.ftl?lang=en"
    api_url = f"{base_url}/careersection/rest/jobboard/searchjobs?lang=en&portal={portal_id}"

    payload: dict = {
        "multilineEnabled": False,
        "sortingSelection": {"sortBySelectionParam": "3", "ascendingSortingOrder": "false"},
        "fieldData": {
            "fields": {"KEYWORD": "", "LOCATION": "", "ORGANIZATION": ""},
            "valid": "true",
        },
        "filterSelectionParam": {"searchFilterSelections": [
            {"id": "POSTING_DATE", "selectedValues": []},
            {"id": "LOCATION", "selectedValues": []},
            {"id": "JOB_FIELD", "selectedValues": []},
        ]},
        "advancedSearchFiltersSelectionParam": {"searchFilterSelections": [
            {"id": "ORGANIZATION", "selectedValues": []},
            {"id": "LOCATION", "selectedValues": []},
            {"id": "JOB_FIELD", "selectedValues": []},
            {"id": "JOB_NUMBER", "selectedValues": []},
            {"id": "URGENT_JOB", "selectedValues": []},
            {"id": "EMPLOYEE_STATUS", "selectedValues": []},
            {"id": "JOB_SHIFT", "selectedValues": []},
        ]},
        "pageNo": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: GET session cookie
            await _rate_limit_domain(base_url)
            session_resp = await client.get(session_url)
            cookies = session_resp.cookies

            # Step 2: POST with session cookie and required headers
            req_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "tz": "Australia/Sydney",
                "tzname": "Australia/Sydney",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": base_url,
                "Referer": session_url,
            }

            all_roles: list[RoleRecord] = []
            total: int | None = None

            while True:
                await _rate_limit_domain(base_url)
                resp = await client.post(
                    api_url, json=payload, headers=req_headers, cookies=cookies
                )
                resp.raise_for_status()
                data = resp.json()

                paging = data.get("pagingData", {})
                if total is None:
                    total = paging.get("totalCount", 0)

                reqs = data.get("requisitionList", [])
                if not reqs:
                    break

                for req in reqs:
                    cols = req.get("column", [])
                    title = cols[0] if len(cols) > 0 else ""
                    location = cols[1] if len(cols) > 1 else None
                    role = RoleRecord(title=title, location=location)
                    role.seniority_bucket = classify_seniority(role.title)
                    all_roles.append(role)

                current_page = paging.get("currentPageNo", 1)
                page_size = paging.get("pageSize", 25)
                if current_page * page_size >= (total or 0):
                    break
                payload["pageNo"] += 1

        pull.roles = all_roles
        pull.total_count = total or len(all_roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    return pull


# ── SuccessFactors CSB scraper ────────────────────────────────────────────────

async def extract_successfactors(
    portal_domain: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    au_keyword_filter: bool = False,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from SuccessFactors Career Site Builder (CSB) /search/ pages.

    The CSB frontend serves server-rendered HTML at /search/ — no JavaScript
    execution, no CSRF tokens, no session cookies required. Do NOT use the
    legacy career{N}.successfactors.com URLs — those are SPAs.

    au_keyword_filter=True: append q=australia to filter global portals (e.g. EY).
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="html_scrape", ats_platform="successfactors",
    )
    base_url = f"https://{portal_domain}/search/"
    owns_client = client is None
    all_roles: list[RoleRecord] = []
    total: int | None = None
    offset = 0

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        while True:
            await _rate_limit_domain(base_url)
            q_val = "australia" if au_keyword_filter else ""
            url = (
                f"{base_url}?q={q_val}"
                f"&sortColumn=referencedate&sortDirection=desc&startrow={offset}"
            )

            async def _do_request(_u=url, _c=client):
                resp = await _c.get(_u)
                resp.raise_for_status()
                return resp

            resp = await _retry_on_transient(_do_request)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract total count — CSB pagination text has no spaces
            # and uses en-dash: e.g. "Results1 – 25of531"
            if total is None:
                pag_el = soup.find(class_="pagination-label-row")
                pag_text = pag_el.get_text(strip=True) if pag_el else soup.get_text()
                # Try compact format first: Results1 – 25of531
                match = re.search(
                    r"Results\s*\d+\s*[\u2013\u2014\-]\s*\d+\s*of\s*([\d,]+)",
                    pag_text,
                )
                if not match:
                    # Fallback: "Results X - Y of Z" with normal spacing
                    match = re.search(
                        r"Results\s+\d+\s+-\s+\d+\s+of\s+([\d,]+)",
                        pag_text,
                    )
                if match:
                    total = int(match.group(1).replace(",", ""))
                else:
                    pull.total_count = 0
                    pull.success = False
                    pull.error_message = (
                        "Could not extract total count from SuccessFactors"
                    )
                    return pull

            # Extract job rows from searchResults table — only data-row rows
            table = soup.find("table", class_="searchResults")
            page_roles: list[RoleRecord] = []
            if table:
                rows = table.find_all("tr", class_="data-row")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        link = cells[0].find("a", class_="jobTitle-link")
                        if not link:
                            link = cells[0].find("a")
                        if link:
                            # Location is always in the second cell
                            location_text = cells[1].get_text(strip=True) or None
                            # Date may be in a colDate cell if present
                            posted = None
                            for cell in cells[2:]:
                                cell_classes = cell.get("class") or []
                                if "colDate" in cell_classes:
                                    posted = cell.get_text(strip=True) or None
                                    break
                            role = RoleRecord(
                                title=link.get_text(strip=True),
                                location=location_text,
                                posted_date=posted,
                                url=link.get("href"),
                            )
                            role.seniority_bucket = classify_seniority(role.title)
                            page_roles.append(role)

            if not page_roles:
                break

            all_roles.extend(page_roles)
            offset += len(page_roles)
            if offset >= (total or 0):
                break

        pull.roles = all_roles
        pull.total_count = total or len(all_roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── Phenom People scraper ─────────────────────────────────────────────────────

def _extract_phenom_eager_load(html: str) -> dict | None:
    """Extract the eagerLoadRefineSearch JSON object from Phenom HTML.

    Phenom embeds the data as a JSON key inside the phApp.ddo object:
        phApp.ddo = {..., "eagerLoadRefineSearch":{...}, ...};

    Uses brace-depth counting to find the matching closing brace, which
    is more robust than a non-greedy regex on deeply nested JSON.
    """
    marker = "eagerLoadRefineSearch"
    idx = html.find(marker)
    if idx < 0:
        return None

    # Advance past the key and its colon/quote delimiters to the opening brace
    colon_idx = html.find(":", idx + len(marker))
    if colon_idx < 0:
        return None

    brace_start = html.find("{", colon_idx)
    if brace_start < 0:
        return None

    depth = 0
    end = brace_start
    for i in range(brace_start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    else:
        # Ran off the end without closing — malformed
        return None

    try:
        return json.loads(html[brace_start:end])
    except json.JSONDecodeError:
        return None


async def extract_phenom(
    portal_domain: str,
    locale: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from Phenom People CareerConnect portal.

    Phenom embeds job data as JSON in the phApp.ddo.eagerLoadRefineSearch
    object in the server-rendered HTML. No browser needed.
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="html_scrape", ats_platform="phenom",
    )
    base_url = f"https://{portal_domain}/{locale}/search-results"
    owns_client = client is None
    all_roles: list[RoleRecord] = []
    total: int | None = None
    offset = 0

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        while True:
            await _rate_limit_domain(base_url)
            url = f"{base_url}?from={offset}&s=1"

            async def _do_request(_u=url, _c=client):
                resp = await _c.get(_u)
                resp.raise_for_status()
                return resp

            resp = await _retry_on_transient(_do_request)

            # Extract embedded JSON from phApp.ddo object
            data = _extract_phenom_eager_load(resp.text)
            if data is None:
                pull.error_message = "Could not find eagerLoadRefineSearch in Phenom HTML"
                pull.success = False
                return pull

            if total is None:
                total = data.get("totalHits", 0)

            jobs = data.get("data", {}).get("jobs", [])
            if not jobs:
                break

            for job in jobs:
                loc_parts = [
                    p for p in [job.get("city"), job.get("state"), job.get("country")]
                    if p
                ]
                role = RoleRecord(
                    title=job.get("title", ""),
                    location=", ".join(loc_parts) if loc_parts else None,
                    department=job.get("category"),
                    posted_date=job.get("postedDate"),
                    url=job.get("applyUrl"),
                )
                role.seniority_bucket = classify_seniority(role.title)
                all_roles.append(role)

            offset += len(jobs)
            if offset >= (total or 0):
                break

        pull.roles = all_roles
        pull.total_count = total or len(all_roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── Avature scraper ───────────────────────────────────────────────────────────

async def extract_avature(
    portal_domain: str,
    search_path: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from Avature ATS portal (server-rendered HTML).

    Used for: Macquarie Group (recruitment.macquarie.com),
              Woolworths Group (careers.woolworthsgroup.com.au).
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="html_scrape", ats_platform="avature",
    )
    base_url = f"https://{portal_domain}{search_path}"
    owns_client = client is None
    all_roles: list[RoleRecord] = []
    total: int | None = None
    offset = 0
    per_page = 100

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        while True:
            await _rate_limit_domain(base_url)
            url = f"{base_url}?jobOffset={offset}&jobRecordsPerPage={per_page}"

            async def _do_request(_u=url, _c=client):
                resp = await _c.get(_u)
                resp.raise_for_status()
                return resp

            resp = await _retry_on_transient(_do_request)
            soup = BeautifulSoup(resp.text, "html.parser")

            if total is None:
                text = soup.get_text()
                m = re.search(r"([\d,]+)\s+(?:results?|jobs?|positions?)", text, re.IGNORECASE)
                if m:
                    total = int(m.group(1).replace(",", ""))

            # Primary: divs with job/position/posting classes
            job_divs = soup.find_all("div", class_=re.compile(r"job|position|posting", re.I))
            # Fallback: Avature article--result pattern (e.g. Woolworths)
            if not job_divs:
                job_divs = soup.find_all("article", class_=re.compile(r"result", re.I))
            if not job_divs:
                # Last resort: links with job-like URLs
                job_divs = [
                    a for a in soup.find_all("a", href=True)
                    if re.search(r"/job|/position|/careers/|/JobDetail/", a.get("href", ""))
                ]

            if not job_divs:
                break

            for div in job_divs:
                link = div.find("a") if hasattr(div, "find") else div
                title_elem = (
                    div.find(["h2", "h3", "h4", "span"]) if hasattr(div, "find") else None
                )
                title = (title_elem or link).get_text(strip=True) if (title_elem or link) else ""
                if not title:
                    continue
                role = RoleRecord(
                    title=title,
                    url=link.get("href") if hasattr(link, "get") else None,
                )
                role.seniority_bucket = classify_seniority(role.title)
                all_roles.append(role)

            offset += len(job_divs)
            if total and offset >= total:
                break
            if len(job_divs) < per_page:
                break

        pull.roles = all_roles
        pull.total_count = total or len(all_roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── NGA.NET ColdFusion scraper ────────────────────────────────────────────────

async def extract_ngasoft(
    subdomain: str,
    board_id: str,
    employer_id: int,
    employer_name: str,
    sector: str,
    client: httpx.AsyncClient | None = None,
) -> EmployerPull:
    """
    Extract roles from NGA.NET ColdFusion career portal.

    Used for: ATO (ato.nga.net.au).
    Server-rendered ColdFusion pages — no JavaScript execution required.
    Confirm HTML structure against live site before finalising selectors.
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="html_scrape", ats_platform="ngasoft",
    )
    base_url = f"https://{subdomain}.nga.net.au/cp/index.cfm"
    owns_client = client is None

    try:
        if owns_client:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        await _rate_limit_domain(base_url)
        url = f"{base_url}?event=jobs.listJobs&CurATC=EXT&CurBID={board_id}"

        async def _do_request(_u=url, _c=client):
            resp = await _c.get(_u)
            resp.raise_for_status()
            return resp

        resp = await _retry_on_transient(_do_request)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Count extraction — adjust selectors after inspecting live HTML
        text = soup.get_text()
        total_match = re.search(
            r"([\d,]+)\s+(?:results?|jobs?|positions?|vacancies?)", text, re.IGNORECASE
        )
        total = int(total_match.group(1).replace(",", "")) if total_match else 0

        # Job rows — confirm exact class names against live site
        job_items = soup.find_all(
            ["tr", "li", "div"], class_=re.compile(r"job|result|posting", re.I)
        )
        for item in job_items:
            link = item.find("a", href=True)
            if link:
                role = RoleRecord(
                    title=link.get_text(strip=True),
                    url=link.get("href"),
                )
                role.seniority_bucket = classify_seniority(role.title)
                pull.roles.append(role)

        pull.total_count = total or len(pull.roles)
        pull.success = True

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    finally:
        if owns_client and client:
            await client.aclose()

    return pull


# ── SEEK fallback (Tier 99 only) ──────────────────────────────────────────────

async def extract_seek_fallback(
    employer_name: str,
    employer_id: int,
    sector: str,
    seek_slug: str | None = None,
) -> EmployerPull:
    """
    Last-resort fallback using SEEK company profile page.
    Returns count only — no individual role data.
    Only used when all primary extractors fail (Tier 99 carry-forward applies first).
    """
    pull = EmployerPull(
        employer_id=employer_id, employer_name=employer_name, sector=sector,
        extraction_method="html_scrape", ats_platform="seek_fallback",
    )
    if seek_slug:
        search_url = f"https://www.seek.com.au/{seek_slug}-jobs/in-All-Australia/at-this-company"
    else:
        search_url = f"https://www.seek.com.au/jobs?keywords={quote(employer_name)}"

    _seek_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            await _rate_limit_domain(search_url, min_interval=5.0)
            resp = await client.get(search_url, headers=_seek_headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Strategy 1: JSON-LD structured data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string)
                    if isinstance(ld, dict) and "numberOfItems" in ld:
                        pull.total_count = int(ld["numberOfItems"])
                        pull.success = True
                        return pull
                except Exception:
                    continue

            # Strategy 2: Regex on page text
            text = soup.get_text()
            match = re.search(r"([\d,]+)\s+jobs?", text, re.IGNORECASE)
            if match:
                pull.total_count = int(match.group(1).replace(",", ""))
                pull.success = True
            else:
                pull.success = False
                pull.error_message = "Could not extract count from SEEK"

    except Exception as e:
        pull.error_message = str(e)
        pull.success = False

    return pull
