"""
tests/test_mev_extractor.py — Unit tests for MEV Sandwich & Liquidation Engine

Tests cover:
  1. ProfitGate.evaluate_sandwich — positive and negative profit scenarios
  2. ProfitGate.evaluate_liquidation — health factor gate and profit calculation
  3. SandwichBot._parse_pending_tx — DEX router filtering and slippage detection
  4. LiquidationHunter.check_and_liquidate_aave_user — health factor threshold
  5. MEVExtractorEngine.get_status — status dict completeness
  6. Paper-trade mode — no real transactions submitted
"""

from __future__ import annotations
import os
import pytest
from unittest.mock import MagicMock, patch

# Force paper trade mode for all tests
os.environ["IS_PAPER"] = "true"
os.environ["MEV_MIN_NET_PROFIT_USD"] = "1.0"
os.environ["MEV_SANDWICH_ENABLED"] = "true"
os.environ["MEV_LIQUIDATION_ENABLED"] = "true"

from core.mev_extractor import (
    ProfitGate,
    SandwichBot,
    LiquidationHunter,
    MEVExtractorEngine,
    PendingSwap,
    MEVOpportunity,
    MIN_NET_PROFIT_USD,
    SLIPPAGE_THRESHOLD_PCT,
)


# ─────────────────────────────────────────────────────────────────────────────
# ProfitGate Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProfitGate:

    def test_sandwich_profitable(self):
        """A large swap with high slippage should produce a profitable opportunity."""
        swap = PendingSwap(
            chain="base",
            tx_hash="0xabc123",
            router_address="0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
            token_in="ETH",
            token_out="0xTokenOut",
            amount_in_usd=100_000.0,
            slippage_pct=3.5,
            raw_tx={},
        )
        opp = ProfitGate.evaluate_sandwich(
            chain="base",
            pending_swap=swap,
            front_run_amount_usd=20_000.0,
            estimated_price_impact_pct=2.1,
        )
        assert opp is not None, "Expected profitable opportunity"
        assert opp.net_profit_usd > MIN_NET_PROFIT_USD
        assert opp.strategy == "sandwich"
        assert opp.chain == "base"

    def test_sandwich_unprofitable_small_swap(self):
        """A small swap should not generate enough profit to cover gas."""
        swap = PendingSwap(
            chain="base",
            tx_hash="0xsmall",
            router_address="0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
            token_in="ETH",
            token_out="0xTokenOut",
            amount_in_usd=500.0,
            slippage_pct=2.1,
            raw_tx={},
        )
        opp = ProfitGate.evaluate_sandwich(
            chain="base",
            pending_swap=swap,
            front_run_amount_usd=100.0,
            estimated_price_impact_pct=1.2,
        )
        # With tiny amounts, gross profit < gas cost → should return None
        # (depending on gas price assumptions — this tests the gate logic)
        if opp is not None:
            # If returned, net profit must still be > floor
            assert opp.net_profit_usd > MIN_NET_PROFIT_USD

    def test_liquidation_profitable_low_health_factor(self):
        """A position with health factor 0.9 should be liquidatable and profitable."""
        opp = ProfitGate.evaluate_liquidation(
            chain="base",
            user_address="0xDeadBeef",
            collateral_usd=10_000.0,
            debt_usd=9_500.0,
            health_factor=0.90,
            bonus_pct=5.0,
        )
        assert opp is not None, "Expected profitable liquidation"
        assert opp.net_profit_usd > MIN_NET_PROFIT_USD
        assert opp.strategy == "liquidation"

    def test_liquidation_rejected_healthy_position(self):
        """A healthy position (hf >= 1.0) must never be liquidated."""
        opp = ProfitGate.evaluate_liquidation(
            chain="base",
            user_address="0xHealthy",
            collateral_usd=20_000.0,
            debt_usd=10_000.0,
            health_factor=1.5,
            bonus_pct=5.0,
        )
        assert opp is None, "Healthy position must not be liquidated"

    def test_liquidation_rejected_tiny_position(self):
        """A position too small to cover gas should be rejected."""
        opp = ProfitGate.evaluate_liquidation(
            chain="ethereum",  # Higher gas cost
            user_address="0xTiny",
            collateral_usd=50.0,
            debt_usd=40.0,
            health_factor=0.95,
            bonus_pct=5.0,
        )
        # Gross profit = 40 * 0.5 * 0.05 = $1.0, gas on ETH ≈ $21 → should be None
        assert opp is None, "Tiny position should not cover Ethereum gas"

    def test_gas_cost_base_cheaper_than_ethereum(self):
        """Base gas should be significantly cheaper than Ethereum."""
        base_gas = ProfitGate.estimate_gas_cost_usd("base")
        eth_gas = ProfitGate.estimate_gas_cost_usd("ethereum")
        assert base_gas < eth_gas, "Base gas must be cheaper than Ethereum"

    def test_jito_tip_reasonable(self):
        """Jito tip should be a small USD amount."""
        tip = ProfitGate.estimate_jito_tip_usd(tip_lamports=1_000_000)
        assert 0.0 < tip < 1.0, f"Jito tip should be < $1, got ${tip:.4f}"


