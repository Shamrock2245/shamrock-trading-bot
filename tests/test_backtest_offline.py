"""Offline backtester (backtest/) — pure-function tests, no network.

vectorbt is research-only (backtest/requirements.txt), so the rolling-split
walk-forward test skips when it isn't installed (as in CI)."""
from __future__ import annotations

import os
import time

import pytest

from backtest import candle_recorder, hl_data, sim
from backtest import walk_forward as wf
from backtest.replay import Signal, daily_from_hourly

H = 3_600_000


def _bars(rows, t0=0):
    return [{"t": t0 + i * H, "o": o, "h": h, "l": l, "c": c, "v": 1.0} for i, (o, h, l, c) in enumerate(rows)]


# ── sim ────────────────────────────────────────────────────────────────────
def test_long_structure_sl_fills_at_stop_with_slippage_and_fees():
    out = sim.simulate("long", 100.0, 98.0, 110.0, _bars([(100, 100.5, 97.5, 98.2)]))
    assert out.reason == "sl_hit"
    exp = (98.0 * (1 - sim.SLIP) - 100) / 100 * 100 - 2 * sim.TAKER_FEE * 100
    assert out.net_pct == pytest.approx(exp)
    assert out.r == pytest.approx(exp / 2.0)


def test_gap_through_stop_fills_at_open():
    out = sim.simulate("long", 100.0, 98.0, 110.0, _bars([(96.0, 96.5, 95.0, 96.0)]))
    assert out.reason == "sl_hit"
    assert out.net_pct < -4.0  # filled at the 96 open, not the 98 stop


def test_sl_wins_when_sl_and_tp_inside_same_bar():
    out = sim.simulate("long", 100.0, 99.0, 101.0, _bars([(100, 101.5, 98.5, 100)]))
    assert out.reason == "sl_hit"


def test_short_tp_hit():
    out = sim.simulate("short", 100.0, 103.0, 99.0, _bars([(100, 100.2, 98.8, 99.0)]))
    assert out.reason == "tp_hit"
    assert out.net_pct > 0


def test_break_even_buffer_covers_fees():
    # bar 1 runs +1% (arms BE), bar 2 comes back to entry → BE stop
    bars = _bars([(100, 101.0, 99.9, 100.5), (100.5, 100.6, 99.0, 99.5)])
    lo = sim.simulate("long", 100.0, 97.0, 110.0, bars, sim.ExitParams(be_buffer_pct=0.05))
    hi = sim.simulate("long", 100.0, 97.0, 110.0, bars, sim.ExitParams(be_buffer_pct=0.12))
    assert lo.reason == hi.reason == "trail_stop"
    assert lo.net_pct < -0.08            # 0.05% buffer locks in a fee loss
    assert hi.net_pct > lo.net_pct and hi.net_pct > -0.05  # 0.12% ≈ flat after fees + 5bps slip


def test_loss_timeout_and_no_enforce():
    bars = _bars([(100, 100.2, 99.6, 99.8)] * 6)
    out = sim.simulate("long", 100.0, 95.0, 110.0, bars, sim.ExitParams(timeout_h=4))
    assert out.reason == "loss_timeout" and out.hold_h == 4
    off = sim.simulate("long", 100.0, 99.9, 100.1, _bars([(100, 100.3, 99.7, 100.0)] * 3),
                       sim.ExitParams(enforce_sltp=False, timeout_h=99, max_hold_h=3))
    assert off.reason == "max_hold"


def test_no_stop_trail_path_does_not_crash():
    out = sim.simulate("long", 100.0, 0.0, 0.0, _bars([(100, 103, 100, 102.5), (102.5, 102.6, 100.5, 101)]))
    assert out.reason in {"trail_stop", "max_hold"}


# ── hl_data / recorder ─────────────────────────────────────────────────────
def test_cache_roundtrip_and_merge(tmp_path):
    a = [hl_data.normalize_candle({"t": 0, "T": 1, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "3", "n": 4})]
    b = [hl_data.normalize_candle({"t": 0, "o": 1, "h": 9, "l": 0.5, "c": 8, "v": 3}),
         hl_data.normalize_candle({"t": H, "o": 8, "h": 9, "l": 7, "c": 8.5, "v": 1})]
    hl_data.write_cache("btc", "1h", hl_data.merge_candles(a, b), tmp_path)
    got = hl_data.read_cache("BTC", "1h", tmp_path)
    assert [c["t"] for c in got] == [0, H] and got[0]["h"] == 9.0  # later series wins


