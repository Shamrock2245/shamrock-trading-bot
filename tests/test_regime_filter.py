import unittest
from unittest.mock import patch, MagicMock
import time

from core.regime_filter import get_regime, Regime, get_sizing_multiplier, RegimeState
from core.position_monitor import evaluate_position
from config.wallets import StrategyProfile

class TestRegimeFilter(unittest.TestCase):
    
    @patch('core.regime_filter._fetch_kraken_candles')
    @patch('core.regime_filter._fetch_funding_rate')
    def test_regime_classification_trending(self, mock_funding, mock_candles):
        # High ADX -> TRENDING
        mock_funding.return_value = 0.0001
        
        # 100 candles of rising price with high ADX
        candles = []
        base_price = 60000.0
        for i in range(100):
            price = base_price + i * 100
            # kline: [open_time, open, high, low, close, volume, ...]
            candles.append([
                i * 3600000,
                str(price),
                str(price + 50),
                str(price - 50),
                str(price + 20),
                "10.0"
            ])
            
        mock_candles.side_effect = lambda symbol, limit: candles if symbol == "BTCUSDT" else candles
        
        state = get_regime(force_refresh=True)
        self.assertEqual(state.regime, Regime.TRENDING)
        self.assertTrue("TRENDING" in state.details)

    @patch('core.regime_filter._fetch_kraken_candles')
    @patch('core.regime_filter._fetch_funding_rate')
    def test_regime_classification_nuke(self, mock_funding, mock_candles):
        # Sudden sharp drop in last few candles -> NUKE
        mock_funding.return_value = 0.0001
        
        candles = []
        base_price = 60000.0
        for i in range(96):
            price = base_price
            candles.append([
                i * 3600000,
                str(price),
                str(price + 10),
                str(price - 10),
                str(price),
                "10.0"
            ])
        # Last 4 candles dropping hard
        for i in range(96, 100):
            price = base_price * (1 - (i - 95) * 0.015) # drop 1.5% per hour -> total 6% drop
            candles.append([
                i * 3600000,
                str(price),
                str(price + 10),
                str(price - 10),
                str(price),
                "10.0"
            ])
            
        mock_candles.side_effect = lambda symbol, limit: candles if symbol == "BTCUSDT" else candles
        
        state = get_regime(force_refresh=True)
        self.assertEqual(state.regime, Regime.NUKE)
        self.assertTrue("NUKE" in state.details)

    @patch('core.regime_filter.get_regime')
    def test_position_monitor_personality_switch_trending(self, mock_get_regime):
        # Mock Trending regime
        mock_get_regime.return_value = RegimeState(
            regime=Regime.TRENDING,
            adx=35.0,
            volume_ratio=1.2,
            timestamp=time.time(),
            details="Mock Trending"
        )
        
        pos = {
            "token_symbol": "GEM",
            "chain": "solana",
            "entry_price": 100.0,
            "highest_price": 100.0,
            "current_price": 100.0,
            "tp1_hit": False,
        }
        
        profile = StrategyProfile(
            name="conservative",
            min_gem_score=68.0,
            express_lane_score=78.0,
            tp1_mult=1.5,
            tp1_sell_pct=0.40,
            tp2_mult=1.8,
            tp2_sell_pct=0.35,
            tp3_mult=5.0,
            tp3_sell_pct=0.25,
            hard_stop_pct=10.0,
            trailing_stop_pct=5.0
        )
        
        # Under normal conditions, no sell action at entry price
        action = evaluate_position(pos, 100.0, strategy_profile=profile)
        self.assertIsNone(action)
        
        # Let's verify that stops and TPs are indeed loosened and let winners run
        # With entry at 100.0, and price hitting 145.0, TP1 is normal 1.5x (150.0).
        # In Trending regime, TPs are multiplied by 1.5, so TP1 becomes 1.5 * 1.5 = 2.25x (225.0).
        # Thus, price 145.0 should NOT trigger TP1 in Trending!
        action = evaluate_position(pos, 145.0, strategy_profile=profile)
        self.assertIsNone(action)

    @patch('core.regime_filter.get_regime')
    def test_position_monitor_personality_switch_choppy(self, mock_get_regime):
        # Mock Choppy regime -> Mean-Reversion mode
        mock_get_regime.return_value = RegimeState(
            regime=Regime.CHOPPY,
            adx=15.0,
            volume_ratio=0.8,
            timestamp=time.time(),
            details="Mock Choppy"
        )
        
        pos = {
            "token_symbol": "GEM",
            "chain": "solana",
            "entry_price": 100.0,
            "highest_price": 100.0,
            "current_price": 100.0,
            "tp1_hit": False,
        }
        
        profile = StrategyProfile(
            name="conservative",
            min_gem_score=68.0,
            express_lane_score=78.0,
            tp1_mult=1.5,
            tp1_sell_pct=0.40,
            tp2_mult=1.8,
            tp2_sell_pct=0.35,
            tp3_mult=5.0,
            tp3_sell_pct=0.25,
            hard_stop_pct=10.0,
            trailing_stop_pct=5.0
        )
        
        # In Choppy regime, TP1 is overridden to 1.03 (3% scalp), selling 100%
        # Price at 103.5 should trigger a full sell!
        action = evaluate_position(pos, 103.5, strategy_profile=profile)
        self.assertIsNotNone(action)
        self.assertEqual(action["sell_pct"], 1.0)
        self.assertTrue("tp1" in action["reason"])

    @patch('core.regime_filter.get_regime')
    def test_position_monitor_personality_switch_nuke(self, mock_get_regime):
        # Mock Nuke regime -> Risk-Off mode
        mock_get_regime.return_value = RegimeState(
            regime=Regime.NUKE,
            adx=45.0,
            volume_ratio=2.0,
            timestamp=time.time(),
            details="Mock Nuke"
        )
        
        pos = {
            "token_symbol": "GEM",
            "chain": "solana",
            "entry_price": 100.0,
            "highest_price": 100.0,
            "current_price": 100.0,
            "tp1_hit": False,
        }
        
        profile = StrategyProfile(
            name="conservative",
            min_gem_score=68.0,
            express_lane_score=78.0,
            tp1_mult=1.5,
            tp1_sell_pct=0.40,
            tp2_mult=1.8,
            tp2_sell_pct=0.35,
            tp3_mult=5.0,
            tp3_sell_pct=0.25,
            hard_stop_pct=10.0,
            trailing_stop_pct=5.0
        )
        
        # In Nuke regime, hard stop loss is tightened to 1%.
        # Price at 98.9 (down 1.1%) should trigger an immediate hard stop-loss!
        action = evaluate_position(pos, 98.9, strategy_profile=profile)
        self.assertIsNotNone(action)
        self.assertEqual(action["sell_pct"], 1.0)
        self.assertTrue("hard_stop_loss" in action["reason"])
