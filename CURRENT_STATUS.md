# Shamrock Trading Bot — Current Status (June 11, 2026)

## 🟢 Pipeline Status: FULLY LIVE — 14-Signal Scanner + 29-Indicator TA + 12 Guardrails + AI Auto-Tuner

The entire trade pipeline is wired and working end-to-end:
```
9 Discovery Sources ✅ → 14-Signal Scoring ✅ → Rug Protection ✅ → Moralis Enrichment ✅ → 29-Indicator TA ✅ → Strategy ✅ → Offensive Guardrails ✅ → ShamrockGuard ✅ → Wallet Router ✅ → Executor ✅
```

### What's Working
- **Gem Scanner**: 9 discovery sources — DexScreener (5 feeds), Moralis trending, Moralis filtered, Whale accumulation, Pump.fun graduates, Binance Pulse
- **14-Signal Composite Scoring**: Volume, liquidity, buy pressure, holder distribution, social, smart money, Moralis enrichment, dev wallet history, copycat detection, sniper detection
- **29-Indicator TA Engine**: Full TA for tokens with 24+ candles, micro-cap enrichment path for new tokens
- **Rug Protection**: Dev wallet age/frequency/sell pattern analysis + fuzzy-match copycat detection (instant-reject)
- **Moralis Pro Integration**: Primary enrichment — buying pressure, on-chain strength, security scores, holder analytics, discovery tokens
- **Binance Pulse**: Smart money signals, social hype, unified rankings (free, no key)
- **LLM Auto-Tuner (Trading-as-Git)**: AI quantitative tuning of active positions. Modifies trailing stops based on logic reasoning via `gpt-5.6-luna` (`OPENAI_MODEL`).
- **ShamrockGuard**: Global risk protector. Scales position sizing relative to the $500/day profit goal, and enforces maximum daily drawdowns.
- **Hourly Reports**: Hourly dispatches to Telegram and Slack with current PnL, active regime, and position count.
- **Progression of Goals & Pyramiding**:
  - We target a daily goal starting at $500/day profit.
  - When the daily goal is met, we *leverage our gains to make more*, establishing a pyramiding structure.
  - Goals compound (e.g., $500 → $1,000 → $2,500) as realized profit gives us "House Money" to scale up position sizes (Nuclear Wallet unlocks up to 60% sizing) aggressively without risking our principal.
- **Signal Engine**: Micro-cap scoring path produces strong composites (80-86 for good gems)
- **Dual-Wallet Architecture**: Conservative (Primary, 5% max) + Nuclear (Wallet B, 60% max)
- **Jupiter (SOL)**: Quote API + swap execution working perfectly
- **Position Monitor**: Trailing stops, dual TP ladders, 3-tier pyramid scaling
- **12 Offensive Guardrails**: Hot streak, god mode, house money, pyramid scaling, fast fail, blitz mode, MEV gas bribe, cascade boost, loss cooling, express overdrive, momentum reentry, profit boost

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

## Key Configuration (Hetzner — LIVE)

| Setting | Value |
|---------|-------|
| MODE | live |
| ACTIVE_CHAINS | solana, base, bsc, avalanche |
| MIN_GEM_SCORE | 55 (global) / 82 (nuclear profile) |
| EXPRESS_LANE_SCORE | 82 (conservative) / 90 (nuclear) |
| Scan Interval | 60s |
| Offensive Guardrails | All 12 enabled |
| Pyramid Scaling | 3-tier (+30%/+100%/+300%) |
| Regime Filter | EXPANSION / NORMAL / CHOP (pseudo-ADX) |

---

## Architecture

```
DexScreener (5 feeds) + Moralis (trending, filtered) + Whale Accumulation + Pump.fun + Binance Pulse
     ↓
Gem Scanner (14 signals → gem_score 0–100)
     ↓
Rug Protection Gate
├── Dev Wallet History (3% weight) — wallet age, frequency, sell patterns
├── Copycat Detection (2% weight) — fuzzy match → instant reject
└── Moralis Sniper Detection — ≥10 snipers → hard block (Solana)
     ↓
Moralis-First Enrichment (buying pressure, on-chain strength, security scores)
     ↓
29-Indicator TA Engine (RSI, MACD, BB, ADX, VWAP, Ichimoku, +23 more)
     ↓
GemSnipe Strategy (Fibonacci zones, signal gate)
     ↓
Offensive Guardrails (12 guardrails: streak tracking, god mode, house money, pyramids, fast fail, blitz)
     ↓
Regime Filter (EXPANSION × 1.5 / NORMAL × 1.0 / CHOP × 0.3)
     ↓
Wallet Router (dual-profile: Conservative 5% / Nuclear 60%, Kelly sizing)
     ↓
Jupiter (SOL) / 1inch (EVM) / Trader Joe (AVAX) → Sign → Broadcast
```

## Key Files
| File | Purpose |
|------|---------|
| `scanner/gem_scanner.py` | 14-signal gem discovery pipeline (9 sources) |
| `core/signal_engine.py` | 29-indicator TA + micro-cap dual-path scoring |
| `strategies/indicators.py` | 29-indicator calculation arsenal |
| `core/offensive_guardrails.py` | 12 offensive guardrails + state persistence |
| `core/regime_filter.py` | EXPANSION/NORMAL/CHOP pseudo-ADX classification |
| `data/providers/moralis_money.py` | Moralis Pro enrichment (primary) |
| `data/providers/binance_pulse.py` | Binance Pulse smart money + social hype |
| `data/providers/dev_wallet_history.py` | Dev wallet rug protection |
| `data/providers/copycat_detector.py` | Copycat/impersonation detection |
| `core/position_monitor.py` | Trailing stops, dual TP ladders, pyramid scaling |
| `core/solana_executor.py` | Jupiter integration, tx signing |
| `core/wallet_router.py` | Dual-wallet routing, Kelly sizing, phase scaling |
| `core/hourly_report.py` | Slack & TG Hourly updates on PnL & positions |
| `core/shamrock_guard.py` | Bank-It Mode & strict Drawdown limiting |
| `core/llm_auto_tuner.py` | LLM quantitative tuning with TaG methodology |
| `config/wallets.py` | Conservative + Nuclear strategy profiles |
| `config/settings.py` | 200+ configurable thresholds |
| `main.py` | Bot loop orchestrator |

## Docker Services
| Container | Status | Purpose |
|-----------|--------|---------|
| `shamrock-bot` | 🟢 Healthy | Main trading bot (LIVE mode) |
| `shamrock-dashboard` | 🟢 Healthy | Reflex UI on :3000 |
| `shamrock-health` | 🟢 Healthy | 5-min health checks |
| `shamrock-db` | 🟢 Running | Shared data volume (Alpine + SQLite) |
| `shamrock-paper` | ⚪ Profile-gated | Paper trading mode (opt-in via `--profile paper`) |

---

## 🚀 Future Roadmap & Objectives
*   **Aggressive Scaling Phase:** Once the current logic proves exponential confidence and builds a strong capital base, the immediate next step is to **increase leverage** and **tighten stop losses further**. This will shift the bot into an aggressive "capital stacking" mode to exponentially gain USDC while relying on the proven win rate.
