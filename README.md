<p align="center">
  <img src="https://img.shields.io/badge/☘️-Shamrock_Trading_Bot-00C853?style=for-the-badge&labelColor=1a1a2e" alt="Shamrock Trading Bot" />
</p>

<h1 align="center">Shamrock Trading Bot</h1>

<p align="center">
  <strong>AI-powered multi-chain crypto trading bot — gem discovery, copy-trading, MEV-protected execution, and automated portfolio management.<br/>Always on. Always scanning. Always compounding. 24/7/365.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/status-🟢%20LIVE%2024%2F7-00C853?style=flat-square" alt="Status" />
  <img src="https://img.shields.io/badge/chains-ETH%20%7C%20Base%20%7C%20ARB%20%7C%20POLY%20%7C%20BSC%20%7C%20SOL%20%7C%20AVAX-blue?style=flat-square" alt="Chains" />
  <img src="https://img.shields.io/badge/infra-Hetzner%20CX33%20Helsinki-red?style=flat-square" alt="Infra" />
  <img src="https://img.shields.io/github/stars/Shamrock2245/shamrock-trading-bot?style=flat-square" alt="Stars" />
</p>

---

## ⚠️ Disclaimer

> **This software is for educational and research purposes only.**
>
> - **Not financial advice.** Trading cryptocurrencies carries significant risk. You can lose your entire investment.
> - **Use at your own risk.** The authors are not responsible for any financial losses.
> - **Always start in paper/dry-run mode.** Never deploy with real funds until you have thoroughly tested and understand the behavior.
> - **Never invest more than you can afford to lose.**
> - **Do your own research (DYOR).**

---

## ✨ Features

