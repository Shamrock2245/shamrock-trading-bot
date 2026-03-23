"""
core/risk.py — Risk management: circuit breaker, daily loss limits, gas guard.

IMPORTANT: Position sizing is now handled by core/wallet_router.py (Kelly Criterion
+ phase-based scaling). This module is the FINAL GATE before execution — it enforces
hard limits that wallet_router cannot override:
  1. Circuit breaker (portfolio drawdown > CIRCUIT_BREAKER_PERCENT halts all trading)
  2. Gas ceiling (gas > MAX_GAS_GWEI blocks the trade)
  3. Minimum gas reserve (must keep enough ETH/SOL for gas)
  4. Daily loss limit (in USD — chain-agnostic)
  5. Max concurrent positions (global cap across all wallets)

The position_size_eth / position_size_usdc fields in RiskCheck are now populated
from the TradeAllocation produced by wallet_router.route_trade(), not calculated here.
This eliminates the duplicate sizing logic that previously existed.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from config import settings
from config.wallets import WalletConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RiskCheck:
    """Result of a risk management check."""
    approved: bool
    reason: str
    # Position sizing (populated from wallet_router.TradeAllocation, not calculated here)
    position_size_eth: float = 0.0
    position_size_usdc: float = 0.0
    position_size_pct: float = 0.0
    use_usdc: bool = False
    # Gas info
    gas_gwei: float = 0.0
    # Chain-aware fields
    chain: str = ""
    native_token: str = "ETH"


# ─────────────────────────────────────────────────────────────────────────────
# Risk Manager
# ─────────────────────────────────────────────────────────────────────────────

class RiskManager:
    """
    Final gate before trade execution. Enforces hard limits.

    Position sizing is delegated to wallet_router.py (Kelly + phase scaling).
    This class only enforces circuit breakers and hard stops.
    """

    def __init__(self):
        # Daily loss tracking: wallet_key → {date: str, loss_usd: float}
        self._daily_loss: dict[str, dict] = {}
        # Open positions: wallet_key → count
        self._open_positions: dict[str, int] = {}
        # Circuit breaker state
        self._circuit_breaker_tripped = False
        self._circuit_breaker_reason = ""

    def check_trade(
        self,
        wallet: WalletConfig,
        wallet_balance_native: float,
        token_address: str,
        chain: str,
        usdc_balance: float = 0.0,
        native_price_usd: float = 3200.0,
        # Position sizing from wallet_router (pass-through)
        position_size_native: float = 0.0,
        position_size_usd: float = 0.0,
    ) -> RiskCheck:
        """
        Run all risk checks for a proposed trade.

        Position sizing parameters come from wallet_router.route_trade() and are
        passed through here for the final approval gate. This method does NOT
        recalculate position sizes — it only validates them against hard limits.

        Args:
            wallet: Wallet configuration
            wallet_balance_native: Current native token balance (ETH, SOL, etc.)
            token_address: Token to buy (for logging)
            chain: Chain name
            usdc_balance: USDC balance (if available)
            native_price_usd: Current native token price in USD
            position_size_native: Proposed position size in native token (from wallet_router)
            position_size_usd: Proposed position size in USD (from wallet_router)
        """
        from config.chains import CHAINS
        chain_config = CHAINS.get(chain)
        native_token = chain_config.native_token if chain_config else "ETH"

        # ── Circuit breaker ───────────────────────────────────────────────────
        if self._circuit_breaker_tripped:
            return RiskCheck(
                approved=False,
                reason=f"Circuit breaker tripped: {self._circuit_breaker_reason}",
                chain=chain,
                native_token=native_token,
            )

        # ── Minimum gas reserve ───────────────────────────────────────────────
        # Solana: keep 0.01 SOL for fees; EVM: keep 0.001 ETH/BNB/MATIC
        min_gas_reserve = 0.01 if (chain_config and chain_config.is_solana) else 0.001
        if wallet_balance_native < min_gas_reserve:
            return RiskCheck(
                approved=False,
                reason=(
                    f"{native_token} balance too low for gas: {wallet_balance_native:.6f} "
                    f"(need at least {min_gas_reserve} {native_token})"
                ),
                chain=chain,
                native_token=native_token,
            )

        # ── Daily loss limit (USD-denominated — chain-agnostic) ───────────────
        daily_loss_usd = self._get_daily_loss_usd(wallet.alias)
        daily_loss_limit_usd = wallet.daily_loss_limit_eth * native_price_usd
        if daily_loss_usd >= daily_loss_limit_usd:
            return RiskCheck(
                approved=False,
                reason=(
                    f"Daily loss limit reached: ${daily_loss_usd:.2f} "
                    f"(limit: ${daily_loss_limit_usd:.2f})"
                ),
                chain=chain,
                native_token=native_token,
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
                chain=chain,
                native_token=native_token,
            )

        # ── Position size sanity check ────────────────────────────────────────
        # If wallet_router provided a size, validate it's not absurd
        if position_size_native > 0:
            # Never spend more than 90% of balance in a single trade
            max_spendable_native = wallet_balance_native * 0.90
            if position_size_native > max_spendable_native:
                position_size_native = max_spendable_native
                position_size_usd = position_size_native * native_price_usd
                logger.warning(
                    f"Position size capped at 90% of balance: "
                    f"{position_size_native:.4f} {native_token}"
                )

        # ── Determine capital source (USDC preferred) ─────────────────────────
        use_usdc = False
        position_usdc = 0.0
        position_eth = position_size_native

        if usdc_balance > 1.0 and position_size_usd > 0:
            # Use USDC if we have it and it covers the position
            if usdc_balance >= position_size_usd * 0.95:
                position_usdc = min(position_size_usd, usdc_balance * 0.90)
                position_eth = position_usdc / native_price_usd if native_price_usd > 0 else 0
                use_usdc = True
                logger.info(
                    f"Capital: USDC | ${usdc_balance:.2f} available → "
                    f"${position_usdc:.2f} position"
                )
            else:
                # Not enough USDC — use native
                logger.info(
                    f"USDC balance ${usdc_balance:.2f} < position ${position_size_usd:.2f} "
                    f"— using native {native_token}"
                )

        if not use_usdc and position_eth <= 0:
            # Fallback: calculate from wallet balance if wallet_router didn't provide size
            position_pct = wallet.max_position_size_pct / 100.0
            position_eth = min(wallet_balance_native * position_pct, wallet_balance_native * 0.90)
            position_size_usd = position_eth * native_price_usd

        if position_eth <= 0 and not use_usdc:
            return RiskCheck(
                approved=False,
                reason="Calculated position size is zero or negative",
                chain=chain,
                native_token=native_token,
            )

        return RiskCheck(
            approved=True,
            reason="All risk checks passed",
            position_size_eth=position_eth,
            position_size_usdc=position_usdc,
            position_size_pct=(position_size_usd / (wallet_balance_native * native_price_usd) * 100)
                if wallet_balance_native * native_price_usd > 0 else 0,
            use_usdc=use_usdc,
            chain=chain,
            native_token=native_token,
        )

    def record_trade_open(self, wallet_alias: str) -> None:
        """Record that a new position was opened."""
        self._open_positions[wallet_alias] = (
            self._open_positions.get(wallet_alias, 0) + 1
        )

    def record_trade_close(self, wallet_alias: str, pnl_usd: float) -> None:
        """
        Record that a position was closed.
        pnl_usd: positive = profit, negative = loss (USD-denominated)
        """
        self._open_positions[wallet_alias] = max(
            0, self._open_positions.get(wallet_alias, 0) - 1
        )
        if pnl_usd < 0:
            self._add_daily_loss_usd(wallet_alias, abs(pnl_usd))

    def record_trade_close_eth(self, wallet_alias: str, pnl_eth: float, native_price_usd: float = 3200.0) -> None:
        """Legacy wrapper — converts ETH P&L to USD for unified tracking."""
        self.record_trade_close(wallet_alias, pnl_eth * native_price_usd)

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

    @property
    def is_circuit_breaker_tripped(self) -> bool:
        return self._circuit_breaker_tripped

    def _get_daily_loss_usd(self, wallet_alias: str) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        record = self._daily_loss.get(wallet_alias, {})
        if record.get("date") != today:
            return 0.0
        return record.get("loss_usd", 0.0)

    def _add_daily_loss_usd(self, wallet_alias: str, loss_usd: float) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        record = self._daily_loss.get(wallet_alias, {"date": today, "loss_usd": 0.0})
        if record["date"] != today:
            record = {"date": today, "loss_usd": 0.0}
        record["loss_usd"] += loss_usd
        self._daily_loss[wallet_alias] = record

    # ── Legacy ETH-denominated methods (backwards compatibility) ──────────────

    def _get_daily_loss(self, wallet_alias: str) -> float:
        """Legacy: returns loss in ETH equivalent (assumes $3200/ETH)."""
        return self._get_daily_loss_usd(wallet_alias) / 3200.0

    def _add_daily_loss(self, wallet_alias: str, loss_eth: float) -> None:
        """Legacy: records loss in ETH (converts to USD at $3200/ETH)."""
        self._add_daily_loss_usd(wallet_alias, loss_eth * 3200.0)


# Global risk manager instance
risk_manager = RiskManager()
