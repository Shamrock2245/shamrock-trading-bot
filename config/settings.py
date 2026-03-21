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

# ─────────────────────────────────────────────────────────────────────────────
# Data Provider API Keys
# ─────────────────────────────────────────────────────────────────────────────
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
TOKEN_SNIFFER_API_KEY = os.getenv("TOKEN_SNIFFER_API_KEY", "")

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

# ─────────────────────────────────────────────────────────────────────────────
# Chain Configuration
# ─────────────────────────────────────────────────────────────────────────────
_active_chains_env = os.getenv("ACTIVE_CHAINS", "ethereum,base,arbitrum,polygon,bsc")
ACTIVE_CHAINS: list[str] = [c.strip().lower() for c in _active_chains_env.split(",") if c.strip()]

# ─────────────────────────────────────────────────────────────────────────────
# Scanner Settings
# ─────────────────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
MIN_GEM_SCORE = float(os.getenv("MIN_GEM_SCORE", "65"))
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "50000"))
MAX_TOKEN_AGE_HOURS = int(os.getenv("MAX_TOKEN_AGE_HOURS", "168"))
MAX_TRADES_PER_CYCLE = int(os.getenv("MAX_TRADES_PER_CYCLE", "3"))

# ─────────────────────────────────────────────────────────────────────────────
# Technical Analysis & Fibonacci (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────
REQUIRE_FIB_ALIGNMENT = os.getenv("REQUIRE_FIB_ALIGNMENT", "true").lower() == "true"
MIN_SIGNAL_SCORE = float(os.getenv("MIN_SIGNAL_SCORE", "55.0"))
OHLCV_LOOKBACK_DAYS = int(os.getenv("OHLCV_LOOKBACK_DAYS", "7"))
FIB_PROXIMITY_PCT = float(os.getenv("FIB_PROXIMITY_PCT", "3.0"))
FIB_SWING_WINDOW = int(os.getenv("FIB_SWING_WINDOW", "3"))
TA_ENABLED = os.getenv("TA_ENABLED", "true").lower() == "true"

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

    return warnings_list
