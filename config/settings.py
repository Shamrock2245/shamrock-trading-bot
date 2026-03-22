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
JUPITER_API_URL = os.getenv("JUPITER_API_URL", "https://quote-api.jup.ag/v6")

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
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

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
# Lowered from 65.0 → 55.0 to surface real candidates.
# Raise back to 60-65 once you confirm the scoring distribution.
MIN_GEM_SCORE = float(os.getenv("MIN_GEM_SCORE", "55.0"))
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
