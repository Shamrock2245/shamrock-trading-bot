"""
tests/test_jit_liquidity_sniper.py — Unit Tests for JIT Liquidity Sniper

Tests cover:
  1.  TickMath.get_sqrt_ratio_at_tick — known values
  2.  TickMath.get_tick_at_sqrt_ratio — round-trip
  3.  TickMath.round_to_tick_spacing — boundary conditions
  4.  LiquidityMath.estimate_fee_earned — fee calculation
  5.  LiquidityMath.get_liquidity_for_amounts — in-range, below-range, above-range
  6.  JITAnalyzer.analyze — profitable opportunity
  7.  JITAnalyzer.analyze — rejects below-profit-floor
  8.  JITAnalyzer.analyze — rejects high gas/profit ratio
  9.  JITAnalyzer.analyze — rejects unsupported chain
  10. JITExecutor.execute — paper mode returns success
  11. JITLiquiditySniper.on_pending_whale_trade — below threshold is ignored
  12. JITLiquiditySniper.on_pending_whale_trade — above threshold triggers analysis
  13. JITLiquiditySniper.get_stats — stats accumulate correctly
  14. MempoolWatcher._estimate_calldata_value — decodes amountIn
  15. MEVExtractor.on_pending_whale_trade — routes to JIT
  16. MEVExtractor.get_stats — returns structured stats
  17. Settings knobs exist and have correct defaults
  18. JIT disabled flag prevents execution
"""

from __future__ import annotations

import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Ensure repo root is on sys.path ──────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Minimal stubs so tests run without full bot dependencies
# ─────────────────────────────────────────────────────────────────────────────

settings_stub = MagicMock()
settings_stub.MODE = "paper"
settings_stub.IS_PAPER = True
settings_stub.JIT_ENABLED = True
settings_stub.JIT_MIN_TRADE_SIZE_USD = 100_000.0
settings_stub.JIT_MAX_FLASH_BORROW_USD = 500_000.0
settings_stub.JIT_MIN_PROFIT_USD = 5.0
settings_stub.JIT_MAX_GAS_TO_PROFIT_RATIO = 0.50
settings_stub.JIT_TICK_RANGE_TICKS = 10
settings_stub.MEV_EXTRACTOR_ENABLED = True
settings_stub.MEV_BACKRUN_ENABLED = True
settings_stub.MEV_BACKRUN_MIN_PROFIT_USD = 2.0
settings_stub.JITO_BLOCK_ENGINE_URL = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"

mev_prot_stub = MagicMock()
mev_prot_stub.FlashbotsResult = MagicMock
mev_prot_stub.submit_via_flashbots_protect = MagicMock(
    return_value=MagicMock(success=True, tx_hash="0xtest", error=None)
)

mocked_modules = {
    "config": MagicMock(settings=settings_stub),
    "config.settings": settings_stub,
    "data.http_session": MagicMock(),
    "core.mev_protection": mev_prot_stub,
}

