"""v31/v32 tuning: hard-ban toxic coins, per-scan cap, daily open cap, edge sizing."""

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock


def _reload_scanner(monkeypatch, **env):
    env.setdefault("HL_PERPS_UNIVERSE", "full")
    env.setdefault("HL_PERPS_EXPECTANCY_GATE_ENABLED", "false")
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import core.hl_perps_scanner as sc
    return importlib.reload(sc)


def test_hard_ban_defaults_include_kaito_ape(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_HARD_BAN_COINS=None,
        HL_PERPS_TOXIC_COINS=None,
    )
    assert "KAITO" in sc.HL_PERPS_HARD_BAN_COINS
    assert "APE" in sc.HL_PERPS_HARD_BAN_COINS
    assert "GRASS" in sc.HL_PERPS_HARD_BAN_COINS
    assert "SOL" in sc.HL_PERPS_HARD_BAN_COINS
    assert "TRB" in sc.HL_PERPS_HARD_BAN_COINS
    # AAVE is soft-toxic only (net winner in v31) — not hard-banned by default
    assert "AAVE" not in sc.HL_PERPS_HARD_BAN_COINS
    assert "AAVE" in sc.HL_PERPS_TOXIC_COINS


def test_execute_signal_hard_bans_kaito(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_HARD_BAN_COINS="KAITO,APE",
        HL_PERPS_TOXIC_COINS="AAVE",
    )
    scanner = sc.HLPerpsScanner(hl_executor=MagicMock())
    scanner.hl_executor.is_available.return_value = True
    scanner.hl_executor.positions = {}
    scanner.hl_executor.get_balance.return_value = {"account_value": 1700.0}
    scanner.hl_executor.open_long = MagicMock(return_value={"ok": True})

    signal = SimpleNamespace(
        coin="KAITO",
        direction="long",
        score=90.0,
        leverage=3,
        position_size_usd=150.0,
        entry_price=1.0,
        stop_loss_price=0.97,
        take_profit_price=1.05,
        components={},
    )
    assert scanner._execute_signal(signal) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_execute_signal_allows_non_banned(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_HARD_BAN_COINS="KAITO,APE",
        HL_PERPS_TOXIC_COINS="",
        WINNING_ENTRY_FILTER_ENABLED="false",
        HL_PERPS_LONG_ONLY="true",
    )
    scanner = sc.HLPerpsScanner(hl_executor=MagicMock())
    scanner.hl_executor.is_available.return_value = True
    scanner.hl_executor.positions = {}
    scanner.hl_executor.get_balance.return_value = {"account_value": 1700.0}
    scanner.hl_executor.open_long = MagicMock(return_value={"coin": "GMX"})

    signal = SimpleNamespace(
        coin="GMX",
        direction="long",
        score=80.0,
        leverage=3,
        position_size_usd=150.0,
        entry_price=6.5,
        stop_loss_price=6.3,
        take_profit_price=6.9,
        components={},
    )
    assert scanner._execute_signal(signal) is True
    scanner.hl_executor.open_long.assert_called_once()


def test_max_new_per_scan_default(monkeypatch):
    # v40: 2 → 1 (quality over spray)
    sc = _reload_scanner(monkeypatch, HL_PERPS_MAX_NEW_PER_SCAN=None)
    assert sc.HL_PERPS_MAX_NEW_PER_SCAN == 1


def test_entry_cap_math():
    """free_slots and max_new_per_scan combine as min()."""
    free_slots = 10
    max_new_per_scan = 1
    assert min(free_slots, max_new_per_scan) == 1
    free_slots = 1
    assert min(free_slots, max_new_per_scan) == 1


# ── v32: daily open cap ──────────────────────────────────────────────────────

def _make_ready_scanner(sc):
    scanner = sc.HLPerpsScanner(hl_executor=MagicMock())
    scanner.hl_executor.is_available.return_value = True
    scanner.hl_executor.positions = {}
    scanner.hl_executor.get_balance.return_value = {"account_value": 1700.0}
    scanner.hl_executor.open_long = MagicMock(return_value={"coin": "GMX"})
    return scanner


def _gmx_signal():
    return SimpleNamespace(
        coin="GMX",
        direction="long",
        score=80.0,
        leverage=3,
        position_size_usd=150.0,
        entry_price=6.5,
        stop_loss_price=6.3,
        take_profit_price=6.9,
        components={},
    )


