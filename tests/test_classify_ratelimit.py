"""Regression tests for the 429 retry-storm fix.

A rate-limited LLM must cause classification to ABORT immediately, never to:
  (a) retry the same throttled call, or
  (b) fan a failed batch out into per-item calls.
Either behaviour turns a 2-minute run into a multi-hour 429 storm.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import flatwhite.model_router as mr
from flatwhite.model_router import LLMRateLimitError, _is_rate_limit_error
import flatwhite.classify.classifier as clf


class _FakeRateLimitError(Exception):
    """Stands in for anthropic.RateLimitError / google ResourceExhausted."""
    def __init__(self) -> None:
        super().__init__("Error code: 429 - Too Many Requests")


def test_is_rate_limit_error_detects_common_shapes() -> None:
    assert _is_rate_limit_error(_FakeRateLimitError())
    assert _is_rate_limit_error(Exception("RESOURCE_EXHAUSTED: quota"))
    assert _is_rate_limit_error(Exception("429 too many requests"))
    assert not _is_rate_limit_error(Exception("connection reset by peer"))
    assert not _is_rate_limit_error(ValueError("bad json"))


def test_route_raises_typed_error_without_retry_on_429() -> None:
    """route() must surface a 429 as LLMRateLimitError on the FIRST failure (no pointless retry)."""
    with patch.object(mr, "_call_model", side_effect=_FakeRateLimitError()) as m:
        with pytest.raises(LLMRateLimitError):
            mr.route("classification", "hi")
    assert m.call_count == 1  # did NOT retry into the same wall


def test_classify_batch_aborts_and_does_not_fan_out_on_429() -> None:
    """A 429 from the batch call must propagate, NOT trigger per-item fallback."""
    items = [{"id": i, "title": f"t{i}", "body": "b", "source": "s", "url": "u"} for i in range(8)]

    with patch.object(clf, "route", side_effect=LLMRateLimitError("gemini: 429")), \
         patch.object(clf, "classify_single_item") as per_item:
        with pytest.raises(LLMRateLimitError):
            clf.classify_batch(items, batch_size=8)
    per_item.assert_not_called()  # the amplification must not happen


def test_otc_batch_aborts_and_does_not_fan_out_on_429() -> None:
    items = [{"id": i, "title": f"t{i}", "body": "b", "source": "s",
              "url": "u", "subreddit": "sydney", "lifestyle_category": "eating"} for i in range(8)]

    with patch.object(clf, "route", side_effect=LLMRateLimitError("haiku: 429")), \
         patch.object(clf, "classify_single_otc_item") as per_item:
        with pytest.raises(LLMRateLimitError):
            clf._classify_otc_batch(items, batch_size=8)
    per_item.assert_not_called()


def test_parse_failure_still_falls_back_to_per_item() -> None:
    """Non-429 failures (bad JSON) must STILL use per-item fallback — that behaviour is intentional."""
    items = [{"id": 1, "title": "t", "body": "b", "source": "s", "url": "u"}]

    with patch.object(clf, "route", return_value="not json at all"), \
         patch.object(clf, "classify_single_item", return_value=None) as per_item:
        results = clf.classify_batch(items, batch_size=8)
    per_item.assert_called_once()
    assert results == [None]
