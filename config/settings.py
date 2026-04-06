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

# Hyperliquid (Perpetual Futures DEX — zero gas, leveraged trading)
# ⚠️  CAPITAL PRESERVATION MODE — conservative defaults to protect seed capital
HYPERLIQUID_ENABLED = os.getenv("HYPERLIQUID_ENABLED", "false").lower() == "true"
HYPERLIQUID_WALLET_ADDRESS = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
HYPERLIQUID_DEFAULT_LEVERAGE = int(os.getenv("HYPERLIQUID_DEFAULT_LEVERAGE", "2"))
HYPERLIQUID_MAX_POSITION_USD = float(os.getenv("HYPERLIQUID_MAX_POSITION_USD", "25"))
HYPERLIQUID_MAX_TOTAL_EXPOSURE = float(os.getenv("HYPERLIQUID_MAX_TOTAL_EXPOSURE", "150"))
HYPERLIQUID_USE_TESTNET = os.getenv("HYPERLIQUID_USE_TESTNET", "false").lower() == "true"
HYPERLIQUID_STOP_LOSS_PCT = float(os.getenv("HYPERLIQUID_STOP_LOSS_PCT", "3.0"))     # Tight 3% SL
HYPERLIQUID_TAKE_PROFIT_PCT = float(os.getenv("HYPERLIQUID_TAKE_PROFIT_PCT", "12.0"))  # 12% TP (4:1 R/R)
HYPERLIQUID_MAX_POSITIONS = int(os.getenv("HYPERLIQUID_MAX_POSITIONS", "4"))
HYPERLIQUID_DAILY_LOSS_LIMIT = float(os.getenv("HYPERLIQUID_DAILY_LOSS_LIMIT", "30.0"))  # Max $30/day loss
HYPERLIQUID_MIN_GEM_SCORE = float(os.getenv("HYPERLIQUID_MIN_GEM_SCORE", "80"))  # Only highest-conviction

# ─────────────────────────────────────────────────────────────────────────────
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
TOKEN_SNIFFER_API_KEY = os.getenv("TOKEN_SNIFFER_API_KEY", "")
GOPLUS_API_KEY = os.getenv("GOPLUS_API_KEY", "")  # Optional — enhances GoPlus rate limits
# LunarCrush removed (no free API)
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_RPC_FALLBACK = os.getenv("SOLANA_RPC_FALLBACK", "https://solana-mainnet.g.alchemy.com/v2/demo")

# ─────────────────────────────────────────────────────────────────────────────
# Risk Management
# ─────────────────────────────────────────────────────────────────────────────
# Global fallback — per-wallet sizing is controlled by StrategyProfile (Primary=5%, WalletB=60%)
MAX_POSITION_SIZE_PERCENT = float(os.getenv("MAX_POSITION_SIZE_PERCENT", "5.0"))
HIGH_CONVICTION_POSITION_PCT = float(os.getenv("HIGH_CONVICTION_POSITION_PCT", "3.5"))  # Score 85+
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", "10"))
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "15.0"))  # Playbook: 15% trailing after TP1
HARD_STOP_LOSS_PERCENT = float(os.getenv("HARD_STOP_LOSS_PERCENT", "20.0"))  # Tightened: cut losers at 20%

# ── Take-Profit Tiers (Profit Machine Playbook) ─────────────────────────────
# TP1 at 1.5x: sell 40% → captures micro-cap gains before reversals
# TP2 at 2.5x: sell 35% of remaining → asymmetric exit on confirmed runners
# TP3 at 5x:   sell 25% of remaining → moonshot capture (remaining rides to 10x+)
# Trailing stop after TP1: 15% below highest price seen
TAKE_PROFIT_TP1_MULT = float(os.getenv("TAKE_PROFIT_TP1_MULT", "1.5"))    # 50% gain → sell 40%
TAKE_PROFIT_TP1_SELL_PCT = float(os.getenv("TAKE_PROFIT_TP1_SELL_PCT", "0.40"))  # Sell 40%
TAKE_PROFIT_TP2_MULT = float(os.getenv("TAKE_PROFIT_TP2_MULT", "2.5"))    # 150% gain → sell 35% of remaining
TAKE_PROFIT_TP2_SELL_PCT = float(os.getenv("TAKE_PROFIT_TP2_SELL_PCT", "0.35"))  # Sell 35% of remaining
TAKE_PROFIT_TP3_MULT = float(os.getenv("TAKE_PROFIT_TP3_MULT", "5.0"))    # 400% gain → sell 25% of remaining
TAKE_PROFIT_TP3_SELL_PCT = float(os.getenv("TAKE_PROFIT_TP3_SELL_PCT", "0.25"))  # Sell 25% of remaining

