"""Market regime is journaled on every HL perps paper open/close and split in paper_metrics."""
import json
from pathlib import Path
from types import SimpleNamespace

from core import predator_v1
from core.hl_perps_scanner import build_regime_ctx
from core.regime_filter import Regime
from tests.test_paper_exit_ab import _exec, _rows

CTX = {"market_regime": "Choppy", "regime_bucket": "chop", "regime_adx": 14.2,
       "regime_volume_ratio": 0.8, "stop_dist_pct": 2.0, "vol_bucket": "mid"}


def test_build_regime_ctx_from_state():
    rs = SimpleNamespace(regime=Regime.TRENDING, adx=31.234, volume_ratio=1.5, data_source="binance")
    ctx = build_regime_ctx(rs, None, entry_price=10.0, stop_loss_price=9.8)
    assert ctx["market_regime"] == "Trending" and ctx["regime_bucket"] == "trend"
    assert ctx["regime_adx"] == 31.23 and ctx["regime_source"] == "binance"
    assert ctx["stop_dist_pct"] == 2.0 and ctx["vol_bucket"] == "mid"
    assert "atr_pct" not in ctx


def test_build_regime_ctx_unknown_and_buckets():
    ctx = build_regime_ctx(None, None, entry_price=10.0, stop_loss_price=9.9)
    assert ctx["market_regime"] == "UNKNOWN" and ctx["regime_bucket"] == "unknown"
    assert ctx["vol_bucket"] == "low"
    assert build_regime_ctx(None, "Nuke", entry_price=10, stop_loss_price=9.5)["vol_bucket"] == "high"
    assert build_regime_ctx(None, "Nuke", entry_price=10, stop_loss_price=9.5)["regime_bucket"] == "nuke"
    assert build_regime_ctx(None, "Choppy")["vol_bucket"] == "unknown"


def test_open_and_closes_tagged_and_survive_restart(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    r = e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7,
                               take_profit_price=10.9, regime_ctx=CTX)
    assert r is not None
    op = _rows(tmp_path)[-1]
    assert op["market_regime"] == "Choppy" and op["vol_bucket"] == "mid"
    e2 = _exec(monkeypatch, tmp_path)
    assert e2._restore_paper_positions() == 1
    assert e2.positions["INJ"].regime_ctx == CTX
    e2._paper_close_position("INJ", size_pct=40, exit_reason="tp1_partial")
    e2._paper_close_position("INJ", exit_reason="paper_trail_stop")
    for row in _rows(tmp_path)[-2:]:
        assert row["action"] == "SELL"
        assert row["market_regime"] == "Choppy" and row["regime_bucket"] == "chop"


def test_open_without_ctx_unchanged(monkeypatch, tmp_path):
    e = _exec(monkeypatch, tmp_path)
    e._paper_open_position("INJ", "buy", 50.0, 3, 70, stop_loss_price=9.7, take_profit_price=10.9)
    assert "market_regime" not in _rows(tmp_path)[-1]
    e._paper_close_position("INJ", exit_reason="paper_sl_hit")
    assert "market_regime" not in _rows(tmp_path)[-1]


def _close(pnl, bucket=None, vol=None, **kw):
    r = {"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": pnl,
         "exit_reason": "paper_sl_hit", **kw}
    if bucket:
        r["regime_bucket"] = bucket
    if vol:
        r["vol_bucket"] = vol
    return r


def test_paper_metrics_by_regime(monkeypatch, tmp_path):
    rows = [_close(2.0, "trend", "low"), _close(-1.0, "trend", "mid"), _close(-3.0, "chop", "high"),
            _close(1.0, regime="chop_half"), _close(-4.0)]
    p = tmp_path / "trades.json"
    p.write_text(json.dumps(rows))
    monkeypatch.setenv("TRADES_FILE", str(p))
    m = predator_v1.get_paper_metrics()
    assert m["gates"]["min_pf"] == 1.30 and m["closed_trades"] == 5   # gate unchanged
    br = m["by_regime"]["regime"]
    assert br["trend"]["closed_trades"] == 2 and br["trend"]["profit_factor"] == 2.0
    assert br["chop"]["closed_trades"] == 2 and br["untagged"]["closed_trades"] == 1
    assert br["nuke"]["closed_trades"] == 0
    vb = m["by_regime"]["vol_bucket"]
    assert vb["low"]["closed_trades"] == 1 and vb["untagged"]["closed_trades"] == 2


def test_paper_metrics_by_regime_empty(monkeypatch, tmp_path):
    p = tmp_path / "trades.json"
    p.write_text("[]")
    monkeypatch.setenv("TRADES_FILE", str(p))
    m = predator_v1.get_paper_metrics()
    assert m["by_regime"]["regime"]["trend"]["closed_trades"] == 0


def test_three_file_rule_vol_buckets():
    root = Path(__file__).resolve().parents[1]
    for line in ("HL_PERPS_VOL_BUCKET_LOW_PCT=1.5", "HL_PERPS_VOL_BUCKET_HIGH_PCT=3.0"):
        assert line in (root / ".env.example").read_text()
        assert line in (root / ".github/workflows/ci.yml").read_text()