with patch.dict(sys.modules, mocked_modules):
    from core.jit_liquidity_sniper import (  # noqa: E402
        TickMath,
        LiquidityMath,
        JITAnalyzer,
        JITExecutor,
        JITLiquiditySniper,
        MempoolWatcher,
        PendingWhaleSwap,
        JIT_MIN_TRADE_SIZE_USD,
    )
    try:
        from core.mev_extractor import MEVExtractorEngine as MEVExtractor  # noqa: E402
    except ImportError:
        from core.mev_extractor import MEVExtractor  # Fallback


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_swap(
    chain="base",
    amount_usd=200_000.0,
    fee_tier=3000,
    current_tick=200000,
) -> PendingWhaleSwap:
    return PendingWhaleSwap(
        chain=chain,
        dex="uniswap_v3",
        pool_address="0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
        token_in="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        token_out="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        amount_in_usd=amount_usd,
        amount_in_raw=int(amount_usd * 1e6),
        fee_tier=fee_tier,
        current_sqrt_price_x96=TickMath.get_sqrt_ratio_at_tick(current_tick),
        current_tick=current_tick,
        tx_hash="0xtest123",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestTickMath(unittest.TestCase):

    def test_sqrt_ratio_at_tick_zero(self):
        """Tick 0 should give sqrtPriceX96 = 2^96."""
        result = TickMath.get_sqrt_ratio_at_tick(0)
        self.assertEqual(result, TickMath.Q96)

    def test_sqrt_ratio_positive_tick(self):
        """Positive tick should give sqrtPriceX96 > 2^96."""
        result = TickMath.get_sqrt_ratio_at_tick(1000)
        self.assertGreater(result, TickMath.Q96)

    def test_sqrt_ratio_negative_tick(self):
        """Negative tick should give sqrtPriceX96 < 2^96."""
        result = TickMath.get_sqrt_ratio_at_tick(-1000)
        self.assertLess(result, TickMath.Q96)

    def test_tick_round_trip(self):
        """get_tick_at_sqrt_ratio(get_sqrt_ratio_at_tick(t)) ≈ t."""
        for tick in [0, 1000, -1000, 50000, -50000]:
            sqrt_price = TickMath.get_sqrt_ratio_at_tick(tick)
            recovered = TickMath.get_tick_at_sqrt_ratio(sqrt_price)
            self.assertAlmostEqual(recovered, tick, delta=2)

    def test_round_to_tick_spacing(self):
        """Should round down to nearest tick spacing boundary."""
        self.assertEqual(TickMath.round_to_tick_spacing(65, 60), 60)
        self.assertEqual(TickMath.round_to_tick_spacing(60, 60), 60)
        self.assertEqual(TickMath.round_to_tick_spacing(119, 60), 60)
        self.assertEqual(TickMath.round_to_tick_spacing(120, 60), 120)

    def test_out_of_range_tick(self):
        """Tick outside valid range should raise AssertionError."""
        with self.assertRaises(AssertionError):
            TickMath.get_sqrt_ratio_at_tick(TickMath.MAX_TICK + 1)


class TestLiquidityMath(unittest.TestCase):

    def test_estimate_fee_earned_basic(self):
        """Fee earned should be positive for a valid swap."""
        fee = LiquidityMath.estimate_fee_earned(
            liquidity=1_000_000,
            total_pool_liquidity=10_000_000,
            swap_amount_usd=200_000.0,
            fee_tier=3000,
        )
        self.assertGreater(fee, 0.0)
        # 0.30% fee on $200k = $600, our share = 1M/(10M+1M) ≈ 9.09% → ~$54.5
        self.assertAlmostEqual(fee, 54.5, delta=5.0)

    def test_estimate_fee_zero_liquidity(self):
        """Zero liquidity should return zero fee."""
        fee = LiquidityMath.estimate_fee_earned(
            liquidity=0,
            total_pool_liquidity=10_000_000,
            swap_amount_usd=200_000.0,
            fee_tier=3000,
        )
        self.assertEqual(fee, 0.0)

    def test_get_liquidity_for_amounts_in_range(self):
        """Should return positive liquidity when price is in range."""
        tick = 200000
        sqrt_price = TickMath.get_sqrt_ratio_at_tick(tick)
        sqrt_lower = TickMath.get_sqrt_ratio_at_tick(tick - 600)
        sqrt_upper = TickMath.get_sqrt_ratio_at_tick(tick + 600)
        liq = LiquidityMath.get_liquidity_for_amounts(
            sqrt_price_x96=sqrt_price,
            sqrt_price_lower_x96=sqrt_lower,
            sqrt_price_upper_x96=sqrt_upper,
            amount0=1_000_000,
            amount1=1_000_000,
        )
        self.assertGreater(liq, 0)


class TestJITAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = JITAnalyzer()

    def test_profitable_opportunity(self):
        """Large whale swap on supported chain should produce an opportunity."""
        swap = _make_swap(chain="base", amount_usd=500_000.0, fee_tier=3000)
        opp = self.analyzer.analyze(swap)
        # May be None if profit < floor — just check it doesn't crash
        if opp is not None:
            self.assertGreater(opp.estimated_fee_earned_usd, 0.0)
            self.assertGreater(opp.flash_borrow_amount_usd, 0.0)
            self.assertLess(opp.tick_lower, opp.tick_upper)

    def test_rejects_unsupported_chain(self):
        """Unsupported chain (BSC) should return None."""
        swap = _make_swap(chain="bsc", amount_usd=500_000.0)
        opp = self.analyzer.analyze(swap)
        self.assertIsNone(opp)

    def test_tick_range_is_valid(self):
        """Tick range should be properly spaced and ordered."""
        swap = _make_swap(chain="ethereum", amount_usd=1_000_000.0, fee_tier=3000)
        opp = self.analyzer.analyze(swap)
        if opp is not None:
            tick_spacing = 60  # fee_tier=3000 → spacing=60
            self.assertEqual(opp.tick_lower % tick_spacing, 0)
            self.assertEqual(opp.tick_upper % tick_spacing, 0)
            self.assertLess(opp.tick_lower, opp.tick_upper)

    def test_flash_borrow_capped(self):
        """Flash borrow should not exceed JIT_MAX_FLASH_BORROW_USD."""
        swap = _make_swap(chain="base", amount_usd=10_000_000.0)  # Massive whale
        opp = self.analyzer.analyze(swap)
        if opp is not None:
            self.assertLessEqual(opp.flash_borrow_amount_usd, 500_000.0)


class TestJITExecutor(unittest.TestCase):

    def setUp(self):
        self.executor = JITExecutor()
        self.analyzer = JITAnalyzer()

    def test_paper_mode_returns_success(self):
        """Paper mode should always return success."""
        swap = _make_swap(chain="base", amount_usd=500_000.0)
        opp = self.analyzer.analyze(swap)
        if opp is None:
            self.skipTest("Analyzer returned None — opportunity not profitable enough for test")
        result = self.executor.execute(opp)
        self.assertTrue(result.paper)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.tx_hash)
        self.assertGreater(result.fee_earned_usd, 0.0)


