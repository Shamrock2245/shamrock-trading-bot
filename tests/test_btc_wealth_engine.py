"""
tests/test_btc_wealth_engine.py — Unit tests for BTC Wealth Retention Engine

Tests cover:
  - BTCWealthEngine.evaluate_rotation() rotation logic
  - BTCWealthEngine.update_whale_multiplier()
  - BTCWealthEngine.calculate_ema()
  - Moralis CU Budget Manager
  - moralis_entity classify_wallet
  - moralis_market_metrics regime signal
  - moralis_defi empty wallet handling
"""

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# BTC Wealth Engine Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestBtcWealthEngine(unittest.TestCase):
    """Test the BTC Wealth Engine rotation logic."""

    def _make_engine(self):
        """Create a BTCWealthEngine without calling __init__ (avoids file I/O)."""
        from core.btc_wealth_engine import BTCWealthEngine, BTCWealthState
        import threading
        engine = BTCWealthEngine.__new__(BTCWealthEngine)
        engine.enabled = True
        engine.base_pct = 0.10          # 10% baseline
        engine.dip_threshold_7d = 0.05  # 5% below 7d EMA
        engine.deep_dip_threshold_30d = 0.15  # 15% below 30d EMA
        engine.euphoria_threshold_30d = 0.20  # 20% above 30d EMA
        engine.state = BTCWealthState(whale_multiplier=1.0)
        engine._lock = threading.Lock()
        return engine

    def _mock_btc_data(self, price_usd: float, sparkline_len: int = 50, ema_offset: float = 0.0):
        """Return mock BTC price data and sparkline."""
        # Build a sparkline where the last price is price_usd
        # ema_offset: positive = price above EMAs, negative = price below EMAs
        base = price_usd / (1 + ema_offset)
        sparkline = [base] * sparkline_len
        sparkline[-1] = price_usd
        btc_info = {
            "price_usd": price_usd,
            "price_change_24h_pct": 0.0,
            "market_cap_usd": 1_000_000_000_000,
        }
        return btc_info, sparkline

    def test_evaluate_rotation_disabled(self):
        """Test that disabled engine always returns 0."""
        engine = self._make_engine()
        engine.enabled = False
        result = engine.evaluate_rotation(1000.0)
        self.assertEqual(result, 0.0)

    def test_evaluate_rotation_negative_pnl(self):
        """Test that negative PnL returns 0."""
        engine = self._make_engine()
        result = engine.evaluate_rotation(-100.0)
        self.assertEqual(result, 0.0)

    def test_evaluate_rotation_baseline(self):
        """Test baseline 10% rotation when BTC is at EMA."""
        engine = self._make_engine()
        btc_info, sparkline = self._mock_btc_data(50000.0, ema_offset=0.0)
        
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=btc_info), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=sparkline), \
             patch("core.macro_filter.get_macro_regime", side_effect=Exception("no macro")):
            result = engine.evaluate_rotation(1000.0)
        
        # 1000 * 0.10 = 100 USD
        self.assertAlmostEqual(result, 100.0, places=1)

    def test_evaluate_rotation_dip_accumulation(self):
        """Test 25% rotation when BTC is 10% below 7d EMA."""
        engine = self._make_engine()
        # Price 10% below EMA → dip accumulation
        btc_info, sparkline = self._mock_btc_data(45000.0, sparkline_len=50, ema_offset=0.0)
        # Override sparkline so EMA7 ≈ 50000 but current price = 45000
        sparkline = [50000.0] * 50
        sparkline[-1] = 45000.0
        btc_info["price_usd"] = 45000.0
        
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=btc_info), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=sparkline), \
             patch("core.macro_filter.get_macro_regime", side_effect=Exception("no macro")):
            result = engine.evaluate_rotation(1000.0)
        
        # 1000 * 0.25 = 250 USD
        self.assertAlmostEqual(result, 250.0, places=1)

    def test_evaluate_rotation_deep_dip(self):
        """Test 40% rotation when BTC is 20% below 30d EMA."""
        engine = self._make_engine()
        sparkline = [50000.0] * 50
        sparkline[-1] = 40000.0  # 20% below EMA
        btc_info = {"price_usd": 40000.0, "price_change_24h_pct": 0.0, "market_cap_usd": 1e12}
        
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=btc_info), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=sparkline), \
             patch("core.macro_filter.get_macro_regime", side_effect=Exception("no macro")):
            result = engine.evaluate_rotation(1000.0)
        
        # 1000 * 0.40 = 400 USD
        self.assertAlmostEqual(result, 400.0, places=1)

    def test_evaluate_rotation_euphoria_brake(self):
        """Test 5% rotation when BTC is 25% above 30d EMA."""
        engine = self._make_engine()
        sparkline = [50000.0] * 50
        sparkline[-1] = 62500.0  # 25% above EMA
        btc_info = {"price_usd": 62500.0, "price_change_24h_pct": 0.0, "market_cap_usd": 1e12}
        
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=btc_info), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=sparkline), \
             patch("core.macro_filter.get_macro_regime", side_effect=Exception("no macro")):
            result = engine.evaluate_rotation(1000.0)
        
        # 1000 * 0.05 = 50 USD
        self.assertAlmostEqual(result, 50.0, places=1)

    def test_evaluate_rotation_no_btc_data(self):
        """Test that missing BTC data returns 0."""
        engine = self._make_engine()
        
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=None), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=[]):
            result = engine.evaluate_rotation(1000.0)
        
        self.assertEqual(result, 0.0)

    def test_update_whale_multiplier_accumulate(self):
        """Test that whale accumulation sets multiplier to 1.2."""
        engine = self._make_engine()
        with patch.object(engine, "_save_state"):
            engine.update_whale_multiplier("accumulate")
        self.assertAlmostEqual(engine.state.whale_multiplier, 1.2, places=2)

    def test_update_whale_multiplier_distribute(self):
        """Test that whale distribution sets multiplier to 0.5."""
        engine = self._make_engine()
        with patch.object(engine, "_save_state"):
            engine.update_whale_multiplier("distribute")
        self.assertAlmostEqual(engine.state.whale_multiplier, 0.5, places=2)

    def test_update_whale_multiplier_neutral(self):
        """Test that neutral resets multiplier to 1.0."""
        engine = self._make_engine()
        engine.state.whale_multiplier = 1.2
        with patch.object(engine, "_save_state"):
            engine.update_whale_multiplier("neutral")
        self.assertAlmostEqual(engine.state.whale_multiplier, 1.0, places=2)

    def test_calculate_ema_simple(self):
        """Test EMA calculation with known values."""
        engine = self._make_engine()
        # All same price → EMA should equal that price
        prices = [100.0] * 20
        ema = engine.calculate_ema(prices, 20)
        self.assertAlmostEqual(ema, 100.0, places=2)

    def test_calculate_ema_empty(self):
        """Test EMA calculation with empty list returns 0."""
        engine = self._make_engine()
        ema = engine.calculate_ema([], 20)
        self.assertEqual(ema, 0.0)

    def test_whale_multiplier_affects_rotation(self):
        """Test that whale multiplier correctly scales rotation amount."""
        engine = self._make_engine()
        sparkline = [50000.0] * 50
        btc_info = {"price_usd": 50000.0, "price_change_24h_pct": 0.0, "market_cap_usd": 1e12}
        
        # Test with whale accumulation (1.2x multiplier)
        engine.state.whale_multiplier = 1.2
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=btc_info), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=sparkline), \
             patch("core.macro_filter.get_macro_regime", side_effect=Exception("no macro")):
            result_accum = engine.evaluate_rotation(1000.0)
        
        # Test with whale distribution (0.5x multiplier)
        engine.state.whale_multiplier = 0.5
        with patch("core.btc_wealth_engine.get_bitcoin_price", return_value=btc_info), \
             patch("core.btc_wealth_engine.get_bitcoin_sparkline", return_value=sparkline), \
             patch("core.macro_filter.get_macro_regime", side_effect=Exception("no macro")):
            result_dist = engine.evaluate_rotation(1000.0)
        
        # Accumulation should give more rotation than distribution
        self.assertGreater(result_accum, result_dist)


