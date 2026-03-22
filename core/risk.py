"""
core/risk.py — Risk management: position sizing, stop-loss, circuit breaker.

All risk parameters are loaded from environment variables (config/settings.py).
The circuit breaker halts ALL trading if portfolio drops >15% in 24 hours.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import settings
from config.wallets import WalletConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    """Result of a risk management check."""
    approved: bool
    reason: str
    position_size_eth: float = 0.0
    position_size_usdc: float = 0.0
    position_size_pct: float = 0.0
    use_usdc: bool = False


class RiskManager:
    """
    Enforces all risk management rules before trade execution.
    Tracks daily P&L and open positions per wallet.
    """

    def __init__(self):
        # Daily loss tracking: wallet_key → {date: str, loss_eth: float}
        self._daily_loss: dict[str, dict] = {}
        # Open positions: wallet_key → count
        self._open_positions: dict[str, int] = {}
        # Circuit breaker state
        self._circuit_breaker_tripped = False
        self._circuit_breaker_reason = ""

    def check_trade(
        self,
        wallet: WalletConfig,
        wallet_balance_eth: float,
        token_address: str,
        chain: str,
        usdc_balance: float = 0.0,
        eth_price_usd: float = 2000.0,
    ) -> RiskCheck:
        """
        Run all risk checks for a proposed trade.
        Supports both ETH and USDC as capital. Prefers USDC when available.
        """

        # ── Circuit breaker ───────────────────────────────────────────────────
        if self._circuit_breaker_tripped:
            return RiskCheck(
                approved=False,
                reason=f"Circuit breaker tripped: {self._circuit_breaker_reason}",
            )

        # ── Minimum balance check (need some ETH for gas) ─────────────────────
        if wallet_balance_eth < 0.001:
            return RiskCheck(
                approved=False,
                reason=(
                    f"ETH balance too low for gas: {wallet_balance_eth:.4f} ETH "
                    f"(need at least 0.001 ETH)"
                ),
            )

        # ── Daily loss limit ──────────────────────────────────────────────────
        daily_loss = self._get_daily_loss(wallet.alias)
        if daily_loss >= wallet.daily_loss_limit_eth:
            return RiskCheck(
                approved=False,
                reason=(
                    f"Daily loss limit reached: {daily_loss:.4f} ETH "
                    f"(limit: {wallet.daily_loss_limit_eth} ETH)"
                ),
            )

        # ── Concurrent positions ──────────────────────────────────────────────
        open_pos = self._open_positions.get(wallet.alias, 0)
        if open_pos >= wallet.max_concurrent_positions:
            return RiskCheck(
                approved=False,
                reason=(
                    f"Max concurrent positions reached: {open_pos} "
                    f"(limit: {wallet.max_concurrent_positions})"
                ),
            )

        # ── Position sizing ───────────────────────────────────────────────────
        position_pct = wallet.max_position_size_pct / 100.0

        # Prefer USDC capital when available (>$1 minimum)
        if usdc_balance > 1.0:
            position_usdc = usdc_balance * position_pct
            position_usdc = min(position_usdc, usdc_balance * 0.90)  # 90% max
            # Also calculate equivalent ETH for logging
            position_eth = position_usdc / eth_price_usd if eth_price_usd > 0 else 0
            logger.info(
                f"USDC capital: ${usdc_balance:.2f} → "
                f"position: ${position_usdc:.2f} ({position_pct*100:.1f}%)"
            )
            return RiskCheck(
                approved=True,
                reason="All risk checks passed (USDC capital)",
                position_size_eth=position_eth,
                position_size_usdc=position_usdc,
                position_size_pct=position_pct * 100,
                use_usdc=True,
            )

        # Fallback: use native ETH balance
        position_eth = wallet_balance_eth * position_pct
        max_spendable = wallet_balance_eth * 0.90
        position_eth = min(position_eth, max_spendable)

        if position_eth <= 0:
            return RiskCheck(
                approved=False,
                reason="Calculated position size is zero or negative",
            )

        return RiskCheck(
            approved=True,
            reason="All risk checks passed",
            position_size_eth=position_eth,
            position_size_pct=position_pct * 100,
        )

    def record_trade_open(self, wallet_alias: str) -> None:
        """Record that a new position was opened."""
        self._open_positions[wallet_alias] = (
            self._open_positions.get(wallet_alias, 0) + 1
        )

    def record_trade_close(self, wallet_alias: str, pnl_eth: float) -> None:
        """
        Record that a position was closed.
        pnl_eth: positive = profit, negative = loss
        """
        self._open_positions[wallet_alias] = max(
            0, self._open_positions.get(wallet_alias, 0) - 1
        )
        if pnl_eth < 0:
            self._add_daily_loss(wallet_alias, abs(pnl_eth))

    def check_circuit_breaker(self, portfolio_change_pct: float) -> bool:
        """
        Check if the circuit breaker should trip.
        portfolio_change_pct: negative = loss (e.g., -16.0 for 16% loss)
        Returns True if circuit breaker was tripped.
        """
        if portfolio_change_pct <= -settings.CIRCUIT_BREAKER_PERCENT:
            self._circuit_breaker_tripped = True
            self._circuit_breaker_reason = (
                f"Portfolio dropped {abs(portfolio_change_pct):.1f}% in 24h "
                f"(threshold: {settings.CIRCUIT_BREAKER_PERCENT}%)"
            )
            logger.critical(
                f"🚨 CIRCUIT BREAKER TRIPPED: {self._circuit_breaker_reason}"
            )
            return True
        return False

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker (operator action only)."""
        self._circuit_breaker_tripped = False
        self._circuit_breaker_reason = ""
        logger.warning("Circuit breaker manually reset by operator")

    def _get_daily_loss(self, wallet_alias: str) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        record = self._daily_loss.get(wallet_alias, {})
        if record.get("date") != today:
            return 0.0
        return record.get("loss_eth", 0.0)

    def _add_daily_loss(self, wallet_alias: str, loss_eth: float) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        record = self._daily_loss.get(wallet_alias, {"date": today, "loss_eth": 0.0})
        if record["date"] != today:
            record = {"date": today, "loss_eth": 0.0}
        record["loss_eth"] += loss_eth
        self._daily_loss[wallet_alias] = record

    @property
    def is_circuit_breaker_tripped(self) -> bool:
        return self._circuit_breaker_tripped


# Global risk manager instance
risk_manager = RiskManager()
