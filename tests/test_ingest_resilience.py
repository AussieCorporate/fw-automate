"""A failing Google Trends pull must not abort the rest of the ingest step.

Trends 429s hard from datacenter IPs and _call_with_retry raises once its retries
are exhausted. It was the first call in _ingest(), so one rate-limit silently took
every signal below it down: the Trends and Reddit signals stopped writing in April
2026 while the market signals, pulled elsewhere, kept updating.
"""

from flatwhite.orchestrate.runner import pull_trends_without_aborting


def test_returns_empty_dict_instead_of_raising_on_429(monkeypatch, capsys):
    import flatwhite.signals.google_trends as gt

    def rate_limited():
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(gt, "pull_all_google_trends", rate_limited)

    result = pull_trends_without_aborting()
    assert result == {}
    assert "continuing without it" in capsys.readouterr().out


def test_degraded_result_still_supports_len(monkeypatch):
    """_ingest does `len(gt) + 11`; returning a scalar on failure would crash it."""
    import flatwhite.signals.google_trends as gt

    monkeypatch.setattr(gt, "pull_all_google_trends", lambda: (_ for _ in ()).throw(RuntimeError("429")))
    assert len(pull_trends_without_aborting()) == 0


def test_passes_scores_through_when_trends_works(monkeypatch):
    import flatwhite.signals.google_trends as gt

    monkeypatch.setattr(gt, "pull_all_google_trends", lambda: {"job_anxiety": 27.7})
    assert pull_trends_without_aborting() == {"job_anxiety": 27.7}
