import time
import core.hl_perps_scanner as m


class _S:
    coin_fails_expectancy = m.HLPerpsScanner.coin_fails_expectancy

    def __init__(self, perf):
        self._coin_perf = perf


def test_legacy_rows_without_pnl_use_wr_only():
    now = time.time()
    s = _S({"AAVE": {"wins": 6, "losses": 6, "last_updated": now},
            "JUP": {"wins": 0, "losses": 5, "last_updated": now}})
    assert s.coin_fails_expectancy("AAVE") is False
    assert s.coin_fails_expectancy("JUP") is True


def test_pf_still_blocks_when_pnl_known():
    s = _S({"SOL": {"wins": 5, "losses": 5, "gross_profit": 10.0,
                    "gross_loss": 80.0, "last_updated": time.time()}})
    assert s.coin_fails_expectancy("SOL") is True


def test_stale_verdict_expires(monkeypatch):
    monkeypatch.setattr(m, "HL_PERPS_EXPECTANCY_STALE_HOURS", 168.0)
    s = _S({"XMR": {"wins": 0, "losses": 9, "last_updated": time.time() - 30 * 86400}})
    assert s.coin_fails_expectancy("XMR") is False
    monkeypatch.setattr(m, "HL_PERPS_EXPECTANCY_STALE_HOURS", 0.0)
    assert s.coin_fails_expectancy("XMR") is True


# ── Oct 2026: PnL plumbing — PF must not read 0.00 from missing $ data ──────

def test_partial_dollar_row_falls_back_to_wr():
    """INJ 5W/5L with legacy wins (no $) + one $0 ghost loss (gl=1.0 placeholder)."""
    s = _S({"INJ": {"wins": 5, "losses": 5, "gross_profit": 0, "gross_loss": 1.0,
                    "last_updated": time.time()}})
    assert m._trusted_profit_factor(s._coin_perf["INJ"]) is None
    assert s.coin_fails_expectancy("INJ") is False


def test_wr_still_blocks_partial_dollar_row():
    s = _S({"XMR": {"wins": 6, "losses": 22, "gross_profit": 0, "gross_loss": 1.0,
                    "last_updated": time.time()}})
    assert s.coin_fails_expectancy("XMR") is True  # 21% WR < 30%


def test_usd_counters_need_min_sample(monkeypatch):
    monkeypatch.setattr(m, "HL_PERPS_AUTOBAN_MIN_TRADES", 5)
    perf = {"wins": 9, "losses": 6, "usd_wins": 1, "usd_losses": 2,
            "usd_gross_profit": 1.0, "usd_gross_loss": 9.0, "last_updated": time.time()}
    assert m._trusted_profit_factor(perf) is None
    assert _S({"A": perf}).coin_fails_expectancy("A") is False
    perf.update(usd_wins=2, usd_losses=3)
    assert m._trusted_profit_factor(perf) == 1.0 / 9.0
    assert _S({"A": perf}).coin_fails_expectancy("A") is True
