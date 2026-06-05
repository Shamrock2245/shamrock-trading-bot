"""
core/social_insider_oracle.py — ☘️ Shamrock Trading Bot
Social Insider Oracle (ECC Skill: sentiment-insider-oracle)

Monitors real-time social streams (Twitter/X and Telegram) for rapid,
anomalous bursts of mentions of new Contract Addresses (CAs). Detects coordinated
pumps orchestrated by Key Opinion Leaders (KOLs) or insider cabals within
a tight window, and triggers pre-volume sniper entries to front-run retail momentum.
"""

import logging
import time
import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import settings
from data.models import Token, GemCandidate
from data.providers.grok_client import call_grok

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SocialMention:
    """Represents a single social mention of a contract address."""
    platform: str              # "twitter" or "telegram"
    contract_address: str
    sender_id: str             # Username or wallet address
    sender_name: str           # Display name or alias
    is_kol: bool = False       # True if sender is in the known KOL/Insider database
    timestamp: float = field(default_factory=time.time)
    text: str = ""
    followers_count: int = 0   # Reach/impact factor

@dataclass
class OracleMetrics:
    """Maintains running social velocity and cabal metrics for a contract address."""
    contract_address: str
    symbol: str
    chain: str
    first_seen: float
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

# ─────────────────────────────────────────────────────────────────────────────
# Social Insider Oracle Engine
# ─────────────────────────────────────────────────────────────────────────────

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
            "realkaleo", "cryptobirb", "incomesharks", "crypto_bitlord", "runner"
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
        
        # Clean up database interval config (TTL: 1 hour)
        self.cleanup_ttl = 3600
        self.last_cleanup = time.time()

        # Thresholds
        self.velocity_threshold_5m = int(getattr(settings, "ORACLE_VELOCITY_THRESHOLD_5M", "10"))
        self.cabal_kol_threshold = int(getattr(settings, "ORACLE_CABAL_KOL_THRESHOLD", "3"))
        self.cabal_window_s = int(getattr(settings, "ORACLE_CABAL_WINDOW_S", "300")) # 5 minutes

    def register_mention(self, mention: SocialMention, symbol: str = "UNKNOWN", chain: str = "ethereum") -> OracleMetrics:
        """
        Registers a raw social mention of a Contract Address.
        Updates internal metrics and checks for cabal triggers.
        """
        self._maybe_cleanup()
        
        ca = mention.contract_address.lower()
        mention.sender_id = mention.sender_id.lower().replace("@", "")
        
        # Check if sender is in known KOL list
        if mention.sender_id in self.known_kols:
            mention.is_kol = True
            
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
        
        # Update symbol if it was unknown
        if metrics.symbol == "UNKNOWN" and symbol != "UNKNOWN":
            metrics.symbol = symbol.upper()
        if chain != "ethereum" and metrics.chain == "ethereum":
            metrics.chain = chain.lower()

        return metrics

    def check_cabal_pump(self, contract_address: str) -> Tuple[bool, List[str]]:
        """
        Insider Cabal Detection (Requirement #2):
        If a token is being simultaneously shilled by multiple known 'KOL' wallets
        or Twitter accounts within a 5-minute window, flag it as an orchestrated pump.
        """
        ca = contract_address.lower()
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
        Pre-Volume Sniping Evaluation (Requirement #3):
        If social velocity crosses our threshold before on-chain volume has spiked,
        bypass the standard waiting period and execute an immediate low-size sniper entry.
        
        Returns: (should_snipe, reason)
        """
        ca = candidate.token.address.lower()
        if ca not in self.registry:
            return False, "No social oracle tracking data"
            
        metrics = self.registry[ca]
        velocity = metrics.mention_velocity_5m
        
        # Threshold checks
        if velocity < self.velocity_threshold_5m:
            return False, f"Social velocity ({velocity}) below threshold ({self.velocity_threshold_5m})"
            
        # Check if on-chain volume has NOT spiked yet (pre-volume condition)
        # We define "no volume spike yet" as 1h volume being relatively low compared to liquidity,
        # or volume spike score being low/moderate (< 70).
        volume_spike_score = getattr(candidate, "volume_score", 0.0)
        volume_1h = candidate.token.volume_1h or 0.0
        liquidity = candidate.token.liquidity_usd or 1.0
        
        # If volume_1h is less than 30% of liquidity AND volume spike score is low,
        # it indicates social buzz is leading the on-chain volume wave.
        is_pre_volume = (volume_1h < (liquidity * 0.30)) or (volume_spike_score < 70.0)
        
        if not is_pre_volume:
            return False, f"On-chain volume already spiked (vol_1h={volume_1h:.0f}, score={volume_spike_score:.0f})"
            
        # Hard safety gates still apply (GoPlus, honeypot checks)
        if not getattr(candidate, "is_safe", True):
            return False, "Token failed standard safety checks (honeypot/tax/rug)"
            
        # Check for cabal backing as an extra validation
        is_cabal, active_kols = self.check_cabal_pump(ca)
        
        reason = (
            f"Pre-volume social spike: velocity={velocity}/5m, "
            f"cabal={is_cabal} ({len(active_kols)} KOLs)"
        )
        return True, reason

    def ingest_grok_mentions(self, symbol: str, chain: str, contract_address: str) -> None:
        """
        Fires off a background Grok social query to search for mentions and ingest them.
        Leverages Grok's live X/Twitter search tool.
        """
        ca = contract_address.lower()
        try:
            # Query Grok for recent mentions of this CA
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
        if now - self.last_cleanup < 600: # Every 10 minutes
            return
            
        self.last_cleanup = now
        pruned_tokens = []
        
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
            
        if pruned_tokens:
            logger.info(f"🧹 Pruned {len(pruned_tokens)} inactive tokens from Social Oracle registry")

# Global shared instance
oracle = SocialInsiderOracle()
