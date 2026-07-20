# Shamrock Trading Bot: Profit-Lock & High-Frequency Alpha Upgrade

**Date:** July 20, 2026  
**Status:** Profit-lock **INTEGRATED** (trailing monitor). HF Moralis scanner remains a **disabled stub**.  
**Target:** Cut multi-hour loser bleed; lock winners earlier; keep existing ROE trail for runners.

---

## What shipped vs what Manus left unfinished

Manus commit `81b4849` added two modules but **did not wire them** into the live loop:

| Module | Manus state | After this integration |
|--------|-------------|------------------------|
| `core/profit_lock_manager.py` | Standalone stateful manager; deadlock risk (`Lock` re-entry); conflicting `hl_trailing_state.json` format | Pure `evaluate_position()` decision engine; applied inside existing HL trailing monitor |
| `core/moralis_hf_scanner.py` | Placeholder returning `[]` | Default **disabled**; not started in `main.py` until real API + HL ticker map exists |

---

## Integrated profit-lock (live)

Wired in `main.py` → `_hl_trailing_monitor_daemon` (same thread that already manages ROE trailing).

### Rules (price-move %, leverage-agnostic)

1. **Break-even lock (+1.5%)** — move SL to entry ± 0.1% (fee buffer)
2. **Early trail (+3%)** — trail 1.5% from peak before full ROE trail activates
3. **Hard time-out** — if still in **loss** after **4 hours**, `close_position()` to free capital

Existing ROE trail (trigger 10% ROE, step-tighten at 20%/50% ROE) still runs after early lock.

### Why (trade_history 28)

- Losers held ≥4h last 7d: **7 trades, −$55.33** (KAITO −$18.68, LDO −$20.99, PUMP −$6.99, …)
- Prior system only activated trailing at ~10% ROE (~3.3% price at 3x) — winners could reverse to full SL before any lock
- KAITO: 7 trades / 14% WR / −$30.57 last 7d → added to `HL_PERPS_TOXIC_COINS`

---

## Config

```env
PROFIT_LOCK_ENABLED=true
PROFIT_LOCK_BE_PCT=1.5
PROFIT_LOCK_BE_BUFFER_PCT=0.1
PROFIT_LOCK_TRAIL_ACTIVATE_PCT=3.0
PROFIT_LOCK_TRAIL_DISTANCE_PCT=1.5
PROFIT_LOCK_LOSS_TIMEOUT_HOURS=4.0

# Stub — keep false
HF_MORALIS_SCANNER_ENABLED=false
```

CI deploy patches `PROFIT_LOCK_ENABLED`, `PROFIT_LOCK_LOSS_TIMEOUT_HOURS`, toxic list (+KAITO), and forces HF scanner off.

---

## Tests

```bash
python -m pytest tests/test_profit_lock_manager.py -q
```

---

## Rollback

```env
PROFIT_LOCK_ENABLED=false
```

Or revert the trailing-monitor block in `main.py` and restore prior `profit_lock_manager.py`.

---

## Still open (not in this pass)

1. Real HF Moralis → HL perp intersection for entry boosts (stub only)
2. Autoban sample size for KAITO is already met — toxic score bar is the hard gate
3. Monitor next 7 days: expect fewer multi-hour red holds; WR may rise mainly via smaller loser tails
