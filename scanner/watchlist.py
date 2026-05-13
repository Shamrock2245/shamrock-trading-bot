"""
scanner/watchlist.py — Persistent gem watchlist for near-miss token re-evaluation.

Tracks tokens that scored just below the buy threshold (35–49) and
re-evaluates them every scan cycle. Tokens that improve over time (e.g.,
volume spike, holder growth, sentiment shift) get promoted to full
candidates once they cross MIN_GEM_SCORE.

The watchlist catches gems that DexScreener shows once and then rotates out,
but which are still building momentum. This is a key edge for sniping
early-stage tokens before they moon.

Storage: output/watchlist.json — survives restarts.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from config import settings
from data.providers.dexscreener import get_token_pairs, extract_gem_signals

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Watchlist config (defaults, overridable from settings/env)
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_MIN_SCORE = float(os.getenv("WATCHLIST_MIN_SCORE", "35"))
WATCHLIST_MAX_AGE_HOURS = float(os.getenv("WATCHLIST_MAX_AGE_HOURS", "24"))
WATCHLIST_MAX_SIZE = int(os.getenv("WATCHLIST_MAX_SIZE", "50"))
WATCHLIST_FILE = os.getenv("WATCHLIST_FILE", "output/watchlist.json")

# Minimum score improvement to log a momentum shift
_MOMENTUM_SHIFT_THRESHOLD = 5.0

# EMA smoothing factor (higher = more weight on recent scores)
_EMA_ALPHA = 0.4
_EMA_MIN_CHECKS = 3  # Need at least N checks before using EMA


@dataclass
class WatchlistEntry:
    """A token being watched for potential promotion."""
    token_address: str
    chain: str
    symbol: str
    name: str
    initial_score: float
    current_score: float
    peak_score: float
    added_at: float          # Unix timestamp
    last_checked: float      # Unix timestamp
    check_count: int = 0
    score_history: list = field(default_factory=list)  # [(timestamp, score), ...]
    source: str = ""         # Where we first saw it (e.g., "dexscreener_profiles")
    promoted: bool = False   # True if promoted to candidate
    pair_address: str = ""   # DexScreener pair address for lookup

    @property
    def age_hours(self) -> float:
        return (time.time() - self.added_at) / 3600

    @property
    def is_expired(self) -> bool:
        return self.age_hours > WATCHLIST_MAX_AGE_HOURS

    @property
    def ema_score(self) -> float:
        """EMA-smoothed score to prevent threshold-bouncing.
        Uses raw score if fewer than _EMA_MIN_CHECKS data points."""
        scores = [s for _, s in self.score_history]
        if len(scores) < _EMA_MIN_CHECKS:
            return self.current_score
        ema = scores[0]
        for s in scores[1:]:
            ema = _EMA_ALPHA * s + (1 - _EMA_ALPHA) * ema
        return ema

    @property
    def momentum(self) -> str:
        """Simple momentum indicator based on score history."""
        if len(self.score_history) < 2:
            return "new"
        recent = self.score_history[-1][1]
        prev = self.score_history[-2][1]
        diff = recent - prev
        if diff >= _MOMENTUM_SHIFT_THRESHOLD:
            return "rising"
        elif diff <= -_MOMENTUM_SHIFT_THRESHOLD:
            return "falling"
        return "stable"


class GemWatchlist:
    """
    Manages the watchlist of near-miss tokens.

    Usage in gem_scanner.py:
        watchlist = GemWatchlist()

        # After scoring, add near-misses:
        watchlist.add_near_miss(candidate)

        # Re-evaluate watched tokens:
        promoted = watchlist.re_evaluate(score_fn)

        # promoted list contains tokens that crossed MIN_GEM_SCORE
    """

    def __init__(self, filepath: str = WATCHLIST_FILE):
        self.filepath = filepath
        self.entries: dict[str, WatchlistEntry] = {}  # key = "chain:address"
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        """Load watchlist from disk."""
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, "r") as f:
                content = f.read().strip()
            if not content:
                # Empty file — reset to clean state and continue
                logger.info("Watchlist file is empty — starting fresh")
                self._save()
                return
            data = json.loads(content)
            for key, raw in data.items():
                self.entries[key] = WatchlistEntry(**raw)
            logger.info(f"Watchlist loaded: {len(self.entries)} entries")
        except Exception as e:
            logger.warning(f"Watchlist load failed: {e} — starting with empty watchlist")
            self.entries.clear()
            self._save()  # Overwrite corrupt file with clean empty JSON

    def _save(self):
        """Persist watchlist to disk."""
        try:
            os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
            data = {k: asdict(v) for k, v in self.entries.items()}
            with open(self.filepath, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Watchlist save failed: {e}")

    # ── Core Operations ──────────────────────────────────────────────────────

    def add_near_miss(
        self,
        token_address: str,
        chain: str,
        symbol: str,
        name: str,
        score: float,
        source: str = "",
        pair_address: str = "",
    ) -> bool:
        """
        Add a near-miss token to the watchlist.
        Returns True if added, False if rejected (too low, already watching, full).
        """
        if score < WATCHLIST_MIN_SCORE or score >= settings.MIN_GEM_SCORE:
            return False  # Only watch near-misses

        key = f"{chain}:{token_address.lower()}"

        # Already watching? Update score
        if key in self.entries:
            entry = self.entries[key]
            entry.current_score = score
            entry.peak_score = max(entry.peak_score, score)
            entry.last_checked = time.time()
            entry.check_count += 1
            entry.score_history.append((time.time(), score))
            # Keep only last 20 checks
            entry.score_history = entry.score_history[-20:]
            self._save()
            return False

        # Watchlist full? Drop the lowest-scoring entry
        if len(self.entries) >= WATCHLIST_MAX_SIZE:
            worst_key = min(
                self.entries, key=lambda k: self.entries[k].current_score
            )
            if self.entries[worst_key].current_score < score:
                del self.entries[worst_key]
                logger.debug(f"Watchlist: dropped {worst_key} to make room")
            else:
                return False  # New token isn't better than worst watched

        now = time.time()
        self.entries[key] = WatchlistEntry(
            token_address=token_address,
            chain=chain,
            symbol=symbol,
            name=name,
            initial_score=score,
            current_score=score,
            peak_score=score,
            added_at=now,
            last_checked=now,
            check_count=1,
            score_history=[(now, score)],
            source=source,
            pair_address=pair_address,
        )
        logger.info(
            f"Watchlist: added {symbol} ({chain}) score={score:.1f} | "
            f"watching {len(self.entries)}/{WATCHLIST_MAX_SIZE}"
        )
        self._save()
        return True

    def re_evaluate(self, score_fn) -> list[dict]:
        """
        Re-evaluate all watched tokens by fetching fresh DexScreener data
        and re-scoring with the provided score_fn.

        Args:
            score_fn: Callable(token_address, chain, pair_data) -> float
                      Returns the new gem_score for the token.

        Returns:
            List of promoted token dicts (ready for gem_scanner candidate list):
            [{"token_address": ..., "chain": ..., "symbol": ..., "score": ..., "pair": ...}]
        """
        promoted: list[dict] = []
        expired_keys: list[str] = []
        now = time.time()

        for key, entry in list(self.entries.items()):
            # Remove expired entries
            if entry.is_expired:
                expired_keys.append(key)
                continue

            # Skip if checked recently (within 2 minutes)
            if (now - entry.last_checked) < 120:
                continue

            # Fetch fresh pair data from DexScreener
            try:
                pairs = get_token_pairs(entry.token_address)
                if not pairs:
                    # Token no longer on DexScreener — might have rugged
                    entry.current_score = max(0, entry.current_score - 10)
                    entry.last_checked = now
                    entry.score_history.append((now, entry.current_score))
                    if entry.current_score < WATCHLIST_MIN_SCORE * 0.5:
                        expired_keys.append(key)
                    continue

                pair = pairs[0]  # Most liquid pair
                signals = extract_gem_signals(pair)

                # Re-score using the scanner's scoring function
                new_score = score_fn(entry.token_address, entry.chain, signals)

                old_score = entry.current_score
                entry.current_score = new_score
                entry.peak_score = max(entry.peak_score, new_score)
                entry.last_checked = now
                entry.check_count += 1
                entry.score_history.append((now, new_score))
                entry.score_history = entry.score_history[-20:]

                # Score improved significantly?
                diff = new_score - old_score
                if diff >= _MOMENTUM_SHIFT_THRESHOLD:
                    logger.info(
                        f"Watchlist: {entry.symbol} momentum ↑ "
                        f"{old_score:.1f} → {new_score:.1f} (+{diff:.1f})"
                    )

                # PROMOTED! Use EMA-smoothed score for promotion decision
                # to prevent threshold-bouncing on noisy data.
                effective_score = entry.ema_score
                if effective_score >= settings.MIN_GEM_SCORE:
                    entry.promoted = True
                    promoted.append({
                        "token_address": entry.token_address,
                        "chain": entry.chain,
                        "symbol": entry.symbol,
                        "name": entry.name,
                        "score": new_score,
                        "pair": pair,
                        "signals": signals,
                        "watchlist_age_h": entry.age_hours,
                        "checks": entry.check_count,
                        "initial_score": entry.initial_score,
                    })
                    logger.info(
                        f"☘️ Watchlist PROMOTION: {entry.symbol} ({entry.chain}) "
                        f"score={new_score:.1f} (was {entry.initial_score:.1f}) "
                        f"after {entry.check_count} checks over {entry.age_hours:.1f}h"
                    )
                    expired_keys.append(key)  # Remove from watchlist after promotion

            except Exception as e:
                logger.debug(f"Watchlist re-eval failed for {entry.symbol}: {e}")
                entry.last_checked = now

        # Cleanup expired / promoted entries
        for key in expired_keys:
            if key in self.entries:
                del self.entries[key]

        if expired_keys:
            logger.debug(f"Watchlist: removed {len(expired_keys)} expired/promoted entries")

        self._save()

        if promoted:
            logger.info(f"Watchlist: {len(promoted)} tokens promoted to candidates!")

        return promoted

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self.entries)

    def get_summary(self) -> dict:
        """Get watchlist summary for dashboard/logging."""
        if not self.entries:
            return {"size": 0, "tokens": []}

        return {
            "size": len(self.entries),
            "avg_score": sum(e.current_score for e in self.entries.values()) / len(self.entries),
            "rising": sum(1 for e in self.entries.values() if e.momentum == "rising"),
            "falling": sum(1 for e in self.entries.values() if e.momentum == "falling"),
            "tokens": [
                {
                    "symbol": e.symbol,
                    "chain": e.chain,
                    "score": e.current_score,
                    "initial": e.initial_score,
                    "momentum": e.momentum,
                    "age_h": round(e.age_hours, 1),
                    "checks": e.check_count,
                }
                for e in sorted(
                    self.entries.values(),
                    key=lambda e: e.current_score,
                    reverse=True,
                )[:10]  # Top 10 by score
            ],
        }

    def cleanup(self):
        """Force cleanup of expired entries."""
        before = len(self.entries)
        self.entries = {
            k: v for k, v in self.entries.items() if not v.is_expired
        }
        removed = before - len(self.entries)
        if removed:
            logger.info(f"Watchlist cleanup: removed {removed} expired entries")
            self._save()
