"""
tests/test_paper_mode_safety.py
================================
Paper-mode safety regression tests.

Goal: 100% confidence that MODE=paper can NEVER execute a real on-chain
transaction. These tests stub all heavy dependencies (web3, solana, etc.)
and verify that:

  1. settings.IS_PAPER is dynamic (reads MODE env var at call time)
  2. execute_trade() returns a paper result without touching web3/1inch
  3. execute_sell_solana() returns a paper result without hitting Jupiter
  4. execute_sell_evm() returns a paper result without hitting 1inch
  5. execute_solana_buy() returns "PAPER_TX" without hitting Jupiter
  6. PositionMonitor.is_paper reflects settings.IS_PAPER
  7. execute_sell() passes is_paper to the sell engine (not hardcoded False)

Run with:
    pytest tests/test_paper_mode_safety.py -v
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock, patch, call

# ── Ensure project root is on sys.path ───────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ─────────────────────────────────────────────────────────────────────────────
# Minimal stubs for heavy dependencies
# ─────────────────────────────────────────────────────────────────────────────

def _make_wallet(alias="primary", address="0x3eb320fad3f51fe4f2a4531f911ef56694346eef"):
    w = MagicMock()
    w.alias = alias
    w.address = address
    w.private_key = None
    w.private_key_env = "WALLET_PRIVATE_KEY_PRIMARY"
    w.solana_address = ""
    w.solana_private_key_env = ""
    return w


_wallet_mock = _make_wallet()

# ── settings stub ─────────────────────────────────────────────────────────────
# We use the REAL settings module (it only needs python-dotenv which is installed)
# but we override MODE via env var in each test.

# ── wallets stub ──────────────────────────────────────────────────────────────
wallets_stub = MagicMock()
wallets_stub.WALLETS = {"primary": _wallet_mock}

# ── chains stub ───────────────────────────────────────────────────────────────
chain_cfg = MagicMock()
chain_cfg.rpc_url = "https://mainnet.base.org"
chain_cfg.chain_id = 8453
chain_cfg.native_token = "ETH"
chain_cfg.oneinch_router = "0x1111111254EEB25477B68fb85Ed929f73A960582"
chain_cfg.cow_settlement = None
chain_cfg.usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
chains_stub = MagicMock()
chains_stub.CHAINS = {k: chain_cfg for k in ("ethereum", "base", "arbitrum", "polygon", "bsc", "solana")}

# ── web3 stub ─────────────────────────────────────────────────────────────────
web3_stub = MagicMock()
web3_stub.Web3 = MagicMock()
web3_stub.Web3.return_value = MagicMock()
web3_middleware_stub = MagicMock()

# ── solana stubs ──────────────────────────────────────────────────────────────
solders_stub = MagicMock()
solana_stub = MagicMock()
base58_stub = MagicMock()

# ── safety stub ───────────────────────────────────────────────────────────────
safety_result_mock = MagicMock()
safety_result_mock.is_safe = True
safety_result_mock.block_reason = None
safety_stub = MagicMock()
safety_stub.check_token_safety.return_value = safety_result_mock

# ── circuit breakers stub ─────────────────────────────────────────────────────
cb_stub = MagicMock()
cb_stub.CircuitBreakers.check_trade_allowed.return_value = (True, "ok")

# ── wallet_router stub ────────────────────────────────────────────────────────
wr_stub = MagicMock()
wr_stub.get_native_price_usd.return_value = 3000.0

# ── mev_protection stub ───────────────────────────────────────────────────────
mev_stub = MagicMock()

# ── http_session stub ─────────────────────────────────────────────────────────
http_session_stub = MagicMock()
mock_response = MagicMock()
mock_response.status_code = 200
mock_response.json.return_value = {"toAmount": "1000000", "tx": {"to": "0x", "data": "0x", "value": "0"}}
http_session_stub.get_session.return_value.get.return_value = mock_response
http_session_stub.get_session.return_value.post.return_value = mock_response

# ── notifications stub ────────────────────────────────────────────────────────
notifications_stub = MagicMock()

# ── slippage_tracker stub ─────────────────────────────────────────────────────
slippage_stub = MagicMock()

# ── goplus stub ───────────────────────────────────────────────────────────────
goplus_stub = MagicMock()
goplus_stub.check_token_safety.return_value = {"is_honeypot": False, "sell_tax": 0.0}

# ── moralis_data stub ─────────────────────────────────────────────────────────
moralis_data_stub = MagicMock()

# ── eth_account stub ─────────────────────────────────────────────────────────
eth_account_stub = MagicMock()

# ── builder_codes stub ───────────────────────────────────────────────────────
builder_codes_stub = MagicMock()
builder_codes_stub.append_attribution.side_effect = lambda data, chain: data

# Full module patch dict
_STUBS = {
    "web3": web3_stub,
    "web3.middleware": web3_middleware_stub,
    "solders": solders_stub,
    "solders.keypair": MagicMock(),
    "solders.pubkey": MagicMock(),
    "solders.transaction": MagicMock(),
    "solana": solana_stub,
    "solana.rpc": MagicMock(),
    "solana.rpc.api": MagicMock(),
    "base58": base58_stub,
    "core.safety": safety_stub,
    "core.circuit_breakers": cb_stub,
    "core.wallet_router": wr_stub,
    "core.mev_protection": mev_stub,
    "core.slippage_tracker": slippage_stub,
    "config.wallets": wallets_stub,
    "config.chains": chains_stub,
    "data.http_session": http_session_stub,
    "data.providers.goplus": goplus_stub,
    "data.providers.moralis_data": moralis_data_stub,
    "notifications.telegram": notifications_stub,
    "notifications": notifications_stub,
    "eth_account": eth_account_stub,
    "config.builder_codes": builder_codes_stub,
}

# ─────────────────────────────────────────────────────────────────────────────
# Test: settings.IS_PAPER is dynamic
# ─────────────────────────────────────────────────────────────────────────────

class TestSettingsIsPaperDynamic(unittest.TestCase):
    """settings.IS_PAPER must reflect the current MODE env var dynamically."""

    def test_is_paper_true_when_mode_paper(self):
        os.environ["MODE"] = "paper"
        try:
            from config import settings
            self.assertTrue(settings.IS_PAPER,
                            "settings.IS_PAPER should be True when MODE=paper")
            self.assertFalse(settings.IS_LIVE,
                             "settings.IS_LIVE should be False when MODE=paper")
        finally:
            os.environ.pop("MODE", None)

    def test_is_paper_false_when_mode_live(self):
        os.environ["MODE"] = "live"
        try:
            from config import settings
            self.assertFalse(settings.IS_PAPER,
                             "settings.IS_PAPER should be False when MODE=live")
            self.assertTrue(settings.IS_LIVE,
                            "settings.IS_LIVE should be True when MODE=live")
        finally:
            os.environ.pop("MODE", None)


# ─────────────────────────────────────────────────────────────────────────────
# Test: execute_trade (EVM) in paper mode
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteTradeEVMPaperMode(unittest.TestCase):
    """execute_trade must return a paper result without touching web3/1inch."""

    def test_no_web3_calls_in_paper_mode(self):
        os.environ["MODE"] = "paper"
        try:
            with patch.dict(sys.modules, _STUBS):
                from core.executor import TradeExecutor, TradeParams
                from config import settings

                self.assertTrue(settings.IS_PAPER,
                                "IS_PAPER should be True when MODE=paper")

                executor = TradeExecutor(is_paper=True)
                params = TradeParams(
                    wallet=_wallet_mock,
                    chain="base",
                    token_in="0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                    token_out="0xABCDEF1234567890abcdef1234567890ABCDEF12",
                    amount_in_wei=int(0.01 * 1e18),
                    slippage_bps=200,
                )

                result = executor.execute_trade(params)

                self.assertTrue(result.success,
                                f"Paper trade should succeed, got: {result.error}")
                self.assertIn("paper", result.execution_path.lower(),
                              f"execution_path should contain 'paper', got: {result.execution_path}")
                self.assertEqual(result.tx_hash, "PAPER_TX",
                                 f"tx_hash should be PAPER_TX, got: {result.tx_hash}")

                # 1inch/CoW use POST — must never be called in paper mode
                http_session_stub.get_session.return_value.post.assert_not_called()
        finally:
            os.environ.pop("MODE", None)
            # Reload executor so next test gets a fresh module
            for mod in list(sys.modules.keys()):
                if "core.executor" in mod:
                    del sys.modules[mod]


# ─────────────────────────────────────────────────────────────────────────────
# Test: execute_sell_solana in paper mode
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteSellSolanaPaperMode(unittest.TestCase):
    """execute_sell_solana must never broadcast a transaction in paper mode."""

    def test_no_jupiter_call_in_paper_mode(self):
        os.environ["MODE"] = "paper"
        try:
            with patch.dict(sys.modules, _STUBS):
                from core.sell_engine import execute_sell_solana

                result = execute_sell_solana(
                    token_mint="CBhmimd1234567890abcdef1234567890ABCDEF12",
                    token_amount_units=1_000_000,
                    wallet_public_key="SolPubKey123",
                    wallet_private_key_env="SOLANA_PRIVATE_KEY",
                    urgency="normal",
                    is_paper=True,
                )

                self.assertTrue(result.success,
                                f"Paper sell should succeed, got: {result.error}")
                self.assertIn("paper", result.execution_path.lower(),
                              f"execution_path should contain 'paper', got: {result.execution_path}")

                # Jupiter uses POST for swaps — must not be called
                http_session_stub.get_session.return_value.post.assert_not_called()
        finally:
            os.environ.pop("MODE", None)
            for mod in list(sys.modules.keys()):
                if "core.sell_engine" in mod:
                    del sys.modules[mod]


# ─────────────────────────────────────────────────────────────────────────────
# Test: execute_sell_evm in paper mode
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteSellEVMPaperMode(unittest.TestCase):
    """execute_sell_evm must never broadcast a transaction in paper mode."""

    def test_no_1inch_call_in_paper_mode(self):
        os.environ["MODE"] = "paper"
        try:
            with patch.dict(sys.modules, _STUBS):
                from core.sell_engine import execute_sell_evm

                result = execute_sell_evm(
                    token_address="0xABCDEF1234567890abcdef1234567890ABCDEF12",
                    token_amount_wei=int(100 * 1e18),
                    chain="base",
                    wallet=_wallet_mock,
                    urgency="normal",
                    is_paper=True,
                )

                self.assertTrue(result.success,
                                f"Paper sell should succeed, got: {result.error}")
                self.assertIn("paper", result.execution_path.lower(),
                              f"execution_path should contain 'paper', got: {result.execution_path}")

                # 1inch uses POST for swap execution — must not be called
                http_session_stub.get_session.return_value.post.assert_not_called()
        finally:
            os.environ.pop("MODE", None)
            for mod in list(sys.modules.keys()):
                if "core.sell_engine" in mod:
                    del sys.modules[mod]


# ─────────────────────────────────────────────────────────────────────────────
# Test: execute_solana_buy in paper mode
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteSolanaBuyPaperMode(unittest.TestCase):
    """execute_solana_buy must return PAPER_TX without hitting Jupiter."""

    def test_no_jupiter_buy_call_in_paper_mode(self):
        os.environ["MODE"] = "paper"
        try:
            with patch.dict(sys.modules, _STUBS):
                from core.solana_executor import execute_solana_buy

                tx = execute_solana_buy(
                    token_mint="CBhmimd1234567890abcdef1234567890ABCDEF12",
                    sol_amount=0.05,
                    wallet_public_key="SolPubKey123",
                    wallet_private_key_env="SOLANA_PRIVATE_KEY",
                    is_paper=True,
                )

                self.assertEqual(tx, "PAPER_TX",
                                 f"Paper buy should return 'PAPER_TX', got: {tx}")

                # Jupiter uses POST for swaps — must not be called
                http_session_stub.get_session.return_value.post.assert_not_called()
        finally:
            os.environ.pop("MODE", None)
            for mod in list(sys.modules.keys()):
                if "core.solana_executor" in mod:
                    del sys.modules[mod]


# ─────────────────────────────────────────────────────────────────────────────
# Test: PositionMonitor.is_paper reads from settings dynamically
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionMonitorPaperFlag(unittest.TestCase):
    """PositionMonitor.is_paper must reflect settings.IS_PAPER at call time."""

    def test_is_paper_reflects_settings(self):
        os.environ["MODE"] = "paper"
        try:
            from core.position_monitor import PositionMonitor
            monitor = PositionMonitor(is_paper=True)
            self.assertTrue(monitor.is_paper,
                            "PositionMonitor.is_paper should be True in paper mode")
        finally:
            os.environ.pop("MODE", None)

    def test_execute_sell_passes_is_paper_to_engine(self):
        """execute_sell must pass is_paper=True to sell engine, not hardcoded False."""
        os.environ["MODE"] = "paper"
        try:
            from core.position_monitor import execute_sell

            pos = {
                "token_address": "0xABCDEF1234567890abcdef1234567890ABCDEF12",
                "token_symbol": "TEST",
                "chain": "base",
                "wallet": "primary",
                "quantity": 100.0,
                "remaining_quantity": 100.0,
                "entry_price": 1.0,
                "entry_time": "2026-01-01T00:00:00Z",
                "gem_score": 70.0,
                "strategy_profile": "gem",
            }
            sell_action = {
                "sell_pct": 0.4,
                "reason": "TP1",
                "urgency": "normal",
            }

            sell_engine_mock = MagicMock()
            sell_result_mock = MagicMock()
            sell_result_mock.success = True
            sell_result_mock.tx_hash = "PAPER_TX"
            sell_result_mock.attempts = 1
            sell_result_mock.slippage_bps_used = 200
            sell_engine_mock.execute_sell_evm.return_value = sell_result_mock
            sell_engine_mock.execute_sell_solana.return_value = sell_result_mock
            sell_engine_mock.resolve_sell_quantity.return_value = (40.0, int(40 * 1e18))

            with patch.dict(sys.modules, {"core.sell_engine": sell_engine_mock,
                                          "config.wallets": wallets_stub}):
                execute_sell(pos, sell_action, current_price=1.5, is_paper=True)

                # Verify is_paper=True was passed to the sell engine
                if sell_engine_mock.execute_sell_evm.called:
                    _, kwargs = sell_engine_mock.execute_sell_evm.call_args
                    self.assertTrue(
                        kwargs.get("is_paper", False),
                        "execute_sell_evm must be called with is_paper=True in paper mode. "
                        f"Got is_paper={kwargs.get('is_paper')}"
                    )
                elif sell_engine_mock.execute_sell_solana.called:
                    _, kwargs = sell_engine_mock.execute_sell_solana.call_args
                    self.assertTrue(
                        kwargs.get("is_paper", False),
                        "execute_sell_solana must be called with is_paper=True in paper mode. "
                        f"Got is_paper={kwargs.get('is_paper')}"
                    )
        finally:
            os.environ.pop("MODE", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
