"""Lightweight per-step timing log for dashboard scrapes.

Appends one line per (section, step) to data/scrape_timing.log so that when a
section "takes hours", we can see exactly which step stalled and for how long,
instead of guessing. Best-effort: logging failures never interrupt a scrape.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent.parent / "data" / "scrape_timing.log"


def log_step(section: str, step: str, elapsed: float, status: str = "ok", extra: str = "") -> None:
    """Append a timing record. Never raises."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts}\t{section}\t{step}\t{elapsed:7.1f}s\t{status}"
        if extra:
            line += f"\t{extra}"
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


class timed_step:
    """Context manager that logs how long a section step took (and its outcome)."""

    def __init__(self, section: str, step: str) -> None:
        self.section = section
        self.step = step

    def __enter__(self) -> "timed_step":
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = time.time() - self._t0
        if exc_type is None:
            log_step(self.section, self.step, elapsed, "ok")
        else:
            log_step(self.section, self.step, elapsed, "ERROR", f"{exc_type.__name__}: {str(exc)[:160]}")
        return False  # never suppress
