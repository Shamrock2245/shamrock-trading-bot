# Winning v31 tuning notes (trade_history 31)

**Date:** 2026-07-22  
**Source:** `~/Downloads/trade_history (31).csv` + live Hetzner logs + Desktop HL screenshot

## Account (source of truth)

- Wallet `0xb867…6F8a` · Unified · **$1,735.58** Available to Trade  
- Flat at screenshot time; bot now reads the same balance

## Diagnosis (v31)

| Metric | Value |
|--------|------:|
| Close fills | 244 |
| Win rate | ~37% |
| Profit factor | ~0.68 |
| Net close PnL | **−$291** |
| Jul 21 (Winning day) | **+$15.71**, WR ~52% |
| Multi-hour losers | still largest $ leak |
| Soft toxic only | KAITO/APE still **EXECUTING** live |

## Ops fix (ghost positions)

Closed fills left **local** positions that filled `max_positions` and blocked new entries while exchange was flat. Winning timeout spam → 429s.

**Fix (wired):** purge ghosts when close fails but exchange is flat; periodic `_sync_positions` in trailing monitor.

## Strategy tuning (this pass)

| Change | Value |
|--------|--------|
| `HL_PERPS_HARD_BAN_COINS` | KAITO,APE,HEMI,ONDO,GRASS,TRB,HMSTR,FARTCOIN,MET,EIGEN,MORPHO,LIT,HYPE,BRETT,POPCAT,MEME,JTO |
| `HL_PERPS_TOXIC_COINS` | AAVE only (score+20; net winner, not hard-banned) |
| `HL_PERPS_MAX_NEW_PER_SCAN` | **3** (stop 6–9 spray opens) |
| `WINNING_LOSS_TIMEOUT_HOURS` | **1.5** |

## Verify

```bash
docker logs shamrock-bot 2>&1 | grep -E "HARD-BANNED|Entry cap|GHOST PURGE|synced .* open|balance=\$|EXECUTING.*KAITO|EXECUTING.*APE"
```

Expect: no KAITO/APE EXECUTING; entry cap logs; balance ~$1735; no ghost spam.

## Not claimed

- PF will not magically hit 1.5 in one day — need 3–7 days clean sample.
