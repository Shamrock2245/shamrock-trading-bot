"""Unit tests for Winning risk + entry filter decision engines."""

from datetime import datetime, timedelta, timezone

import pytest

from core.winning_risk_manager import (
    WinningRiskConfig,
    evaluate_position,
    get_position_size_multiplier,
    is_toxic_zone,
)
from core.hl_scanner_winning_tuning import WinningEntryConfig, WinningEntryFilter


CFG = WinningRiskConfig(
    enabled=True,
    be_pct=0.75,
    be_buffer_pct=0.05,
    tp1_profit_pct=2.0,
    tp1_size_pct=50.0,
    trail_activate_pct=2.0,
    trail_distance_pct=0.5,
    trail_ladder="",  # legacy flat-trail fixture (v32 ladder tested separately)
    min_rule_minutes=30.0,
    min_rule_sl_pct=-1.0,
    loss_timeout_hours=2.0,
)


def test_ultra_fast_break_even_long():
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="BTC",
        current_price=100.80,  # +0.80%
        entry_price=entry,
        entry_time=now - timedelta(minutes=10),
        side="long",
        current_sl=97.5,
        now=now,
        config=CFG,
    )
    assert d.status == "active"
    assert d.should_update_sl
    assert d.sl_price == pytest.approx(entry * 1.0005)
    assert d.reason == "winning_break_even"


def test_tp1_fires_before_be_at_two_pct():
    """Critical: Manus original always returned BE first — TP1 was dead code."""
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="SOL",
        current_price=102.5,  # +2.5%
        entry_price=entry,
        entry_time=now - timedelta(minutes=15),
        side="long",
        current_sl=97.5,
        tp1_hit=False,
        now=now,
        config=CFG,
    )
    assert d.should_partial_close
    assert d.close_size_pct == 50.0
    assert d.mark_tp1 is True
    assert "tp1" in d.reason


def test_aggressive_trail_after_tp1():
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="ETH",
        current_price=103.0,
        entry_price=entry,
        entry_time=now - timedelta(minutes=40),
        side="long",
        peak_price=104.0,
        current_sl=100.05,  # already at BE
        tp1_hit=True,
        now=now,
        config=CFG,
    )
    assert d.should_update_sl
    # CFG has no ladder → flat 0.5% trail from peak 104 → 103.48
    assert abs(d.sl_price - 104.0 * 0.995) < 1e-9
    assert d.reason == "winning_aggressive_trail"


def test_v32_trail_ladder_parsing():
    from core.winning_risk_manager import parse_trail_ladder, trail_distance_for_pnl

    ladder = parse_trail_ladder("2:1.25,4:1.75,8:2.5")
    assert ladder == [(2.0, 1.25), (4.0, 1.75), (8.0, 2.5)]
    # Malformed entries are skipped
    assert parse_trail_ladder("garbage,2:1.25,:,x:y") == [(2.0, 1.25)]
    assert parse_trail_ladder("") == []
    # Rung selection: highest threshold ≤ peak wins; below first rung → base
    assert trail_distance_for_pnl(1.0, ladder, 0.9) == 0.9
    assert trail_distance_for_pnl(2.5, ladder, 0.9) == 1.25
    assert trail_distance_for_pnl(5.0, ladder, 0.9) == 1.75
    assert trail_distance_for_pnl(12.0, ladder, 0.9) == 2.5
    # Empty ladder → flat base
    assert trail_distance_for_pnl(12.0, [], 0.9) == 0.9


def test_v32_tiered_trail_widens_for_runner():
    """An +8% runner must trail 2.5% from peak, not the flat base distance."""
    cfg = WinningRiskConfig(
        enabled=True,
        be_pct=0.75,
        be_buffer_pct=0.05,
        tp1_profit_pct=2.0,
        tp1_size_pct=40.0,
        trail_activate_pct=2.0,
        trail_distance_pct=1.25,
        trail_ladder="2:1.25,4:1.75,8:2.5",
        min_rule_minutes=45.0,
        min_rule_sl_pct=-1.5,
        loss_timeout_hours=4.0,
    )
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="MON",
        current_price=108.0,
        entry_price=entry,
        entry_time=now - timedelta(hours=2),
        side="long",
        peak_price=109.0,  # +9% peak → top rung 2.5%
        current_sl=100.05,
        tp1_hit=True,
        now=now,
        config=cfg,
    )
    assert d.should_update_sl
    assert d.sl_price == pytest.approx(109.0 * (1 - 0.025))
    assert d.reason == "winning_aggressive_trail"


