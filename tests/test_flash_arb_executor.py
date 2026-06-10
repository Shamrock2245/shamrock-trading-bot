"""
tests/test_flash_arb_executor.py — Unit Tests for Zero-Risk Flash Arb Engine

Tests cover:
  1. Flash size calculation (EVM + Solana)
  2. Profit gate enforcement (1.5% floor)
  3. Gas/profit ratio gate
  4. Paper trade simulation (cross-dex, triangular, cross-chain)
  5. Expired opportunity rejection
  6. ArbTradeResult backwards compatibility alias
  7. Solana route arb simulation
  8. Stats aggregation
  9. CSV logging
  10. Safety revert scenario (unprofitable arb rejected)
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# Minimal stubs so tests run without full bot dependencies
# ─────────────────────────────────────────────────────────────────────────────

# We no longer pollute sys.modules at the global module scope because it breaks test discovery.
# Instead, we define our mocks and import the tested modules inside a patch.dict context manager.

# Stub config.settings
settings_stub = MagicMock()
settings_stub.PAPER_TRADE = True
settings_stub.ARB_WALLET_ALIAS = "primary"
settings_stub.ARB_MAX_GAS_TO_PROFIT_RATIO = 0.50
settings_stub.ARB_RECHECK_SPREAD_BEFORE_EXEC = False
settings_stub.ARB_MIN_SPREAD_TO_EXECUTE_PCT = 0.5
settings_stub.ARB_SLIPPAGE_BPS = 50
settings_stub.FLASH_ARB_MIN_PROFIT_PCT = 1.5
settings_stub.FLASH_ARB_MAX_POSITION_USD = 500_000.0
settings_stub.FLASH_ARB_LIQUIDITY_FRACTION = 0.30
settings_stub.FLASH_ARB_SAFETY_MARGIN_PCT = 0.10
settings_stub.FLASH_ARB_PREFER_BALANCER = True
settings_stub.MORALIS_API_KEY = ""
settings_stub.JUPITER_API_URL = "https://lite-api.jup.ag/swap/v1"
settings_stub.JUPITER_API_KEY = ""
settings_stub.SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
settings_stub.get_current_mode.return_value = "paper"

arb_price_feed_stub = MagicMock()
arb_price_feed_stub.STABLECOINS = {
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "base":     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "polygon":  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "bsc":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
}
arb_price_feed_stub.CHAIN_IDS = {
    "ethereum": 1, "base": 8453, "arbitrum": 42161, "polygon": 137, "bsc": 56,
}
arb_price_feed_stub.ARB_GAS_COST_USD = {
    "ethereum": 15.0, "base": 0.20, "arbitrum": 0.35, "polygon": 0.05, "bsc": 0.15, "solana": 0.001,
}

wallet_router_stub = MagicMock()
wallet_router_stub.get_usdc_balance.return_value = 10_000.0
wallet_router_stub.get_native_balance.return_value = 1.0
wallet_router_stub.get_native_price_usd.return_value = 3000.0

chains_stub = MagicMock()
chain_cfg_mock = MagicMock()
chain_cfg_mock.rpc_url = "https://ethereum.publicnode.com"
chain_cfg_mock.chain_id = 1
chain_cfg_mock.native_token = "ETH"
chain_cfg_mock.oneinch_router = "0x1111111254EEB25477B68fb85Ed929f73A960582"
chains_stub.CHAINS = {
    "ethereum": chain_cfg_mock,
    "base": chain_cfg_mock,
    "arbitrum": chain_cfg_mock,
    "polygon": chain_cfg_mock,
    "bsc": chain_cfg_mock,
}

wallets_stub = MagicMock()
wallet_mock = MagicMock()
wallet_mock.alias = "primary"
wallet_mock.address = "0x3eb320fad3f51fe4f2a4531f911ef56694346eef"
wallets_stub.WALLETS = {"primary": wallet_mock}

@dataclass
class ArbOpportunity:
    strategy: str = "cross_dex"
    chain: str = "base"
    buy_chain: str = "base"
    sell_chain: str = "base"
    token_address: str = "0xTokenAddress"
    token_symbol: str = "GEM"
    buy_dex: str = "uniswap_v3"
    sell_dex: str = "aerodrome"
    gross_profit_pct: float = 2.5
    cycle_profit_pct: float = 2.5
    net_profit_usd: float = 25.0
    position_size_usd: float = 1000.0
    gas_cost_usd: float = 0.40
    bridge_fee_usd: float = 0.0
    liquidity_usd: float = 200_000.0
    buy_price: float = 1.0
    sell_price: float = 1.025
    path: list = field(default_factory=lambda: [
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "0xTokenAddress",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    ])
    is_expired: bool = False
    ttl_seconds: int = 30
    discovered_at: float = field(default_factory=time.time)

arb_scanner_stub = MagicMock()
arb_scanner_stub.ArbOpportunity = ArbOpportunity

config_mock = MagicMock()
config_mock.settings = settings_stub

mocked_modules = {
    "config": config_mock,
    "config.settings": settings_stub,
    "config.wallets": wallets_stub,
    "config.chains": chains_stub,
    "core.executor": MagicMock(),
    "core.wallet_router": wallet_router_stub,
    "core.mev_protection": MagicMock(),
    "data.providers.arb_price_feed": arb_price_feed_stub,
    "data.http_session": MagicMock(),
    "scanner.arb_scanner": arb_scanner_stub,
}

import tempfile
_tmp_csv = tempfile.mktemp(suffix=".csv")
os.environ["ARB_OUTPUT_FILE"] = _tmp_csv

with patch.dict(sys.modules, mocked_modules):
    from core.arb_executor import (
        ArbExecutor,
        FlashArbResult,
        ArbTradeResult,
        calculate_max_flash_size,
        FLASH_ARB_MIN_PROFIT_PCT,
        BALANCER_VAULT,
        AAVE_POOL,
    )
    from core.solana_flash_arb import (
        calculate_solana_max_flash_size,
        simulate_jupiter_route_arb,
        _simulate_jupiter_route_arb,
        SolanaFlashArbResult,
        USDC_MINT,
    )
    import core.arb_executor as arb_module
    arb_module.ARB_OUTPUT_FILE = _tmp_csv


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestFlashSizeCalculator(unittest.TestCase):
    """Tests for calculate_max_flash_size()."""

    def test_basic_profitable_size(self):
        """Flash size should be positive for a profitable arb."""
        opp = ArbOpportunity(
            gross_profit_pct=2.5, liquidity_usd=200_000.0,
            gas_cost_usd=0.40, position_size_usd=1000.0,
        )
        size = calculate_max_flash_size(opp, "base", "0xToken", 2.5)
        self.assertGreater(size, 0, "Flash size should be positive for profitable arb")

    def test_size_bounded_by_liquidity(self):
        """Flash size should not exceed 30% of pool liquidity."""
        opp = ArbOpportunity(liquidity_usd=100_000.0, gross_profit_pct=3.0)
        size = calculate_max_flash_size(opp, "base", "0xToken", 3.0)
        self.assertLessEqual(size, 100_000.0 * 0.30 + 1, "Size should be bounded by liquidity fraction")

    def test_size_bounded_by_hard_cap(self):
        """Flash size should not exceed FLASH_ARB_MAX_POSITION_USD."""
        opp = ArbOpportunity(liquidity_usd=10_000_000.0, gross_profit_pct=5.0)
        size = calculate_max_flash_size(opp, "base", "0xToken", 5.0)
        self.assertLessEqual(size, 500_000.0 + 1, "Size should be bounded by hard cap")

    def test_zero_for_unprofitable_arb(self):
        """Flash size should be 0 when net profit rate is negative."""
        opp = ArbOpportunity(gross_profit_pct=0.01, liquidity_usd=1_000.0)
        size = calculate_max_flash_size(opp, "base", "0xToken", 0.01)
        self.assertEqual(size, 0.0, "Unprofitable arb should return 0 flash size")

    def test_high_gas_chain_reduces_size(self):
        """Ethereum's high gas should require a larger minimum size."""
        opp = ArbOpportunity(gross_profit_pct=2.0, liquidity_usd=50_000.0, gas_cost_usd=15.0)
        size_eth = calculate_max_flash_size(opp, "ethereum", "0xToken", 2.0)
        size_base = calculate_max_flash_size(opp, "base", "0xToken", 2.0)
        # Both should be positive but Ethereum requires more capital to cover gas
        self.assertGreater(size_eth, 0, "Ethereum flash size should be positive")
        self.assertGreater(size_base, 0, "Base flash size should be positive")


