"""Autoban scores per position on net $ (TP1 partial + remainder = one outcome),
renews bans that expire while the window is still bad, and the expectancy gate
uses the same verdict as the ban (Oct 26 2026)."""
import importlib
import json
import time
from unittest.mock import MagicMock

import pytest

from tests.test_paper_exit_ab import _exec


def _sc(monkeypatch, tmp_path, **env):
    base = dict(
        HL_PERPS_UNIVERSE="full",
        HL_PERPS_AUTOBAN_ENABLED="true",
        HL_PERPS_EXPECTANCY_GATE_ENABLED="true",
        HL_PERPS_AUTOBAN_MIN_TRADES="5",
        HL_PERPS_AUTOBAN_WR_THRESHOLD="0.30",
        HL_PERPS_AUTOBAN_PF_THRESHOLD="0.85",
        HL_PERPS_AUTOBAN_HOURS="48",
        HL_PERPS_AUTOBAN_MAX_HOURS="336",
        HL_PERPS_AUTOBAN_WINDOW="20",
        TRADES_FILE=str(tmp_path / "trades.json"),
    )
    base.update(env)
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    import core.hl_perps_scanner as sc
    sc = importlib.reload(sc)
    monkeypatch.setattr(sc, "_COIN_PERF_FILE", tmp_path / "hl_coin_perf.json")
    return sc


def _scanner(sc):
    s = sc.HLPerpsScanner(hl_executor=MagicMock())
    s._coin_perf, s._autoban_until, s._autoban_since = {}, {}, {}
    return s


def test_defaults(monkeypatch, tmp_path):
    for k in ("HL_PERPS_AUTOBAN_WINDOW", "HL_PERPS_AUTOBAN_MAX_HOURS"):
        monkeypatch.delenv(k, raising=False)
    import core.hl_perps_scanner as sc
    sc = importlib.reload(sc)
    assert sc.HL_PERPS_AUTOBAN_WINDOW == 20
    assert sc.HL_PERPS_AUTOBAN_MAX_HOURS == 336.0


def test_pair_positions_folds_partials():
    import core.hl_perps_scanner as sc
    rows = [
        {"token_symbol": "VVV", "reason": "paper_tp1_partial", "pnl_usd": 2.05},
        {"token_symbol": "VVV", "reason": "paper_close", "pnl_usd": -0.5, "timestamp": "2026-10-22T01:02:00+00:00"},
        {"token_symbol": "INJ", "reason": "paper_close", "pnl_usd": -4.0, "timestamp": "2026-10-22T02:00:00+00:00"},
        {"token_symbol": "INJ", "reason": "paper_tp1_partial", "pnl_usd": 1.0},  # dangling → dropped
    ]
    out = sc._pair_positions(rows)
    assert [(c, round(p, 2)) for c, _t, p in out] == [("VVV", 1.55), ("INJ", -4.0)]


def test_tp1_partial_plus_small_stopped_remainder_is_one_win(monkeypatch, tmp_path):
    """Executor passes remainder + partial $ as one net outcome."""
    e = _exec(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(e, "_inject_scanner_cooldown", lambda sym, **k: calls.append((sym, k)), raising=False)
    e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: 10.4, raising=False)
    part = e._paper_close_position("INJ", size_pct=50, exit_reason="tp1_partial")
    assert part["partial"] and part["pnl"] > 0
    assert calls == []  # partial alone is not an outcome
    assert e.positions["INJ"].realized_partial_pnl == pytest.approx(part["pnl"])
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: 9.95, raising=False)
    full = e._paper_close_position("INJ", exit_reason="paper_trail_stop")
    assert full["pnl"] < 0  # remainder alone lost
    (sym, kw), = calls
    net = part["pnl"] + full["pnl"]
    assert net > 0 and kw["pnl_usd"] == pytest.approx(net) and kw["loss"] is False