# ── Time-Based & Liquidity Exits (Offensive Playbook §5) ──────────────────
TIME_EXIT_HOURS = float(os.getenv("TIME_EXIT_HOURS", "24.0"))              # Extended: allow 24h for Base/BSC gems to develop
TIME_EXIT_MIN_GAIN_PCT = float(os.getenv("TIME_EXIT_MIN_GAIN_PCT", "10.0"))  # Must be up >10% to stay

# ── Pre-TP1 Peak Protection (CRITICAL: prevents holding through full reversals) ─
# If a position builds gains but never hits TP1, we still protect those gains.
# Activates when position is up > PRE_TP1_ACTIVATE_GAIN_PCT (default 15%).
# Uses a WIDER stop than the post-TP1 trailing (25% vs 15%) to give room to run.
PRE_TP1_TRAILING_STOP_PCT = float(os.getenv("PRE_TP1_TRAILING_STOP_PCT", "25.0"))  # 25% trail before TP1
PRE_TP1_ACTIVATE_GAIN_PCT = float(os.getenv("PRE_TP1_ACTIVATE_GAIN_PCT", "15.0"))  # Activate when up 15%+

# ── Confluence Gate Override ─────────────────────────────────────────────────
# Hard override: if price drops this much from the high on a profitable position,
# sell regardless of how many confluence signals are present.
CONFLUENCE_HARD_REVERSAL_PCT = float(os.getenv("CONFLUENCE_HARD_REVERSAL_PCT", "25.0"))  # 25% drop from peak = sell
LIQUIDITY_DRAIN_EXIT_ENABLED = os.getenv("LIQUIDITY_DRAIN_EXIT_ENABLED", "true").lower() == "true"
LIQUIDITY_DRAIN_DROP_PCT = float(os.getenv("LIQUIDITY_DRAIN_DROP_PCT", "30.0"))  # >30% pool drain = emergency sell

# ── Continuous Rebalancing (Offensive Playbook §6) ─────────────────────────
DUST_THRESHOLD_USD = float(os.getenv("DUST_THRESHOLD_USD", "5.0"))         # Liquidate positions <$5
DUST_MIN_SELL_USD = float(os.getenv("DUST_MIN_SELL_USD", "1.00"))           # Only sell dust if value > est. gas cost
UNDERPERFORMER_LIQ_DOWN_PCT = float(os.getenv("UNDERPERFORMER_LIQ_DOWN_PCT", "30.0"))  # >30% down
UNDERPERFORMER_LIQ_MIN_USD = float(os.getenv("UNDERPERFORMER_LIQ_MIN_USD", "20000.0"))  # <$20k liquidity

# ── MEV Protection (Offensive Playbook §4) ─────────────────────────────────────────────────────────────────────────────
GAS_BRIBE_PREMIUM_PCT = float(os.getenv("GAS_BRIBE_PREMIUM_PCT", "15.0"))  # 15% gas premium for God Signals
# Jito (Solana MEV protection)
JITO_BLOCK_ENGINE_URL = os.getenv("JITO_BLOCK_ENGINE_URL", "https://mainnet.block-engine.jito.wtf/api/v1/bundles")
JITO_AUTH_KEY = os.getenv("JITO_AUTH_KEY", "")  # Optional: Jito auth keypair for priority access
# Helius RPC (enhanced Solana data — used by bundle detector + Jito)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

# ── Upgrade 2: Bundle Detector ───────────────────────────────────────────────
BUNDLE_DETECTOR_ENABLED = os.getenv("BUNDLE_DETECTOR_ENABLED", "true").lower() == "true"
BUNDLE_REJECT_THRESHOLD = float(os.getenv("BUNDLE_REJECT_THRESHOLD", "0.20"))  # Reject if >20% supply sniped in block 0

