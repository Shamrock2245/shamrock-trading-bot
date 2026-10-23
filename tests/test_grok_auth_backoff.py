"""Grok 401/403 → timed backoff with a single log line, quiet callers, auto re-probe."""
import logging

import pytest
import requests

from data.providers import grok_client as gc


class _Resp:
    def __init__(self, status, body=""):
        self.status_code = status
        self.text = body

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.exceptions.HTTPError(f"{self.status_code}")
            err.response = self
            raise err

    def json(self):
        return {"output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": '{"ok": 1}'}]}]}


class _Sess:
    def __init__(self, resps):
        self.resps = list(resps)
        self.calls = 0

    def post(self, *a, **k):
        self.calls += 1
        return self.resps.pop(0)


@pytest.fixture
def grok(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "test-key")
    monkeypatch.setattr(gc, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(gc, "rate_limit", lambda: None)
    for k, v in (("_api_key_invalid", False), ("_disabled_until", 0.0), ("_disable_reason", ""),
                 ("_last_auth_status", None), ("_skipped_calls", 0), ("_missing_key_logged", False)):
        monkeypatch.setattr(gc, k, v)
    return gc


def test_403_backs_off_logs_once_then_reprobes(grok, monkeypatch, caplog):
    sess = _Sess([_Resp(403, "Your team has run out of credits"), _Resp(200)])
    monkeypatch.setattr(gc, "get_session", lambda: sess)
    monkeypatch.setenv("GROK_AUTH_BACKOFF_MIN", "360")
    clock = [1_000_000.0]
    monkeypatch.setattr(gc.time, "time", lambda: clock[0])
    with caplog.at_level(logging.WARNING, logger=gc.__name__):
        assert gc.call_grok("s", "u", module="t") is None
        for _ in range(50):
            assert gc.call_grok("s", "u", module="t") is None
    assert sess.calls == 1                       # no HTTP during backoff
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) == 1 and "403" in warns[0].getMessage() and "credits" in warns[0].getMessage()
    st = gc.get_status()
    assert st["available"] is False and st["last_auth_status"] == 403 and st["skipped_calls"] == 50
    assert gc.is_available() is False
    clock[0] += 361 * 60                         # window over → re-probe
    assert gc.is_available() is True
    assert gc.call_grok("s", "u", module="t") == {"ok": 1}
    assert sess.calls == 2 and gc.get_status()["last_auth_status"] is None


def test_missing_key_logs_once(grok, monkeypatch, caplog):
    monkeypatch.setattr(gc, "_get_api_key", lambda: "")
    with caplog.at_level(logging.WARNING, logger=gc.__name__):
        for _ in range(5):
            assert gc.call_grok("s", "u") is None
    assert len(caplog.records) == 1
    assert gc.is_available() is False


def test_sentiment_skips_quietly_and_counts_neutral(grok, monkeypatch, caplog):
    from data.providers import grok_sentiment as gs
    monkeypatch.setattr(gc, "is_available", lambda: False)
    monkeypatch.setattr(gs, "_cache", {})
    called = []
    monkeypatch.setattr(gs, "_call_grok", lambda *a: called.append(a))
    before = gs._neutral_fallbacks
    with caplog.at_level(logging.WARNING):
        assert gs.get_grok_sentiment_score("IF", "base") == 50.0
    assert called == [] and not caplog.records
    assert gs._neutral_fallbacks == before + 1
    assert gs.get_usage_stats()["neutral_fallbacks"] == before + 1


def test_trending_skips_when_unavailable(grok, monkeypatch):
    from data.providers import grok_trending_scan as gt
    monkeypatch.setattr(gc, "is_available", lambda: False)
    monkeypatch.setattr(gt, "_cache", {})
    monkeypatch.setattr(gt, "_call_grok_trending", lambda: pytest.fail("should not call"))
    assert gt.discover_grok_trending() == []


def test_oracle_skips_when_unavailable_and_dedups_empty(grok, monkeypatch):
    import core.social_insider_oracle as so
    o = so.SocialInsiderOracle()
    calls = []
    monkeypatch.setattr(so, "call_grok", lambda **k: calls.append(k) or None)
    monkeypatch.setattr(gc, "is_available", lambda: False)
    o.ingest_grok_mentions("IF", "base", "0xabc")
    assert calls == []
    monkeypatch.setattr(gc, "is_available", lambda: True)
    monkeypatch.setenv("GROK_SOCIAL_REINGEST_MIN", "30")
    for _ in range(5):
        o.ingest_grok_mentions("IF", "base", "0xabc")   # empty result each time
    assert len(calls) == 1                               # re-query suppressed within TTL


def test_three_file_rule_grok():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for line in ("GROK_AUTH_BACKOFF_MIN=360", "GROK_SOCIAL_REINGEST_MIN=30"):
        assert line in (root / ".env.example").read_text()
        assert line in (root / ".github/workflows/ci.yml").read_text()