# ─────────────────────────────────────────────────────────────────────────────
# Moralis CU Budget Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestMoralisCUBudget(unittest.TestCase):
    """Test the Moralis CU Budget Manager."""

    def _make_manager(self):
        """Create a fresh CU budget manager without loading from disk."""
        from core.moralis_cu_budget import MoralisCUBudgetManager, CUBudgetState
        manager = MoralisCUBudgetManager.__new__(MoralisCUBudgetManager)
        manager._state = CUBudgetState()
        return manager

    def test_record_increases_consumed(self):
        """Test that recording an endpoint increases total consumed."""
        from core.moralis_cu_budget import CU_COSTS
        manager = self._make_manager()
        initial = manager._state.total_consumed
        
        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000):
            manager.record("token_price")
        
        self.assertEqual(
            manager._state.total_consumed,
            initial + CU_COSTS["token_price"]
        )

    def test_can_afford_cheap_in_emergency(self):
        """Test that cheap calls are allowed in EMERGENCY mode."""
        manager = self._make_manager()
        manager._state.throttle_mode = "EMERGENCY"
        manager._state.total_consumed = 90_000
        manager._state.day_key = "2099-01-01"  # avoid daily-reset side effects in assertions
        
        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget.SAFETY_BUFFER_PCT", 0.15), \
             patch("core.moralis_cu_budget._utc_day_key", return_value="2099-01-01"):
            # Cheap band (≤50 CU): EVM price / metadata allowed
            self.assertTrue(manager.can_afford("token_metadata"))
            self.assertTrue(manager.can_afford("token_price"))

    def test_cannot_afford_expensive_in_emergency(self):
        """Test that expensive calls are blocked in EMERGENCY mode."""
        manager = self._make_manager()
        manager._state.throttle_mode = "EMERGENCY"
        manager._state.total_consumed = 90_000
        manager._state.day_key = "2099-01-01"
        
        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget.SAFETY_BUFFER_PCT", 0.15), \
             patch("core.moralis_cu_budget._utc_day_key", return_value="2099-01-01"):
            # Score (100 CU) and DeFi (5000 CU) blocked in EMERGENCY
            self.assertFalse(manager.can_afford("token_score"))
            self.assertFalse(manager.can_afford("wallet_defi_positions"))

    def test_hard_stop_never_exceeds_monthly_budget(self):
        """Even NORMAL mode cannot spend past remaining monthly CU."""
        manager = self._make_manager()
        manager._state.throttle_mode = "NORMAL"
        manager._state.total_consumed = 99_980  # 20 CU left
        manager._state.day_key = "2099-01-01"

        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget._utc_day_key", return_value="2099-01-01"):
            # token_price costs 50 > 20 remaining → blocked
            self.assertFalse(manager.can_afford("token_price"))
            # entity_categories costs 10 ≤ 20 → allowed
            self.assertTrue(manager.can_afford("entity_categories"))

    def test_exhausted_blocks_everything(self):
        """EXHAUSTED / zero remaining blocks all paid REST."""
        manager = self._make_manager()
        manager._state.total_consumed = 100_000
        manager._state.throttle_mode = "EXHAUSTED"
        manager._state.day_key = "2099-01-01"

        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget._utc_day_key", return_value="2099-01-01"):
            self.assertFalse(manager.can_afford("token_metadata"))
            self.assertFalse(manager.can_afford("token_price"))
            self.assertFalse(manager.can_afford("wallet_defi_positions"))

    def test_cannot_afford_defi_in_conservative(self):
        """Test that DeFi calls (5000 CU) are blocked in CONSERVATIVE mode."""
        manager = self._make_manager()
        manager._state.throttle_mode = "CONSERVATIVE"
        # ~76% used → remaining < 25% keeps CONSERVATIVE via _effective_mode
        manager._state.total_consumed = 76_000
        manager._state.day_key = "2099-01-01"

        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget.CONSERVATIVE_PCT", 0.25), \
             patch("core.moralis_cu_budget._utc_day_key", return_value="2099-01-01"):
            self.assertFalse(manager.can_afford("wallet_defi_positions"))

    def test_get_remaining_budget(self):
        """Test remaining budget calculation."""
        manager = self._make_manager()
        manager._state.total_consumed = 25_000
        
        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000):
            remaining = manager.get_remaining_budget()
        # 100,000 - 25,000 = 75,000
        self.assertEqual(remaining, 75_000)

    def test_throttle_mode_updates_to_emergency(self):
        """Test that throttle mode updates to EMERGENCY when budget is nearly exhausted."""
        manager = self._make_manager()
        manager._state.total_consumed = 86_000  # 86% used
        
        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget.SAFETY_BUFFER_PCT", 0.15):
            manager._update_throttle_mode()
        
        self.assertEqual(manager._state.throttle_mode, "EMERGENCY")

    def test_throttle_mode_updates_to_conservative(self):
        """Test that throttle mode updates to CONSERVATIVE at 76% used (24% remaining < 25% threshold)."""
        manager = self._make_manager()
        manager._state.total_consumed = 76_000  # 76% used → 24% remaining < 25% threshold

        with patch("core.moralis_cu_budget.MONTHLY_CU_BUDGET", 100_000), \
             patch("core.moralis_cu_budget.SAFETY_BUFFER_PCT", 0.15):
            manager._update_throttle_mode()

        self.assertEqual(manager._state.throttle_mode, "CONSERVATIVE")

    def test_cu_costs_registry_has_expected_keys(self):
        """Test that CU_COSTS registry has all expected endpoint keys."""
        from core.moralis_cu_budget import CU_COSTS
        
        expected_keys = [
            "token_price", "token_metadata", "token_score",
            "token_top_traders", "wallet_defi_summary", "wallet_defi_positions",
            "entity_search", "global_market_cap", "btc_address_stats",
        ]
        for key in expected_keys:
            self.assertIn(key, CU_COSTS, f"Missing CU cost for: {key}")

    def test_track_cu_decorator_skips_on_emergency(self):
        """Test that @track_cu decorator skips function call in EMERGENCY mode."""
        from core.moralis_cu_budget import track_cu, cu_budget, MONTHLY_CU_BUDGET
        
        original_mode = cu_budget._state.throttle_mode
        original_consumed = cu_budget._state.total_consumed
        original_day = cu_budget._state.day_key
        
        try:
            # Force emergency band via remaining budget, not only stored mode
            budget = MONTHLY_CU_BUDGET or 394_000_000
            cu_budget._state.total_consumed = int(budget * 0.95)  # 5% left → EMERGENCY
            cu_budget._state.throttle_mode = "EMERGENCY"
            cu_budget._state.day_key = "2099-01-01"
            
            call_count = [0]
            
            @track_cu("wallet_defi_positions")  # 5000 CU — blocked in EMERGENCY
            def expensive_call():
                call_count[0] += 1
                return "result"
            
            with patch("core.moralis_cu_budget._utc_day_key", return_value="2099-01-01"):
                result = expensive_call()
            self.assertIsNone(result)
            self.assertEqual(call_count[0], 0)
        finally:
            cu_budget._state.throttle_mode = original_mode
            cu_budget._state.total_consumed = original_consumed
            cu_budget._state.day_key = original_day


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Entity Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestMoralisEntity(unittest.TestCase):
    """Test the Moralis Entity API provider."""

    def test_classify_wallet_returns_unknown_on_none(self):
        """Test that classify_wallet returns 'unknown' when entity is None."""
        with patch("data.providers.moralis_entity.get_entity_by_address") as mock_get:
            mock_get.return_value = None
            
            from data.providers.moralis_entity import classify_wallet
            result = classify_wallet("0xabcdef1234567890")
            self.assertEqual(result, "unknown")

    def test_classify_wallet_returns_exchange(self):
        """Test that classify_wallet returns 'exchange' for exchange entities."""
        with patch("data.providers.moralis_entity.get_entity_by_address") as mock_get:
            mock_get.return_value = {
                "entity_id": "coinbase",
                "name": "Coinbase",
                "is_exchange": True,
                "is_fund": False,
                "is_mev": False,
                "risk_flag": False,
                "category": "exchange",
            }
            
            from data.providers.moralis_entity import classify_wallet
            result = classify_wallet("0xabcdef1234567890")
            self.assertEqual(result, "exchange")

    def test_classify_wallet_returns_bad_actor_for_mev(self):
        """Test that classify_wallet returns 'bad_actor' for MEV bots (risk_flag=True)."""
        with patch("data.providers.moralis_entity.get_entity_by_address") as mock_get:
            mock_get.return_value = {
                "entity_id": "mev_bot_1",
                "name": "MEV Bot",
                "is_exchange": False,
                "is_fund": False,
                "is_mev": True,
                "risk_flag": True,
                "category": "mev",
            }
            
            from data.providers.moralis_entity import classify_wallet
            result = classify_wallet("0xabcdef1234567890")
            self.assertEqual(result, "bad_actor")

    def test_classify_wallet_returns_fund(self):
        """Test that classify_wallet returns 'fund' for institutional funds."""
        with patch("data.providers.moralis_entity.get_entity_by_address") as mock_get:
            mock_get.return_value = {
                "entity_id": "wintermute",
                "name": "Wintermute",
                "is_exchange": False,
                "is_fund": True,
                "is_mev": False,
                "risk_flag": False,
                "category": "market_maker",
            }
            
            from data.providers.moralis_entity import classify_wallet
            result = classify_wallet("0xabcdef1234567890")
            self.assertEqual(result, "fund")

    def test_batch_classify_wallets_deduplicates(self):
        """Test that batch_classify_wallets deduplicates addresses."""
        with patch("data.providers.moralis_entity.classify_wallet") as mock_classify:
            mock_classify.return_value = "unknown"
            
            from data.providers.moralis_entity import batch_classify_wallets
            # Pass duplicates
            addresses = ["0xabc", "0xabc", "0xdef"]
            result = batch_classify_wallets(addresses)
            
            # Should only call classify_wallet twice (deduped)
            self.assertEqual(mock_classify.call_count, 2)
            self.assertIn("0xabc", result)
            self.assertIn("0xdef", result)

    def test_is_known_bad_actor_returns_false_for_unknown(self):
        """Test that is_known_bad_actor returns False for unknown wallets."""
        with patch("data.providers.moralis_entity.get_entity_by_address") as mock_get:
            mock_get.return_value = None
            
            from data.providers.moralis_entity import is_known_bad_actor
            result = is_known_bad_actor("0xabcdef1234567890")
            self.assertFalse(result)

    def test_is_known_bad_actor_returns_true_for_risk_flag(self):
        """Test that is_known_bad_actor returns True for risk-flagged entities."""
        with patch("data.providers.moralis_entity.get_entity_by_address") as mock_get:
            mock_get.return_value = {
                "entity_id": "mev_bot",
                "name": "MEV Bot",
                "is_exchange": False,
                "is_fund": False,
                "is_mev": True,
                "risk_flag": True,
                "category": "mev",
            }
            
            from data.providers.moralis_entity import is_known_bad_actor
            result = is_known_bad_actor("0xabcdef1234567890")
            self.assertTrue(result)


