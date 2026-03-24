"""
scanner/gem_scanner.py — Multi-chain gem discovery and scoring engine.

Scans DexScreener + Moralis for new/boosted/trending tokens across Ethereum,
Base, Arbitrum, Polygon, BSC, Avalanche, and Solana. Scores each candidate
0–100 using weighted criteria and returns a ranked list of GemCandidates
ready for safety checks and execution.

Data sources:
  1. DexScreener latest token profiles
  2. DexScreener latest boosts
  3. DexScreener top boosts
  4. DexScreener community takeovers (CTO Revival)
  5. DexScreener ads
  6. Moralis trending tokens + buying pressure (Pro plan)
  7. Gem Watchlist re-evaluation (near-miss tokens from prior cycles)

Scoring weights (rebalanced, 14 signals, sum = 100%):
  - Token age:                12%
  - Volume spike:             15%
  - Liquidity depth:          13%
  - Contract verified:         8%
  - Holder distribution:       8%
  - Buy/sell tax:              8%
  - Social signals:            6%  ← real social scoring (LunarCrush + CoinGecko)
  - DexScreener boost:         4%
  - Smart money:               4%  ← real wallet overlap scoring
  - TVL (DefiLlama):           5%
  - Social sentiment (LC):     5%
  - Holder concentration:      4%
  - Unlock/dilution risk:      4%
  - Grok X sentiment:          4%  ← Grok AI real-time X/Twitter analysis
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
    get_latest_community_takeovers,
    get_latest_ads,
    extract_gem_signals,
    get_token_pairs,
)
from data.providers.defillama import get_tvl_score
from data.providers.social_scoring import get_social_score
from data.providers.smart_money import get_smart_money_score
from data.providers.holder_analysis import get_holder_score
from data.providers.token_unlocks import get_unlock_risk_score
from data.providers.moralis_money import (
    discover_tokens as moralis_discover,
    enrich_candidate as moralis_enrich,
    calculate_moralis_score_contribution as moralis_score_contribution,
)
from scanner.watchlist import GemWatchlist, WATCHLIST_MIN_SCORE

logger = logging.getLogger(__name__)

# Chains to scan (EVM + Solana)
SCAN_CHAINS = ["ethereum", "base", "arbitrum", "polygon", "bsc", "avalanche", "solana"]

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
      - Re-evaluate near-miss tokens via watchlist (score 35-49)
    """

    def __init__(self):
        self.watchlist = GemWatchlist()

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
            pairs = get_token_pairs(token_addr) or []
            for pair in pairs:
                signals = extract_gem_signals(pair)
                token = self._signals_to_token(signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=False)
                    if candidate.gem_score >= settings.MIN_GEM_SCORE:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                        self.add_near_miss(token, candidate.gem_score, "profiles")
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
            pairs = get_token_pairs(token_addr) or []
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
                    elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                        self.add_near_miss(token, candidate.gem_score, "boosts")
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
            pairs = get_token_pairs(token_addr) or []
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
                    elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                        self.add_near_miss(token, candidate.gem_score, "top_boosts")
                    break

        # ── Source 4: Community takeovers (CTO Revival — top-tier signal) ──────
        # CTO = original dev abandoned, community took over and is pumping it.
        # Per docs/SIGNALS.md: CTO Revival is a high-profit setup — treat as
        # full-conviction express lane candidate if volume + social confirm.
        ctos = get_latest_community_takeovers()
        logger.info(f"Fetched {len(ctos)} community takeovers")
        for cto in ctos:
            token_addr = cto.get("tokenAddress", "")
            chain_id = cto.get("chainId", "")
            chain = self._dexscreener_to_chain(chain_id)
            if not chain or not token_addr:
                continue
            if chain not in settings.ACTIVE_CHAINS:
                continue
            if token_addr.lower() in seen_addresses:
                continue
            pairs = get_token_pairs(token_addr) or []
            for pair in pairs:
                signals = extract_gem_signals(pair)
                signals["is_boosted"] = True
                signals["boost_amount"] = 200   # CTO gets higher boost weight than regular boosts
                signals["is_cto"] = True        # CTO flag for scoring bonus
                token = self._signals_to_token(signals, chain)
                if token:
                    # CTO signal decay: only valid within 48h of CTO claim
                    # (per docs/SIGNALS.md stale-data window)
                    age_h = token.age_hours or 0
                    if age_h > 48:
                        logger.debug(f"CTO signal expired for {token.symbol} (age={age_h:.0f}h > 48h)")
                        break
                    candidate = self._score_token(token, is_boosted=True, is_cto=True)
                    if candidate.gem_score >= settings.MIN_GEM_SCORE:
                        candidates.append(candidate)
                    elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                        self.add_near_miss(token, candidate.gem_score, "cto_revival")
                        seen_addresses.add(token_addr.lower())
                    break

        # ── Source 5: Ads (funded team with marketing budget) ───────────────
        ads = get_latest_ads()
        logger.info(f"Fetched {len(ads)} latest ads")
        for ad in ads:
            token_addr = ad.get("tokenAddress", "")
            chain_id = ad.get("chainId", "")
            chain = self._dexscreener_to_chain(chain_id)
            if not chain or not token_addr:
                continue
            if chain not in settings.ACTIVE_CHAINS:
                continue
            if token_addr.lower() in seen_addresses:
                continue
            pairs = get_token_pairs(token_addr) or []
            for pair in pairs:
                signals = extract_gem_signals(pair)
                signals["is_boosted"] = True  # Ads = paid visibility signal
                signals["boost_amount"] = 50   # Moderate boost for ads
                token = self._signals_to_token(signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=True)
                    if candidate.gem_score >= settings.MIN_GEM_SCORE:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    break

        # ── Source 6: Moralis trending + buying pressure ──────────────────────
        # Moralis surfaces tokens with volume spikes and rising buy:sell ratios
        # across all chains. Each token gets pair data from DexScreener and
        # enters the same 14-signal scoring pipeline.
        try:
            moralis_tokens = moralis_discover(chains=settings.ACTIVE_CHAINS)
            moralis_added = 0
            for mt in moralis_tokens:
                token_addr = mt.get("token_address", "")
                chain = mt.get("chain", "")
                if not token_addr or not chain:
                    continue
                if chain not in settings.ACTIVE_CHAINS:
                    continue
                if token_addr.lower() in seen_addresses:
                    continue
                pairs = get_token_pairs(token_addr) or []
                for pair in pairs:
                    signals = extract_gem_signals(pair)
                    # Moralis trending = moderate boost signal
                    signals["is_boosted"] = True
                    signals["boost_amount"] = 75  # Moralis trending weight
                    token = self._signals_to_token(signals, chain)
                    if token:
                        candidate = self._score_token(token, is_boosted=True)
                        if candidate.gem_score >= settings.MIN_GEM_SCORE:
                            candidate.strategy_tag = "moralis_trending"
                            candidates.append(candidate)
                            seen_addresses.add(token_addr.lower())
                            moralis_added += 1
                        elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                            self.add_near_miss(token, candidate.gem_score, "moralis")
                        break
            if moralis_added:
                logger.info(f"Moralis: {moralis_added} tokens passed scoring")
        except Exception as e:
            logger.warning(f"Moralis discovery error: {e}")

        # ── Source 7: Watchlist re-evaluation (near-miss promotions) ───────────
        # Re-score watched tokens using fresh DexScreener data. Tokens that
        # improved since last cycle get promoted to full candidates.
        try:
            promoted = self.watchlist.re_evaluate(
                score_fn=self._watchlist_score_fn
            )
            for promo in promoted:
                token_addr = promo["token_address"]
                chain = promo["chain"]
                if token_addr.lower() in seen_addresses:
                    continue
                signals = promo["signals"]
                token = self._signals_to_token(signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=False)
                    candidate.gem_score = promo["score"]  # Use watchlist score
                    candidate.strategy_tag = "watchlist_promotion"
                    candidates.append(candidate)
                    seen_addresses.add(token_addr.lower())
                    logger.info(
                        f"☘️ Watchlist promoted {promo['symbol']} "
                        f"(score {promo['initial_score']:.1f} → {promo['score']:.1f}) "
                        f"after {promo['checks']} checks"
                    )
        except Exception as e:
            logger.warning(f"Watchlist re-evaluation error: {e}")

        # ── Sort by score descending ──────────────────────────────────────────
        candidates.sort(key=lambda c: c.gem_score, reverse=True)
        express_count = sum(1 for c in candidates if c.gem_score >= settings.EXPRESS_LANE_SCORE)
        logger.info(
            f"Scan complete: {len(candidates)} candidates above "
            f"score threshold {settings.MIN_GEM_SCORE} "
            f"({express_count} express lane) "
            f"| watchlist: {self.watchlist.size} tokens watched"
        )
        return candidates

    def _watchlist_score_fn(self, token_address: str, chain: str, signals: dict) -> float:
        """Scoring callback for watchlist re-evaluation."""
        token = self._signals_to_token(signals, chain)
        if not token:
            return 0.0
        candidate = self._score_token(token, is_boosted=False)
        return candidate.gem_score

    def add_near_miss(self, token: Token, score: float, source: str = ""):
        """Add a near-miss token to the watchlist for future re-evaluation."""
        self.watchlist.add_near_miss(
            token_address=token.address,
            chain=token.chain,
            symbol=token.symbol,
            name=token.name,
            score=score,
            source=source,
            pair_address=getattr(token, "pair_address", ""),
        )

    def _score_token(self, token: Token, is_boosted: bool = False, is_cto: bool = False) -> GemCandidate:
        """
        Score a token 0–100 using weighted criteria.
        Returns a GemCandidate with all score components populated.

        Phase 3 rebalanced weights (14 signals, sum = 100%):
            age=12%, volume=15%, liquidity=13%, contract=8%, holder=8%,
            tax=8%, social=6%, boost=4%, smart_money=4%,
            tvl=5%, social_sentiment=5%, holder_conc=4%, unlock_risk=4%,
            grok_sentiment=4%
        """
        candidate = GemCandidate(token=token)

        # ── Age score (12%) ───────────────────────────────────────────────────
        # New tokens are better for sniping.
        # < 24h = 100, < 48h = 75, < 72h = 50, < 168h = 25, > 168h = 10
        # For Moralis trending tokens (which are often older), we are more lenient
        is_moralis_trending = getattr(token, "is_moralis_trending", False)
        
        if token.age_hours is None:
            candidate.age_score = 50.0
        elif token.age_hours <= 24:
            candidate.age_score = 100.0
        elif token.age_hours <= 48:
            candidate.age_score = 85.0 if is_moralis_trending else 75.0
        elif token.age_hours <= 72:
            candidate.age_score = 70.0 if is_moralis_trending else 50.0
        elif token.age_hours <= 168:
            candidate.age_score = 50.0 if is_moralis_trending else 25.0
        else:
            candidate.age_score = 30.0 if is_moralis_trending else 10.0

        # ── Volume spike score (15%) ──────────────────────────────────────────────
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
            + candidate.volume_score * 0.15
            + candidate.liquidity_score * 0.13
            + candidate.contract_score * 0.08
            + candidate.holder_score * 0.08
            + candidate.tax_score * 0.08
            + candidate.social_score * 0.06
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

            try:
                from data.providers.grok_sentiment import get_grok_sentiment_score
                candidate.grok_sentiment_score = get_grok_sentiment_score(
                    token.symbol, token.chain
                )
            except Exception as e:
                logger.debug(f"Grok sentiment failed for {token.symbol}: {e}")
                candidate.grok_sentiment_score = 50.0
        else:
            candidate.tvl_score = 30.0
            candidate.social_sentiment_score = 30.0
            candidate.holder_concentration_score = 40.0
            candidate.unlock_risk_score = 50.0
            candidate.grok_sentiment_score = 50.0

        # ── Moralis Money Enrichment (PRIMARY source — 12% weight) ─────────────
        # Enrich every candidate that passes base_score >= 45 with Moralis
        # token score, buy/sell analytics, and net buyer counts.
        # Moralis Money is one of our MAIN data sources — high-conviction signal.
        moralis_enrichment_score = 50.0  # default neutral
        if base_score >= 45:
            try:
                enrichment = moralis_enrich(token.address, token.chain)
                moralis_enrichment_score = moralis_score_contribution(enrichment)
                # Store enrichment fields on candidate for dashboard/logging
                candidate.moralis_score = enrichment.get("moralis_score", 0)
                candidate.moralis_buy_pressure = enrichment.get("moralis_buy_pressure", 0.5)
                candidate.moralis_net_buyers_1h = enrichment.get("moralis_net_buyers_1h", 0)
                candidate.moralis_buyers_1h = enrichment.get("moralis_buyers_1h", 0)
                candidate.moralis_sellers_1h = enrichment.get("moralis_sellers_1h", 0)
                candidate.moralis_txns_1h = enrichment.get("moralis_txns_1h", 0)
                candidate.moralis_top10_pct = enrichment.get("moralis_top10_pct", 0.0)
                if enrichment.get("moralis_score", 0) > 0:
                    logger.debug(
                        f"Moralis enrichment {token.symbol}: "
                        f"score={enrichment['moralis_score']} "
                        f"buy_pressure={enrichment['moralis_buy_pressure']:.2f} "
                        f"net_buyers_1h={enrichment['moralis_net_buyers_1h']}"
                    )
            except Exception as e:
                logger.debug(f"Moralis enrichment failed for {token.symbol}: {e}")
                candidate.moralis_score = 0
                candidate.moralis_buy_pressure = 0.5
                candidate.moralis_net_buyers_1h = 0
        else:
            candidate.moralis_score = 0
            candidate.moralis_buy_pressure = 0.5
            candidate.moralis_net_buyers_1h = 0
        candidate.moralis_enrichment_score = moralis_enrichment_score

        # ── Buy Pressure Score ────────────────────────────────────────────────
        buy_pressure_score = 50.0
        total_txns = token.buys_1h + token.sells_1h
        if total_txns > 0:
            buy_ratio = token.buys_1h / total_txns
            if buy_ratio >= 0.70:
                buy_pressure_score = 100.0
            elif buy_ratio >= 0.60:
                buy_pressure_score = 80.0
            elif buy_ratio >= 0.50:
                buy_pressure_score = 60.0
            elif buy_ratio < 0.40:
                buy_pressure_score = 20.0
        candidate.buy_pressure_score = buy_pressure_score

        # ── Final composite score (16 signals — Moralis Money as primary) ────────
        # Weights sum to 1.00. Moralis enrichment replaces the old 4% smart-money
        # weight and gets its own 12% allocation as a PRIMARY data source.
        candidate.gem_score = round(
            candidate.age_score              * 0.09
            + candidate.volume_score         * 0.11
            + candidate.liquidity_score      * 0.09
            + candidate.buy_pressure_score   * 0.09
            + candidate.moralis_enrichment_score * 0.12   # ← Moralis Money PRIMARY
            + candidate.contract_score       * 0.07
            + candidate.holder_score         * 0.07
            + candidate.tax_score            * 0.07
            + candidate.social_score         * 0.05
            + candidate.boost_score          * 0.04
            + candidate.smart_money_score    * 0.03
            + candidate.tvl_score            * 0.05
            + candidate.social_sentiment_score * 0.05
            + candidate.holder_concentration_score * 0.04
            + candidate.unlock_risk_score    * 0.03
            + candidate.grok_sentiment_score * 0.03,
            2,
        )

        # ── CTO Revival bonus ─────────────────────────────────────────────────
        # CTO tokens get a +8 point bonus on top of composite score.
        # Rationale: community-driven revival is a high-conviction signal that
        # the token has organic support beyond the original dev.
        # Capped at 100 to prevent score inflation.
        if is_cto:
            candidate.gem_score = min(100.0, round(candidate.gem_score + 8.0, 2))
            candidate.strategy_tag = "cto_revival"  # Tag for position monitor exit rules
        else:
            candidate.strategy_tag = "gem_snipe"

        # ── Express lane flag ─────────────────────────────────────────────────
        # CTO tokens with score >= 75 also qualify for express lane
        # (lower threshold than standard 82 — CTO is inherently high-conviction)
        cto_express_threshold = 75.0
        candidate.express_lane = (
            candidate.gem_score >= settings.EXPRESS_LANE_SCORE
            or (is_cto and candidate.gem_score >= cto_express_threshold)
        )

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
        token.is_cto = signals.get("is_cto", False)

        return token

    @staticmethod
    def _dexscreener_to_chain(dexscreener_chain_id: str) -> Optional[str]:
        """Map DexScreener chain ID string to our internal chain name."""
        return _DEXSCREENER_CHAIN_MAP.get(dexscreener_chain_id.lower())
