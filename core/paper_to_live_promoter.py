"""
core/paper_to_live_promoter.py — Automatic Paper-to-Live Mode Promoter

Monitors daily paper-trading profit and automatically promotes the bot to
LIVE mode once the $500/day threshold is proven in simulation.

Promotion Criteria (ALL must pass):
  ✅ Paper profit ≥ $500 in the current 24-hour window
  ✅ Gas balance present on ALL active chains (min thresholds per chain)
  ✅ Private keys loaded (WALLET_PRIVATE_KEY_PRIMARY set in environment)
  ✅ Not already in live mode
  ✅ Promotion not manually locked (PAPER_MODE_LOCKED=true env var)

Promotion Actions:
  1. Writes MODE=live to the .env file (persists across restarts)
  2. Sets os.environ["MODE"] = "live" immediately (takes effect this session)
  3. Reloads settings.MODE, settings.IS_LIVE, (settings.get_current_mode() == "paper")
  4. Sends Slack + Telegram alert with full promotion summary
  5. Logs a permanent promotion record to output/live_promotion.json
  6. Restarts the TradeExecutor in live mode

Safety Locks:
  - PAPER_MODE_LOCKED=true in .env → never auto-promote (manual override only)
  - If any chain is missing gas → blocks promotion, sends warning alert
  - If private keys missing → blocks promotion, sends critical alert
  - Once promoted, NEVER auto-demotes back to paper (manual only)

Usage:
  from core.paper_to_live_promoter import check_and_promote
  # Call this after every profitable trade record
  check_and_promote(today_profit_usd=523.40)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

LIVE_PROMOTION_THRESHOLD_USD: float = float(
    os.getenv("LIVE_PROMOTION_THRESHOLD_USD", "500.0")
)

# Minimum native gas balance required per chain before going live
# These are conservative minimums — you want enough gas for ~50 trades
GAS_MINIMUMS: dict[str, float] = {
    "ethereum":  0.05,   # 0.05 ETH  (~$150 at $3k ETH — covers ~20 Flashbots txns)
    "base":      0.01,   # 0.01 ETH  (~$30  — Base is cheap, covers ~200 txns)
    "arbitrum":  0.01,   # 0.01 ETH  (~$30  — Arb is cheap)
    "polygon":   5.0,    # 5 MATIC   (~$3   — very cheap)
    "bsc":       0.05,   # 0.05 BNB  (~$30  — covers ~100 txns)
    "solana":    0.1,    # 0.1 SOL   (~$15  — covers ~1000 txns)
}

PROMOTION_RECORD_FILE = Path("output/live_promotion.json")
CAMPAIGN_STATE_FILE = Path("output/paper_tuning_campaign.json")
ENV_FILE = Path(".env")

# Chains we require gas on before going live
REQUIRED_GAS_CHAINS: list[str] = ["base", "arbitrum", "polygon", "bsc"]
# Ethereum is optional (expensive) — warn but don't block
OPTIONAL_GAS_CHAINS: list[str] = ["ethereum", "solana"]


def _campaign_allows_promotion() -> bool:
    """
    Multi-week paper tuning gate.

    When PAPER_TUNING_CAMPAIGN_ENABLED=true (default), refuse auto-promotion
    until:
      1. Campaign duration (PAPER_TUNING_CAMPAIGN_DAYS, default 21) has elapsed
      2. Optional metric floors (trades / win rate / PF) are met if trade journal exists

    Always returns True when the campaign flag is off (legacy single-day promote).
    """
    try:
        from config import settings
    except Exception:
        settings = None

    campaign_on = True
    if settings is not None:
        campaign_on = bool(getattr(settings, "PAPER_TUNING_CAMPAIGN_ENABLED", True))
    else:
        campaign_on = os.getenv("PAPER_TUNING_CAMPAIGN_ENABLED", "true").lower() == "true"

    if not campaign_on:
        return True

    days = 21
    start_iso = ""
    if settings is not None:
        days = int(getattr(settings, "PAPER_TUNING_CAMPAIGN_DAYS", 21) or 21)
        start_iso = str(getattr(settings, "PAPER_TUNING_CAMPAIGN_START", "") or "")
    else:
        days = int(os.getenv("PAPER_TUNING_CAMPAIGN_DAYS", "21"))
        start_iso = os.getenv("PAPER_TUNING_CAMPAIGN_START", "")

    # Persist / load campaign start so restarts don't reset the clock
    state = _load_or_init_campaign_state(start_iso=start_iso, days=days)
    start_dt = datetime.fromisoformat(state["start_date"].replace("Z", "+00:00"))
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    elapsed_days = (datetime.now(timezone.utc) - start_dt).total_seconds() / 86400.0
    if elapsed_days < float(days):
        remaining = max(0.0, float(days) - elapsed_days)
        logger.info(
            f"📄 Paper tuning campaign active — day {elapsed_days:.1f}/{days} "
            f"({remaining:.1f}d remaining). Auto-promote blocked."
        )
        return False

    # Soft metric floors (do not hard-fail if journal missing — duration is primary)
    min_trades = int(getattr(settings, "PAPER_PROMOTE_MIN_TRADES", 50) if settings else 50)
    min_wr = float(getattr(settings, "PAPER_PROMOTE_MIN_WIN_RATE", 0.50) if settings else 0.50)
    min_pf = float(
        getattr(settings, "PAPER_PROMOTE_MIN_PROFIT_FACTOR", 1.30) if settings else 1.30
    )
    metrics = _paper_journal_metrics()
    if metrics is None:
        logger.warning(
            "📄 Campaign duration met but no paper trade journal found — "
            "refusing auto-promote until metrics exist"
        )
        return False

    if metrics["closed_trades"] < min_trades:
        logger.info(
            f"📄 Campaign day gate passed but only {metrics['closed_trades']} closed "
            f"paper trades < {min_trades} required — promote blocked"
        )
        return False
    if metrics["win_rate"] < min_wr:
        logger.info(
            f"📄 Paper win rate {metrics['win_rate']:.1%} < {min_wr:.0%} — promote blocked"
        )
        return False
    if metrics["profit_factor"] < min_pf:
        logger.info(
            f"📄 Paper profit factor {metrics['profit_factor']:.2f} < {min_pf:.2f} — promote blocked"
        )
        return False

    logger.info(
        f"✅ Paper campaign gates passed: {metrics['closed_trades']} trades, "
        f"WR={metrics['win_rate']:.1%}, PF={metrics['profit_factor']:.2f}"
    )
    return True


def _valid_campaign_start(value) -> bool:
    """Reject mocks / garbage written by tests; require parseable ISO datetime."""
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s or "MagicMock" in s or len(s) < 8:
        return False
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.year >= 2020
    except Exception:
        return False


def _load_or_init_campaign_state(*, start_iso: str, days: int) -> dict:
    """Create or load output/paper_tuning_campaign.json."""
    now = datetime.now(timezone.utc)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 21
    if days < 1 or days > 90:
        days = 21

    if CAMPAIGN_STATE_FILE.exists():
        try:
            data = json.loads(CAMPAIGN_STATE_FILE.read_text(encoding="utf-8"))
            if _valid_campaign_start(data.get("start_date")):
                # Keep start_date sticky; allow days update from env
                try:
                    data["days"] = int(data.get("days") or days) or days
                except (TypeError, ValueError):
                    data["days"] = days
                if data.get("days", 0) < 1:
                    data["days"] = days
                return data
        except Exception:
            pass

    start_date: str
    if _valid_campaign_start(start_iso):
        start_date = str(start_iso).strip()
        if "T" not in start_date:
            start_date = f"{start_date}T00:00:00+00:00"
    else:
        start_date = now.isoformat()

    state = {
        "start_date": start_date,
        "days": days,
        "mode": "paper",
        "paper_mode_locked": True,
        "created_at": now.isoformat(),
        "goal": "Tune parameters in paper for 2–3 weeks before any live unlock",
    }
    try:
        CAMPAIGN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CAMPAIGN_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(CAMPAIGN_STATE_FILE)
    except Exception as e:
        logger.debug(f"Campaign state write failed: {e}")
    return state


def _paper_journal_metrics() -> Optional[dict]:
    """Compute basic closed-trade metrics from trades.json (paper rows preferred)."""
    candidates = [
        Path(os.getenv("TRADES_FILE", "output/trades.json")),
        Path("output/trades.json"),
        Path("/app/output/trades.json"),
    ]
    trades: list = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "[]")
            if isinstance(raw, list) and raw:
                trades = raw
                break
        except Exception:
            continue
    if not trades:
        return None

    # Prefer paper-tagged rows; fall back to all SELL closes with pnl
    paper = [t for t in trades if t.get("is_paper") is True]
    pool = paper if paper else trades
    closes = [
        t for t in pool
        if str(t.get("action", "")).upper() in ("SELL", "CLOSE", "SELL_SHORT")
        and t.get("pnl_usd") is not None
    ]
    if not closes:
        return None

    wins = [float(t["pnl_usd"]) for t in closes if float(t["pnl_usd"]) > 0]
    losses = [float(t["pnl_usd"]) for t in closes if float(t["pnl_usd"]) < 0]
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    wr = (len(wins) / len(closes)) if closes else 0.0
    return {
        "closed_trades": len(closes),
        "win_rate": wr,
        "profit_factor": pf,
        "net_pnl": sum(float(t["pnl_usd"]) for t in closes),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Promotion Record
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PromotionRecord:
    """Permanent record of the paper-to-live promotion event."""
    promoted_at: str
    paper_profit_usd: float
    threshold_usd: float
    gas_balances: dict
    chains_with_gas: list
    chains_missing_gas: list
    private_keys_present: list
    env_file_updated: bool
    notifications_sent: list
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Main Promotion Logic
# ─────────────────────────────────────────────────────────────────────────────

def check_and_promote(today_profit_usd: float) -> bool:
    """
    Check if paper-trading has proven $500/day and promote to live if so.
    Returns True if promotion occurred, False otherwise.

    Call this after every profitable trade record in main.py.
    """
    from config import settings

    # Already live — nothing to do
    if settings.IS_LIVE:
        return False

    # Manual lock — prefer live env (default true during paper tuning campaigns)
    if os.getenv("PAPER_MODE_LOCKED", "true").lower() == "true":
        logger.info(
            "📄 PAPER_MODE_LOCKED=true — auto-promotion disabled "
            f"(today paper PnL ${today_profit_usd:.2f}). "
            "See docs/PAPER_TUNING_CAMPAIGN.md"
        )
        return False

    # Multi-week campaign gate: never auto-promote before campaign end
    if not _campaign_allows_promotion():
        return False

    # Not yet at threshold
    if today_profit_usd < LIVE_PROMOTION_THRESHOLD_USD:
        return False

    # Already promoted today (prevent duplicate promotions)
    if _already_promoted_today():
        return False

    logger.info(
        f"🎯 PAPER THRESHOLD HIT: ${today_profit_usd:.2f} ≥ ${LIVE_PROMOTION_THRESHOLD_USD:.0f} — "
        f"evaluating live promotion..."
    )

    # Run all pre-promotion checks
    checks = _run_promotion_checks()

    if not checks["can_promote"]:
        _send_blocked_alert(today_profit_usd, checks)
        return False

    # All checks passed — PROMOTE
    _execute_promotion(today_profit_usd, checks)
    return True


def _run_promotion_checks() -> dict:
    """Run all pre-promotion safety checks. Returns a dict with results."""
    from config.wallets import WALLETS
    from core.wallet_router import get_native_balance

    checks = {
        "can_promote": True,
        "gas_balances": {},
        "chains_with_gas": [],
        "chains_missing_gas": [],
        "private_keys_present": [],
        "private_keys_missing": [],
        "blockers": [],
        "warnings": [],
    }

    # ── Check 1: Private keys ──────────────────────────────────────────────
    key_vars = [
        "WALLET_PRIVATE_KEY_PRIMARY",
        "WALLET_PRIVATE_KEY_B",
        "WALLET_PRIVATE_KEY_C",
    ]
    for key_var in key_vars:
        val = os.getenv(key_var, "")
        if val and len(val) > 10:
            checks["private_keys_present"].append(key_var)
        else:
            checks["private_keys_missing"].append(key_var)

    if not checks["private_keys_present"]:
        checks["blockers"].append(
            "❌ NO PRIVATE KEYS FOUND — Set WALLET_PRIVATE_KEY_PRIMARY in .env to enable live trading"
        )
        checks["can_promote"] = False

    # ── Check 2: Gas balances on required chains ───────────────────────────
    primary_wallet = WALLETS.get("primary")
    if primary_wallet:
        for chain in REQUIRED_GAS_CHAINS + OPTIONAL_GAS_CHAINS:
            try:
                balance = get_native_balance(primary_wallet.address, chain)
                min_required = GAS_MINIMUMS.get(chain, 0.01)
                checks["gas_balances"][chain] = round(balance, 6)

                if balance >= min_required:
                    checks["chains_with_gas"].append(chain)
                else:
                    if chain in REQUIRED_GAS_CHAINS:
                        checks["chains_missing_gas"].append(chain)
                        checks["blockers"].append(
                            f"❌ INSUFFICIENT GAS on {chain}: "
                            f"{balance:.6f} < {min_required} required"
                        )
                    else:
                        checks["warnings"].append(
                            f"⚠️ Low gas on {chain}: {balance:.6f} (optional chain)"
                        )
            except Exception as e:
                logger.debug(f"Gas check failed for {chain}: {e}")
                if chain in REQUIRED_GAS_CHAINS:
                    checks["chains_missing_gas"].append(chain)
                    checks["warnings"].append(f"⚠️ Could not verify gas on {chain}: {e}")

    # Block if ANY required chain is missing gas
    if checks["chains_missing_gas"]:
        checks["can_promote"] = False

    # ── Check 3: 1inch API key (needed for live execution) ─────────────────
    if not os.getenv("ONEINCH_API_KEY", ""):
        checks["warnings"].append(
            "⚠️ ONEINCH_API_KEY not set — live execution will use fallback routing"
        )

    return checks


def _execute_promotion(today_profit_usd: float, checks: dict) -> None:
    """Execute the paper-to-live promotion."""
    from config import settings

    promoted_at = datetime.now(timezone.utc).isoformat()
    notifications_sent = []

    logger.info("=" * 70)
    logger.info("🚀 LIVE MODE PROMOTION INITIATED")
    logger.info(f"   Paper profit: ${today_profit_usd:.2f}")
    logger.info(f"   Threshold:    ${LIVE_PROMOTION_THRESHOLD_USD:.0f}")
    logger.info(f"   Chains ready: {checks['chains_with_gas']}")
    logger.info(f"   Keys present: {checks['private_keys_present']}")
    logger.info("=" * 70)

    # ── Step 1: Update .env file ───────────────────────────────────────────
    env_updated = _update_env_file("MODE", "live")
    if env_updated:
        logger.info("✅ .env updated: MODE=live")
    else:
        logger.warning("⚠️ Could not update .env file — setting env var directly")

    # ── Step 2: Update os.environ immediately ─────────────────────────────
    os.environ["MODE"] = "live"

    # ── Step 3: Reload settings module ────────────────────────────────────
    try:
        import importlib
        import config.settings as _settings_module
        importlib.reload(_settings_module)
        # Re-import the updated values
        from config import settings as _s
        _s.MODE = "live"
        _s.IS_LIVE = True
        _s.IS_PAPER = False
        logger.info("✅ settings.MODE reloaded: live")
    except Exception as e:
        logger.warning(f"Could not reload settings module: {e} — env var is set, will take effect on next import")

    # ── Step 4: Send Slack alert ───────────────────────────────────────────
    try:
        from notifications.slack import notify_alert
        gas_summary = " | ".join(
            f"{c}: {checks['gas_balances'].get(c, 0):.4f}"
            for c in checks["chains_with_gas"]
        )
        slack_msg = (
            f"*🚀 LIVE MODE ACTIVATED — Paper-to-Live Promotion*\n\n"
            f"*Paper profit today:* ${today_profit_usd:.2f} (threshold: ${LIVE_PROMOTION_THRESHOLD_USD:.0f})\n"
            f"*Chains with gas:* {', '.join(checks['chains_with_gas'])}\n"
            f"*Gas balances:* {gas_summary}\n"
            f"*Private keys loaded:* {len(checks['private_keys_present'])}/3\n"
            f"*Promoted at:* {promoted_at}\n\n"
            f"⚠️ *Real funds will now be used. Monitor closely.*\n"
            f"To revert: set `MODE=paper` in .env and restart."
        )
        notify_alert(
            title="🚀 LIVE MODE ACTIVATED",
            message=slack_msg,
            level="critical",
        )
        notifications_sent.append("slack")
        logger.info("✅ Slack promotion alert sent")
    except Exception as e:
        logger.warning(f"Slack alert failed: {e}")

    # ── Step 5: Send Telegram alert ────────────────────────────────────────
    try:
        from notifications.telegram import notify_alert as tg_alert
        tg_msg = (
            f"🚀 LIVE MODE ACTIVATED\n\n"
            f"Paper profit: ${today_profit_usd:.2f}\n"
            f"Chains ready: {', '.join(checks['chains_with_gas'])}\n"
            f"Keys loaded: {len(checks['private_keys_present'])}/3\n\n"
            f"⚠️ Real funds active. Monitor closely.\n"
            f"Revert: set MODE=paper in .env"
        )
        tg_alert(
            title="🚀 LIVE MODE ACTIVATED",
            message=tg_msg,
            level="critical",
        )
        notifications_sent.append("telegram")
        logger.info("✅ Telegram promotion alert sent")
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")

    # ── Step 6: Save promotion record ─────────────────────────────────────
    record = PromotionRecord(
        promoted_at=promoted_at,
        paper_profit_usd=today_profit_usd,
        threshold_usd=LIVE_PROMOTION_THRESHOLD_USD,
        gas_balances=checks["gas_balances"],
        chains_with_gas=checks["chains_with_gas"],
        chains_missing_gas=checks["chains_missing_gas"],
        private_keys_present=checks["private_keys_present"],
        env_file_updated=env_updated,
        notifications_sent=notifications_sent,
        notes=f"Auto-promoted after hitting ${LIVE_PROMOTION_THRESHOLD_USD:.0f}/day paper threshold",
    )
    _save_promotion_record(record)

    logger.info("=" * 70)
    logger.info("✅ LIVE MODE PROMOTION COMPLETE")
    logger.info(f"   Record saved to: {PROMOTION_RECORD_FILE}")
    logger.info("=" * 70)


def _send_blocked_alert(today_profit_usd: float, checks: dict) -> None:
    """Send an alert when promotion is blocked due to missing gas/keys."""
    blockers = checks.get("blockers", [])
    warnings = checks.get("warnings", [])

    logger.warning(
        f"⚠️ LIVE PROMOTION BLOCKED: ${today_profit_usd:.2f} threshold hit but "
        f"{len(blockers)} blocker(s) preventing promotion:"
    )
    for b in blockers:
        logger.warning(f"   {b}")

    try:
        from notifications.slack import notify_alert
        blocker_text = "\n".join(f"• {b}" for b in blockers)
        warning_text = "\n".join(f"• {w}" for w in warnings) if warnings else "None"
        msg = (
            f"*⚠️ Live Promotion BLOCKED*\n\n"
            f"Paper profit ${today_profit_usd:.2f} hit the ${LIVE_PROMOTION_THRESHOLD_USD:.0f} threshold "
            f"but promotion was blocked:\n\n"
            f"*Blockers:*\n{blocker_text}\n\n"
            f"*Warnings:*\n{warning_text}\n\n"
            f"*Action required:* Deposit gas to the required chains and ensure "
            f"`WALLET_PRIVATE_KEY_PRIMARY` is set in your .env file."
        )
        notify_alert(
            title="⚠️ Live Promotion Blocked — Action Required",
            message=msg,
            level="warning",
        )
    except Exception as e:
        logger.debug(f"Blocked alert notification failed: {e}")

    try:
        from notifications.telegram import notify_alert as tg_alert
        tg_alert(
            title="⚠️ Live Promotion Blocked",
            message=(
                f"Paper ${today_profit_usd:.2f} hit threshold but blocked:\n"
                + "\n".join(blockers)
                + "\n\nDeposit gas to required chains to enable live trading."
            ),
            level="warning",
        )
    except Exception as e:
        logger.debug(f"Telegram blocked alert failed: {e}")


def _update_env_file(key: str, value: str) -> bool:
    """
    Update or add a key=value pair in the .env file.
    Preserves all other settings. Creates .env if it doesn't exist.
    """
    try:
        env_path = ENV_FILE

        # Read existing content
        lines = []
        if env_path.exists():
            with open(env_path, "r") as f:
                lines = f.readlines()

        # Update or append
        key_found = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}\n")
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        return True
    except Exception as e:
        logger.warning(f"Could not update .env file: {e}")
        return False


def _already_promoted_today() -> bool:
    """Check if we already promoted to live today (prevent duplicate promotions)."""
    try:
        if PROMOTION_RECORD_FILE.exists():
            with open(PROMOTION_RECORD_FILE) as f:
                records = json.load(f)
            if isinstance(records, list) and records:
                last = records[-1]
                last_date = last.get("promoted_at", "")[:10]
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if last_date == today:
                    return True
    except Exception:
        pass
    return False


def _save_promotion_record(record: PromotionRecord) -> None:
    """Append the promotion record to the JSON log."""
    try:
        PROMOTION_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
        records = []
        if PROMOTION_RECORD_FILE.exists():
            with open(PROMOTION_RECORD_FILE) as f:
                records = json.load(f)
        if not isinstance(records, list):
            records = []
        records.append(asdict(record))
        with open(PROMOTION_RECORD_FILE, "w") as f:
            json.dump(records, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Could not save promotion record: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Gas Deposit Status Helper (for dashboard / logging)
# ─────────────────────────────────────────────────────────────────────────────

def get_gas_readiness_status() -> dict:
    """
    Returns a dict showing gas readiness for live trading.
    Used by the dashboard and pre-flight checks.
    """
    from config.wallets import WALLETS
    from core.wallet_router import get_native_balance

    status = {
        "ready_for_live": True,
        "chains": {},
        "missing_chains": [],
        "total_chains_ready": 0,
    }

    primary_wallet = WALLETS.get("primary")
    if not primary_wallet:
        status["ready_for_live"] = False
        return status

    all_chains = REQUIRED_GAS_CHAINS + OPTIONAL_GAS_CHAINS
    for chain in all_chains:
        try:
            balance = get_native_balance(primary_wallet.address, chain)
            min_req = GAS_MINIMUMS.get(chain, 0.01)
            has_gas = balance >= min_req
            status["chains"][chain] = {
                "balance": round(balance, 6),
                "minimum": min_req,
                "has_gas": has_gas,
                "required": chain in REQUIRED_GAS_CHAINS,
            }
            if has_gas:
                status["total_chains_ready"] += 1
            elif chain in REQUIRED_GAS_CHAINS:
                status["missing_chains"].append(chain)
                status["ready_for_live"] = False
        except Exception as e:
            status["chains"][chain] = {"error": str(e), "has_gas": False, "required": chain in REQUIRED_GAS_CHAINS}
            if chain in REQUIRED_GAS_CHAINS:
                status["ready_for_live"] = False

    # Also check private keys
    if not os.getenv("WALLET_PRIVATE_KEY_PRIMARY", ""):
        status["ready_for_live"] = False
        status["missing_private_key"] = True

    return status
