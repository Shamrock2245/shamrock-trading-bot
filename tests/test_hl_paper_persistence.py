"""Paper HL positions survive restarts; restart orphans are excluded from gate metrics."""
import json
import threading
from datetime import datetime, timezone

import pytest

import core.hyperliquid_executor as hx


def _exec(monkeypatch, tmp_path):
    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("TRADES_FILE", str(tmp_path / "trades.json"))
    monkeypatch.setattr(hx, "_PAPER_POSITIONS_FILE", tmp_path / "hl_paper_positions.json")
    monkeypatch.setattr(hx, "_TRAILING_STATE_FILE", tmp_path / "trail.json")
    import core.position_monitor as pm
    monkeypatch.setattr(pm, "TRADE_LEDGER_FILE", tmp_path / "trade_ledger.jsonl")
    monkeypatch.setattr(hx.HyperliquidExecutor, "_orphans_reconciled", False, raising=False)
    e = hx.HyperliquidExecutor.__new__(hx.HyperliquidExecutor)
    e.positions = {}
    e._lock = threading.RLock()
    e.default_leverage = 3
    e.stop_loss_pct = 2.5
    e.take_profit_pct = 5.0
    e.min_rr_ratio = 1.5
    e._info = None
    e.daily_pnl = 0.0
    monkeypatch.setattr(hx.HyperliquidExecutor, "is_paper", property(lambda self: True))
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: 10.0, raising=False)
    monkeypatch.setattr(e, "_feed_daily_goal", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(e, "_inject_scanner_cooldown", lambda *a, **k: None, raising=False)
    return e


def test_paper_position_survives_restart_and_closes(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    assert e._paper_open_position("INJ", "buy", 100.0, 3, 70.0, 9.5, 11.0) is not None
    assert (tmp_path / "hl_paper_positions.json").exists()

    e2 = _exec(monkeypatch, tmp_path)  # simulated container restart
    e2._sync_positions()
    assert "INJ" in e2.positions
    pos = e2.positions["INJ"]
    assert pos.stop_loss_price == 9.5 and pos.take_profit_price == 11.0
    assert pos.size_usd == 100.0

    monkeypatch.setattr(e2, "_paper_mid_price", lambda sym: 11.0, raising=False)
    assert e2._paper_close_position("INJ") is not None
    trades = json.loads((tmp_path / "trades.json").read_text())
    closes = [t for t in trades if t["reason"] == "paper_close"]
    assert len(closes) == 1 and closes[0]["pnl_usd"] > 0
    # No orphan was invented for a properly restored position
    assert not [t for t in trades if t["reason"] == hx.ORPHAN_REASON]
    assert json.loads((tmp_path / "hl_paper_positions.json").read_text()) == {}


def test_restart_orphans_tagged_and_excluded_from_metrics(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    base = {"chain": "hyperliquid", "is_paper": True, "quantity": 10, "price_usd": 9.0}
    trades = [
        {**base, "timestamp": now, "token_symbol": "XMR", "action": "BUY", "reason": "paper_open", "pnl_usd": None},
        {**base, "timestamp": now, "token_symbol": "LTC", "action": "BUY", "reason": "paper_open", "pnl_usd": None},
        {**base, "timestamp": now, "token_symbol": "LTC", "action": "SELL", "reason": "paper_close", "pnl_usd": 5.0},
    ]
    (tmp_path / "trades.json").write_text(json.dumps(trades))
    e = _exec(monkeypatch, tmp_path)
    e._sync_positions()
    out = json.loads((tmp_path / "trades.json").read_text())
    orphans = [t for t in out if t["reason"] == hx.ORPHAN_REASON]
    assert [o["token_symbol"] for o in orphans] == ["XMR"]
    assert orphans[0]["pnl_usd"] is None and orphans[0]["exclude_from_metrics"] is True

    # Idempotent within a process
    e._sync_positions()
    assert len([t for t in json.loads((tmp_path / "trades.json").read_text())
                if t["reason"] == hx.ORPHAN_REASON]) == 1

    from core.predator_v1 import get_paper_metrics
    m = get_paper_metrics()
    assert m["closed_trades"] == 1  # only the real LTC close


def test_metrics_skip_flagged_rows(monkeypatch, tmp_path):
    rows = [{"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": -50.0, "exclude_from_metrics": True},
            {"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": 10.0}]
    (tmp_path / "trades.json").write_text(json.dumps(rows))
    monkeypatch.setenv("TRADES_FILE", str(tmp_path / "trades.json"))
    from core.predator_v1 import get_paper_metrics
    m = get_paper_metrics()
    assert m["closed_trades"] == 1 and m["net_pnl"] == 10.0