### 🔍 Gem Discovery Engine (14-Signal Scanner + 29-Indicator TA)
- Multi-chain token scanner (Ethereum, Base, Arbitrum, Polygon, BSC, **Solana**, **Avalanche**)
- **9+ discovery sources**: DexScreener (5 feeds), Moralis trending, Moralis filtered, Whale accumulation, Pump.fun graduates, Binance Pulse, Grok/X trending scan, Moralis intelligence
- **[Moralis Money Pro](https://moralis.io/)** — primary enrichment: buying pressure, on-chain strength, security scores, holder analytics
- **14-signal composite scoring** (0–100) — volume, liquidity, holders, social, smart money, unlock risk, Moralis enrichment, dev wallet history, copycat detection, sniper detection
- **29-indicator TA engine** — RSI, MACD, Bollinger Bands, ADX, VWAP, Ichimoku, Williams %R, Stochastic, OBV, CMF, and 19 more
- **Smart money wallet tracking** — follow known alpha wallets via Moralis + Binance Pulse
- **Grok/X sentiment analysis** — real-time social buzz scoring via X API
- **Holder concentration analysis** — buy/sell ratio, LP concentration, transaction patterns
- **Token unlock risk scoring** — circulating supply %, FDV ratio, vesting detection

### 🛡️ 7-Layer Validation Pipeline
Every token must pass a gauntlet of safety gates before any buy is executed:

| Layer | Gate | Provider | What It Checks |
|-------|------|----------|----------------|
| 1 | GoPlus Security | GoPlus API | Contract risk flags (honeypot, mint authority, etc.) |
| 2 | Honeypot.is | Honeypot.is API | Buy/sell tax simulation, actual honeypot detection |
| 3 | TokenSniffer | TokenSniffer API | Automated audit score, known scam patterns |
| 4 | RugCheck | RugCheck API (Solana) | Solana-specific rug pull indicators |
| 5 | ChainAware Deployer Fraud | ChainAware API | Deployer wallet history — past rug deployments |
| 6 | Perplexity Rug Search | Perplexity AI API | Web search for rug reports, scam mentions |
| 7 | CoinPaprika ATH Gate | CoinPaprika API | Rejects tokens already at/near all-time high |

### 🧬 Rug Pull Protection
- **Dev wallet history analysis** — creator wallet age, token deployment frequency, sell pattern detection
- **Copycat detection** — fuzzy-match against 50+ high-profile tokens, Unicode homoglyph detection, instant-reject filter
- **Moralis sniper detection** — ≥10 snipers → hard block (Solana)
- **12 offensive guardrails** — hot streak tracker, god mode, house money protocol, 3-tier pyramid scaling, fast fail, blitz mode, MEV gas bribe, cascade boost, loss cooling, express overdrive, momentum reentry, profit boost

### 🐋 Copy-Trading Pipeline
- **Alpha Wallet Monitor** — real-time polling of known profitable wallets across EVM + Solana
- **Proactive Whale Discovery** — every 6 hours, harvests top traders from the bot's best gems, scores their wallets via Moralis profitability data, auto-adds top performers to the watchlist
- **Moralis Streams** — push-based webhook ingestion for instant copy-trade detection (whale transfers, new liquidity events)
- **Fastlane execution** — dedicated queue with latency tracking, freshness-decay position sizing, and SLO alerts
- **Multi-wallet confirmation** — 2+ alpha wallets buying the same token within 2 minutes triggers a high-conviction signal

### 🧠 Machine Learning & AI Tuning
- **Goal Progression & Compounding (Pyramiding Daily Goals)** — The bot operates in phased financial goals that "pyramid" as capital grows:
  - **Phase 1 (Seed):** $500/day Target (Survival & consistency)
  - **Phase 2 (Growth):** $1,000/day Target (Activates past the first $10K milestone)
  - **Phase 3 (Acceleration):** $5,000/day Target (Heavy nuclear wallet leverage)
  - **Phase 4 (Compound/Whale):** $10,000+/day Target (Full auto-tune scaling)
  As targets are met, it leverages realized gains to increase buying power and dynamic position sizing for exponential compounding.
- **LLM Auto-Tuner (OpenAlice TaG)** — Reasoning-driven agent powered by `gpt-4o-mini` that reviews active positions every 15 minutes, adjusts trailing stops, and commits parameter updates using a "Trading-as-Git" workflow.
- **ShamrockGuard & Daily Goals** — Enforces a strict daily target (e.g. $500/day) and dynamically scales down position sizes or enters "Bank-It Mode" to protect profits when the target is nearing completion. Protects against excessive daily drawdowns.
- **TimesFM Forecaster** — Google's 200M-param foundation model runs locally on the VPS; forecasts 4-hour price direction as a confirmation signal before entry
- **RL Position Sizer** — reinforcement learning agent that trains every 24 hours on completed trades and learns optimal position size multipliers per situation
- **XGBoost Weight Optimizer** — ML-driven score weight tuning from realized PnL data
- **Macro Regime Filter** — reads BTC, ETH, SOL, BNB 24h trends + Fear & Greed Index → classifies BULL/BEAR/NEUTRAL → dynamically adjusts score thresholds
- **Helius Enrichment** — Solana DAS API on-chain metadata: holder concentration, mint authority status, mutable metadata, top-10 wallet analysis

### ⚡ Trade Execution (Hyperliquid Primary)
- **Hyperliquid Perps (Primary Engine)** — Zero-gas, leveraged perpetual futures execution with deep liquidity and exact market-triggered stops.
- **EV-Aware Kelly Sizing** — Mathematical position sizing that starves negative-EV trades and scales into high-probability setups (up to 40% wallet cap).
- **Market-Triggered Stop Losses** — Guaranteed exit execution during flash crashes; prevents limit-order slippage wipeouts.
- **Strict "No-SL = No-Trade" Guard** — If the exchange rate-limits or fails to place a Stop Loss, the bot instantly market-closes the position to prevent unprotected exposure.
- **DEX Fallbacks** — [1inch](https://portal.1inch.dev/) + [Jupiter](https://jup.ag/) + [Trader Joe](https://traderjoexyz.com/) routing for on-chain gems.
- **Dual TP ladders** — Conservative (1.5x/2.5x/5x) + Nuclear (5x/12x/30x + ride) with dynamic ratcheting trailing stops.

### 📊 Portfolio Dashboard (9 Pages)
Reflex-powered UI at `http://46.62.231.43:3000`:

| Page | Purpose |
|------|---------|
| **Home** | Live bot status, heartbeat, cycle ticker, force-scan button |
| **🔍 Gem Scanner** | Real-time gem feed with scores, validation status, DexScreener links |
| **📊 Analytics** | P&L charts, win/loss ratios, trade history analysis |
| **🧠 Gem Advisor** | Decision cockpit — score breakdown, TA summary, AI recommendation |
| **💰 Positions** | Open positions monitor, Force Buy/Sell/Close buttons, TP ladder tracking |
| **🏥 System Health** | Docker status, memory/CPU gauges, error rates, API health |
| **👛 Wallet Overview** | Multi-chain balance breakdown, portfolio allocation, gas tracker |
| **🤝 Alpha Wallets** | Tracked alpha wallet performance, copy-trade signal history |
| **🎯 Sniper Wallets** | Proactive discovery results, top sniper rankings, auto-promotion status |
| **🏦 Paycheck Wallet** | Profit sweep progress, cold storage balance, sweep history |

### 🔔 Notifications
- **Slack** multi-channel alerts — gems, trades, stop-losses, circuit breakers, daily summaries
- **Telegram** bot integration — score-change alerts, trade notifications, copy-trade signals
- **Hourly Status Reports** — automated summary dispatched to Slack & Telegram with daily goal progress, PnL, active positions, and active regime.
- Configurable priority levels per event type

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- RPC endpoints ([Alchemy](https://www.alchemy.com/) or [Infura](https://infura.io/) — free tier works)
- Wallet(s) with ETH for gas

### Installation

```bash
# Clone the repo
git clone https://github.com/Shamrock2245/shamrock-trading-bot.git
cd shamrock-trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your values:

```env
# Wallets (NEVER share private keys)
WALLET_PRIVATE_KEY_PRIMARY=your_key_here
WALLET_ADDRESS_PRIMARY=0x3eb320fad3f51fe4f2a4531f911ef56694346eef

WALLET_PRIVATE_KEY_B=your_key_here
WALLET_ADDRESS_B=0x0835eb8447f3ac90351951bb5d22e77afd9b81c0

WALLET_PRIVATE_KEY_C=your_key_here
WALLET_ADDRESS_C=0x32a71a0b8f10f263cd5d3fd8802fd9683ae6c860

# RPC Endpoints
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
ETH_RPC_MEV_PROTECTED=https://rpc.flashbots.net

# Trading
MODE=paper   # ← START HERE. Switch to 'live' only after testing.
MAX_POSITION_SIZE_PERCENT=2.0
STOP_LOSS_PERCENT=10.0
CIRCUIT_BREAKER_PERCENT=15.0
```

> See [MANUS_PROJECT_INSTRUCTIONS.md](./MANUS_PROJECT_INSTRUCTIONS.md) for the full `.env` reference with all available parameters.
> See [GUARDRAILS.md](./GUARDRAILS.md) for the mandatory pre-live safety checklist.

---

## 📖 Usage

### Paper Trading (Dry Run)
```bash
# Scan for gems (no trades executed)
python main.py --scan

# Run paper trading simulation
python scripts/paper_trade.py
```

### Live Trading
```bash
# ⚠️ Only after thorough paper testing!
# Set MODE=live in .env, then:
python main.py
```

### CLI Commands
```bash
python main.py                          # Run full bot loop (paper mode by default)
python main.py --balances               # Fetch and print wallet balances only
python main.py --scan                   # Run one gem scan cycle and print results
python main.py --snipe <addr> <chain>   # Test gem snipe for a specific token
python main.py --analyze <addr> <chain> # Run TA + Fibonacci analysis (no trade)
python main.py --positions              # Show all open positions and PnL
```

### Dashboard
```bash
# Launch Reflex portfolio dashboard
reflex run --env prod
```

---

## 🏗 Architecture

```
┌─────────────────────┐     ┌────────────────────┐     ┌─────────────────┐
│   GEM SCANNER       │     │   SIGNAL ENGINE    │     │  GEM SNIPE      │
│                     │     │                    │     │  STRATEGY       │
│ • DexScreener (5)   │────→│ ≥24 candles:       │────→│                 │
│ • Moralis Money Pro │     │   Full TA pipeline │     │ • Fib alignment │
│ • Moralis Intel     │     │   (29 indicators)  │     │ • Signal gate   │
│ • Binance Pulse     │     │                    │     │ • TP/SL levels  │
│ • Grok/X Trending   │     │ <24 candles:       │     └────────┬────────┘
│ • Pump.fun Grads    │     │   🔬 Micro-cap     │              │
│ • Whale Accumulation│     │   (gem+enrichment) │     ┌────────▼────────┐
│                     │     └────────────────────┘     │  WALLET ROUTER  │
│ 7-LAYER SAFETY      │                                │                 │
│ ├─ GoPlus           │     ┌────────────────────┐     │ • Kelly sizing  │
│ ├─ Honeypot.is      │     │   MACRO REGIME     │     │ • Phase scaling │
│ ├─ TokenSniffer     │     │                    │     │ • RL sizer adj  │
│ ├─ RugCheck (SOL)   │     │ BTC/ETH/SOL trends │     │ • Chain slippage│
│ ├─ ChainAware       │     │ Fear & Greed Index │     └────────┬────────┘
│ ├─ Perplexity AI    │     │ ↓ BULL/BEAR/NEUTRAL│              │
│ └─ CoinPaprika ATH  │     └────────────────────┘     ┌────────▼────────┐
└─────────────────────┘                                │  TRADE EXECUTOR │
                                                       │                 │
┌─────────────────┐     ┌──────────────────┐           │ • Jupiter (SOL) │
│   DASHBOARD     │←────│ POSITION MONITOR │←── Trades─│ • 1inch (EVM)   │
│   (Streamlit)   │     │                  │           │ • Flashbots MEV │
│   9 pages       │     │ • Multi-tier TP  │           │ • Hyperliquid   │
└─────────────────┘     │ • Trailing stops │           │   (perps)       │
                        │ • Pyramid scaling│           └─────────────────┘
┌─────────────────┐     │ • Fast fail      │
│   COPY-TRADE    │     └──────────────────┘    ┌─────────────────┐
│   PIPELINE      │                             │   ML LAYER      │
│                 │                             │                 │
│ • Wallet Monitor│                             │ • TimesFM 200M  │
│ • Moralis Stream│                             │ • RL Pos Sizer  │
│ • Whale Discover│                             │ • XGBoost Optim │
│ • Fastlane Queue│                             └─────────────────┘
└─────────────────┘
```

### Trade Pipeline Flow
```
Scanner (9+ sources) → 14-Signal Scoring → 7-Layer Safety Gate → 29-Indicator TA
        → Macro Regime Filter → TimesFM Forecast → Strategy Gate
        → RL Position Sizer → Offensive Guardrails → Wallet Router → Executor
```

### Copy-Trade Pipeline Flow
```
Alpha Wallet Monitor (30s polling) + Moralis Streams (push webhook)
    → Signal Enrichment → GemScanner Scoring (≥65 threshold)
    → Safety Check → Risk Gate → Fastlane Queue → Executor
    → Latency tracking + SLO alerts
```

### Wallet Strategy Assignment
| Wallet | Profile | Min Score | Max Position | Role |
|--------|---------|-----------|-------------|------|
| **Primary** | Conservative | 58.0 | 10% of wallet | Steady gem sniping across all chains |
| **Wallet B** | Nuclear | 72.0 | 25% of wallet | Aggressive bets on high-conviction setups |
| **Wallet C** | Paycheck (Cold) | — | — | Profit vault + cold storage (manual only) |

---

## 🛡️ Risk Management

| Rule | Default | Configurable |
|------|---------|-------------|
| Max position size (Conservative) | 10% of wallet | ✅ `MAX_POSITION_SIZE_PERCENT` |
| Max position size (Nuclear) | 25% of wallet | ✅ via `StrategyProfile` |
| **EV-Aware Kelly Sizing** | Active (Scales dynamically based on R/R and Est. WR) | 🔒 Hardcoded |
| Max concurrent positions | 5 (Conservative) / 3 (Nuclear) | ✅ `MAX_CONCURRENT_POSITIONS` |
| Trailing stop-loss | 20% (Conservative) / 28% (Nuclear) | ✅ `STOP_LOSS_PERCENT` |
| **Stop Loss Order Type** | **Market Trigger** (Protects vs slippage) | 🔒 Hardcoded |
| **Emergency SL Guard** | **No-SL = No-Trade** (Insta-close if SL fails) | 🔒 Hardcoded |
| Take-profit exits (Conservative) | 40% @ 1.5x, 35% @ 2.5x, 25% @ 5x | ✅ `StrategyProfile` |
| Take-profit exits (Nuclear) | 20% @ 5x, 25% @ 12x, 20% @ 30x, ride 35% | ✅ `StrategyProfile` |
| Circuit breaker | Halt at -15% daily | ✅ `CIRCUIT_BREAKER_PERCENT` |
| Gas ceiling | 50 gwei max | ✅ `MAX_GAS_GWEI` |
| Daily loss limit | 0.5 ETH (Primary) / 2.0 ETH (Nuclear) | ✅ `DAILY_LOSS_LIMIT_ETH` |
| Token approvals | Exact amounts only | 🔒 Hardcoded (security) |
| Honeypot check | Required pre-trade | 🔒 Hardcoded (security) |
| Solana quality gate | $30K liq / $200K mcap / score ≥75 / age ≥30m | 🔒 Hardcoded |

---

## 🗂 Project Structure

```
shamrock-trading-bot/
├── main.py                # Entry point + CLI (--balances, --scan, --snipe, --analyze, --positions)
├── config/                # Settings (200+ params), chain configs, wallet profiles, token lists, builder codes
├── core/                  # 30 modules — balance fetcher, safety pipeline, executor, risk manager,
│   │                      #   position monitor, wallet monitor, wallet router, signal engine,
│   │                      #   offensive guardrails, regime filter, capital compounder,
│   │                      #   sniper discovery, Moralis streams, Hyperliquid executor,
│   │                      #   bluechip anchor, daily floor guardian, MEV protection,
│   │                      #   moonshot allocator, portfolio rebalancer, research report, etc.
│   ├── wallet_monitor.py  # Alpha wallet copy-trade daemon (30s polling cycle)
│   ├── moralis_streams.py # Moralis Streams webhook server (push-based copy-detection)
│   ├── sniper_discovery.py # Proactive whale/sniper wallet discovery (6h cycle)
│   └── ...
├── data/
│   ├── models.py          # Token, GemCandidate, Trade, Position, SignalScore, CopyTradeSignal
│   └── providers/         # 28 data providers — DexScreener, Moralis (6 modules), GoPlus,
│                          #   Honeypot, TokenSniffer, Helius, ChainAware, CoinPaprika,
│                          #   Perplexity, Binance Pulse, Grok/X, CoinGecko, DefiLlama,
│                          #   Smart Money, Holder Analysis, Copycat Detector, etc.
├── scanner/               # Gem discovery engine (14-signal scoring + 29-indicator TA, 0–100)
│   ├── gem_scanner.py     # Core scanning pipeline (1,900 lines)
│   ├── watchlist.py       # EMA-smoothed watchlist score tracking
│   └── swing_scanner.py   # Blue-chip swing/scalp scanner
├── strategies/            # Trading strategies — GemSnipeStrategy, SwingStrategy,
│                          #   Fibonacci analysis, indicator engine (1,800 lines), signal scorer
├── ml/                    # Machine learning — TimesFM forecaster, RL position sizer,
│                          #   XGBoost weight optimizer
├── notifications/         # Slack & Telegram alert modules
├── dashboard/             # Streamlit portfolio UI (9 pages)
│   ├── app.py             # Main dashboard app
│   ├── state.py           # Bot state reader/writer (shared with main bot via JSON)
│   ├── styles.py          # Custom CSS theming
│   └── pages/             # 9 pages (Gem Scanner, Analytics, Gem Advisor, Positions,
│                          #   System Health, Wallet Overview, Alpha Wallets, Sniper Wallets,
│                          #   Paycheck Wallet)
├── scripts/               # Backtest, paper trade, profit sweep, health check, preflight,
│                          #   rollback, reviewer, AVAX/Base USDC deployers
├── memory/                # Self-improving agent memory (semantic + episodic + working)
├── tests/                 # Unit & integration tests
├── docs/                  # 38 behavioral documents (see below)
├── reports/               # Generated scan reports (JSON)
├── vendor/                # Vendored dependencies
├── logs/                  # Trade, scanner, safety, and error logs (gitignored)
├── output/                # JSON output files — balances, scan results (gitignored)
├── Dockerfile
├── docker-compose.yml     # 5 services: bot, paper-trader, db, dashboard, health
├── GUARDRAILS.md          # ← Safety rules + pre-live checklist (READ FIRST)
├── SECURITY.md            # Security policy + key handling
├── DEPLOYMENT.md          # Hetzner VPS setup + Docker deploy guide
├── CONTRIBUTING.md        # Dev workflow, code standards, roadmap
├── CURRENT_STATUS.md      # Living status document — pipeline state, config, key files
└── OFFENSIVE_GUARDRAILS_DESIGN.md  # Offensive guardrails architecture + rationale
```

---

## 📋 Key Documentation

| Document | Purpose |
|----------|--------|
| [GUARDRAILS.md](./GUARDRAILS.md) | **Read before going live** — safety pipeline, risk rules, pre-live checklist |
| [SECURITY.md](./SECURITY.md) | Private key handling, vulnerability reporting, security architecture |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Hetzner VPS setup, Docker deploy, monitoring, log rotation |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Dev workflow, code standards, adding chains/providers, roadmap |
| [CURRENT_STATUS.md](./CURRENT_STATUS.md) | Living architecture document — current pipeline state, configs, key files |
| [MANUS_PROJECT_INSTRUCTIONS.md](./MANUS_PROJECT_INSTRUCTIONS.md) | Full project spec, API references, phase-by-phase build guide |
| [OFFENSIVE_GUARDRAILS_DESIGN.md](./OFFENSIVE_GUARDRAILS_DESIGN.md) | Offensive guardrails architecture + design rationale |

---

## 📚 Reference & Inspiration

Built studying the best in the ecosystem:

| Project | Why | Link |
|---------|-----|------|
| **freqtrade** | Most mature Python trading bot — backtesting, ML, Telegram | [GitHub](https://github.com/freqtrade/freqtrade) |
| **Hummingbot** | DEX + CEX market making, great architecture | [GitHub](https://github.com/coinalpha/hummingbot) |
| **OctoBot** | Modular plugin system, built-in UI | [GitHub](https://github.com/Drakkar-Software/OctoBot) |
| **jesse** | Clean strategy framework, excellent docs | [GitHub](https://github.com/jesse-ai/jesse) |
| **awesome-crypto-trading-bots** | Curated list of tools, libraries, and bots | [GitHub](https://github.com/botcrypto-io/awesome-crypto-trading-bots) |
| **OpenAlice** | AI-driven quantitative trading, dynamic tuning ("Trading-as-Git") | [GitHub](https://github.com/TraderAlice/OpenAlice) |

---

## 🏗️ Infrastructure — Always On, Always Trading

The bot runs **24/7/365** on a dedicated **Hetzner Cloud** VPS in the EU. It is always scanning, always scoring, and always executing.

| Property | Value |
|----------|-------|
| **Server** | CX33 — 4 vCPU / 8 GB RAM / 80 GB NVMe SSD |
| **Server ID** | #142997655 |
| **IP** | `46.62.231.43` |
| **Location** | Helsinki, Finland (EU, datacenter `hel1-dc2`) |
| **OS** | Ubuntu 24.04 LTS |
| **Runtime** | Docker + docker-compose |
| **Auto-restart** | `restart: unless-stopped` |
| **Cost** | €8.99/mo (~$10/mo) |
| **Backups** | Automated daily (€1.80/mo) |
| **Firewall** | Hetzner Cloud Firewall (SSH + dashboards + ICMP) |
| **Security** | fail2ban + unattended-upgrades |
| **Status** | 🟢 **ON** |

### Docker Services
| Container | Purpose | Port |
|-----------|---------|------|
| `shamrock-bot` | Main trading bot (LIVE mode) | 8787 (Moralis Streams webhook) |
| `shamrock-dashboard` | Reflex portfolio UI | 3000 |
| `shamrock-health` | 5-minute health check cron | — |
| `shamrock-db` | Shared data volume (Alpine + SQLite) | — |
| `shamrock-paper` | Paper trading mode (opt-in profile) | — |

### Operational Model
- The bot **never sleeps** — it scans every 60 seconds across active chains (Solana, Base, BSC, Avalanche, + ETH/ARB/POLY available)
- Alpha wallet monitor polls every 30 seconds for copy-trade signals
- Moralis Streams webhook server ingests whale/liquidity events in real-time
- Proactive whale discovery runs every 6 hours to expand the alpha wallet pool
- TimesFM forecaster confirms directional bias before entry
- RL position sizer retrains every 24 hours on completed trades
- Heartbeat emitted every 5 minutes to confirm liveness
- Circuit breaker auto-triggers on 15% portfolio drawdown
- Kill switch available via `MODE=paper` in `.env` or process termination
- Slack + Telegram alerts on every trade, error, score change, and daily summary

See [DEPLOYMENT.md](./DEPLOYMENT.md) for SSH access, update procedures, and monitoring setup.

---

## 📖 Behavioral Documentation (38 Docs)

The `docs/` directory contains **38 detailed behavioral documents** that define exactly how the bot thinks, trades, and protects capital:

| Category | Documents |
|----------|-----------| 
| **Core** | [IDENTITY](docs/IDENTITY.md) · [SYSTEM](docs/SYSTEM.md) · [RULES](docs/RULES.md) |
| **Trading** | [STRATEGIES](docs/STRATEGIES.md) · [SIGNALS](docs/SIGNALS.md) · [EXCHANGES](docs/EXCHANGES.md) · [TOOLS](docs/TOOLS.md) |
| **Risk** | [RISK_MANAGEMENT](docs/RISK_MANAGEMENT.md) · [POSITION_SIZING](docs/POSITION_SIZING.md) · [MAX_DRAWDOWN_RULES](docs/MAX_DRAWDOWN_RULES.md) · [DAILY_LOSS_LIMITS](docs/DAILY_LOSS_LIMITS.md) · [EXPOSURE_LIMITS](docs/EXPOSURE_LIMITS.md) |
| **Execution** | [ORDER_EXECUTION](docs/ORDER_EXECUTION.md) · [SLIPPAGE_RULES](docs/SLIPPAGE_RULES.md) · [LIQUIDITY_FILTERS](docs/LIQUIDITY_FILTERS.md) · [VOLATILITY_RULES](docs/VOLATILITY_RULES.md) |
| **Operations** | [PAPER_TRADING](docs/PAPER_TRADING.md) · [LIVE_TRADING](docs/LIVE_TRADING.md) · [BACKTESTING](docs/BACKTESTING.md) · [MARKET_REGIMES](docs/MARKET_REGIMES.md) · [OFFENSIVE_PLAYBOOK](docs/OFFENSIVE_PLAYBOOK.md) |
| **Safety** | [FAILSAFES](docs/FAILSAFES.md) · [KILL_SWITCH](docs/KILL_SWITCH.md) · [SECRETS_HANDLING](docs/SECRETS_HANDLING.md) · [ERRORS_AND_RECOVERY](docs/ERRORS_AND_RECOVERY.md) |
| **Monitoring** | [HEARTBEAT](docs/HEARTBEAT.md) · [STATE](docs/STATE.md) · [MEMORY](docs/MEMORY.md) · [TRADE_JOURNAL](docs/TRADE_JOURNAL.md) · [MODEL_EVALUATION](docs/MODEL_EVALUATION.md) |
| **Guides** | [UPGRADES](docs/UPGRADES.md) · [RUNBOOK_PHASE4](docs/RUNBOOK_PHASE4.md) · [AVAX_REBALANCE](docs/AVAX_REBALANCE.md) · [BASE_USDC_DEPLOY](docs/BASE_USDC_DEPLOY.md) |
| **Meta** | [PARAMETERS](docs/PARAMETERS.md) · [CHANGELOG](docs/CHANGELOG.md) |

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-strategy`)
3. Commit your changes (`git commit -m 'Add amazing strategy'`)
4. Push to the branch (`git push origin feature/amazing-strategy`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see [LICENSE](./LICENSE) for details.

---

<p align="center">
  <strong>☘️ Shamrock Trading Bot</strong><br/>
  <em>Always on. Always scanning. Zero tolerance for rugs. Let's find gems.</em> 💎
</p>
