"""
tests/test_daily_goal_and_promoter.py — Unit tests for:
  - core/daily_goal_engine.py
  - core/paper_to_live_promoter.py
  - core/arb_executor.py (basic smoke tests)
"""
import json
import os
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── Ensure project root is on path ────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_fresh_engine(tmp_path):
    """Create a DailyGoalEngine with a temp state file."""
    import core.daily_goal_engine as dge_module
    # Reset singleton
    dge_module._engine = None
    state_file = tmp_path / "daily_goal_state.json"
    with patch.object(dge_module, "GOAL_STATE_FILE", state_file):
        engine = dge_module.DailyGoalEngine()
    return engine, state_file


# ─────────────────────────────────────────────────────────────────────────────
# DailyGoalEngine Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyGoalEngine:

    def test_initial_state(self, tmp_path):
        """Engine starts at Tier 0, $500/day target, 0 profit."""
        engine, _ = make_fresh_engine(tmp_path)
        assert engine.current_tier == 0
        assert engine.current_target_usd == 500.0
        assert engine.today_profit_usd == 0.0
        assert engine.progress_pct == 0.0
        assert engine.remaining_usd == 500.0

    def test_record_profit_accumulates(self, tmp_path):
        """record_profit accumulates correctly."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.paper_to_live_promoter.check_and_promote"):
            engine.record_profit(100.0, source="arb_cross_dex")
            engine.record_profit(150.0, source="gem_snipe")
            engine.record_profit(75.0, source="arb_triangular")
        assert abs(engine.today_profit_usd - 325.0) < 0.01
        assert engine._state.today_arb_profit_usd == pytest.approx(175.0)
        assert engine._state.today_gem_profit_usd == pytest.approx(150.0)

    def test_progress_pct_calculation(self, tmp_path):
        """Progress percentage is correct."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.paper_to_live_promoter.check_and_promote"):
            engine.record_profit(250.0, source="arb_cross_dex")
        assert engine.progress_pct == pytest.approx(50.0)

    def test_remaining_usd_decreases(self, tmp_path):
        """Remaining USD decreases as profit is recorded."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.paper_to_live_promoter.check_and_promote"):
            engine.record_profit(300.0, source="gem_snipe")
        assert engine.remaining_usd == pytest.approx(200.0)

    def test_remaining_usd_never_negative(self, tmp_path):
        """Remaining USD floors at 0 when goal is exceeded."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.paper_to_live_promoter.check_and_promote"):
            engine.record_profit(800.0, source="arb_cross_dex")
        assert engine.remaining_usd == 0.0

    def test_strategy_mode_normal_at_start(self, tmp_path):
        """Strategy mode is 'normal' at start of day."""
        engine, _ = make_fresh_engine(tmp_path)
        assert engine.strategy_mode == "normal"

    def test_strategy_mode_protect_at_100pct(self, tmp_path):
        """Strategy mode switches to 'protect' at 100%+ of goal."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.daily_goal_engine.settings") as mock_settings:
            mock_settings.MODE = "live"
            with patch("core.paper_to_live_promoter.check_and_promote"):
                engine.record_profit(520.0, source="arb_cross_dex")
        assert engine.strategy_mode == "protect"

    def test_strategy_mode_bank_it_at_150pct(self, tmp_path):
        """Strategy mode switches to 'bank_it' at 150%+ of goal."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.daily_goal_engine.settings") as mock_settings:
            mock_settings.MODE = "live"
            with patch("core.paper_to_live_promoter.check_and_promote"):
                engine.record_profit(800.0, source="arb_cross_dex")
        assert engine.strategy_mode == "bank_it"

    def test_strategy_mode_catch_up_after_6pm(self, tmp_path):
        """Strategy mode switches to 'catch_up' after 6 PM UTC if below 30%."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.daily_goal_engine.settings") as mock_settings:
            mock_settings.MODE = "live"
            with patch("core.paper_to_live_promoter.check_and_promote"):
                engine.record_profit(50.0, source="arb_cross_dex")  # Only 10% of $500
            # Simulate 6 PM UTC
            from datetime import datetime, timezone
            mock_dt = MagicMock()
            mock_dt.hour = 19  # 7 PM UTC
            with patch("core.daily_goal_engine.datetime") as mock_datetime:
                mock_datetime.now.return_value = mock_dt
                engine._update_strategy_mode()
        assert engine.strategy_mode == "catch_up"

    def test_tier_advance_after_5_consecutive_hits(self, tmp_path):
        """Tier advances from 0 to 1 after 5 consecutive $500+ days."""
        engine, _ = make_fresh_engine(tmp_path)
        engine._state.consecutive_hits = 4  # 4 hits already
        engine._state.today_date = "2026-01-01"
        engine._state.today_profit_usd = 600.0
        engine._state.today_trade_count = 10
        with patch("core.daily_goal_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-01-02"
            mock_dt.now.return_value.isoformat.return_value = "2026-01-02T00:00:00+00:00"
            engine.close_day()
        assert engine.current_tier == 1
        assert engine.current_target_usd == 750.0
        assert engine._state.consecutive_hits == 0  # Reset after advance

    def test_tier_drop_after_3_consecutive_misses(self, tmp_path):
        """Tier drops from 1 to 0 after 3 consecutive misses."""
        engine, _ = make_fresh_engine(tmp_path)
        engine._state.current_tier = 1
        engine._state.current_target_usd = 750.0
        engine._state.consecutive_misses = 2  # 2 misses already
        engine._state.today_date = "2026-01-01"
        engine._state.today_profit_usd = 300.0  # Miss
        engine._state.today_trade_count = 5
        with patch("core.daily_goal_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-01-02"
            mock_dt.now.return_value.isoformat.return_value = "2026-01-02T00:00:00+00:00"
            engine.close_day()
        assert engine.current_tier == 0
        assert engine.current_target_usd == 500.0

    def test_tier_never_drops_below_0(self, tmp_path):
        """Tier never drops below 0 ($500/day floor is permanent)."""
        engine, _ = make_fresh_engine(tmp_path)
        engine._state.current_tier = 0
        engine._state.consecutive_misses = 10
        engine._state.today_date = "2026-01-01"
        engine._state.today_profit_usd = 0.0
        engine._state.today_trade_count = 1
        with patch("core.daily_goal_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-01-02"
            mock_dt.now.return_value.isoformat.return_value = "2026-01-02T00:00:00+00:00"
            engine.close_day()
        assert engine.current_tier == 0
        assert engine.current_target_usd == 500.0

    def test_arb_config_overrides_catch_up(self, tmp_path):
        """Catch-up mode returns lower spread thresholds and faster scan."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch.object(engine, "get_strategy_mode", return_value="catch_up"):
            cfg = engine.get_arb_config_overrides()
        assert cfg["ARB_MIN_SPREAD_PCT"] < 0.8  # Lower than normal
        assert cfg["scan_interval_seconds"] < 15  # Faster than normal

    def test_arb_config_overrides_protect(self, tmp_path):
        """Protect mode returns higher spread thresholds and slower scan."""
        engine, _ = make_fresh_engine(tmp_path)
        engine._state.strategy_mode = "protect"
        # Force get_strategy_mode to return 'protect'
        with patch.object(engine, "get_strategy_mode", return_value="protect"):
            cfg = engine.get_arb_config_overrides()
        assert cfg["ARB_MIN_SPREAD_PCT"] > 0.8  # Higher than normal
        assert cfg["scan_interval_seconds"] > 15  # Slower than normal

    def test_position_size_multiplier_scales_with_tier(self, tmp_path):
        """Position size multiplier increases with tier."""
        engine, _ = make_fresh_engine(tmp_path)
        engine._state.strategy_mode = "normal"
        engine._state.current_tier = 0
        mult_t0 = engine.get_position_size_multiplier()
        engine._state.current_tier = 3
        mult_t3 = engine.get_position_size_multiplier()
        assert mult_t3 > mult_t0

    def test_gem_score_override_catch_up_lowers_floor(self, tmp_path):
        """Catch-up mode lowers the gem score floor."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch.object(engine, "get_strategy_mode", return_value="catch_up"):
            with patch("core.daily_goal_engine.settings") as mock_settings:
                mock_settings.MIN_GEM_SCORE = 68.0
                override = engine.get_gem_score_override()
        assert override < 68.0

    def test_gem_score_override_protect_raises_floor(self, tmp_path):
        """Protect mode raises the gem score floor."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch.object(engine, "get_strategy_mode", return_value="protect"):
            with patch("core.daily_goal_engine.settings") as mock_settings:
                mock_settings.MIN_GEM_SCORE = 68.0
                override = engine.get_gem_score_override()
        assert override > 68.0

    def test_dashboard_returns_complete_dict(self, tmp_path):
        """get_dashboard returns all expected keys."""
        engine, _ = make_fresh_engine(tmp_path)
        dashboard = engine.get_dashboard()
        required_keys = [
            "today_date", "today_profit_usd", "today_target_usd",
            "progress_pct", "remaining_usd", "strategy_mode",
            "current_tier", "tier_label", "consecutive_hits",
            "consecutive_misses", "all_time_best_day_usd",
            "today_breakdown", "position_size_multiplier",
        ]
        for key in required_keys:
            assert key in dashboard, f"Missing key: {key}"

    def test_state_persists_to_file(self, tmp_path):
        """State is saved to JSON file after recording profit."""
        engine, state_file = make_fresh_engine(tmp_path)
        import core.daily_goal_engine as dge_module
        with patch.object(dge_module, "GOAL_STATE_FILE", state_file):
            with patch("core.paper_to_live_promoter.check_and_promote"):
                engine.record_profit(200.0, source="arb_cross_dex")
        assert state_file.exists()
        with open(state_file) as f:
            data = json.load(f)
        assert data["today_profit_usd"] == pytest.approx(200.0)

    def test_tier_7_unlimited_always_hits(self, tmp_path):
        """Tier 7 (unlimited) always counts as a hit regardless of profit."""
        engine, _ = make_fresh_engine(tmp_path)
        engine._state.current_tier = 7
        engine._state.current_target_usd = 0.0  # Unlimited
        engine._state.today_date = "2026-01-01"
        engine._state.today_profit_usd = 1.0  # Even $1
        engine._state.today_trade_count = 1
        with patch("core.daily_goal_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-01-02"
            mock_dt.now.return_value.isoformat.return_value = "2026-01-02T00:00:00+00:00"
            result = engine.close_day()
        assert result["hit"] is True


# ─────────────────────────────────────────────────────────────────────────────
# PaperToLivePromoter Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPaperToLivePromoter:

    def test_no_promotion_below_threshold(self, tmp_path):
        """No promotion when profit is below $500."""
        with patch("config.settings.IS_LIVE", False), \
             patch("config.settings.IS_PAPER", True):
            import core.paper_to_live_promoter as ptlp
            with patch.object(ptlp, "PROMOTION_RECORD_FILE", tmp_path / "promo.json"):
                result = ptlp.check_and_promote(today_profit_usd=499.99)
        assert result is False

    def test_no_promotion_when_already_live(self, tmp_path):
        """No promotion when already in live mode."""
        import core.paper_to_live_promoter as ptlp
        with patch("core.paper_to_live_promoter.os.getenv", return_value="false"):
            with patch("config.settings") as mock_settings:
                mock_settings.IS_LIVE = True
                result = ptlp.check_and_promote(today_profit_usd=600.0)
        assert result is False

    def test_no_promotion_when_locked(self, tmp_path):
        """No promotion when PAPER_MODE_LOCKED=true."""
        import core.paper_to_live_promoter as ptlp
        with patch.dict(os.environ, {"PAPER_MODE_LOCKED": "true"}):
            with patch("config.settings") as mock_settings:
                mock_settings.IS_LIVE = False
                result = ptlp.check_and_promote(today_profit_usd=600.0)
        assert result is False

    def test_promotion_blocked_without_private_key(self, tmp_path):
        """Promotion blocked if no private key is set."""
        import core.paper_to_live_promoter as ptlp
        # Remove private keys from env
        env_overrides = {
            "PAPER_MODE_LOCKED": "false",
            "WALLET_PRIVATE_KEY_PRIMARY": "",
            "WALLET_PRIVATE_KEY_B": "",
            "WALLET_PRIVATE_KEY_C": "",
        }
        mock_wallet = MagicMock()
        mock_wallet.address = "0x3eb320fad3f51fe4f2a4531f911ef56694346eef"
        mock_wallets_module = MagicMock()
        mock_wallets_module.WALLETS = {"primary": mock_wallet}
        with patch.dict(os.environ, env_overrides):
            with patch.dict("sys.modules", {"config.wallets": mock_wallets_module}):
                with patch.object(ptlp, "PROMOTION_RECORD_FILE", tmp_path / "promo.json"):
                    with patch.object(ptlp, "_already_promoted_today", return_value=False):
                        with patch("core.wallet_router.get_native_balance", return_value=1.0):
                            with patch("core.paper_to_live_promoter._send_blocked_alert"):
                                with patch("config.settings") as mock_settings:
                                    mock_settings.IS_LIVE = False
                                    result = ptlp.check_and_promote(today_profit_usd=600.0)
        assert result is False

    def test_update_env_file_creates_file(self, tmp_path):
        """_update_env_file creates .env if it doesn't exist."""
        import core.paper_to_live_promoter as ptlp
        env_file = tmp_path / ".env"
        with patch.object(ptlp, "ENV_FILE", env_file):
            result = ptlp._update_env_file("MODE", "live")
        assert result is True
        assert env_file.exists()
        content = env_file.read_text()
        assert "MODE=live" in content

    def test_update_env_file_updates_existing_key(self, tmp_path):
        """_update_env_file updates existing MODE=paper to MODE=live."""
        import core.paper_to_live_promoter as ptlp
        env_file = tmp_path / ".env"
        env_file.write_text("MODE=paper\nMORALIS_API_KEY=abc123\n")
        with patch.object(ptlp, "ENV_FILE", env_file):
            result = ptlp._update_env_file("MODE", "live")
        assert result is True
        content = env_file.read_text()
        assert "MODE=live" in content
        assert "MODE=paper" not in content
        assert "MORALIS_API_KEY=abc123" in content  # Other keys preserved

    def test_update_env_file_appends_new_key(self, tmp_path):
        """_update_env_file appends new key if not present."""
        import core.paper_to_live_promoter as ptlp
        env_file = tmp_path / ".env"
        env_file.write_text("MORALIS_API_KEY=abc123\n")
        with patch.object(ptlp, "ENV_FILE", env_file):
            result = ptlp._update_env_file("MODE", "live")
        assert result is True
        content = env_file.read_text()
        assert "MODE=live" in content
        assert "MORALIS_API_KEY=abc123" in content

    def test_already_promoted_today_false_when_no_file(self, tmp_path):
        """_already_promoted_today returns False when no record file exists."""
        import core.paper_to_live_promoter as ptlp
        with patch.object(ptlp, "PROMOTION_RECORD_FILE", tmp_path / "promo.json"):
            result = ptlp._already_promoted_today()
        assert result is False

    def test_already_promoted_today_true_when_same_day(self, tmp_path):
        """_already_promoted_today returns True when promoted today."""
        import core.paper_to_live_promoter as ptlp
        from datetime import datetime, timezone
        promo_file = tmp_path / "promo.json"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        promo_file.write_text(json.dumps([{"promoted_at": f"{today}T12:00:00+00:00"}]))
        with patch.object(ptlp, "PROMOTION_RECORD_FILE", promo_file):
            result = ptlp._already_promoted_today()
        assert result is True

    def test_gas_readiness_status_returns_dict(self, tmp_path):
        """get_gas_readiness_status returns a dict with expected keys."""
        import core.paper_to_live_promoter as ptlp
        mock_wallet = MagicMock()
        mock_wallet.address = "0x3eb320fad3f51fe4f2a4531f911ef56694346eef"
        # Patch the module-level imports used inside the function
        with patch("core.wallet_router.get_native_balance", return_value=0.05):
            # Patch the import inside the function
            with patch.dict("sys.modules", {"config.wallets": MagicMock(WALLETS={"primary": mock_wallet})}):
                status = ptlp.get_gas_readiness_status()
        assert "ready_for_live" in status
        assert "chains" in status
        assert "total_chains_ready" in status

    def test_save_and_load_promotion_record(self, tmp_path):
        """Promotion record is saved and can be loaded."""
        import core.paper_to_live_promoter as ptlp
        from core.paper_to_live_promoter import PromotionRecord
        promo_file = tmp_path / "promo.json"
        record = PromotionRecord(
            promoted_at="2026-05-29T12:00:00+00:00",
            paper_profit_usd=523.40,
            threshold_usd=500.0,
            gas_balances={"base": 0.05},
            chains_with_gas=["base"],
            chains_missing_gas=[],
            private_keys_present=["WALLET_PRIVATE_KEY_PRIMARY"],
            env_file_updated=True,
            notifications_sent=["slack", "telegram"],
        )
        with patch.object(ptlp, "PROMOTION_RECORD_FILE", promo_file):
            ptlp._save_promotion_record(record)
        assert promo_file.exists()
        with open(promo_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["paper_profit_usd"] == pytest.approx(523.40)
        assert data[0]["chains_with_gas"] == ["base"]


# ─────────────────────────────────────────────────────────────────────────────
# ArbExecutor Smoke Tests (require web3 — skip if not installed)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from web3 import Web3
    _WEB3_AVAILABLE = True
except ImportError:
    _WEB3_AVAILABLE = False

@pytest.mark.skipif(not _WEB3_AVAILABLE, reason="web3 not installed in test env")
class TestArbExecutorSmoke:

    def test_expired_opportunity_rejected(self):
        """Expired opportunities are rejected immediately."""
        from core.arb_executor import ArbExecutor
        from scanner.arb_scanner import ArbOpportunity
        import time as _time

        opp = ArbOpportunity(
            strategy="cross_dex",
            chain="base",
            token_address="0xabc",
            token_symbol="TEST",
            buy_dex="uniswap_v3",
            sell_dex="aerodrome",
            buy_price=1.0,
            sell_price=1.02,
            gross_profit_pct=2.0,
            gas_cost_usd=5.0,
            net_profit_usd=15.0,
            position_size_usd=1000.0,
            discovered_at=_time.time() - 120,  # 2 minutes ago = expired
            ttl_seconds=60,
        )
        executor = ArbExecutor()
        result = executor.execute(opp)
        assert result.success is False
        assert "expired" in result.error.lower()

    def test_gas_profit_ratio_gate(self):
        """Opportunities with gas > 50% of profit are rejected."""
        from core.arb_executor import ArbExecutor
        from scanner.arb_scanner import ArbOpportunity
        import time as _time

        opp = ArbOpportunity(
            strategy="cross_dex",
            chain="base",
            token_address="0xabc",
            token_symbol="TEST",
            buy_dex="uniswap_v3",
            sell_dex="aerodrome",
            buy_price=1.0,
            sell_price=1.05,
            gross_profit_pct=5.0,
            gas_cost_usd=20.0,   # Gas > 50% of net profit
            net_profit_usd=30.0,
            position_size_usd=1000.0,
            discovered_at=_time.time(),
            ttl_seconds=300,
        )
        executor = ArbExecutor()
        result = executor.execute(opp)
        assert result.success is False
        assert "gas" in result.error.lower()

    def test_paper_cross_dex_simulation(self):
        """Paper mode cross-DEX simulation runs without error."""
        from core.arb_executor import ArbExecutor
        from scanner.arb_scanner import ArbOpportunity
        import time as _time

        opp = ArbOpportunity(
            strategy="cross_dex",
            chain="base",
            token_address="0xabc",
            token_symbol="TEST",
            buy_dex="uniswap_v3",
            sell_dex="aerodrome",
            buy_price=1.0,
            sell_price=1.015,
            gross_profit_pct=1.5,
            gas_cost_usd=2.0,
            net_profit_usd=13.0,
            position_size_usd=1000.0,
            discovered_at=_time.time(),
            ttl_seconds=300,
        )
        with patch("core.arb_executor.PAPER_TRADE", True):
            with patch("core.arb_executor.get_usdc_balance", return_value=5000.0):
                with patch("core.arb_executor.STABLECOINS", {"base": "0xusdc"}):
                    executor = ArbExecutor()
                    result = executor.execute(opp)
        # Paper simulation should either succeed or fail gracefully
        assert result is not None
        assert isinstance(result.success, bool)
        assert result.paper is True

    def test_stats_returns_dict(self):
        """get_stats returns a dict with expected keys."""
        from core.arb_executor import ArbExecutor
        executor = ArbExecutor()
        stats = executor.get_stats()
        assert "daily_profit_usd" in stats
        assert "daily_trade_count" in stats
        assert "success_rate" in stats
        assert "paper_mode" in stats


# ─────────────────────────────────────────────────────────────────────────────
# Integration: DailyGoalEngine + Promoter
# ─────────────────────────────────────────────────────────────────────────────

class TestGoalEnginePromoterIntegration:

    def test_promotion_triggered_at_500(self, tmp_path):
        """check_and_promote is called when daily profit hits $500."""
        engine, _ = make_fresh_engine(tmp_path)
        promotion_calls = []

        def mock_promote(today_profit_usd):
            promotion_calls.append(today_profit_usd)
            return False  # Don't actually promote in test

        with patch("core.paper_to_live_promoter.check_and_promote", side_effect=mock_promote):
            engine.record_profit(499.0, source="arb_cross_dex")
            engine.record_profit(2.0, source="gem_snipe")  # Crosses $500

        # Should have been called at least twice (once per record_profit)
        assert len(promotion_calls) >= 2
        # Last call should have profit >= 500
        assert promotion_calls[-1] >= 500.0

    def test_full_day_cycle(self, tmp_path):
        """Simulate a full day: record profits, close day, check tier."""
        engine, _ = make_fresh_engine(tmp_path)
        with patch("core.daily_goal_engine.settings") as mock_settings:
            mock_settings.MODE = "live"
            with patch("core.paper_to_live_promoter.check_and_promote"):
                # Simulate 10 trades totaling $620
                for i in range(10):
                    engine.record_profit(62.0, source="arb_cross_dex")

            assert engine.today_profit_usd == pytest.approx(620.0)
            assert engine.progress_pct == pytest.approx(124.0)
            assert engine.strategy_mode in ("protect", "bank_it")

        # Close the day
        with patch("core.daily_goal_engine.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-01-02"
            mock_dt.now.return_value.isoformat.return_value = "2026-01-02T00:00:00+00:00"
            result = engine.close_day()

        assert result["hit"] is True
        assert result["profit_usd"] == pytest.approx(620.0)
        assert engine._state.consecutive_hits == 1