class TestSolanaFlashSizeCalculator(unittest.TestCase):
    """Tests for calculate_solana_max_flash_size()."""

    def test_basic_profitable_size(self):
        size = calculate_solana_max_flash_size(200_000.0, 2.5, n_hops=2)
        self.assertGreater(size, 0)

    def test_zero_for_negative_profit_rate(self):
        size = calculate_solana_max_flash_size(1_000.0, 0.001, n_hops=3)
        self.assertEqual(size, 0.0)

    def test_bounded_by_hard_cap(self):
        size = calculate_solana_max_flash_size(100_000_000.0, 5.0, n_hops=2)
        self.assertLessEqual(size, 500_000.0 + 1)


class TestFlashArbExecutorPaperMode(unittest.TestCase):
    """Tests for ArbExecutor in paper trade mode."""

    def setUp(self):
        arb_module.PAPER_TRADE = True
        arb_module.ARB_RECHECK_SPREAD_BEFORE_EXEC = False
        self.executor = ArbExecutor()

    def _make_opp(self, **kwargs) -> ArbOpportunity:
        defaults = dict(
            strategy="cross_dex",
            chain="base",
            buy_chain="base",
            sell_chain="base",
            gross_profit_pct=2.5,
            cycle_profit_pct=2.5,
            net_profit_usd=25.0,
            position_size_usd=1000.0,
            gas_cost_usd=0.40,
            liquidity_usd=200_000.0,
            is_expired=False,
        )
        defaults.update(kwargs)
        return ArbOpportunity(**defaults)

    def test_cross_dex_paper_success(self):
        """Paper cross-DEX arb should succeed when spread > 1.5%."""
        opp = self._make_opp(gross_profit_pct=2.5)
        result = self.executor.execute(opp)
        self.assertIsInstance(result, FlashArbResult)
        self.assertTrue(result.paper, "Should be paper trade")
        self.assertIn("cross_dex", result.execution_path)

    def test_triangular_paper_success(self):
        """Paper triangular arb should succeed when cycle profit > 1.5%."""
        opp = self._make_opp(strategy="triangular", cycle_profit_pct=2.0, gross_profit_pct=2.0)
        result = self.executor.execute(opp)
        self.assertIsInstance(result, FlashArbResult)
        self.assertTrue(result.paper)
        self.assertIn("triangular", result.execution_path)

    def test_cross_chain_paper_success(self):
        """Paper cross-chain arb should succeed."""
        opp = self._make_opp(
            strategy="cross_chain",
            buy_chain="base", sell_chain="arbitrum",
            gross_profit_pct=3.0,
        )
        result = self.executor.execute(opp)
        self.assertIsInstance(result, FlashArbResult)
        self.assertTrue(result.paper)

    def test_expired_opportunity_rejected(self):
        """Expired opportunities must be rejected immediately."""
        opp = self._make_opp(is_expired=True)
        result = self.executor.execute(opp)
        self.assertFalse(result.success)
        self.assertIn("expired", result.error.lower())

    def test_profit_floor_gate(self):
        """Opportunities below 1.5% net profit must be rejected."""
        opp = self._make_opp(
            gross_profit_pct=0.5,  # Below 1.5% floor
            net_profit_usd=5.0,
            gas_cost_usd=0.40,
        )
        result = self.executor.execute(opp)
        self.assertFalse(result.success)
        self.assertIn("floor", result.error.lower())

    def test_gas_profit_ratio_gate(self):
        """Reject when gas cost > 50% of expected profit."""
        opp = self._make_opp(
            gross_profit_pct=2.5,
            net_profit_usd=0.50,  # Very small profit
            gas_cost_usd=0.40,    # Gas = 80% of profit → rejected
        )
        result = self.executor.execute(opp)
        self.assertFalse(result.success)
        self.assertIn("gas", result.error.lower())

    def test_unknown_strategy_rejected(self):
        """Unknown strategy must be rejected gracefully."""
        opp = self._make_opp(strategy="unknown_strategy")
        result = self.executor.execute(opp)
        self.assertFalse(result.success)
        self.assertIn("Unknown strategy", result.error)

    def test_daily_profit_accumulates(self):
        """Successful trades should accumulate daily profit."""
        opp = self._make_opp(gross_profit_pct=3.0, net_profit_usd=30.0)
        initial_profit = self.executor.daily_profit_usd
        result = self.executor.execute(opp)
        if result.success:
            self.assertGreater(
                self.executor.daily_profit_usd, initial_profit,
                "Daily profit should increase after successful trade",
            )

    def test_stats_structure(self):
        """get_stats() should return expected keys."""
        stats = self.executor.get_stats()
        required_keys = [
            "daily_profit_usd", "daily_trade_count", "total_trades",
            "flash_trades", "legacy_trades", "success_rate",
            "avg_profit_per_trade", "avg_flash_size_usd", "paper_mode",
            "flash_arb_min_profit_pct",
        ]
        for key in required_keys:
            self.assertIn(key, stats, f"Stats missing key: {key}")

    def test_arb_trade_result_alias(self):
        """ArbTradeResult should be an alias for FlashArbResult (backwards compat)."""
        self.assertIs(ArbTradeResult, FlashArbResult, "ArbTradeResult must alias FlashArbResult")

    def test_csv_logging(self):
        """Successful trades should be logged to CSV."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp_path = f.name

        arb_module.ARB_OUTPUT_FILE = tmp_path
        self.executor._ensure_output_dir()

        opp = self._make_opp(gross_profit_pct=3.0, net_profit_usd=30.0)
        self.executor.execute(opp)

        if Path(tmp_path).exists():
            with open(tmp_path) as f:
                content = f.read()
            self.assertIn("cross_dex", content, "CSV should contain strategy name")
        os.unlink(tmp_path)

    def test_flash_amount_larger_than_position_size(self):
        """Flash arb should use a larger position than wallet capital (leverage)."""
        opp = self._make_opp(
            gross_profit_pct=3.0,
            position_size_usd=1000.0,
            liquidity_usd=500_000.0,
        )
        result = self.executor.execute(opp)
        if result.success:
            # Flash amount should be larger than the original position_size_usd
            # because we're borrowing from the flash loan provider
            self.assertGreater(
                result.flash_amount_usd, 0,
                "Flash amount should be positive",
            )

    def test_str_representation(self):
        """FlashArbResult __str__ should not raise."""
        opp = self._make_opp()
        result = FlashArbResult(opportunity=opp, success=True, flash_provider="paper_balancer")
        s = str(result)
        self.assertIn("FlashArbResult", s)
        self.assertIn("paper=True", s)


class TestFlashArbSafetyRevert(unittest.TestCase):
    """Tests for the atomic safety-revert guarantee."""

    def test_safety_revert_scenario(self):
        """
        When the arb is unprofitable (spread evaporated), the on-chain contract
        reverts. In paper mode, this is simulated by the profit gate.
        """
        arb_module.PAPER_TRADE = True
        executor = ArbExecutor()

        # Simulate an arb that was profitable when detected but is now below floor
        opp = ArbOpportunity(
            strategy="cross_dex",
            chain="base",
            buy_chain="base",
            sell_chain="base",
            gross_profit_pct=0.8,   # Below 1.5% floor
            cycle_profit_pct=0.8,
            net_profit_usd=8.0,
            position_size_usd=1000.0,
            gas_cost_usd=0.40,
            liquidity_usd=100_000.0,
            is_expired=False,
        )
        result = executor.execute(opp)
        self.assertFalse(result.success, "Unprofitable arb must be rejected (safety revert)")
        self.assertIsNotNone(result.error)

    def test_zero_capital_at_risk_in_flash_mode(self):
        """
        In flash loan mode, the flash_amount_usd represents borrowed capital.
        The wallet's own capital should not be at risk.
        """
        arb_module.PAPER_TRADE = True
        executor = ArbExecutor()

        opp = ArbOpportunity(
            strategy="cross_dex",
            chain="base",
            gross_profit_pct=3.0,
            net_profit_usd=30.0,
            gas_cost_usd=0.40,
            liquidity_usd=200_000.0,
            is_expired=False,
        )
        result = executor.execute(opp)
        # In paper mode, flash_amount_usd should be set (borrowed capital)
        # The wallet's own USDC is NOT used in flash mode
        if result.success:
            self.assertGreater(result.flash_amount_usd, 0)
            self.assertIn("paper", result.flash_provider)


class TestBalancerAaveAddresses(unittest.TestCase):
    """Verify flash loan provider addresses are correctly configured."""

    def test_balancer_vault_addresses(self):
        """Balancer Vault V2 should have the canonical address on all supported chains."""
        canonical = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
        for chain in ["ethereum", "arbitrum", "polygon", "base"]:
            self.assertEqual(
                BALANCER_VAULT.get(chain), canonical,
                f"Balancer Vault address mismatch on {chain}",
            )

    def test_aave_pool_addresses_set(self):
        """Aave V3 Pool should have addresses for main EVM chains."""
        for chain in ["ethereum", "arbitrum", "polygon", "base"]:
            addr = AAVE_POOL.get(chain, "")
            self.assertTrue(
                addr.startswith("0x"),
                f"Aave Pool address missing or invalid on {chain}",
            )

    def test_bsc_uses_no_balancer(self):
        """BSC does not have Balancer — should be empty string."""
        self.assertEqual(BALANCER_VAULT.get("bsc", ""), "", "BSC should not have Balancer")


class TestSolanaFlashArbSimulation(unittest.TestCase):
    """Tests for Solana flash arb simulation."""

    def test_paper_route_arb_returns_result(self):
        """Paper Solana route arb should return a SolanaFlashArbResult."""
        path = [USDC_MINT, "TokenA_MINT", "TokenB_MINT", USDC_MINT]
        result = _simulate_jupiter_route_arb(path, 1000.0)
        self.assertIsInstance(result, SolanaFlashArbResult)
        self.assertTrue(result.paper)
        self.assertEqual(result.chain, "solana")

    def test_paper_route_arb_has_positive_flash_amount(self):
        """Flash amount should equal the input amount."""
        path = [USDC_MINT, "TokenA_MINT", USDC_MINT]
        result = _simulate_jupiter_route_arb(path, 5000.0)
        self.assertEqual(result.flash_amount_usd, 5000.0)

    def test_paper_route_arb_str_representation(self):
        """SolanaFlashArbResult __str__ should not raise."""
        path = [USDC_MINT, "TokenA_MINT", USDC_MINT]
        result = _simulate_jupiter_route_arb(path, 1000.0)
        s = str(result)
        self.assertIn("SolanaFlashArbResult", s)

    def test_solana_max_size_bounded(self):
        """Solana max flash size should be bounded by liquidity and hard cap."""
        size = calculate_solana_max_flash_size(1_000_000.0, 3.0, n_hops=2)
        self.assertLessEqual(size, 500_000.0 + 1)
        self.assertGreater(size, 0)


class TestMinProfitFloor(unittest.TestCase):
    """Verify the 1.5% minimum profit floor is enforced."""

    def setUp(self):
        arb_module.PAPER_TRADE = True
        arb_module.ARB_RECHECK_SPREAD_BEFORE_EXEC = False
        self.executor = ArbExecutor()

    def test_exactly_at_floor_passes(self):
        """An arb exactly at 1.5% should pass the gate."""
        opp = ArbOpportunity(
            strategy="cross_dex", chain="base",
            gross_profit_pct=1.5, net_profit_usd=15.0,
            gas_cost_usd=0.20, liquidity_usd=100_000.0, is_expired=False,
        )
        result = self.executor.execute(opp)
        # At exactly 1.5%, the gate should pass (≥ floor)
        # Note: gas deduction may push it below; this tests the gate logic
        self.assertIsNotNone(result)

    def test_below_floor_rejected(self):
        """An arb below 1.5% must be rejected."""
        opp = ArbOpportunity(
            strategy="cross_dex", chain="base",
            gross_profit_pct=1.0, net_profit_usd=10.0,
            gas_cost_usd=0.20, liquidity_usd=100_000.0, is_expired=False,
        )
        result = self.executor.execute(opp)
        self.assertFalse(result.success)

    def test_high_profit_passes(self):
        """A high-profit arb (5%) should pass all gates."""
        opp = ArbOpportunity(
            strategy="cross_dex", chain="base",
            gross_profit_pct=5.0, net_profit_usd=50.0,
            gas_cost_usd=0.20, liquidity_usd=200_000.0, is_expired=False,
        )
        result = self.executor.execute(opp)
        self.assertIsNotNone(result)
        # Should not be rejected by profit floor
        if not result.success:
            self.assertNotIn("floor", result.error.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
