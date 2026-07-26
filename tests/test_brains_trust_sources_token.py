"""The Brains Trust source-PDF email must never narrow the SHARED Gmail token.

`credentials/token.json` in the Trading Strategy project is shared: the nightly
research ingest and the TAC carousel job both read it and both need the full
read + modify + send scope set. This module only ever *sends*, but if it loads
that token with a send-only scope list and then writes the refreshed token back
to disk, it silently rewrites the shared file down to `["gmail.send"]` — which
breaks every other job that needs to read Gmail.

That is not hypothetical: it happened on 20 Jul 2026 (the day this feature
shipped), leaving a `token.json.sendonly-bak` behind and the TAC carousel job
dead, which in turn starved the Brains Trust angle picker of fresh research.
"""
import json

import pytest

from flatwhite.dashboard import brains_trust_sources as bts

FULL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def _write_token(path) -> None:
    """A realistic shared token: full scopes, already expired."""
    path.write_text(json.dumps({
        "token": "stale-access-token",
        "refresh_token": "refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scopes": FULL_SCOPES,
        "expiry": "2020-01-01T00:00:00Z",
    }))


def test_refresh_preserves_all_shared_scopes(tmp_path, monkeypatch):
    """After _gmail_service() refreshes an expired token, the shared file on
    disk must still carry read + modify + send — not just send."""
    token = tmp_path / "token.json"
    _write_token(token)
    monkeypatch.setattr(bts, "_TOKEN_PATH", str(token))

    import google.oauth2.credentials as gcreds
    import googleapiclient.discovery as gdiscovery

    def fake_refresh(self, request):
        # Google hands back a fresh access token; scopes come from the grant.
        self.token = "fresh-access-token"
        self.expiry = None

    monkeypatch.setattr(gcreds.Credentials, "refresh", fake_refresh)
    monkeypatch.setattr(gdiscovery, "build", lambda *a, **k: object())

    bts._gmail_service()

    written = json.loads(token.read_text())
    assert sorted(written["scopes"]) == sorted(FULL_SCOPES), (
        "the shared Gmail token was rewritten with narrowed scopes "
        f"({written['scopes']}) — this breaks the Trading Strategy research "
        "ingest and the TAC carousel job"
    )


def test_module_does_not_declare_a_narrowed_scope_set():
    """Guard the constant itself, so a future edit can't reintroduce the bug
    without this test failing."""
    assert sorted(bts._SHARED_SCOPES) == sorted(FULL_SCOPES)
