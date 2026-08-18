"""tests/test_llm_auto_tuner.py — deterministic fallback + cooldown."""

from core.llm_auto_tuner import (
    _deterministic_trailing_commands,
    _is_open_gem_position,
    generate_tuning_commands,
)


def test_skips_hyperliquid_perps():
    assert _is_open_gem_position({
        "status": "open",
        "token_symbol": "BTC",
        "exchange": "hyperliquid",
    }) is False
    assert _is_open_gem_position({
        "status": "open",
        "token_symbol": "PEPE",
        "chain": "solana",
    }) is True


def test_deterministic_tightens_near_daily_target():
    positions = [{
        "status": "open",
        "token_symbol": "WIF",
        "chain": "solana",
        "entry_price": 1.0,
        "current_price": 1.05,
        "trailing_stop_pct": 10.0,
    }]
    cmds = _deterministic_trailing_commands(positions, daily_pnl=450.0, target_pnl=500.0)
    assert len(cmds) == 1
    assert cmds[0]["action"] == "update_trailing_stop"
    assert cmds[0]["new_trailing_stop_pct"] < 10.0
    assert cmds[0]["new_trailing_stop_pct"] >= 2.0


def test_deterministic_tightens_large_winner_even_if_day_is_cold():
    positions = [{
        "status": "open",
        "token_symbol": "BONK",
        "chain": "solana",
        "entry_price": 1.0,
        "current_price": 1.50,
        "trailing_stop_pct": 12.0,
    }]
    cmds = _deterministic_trailing_commands(positions, daily_pnl=10.0, target_pnl=500.0)
    assert len(cmds) == 1
    assert cmds[0]["new_trailing_stop_pct"] < 12.0


def test_deterministic_does_not_loosen():
    positions = [{
        "status": "open",
        "token_symbol": "POPCAT",
        "chain": "solana",
        "entry_price": 1.0,
        "current_price": 0.97,
        "trailing_stop_pct": 4.0,
    }]
    cmds = _deterministic_trailing_commands(positions, daily_pnl=10.0, target_pnl=500.0)
    assert cmds == []


def test_generate_commands_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    positions = [{
        "status": "open",
        "token_symbol": "WIF",
        "chain": "solana",
        "entry_price": 1.0,
        "current_price": 1.04,
        "trailing_stop_pct": 10.0,
    }]
    cmds = generate_tuning_commands(positions, daily_pnl=460.0, target_pnl=500.0)
    assert cmds
    assert cmds[0]["token"] == "WIF"