# ─────────────────────────────────────────────────────────────────────────────
# Moralis DeFi Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestMoralisDefi(unittest.TestCase):
    """Test the Moralis DeFi API provider."""

    def test_get_token_defi_exposure_empty_wallets(self):
        """Test that get_token_defi_exposure handles empty wallet list."""
        from data.providers.moralis_defi import get_token_defi_exposure
        result = get_token_defi_exposure("0xtoken", "ethereum", [])
        
        self.assertEqual(result["defi_exposure_score"], 0.0)
        self.assertEqual(result["exposed_wallets"], 0)

    def test_get_token_defi_exposure_returns_dict(self):
        """Test that get_token_defi_exposure returns expected structure."""
        with patch("data.providers.moralis_defi.get_wallet_defi_positions") as mock_pos, \
             patch("data.providers.moralis_defi._available", return_value=True):
            mock_pos.return_value = [
                {
                    "protocol_name": "Uniswap V3",
                    "position_type": "liquidity",
                    "usd_value": 10000.0,
                    "tokens": [{"token_address": "0xtoken", "symbol": "TEST"}],
                }
            ]
            
            from data.providers.moralis_defi import get_token_defi_exposure
            result = get_token_defi_exposure(
                "0xtoken", "ethereum",
                ["0xwallet1", "0xwallet2"]
            )
            
            self.assertIn("defi_exposure_score", result)
            self.assertIn("exposed_wallets", result)
            self.assertIn("protocols", result)
            self.assertIn("total_usd_value", result)

    def test_get_wallet_defi_summary_handles_error(self):
        """Test that get_wallet_defi_summary returns None on API error."""
        with patch("data.providers.moralis_defi.get_session") as mock_session:
            mock_session.return_value.get.side_effect = Exception("Connection error")
            
            from data.providers.moralis_defi import get_wallet_defi_summary
            result = get_wallet_defi_summary("0xabcdef1234567890", "ethereum")
            self.assertIsNone(result)

    def test_defi_exposure_score_increases_with_wallets(self):
        """Test that more exposed wallets increases the defi_exposure_score."""
        with patch("data.providers.moralis_defi.get_wallet_defi_positions") as mock_pos:
            mock_pos.return_value = [
                {
                    "protocol_name": "Uniswap V3",
                    "position_type": "liquidity",
                    "usd_value": 5000.0,
                    "tokens": [{"token_address": "0xtoken", "symbol": "TEST"}],
                }
            ]
            
            from data.providers.moralis_defi import get_token_defi_exposure
            
            # 1 wallet
            result_1 = get_token_defi_exposure("0xtoken", "ethereum", ["0xwallet1"])
            # 3 wallets
            result_3 = get_token_defi_exposure("0xtoken", "ethereum", ["0xw1", "0xw2", "0xw3"])
            
            self.assertGreaterEqual(result_3["defi_exposure_score"], result_1["defi_exposure_score"])


