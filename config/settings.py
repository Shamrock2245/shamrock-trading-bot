"""
config/settings.py — Central settings loader for Shamrock Trading Bot.

All values are loaded from environment variables with safe defaults.
Import this module anywhere in the codebase to access settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present (development only — production uses real env vars)
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Trading Mode
# ─────────────────────────────────────────────────────────────────────────────
MODE = os.getenv("MODE", "paper").lower()
IS_LIVE = MODE == "live"
IS_PAPER = MODE == "paper"

if IS_LIVE:
    import warnings
    warnings.warn(
        "⚠️  LIVE TRADING MODE ACTIVE — Real funds will be used. "
        "Ensure all safety checks are passing before proceeding.",
        stacklevel=2,
    )

# ─────────────────────────────────────────────────────────────────────────────
# MEV Protection
# ─────────────────────────────────────────────────────────────────────────────
FLASHBOTS_RPC_URL = os.getenv("FLASHBOTS_RPC_URL", "https://rpc.flashbots.net")
FLASHBOTS_SIGNING_KEY = os.getenv("FLASHBOTS_SIGNING_KEY", "")
COW_API_URL = os.getenv("COW_API_URL", "https://api.cow.fi/mainnet")

# ─────────────────────────────────────────────────────────────────────────────
# DEX APIs
# ─────────────────────────────────────────────────────────────────────────────
ONEINCH_API_KEY = os.getenv("ONEINCH_API_KEY", "")
ONEINCH_API_URL = os.getenv("ONEINCH_API_URL", "https://api.1inch.dev/swap/v6.0")

# Jupiter (Solana DEX aggregator)
# Primary API requires a key (https://portal.jup.ag). Falls back to lite-api automatically.
JUPITER_API_URL = os.getenv("JUPITER_API_URL", "https://api.jup.ag/swap/v1")
JUPITER_LITE_URL = "https://lite-api.jup.ag/swap/v1"  # Free fallback — no key needed
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
# Data Provider API Keys
# ─────────────────────────────────────────────────────────────────────────────
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
TOKEN_SNIFFER_API_KEY = os.getenv("TOKEN_SNIFFER_API_KEY", "")
LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_RPC_FALLBACK = os.getenv("SOLANA_RPC_FALLBACK", "https://solana-mainnet.g.alchemy.com/v2/demo")

# ─────────────────────────────────────────────────────────────────────────────
# Risk Management
# ─────────────────────────────────────────────────────────────────────────────
MAX_POSITION_SIZE_PERCENT = float(os.getenv("MAX_POSITION_SIZE_PERCENT", "2.0"))
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", "10"))
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "10.0"))
HARD_STOP_LOSS_PERCENT = float(os.getenv("HARD_STOP_LOSS_PERCENT", "25.0"))
TAKE_PROFIT_1X = float(os.getenv("TAKE_PROFIT_1X", "2.0"))
TAKE_PROFIT_2X = float(os.getenv("TAKE_PROFIT_2X", "5.0"))
CIRCUIT_BREAKER_PERCENT = float(os.getenv("CIRCUIT_BREAKER_PERCENT", "15.0"))
DAILY_LOSS_LIMIT_ETH = float(os.getenv("DAILY_LOSS_LIMIT_ETH", "0.5"))
MAX_GAS_GWEI = int(os.getenv("MAX_GAS_GWEI", "50"))
MIN_ETH_BALANCE_ALERT = float(os.getenv("MIN_ETH_BALANCE_ALERT", "0.05"))

# Dynamic position sizing by conviction score
# Score 80+ → 100% of max, 70-80 → 75%, 55-70 → 50%
CONVICTION_HIGH_THRESHOLD = float(os.getenv("CONVICTION_HIGH_THRESHOLD", "80.0"))
CONVICTION_MID_THRESHOLD = float(os.getenv("CONVICTION_MID_THRESHOLD", "70.0"))
CONVICTION_HIGH_MULTIPLIER = float(os.getenv("CONVICTION_HIGH_MULTIPLIER", "1.0"))
CONVICTION_MID_MULTIPLIER = float(os.getenv("CONVICTION_MID_MULTIPLIER", "0.75"))
CONVICTION_LOW_MULTIPLIER = float(os.getenv("CONVICTION_LOW_MULTIPLIER", "0.50"))

# ─────────────────────────────────────────────────────────────────────────────
# Chain Configuration
# ─────────────────────────────────────────────────────────────────────────────
_active_chains_env = os.getenv("ACTIVE_CHAINS", "ethereum,base,arbitrum,polygon,bsc,solana")
ACTIVE_CHAINS: list[str] = [c.strip().lower() for c in _active_chains_env.split(",") if c.strip()]

# ─────────────────────────────────────────────────────────────────────────────
# Scanner Settings
# ─────────────────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
# Lowered from 65.0 → 50.0 to surface Moralis trending tokens (typically score 42-50).
# Raise back to 55-60 once scoring distribution is confirmed in live trading.
MIN_GEM_SCORE = float(os.getenv("MIN_GEM_SCORE", "50.0"))
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "25000"))
MAX_TOKEN_AGE_HOURS = int(os.getenv("MAX_TOKEN_AGE_HOURS", "168"))
MAX_TRADES_PER_CYCLE = int(os.getenv("MAX_TRADES_PER_CYCLE", "3"))

# Express lane: skip full TA pipeline and execute immediately if score >= this
EXPRESS_LANE_SCORE = float(os.getenv("EXPRESS_LANE_SCORE", "82.0"))

# Volume spike threshold for breakout detection (multiplier vs 24h average)
VOLUME_SPIKE_THRESHOLD = float(os.getenv("VOLUME_SPIKE_THRESHOLD", "5.0"))

# ─────────────────────────────────────────────────────────────────────────────
# Technical Analysis & Fibonacci (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────
REQUIRE_FIB_ALIGNMENT = os.getenv("REQUIRE_FIB_ALIGNMENT", "true").lower() == "true"
MIN_SIGNAL_SCORE = float(os.getenv("MIN_SIGNAL_SCORE", "50.0"))
OHLCV_LOOKBACK_DAYS = int(os.getenv("OHLCV_LOOKBACK_DAYS", "7"))
FIB_PROXIMITY_PCT = float(os.getenv("FIB_PROXIMITY_PCT", "3.0"))
FIB_SWING_WINDOW = int(os.getenv("FIB_SWING_WINDOW", "3"))
TA_ENABLED = os.getenv("TA_ENABLED", "true").lower() == "true"

# ─────────────────────────────────────────────────────────────────────────────
# Position Monitoring
# ─────────────────────────────────────────────────────────────────────────────
POSITION_CHECK_INTERVAL_SECONDS = int(os.getenv("POSITION_CHECK_INTERVAL_SECONDS", "30"))
POSITIONS_FILE = os.getenv("POSITIONS_FILE", "output/positions.json")
TRADES_FILE = os.getenv("TRADES_FILE", "output/trades.json")

# ─────────────────────────────────────────────────────────────────────────────
# Trade Loop Guardrails (Defensive)
# ─────────────────────────────────────────────────────────────────────────────
# Dedup guard: skip tokens with an existing open position
DEDUP_GUARD_ENABLED = os.getenv("DEDUP_GUARD_ENABLED", "true").lower() == "true"
# Cooldown: hours to wait before re-entering a recently closed token
COOLDOWN_HOURS = float(os.getenv("COOLDOWN_HOURS", "2.0"))
# Total exposure cap: max % of portfolio deployed in open positions
MAX_PORTFOLIO_EXPOSURE_PCT = float(os.getenv("MAX_PORTFOLIO_EXPOSURE_PCT", "80.0"))
# Stale price guard: reject candidates with price data older than this (seconds)
MAX_PRICE_AGE_SECONDS = int(os.getenv("MAX_PRICE_AGE_SECONDS", "120"))

# ─────────────────────────────────────────────────────────────────────────────
# Offensive Guardrails (Work In Our Favor)
# ─────────────────────────────────────────────────────────────────────────────
# Winner scaling: add to positions that are pumping (>30% gain, volume rising)
WINNER_SCALING_ENABLED = os.getenv("WINNER_SCALING_ENABLED", "true").lower() == "true"
WINNER_SCALING_GAIN_PCT = float(os.getenv("WINNER_SCALING_GAIN_PCT", "30.0"))  # Min gain to trigger
WINNER_SCALING_MAX_ADDS = int(os.getenv("WINNER_SCALING_MAX_ADDS", "1"))  # Max scale-ins per position

# Smart DCA: buy more if a high-conviction position dips (10-20% down, above stop)
SMART_DCA_ENABLED = os.getenv("SMART_DCA_ENABLED", "true").lower() == "true"
SMART_DCA_DIP_PCT = float(os.getenv("SMART_DCA_DIP_PCT", "15.0"))  # Dip threshold to trigger
SMART_DCA_MIN_GEM_SCORE = float(os.getenv("SMART_DCA_MIN_GEM_SCORE", "65.0"))  # Min original score

# Profit reinvestment: boost conviction multiplier after big wins
PROFIT_BOOST_ENABLED = os.getenv("PROFIT_BOOST_ENABLED", "true").lower() == "true"
PROFIT_BOOST_MIN_GAIN_PCT = float(os.getenv("PROFIT_BOOST_MIN_GAIN_PCT", "50.0"))  # Min gain to trigger
PROFIT_BOOST_MULTIPLIER = float(os.getenv("PROFIT_BOOST_MULTIPLIER", "1.25"))  # 25% bigger next bets
PROFIT_BOOST_TRADES = int(os.getenv("PROFIT_BOOST_TRADES", "3"))  # Number of boosted trades

# Volume surge fast exit: take partial profit on blowoff tops
VOLUME_SURGE_EXIT_ENABLED = os.getenv("VOLUME_SURGE_EXIT_ENABLED", "true").lower() == "true"
VOLUME_SURGE_MULTIPLIER = float(os.getenv("VOLUME_SURGE_MULTIPLIER", "10.0"))  # Volume vs 24h avg
VOLUME_SURGE_MIN_GAIN_PCT = float(os.getenv("VOLUME_SURGE_MIN_GAIN_PCT", "50.0"))  # Must be in profit
VOLUME_SURGE_SELL_PCT = float(os.getenv("VOLUME_SURGE_SELL_PCT", "0.25"))  # Sell 25% of remaining

# Underperformer rotation: close flat positions to free capital
UNDERPERFORMER_EXIT_ENABLED = os.getenv("UNDERPERFORMER_EXIT_ENABLED", "true").lower() == "true"
UNDERPERFORMER_FLAT_HOURS = float(os.getenv("UNDERPERFORMER_FLAT_HOURS", "12.0"))  # Hours flat
UNDERPERFORMER_FLAT_PCT = float(os.getenv("UNDERPERFORMER_FLAT_PCT", "5.0"))  # ±5% = "flat"

# ─────────────────────────────────────────────────────────────────────────────
# Advanced Offensive Guardrails (Seven-Figure Acceleration System)
# ─────────────────────────────────────────────────────────────────────────────

# ── 1. Hot Streak Kelly Scaling ───────────────────────────────────────────────
# Scales Kelly fraction up/down based on consecutive wins/losses.
# 2+ wins → 1.25x Kelly | 4+ wins → 1.5x Kelly | 6+ wins → Full Kelly (2.0x)
# 1 loss  → 0.85x Kelly | 2 losses → 0.70x | 3+ losses → 0.50x (Quarter-Kelly)
HOT_STREAK_ENABLED = os.getenv("HOT_STREAK_ENABLED", "true").lower() == "true"

# ── 2. God Mode ───────────────────────────────────────────────────────────────
# Activates when daily realized PnL crosses threshold.
# Switches to Full Kelly sizing, tightens trailing stops, skips TP1 (hold for 5x).
GOD_MODE_ENABLED = os.getenv("GOD_MODE_ENABLED", "true").lower() == "true"
GOD_MODE_DAILY_PNL_THRESHOLD_USD = float(os.getenv("GOD_MODE_DAILY_PNL_THRESHOLD_USD", "500.0"))
GOD_MODE_KELLY_MULTIPLIER = float(os.getenv("GOD_MODE_KELLY_MULTIPLIER", "2.0"))  # Full Kelly
GOD_MODE_TRAILING_STOP_PCT = float(os.getenv("GOD_MODE_TRAILING_STOP_PCT", "12.0"))  # Tighter stop
GOD_MODE_SKIP_TP1 = os.getenv("GOD_MODE_SKIP_TP1", "true").lower() == "true"  # Skip 2x sell

# ── 3. House Money Protocol ───────────────────────────────────────────────────
# Reinvests a % of each win's profit into a "house money pool".
# Pool is deployed as a bonus on top of the next high-conviction trade.
HOUSE_MONEY_ENABLED = os.getenv("HOUSE_MONEY_ENABLED", "true").lower() == "true"
HOUSE_MONEY_REINVEST_PCT = float(os.getenv("HOUSE_MONEY_REINVEST_PCT", "30.0"))  # 30% of wins → pool
HOUSE_MONEY_MAX_POOL_USD = float(os.getenv("HOUSE_MONEY_MAX_POOL_USD", "2000.0"))  # Max pool size
HOUSE_MONEY_MIN_DEPLOY_USD = float(os.getenv("HOUSE_MONEY_MIN_DEPLOY_USD", "10.0"))  # Min to deploy
HOUSE_MONEY_MAX_DEPLOY_PCT = float(os.getenv("HOUSE_MONEY_MAX_DEPLOY_PCT", "50.0"))  # Max % of pool per trade
HOUSE_MONEY_MAX_POSITION_MULT = float(os.getenv("HOUSE_MONEY_MAX_POSITION_MULT", "1.5"))  # Max 1.5x base

# ── 4. Dynamic Profit Boost (enhanced from existing) ─────────────────────────
# Existing PROFIT_BOOST_* settings are the baseline.
# Large wins trigger an even bigger boost.
PROFIT_BOOST_MIN_GAIN_USD = float(os.getenv("PROFIT_BOOST_MIN_GAIN_USD", "50.0"))  # Min USD gain
PROFIT_BOOST_LARGE_WIN_USD = float(os.getenv("PROFIT_BOOST_LARGE_WIN_USD", "500.0"))  # Large win threshold
PROFIT_BOOST_LARGE_MULTIPLIER = float(os.getenv("PROFIT_BOOST_LARGE_MULTIPLIER", "1.75"))  # 75% bigger bets
PROFIT_BOOST_LARGE_TRADES = int(os.getenv("PROFIT_BOOST_LARGE_TRADES", "5"))  # 5 boosted trades

# ── 5. Cascade Score Boost ────────────────────────────────────────────────────
# Each profitable trade lowers MIN_GEM_SCORE by CASCADE_BOOST_PER_WIN points.
# Allows more aggressive discovery as the bot builds a winning streak.
# Losses recover the threshold. Floor prevents going too low.
CASCADE_BOOST_ENABLED = os.getenv("CASCADE_BOOST_ENABLED", "true").lower() == "true"
CASCADE_BOOST_PER_WIN = float(os.getenv("CASCADE_BOOST_PER_WIN", "0.5"))  # -0.5 per win
CASCADE_BOOST_MAX_REDUCTION = float(os.getenv("CASCADE_BOOST_MAX_REDUCTION", "10.0"))  # Max -10 pts
CASCADE_BOOST_RECOVERY_PER_LOSS = float(os.getenv("CASCADE_BOOST_RECOVERY_PER_LOSS", "1.0"))  # +1 per loss
CASCADE_BOOST_FLOOR_SCORE = float(os.getenv("CASCADE_BOOST_FLOOR_SCORE", "40.0"))  # Never below 40

# ── 6. Express Lane Overdrive ─────────────────────────────────────────────────
# Highest-conviction snipes (score ≥ EXPRESS_LANE_SCORE) get 1.5-2.0x sizing
# and wider slippage to guarantee entry on fast-moving tokens.
EXPRESS_OVERDRIVE_ENABLED = os.getenv("EXPRESS_OVERDRIVE_ENABLED", "true").lower() == "true"
EXPRESS_OVERDRIVE_EXTRA_SLIPPAGE_BPS = int(os.getenv("EXPRESS_OVERDRIVE_EXTRA_SLIPPAGE_BPS", "100"))  # +1%

# ── 7. Tiered Pyramiding ──────────────────────────────────────────────────────
# Adds to winners at 3 gain tiers. Trailing stop tightens with each add.
# Replaces the single WINNER_SCALING with a full pyramid strategy.
PYRAMID_SCALING_ENABLED = os.getenv("PYRAMID_SCALING_ENABLED", "true").lower() == "true"
# Tier 1: +30% gain → add 50% of original position, trailing stop = 20%
PYRAMID_TIER1_ENABLED = os.getenv("PYRAMID_TIER1_ENABLED", "true").lower() == "true"
PYRAMID_TIER1_GAIN_PCT = float(os.getenv("PYRAMID_TIER1_GAIN_PCT", "30.0"))
PYRAMID_TIER1_ADD_PCT = float(os.getenv("PYRAMID_TIER1_ADD_PCT", "50.0"))  # 50% of original
PYRAMID_TIER1_TRAILING_STOP_PCT = float(os.getenv("PYRAMID_TIER1_TRAILING_STOP_PCT", "20.0"))
# Tier 2: +100% gain → add 25% of original, trailing stop = 15%
PYRAMID_TIER2_ENABLED = os.getenv("PYRAMID_TIER2_ENABLED", "true").lower() == "true"
PYRAMID_TIER2_GAIN_PCT = float(os.getenv("PYRAMID_TIER2_GAIN_PCT", "100.0"))
PYRAMID_TIER2_ADD_PCT = float(os.getenv("PYRAMID_TIER2_ADD_PCT", "25.0"))  # 25% of original
PYRAMID_TIER2_TRAILING_STOP_PCT = float(os.getenv("PYRAMID_TIER2_TRAILING_STOP_PCT", "15.0"))
# Tier 3: +300% gain → add 10% of original, trailing stop = 10%
PYRAMID_TIER3_ENABLED = os.getenv("PYRAMID_TIER3_ENABLED", "true").lower() == "true"
PYRAMID_TIER3_GAIN_PCT = float(os.getenv("PYRAMID_TIER3_GAIN_PCT", "300.0"))
PYRAMID_TIER3_ADD_PCT = float(os.getenv("PYRAMID_TIER3_ADD_PCT", "10.0"))  # 10% of original
PYRAMID_TIER3_TRAILING_STOP_PCT = float(os.getenv("PYRAMID_TIER3_TRAILING_STOP_PCT", "10.0"))

# ── 8. Fast Fail ──────────────────────────────────────────────────────────────
# Cuts momentum-dead positions quickly to free capital for live opportunities.
# Replaces the 12-hour underperformer rotation with faster, smarter exits.
FAST_FAIL_ENABLED = os.getenv("FAST_FAIL_ENABLED", "true").lower() == "true"
FAST_FAIL_HOURS = float(os.getenv("FAST_FAIL_HOURS", "2.0"))  # Hours before checking
FAST_FAIL_DOWN_PCT = float(os.getenv("FAST_FAIL_DOWN_PCT", "10.0"))  # Down >10% = momentum dead
FAST_FAIL_STALL_HOURS = float(os.getenv("FAST_FAIL_STALL_HOURS", "4.0"))  # Hours before stall check
FAST_FAIL_STALL_PCT = float(os.getenv("FAST_FAIL_STALL_PCT", "15.0"))  # Must be up >15% in 4h

# ── 9. Momentum Reentry ───────────────────────────────────────────────────────
# After TP1 is hit on a token, immediately re-enters if volume is still surging.
# Captures the second leg of a pump (common in micro-caps).
MOMENTUM_REENTRY_ENABLED = os.getenv("MOMENTUM_REENTRY_ENABLED", "true").lower() == "true"
MOMENTUM_REENTRY_VOLUME_MULT = float(os.getenv("MOMENTUM_REENTRY_VOLUME_MULT", "3.0"))  # Vol must be 3x avg
MOMENTUM_REENTRY_MAX_AGE_MINUTES = float(os.getenv("MOMENTUM_REENTRY_MAX_AGE_MINUTES", "30.0"))  # 30min window
MOMENTUM_REENTRY_SIZE_MULT = float(os.getenv("MOMENTUM_REENTRY_SIZE_MULT", "1.25"))  # 1.25x normal size

# ── 10. Absolute Position Cap ─────────────────────────────────────────────────
# Hard cap on any single trade after all offensive multipliers are applied.
# Prevents runaway sizing even on a 6-win streak in God Mode.
OFFENSIVE_MAX_POSITION_USD = float(os.getenv("OFFENSIVE_MAX_POSITION_USD", "5000.0"))

# ─────────────────────────────────────────────────────────────────────────────
# Smart Money Tracking
# ─────────────────────────────────────────────────────────────────────────────
# Known smart money / whale wallet addresses to track across chains
SMART_MONEY_WALLETS: list[str] = [
    # Top DeFi traders / known alpha wallets (public addresses only)
    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",  # Vitalik (signal only)
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance hot wallet (accumulation signal)
    "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance 14
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Binance 15
    "0x0548f59fee79f8832c299e01dca5c76f034f558e",  # Known DeFi whale
    "0x9696f59e4d72e237be84ffd425dcad154bf96976",  # Known accumulator
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503",  # Binance cold
    "0xf977814e90da44bfa03b6295a0616a897441acec",  # Binance 8
    "0x5a52e96bacdabb82fd05763e25335261b270efcb",  # Known whale
    "0x742d35cc6634c0532925a3b8d4c9b5e9b3e1e2f3",  # DeFi alpha wallet
]

# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL_TRADES = os.getenv("SLACK_CHANNEL_TRADES", "#shamrock-trades")
SLACK_CHANNEL_ALERTS = os.getenv("SLACK_CHANNEL_ALERTS", "#shamrock-alerts")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────────────────────────────────────
# Database & Logging
# ─────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/shamrock_trading.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# API Rate Limits (requests per minute)
# ─────────────────────────────────────────────────────────────────────────────
RATE_LIMITS = {
    "dexscreener": 60,
    "coingecko": 30,
    "geckoterminal": 30,
    "coinmarketcap": 30,
    "goplus": 20,
    "honeypot_is": 30,
    "tokensniffer": 10,
    "etherscan": 5,       # per second — converted to 300/min
    "oneinch": 60,
    "moralis": 25,
    "lunarcrush": 4,      # per minute — 100/day hard cap
    "defillama": 500,     # generous, no key needed
    "jupiter": 600,       # Solana Jupiter API — very generous
    "grok": 30,           # Grok X sentiment — conservative to control costs
}

# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────
def validate_settings() -> list[str]:
    """
    Validate critical settings. Returns list of warning messages.
    Does NOT raise exceptions — warnings are logged and surfaced to operator.
    """
    warnings_list = []

    if IS_LIVE:
        if not FLASHBOTS_SIGNING_KEY:
            warnings_list.append("LIVE MODE: FLASHBOTS_SIGNING_KEY not set — MEV protection disabled")
        if not ONEINCH_API_KEY:
            warnings_list.append("LIVE MODE: ONEINCH_API_KEY not set — 1inch routing unavailable")
        if MAX_POSITION_SIZE_PERCENT > 5.0:
            warnings_list.append(f"LIVE MODE: MAX_POSITION_SIZE_PERCENT={MAX_POSITION_SIZE_PERCENT}% is high — consider ≤2%")
        if CIRCUIT_BREAKER_PERCENT > 20.0:
            warnings_list.append(f"LIVE MODE: CIRCUIT_BREAKER_PERCENT={CIRCUIT_BREAKER_PERCENT}% is very high")

    if not CMC_API_KEY:
        warnings_list.append("CMC_API_KEY not set — CoinMarketCap data unavailable")

    if MIN_GEM_SCORE < 50.0:
        warnings_list.append(f"MIN_GEM_SCORE={MIN_GEM_SCORE} is very low — may produce low-quality candidates")

    return warnings_list
