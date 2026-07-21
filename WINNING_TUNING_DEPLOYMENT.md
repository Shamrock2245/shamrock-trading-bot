# Shamrock Trading Bot: "Winning" Tuning — Integration Complete

**Date:** July 21, 2026  
**Status:** **WIRED** into production code paths (Manus modules were previously unwired)  
**Source CSV:** `trade_history (29).csv` (406 fills, 221 closed pairs)

---

## Second-set-of-eyes findings (Manus gap)

Manus commit `8d776bb` added four files only:

| File | Manus state | After this pass |
|------|-------------|-----------------|
| `core/winning_risk_manager.py` | Standalone; **TP1/trail dead** (BE always returned first); **zero callers** | Pure `evaluate_position()`; correct priority; wired in `main.py` trailing monitor |
| `core/hl_scanner_winning_tuning.py` | Standalone; **zero callers** | Stateful filter + SL blacklist; wired in `hl_perps_scanner._execute_signal` |
| `.env.winning` | Reference only; enabled HF Moralis stub | Corrected; CI patches live `.env` on deploy |
| `WINNING_TUNING_DEPLOYMENT.md` | "how to integrate later" | Documents **actual** wiring |

This is the same pattern as Manus’s earlier profit-lock drop (fixed in `1ccf85c` / `PROFIT_LOCK_UPGRADE.md`).

---

## trade_history (29) diagnosis (verified)

| Metric | Value |
|--------|------:|
| Closed trades | 221 |
| Win rate | 35.75% |
| Profit factor | **0.668** |
| Net PnL | **−$298.21** |
| Small losses (&lt;$3) | 87 trades, −$62.63 |
| Losers held ≥30m | 64 trades, −$603.63 |
| Losers held ≥4h | 44 trades, **−$503.63** |
| Opens 08–14 (hour) | 110 trades, **−$326.10** |
| Other hours | 111 trades, **+$27.90** |
| Last 7d | 53 trades, 39.6% WR, PF ≈ 1.01, net +$1 |

Manus’s high-level diagnosis is right (small cuts + long bleeds + toxic hours). The **largest** dollar leak is multi-hour losers, not sub-$3 noise.

---

## What is live now

### Exit path — `main.py` → `_hl_trailing_monitor_daemon`

When `WINNING_RISK_MANAGER_ENABLED=true` (default):

1. **Hard timeout 2h** still red → `close_position()` (tighter than profit_lock 4h)
2. **TP1 @ +2%** → `close_position(size_pct=50)` partial; marks `tp1_hit`
3. **Ultra-fast BE @ +0.75%** → SL to entry + 0.05%
4. **Aggressive trail 0.5%** from peak after TP1 / +2%
5. **30-Min Rule** still red → tighten SL to −1%

When Winning is **off**, legacy profit_lock (BE 1.5% / trail 3% / 4h) still runs.

### Entry path — `hl_perps_scanner._execute_signal`

When `WINNING_ENTRY_FILTER_ENABLED=true` (default):

1. **$1M** `dayNtlVlm` floor (missing volume = allow; don’t halt book on cache miss)
2. Dynamic blacklist after **3 SL hits / 24h**
3. High ATR size cut (when atr provided)
4. **Toxic zone 08–14 ET** → size × 0.5

Toxic list adds **HEMI, ONDO** from v29.

### Executor

- `HLPosition.tp1_hit` persisted in `hl_trailing_state.json`
- `close_position(symbol, size_pct=…)` for TP1 partials via `market_close(sz=…)`

---

## Config (also in `.env.example` + CI deploy patch)

```env
WINNING_RISK_MANAGER_ENABLED=true
WINNING_ENTRY_FILTER_ENABLED=true
FAST_BREAK_EVEN_PCT=0.75
TP1_PROFIT_PCT=2.0
TP1_SIZE_PCT=50
MIN_RULE_TIME_MINUTES=30
TRAILING_STOP_PCT=0.5
WINNING_LOSS_TIMEOUT_HOURS=2.0
TOXIC_ZONE_RESTRICTION=true
MIN_VOLUME_USD=1000000
HF_MORALIS_SCANNER_ENABLED=false   # still a stub — never enable
```

---

## Tests

```bash
python -m pytest tests/test_winning_risk_manager.py tests/test_profit_lock_manager.py -q
```

---

## Deploy

```bash
# After merge to main (CI also patches server .env):
docker compose build --no-cache && docker compose up -d
docker compose logs -f shamrock-bot | grep -E "WINNING|Winning|TP1|30min|Toxic Zone"
```

---

## Knobs if too tight / too loose

| Symptom | Adjust |
|---------|--------|
| Too few entries | Lower `MIN_VOLUME_USD` to 500000 |
| Still multi-hour red | Lower `WINNING_LOSS_TIMEOUT_HOURS` to 1.5 |
| Stopped out of winners | Raise `FAST_BREAK_EVEN_PCT` to 1.0 or `TRAILING_STOP_PCT` to 0.8 |
| Toxic hours still bleed | Expand `HL_PERPS_BLOCKED_HOURS_ET` (already blocks 10,17,22 hard) |

---

## Explicitly NOT claimed

- Profit factor will not magically jump to 1.5 on day one — need 3–7 days of live sample.
- VWAP filter only applies when `vwap_15m` is supplied (scanner currently passes 0 → skip).
- HF Moralis scanner remains a disabled stub (Manus’s `.env.winning` wrongly set it true).
