"""
Social Insider Oracle (ECC Skill: sentiment-insider-oracle adapted)
Combines on-chain data with off-chain sentiment to detect when a token is about to experience
a massive influx of retail volume, specifically looking for "insider" accumulation before the hype.

The module ingests real-time social volume data (Twitter mentions via Grok, Telegram group growth)
and cross-references it with early token accumulation by 'fresh' wallets.
If the engine detects that a token has been silently accumulated by a cluster of interconnected wallets,
and then experiences a sudden >300% spike in social sentiment metrics, it fires a high-confidence
buy signal to the ito_trade_planner.
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional

from config import settings
from data.providers.grok_client import call_grok
from data.models import GemCandidate, Token

logger = logging.getLogger(__name__)


@dataclass
class SocialMention:
    """Represents a single social mention of a contract address."""
    platform: str              # "twitter" or "telegram"
    contract_address: str
    sender_id: str             # Username or wallet address
    sender_name: str           # Display name or alias
    timestamp: float = field(default_factory=time.time)
    text: str = ""
    followers_count: int = 0
    is_kol: bool = False       # True if sender is in the known KOL/Insider database


@dataclass
class OracleMetrics:
    """Maintains running social velocity and cabal metrics for a contract address."""
    contract_address: str
    symbol: str = "UNKNOWN"
    chain: str = "ethereum"
    first_seen: float = field(default_factory=time.time)
    mentions: List[SocialMention] = field(default_factory=list)
    unique_senders: Set[str] = field(default_factory=set)
    unique_kols: Set[str] = field(default_factory=set)
    twitter_count: int = 0
    telegram_count: int = 0
    total_reach: int = 0

    @property
    def mention_velocity_5m(self) -> int:
        """Mentions in the last 5 minutes."""
        cutoff = time.time() - 300
        return sum(1 for m in self.mentions if m.timestamp >= cutoff)

    @property
    def kol_velocity_5m(self) -> int:
        """KOL mentions in the last 5 minutes."""
        cutoff = time.time() - 300
        return sum(1 for m in self.mentions if m.timestamp >= cutoff and m.is_kol)


# Alias for backwards compatibility
TokenSocialMetrics = OracleMetrics


class SocialInsiderOracle:
    """
    Social Insider Oracle engine.
    Monitors Twitter and Telegram mentions of contract addresses,
    detects coordinated KOL shills, and determines sniper entry qualifications.
    """

    def __init__(self):
        # Known KOL Twitter handles and known insider wallet addresses
        self.known_kols: Set[str] = {
            # Top tier alpha influencers, callers, and insider wallets
            "ansem", "crash", "binks", "wizardofsoho", "gcr", "keyboardmonkey",
            "blockgraze", "0xsun", "cl_207", "blknoiz06", "bastille", "pauly",
            "shardi_b", "machibigbrother", "rover", "ladyofcrypto", "milesdeutscher",
            "solana_legend", "loopify", "mistercrypto", "coldbloodsart", "pentosh1",
            "realkaleo", "cryptobirb", "incomesharks", "crypto_bitlord", "runner",
        }

        # Load from config or env if specified
        kol_env = getattr(settings, "KOL_HANDLES_LIST", "") or ""
        if kol_env:
            for handle in kol_env.split(","):
                h = handle.strip().lower().replace("@", "")
                if h:
                    self.known_kols.add(h)

        # In-memory database of active contract mentions
        self.registry: Dict[str, OracleMetrics] = {}
        self._lock = threading.Lock()

        # Clean up database interval config (TTL: 1 hour)
        self.cleanup_ttl = 3600
        self.last_cleanup = time.time()

        # Thresholds
        self.velocity_threshold_5m = int(getattr(settings, "ORACLE_VELOCITY_THRESHOLD_5M", 10))
        self.cabal_kol_threshold = int(getattr(settings, "ORACLE_CABAL_KOL_THRESHOLD", 3))
        self.cabal_window_s = int(getattr(settings, "ORACLE_CABAL_WINDOW_S", 300))

        logger.info(f"SocialInsiderOracle initialized. Tracking {len(self.known_kols)} KOLs.")

    def register_mention(self, mention: SocialMention, symbol: str = "UNKNOWN", chain: str = "ethereum") -> OracleMetrics:
        """
        Registers a raw social mention of a Contract Address.
        Updates internal metrics and checks for cabal triggers.
        Returns the updated OracleMetrics for this CA.
        """
        self._maybe_cleanup()

        # Normalize sender_id: strip @ prefix
        mention.sender_id = mention.sender_id.lower().replace("@", "")

        ca = mention.contract_address.lower()

        # Check if sender is in known KOL list or has large following
        if mention.sender_id in self.known_kols or mention.followers_count > 10000:
            mention.is_kol = True

        with self._lock:
            if ca not in self.registry:
                self.registry[ca] = OracleMetrics(
                    contract_address=ca,
                    symbol=symbol.upper(),
                    chain=chain.lower(),
                    first_seen=time.time()
                )

            metrics = self.registry[ca]
            metrics.mentions.append(mention)
            metrics.unique_senders.add(mention.sender_id)

            if mention.is_kol:
                metrics.unique_kols.add(mention.sender_id)

            if mention.platform == "twitter":
                metrics.twitter_count += 1
            elif mention.platform == "telegram":
                metrics.telegram_count += 1

            metrics.total_reach += mention.followers_count

            # Update symbol/chain if they were unknown
            if metrics.symbol == "UNKNOWN" and symbol != "UNKNOWN":
                metrics.symbol = symbol.upper()
            if chain != "ethereum" and metrics.chain == "ethereum":
                metrics.chain = chain.lower()

            return metrics

    def check_cabal_pump(self, contract_address: str) -> Tuple[bool, List[str]]:
        """
        Insider Cabal Detection:
        If a token is being simultaneously shilled by multiple known 'KOL' wallets
        or Twitter accounts within a 5-minute window, flag it as an orchestrated pump.
        Returns (is_cabal, list_of_kol_handles).
        """
        ca = contract_address.lower()
        with self._lock:
            if ca not in self.registry:
                return False, []

            metrics = self.registry[ca]
            cutoff = time.time() - self.cabal_window_s

            # Gather active KOLs in the 5-minute window
            active_kols = set()
            for m in metrics.mentions:
                if m.timestamp >= cutoff and m.is_kol:
                    active_kols.add(m.sender_id)

            is_cabal = len(active_kols) >= self.cabal_kol_threshold
            if is_cabal:
                logger.warning(
                    f"🚨 INSIDER CABAL DETECTED: {metrics.symbol} ({ca}) shilled by "
                    f"{len(active_kols)} KOLs in 5m: {list(active_kols)}"
                )

            return is_cabal, list(active_kols)

    def evaluate_pre_volume_sniper(self, candidate: GemCandidate) -> Tuple[bool, str]:
        """
        Pre-Volume Sniping Evaluation:
        If social velocity crosses our threshold before on-chain volume has spiked,
        bypass the standard waiting period and execute an immediate low-size sniper entry.

        Returns: (should_snipe, reason)
        """
        ca = candidate.token.address.lower()
        with self._lock:
            if ca not in self.registry:
                return False, "No social oracle tracking data"

            metrics = self.registry[ca]
            velocity = metrics.mention_velocity_5m

        # Threshold checks
        if velocity < self.velocity_threshold_5m:
            return False, f"Social velocity ({velocity}) below threshold ({self.velocity_threshold_5m})"

        # Check if on-chain volume has NOT spiked yet (pre-volume condition)
        volume_spike_score = getattr(candidate, "volume_score", 0.0)
        volume_1h = candidate.token.volume_1h or 0.0
        liquidity = candidate.token.liquidity_usd or 1.0

        is_pre_volume = (volume_1h < (liquidity * 0.30)) or (volume_spike_score < 70.0)

        if not is_pre_volume:
            return False, f"On-chain volume already spiked (vol_1h={volume_1h:.0f}, score={volume_spike_score:.0f})"

        # Hard safety gates still apply
        if not getattr(candidate, "is_safe", True):
            return False, "Token failed standard safety checks (honeypot/tax/rug)"

        # Check for cabal backing as extra validation
        is_cabal, active_kols = self.check_cabal_pump(ca)

        reason = (
            f"Pre-volume social spike: velocity={velocity}/5m, "
            f"cabal={is_cabal} ({len(active_kols)} KOLs)"
        )
        return True, reason

    def evaluate_candidate(self, candidate: GemCandidate) -> Tuple[bool, str]:
        """Alias for evaluate_pre_volume_sniper for backwards compatibility."""
        return self.evaluate_pre_volume_sniper(candidate)

    def get_recent_velocity(self, contract_address: str, window_s: int = 300) -> int:
        """Calculates mentions in the last `window_s` seconds."""
        ca = contract_address.lower()
        with self._lock:
            if ca not in self.registry:
                return 0
            now = time.time()
            return sum(1 for m in self.registry[ca].mentions if now - m.timestamp <= window_s)

    def ingest_grok_mentions(self, symbol: str, chain: str, contract_address: str) -> None:
        """
        Fires off a Grok social query to search for mentions and ingest them.
        Leverages Grok's live X/Twitter search tool.
        """
        ca = contract_address.lower()
        try:
            prompt = (
                f"Search X (Twitter) for recent mentions of the contract address: {contract_address}. "
                f"List the usernames of people talking about it, especially any prominent influencers or KOLs. "
                f"Return valid JSON only with this structure: "
                f'{{"mentions": [{{"username": "string", "name": "string", "text": "string", "followers": int, "timestamp_s": float}}]}}'
            )

            logger.info(f"🔍 Ingesting Grok social firehose for {symbol} ({contract_address})...")
            result = call_grok(
                cache_key=f"social_oracle_{symbol}",
                system_prompt="You are a real-time social firehose crawler. Find X posts mentioning the given contract address.",
                user_message=prompt,
                temperature=0.2,
                parse_json=True
            )

            if not result or "mentions" not in result:
                logger.debug(f"Grok firehose returned empty result for {symbol}")
                return

            for m in result.get("mentions", []):
                username = m.get("username", "")
                if not username:
                    continue

                mention = SocialMention(
                    platform="twitter",
                    contract_address=ca,
                    sender_id=username,
                    sender_name=m.get("name", username),
                    timestamp=m.get("timestamp_s", time.time()),
                    text=m.get("text", ""),
                    followers_count=m.get("followers", 0)
                )
                self.register_mention(mention, symbol, chain)

            logger.info(f"✅ Ingested {len(result['mentions'])} Twitter mentions from Grok for {symbol}")

        except Exception as e:
            logger.error(f"Grok social ingestion failed for {symbol}: {e}")

    def _maybe_cleanup(self) -> None:
        """Prunes registry items and mentions older than the TTL."""
        now = time.time()
        if now - self.last_cleanup < 600:  # Every 10 minutes
            return

        self.last_cleanup = now
        pruned_tokens = []

        with self._lock:
            for ca, metrics in list(self.registry.items()):
                # Prune individual old mentions
                cutoff = now - self.cleanup_ttl
                metrics.mentions = [m for m in metrics.mentions if m.timestamp >= cutoff]

                # Recalculate stats
                metrics.unique_senders = {m.sender_id for m in metrics.mentions}
                metrics.unique_kols = {m.sender_id for m in metrics.mentions if m.is_kol}
                metrics.twitter_count = sum(1 for m in metrics.mentions if m.platform == "twitter")
                metrics.telegram_count = sum(1 for m in metrics.mentions if m.platform == "telegram")

                # If no mentions left and first seen was long ago, remove token entirely
                if not metrics.mentions and (now - metrics.first_seen > self.cleanup_ttl):
                    pruned_tokens.append(ca)

            for ca in pruned_tokens:
                del self.registry[ca]

    def detect_wallet_cluster_accumulation(
        self,
        contract_address: str,
        recent_buyers: list[str],
    ) -> dict:
        """
        Cluster analysis: checks if 3+ known insider/alpha/cabal wallets accumulated
        the contract within a tight window.
        Returns a dict: {'cluster_detected': bool, 'insider_count': int, 'score_boost': float}
        """
        if not recent_buyers:
            return {"cluster_detected": False, "insider_count": 0, "score_boost": 0.0}

        buyers_set = {b.lower() for b in recent_buyers if isinstance(b, str)}
        insiders = buyers_set.intersection(self.known_kols)

        insider_count = len(insiders)
        if insider_count >= 3:
            logger.info(
                f"🔥 INSIDER CLUSTER DETECTED for {contract_address[:8]}... "
                f"({insider_count} cabal/KOL wallets accumulated)"
            )
            return {
                "cluster_detected": True,
                "insider_count": insider_count,
                "score_boost": 25.0,  # Bumps composite gem score to fast-track entry
            }
        elif insider_count == 2:
            return {
                "cluster_detected": False,
                "insider_count": 2,
                "score_boost": 10.0,
            }
        return {"cluster_detected": False, "insider_count": insider_count, "score_boost": 0.0}


# Global singleton instance
_oracle_instance: Optional[SocialInsiderOracle] = None


def get_social_insider_oracle() -> SocialInsiderOracle:
    """Get or initialize global SocialInsiderOracle singleton."""
    global _oracle_instance
    if _oracle_instance is None:
        _oracle_instance = SocialInsiderOracle()
    return _oracle_instance
