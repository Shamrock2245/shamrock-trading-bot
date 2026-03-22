"""
scanner/gem_scanner.py — Multi-chain gem discovery and scoring engine.

Scans DexScreener for new/boosted tokens across Ethereum, Base, Arbitrum,
Polygon, BSC, and Solana. Scores each candidate 0–100 using weighted criteria
and returns a ranked list of GemCandidates ready for safety checks and execution.

Scoring weights (rebalanced, sum = 100%):
  - Token age:                12%
  - Volume spike:             17%
  - Liquidity depth:          13%
  - Contract verified:         8%
  - Holder distribution:       8%
  - Buy/sell tax:              8%
  - Social signals:            8%  ← real social scoring (LunarCrush + CoinGecko)
  - DexScreener boost:         4%
  - Smart money:               4%  ← real wallet overlap scoring
  - TVL (DefiLlama):           5%
  - Social sentiment (LC):     5%
  - Holder concentration:      4%
  - Unlock/dilution risk:      4%
  - Honeypot: PASS/FAIL (instant disqualify)
"""

import logging
from typing import Optional

from config.chains import DEXSCREENER_CHAIN_MAP
from config import settings
from data.models import Token, GemCandidate
from data.providers.dexscreener import (
    get_latest_token_profiles,
    get_latest_boosts,
    get_top_boosts,
    extract_gem_signals,
    get_token_pairs,
)
from data.providers.defillama import get_tvl_score
from data.providers.social_scoring import get_social_score
from data.providers.smart_money import get_smart_money_score
from data.providers.holder_analysis import get_holder_score
from data.providers.token_unlocks import get_unlock_risk_score

logger = logging.getLogger(__name__)

# All supported chains including Solana
SCAN_CHAINS = ["ethereum", "base", "arbitrum", "polygon", "bsc", "solana"]

# DexScreener chain ID → internal chain name (including Solana)
_DEXSCREENER_CHAIN_MAP = {
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon",
    "bsc": "bsc",
    "solana": "solana",
}


