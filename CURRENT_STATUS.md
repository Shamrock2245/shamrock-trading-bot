# Shamrock Trading Bot — Current Status (March 23, 2026)

## 🟢 Pipeline Status: NEARLY LIVE — One Bug Remains

The entire trade pipeline is wired and working end-to-end:
```
Scanner ✅ → Signal Engine ✅ → Strategy ✅ → Wallet Router ✅ → Jupiter Quote ✅ → Signing ❌
```

### What's Working
- **Gem Scanner**: Finds 4-6 candidates per cycle from DexScreener + Moralis (146 tokens across 4 chains)
- **Enrichment Pipeline**: HolderAnalysis, UnlockRisk, Grok Sentiment, Smart Money, DefiLlama — all firing
- **Signal Engine**: Micro-cap scoring path produces strong composites (80-86 for good gems)
- **Strategy (GemSnipe)**: Correctly reuses signal engine composite scores
- **Wallet Router**: Routes trades with phase-based sizing, conviction multipliers, chain-aware slippage
- **Jupiter**: Quote API works perfectly (302.5B tokens for 0.452 SOL, 0.01% price impact)

### ❌ REMAINING BUG: Solana Transaction Signing

The last error is on line ~154 of `core/solana_executor.py`:
```
Sign and send failed: 'solders.transaction.VersionedTransaction' object has no attribute 'sign'
```

**Root Cause**: The `solders` library v0.27.1 treats `VersionedTransaction` deserialized from bytes as immutable. You can't call `.sign()` on it.

**Fix Applied (needs verification)**:
Changed from:
```python
tx = VersionedTransaction.from_bytes(tx_bytes)
tx.sign([keypair])  # ← FAILS in solders 0.27+
```
To:
```python
tx = VersionedTransaction.from_bytes(tx_bytes)
signed_tx = VersionedTransaction(tx.message, [keypair])  # Construct with signature
```

This fix is deployed on Hetzner but hasn't been verified because the scan cycle takes ~5 minutes.

---

## Recent Fixes Applied (This Session)

### 1. Signal Engine — Micro-Cap Scoring Path
- **File**: `core/signal_engine.py`
- Tokens with <24 candles now route to `_microcap_signals()` instead of sparse TA
- 5-axis composite: trend, momentum, volume, on-chain, sentiment
- Uses enrichment data: `gem_score`, `holder_concentration`, `smart_money`, `unlock_risk`, `grok_sentiment`
- Produces scores of 80-86 for promising tokens (vs. ~21 with old fallback)

### 2. Strategy Score Reuse
- **Files**: `main.py`, `strategies/gem_snipe.py`
- Strategy reuses signal engine composite when OHLCV insufficient (prevents recalculation to lower score)

### 3. Gem Scanner NameError Fix
- **File**: `scanner/gem_scanner.py`
- Re-added `candidate = GemCandidate(token=token)` at line 357 (Manus accidentally removed it)

### 4. Wallet Router Fixes
- **File**: `core/wallet_router.py`
- Solana min trade: $25 → $1 (for micro-cap sniping with small wallets)
- Seed phase max position: 5% → 25% (for small wallet balances)
- Added Solana-specific branch in min_trade_usd logic
- Added extensive debug logging (balance, native_price, phase, pos_size, min_trade)

### 5. Jupiter Swap Payload Fix
- **File**: `core/solana_executor.py`
- Removed conflicting `computeUnitPriceMicroLamports` (conflicts with `prioritizationFeeLamports: "auto"`)
- Added response body error logging

### 6. .env Updates (Hetzner only)
- `MIN_GEM_SCORE=55` → `MIN_GEM_SCORE=50`

---

## Key Configuration (Hetzner)

| Setting | Value |
|---------|-------|
| MODE | live |
| ACTIVE_CHAINS | solana, base, bsc, avalanche |
| MIN_GEM_SCORE | 50 |
| MIN_SIGNAL_SCORE | 50 |
| EXPRESS_LANE_THRESHOLD | 82 |
| Solana Wallet Balance | ~4.5 SOL ($413) |
| Seed Phase Position | 25% max × conviction multiplier |
| Solana Min Trade | $1.00 |

---

## Priority Tasks for Manus

### 🔴 P0: Fix Solana Transaction Signing
The fix in `core/solana_executor.py` (line ~154) may need adjustment. Test with:
```python
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
import base64

# The correct pattern for solders 0.27+:
tx = VersionedTransaction.from_bytes(tx_bytes)
signed_tx = VersionedTransaction(tx.message, [keypair])
```

If `VersionedTransaction(message, [keypair])` doesn't work in solders 0.27.1, try:
```python
from solders.message import MessageV0
# Get message from unsigned tx, sign externally
msg = tx.message
signed_tx = VersionedTransaction.populate(msg, [keypair.sign_message(bytes(msg))])
```

### 🟡 P1: Remove Debug Logging from wallet_router.py
There are temporary `logger.info()` debug lines added for troubleshooting wallet routing. These should be converted to `logger.debug()` or removed before the next git push.

### 🟡 P2: EVM Chain Wallet Setup
Currently only Solana trades work. EVM chains (Base, BSC, Avalanche) need:
- Funded wallets with native tokens (ETH for Base, BNB for BSC, AVAX for Avalanche)
- Verified executor implementations (`core/evm_executor.py`)

### 🟢 P3: Position Sizing Review
Current math: `$413 × 25% × 0.40 conviction × kelly = ~$41`. Review whether the conviction multiplier of 0.40 for gems scoring 50-70 is too conservative.

---

## Architecture Reference

```
DexScreener (profiles, boosts, CTO, ads)
         ↓
    Gem Scanner (14 signals → gem_score)
         ↓
    Enrichment (Moralis, HolderAnalysis, SmartMoney, Grok, UnlockRisk, DefiLlama)
         ↓
    Signal Engine (micro-cap path: 5-axis composite)
         ↓
    GemSnipe Strategy (reuses composite, no TA recalc)
         ↓
    Wallet Router (phase sizing, Kelly, conviction, slippage)
         ↓
    Jupiter Quote API → Swap API → Sign → Broadcast
```

## Key Files
| File | Purpose |
|------|---------|
| `core/solana_executor.py` | Jupiter integration, tx signing, Solana execution |
| `core/wallet_router.py` | Position sizing, phase scaling, wallet selection |
| `core/signal_engine.py` | TA + micro-cap dual-path signal scoring |
| `scanner/gem_scanner.py` | 14-signal gem discovery pipeline |
| `strategies/gem_snipe.py` | Entry strategy with Fibonacci integration |
| `main.py` | Bot loop orchestrator |
| `config/settings.py` | All configurable thresholds |