# ── Upgrade 3: ML Weight Optimizer ───────────────────────────────────────────
ML_WEIGHT_OPTIMIZER_ENABLED = os.getenv("ML_WEIGHT_OPTIMIZER_ENABLED", "true").lower() == "true"
ML_WEIGHT_LOOKBACK_DAYS = int(os.getenv("ML_WEIGHT_LOOKBACK_DAYS", "7"))        # Rolling 7-day training window
ML_WEIGHT_MIN_TRADES = int(os.getenv("ML_WEIGHT_MIN_TRADES", "20"))             # Min trades before ML kicks in
ML_WEIGHT_RETRAIN_HOURS = int(os.getenv("ML_WEIGHT_RETRAIN_HOURS", "6"))        # Retrain every 6 hours
DYNAMIC_WEIGHTS_PATH = os.getenv("DYNAMIC_WEIGHTS_PATH", "output/dynamic_weights.json")

# ── Upgrade 4: Wallet Monitor (Copy-Trading Daemon) ──────────────────────────
WALLET_MONITOR_ENABLED = os.getenv("WALLET_MONITOR_ENABLED", "true").lower() == "true"
WALLET_MONITOR_POLL_INTERVAL = int(os.getenv("WALLET_MONITOR_POLL_INTERVAL", "30"))      # seconds between polls
# ── Copy Trade Quality Gates ────────────────────────────────────────────────────────
# MIN_BUY_USD=500: require alpha wallet to make a $500+ buy (conviction, not noise)
# DEFAULT_COPY_USD=0: if Streams gives no buy_value, skip the trade entirely
# TIER1=3, TIER2=2: require 3 wallets for instant execute, 2 for express lane
WALLET_MONITOR_MIN_BUY_USD = float(os.getenv("WALLET_MONITOR_MIN_BUY_USD", "500"))      # skip buys < $500 (noise)
WALLET_MONITOR_MAX_BUY_AGE = int(os.getenv("WALLET_MONITOR_MAX_BUY_AGE", "120"))        # 2 min max age
WALLET_MONITOR_TIER1_COUNT = int(os.getenv("WALLET_MONITOR_TIER1_COUNT", "3"))          # 3+ wallets = immediate
WALLET_MONITOR_TIER2_COUNT = int(os.getenv("WALLET_MONITOR_TIER2_COUNT", "2"))          # 2 wallets = express lane
WALLET_MONITOR_COPY_SIZE_PCT = float(os.getenv("WALLET_MONITOR_COPY_SIZE_PCT", "0.05"))  # 5% of our balance
WALLET_MONITOR_MAX_COPY_USD = float(os.getenv("WALLET_MONITOR_MAX_COPY_USD", "250"))    # cap at $250
WALLET_MONITOR_DEFAULT_COPY_USD = float(os.getenv("WALLET_MONITOR_DEFAULT_COPY_USD", "0"))  # 0 = skip unknown signals
WALLET_MONITOR_FASTLANE_ENABLED = os.getenv("WALLET_MONITOR_FASTLANE_ENABLED", "true").lower() == "true"
WALLET_MONITOR_FASTLANE_QUEUE_MAX = int(os.getenv("WALLET_MONITOR_FASTLANE_QUEUE_MAX", "200"))
COPYTRADE_LATENCY_SLO_SECONDS = float(os.getenv("COPYTRADE_LATENCY_SLO_SECONDS", "20"))
COPYTRADE_MAX_DELAY_REJECT_SECONDS = int(os.getenv("COPYTRADE_MAX_DELAY_REJECT_SECONDS", "180"))
COPYTRADE_DELAY_REDUCTION_START_SECONDS = int(os.getenv("COPYTRADE_DELAY_REDUCTION_START_SECONDS", "45"))

# Moralis Streams webhook ingestion (push-based low-latency detection)
MORALIS_STREAMS_ENABLED = os.getenv("MORALIS_STREAMS_ENABLED", "false").lower() == "true"
MORALIS_STREAMS_HOST = os.getenv("MORALIS_STREAMS_HOST", "0.0.0.0")
MORALIS_STREAMS_PORT = int(os.getenv("MORALIS_STREAMS_PORT", "8787"))
MORALIS_STREAMS_WEBHOOK_SECRET = os.getenv("MORALIS_STREAMS_WEBHOOK_SECRET", "")
# Public URL that Moralis will POST webhooks to (must be reachable from internet)
MORALIS_STREAMS_WEBHOOK_URL = os.getenv("MORALIS_STREAMS_WEBHOOK_URL", "")  # e.g. http://5.161.126.32:8787

