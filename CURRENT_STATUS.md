# Shamrock Trading Bot — Current Status (March 24, 2026)

## 🟢 Pipeline Status: FULLY LIVE — 18-Signal Gem Engine + Rug Protection

The entire trade pipeline is wired and working end-to-end:
```
Scanner ✅ → 18-Signal Scoring ✅ → Rug Protection ✅ → Moralis Enrichment ✅ → Signal Engine ✅ → Strategy ✅ → Wallet Router ✅ → Executor ✅
```

### What's Working
- **Gem Scanner**: Discovers 4-6 candidates per cycle from DexScreener + Moralis Money (Pro)
- **18-Signal Composite Scoring**: Volume, liquidity, holder distribution, social, smart money, unlock risk, Moralis enrichment (12%), dev wallet history (3%), copycat detection (2%)
- **Rug Protection**: Dev wallet age/frequency/sell pattern analysis + fuzzy-match copycat detection (instant-reject)
- **Moralis Pro Integration**: 10 endpoints — filtered tokens, trending, top gainers/losers, buying pressure, token score, analytics, batch analytics, stats, holders
- **Enrichment Pipeline**: HolderAnalysis, UnlockRisk, Grok Sentiment, Smart Money, DefiLlama, CoinGecko Social — all firing
- **Signal Engine**: Micro-cap scoring path produces strong composites (80-86 for good gems)
- **Strategy (GemSnipe)**: Correctly reuses signal engine composite scores
- **Wallet Router**: Routes trades with phase-based sizing, conviction multipliers, chain-aware slippage
- **Jupiter (SOL)**: Quote API + swap execution working perfectly
- **Position Monitor**: Trailing stops, take-profit exits, pyramid scaling evaluation
- **Offensive Guardrails**: Win/loss streak tracking, house money mode, god mode, loss cooling

### ✅ Solana Transaction Signing — Verified

Both signing patterns confirmed working in solders 0.21+:

**Pattern 1 (primary):**
```python
tx = VersionedTransaction.from_bytes(tx_bytes)
signed_tx = VersionedTransaction(tx.message, [keypair])  # ✅ WORKS
```

**Pattern 2 (fallback — auto-tried if Pattern 1 raises TypeError):**
```python
sig = keypair.sign_message(bytes(tx.message))
signed_tx = VersionedTransaction.populate(tx.message, [sig])  # ✅ WORKS
```

---

## Moralis Pro — Full Endpoint Utilization

| # | Endpoint | Purpose | Weight |
|---|----------|---------|--------|
| 1 | Filtered Tokens | Custom filter discovery (experienced buyers, liquidity, security) | Discovery |
| 2 | Trending Tokens | Momentum-based discovery | Discovery |
| 3 | Top Gainers | Breakout detection | Discovery |
| 4 | Top Losers | Mean-reversion candidates | Discovery |
| 5 | Buying Pressure | Early momentum signal | Discovery |
| 6 | Token Score | Proprietary 0–100 scoring | 12% enrichment |
| 7 | Token Analytics | Buy/sell volume, net buyers | 12% enrichment |
| 8 | Batch Analytics | Bulk 30-token enrichment | Efficiency |
| 9 | Token Stats | Transfer count | Free tier |
| 10 | Holder Count | Holder enumeration | Free tier |

---

## Rug Protection Modules

### Dev Wallet History (`data/providers/dev_wallet_history.py`)
- Analyzes creator wallet age (<30 days = red flag)
- Checks token creation frequency (serial deployers)
- Scans for sell patterns (dump history)
- **Weight**: 3% of composite score

### Copycat Detection (`data/providers/copycat_detector.py`)
- Fuzzy-matches token name/symbol against 50+ high-profile tokens
- Checks for Unicode homoglyphs, zero-width characters, reversed strings
- **Instant-reject**: Copycats are removed before enrichment (saves API rate limits)
- **Weight**: 2% of composite score

---

## Key Configuration (Hetzner — LIVE)

| Setting | Value |
|---------|-------|
| MODE | live |
| ACTIVE_CHAINS | solana, base, bsc, avalanche |
| MIN_GEM_SCORE | 55 |
| EXPRESS_LANE_THRESHOLD | 82 |
| Scan Interval | 60s |
| Offensive Guardrails | Loss streak cooling (+10 to min score per 2L streak) |

---

## Architecture

```
DexScreener (profiles, boosts, CTO, ads)
    + Moralis Money Pro (filtered, trending, gainers, losers, buying pressure)
         ↓
    Gem Scanner (18 signals → gem_score 0–100)
         ↓
    Rug Protection Gate
    ├── Dev Wallet History (3% weight) — wallet age, frequency, sell patterns
    └── Copycat Detection (2% weight) — fuzzy match → instant reject
         ↓
    Enrichment (Moralis Score+Analytics 12%, HolderAnalysis, SmartMoney, Grok, UnlockRisk, DefiLlama)
         ↓
    Signal Engine (micro-cap path: 5-axis composite)
         ↓
    GemSnipe Strategy (reuses composite, no TA recalc)
         ↓
    Offensive Guardrails (streak tracking, house money, god mode, loss cooling)
         ↓
    Wallet Router (phase sizing, Kelly, conviction, slippage)
         ↓
    Jupiter (SOL) / 1inch (EVM) → Sign → Broadcast
```

## Key Files
| File | Purpose |
|------|---------|
| `scanner/gem_scanner.py` | 18-signal gem discovery pipeline |
| `data/providers/moralis_money.py` | Moralis Pro integration (10 endpoints) |
| `data/providers/dev_wallet_history.py` | Dev wallet rug protection |
| `data/providers/copycat_detector.py` | Copycat/impersonation detection |
| `core/signal_engine.py` | TA + micro-cap dual-path signal scoring |
| `core/position_monitor.py` | Trailing stops, TP exits, pyramid scaling |
| `core/offensive_guardrails.py` | Win/loss streak, house money, god mode |
| `core/solana_executor.py` | Jupiter integration, tx signing |
| `core/wallet_router.py` | Position sizing, phase scaling, wallet selection |
| `strategies/gem_snipe.py` | Entry strategy with Fibonacci integration |
| `main.py` | Bot loop orchestrator |
| `config/settings.py` | All configurable thresholds |

## Docker Services
| Container | Status | Purpose |
|-----------|--------|---------|
| `shamrock-bot` | 🟢 Healthy | Main trading bot (LIVE mode) |
| `shamrock-cosmos` | 🟢 Healthy | Cosmos yield staking module |
| `shamrock-dashboard` | 🟢 Healthy | Streamlit UI on :8501 |
| `shamrock-health` | 🟢 Healthy | 5-min health checks |
| `shamrock-db` | 🟢 Running | Shared data volume |
