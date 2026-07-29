# HL Perps Engine — Operational Runbook
**Last Updated:** July 29, 2026  
**Covers:** Hyperliquid perpetuals scanner, executor, trailing stop monitor, auto-blacklist  
**Server:** Hetzner `46.62.231.43` — Docker Compose, container `shamrock-bot`

---

## Quick Reference — SSH + Log Commands

```bash
# SSH into Hetzner
ssh -i ~/.shamrock_deploy_key root@46.62.231.43

# Tail live bot logs
docker compose logs bot -f --tail=50

# Check container status
docker compose ps

# Restart bot only (no rebuild)
docker compose restart bot

# Full rebuild + restart
cd /root/shamrock-trading-bot && git pull origin main && docker compose build --no-cache && docker compose up -d
```

---

## Symptom: Bot Is Running But Not Trading

This is the most dangerous silent failure mode. The bot starts cleanly, scans every 2 minutes, and logs `no setups passed gate this cycle` — but never executes a trade.

### Step 1 — Verify the live env vars

```bash
docker compose exec bot env | grep -E "HL_PERPS|HYPERLIQUID" | sort
```

Compare against the **Current Correct Values** table at the bottom of this document. Any mismatch is the culprit.

### Step 2 — Read the scan cycle logs for gate rejection reasons

```bash
docker compose logs bot --tail=200 | grep -E "NEAR MISS|score=|gate|cooldown|banned|LONG_ONLY|circuit|CIRCUIT"
```

| Log Pattern | Diagnosis | Fix |
|---|---|---|
| `NEAR MISS: score=54 < 65` | EXEC_SCORE is still 65 | `.env` patch didn't apply — see Step 3 |
| `NEAR MISS: score=54 < 58` | Signals are borderline | Lower `HL_PERPS_EXEC_SCORE` to 55 in `.env` |
| `SHORT blocked — HL_PERPS_LONG_ONLY=true` | LONG_ONLY still true | Set `HL_PERPS_LONG_ONLY=false` in `.env` |
| `max positions (6) reached` | MAX_POSITIONS still 6 | Check position capacity or purge ghosts |
| `[AUTO-BAN] COIN banned for Xh` | Auto-blacklist working | Expected — check if too many coins are banned |
| `🛑 CIRCUIT BREAKER: daily PnL` | Daily loss limit hit | Check `HYPERLIQUID_DAILY_LOSS_LIMIT` — resets at midnight UTC |
| `Re-entry throttle activated` | Normal cooldown | Check cooldown duration — should be 5 min |
| `Emergency cooldown activated` | SL placement failed | Check `HL_PERPS_EMERGENCY_COOLDOWN_MIN` — should be 60 min |

### Step 3 — Force-apply the env patch manually

If CI hasn't run recently or the `.env` is stale:

```bash
cd /root/shamrock-trading-bot
sed -i 's/^HL_PERPS_EXEC_SCORE=.*/HL_PERPS_EXEC_SCORE=58/' .env
sed -i 's/^HL_PERPS_MIN_RR=.*/HL_PERPS_MIN_RR=1.1/' .env
sed -i 's/^HL_PERPS_LONG_ONLY=.*/HL_PERPS_LONG_ONLY=false/' .env
sed -i 's/^HL_PERPS_REENTRY_COOLDOWN_MIN=.*/HL_PERPS_REENTRY_COOLDOWN_MIN=5/' .env
sed -i 's/^HL_PERPS_LOSS_COOLDOWN_MIN=.*/HL_PERPS_LOSS_COOLDOWN_MIN=10/' .env
sed -i 's/^HL_PERPS_EMERGENCY_COOLDOWN_MIN=.*/HL_PERPS_EMERGENCY_COOLDOWN_MIN=60/' .env
sed -i 's/^HYPERLIQUID_MAX_POSITIONS=.*/HYPERLIQUID_MAX_POSITIONS=6/' .env
sed -i 's/^HL_PERPS_MAX_POSITIONS=.*/HL_PERPS_MAX_POSITIONS=6/' .env
sed -i 's/^HL_PERPS_BLOCKED_HOURS_ET=.*/HL_PERPS_BLOCKED_HOURS_ET=/' .env
sed -i 's/^HL_PERPS_HARD_BAN_COINS=.*/HL_PERPS_HARD_BAN_COINS=GRASS,TRB,HMSTR,FARTCOIN/' .env
docker compose restart bot && docker compose logs bot --tail=30
```