# Streams Manager — auto-creates and syncs streams on Moralis
MORALIS_STREAMS_AUTO_SYNC = os.getenv("MORALIS_STREAMS_AUTO_SYNC", "true").lower() == "true"
MORALIS_STREAMS_HEALTH_INTERVAL = int(os.getenv("MORALIS_STREAMS_HEALTH_INTERVAL", "300"))  # 5 min

# Whale detection stream — requires Moralis Business plan (allAddresses=true)
MORALIS_STREAMS_WHALE_ENABLED = os.getenv("MORALIS_STREAMS_WHALE_ENABLED", "false").lower() == "true"
MORALIS_STREAMS_WHALE_MIN_USD = float(os.getenv("MORALIS_STREAMS_WHALE_MIN_USD", "50000"))  # $50K+ transfers

# Liquidity event stream — monitors DEX factory contracts for new pools
MORALIS_STREAMS_LIQUIDITY_ENABLED = os.getenv("MORALIS_STREAMS_LIQUIDITY_ENABLED", "false").lower() == "true"

# Hybrid mode — when streams are active, extend poll interval as fallback
MORALIS_STREAMS_FALLBACK_POLL_INTERVAL = int(os.getenv("MORALIS_STREAMS_FALLBACK_POLL_INTERVAL", "120"))  # 2 min
# Solana alpha wallets — verified Pump.fun/Raydium snipers (seeded 2026-04-04)
# .env ALPHA_WALLETS_SOLANA always takes priority over this hardcoded seed.
ALPHA_WALLETS_SOLANA: list[str] = list(dict.fromkeys([
    addr.strip() for addr in
    os.getenv("ALPHA_WALLETS_SOLANA", "").split(",")
    if addr.strip()
] + [
    "AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm",  # High-PNL Pump.fun meme sniper
    "4Be9CvxqHW6BYiRAxW9Q3xu1ycTMWaL5z8NX4HR3ha7t",  # Verified profitable early buyer
    "B6J251t6KbZhh7R6GhHJdwKQGj22dcck83AULtxNPSat",   # Consistent early Raydium entry
    "AMRsSeU5JpqwQWJGNLMpZzRCZSFEwYQYbMnms3dD4311",   # Raydium gem hunter
]))

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
# 65.0 = standard entry gate (conservative profile). Nuclear profile enforces 82.0 via StrategyProfile.
# Conservative profile: min_gem_score=65.0 | Nuclear profile: min_gem_score=82.0 (express-lane quality only)
MIN_GEM_SCORE = float(os.getenv("MIN_GEM_SCORE", "65.0"))
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
# Gas-vs-position-size guard: position must be >= this × estimated gas cost
# A ratio of 5 means a $10 gas trade requires a $50+ position to be profitable
MIN_POSITION_GAS_RATIO = float(os.getenv("MIN_POSITION_GAS_RATIO", "5.0"))
# Daily trade count cap: prevents gas burn on volatile days (0 = unlimited)
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "50"))

