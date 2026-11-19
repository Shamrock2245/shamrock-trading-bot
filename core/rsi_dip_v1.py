"""Paper-only long RSI dip sleeve (rsi_dip_v1).

Frozen forward test of the 1h capitulation-buy from
docs/backtest/ALT_STRATEGY_RESEARCH_2026-11-03.md. The research parameters
stay code constants (the walk-forward tuner may recommend new ones; it does
not apply them):

  * 1h candles, signal on the last *closed* bar, fill at the paper mid
  * long when RSI(14) <= 20 (Wilder / pandas ewm alpha=1/14, same as the study)
  * exit when RSI(14) >= 50, or after 12 hours, whichever comes first
  * stop = entry − 3 × ATR(14); checked before the RSI and time exits
  * at most 3 open positions in this sleeve
  * universe = Predator allowlist minus the hard-ban list

A stop-out is different from an RSI or time exit: that coin stays blocked
until RSI_DIP_STOP_COOLDOWN_HOURS has passed and a later closed bar has
printed RSI at or above RSI_DIP_STOP_REARM_RSI. Both default on. Zero
disables that gate. State is output/rsi_dip_stop_cooldowns.json.

Flag RSI_DIP_V1_ENABLED defaults off in code. .env.example and the CI deploy
sed turn it on for the paper host. enabled() is still false unless the
process mode is paper, so the flag cannot reach a live order.

This sleeve does not score with Moralis, does not join the Predator exit A/B
(control vs atr2x_8h), and does not count toward the Predator promote gate.
Its journal rows carry strategy='rsi_dip_v1'. The paper tournament can pause
new entries; open positions still exit.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STRATEGY = "rsi_dip_v1"
FLAG = "RSI_DIP_V1_ENABLED"

# Frozen. Do not read these from the environment.
RSI_PERIOD = 14
RSI_ENTRY = 20.0
RSI_EXIT = 50.0
MAX_HOLD_HOURS = 12.0
ATR_PERIOD = 14
ATR_MULT = 3.0
MAX_CONCURRENT = 3
TIMEFRAME = "1h"
CANDLE_LOOKBACK_HOURS = 120
MIN_MARGIN_USD = 10.0

EXIT_STOP = "stop"
EXIT_RSI = "rsi_revert"
EXIT_TIME = "time"


def _env_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def cooldown_hours() -> float:
    """Hours a coin stays blocked after a stop. 0 disables the clock."""
    return max(0.0, _env_float("RSI_DIP_STOP_COOLDOWN_HOURS", "6"))


def rearm_level() -> float:
    """RSI that must print after the stop before the coin can arm again. <= 0 disables."""
    level = _env_float("RSI_DIP_STOP_REARM_RSI", "35")
    return level if level > 0 else 0.0


def now_ts() -> float:
    return time.time()


def _cooldown_path() -> Path:
    return Path(os.getenv("RSI_DIP_COOLDOWN_STATE_FILE", "output/rsi_dip_stop_cooldowns.json"))


def _load_stop_state() -> dict:
    path = _cooldown_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_stop_state(state: dict) -> None:
    path = _cooldown_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.debug(f"[RSI-DIP] cooldown state write failed: {exc}")


def note_stop_out(coin: str, now: Optional[float] = None) -> None:
    """Remember a stop. RSI and time exits do not call this."""
    name = (coin or "").strip().upper()
    if not name:
        return
    state = _load_stop_state()
    state[name] = {
        "stopped_at": float(now if now is not None else now_ts()),
        "rearmed": False,
    }
    _save_stop_state(state)


def refresh_stop_rearm(coin: str, bars: list[tuple]) -> None:
    """Mark the coin rearmed once a closed bar after the stop prints RSI >= level."""
    level = rearm_level()
    if level <= 0:
        return
    name = (coin or "").strip().upper()
    state = _load_stop_state()
    rec = state.get(name)
    if not rec or rec.get("rearmed"):
        return
    stopped = float(rec.get("stopped_at") or 0)
    closes = [float(bar[4]) for bar in bars or []]
    path = rsi_path(closes)
    for i, bar in enumerate(bars or []):
        if float(bar[1]) / 1000.0 <= stopped:
            continue
        rsi = path[i] if i < len(path) else None
        if rsi is not None and float(rsi) >= level:
            rec["rearmed"] = True
            state[name] = rec
            _save_stop_state(state)
            return


def stop_block_reason(coin: str, now: Optional[float] = None) -> Optional[str]:
    """Why this coin cannot re-enter, or None when the stop block has cleared."""
    name = (coin or "").strip().upper()
    state = _load_stop_state()
    rec = state.get(name)
    if not rec:
        return None
    now_v = float(now if now is not None else now_ts())
    elapsed_h = (now_v - float(rec.get("stopped_at") or 0)) / 3600.0
    cool = cooldown_hours()
    if cool > 0 and elapsed_h < cool:
        return "stop_cooldown"
    if rearm_level() > 0 and not rec.get("rearmed"):
        return "stop_rearm"
    state.pop(name, None)
    _save_stop_state(state)
    return None


def paper_mode_active() -> bool:
    """True only when the process mode is paper. Fails closed."""
    try:
        from config import settings as _s
        return _s.get_current_mode() == "paper"
    except Exception:
        return False


def enabled() -> bool:
    """Sleeve flag, default off. Never true outside paper mode."""
    flag = os.getenv(FLAG, "false").strip().lower() in ("1", "true", "yes", "on")
    if not flag:
        return False
    return paper_mode_active()


def is_sleeve_position(pos) -> bool:
    """True for this sleeve and any other name in the paper-sleeve set.

    The executor uses this to keep sleeve closes out of Predator autoban,
    the hot streak, and the daily-goal switch. rsi_dip_v1 is always included.
    """
    if pos is None:
        return False
    from core.paper_sleeves import is_sleeve_strategy
    if is_sleeve_strategy(getattr(pos, "strategy", "")):
        return True
    ctx = getattr(pos, "regime_ctx", None) or {}
    return is_sleeve_strategy(ctx.get("strategy"))


def rsi_ewm(closes: list[float], period: int = RSI_PERIOD) -> Optional[float]:
    """RSI matching the research script: diff.clip ewm(alpha=1/period, adjust=False).

    The first price change seeds the average (pandas ewm adjust=False). A flat
    series (no up and no down) returns None so it cannot signal.
    """
    if closes is None or len(closes) < period + 1:
        return None
    alpha = 1.0 / period
    avg_up = None
    avg_dn = None
    for i in range(1, len(closes)):
        delta = float(closes[i]) - float(closes[i - 1])
        up = delta if delta > 0 else 0.0
        dn = -delta if delta < 0 else 0.0
        if avg_up is None:
            avg_up = up
            avg_dn = dn
        else:
            avg_up = alpha * up + (1.0 - alpha) * avg_up
            avg_dn = alpha * dn + (1.0 - alpha) * avg_dn
    if not avg_dn:
        if avg_up and avg_up > 0:
            return 100.0
        return None
    return 100.0 - (100.0 / (1.0 + (avg_up / avg_dn)))


def rsi_path(closes: list[float], period: int = RSI_PERIOD) -> list[Optional[float]]:
    """RSI after each close. The last value matches rsi_ewm. Early bars are None."""
    n = 0 if closes is None else len(closes)
    out: list[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    alpha = 1.0 / period
    avg_up = None
    avg_dn = None
    for i in range(1, n):
        delta = float(closes[i]) - float(closes[i - 1])
        up = delta if delta > 0 else 0.0
        dn = -delta if delta < 0 else 0.0
        if avg_up is None:
            avg_up = up
            avg_dn = dn
        else:
            avg_up = alpha * up + (1.0 - alpha) * avg_up
            avg_dn = alpha * dn + (1.0 - alpha) * avg_dn
        if i < period:
            continue
        if not avg_dn:
            out[i] = 100.0 if avg_up and avg_up > 0 else None
        else:
            out[i] = 100.0 - (100.0 / (1.0 + (avg_up / avg_dn)))
    return out


def atr_ewm(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = ATR_PERIOD,
) -> Optional[float]:
    """ATR matching the research script: true range ewm(alpha=1/period, adjust=False)."""
    n = len(closes) if closes is not None else 0
    if n < period + 1 or len(highs) < n or len(lows) < n:
        return None
    alpha = 1.0 / period
    ema = None
    for i in range(1, n):
        h = float(highs[i])
        l = float(lows[i])
        prev = float(closes[i - 1])
        tr = max(h - l, abs(h - prev), abs(l - prev))
        ema = tr if ema is None else alpha * tr + (1.0 - alpha) * ema
    if ema is None or ema <= 0:
        return None
    return float(ema)


def atr_path(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = ATR_PERIOD,
) -> list[Optional[float]]:
    """ATR after each bar. The last value matches atr_ewm once history is long enough."""
    n = len(closes) if closes is not None else 0
    out: list[Optional[float]] = [None] * n
    if n < 2 or len(highs) < n or len(lows) < n:
        return out
    alpha = 1.0 / period
    ema = None
    for i in range(1, n):
        high = float(highs[i])
        low = float(lows[i])
        prev = float(closes[i - 1])
        tr = max(high - low, abs(high - prev), abs(low - prev))
        ema = tr if ema is None else alpha * tr + (1.0 - alpha) * ema
        if i >= period and ema and ema > 0:
            out[i] = float(ema)
    return out


def entry_signal(rsi: Optional[float]) -> bool:
    """Long-only. RSI >= 80 is not a short."""
    return rsi is not None and float(rsi) <= RSI_ENTRY


def atr_stop_price(entry: float, atr: Optional[float], mult: float = ATR_MULT) -> Optional[float]:
    """Long stop: entry − mult × ATR. None unless it sits strictly below entry."""
    try:
        entry_f = float(entry)
        atr_f = float(atr) if atr is not None else 0.0
    except (TypeError, ValueError):
        return None
    if entry_f <= 0 or atr_f <= 0 or mult <= 0:
        return None
    stop = entry_f - mult * atr_f
    if stop <= 0 or stop >= entry_f:
        return None
    return stop


def exit_reason(
    *,
    rsi: Optional[float],
    held_hours: Optional[float],
    mark: Optional[float],
    stop: Optional[float],
) -> Optional[str]:
    """Stop first (intrabar), then RSI reversion, then the 12h time stop.

    Same precedence as the research simulator: a stop on the bar wins over
    the RSI exit, and the RSI exit wins over the time stop.
    """
    try:
        mark_f = float(mark) if mark is not None else None
        stop_f = float(stop) if stop is not None else None
    except (TypeError, ValueError):
        mark_f, stop_f = None, None
    if mark_f is not None and stop_f is not None and stop_f > 0 and mark_f <= stop_f:
        return EXIT_STOP
    if rsi is not None and float(rsi) >= RSI_EXIT:
        return EXIT_RSI
    if held_hours is not None and float(held_hours) >= MAX_HOLD_HOURS:
        return EXIT_TIME
    return None


def hours_held(opened_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    if opened_at is None:
        return None
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - opened_at).total_seconds() / 3600.0


def in_universe(coin: str, allow: set[str], ban: set[str]) -> bool:
    """Allowlist minus hard-ban. An empty allowlist fails closed."""
    c = (coin or "").strip().upper()
    if not c or not allow:
        return False
    if c in ban or c not in allow:
        return False
    return True


def universe_coins(allow: Optional[set[str]] = None, ban: Optional[set[str]] = None) -> list[str]:
    if allow is None or ban is None:
        from core.predator_v1 import allowlist, hard_ban
        if allow is None:
            allow = allowlist()
        if ban is None:
            ban = hard_ban()
    return sorted(c for c in allow if in_universe(c, allow, ban))


def sleeve_admission(
    coin: str,
    open_sleeve: set[str],
    *,
    max_concurrent: int = MAX_CONCURRENT,
) -> tuple[bool, str]:
    """Concurrent sleeve cap (default 3), one position per coin."""
    c = (coin or "").strip().upper()
    if not c:
        return False, "bad_coin"
    if c in open_sleeve:
        return False, "already_open"
    try:
        cap = int(max_concurrent)
    except (TypeError, ValueError):
        cap = MAX_CONCURRENT
    if cap <= 0 or len(open_sleeve) >= cap:
        return False, "sleeve_cap"
    return True, "ok"


def _sleeve_slot_cap() -> int:
    """Tournament cap. A failure leaves the sleeve at its own max of 3."""
    try:
        from core.strategy_tournament import slot_cap
        return int(slot_cap(STRATEGY, MAX_CONCURRENT))
    except Exception as exc:
        logger.debug(f"[RSI-DIP] tournament cap unavailable: {exc}")
        return MAX_CONCURRENT


def plan_margin_usd(
    *,
    equity: float,
    max_positions: int,
    max_position_usd: float,
    max_notional_usd: float,
    leverage: int,
    margin_equity_pct: float,
    max_loss_usd: float,
    entry: float,
    atr: float,
    size_multiplier: float = 1.0,
) -> Optional[float]:
    """Slot size (the scanner's unknown-EV Kelly branch) clamped to the live caps.

    The 3×ATR stop distance is not tightened. MAX_TRADE_LOSS_USD is honored by
    shrinking margin so a stop-out at that distance stays inside the cap.
    Returns None when even the $10 minimum would break a cap.
    """
    try:
        equity_f = float(equity)
        entry_f = float(entry)
        atr_f = float(atr)
        lev = int(leverage)
    except (TypeError, ValueError):
        return None
    if equity_f <= 0 or entry_f <= 0 or atr_f <= 0 or lev <= 0:
        return None
    slots = max_positions if max_positions and max_positions > 0 else 6
    size = max(MIN_MARGIN_USD, equity_f / slots)
    try:
        mult = float(size_multiplier)
    except (TypeError, ValueError):
        mult = 1.0
    if mult > 0:
        size *= mult
    caps = []
    if max_position_usd and max_position_usd > 0:
        caps.append(float(max_position_usd))
    if margin_equity_pct and margin_equity_pct > 0:
        caps.append(equity_f * float(margin_equity_pct))
    if max_notional_usd and max_notional_usd > 0:
        caps.append(float(max_notional_usd) / lev)
    stop_frac = (ATR_MULT * atr_f) / entry_f
    if stop_frac <= 0:
        return None
    if max_loss_usd and max_loss_usd > 0:
        caps.append(float(max_loss_usd) / (lev * stop_frac))
    if caps:
        size = min(size, *caps)
    if size < MIN_MARGIN_USD:
        return None
    return round(size, 2)


def closed_bars(candles, now_ms: Optional[int] = None) -> list[tuple]:
    """Closed 1h bars as (open_ms, close_ms, high, low, close). Drops the forming bar."""
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    out = []
    for c in candles or []:
        if not isinstance(c, dict):
            continue
        try:
            t = int(float(c.get("t") or 0))
            close_ms = int(float(c.get("T") or 0))
            h = float(c["h"])
            l = float(c["l"])
            cl = float(c["c"])
        except (TypeError, ValueError, KeyError):
            continue
        if h <= 0 or l <= 0 or cl <= 0 or h < l:
            continue
        if close_ms <= 0 and t > 0:
            close_ms = t + 3_600_000
        if close_ms >= now:
            continue
        out.append((t, close_ms, h, l, cl))
    out.sort(key=lambda b: b[0])
    return out


def bar_indicators(bars: list[tuple]) -> Optional[tuple[float, float]]:
    """RSI and ATR of the last closed bar. None when there is not enough history."""
    if len(bars) < max(RSI_PERIOD, ATR_PERIOD) + 1:
        return None
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    closes = [b[4] for b in bars]
    rsi = rsi_ewm(closes, RSI_PERIOD)
    atr = atr_ewm(highs, lows, closes, ATR_PERIOD)
    if rsi is None or atr is None:
        return None
    return float(rsi), float(atr)


def _sleeve_coins(positions: dict) -> set[str]:
    return {str(c).upper() for c, p in (positions or {}).items() if is_sleeve_position(p)}


def _close_paper(executor, sym: str, *, fill: Optional[float], reason: str):
    """Paper close only. Never calls market_close."""
    if not getattr(executor, "is_paper", False) or not paper_mode_active():
        logger.error(f"[RSI-DIP] {sym} close refused — not paper; no order sent")
        return None
    return executor._paper_close_position(sym, fill_price=fill, exit_reason=reason)


def _manage_exits(scanner, executor) -> list[str]:
    closed: list[str] = []
    positions = dict(getattr(executor, "positions", {}) or {})
    for coin, pos in positions.items():
        if not is_sleeve_position(pos):
            continue
        sym = str(coin).upper()
        mark = None
        try:
            mark = executor.get_price(sym) if hasattr(executor, "get_price") else None
        except Exception:
            mark = None
        if not mark:
            try:
                mark = executor._paper_mid_price(sym)
            except Exception:
                mark = None
        rsi = None
        try:
            raw = scanner._get_candles(sym, TIMEFRAME, CANDLE_LOOKBACK_HOURS)
            bars = closed_bars(raw)
            ind = bar_indicators(bars)
            if ind is not None:
                rsi = ind[0]
        except Exception as exc:
            logger.debug(f"[RSI-DIP] {sym} exit candles failed: {exc}")
        reason = exit_reason(
            rsi=rsi,
            held_hours=hours_held(getattr(pos, "opened_at", None)),
            mark=float(mark) if mark else None,
            stop=getattr(pos, "stop_loss_price", None),
        )
        if not reason:
            continue
        fill = None
        if reason == EXIT_STOP and mark and pos.stop_loss_price:
            # Same adverse gap fill the paper trigger uses: worse of stop and mark.
            try:
                from core.hyperliquid_executor import paper_trigger_slippage_frac
                slip = paper_trigger_slippage_frac()
            except Exception:
                slip = 0.0005
            fill = min(float(pos.stop_loss_price), float(mark)) * (1.0 - slip)
        res = None
        if reason == EXIT_STOP and hasattr(executor, "check_paper_triggers") and mark:
            try:
                res = executor.check_paper_triggers(sym, float(mark))
            except Exception as exc:
                logger.debug(f"[RSI-DIP] {sym} trigger check failed: {exc}")
        if res is None:
            res = _close_paper(executor, sym, fill=fill, reason=reason)
        if res:
            closed.append(sym)
            if reason == EXIT_STOP:
                note_stop_out(sym)
            logger.info(
                f"[RSI-DIP] CLOSE {sym} reason={reason} rsi={rsi if rsi is not None else 'na'}"
            )
    return closed


def _entry_blocked(scanner, executor) -> Optional[str]:
    """Shared account risk caps. None when a new sleeve entry is allowed."""
    try:
        if hasattr(executor, "_check_daily_reset"):
            executor._check_daily_reset()
    except Exception:
        pass
    try:
        if hasattr(scanner, "_check_daily_reset"):
            scanner._check_daily_reset()
    except Exception:
        pass
    daily_limit = float(getattr(executor, "daily_loss_limit", 0) or 0)
    if daily_limit > 0 and float(getattr(executor, "daily_pnl", 0) or 0) <= -daily_limit:
        return "executor_daily_loss"
    try:
        from core.hl_perps_scanner import (
            HL_PERPS_BASE_CAPITAL,
            HL_PERPS_DAILY_LOSS_LIMIT,
            HL_PERPS_MAX_OPENS_PER_DAY,
        )
    except Exception:
        HL_PERPS_BASE_CAPITAL = 150.0
        HL_PERPS_DAILY_LOSS_LIMIT = 80.0
        HL_PERPS_MAX_OPENS_PER_DAY = 6
    equity = HL_PERPS_BASE_CAPITAL
    try:
        bal = executor.get_balance()
        equity = float(bal.get("account_value") or bal.get("equity") or equity)
    except Exception:
        pass
    scan_limit = max(HL_PERPS_DAILY_LOSS_LIMIT, round(equity * 0.33, 2))
    if float(getattr(scanner, "daily_pnl", 0) or 0) <= -scan_limit:
        return "scanner_daily_loss"
    opens = int(getattr(scanner, "opens_today", 0) or 0)
    if HL_PERPS_MAX_OPENS_PER_DAY > 0 and opens >= HL_PERPS_MAX_OPENS_PER_DAY:
        return "daily_open_cap"
    return None


def _manage_entries(scanner, executor) -> list[str]:
    opened: list[str] = []
    block = _entry_blocked(scanner, executor)
    if block:
        logger.info(f"[RSI-DIP] entries paused — {block}")
        return opened
    cap = _sleeve_slot_cap()
    if cap <= 0:
        logger.info("[RSI-DIP] entries paused — strategy tournament")
        return opened
    coins = universe_coins()
    positions = getattr(executor, "positions", {}) or {}
    sleeve_open = _sleeve_coins(positions)
    candidates = []
    for coin in coins:
        if str(coin).upper() in {str(k).upper() for k in positions.keys()}:
            continue
        try:
            raw = scanner._get_candles(coin, TIMEFRAME, CANDLE_LOOKBACK_HOURS)
        except Exception as exc:
            logger.debug(f"[RSI-DIP] {coin} candles failed: {exc}")
            continue
        bars = closed_bars(raw)
        refresh_stop_rearm(coin, bars)
        ind = bar_indicators(bars)
        if ind is None:
            continue
        rsi, atr = ind
        if not entry_signal(rsi):
            continue
        blocked = stop_block_reason(coin)
        if blocked:
            logger.info(f"[RSI-DIP] {coin} skipped — {blocked}")
            continue
        candidates.append((rsi, coin, atr))
    # Deepest dip first when several coins signal on the same pass (the cap
    # study kept the earliest fill; a live scan sees them together).
    candidates.sort(key=lambda row: (row[0], row[1]))
    try:
        freq = scanner._goal_frequency_params()
    except Exception:
        freq = {}
    goal_slots = int(freq.get("max_positions") or 0)
    exec_slots = int(getattr(executor, "max_positions", 0) or 0)
    if goal_slots and exec_slots:
        global_max = min(goal_slots, exec_slots)
    else:
        global_max = goal_slots or exec_slots or 4
    size_mult = float(freq.get("size_multiplier") or 1.0)
    try:
        from core.hl_perps_scanner import (
            HL_PERPS_LEVERAGE,
            HL_PERPS_MAX_NOTIONAL_USD,
            HL_PERPS_MAX_POSITION_USD,
        )
    except Exception:
        HL_PERPS_LEVERAGE = 3
        HL_PERPS_MAX_NOTIONAL_USD = 350.0
        HL_PERPS_MAX_POSITION_USD = 150.0
    lev = int(getattr(executor, "default_leverage", None) or HL_PERPS_LEVERAGE or 3)
    lev = max(1, lev)
    max_pos_usd = float(getattr(executor, "max_position_usd", None) or HL_PERPS_MAX_POSITION_USD)
    max_notional = float(getattr(executor, "max_notional_usd", None) or HL_PERPS_MAX_NOTIONAL_USD)
    margin_pct = float(getattr(executor, "max_margin_equity_pct", None) or 0.15)
    try:
        max_loss = float(os.getenv("MAX_TRADE_LOSS_USD", "15.0"))
    except (TypeError, ValueError):
        max_loss = 15.0

    for rsi, coin, atr in candidates:
        positions = getattr(executor, "positions", {}) or {}
        sleeve_open = _sleeve_coins(positions)
        ok, why = sleeve_admission(coin, sleeve_open, max_concurrent=cap)
        if not ok:
            logger.info(f"[RSI-DIP] {coin} skipped — {why}")
            continue
        if global_max and len(positions) >= global_max:
            logger.info(f"[RSI-DIP] {coin} skipped — global position cap {global_max}")
            break
        if _entry_blocked(scanner, executor):
            break
        mark = None
        try:
            mark = executor.get_price(coin)
        except Exception:
            mark = None
        if not mark:
            try:
                mark = executor._paper_mid_price(coin)
            except Exception:
                mark = None
        if not mark or float(mark) <= 0:
            logger.info(f"[RSI-DIP] {coin} skipped — no mid")
            continue
        equity = 0.0
        try:
            bal = executor.get_balance()
            equity = float(bal.get("account_value") or 0)
        except Exception:
            equity = 0.0
        size = plan_margin_usd(
            equity=equity,
            max_positions=global_max,
            max_position_usd=max_pos_usd,
            max_notional_usd=max_notional,
            leverage=lev,
            margin_equity_pct=margin_pct,
            max_loss_usd=max_loss,
            entry=float(mark),
            atr=atr,
            size_multiplier=size_mult,
        )
        if size is None:
            logger.info(f"[RSI-DIP] {coin} skipped — size outside risk caps")
            continue
        res = executor.open_paper_sleeve(
            coin,
            size_usd=size,
            leverage=lev,
            atr=atr,
            strategy=STRATEGY,
            rsi=rsi,
        )
        if not res:
            continue
        opened.append(str(coin).upper())
        try:
            scanner.opens_today = int(getattr(scanner, "opens_today", 0) or 0) + 1
        except Exception:
            pass
        logger.info(
            f"[RSI-DIP] OPEN LONG {coin} rsi={rsi:.2f} atr={atr:.6f} "
            f"margin=${size:.2f} × {lev}x stop=${res.get('stop_loss')}"
        )
    return opened


def run_sleeve(scanner, *, allow_entries: bool = True) -> list[str]:
    """One pass: exit open sleeve positions, then maybe open new ones.

    Returns the coins that were closed or opened. No-op when the flag is off
    or the process is not in paper mode. Does not call the live order path.
    """
    if not enabled():
        return []
    executor = getattr(scanner, "hl_executor", None)
    if executor is None:
        return []
    if not getattr(executor, "is_paper", False) or not paper_mode_active():
        logger.error("[RSI-DIP] executor is not paper — sleeve idle, no order sent")
        return []
    try:
        from core.strategy_tournament import publish
        publish()
    except Exception as exc:
        logger.debug(f"[RSI-DIP] tournament status skipped: {exc}")
    acted = _manage_exits(scanner, executor)
    if allow_entries:
        acted.extend(_manage_entries(scanner, executor))
    return acted