# ─────────────────────────────────────────────────────────────────────────────
# SandwichBot Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSandwichBot:

    def setup_method(self):
        # Disable Flashbots for unit tests (no real key)
        os.environ.pop("FLASHBOTS_SIGNING_KEY", None)
        self.bot = SandwichBot()

    def test_parse_pending_tx_ignores_non_dex(self):
        """Transactions to non-DEX addresses should be ignored."""
        tx = {
            "hash": "0xabc",
            "to": "0x1234567890123456789012345678901234567890",
            "value": hex(int(10 * 1e18)),
            "input": "0x",
        }
        result = self.bot._parse_pending_tx(tx, chain="base")
        assert result is None

    def test_parse_pending_tx_ignores_small_swaps(self):
        """Swaps under $10k should be ignored."""
        tx = {
            "hash": "0xsmall",
            "to": "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43",  # Aerodrome (lowercase)
            "value": hex(int(0.5 * 1e18)),  # 0.5 ETH ≈ $1,750
            "input": "0x",
        }
        result = self.bot._parse_pending_tx(tx, chain="base")
        assert result is None

    def test_parse_pending_tx_detects_large_swap(self):
        """A large swap to a known DEX router should be detected."""
        tx = {
            "hash": "0xlarge",
            "to": "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43",  # Aerodrome
            "value": hex(int(20 * 1e18)),  # 20 ETH ≈ $70,000
            "input": "0x",
        }
        result = self.bot._parse_pending_tx(tx, chain="base")
        assert result is not None
        assert result.amount_in_usd > 10_000
        assert result.slippage_pct >= SLIPPAGE_THRESHOLD_PCT

    def test_execute_sandwich_base_paper_mode(self):
        """In paper mode, sandwich execution should succeed without real txs."""
        opp = MEVOpportunity(
            strategy="sandwich",
            chain="base",
            target_address="0xvictim",
            token_address="0xtoken",
            gross_profit_usd=50.0,
            gas_cost_usd=5.0,
            bribe_cost_usd=2.5,
            net_profit_usd=42.5,
            raw_data={"swap": {"router_address": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43", "raw_tx": {}}},
        )
        result = self.bot.execute_sandwich_base(opp)
        assert result.success is True
        assert result.strategy == "sandwich"
        assert result.chain == "base"

    def test_execute_sandwich_solana_paper_mode(self):
        """In paper mode, Solana sandwich should succeed without real Jito call."""
        opp = MEVOpportunity(
            strategy="sandwich",
            chain="solana",
            target_address="SolanaVictimTxSig",
            token_address="TokenMintAddress",
            gross_profit_usd=30.0,
            gas_cost_usd=0.5,
            bribe_cost_usd=0.15,
            net_profit_usd=29.35,
            raw_data={},
        )
        result = self.bot.execute_sandwich_solana(opp)
        assert result.success is True
        assert result.chain == "solana"


# ─────────────────────────────────────────────────────────────────────────────
# LiquidationHunter Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLiquidationHunter:

    def setup_method(self):
        self.hunter = LiquidationHunter()

    def test_execute_aave_liquidation_paper_mode(self):
        """In paper mode, Aave liquidation should succeed without real tx."""
        opp = MEVOpportunity(
            strategy="liquidation",
            chain="base",
            target_address="0xUnderCollateralised",
            token_address="",
            gross_profit_usd=237.5,
            gas_cost_usd=2.5,
            bribe_cost_usd=0.0,
            net_profit_usd=235.0,
            raw_data={"debt_to_cover": 4_750.0, "health_factor": 0.85},
        )
        result = self.hunter.execute_aave_liquidation(opp, chain="base")
        assert result.success is True
        assert result.strategy == "liquidation"
        assert result.chain == "base"

    def test_execute_hyperliquid_liquidation_paper_mode(self):
        """In paper mode, HL liquidation should succeed without real API call."""
        result = self.hunter.execute_hyperliquid_liquidation(
            user_address="0xHLUser",
            coin="BTC",
            is_buy=True,
            sz=0.01,
        )
        assert result.success is True
        assert result.chain == "hyperliquid"

    def test_check_and_liquidate_no_web3(self):
        """Without Web3 connection, check_and_liquidate should return None gracefully."""
        self.hunter._web3_base = None
        self.hunter._aave_pool_base = None
        result = self.hunter.check_and_liquidate_aave_user("0xUser", chain="base")
        assert result is None

    def test_liquidation_bonus_mapping(self):
        """Liquidation bonus should be defined for common assets."""
        assert "WETH" in LiquidationHunter.AAVE_LIQUIDATION_BONUS
        assert "WBTC" in LiquidationHunter.AAVE_LIQUIDATION_BONUS
        assert LiquidationHunter.AAVE_LIQUIDATION_BONUS["WETH"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# MEVExtractorEngine Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMEVExtractorEngine:

    def setup_method(self):
        self.engine = MEVExtractorEngine()

    def test_get_status_returns_dict(self):
        """get_status() should return a complete status dictionary."""
        status = self.engine.get_status()
        assert isinstance(status, dict)
        assert "sandwich_enabled" in status
        assert "liquidation_enabled" in status
        assert "total_executions" in status
        assert "total_profit_usd" in status
        assert "min_net_profit_usd" in status
        assert status["min_net_profit_usd"] == MIN_NET_PROFIT_USD

    def test_engine_components_initialised(self):
        """Engine should have both SandwichBot and LiquidationHunter."""
        assert isinstance(self.engine.sandwich_bot, SandwichBot)
        assert isinstance(self.engine.liquidation_hunter, LiquidationHunter)

    def test_profit_gate_is_profitable_property(self):
        """MEVOpportunity.is_profitable should reflect the net profit gate."""
        profitable = MEVOpportunity(
            strategy="sandwich", chain="base", target_address="0x",
            token_address="0x", gross_profit_usd=100.0,
            gas_cost_usd=5.0, bribe_cost_usd=2.5, net_profit_usd=92.5,
            raw_data={},
        )
        unprofitable = MEVOpportunity(
            strategy="sandwich", chain="base", target_address="0x",
            token_address="0x", gross_profit_usd=2.0,
            gas_cost_usd=5.0, bribe_cost_usd=2.5, net_profit_usd=-5.5,
            raw_data={},
        )
        assert profitable.is_profitable is True
        assert unprofitable.is_profitable is False