def test_v32_fresh_winner_uses_first_rung():
    """A fresh +2.5% winner trails at 1.25%, not wider."""
    cfg = WinningRiskConfig(
        enabled=True,
        trail_activate_pct=2.0,
        trail_distance_pct=1.25,
        trail_ladder="2:1.25,4:1.75,8:2.5",
    )
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="LDO",
        current_price=102.2,
        entry_price=entry,
        entry_time=now - timedelta(minutes=50),
        side="long",
        peak_price=102.5,  # +2.5% peak → first rung 1.25%
        current_sl=100.05,
        tp1_hit=True,
        now=now,
        config=cfg,
    )
    assert d.should_update_sl
    assert d.sl_price == pytest.approx(102.5 * (1 - 0.0125))


def test_thirty_min_rule_tightens_sl():
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="HEMI",
        current_price=98.5,  # -1.5%
        entry_price=entry,
        entry_time=now - timedelta(minutes=35),
        side="long",
        current_sl=97.5,  # initial -2.5%
        now=now,
        config=CFG,
    )
    assert d.should_update_sl
    assert d.sl_price == pytest.approx(entry * 0.99)  # -1%
    assert d.reason == "winning_30min_rule"


def test_hard_timeout_2h():
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="ONDO",
        current_price=97.0,
        entry_price=entry,
        entry_time=now - timedelta(hours=2.5),
        side="long",
        current_sl=97.5,
        now=now,
        config=CFG,
    )
    assert d.should_close
    assert d.status == "timeout_close"


def test_no_timeout_when_green_after_2h():
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="XMR",
        current_price=101.0,
        entry_price=entry,
        entry_time=now - timedelta(hours=3),
        side="long",
        current_sl=100.05,
        tp1_hit=False,
        now=now,
        config=CFG,
    )
    assert not d.should_close
    # +1% → BE lock
    assert d.should_update_sl or d.reason in ("hold", "winning_break_even")


def test_short_break_even():
    entry = 100.0
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    d = evaluate_position(
        coin="BTC",
        current_price=99.0,  # +1% short
        entry_price=entry,
        entry_time=now - timedelta(minutes=20),
        side="short",
        current_sl=102.5,
        now=now,
        config=CFG,
    )
    assert d.should_update_sl
    assert abs(d.sl_price - entry * 0.9995) < 1e-9


def test_toxic_zone_hours():
    assert is_toxic_zone(hour=10, config=CFG) is True
    assert is_toxic_zone(hour=8, config=CFG) is True
    assert is_toxic_zone(hour=14, config=CFG) is False
    assert is_toxic_zone(hour=3, config=CFG) is False
    assert get_position_size_multiplier(hour=11, config=CFG) == 0.5
    assert get_position_size_multiplier(hour=20, config=CFG) == 1.0


def test_entry_volume_floor():
    f = WinningEntryFilter(config=WinningEntryConfig(enabled=True, min_volume_usd=1_000_000))
    bad = f.validate_entry({
        "symbol": "DUST",
        "current_price": 1.0,
        "volume_24h_usd": 50_000,
    })
    assert bad["approved"] is False
    assert "volume" in bad["reason"]

    good = f.validate_entry({
        "symbol": "BTC",
        "current_price": 100.0,
        "volume_24h_usd": 50_000_000,
    })
    assert good["approved"] is True


def test_entry_blacklist_after_3_sl():
    f = WinningEntryFilter(
        config=WinningEntryConfig(enabled=True, min_volume_usd=1_000_000, blacklist_sl_hits=3)
    )
    for _ in range(3):
        f.record_sl_hit("HEMI")
    out = f.validate_entry({
        "symbol": "HEMI",
        "current_price": 1.0,
        "volume_24h_usd": 5_000_000,
    })
    assert out["approved"] is False
    assert out["reason"] == "dynamic_blacklist"


def test_entry_missing_volume_does_not_block():
    """Missing ctx volume (0) must not halt all trading."""
    f = WinningEntryFilter(config=WinningEntryConfig(enabled=True, min_volume_usd=1_000_000))
    out = f.validate_entry({
        "symbol": "ETH",
        "current_price": 3000.0,
        "volume_24h_usd": 0,
    })
    assert out["approved"] is True



def test_vwap_blocks_long_below():
    f = WinningEntryFilter(config=WinningEntryConfig(enabled=True, use_vwap_filter=True))
    out = f.validate_entry({
        "symbol": "ETH",
        "current_price": 99.0,
        "volume_24h_usd": 10_000_000,
        "vwap_15m": 100.0,
        "side": "long",
    })
    assert out["approved"] is False
    assert "vwap" in out["reason"]


def test_disabled_noop():
    d = evaluate_position(
        coin="X",
        current_price=90.0,
        entry_price=100.0,
        entry_time=datetime.now(timezone.utc) - timedelta(hours=5),
        side="long",
        config=WinningRiskConfig(enabled=False),
    )
    assert d.reason == "disabled"
    assert not d.should_close