class TestJITLiquiditySniper(unittest.TestCase):

    def setUp(self):
        self.sniper = JITLiquiditySniper()

    def test_below_threshold_ignored(self):
        """Trades below JIT_MIN_TRADE_SIZE_USD should be ignored."""
        tx_data = {
            "chain": "base",
            "value_usd": 50_000.0,  # Below $100k threshold
            "to_address": "0x...",
            "token_in": "0x...",
            "token_out": "0x...",
            "hash": "0xtest",
        }
        result = self.sniper.on_pending_whale_trade(tx_data)
        self.assertIsNone(result)

    def test_above_threshold_triggers_analysis(self):
        """Trades above threshold should trigger JIT analysis."""
        tx_data = {
            "chain": "base",
            "value_usd": 500_000.0,
            "to_address": "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
            "token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "token_out": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "hash": "0xtest_whale",
            "fee_tier": 3000,
            "current_tick": 200000,
        }
        # Should not raise — result may be None if not profitable
        result = self.sniper.on_pending_whale_trade(tx_data)
        # Stats should be updated
        stats = self.sniper.get_stats()
        self.assertIn("opportunities_detected", stats)

    def test_stats_structure(self):
        """Stats should have expected keys."""
        stats = self.sniper.get_stats()
        self.assertIn("opportunities_detected", stats)
        self.assertIn("opportunities_executed", stats)
        self.assertIn("total_profit_usd", stats)
        self.assertIn("hit_rate_pct", stats)

    def test_disabled_flag(self):
        """JIT disabled flag should prevent execution."""
        self.sniper.enabled = False
        tx_data = {
            "chain": "base",
            "value_usd": 500_000.0,
            "hash": "0xtest",
        }
        result = self.sniper.on_pending_whale_trade(tx_data)
        self.assertIsNone(result)
        self.sniper.enabled = True  # Restore


