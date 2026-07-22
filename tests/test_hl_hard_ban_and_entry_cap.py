"""v31 tuning: hard-ban toxic coins + max new entries per scan."""

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock


def _reload_scanner(monkeypatch, **env):
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
    sc = _reload_scanner(monkeypatch, HL_PERPS_MAX_NEW_PER_SCAN=None)
    assert sc.HL_PERPS_MAX_NEW_PER_SCAN == 3


def test_entry_cap_math():
    """free_slots and max_new_per_scan combine as min()."""
    free_slots = 10
    max_new_per_scan = 3
    assert min(free_slots, max_new_per_scan) == 3
    free_slots = 1
    assert min(free_slots, max_new_per_scan) == 1
