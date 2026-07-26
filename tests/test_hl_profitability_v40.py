"""v40 profitability architecture: Fib geometry, volume tiers, token resolve."""

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_ensure_tp_sl_geometry_long_repairs_wrong_side_fib():
    import core.hl_perps_scanner as sc

    importlib.reload(sc)
    entry = 100.0
    # Fib bug: TP below entry for a long
    tp, sl, src = sc._ensure_tp_sl_geometry(
        direction="long",
        entry=entry,
        take_profit=88.0,
        stop_loss=97.0,
        min_rr=1.2,
        default_sl_pct=0.025,
        tp_source="fib",
    )
    assert sl < entry < tp
    risk = entry - sl
    assert (tp - entry) / risk >= 1.2 - 1e-9
    assert "rr_fallback" in src


def test_ensure_tp_sl_geometry_short_repairs_wrong_side():
    import core.hl_perps_scanner as sc

    importlib.reload(sc)
    entry = 50.0
    tp, sl, src = sc._ensure_tp_sl_geometry(
        direction="short",
        entry=entry,
        take_profit=55.0,  # wrong side
        stop_loss=51.0,
        min_rr=1.2,
        default_sl_pct=0.025,
        tp_source="fib",
    )
    assert tp < entry < sl
    assert "rr_fallback" in src


def test_ensure_tp_sl_geometry_preserves_valid_structure():
    import core.hl_perps_scanner as sc

    importlib.reload(sc)
    entry = 10.0
    tp, sl, src = sc._ensure_tp_sl_geometry(
        direction="long",
        entry=entry,
        take_profit=10.6,
        stop_loss=9.75,
        min_rr=1.2,
        default_sl_pct=0.025,
        tp_source="fib",
    )
    assert abs(tp - 10.6) < 1e-9
    assert abs(sl - 9.75) < 1e-9


def test_volume_tier_hard_reject():
    from core.hl_scanner_winning_tuning import WinningEntryConfig, WinningEntryFilter

    filt = WinningEntryFilter(
        config=WinningEntryConfig(
            enabled=True,
            min_volume_usd=500_000,
            hard_volume_usd=250_000,
            low_volume_size_multiplier=0.5,
        )
    )
    out = filt.validate_entry(
        {"symbol": "STBL", "volume_24h_usd": 160_000, "current_price": 1.0}
    )
    assert out["approved"] is False
    assert "volume_below_hard" in out["reason"]


def test_volume_tier_soft_size_cut():
    from core.hl_scanner_winning_tuning import WinningEntryConfig, WinningEntryFilter

    filt = WinningEntryFilter(
        config=WinningEntryConfig(
            enabled=True,
            min_volume_usd=500_000,
            hard_volume_usd=250_000,
            low_volume_size_multiplier=0.5,
            use_vwap_filter=False,
        )
    )
    out = filt.validate_entry(
        {"symbol": "GMX", "volume_24h_usd": 290_000, "current_price": 7.0}
    )
    assert out["approved"] is True
    assert out["position_size_multiplier"] == pytest.approx(0.5)


def test_volume_tier_high_boost():
    from core.hl_scanner_winning_tuning import WinningEntryConfig, WinningEntryFilter

    filt = WinningEntryFilter(
        config=WinningEntryConfig(
            enabled=True,
            min_volume_usd=500_000,
            hard_volume_usd=250_000,
            high_volume_usd=2_000_000,
            high_volume_size_multiplier=1.1,
            use_vwap_filter=False,
        )
    )
    out = filt.validate_entry(
        {"symbol": "VVV", "volume_24h_usd": 5_000_000, "current_price": 13.0}
    )
    assert out["approved"] is True
    assert out["position_size_multiplier"] == pytest.approx(1.1)


def test_resolve_static_aave():
    from data.providers.hl_token_resolve import resolve_hl_token

    r = resolve_hl_token("AAVE", use_search=False)
    assert r is not None
    assert r["chain"] == "ethereum"
    assert r["address"].startswith("0x")
    assert r["source"] == "static"


def test_resolve_empty_stays_none_without_search():
    from data.providers.hl_token_resolve import resolve_hl_token, _RESOLVE_CACHE

    _RESOLVE_CACHE.pop("STBL", None)
    r = resolve_hl_token("STBL", use_search=False)
    # empty static + no search
    assert r is None or not r.get("address")


def test_moralis_score_for_hl_coin_uses_resolve(monkeypatch):
    from data.providers import hl_token_resolve as r

    monkeypatch.setattr(
        r,
        "resolve_hl_token",
        lambda sym, use_search=True: {
            "symbol": "GMX",
            "chain": "arbitrum",
            "address": "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a",
            "source": "static",
        },
    )
    with patch(
        "data.providers.moralis_money.get_token_score",
        return_value={"score": 25, "token_address": "0xfc5A"},
    ):
        out = r.moralis_score_for_hl_coin("GMX")
    assert out is not None
    assert out["score"] == 25
    assert out["resolved_chain"] == "arbitrum"
    assert out["resolve_source"] == "static"