def test_daily_open_cap_default(monkeypatch):
    # Quality over spray: 6 quality trades/day max
    sc = _reload_scanner(monkeypatch, HL_PERPS_MAX_OPENS_PER_DAY=None)
    assert sc.HL_PERPS_MAX_OPENS_PER_DAY == 6


def test_daily_open_cap_blocks_after_limit(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_HARD_BAN_COINS="KAITO",
        HL_PERPS_TOXIC_COINS="",
        WINNING_ENTRY_FILTER_ENABLED="false",
        HL_PERPS_EDGE_SIZING_ENABLED="false",
        HL_PERPS_LONG_ONLY="true",
        HL_PERPS_MAX_OPENS_PER_DAY="2",
    )
    scanner = _make_ready_scanner(sc)
    # First two opens pass and increment the counter
    assert scanner._execute_signal(_gmx_signal()) is True
    assert scanner._execute_signal(_gmx_signal()) is True
    assert scanner.opens_today == 2
    # Third is blocked by the daily cap
    assert scanner._execute_signal(_gmx_signal()) is False
    assert scanner.hl_executor.open_long.call_count == 2


def test_daily_open_cap_resets_at_new_day(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        WINNING_ENTRY_FILTER_ENABLED="false",
        HL_PERPS_EDGE_SIZING_ENABLED="false",
        HL_PERPS_MAX_OPENS_PER_DAY="2",
    )
    scanner = _make_ready_scanner(sc)
    scanner.opens_today = 2
    scanner.daily_pnl_reset_date = "2000-01-01"  # stale → forces reset
    scanner._check_daily_reset()
    assert scanner.opens_today == 0


# ── v32: per-coin edge sizing ──────────────────────────────────────────────

def test_edge_sizing_neutral_below_min_trades(monkeypatch):
    sc = _reload_scanner(monkeypatch, HL_PERPS_EDGE_SIZING_ENABLED="true", HL_PERPS_EDGE_MIN_TRADES="4")
    scanner = _make_ready_scanner(sc)
    scanner._coin_perf = {"MON": {"wins": 2, "losses": 1}}  # 3 trades < 4
    assert scanner.get_edge_size_multiplier("MON") == 1.0
    assert scanner.get_edge_size_multiplier("UNKNOWN") == 1.0


def test_edge_sizing_scales_with_win_rate(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_EDGE_SIZING_ENABLED="true",
        HL_PERPS_EDGE_MIN_TRADES="4",
        HL_PERPS_EDGE_SIZE_MIN="0.6",
        HL_PERPS_EDGE_SIZE_MAX="1.3",
    )
    scanner = _make_ready_scanner(sc)
    scanner._coin_perf = {
        "WINNER": {"wins": 8, "losses": 2},   # 80% WR → max 1.3
        "NEUTRAL": {"wins": 5, "losses": 5},  # 50% WR → 1.0
        "WEAK": {"wins": 3, "losses": 7},     # 30% WR → min 0.6
        "MID": {"wins": 4, "losses": 6},      # 40% WR → 0.8 (midpoint 0.6→1.0)
    }
    assert scanner.get_edge_size_multiplier("WINNER") == 1.3
    assert scanner.get_edge_size_multiplier("NEUTRAL") == 1.0
    assert scanner.get_edge_size_multiplier("WEAK") == 0.6
    assert scanner.get_edge_size_multiplier("MID") == 0.8


def test_edge_sizing_disabled_returns_neutral(monkeypatch):
    sc = _reload_scanner(monkeypatch, HL_PERPS_EDGE_SIZING_ENABLED="false")
    scanner = _make_ready_scanner(sc)
    scanner._coin_perf = {"WINNER": {"wins": 9, "losses": 1}}
    assert scanner.get_edge_size_multiplier("WINNER") == 1.0


# ── v33: freqtrade protections + regime gate ──────────────────────────────

def _v33_env(**extra):
    env = dict(
        WINNING_ENTRY_FILTER_ENABLED="false",
        HL_PERPS_EDGE_SIZING_ENABLED="false",
        HL_PERPS_REGIME_GATE_ENABLED="false",
        HL_PERPS_LONG_ONLY="true",
        HL_PERPS_HARD_BAN_COINS="KAITO",
        HL_PERPS_TOXIC_COINS="",
    )
    env.update(extra)
    return env


