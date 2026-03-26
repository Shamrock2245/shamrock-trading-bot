# SYSTEM — Architecture & Data Flow

## System Overview
```
┌──────────────────────────────────────────────────────────────────────────┐
│                       SHAMROCK TRADING BOT                               │
│                                                                          │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────────┐  │
│  │ GEM SCANNER │──▶│  SIGNAL    │──▶│  EXECUTOR  │──▶│   POSITION     │  │
│  │ 9 Sources   │   │  ENGINE    │   │  (Trade)   │   │   MONITOR      │  │
│  │ 14 Signals  │   │  29 TA     │   │  Route+MEV │   │ TP/SL/Pyramid  │  │
│  └────────────┘   └────────────┘   └────────────┘   └────────────────┘  │
│       │                │                │                │               │
│       ▼                ▼                ▼                ▼               │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Risk Manager · Regime Filter · Offensive Guardrails · Safety   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│       │                │                │                │               │
│       ▼                ▼                ▼                ▼               │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                  Notifications (Slack · Telegram · Logs)         │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

## Pipeline: Discover → Score → Enrich → Analyze → Execute → Monitor

### Phase 1: Discovery (`scanner/gem_scanner.py`)
Pulls from **9 sources** every 60 seconds:

| # | Source | Type | Details |
|---|--------|------|---------|
| 1 | DexScreener Profiles | New listings | Latest token profiles across all chains |
| 2 | DexScreener Boosts | Community hype | Latest and top boost rankings |
| 3 | DexScreener CTOs | Revival plays | Community takeover events (+8 score bonus) |
| 4 | DexScreener Ads | Funded projects | Tokens with active DexScreener ad spend |
| 5 | Moralis Trending | Hot tokens | Momentum-based discovery across EVM chains |
| 6 | Moralis Filtered | Custom query | Experienced net buyers, liquidity, security filters |
| 7 | Pump.fun Graduates | Solana launches | Tokens graduating from bonding curve → Raydium |
| 8 | Binance Pulse | Smart money | Social hype scoring, unified rankings |
| 9 | Gem Watchlist | Re-evaluation | Near-miss tokens (score 35–49) from prior cycles |

Whale Accumulation discovery via `netExperiencedBuyers` triggers a **+20% bonus weight** on the gem score.

### Phase 2: Scoring (`scanner/gem_scanner.py`)
14-signal weighted scoring (0–100). See [SIGNALS.md](SIGNALS.md) for full table.

**Key thresholds:**
| Threshold | Effect |
|-----------|--------|
| ≥ 90 | Express lane — instant market buy, skip TA |
| ≥ 85 | God Signal — 1.5x gas bribe for next-block inclusion |
| ≥ 82 | Nuclear profile (Wallet B) minimum entry |
| ≥ 65 | Conservative profile (Primary) minimum entry |
| 45–64 | Standard path — requires full TA + Fibonacci confirmation |

### Phase 3: Enrichment (Moralis-First, 5 Parallel Calls)
For candidates scoring ≥ 45, five lean API calls fire in parallel:

1. **Moralis Money** — buying pressure, token analytics, score, discovery enrichment
2. **Moralis Metadata** — FDV, spam flag, social links, contract verification
3. **Dev Wallet History** — wallet age, deployment frequency, sell patterns
4. **Copycat Detection** — fuzzy match against 50+ high-profile tokens (instant-reject)
5. **Binance Pulse** — smart money signals, social hype score

**Nuclear bonuses applied after enrichment:**
- Moralis buying pressure > 70% → **+18 points**
- Dev wallet serial deployer (< 48h, > 3 tokens) → **−30 points**

### Phase 4: Technical Analysis (`core/signal_engine.py`)
Dual-path analysis:

| Path | Condition | Engine |
|------|-----------|--------|
| **Full TA** | ≥ 24 OHLCV candles | 29-indicator blend (RSI, MACD, BB, EMA, VWAP, ADX, Stochastic, Ichimoku, OBV, ATR + 19 more) |
| **Micro-cap** | < 24 candles | gem_score + enrichment composite (5-axis: trend, momentum, volume, on-chain, sentiment) |

Micro-cap path uses **neutral fallbacks (50.0)** for missing indicators — zero-data never penalizes.

### Phase 5: Safety Gate (`core/safety.py`)
- GoPlus API security audit (cached 5 min)
- Honeypot.is simulation (cached 5 min)
- Token Sniffer score check
- Blocklist verification
- Solana sniper detection (≥ 10 snipers or critical risk = **HARD BLOCK**)
- **Any failure = instant reject**

### Phase 6: Execution (`core/executor.py` / `core/solana_executor.py`)
- Chain-appropriate DEX routing (CoW for ETH, Jupiter for SOL, 1inch elsewhere, Trader Joe for AVAX)
- MEV protection on Ethereum (Flashbots/CoW)
- Exact approval amounts only (no unlimited approvals)
- Gas optimization (skip if > `MAX_GAS_GWEI`)
- Dual-wallet strategy routing (Conservative primary + Nuclear Wallet B)

### Phase 7: Monitoring (`core/position_monitor.py`)
- 30-second price checks on all open positions
- Profile-aware TP ladder (Conservative: 2x/3x, Nuclear: 5x/12x/30x)
- Dynamic trailing stops (Nuclear: 30% → 18% at 10x → 8% at 20x)
- **3-tier pyramid scaling** (add at +30%, +100%, +300% gain using house money)
- Fast fail guardrails (volume collapse, time exit for flat positions)
- Offensive guardrails (win/loss streak tracking, house money mode, god mode)

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | Entry point, main loop orchestration |
| `config/settings.py` | All env-driven settings (200+ params) |
| `config/chains.py` | Chain RPC endpoints and DEX config |
| `config/tokens.py` | Whitelists, blocklists, stablecoins |
| `config/wallets.py` | Wallet routing, StrategyProfile definitions |
| `core/executor.py` | EVM trade execution (1inch + CoW) |
| `core/solana_executor.py` | Solana trade execution (Jupiter) |
| `core/safety.py` | Pre-trade safety checks (cached) |
| `core/risk.py` | Risk management logic |
| `core/position_monitor.py` | Position tracking, exits, pyramid scaling |
| `core/regime_filter.py` | EXPANSION / NORMAL / CHOP market regime |
| `core/offensive_guardrails.py` | Win/loss streaks, house money, god mode |
| `core/wallet_router.py` | Kelly sizing, phase scaling, conviction multipliers |
| `scanner/gem_scanner.py` | Gem discovery & 14-signal scoring |
| `strategies/gem_snipe.py` | GemSnipe strategy (TA + Fibonacci) |
| `strategies/indicators.py` | 29-indicator TA arsenal |
| `data/providers/moralis_money.py` | Moralis Pro (discovery + enrichment, 10 endpoints) |
| `data/providers/moralis_solana.py` | Moralis Solana (snipers, OHLCV, Pump.fun) |
| `data/providers/binance_pulse.py` | Binance Pulse (smart money, social hype) |
| `dashboard/app.py` | Streamlit dashboard |

## Operating Modes
| Mode | Behavior | Env Var |
|------|----------|---------|
| `paper` | Simulated trades, no real funds | `MODE=paper` |
| `live` | Real blockchain txns, real money | `MODE=live` |

## Market Regime Filter (Global Gate)
The regime filter runs **before scanning** every cycle using pseudo-ADX from ETH + SOL:

| Regime | Condition | Effect |
|--------|-----------|--------|
| **EXPANSION** | pseudo-ADX ≥ 35, vol_ratio ≥ 0.04 | Nuclear sizing × 1.5 multiplier |
| **NORMAL** | Between CHOP and EXPANSION | Standard sizing |
| **CHOP** | pseudo-ADX < 20, vol_ratio < 0.03 | All new entries skipped, 30% sizing if forced |
