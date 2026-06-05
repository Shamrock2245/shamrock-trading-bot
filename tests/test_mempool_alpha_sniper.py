"""
tests/test_mempool_alpha_sniper.py — Unit tests for core/mempool_alpha_sniper.py

Tests:
  1.  Module import and singleton creation
  2.  Wallet cache loading (leaderboard + static SMART_MONEY_WALLETS)
  3.  Wallet cache unknown wallet returns 0.0
  4.  Elite score gate — sub-threshold wallets are rejected
  5.  Elite score gate — high-score wallets spawn execution thread
  6.  Duplicate tx dedup guard
  7.  Conviction multiplier — baseline (1% of net worth → mult ≈ 1.0)
  8.  Conviction multiplier — high conviction (5% → capped at MAX)
  9.  Conviction multiplier — low conviction (floored at 0.5)
  10. EVM paper-mode snipe end-to-end (no real execution)
  11. Solana paper-mode snipe end-to-end (no real execution)
  12. Safety check rejection blocks EVM snipe
  13. Safety check rejection blocks Solana snipe
  14. Settings knobs exist in config.settings
  15. Settings defaults are sensible
  16. Disabled sniper spawns no threads
  17. main.py wiring contains dual-path handlers
"""

import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Ensure repo root is on sys.path ──────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_evm_swap(tx_hash="0xabc123", token_address="0xdeadbeef",
                   token_symbol="PEPE", chain="base", buy_value_usd=500.0):
    return {
        "tx_hash": tx_hash,
        "token_address": token_address,
        "token_symbol": token_symbol,
        "token_name": "PepeToken",
        "chain": chain,
        "buy_value_usd": buy_value_usd,
        "value_with_decimals": buy_value_usd,
        "timestamp": "2025-01-01T00:00:00Z",
        "seen_via": "moralis_streams",
    }


def _make_sol_swap(sig="5xSig123",
                   token_mint="So11111111111111111111111111111111111111112",
                   token_symbol="BONK", buy_value_usd=200.0):
    return {
        "tx_hash": sig,
        "signature": sig,
        "token_address": token_mint,
        "token_symbol": token_symbol,
        "token_name": "BonkToken",
        "chain": "solana",
        "buy_value_usd": buy_value_usd,
        "value_with_decimals": buy_value_usd,
        "timestamp": "2025-01-01T00:00:00Z",
        "seen_via": "moralis_streams_solana",
    }


def _make_leaderboard_entry(address, score=95.0, net_worth=100_000.0):
    return {
        "address": address,
        "sniper_score": score,
        "win_rate": 0.65,
        "total_realized_pnl_usd": 50_000.0,
        "net_worth_usd": net_worth,
        "is_active": True,
    }


def _mock_alloc(chain="base"):
    """Build a minimal TradeAllocation mock."""
    alloc = MagicMock()
    alloc.position_size_usd = 100.0
    alloc.slippage_bps = 200
    alloc.chain.native_token = "ETH" if chain != "solana" else "SOL"
    alloc.wallet.alias = "Primary"
    alloc.wallet.solana_address = "SolPub111111111111111111111111111111111111"
    alloc.wallet.solana_private_key_env = "SOLANA_PRIVATE_KEY_PRIMARY"
    return alloc


def _mock_safety(is_safe=True, reason=""):
    s = MagicMock()
    s.is_safe = is_safe
    s.block_reason = reason
    return s