def test_slguard_halts_after_loss_cascade(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        **_v33_env(HL_PERPS_SLGUARD_LIMIT="3", HL_PERPS_SLGUARD_WINDOW_MIN="120",
                   HL_PERPS_SLGUARD_HALT_MIN="90", HL_PERPS_AUTOBAN_ENABLED="false"),
    )
    scanner = _make_ready_scanner(sc)
    for coin in ("A1", "B2", "C3"):
        scanner.record_trade_outcome(coin, won=False)
    assert scanner._slguard_halt_until > 0
    # Entries now blocked
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_slguard_ignores_wins(monkeypatch):
    sc = _reload_scanner(monkeypatch, **_v33_env(HL_PERPS_SLGUARD_LIMIT="3"))
    scanner = _make_ready_scanner(sc)
    for coin in ("A1", "B2", "C3", "D4"):
        scanner.record_trade_outcome(coin, won=True)
    assert scanner._slguard_halt_until == 0.0


def test_day_loser_block(monkeypatch):
    from datetime import datetime, timezone
    sc = _reload_scanner(monkeypatch, **_v33_env(HL_PERPS_DAY_LOSER_BLOCK="2"))
    scanner = _make_ready_scanner(sc)
    # Anchor the daily-reset date so _check_daily_reset doesn't wipe the block
    scanner.daily_pnl_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scanner._day_losses = {"GMX": 2}
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()
    # A different coin still trades
    sig = _gmx_signal()
    sig.coin = "OP"
    assert scanner._execute_signal(sig) is True


def test_fee_aware_min_tp_distance(monkeypatch):
    sc = _reload_scanner(monkeypatch, **_v33_env(HL_PERPS_MIN_TP_DISTANCE_PCT="0.8"))
    scanner = _make_ready_scanner(sc)
    sig = _gmx_signal()
    sig.entry_price = 100.0
    sig.take_profit_price = 100.4  # 0.4% < 0.8% — noise trade
    sig.stop_loss_price = 99.0
    assert scanner._execute_signal(sig) is False
    sig2 = _gmx_signal()
    sig2.entry_price = 100.0
    sig2.take_profit_price = 102.0  # 2% — pays
    sig2.stop_loss_price = 99.0
    assert scanner._execute_signal(sig2) is True


def test_leverage_roe_cap(monkeypatch):
    """15x leverage with a 2.5% SL = 37.5% ROE stop-out — capped to 4x at 12% ROE."""
    sc = _reload_scanner(monkeypatch, **_v33_env(HL_PERPS_MAX_SL_ROE_LOSS_PCT="12.0"))
    scanner = _make_ready_scanner(sc)
    sig = _gmx_signal()
    sig.entry_price = 100.0
    sig.stop_loss_price = 97.5   # 2.5% SL
    sig.take_profit_price = 106.0
    sig.leverage = 15
    assert scanner._execute_signal(sig) is True
    assert sig.leverage == 4  # 12 / 2.5 = 4.8 → int → 4


def test_regime_gate_blocks_short_when_not_nuke(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        **_v33_env(HL_PERPS_REGIME_GATE_ENABLED="true", HL_PERPS_LONG_ONLY="false"),
    )
    scanner = _make_ready_scanner(sc)
    scanner.hl_executor.open_short = MagicMock(return_value={"coin": "GMX"})

    from unittest.mock import patch
    import core.regime_filter as rf
    trending_state = rf.RegimeState(
        regime=rf.Regime.TRENDING, adx=30.0, volume_ratio=1.0,
        timestamp=0.0, details="test",
    )
    sig = _gmx_signal()
    sig.direction = "short"
    sig.entry_price = 100.0
    sig.stop_loss_price = 102.5
    sig.take_profit_price = 97.0
    with patch("core.regime_filter.get_regime", return_value=trending_state):
        assert scanner._execute_signal(sig) is False
    scanner.hl_executor.open_short.assert_not_called()


def test_day_loser_block_net_aware_allows_winner(monkeypatch):
    """v41: a coin with losses AND a win today keeps trading (NIL 7/27 case)."""
    from datetime import datetime, timezone
    sc = _reload_scanner(monkeypatch, **_v33_env(HL_PERPS_DAY_LOSER_BLOCK="3"))
    scanner = _make_ready_scanner(sc)
    scanner.daily_pnl_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scanner._day_losses = {"GMX": 3}
    scanner._day_wins = {"GMX": 1}  # one win today → keeps its slot
    assert scanner._execute_signal(_gmx_signal()) is True


