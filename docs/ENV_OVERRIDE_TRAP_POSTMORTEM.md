# Post-Mortem: The `.env` Override Trap — Why the Bot Stopped Trading
**Date:** July 14–15, 2026  
**Impact:** ~23 hours of zero trading activity  
**Root Cause:** Stale `.env` values on Hetzner silently overriding all code-level gate fixes  
**Status:** ✅ Fixed and prevention mechanism deployed

---

## What Happened

Over the course of three debugging sessions (July 6–14), Manus and Brendan fixed a series of critical bugs:

1. **SL placement failures** causing 49 rapid closes in under 10 seconds
2. **Stacked entry gates** (EXEC_SCORE=65, MIN_RR=1.5, LONG_ONLY=true, REENTRY=30min) suppressing trade volume to near zero
3. **Scanner/executor MIN_RR mismatch** causing 5–6 second closes post-fix
4. **Auto-blacklist** to prevent re-entry into confirmed toxic coins

All fixes were committed to `main`, CI passed, and Docker rebuilt successfully. But the bot **still wasn't trading** after each deploy.

**The reason:** The Hetzner server's `.env` file was created by copying `.env.example` at initial setup. Every `docker compose up` reads `.env` first — and those values override the code defaults. The `.env.example` had never been updated to reflect any of the fixes, so the live bot was running with:

| Variable | `.env` on Hetzner | Correct Value | Effect of Wrong Value |
|---|---|---|---|
| `HL_PERPS_EXEC_SCORE` | `65` | `58` | Only ~5% of signals pass — near-zero trades |
| `HL_PERPS_MIN_RR` | `1.5` | `1.1` | Post-fill R/R check rejects valid trades → 5–6s closes |
| `HL_PERPS_LONG_ONLY` | `true` | `false` | Shorts completely disabled — 50% of opportunity gone |
| `HL_PERPS_REENTRY_COOLDOWN_MIN` | `30` | `5` | Same coin blocked 30 min after every close |
| `HL_PERPS_LOSS_COOLDOWN_MIN` | `30` | `10` | Same coin blocked 30 min after every loss |
| `HL_PERPS_EMERGENCY_COOLDOWN_MIN` | `240` | `60` | 4-hour blackout after any SL placement failure |
| `HYPERLIQUID_MAX_POSITIONS` | `6` | `10` | Hard ceiling on concurrent trades |

The combined effect of all seven wrong values was a bot that could theoretically pass lint, preflight, and Docker startup checks — but would find zero tradeable signals in practice.

---

## Why This Is Particularly Dangerous

This class of bug is hard to detect because:

- **CI passes green** — lint, preflight, and Docker build all succeed
- **The bot starts without errors** — no crash, no exception, no alert
- **Logs look normal** — scan cycles run every 2 minutes, the loop is alive
- **The only symptom is silence** — no `SIGNAL — EXECUTING` lines, just `no setups passed gate this cycle` repeated indefinitely

A developer looking at the logs would assume the market just isn't producing signals. In reality, the gate threshold is set so high that no real market condition can ever satisfy it.

---

## The Fix

### 1. CI Deploy Script Now Patches `.env` on Every Deploy

`ci.yml` now runs a `sed` patch block immediately after `git pull` and before `docker compose down`:

```bash
# ── Patch .env with tuned gate values ──
sed -i 's/^HL_PERPS_EXEC_SCORE=.*/HL_PERPS_EXEC_SCORE=58/' .env
sed -i 's/^HL_PERPS_MIN_RR=.*/HL_PERPS_MIN_RR=1.1/' .env
sed -i 's/^HL_PERPS_LONG_ONLY=.*/HL_PERPS_LONG_ONLY=false/' .env
sed -i 's/^HL_PERPS_REENTRY_COOLDOWN_MIN=.*/HL_PERPS_REENTRY_COOLDOWN_MIN=5/' .env
sed -i 's/^HL_PERPS_LOSS_COOLDOWN_MIN=.*/HL_PERPS_LOSS_COOLDOWN_MIN=10/' .env
sed -i 's/^HL_PERPS_EMERGENCY_COOLDOWN_MIN=.*/HL_PERPS_EMERGENCY_COOLDOWN_MIN=60/' .env
sed -i 's/^HYPERLIQUID_MAX_POSITIONS=.*/HYPERLIQUID_MAX_POSITIONS=10/' .env
```

This means **even if the `.env` on Hetzner is manually edited or reset**, the next CI deploy will correct it automatically.

### 2. `.env.example` Updated to Reflect All Tuned Values

The template file now contains the correct production values with inline comments explaining why each value was chosen. Future server setups will start with the right configuration.

### 3. Auto-Blacklist Vars Injected If Missing

The CI script also appends the four `HL_PERPS_AUTOBAN_*` variables to `.env` if they are not already present, ensuring the dynamic toxic-coin blacklist is always active.

---

## Prevention Checklist for Future Gate Changes

Whenever a gate threshold is changed in code, **all three of these must be updated**:

- [ ] The code default in `core/hl_perps_scanner.py` or `core/hyperliquid_executor.py`
- [ ] The `.env.example` template value
- [ ] The `sed -i` patch line in `.github/workflows/ci.yml`