### Step 4 — Check the auto-blacklist state

```bash
cat /root/shamrock-trading-bot/data/dashboard/hl_coin_perf.json | python3 -c "
import json, sys, time
data = json.load(sys.stdin)
bans = data.get('autoban_until', {})
now = time.time()
active = {k: f'{(v-now)/3600:.1f}h remaining' for k,v in bans.items() if v > now}
print(f'Active bans ({len(active)}): {active}')
perf = data.get('coin_perf', {})
print(f'Tracked coins: {len(perf)}')
"
```

If too many coins are banned and the watchlist is exhausted, reduce `HL_PERPS_AUTOBAN_HOURS` to 24 or temporarily set `HL_PERPS_AUTOBAN_ENABLED=false` in `.env` and restart.

---

## Symptom: Rapid Closes (< 10 seconds after open)

### Known Causes

**Cause A — SL size precision / OID mismatch (sub-2s closes):**  
HL API rejects the SL order with `Invalid order size` when un-rounded float size is passed. Handled & fixed by `szDecimals` rounding in `_place_tpsl` and live `user_state` position size querying in `_open_position`.

**Cause B — Scanner/executor MIN_RR mismatch (5–6s closes):**  
Scanner pre-approves a signal at R/R = 1.1–1.4x while executor checked against a higher threshold. Fixed by syncing both to `HL_PERPS_MIN_RR=1.1`.

**Diagnosis:**
```bash
docker compose logs bot --tail=200 | grep -E "RED TEAM GUARD|R/R|r_r_ratio|post-fill|market_close"
```

**If you see `RED TEAM GUARD: SL placement FAILED` after 3 attempts:**  
The coin is genuinely illiquid. Add it to `HL_PERPS_TOXIC_COINS` in `.env` and restart.

**If you see `post-fill R/R reject`:**  
`HL_PERPS_MIN_RR` in `.env` is higher than `1.1`. Apply the patch from Step 3 above.

---

## Symptom: Large Losses on a Single Coin

### Known Causes

- **Oversized position:** Old `.env` had `HYPERLIQUID_MAX_POSITION_USD=150` with 7x leverage = $1,050 notional. Now capped at 3x leverage with 15% equity margin limit.
- **Toxic coin not blacklisted:** Check `HL_PERPS_TOXIC_COINS` in `.env` and the auto-blacklist state.
- **LONG_ONLY=true during a bear market:** Shorts are now enabled. If win rate drops below 40%, check if the market is in a downtrend and consider temporarily setting `HL_PERPS_LONG_ONLY=true`.

### Emergency: Close All Positions Immediately

```bash
# From Hetzner server
docker compose exec bot python3 -c "
from core.hyperliquid_executor import HyperliquidExecutor
ex = HyperliquidExecutor()
for coin in list(ex.positions.keys()):
    print(f'Closing {coin}...')
    ex.close_position(coin)
    print(f'{coin} closed')
"
```

---

## Symptom: CI Deploy Failed

### Common Causes

| Error | Fix |
|---|---|
| `NameError: name '_STATE_DIR' is not defined` | Module-level constant defined before its dependency — check `hl_perps_scanner.py` line order |
| `write .../libtriton.so: no space left on device` | Disk full — CI now runs `docker system prune -af` before build, but if it happens again: SSH in and run `docker system prune -af --volumes` manually |
| `Process completed with exit code 1` in deploy | SSH into Hetzner and check if `.env` exists — bot won't start without it |
| `lint-and-test` fails | Syntax error in Python — run `python3 -m py_compile core/hl_perps_scanner.py core/hyperliquid_executor.py` locally |

---

## Symptom: Circuit Breaker Triggered

The circuit breaker halts all trading when daily PnL hits -33% of live equity (or `HYPERLIQUID_DAILY_LOSS_LIMIT`, whichever is larger).

```bash
# Check current daily PnL
docker compose logs bot --tail=100 | grep "daily_pnl"

# Check what triggered it
docker compose logs bot --tail=200 | grep "CIRCUIT BREAKER"
```

The circuit breaker resets automatically at midnight UTC. To reset manually:

```bash
docker compose restart bot
```

> **Warning:** Only restart if you have investigated and resolved the cause of the losses. Do not restart just to bypass the circuit breaker.

---

## Gate Tuning Reference

Use this table when deciding whether to tighten or loosen the entry gates.

