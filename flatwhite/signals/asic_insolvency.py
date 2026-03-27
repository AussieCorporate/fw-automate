"""ASIC Series 1 — Companies entering external administration (weekly count).

Lane A pulse signal. Higher insolvency counts indicate greater corporate stress,
so the normalised score is INVERTED: more insolvencies = lower score.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

from flatwhite.db import get_current_week_iso, get_recent_signals, insert_signal
from flatwhite.signals.normalise import get_min_weeks_warm, normalise_hybrid

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _parse_insolvency_page(html: str) -> int | None:
    """Parse HTML tables from the ASIC Series 1 page for the most recent weekly count.

    Walks tables in reverse order, then rows in reverse, looking for an integer
    value in the 10–5000 range (sanity check to avoid picking up year labels,
    percentages, or other noise).
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None

    for table in reversed(tables):
        rows = table.find_all("tr")
        for row in reversed(rows):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            for cell_text in reversed(cells):
                # Strip commas and whitespace, try to parse as int
                cleaned = re.sub(r"[,\s]", "", cell_text)
                try:
                    value = int(cleaned)
                    if 10 <= value <= 5000:
                        return value
                except ValueError:
                    continue
    return None


def _try_excel_download(url: str) -> int | None:
    """Fallback: download the Series 1 Excel file and parse the latest weekly count.

    Walks rows in reverse looking for an integer in the 10–5000 range.
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("  openpyxl not available — skipping Excel fallback")
        return None

    try:
        response = httpx.get(
            url,
            headers={"User-Agent": BROWSER_UA},
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception as e:
        print(f"  Excel download failed: {e}")
        return None

    try:
        wb = load_workbook(filename=io.BytesIO(response.content), read_only=True, data_only=True)
        # Try the first sheet
        ws = wb.active
        if ws is None:
            return None

        # Walk rows in reverse looking for an integer count
        rows = list(ws.iter_rows(values_only=True))
        for row in reversed(rows):
            for cell in reversed(row):
                if cell is None:
                    continue
                try:
                    value = int(cell)
                    if 10 <= value <= 5000:
                        return value
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"  Excel parse failed: {e}")
        return None

    return None


def pull_asic_insolvency() -> float:
    """Fetch ASIC Series 1 insolvency data and insert as a pulse signal.

    Returns the normalised score (0–100, inverted: more insolvencies = lower score).
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    asic_config = config.get("asic_insolvency", {})
    series1_url = asic_config.get(
        "series1_url",
        "https://asic.gov.au/regulatory-resources/find-a-document/statistics/"
        "insolvency-statistics/series-1-companies-entering-external-administration/",
    )
    baseline_weeks = asic_config.get("baseline_weeks", 8)

    week_iso = get_current_week_iso()
    count: int | None = None

    # --- Try HTML parse first ---
    try:
        response = httpx.get(
            series1_url,
            headers={"User-Agent": BROWSER_UA},
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        count = _parse_insolvency_page(response.text)
        if count is not None:
            print(f"  ASIC insolvency: parsed weekly count = {count} (HTML)")
        else:
            print("  ASIC insolvency: HTML parse found no valid count, trying Excel fallback")
            # Look for Excel download links on the page
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.endswith((".xlsx", ".xls")):
                    # Resolve relative URLs
                    if href.startswith("/"):
                        href = "https://asic.gov.au" + href
                    count = _try_excel_download(href)
                    if count is not None:
                        print(f"  ASIC insolvency: parsed weekly count = {count} (Excel)")
                        break
    except Exception as e:
        print(f"  ASIC insolvency: page fetch failed ({e})")

    # --- Total failure — insert neutral signal with weight=0.0 (excluded from composite) ---
    if count is None:
        print("  ✗ ASIC insolvency FAILED: all extraction methods failed")
        print(f"    URL attempted: {series1_url}")
        print("    Inserting neutral (50.0, weight=0.0) so signal is excluded, not missing.")
        insert_signal(
            signal_name="asic_insolvency",
            lane="pulse",
            area="corporate_stress",
            raw_value=0.0,
            normalised_score=50.0,
            source_weight=0.0,
            week_iso=week_iso,
        )
        return 50.0

    # --- Hybrid normalisation ---
    recent = get_recent_signals("asic_insolvency", weeks=52)
    history = [r["raw_value"] for r in recent
               if r.get("source_weight", 1.0) > 0.3 and r["raw_value"] > 0]

    ref = config.get("signal_reference_ranges", {}).get("signals", {}).get("asic_insolvency", {})
    normalised, source_weight = normalise_hybrid(
        raw_value=float(count),
        floor=ref.get("floor", 100),
        ceiling=ref.get("ceiling", 350),
        inverted=ref.get("inverted", True),
        history=history,
        min_weeks_warm=get_min_weeks_warm(config),
    )

    insert_signal(
        signal_name="asic_insolvency",
        lane="pulse",
        area="corporate_stress",
        raw_value=float(count),
        normalised_score=normalised,
        source_weight=source_weight,
        week_iso=week_iso,
    )

    print(f"  ASIC insolvency: count={count}, normalised={normalised:.1f}, weight={source_weight}")
    return normalised