# ─────────────────────────────────────────────────────────────────────────────
# Moralis Market Metrics Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestMoralisMarketMetrics(unittest.TestCase):
    """Test the Moralis Market Metrics API provider."""

    def test_get_market_regime_signal_returns_valid_regime(self):
        """Test that get_market_regime_signal returns a valid regime string."""
        with patch("data.providers.moralis_market_metrics.get_global_market_metrics") as mock_global, \
             patch("data.providers.moralis_market_metrics.get_top_coins_by_market_cap") as mock_coins, \
             patch("data.providers.moralis_market_metrics.get_volume_by_chain") as mock_vol:
            
            mock_global.return_value = {
                "btc_dominance_pct": 52.0,
                "total_market_cap_usd": 2.5e12,
                "market_cap_change_24h_pct": 2.0,
            }
            mock_coins.return_value = [
                {"symbol": "BTC", "price_usd": 50000, "price_change_24h_pct": 2.5},
                {"symbol": "ETH", "price_usd": 3000, "price_change_24h_pct": 1.5},
            ]
            mock_vol.return_value = {"ethereum": {"heat_score": 70}}
            
            from data.providers.moralis_market_metrics import get_market_regime_signal
            result = get_market_regime_signal()
            
            valid_regimes = {"BULL", "BEAR", "NEUTRAL", "MILD_BULL", "MILD_BEAR", "BTC_DOMINANCE"}
            self.assertIn("regime", result)
            self.assertIn(result["regime"], valid_regimes)
            self.assertIn("confidence", result)
            self.assertIn("hot_chains", result)

    def test_get_market_regime_signal_handles_none_data(self):
        """Test that get_market_regime_signal handles None API responses gracefully."""
        with patch("data.providers.moralis_market_metrics.get_global_market_metrics") as mock_global, \
             patch("data.providers.moralis_market_metrics.get_top_coins_by_market_cap") as mock_coins, \
             patch("data.providers.moralis_market_metrics.get_volume_by_chain") as mock_vol:
            
            mock_global.return_value = None
            mock_coins.return_value = []
            mock_vol.return_value = {}
            
            from data.providers.moralis_market_metrics import get_market_regime_signal
            result = get_market_regime_signal()
            
            # Should return a default regime, not crash
            self.assertIn("regime", result)
            valid_regimes = {"BULL", "BEAR", "NEUTRAL", "MILD_BULL", "MILD_BEAR", "BTC_DOMINANCE"}
            self.assertIn(result["regime"], valid_regimes)

    def test_get_market_regime_bull_signal(self):
        """Test that positive market data returns BULL or MILD_BULL regime."""
        with patch("data.providers.moralis_market_metrics.get_global_market_metrics") as mock_global, \
             patch("data.providers.moralis_market_metrics.get_top_coins_by_market_cap") as mock_coins, \
             patch("data.providers.moralis_market_metrics.get_volume_by_chain") as mock_vol:
            
            # Strong bull signals
            mock_global.return_value = {
                "btc_dominance_pct": 45.0,  # Low dominance = alt season
                "total_market_cap_usd": 3.0e12,
                "market_cap_change_24h_pct": 8.0,  # Strong positive
            }
            mock_coins.return_value = [
                {"symbol": "BTC", "price_usd": 60000, "price_change_24h_pct": 8.0},
                {"symbol": "ETH", "price_usd": 4000, "price_change_24h_pct": 10.0},
            ]
            mock_vol.return_value = {
                "ethereum": {"heat_score": 90},
                "bsc": {"heat_score": 85},
            }
            
            from data.providers.moralis_market_metrics import get_market_regime_signal
            result = get_market_regime_signal()
            
            self.assertIn(result["regime"], {"BULL", "MILD_BULL"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