| Symptom | Action | Variable | Direction |
|---|---|---|---|
| Bot not trading / very few trades | Loosen entry | `HL_PERPS_EXEC_SCORE` | Lower (e.g. 58 → 55) |
| Win rate < 35% after 50+ trades | Tighten entry | `HL_PERPS_EXEC_SCORE` | Raise (e.g. 58 → 62) |
| Same coin re-entered too quickly | Slow re-entry | `HL_PERPS_REENTRY_COOLDOWN_MIN` | Raise (e.g. 5 → 15) |
| Good coins blocked too long | Speed re-entry | `HL_PERPS_REENTRY_COOLDOWN_MIN` | Lower (e.g. 5 → 3) |
| 5–6s rapid closes appearing | Fix R/R mismatch | `HL_PERPS_MIN_RR` | Must match executor (1.1) |
| Toxic coins keep getting traded | Tighten blacklist | `HL_PERPS_AUTOBAN_WR_THRESHOLD` | Raise (e.g. 0.30 → 0.40) |
| Too many coins banned, no signals | Loosen blacklist | `HL_PERPS_AUTOBAN_HOURS` | Lower (e.g. 48 → 24) |
| Large losses per trade | Reduce leverage | `HYPERLIQUID_DEFAULT_LEVERAGE` | Lower (e.g. 3 → 2) |
| Small wins, need more upside | Widen TP | `HYPERLIQUID_TAKE_PROFIT_PCT` | Raise (e.g. 12 → 15) |

**After any `.env` change:**
```bash
docker compose restart bot && docker compose logs bot --tail=20
```
No rebuild needed — env vars are read at startup.

---

## Current Correct Gate Values (July 15, 2026)

| Variable | Value | Notes |
|---|---|---|
| `HL_PERPS_EXEC_SCORE` | `58` | Lowered from 65 — real setups score 50–62 |
| `HL_PERPS_MIN_RR` | `1.1` | Must match executor post-fill check — prevents 5–6s closes |
| `HL_PERPS_LONG_ONLY` | `false` | Shorts enabled with RSI veto guard |
| `HL_PERPS_REENTRY_COOLDOWN_MIN` | `5` | RSI veto is the quality gate |
| `HL_PERPS_LOSS_COOLDOWN_MIN` | `10` | Auto-blacklist handles persistent losers |
| `HL_PERPS_EMERGENCY_COOLDOWN_MIN` | `60` | Was 240 — too punishing for illiquid coin SL failures |
| `HYPERLIQUID_MAX_POSITIONS` | `10` | Was 6 |
| `HYPERLIQUID_DEFAULT_LEVERAGE` | `3` | Was 7 — reduced for safer compounding |
| `HYPERLIQUID_STOP_LOSS_PCT` | `2.5` | Was 3.5 |
| `HYPERLIQUID_TAKE_PROFIT_PCT` | `12.0` | Unchanged |
| `HYPERLIQUID_DAILY_LOSS_LIMIT` | `100.0` | Hard floor; dynamic limit is 33% of live equity |
| `HL_PERPS_AUTOBAN_ENABLED` | `true` | Dynamic performance-based blacklist |
| `HL_PERPS_AUTOBAN_MIN_TRADES` | `5` | Min sample before ban eligible |
| `HL_PERPS_AUTOBAN_WR_THRESHOLD` | `0.30` | Ban if WR < 30% |
| `HL_PERPS_AUTOBAN_HOURS` | `48.0` | Ban duration |
| `HL_TRAILING_ROE_TRIGGER_PCT` | `10.0` | Trailing stop activates at 10% ROE |
| `HL_TRAILING_DISTANCE_PCT` | `1.0` | Default trail distance (tightens at 20%/50% ROE) |

---

## Prevention Rule: The Three-File Update Rule

Whenever a gate threshold is changed, **all three of these must be updated simultaneously**:

1. **Code default** in `core/hl_perps_scanner.py` or `core/hyperliquid_executor.py`
2. **`.env.example`** template value (with inline comment explaining why)
3. **`sed -i` patch line** in `.github/workflows/ci.yml` deploy script

Missing any one of these means the Hetzner `.env` will silently override the fix on the next deploy.

---

## Related Documents

- `docs/ENV_OVERRIDE_TRAP_POSTMORTEM.md` — Full post-mortem on the `.env` override trap
- `docs/HL_PERPS_RAPID_CLOSE_POSTMORTEM.md` — Root cause analysis of the 49 rapid closes
- `docs/CHANGELOG.md` — Full version history