If any one of these is missed, the Hetzner `.env` will silently override the fix on the next deploy.

---

## How to Diagnose This in the Future

If the bot is running but not trading, run this diagnostic checklist **before** looking at signal quality:

### Step 1 — Check what the bot is actually using

```bash
# SSH into Hetzner
ssh -i ~/.shamrock_deploy_key root@46.62.231.43

# Print the live env vars the bot sees
docker compose exec bot env | grep -E "HL_PERPS|HYPERLIQUID" | sort
```

Compare the output against the table in this document. Any value that doesn't match is the culprit.

### Step 2 — Check the scan cycle logs for gate rejection reasons

```bash
docker compose logs bot --tail=200 | grep -E "NEAR MISS|score=|gate|cooldown|banned|LONG_ONLY|circuit"
```

**What each log line means:**

| Log Pattern | Meaning |
|---|---|
| `NEAR MISS: score=54 < 58` | EXEC_SCORE is correct but signals are borderline — consider lowering to 55 |
| `NEAR MISS: score=54 < 65` | EXEC_SCORE is still at 65 — `.env` patch didn't apply |
| `SHORT blocked — HL_PERPS_LONG_ONLY=true` | LONG_ONLY is still true — `.env` patch didn't apply |
| `[AUTO-BAN] COIN banned for Xh` | Auto-blacklist is working — this is expected for toxic coins |
| `🛑 CIRCUIT BREAKER: daily PnL` | Daily loss limit hit — check `HYPERLIQUID_DAILY_LOSS_LIMIT` |
| `max positions (6) reached` | MAX_POSITIONS is still 6 — `.env` patch didn't apply |
| `Re-entry throttle activated` | Normal cooldown — check if cooldown duration is correct |

### Step 3 — Force-apply the env patch manually if CI isn't running

```bash
cd /root/shamrock-trading-bot
sed -i 's/^HL_PERPS_EXEC_SCORE=.*/HL_PERPS_EXEC_SCORE=58/' .env
sed -i 's/^HL_PERPS_MIN_RR=.*/HL_PERPS_MIN_RR=1.1/' .env
sed -i 's/^HL_PERPS_LONG_ONLY=.*/HL_PERPS_LONG_ONLY=false/' .env
sed -i 's/^HL_PERPS_REENTRY_COOLDOWN_MIN=.*/HL_PERPS_REENTRY_COOLDOWN_MIN=5/' .env
sed -i 's/^HL_PERPS_LOSS_COOLDOWN_MIN=.*/HL_PERPS_LOSS_COOLDOWN_MIN=10/' .env
sed -i 's/^HL_PERPS_EMERGENCY_COOLDOWN_MIN=.*/HL_PERPS_EMERGENCY_COOLDOWN_MIN=60/' .env
sed -i 's/^HYPERLIQUID_MAX_POSITIONS=.*/HYPERLIQUID_MAX_POSITIONS=10/' .env
docker compose restart bot
docker compose logs bot --tail=30
```

---

## Current Correct Gate Values (as of July 15, 2026)

| Variable | Value | Rationale |
|---|---|---|
| `HL_PERPS_EXEC_SCORE` | `58` | Lowered from 65 — real setups score 50–62; 65 was blocking ~95% of valid signals |
| `HL_PERPS_MIN_RR` | `1.1` | Lowered from 1.5 — must match executor post-fill R/R check or causes 5–6s closes |
| `HL_PERPS_LONG_ONLY` | `false` | Shorts re-enabled with RSI veto guard (RSI > 65 required for shorts) |
| `HL_PERPS_REENTRY_COOLDOWN_MIN` | `5` | RSI veto is the quality gate — 5 min is enough to prevent micro-churn |
| `HL_PERPS_LOSS_COOLDOWN_MIN` | `10` | Auto-blacklist handles persistent losers; 10 min prevents immediate re-entry |
| `HL_PERPS_EMERGENCY_COOLDOWN_MIN` | `60` | 240 min was too punishing for SL placement failures on illiquid coins |
| `HYPERLIQUID_MAX_POSITIONS` | `10` | Increased from 6 to allow more concurrent positions |
| `HYPERLIQUID_DEFAULT_LEVERAGE` | `3` | Reduced from 7 — lower leverage, more sustainable compounding |
| `HYPERLIQUID_STOP_LOSS_PCT` | `2.5` | Tightened from 3.5 — limits loss per trade |
| `HL_PERPS_AUTOBAN_ENABLED` | `true` | Dynamic blacklist — bans coins with < 30% WR after 5 trades for 48h |
| `HL_PERPS_AUTOBAN_WR_THRESHOLD` | `0.30` | Coins below 30% WR are auto-banned |
| `HL_PERPS_AUTOBAN_MIN_TRADES` | `5` | Minimum sample size before ban eligibility |
| `HL_PERPS_AUTOBAN_HOURS` | `48.0` | Ban duration — 48h gives the market time to change character |

---

## Related Documents

- `docs/HL_PERPS_RAPID_CLOSE_POSTMORTEM.md` — Root cause analysis of the 49 rapid closes
- `docs/CHANGELOG.md` — Full version history of all fixes
- `docs/RUNBOOK.md` — Operational runbook for the Hetzner deployment
