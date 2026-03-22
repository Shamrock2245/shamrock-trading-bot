"""
config/tokens.py — Known token lists, blocklists, and whitelists.

Used by the safety pipeline to instantly block known scams and
whitelist trusted tokens that can skip certain checks.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Stablecoins (never trade these as gems — use as quote currency only)
# ─────────────────────────────────────────────────────────────────────────────
STABLECOINS: dict[str, dict] = {
    "USDC": {
        "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "base":     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "polygon":  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "bsc":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "solana":   "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    },
    "USDT": {
        "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "arbitrum": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "polygon":  "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "bsc":      "0x55d398326f99059fF775485246999027B3197955",
        "solana":   "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    },
    "DAI": {
        "ethereum": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "arbitrum": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "polygon":  "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
    },
    "WETH": {
        "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "base":     "0x4200000000000000000000000000000000000006",
        "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "polygon":  "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    },
    "WSOL": {
        "solana":   "So11111111111111111111111111111111111111112",
    },
}

# Flat set of all stablecoin addresses for quick lookup
# Includes both lowercase (EVM) and original case (Solana base58)
STABLECOIN_ADDRESSES: set[str] = set()
for _token_chains in STABLECOINS.values():
    for _addr in _token_chains.values():
        STABLECOIN_ADDRESSES.add(_addr.lower())
        STABLECOIN_ADDRESSES.add(_addr)  # Preserve original case for Solana


# ─────────────────────────────────────────────────────────────────────────────
# Permanent Blocklist — Known scams, rugs, and honeypots
# Add addresses here as they are discovered. Format: lowercase hex.
# ─────────────────────────────────────────────────────────────────────────────
PERMANENT_BLOCKLIST: set[str] = {
    # Add confirmed scam/rug addresses here as discovered
    # Example: "0xdeadbeef000000000000000000000000deadbeef",
}


# ─────────────────────────────────────────────────────────────────────────────
# Trusted Token Whitelist — Skip honeypot checks for these (blue chips only)
# ─────────────────────────────────────────────────────────────────────────────
TRUSTED_WHITELIST: set[str] = {
    # Ethereum mainnet blue chips
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",  # UNI
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",  # AAVE
    "0xd533a949740bb3306d119cc777fa900ba034cd52",  # CRV
    "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72",  # ENS
    # Solana blue chips (base58 mint addresses)
    "So11111111111111111111111111111111111111112",   # Wrapped SOL (WSOL)
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # Jupiter (JUP)
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", # Bonk (BONK)
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", # WIF (dogwifhat)
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", # PYTH
    "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",   # Jito (JTO)
    "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",   # Render (RNDR)
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def is_stablecoin(address: str) -> bool:
    """Check if a token address is a stablecoin."""
    return address in STABLECOIN_ADDRESSES or address.lower() in STABLECOIN_ADDRESSES


def is_blocked(address: str) -> bool:
    """Check if a token is on the permanent blocklist."""
    return address.lower() in PERMANENT_BLOCKLIST or address in PERMANENT_BLOCKLIST


def is_trusted(address: str) -> bool:
    """Check if a token is on the trusted whitelist."""
    return address in TRUSTED_WHITELIST or address.lower() in TRUSTED_WHITELIST


def add_to_blocklist(address: str, reason: str = "") -> None:
    """
    Dynamically add a token to the runtime blocklist.
    Note: This does not persist across restarts — update PERMANENT_BLOCKLIST
    in this file for permanent blocks.
    """
    PERMANENT_BLOCKLIST.add(address.lower())