def test_recorder_writes_candles_ctxs_and_heartbeat(tmp_path, monkeypatch):
    now = 100 * H

    def fake_post(payload, **_):
        if payload["type"] == "candleSnapshot":
            return [{"t": now - H, "T": now - 1, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1", "n": 1}]
        return [{"universe": [{"name": "BTC"}, {"name": "ZZZ"}]},
                [{"funding": "0.0000125", "premium": "0", "openInterest": "1", "markPx": "1",
                  "oraclePx": "1", "dayNtlVlm": "1"}, {"funding": "0.1"}]]

    monkeypatch.setattr(hl_data, "_post", fake_post)
    monkeypatch.setattr(candle_recorder.time, "sleep", lambda *_: None)
    monkeypatch.setenv("CANDLE_RECORDER_COINS", "btc")
    candle_recorder.run_once(tmp_path)
    assert hl_data.read_cache("BTC", "1h", tmp_path)[0]["t"] == now - H
    assert (tmp_path / "BTC_15m.csv").exists()
    ctx = (tmp_path / "asset_ctxs.csv").read_text().splitlines()
    assert len(ctx) == 2 and ctx[1].split(",")[1:3] == ["BTC", "0.0000125"]
    hb = tmp_path / candle_recorder.HEARTBEAT
    assert hb.exists() and time.time() - os.path.getmtime(hb) < 60


def test_recorder_never_imports_trading_code():
    src = open(candle_recorder.__file__).read()
    assert "from core" not in src and "import core" not in src and "dotenv" not in src


def test_daily_from_hourly_includes_partial_day():
    h = _bars([(1, 2, 0.5, 1.5)] * 30)
    d = daily_from_hourly(h)
    assert len(d) == 2 and d[0]["h"] == 2 and d[1]["c"] == 1.5


# ── walk-forward selection ─────────────────────────────────────────────────
def _sig(coin, t, score, direction="long", hour=15, src="structure"):
    return Signal(coin, t, t + H, hour, direction, score, 100.0, 98.0, 104.0, src, "", 0.0)


def _outcomes(sigs, net=1.0, hold=2):
    o = sim.Outcome(0, net, net / 2, "tp_hit", hold, net)
    res = {}
    for s in sigs:
        oc = sim.Outcome(s.entry_ms + hold * H, o.net_pct, o.r, o.reason, hold, o.mfe_pct)
        res[(s.coin, s.entry_ms, s.direction)] = {wf.exit_key(b, t): oc for b in wf.GRID["be_buffer"]
                                                  for t in wf.GRID["timeout_h"]}
    return res


def test_select_trades_filters_and_portfolio_caps():
    sigs = [_sig("BTC", 0, 60), _sig("BTC", H, 70),            # same coin overlaps → 1 trade
            _sig("ETH", 0, 60, direction="short"),               # shorts off
            _sig("SOL", 0, 60, hour=10),                         # toxic hour
            _sig("XRP", 0, 50),                                  # under exec bar
            _sig("INJ", 0, 62, src="rr_stretch"),                # demoted to 52 → out
            _sig("LINK", 0, 66, src="rr_fallback")]              # demoted to 56 → in
    tr = wf.select_trades(sigs, _outcomes(sigs), wf.BASELINE)
    assert sorted(t.coin for t in tr) == ["BTC", "LINK"]
    rej = wf.select_trades(sigs, _outcomes(sigs), {**wf.BASELINE, "stretched": "reject"})
    assert sorted(t.coin for t in rej) == ["BTC"]


def test_max_positions_cap():
    sigs = [_sig(c, 0, 60 + i) for i, c in enumerate(["A", "B", "C", "D", "E", "F"])]
    tr = wf.select_trades(sigs, _outcomes(sigs), wf.BASELINE)
    assert len(tr) == wf.MAX_POSITIONS and "F" in {t.coin for t in tr}  # best scores first


def test_metrics():
    T = wf.Trade
    m = wf.metrics([T("A", "long", 0, 1, 0, 60, 2.0, 1, "tp", ""), T("A", "long", 2, 3, 0, 60, -1.0, -0.5, "sl", "")], 2)
    assert m["n"] == 2 and m["wr"] == 0.5 and m["pf"] == 2.0 and m["max_dd_pct"] == -1.0 and m["per_day"] == 1.0
    assert wf.metrics([])["n"] == 0


def test_rolling_walk_forward_runs_when_vectorbt_installed():
    pytest.importorskip("vectorbt")
    sigs = [_sig(c, i * 6 * H, 60) for i in range(24 * 4 * 30 // 6) for c in ("BTC",)]
    res = wf.walk_forward(sigs, _outcomes(sigs), 0, sigs[-1].entry_ms + H, train_days=20, test_days=5,
                          min_train_trades=5)
    assert res
