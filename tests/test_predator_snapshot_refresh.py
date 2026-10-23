"""predator_v1.json must refresh on closes and on a timer, not only on entry evaluations."""
import json

import pytest


@pytest.fixture
def pv1(monkeypatch, tmp_path):
    import core.predator_v1 as pv1

    monkeypatch.setattr(pv1, "_SNAPSHOT", tmp_path / "dash" / "predator_v1.json")
    monkeypatch.setattr(pv1, "_LAST", None)
    monkeypatch.setattr(pv1, "_LAST_BLOCK", None)
    monkeypatch.setattr(pv1, "_LAST_REFRESH_TS", 0.0)
    trades = tmp_path / "trades.json"
    trades.write_text("[]")
    monkeypatch.setenv("TRADES_FILE", str(trades))
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    return pv1


def _close_row(pnl, variant="control"):
    return {
        "timestamp": "2026-10-23T12:00:00+00:00", "token_symbol": "BTC", "chain": "hyperliquid",
        "action": "SELL", "pnl_usd": pnl, "pnl_pct": 1.0, "is_paper": True,
        "strategy_profile": "hl_perps", "exit_variant": variant,
    }


def test_refresh_disabled_is_noop(pv1, monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "false")
    assert pv1.refresh_snapshot("close") is False
    assert not pv1._SNAPSHOT.exists()


def test_refresh_writes_metrics_and_keeps_last_verdict(pv1, tmp_path):
    v_block = pv1.PredatorVerdict(allow=False, reason="toxic_hour", regime="TRENDING", hour_et=9, coin="BTC")
    pv1._write_snapshot(v_block, last_block=v_block)
    v_allow = pv1.PredatorVerdict(allow=True, reason="ok", regime="TRENDING", hour_et=15, coin="XMR")
    pv1._write_snapshot(v_allow, last_block=None)
    snap = json.loads(pv1._SNAPSHOT.read_text())
    assert snap["last"]["coin"] == "XMR"
    assert snap["last_block"]["reason"] == "toxic_hour"  # kept after an allow

    trades = tmp_path / "trades.json"
    gate_rows = [_close_row(5.0), _close_row(-2.0)]
    trades.write_text(json.dumps(gate_rows))
    assert pv1.refresh_snapshot("close") is True
    snap = json.loads(pv1._SNAPSHOT.read_text())
    assert snap["refresh_reason"] == "close"
    assert snap["last"]["coin"] == "XMR"
    pm = snap["paper_metrics"]
    expected = len([r for r in gate_rows if pv1.is_gate_close(r)])
    assert pm["closed_trades"] == expected


def test_refresh_after_restart_reads_verdicts_from_disk(pv1, monkeypatch):
    v = pv1.PredatorVerdict(allow=False, reason="not_allowlisted", coin="ETH")
    pv1._write_snapshot(v, last_block=v)
    monkeypatch.setattr(pv1, "_LAST", None)
    monkeypatch.setattr(pv1, "_LAST_BLOCK", None)
    assert pv1.refresh_snapshot("timer") is True
    snap = json.loads(pv1._SNAPSHOT.read_text())
    assert snap["last"]["coin"] == "ETH"
    assert snap["last_block"]["reason"] == "not_allowlisted"


def test_timer_respects_interval(pv1, monkeypatch):
    monkeypatch.setenv("PREDATOR_SNAPSHOT_REFRESH_SEC", "300")
    assert pv1.refresh_snapshot("timer", force=False) is True
    assert pv1.refresh_snapshot("timer", force=False) is False  # within 300s
    monkeypatch.setattr(pv1, "_LAST_REFRESH_TS", 0.0)
    assert pv1.refresh_snapshot("timer", force=False) is True
    monkeypatch.setenv("PREDATOR_SNAPSHOT_REFRESH_SEC", "0")
    monkeypatch.setattr(pv1, "_LAST_REFRESH_TS", 0.0)
    assert pv1.refresh_snapshot("timer", force=False) is False  # timer off
    assert pv1.refresh_snapshot("close") is True  # closes still refresh


def test_executor_close_journal_refreshes_snapshot(pv1, monkeypatch):
    from core import hyperliquid_executor as hx

    calls = []
    monkeypatch.setattr(pv1, "refresh_snapshot", lambda reason="manual", force=True: calls.append(reason) or True)
    ex = hx.HyperliquidExecutor.__new__(hx.HyperliquidExecutor)
    monkeypatch.setattr(hx, "_journal_to_ledger", lambda rec: None)
    ex._log_hl_trade(action="BUY", coin="BTC", side="long", price=1.0, quantity=1.0, value_usd=1.0)
    assert calls == []
    ex._log_hl_trade(action="SELL", coin="BTC", side="long", price=1.1, quantity=1.0, value_usd=1.1,
                     pnl_usd=0.1, pnl_pct=10.0, reason="paper_close")
    assert calls == ["close"]


def test_three_file_rule_snapshot_refresh():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert "PREDATOR_SNAPSHOT_REFRESH_SEC=300" in (root / ".env.example").read_text()
    assert "PREDATOR_SNAPSHOT_REFRESH_SEC=300" in (root / ".github/workflows/ci.yml").read_text()
