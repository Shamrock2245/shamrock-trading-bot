# 🤖 Shamrock Trading Bot — Manus Project Instructions

> **Goal**: Build an AI-powered crypto trading bot that discovers undervalued gems across multiple wallets, executes trades with MEV protection, and manages portfolios — fully automated, 24/7.

---

## 🔑 Wallets & Chain Info

### Managed Wallets
| Alias | Address | Role |
|-------|---------|------|
| **Primary** | `0x3eb320fad3f51fe4f2a4531f911ef56694346eef` | Main trading wallet — gem sniping & active positions |
| **Wallet B** | `0x0835eb8447f3ac90351951bb5d22e77afd9b81c0` | Secondary wallet — DCA & mean-reversion strategies |
| **Wallet C** | `0x32a71a0b8f10f263cd5d3fd8802fd9683ae6c860` | Cold/reserve wallet — long-term holds & profit sweeps |

### Supported Chains
| Chain | Use Case | DEX Routers |
|-------|----------|-------------|
| **Ethereum** | Blue-chip tokens, high-liquidity pairs | Uniswap V3, 1inch, CoW Protocol |
| **Base** | Low-gas gem sniping, new launches | Aerodrome, Uniswap V3 (Base) |
| **Arbitrum** | Mid-cap trading, derivatives | Uniswap V3, Camelot, GMX |
| **Polygon** | Low-fee swing trades | QuickSwap, Uniswap V3 |
| **BSC** | Altcoin/memecoin scanning | PancakeSwap V3 |

> [!CAUTION]
> **NEVER** hardcode private keys. Use environment variables (`WALLET_PRIVATE_KEY_PRIMARY`, `WALLET_PRIVATE_KEY_B`, `WALLET_PRIVATE_KEY_C`) or a secure vault (AWS Secrets Manager / HashiCorp Vault). Public addresses above are safe to reference in code.

---

## 📋 What to Build

### Phase 1 — Gem Discovery Engine
Build a multi-chain scanner that finds new/undervalued tokens before they pump.

#### Data Sources to Wire Up

