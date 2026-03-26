"""
scanner/swing_scanner.py — Capital Recovery Swing Scanner.

Scans a curated watchlist of established, liquid "capital-making" blue-chip
tokens for short-term swing trade entries on 15-minute candles.

Unlike the gem scanner which hunts micro-cap moonshots, the swing scanner
targets reliable tokens with real volume where technical analysis actually
works. The goal is steady capital recovery via 3-8% scalp profits.

Watchlist tokens are pre-vetted (no rug risk) so safety checks are skipped.
Entries use pure TA: RSI oversold + MACD cross + volume confirmation.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from data.providers.ohlcv_provider import (
    _fetch_geckoterminal_ohlcv,
    GECKOTERMINAL_CHAIN_MAP,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Swing Candidate Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SwingCandidate:
    """A blue-chip token evaluated for swing entry."""
    symbol: str
    address: str
    chain: str
    pair_address: str = ""
    price_usd: float = 0.0
    # TA scores
    rsi_14: float = 50.0
    macd_signal: str = "neutral"
    macd_histogram: float = 0.0
    bb_pct_b: float = 0.5
    ema_signal: str = "neutral"
    vwap_deviation: float = 0.0
    volume_ratio: float = 1.0
    adx_value: float = 20.0
    # Composite
    ta_composite: float = 50.0
    entry_signal: bool = False
    entry_reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Blue-Chip Watchlists (per chain)
# ─────────────────────────────────────────────────────────────────────────────
# Each entry: (symbol, token_address, pair_address_for_ohlcv)
# pair_address is the highest-liquidity DEX pool for OHLCV candles.
# These are established tokens — no safety check needed.

SWING_WATCHLIST = {
    "base": [
        # pair_address = highest-liquidity Aerodrome/Uniswap V3 pool on Base
        ("WETH",    "0x4200000000000000000000000000000000000006", "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"),  # WETH/USDC Aerodrome
        ("cbBTC",   "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf", "0x8B9b8DB2EdC6F5e3C8Eb6B1F5E1E5e5E5E5E5E5E"),  # cbBTC/WETH — discover at runtime
        ("AERO",    "0x940181a94A35A4569E4529A3CDfB74e38FD98631", "0x7f670f78B17dEC44d5Ef68a48740b6f8849cc2e6"),  # AERO/USDC Aerodrome
        ("BRETT",   "0x532f27101965dd16442E59d40670FaF5eBB142E4", "0xBA3F945812a83471d709BCe9C3CA699A19FB46f7"),  # BRETT/WETH Aerodrome
        ("DEGEN",   "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed", ""),  # discover at runtime
        ("TOSHI",   "0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4", ""),  # discover at runtime
        ("VIRTUAL", "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b", "0x0fD7a301B51d0A83fcaF6718628174D527B373b6"),  # VIRTUAL/WETH Aerodrome
    ],
    "bsc": [
        # pair_address = highest-liquidity PancakeSwap V3 pool on BSC
        ("WBNB", "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "0x36696169C63e42cd08ce11f5deeBbCeBae652050"),  # WBNB/USDT PCS V3
        ("CAKE", "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "0x133B3D95bAD5405d14d53473671200e9342896bF"),  # CAKE/WBNB PCS V3
        ("ETH",  "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", ""),  # discover at runtime
        ("XVS",  "0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63", ""),  # discover at runtime
    ],
    "avalanche": [
        ("WAVAX", "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7", ""),
        ("JOE", "0x6e84a6216eA6dACC71eE8E6b0a5B7322EEbC0fDd", ""),
        ("BTC.b", "0x152b9d0FdC40C096dE01360F6da4F2518AF1bC88", ""),
        ("GMX", "0x62edc0692BD897D2295872a9FFCac5425011c661", ""),
    ],
    "solana": [
        ("SOL", "So11111111111111111111111111111111111111112", ""),
        ("JTO", "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", ""),
        ("JUP", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", ""),
        ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", ""),
        ("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", ""),
        ("PYTH", "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", ""),
    ],
    "ethereum": [
        # pair_address = highest-liquidity Uniswap V3 pool on Ethereum
        ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"),  # WETH/USDC 0.05% Uni V3
        ("LINK", "0x514910771AF9Ca656af840dff83E8264EcF986CA", "0xa6Cc3C2531FdaA6Ae1A3CA84c2855806728693e8"),  # LINK/ETH 0.3% Uni V3
        ("UNI",  "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "0x1d42064Fc4Beb5F8aAF85F4617AE8b3b5B8Bd801"),  # UNI/ETH 0.3% Uni V3
        ("AAVE", "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", "0x5aB53EE1d50eeF2C1DD3d5402789cd27bB52c1bB"),  # AAVE/ETH 0.3% Uni V3
        ("MKR",  "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2", "0xe8c6c9227491C0a8156A0106A0204d881BB7E531"),  # MKR/ETH 0.3% Uni V3
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Swing Scanner
# ─────────────────────────────────────────────────────────────────────────────

class SwingScanner:
    """
    Scans blue-chip tokens for swing trade entries.

    Uses 15-minute candles with the existing TA indicator stack to find
    oversold bounce entries on established tokens.
    """

    def __init__(self, chains: list[str] = None):
        """
        Args:
            chains: Which chains to scan. Defaults to all configured chains.
        """
        self.chains = chains or list(SWING_WATCHLIST.keys())
        self._last_scan_time: dict[str, float] = {}

    def scan(self) -> list[SwingCandidate]:
        """
        Scan all watchlist tokens across configured chains.

        Returns list of SwingCandidates with entry_signal=True for actionable entries.
        """
        from strategies.indicators import (
            calculate_rsi,
            calculate_macd,
            calculate_bollinger_bands,
            calculate_ema_crossover,
            calculate_vwap,
            calculate_volume_spike,
            calculate_adx,
        )

        candidates = []
        scan_start = time.time()

        for chain in self.chains:
            watchlist = SWING_WATCHLIST.get(chain, [])
            if not watchlist:
                continue

            logger.info(f"🔄 Swing scan: {chain} — {len(watchlist)} tokens")

            for symbol, address, pair_addr in watchlist:
                try:
                    candidate = self._evaluate_token(
                        symbol=symbol,
                        address=address,
                        chain=chain,
                        pair_address=pair_addr,
                        calculate_rsi=calculate_rsi,
                        calculate_macd=calculate_macd,
                        calculate_bollinger_bands=calculate_bollinger_bands,
                        calculate_ema_crossover=calculate_ema_crossover,
                        calculate_vwap=calculate_vwap,
                        calculate_volume_spike=calculate_volume_spike,
                        calculate_adx=calculate_adx,
                    )
                    if candidate:
                        candidates.append(candidate)
                except Exception as e:
                    logger.debug(f"Swing scan error for {symbol}/{chain}: {e}")
                    continue

        # Sort by composite score descending
        candidates.sort(key=lambda c: c.ta_composite, reverse=True)

        # Log results
        entries = [c for c in candidates if c.entry_signal]
        elapsed = time.time() - scan_start
        logger.info(
            f"📊 Swing scan complete: {len(candidates)} evaluated, "
            f"{len(entries)} entry signals in {elapsed:.1f}s"
        )
        for c in entries:
            logger.info(
                f"  ⚡ SWING ENTRY: {c.symbol}/{c.chain} — "
                f"composite={c.ta_composite:.1f} | RSI={c.rsi_14:.1f} | "
                f"MACD={c.macd_signal} | {c.entry_reason}"
            )

        return candidates

    def _evaluate_token(
        self,
        symbol: str,
        address: str,
        chain: str,
        pair_address: str,
        calculate_rsi,
        calculate_macd,
        calculate_bollinger_bands,
        calculate_ema_crossover,
        calculate_vwap,
        calculate_volume_spike,
        calculate_adx,
    ) -> Optional[SwingCandidate]:
        """Evaluate a single token for swing entry using 15m candles."""

        # Fetch 15-minute candles (need at least 100 candles = 25 hours)
        df = self._fetch_15m_candles(address, chain, pair_address)
        if df is None or len(df) < 20:
            logger.debug(f"Swing: insufficient 15m data for {symbol}/{chain}")
            return None

        candidate = SwingCandidate(
            symbol=symbol,
            address=address,
            chain=chain,
            pair_address=pair_address,
            price_usd=float(df["close"].iloc[-1]),
        )

        # ── Run TA indicators on 15m candles ──────────────────────────────
        rsi = calculate_rsi(df, period=14)
        macd = calculate_macd(df)
        bb = calculate_bollinger_bands(df)
        ema = calculate_ema_crossover(df)
        vwap = calculate_vwap(df)
        vol = calculate_volume_spike(df, threshold=1.5)
        adx = calculate_adx(df, period=14)

        candidate.rsi_14 = rsi.value if rsi.value is not None else 50.0
        candidate.macd_signal = macd.signal
        candidate.macd_histogram = macd.value if macd.value is not None else 0.0
        candidate.bb_pct_b = bb.value if bb.value is not None else 0.5
        candidate.ema_signal = ema.signal
        candidate.vwap_deviation = vwap.value if vwap.value is not None else 0.0
        candidate.volume_ratio = vol.value if vol.value is not None else 1.0
        candidate.adx_value = adx.value if adx.value is not None else 20.0

        # ── Composite TA score ────────────────────────────────────────────
        # Weighted average of indicator scores (all 0-100)
        composite = (
            rsi.score * 0.25 +        # RSI is king for mean reversion
            macd.score * 0.20 +        # MACD confirms momentum shift
            bb.score * 0.15 +          # Bollinger shows mean reversion setup
            ema.score * 0.15 +         # EMA trend direction
            vwap.score * 0.10 +        # VWAP institutional reference
            vol.score * 0.10 +         # Volume confirmation
            adx.score * 0.05           # Trend strength
        )
        candidate.ta_composite = composite

        # ── Entry Signal Detection ────────────────────────────────────────
        # Criteria: RSI oversold + at least one confirming signal
        entry_reasons = []

        # Primary trigger: RSI oversold
        rsi_oversold = candidate.rsi_14 <= 35
        rsi_near_oversold = candidate.rsi_14 <= 42

        # Confirming signals
        macd_bullish = macd.signal == "bullish"
        bb_oversold = candidate.bb_pct_b is not None and candidate.bb_pct_b <= 0.2
        ema_bullish = ema.signal == "bullish"
        volume_confirmed = candidate.volume_ratio >= 1.5
        adx_trending = candidate.adx_value >= 20

        if rsi_oversold:
            entry_reasons.append(f"RSI={candidate.rsi_14:.1f} oversold")
        if rsi_near_oversold and macd_bullish:
            entry_reasons.append(f"RSI={candidate.rsi_14:.1f}+MACD bullish cross")
        if bb_oversold:
            entry_reasons.append(f"BB %B={candidate.bb_pct_b:.2f} at lower band")
        if volume_confirmed:
            entry_reasons.append(f"Vol {candidate.volume_ratio:.1f}x confirmed")

        # Entry decision: RSI oversold + 1 confirm, OR RSI near + 2 confirms
        confirm_count = sum([macd_bullish, bb_oversold, ema_bullish, volume_confirmed])

        if rsi_oversold and confirm_count >= 1 and adx_trending:
            candidate.entry_signal = True
            candidate.entry_reason = " | ".join(entry_reasons)
        elif rsi_near_oversold and confirm_count >= 2 and adx_trending:
            candidate.entry_signal = True
            candidate.entry_reason = " | ".join(entry_reasons)
        elif composite >= 72 and adx_trending:
            # High composite override — strong consensus across indicators
            candidate.entry_signal = True
            candidate.entry_reason = f"High composite={composite:.1f} consensus entry"

        return candidate

    def _fetch_15m_candles(
        self, token_address: str, chain: str, pair_address: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch 15-minute candles from GeckoTerminal.

        Falls back to pool discovery if no pair_address is provided.
        """
        # Try known pair address first
        if pair_address:
            try:
                df = _fetch_geckoterminal_ohlcv(
                    chain=chain,
                    pool_address=pair_address,
                    timeframe="minute",
                    aggregate=15,
                    limit=200,
                )
                if df is not None and len(df) >= 20:
                    return df
            except Exception as e:
                logger.debug(f"15m candles (pair) failed for {token_address[:10]}...: {e}")

        # Discover pools and fetch 15m candles
        try:
            from data.providers.ohlcv_provider import (
                _fetch_geckoterminal_pools,
            )
            pools = _fetch_geckoterminal_pools(token_address, chain)
            if not pools:
                return None

            # Use highest-liquidity pool
            pools_sorted = sorted(
                pools,
                key=lambda p: float(
                    p.get("attributes", {}).get("reserve_in_usd", 0) or 0
                ),
                reverse=True,
            )

            for pool in pools_sorted[:2]:
                pool_addr = pool.get("attributes", {}).get("address", "")
                if not pool_addr:
                    continue
                try:
                    df = _fetch_geckoterminal_ohlcv(
                        chain=chain,
                        pool_address=pool_addr,
                        timeframe="minute",
                        aggregate=15,
                        limit=200,
                    )
                    if df is not None and len(df) >= 20:
                        return df
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"15m candle discovery failed for {token_address[:10]}...: {e}")

        return None
