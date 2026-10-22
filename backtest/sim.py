"""Bar-level exit simulation mirroring the live Winning v32 monitor rules.

Rules (price-move %, leverage-agnostic), evaluated on 1h bars:
  * structure SL / TP from the signal (exchange-side triggers)
  * break-even: peak ≥ +be_pct → SL = entry ± be_buffer
  * TP1: 40% off at +2%
  * tiered trail from peak: +2% → 1.25%, +4% → 1.75%, +8% → 2.5%
  * 45-min rule: first bar closes red → SL tightened to −1.5%
  * loss timeout: still red at timeout_h → close at bar close
  * hard cap −5% (monitor market close); max hold safety cap
Conservative intrabar ordering: a bar's SL check uses the stop set by prior
bars (this bar's high can't both raise the trail and stop it), and when SL and
TP are both inside one bar the SL fills first. Stops fill at the worse of the
stop and the bar open (gaps), with adverse slippage. Fees: taker both sides.
Returns net % of notional (unlevered) and R multiple.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

TAKER_FEE = 0.00045       # Hyperliquid base-tier taker, per side
SLIP = 0.0005             # 5 bps adverse on stop / market exits
DEFAULT_LADDER = ((2.0, 1.25), (4.0, 1.75), (8.0, 2.5))


@dataclass(frozen=True)
class ExitParams:
    be_pct: float = 0.75
    be_buffer_pct: float = 0.05
    tp1_pct: float = 2.0
    tp1_frac: float = 0.40
    ladder: tuple = DEFAULT_LADDER
    min_rule_sl_pct: float = -1.5
    timeout_h: float = 4.0
    hard_cap_pct: float = -5.0
    max_hold_h: int = 168
    enforce_sltp: bool = True


@dataclass
class Outcome:
    exit_ms: int
    net_pct: float
    r: float
    reason: str
    hold_h: int
    mfe_pct: float


def _trail_dist(peak_pct: float, ladder: Sequence) -> float | None:
    d = None
    for thr, dist in ladder:
        if peak_pct >= thr:
            d = dist
    return d


def simulate(direction: str, entry: float, sl: float, tp: float, bars: Sequence[dict],
             p: ExitParams = ExitParams()) -> Outcome:
    """bars: the 1h bars AFTER entry (entry at the close of the signal bar)."""
    sgn = 1.0 if direction == "long" else -1.0
    risk_pct = abs(entry - sl) / entry * 100.0 if sl else 2.5

    def mv(px: float) -> float:
        return sgn * (px - entry) / entry * 100.0

    def adverse(px: float) -> float:     # apply slippage against us
        return px * (1.0 - sgn * SLIP)

    stop = sl
    rem = 1.0
    realized = 0.0   # % of notional already banked (weighted)
    tp1 = False
    peak = entry
    mfe = 0.0

    def done(exit_px: float, j: int, reason: str) -> Outcome:
        net = realized + rem * mv(exit_px) - 2 * TAKER_FEE * 100.0
        return Outcome(exit_ms=int(bars[j]["t"]) + 3_600_000, net_pct=net,
                       r=net / risk_pct if risk_pct > 0 else 0.0, reason=reason,
                       hold_h=j + 1, mfe_pct=mfe)

    n = min(len(bars), p.max_hold_h)
    if n == 0:
        return Outcome(exit_ms=0, net_pct=-2 * TAKER_FEE * 100.0, r=0.0, reason="no_data", hold_h=0, mfe_pct=0.0)
    for j in range(n):
        b = bars[j]
        o, h, l, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
        fav, adv = (h, l) if sgn > 0 else (l, h)
        # 1) stop (incl. trailed / BE) from prior state
        if p.enforce_sltp and stop:
            hit = (adv <= stop) if sgn > 0 else (adv >= stop)
            if hit:
                gap_px = min(stop, o) if sgn > 0 else max(stop, o)
                why = "trail_stop" if mv(stop) > 0 else "sl_hit"
                return done(adverse(gap_px), j, why)
        # 2) hard cap (monitor)
        if mv(adv) <= p.hard_cap_pct:
            return done(adverse(entry * (1 + sgn * p.hard_cap_pct / 100.0)), j, "hard_loss_cap")
        # 3) TP1 partial, then full TP
        if not tp1 and mv(fav) >= p.tp1_pct and (not tp or mv(tp) > p.tp1_pct):
            realized += p.tp1_frac * p.tp1_pct
            rem -= p.tp1_frac
            tp1 = True
        if p.enforce_sltp and tp:
            if (fav >= tp) if sgn > 0 else (fav <= tp):
                return done(adverse(tp), j, "tp_hit")
        # 4) update peak → BE / trail for next bars
        if (sgn > 0 and fav > peak) or (sgn < 0 and fav < peak):
            peak = fav
        mfe = max(mfe, mv(peak))
        new_stop = stop
        if mv(peak) >= p.be_pct:
            be = entry * (1 + sgn * p.be_buffer_pct / 100.0)
            new_stop = be if new_stop is None else (max(new_stop, be) if sgn > 0 else min(new_stop, be))
        d = _trail_dist(mv(peak), p.ladder)
        if d is not None:
            tr = peak * (1 - sgn * d / 100.0)
            if new_stop is None:
                new_stop = tr
            else:
                new_stop = max(new_stop, tr) if sgn > 0 else min(new_stop, tr)
        # 5) 45-min rule & loss timeout on the bar close
        if mv(c) < 0:
            if j == 0:
                t = entry * (1 + sgn * p.min_rule_sl_pct / 100.0)
                if new_stop is None:
                    new_stop = t
                else:
                    new_stop = max(new_stop, t) if sgn > 0 else min(new_stop, t)
            if (j + 1) >= p.timeout_h:
                return done(adverse(c), j, "loss_timeout")
        stop = new_stop
    return done(adverse(float(bars[n - 1]["c"])), n - 1, "max_hold")
