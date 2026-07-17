# Shamrock Trading Bot — Grok Briefing & Tuning Prompt
**Date:** July 15, 2026  
**Prepared by:** Manus (Antigravity)  
**Purpose:** Bring Grok up to speed on the full system state, all fixes applied to date, and prime Grok to analyze a new trade history CSV and tune the bot.

---

## Your Role

You are being brought in as a trading strategy tuning agent for the **Shamrock Trading Bot** — an autonomous, multi-strategy algorithmic trading engine deployed on a Hetzner VPS via Docker. Your job is to:

1. Understand the current system state (read this document fully)
2. Analyze the trade history CSV that Brendan will share with you
3. Recommend and implement specific, targeted code or `.env` changes to improve win rate, trade frequency, and daily PnL
4. Follow the **Three-File Update Rule** (explained below) for every change

---

## System Overview

**Primary Strategy:** Hyperliquid L2 Perpetual Futures (HL Perps)  
**Execution:** Python bot running in Docker on Hetzner server `46.62.231.43`  
**Deployment:** Every push to `main` on GitHub triggers a CI/CD pipeline (GitHub Actions) that SSHs into Hetzner, patches `.env`, rebuilds Docker, and restarts the bot  
**Repository:** `https://github.com/Shamrock2245/shamrock-trading-bot`  
**Capital:** ~$667 live equity on Hyperliquid L2 clearinghouse  
**Leverage:** 3x (reduced from 7x after catastrophic losses)  
**Goal:** Compound to $500/day profit → auto-sweep to Arbitrum L1 wallet

---

## Architecture: How the Bot Trades

### Entry Pipeline (29-indicator convergence gate)
1. **`core/hl_perps_scanner.py`** — scans up to 150 coins per cycle (every 2 min)
2. Each coin is scored 0–100 across: RSI, EMA cross, MACD, volume, Bollinger Bands, Fibonacci retracement, OI, funding rate, macro trend (1D), and ECC wave analysis
3. Signal must score ≥ `HL_PERPS_EXEC_SCORE` (currently **58**) to execute
4. RSI veto is **sticky**: RSI < 35 for longs or RSI > 65 for shorts sets score to 0.0 and no downstream indicator can recover it
5. Fib proximity gate: price must be within 2% of a key Fibonacci level (0.382, 0.5, 0.618, 0.786) to get the Fib boost

### Execution & Risk Management
- **`core/hyperliquid_executor.py`** — places market order, then immediately attaches on-chain TP and SL
- SL retry backoff: 3 attempts (1s, 2s delay) before RED TEAM GUARD fires a market close
- Post-fill R:R check: if actual R:R < `HL_PERPS_MIN_RR` (1.1x), position is immediately closed
- Trailing stop: activates at `HL_TRAILING_ROE_TRIGGER_PCT` (10% ROE), tightens step-function at 20% and 50% ROE

### Profit Extraction
- Auto-sweeper: for every $500 earned over the $150 baseline, the exact $500 is withdrawn to the Arbitrum L1 paycheck wallet

---

## Complete Fix History (June–July 2026)

### v2.1.1 — July 6, 2026 (SL Placement Fix)
**Problem:** 49 trades closed in under 10 seconds with avg PnL of -$0.33. The bot was opening positions and immediately closing them.

**Root cause A (sub-2s closes):** Hyperliquid API rejected SL orders with `"Order price cannot be more than 95% away from the reference price"` on illiquid altcoins. The old code used a 50% slippage buffer for the SL limit price, which exceeded HL's 95% deviation cap. RED TEAM GUARD fired immediately.

**Fix:** `_place_tpsl()` in `hyperliquid_executor.py` now retries SL placement 3 times with exponential backoff (1s, 2s). Attempt 1 uses 50% slippage; attempts 2–3 fall back to 10% slippage which HL accepts on illiquid coins.