# ─────────────────────────────────────────────────────────────────────────────
# Capital Recovery Mode
# When a wallet's balance falls below CAPITAL_RECOVERY_THRESHOLD_USD,
# the bot switches to conservative recovery sizing:
#   - Position size capped at CAPITAL_RECOVERY_MAX_POSITION_PCT
#   - MIN_GEM_SCORE raised to CAPITAL_RECOVERY_MIN_SCORE
#   - Nuclear profile disabled for that wallet until balance recovers
#   - Max 2 concurrent positions while in recovery
# This prevents a depleted wallet from making desperate low-quality trades.
# ─────────────────────────────────────────────────────────────────────────────
CAPITAL_RECOVERY_ENABLED = os.getenv("CAPITAL_RECOVERY_ENABLED", "true").lower() == "true"
CAPITAL_RECOVERY_THRESHOLD_USD = float(os.getenv("CAPITAL_RECOVERY_THRESHOLD_USD", "15.0"))
CAPITAL_RECOVERY_MAX_POSITION_PCT = float(os.getenv("CAPITAL_RECOVERY_MAX_POSITION_PCT", "15.0"))
CAPITAL_RECOVERY_MIN_SCORE = float(os.getenv("CAPITAL_RECOVERY_MIN_SCORE", "62.0"))  # Raised from 55 → 62: no more junk entries during recovery
CAPITAL_RECOVERY_MAX_POSITIONS = int(os.getenv("CAPITAL_RECOVERY_MAX_POSITIONS", "3"))

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
UNDERPERFORMER_FLAT_HOURS = float(os.getenv("UNDERPERFORMER_FLAT_HOURS", "4.0"))   # FIX: project spec = 4h (was 12h — dead capital held too long)
UNDERPERFORMER_FLAT_PCT = float(os.getenv("UNDERPERFORMER_FLAT_PCT", "2.5"))    # FIX: project spec = ±2.5% (was ±5% — too lenient)

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
GOD_MODE_DAILY_PNL_THRESHOLD_USD = float(os.getenv("GOD_MODE_DAILY_PNL_THRESHOLD_USD", "250.0"))  # TUNED: was $500 — enter God Mode sooner
GOD_MODE_KELLY_MULTIPLIER = float(os.getenv("GOD_MODE_KELLY_MULTIPLIER", "2.5"))  # TUNED: was 2.0 — more aggressive in God Mode
GOD_MODE_TRAILING_STOP_PCT = float(os.getenv("GOD_MODE_TRAILING_STOP_PCT", "10.0"))  # TUNED: was 12% — tighter to protect God Mode gains
GOD_MODE_SKIP_TP1 = os.getenv("GOD_MODE_SKIP_TP1", "true").lower() == "true"

# Deactivate God Mode if daily PnL drops this much below the peak (protect gains)
GOD_MODE_MAX_DRAWDOWN_FROM_PEAK_USD = float(os.getenv("GOD_MODE_MAX_DRAWDOWN_FROM_PEAK_USD", "150.0"))  # TUNED: was $200 — protect gains more aggressively
# Lock and Coast: if daily PnL hits this, reduce max position size to protect the day's gains
DAILY_PROFIT_LOCK_THRESHOLD_USD = float(os.getenv("DAILY_PROFIT_LOCK_THRESHOLD_USD", "2000.0"))
  # Skip 2x sell

# ── 3. House Money Protocol ───────────────────────────────────────────────────
# Reinvests a % of each win's profit into a "house money pool".
# Pool is deployed as a bonus on top of the next high-conviction trade.
HOUSE_MONEY_ENABLED = os.getenv("HOUSE_MONEY_ENABLED", "true").lower() == "true"
HOUSE_MONEY_REINVEST_PCT = float(os.getenv("HOUSE_MONEY_REINVEST_PCT", "40.0"))  # TUNED: was 30% — compound harder from wins
HOUSE_MONEY_MAX_POOL_USD = float(os.getenv("HOUSE_MONEY_MAX_POOL_USD", "5000.0"))  # TUNED: was $2000 — bigger war chest
HOUSE_MONEY_MIN_DEPLOY_USD = float(os.getenv("HOUSE_MONEY_MIN_DEPLOY_USD", "10.0"))  # Min to deploy
HOUSE_MONEY_MAX_DEPLOY_PCT = float(os.getenv("HOUSE_MONEY_MAX_DEPLOY_PCT", "60.0"))  # TUNED: was 50% — deploy more per trade
HOUSE_MONEY_MAX_POSITION_MULT = float(os.getenv("HOUSE_MONEY_MAX_POSITION_MULT", "2.0"))  # TUNED: was 1.5x — allow 2x base on house money

# ── 4. Dynamic Profit Boost (enhanced from existing) ─────────────────────────
# Existing PROFIT_BOOST_* settings are the baseline.
# Large wins trigger an even bigger boost.
PROFIT_BOOST_MIN_GAIN_USD = float(os.getenv("PROFIT_BOOST_MIN_GAIN_USD", "30.0"))  # TUNED: was $50 — trigger boost on smaller wins
PROFIT_BOOST_LARGE_WIN_USD = float(os.getenv("PROFIT_BOOST_LARGE_WIN_USD", "300.0"))  # TUNED: was $500 — trigger large-win boost sooner
PROFIT_BOOST_LARGE_MULTIPLIER = float(os.getenv("PROFIT_BOOST_LARGE_MULTIPLIER", "2.0"))  # TUNED: was 1.75x — 2x bets after large wins
PROFIT_BOOST_LARGE_TRADES = int(os.getenv("PROFIT_BOOST_LARGE_TRADES", "7"))  # TUNED: was 5 — ride the streak 7 trades

