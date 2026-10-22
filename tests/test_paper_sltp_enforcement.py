"""Paper-only SL/TP trigger simulation (exchange-side stops don't exist in paper)."""
import json
import threading

import pytest

import core.hyperliquid_executor as hx


def _exec(monkeypatch, tmp_path, paper=True, mid=10.0):
    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("TRADES_FILE", str(tmp_path / "trades.json"))
    monkeypatch.setenv("PAPER_TRIGGER_SLIPPAGE_BPS", "5")
    monkeypatch.delenv("PAPER_SLTP_ENFORCE", raising=False)
    monkeypatch.setattr(hx, "_PAPER_POSITIONS_FILE", tmp_path / "hl_paper_positions.json")
    monkeypatch.setattr(hx, "_TRAILING_STATE_FILE", tmp_path / "trail.json")
    import core.position_monitor as pm
    monkeypatch.setattr(pm, "TRADE_LEDGER_FILE", tmp_path / "trade_ledger.jsonl")
    e = hx.HyperliquidExecutor.__new__(hx.HyperliquidExecutor)
    e.positions = {}
    e._lock = threading.RLock()
    e.default_leverage = 3
    e.stop_loss_pct = 2.5
    e.take_profit_pct = 5.0
    e.min_rr_ratio = 1.5
    e._info = None
    e.daily_pnl = 0.0
    monkeypatch.setattr(hx.HyperliquidExecutor, "is_paper", property(lambda self: paper))
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: mid, raising=False)
    monkeypatch.setattr(e, "_feed_daily_goal", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(e, "_inject_scanner_cooldown", lambda *a, **k: None, raising=False)
    return e


def _pos(sym="INJ", side="long", entry=10.0, sl=9.8, tp=10.5, size_usd=100.0, lev=3):
    return hx.HLPosition(coin=sym, side=side, entry_price=entry, size=size_usd / entry,
                         size_usd=size_usd, leverage=lev, stop_loss_price=sl,
                         take_profit_price=tp, highest_price=entry, lowest_price=entry)


def _rows(tmp_path):
    return json.loads((tmp_path / "trades.json").read_text())


def test_no_trigger_inside_band(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = _pos()
    assert e.check_paper_triggers("INJ", 10.1) is None
    assert "INJ" in e.positions


def test_long_sl_hit_fills_at_stop_minus_slippage(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = _pos()
    res = e.check_paper_triggers("INJ", 9.79)
    assert res and res["exit_reason"] == "paper_sl_hit"
    assert "INJ" not in e.positions
    # gap below stop → worse of stop and mark, then 5 bps slippage
    assert res["close_price"] == pytest.approx(9.79 * (1 - 0.0005))
    row = _rows(tmp_path)[-1]
    assert row["exit_reason"] == "paper_sl_hit" and row["is_paper"] is True
    assert row["pnl_usd"] < 0


def test_long_trailed_stop_in_profit_is_trail_stop(monkeypatch, tmp_path):
    """INJ 10/20 replay: trail locked above entry, price falls through → profitable close."""
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = _pos(entry=8.722, sl=9.2974, tp=None, size_usd=196.0 / 6, lev=6)
    res = e.check_paper_triggers("INJ", 9.29)
    assert res["exit_reason"] == "paper_trail_stop"
    assert res["pnl"] > 0


def test_long_tp_hit(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = _pos()
    res = e.check_paper_triggers("INJ", 10.6)
    assert res["exit_reason"] == "paper_tp_hit"
    assert res["close_price"] == pytest.approx(10.5 * (1 - 0.0005))
    assert res["pnl"] > 0


def test_short_sl_and_tp(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.positions["XMR"] = _pos(sym="XMR", side="short", entry=100.0, sl=102.0, tp=97.0)
    assert e.check_paper_triggers("XMR", 101.0) is None
    res = e.check_paper_triggers("XMR", 102.5)
    assert res["exit_reason"] == "paper_sl_hit"
    assert res["close_price"] == pytest.approx(102.5 * 1.0005)
    e.positions["XMR"] = _pos(sym="XMR", side="short", entry=100.0, sl=99.5, tp=97.0)
    res = e.check_paper_triggers("XMR", 99.6)
    assert res["exit_reason"] == "paper_trail_stop"
    e.positions["XMR"] = _pos(sym="XMR", side="short", entry=100.0, sl=102.0, tp=97.0)
    res = e.check_paper_triggers("XMR", 96.9)
    assert res["exit_reason"] == "paper_tp_hit"


def test_noop_in_live(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path, paper=False)
    e.positions["INJ"] = _pos()
    assert e.check_paper_triggers("INJ", 5.0) is None
    assert "INJ" in e.positions


def test_disabled_flag(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    monkeypatch.setenv("PAPER_SLTP_ENFORCE", "false")
    e.positions["INJ"] = _pos()
    assert e.check_paper_triggers("INJ", 5.0) is None


def test_missing_levels_and_bad_mark(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = _pos(sl=None, tp=None)
    assert e.check_paper_triggers("INJ", 1.0) is None
    assert e.check_paper_triggers("INJ", 0) is None
    assert e.check_paper_triggers("NOPE", 1.0) is None


def test_monitor_close_records_exit_reason(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = _pos()
    monkeypatch.setattr(e, "is_available", lambda: True, raising=False)
    assert e.close_position("INJ", exit_reason="winning_loss_timeout_4.0h") is not None
    assert _rows(tmp_path)[-1]["exit_reason"] == "winning_loss_timeout_4.0h"


def test_slippage_bounds(monkeypatch):
    monkeypatch.setenv("PAPER_TRIGGER_SLIPPAGE_BPS", "junk")
    assert hx.paper_trigger_slippage_frac() == pytest.approx(0.0005)
    monkeypatch.setenv("PAPER_TRIGGER_SLIPPAGE_BPS", "-3")
    assert hx.paper_trigger_slippage_frac() == 0.0
    monkeypatch.setenv("PAPER_TRIGGER_SLIPPAGE_BPS", "9999")
    assert hx.paper_trigger_slippage_frac() == 0.01


def test_three_file_rule():
    from pathlib import Path
    env = Path(".env.example").read_text()
    ci = Path(".github/workflows/ci.yml").read_text()
    for k in ("PAPER_SLTP_ENFORCE=true", "PAPER_TRIGGER_SLIPPAGE_BPS=5"):
        assert k in env and k in ci