**Other fixes in this commit:**
- RSI veto made sticky (downstream indicators cannot add points back after veto)
- Balance key mismatch fixed: scanner was using `accountValue` (camelCase HL API key) instead of `account_value` (executor's normalized key), causing Kelly sizing to fall back to $150 base capital instead of live equity
- Aggressive Mode `.env` block deleted (restored safe defaults)

---

### v2.2.0 — July 13, 2026 (Trade Volume Fix)
**Problem:** Bot was generating only 2–5 trades/day. Analysis of the entry gate stack revealed 10 bottlenecks stacking on top of each other.

**Fixes applied:**

| Variable | Old | New | Reason |
|---|---|---|---|
| `HL_PERPS_EXEC_SCORE` | 65 | **58** | Real setups score 50–62; 65 was blocking ~95% of valid signals |
| `HL_PERPS_MIN_RR` | 1.5 | **1.1** | Fib-computed TP/SL rarely hits 1.5x on tight SL |
| `HL_PERPS_LONG_ONLY` | true | **false** | Shorts re-enabled with RSI veto guard |
| `HL_PERPS_REENTRY_COOLDOWN_MIN` | 30 | **5** | RSI veto is the quality gate |
| `HL_PERPS_LOSS_COOLDOWN_MIN` | 30 | **10** | Auto-blacklist handles persistent losers |
| `HL_PERPS_EMERGENCY_COOLDOWN_MIN` | 240 | **60** | 4h was too punishing for SL placement failures |
| `HYPERLIQUID_MAX_POSITIONS` | 6 | **10** | Hard ceiling was limiting concurrent trades |
| RSI dead zones | 0 pts for RSI 35–40, 60–65 | **Proportional scoring** | Healthy trending coins (RSI 62) were scoring 0 RSI points |
| Fib proximity | 1% | **2%** | Too tight on illiquid coins |
| Retracement sniper | 1hr parking delay | **Removed** | Was parking valid signals for up to 1 hour |

---

### v2.3.0 — July 13, 2026 (CI Disk Fix)
**Problem:** CI deploy failed with `no space left on device` during Docker build.  
**Fix:** CI now runs `docker system prune -af --volumes && docker builder prune -af` before every build.

---

### v2.4.0 — July 14, 2026 (Scanner/Executor R:R Mismatch)
**Problem:** 5–6 second closes appearing in trade history after v2.2 deploy.

**Root cause B (5–6s closes):** The scanner pre-approved signals at R:R = 1.1–1.4x using its `HL_PERPS_MIN_RR` default of `1.1`. But the executor had a **separate, stale default of `1.5`**. The post-fill R:R guard in the executor rejected those same signals, triggering `market_close` 5–6 seconds after open.

**Fix:** Synced executor `HL_PERPS_MIN_RR` default from `1.5` → `1.1`. Also synced emergency cooldown default from 240 → 60 min.

---

### v2.5.0 — July 14, 2026 (Auto-Blacklist)
**Problem:** Toxic coins (AAVE 9% WR, HMSTR 0%, BRETT 8%, GRASS 20%, EIGEN 20%, MET 20%, MEME 0%) were consuming entry slots and generating consistent losses.

**Fix:** Dynamic performance-based auto-blacklist:
- Per-coin win/loss stats tracked in `data/dashboard/hl_coin_perf.json` (persisted across restarts)
- Any coin with ≥ 5 trades and WR < 30% is automatically banned for 48 hours
- Ban check is gate #0 in `_is_on_cooldown()` — banned coins never reach signal scoring
- Seed script pre-populated the 7 confirmed toxic coins immediately

**New env vars:** `HL_PERPS_AUTOBAN_ENABLED=true`, `HL_PERPS_AUTOBAN_MIN_TRADES=5`, `HL_PERPS_AUTOBAN_WR_THRESHOLD=0.30`, `HL_PERPS_AUTOBAN_HOURS=48.0`

---

### v2.6.0 — July 15, 2026 (The `.env` Override Trap — Critical)
**Problem:** Bot stopped trading entirely for ~23 hours despite all fixes being deployed.

**Root cause:** The Hetzner `.env` file was copied from `.env.example` at initial server setup and **never updated**. Every `docker compose up` reads `.env` first, and those values override code defaults. The `.env` had all the old aggressive values: `EXEC_SCORE=65`, `MIN_RR=1.5`, `LONG_ONLY=true`, `REENTRY=30min`, etc. — completely undoing every fix from v2.1–v2.5.

**Why it's dangerous:** The bot starts without errors, scans on schedule, logs normally — it just never finds a signal that passes the gate. No crash, no alert, no obvious symptom.

**Fix:** CI deploy script now patches `.env` via `sed` on every deploy before `docker compose down`, guaranteeing correct values regardless of what is in the file.

**The Three-File Update Rule** (MUST follow for every gate change):
1. Code default in `core/hl_perps_scanner.py` or `core/hyperliquid_executor.py`
2. `.env.example` template value (with inline comment)
3. `sed -i` patch line in `.github/workflows/ci.yml`

---

## Current Live Configuration (July 17, 2026 — v2.7.0)

| Variable | Value | Notes |
|---|---|---|
| `HL_PERPS_EXEC_SCORE` | `55` | Entry threshold (was 58; goal-adaptive floor 52) |
| `HL_PERPS_MIN_RR` | `1.2` | Must match in both scanner AND executor |
| `HL_PERPS_LONG_ONLY` | `true` | Shorts ~17% WR — stay off until edge proven |
| `HL_PERPS_REENTRY_COOLDOWN_MIN` | `8` | Per-coin re-entry throttle |
| `HL_PERPS_LOSS_COOLDOWN_MIN` | `10` | Post-loss cooldown |
| `HL_PERPS_EMERGENCY_COOLDOWN_MIN` | `60` | Post-SL-failure cooldown |
| `HYPERLIQUID_MAX_POSITIONS` | `10` | Max concurrent positions |
| `HL_PERPS_MAX_POSITIONS` | `10` | Scanner-side slot cap |
| `HYPERLIQUID_DEFAULT_LEVERAGE` | `3` | Reduced from 7 — never raise |
| `HYPERLIQUID_STOP_LOSS_PCT` | `2.5` | Per-trade SL |
| `HYPERLIQUID_TAKE_PROFIT_PCT` | `12.0` | Executor fallback TP |
| `HYPERLIQUID_DAILY_LOSS_LIMIT` | `100.0` | Circuit breaker floor |
| `HL_PERPS_TOXIC_COINS` | AAVE…TRB,**HYPE** | Higher score bar for known losers |
| `HL_PERPS_AUTOBAN_ENABLED` | `true` | Dynamic coin blacklist |
| `HL_PERPS_AUTOBAN_WR_THRESHOLD` | `0.30` | Ban if WR < 30% |
| `HL_PERPS_AUTOBAN_MIN_TRADES` | `5` | Min sample before ban |
| `HL_PERPS_AUTOBAN_HOURS` | `48.0` | Ban duration |
| `HL_TRAILING_ROE_TRIGGER_PCT` | `10.0` | Trailing stop activation |
| `HL_TRAILING_DISTANCE_PCT` | `1.0` | Default trail distance |

---

## Trade Performance Summary (as of July 15, 2026)

| Period | Trades | Net PnL | Win Rate | Avg Win | Avg Loss | R:R | Rapid Closes |
|---|---|---|---|---|---|---|---|
| Pre-fix (Jun 16 – Jul 12) | 163 | -$302 | 35.0% | +$7.62 | -$6.95 | 1.10x | 48 |
| Post-fix-2 (Jul 13–14) | 14 | **+$28.66** | 42.9% | +$8.22 | **-$2.58** | **3.18x** | 1 |
| Last 48h | 13 | **+$31.62** | 46.2% | — | — | — | 0 |

The -$302 pre-fix figure is dominated by two catastrophic oversized positions (TRB -$195, GRASS -$166) from the old 7x leverage config — not signal quality failures. The underlying signal engine was roughly breakeven before those events.

**Current trajectory:** Positive. Rapid closes eliminated, losses shrinking, R:R improving.

**Remaining gap:** Trade volume is ~6.5/day, target is 15–25/day. The `.env` override fix only deployed hours before this briefing was written — the next trade history CSV will show whether volume has improved.

---

## Your Task: Analyze the New Trade History and Tune the Bot

Brendan will now share a new trade history CSV with you. When you receive it:

### Step 1 — Parse and analyze
- Count total trades, trades/day rate, win rate, avg win, avg loss, R:R
- Check for any remaining rapid closes (< 10s hold time)
- Break down performance by coin — identify any new toxic coins (≥ 5 trades, WR < 30%)
- Compare daily PnL trend — is it improving?
- Check long vs short performance separately

### Step 2 — Identify the biggest bottleneck
Focus on whichever of these is the primary issue:
- **Too few trades:** Lower `HL_PERPS_EXEC_SCORE` (try 55), check if cooldowns are still too long
- **Win rate < 40%:** Raise `HL_PERPS_EXEC_SCORE` (try 62), check if toxic coins are still trading
- **Large individual losses:** Check if position sizing is correct (should be ~$300 notional at current equity)
- **Rapid closes still appearing:** Check if `HL_PERPS_MIN_RR` is still mismatched between scanner and executor

### Step 3 — Recommend specific changes
For each change, specify:
1. The exact variable name and new value
2. Which file(s) need updating (remember the Three-File Update Rule)
3. The rationale based on the data

### Step 4 — Implement and commit
- Edit the relevant files in the repo
- Follow the Three-File Update Rule for every gate change
- Commit with a descriptive message: `fix: [description] based on trade history analysis`
- Push to `main` — CI will automatically deploy to Hetzner

---

## Key Files to Know

| File | Purpose |
|---|---|
| `core/hl_perps_scanner.py` | Signal scoring, entry gates, auto-blacklist, coin universe |
| `core/hyperliquid_executor.py` | Order execution, SL/TP placement, trailing stop, position management |
| `main.py` | Main loop, trailing stop monitor, profit sweeper |
| `.env.example` | Template for Hetzner `.env` — must be kept in sync |
| `.github/workflows/ci.yml` | CI/CD pipeline — includes `.env` patch block |
| `data/dashboard/hl_coin_perf.json` | Auto-blacklist state (persisted across restarts) |
| `docs/HL_PERPS_RUNBOOK.md` | Operational runbook — diagnostic procedures |
| `docs/ENV_OVERRIDE_TRAP_POSTMORTEM.md` | The `.env` override trap post-mortem |
| `docs/CHANGELOG.md` | Full version history |

---

## Critical Rules (Do Not Violate)

1. **Three-File Update Rule:** Every gate change must update code default + `.env.example` + `ci.yml` sed patch simultaneously
2. **Never remove the SL retry backoff** — it prevents the 49-rapid-close pattern
3. **Never remove the RSI sticky veto** — it prevents catching falling knives
4. **Never set `HYPERLIQUID_DEFAULT_LEVERAGE` above 3** — 7x caused -$248 in a single day
5. **Never set `HL_PERPS_EXEC_SCORE` below 52** — below this, noise trades outweigh signal trades
6. **`HL_PERPS_MIN_RR` must be identical in both scanner and executor** — mismatch causes 5–6s closes
7. **Always run `python3 -m py_compile core/hl_perps_scanner.py core/hyperliquid_executor.py` before committing**
