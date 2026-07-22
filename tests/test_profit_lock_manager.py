"""Unit tests for early profit-lock + hard loss time-out decision engine."""

from datetime import datetime, timedelta, timezone

import pytest

from core.profit_lock_manager import (
    ProfitLockConfig,
    ProfitLockManager,
    evaluate_position,
)


CFG = ProfitLockConfig(
    enabled=True,
    be_pct=1.5,
    be_buffer_pct=0.1,
    trail_activate_pct=3.0,
    trail_distance_pct=1.5,
    loss_timeout_hours=4.0,
)


def test_break_even_lock_long():
    entry = 100.0
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="BTC",
        current_price=101.6,  # +1.6%
        entry_price=entry,
        entry_time=now - timedelta(minutes=30),
        side="long",
        current_sl=97.5,  # initial -2.5% SL
        now=now,
        config=CFG,
    )
    assert d.status == "active"
    assert d.should_update_sl
    assert d.sl_price == pytest.approx(entry * 1.001)
    assert d.reason == "break_even_lock"


def test_no_be_lock_below_threshold():
    entry = 100.0
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="ETH",
        current_price=101.0,  # +1.0% < 1.5%
        entry_price=entry,
        entry_time=now - timedelta(minutes=10),
        side="long",
        current_sl=97.5,
        now=now,
        config=CFG,
    )
    assert d.status == "active"
    assert d.sl_price is None
    assert not d.should_close


def test_early_trail_long_from_peak():
    entry = 100.0
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="SOL",
        current_price=105.0,  # +5%
        entry_price=entry,
        entry_time=now - timedelta(hours=1),
        side="long",
        peak_price=106.0,
        current_sl=100.1,  # already at BE
        now=now,
        config=CFG,
    )
    assert d.status == "active"
    assert d.should_update_sl
    # trail 1.5% from peak 106 → 104.41
    assert abs(d.sl_price - 106.0 * 0.985) < 1e-9
    assert d.reason == "early_trail"


def test_hard_timeout_closes_long_loser():
    entry = 100.0
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="KAITO",
        current_price=97.0,  # -3%
        entry_price=entry,
        entry_time=now - timedelta(hours=5),
        side="long",
        current_sl=97.5,
        now=now,
        config=CFG,
    )
    assert d.should_close
    assert d.status == "timeout_close"
    assert d.hold_hours >= 4.0
    assert d.pnl_pct < 0


def test_no_timeout_when_profitable_after_4h():
    entry = 100.0
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="INJ",
        current_price=102.0,  # still green
        entry_price=entry,
        entry_time=now - timedelta(hours=6),
        side="long",
        current_sl=100.1,
        now=now,
        config=CFG,
    )
    assert not d.should_close
    assert d.status == "active"


def test_short_break_even_and_timeout():
    entry = 100.0
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    # Short in profit: price fell to 98 (-2% for long = +2% short)
    d = evaluate_position(
        coin="BTC",
        current_price=98.0,
        entry_price=entry,
        entry_time=now - timedelta(minutes=20),
        side="short",
        current_sl=102.5,
        now=now,
        config=CFG,
    )
    assert d.should_update_sl
    assert abs(d.sl_price - entry * 0.999) < 1e-9

    # Short in loss >4h
    d2 = evaluate_position(
        coin="BTC",
        current_price=103.0,  # against short
        entry_price=entry,
        entry_time=now - timedelta(hours=5),
        side="short",
        current_sl=102.5,
        now=now,
        config=CFG,
    )
    assert d2.should_close


def test_disabled_config_noop():
    d = evaluate_position(
        coin="BTC",
        current_price=110.0,
        entry_price=100.0,
        entry_time=datetime.now(timezone.utc) - timedelta(hours=10),
        side="long",
        config=ProfitLockConfig(enabled=False),
    )
    assert d.reason == "disabled"
    assert d.sl_price is None
    assert not d.should_close


def test_manager_wrapper_dict_api():
    mgr = ProfitLockManager(config=CFG)
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    state = mgr.process_position(
        "LTC",
        47.0,
        46.0,
        now - timedelta(minutes=40),
        side="long",
        current_sl=45.0,
        now=now,
    )
    assert state["status"] == "active"
    assert state["recommended_sl"] is not None
    assert state["pnl_pct"] > 1.5


def test_kaito_in_toxic_source_default(monkeypatch):
    """trade_history 28/31: KAITO must be hard-banned (soft toxic was insufficient)."""
    import importlib
    import core.hl_perps_scanner as scanner

    monkeypatch.delenv("HL_PERPS_TOXIC_COINS", raising=False)
    monkeypatch.delenv("HL_PERPS_HARD_BAN_COINS", raising=False)
    scanner = importlib.reload(scanner)
    assert "KAITO" in scanner.HL_PERPS_HARD_BAN_COINS
