# 🚦 Current Status — Shamrock Trading Bot
> Last updated: 2026-03-23 @ 14:00 EDT

## Bot Status: 🟡 ALMOST TRADING (1 blocker remaining)

The bot is running **LIVE** on the Hetzner VPS (5.161.126.32). The entire
signal pipeline is working — gems are being discovered, scored, enriched,
analyzed, and approved. **The last blocker is wallet routing for Solana.**

---

## ✅ What's Working (Verified in Production)

### 1. Gem Discovery (14-Signal Pipeline)
- DexScreener: token profiles, boosts, community takeovers, ads
- Moralis Discovery: 145 trending tokens across 4 chains (solana, base, bsc, avalanche)
- Safety checks: GoPlus + Honeypot.is + TokenSniffer + stablecoin blocking
- **14 enrichment signals** scored per candidate:
  - HolderAnalysis → score=72 (buy/sell ratio, LP concentration, txn count)
  - UnlockRisk → score=100 (circulating supply %, mcap/fdv ratio)
  - Grok/X Sentiment → score=75 (buzz=high, 15 influencers, red_flags analysis)
  - SmartMoney → tracking known wallet holders per chain
  - LunarCrush, DefiLlama, GoPlus, TokenSniffer, etc.

### 2. Signal Engine (Dual-Path Scoring)
- **Full TA path** (≥24 candles): RSI, MACD, Bollinger Bands, EMA, VWAP, ADX
- **Micro-cap path** (<24 candles): Uses `gem_score` + enrichment data as quality proxy
  - Builds composite from: trend + momentum + volume + on-chain + sentiment
  - Example: Token "7" with 4 candles → `gem=66 → trend=100 momentum=95 volume=90 onchain=58 → composite=86.2`
- Threshold: `MIN_SIGNAL_SCORE = 50.0`

### 3. Strategy Evaluation (GemSnipeStrategy)
- Fibonacci alignment check (permissive for insufficient_data)
- Reuses signal engine's composite score when OHLCV is sparse
- TP/SL calculation based on gem score + Fibonacci zones
- **Confirmed BUY SIGNAL**: `✅ BUY SIGNAL for 7 (confidence: 61)`

### 4. Infrastructure
- Docker containers: bot + dashboard + health checker
- Slack notifications: startup alerts, error reporting
- Position monitor: running in background thread (30s intervals)
- Scan interval: 60 seconds across 4 chains

---

## ❌ Current Blocker

### Wallet Router: "No eligible wallet found for solana trade"

**The signal engine approves. The strategy approves. But no wallet is selected.**

The wallet router at `core/wallet_router.py` is rejecting the trade. Possible causes:

1. **Missing Solana private key** — `SOLANA_PRIVATE_KEY_PRIMARY` and/or `SOLANA_PRIVATE_KEY_B` may not be set in the Hetzner `.env`
2. **Insufficient SOL balance** — wallet may not have enough SOL for gas + trade
3. **Max concurrent positions hit** — phase-based limits could be blocking
4. **Daily loss limit reached** — though unlikely on first day

**Key files to investigate:**
- `core/wallet_router.py` — routing logic, Kelly sizing, phase scaling (lines 400-539)
- `config/wallets.py` — wallet configuration, Solana key loading (lines 90-120)
- `.env` on Hetzner — check `SOLANA_PRIVATE_KEY_PRIMARY`, `SOLANA_ADDRESS_PRIMARY`
- `core/balance_fetcher.py` — how Solana balances are fetched

---

## 📊 Recent Fixes (March 23, 2026)

### Fix 1: Micro-Cap Signal Engine (`core/signal_engine.py`)
**Problem**: The `_fallback_signals()` method gave all new tokens a flat score of ~21, below the 50.0 threshold.  
**Fix**: Renamed to `_microcap_signals()`. Now uses a 5-axis composite:
```
trend (25%) + momentum (25%) + volume (25%) + on-chain (15%) + sentiment (10%)
```
Each axis pulls from DexScreener price data + enrichment signals (gem_score, holder_concentration, smart_money, unlock_risk, grok_sentiment).

### Fix 2: 24-Candle Threshold (`core/signal_engine.py`)
**Problem**: GeckoTerminal returned sparse OHLCV data (4-10 candles) for new tokens. The bot ran full TA (RSI/MACD/BB) on garbage data → composite=23.8.  
**Fix**: If `len(candles) < 24`, route to micro-cap scoring instead of sparse TA.

### Fix 3: Strategy Score Reuse (`main.py` + `strategies/gem_snipe.py`)
**Problem**: The strategy created its own `SignalScore` with only `onchain_score` when OHLCV was insufficient → composite=35.1 → rejected (even after signal engine approved at 86.2).  
**Fix**: `main.py` stores the signal engine's score on `candidate.signal_score`. `gem_snipe.py` reuses it when OHLCV is insufficient.

---

## 🏗 Trade Pipeline Architecture

```
Scanner → 14-Signal Score → Safety Check → Signal Engine → Strategy Gate → Wallet Router → Executor
                                               │                                │
                                   ≥24 candles: Full TA           Kelly Criterion sizing
                                   <24 candles: Micro-cap          Phase-based scaling
                                   (gem_score + enrichment)        Chain-aware slippage
```

### Key Files
| File | Purpose |
|------|---------|
| `main.py` | Bot loop — scan → score → signal → strategy → trade |
| `scanner/gem_scanner.py` | Multi-source token discovery + 14-signal scoring |
| `core/signal_engine.py` | Dual-path TA: full TA (≥24 candles) or micro-cap (<24) |
| `strategies/gem_snipe.py` | Fibonacci + signal gate + TP/SL calculation |
| `core/wallet_router.py` | Kelly/phase/chain routing — **CURRENT BLOCKER** |
| `core/executor.py` | 1inch (EVM) + Jupiter (Solana) swap execution |
| `core/solana_executor.py` | Solana-specific: Jupiter API, priority fees |
| `config/wallets.py` | Wallet configs, Solana key loading |
| `config/settings.py` | All thresholds (MIN_GEM_SCORE=55, MIN_SIGNAL_SCORE=50) |
| `data/models.py` | GemCandidate, SignalScore, Token, Trade dataclasses |
| `data/providers/` | All data providers (Moralis, Grok, HolderAnalysis, etc.) |
| `config/chains.py` | Chain configs, RPC URLs, DEX router addresses |

### Key Settings (config/settings.py)
```python
MODE = "live"
MIN_GEM_SCORE = 55.0         # Minimum gem score to consider
MIN_SIGNAL_SCORE = 50.0      # Minimum composite for buy signal
EXPRESS_LANE_SCORE = 82.0    # Skip signal engine, go direct
MAX_POSITION_SIZE_PERCENT = 2.0
STOP_LOSS_PERCENT = 10.0
CIRCUIT_BREAKER_PERCENT = 15.0
SCAN_INTERVAL = 60           # seconds
ACTIVE_CHAINS = ["solana", "base", "bsc", "avalanche"]
```

---

## 🎯 Priority Tasks

1. **[CRITICAL] Fix Solana wallet routing** — Bot is finding gems, approving signals, generating BUY signals, but can't execute because no wallet is eligible
2. **[HIGH] Verify EVM wallet routing** — Same issue may affect Base/BSC/Avalanche trades
3. **[MEDIUM] LunarCrush errors** — `RetryError` on sentiment fetches (API rate limiting?)
4. **[LOW] gem_score tuning** — Most Moralis-discovered tokens score 42-44, below MIN_GEM_SCORE (55). These are larger market-cap tokens that should be tradeable with adjusted scoring
