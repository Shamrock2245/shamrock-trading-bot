<p align="center">
  <img src="https://img.shields.io/badge/☘️-Shamrock_Trading_Bot-00C853?style=for-the-badge&labelColor=1a1a2e" alt="Shamrock Trading Bot" />
</p>

<h1 align="center">Shamrock Trading Bot</h1>

<p align="center">
  <strong>AI-powered multi-wallet crypto trading bot — gem discovery, MEV-protected execution, and automated portfolio management.<br/>Always on. Always scanning. Always compounding. 24/7/365.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/status-🟢%20LIVE%2024%2F7-00C853?style=flat-square" alt="Status" />
  <img src="https://img.shields.io/badge/chains-ETH%20%7C%20Base%20%7C%20ARB%20%7C%20POLY%20%7C%20BSC%20%7C%20SOL-blue?style=flat-square" alt="Chains" />
  <img src="https://img.shields.io/badge/infra-Hetzner%20CPX21-red?style=flat-square" alt="Infra" />
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

### 🔍 Gem Discovery Engine
- Multi-chain token scanner (Ethereum, Base, Arbitrum, Polygon, BSC, **Solana**)
- Real-time new pair detection via [DexScreener API](https://docs.dexscreener.com/api/reference)
- Token scoring system (0–100) — volume spikes, liquidity depth, holder distribution, social signals
- Boosted token tracking — community hype detection
- Smart money wallet tracking — follow the alpha

### 🛡️ Safety First
- **Honeypot detection** — [GoPlus Security](https://gopluslabs.io/) + [Honeypot.is](https://honeypot.is/) pre-trade checks
- **Rug pull protection** — contract verification, tax analysis, owner permissions audit
- **MEV protection** — all trades routed through [Flashbots Protect](https://docs.flashbots.net/flashbots-protect/overview) / [MEV Blocker](https://mevblocker.io/)
- **Circuit breakers** — auto-halt trading on 15% portfolio drawdown
- **Exact token approvals** — never unlimited spending

### 📊 Technical Analysis
- 10+ indicators via [pandas-ta](https://github.com/twopirllc/pandas-ta) — RSI, MACD, Bollinger Bands, EMA crossovers, VWAP, ADX
- Composite signal scoring — weighted trend, momentum, volume, and on-chain signals
- On-chain analytics — holder growth, whale accumulation, DEX volume ratios

### ⚡ Trade Execution
- Multi-wallet support (3 wallets, distinct strategies per wallet)
- [1inch](https://portal.1inch.dev/) DEX aggregation for best swap prices
- EIP-1559 gas optimization with configurable gas ceiling
- Staged take-profit exits (50% at 2x, 25% at 5x, ride the rest)
- Trailing + hard stop-loss enforcement

### 📈 Portfolio Dashboard
- Real-time portfolio tracking across all wallets
- P&L reports (daily, weekly, monthly)
- Trade history with full audit trail (CSV export)
- Streamlit-powered UI with [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts)

### 🔔 Notifications
- Slack multi-channel alerts — gems, trades, stop-losses, circuit breakers
- Telegram bot integration (optional)
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
python -m core.scanner

# Run paper trading simulation
python scripts/paper_trade.py
```

### Live Trading
```bash
# ⚠️ Only after thorough paper testing!
# Set MODE=live in .env, then:
python main.py
```

### Backtesting
```bash
# Backtest a strategy on historical data
python scripts/backtest.py --strategy momentum --days 30

# Backtest with ML features (Phase 5)
python ml/backtest_ml.py --strategy gem_snipe --days 60
```

### Dashboard
```bash
# Launch Streamlit portfolio dashboard
streamlit run dashboard/app.py
```

---

## 🏗 Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐    ┌──────────────────┐
│ Gem Scanner  │───→│ Signal Generator │───→│  Risk Check  │───→│ Trade Executor   │
│              │    │                  │    │              │    │                  │
│ • DexScreener│    │ • RSI / MACD     │    │ • Position   │    │ • 1inch / Uni V3 │
│ • CoinGecko  │    │ • EMA crossovers │    │   sizing     │    │ • Flashbots RPC  │
│ • GoPlus     │    │ • Volume spikes  │    │ • Stop-loss  │    │ • Multi-wallet   │
│ • On-chain   │    │ • On-chain       │    │ • Circuit    │    │ • Gas optimized  │
└──────────────┘    └──────────────────┘    │   breaker    │    └────────┬─────────┘
                                            └──────────────┘             │
                                                                    ┌────▼─────────┐
┌──────────────┐                                                    │  Blockchain  │
│  Dashboard   │←── Portfolio Manager ←── Trade Logs ←──────────────│  (ETH/Base/  │
│  (Streamlit) │                                                    │   ARB/POLY)  │
└──────────────┘                                                    └──────────────┘
```

### Wallet Strategy Assignment
| Wallet | Strategies | Chains | Role |
|--------|-----------|--------|------|
| **Primary** | Gem sniping, Momentum | ETH, Base | Active trading |
| **Wallet B** | DCA, Mean reversion | ARB, Polygon | Steady accumulation |
| **Wallet C** | Long-term holds | ETH | Profit vault + cold storage |

---

## 🛡️ Risk Management

| Rule | Default | Configurable |
|------|---------|-------------|
| Max position size | 2% of wallet | ✅ `MAX_POSITION_SIZE_PERCENT` |
| Max concurrent positions | 10 per wallet | ✅ `MAX_CONCURRENT_POSITIONS` |
| Trailing stop-loss | 10% from peak | ✅ `STOP_LOSS_PERCENT` |
| Hard stop-loss | 25% from entry | ✅ `HARD_STOP_LOSS_PERCENT` |
| Take-profit exits | 50% @ 2x, 25% @ 5x | ✅ `TAKE_PROFIT_1X`, `TAKE_PROFIT_2X` |
| Circuit breaker | Halt at -15% daily | ✅ `CIRCUIT_BREAKER_PERCENT` |
| Gas ceiling | 50 gwei max | ✅ `MAX_GAS_GWEI` |
| Daily loss limit | 0.5 ETH per wallet | ✅ `DAILY_LOSS_LIMIT_ETH` |
| Token approvals | Exact amounts only | 🔒 Hardcoded (security) |
| Honeypot check | Required pre-trade | 🔒 Hardcoded (security) |

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

> See [MANUS_PROJECT_INSTRUCTIONS.md](./MANUS_PROJECT_INSTRUCTIONS.md) for the complete build guide, API references, and phase-by-phase instructions.

---

## 🗂 Project Structure

```
shamrock-trading-bot/
├── main.py           # Entry point + CLI (--balances, --scan, --snipe)
├── config/           # Settings, chain configs, wallet assignment, token lists
├── core/             # Balance fetcher, safety pipeline, executor, risk manager
├── data/
│   ├── models.py     # Token, GemCandidate, Trade, Position, SignalScore
│   └── providers/    # DexScreener, CoinGecko, GoPlus, 1inch, Honeypot.is
├── scanner/          # Gem discovery + scoring engine (0–100)
├── strategies/       # Trading strategies (gem snipe, DCA, momentum, etc.)
├── ml/               # Machine learning models & feature engineering
├── notifications/    # Slack & Telegram alert modules
├── dashboard/        # Streamlit portfolio UI
├── scripts/          # Backtest, paper trade, profit sweep, health check
├── tests/            # Unit & integration tests
├── logs/             # Trade, scanner, safety, and error logs (gitignored)
├── output/           # JSON output files — balances, scan results (gitignored)
├── Dockerfile
├── docker-compose.yml
├── GUARDRAILS.md     # ← Safety rules + pre-live checklist (READ FIRST)
├── SECURITY.md       # Security policy + key handling
├── DEPLOYMENT.md     # Hetzner VPS setup + Docker deploy guide
└── CONTRIBUTING.md   # Dev workflow, code standards, roadmap
```

---

## 📋 Key Documentation

| Document | Purpose |
|----------|--------|
| [GUARDRAILS.md](./GUARDRAILS.md) | **Read before going live** — safety pipeline, risk rules, pre-live checklist |
| [SECURITY.md](./SECURITY.md) | Private key handling, vulnerability reporting, security architecture |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Hetzner VPS setup, Docker deploy, monitoring, log rotation |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Dev workflow, code standards, adding chains/providers, roadmap |
| [MANUS_PROJECT_INSTRUCTIONS.md](./MANUS_PROJECT_INSTRUCTIONS.md) | Full project spec, API references, phase-by-phase build guide |

---

## 🏗️ Infrastructure — Always On, Always Trading

The bot runs **24/7/365** on a dedicated **Hetzner Cloud** VPS. It is always scanning, always scoring, and always executing.

| Property | Value |
|----------|-------|
| **Server** | CPX21 — 3 vCPU / 4 GB RAM / 80 GB SSD |
| **Server ID** | #124347708 |
| **IP** | `5.161.126.32` |
| **Location** | Ashburn, VA (us-east, datacenter `ash-dc1`) |
| **OS** | Ubuntu 22.04 LTS |
| **Runtime** | Docker + docker-compose |
| **Auto-restart** | `restart: unless-stopped` |
| **Cost** | $9.99/mo |
| **Status** | 🟢 **ON** |

### Operational Model
- The bot **never sleeps** — it scans every 15 seconds across 6 chains
- Heartbeat emitted every 5 minutes to confirm liveness
- Circuit breaker auto-triggers on 15% portfolio drawdown
- Kill switch available via `MODE=paper` in `.env` or process termination
- Slack alerts on every trade, error, and daily summary

See [DEPLOYMENT.md](./DEPLOYMENT.md) for SSH access, update procedures, and monitoring setup.

---

## 📖 Behavioral Documentation (31 Docs)

The `docs/` directory contains **31 detailed behavioral documents** that define exactly how the bot thinks, trades, and protects capital:

| Category | Documents |
|----------|-----------|
| **Core** | [IDENTITY](docs/IDENTITY.md) · [SYSTEM](docs/SYSTEM.md) · [RULES](docs/RULES.md) |
| **Trading** | [STRATEGIES](docs/STRATEGIES.md) · [SIGNALS](docs/SIGNALS.md) · [EXCHANGES](docs/EXCHANGES.md) · [TOOLS](docs/TOOLS.md) |
| **Risk** | [RISK_MANAGEMENT](docs/RISK_MANAGEMENT.md) · [POSITION_SIZING](docs/POSITION_SIZING.md) · [MAX_DRAWDOWN_RULES](docs/MAX_DRAWDOWN_RULES.md) · [DAILY_LOSS_LIMITS](docs/DAILY_LOSS_LIMITS.md) · [EXPOSURE_LIMITS](docs/EXPOSURE_LIMITS.md) |
| **Execution** | [ORDER_EXECUTION](docs/ORDER_EXECUTION.md) · [SLIPPAGE_RULES](docs/SLIPPAGE_RULES.md) · [LIQUIDITY_FILTERS](docs/LIQUIDITY_FILTERS.md) · [VOLATILITY_RULES](docs/VOLATILITY_RULES.md) |
| **Operations** | [PAPER_TRADING](docs/PAPER_TRADING.md) · [LIVE_TRADING](docs/LIVE_TRADING.md) · [BACKTESTING](docs/BACKTESTING.md) · [MARKET_REGIMES](docs/MARKET_REGIMES.md) |
| **Safety** | [FAILSAFES](docs/FAILSAFES.md) · [KILL_SWITCH](docs/KILL_SWITCH.md) · [SECRETS_HANDLING](docs/SECRETS_HANDLING.md) · [ERRORS_AND_RECOVERY](docs/ERRORS_AND_RECOVERY.md) |
| **Monitoring** | [HEARTBEAT](docs/HEARTBEAT.md) · [STATE](docs/STATE.md) · [MEMORY](docs/MEMORY.md) · [TRADE_JOURNAL](docs/TRADE_JOURNAL.md) · [MODEL_EVALUATION](docs/MODEL_EVALUATION.md) |
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