| Source | What It Provides | Rate Limits | Cost |
|--------|-----------------|-------------|------|
| [DexScreener API](https://docs.dexscreener.com/api/reference) | New pairs, boosted tokens, volume spikes, token profiles | 60 req/min (free) | Free |
| [CoinGecko API](https://www.coingecko.com/en/api) | Market cap, historical data, trending coins, OHLCV | 30 req/min (free) | Free / Pro |
| [Bitquery](https://bitquery.io/) | On-chain DEX trades, whale movements, token flows | Varies | Free tier + paid |
| [DeFiLlama API](https://defillama.com/docs/api) | TVL, protocol revenue, yield data | Unlimited | Free |
| [Etherscan/Basescan APIs](https://docs.etherscan.io/) | Contract verification, holder counts, token transfers | 5 req/sec (free) | Free |
| [Moralis API](https://moralis.io/) | Wallet balances, token metadata, NFT data, historical txns | Varies | Free tier |
| [GeckoTerminal API](https://www.geckoterminal.com/dex-api) | Pool data, OHLCV by pool, trending pools per chain | 30 req/min | Free |

**DexScreener Specific Endpoints to Use:**
```
GET /token-profiles/latest        → Latest token profiles (new projects)
GET /token-boosts/latest          → Currently boosted tokens (paid visibility = community hype signal)
GET /token-boosts/top             → Most boosted tokens (strongest community push)
GET /dex/search?q={query}         → Search pairs by token name/symbol
GET /dex/tokens/{addresses}       → Get pairs for specific token addresses
GET /dex/pairs/{chainId}/{pairAddress} → Detailed pair data (price, volume, liquidity, txns)
```

#### Scanning Criteria (Score Each Token 0–100)

| Signal | Weight | Threshold |
|--------|--------|-----------|
| Token age | 15% | < 24h = high score, > 7d = lower |
| Volume spike | 20% | >300% increase in 1h = hot |
| Liquidity depth | 15% | Minimum $50K, ideal >$200K |
| Contract verified | 10% | Must be verified on block explorer |
| Honeypot check | **PASS/FAIL** | Must pass — instant disqualify if fail |
| Holder distribution | 10% | Flag if top 10 wallets hold >60% |
| Buy/sell tax | 10% | Flag if tax >5% on either side |
| Social signals | 10% | Twitter mentions, TG group size, CT buzz |
| DexScreener boost status | 5% | Boosted = community investing in visibility |
| Smart money wallets | 5% | Tracked wallets buying = strong signal |

#### Honeypot & Rug Detection (MANDATORY pre-trade checks)

Run **ALL** of these before any buy:
| Tool | What It Checks | API |
|------|---------------|-----|
| [Honeypot.is](https://honeypot.is/) | Simulates buy+sell, detects honeypots | `https://api.honeypot.is/v2/IsHoneypot?address={addr}&chainID={id}` |
| [Token Sniffer](https://tokensniffer.com/) | "Smell Test" score, scam pattern matching | `https://tokensniffer.com/api/v2/tokens/{chainId}/{address}` |
| [De.Fi Scanner](https://de.fi/scanner) | Contract audit, honeypot, rug patterns (40+ chains) | Web scrape or API |
| [GoPlus Security API](https://gopluslabs.io/) | Token security, malicious contract detection | `https://api.gopluslabs.io/api/v1/token_security/{chainId}?contract_addresses={addr}` |

```python
# Example: Pre-trade safety check pipeline
async def is_safe_to_trade(token_address: str, chain_id: int) -> bool:
    honeypot = await check_honeypot_is(token_address, chain_id)
    goplus = await check_goplus_security(token_address, chain_id)
    
    if honeypot["isHoneypot"]:
        return False  # BLOCKED
    if goplus["buy_tax"] > 0.05 or goplus["sell_tax"] > 0.05:
        return False  # High tax = likely scam
    if goplus["is_open_source"] == "0":
        return False  # Unverified contract
    if goplus["owner_change_balance"] == "1":
        return False  # Owner can drain
    if goplus["cannot_sell_all"] == "1":
        return False  # Sell restrictions
    
    return True
```

---

### Phase 2 — Technical Analysis & Signals

#### Recommended Libraries
| Library | Language | Best For | Link |
|---------|----------|----------|------|
| **pandas-ta** | Python | 120+ indicators, Pandas integration | [GitHub](https://github.com/twopirllc/pandas-ta) |
| **ta** | Python | Feature engineering from OHLCV | [GitHub](https://github.com/bukosabino/ta) |
| **ccxt** | Python/JS | 120+ exchange unified API | [GitHub](https://github.com/ccxt/ccxt) |
| **finta** | Python | FinTech indicators in Pandas | [GitHub](https://github.com/peerchemist/finta) |
| **technicalindicators** | JavaScript | 20+ indicators + 30 candlestick patterns | [GitHub](https://github.com/anandanand84/technicalindicators) |

#### Indicators to Implement

**Trend Detection:**
- EMA crossovers: 9/21 (short-term), 50/200 (golden/death cross)
- MACD (12, 26, 9) — crossover signals + histogram divergence
- ADX (Average Directional Index) — trend strength filter (>25 = strong trend)

**Momentum & Reversal:**
- RSI (14-period) — Buy <30 (oversold), Sell >70 (overbought)
- Stochastic RSI — confirmation signal for RSI extremes
- Bollinger Bands — squeeze detection (volatility contraction → breakout imminent)
- VWAP — institutional entry/exit reference

**Volume Analysis:**
- OBV (On-Balance Volume) — confirm price moves with volume
- Volume spike detection (>3x average = significant event)
- Accumulation/Distribution — smart money flow

**On-Chain Signals (Gem-Specific):**
- Unique holder count growth rate
- Transaction count acceleration
- Whale wallet accumulation (wallets >1% of supply buying)
- DEX volume / Market cap ratio (>10% daily = high activity)
- Liquidity lock status and duration

#### Signal Scoring System
```python
class SignalScore:
    def __init__(self):
        self.trend_score = 0      # -100 to +100 (bearish to bullish)
        self.momentum_score = 0   # 0 to 100
        self.volume_score = 0     # 0 to 100
        self.onchain_score = 0    # 0 to 100
        
    @property
    def composite(self) -> float:
        """Weighted composite score. >70 = BUY, <30 = SELL"""
        return (
            self.trend_score * 0.30 +
            self.momentum_score * 0.25 +
            self.volume_score * 0.20 +
            self.onchain_score * 0.25
        )
```

---

### Phase 3 — Trade Execution Engine

#### Architecture
```
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐    ┌──────────────────┐
│ Gem Scanner  │───→│ Signal Generator │───→│  Risk Check  │───→│ Execute Trade    │
│ (Phase 1)    │    │ (Phase 2)        │    │              │    │                  │
└──────────────┘    └──────────────────┘    │ • Position   │    │ • MEV Protected  │
                                            │   Sizing     │    │ • Slippage Guard │
┌──────────────┐                            │ • Stop-Loss  │    │ • Gas Optimized  │
│ Portfolio    │←────────────────────────────│ • Circuit    │    │ • Multi-wallet   │
│ Manager     │    (P&L updates, rebalance) │   Breaker    │    │   routing        │
└──────────────┘                            └──────────────┘    └──────────────────┘
                                                                         │
                                                                    ┌────▼────┐
                                                                    │ Flashbots│
                                                                    │ Protect  │
                                                                    │ RPC      │
                                                                    └─────────┘
```

#### Execution Stack
| Component | Tool | Why |
|-----------|------|-----|
| **On-chain txns** | [web3.py](https://github.com/ethereum/web3.py) | Python-native, mature, well-documented |
| **DEX aggregation** | [1inch Swap API](https://portal.1inch.dev/) | Best price routing across all DEXs |
| **Backup DEX** | Uniswap V3 SDK / Router | Direct contract calls when 1inch is slow |
| **MEV Protection** | [Flashbots Protect RPC](https://docs.flashbots.net/flashbots-protect/overview) | Private mempool — prevents front-running/sandwich attacks |
| **MEV Protection Alt** | [MEV Blocker](https://mevblocker.io/) | 90% backrun rebates, orderflow protection |
| **Gas estimation** | EIP-1559 + Blocknative Gas API | Accurate priority fees, avoid overpaying |

#### MEV Protection (CRITICAL)
All trades MUST be routed through MEV-protected RPCs to prevent:
- **Front-running**: Bots seeing your pending txn and buying ahead of you
- **Sandwich attacks**: Buy before you → your trade executes at worse price → sell after you

```python
# Flashbots Protect RPC endpoints
MEV_PROTECTED_RPCS = {
    "ethereum": "https://rpc.flashbots.net",
    "base": "https://rpc.flashbots.net/base",  # If available, else use standard
}

# MEV Blocker (alternative — offers rebates)
MEV_BLOCKER_RPC = "https://rpc.mevblocker.io"
```

#### Multi-Wallet Trade Routing
```python
WALLET_STRATEGY = {
    "primary": {
        "address": "0x3eb320fad3f51fe4f2a4531f911ef56694346eef",
        "strategies": ["gem_snipe", "momentum"],
        "max_position_eth": 0.5,
        "chains": ["ethereum", "base"],
    },
    "wallet_b": {
        "address": "0x0835eb8447f3ac90351951bb5d22e77afd9b81c0",
        "strategies": ["dca", "mean_reversion"],
        "max_position_eth": 0.3,
        "chains": ["arbitrum", "polygon"],
    },
    "wallet_c": {
        "address": "0x32a71a0b8f10f263cd5d3fd8802fd9683ae6c860",
        "strategies": ["long_term_hold"],
        "max_position_eth": 1.0,
        "chains": ["ethereum"],
        "note": "Profit sweep destination. Auto-transfer profits >0.5 ETH from primary/B here."
    },
}
```

#### Risk Management Rules
| Rule | Parameter | Default |
|------|-----------|---------|
| Max position size | % of wallet balance | 2% per trade |
| Max concurrent positions | Per wallet | 10 |
| Slippage tolerance | Max % | 3% (configurable per token) |
| Trailing stop-loss | % from peak | 10% |
| Hard stop-loss | % from entry | 25% |
| Take-profit levels | Staged exits | 50% at 2x, 25% at 5x, let 25% ride |
| **Circuit breaker** | Portfolio drawdown | **HALT ALL TRADING if -15% in 24h** |
| Daily loss limit | Max ETH lost | 0.5 ETH per wallet per day |
| Gas ceiling | Max gwei willing to pay | 50 gwei (skip trade if higher) |
| Token approval | Max approval amount | Exact trade amount only (NEVER unlimited) |

---

### Phase 4 — Portfolio Management Dashboard

#### Features
| Feature | Description |
|---------|-------------|
| **Real-time portfolio** | All 3 wallets — ETH + USD values, per-chain breakdown |
| **Position tracker** | Entry price, current price, % P&L, unrealized/realized gains |
| **Trade history** | Full log with timestamps, gas costs, reasoning, CSV export |
| **P&L reports** | Daily, weekly, monthly summaries — by wallet and combined |
| **Alert system** | Slack + Telegram notifications for trades, stop-loss triggers, circuit breakers |
| **Charting** | [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) embedded |
| **Signal dashboard** | Live gem scanner output, confidence scores, pending signals |
| **Safety dashboard** | Honeypot check results, rejected tokens, blocked wallets |

#### Notification Events (Slack/Telegram)
| Event | Priority | Channel |
|-------|----------|---------|
| New gem discovered (score >80) | 🟡 Medium | `#trading-gems` |
| Trade executed | 🟢 Normal | `#trading-activity` |
| Stop-loss triggered | 🔴 High | `#trading-alerts` |
| Circuit breaker activated | 🔴🔴 Critical | `#trading-alerts` + SMS |
| Honeypot detected (pre-trade block) | 🟡 Medium | `#trading-safety` |
| Profit sweep to Wallet C | 🟢 Normal | `#trading-activity` |
| Daily P&L summary | 🟢 Normal | `#trading-daily` |

---

### Phase 5 — AI Strategy Layer (Advanced)

#### Machine Learning Integration
| Component | What It Does |
|-----------|-------------|
| **Pattern recognition** | Train on historical gem data — what signals preceded 10x tokens? |
| **Sentiment analysis** | NLP on Crypto Twitter, Telegram groups, Reddit for alpha |
| **Reinforcement learning** | Optimize entry/exit timing based on reward function (P&L) |
| **Anomaly detection** | Flag unusual on-chain activity (whale dumps, liquidity pulls) |

#### Recommended ML Tools
- [scikit-learn](https://scikit-learn.org/) — Classification, feature importance
- [XGBoost](https://github.com/dmlc/xgboost) — Gradient boosting for tabular signal data
- [financial-dataset-generator](https://github.com/Erfaniaa/financial-dataset-generator) — Training data creation
- [Intelligent Trading Bot](https://github.com/asavinov/intelligent-trading-bot) — Reference implementation for ML signals

---

## 🏗 Tech Stack

| Layer | Recommended | Alternatives |
|-------|------------|--------------|
| **Language** | Python 3.11+ | TypeScript/Node.js |
| **Exchange Data** | [ccxt](https://github.com/ccxt/ccxt) | Exchange-specific SDKs |
| **On-chain Execution** | [web3.py](https://github.com/ethereum/web3.py) | ethers.js, viem |
| **DEX Aggregation** | 1inch Swap API | Paraswap, 0x API, CoW Protocol |
| **Technical Analysis** | pandas-ta | ta-lib, finta |
| **Honeypot Detection** | GoPlus Security API + Honeypot.is | Token Sniffer, De.Fi Scanner |
| **MEV Protection** | Flashbots Protect RPC | MEV Blocker, Alchemy MEV Protection |
| **Data Storage** | SQLite (dev) → PostgreSQL (prod) | MongoDB, TimescaleDB |
| **Task Scheduling** | APScheduler | Celery, cron |
| **Notifications** | Slack webhooks + Telegram Bot | Discord webhooks |
| **Dashboard** | Streamlit | Next.js, Grafana |
| **ML/AI** | scikit-learn + XGBoost | TensorFlow, PyTorch |
| **Containerization** | Docker + docker-compose | Podman |

---

## 📦 Reference Repository

**PRIMARY REFERENCE:**
> 🔗 [https://github.com/botcrypto-io/awesome-crypto-trading-bots](https://github.com/botcrypto-io/awesome-crypto-trading-bots)

### Top Open-Source Bots to Study
| Bot | Language | Why It's Useful | Link |
|-----|----------|----------------|------|
| **freqtrade** | Python | Most mature — backtesting, ML, Telegram control, strategy marketplace | [GitHub](https://github.com/freqtrade/freqtrade) |
| **Hummingbot** | Python | DEX + CEX market making, best architecture reference | [GitHub](https://github.com/coinalpha/hummingbot) |
| **jesse** | Python | Advanced strategy framework, clean API, great docs | [GitHub](https://github.com/jesse-ai/jesse) |
| **OctoBot** | Python | Fully modular, plugin-based, built-in UI | [GitHub](https://github.com/Drakkar-Software/OctoBot) |
| **OpenTrader** | TypeScript | GRID + DCA strategies, 100+ exchanges via CCXT, UI included | [GitHub](https://github.com/bludnic/opentrader) |
| **Intelligent Trading Bot** | Python | ML-based signal generation — closest to Phase 5 goals | [GitHub](https://github.com/asavinov/intelligent-trading-bot) |
| **the0** | Multi | Multi-language strategy engine, containerized deployment | [GitHub](https://github.com/alexanderwanyoike/the0) |
| **Superalgos** | JavaScript | Visual strategy designer, integrated charting & backtesting | [GitHub](https://github.com/Superalgos/Superalgos) |

### Utility Repos
| Tool | Purpose | Link |
|------|---------|------|
| **undervalued-crypto-finder** | Find coins below MA200 — gem scanner inspiration | [GitHub](https://github.com/Erfaniaa/undervalued-crypto-finder) |
| **financial-dataset-generator** | Generate ML training datasets from market data | [GitHub](https://github.com/Erfaniaa/financial-dataset-generator) |
| **crypto-trading-strategy-backtester** | Quick strategy backtesting framework | [GitHub](https://github.com/Erfaniaa/crypto-trading-strategy-backtester) |
| **OrderBooks** | Orderbook snapshot & delta management (Node.js) | [GitHub](https://github.com/tiagosiebler/OrderBooks) |
| **awesome-crypto-examples** | Working API examples for major exchanges | [GitHub](https://github.com/tiagosiebler/awesome-crypto-examples) |

---

## ⚙️ Configuration & Environment

Create a `.env` file (**NEVER** commit this — already in `.gitignore`):

```env
# ═══════════════════════════════════════════════
# WALLETS
# ═══════════════════════════════════════════════
WALLET_PRIVATE_KEY_PRIMARY=your_primary_key_here
WALLET_PRIVATE_KEY_B=your_wallet_b_key_here
WALLET_PRIVATE_KEY_C=your_wallet_c_key_here

WALLET_ADDRESS_PRIMARY=0x3eb320fad3f51fe4f2a4531f911ef56694346eef
WALLET_ADDRESS_B=0x0835eb8447f3ac90351951bb5d22e77afd9b81c0
WALLET_ADDRESS_C=0x32a71a0b8f10f263cd5d3fd8802fd9683ae6c860

# ═══════════════════════════════════════════════
# RPC ENDPOINTS (get keys from Alchemy or Infura)
# ═══════════════════════════════════════════════
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
ARB_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
BSC_RPC_URL=https://bsc-dataseed.binance.org

# MEV-Protected RPCs (USE THESE FOR TRADE EXECUTION)
ETH_RPC_MEV_PROTECTED=https://rpc.flashbots.net
# or: https://rpc.mevblocker.io

# ═══════════════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════════════
ETHERSCAN_API_KEY=your_key
BASESCAN_API_KEY=your_key
ARBISCAN_API_KEY=your_key
COINGECKO_API_KEY=your_key_if_pro
ONEINCH_API_KEY=your_key
MORALIS_API_KEY=your_key
GOPLUS_API_KEY=optional

# ═══════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════
SLACK_WEBHOOK_GEMS=https://hooks.slack.com/services/xxx
SLACK_WEBHOOK_ACTIVITY=https://hooks.slack.com/services/xxx
SLACK_WEBHOOK_ALERTS=https://hooks.slack.com/services/xxx
TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional

# ═══════════════════════════════════════════════
# TRADING PARAMETERS
# ═══════════════════════════════════════════════
MODE=paper                          # paper | live (START WITH PAPER!)
MAX_POSITION_SIZE_PERCENT=2.0       # % of wallet per trade
MAX_SLIPPAGE_PERCENT=3.0
STOP_LOSS_PERCENT=10.0
HARD_STOP_LOSS_PERCENT=25.0
TAKE_PROFIT_1X=2.0                  # Sell 50% at 2x
TAKE_PROFIT_2X=5.0                  # Sell 25% at 5x
CIRCUIT_BREAKER_PERCENT=15.0        # Halt if portfolio drops this much in 24h
MAX_GAS_GWEI=50
MIN_LIQUIDITY_USD=50000
MAX_CONCURRENT_POSITIONS=10
DAILY_LOSS_LIMIT_ETH=0.5
PROFIT_SWEEP_THRESHOLD_ETH=0.5     # Auto-transfer to Wallet C above this
```

---

## 🚨 Safety Rules (NON-NEGOTIABLE)

### Code Safety
1. **NEVER** commit private keys, `.env`, or seed phrases to git
2. **NEVER** approve unlimited token spending — use exact amounts per trade
3. **ALWAYS** use MEV-protected RPCs (Flashbots/MEV Blocker) for trade execution
4. **ALWAYS** run honeypot + rug checks (GoPlus + Honeypot.is) before any buy
5. **ALWAYS** verify contract source code on block explorer before trading

### Trading Safety
6. **START** in `MODE=paper` — paper trade for at least 2 weeks before going live
7. **IMPLEMENT** circuit breaker: halt all trading if portfolio drops >15% in 24h
8. **ENFORCE** daily loss limits per wallet (0.5 ETH default)
9. **LOG** every transaction: timestamp, gas cost, reasoning, wallet, chain
10. **SET** a gas ceiling (50 gwei) — skip trades during gas spikes

### Operational Safety
11. **RATE LIMIT** all API calls (respect each provider's limits — see table in Phase 1)
12. **RETRY** with exponential backoff on failed requests (max 3 retries)
13. **MONITOR** wallet balances — alert if ETH balance drops below 0.05 ETH (can't pay gas)
14. **ROTATE** RPC endpoints if primary is slow/down (have fallback RPCs configured)
15. **BACKUP** trade logs and database daily

---

## 📁 Project Structure

```
shamrock-trading-bot/
├── .env                          # Secrets (gitignored)
├── .env.example                  # Template with placeholder values
├── .gitignore
├── README.md
├── requirements.txt
├── docker-compose.yml            # Container orchestration
├── Dockerfile
│
├── config/
│   ├── settings.py               # Trading parameters from .env
│   ├── chains.py                 # Chain configs (RPC URLs, router addresses, chain IDs)
│   ├── wallets.py                # Multi-wallet config & strategy assignment
│   └── tokens.py                 # Known token lists, blocklists, whitelists
│
├── core/
│   ├── scanner.py                # Gem discovery engine (Phase 1)
│   ├── analyzer.py               # Technical analysis signals (Phase 2)
│   ├── executor.py               # Trade execution with MEV protection (Phase 3)
│   ├── portfolio.py              # Portfolio tracking & P&L (Phase 4)
│   ├── risk.py                   # Position sizing, stop-loss, circuit breakers
│   └── safety.py                 # Honeypot/rug detection pipeline
│
├── data/
│   ├── providers/
│   │   ├── dexscreener.py        # DexScreener API wrapper
│   │   ├── coingecko.py          # CoinGecko API wrapper
│   │   ├── goplus.py             # GoPlus security API wrapper
│   │   ├── honeypot.py           # Honeypot.is API wrapper
│   │   ├── onchain.py            # Etherscan/block explorer wrappers
│   │   └── oneinch.py            # 1inch swap API wrapper
│   ├── models.py                 # Data models (Token, Trade, Position, Signal)
│   └── database.py               # SQLite/PostgreSQL ORM
│
├── strategies/
│   ├── base.py                   # Abstract strategy class
│   ├── gem_snipe.py              # New listing sniper (Primary wallet)
│   ├── momentum.py               # Momentum-based trading (Primary wallet)
│   ├── dca.py                    # Dollar-cost averaging (Wallet B)
│   ├── mean_reversion.py         # Buy dips on established tokens (Wallet B)
│   └── long_term.py              # Blue-chip accumulation (Wallet C)
│
├── ml/                           # Phase 5 — AI Strategy Layer
│   ├── features.py               # Feature engineering pipeline
│   ├── models.py                 # ML model training & inference
│   ├── sentiment.py              # Social sentiment analysis
│   └── backtest_ml.py            # ML strategy backtesting
│
├── notifications/
│   ├── slack.py                  # Slack webhook alerts (multi-channel)
│   └── telegram.py               # Telegram bot alerts
│
├── dashboard/
│   └── app.py                    # Streamlit dashboard
│
├── scripts/
│   ├── backtest.py               # Run backtests on historical data
│   ├── paper_trade.py            # Simulated trading mode
│   ├── sweep_profits.py          # Transfer profits to Wallet C
│   └── health_check.py           # System health monitoring
│
├── tests/
│   ├── test_scanner.py
│   ├── test_safety.py            # Honeypot/rug detection tests
│   ├── test_executor.py
│   ├── test_risk.py
│   └── test_strategies.py
│
└── logs/
    ├── trades.log                # Transaction history
    ├── scanner.log               # Gem discovery log
    ├── safety.log                # Blocked tokens & reasons
    └── errors.log                # Error tracking
```

---

## 🎯 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Gems discovered per day | 10–50 candidates | Scanner output count |
| Pre-trade safety check pass rate | 100% enforced | Every trade must pass |
| Signal accuracy (backtested) | >55% win rate | Backtest results |
| Average trade execution time | <5 seconds | Execution logs |
| MEV protection coverage | 100% of trades | All txns via Flashbots |
| Max drawdown tolerance | 15% | Circuit breaker enforcement |
| Portfolio tracking accuracy | <$1 discrepancy | Cross-reference with Etherscan |
| Uptime | 99%+ | Docker health checks |

---

## 🏁 Getting Started — Manus Execution Order

### Step 1: Scaffold
```bash
git clone https://github.com/Shamrock2245/shamrock-trading-bot.git
cd shamrock-trading-bot
python -m venv venv && source venv/bin/activate
pip install ccxt pandas-ta web3 python-dotenv requests aiohttp sqlalchemy
cp .env.example .env  # Then fill in real values
```

### Step 2: Build Phase 1 (Gem Scanner) FIRST
- Wire up DexScreener + CoinGecko + GoPlus APIs
- Implement the token scoring system (0–100)
- Build the honeypot/rug detection pipeline
- Output: ranked list of gems printed to console + logged

### Step 3: Build Phase 2 (Signals)
- Implement TA indicators using pandas-ta
- Create the SignalScore composite system
- Connect signals to scanner output

### Step 4: Build Phase 3 (Execution) — PAPER MODE ONLY
- Set `MODE=paper` in `.env`
- Build trade executor with 1inch + web3.py
- Implement risk management (position sizing, stop-loss)
- Simulate trades for minimum 2 weeks

### Step 5: Build Phase 4 (Dashboard)
- Streamlit app showing all 3 wallets
- Trade history, P&L, open positions
- Slack/Telegram notifications

### Step 6: Go Live (CAREFULLY)
- Switch `MODE=live` only after thorough paper trading
- Start with tiny positions (0.01 ETH max)
- Monitor closely for first 48 hours
- Scale up gradually

### Step 7: Phase 5 (ML — when ready)
- Collect 30+ days of trading data first
- Train models on what worked vs. what didn't
- Deploy incrementally

**Study this entire repo thoroughly:**
> 🔗 [awesome-crypto-trading-bots](https://github.com/botcrypto-io/awesome-crypto-trading-bots)

**Push all code to GitHub as you go:**
> 🔗 [https://github.com/Shamrock2245/shamrock-trading-bot](https://github.com/Shamrock2245/shamrock-trading-bot)

---

*Built for Shamrock Trading. Three wallets. Zero tolerance for rugs. Let's find gems. 💎☘️*