class _SysModulesPatcher:
    """
    Context manager that injects fake module objects into sys.modules so that
    `from X import Y` calls inside the sniper's method bodies resolve to mocks.
    """
    def __init__(self, module_attrs: dict):
        """
        module_attrs: {module_name: {attr_name: value, ...}, ...}
        """
        self._module_attrs = module_attrs
        self._originals = {}

    def __enter__(self):
        for mod_name, attrs in self._module_attrs.items():
            self._originals[mod_name] = sys.modules.get(mod_name)
            fake = types.ModuleType(mod_name)
            for attr, val in attrs.items():
                setattr(fake, attr, val)
            sys.modules[mod_name] = fake
        return self

    def __exit__(self, *_):
        for mod_name, original in self._originals.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestMempoolAlphaSniper(unittest.TestCase):

    # ── 1. Module import ─────────────────────────────────────────────────────

    def test_01_module_imports(self):
        """Module should import cleanly without requiring live keys."""
        import core.mempool_alpha_sniper as m
        self.assertTrue(hasattr(m, "MempoolAlphaSniper"))
        self.assertTrue(hasattr(m, "mempool_sniper"))
        self.assertTrue(hasattr(m, "_SniperWalletCache"))
        self.assertTrue(hasattr(m, "_conviction_multiplier"))

    def test_02_singleton_is_paper(self):
        """Module-level singleton should be in paper mode (no live keys in test env)."""
        from core.mempool_alpha_sniper import mempool_sniper
        self.assertTrue(mempool_sniper.is_paper)

    # ── 2. Wallet cache ──────────────────────────────────────────────────────

    def test_03_wallet_cache_loads_leaderboard(self):
        """Cache should load from a temp leaderboard file and return correct score."""
        import core.mempool_alpha_sniper as m

        elite_addr = "0xelite0000000000000000000000000000000001"
        leaderboard = [_make_leaderboard_entry(elite_addr, score=95.0)]

        with tempfile.TemporaryDirectory() as tmpdir:
            lb_file = Path(tmpdir) / "sniper_leaderboard.json"
            lb_file.write_text(json.dumps(leaderboard))

            cache = m._SniperWalletCache()
            with patch.object(m, "_LEADERBOARD_FILE", lb_file):
                with patch.object(m, "_ACTIVE_SNIPERS_FILE", Path(tmpdir) / "nonexistent.json"):
                    score = cache.get_score(elite_addr)
                    self.assertAlmostEqual(score, 95.0, places=1)

    def test_04_wallet_cache_unknown_wallet_returns_zero(self):
        """Unknown wallet address should return score of 0.0."""
        import core.mempool_alpha_sniper as m

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = m._SniperWalletCache()
            with patch.object(m, "_LEADERBOARD_FILE", Path(tmpdir) / "nope.json"):
                with patch.object(m, "_ACTIVE_SNIPERS_FILE", Path(tmpdir) / "nope2.json"):
                    score = cache.get_score("0xunknown")
                    self.assertEqual(score, 0.0)

    # ── 3. Elite score gate ──────────────────────────────────────────────────

    def test_05_elite_gate_rejects_low_score(self):
        """Wallets with score < ELITE_SCORE_THRESHOLD should be silently skipped."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache
        sniper = MempoolAlphaSniper(is_paper=True)

        low_score_addr = "0xlowscore00000000000000000000000000000001"
        swap = _make_evm_swap(token_symbol="SCAM", chain="base")

        threads_spawned = []
        original_start = threading.Thread.start

        def mock_start(self_thread):
            threads_spawned.append(self_thread.name)
            original_start(self_thread)

        with patch.object(_wallet_cache, "get_score", return_value=50.0):
            with patch.object(threading.Thread, "start", mock_start):
                sniper.on_evm_swap_event(low_score_addr, swap)

        sniper_threads = [n for n in threads_spawned if "MempoolSniper" in n]
        self.assertEqual(len(sniper_threads), 0, "Low-score wallet should not spawn any thread")

    def test_06_elite_gate_accepts_high_score(self):
        """Wallets with score >= ELITE_SCORE_THRESHOLD should trigger execution thread."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache
        sniper = MempoolAlphaSniper(is_paper=True)

        elite_addr = "0xelite0000000000000000000000000000000002"
        swap = _make_evm_swap(tx_hash="0xhighscore001", token_symbol="GEM", chain="base")

        threads_spawned = []
        original_start = threading.Thread.start

        def mock_start(self_thread):
            threads_spawned.append(self_thread.name)
            original_start(self_thread)

        with patch.object(_wallet_cache, "get_score", return_value=95.0):
            with patch.object(threading.Thread, "start", mock_start):
                sniper.on_evm_swap_event(elite_addr, swap)

        self.assertTrue(
            any("MempoolSniper-EVM" in n for n in threads_spawned),
            f"Expected MempoolSniper-EVM thread, got: {threads_spawned}"
        )

    # ── 4. Dedup guard ───────────────────────────────────────────────────────

    def test_07_dedup_same_tx_hash(self):
        """Same tx_hash should only be processed once."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache
        sniper = MempoolAlphaSniper(is_paper=True)

        elite_addr = "0xelite0000000000000000000000000000000003"
        swap = _make_evm_swap(tx_hash="0xduplicate001", token_symbol="DUP", chain="base")

        threads_spawned = []
        original_start = threading.Thread.start

        def mock_start(self_thread):
            threads_spawned.append(self_thread.name)
            original_start(self_thread)

        with patch.object(_wallet_cache, "get_score", return_value=95.0):
            with patch.object(threading.Thread, "start", mock_start):
                sniper.on_evm_swap_event(elite_addr, swap)   # First — should spawn
                sniper.on_evm_swap_event(elite_addr, swap)   # Second — should be deduped

        evm_threads = [n for n in threads_spawned if "MempoolSniper-EVM" in n]
        self.assertEqual(len(evm_threads), 1, "Duplicate tx should only spawn one thread")

    # ── 5. Conviction multiplier ─────────────────────────────────────────────

    def test_08_conviction_multiplier_baseline(self):
        """1% of net worth should return multiplier of 1.0 (baseline)."""
        from core.mempool_alpha_sniper import _conviction_multiplier, _WalletEntry
        entry = _WalletEntry(
            address="0xtest", sniper_score=95.0, win_rate=0.65,
            total_realized_pnl_usd=10_000.0, net_worth_usd=100_000.0,
        )
        # 1% of $100k = $1000 buy → conviction = 0.01 = BASELINE_CONVICTION → mult = 1.0
        mult = _conviction_multiplier(entry, alpha_buy_usd=1_000.0)
        self.assertAlmostEqual(mult, 1.0, places=1)

    def test_09_conviction_multiplier_high_conviction(self):
        """5% of net worth should be capped at MAX_CONVICTION_MULT."""
        from core.mempool_alpha_sniper import _conviction_multiplier, _WalletEntry, MAX_CONVICTION_MULT
        entry = _WalletEntry(
            address="0xtest", sniper_score=95.0, win_rate=0.65,
            total_realized_pnl_usd=10_000.0, net_worth_usd=100_000.0,
        )
        # 5% of $100k = $5000 → conviction = 0.05 → mult = 5.0 → capped at MAX_CONVICTION_MULT
        mult = _conviction_multiplier(entry, alpha_buy_usd=5_000.0)
        self.assertLessEqual(mult, MAX_CONVICTION_MULT)
        self.assertGreater(mult, 1.0)

    def test_10_conviction_multiplier_low_conviction(self):
        """Very small buy relative to net worth should return minimum multiplier (0.5)."""
        from core.mempool_alpha_sniper import _conviction_multiplier, _WalletEntry
        entry = _WalletEntry(
            address="0xtest", sniper_score=95.0, win_rate=0.65,
            total_realized_pnl_usd=10_000.0, net_worth_usd=1_000_000.0,
        )
        # $10 on $1M net worth → well below baseline → floored at 0.5
        mult = _conviction_multiplier(entry, alpha_buy_usd=10.0)
        self.assertGreaterEqual(mult, 0.5)

    # ── 6. EVM paper-mode snipe ──────────────────────────────────────────────

    def test_11_evm_paper_snipe_executes(self):
        """EVM paper-mode snipe should complete without error and call register_position."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache, _WalletEntry

        sniper = MempoolAlphaSniper(is_paper=True)
        elite_addr = "0xelite0000000000000000000000000000000004"
        swap = _make_evm_swap(
            tx_hash="0xpaper_evm_001", token_symbol="MOON",
            chain="base", buy_value_usd=1000.0,
        )

        mock_reg = MagicMock()
        alloc = _mock_alloc("base")

        # Build mock Token and GemCandidate that satisfy the sniper's constructor calls
        mock_token = MagicMock()
        mock_token.address = swap["token_address"]
        mock_token.symbol = swap["token_symbol"]
        mock_token.chain = "base"
        mock_token.price_usd = 0.0

        mock_candidate = MagicMock()
        mock_candidate.gem_score = 95.0
        mock_candidate.strategy_tag = ""

        with patch.object(_wallet_cache, "get_score", return_value=95.0):
            with patch.object(_wallet_cache, "get", return_value=_WalletEntry(
                address=elite_addr, sniper_score=95.0, win_rate=0.65,
                total_realized_pnl_usd=50_000.0, net_worth_usd=100_000.0,
            )):
                with _SysModulesPatcher({
                    "core.safety": {
                        "check_token_safety": lambda *a, **kw: _mock_safety(True),
                    },
                    "core.wallet_router": {
                        "calculate_kelly_position_pct": lambda **kw: 0.05,
                        "route_trade": lambda **kw: alloc,
                        "get_native_price_usd": lambda t: 2500.0,
                        "KellyParams": MagicMock,
                    },
                    "data.models": {
                        "Token": lambda **kw: mock_token,
                        "GemCandidate": lambda **kw: mock_candidate,
                    },
                    "core.position_monitor": {
                        "register_position": mock_reg,
                    },
                }):
                    sniper._execute_evm_snipe(elite_addr, swap, 95.0)

        self.assertTrue(mock_reg.called, "register_position should be called after paper EVM snipe")

    # ── 7. Solana paper-mode snipe ───────────────────────────────────────────

    def test_12_solana_paper_snipe_executes(self):
        """Solana paper-mode snipe should complete without error and call register_position."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache, _WalletEntry

        sniper = MempoolAlphaSniper(is_paper=True)
        elite_addr = "SolElite111111111111111111111111111111111111"
        swap = _make_sol_swap(sig="5xSolPaper001", token_symbol="BONK", buy_value_usd=300.0)

        mock_reg = MagicMock()
        alloc = _mock_alloc("solana")

        mock_token = MagicMock()
        mock_token.address = swap["token_address"]
        mock_token.symbol = swap["token_symbol"]
        mock_token.chain = "solana"
        mock_token.price_usd = 0.0

        mock_candidate = MagicMock()
        mock_candidate.gem_score = 93.0
        mock_candidate.strategy_tag = ""

        with patch.object(_wallet_cache, "get_score", return_value=93.0):
            with patch.object(_wallet_cache, "get", return_value=_WalletEntry(
                address=elite_addr, sniper_score=93.0, win_rate=0.60,
                total_realized_pnl_usd=20_000.0, net_worth_usd=50_000.0,
            )):
                with _SysModulesPatcher({
                    "core.safety": {
                        "check_token_safety": lambda *a, **kw: _mock_safety(True),
                    },
                    "core.wallet_router": {
                        "calculate_kelly_position_pct": lambda **kw: 0.05,
                        "route_trade": lambda **kw: alloc,
                        "get_native_price_usd": lambda t: 175.0,
                        "KellyParams": MagicMock,
                    },
                    "data.models": {
                        "Token": lambda **kw: mock_token,
                        "GemCandidate": lambda **kw: mock_candidate,
                    },
                    "core.position_monitor": {
                        "register_position": mock_reg,
                    },
                }):
                    sniper._execute_solana_snipe(elite_addr, swap, 93.0)

        self.assertTrue(mock_reg.called, "register_position should be called after paper Solana snipe")

    # ── 8. Safety check rejection ────────────────────────────────────────────

    def test_13_safety_rejection_blocks_evm_snipe(self):
        """Honeypot detection should block EVM execution before any trade."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache

        sniper = MempoolAlphaSniper(is_paper=True)
        elite_addr = "0xelite0000000000000000000000000000000005"
        swap = _make_evm_swap(tx_hash="0xhoneypot001", token_symbol="SCAM", chain="base")

        mock_route = MagicMock()

        with patch.object(_wallet_cache, "get_score", return_value=95.0):
            with _SysModulesPatcher({
                "core.safety": {
                    "check_token_safety": lambda *a, **kw: _mock_safety(False, "HONEYPOT"),
                },
                "core.wallet_router": {
                    "route_trade": mock_route,
                    "calculate_kelly_position_pct": lambda **kw: 0.05,
                    "get_native_price_usd": lambda t: 2500.0,
                    "KellyParams": MagicMock,
                },
                "data.models": {
                    "Token": MagicMock,
                    "GemCandidate": MagicMock,
                },
            }):
                sniper._execute_evm_snipe(elite_addr, swap, 95.0)

        mock_route.assert_not_called()

    def test_14_safety_rejection_blocks_solana_snipe(self):
        """Honeypot detection should block Solana execution before any trade."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache

        sniper = MempoolAlphaSniper(is_paper=True)
        elite_addr = "SolElite222222222222222222222222222222222222"
        swap = _make_sol_swap(sig="5xScam001", token_symbol="RUGPULL")

        mock_route = MagicMock()

        with patch.object(_wallet_cache, "get_score", return_value=91.0):
            with _SysModulesPatcher({
                "core.safety": {
                    "check_token_safety": lambda *a, **kw: _mock_safety(False, "HONEYPOT"),
                },
                "core.wallet_router": {
                    "route_trade": mock_route,
                    "calculate_kelly_position_pct": lambda **kw: 0.05,
                    "get_native_price_usd": lambda t: 175.0,
                    "KellyParams": MagicMock,
                },
                "data.models": {
                    "Token": MagicMock,
                    "GemCandidate": MagicMock,
                },
            }):
                sniper._execute_solana_snipe(elite_addr, swap, 91.0)

        mock_route.assert_not_called()

    # ── 9. Settings knobs ────────────────────────────────────────────────────

    def test_15_settings_keys_exist(self):
        """All MEMPOOL_SNIPER_* settings should be present in config.settings."""
        from config import settings
        for key in [
            "MEMPOOL_SNIPER_ENABLED",
            "MEMPOOL_SNIPER_ELITE_SCORE",
            "MEMPOOL_SNIPER_MAX_USD",
            "MEMPOOL_SNIPER_MIN_USD",
            "MEMPOOL_SNIPER_BASELINE_CONVICTION",
            "MEMPOOL_SNIPER_MAX_CONVICTION_MULT",
        ]:
            self.assertTrue(hasattr(settings, key), f"settings.{key} is missing")

    def test_16_settings_defaults(self):
        """Default settings should be sensible."""
        from config import settings
        self.assertGreaterEqual(settings.MEMPOOL_SNIPER_ELITE_SCORE, 85.0)
        self.assertGreaterEqual(settings.MEMPOOL_SNIPER_MAX_USD, 10.0)
        self.assertLess(settings.MEMPOOL_SNIPER_BASELINE_CONVICTION, 0.10)

    # ── 10. Disabled sniper ──────────────────────────────────────────────────

    def test_17_disabled_sniper_does_nothing(self):
        """When sniper.enabled=False, no threads should be spawned."""
        from core.mempool_alpha_sniper import MempoolAlphaSniper, _wallet_cache
        sniper = MempoolAlphaSniper(is_paper=True)
        sniper.enabled = False

        elite_addr = "0xelite0000000000000000000000000000000006"
        swap = _make_evm_swap(tx_hash="0xdisabled001", token_symbol="NOOP", chain="base")

        threads_spawned = []
        original_start = threading.Thread.start

        def mock_start(self_thread):
            threads_spawned.append(self_thread.name)
            original_start(self_thread)

        with patch.object(_wallet_cache, "get_score", return_value=99.0):
            with patch.object(threading.Thread, "start", mock_start):
                sniper.on_evm_swap_event(elite_addr, swap)

        sniper_threads = [n for n in threads_spawned if "MempoolSniper" in n]
        self.assertEqual(len(sniper_threads), 0, "Disabled sniper should spawn no threads")


# ─────────────────────────────────────────────────────────────────────────────
# Integration smoke test — verifies main.py wiring compiles without error
# ─────────────────────────────────────────────────────────────────────────────

class TestMainPyWiring(unittest.TestCase):

    def test_18_main_py_has_sniper_wiring(self):
        """main.py should contain the dual-path swap handler wiring."""
        main_py = REPO_ROOT / "main.py"
        self.assertTrue(main_py.exists(), "main.py must exist")
        content = main_py.read_text()
        self.assertIn("_on_swap_event_with_sniper", content)
        self.assertIn("_on_solana_alpha_event_with_sniper", content)
        self.assertIn("mempool_alpha_sniper", content)
        self.assertIn("on_evm_swap_event", content)
        self.assertIn("on_solana_alpha_event", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