# ── 5. Cascade Score Boost ────────────────────────────────────────────────────
# Each profitable trade lowers MIN_GEM_SCORE by CASCADE_BOOST_PER_WIN points.
# Allows more aggressive discovery as the bot builds a winning streak.
# Losses recover the threshold. Floor prevents going too low.
CASCADE_BOOST_ENABLED = os.getenv("CASCADE_BOOST_ENABLED", "true").lower() == "true"
CASCADE_BOOST_PER_WIN = float(os.getenv("CASCADE_BOOST_PER_WIN", "0.75"))  # FIX: project spec = 0.75 pts per win (was 0.5)
CASCADE_BOOST_MAX_REDUCTION = float(os.getenv("CASCADE_BOOST_MAX_REDUCTION", "5.0"))  # Reduced from 10 → 5: floor can't drop as far
CASCADE_BOOST_RECOVERY_PER_LOSS = float(os.getenv("CASCADE_BOOST_RECOVERY_PER_LOSS", "1.0"))  # +1 per loss
CASCADE_BOOST_FLOOR_SCORE = float(os.getenv("CASCADE_BOOST_FLOOR_SCORE", "58.0"))  # Raised from 40 → 58: hard quality floor

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
FAST_FAIL_STALL_HOURS = float(os.getenv("FAST_FAIL_STALL_HOURS", "3.0"))  # TUNED: was 4h — cut stalls faster
FAST_FAIL_STALL_PCT = float(os.getenv("FAST_FAIL_STALL_PCT", "20.0"))  # TUNED: was 15% — must show stronger momentum to survive
FAST_FAIL_VOLUME_COLLAPSE_PCT = float(os.getenv("FAST_FAIL_VOLUME_COLLAPSE_PCT", "70.0"))  # TUNED: was 80% — exit sooner on volume death

# ── 9. Momentum Reentry ───────────────────────────────────────────────────────
# After TP1 is hit on a token, immediately re-enters if volume is still surging.
# Captures the second leg of a pump (common in micro-caps).
MOMENTUM_REENTRY_ENABLED = os.getenv("MOMENTUM_REENTRY_ENABLED", "true").lower() == "true"
MOMENTUM_REENTRY_VOLUME_MULT = float(os.getenv("MOMENTUM_REENTRY_VOLUME_MULT", "3.0"))  # Vol must be 3x avg
MOMENTUM_REENTRY_MAX_AGE_MINUTES = float(os.getenv("MOMENTUM_REENTRY_MAX_AGE_MINUTES", "60.0"))  # 30min window
MOMENTUM_REENTRY_SIZE_MULT = float(os.getenv("MOMENTUM_REENTRY_SIZE_MULT", "1.25"))  # 1.25x normal size

# ── 10. Absolute Position Cap ─────────────────────────────────────────────────
# Hard cap on any single trade after all offensive multipliers are applied.
# Prevents runaway sizing even on a 6-win streak in God Mode.
OFFENSIVE_MAX_POSITION_USD = float(os.getenv("OFFENSIVE_MAX_POSITION_USD", "5000.0"))
# Auto-scaling cap: max % of wallet balance per trade (overrides fixed USD cap when wallet grows)
# e.g., 30% of a $20K wallet = $6K max position — grows with the wallet
OFFENSIVE_MAX_POSITION_WALLET_PCT = float(os.getenv("OFFENSIVE_MAX_POSITION_WALLET_PCT", "30.0"))
# Auto-compound: % of Wallet B TP profits flagged for rebalancing to Primary
# 50% means half of nuclear TP profits build the safety net, other half keeps compounding
AUTO_COMPOUND_PCT = float(os.getenv("AUTO_COMPOUND_PCT", "50.0"))

# ── 11. Blitz Mode (Synergy Bonus) ────────────────────────────────────────────
# When 3+ offensive conditions align (e.g. God Mode + Hot Streak + Express Lane),
# apply an extra multiplier to maximize the perfect setup.
BLITZ_MODE_ENABLED = os.getenv("BLITZ_MODE_ENABLED", "true").lower() == "true"
BLITZ_MODE_MULTIPLIER = float(os.getenv("BLITZ_MODE_MULTIPLIER", "1.25"))

