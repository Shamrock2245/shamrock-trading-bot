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
