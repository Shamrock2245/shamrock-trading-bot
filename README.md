<p align="center">
  <img src="https://img.shields.io/badge/☘️-Shamrock_Trading_Bot-00C853?style=for-the-badge&labelColor=1a1a2e" alt="Shamrock Trading Bot" />
</p>

<h1 align="center">Shamrock Trading Bot</h1>

<p align="center">
  <strong>AI-powered multi-wallet crypto trading bot — gem discovery, MEV-protected execution, and automated portfolio management.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/mode-paper%20%7C%20live-orange?style=flat-square" alt="Mode" />
  <img src="https://img.shields.io/badge/chains-ETH%20%7C%20Base%20%7C%20ARB%20%7C%20POLY%20%7C%20BSC-blue?style=flat-square" alt="Chains" />
  <img src="https://img.shields.io/badge/wallets-3-blueviolet?style=flat-square" alt="Wallets" />
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
- Multi-chain token scanner (Ethereum, Base, Arbitrum, Polygon, BSC)
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
├── config/           # Settings, chain configs, wallet assignment
├── core/             # Scanner, analyzer, executor, portfolio, risk, safety
├── data/providers/   # API wrappers (DexScreener, CoinGecko, GoPlus, 1inch)
├── strategies/       # Trading strategies (gem snipe, DCA, momentum, etc.)
├── ml/               # Machine learning models & feature engineering
├── notifications/    # Slack & Telegram alert modules
├── dashboard/        # Streamlit portfolio UI
├── scripts/          # Backtest, paper trade, profit sweep, health check
├── tests/            # Unit & integration tests
└── logs/             # Trade, scanner, safety, and error logs
```

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
  <em>Three wallets. Zero tolerance for rugs. Let's find gems.</em> 💎
</p>