def test_partial_pnl_survives_restart(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    monkeypatch.setattr(e, "_paper_mid_price", lambda sym: 10.4, raising=False)
    part = e._paper_close_position("INJ", size_pct=50, exit_reason="tp1_partial")
    e2 = _exec(monkeypatch, tmp_path)
    assert e2._restore_paper_positions() == 1
    assert e2.positions["INJ"].realized_partial_pnl == pytest.approx(part["pnl"])


def test_window_overrides_legacy_wl_counts(monkeypatch, tmp_path):
    """VVV case: legacy 14W/30L (partials counted as wins) but positions are fine."""
    sc = _sc(monkeypatch, tmp_path)
    s = _scanner(sc)
    s._coin_perf["VVV"] = {"wins": 14, "losses": 30, "last_updated": time.time()}
    for p in (3.0, 3.8, -1.0, 0.5, -0.7):
        s.record_trade_outcome("VVV", won=p > 0, pnl_usd=p)
    bad, n, wr, pf, src = sc.coin_ban_verdict(s._coin_perf["VVV"])
    assert src == "window" and n == 5 and not bad
    assert "VVV" not in s._autoban_until
    assert s.coin_fails_expectancy("VVV") is False


def test_window_ban_and_expectancy_agree(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path)
    s = _scanner(sc)
    for p in (1.0, -4.0, -3.0, 0.5, -2.0):
        s.record_trade_outcome("INJ", won=p > 0, pnl_usd=p)
    assert "INJ" in s._autoban_until
    assert s.coin_fails_expectancy("INJ") is True


def test_legacy_fallback_when_window_thin(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path)
    s = _scanner(sc)
    s._coin_perf["GMX"] = {"wins": 1, "losses": 6, "last_updated": time.time()}
    assert sc.coin_ban_verdict(s._coin_perf["GMX"])[4] == "legacy"
    assert s.coin_fails_expectancy("GMX") is True


def test_ban_renews_on_expiry_while_still_bad(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path)
    s = _scanner(sc)
    s._goal_frequency_params = lambda: {"reentry_cooldown_min": 0, "loss_cooldown_min": 0}
    now = time.time()
    s._coin_perf["INJ"] = {"wins": 0, "losses": 0, "recent": [[now, -1.0]] * 5, "last_updated": now}
    s._autoban_until["INJ"] = now - 1
    s._autoban_since["INJ"] = now - 49 * 3600
    assert s._is_on_cooldown("INJ") is True
    assert s._autoban_until["INJ"] > now + 47 * 3600


def test_ban_lapses_when_stats_recovered(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path)
    s = _scanner(sc)
    s._goal_frequency_params = lambda: {"reentry_cooldown_min": 0, "loss_cooldown_min": 0}
    now = time.time()
    s._coin_perf["INJ"] = {"wins": 0, "losses": 0, "recent": [[now, 2.0]] * 5, "last_updated": now}
    s._autoban_until["INJ"] = now - 1
    assert s._is_on_cooldown("INJ") is False
    assert "INJ" not in s._autoban_until


def test_renewal_cap_gives_probation(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path)
    s = _scanner(sc)
    s._goal_frequency_params = lambda: {"reentry_cooldown_min": 0, "loss_cooldown_min": 0}
    now = time.time()
    s._coin_perf["INJ"] = {"wins": 0, "losses": 0, "recent": [[now, -1.0]] * 5, "last_updated": now}
    s._autoban_until["INJ"] = now - 1
    s._autoban_since["INJ"] = now - 337 * 3600
    assert s._is_on_cooldown("INJ") is False
    assert "INJ" not in s._autoban_until and "INJ" not in s._autoban_since


def test_expired_ban_on_disk_is_renewed_after_restart(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path)
    now = time.time()
    (tmp_path / "hl_coin_perf.json").write_text(json.dumps({
        "coin_perf": {"XMR": {"wins": 0, "losses": 0, "recent": [[now, -1.0]] * 5, "last_updated": now}},
        "autoban_until": {"XMR": now - 3600},
    }))
    s = sc.HLPerpsScanner(hl_executor=MagicMock())
    s._goal_frequency_params = lambda: {"reentry_cooldown_min": 0, "loss_cooldown_min": 0}
    assert s._is_on_cooldown("XMR") is True
    saved = json.loads((tmp_path / "hl_coin_perf.json").read_text())
    assert saved["autoban_until"]["XMR"] > now and "XMR" in saved["autoban_since"]


def test_seed_recent_from_trade_log(monkeypatch, tmp_path):
    sc = _sc(monkeypatch, tmp_path, HL_PERPS_SEED_LEDGER_IN_TESTS="true",
             HL_PAIRED_TRADES_FILE=str(tmp_path / "none.json"))
    rows = [
        {"chain": "hyperliquid", "action": "SELL", "is_paper": True, "token_symbol": "VVV",
         "reason": "paper_tp1_partial", "pnl_usd": 2.0},
        {"chain": "hyperliquid", "action": "SELL", "is_paper": True, "token_symbol": "VVV",
         "reason": "paper_close", "pnl_usd": -0.5, "timestamp": "2026-10-22T01:02:00+00:00"},
        {"chain": "hyperliquid", "action": "SELL", "is_paper": True, "token_symbol": "XMR",
         "reason": "restart_orphan", "pnl_usd": 0, "timestamp": "2026-10-15T19:11:00+00:00"},
        {"chain": "hyperliquid", "action": "SELL", "is_paper": False, "token_symbol": "BTC",
         "reason": "manual_or_monitor_close", "pnl_usd": -3, "timestamp": "2026-08-11T00:00:00+00:00"},
    ]
    (tmp_path / "trades.json").write_text(json.dumps(rows))
    s = sc.HLPerpsScanner(hl_executor=MagicMock())
    assert [round(x[1], 2) for x in s._coin_perf["VVV"]["recent"]] == [1.5]
    assert "XMR" not in s._coin_perf and "BTC" not in s._coin_perf
    # second start does not double-seed
    s2 = sc.HLPerpsScanner(hl_executor=MagicMock())
    assert len(s2._coin_perf["VVV"]["recent"]) == 1
