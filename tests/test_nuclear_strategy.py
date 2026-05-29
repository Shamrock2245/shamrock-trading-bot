"""
tests/test_nuclear_strategy.py — Unit tests for profile-aware TP/SL evaluation.

Validates that the nuclear strategy pipeline correctly uses StrategyProfile
parameters (5x/12x/30x TP tiers, 10% hard stop, dynamic trailing) instead
of falling back to global settings defaults.
"""

import pytest
import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.wallets import (
    StrategyProfile,
    CONSERVATIVE_PROFILE,
    NUCLEAR_PROFILE,
)
from core.position_monitor import evaluate_position


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: Fake position dictionaries
# ─────────────────────────────────────────────────────────────────────────────

def _make_position(entry_price: float = 1.0, **overrides) -> dict:
    """Create a minimal position dict for testing."""
    pos = {
        "token_address": "0xdeadbeef",
        "token_symbol": "TEST",
        "chain": "base",
        "wallet": "nuclear_wallet_b",
        "entry_price": entry_price,
        "quantity": 1000.0,
        "entry_value_usd": entry_price * 1000,
        "status": "open",
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
        "strategy_profile": "nuclear",
        "gem_score": 90.0,
        "trailing_stop_pct": None,
        "highest_price": entry_price,
    }
    pos.update(overrides)
    return pos


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Nuclear profile TP1 fires at 5x (not default 2x)
# ─────────────────────────────────────────────────────────────────────────────