# ── 12. Loss Streak Cooling ───────────────────────────────────────────────────
# Increase MIN_GEM_SCORE threshold on losing streaks to force the bot to be pickier.
LOSS_STREAK_COOLING_ENABLED = os.getenv("LOSS_STREAK_COOLING_ENABLED", "true").lower() == "true"
LOSS_STREAK_SCORE_PENALTY = float(os.getenv("LOSS_STREAK_SCORE_PENALTY", "2.0"))  # +2 pts per loss (was 5 — too aggressive)
LOSS_STREAK_MAX_PENALTY = float(os.getenv("LOSS_STREAK_MAX_PENALTY", "10.0"))     # Max +10 pts


# ─────────────────────────────────────────────────────────────────────────────
# Smart Money Tracking
# ─────────────────────────────────────────────────────────────────────────────
# Known smart money / whale wallet addresses to track across chains
# SOURCE OF TRUTH: .env ALPHA_WALLETS_EVM — all wallets are Moralis on-chain
# verified (audited 2026-04-05 via getWalletProfitabilitySummary).
# NO hardcoded fallbacks — if the env var is empty, monitor is disabled by design.
_ALPHA_EVM_ENV: list[str] = [
    addr.strip() for addr in
    os.getenv("ALPHA_WALLETS_EVM", "").split(",")
    if addr.strip()
]
SMART_MONEY_WALLETS: list[str] = list(dict.fromkeys(_ALPHA_EVM_ENV))


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
    "binance_pulse": 60,  # Binance Web3 Pulse APIs — no key, conservative
}

# ─────────────────────────────────────────────────────────────────────────────
# Binance Pulse (Free Web3 APIs — no key required)
# ─────────────────────────────────────────────────────────────────────────────
BINANCE_PULSE_ENABLED = os.getenv("BINANCE_PULSE_ENABLED", "true").lower() == "true"

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
        # Note: MAX_POSITION_SIZE_PERCENT is a global fallback only.
        # Wallet B (nuclear) legitimately uses 60%+ sizing via StrategyProfile.
        # Only warn if the global fallback itself is dangerously high (>10%).
        if MAX_POSITION_SIZE_PERCENT > 10.0:
            warnings_list.append(f"LIVE MODE: MAX_POSITION_SIZE_PERCENT={MAX_POSITION_SIZE_PERCENT}% global fallback is very high — per-wallet profiles should override this")
        if CIRCUIT_BREAKER_PERCENT > 20.0:
            warnings_list.append(f"LIVE MODE: CIRCUIT_BREAKER_PERCENT={CIRCUIT_BREAKER_PERCENT}% is very high")

    if not CMC_API_KEY:
        warnings_list.append("CMC_API_KEY not set — CoinMarketCap data unavailable")

    if not MORALIS_API_KEY:
        warnings_list.append(
            "MORALIS_API_KEY not set — Moralis enrichment (~27% of gem score) unavailable. "
            "Gem quality will be severely degraded. Set MORALIS_API_KEY in your .env or server environment."
        )

    if not GROK_API_KEY:
        warnings_list.append("GROK_API_KEY not set — Grok sentiment scoring (5% weight) disabled. Meaningful impact on narrative-driven tokens.")  # FIX: was 2% — Grok boosted to 5%

    _sol_pk_primary = os.getenv("SOLANA_PRIVATE_KEY_PRIMARY", "")
    _sol_pk_b = os.getenv("SOLANA_PRIVATE_KEY_B", "")
    if not _sol_pk_primary and not _sol_pk_b:
        warnings_list.append(
            "SOLANA_PRIVATE_KEY_PRIMARY and SOLANA_PRIVATE_KEY_B both unset — "
            "Solana trading fully disabled. Set these in your server environment to enable Solana."
        )

    if not ETHERSCAN_API_KEY:
        warnings_list.append("ETHERSCAN_API_KEY not set — contract verification on Ethereum limited to 5 req/sec")

    if not BASESCAN_API_KEY:
        warnings_list.append("BASESCAN_API_KEY not set — contract verification on Base limited to 5 req/sec")

    if MIN_GEM_SCORE < 55.0:
        warnings_list.append(f"MIN_GEM_SCORE={MIN_GEM_SCORE} is very low — may produce low-quality candidates (nuclear profile min=72.0, conservative min=58.0)")

    return warnings_list
