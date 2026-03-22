# SYSTEM — Architecture & Data Flow

## System Overview
```
┌─────────────────────────────────────────────────────────────────┐
│                    SHAMROCK TRADING BOT                         │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Scanner  │───▶│  Signal  │───▶│ Executor │───▶│ Position │  │
│  │  (Gems)  │    │  Engine  │    │  (Trade) │    │ Monitor  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │                │              │               │         │
│       ▼                ▼              ▼               ▼         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Risk Manager (circuit breaker)              │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │                │              │               │         │
│       ▼                ▼              ▼               ▼         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Notifications                         │   │
│  │              Slack  ·  Telegram  ·  Logs                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Pipeline: Scan → Score → Execute → Monitor

### Phase 1: Discovery (`scanner/gem_scanner.py`)
- Pulls from 5 DexScreener sources every 30 seconds
- Sources: Profiles, Latest Boosts, Top Boosts, CTOs, Ads
- Filters: `MIN_LIQUIDITY_USD ≥ $25,000`, active chains only

### Phase 2: Scoring (`scanner/gem_scanner.py` → `core/signal_engine.py`)
- 13-signal weighted scoring (0–100)
- Express lane: score ≥ 82 → skip TA, execute immediately
- Standard path: score ≥ 55 → full TA + Fibonacci analysis

### Phase 3: Safety Gate (`core/safety.py`)
- GoPlus API security audit
- Honeypot.is simulation
- Token Sniffer score check
- Blocklist verification
- **Any failure = instant reject**

### Phase 4: Execution (`core/executor.py` / `core/solana_executor.py`)
- Chain-appropriate DEX routing (CoW for ETH, Jupiter for SOL, 1inch elsewhere)
- MEV protection on Ethereum (Flashbots/CoW)
- Exact approval amounts only (no unlimited approvals)
- Gas optimization (skip if > `MAX_GAS_GWEI`)

### Phase 5: Monitoring (`core/position_monitor.py`)
- 30-second price checks on all open positions
- Trailing stop-loss and take-profit execution
- Tiered exits: 50% at 2x, 25% at 5x, let 25% ride

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | Entry point, main loop orchestration |
| `config/settings.py` | All env-driven settings |
| `config/chains.py` | Chain RPC endpoints and DEX config |
| `config/tokens.py` | Whitelists, blocklists, stablecoins |
| `config/wallets.py` | Wallet routing per chain |
| `core/executor.py` | EVM trade execution |
| `core/solana_executor.py` | Solana trade execution |
| `core/safety.py` | Pre-trade safety checks |
| `core/risk.py` | Risk management logic |
| `core/position_monitor.py` | Position tracking & exits |
| `scanner/gem_scanner.py` | Gem discovery & scoring |
| `strategies/gem_snipe.py` | GemSnipe strategy (TA + Fibonacci) |
| `dashboard/app.py` | Streamlit dashboard |

## Operating Modes
| Mode | Behavior | Env Var |
|------|----------|---------|
| `paper` | Simulated trades, no real funds | `MODE=paper` |
| `live` | Real blockchain txns, real money | `MODE=live` |
