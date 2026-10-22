"""Predator gate counts only Hyperliquid perps paper closes (counting fix, thresholds unchanged)."""
import json

import pytest

from core import predator_v1 as pv1


def _hl(**kw):
    row = {"chain": "hyperliquid", "token_address": "hl:INJ", "strategy_profile": "hl_perps",
           "is_paper": True, "action": "SELL", "reason": "paper_close", "pnl_usd": 1.0}
    row.update(kw)
    return row


@pytest.fixture
def write(monkeypatch, tmp_path):
    def _w(rows):
        f = tmp_path / "trades.json"
        f.write_text(json.dumps(rows))
        monkeypatch.setenv("TRADES_FILE", str(f))
        return pv1.get_paper_metrics()
    return _w


def test_gem_dex_rows_excluded(write):
    rows = [
        _hl(pnl_usd=4.0),
        _hl(pnl_usd=-2.0),
        # Gem side paper closes on DEX chains must never count
        {"chain": "base", "token_symbol": "AERO", "is_paper": True, "action": "SELL",
         "reason": "fast_fail_stale_momentum", "pnl_usd": -500.0, "strategy_profile": ""},
        {"chain": "solana", "is_paper": True, "action": "SELL", "pnl_usd": 38.0,
         "strategy_profile": "nuclear"},
        {"chain": "ethereum", "is_paper": True, "action": "SELL", "pnl_usd": 92.0},
    ]
    m = write(rows)
    assert m["scope"] == "hyperliquid_perps_paper"
    assert m["closed_trades"] == 2
    assert m["net_pnl"] == 2.0
    assert m["win_rate"] == 0.5
    assert m["profit_factor"] == 2.0


def test_zero_orphan_flagged_live_and_opens_excluded(write):
    rows = [
        _hl(pnl_usd=3.0),
        _hl(pnl_usd=0.0),  # $0 placeholder
        _hl(pnl_usd=None),
        _hl(reason="restart_orphan", pnl_usd=-9.0),
        _hl(exclude_from_metrics=True, pnl_usd=-9.0),
        _hl(is_paper=False, pnl_usd=-9.0),  # live row
        _hl(action="BUY", reason="paper_open", pnl_usd=None),
        _hl(pnl_usd="nan"),
    ]
    m = write(rows)
    assert m["closed_trades"] == 1
    assert m["net_pnl"] == 3.0


def test_legacy_rows_without_chain(write):
    rows = [
        {"strategy_profile": "hl_perps", "is_paper": True, "action": "SELL", "pnl_usd": 1.5},
        {"token_address": "hl:BTC", "is_paper": True, "action": "SELL", "pnl_usd": -0.5},
        {"is_paper": True, "action": "SELL", "pnl_usd": 7.0},  # unknown origin → excluded
    ]
    m = write(rows)
    assert m["closed_trades"] == 2
    assert m["net_pnl"] == 1.0


def test_thresholds_unchanged(write):
    m = write([_hl()])
    g = m["gates"]
    assert (g["min_trades"], g["min_wr"], g["min_pf"]) == (50, 0.50, 1.30)
    assert g["ready"] is False


def test_empty_returns_scope(write):
    m = write([{"chain": "base", "is_paper": True, "action": "SELL", "pnl_usd": 5.0}])
    assert m["closed_trades"] == 0
    assert m["scope"] == "hyperliquid_perps_paper"
