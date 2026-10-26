"""Regression tests: gem denylist (AERO) + Fib re-entry frozen gem_score.

Root cause (2026-10-26): Fib Hunter watchlist entries kept the gem_score from
when the token was first added (AERO 65.79168016826898 from 2026-08-09) and
every Fib re-entry reused it.  Entries must now be re-scored fresh.
"""
import json

import pytest

from config import settings
import core.fib_hunter as fh

STALE = 65.79168016826898
ADDR = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"
OTHER = "0x1111111111111111111111111111111111111111"


def test_denylist_parsing(monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "aero, foo ," + ADDR.upper())
    deny = settings.gem_denylist()
    assert "AERO" in deny and "FOO" in deny and ADDR in deny
    assert settings.is_gem_denylisted("Aero")
    assert settings.is_gem_denylisted("", ADDR.upper())
    assert not settings.is_gem_denylisted("BAR", OTHER)


def test_denylist_default_is_aero(monkeypatch):
    monkeypatch.delenv("GEM_SCANNER_DENYLIST", raising=False)
    assert settings.is_gem_denylisted("AERO")


def test_denylist_empty_disables(monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "")
    assert not settings.is_gem_denylisted("AERO")


def test_gem_scanner_rejects_denylisted(monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "AERO")
    from scanner.gem_scanner import GemScanner
    from data.models import Token
    sc = GemScanner.__new__(GemScanner)
    tok = Token(address=ADDR, symbol="AERO", name="Aerodrome", chain="base")
    assert sc._score_token(tok) is None


@pytest.fixture
def fib_env(tmp_path, monkeypatch):
    wl = tmp_path / "fib_watchlist.json"
    monkeypatch.setattr(fh, "WATCHLIST_FILE", wl)
    monkeypatch.setattr(fh, "build_watchlist_from_history", lambda: None)
    monkeypatch.setattr(fh.time, "sleep", lambda *_: None)
    import core.position_monitor as pm
    monkeypatch.setattr(pm, "load_positions", lambda: [])
    import core.safety as safety

    class _Safe:
        is_safe = True
        block_reason = ""
    monkeypatch.setattr(safety, "check_token_safety", lambda *a, **k: _Safe())

    def _sig(addr, chain):
        return fh.FibEntrySignal(
            token_address=addr, symbol="", chain=chain, fib_zone="fib_618",
            fib_confidence=70.0, current_price=1.0, stop_loss=0.9,
            take_profit_targets=[1.1],
        )
    monkeypatch.setattr(fh, "analyze_fib_entry", _sig)
    return wl


def _seed(wl, *entries):
    wl.write_text(json.dumps([
        {"token_address": a, "symbol": s, "chain": "base",
         "source": "trade_history", "gem_score": STALE} for a, s in entries
    ]))


def test_fib_uses_fresh_score_not_stored(fib_env, monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "")
    _seed(fib_env, (OTHER, "FOO"))
    monkeypatch.setattr(fh, "fresh_gem_score", lambda a, c: 71.25)
    sigs = fh.run_fib_hunt_sweep()
    assert len(sigs) == 1
    assert sigs[0].gem_score == 71.25 != STALE
    saved = json.loads(fib_env.read_text())
    assert saved[0]["gem_score"] == 71.25


def test_fib_skips_when_fresh_score_unavailable(fib_env, monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "")
    _seed(fib_env, (OTHER, "FOO"))
    monkeypatch.setattr(fh, "fresh_gem_score", lambda a, c: None)
    assert fh.run_fib_hunt_sweep() == []


def test_fib_skips_when_fresh_score_below_min(fib_env, monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "")
    _seed(fib_env, (OTHER, "FOO"))
    monkeypatch.setattr(fh, "fresh_gem_score", lambda a, c: settings.MIN_GEM_SCORE - 5)
    assert fh.run_fib_hunt_sweep() == []


def test_fib_purges_denylisted(fib_env, monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "AERO")
    _seed(fib_env, (ADDR, "AERO"), (OTHER, "FOO"))
    monkeypatch.setattr(fh, "fresh_gem_score", lambda a, c: 80.0)
    sigs = fh.run_fib_hunt_sweep()
    assert [s.symbol for s in sigs] == ["FOO"]
    assert [e["symbol"] for e in json.loads(fib_env.read_text())] == ["FOO"]


def test_add_to_watchlist_skips_denylisted(tmp_path, monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "AERO")
    monkeypatch.setattr(fh, "WATCHLIST_FILE", tmp_path / "w.json")
    fh.add_to_watchlist(ADDR, "AERO", "base", "trade_history", STALE)
    assert fh.load_watchlist() == []


def test_copy_trade_gate_rejects_denylisted(monkeypatch):
    monkeypatch.setenv("GEM_SCANNER_DENYLIST", "AERO")
    from core import wallet_monitor as wm

    class S:
        token_symbol = "AERO"
        token_address = ADDR
        chain = "base"
        liquidity_usd = 1e6
    ok, why = wm._validate_signal(S())
    assert not ok and "denylist" in why.lower()