def test_hot_streak_boost_and_reset(monkeypatch):
    """v41: 2 consecutive wins → 1.25x size boost; any loss resets the streak."""
    sc = _reload_scanner(
        monkeypatch,
        **_v33_env(HL_PERPS_HOT_STREAK_WINS="2", HL_PERPS_HOT_STREAK_MULT="1.25"),
    )
    scanner = _make_ready_scanner(sc)
    scanner.record_trade_outcome("GMX", won=True)
    scanner.record_trade_outcome("GMX", won=True)
    assert scanner._win_streak["GMX"] == 2
    sig = _gmx_signal()
    assert scanner._execute_signal(sig) is True
    # open_long called with boosted size (base 150 × 1.25 capped by notional/lev)
    _, kwargs = scanner.hl_executor.open_long.call_args
    assert kwargs["size_usd"] > 100.0  # boosted above the notional-capped base
    # streak dies on a loss
    scanner.record_trade_outcome("GMX", won=False)
    assert scanner._win_streak["GMX"] == 0


def test_regime_gate_blocks_long_in_nuke(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        **_v33_env(HL_PERPS_REGIME_GATE_ENABLED="true"),
    )
    scanner = _make_ready_scanner(sc)
    from unittest.mock import patch
    import core.regime_filter as rf
    nuke_state = rf.RegimeState(
        regime=rf.Regime.NUKE, adx=40.0, volume_ratio=2.0,
        timestamp=0.0, details="test",
    )
    with patch("core.regime_filter.get_regime", return_value=nuke_state):
        assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_min_rr_and_allowlist_defaults(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_MIN_RR=None,
        HL_PERPS_UNIVERSE=None,
        HL_PERPS_ALLOWLIST=None,
    )
    assert sc.HL_PERPS_MIN_RR == 1.5
    assert sc.HL_PERPS_UNIVERSE == "allowlist"
    assert "AAVE" in sc.HL_PERPS_ALLOWLIST
    assert "MON" in sc.HL_PERPS_ALLOWLIST
    assert "SOL" not in sc.HL_PERPS_ALLOWLIST
    assert "TRB" not in sc.HL_PERPS_ALLOWLIST


def test_allowlist_blocks_off_list_coin(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_UNIVERSE="allowlist",
        HL_PERPS_ALLOWLIST="AAVE,MON",
        HL_PERPS_TOXIC_COINS="",
        HL_PERPS_EXPECTANCY_GATE_ENABLED="false",
        WINNING_ENTRY_FILTER_ENABLED="false",
        HL_PERPS_EDGE_SIZING_ENABLED="false",
        HL_PERPS_LONG_ONLY="true",
    )
    scanner = _make_ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()
    sig = _gmx_signal()
    sig.coin = "MON"
    assert scanner._execute_signal(sig) is True


def test_expectancy_gate_blocks_negative_pf(monkeypatch):
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_UNIVERSE="full",
        HL_PERPS_EXPECTANCY_GATE_ENABLED="true",
        HL_PERPS_AUTOBAN_MIN_TRADES="5",
        HL_PERPS_AUTOBAN_PF_THRESHOLD="0.85",
        WINNING_ENTRY_FILTER_ENABLED="false",
        HL_PERPS_EDGE_SIZING_ENABLED="false",
        HL_PERPS_LONG_ONLY="true",
    )
    scanner = _make_ready_scanner(sc)
    scanner._coin_perf = {
        "GMX": {
            "wins": 2,
            "losses": 6,
            "gross_profit": 4.0,
            "gross_loss": 20.0,
            "pnl_usd": -16.0,
        }
    }
    assert scanner.coin_fails_expectancy("GMX") is True
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_pf_autoban_catches_high_wr_loser(monkeypatch):
    """SOL-class: 45% WR still loses money — must ban on PF, not just WR."""
    sc = _reload_scanner(
        monkeypatch,
        HL_PERPS_AUTOBAN_ENABLED="true",
        HL_PERPS_AUTOBAN_MIN_TRADES="5",
        HL_PERPS_AUTOBAN_WR_THRESHOLD="0.32",
        HL_PERPS_AUTOBAN_PF_THRESHOLD="0.85",
    )
    scanner = _make_ready_scanner(sc)
    # 3 wins / 4 losses = 43% WR (above WR threshold) but PF = 3/20 = 0.15
    for _ in range(3):
        scanner.record_trade_outcome("SOLX", won=True, pnl_usd=1.0)
    for _ in range(4):
        scanner.record_trade_outcome("SOLX", won=False, pnl_usd=-5.0)
    assert "SOLX" in scanner._autoban_until
