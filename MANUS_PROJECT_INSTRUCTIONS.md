# 🤖 Shamrock Trading Bot — Manus Project Instructions

> **Goal**: Build an AI-powered crypto trading bot that discovers undervalued gems, executes trades, and manages a portfolio — all targeting the wallet below.

---

## 🔑 Wallet & Chain Info

| Key | Value |
|-----|-------|
| **Wallet Address** | `0x3eb320fad3f51fe4f2a4531f911ef56694346eef` |
| **Primary Chain** | Ethereum / EVM-compatible (Base, Arbitrum, Polygon, BSC) |
| **Wallet Type** | MetaMask-style EOA (Externally Owned Account) |

> [!CAUTION]
> Never hardcode the private key. Use environment variables (`WALLET_PRIVATE_KEY`) or a secure vault. The public address above is safe to reference in code.

---

## 📋 What to Build

### Phase 1 — Gem Discovery Engine
Build a scanner that finds new/undervalued tokens before they pump.

**Data Sources to Wire Up:**
- [DexScreener API](https://docs.dexscreener.com/api/reference) — Real-time DEX pairs, new listings, volume spikes
- [CoinGecko API](https://www.coingecko.com/en/api) — Market cap, historical data, trending
- [Bitquery](https://bitquery.io/) — On-chain DEX trade data, whale movements
- [undervalued-crypto-finder](https://github.com/Erfaniaa/undervalued-crypto-finder) — Coins below MA200 (use this as inspiration)

**Scanning Criteria:**
- New token launches (< 24h old) on Uniswap, SushiSwap, PancakeSwap, Aerodrome (Base)
- Volume spike detection (>300% increase in 1h)
- Liquidity pool depth analysis (minimum $50K liquidity)
- Contract verification status (reject unverified / honeypot contracts)
- Holder distribution analysis (flag if top 10 wallets hold >60%)
- Social signal scraping (Twitter/X mentions, Telegram group size)

### Phase 2 — Technical Analysis & Signals
Implement TA indicators for entry/exit signals.

**Recommended Libraries:**
- [pandas-ta](https://github.com/twopirllc/pandas-ta) — 120+ indicators, Python (RECOMMENDED)
- [ta](https://github.com/bukosabino/ta) — Feature engineering from OHLCV data
- [ccxt](https://github.com/ccxt/ccxt) — Unified exchange API (120+ exchanges)
- [finta](https://github.com/peerchemist/finta) — Financial indicators in Pandas

**Indicators to Implement:**
- RSI (14-period) — Buy < 30, Sell > 70
- MACD crossover signals
- Bollinger Bands squeeze detection
- Volume-weighted average price (VWAP)
- EMA crossovers (9/21 and 50/200)
- On-chain momentum (increasing unique holders, growing txn count)

### Phase 3 — Trade Execution Engine
Automate buying and selling using the wallet.

**Architecture:**
```
Gem Scanner ──→ Signal Generator ──→ Risk Check ──→ Execute Trade
                                         │
                                    Position Sizing
                                    Stop-Loss Logic
                                    Gas Optimization
```

**Execution Requirements:**
- Use [web3.py](https://github.com/ethereum/web3.py) or [ethers.js](https://github.com/ethers-io/ethers.js) for on-chain txns
- DEX router integration (Uniswap V3 Router, 1inch Aggregator for best prices)
- Slippage protection (max 3% default, configurable)
- Gas price optimization (use EIP-1559 fee estimation)
- Anti-MEV: Use Flashbots Protect RPC or private mempool submission
- Position sizing: Never risk more than 2% of portfolio per trade
- Trailing stop-loss: Auto-sell if price drops 10% from peak (configurable)

### Phase 4 — Portfolio Management Dashboard
Track holdings, P&L, and trade history.

**Features:**
- Real-time portfolio value (ETH + USD)
- Individual position tracking (entry price, current price, % gain/loss)
- Trade history log (CSV export)
- Daily/weekly P&L summary
- Alert system (Slack webhook or Telegram bot notification)
- Charting with [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts)

---

## 🏗 Tech Stack Recommendations

| Layer | Recommended | Alternatives |
|-------|------------|--------------|
| **Language** | Python 3.11+ | TypeScript/Node.js |
| **Exchange Data** | [ccxt](https://github.com/ccxt/ccxt) | Exchange-specific SDKs |
| **On-chain Execution** | web3.py / ethers.js | viem |
| **Technical Analysis** | pandas-ta | ta-lib, finta |
| **DEX Aggregation** | 1inch API / Uniswap SDK | Paraswap, 0x API |
| **Data Storage** | SQLite (local) → PostgreSQL (prod) | MongoDB |
| **Scheduling** | APScheduler / cron | Celery |
| **Notifications** | Slack webhooks / Telegram Bot | Discord |
| **Dashboard** | Streamlit or Next.js | Grafana |

---

## 📦 Reference Repository

**USE THIS AS YOUR PRIMARY REFERENCE:**
> 🔗 [https://github.com/botcrypto-io/awesome-crypto-trading-bots](https://github.com/botcrypto-io/awesome-crypto-trading-bots)

### Top Open-Source Bots to Study & Borrow From:
| Bot | Why It's Useful | Link |
|-----|----------------|------|
| **freqtrade** | Most mature Python bot — backtesting, ML, Telegram control | [GitHub](https://github.com/freqtrade/freqtrade) |
| **Hummingbot** | DEX + CEX market making, great architecture | [GitHub](https://github.com/coinalpha/hummingbot) |
| **jesse** | Advanced strategy framework, clean API | [GitHub](https://github.com/jesse-ai/jesse) |
| **OctoBot** | Fully modular, plugin-based, great UI | [GitHub](https://github.com/Drakkar-Software/OctoBot) |
| **OpenTrader** | GRID + DCA strategies, 100+ exchanges via CCXT | [GitHub](https://github.com/bludnic/opentrader) |
| **Intelligent Trading Bot** | ML-based signal generation | [GitHub](https://github.com/asavinov/intelligent-trading-bot) |
| **the0** | Multi-language strategy engine, containerized | [GitHub](https://github.com/alexanderwanyoike/the0) |

### Useful Utility Repos:
| Tool | Purpose | Link |
|------|---------|------|
| **undervalued-crypto-finder** | Find coins below MA200 | [GitHub](https://github.com/Erfaniaa/undervalued-crypto-finder) |
| **financial-dataset-generator** | Generate ML training datasets | [GitHub](https://github.com/Erfaniaa/financial-dataset-generator) |
| **crypto-trading-strategy-backtester** | Quick strategy backtesting | [GitHub](https://github.com/Erfaniaa/crypto-trading-strategy-backtester) |
| **OrderBooks** | Orderbook snapshot management | [GitHub](https://github.com/tiagosiebler/OrderBooks) |

---

## ⚙️ Configuration & Environment

Create a `.env` file (NEVER commit this):

```env
# Wallet
WALLET_PRIVATE_KEY=your_private_key_here
WALLET_ADDRESS=0x3eb320fad3f51fe4f2a4531f911ef56694346eef

# RPC Endpoints (get free keys from Alchemy/Infura)
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
ARB_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY

# API Keys
DEXSCREENER_API_KEY=optional_if_free_tier
COINGECKO_API_KEY=your_key
ETHERSCAN_API_KEY=your_key

# Notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
TELEGRAM_BOT_TOKEN=optional

# Trading Parameters
MAX_POSITION_SIZE_ETH=0.1
MAX_SLIPPAGE_PERCENT=3.0
STOP_LOSS_PERCENT=10.0
MIN_LIQUIDITY_USD=50000
```

---

## 🚨 Safety Rules (NON-NEGOTIABLE)

1. **NEVER** commit private keys or `.env` to git
2. **ALWAYS** start with paper trading / simulation mode before going live
3. **NEVER** approve unlimited token spending — use exact amounts
4. **ALWAYS** verify contract addresses against known token lists
5. **IMPLEMENT** circuit breakers: halt trading if portfolio drops >15% in 24h
6. **LOG** every transaction with timestamp, gas cost, and reasoning
7. **CHECK** for honeypot/rug indicators before any trade (use [honeypot.is](https://honeypot.is/) API)
8. **RATE LIMIT** API calls to avoid bans (respect each provider's limits)

---

## 📁 Suggested Project Structure

```
shamrock-trading-bot/
├── .env                    # Secrets (gitignored)
├── .gitignore
├── README.md
├── requirements.txt        # Python dependencies
├── config/
│   ├── settings.py         # Trading parameters, thresholds
│   └── chains.py           # Chain configs (RPC URLs, router addresses)
├── core/
│   ├── scanner.py          # Gem discovery engine
│   ├── analyzer.py         # Technical analysis signals
│   ├── executor.py         # Trade execution (web3 txns)
│   ├── portfolio.py        # Portfolio tracking & P&L
│   └── risk.py             # Position sizing, stop-loss, circuit breakers
├── data/
│   ├── providers.py        # DexScreener, CoinGecko, Bitquery wrappers
│   └── models.py           # Data models (Token, Trade, Position)
├── strategies/
│   ├── base.py             # Abstract strategy class
│   ├── momentum.py         # Momentum-based gem strategy
│   ├── mean_reversion.py   # Buy dips on established tokens
│   └── new_listing.py      # Snipe new DEX listings
├── notifications/
│   ├── slack.py            # Slack webhook alerts
│   └── telegram.py         # Telegram bot alerts
├── dashboard/
│   └── app.py              # Streamlit dashboard
├── scripts/
│   ├── backtest.py         # Run backtests on historical data
│   └── paper_trade.py      # Simulated trading mode
├── tests/
│   ├── test_scanner.py
│   ├── test_executor.py
│   └── test_risk.py
└── logs/
    └── trades.log          # Transaction history
```

---

## 🎯 Success Metrics

| Metric | Target |
|--------|--------|
| Gems discovered per day | 10-50 candidates |
| Signal accuracy (backtested) | >55% win rate |
| Average trade execution time | <5 seconds |
| Max drawdown tolerance | 15% |
| Uptime | 99%+ (systemd service or Docker) |

---

## 🏁 Getting Started — First Steps for Manus

1. **Clone the repo**: `git clone https://github.com/Shamrock2245/shamrock-trading-bot.git`
2. **Set up Python environment**: `python -m venv venv && source venv/bin/activate`
3. **Install core deps**: `pip install ccxt pandas-ta web3 python-dotenv requests aiohttp`
4. **Study the reference repo**: Browse [awesome-crypto-trading-bots](https://github.com/botcrypto-io/awesome-crypto-trading-bots) thoroughly
5. **Build the scanner first** (Phase 1) — get data flowing before building execution
6. **Paper trade only** until Phase 3 is battle-tested with backtests
7. **Push all code** to the GitHub repo as you go

**GitHub Repo**: [https://github.com/Shamrock2245/shamrock-trading-bot](https://github.com/Shamrock2245/shamrock-trading-bot)

---

*Built for Shamrock Trading. Let's find gems. 💎☘️*
