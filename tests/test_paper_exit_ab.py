"""Paper-only exit A/B: control (structure SL + default timeout) vs atr2x_8h."""
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

import core.hyperliquid_executor as hx
from core import paper_exit_ab as ab
from core import predator_v1
from core.winning_risk_manager import evaluate_position


def _exec(monkeypatch, tmp_path, paper=True, mid=10.0, info=None):
    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("TRADES_FILE", str(tmp_path / "trades.json"))
    for k in ("PAPER_EXIT_AB_ENABLED", "PAPER_EXIT_AB_ATR_MULT", "PAPER_EXIT_AB_ATR_TIMEOUT_HOURS",
              "PAPER_EXIT_AB_SALT"):
        monkeypatch.delenv(k, raising=False)
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
    e._info = info
    e.daily_pnl = 0.0
    monkeypatch.setattr(hx.HyperliquidExecutor, "is_paper", property(lambda self: paper))
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: mid, raising=False)
    monkeypatch.setattr(e, "_feed_daily_goal", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(e, "_inject_scanner_cooldown", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(e, "_get_sz_decimals", lambda sym: 4, raising=False)
    monkeypatch.setattr(e, "_execute_api", lambda f, *a, **k: f(*a, **k), raising=False)
    return e


class _Info:
    """Fake SDK Info: 20 closed 1h bars with constant true range 0.1 (ATR=0.1)."""
    def __init__(self, tr=0.1):
        self.tr = tr

    def candles_snapshot(self, name, interval, start, end):
        out = []
        for i in range(20):
            t = end - (21 - i) * 3_600_000
            out.append({"t": t, "T": t + 3_599_999, "o": "10", "h": str(10 + self.tr / 2),
                        "l": str(10 - self.tr / 2), "c": "10"})
        return out


def _rows(tmp_path):
    return json.loads((tmp_path / "trades.json").read_text())


def _force(monkeypatch, arm):
    monkeypatch.setattr(ab, "assign_variant", lambda coin, opened_at=None: arm)


# ── assignment ─────────────────────────────────────────────────────────────
def test_assignment_is_deterministic_and_roughly_balanced():
    t = datetime(2026, 10, 21, 15, 7, tzinfo=timezone.utc)
    assert ab.assign_variant("INJ", t) == ab.assign_variant("inj", t.replace(minute=59))
    arms = [ab.assign_variant(c, t + timedelta(hours=h))
            for c in ("BTC", "INJ", "XMR", "AAVE", "LINK") for h in range(400)]
    share = arms.count(ab.ATR_ARM) / len(arms)
    assert 0.45 < share < 0.55
    assert set(arms) == {ab.CONTROL, ab.ATR_ARM}


def test_compute_atr_and_stop():
    bars = [{"h": 10.05, "l": 9.95, "c": 10.0}] * 15
    assert ab.compute_atr(bars) == pytest.approx(0.1)
    assert ab.compute_atr(bars[:10]) is None
    assert ab.atr_stop("long", 10.0, 0.1, 2.0) == pytest.approx(9.8)
    assert ab.atr_stop("short", 10.0, 0.1, 2.0) == pytest.approx(10.2)


def test_settings_clamped(monkeypatch):
    monkeypatch.setenv("PAPER_EXIT_AB_ATR_MULT", "99")
    monkeypatch.setenv("PAPER_EXIT_AB_ATR_TIMEOUT_HOURS", "nan")
    assert ab.atr_mult() == 5.0 and ab.atr_timeout_hours() == 8.0


def test_live_mode_never_runs_ab(monkeypatch, tmp_path):
    import config.settings as cs
    monkeypatch.setattr(cs, "get_current_mode", lambda: "live")
    assert ab.ab_enabled() is False
    assert ab.winning_config_for(ab.ATR_ARM, is_paper=True) is None
    e = _exec(monkeypatch, tmp_path, info=_Info())
    monkeypatch.setattr(cs, "get_current_mode", lambda: "live")
    assert e._paper_exit_ab_apply("INJ", "long", 10.0, 9.7) == {}


def test_disabled_flag(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path, info=_Info())
    monkeypatch.setenv("PAPER_EXIT_AB_ENABLED", "false")
    r = e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    assert r["stop_loss"] == pytest.approx(9.7)
    assert "exit_variant" not in _rows(tmp_path)[-1]


# ── open / close tagging ───────────────────────────────────────────────────
def test_control_arm_keeps_structure_sl_and_tags_rows(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path, info=_Info())
    _force(monkeypatch, ab.CONTROL)
    r = e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    assert r["stop_loss"] == pytest.approx(9.7)
    op = _rows(tmp_path)[-1]
    assert op["exit_variant"] == "control" and op["ab_structure_sl"] == pytest.approx(9.7)
    assert e.positions["INJ"].exit_variant == "control"
    e._paper_close_position("INJ", fill_price=9.69, exit_reason="paper_sl_hit")
    cl = _rows(tmp_path)[-1]
    assert cl["action"] == "SELL" and cl["exit_variant"] == "control" and "ab_structure_sl" not in cl


def test_atr_arm_uses_2x_atr_stop_and_persists(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path, info=_Info(tr=0.1))
    _force(monkeypatch, ab.ATR_ARM)
    r = e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    assert r["stop_loss"] == pytest.approx(9.8)   # 10 − 2×0.1
    op = _rows(tmp_path)[-1]
    assert op["exit_variant"] == "atr2x_8h" and op["stop_loss"] == pytest.approx(9.8)
    assert op["ab_structure_sl"] == pytest.approx(9.7) and op["ab_atr_1h"] == pytest.approx(0.1)
    assert op["ab_atr_fallback"] is False and op["ab_loss_timeout_h"] == 8.0
    # survives restart
    e2 = _exec(monkeypatch, tmp_path)
    assert e2._restore_paper_positions() == 1
    assert e2.positions["INJ"].exit_variant == "atr2x_8h"
    # TP1 partial + final close both tagged
    e2._paper_close_position("INJ", size_pct=40, exit_reason="tp1_partial")
    e2._paper_close_position("INJ", exit_reason="paper_trail_stop")
    assert [x.get("exit_variant") for x in _rows(tmp_path)[-2:]] == ["atr2x_8h", "atr2x_8h"]


def test_short_atr_arm(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path, info=_Info(tr=0.1))
    _force(monkeypatch, ab.ATR_ARM)
    r = e._paper_open_position("INJ", "sell", 50.0, 3, 70, stop_loss_price=10.3, take_profit_price=9.1)
    assert r["stop_loss"] == pytest.approx(10.2)


def test_atr_unavailable_falls_back_to_structure_sl_flagged(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path, info=None)
    _force(monkeypatch, ab.ATR_ARM)
    r = e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    assert r["stop_loss"] == pytest.approx(9.7)
    op = _rows(tmp_path)[-1]
    assert op["exit_variant"] == "atr2x_8h" and op["ab_atr_fallback"] is True


def test_rr_filter_uses_structure_sl_so_arms_admit_same_signals(monkeypatch, tmp_path):
    # structure SL 9.9 / TP 10.5 → R/R 5 passes; a 2×ATR stop (ATR 0.4 → 9.2) would be R/R 0.6
    e = _exec(monkeypatch, tmp_path, info=_Info(tr=0.4))
    _force(monkeypatch, ab.ATR_ARM)
    r = e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.9, take_profit_price=10.5)
    assert r is not None and r["stop_loss"] == pytest.approx(9.2)


# ── monitor timeout ────────────────────────────────────────────────────────
def test_atr_arm_gets_8h_timeout_control_keeps_default(monkeypatch):
    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("WINNING_LOSS_TIMEOUT_HOURS", "4.0")
    now = datetime(2026, 10, 21, 20, 0, tzinfo=timezone.utc)
    kw = dict(coin="INJ", current_price=9.95, entry_price=10.0, entry_time=now - timedelta(hours=5),
              side="long", now=now)
    assert ab.winning_config_for(ab.CONTROL, True) is None
    assert evaluate_position(**kw, config=ab.winning_config_for(ab.CONTROL, True)).should_close
    cfg = ab.winning_config_for(ab.ATR_ARM, True)
    assert cfg.loss_timeout_hours == 8.0
    d = evaluate_position(**kw, config=cfg)
    assert not d.should_close
    # 45-min rule still applies to the ATR arm
    assert d.sl_price == pytest.approx(9.85)
    kw["entry_time"] = now - timedelta(hours=8.5)
    assert evaluate_position(**kw, config=cfg).should_close
    assert ab.winning_config_for(ab.ATR_ARM, is_paper=False) is None


# ── gate reporting ─────────────────────────────────────────────────────────
def _close(pnl, variant=None, reason="paper_sl_hit"):
    r = {"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": pnl, "exit_reason": reason}
    if variant:
        r["exit_variant"] = variant
    return r


def test_gate_by_variant(monkeypatch, tmp_path):
    rows = [_close(2.0, "control"), _close(-1.0, "control"), _close(3.0, "atr2x_8h"),
            _close(1.0, "atr2x_8h", "tp1_partial"), _close(-4.0), _close(5.0, "bogus"),
            {"chain": "hyperliquid", "is_paper": True, "action": "BUY", "exit_variant": "control"}]
    p = tmp_path / "trades.json"
    p.write_text(json.dumps(rows))
    monkeypatch.setenv("TRADES_FILE", str(p))
    m = predator_v1.get_paper_metrics()
    assert m["closed_trades"] == 6 and m["gates"]["min_pf"] == 1.30   # overall gate unchanged
    bv = m["by_variant"]
    assert bv["control"]["closed_trades"] == 2 and bv["control"]["profit_factor"] == 2.0
    assert bv["atr2x_8h"]["closed_trades"] == 2 and bv["atr2x_8h"]["positions_closed"] == 1
    assert bv["atr2x_8h"]["win_rate"] == 1.0
    assert bv["untagged"]["closed_trades"] == 2