class GemScanner:
    """
    Discovers and scores gem candidates across all configured chains.
    Implements the Alex Becker / top-trader playbook:
      - Catch new launches in the first 1-6 hours
      - Prioritize volume spikes (>5x hourly average)
      - Require smart money overlap or strong social momentum
      - Express lane for score ≥ 82 (skip full TA, execute immediately)
    """

    def scan(self) -> list[GemCandidate]:
        """
        Run a full scan cycle.
        1. Fetch latest profiles + boosts (latest + top) from DexScreener
        2. Score each token 0–100
        3. Filter by minimum score threshold
        4. Return ranked list (highest score first)
        """
        logger.info("Starting gem scan cycle...")
        candidates: list[GemCandidate] = []
        seen_addresses: set[str] = set()

        # ── Source 1: Latest token profiles ──────────────────────────────────
        profiles = get_latest_token_profiles()
        logger.info(f"Fetched {len(profiles)} latest token profiles")
        for profile in profiles:
            token_addr = profile.get("tokenAddress", "")
            chain_id = profile.get("chainId", "")
            chain = self._dexscreener_to_chain(chain_id)
            if not chain or not token_addr:
                continue
            if chain not in settings.ACTIVE_CHAINS:
                continue
            if token_addr.lower() in seen_addresses:
                continue
            pairs = get_token_pairs(token_addr)
            for pair in pairs:
                signals = extract_gem_signals(pair)
                token = self._signals_to_token(signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=False)
                    if candidate.gem_score >= settings.MIN_GEM_SCORE:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    break  # Use first (most liquid) pair only

        # ── Source 2: Latest boosts ───────────────────────────────────────────
        boosts = get_latest_boosts()
        logger.info(f"Fetched {len(boosts)} latest boosts")
        for boost in boosts:
            token_addr = boost.get("tokenAddress", "")
            chain_id = boost.get("chainId", "")
            chain = self._dexscreener_to_chain(chain_id)
            boost_amount = int(boost.get("amount", 0) or 0)
            if not chain or not token_addr:
                continue
            if chain not in settings.ACTIVE_CHAINS:
                continue
            if token_addr.lower() in seen_addresses:
                continue
            pairs = get_token_pairs(token_addr)
            for pair in pairs:
                signals = extract_gem_signals(pair)
                signals["is_boosted"] = True
                signals["boost_amount"] = boost_amount
                token = self._signals_to_token(signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=True)
                    if candidate.gem_score >= settings.MIN_GEM_SCORE:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    break

        # ── Source 3: Top boosts (strongest community push) ───────────────────
        top_boosts = get_top_boosts()
        logger.info(f"Fetched {len(top_boosts)} top boosts")
        for boost in top_boosts:
            token_addr = boost.get("tokenAddress", "")
            chain_id = boost.get("chainId", "")
            chain = self._dexscreener_to_chain(chain_id)
            boost_amount = int(boost.get("amount", 0) or 0)
            if not chain or not token_addr:
                continue
            if chain not in settings.ACTIVE_CHAINS:
                continue
            if token_addr.lower() in seen_addresses:
                continue
            pairs = get_token_pairs(token_addr)
            for pair in pairs:
                signals = extract_gem_signals(pair)
                signals["is_boosted"] = True
                signals["boost_amount"] = boost_amount
                token = self._signals_to_token(signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=True)
                    if candidate.gem_score >= settings.MIN_GEM_SCORE:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    break

        # ── Sort by score descending ──────────────────────────────────────────
        candidates.sort(key=lambda c: c.gem_score, reverse=True)
        express_count = sum(1 for c in candidates if c.gem_score >= settings.EXPRESS_LANE_SCORE)
        logger.info(
            f"Scan complete: {len(candidates)} candidates above "
            f"score threshold {settings.MIN_GEM_SCORE} "
            f"({express_count} express lane)"
        )
        return candidates

    def _score_token(self, token: Token, is_boosted: bool = False) -> GemCandidate:
        """
        Score a token 0–100 using weighted criteria.
        Returns a GemCandidate with all score components populated.

        Phase 3 rebalanced weights (13 signals, sum = 100%):
            age=12%, volume=17%, liquidity=13%, contract=8%, holder=8%,
            tax=8%, social=8%, boost=4%, smart_money=4%,
            tvl=5%, social_sentiment=5%, holder_conc=4%, unlock_risk=4%
        """
        candidate = GemCandidate(token=token)

        # ── Age score (12%) ───────────────────────────────────────────────────
        if token.age_hours is not None:
            if token.age_hours < 1:
                candidate.age_score = 100
            elif token.age_hours < 6:
                candidate.age_score = 90
            elif token.age_hours < 24:
                candidate.age_score = 75
            elif token.age_hours < 72:
                candidate.age_score = 50
            elif token.age_hours < 168:
                candidate.age_score = 25
            else:
                candidate.age_score = 10

        # ── Volume spike score (17%) ──────────────────────────────────────────
        if token.volume_1h > 0 and token.volume_24h > 0:
            avg_hourly_vol = token.volume_24h / 24
            if avg_hourly_vol > 0:
                spike_ratio = token.volume_1h / avg_hourly_vol
                if spike_ratio >= 10:
                    candidate.volume_score = 100
                elif spike_ratio >= 5:
                    candidate.volume_score = 85
                elif spike_ratio >= 3:
                    candidate.volume_score = 70
                elif spike_ratio >= 2:
                    candidate.volume_score = 50
                else:
                    candidate.volume_score = 20
        elif token.volume_24h >= 500_000:
            candidate.volume_score = 60
        elif token.volume_24h >= 100_000:
            candidate.volume_score = 40

        # ── Liquidity score (13%) ─────────────────────────────────────────────
        liq = token.liquidity_usd
        if liq >= 500_000:
            candidate.liquidity_score = 100
        elif liq >= 200_000:
            candidate.liquidity_score = 85
        elif liq >= 100_000:
            candidate.liquidity_score = 70
        elif liq >= 50_000:
            candidate.liquidity_score = 50
        elif liq >= 20_000:
            candidate.liquidity_score = 25
        else:
            candidate.liquidity_score = 0

        # ── Tax score (8%) ────────────────────────────────────────────────────
        max_tax = max(token.buy_tax, token.sell_tax)
        if max_tax == 0:
            candidate.tax_score = 100
        elif max_tax <= 0.01:
            candidate.tax_score = 85
        elif max_tax <= 0.03:
            candidate.tax_score = 60
        elif max_tax <= 0.05:
            candidate.tax_score = 30
        else:
            candidate.tax_score = 0

        # ── Holder distribution score (8%) ────────────────────────────────────
        if token.holder_count >= 1000:
            candidate.holder_score = 100
        elif token.holder_count >= 500:
            candidate.holder_score = 80
        elif token.holder_count >= 200:
            candidate.holder_score = 60
        elif token.holder_count >= 100:
            candidate.holder_score = 40
        elif token.holder_count >= 50:
            candidate.holder_score = 20
        else:
            candidate.holder_score = 10

        # ── Social signals score (8%) — REAL scoring ─────────────────────────
        # Uses social_scoring.py: DexScreener profile links + LunarCrush + CoinGecko
        try:
            candidate.social_score = get_social_score(
                symbol=token.symbol,
                websites=getattr(token, "websites", []),
                socials=getattr(token, "socials", []),
                buys_1h=getattr(token, "buys_1h", 0),
                sells_1h=getattr(token, "sells_1h", 0),
                volume_1h=token.volume_1h,
                market_cap=token.market_cap,
                is_boosted=is_boosted,
                boost_amount=getattr(token, "boost_amount", 0),
            )
        except Exception as e:
            logger.debug(f"Social scoring failed for {token.symbol}: {e}")
            candidate.social_score = 30.0

        # ── DexScreener boost score (4%) ──────────────────────────────────────
        if is_boosted:
            boost_amount = getattr(token, "boost_amount", 0)
            if boost_amount >= 500:
                candidate.boost_score = 100
            elif boost_amount >= 200:
                candidate.boost_score = 80
            elif boost_amount >= 100:
                candidate.boost_score = 60
            elif boost_amount > 0:
                candidate.boost_score = 40
        else:
            candidate.boost_score = 0

        # ── Smart money score (4%) — REAL wallet overlap ──────────────────────
        try:
            candidate.smart_money_score = get_smart_money_score(token.address, token.chain)
        except Exception as e:
            logger.debug(f"Smart money scoring failed for {token.symbol}: {e}")
            candidate.smart_money_score = 0.0

        # ── Contract verified score (8%) ──────────────────────────────────────
        # Default 70 — updated by GoPlus safety check in executor
        candidate.contract_score = 70

        # ── Initial composite (before enrichment) ─────────────────────────────
        base_score = (
            candidate.age_score * 0.12
            + candidate.volume_score * 0.17
            + candidate.liquidity_score * 0.13
            + candidate.contract_score * 0.08
            + candidate.holder_score * 0.08
            + candidate.tax_score * 0.08
            + candidate.social_score * 0.08
            + candidate.boost_score * 0.04
            + candidate.smart_money_score * 0.04
        )

        # ── Enhanced signal enrichment (Phase 3) ──────────────────────────────
        # Only query external APIs for candidates that pass initial screening
        # to conserve rate limits (especially LunarCrush: 100 req/day).
        if base_score >= 45:
            try:
                candidate.tvl_score = get_tvl_score(token.address, token.chain)
            except Exception as e:
                logger.debug(f"TVL scoring failed for {token.symbol}: {e}")
                candidate.tvl_score = 30.0

            try:
                # social_sentiment_score uses LunarCrush galaxy score
                from data.providers.lunarcrush import get_social_score as get_lc_score
                candidate.social_sentiment_score = get_lc_score(token.symbol)
            except Exception as e:
                logger.debug(f"LunarCrush scoring failed for {token.symbol}: {e}")
                candidate.social_sentiment_score = 30.0

            try:
                candidate.holder_concentration_score = get_holder_score(
                    token.address, token.chain
                )
            except Exception as e:
                logger.debug(f"Holder analysis failed for {token.symbol}: {e}")
                candidate.holder_concentration_score = 40.0

            try:
                candidate.unlock_risk_score = get_unlock_risk_score(
                    token.address, token.chain
                )
            except Exception as e:
                logger.debug(f"Unlock risk scoring failed for {token.symbol}: {e}")
                candidate.unlock_risk_score = 50.0
        else:
            candidate.tvl_score = 30.0
            candidate.social_sentiment_score = 30.0
            candidate.holder_concentration_score = 40.0
            candidate.unlock_risk_score = 50.0

        # ── Final composite score (13 signals) ────────────────────────────────
        candidate.gem_score = round(
            candidate.age_score * 0.12
            + candidate.volume_score * 0.17
            + candidate.liquidity_score * 0.13
            + candidate.contract_score * 0.08
            + candidate.holder_score * 0.08
            + candidate.tax_score * 0.08
            + candidate.social_score * 0.08
            + candidate.boost_score * 0.04
            + candidate.smart_money_score * 0.04
            + candidate.tvl_score * 0.05
            + candidate.social_sentiment_score * 0.05
            + candidate.holder_concentration_score * 0.04
            + candidate.unlock_risk_score * 0.04,
            2,
        )

        # ── Express lane flag ─────────────────────────────────────────────────
        candidate.express_lane = candidate.gem_score >= settings.EXPRESS_LANE_SCORE

        return candidate

    def _signals_to_token(self, signals: dict, chain: str) -> Optional[Token]:
        """Convert DexScreener signals dict to a Token object."""
        address = signals.get("base_token_address", "")
        symbol = signals.get("base_token_symbol", "")
        if not address or not symbol:
            return None

        # Filter by minimum liquidity
        if signals.get("liquidity_usd", 0) < settings.MIN_LIQUIDITY_USD:
            return None

        token = Token(
            address=address,
            symbol=symbol,
            name=signals.get("base_token_name", symbol),
            chain=chain,
            pair_address=signals.get("pair_address", ""),
            price_usd=signals.get("price_usd", 0.0),
            market_cap=signals.get("market_cap", 0.0),
            liquidity_usd=signals.get("liquidity_usd", 0.0),
            volume_24h=signals.get("volume_24h", 0.0),
            volume_1h=signals.get("volume_1h", 0.0),
            price_change_1h=signals.get("price_change_1h", 0.0),
            price_change_24h=signals.get("price_change_24h", 0.0),
            age_hours=signals.get("age_hours"),
            is_boosted=signals.get("is_boosted", False),
            boost_amount=signals.get("boost_amount", 0),
            dex_url=signals.get("url", ""),
        )

        # Attach social metadata for scoring
        token.websites = signals.get("websites", [])
        token.socials = signals.get("socials", [])
        token.buys_1h = signals.get("buys_1h", 0)
        token.sells_1h = signals.get("sells_1h", 0)

        return token

    @staticmethod
    def _dexscreener_to_chain(dexscreener_chain_id: str) -> Optional[str]:
        """Map DexScreener chain ID string to our internal chain name."""
        return _DEXSCREENER_CHAIN_MAP.get(dexscreener_chain_id.lower())
