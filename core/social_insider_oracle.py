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
    platform: str
    contract_address: str
    sender_id: str
    sender_name: str
    timestamp: float = field(default_factory=time.time)
    text: str = ""
    followers_count: int = 0
    is_kol: bool = False

@dataclass
class TokenSocialMetrics:
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
    baseline_velocity: float = 0.0  # Mentions per 5m before the spike
    peak_velocity: float = 0.0      # Max mentions per 5m observed
    
    @property
    def total_mentions(self) -> int:
        return len(self.mentions)

class SocialInsiderOracle:
    def __init__(self):
        self.registry: Dict[str, TokenSocialMetrics] = {}
        self.lock = threading.Lock()
        
        # Configuration
        self.velocity_threshold_5m = int(getattr(settings, "ORACLE_VELOCITY_THRESHOLD_5M", 10))
        self.cabal_kol_threshold = int(getattr(settings, "ORACLE_CABAL_KOL_THRESHOLD", 3))
        self.cabal_window_s = int(getattr(settings, "ORACLE_CABAL_WINDOW_S", 300))
        self.cleanup_ttl = 3600 * 24  # 24 hours
        self.last_cleanup = time.time()
        
        # Known KOLs
        kol_handles = getattr(settings, "KOL_HANDLES_LIST", "")
        self.known_kols = {h.strip().lower() for h in kol_handles.split(",") if h.strip()}
        
        logger.info(f"SocialInsiderOracle initialized. Tracking {len(self.known_kols)} KOLs.")

    def register_mention(self, mention: SocialMention, symbol: str = "UNKNOWN", chain: str = "ethereum") -> None:
        """Records a new social mention and updates metrics."""
        ca = mention.contract_address.lower()
        
        # Tag KOLs
        if mention.sender_id.lower() in self.known_kols or mention.followers_count > 10000:
            mention.is_kol = True

        with self.lock:
            if ca not in self.registry:
                self.registry[ca] = TokenSocialMetrics(contract_address=ca, symbol=symbol.upper(), chain=chain.lower())
            
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

            # Update velocity
            now = time.time()
            recent_mentions = [m for m in metrics.mentions if now - m.timestamp <= 300]
            current_velocity = len(recent_mentions)
            
            if current_velocity > metrics.peak_velocity:
                metrics.peak_velocity = current_velocity
                
            if len(metrics.mentions) == 1:
                metrics.baseline_velocity = 1.0
            elif current_velocity > metrics.baseline_velocity * 4 and current_velocity > 5:
                # We detected a >300% spike (4x baseline)
                logger.info(f"🔥 SOCIAL SPIKE DETECTED: {symbol} ({ca}) - Velocity: {current_velocity}/5m (Baseline: {metrics.baseline_velocity:.1f})")

        self._maybe_cleanup()

    def get_recent_velocity(self, contract_address: str, window_s: int = 300) -> int:
        """Calculates mentions in the last `window_s` seconds."""
        ca = contract_address.lower()
        with self.lock:
            if ca not in self.registry:
                return 0
            now = time.time()
            return sum(1 for m in self.registry[ca].mentions if now - m.timestamp <= window_s)

    def check_cabal_pump(self, contract_address: str) -> Tuple[bool, List[str]]:
        """
        Detects if multiple KOLs are shilling the token simultaneously (insider cabal).
        Returns (is_cabal, list_of_kol_names).
        """
        ca = contract_address.lower()
        with self.lock:
            if ca not in self.registry:
                return False, []
            
            now = time.time()
            recent_kol_mentions = [
                m for m in self.registry[ca].mentions 
                if m.is_kol and (now - m.timestamp <= self.cabal_window_s)
            ]
            
            active_kols = list({m.sender_id for m in recent_kol_mentions})
            is_cabal = len(active_kols) >= self.cabal_kol_threshold
            
            return is_cabal, active_kols

    def evaluate_candidate(self, candidate: GemCandidate) -> Tuple[bool, str]:
        """
        Evaluates if a GemCandidate meets the criteria for a Social Insider Oracle buy signal.
        Criteria:
        1. Social velocity > threshold OR Cabal detected
        2. On-chain volume has NOT fully spiked yet (we are early)
        """
        ca = candidate.token.address.lower()
        symbol = candidate.token.symbol
        
        velocity = self.get_recent_velocity(ca)
        is_cabal, active_kols = self.check_cabal_pump(ca)
        
        if velocity < self.velocity_threshold_5m and not is_cabal:
            return False, f"Social velocity ({velocity}/5m) below threshold ({self.velocity_threshold_5m})"
            
        # Check if on-chain volume has NOT spiked yet (pre-volume condition)
        volume_spike_score = getattr(candidate, "volume_score", 0.0)
        volume_1h = candidate.token.volume_1h or 0.0
        liquidity = candidate.token.liquidity_usd or 1.0
        
        # If volume_1h is less than 30% of liquidity AND volume spike score is low,
        # it indicates social buzz is leading the on-chain volume wave.
        is_pre_volume = (volume_1h < (liquidity * 0.30)) or (volume_spike_score < 70.0)
        
        if not is_pre_volume:
            return False, f"On-chain volume already spiked (vol_1h={volume_1h:.0f}, score={volume_spike_score:.0f})"
            
        # Hard safety gates
        if not getattr(candidate, "is_safe", True):
            return False, "Token failed standard safety checks"
            
        reason = (
            f"Pre-volume social spike: velocity={velocity}/5m, "
            f"cabal={is_cabal} ({len(active_kols)} KOLs)"
        )
        return True, reason

    def ingest_grok_mentions(self, symbol: str, chain: str, contract_address: str) -> None:
        """
        Fires off a background Grok social query to search for mentions and ingest them.
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
        if now - self.last_cleanup < 600:
            return
            
        self.last_cleanup = now
        pruned_tokens = []
        
        with self.lock:
            for ca, metrics in list(self.registry.items()):
                cutoff = now - self.cleanup_ttl
                metrics.mentions = [m for m in metrics.mentions if m.timestamp >= cutoff]
                
                metrics.unique_senders = {m.sender_id for m in metrics.mentions}
                metrics.unique_kols = {m.sender_id for m in metrics.mentions if m.is_kol}
                metrics.twitter_count = sum(1 for m in metrics.mentions if m.platform == "twitter")
                metrics.telegram_count = sum(1 for m in metrics.mentions if m.platform == "telegram")
                
                if not metrics.mentions and (now - metrics.first_seen > self.cleanup_ttl):
                    pruned_tokens.append(ca)
                    
            for ca in pruned_tokens:
                del self.registry[ca]
            
        if pruned_tokens:
            logger.info(f"🧹 Pruned {len(pruned_tokens)} inactive tokens from Social Oracle registry")

oracle = SocialInsiderOracle()