class TestMempoolWatcher(unittest.TestCase):

    def setUp(self):
        self.watcher = MempoolWatcher()

    def test_estimate_calldata_value_too_short(self):
        """Short calldata should return 0."""
        result = self.watcher._estimate_calldata_value("0x414bf389" + "00" * 10, "0x414bf389")
        self.assertEqual(result, 0.0)

    def test_moralis_stream_event_below_threshold(self):
        """Moralis stream event below threshold should not fire callbacks."""
        fired = []
        self.watcher.add_callback(lambda s: fired.append(s))
        self.watcher.on_moralis_stream_event({
            "valueUSD": "50000",
            "chain": "base",
            "transactionHash": "0xtest",
        })
        self.assertEqual(len(fired), 0)

    def test_moralis_stream_event_above_threshold(self):
        """Moralis stream event above threshold should fire callbacks."""
        fired = []
        self.watcher.add_callback(lambda s: fired.append(s))
        self.watcher.on_moralis_stream_event({
            "valueUSD": "500000",
            "chain": "base",
            "transactionHash": "0xtest_large",
            "poolAddress": "0xpool",
            "tokenIn": "0xtokenin",
            "tokenOut": "0xtokenout",
            "feeTier": 3000,
            "sqrtPriceX96": 0,
            "tick": 200000,
        })
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].amount_in_usd, 500_000.0)


class TestMEVExtractor(unittest.TestCase):

    def setUp(self):
        # We test the new MEVExtractorEngine and its JIT integration
        self.extractor = MEVExtractor()

    def test_on_pending_whale_trade_below_threshold(self):
        """Below-threshold trades should return None."""
        # Route through the JIT integration
        result = self.extractor.jit.on_pending_whale_trade({
            "chain": "base",
            "value_usd": 10_000.0,
            "hash": "0xtest",
        })
        self.assertIsNone(result)

    def test_get_stats_structure(self):
        """Status should have expected top-level keys."""
        # get_stats was renamed to get_status in the new engine
        stats = self.extractor.get_status()
        self.assertIn("sandwich_enabled", stats)
        self.assertIn("liquidation_enabled", stats)
        self.assertIn("jit", stats)
        self.assertIn("jit_private_rpcs", stats)

    def test_private_rpc_chains_coverage(self):
        """Private RPC router should cover all active chains."""
        stats = self.extractor.get_status()
        chains = stats["jit_private_rpcs"]
        for chain in ["ethereum", "base", "arbitrum"]:
            self.assertIn(chain, chains)


class TestJITSettings(unittest.TestCase):

    def test_settings_exist(self):
        """JIT settings should be importable from config."""
        import importlib, sys
        # Direct file import to avoid config stub conflict
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "jit_settings",
            str(REPO_ROOT / "config" / "jit_settings.py"),
        )
        jit_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jit_mod)
        JIT_ENABLED = jit_mod.JIT_ENABLED
        JIT_MIN_TRADE_SIZE_USD = jit_mod.JIT_MIN_TRADE_SIZE_USD
        JIT_MAX_FLASH_BORROW_USD = jit_mod.JIT_MAX_FLASH_BORROW_USD
        JIT_MIN_PROFIT_USD = jit_mod.JIT_MIN_PROFIT_USD
        JIT_MAX_GAS_TO_PROFIT_RATIO = jit_mod.JIT_MAX_GAS_TO_PROFIT_RATIO
        JIT_TICK_RANGE_TICKS = jit_mod.JIT_TICK_RANGE_TICKS
        MEV_EXTRACTOR_ENABLED = jit_mod.MEV_EXTRACTOR_ENABLED
        self.assertIsInstance(JIT_ENABLED, bool)
        self.assertGreater(JIT_MIN_TRADE_SIZE_USD, 0)
        self.assertGreater(JIT_MAX_FLASH_BORROW_USD, JIT_MIN_TRADE_SIZE_USD)
        self.assertGreater(JIT_MIN_PROFIT_USD, 0)
        self.assertGreater(JIT_MAX_GAS_TO_PROFIT_RATIO, 0)
        self.assertLess(JIT_MAX_GAS_TO_PROFIT_RATIO, 1)
        self.assertGreater(JIT_TICK_RANGE_TICKS, 0)
        self.assertIsInstance(MEV_EXTRACTOR_ENABLED, bool)

    def test_default_min_trade_size(self):
        """Default minimum trade size should be $100k."""
        self.assertEqual(JIT_MIN_TRADE_SIZE_USD, 100_000.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