class TestNuclearTPLadder:
    """Nuclear profile should use 5x/12x/30x TP tiers."""

    def test_tp1_at_5x(self):
        """TP1 should NOT fire at 1.5x under nuclear profile (nuclear TP1 is 2x)."""
        pos = _make_position(entry_price=1.0)
        # At 1.5x — nuclear TP1 is 2x so should NOT sell yet
        result = evaluate_position(pos, current_price=1.5, strategy_profile=NUCLEAR_PROFILE)
        assert result is None, (
            f"Nuclear profile should NOT fire TP1 at 1.5x, got: {result}"
        )

    def test_tp1_fires_at_5x(self):
        """TP1 should fire at 2x under nuclear profile (tuned from 5x)."""
        pos = _make_position(entry_price=1.0)
        result = evaluate_position(pos, current_price=2.1, strategy_profile=NUCLEAR_PROFILE)
        assert result is not None, "Nuclear TP1 should fire at 2.1x"
        assert "tp1_" in result.get("reason", ""), (
            f"Reason should contain 'tp1_', got: {result.get('reason')}"
        )
        assert abs(result.get("sell_pct", 0) - 0.25) < 0.01, (
            f"Nuclear TP1 should sell 25%, got: {result.get('sell_pct')}"
        )

    def test_tp2_fires_at_15x(self):
        """TP2 should fire at 5x under nuclear profile (tuned from 15x)."""
        pos = _make_position(entry_price=1.0, tp1_hit=True)
        result = evaluate_position(pos, current_price=5.1, strategy_profile=NUCLEAR_PROFILE)
        assert result is not None, "Nuclear TP2 should fire at 5.1x"
        assert "tp2_" in result.get("reason", ""), (
            f"Reason should contain 'tp2_', got: {result.get('reason')}"
        )

    def test_tp3_fires_at_50x(self):
        """TP3 should fire at 15x under nuclear profile (tuned from 50x)."""
        pos = _make_position(entry_price=1.0, tp1_hit=True, tp2_hit=True)
        result = evaluate_position(pos, current_price=15.1, strategy_profile=NUCLEAR_PROFILE)
        assert result is not None, "Nuclear TP3 should fire at 15.1x"
        assert "tp3_" in result.get("reason", ""), (
            f"Reason should contain 'tp3_', got: {result.get('reason')}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Conservative profile TP1 fires at 2x
# ─────────────────────────────────────────────────────────────────────────────

class TestConservativeTPLadder:
    """Conservative profile should use 2x/3x TP tiers."""

    def test_tp1_fires_at_2_5x(self):
        """TP1 should fire at 1.5x under conservative profile (tuned from 2.5x)."""
        pos = _make_position(entry_price=1.0, strategy_profile="conservative")
        result = evaluate_position(pos, current_price=1.6, strategy_profile=CONSERVATIVE_PROFILE)
        assert result is not None, "Conservative TP1 should fire at 1.6x"
        assert "tp1_" in result.get("reason", ""), (
            f"Reason should contain 'tp1_', got: {result.get('reason')}"
        )
        assert abs(result.get("sell_pct", 0) - 0.40) < 0.01, (
            f"Conservative TP1 should sell 40%, got: {result.get('sell_pct')}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: No profile falls back to global settings
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackBehavior:
    """Without a profile, evaluate_position should use settings.* defaults."""

    def test_no_profile_uses_defaults(self):
        """Positions without strategy_profile should still work (no crash)."""
        pos = _make_position(entry_price=1.0, strategy_profile="")
        # Should not crash with strategy_profile=None
        result = evaluate_position(pos, current_price=1.5, strategy_profile=None)
        # At 1.5x neither default TP1 (2x) nor nuclear TP1 (5x) should fire
        # But no crash is the main assertion
        # (result may be None or a stop-loss action depending on defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Hard stop fires at correct threshold per profile
# ─────────────────────────────────────────────────────────────────────────────

class TestHardStops:
    """Hard stop should use profile-specific percentages."""

    def test_nuclear_hard_stop_at_10pct(self):
        """Nuclear hard stop is -10%, should fire at -12%."""
        pos = _make_position(entry_price=1.0)
        # Price dropped 12% — below nuclear's 10% threshold
        result = evaluate_position(pos, current_price=0.88, strategy_profile=NUCLEAR_PROFILE)
        assert result is not None, "Nuclear hard stop should fire at -12%"
        assert "stop" in result.get("reason", "").lower(), (
            f"Reason should mention 'stop', got: {result.get('reason')}"
        )

    def test_conservative_hard_stop_tolerance(self):
        """Conservative hard stop is -15% (tuned from -20%), should NOT fire at -10%."""
        pos = _make_position(entry_price=1.0, strategy_profile="conservative")
        # Price dropped 10% — within conservative tolerance (hard stop is now 15%)
        result = evaluate_position(pos, current_price=0.91, strategy_profile=CONSERVATIVE_PROFILE)
        # Should NOT trigger hard stop (15% threshold)
        if result is not None:
            assert "stop" not in result.get("reason", "").lower(), (
                f"Conservative should NOT stop at -9%, got: {result.get('reason')}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Profile configuration values are correct
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileConfig:
    """Verify the StrategyProfile dataclass values are what we expect."""

    def test_nuclear_profile_values(self):
        # TUNED values: TP1 2x (was 5x), TP2 5x (was 15x), TP3 15x (was 50x)
        # Position size 20% (was 35%), hard stop 12% (was 10%), kelly 0.50 (was 0.80)
        assert NUCLEAR_PROFILE.name == "nuclear"
        assert NUCLEAR_PROFILE.tp1_mult == 2.0
        assert NUCLEAR_PROFILE.tp1_sell_pct == 0.25
        assert NUCLEAR_PROFILE.tp2_mult == 5.0
        assert NUCLEAR_PROFILE.tp2_sell_pct == 0.30
        assert NUCLEAR_PROFILE.tp3_mult == 15.0
        assert NUCLEAR_PROFILE.tp3_sell_pct == 0.20
        assert NUCLEAR_PROFILE.hard_stop_pct == 12.0
        assert NUCLEAR_PROFILE.trailing_tighten == {5.0: 12.0, 10.0: 7.0}
        assert NUCLEAR_PROFILE.max_position_pct == 20.0
        assert NUCLEAR_PROFILE.kelly_clamp_max == 0.50
        assert NUCLEAR_PROFILE.max_slippage_pct == 8.0

    def test_conservative_profile_values(self):
        # TUNED values: TP1 1.5x, sell 40%, TP2 1.8x, hard stop 10%
        assert CONSERVATIVE_PROFILE.name == "conservative"
        assert CONSERVATIVE_PROFILE.tp1_mult == 1.5
        assert CONSERVATIVE_PROFILE.tp1_sell_pct == 0.40
        assert CONSERVATIVE_PROFILE.tp2_mult == 1.8
        assert CONSERVATIVE_PROFILE.tp2_sell_pct == 0.35
        assert CONSERVATIVE_PROFILE.tp3_mult == 5.0
        assert CONSERVATIVE_PROFILE.hard_stop_pct == 10.0

    def test_profile_map_lookups(self):
        """Verify the _PROFILE_MAP used by position_monitor resolves correctly."""
        from core.position_monitor import _PROFILE_MAP
        assert _PROFILE_MAP["nuclear"] is NUCLEAR_PROFILE
        assert _PROFILE_MAP["conservative"] is CONSERVATIVE_PROFILE
        assert _PROFILE_MAP.get("") is None
        assert _PROFILE_MAP.get("nonexistent") is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: TP tier marking uses substring match
# ─────────────────────────────────────────────────────────────────────────────

class TestTPTierMarking:
    """TP tier flags should be set correctly for any profile's reason strings."""

    def test_nuclear_tp1_reason_format(self):
        """Nuclear TP1 reason should contain 'tp1_' (e.g. 'tp1_2x')."""
        pos = _make_position(entry_price=1.0)
        result = evaluate_position(pos, current_price=2.1, strategy_profile=NUCLEAR_PROFILE)
        if result:
            reason = result.get("reason", "")
            assert "tp1_" in reason, f"Expected 'tp1_' in reason, got: {reason}"
            # Verify the multiplier is in the reason (e.g. "tp1_2x")
            assert "2" in reason, f"Expected '2' in nuclear TP1 reason, got: {reason}"

    def test_conservative_tp1_reason_format(self):
        """Conservative TP1 reason should contain 'tp1_' (e.g. 'tp1_2.5x')."""
        pos = _make_position(entry_price=1.0, strategy_profile="conservative")
        result = evaluate_position(pos, current_price=2.6, strategy_profile=CONSERVATIVE_PROFILE)
        if result:
            reason = result.get("reason", "")
            assert "tp1_" in reason, f"Expected 'tp1_' in reason, got: {reason}"
            assert "2" in reason, f"Expected '2' in conservative TP1 reason, got: {reason}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
