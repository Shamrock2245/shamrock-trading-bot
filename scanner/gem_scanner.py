"""
scanner/gem_scanner.py — Multi-chain gem discovery and scoring engine.

Scans DexScreener + Moralis + Grok for new/boosted/trending tokens across
Ethereum, Base, Arbitrum, Polygon, BSC, Avalanche, and Solana. Scores each
candidate 0–100 using weighted criteria and returns a ranked list of
GemCandidates ready for safety checks and execution.

Data sources (17 total):
  1.  DexScreener latest token profiles
  2.  DexScreener latest boosts
  3.  DexScreener top boosts
  4.  DexScreener community takeovers (CTO Revival)
  5.  DexScreener ads
  6.  Moralis trending tokens + buying pressure (Pro plan)
  7.  Gem Watchlist re-evaluation (near-miss tokens from prior cycles)
  8.  Pump.fun Graduated Tokens (Solana)
  9.  Binance Pulse Trending (Multi-chain)
  10. Pump.fun NEW Tokens (Solana — earliest entry)
  11. Pump.fun BONDING Tokens (near-graduation)
  12. Moralis Sniper Convergence (≥3 snipers → express lane)
  13. DexScreener New Pairs (Base + Solana, ≤10m old)
  14. Grok CT Trending (top 5 X/Twitter discussed tokens)

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
from data.providers.social_scoring import get_social_score
from data.providers.smart_money import get_smart_money_score
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
from data.providers.moralis_intelligence import (
    enrich_token_intelligence,
    calculate_intelligence_score_boost,
    get_pumpfun_new_tokens,
    get_pumpfun_bonding_tokens,
    get_chain_heat,
)
from scanner.watchlist import GemWatchlist, WATCHLIST_MIN_SCORE

# ── Macro Market Regime Filter ────────────────────────────────────────────────
# Adjusts gem score threshold and applies a multiplier based on BTC/ETH/SOL
# market regime (BULL / NEUTRAL / BEAR / EXTREME_FEAR). Fetched once per scan
# cycle and cached for 1 hour to respect free API rate limits.
try:
    from core.macro_filter import get_macro_regime, get_effective_min_score
    _MACRO_FILTER_AVAILABLE = True
except ImportError:
    _MACRO_FILTER_AVAILABLE = False

# ── ML Dynamic Weight Optimizer ───────────────────────────────────────────────
# Loads XGBoost-derived weights from output/dynamic_weights.json.
# Falls back to static defaults if insufficient trade history exists.
try:
    from ml.weight_optimizer import load_dynamic_weights, STATIC_WEIGHTS as _STATIC_WEIGHTS
    _ML_WEIGHTS_AVAILABLE = True
except ImportError:
    _ML_WEIGHTS_AVAILABLE = False
    _STATIC_WEIGHTS = {
        "volume": 0.22, "whale_holder": 0.18, "liquidity": 0.14,
        "safety": 0.12, "momentum_ta": 0.10, "boost_cto": 0.07,
        "fibonacci": 0.05, "grok_sentiment": 0.05, "age": 0.04, "social": 0.03,
    }

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
        # Thread-safe queue for candidates injected by Moralis Streams callbacks.
        # Moralis Streams daemon threads append here; the main scan loop drains it
        # every cycle so real-time whale/pool events are processed immediately.
        import collections as _collections
        self._stream_candidates: _collections.deque = _collections.deque(maxlen=50)
        # Load ML-derived dynamic weights (refreshed every 6h from trades.json)
        # Falls back to static defaults when insufficient trade history exists.
        if _ML_WEIGHTS_AVAILABLE:
            self._weights = load_dynamic_weights()
        else:
            self._weights = dict(_STATIC_WEIGHTS)
        logger.info(
            f"GemScanner weights loaded: "
            f"vol={self._weights.get('volume', 0):.2f} | "
            f"whale={self._weights.get('whale_holder', 0):.2f} | "
            f"liq={self._weights.get('liquidity', 0):.2f} | "
            f"grok={self._weights.get('grok_sentiment', 0):.2f}"
        )

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

        # ── Macro Regime: fetch once per scan cycle ───────────────────────────
        _macro_multiplier = 1.0
        _macro_min_score = float(settings.MIN_GEM_SCORE)
        _macro_regime_label = "NEUTRAL"
        if _MACRO_FILTER_AVAILABLE:
            try:
                _mr = get_macro_regime()
                _macro_multiplier = _mr.score_multiplier
                _macro_min_score = get_effective_min_score(settings.MIN_GEM_SCORE)
                _macro_regime_label = _mr.regime
                logger.info(
                    f"MacroFilter active: regime={_mr.regime} | "
                    f"multiplier={_macro_multiplier:.2f}x | "
                    f"effective_min={_macro_min_score:.0f} | "
                    f"F&G={_mr.fear_greed_value} ({_mr.fear_greed_label}) | "
                    f"cached={_mr.cached}"
                )
            except Exception as _mf_err:
                logger.debug(f"MacroFilter unavailable: {_mf_err}")

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
                    if candidate is None:
                        break
                    _adjusted_score = candidate.gem_score * _macro_multiplier
                    candidate.gem_score = _adjusted_score
                    if _adjusted_score >= _macro_min_score:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    elif _adjusted_score >= WATCHLIST_MIN_SCORE:
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
                    if candidate is None:
                        break
                    _adjusted_score = candidate.gem_score * _macro_multiplier
                    candidate.gem_score = _adjusted_score
                    if _adjusted_score >= _macro_min_score:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    elif _adjusted_score >= WATCHLIST_MIN_SCORE:
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
                    if candidate is None:
                        break
                    _adjusted_score = candidate.gem_score * _macro_multiplier
                    candidate.gem_score = _adjusted_score
                    if _adjusted_score >= _macro_min_score:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                    elif _adjusted_score >= WATCHLIST_MIN_SCORE:
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
                    if candidate is None:
                        break
                    _adj = candidate.gem_score * _macro_multiplier
                    candidate.gem_score = _adj
                    if _adj >= _macro_min_score:
                        candidates.append(candidate)
                    elif _adj >= WATCHLIST_MIN_SCORE:
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
                    if candidate is None:
                        break
                    _adj = candidate.gem_score * _macro_multiplier
                    candidate.gem_score = _adj
                    if _adj >= _macro_min_score:
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
                        if candidate is None:
                            break
                        _adj = candidate.gem_score * _macro_multiplier
                        candidate.gem_score = _adj
                        if _adj >= _macro_min_score:
                            candidate.strategy_tag = "moralis_trending"
                            candidates.append(candidate)
                            seen_addresses.add(token_addr.lower())
                            moralis_added += 1
                        elif _adj >= WATCHLIST_MIN_SCORE:
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
                    if candidate is None:
                        continue
                    candidate.gem_score = promo["score"]  # Use watchlist score
                    candidate.strategy_tag = "watchlist_promotion"
                    candidates.append(candidate)
                    seen_addresses.add(token_addr.lower())
                    logger.info(
                        f"☘️ Watchlist promoted {promo['symbol']} "
                        f"(score {promo['initial_score']:.1f} → {promo['score']:.1f}) "
                        f"after {promo['checks']} checks"
                    )
                    # ── Telegram threshold breach alert ─────────────────────
                    try:
                        from notifications.telegram import notify_threshold_breach
                        notify_threshold_breach(
                            symbol=promo['symbol'],
                            chain=promo['chain'],
                            old_score=promo['initial_score'],
                            new_score=promo['score'],
                            timing=getattr(candidate, 'timing_bp_trend', 'flat') or 'flat',
                            liquidity_usd=getattr(candidate.token, 'liquidity_usd', 0) or 0,
                            volume_1h=getattr(candidate.token, 'volume_1h', 0) or 0,
                            buy_pressure=getattr(candidate, 'moralis_buy_pressure', 0) or 0,
                            source="watchlist_promotion",
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Watchlist re-evaluation error: {e}")

        # ── Source 8: Pump.fun Graduated Tokens (Solana only) ──────────────────
        # Tokens that just graduated from Pump.fun bonding curve to Raydium.
        # This is THE highest-conviction moment for early Solana meme entry.
        if "solana" in settings.ACTIVE_CHAINS:
            try:
                graduated = get_pumpfun_graduated(limit=20)
                graduated = [g for g in graduated if g.get("moralis_exp_net_buyers_1w", 0) >= 15]
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
                            if candidate is None:
                                break
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
                                if candidate is None:
                                    break
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

        # ── Source 10: Pump.fun NEW Tokens (Solana — earliest possible entry) ────
        # Tokens just created on Pump.fun, still on the bonding curve.
        # Filtered by age gate (≥2h) + safety + score floor.
        # Gives us the earliest possible Solana entry before DexScreener lists them.
        if "solana" in settings.ACTIVE_CHAINS:
            try:
                new_tokens = get_pumpfun_new_tokens(limit=25)
                pumpfun_new_added = 0
                for nt in new_tokens:
                    token_addr = nt.get("address", "")
                    if not token_addr or token_addr.lower() in seen_addresses:
                        continue
                    # Skip tokens with zero volume (pure noise)
                    if nt.get("volume_24h", 0) < 500:
                        continue
                    signals = {
                        "address": token_addr,
                        "symbol": nt.get("symbol", ""),
                        "name": nt.get("name", ""),
                        "chain": "solana",
                        "market_cap": nt.get("market_cap", 0),
                        "volume_24h": nt.get("volume_24h", 0),
                        "bonding_pct": nt.get("bonding_pct", 0),
                        "is_boosted": False,
                        "boost_amount": 0,
                        "source": "pumpfun_new",
                    }
                    token_obj = self._signals_to_token(signals, "solana")
                    if token_obj:
                        candidate = self._score_token(token_obj, is_boosted=False)
                        if candidate is None:
                            continue
                        candidate.strategy_tag = "pumpfun_new"
                        # +3 bonus for being caught pre-graduation (early entry premium)
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 3.0, 2))
                        if candidate.gem_score >= _macro_min_score:
                            candidates.append(candidate)
                            seen_addresses.add(token_addr.lower())
                            pumpfun_new_added += 1
                        elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                            self.add_near_miss(token_obj, candidate.gem_score, "pumpfun_new")
                if pumpfun_new_added:
                    logger.info(f"🌱 Pump.fun NEW: {pumpfun_new_added} pre-graduation tokens passed scoring")
            except Exception as e:
                logger.warning(f"Pump.fun NEW discovery error: {e}")

        # ── Source 11: Pump.fun BONDING Tokens (near-graduation, highest momentum) ─
        # Tokens at 80%+ bonding curve progress — about to graduate to Raydium.
        # These are the highest-momentum pre-graduation plays with whale confirmation.
        if "solana" in settings.ACTIVE_CHAINS:
            try:
                bonding_tokens = get_pumpfun_bonding_tokens(limit=25)
                pumpfun_bonding_added = 0
                for bt in bonding_tokens:
                    token_addr = bt.get("address", "")
                    if not token_addr or token_addr.lower() in seen_addresses:
                        continue
                    # Only take tokens near graduation (≥80% bonding curve)
                    if not bt.get("near_graduation", False):
                        continue
                    signals = {
                        "address": token_addr,
                        "symbol": bt.get("symbol", ""),
                        "name": bt.get("name", ""),
                        "chain": "solana",
                        "market_cap": bt.get("market_cap", 0),
                        "volume_24h": bt.get("volume_24h", 0),
                        "bonding_pct": bt.get("bonding_pct", 0),
                        "is_boosted": True,
                        "boost_amount": 60,
                        "source": "pumpfun_bonding",
                    }
                    token_obj = self._signals_to_token(signals, "solana")
                    if token_obj:
                        candidate = self._score_token(token_obj, is_boosted=True)
                        if candidate is None:
                            continue
                        candidate.strategy_tag = "pumpfun_bonding"
                        # +8 bonus for near-graduation — highest pre-grad signal
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 8.0, 2))
                        if candidate.gem_score >= _macro_min_score:
                            candidates.append(candidate)
                            seen_addresses.add(token_addr.lower())
                            pumpfun_bonding_added += 1
                        elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                            self.add_near_miss(token_obj, candidate.gem_score, "pumpfun_bonding")

                if pumpfun_bonding_added:
                    logger.info(f"🔥 Pump.fun BONDING: {pumpfun_bonding_added} near-graduation tokens passed scoring")
            except Exception as e:
                logger.warning(f"Pump.fun BONDING discovery error: {e}")

        # ── Source 12: Moralis Sniper Convergence (≥3 snipers → express lane) ──
        # When ≥3 known profitable sniper wallets buy the same token within
        # 5 minutes, that convergence is the strongest possible signal.
        # These get a +10 bonus and are flagged as express-lane candidates.
        try:
            from data.providers.moralis_sniper_detection import discover_sniper_convergence
            convergence_tokens = discover_sniper_convergence()
            sniper_conv_added = 0
            for conv in convergence_tokens:
                token_addr = conv.get("token_address", "")
                chain = conv.get("chain", "")
                if not token_addr or not chain:
                    continue
                if chain not in settings.ACTIVE_CHAINS:
                    continue
                if token_addr.lower() in seen_addresses:
                    continue
                pairs = get_token_pairs(token_addr) or []
                for pair in pairs:
                    signals = extract_gem_signals(pair)
                    signals["is_boosted"] = True
                    signals["boost_amount"] = 120  # Strong sniper convergence signal
                    token = self._signals_to_token(signals, chain)
                    if token:
                        candidate = self._score_token(token, is_boosted=True)
                        if candidate is None:
                            break
                        # +10 bonus for multi-sniper convergence
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 10.0, 2))
                        candidate.strategy_tag = "sniper_convergence"
                        candidate.express_lane = conv.get("express_lane", True)
                        if candidate.gem_score >= _macro_min_score:
                            candidates.append(candidate)
                            seen_addresses.add(token_addr.lower())
                            sniper_conv_added += 1
                            logger.info(
                                f"🎯 SNIPER CONVERGENCE HIT: {token.symbol} — "
                                f"{conv['sniper_count']} snipers, "
                                f"${conv.get('total_usd_value', 0):,.0f} total, "
                                f"score={candidate.gem_score:.1f} → EXPRESS LANE"
                            )
                        elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                            self.add_near_miss(token, candidate.gem_score, "sniper_convergence")
                        break
            if sniper_conv_added:
                logger.info(f"🎯 Sniper convergence: {sniper_conv_added} tokens passed scoring")
        except Exception as e:
            logger.warning(f"Sniper convergence discovery error: {e}")

        # ── Source 14: Grok CT Trending (top 5 X/Twitter discussed tokens) ─────
        # Social narrative precedes price action in meme/micro-cap markets.
        # Grok identifies the hottest CT discussions and we check if those
        # tokens are tradeable. +5 social momentum bonus.
        try:
            from data.providers.grok_trending_scan import discover_grok_trending
            grok_trending = discover_grok_trending()
            grok_added = 0
            for gt_signals in grok_trending:
                token_addr = gt_signals.get("base_token_address", "")
                chain_id = gt_signals.get("chain_id", "")
                chain = self._dexscreener_to_chain(chain_id)
                if not chain or not token_addr:
                    continue
                if chain not in settings.ACTIVE_CHAINS:
                    continue
                if token_addr.lower() in seen_addresses:
                    continue
                token = self._signals_to_token(gt_signals, chain)
                if token:
                    candidate = self._score_token(token, is_boosted=True)
                    if candidate is None:
                        continue
                    # +5 social momentum bonus for CT trending
                    candidate.gem_score = min(100.0, round(candidate.gem_score + 5.0, 2))
                    candidate.strategy_tag = "grok_trending"
                    buzz = gt_signals.get("grok_buzz_level", "?")
                    narrative = gt_signals.get("grok_narrative", "")[:50]
                    # Viral buzz gets extra +5 (total +10)
                    if buzz == "viral":
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 5.0, 2))
                    if candidate.gem_score >= _macro_min_score:
                        candidates.append(candidate)
                        seen_addresses.add(token_addr.lower())
                        grok_added += 1
                        logger.info(
                            f"🐦 GROK TRENDING: {token.symbol} on {chain} — "
                            f"buzz={buzz}, score={candidate.gem_score:.1f}, "
                            f"narrative=\"{narrative}...\""
                        )
                    elif candidate.gem_score >= WATCHLIST_MIN_SCORE:
                        self.add_near_miss(token, candidate.gem_score, "grok_trending")
            if grok_added:
                logger.info(f"🐦 Grok trending: {grok_added} CT-hot tokens passed scoring")
        except Exception as e:
            logger.warning(f"Grok trending discovery error: {e}")

        # ── Sort by score descending ──────────────────────────────────────────
        candidates.sort(key=lambda c: c.gem_score, reverse=True)
        express_count = sum(1 for c in candidates if c.gem_score >= settings.EXPRESS_LANE_SCORE)
        logger.info(
            f"Scan complete: {len(candidates)} candidates above "
            f"score threshold {settings.MIN_GEM_SCORE} "
            f"({express_count} express lane) "
            f"| watchlist: {self.watchlist.size} tokens watched"
        )

        # ── Telegram alerts for all high-conviction gems ─────────────────────
        for c in candidates:
            try:
                from notifications.telegram import notify_conviction_alert
                notify_conviction_alert(
                    symbol=c.token.symbol,
                    chain=c.token.chain,
                    score=c.gem_score,
                    strategy_tag=c.strategy_tag or '',
                    price_usd=c.token.price_usd or 0,
                    market_cap=c.token.market_cap or 0,
                    liquidity_usd=c.token.liquidity_usd or 0,
                )
            except Exception:
                pass

        return candidates

    def _watchlist_score_fn(self, token_address: str, chain: str, signals: dict) -> float:
        """Scoring callback for watchlist re-evaluation."""
        token = self._signals_to_token(signals, chain)
        if not token:
            return 0.0
        candidate = self._score_token(token, is_boosted=False)
        return candidate.gem_score if candidate else 0.0

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

        # ── HARD GATE #1: Solana tokens < 2h old → instant reject ─────────────
        # Tokens this fresh on Solana are still in the rug-pull danger window.
        # The 2h rule lets us see at least 2 candlesticks of real price action
        # before we commit capital. No exceptions — not even for boosted tokens.
        if token.chain == "solana" and (token.age_hours or 0) < 2.0 and not is_cto:
            logger.info(
                f"⛔ SOLANA AGE GATE: {token.symbol} is only {token.age_hours:.1f}h old "
                f"— too fresh for safe entry (< 2h). Skipping."
            )
            return None

        # ── HARD GATE #2: Block-0 Sniper / Bundle Detection ───────────────────────
        # Reject tokens where coordinated snipers acquired a disproportionate
        # share of supply at launch. This structural overhang means the top
        # holders are permanent sellers at any price uptick — no TA signal
        # can overcome it. Hard reject before any scoring runs.
        try:
            from core.bundle_detector import check_bundle
            _bundle = check_bundle(token.address, token.chain)
            if _bundle.is_bundled:
                logger.warning(
                    f"⛔ BUNDLE GATE: {token.symbol} [{token.chain}] rejected — "
                    f"{_bundle.reject_reason}"
                )
                return None
            elif _bundle.detection_method not in (
                "disabled", "skipped_unsupported_chain",
                "skipped_no_data", "skipped_no_supply",
                "skipped_no_holders", "skipped_zero_supply", "error",
            ):
                logger.debug(
                    f"✅ Bundle check clean: {token.symbol} | "
                    f"block0={_bundle.block_0_supply_pct:.1f}% | "
                    f"cluster={_bundle.cluster_supply_pct:.1f}%"
                )
        except Exception as _bd_err:
            logger.debug(f"Bundle detection skipped for {token.symbol}: {_bd_err}")
            
        # ── HARD GATE #3: Stablecoin & Fiat Exclusion ──────────────────────────
        # Reject stablecoins/fiat pegs so we don't accidentally deploy capital 
        # into pegged assets thinking they are gems.
        _sym = token.symbol.upper()
        if ("USD" in _sym or "EUR" in _sym or "AUD" in _sym or "CAD" in _sym or 
            "GBP" in _sym or "STABLE" in _sym or "FIAT" in _sym or "YEN" in _sym or
            _sym in ("DAI", "FRAX", "BUSD", "SDAI", "BTC", "CBTC", "WETH", "WAVAX", "WSOL", "CBBTC")):
            logger.info(
                f"🚫 EXCLUDED FIAT/STABLE: {token.symbol} [{token.chain}] "
                f"— skipping (we avoid stablecoin pairs for gem sniping)"
            )
            return None

        # ── HARD GATE #4: Moralis Security Score & Metadata ────────────────────────
        try:
            from data.providers.moralis_data import get_token_score, get_token_metadata
            
            # Check Token Metadata for the new 'possible_spam' indicator
            metadata_res = get_token_metadata([token.address], token.chain)
            if metadata_res and isinstance(metadata_res, list) and len(metadata_res) > 0:
                metadata = metadata_res[0]
                if metadata.get("possible_spam") is True:
                    logger.warning(
                        f"⛔ SPAM GATE: {token.symbol} [{token.chain}] rejected — "
                        f"Moralis native spam detection triggered."
                    )
                    return None
            
            token_score_data = get_token_score(token.address, token.chain)
            if token_score_data:
                score_value = token_score_data.get("security_score", 100)
                if score_value < 70:
                    logger.warning(
                        f"⛔ SECURITY GATE: {token.symbol} [{token.chain}] rejected — "
                        f"Moralis Security Score {score_value}/100"
                    )
                    return None
                # Save it so we can use it in contract score
                candidate.moralis_security_score = score_value
            else:
                candidate.moralis_security_score = 70
        except Exception as e:
            logger.debug(f"Moralis security/metadata score skipped for {token.symbol}: {e}")
            candidate.moralis_security_score = 70

        # ── Age score (12%) ────────────────────────────────────────────────────────
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

        # ── Volume trend adjustment (cross-cycle momentum) ────────────────
        try:
            from core.volume_trend import VolumeTrendTracker
            _vtt = VolumeTrendTracker()
            _vtt.record(token.address, token.chain, token.volume_1h or 0)
            _vt = _vtt.get_trend(token.address, token.chain)
            if _vt["score_bonus"] != 0 and _vt["readings"] >= 3:
                candidate.volume_score = max(0, min(100, candidate.volume_score + _vt["score_bonus"]))
                candidate.volume_trend = _vt["direction"]
                logger.debug(
                    f"📊 Volume trend {token.symbol}: {_vt['direction']} "
                    f"({_vt['change_pct']:+.0f}%) → vol score {_vt['score_bonus']:+.1f}"
                )
            _vtt.flush()
        except Exception as _vt_err:
            logger.debug(f"Volume trend skipped for {token.symbol}: {_vt_err}")

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
        # ── Dynamic Volume Decay & Holder Momentum (Upgrade 2) ────────────────
        # Incorporate Moralis Deep Analytics if available
        try:
            from data.providers.moralis_data import get_token_analytics
            analytics_data = get_token_analytics(token.address, token.chain)
            
            if analytics_data:
                # 1. Net Buyers & Volume (1 Day or 1 Month based on token age)
                # If < 12h use '1d' fallback, else use 1w or 1m
                if token.age_hours < 12:
                    period_key = "1d"
                else:
                    period_key = "1w" if "1w" in analytics_data else "1m"
                    
                net_buyers = analytics_data.get(period_key, {}).get("net_buyers", 0)
                exp_net_buyers = analytics_data.get(period_key, {}).get("experienced_net_buyers", 0)
                buy_vol = analytics_data.get(period_key, {}).get("buy_volume_usd", 0)
                sell_vol = analytics_data.get(period_key, {}).get("sell_volume_usd", 0)
                
                candidate.moralis_buy_pressure = net_buyers
                candidate.moralis_exp_net_buyers_1w = exp_net_buyers
                
                # Overwhelming sell pressure penalty
                if net_buyers < 0:
                    penalty = 30.0
                    candidate.holder_score = max(0, candidate.holder_score - penalty)
                    logger.info(f"🐌 Negative Net Buyers Penalty: {token.symbol} (net_buyers={net_buyers}) -> -{penalty} holder score")
                elif net_buyers > 50:
                    bonus = 15.0
                    candidate.holder_score = min(100, candidate.holder_score + bonus)
                    logger.info(f"🚀 Massive Net Buyers Bonus: {token.symbol} (net_buyers={net_buyers}) -> +{bonus} holder score")
                    
                # Volume Acceleration/Decay
                if buy_vol > 0 and sell_vol > 0:
                    buy_sell_ratio = buy_vol / sell_vol
                    if buy_sell_ratio < 0.5:
                        penalty = 15.0
                        candidate.volume_score = max(0, candidate.volume_score - penalty)
                        logger.info(f"📉 Volume Decay Penalty: {token.symbol} (buy:sell={buy_sell_ratio:.2f}) -> -{penalty} vol score")
                    elif buy_sell_ratio > 2.0:
                        bonus = 15.0
                        candidate.volume_score = min(100, candidate.volume_score + bonus)
                        logger.info(f"📈 Volume Acceleration Bonus: {token.symbol} (buy:sell={buy_sell_ratio:.2f}) -> +{bonus} vol score")

        except Exception as e:
            logger.debug(f"Moralis analytics skipped for {token.symbol}: {e}")

        # Smart Money Convergence (Whale + Sniper Confluence)
        whale_buyers = getattr(candidate, 'moralis_exp_net_buyers_1w', 0) or 0
        sniper_count = getattr(candidate, 'sniper_count', 0) or 0
        
        if whale_buyers >= 5 and sniper_count >= 2 and getattr(candidate, 'sniper_risk', 'unknown') != 'critical':
            candidate.smart_money_score = min(100, getattr(candidate, 'smart_money_score', 50) + 25)
            logger.info(f"🐋🎯 Smart Money Confluence: {token.symbol} (whales={whale_buyers}, snipers={sniper_count}) -> +25 smart money score")

        # ── Social score (6%) — REAL social scoring ───────────────────────────
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
        # Default 70 (or Moralis security score) — updated by GoPlus safety check in executor
        candidate.contract_score = getattr(candidate, "moralis_security_score", 70)

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

            # ── Helius DAS + Moralis Solana Gateway enrichment ────────────────────
            # Uses Helius DAS (getAsset, getTokenAccounts) + Moralis Solana
            # gateway for richer metadata, authority checks, and price data.
            # Score bonus: -10 to +15 points based on on-chain safety signals.
            try:
                from data.providers.helius_enrichment import enrich_solana_token
                # Load known sniper wallets for presence check
                _sniper_wallets: list[str] = []
                try:
                    import json as _json, os as _os
                    _lb_path = _os.path.join(
                        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                        "data", "dashboard", "sniper_leaderboard.json"
                    )
                    if _os.path.exists(_lb_path):
                        _lb = _json.loads(open(_lb_path).read())
                        _sniper_wallets = [
                            w.get("address", "") for w in _lb
                            if w.get("is_active") and w.get("chain") == "solana"
                        ]
                except Exception:
                    pass

                _helius_enrich = enrich_solana_token(
                    token.address,
                    known_sniper_wallets=_sniper_wallets or None,
                )
                # Apply score bonus from enrichment
                if _helius_enrich.sniper_score_bonus != 0:
                    candidate.gem_score = max(
                        0.0,
                        min(100.0, candidate.gem_score + _helius_enrich.sniper_score_bonus)
                    )
                    logger.debug(
                        f"Helius enrichment bonus for {token.symbol}: "
                        f"{_helius_enrich.sniper_score_bonus:+.1f} pts "
                        f"(top10={_helius_enrich.top10_holder_pct}, "
                        f"mutable={_helius_enrich.is_mutable_metadata}, "
                        f"mint_auth={_helius_enrich.is_mint_authority_set})"
                    )
                # Store enrichment data on candidate for dashboard display
                candidate.helius_enrichment = _helius_enrich.to_dict()
                # Override holder concentration if Helius gave us better data
                if _helius_enrich.top10_holder_pct is not None:
                    conc_pct = _helius_enrich.top10_holder_pct
                    if conc_pct >= 80:
                        candidate.holder_concentration_score = 10.0
                    elif conc_pct >= 50:
                        candidate.holder_concentration_score = 30.0
                    elif conc_pct >= 30:
                        candidate.holder_concentration_score = 60.0
                    else:
                        candidate.holder_concentration_score = 90.0
                # Smart wallet presence boosts conviction
                if _helius_enrich.smart_wallet_count >= 3:
                    candidate.smart_money_score = min(
                        100.0, candidate.smart_money_score + 20.0
                    )
                elif _helius_enrich.smart_wallet_count >= 1:
                    candidate.smart_money_score = min(
                        100.0, candidate.smart_money_score + 10.0
                    )
            except Exception as _he_err:
                logger.debug(f"Helius enrichment failed for {token.symbol}: {_he_err}")

        # ── TimesFM Price Direction Forecast ────────────────────────────────────
        # Google’s 200M-parameter time series foundation model (zero-shot).
        # Runs locally on VPS CPU. Falls back to linear regression if not installed.
        # Applies a score bonus (UP) or penalty (DOWN) based on direction + confidence.
        try:
            from ml.timesfm_signal import get_forecast_from_dexscreener
            _tf_result = get_forecast_from_dexscreener(
                token_address=token.address,
                chain=token.chain,
                pair_address=getattr(token, "pair_address", ""),
            )
            _tf_delta = _tf_result.get("score_delta", 0.0)
            if _tf_delta != 0.0:
                pre_tf = candidate.gem_score
                candidate.gem_score = max(0.0, min(100.0, round(candidate.gem_score + _tf_delta, 2)))
                logger.debug(
                    f"🔮 TimesFM [{_tf_result.get('method','?')}] {token.symbol}: "
                    f"dir={_tf_result.get('direction','?')} "
                    f"conf={_tf_result.get('confidence', 0):.0%} "
                    f"→ score {pre_tf} {_tf_delta:+.1f} = {candidate.gem_score}"
                )
            candidate.timesfm_direction = _tf_result.get("direction", "FLAT")
            candidate.timesfm_confidence = _tf_result.get("confidence", 0.0)
            candidate.timesfm_method = _tf_result.get("method", "none")
        except Exception as _tf_err:
            logger.debug(f"TimesFM signal skipped for {token.symbol}: {_tf_err}")
            candidate.timesfm_direction = "FLAT"
            candidate.timesfm_confidence = 0.0
            candidate.timesfm_method = "none"

        # ── Enhanced signal enrichment (Phase 3) ────────────────────────────────
        # ⚡ MORALIS-FIRST ENRICHMENT: 5 lean parallel calls replace the old 9.
        # Removed: DefiLlama TVL, LunarCrush social, holder_analysis, token_unlocks
        # All replaced by Moralis ecosystem signals (discovery, analytics, pair stats).
        # Grok sentiment (6-8s LLM call, 5% weight) still deferred to 2nd pass.
        if base_score >= 45:
            from concurrent.futures import ThreadPoolExecutor, as_completed

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

            def _get_moralis_money():
                return moralis_enrich(token.address, token.chain)

            def _get_binance_pulse():
                if not settings.BINANCE_PULSE_ENABLED:
                    return {"binance_smart_money_confirmed": False, "binance_social_hype_score": 50.0}
                return binance_enrich(token.address, chain=token.chain)

            def _get_intelligence():
                """Full Moralis intelligence suite — top traders, snipers, holders, swap flow."""
                return enrich_token_intelligence(
                    token_address=token.address,
                    chain=token.chain,
                    pair_address=getattr(token, "pair_address", ""),
                    is_solana=(token.chain == "solana"),
                )

            # Submit 6 enrichment calls — added moralis_intelligence for full suite
            enrichment_results = {}
            future_map = {}
            with ThreadPoolExecutor(max_workers=6, thread_name_prefix="enrich") as pool:
                future_map = {
                    pool.submit(_get_dev): "dev",
                    pool.submit(_get_copycat): "copycat",
                    pool.submit(_get_moralis_meta): "moralis_meta",
                    pool.submit(_get_moralis_money): "moralis_money",
                    pool.submit(_get_binance_pulse): "binance_pulse",
                    pool.submit(_get_intelligence): "moralis_intelligence",
                }
                try:
                    for future in as_completed(future_map, timeout=15):
                        name = future_map[future]
                        try:
                            enrichment_results[name] = future.result()
                        except Exception as e:
                            logger.debug(f"Enrichment '{name}' failed for {token.symbol}: {e}")
                            enrichment_results[name] = None
                except TimeoutError:
                    # Cancel any slow futures that haven't completed yet to avoid
                    # the "N futures unfinished" log noise on ThreadPoolExecutor exit.
                    for f, n in future_map.items():
                        if not f.done():
                            f.cancel()
                            logger.debug(f"Enrichment '{n}' timed out for {token.symbol} — cancelled")

            # Moralis-derived scores replace removed custom providers
            candidate.tvl_score = 50.0              # Now inside Moralis (liquidity_locked_pct)
            candidate.social_sentiment_score = 50.0  # Now inside Moralis (on_chain_strength)
            candidate.holder_concentration_score = 50.0  # Now inside Moralis (pair stats)
            candidate.unlock_risk_score = 50.0       # Removed — negligible for micro-caps
            candidate.grok_sentiment_score = 50.0    # Deferred to 2nd pass

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
            candidate.moralis_is_bonding = False
            candidate.moralis_pair_buyers_5m = 0
            candidate.moralis_pair_sellers_5m = 0

        # ── GROK SENTIMENT (conditional second pass — 5% weight) ──────────────
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

            # ── Moralis Cortex AI — on-chain grounded analysis (P6) ─────────
            # Runs only if prelim_score >= 48 AND token is on EVM chain
            # Cortex is grounded in Moralis data — different from Grok (X/Twitter)
            # and Perplexity (web search). Score delta applied to grok_sentiment_score.
            if token.chain != "solana" and prelim_score >= 48:
                try:
                    from data.providers.moralis_intelligence import cortex_analyze_token
                    _cortex = cortex_analyze_token(
                        token_address=token.address,
                        chain=token.chain,
                        symbol=token.symbol,
                    )
                    if _cortex and not _cortex.get("skipped"):
                        # Blend Cortex delta into grok_sentiment_score (both are sentiment signals)
                        # Cortex is on-chain grounded; Grok is social. Average them.
                        cortex_adj = _cortex.get("score_delta", 0.0)
                        candidate.grok_sentiment_score = min(
                            100.0,
                            max(0.0, candidate.grok_sentiment_score + cortex_adj * 0.5)
                        )
                        logger.debug(
                            f"Cortex AI [{token.symbol}]: {_cortex['sentiment']} "
                            f"delta={cortex_adj:+.1f} → grok_score={candidate.grok_sentiment_score:.1f}"
                        )
                except Exception as _cx_err:
                    logger.debug(f"Cortex AI skipped for {token.symbol}: {_cx_err}")

        # ── Moralis Money Enrichment (PRIMARY source — 27% weight) ─────────────
        # ⚡ Now runs IN the parallel pool above. Results from enrichment_results.
        # This is the DOMINANT scoring signal — replaces TVL, social, holders, unlocks.
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
                    # Whale accumulation + discovery signals
                    candidate.moralis_exp_net_buyers_1d = enrichment.get("moralis_exp_net_buyers_1d", 0)
                    candidate.moralis_exp_net_buyers_1w = enrichment.get("moralis_exp_net_buyers_1w", 0)
                    candidate.moralis_holders_change_1d = enrichment.get("moralis_holders_change_1d", 0)
                    candidate.moralis_holders_change_1w = enrichment.get("moralis_holders_change_1w", 0)
                    candidate.moralis_on_chain_strength = enrichment.get("moralis_on_chain_strength", 0.0)
                    candidate.moralis_liquidity_locked_pct = enrichment.get("moralis_liquidity_locked_pct", 0.0)
                    candidate.moralis_security_score = enrichment.get("moralis_security_score", 0)
                    candidate.moralis_token_age_days = enrichment.get("moralis_token_age_days", 0.0)

                    # ── NEW: Bonding status reject gate ──────────────────────
                    candidate.moralis_is_bonding = enrichment.get("moralis_is_bonding", False)
                    if enrichment.get("moralis_is_bonding", False):
                        bonding_exchange = enrichment.get("moralis_bonding_exchange", "unknown")
                        logger.info(
                            f"⛔ BONDING REJECT: {token.symbol} still on bonding curve "
                            f"({bonding_exchange}) — pre-graduation = high rug risk. Skipping."
                        )
                        return None  # Hard reject — don't even score

                    # ── NEW: Pair stats (buyer/seller velocity) ──────────────
                    candidate.moralis_pair_buyers_5m = enrichment.get("moralis_pair_buyers_5m", 0)
                    candidate.moralis_pair_sellers_5m = enrichment.get("moralis_pair_sellers_5m", 0)
                    candidate.moralis_pair_buy_vol_1h = enrichment.get("moralis_pair_buy_vol_1h", 0.0)
                    candidate.moralis_pair_sell_vol_1h = enrichment.get("moralis_pair_sell_vol_1h", 0.0)
                    candidate.moralis_pair_buyers_24h = enrichment.get("moralis_pair_buyers_24h", 0)
                    candidate.moralis_pair_sellers_24h = enrichment.get("moralis_pair_sellers_24h", 0)
                    candidate.moralis_total_liquidity = enrichment.get("moralis_total_liquidity", 0.0)

                    # ── Entry timing intelligence (multi-timeframe) ──────────
                    candidate.timing_bp_trend = enrichment.get("timing_bp_trend", "flat")
                    candidate.timing_bp_micro_ratio = enrichment.get("timing_bp_micro_ratio", 1.0)
                    candidate.timing_volume_acceleration = enrichment.get("timing_volume_acceleration", 1.0)
                    candidate.timing_buyer_velocity = enrichment.get("timing_buyer_velocity", 1.0)
                    candidate.timing_score = enrichment.get("timing_score", 50.0)

                    # Whale accumulation bonus: log and SCORE strong whale interest
                    exp_net_1w = enrichment.get("moralis_exp_net_buyers_1w", 0)
                    exp_net_1d = enrichment.get("moralis_exp_net_buyers_1d", 0)
                    if exp_net_1w >= 10:
                        # Strong institutional accumulation: +15 to gem score
                        pre_sc = candidate.gem_score
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 15.0, 2))
                        logger.info(
                            f"🐋 WHALE ACCUMULATION: {token.symbol} — "
                            f"{exp_net_1w} experienced net buyers this week → "
                            f"+15 (score {pre_sc} → {candidate.gem_score})"
                        )
                    elif exp_net_1w >= 5:
                        # Moderate whale interest: +8 to gem score
                        pre_sc = candidate.gem_score
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 8.0, 2))
                        logger.info(
                            f"🐋 WHALE INTEREST: {token.symbol} — "
                            f"{exp_net_1w} experienced net buyers this week → "
                            f"+8 (score {pre_sc} → {candidate.gem_score})"
                        )
                    elif exp_net_1d >= 5:
                        # Short-term whale activity: +5 to gem score
                        pre_sc = candidate.gem_score
                        candidate.gem_score = min(100.0, round(candidate.gem_score + 5.0, 2))
                        logger.info(
                            f"🐳 WHALE ACTIVITY: {token.symbol} — "
                            f"{exp_net_1d} experienced net buyers today → "
                            f"+5 (score {pre_sc} → {candidate.gem_score})"
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

                    # Entry timing gate log
                    bp_trend = enrichment.get("timing_bp_trend", "flat")
                    vol_accel = enrichment.get("timing_volume_acceleration", 1.0)
                    t_score = enrichment.get("timing_score", 50.0)

                    if bp_trend == "accelerating":
                        logger.info(
                            f"🚀 ACCELERATING: {token.symbol} — "
                            f"timing_score={t_score:.0f} "
                            f"vol_accel={vol_accel:.1f}x "
                            f"micro_ratio={enrichment.get('timing_bp_micro_ratio', 1.0):.2f}"
                        )
                    elif bp_trend == "decelerating":
                        logger.info(
                            f"⏭️ DECELERATING: {token.symbol} — "
                            f"timing_score={t_score:.0f} "
                            f"vol_accel={vol_accel:.1f}x "
                            f"(pressure fading, late entry risk)"
                        )

                    # Pair stats velocity log
                    pb5 = enrichment.get("moralis_pair_buyers_5m", 0)
                    ps5 = enrichment.get("moralis_pair_sellers_5m", 0)
                    if pb5 + ps5 > 0:
                        pair_ratio = pb5 / (pb5 + ps5)
                        if pair_ratio >= 0.70:
                            logger.info(
                                f"📊 PAIR VELOCITY: {token.symbol} — "
                                f"{pb5} buyers vs {ps5} sellers in 5m ({pair_ratio:.0%} buy)"
                            )

                    if enrichment.get("moralis_score", 0) > 0:
                        logger.debug(
                            f"Moralis enrichment {token.symbol}: "
                            f"score={enrichment['moralis_score']} "
                            f"buy_pressure={enrichment['moralis_buy_pressure']:.2f} "
                            f"net_buyers_1h={enrichment['moralis_net_buyers_1h']} "
                            f"whale_1w={exp_net_1w} "
                            f"timing={bp_trend} vol_accel={vol_accel:.1f}x "
                            f"holders_1d={enrichment.get('moralis_holders_change_1d', 0)} "
                            f"pair_5m={pb5}b/{ps5}s liq=${enrichment.get('moralis_total_liquidity', 0):,.0f}"
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

        # ── Final composite score (15 signals — Moralis-first + rug protection) ───
        # Weights sum to 1.00. Moralis enrichment now at 27% — DOMINANT signal.
        # Removed: tvl(0.04), social_sentiment(0.04), holder_conc(0.03), unlock(0.02)
        # All replaced by Moralis native signals inside moralis_enrichment_score.
        # Dev wallet (4%) and copycat (5%) rug-protection retained.
        # ── Final composite score ────────────────────────────────────────────────────────────
        # Uses ML-derived dynamic weights (self._weights) when sufficient trade
        # history exists, otherwise falls back to static defaults.
        # Fixed-weight signals (safety/rug protection) are NOT ML-adjusted.
        _w = self._weights
        candidate.gem_score = round(
            candidate.age_score              * _w.get("age", 0.04)
            + candidate.volume_score         * _w.get("volume", 0.07)
            + candidate.liquidity_score      * _w.get("liquidity", 0.07)
            + candidate.buy_pressure_score   * 0.06   # Fixed: buy pressure (was 0.08, rebalanced for Moralis)
            + candidate.moralis_enrichment_score * 0.32  # Fixed: Moralis dominant signal
            + candidate.sniper_score         * 0.04   # Fixed: Solana sniper detection
            + candidate.contract_score       * 0.05   # Fixed: safety signal (was 0.06, rebalanced)
            + candidate.holder_score         * _w.get("whale_holder", 0.05)
            + candidate.tax_score            * 0.05   # Fixed: safety signal (was 0.06, rebalanced)
            + candidate.social_score         * _w.get("social", 0.05)
            + candidate.boost_score          * _w.get("boost_cto", 0.04)
            + candidate.smart_money_score    * 0.02   # Fixed: smart money baseline (was 0.03, rebalanced)
            + candidate.grok_sentiment_score * _w.get("grok_sentiment", 0.05)
            + candidate.dev_wallet_score     * 0.04   # Fixed: rug protection
            + candidate.copycat_score        * 0.05,  # Fixed: rug protection
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

        # ── MORALIS INTELLIGENCE SCORE BOOST ──────────────────────────────────────────────────
        # Apply all new intelligence signals (top traders, snipers, holder trend,
        # momentum timeseries, swap flow, chain heat) as a score delta.
        # Max +30 / -25 points. Runs AFTER base composite and bonuses.
        if base_score >= 45:
            intel = enrichment_results.get("moralis_intelligence", {}) if base_score >= 45 else {}
            if intel:
                try:
                    intel_delta, intel_reasons = calculate_intelligence_score_boost(intel)
                    if intel_delta != 0.0:
                        pre_intel = candidate.gem_score
                        candidate.gem_score = max(0.0, min(100.0, round(candidate.gem_score + intel_delta, 2)))
                        # Store intel fields on candidate for dashboard display
                        candidate.intel_smart_money_buying    = intel.get("intel_smart_money_buying", False)
                        candidate.intel_smart_money_score     = intel.get("intel_smart_money_score", 50.0)
                        candidate.intel_sniper_count          = intel.get("intel_sniper_count", 0)
                        candidate.intel_sniper_risk           = intel.get("intel_sniper_risk", "unknown")
                        candidate.intel_momentum_trend        = intel.get("intel_momentum_trend", "neutral")
                        candidate.intel_holder_trend          = intel.get("intel_holder_trend", "stable")
                        candidate.intel_holder_growth_pct     = intel.get("intel_holder_growth_pct", 0.0)
                        candidate.intel_concentration_risk    = intel.get("intel_concentration_risk", "unknown")
                        candidate.intel_whale_buying          = intel.get("intel_whale_buying", False)
                        candidate.intel_swap_flow_score       = intel.get("intel_swap_flow_score", 50.0)
                        candidate.intel_chain_heat            = intel.get("intel_chain_heat", 50.0)
                        candidate.intel_score_trend           = intel.get("intel_score_trend", "stable")
                        if intel_delta > 0:
                            logger.info(
                                f"🧠 INTEL BOOST: {token.symbol} +{intel_delta:.1f} "
                                f"({', '.join(intel_reasons[:3])}) "
                                f"score {pre_intel} → {candidate.gem_score}"
                            )
                        else:
                            logger.info(
                                f"🧠 INTEL PENALTY: {token.symbol} {intel_delta:.1f} "
                                f"({', '.join(intel_reasons[:3])}) "
                                f"score {pre_intel} → {candidate.gem_score}"
                            )
                    # Hard block: critical EVM snipers → reject immediately
                    if intel.get("intel_sniper_risk") == "critical" or intel.get("intel_sniper_count", 0) >= 10:
                        logger.warning(
                            f"⛔ EVM SNIPER BLOCK: {token.symbol} — "
                            f"{intel.get('intel_sniper_count', 0)} snipers (critical risk) → dropped"
                        )
                        return None
                except Exception as e:
                    logger.debug(f"Intelligence boost failed for {token.symbol}: {e}")

        # ── ENTRY TIMING INTEGRATION: timing_score adjusts gem_score ────────────────────
        # timing_score (0–100) from Moralis multi-timeframe entry intelligence.
        # Accelerating buy pressure = momentum building = BEST time to enter.
        # Decelerating buy pressure = momentum fading = LATE entry risk.
        # Only apply when timing data is actually available (not default 50).
        _timing_score = getattr(candidate, 'timing_score', 50.0)
        _timing_bp_trend = getattr(candidate, 'timing_bp_trend', 'flat')
        _timing_vol_accel = getattr(candidate, 'timing_volume_acceleration', 1.0)
        if _timing_bp_trend == 'accelerating' and _timing_score > 60:
            # Strong momentum building: best possible entry window
            _timing_bonus = min(8.0, round((_timing_score - 60) * 0.4, 1))
            pre_adj = candidate.gem_score
            candidate.gem_score = min(100.0, round(candidate.gem_score + _timing_bonus, 2))
            logger.info(
                f"⏱️ TIMING BONUS: {token.symbol} — accelerating BP → +{_timing_bonus:.1f} "
                f"(timing_score={_timing_score:.0f}, vol_accel={_timing_vol_accel:.1f}x) "
                f"score {pre_adj} → {candidate.gem_score}"
            )
        elif _timing_bp_trend == 'decelerating' and _timing_score < 40:
            # Momentum fading: penalise to avoid chasing a dying move
            _timing_penalty = min(12.0, round((40 - _timing_score) * 0.6, 1))
            pre_adj = candidate.gem_score
            candidate.gem_score = max(0.0, round(candidate.gem_score - _timing_penalty, 2))
            logger.info(
                f"⏱️ TIMING PENALTY: {token.symbol} — decelerating BP → -{_timing_penalty:.1f} "
                f"(timing_score={_timing_score:.0f}, vol_accel={_timing_vol_accel:.1f}x) "
                f"score {pre_adj} → {candidate.gem_score}"
            )

        # ── Express lane flag ───────────────────────────────────────────────────────────────────────────
        # CTO tokens with score >= 75 also qualify for express lane
        # (lower threshold than standard 82 — CTO is inherently high-conviction)
        cto_express_threshold = 75.0
        candidate.express_lane = (
            candidate.gem_score >= settings.EXPRESS_LANE_SCORE
            or (is_cto and candidate.gem_score >= cto_express_threshold)
        )

        # ── HISTORICAL PRICE CONTEXT: 7-day range position adjustment ─────────
        # Penalizes overextended entries near 7d ATH (-10 pts)
        # Rewards accumulation zone entries in bottom 30% of range (+8 pts)
        # This is the last adjustment so it can cap or boost based on WHERE
        # we are buying, regardless of all other signals.
        try:
            from data.providers.moralis_money import get_historical_price_context
            price_ctx = get_historical_price_context(
                token_address=token.address,
                chain=token.chain,
                current_price=token.price_usd,
                pair_address=getattr(token, "pair_address", ""),
            )
            candidate.price_range_position = price_ctx.get("range_position", 0.5)
            candidate.price_context_score = price_ctx.get("context_score", 50.0)
            candidate.is_near_ath = price_ctx.get("is_near_ath", False)
            candidate.is_accumulation_zone = price_ctx.get("is_accumulation_zone", False)
            candidate.vol_trend_7d = price_ctx.get("vol_trend_7d", "neutral")

            if price_ctx.get("is_near_ath", False):
                # Penalize: buying near ATH — high reversal risk
                pre_adj = candidate.gem_score
                candidate.gem_score = max(0.0, round(candidate.gem_score - 10.0, 2))
                logger.info(
                    f"📉 NEAR-ATH PENALTY: {token.symbol} "
                    f"range_pos={price_ctx['range_position']:.0%} "
                    f"→ score {pre_adj} - 10 = {candidate.gem_score}"
                )
                # ── HARD GATE #2: Near-ATH with no whale backing → reject ───
                # If we're in the top 15% of the 7d range AND there's no smart
                # money behind it, this is a late FOMO entry — highest loss risk.
                whale_backing = getattr(candidate, "moralis_exp_net_buyers_1w", 0) or 0
                buy_pressure = getattr(candidate, "moralis_buy_pressure", 0.0) or 0.0
                if whale_backing < 3 and buy_pressure < 0.65:
                    logger.info(
                        f"⛔ NEAR-ATH REJECT: {token.symbol} is near 7d ATH with no whale "
                        f"confirmation (exp_buyers={whale_backing}, bp={buy_pressure:.0%}) — "
                        f"FOMO entry rejected."
                    )
                    return None
            elif price_ctx.get("is_accumulation_zone", False):
                # Reward: buying in the dip with on-chain strength
                pre_adj = candidate.gem_score
                bonus = 10.0 if price_ctx.get("vol_trend_7d") == "expanding" else 8.0
                candidate.gem_score = min(100.0, round(candidate.gem_score + bonus, 2))
                logger.info(
                    f"🟢 ACCUMULATION ZONE BONUS: {token.symbol} "
                    f"range_pos={price_ctx['range_position']:.0%} "
                    f"vol={price_ctx['vol_trend_7d']} "
                    f"→ score {pre_adj} + {bonus:.0f} = {candidate.gem_score}"
                )
            else:
                logger.debug(
                    f"📊 Price context: {token.symbol} "
                    f"range_pos={price_ctx.get('range_position', 0.5):.0%} "
                    f"ctx_score={price_ctx.get('context_score', 50):.0f} "
                    f"vol={price_ctx.get('vol_trend_7d', 'neutral')}"
                )
        except Exception as e:
            logger.debug(f"Historical price context failed for {token.symbol}: {e}")
            candidate.price_range_position = 0.5
            candidate.price_context_score = 50.0
            candidate.is_near_ath = False
            candidate.is_accumulation_zone = False
            candidate.vol_trend_7d = "neutral"

        # ── CoinPaprika: True All-Time ATH Gate ──────────────────────────────────
        # Supplements the 7-day ATH gate with true all-time ATH data (free, no key).
        # Rejects tokens within 15% of their all-time high — strongest FOMO signal.
        # Graceful no-op if CoinPaprika doesn’t have the token indexed.
        try:
            from data.providers.coinpaprika import check_alltime_ath_gate
            cp_reject, cp_reason = check_alltime_ath_gate(
                symbol=token.symbol,
                current_price_usd=token.price_usd,
                name=getattr(token, "name", ""),
                reject_within_pct=0.15,
            )
            if cp_reject:
                logger.info(f"⛔ ALLTIME-ATH REJECT: {token.symbol} — {cp_reason}")
                return None
        except Exception as _cp_err:
            logger.debug(f"CoinPaprika ATH gate skipped for {token.symbol}: {_cp_err}")

        # ── Apply ChainAware score penalty (if safety check stored one) ─────────────
        # safety.py stores chainaware_penalty on SafetyResult when the deployer
        # wallet has suspicious (but sub-threshold) fraud indicators.
        try:
            safety_result = getattr(candidate, "_safety_result", None)
            ca_penalty = getattr(safety_result, "chainaware_penalty", 0.0) or 0.0
            if ca_penalty > 0:
                pre_adj = candidate.gem_score
                candidate.gem_score = max(0.0, round(candidate.gem_score - ca_penalty, 2))
                logger.info(
                    f"🔴 CHAINAWARE PENALTY: {token.symbol} deployer risk → "
                    f"score {pre_adj} - {ca_penalty:.1f} = {candidate.gem_score}"
                )
        except Exception:
            pass

        # ── FINAL GATE: Solana Meme Coin Quality Floor ─────────────────────────────────────────────────────────────────────────────────────
        # Solana meme coins need a HIGHER bar than EVM tokens. The ecosystem
        # is flooded with low-quality pump-and-dumps. Only take the cream.
        SOLANA_MIN_SCORE = 65.0
        if token.chain == "solana" and candidate.gem_score < SOLANA_MIN_SCORE:
            logger.info(
                f"⛔ SOLANA QUALITY GATE: {token.symbol} score={candidate.gem_score:.1f} "
                f"< {SOLANA_MIN_SCORE} Solana minimum. Only high-conviction Solana trades allowed."
            )
            return None

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
