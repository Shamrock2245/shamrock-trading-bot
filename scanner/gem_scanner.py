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
from data.providers.dev_wallet_history import get_dev_wallet_score
from data.providers.copycat_detector import get_copycat_score, is_token_copycat
from data.providers.moralis_money import (
    discover_tokens as moralis_discover,
    enrich_candidate as moralis_enrich,
    calculate_moralis_score_contribution as moralis_score_contribution,
)
from data.providers.moralis_solana import (
    get_sniper_score,
    get_token_snipers,
    get_pumpfun_graduated,
    get_token_top_holders,
)
from data.providers.binance_pulse import (
    enrich_candidate as binance_enrich,
    get_trending_tokens as binance_trending,
    get_supported_chains as binance_supported_chains,
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
    "avalanche": "avalanche",
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

        # ── Source 8: Pump.fun Graduated Tokens (Solana only) ──────────────────
        # Tokens that just graduated from Pump.fun bonding curve to Raydium.
        # This is THE highest-conviction moment for early Solana meme entry.
        if "solana" in settings.ACTIVE_CHAINS:
            try:
                graduated = get_pumpfun_graduated(limit=20)
                pumpfun_added = 0
                for grad in graduated:
                    token_addr = grad.get("token_address", "")
                    if not token_addr or token_addr.lower() in seen_addresses:
                        continue

                    # Need minimum liquidity
                    liq_usd = grad.get("liquidity_usd", 0)
                    if liq_usd < settings.MIN_LIQUIDITY_USD:
                        continue

                    # Get DexScreener data for full scoring
                    pairs = get_token_pairs(token_addr) or []
                    for pair in pairs:
                        signals = extract_gem_signals(pair)
                        signals["is_boosted"] = True
                        signals["boost_amount"] = 100  # Pump.fun graduation = strong signal
                        token = self._signals_to_token(signals, "solana")
                        if token:
                            candidate = self._score_token(token, is_boosted=True)
                            candidate.is_pumpfun_graduate = True
                            candidate.strategy_tag = "pumpfun_graduate"
                            # +5 bonus for Pump.fun graduation (capped at 100)
                            candidate.gem_score = min(100.0, round(candidate.gem_score + 5.0, 2))
                            if candidate.gem_score >= settings.MIN_GEM_SCORE:
                                candidates.append(candidate)
                                seen_addresses.add(token_addr.lower())
                                pumpfun_added += 1
                            elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                                self.add_near_miss(token, candidate.gem_score, "pumpfun")
                            break

                if pumpfun_added:
                    logger.info(f"🚀 Pump.fun graduates: {pumpfun_added} tokens passed scoring")
            except Exception as e:
                logger.warning(f"Pump.fun discovery error: {e}")

        # ── Source 9: Binance Pulse Trending (Multi-chain) ─────────────────────
        # Free discovery from Binance's Web3 wallet platform.
        # Fetch trending tokens for chains Binance supports, cross-reference
        # with DexScreener for full scoring.
        if settings.BINANCE_PULSE_ENABLED:
            try:
                bp_chains = [c for c in settings.ACTIVE_CHAINS if c in binance_supported_chains()]
                binance_added = 0
                for bp_chain in bp_chains:
                    trending = binance_trending(chain=bp_chain, rank_type=10, limit=15)
                    for bt in trending:
                        token_addr = bt.get("token_address", "")
                        if not token_addr or token_addr.lower() in seen_addresses:
                            continue
                        # Skip ultra-low mcap (< $10k) — likely noise
                        if bt.get("market_cap", 0) < 10_000:
                            continue
                        pairs = get_token_pairs(token_addr) or []
                        for pair in pairs:
                            signals = extract_gem_signals(pair)
                            signals["is_boosted"] = True
                            signals["boost_amount"] = 80  # Binance trending = strong signal
                            token_obj = self._signals_to_token(signals, bp_chain)
                            if token_obj:
                                candidate = self._score_token(token_obj, is_boosted=True)
                                candidate.strategy_tag = "binance_trending"
                                if candidate.gem_score >= settings.MIN_GEM_SCORE:
                                    candidates.append(candidate)
                                    seen_addresses.add(token_addr.lower())
                                    binance_added += 1
                                elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                                    self.add_near_miss(token_obj, candidate.gem_score, "binance")
                                break
                if binance_added:
                    logger.info(f"🟡 Binance Pulse: {binance_added} trending tokens passed scoring")
            except Exception as e:
                logger.warning(f"Binance Pulse discovery error: {e}")

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
            candidate.social_score = 50.0  # Neutral fallback on failure

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
            candidate.boost_score = 50  # Neutral when not boosted — 0 was unfairly penalizing

        # ── Smart money score (4%) — REAL wallet overlap ──────────────────────
        try:
            candidate.smart_money_score = get_smart_money_score(token.address, token.chain)
        except Exception as e:
            logger.debug(f"Smart money scoring failed for {token.symbol}: {e}")
            candidate.smart_money_score = 50.0  # Neutral fallback — 0 was dragging scores down

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

        # ── Solana on-chain intelligence (Phase 5) ─────────────────────────────
        # Sniper detection + holder concentration from Moralis Solana API.
        # Only for Solana tokens — these endpoints don't exist for EVM.
        if token.chain == "solana" and base_score >= 40:
            pair_addr = getattr(token, "pair_address", "")
            if pair_addr:
                try:
                    sniper_data = get_token_snipers(pair_addr)
                    candidate.sniper_score = get_sniper_score(pair_addr)
                    candidate.sniper_count = sniper_data.get("sniper_count", 0)
                    candidate.sniper_risk = sniper_data.get("risk_level", "unknown")
                    sniper_count = sniper_data.get("sniper_count", 0)
                    sniper_risk_level = sniper_data.get("risk_level", "unknown")
                    sniped_usd = sniper_data.get("total_sniped_usd", 0)
                    if sniper_count >= 5 or sniper_risk_level in ("high", "critical"):
                        logger.warning(
                            f"🎯 SNIPER ALERT {token.symbol}: "
                            f"{sniper_count} snipers "
                            f"(${sniped_usd:,.0f} sniped) "
                            f"— risk={sniper_risk_level}"
                        )
                        # Slack alert for high sniper activity
                        try:
                            from notifications.slack import notify_alert
                            notify_alert(
                                "🎯 Sniper Warning",
                                f"{token.symbol} has {sniper_count} snipers "
                                f"(${sniped_usd:,.0f} sniped) — "
                                f"risk: {sniper_risk_level}",
                                level="warning",
                            )
                        except Exception:
                            pass
                        # HARD BLOCK: critical sniper risk = we are the exit liquidity.
                        # 10+ snipers or critical risk = coordinated dump setup — skip.
                        if sniper_risk_level == "critical" or sniper_count >= 10:
                            logger.warning(
                                f"🚫 SNIPER BLOCK {token.symbol}: "
                                f"critical sniper risk ({sniper_count} snipers, "
                                f"${sniped_usd:,.0f} sniped) — dropping candidate"
                            )
                            return None  # Drop this candidate entirely
                except Exception as e:
                    logger.debug(f"Sniper detection failed for {token.symbol}: {e}")
                    candidate.sniper_score = 50.0

            try:
                holder_data = get_token_top_holders(token.address)
                candidate.solana_holder_concentration = holder_data.get("top10_concentration", 0.0)
                # Override EVM holder_concentration_score with Solana-native data
                conc = candidate.solana_holder_concentration
                if conc >= 0.80:
                    candidate.holder_concentration_score = 10.0
                elif conc >= 0.50:
                    candidate.holder_concentration_score = 30.0
                elif conc >= 0.30:
                    candidate.holder_concentration_score = 60.0
                else:
                    candidate.holder_concentration_score = 90.0
            except Exception as e:
                logger.debug(f"Solana holder analysis failed for {token.symbol}: {e}")

        # ── Enhanced signal enrichment (Phase 3) ──────────────────────────────
        # Only query external APIs for candidates that pass initial screening
        # to conserve rate limits (especially LunarCrush: 100 req/day).
        #
        # ⚡ PARALLEL ENRICHMENT: 10 fast API calls run concurrently via
        # ThreadPoolExecutor. Moralis + Binance Pulse now run IN the pool
        # (previously Moralis was sequential — saved 6-8s per candidate).
        # Grok sentiment (6-8s LLM call, 2% weight) deferred to 2nd pass.
        if base_score >= 45:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            # Define enrichment tasks as (name, callable) pairs
            def _get_tvl():
                return get_tvl_score(token.address, token.chain)

            def _get_lc():
                from data.providers.coingecko_social import get_social_score as get_lc_score
                return get_lc_score(token.symbol)

            def _get_holder():
                return get_holder_score(token.address, token.chain)

            def _get_unlock():
                return get_unlock_risk_score(token.address, token.chain)

            def _get_dev():
                return get_dev_wallet_score(token.address, token.chain)

            def _get_copycat():
                has_website = bool(getattr(token, 'websites', []))
                has_socials = bool(getattr(token, 'socials', []))
                return get_copycat_score(
                    name=token.name,
                    symbol=token.symbol,
                    has_image=True,
                    has_description=has_socials,
                    has_website=has_website,
                    token_address=token.address,
                )

            def _get_moralis_meta():
                from data.providers.moralis_wallet import get_enhanced_token_metadata
                return get_enhanced_token_metadata([token.address], chain=token.chain)

            # ⚡ NEW: Moralis Money enrichment now runs IN the pool (was sequential)
            def _get_moralis_money():
                return moralis_enrich(token.address, token.chain)

            # ⚡ NEW: Binance Pulse smart money + social hype (free, no key)
            def _get_binance_pulse():
                if not settings.BINANCE_PULSE_ENABLED:
                    return {"binance_smart_money_confirmed": False, "binance_social_hype_score": 50.0}
                return binance_enrich(token.address, chain=token.chain)

            # Submit ALL enrichment calls concurrently — 10 workers (no Grok — deferred)
            enrichment_results = {}
            with ThreadPoolExecutor(max_workers=10, thread_name_prefix="enrich") as pool:
                futures = {
                    pool.submit(_get_tvl): "tvl",
                    pool.submit(_get_lc): "lc",
                    pool.submit(_get_holder): "holder",
                    pool.submit(_get_unlock): "unlock",
                    pool.submit(_get_dev): "dev",
                    pool.submit(_get_copycat): "copycat",
                    pool.submit(_get_moralis_meta): "moralis_meta",
                    pool.submit(_get_moralis_money): "moralis_money",     # ← was sequential!
                    pool.submit(_get_binance_pulse): "binance_pulse",     # ← NEW
                }
                for future in as_completed(futures, timeout=15):
                    name = futures[future]
                    try:
                        enrichment_results[name] = future.result()
                    except Exception as e:
                        logger.debug(f"Enrichment '{name}' failed for {token.symbol}: {e}")
                        enrichment_results[name] = None

            # Apply results to candidate
            candidate.tvl_score = enrichment_results.get("tvl") or 50.0
            candidate.social_sentiment_score = enrichment_results.get("lc") or 50.0
            candidate.holder_concentration_score = enrichment_results.get("holder") or 50.0
            candidate.unlock_risk_score = enrichment_results.get("unlock") or 50.0
            candidate.grok_sentiment_score = 50.0  # default — deferred to second pass

            # Dev wallet
            dev_result = enrichment_results.get("dev")
            if dev_result and isinstance(dev_result, tuple):
                dev_score, dev_flags = dev_result
                candidate.dev_wallet_score = dev_score
                candidate.dev_wallet_flags = dev_flags
                if dev_score < 25:
                    logger.warning(
                        f"🚩 Dev wallet RED FLAG for {token.symbol}: "
                        f"score={dev_score:.0f} — {', '.join(f for f in dev_flags if '🚩' in f)}"
                    )
            else:
                candidate.dev_wallet_score = 50.0

            # Copycat
            copycat_result = enrichment_results.get("copycat")
            if copycat_result and isinstance(copycat_result, tuple):
                copy_score, copy_flags = copycat_result
                candidate.copycat_score = copy_score
                candidate.copycat_flags = copy_flags
                if copy_score < 30:
                    logger.warning(
                        f"🚩 COPYCAT ALERT for {token.symbol} ({token.name}): "
                        f"score={copy_score:.0f} — likely impersonator!"
                    )
            else:
                candidate.copycat_score = 70.0

            # Moralis metadata
            metadata_list = enrichment_results.get("moralis_meta")
            if metadata_list and isinstance(metadata_list, list) and len(metadata_list) > 0:
                meta = metadata_list[0]
                candidate.moralis_fdv = meta.get("fdv", 0.0)
                candidate.moralis_market_cap = meta.get("market_cap", 0.0)
                candidate.moralis_verified = meta.get("verified_contract", False)
                candidate.moralis_spam = meta.get("possible_spam", False)
                candidate.moralis_has_website = bool(meta.get("website", ""))
                candidate.moralis_has_twitter = bool(meta.get("twitter", ""))
                candidate.moralis_categories = meta.get("categories", [])

                # Spam token → instant reject
                if meta.get("possible_spam", False):
                    logger.info(f"🚫 Moralis spam flag: {token.symbol} — skipping")
                    return None

                # Verified contract → score boost
                if meta.get("verified_contract", False):
                    candidate.contract_score = min(100.0, candidate.contract_score + 5.0)

                # Social presence boost
                social_links = sum([
                    bool(meta.get("website", "")),
                    bool(meta.get("twitter", "")),
                    bool(meta.get("telegram", "")),
                    bool(meta.get("discord", "")),
                ])
                if social_links >= 2:
                    candidate.social_score = min(100.0, candidate.social_score + 3.0)

                # FDV sanity check
                if meta.get("fdv", 0) > 1_000_000_000 and token.liquidity_usd < 100_000:
                    logger.info(
                        f"⚠️ FDV anomaly: {token.symbol} FDV=${meta['fdv']:,.0f} "
                        f"but liquidity=${token.liquidity_usd:,.0f}"
                    )
                    candidate.contract_score = max(0.0, candidate.contract_score - 15.0)
        else:
            candidate.tvl_score = 50.0
            candidate.social_sentiment_score = 50.0
            candidate.holder_concentration_score = 50.0
            candidate.unlock_risk_score = 50.0
            candidate.grok_sentiment_score = 50.0
            candidate.dev_wallet_score = 50.0
            candidate.copycat_score = 70.0

        # ── GROK SENTIMENT (conditional second pass — 2% weight) ──────────────
        # Only call the slow Grok LLM (~6-8s) if the token still looks
        # promising after all the fast enrichment signals. This saves API
        # credits and shaves ~6s off ~80% of tokens that won't pass anyway.
        if base_score >= 45 and candidate.grok_sentiment_score == 50.0:
            # Quick preliminary score to decide if Grok is worth calling
            prelim_score = (
                candidate.age_score * 0.08
                + candidate.volume_score * 0.10
                + candidate.liquidity_score * 0.08
                + candidate.buy_pressure_score * 0.07
                + candidate.contract_score * 0.07
                + candidate.holder_score * 0.07
                + candidate.tax_score * 0.06
                + candidate.social_score * 0.05
                + candidate.boost_score * 0.04
                + candidate.smart_money_score * 0.03
                + candidate.tvl_score * 0.04
                + candidate.social_sentiment_score * 0.04
                + candidate.holder_concentration_score * 0.03
                + candidate.unlock_risk_score * 0.02
                + candidate.dev_wallet_score * 0.03
                + candidate.copycat_score * 0.03
            )
            if prelim_score >= 48:
                try:
                    from data.providers.grok_sentiment import get_grok_sentiment_score
                    candidate.grok_sentiment_score = get_grok_sentiment_score(
                        token.symbol, token.chain
                    )
                except Exception as e:
                    logger.debug(f"Grok sentiment failed for {token.symbol}: {e}")
                    candidate.grok_sentiment_score = 50.0

        # ── Moralis Money Enrichment (PRIMARY source — 20% weight) ─────────────
        # ⚡ Now runs IN the parallel pool above (was sequential — saved 6-8s).
        # Results are extracted from enrichment_results["moralis_money"].
        moralis_enrichment_score = 50.0  # default neutral
        if base_score >= 45:
            enrichment = enrichment_results.get("moralis_money", {})
            if enrichment:
                try:
                    moralis_enrichment_score = moralis_score_contribution(enrichment)
                    # Store enrichment fields on candidate for dashboard/logging
                    candidate.moralis_score = enrichment.get("moralis_score", 0)
                    candidate.moralis_buy_pressure = enrichment.get("moralis_buy_pressure", 0.5)
                    candidate.moralis_net_buyers_1h = enrichment.get("moralis_net_buyers_1h", 0)
                    candidate.moralis_buyers_1h = enrichment.get("moralis_buyers_1h", 0)
                    candidate.moralis_sellers_1h = enrichment.get("moralis_sellers_1h", 0)
                    candidate.moralis_txns_1h = enrichment.get("moralis_txns_1h", 0)
                    candidate.moralis_top10_pct = enrichment.get("moralis_top10_pct", 0.0)
                    # New whale accumulation + discovery signals
                    candidate.moralis_exp_net_buyers_1d = enrichment.get("moralis_exp_net_buyers_1d", 0)
                    candidate.moralis_exp_net_buyers_1w = enrichment.get("moralis_exp_net_buyers_1w", 0)
                    candidate.moralis_holders_change_1d = enrichment.get("moralis_holders_change_1d", 0)
                    candidate.moralis_holders_change_1w = enrichment.get("moralis_holders_change_1w", 0)
                    candidate.moralis_on_chain_strength = enrichment.get("moralis_on_chain_strength", 0.0)
                    candidate.moralis_liquidity_locked_pct = enrichment.get("moralis_liquidity_locked_pct", 0.0)
                    candidate.moralis_security_score = enrichment.get("moralis_security_score", 0)
                    candidate.moralis_token_age_days = enrichment.get("moralis_token_age_days", 0.0)

                    # Whale accumulation bonus: log strong whale interest
                    exp_net_1w = enrichment.get("moralis_exp_net_buyers_1w", 0)
                    if exp_net_1w >= 10:
                        logger.info(
                            f"🐋 WHALE ACCUMULATION: {token.symbol} — "
                            f"{exp_net_1w} experienced net buyers this week!"
                        )

                    # Security score from discovery: if score < 40 → deduct from contract_score
                    disc_security = enrichment.get("moralis_security_score", 0)
                    if disc_security > 0 and disc_security < 40:
                        candidate.contract_score = max(
                            0.0, candidate.contract_score - 10.0
                        )
                        logger.debug(
                            f"⚠️ Low Moralis security score for {token.symbol}: "
                            f"{disc_security}/100 → contract score penalized"
                        )
                    elif disc_security >= 80:
                        candidate.contract_score = min(
                            100.0, candidate.contract_score + 5.0
                        )

                    if enrichment.get("moralis_score", 0) > 0:
                        logger.debug(
                            f"Moralis enrichment {token.symbol}: "
                            f"score={enrichment['moralis_score']} "
                            f"buy_pressure={enrichment['moralis_buy_pressure']:.2f} "
                            f"net_buyers_1h={enrichment['moralis_net_buyers_1h']} "
                            f"whale_1w={exp_net_1w} "
                            f"holders_1d={enrichment.get('moralis_holders_change_1d', 0)}"
                        )
                except Exception as e:
                    logger.debug(f"Moralis enrichment processing failed for {token.symbol}: {e}")
                    candidate.moralis_score = 0
                    candidate.moralis_buy_pressure = 0.5
                    candidate.moralis_net_buyers_1h = 0
            else:
                candidate.moralis_score = 0
                candidate.moralis_buy_pressure = 0.5
                candidate.moralis_net_buyers_1h = 0
        else:
            candidate.moralis_score = 0
            candidate.moralis_buy_pressure = 0.5
            candidate.moralis_net_buyers_1h = 0
        candidate.moralis_enrichment_score = moralis_enrichment_score

        # ── Binance Pulse Enrichment (smart money + social hype) ──────────────
        # ⚡ Runs IN the parallel pool above — zero extra latency.
        if base_score >= 45:
            bp_data = enrichment_results.get("binance_pulse", {})
            if bp_data:
                candidate.binance_smart_money_confirmed = bp_data.get(
                    "binance_smart_money_confirmed", False
                )
                candidate.binance_smart_money_inflow_usd = bp_data.get(
                    "binance_smart_money_inflow_usd", 0.0
                )
                candidate.binance_smart_money_rank = bp_data.get(
                    "binance_smart_money_rank", 0
                )
                candidate.binance_social_hype_score = bp_data.get(
                    "binance_social_hype_score", 50.0
                )
                if candidate.binance_smart_money_confirmed:
                    logger.info(
                        f"🐋 BINANCE SMART MONEY: {token.symbol} — "
                        f"rank #{candidate.binance_smart_money_rank}, "
                        f"${candidate.binance_smart_money_inflow_usd:,.0f} inflow"
                    )

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

        # ── Final composite score (19 signals — Moralis + Solana intelligence) ──────
        # Weights sum to 1.00. Moralis enrichment gets 20% allocation as PRIMARY
        # data source — the strongest single alpha signal. Rebalanced from v1.
        # Dev wallet (3%) and copycat (2%) rug-protection signals retained.
        candidate.gem_score = round(
            candidate.age_score              * 0.07    # was 0.08
            + candidate.volume_score         * 0.07    # was 0.10
            + candidate.liquidity_score      * 0.06    # was 0.08
            + candidate.buy_pressure_score   * 0.07
            + candidate.moralis_enrichment_score * 0.20 # ← DOUBLED: Moralis PRIMARY
            + candidate.sniper_score         * 0.04    # Solana sniper detection
            + candidate.contract_score       * 0.05    # was 0.07
            + candidate.holder_score         * 0.05    # was 0.07
            + candidate.tax_score            * 0.06
            + candidate.social_score         * 0.05
            + candidate.boost_score          * 0.04
            + candidate.smart_money_score    * 0.03
            + candidate.tvl_score            * 0.04
            + candidate.social_sentiment_score * 0.04
            + candidate.holder_concentration_score * 0.03
            + candidate.unlock_risk_score    * 0.02
            + candidate.grok_sentiment_score * 0.02
            + candidate.dev_wallet_score     * 0.03
            + candidate.copycat_score        * 0.03,
            2,
        )

        # ── NUCLEAR BONUS: Moralis buying pressure >70% → +18 ──────────────
        # When Moralis confirms >70% buy pressure, this is a high-conviction
        # accumulation signal. +18 bonus rockets high-base-score tokens into
        # express lane territory. Capped at 100.
        moralis_bp = getattr(candidate, 'moralis_buy_pressure', 0.5)
        if moralis_bp > 0.70:
            candidate.gem_score = min(100.0, round(candidate.gem_score + 18.0, 2))
            logger.info(
                f"🚀 MORALIS BUYING PRESSURE BONUS: {token.symbol} "
                f"buy_pressure={moralis_bp:.0%} → +18 (new score={candidate.gem_score})"
            )

        # ── DEV REJECT: fresh dev wallet + serial deployer → -30 ───────────
        # If the dev wallet is <48h old AND has launched >3 tokens, this is
        # a serial rug deployer pattern. Heavy penalty to keep these out of
        # the nuclear pipeline. Floored at 0.
        dev_flags = getattr(candidate, 'dev_wallet_flags', [])
        dev_is_fresh = any('new_wallet' in f.lower() or '<48h' in f.lower() for f in dev_flags)
        dev_serial = any('serial' in f.lower() or 'multi' in f.lower() or '>3' in f for f in dev_flags)
        if dev_is_fresh and dev_serial:
            candidate.gem_score = max(0.0, round(candidate.gem_score - 30.0, 2))
            logger.warning(
                f"🚫 DEV REJECT: {token.symbol} — fresh wallet + serial deployer → -30 "
                f"(new score={candidate.gem_score})"
            )

        # ── BINANCE SMART MONEY BONUS: confirmed inflow → +5 ──────────────
        # If Binance Pulse confirms smart money is actively buying this token,
        # boost score by 5 points. High-conviction whale signal, capped at 100.
        if candidate.binance_smart_money_confirmed:
            candidate.gem_score = min(100.0, round(candidate.gem_score + 5.0, 2))
            logger.info(
                f"🟡 BINANCE SM BONUS: {token.symbol} → +5 "
                f"(rank #{candidate.binance_smart_money_rank}, "
                f"new score={candidate.gem_score})"
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

        # ── Instant copycat reject ────────────────────────────────────────
        # Block obvious impersonators before spending API calls on enrichment
        token_name = signals.get("base_token_name", symbol)
        try:
            if is_token_copycat(token_name, symbol, token_address=address):
                logger.info(
                    f"🚫 Rejected copycat token: {symbol} ({token_name}) on {chain}"
                )
                return None
        except Exception:
            pass  # Don't block on detector errors

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
            is_cto=signals.get("is_cto", False),
            buys_1h=signals.get("buys_1h", 0),
            sells_1h=signals.get("sells_1h", 0),
            dex_url=signals.get("url", ""),
            websites=signals.get("websites", []),
            socials=signals.get("socials", []),
        )

        return token

    @staticmethod
    def _dexscreener_to_chain(dexscreener_chain_id: str) -> Optional[str]:
        """Map DexScreener chain ID string to our internal chain name."""
        return _DEXSCREENER_CHAIN_MAP.get(dexscreener_chain_id.lower())
