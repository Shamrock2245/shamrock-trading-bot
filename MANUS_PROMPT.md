# Manus Task: Fix Solana Transaction Signing & Verify Live Trading

## Context
Read `CURRENT_STATUS.md` first — it has the full pipeline status and all recent fixes.

The Shamrock Trading Bot's entire pipeline is working **except the final step**: Solana transaction signing. The bot successfully:
1. Scans 146+ tokens across 4 chains (Solana, Base, BSC, Avalanche)
2. Scores gems using a 14-signal pipeline + enrichment (Moralis, Grok, HolderAnalysis, etc.)
3. Generates composite scores of 80-86 for promising micro-caps
4. Routes trades through the wallet router with phase-based position sizing
5. Gets Jupiter quotes (tested: 302.5B tokens for 0.452 SOL at 0.01% price impact)

**Then it fails** at `core/solana_executor.py` line ~154 with:
```
'solders.transaction.VersionedTransaction' object has no attribute 'sign'
```

## Your Task

### P0: Fix the Solana Transaction Signing
The `solders` library is version **0.27.1**. `VersionedTransaction` deserialized from bytes is immutable — no `.sign()` method.

I attempted this fix but couldn't verify (scan cycles take ~5 min):
```python
# OLD (broken):
tx = VersionedTransaction.from_bytes(tx_bytes)
tx.sign([keypair])  # ← AttributeError

# NEW (deployed but unverified):
tx = VersionedTransaction.from_bytes(tx_bytes)
signed_tx = VersionedTransaction(tx.message, [keypair])
```

**If that doesn't work**, the correct solders 0.27 pattern may be:
```python
from solders.signature import Signature
msg_bytes = bytes(tx.message)
sig = keypair.sign_message(msg_bytes)
signed_tx = VersionedTransaction.populate(tx.message, [sig])
```

**Test this by**:
1. SSH to Hetzner: `ssh -i ~/.ssh/id_ed25519 root@5.161.126.32`
2. Check latest logs: `docker logs shamrock-bot --tail 50`
3. If signing still fails, fix `core/solana_executor.py`, rebuild: `cd /root/shamrock-trading-bot && docker compose build bot && docker compose up -d --no-deps bot`
4. Wait for next cycle (~5 min) and verify a trade executes

### P1: Clean Up Debug Logging
`core/wallet_router.py` has temporary `logger.info()` debug lines. Convert them to `logger.debug()`:
- Lines with `Routing ... trade`
- Lines with `Evaluating ... for`
- Lines with `balance=` and `native_price=`
- Lines with `phase=` and `pos_size=`

### P2: Review Position Sizing
Current math for Solana: `$413 balance × 25% max × 0.40 conviction = $41 per trade`.
- Is 25% seed phase max appropriate?
- Is 0.40 conviction multiplier for gems scoring 50-70 too conservative?
- The Solana min trade is $1 — should it be higher?

### P3: Verify EVM Chain Support
Base, BSC, and Avalanche are in ACTIVE_CHAINS but have no funded wallets yet. Verify the EVM executor path (`core/evm_executor.py`) is ready for when wallets are funded.

## Key Files
| File | What to focus on |
|------|-----------------|
| `core/solana_executor.py` | **P0** — Fix `sign_and_send_transaction()` function |
| `core/wallet_router.py` | P1 — Clean debug logs; P2 — Review position sizing |
| `CURRENT_STATUS.md` | Full context on fixes and architecture |
| `config/settings.py` | All thresholds and env var defaults |

## Hetzner Access
- SSH: `ssh -i ~/.ssh/id_ed25519 root@5.161.126.32`
- Bot directory: `/root/shamrock-trading-bot`
- Rebuild: `docker compose build bot && docker compose up -d --no-deps bot`
- Logs: `docker logs shamrock-bot --tail 100`
- Mode: **LIVE** (real trades with real SOL)

## Success Criteria
- [ ] A Solana trade executes successfully (tx signature appears in logs)
- [ ] Debug logging cleaned up
- [ ] Position sizing reviewed and documented
- [ ] Changes committed and pushed to GitHub
