# 🤖 Shamrock Trading Bot — Manus Project Instructions

> **Status**: 🟢 LIVE — Running on Hetzner VPS (`root@5.161.126.32`) via Docker Compose.
> **Current Build**: `df195f8` | **Chains**: 6 active | **Sources**: 9 discovery pipelines
> **Goal**: AI-powered multi-chain gem discovery, execution, and portfolio management — 24/7 autonomous.

---

## 🔑 Wallets & Chain Info

### Managed Wallets
| Alias | Address | Role |
|-------|---------|------|
| **Primary** | `0x3eb320fad3f51fe4f2a4531f911ef56694346eef` | Main EVM trading wallet — gem sniping & active positions |
| **Wallet B** | `0x0835eb8447f3ac90351951bb5d22e77afd9b81c0` | Secondary EVM — DCA, mean-reversion strategies |
| **Wallet C** | `0x32a71a0b8f10f263cd5d3fd8802fd9683ae6c860` | Cold/reserve — long-term holds & profit sweeps |
| **Solana** | Configured via `SOLANA_WALLET_ADDRESS` env | Solana-native execution via Jupiter V6 |

### Active Chains (LIVE)
| Chain | Env Key | Use Case | DEX Routers |
|-------|---------|----------|-------------|
| **Ethereum** | `ethereum` | Blue-chip, high-liquidity pairs | Uniswap V3, 1inch, CoW Protocol |
| **Base** | `base` | Low-gas gem sniping, new launches | Aerodrome, Uniswap V3 Base |
| **Arbitrum** | `arbitrum` | Mid-cap, derivatives | Uniswap V3, Camelot |
| **Polygon** | `polygon` | Low-fee swing trades | QuickSwap, Uniswap V3 |
| **BSC** | `bsc` | Altcoin/memecoin scanning | PancakeSwap V3 |
| **Solana** | `solana` | Meme coins, Pump.fun graduates, high-velocity plays | Jupiter V6 Swap API |

> [!CAUTION]
> **NEVER** hardcode private keys. All secrets live in `.env` via `WALLET_PRIVATE_KEY_PRIMARY`, `WALLET_PRIVATE_KEY_B`, `WALLET_PRIVATE_KEY_C`, `SOLANA_PRIVATE_KEY`. Public addresses above are safe to reference in code.

---

## 🏗 System Architecture (LIVE)

```
┌─────────────────────────────────────────────────────────────┐
│                    GEM SCANNER (9 Sources)                  │
│  DexScreener × 4  |  Moralis × 1  |  Pump.fun  |  Binance  │
│  Watchlist Reeval  |  CTO Revival  |  Ads                   │
└───────────────────────────┬─────────────────────────────────┘
                            │ GemCandidate objects
┌───────────────────────────▼─────────────────────────────────┐
│              SIGNAL ENGINE (29 Indicators)                  │
│  TA: RSI, MACD, BB, EMA, ADX, Stoch, OBV, VWAP, ATR…      │
│  On-chain: Holders, Volume, Whale score, Moralis score      │
│  Sentiment: Grok 5%, Social 3%                              │
│  Fibonacci: Retracement zones from fib_hunter.py            │
└───────────────────────────┬─────────────────────────────────┘
                            │ gem_score 0–100
┌───────────────────────────▼─────────────────────────────────┐
│              HARD ENTRY GATES (Pre-trade)                   │
│  ① Solana age gate: REJECT if < 2h old                      │
│  ② Near-ATH FOMO gate: REJECT if top 15% of 7d range        │
│     without whale confirmation (exp_buyers < 3)             │
│  ③ Score floor: MIN_GEM_SCORE = 65                          │
│  ④ GoPlus safety: honeypot / tax / rug checks               │
└───────────────────────────┬─────────────────────────────────┘
                            │ qualified gem
┌───────────────────────────▼─────────────────────────────────┐
│              EXECUTION ENGINE                               │
│  EVM: executor.py → wallet_router.py → 1inch / Uniswap      │
│  SOL: solana_executor.py → Jupiter V6 Swap API              │
│  MEV: mev_protection.py (Flashbots / private mempool)       │
└───────────────────────────┬─────────────────────────────────┘
                            │ open position
┌───────────────────────────▼─────────────────────────────────┐
│              POSITION MONITOR (30s interval)                │
│  TP1 @ 1.5× → sell 40%   |  Trailing stop Tier 1: 20%      │
│  TP2 @ 2.5× → sell 35%   |  Trailing stop Tier 2: 15%      │
│  TP3 @ 5.0× → sell 25%   |  Trailing stop Tier 3: 10%      │
│  Stale rotation: eject if ±2.5% for 4+ hours               │
│  Pyramid scaling: add to winners at each TP tier            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📡 Discovery Pipeline — 9 Active Sources

The scanner runs `scan_for_gems()` on all 6 chains in parallel. Sources are evaluated in priority order.

### Source Priority Order

| # | Source | Signal | File |
|---|--------|--------|------|
| 1 | **DexScreener Latest Profiles** | New project launches | `dexscreener.py` |
| 2 | **DexScreener Latest Boosts** | Community-paid visibility | `dexscreener.py` |
| 3 | **DexScreener Top Boosts** | Strongest community momentum | `dexscreener.py` |
| 4 | **CTO Revival** | Community-rescued projects (top-tier turnaround signal) | `dexscreener.py` |
| 5 | **Ads** | Funded teams with marketing spend | `dexscreener.py` |
| 6 | **Moralis Multi-Signal** | Buying pressure → filtered tokens → whale accumulation → trending → top gainers | `moralis_money.py` |
| 7 | **Watchlist Re-evaluation** | Near-miss tokens that improved since last cycle | `gem_scanner.py` |
| 8 | **Pump.fun Graduated** | Solana tokens that just graduated bonding curve to Raydium | `moralis_solana.py` |
| 9 | **Binance Pulse Trending** | Web3 wallet trending tokens across supported chains | `binance_pulse.py` |

### Moralis Discovery Sub-Sources (Source 6, in order)

```
moralis_discover():
  [0] get_buying_pressure_tokens()      ← FIRST: real-time momentum
  [1] get_filtered_tokens()             ← Smart money accumulation filter
  [2] get_whale_accumulation_tokens()   ← netExperiencedBuyers signal
  [3] get_trending_tokens()             ← Volume/social trending
  [4] get_top_gainers(timeframe="1h")   ← 1h breakout momentum
  [5] get_top_losers(timeframe="1h")    ← Mean-reversion candidates (Wallet B)
```

---

## 🔢 Gem Scoring Engine — Live Weights

All tokens are scored 0–100. A token needs **65+** to enter.

### Composite Score Formula

| Category | Weight | Key Signals |
|----------|--------|-------------|
| Volume score | 22% | Volume spike, buy/sell ratio, 1h vs 24h volume |
| Holder/Whale score | 18% | Whale accumulation bonus (+20% if exp_buyers > 5), holder growth |
| Liquidity score | 14% | Pool depth, liquidity change trend |
| Age score | 4% | Optimal window 2h–24h (Solana < 2h = hard reject) |
| Safety score | 12% | GoPlus security score, honeypot, taxes, ownership |
| TA/Momentum score | 10% | RSI, MACD, BB squeeze, EMA crossovers |
| Fibonacci score | 5% | Price position within retracement zones |
| Social score | 3% | Twitter/TG mentions via `social_scoring.py` |
| Grok sentiment | **5%** | Narrative/sentiment via `grok_sentiment.py` |
| Boost/CTO score | 7% | DexScreener boost amount, CTO revival flag |

> **Grok sentiment is a PRIMARY swing-trade signal** — boosted from 2% to 5%. Tokens with strong narrative momentum receive meaningful score uplift.

### Score Floors & Gates

| Setting | Value | Purpose |
|---------|-------|---------|
| `MIN_GEM_SCORE` | **65.0** | Standard entry gate |
| `CAPITAL_RECOVERY_MIN_SCORE` | **62.0** | Floor during recovery mode (raised from 55) |
| `CASCADE_BOOST_FLOOR_SCORE` | **58.0** | Floor during win-streak cascade (raised from 38) |
| `CASCADE_BOOST_MAX_REDUCTION` | **5.0 pts** | Max score discount from win streak (was 12) |

---

## 🚫 Hard Entry Gates (MANDATORY — fires before scoring)

These are binary REJECT gates in `gem_scanner.py::_score_token()`. If any fires, the token is **dropped entirely**.

### Gate 1: Solana Age Gate
```python
# In _score_token()
if chain == "solana" and token.age_hours < 2.0:
    logger.info(f"⛔ SOLANA AGE GATE: {token.symbol} only {token.age_hours:.1f}h old")
    return None  # HARD REJECT
```
**Why**: Solana tokens < 2h old are in the rug-pull danger window. The bonding curve hasn't proven itself.

### Gate 2: Near-ATH FOMO Reject
```python
# If price > 85% of 7d ATH AND whale confirmation missing:
if near_ath and not whale_confirmed:
    logger.info(f"⛔ NEAR-ATH REJECT: {token.symbol} at {pct_from_ath:.0f}% of ATH, no whale backing")
    return None  # HARD REJECT
```
**Why**: Chasing tokens near their ATH without smart money confirmation = FOMO entry = guaranteed bag.

### Gate 3: GoPlus Safety
```python
# In safety.py / goplus.py — runs for every candidate
if goplus["buy_tax"] > 0.10 or goplus["sell_tax"] > 0.10:
    return False  # BLOCKED
if goplus["is_honeypot"]:
    return False  # BLOCKED
if goplus["cannot_sell_all"] == "1":
    return False  # BLOCKED
```

---

## 💰 Position Management — Live Rules

### Take Profit Tiers (Pyramid Scaling)
| Tier | Trigger | Action | Trailing Stop Applied |
|------|---------|--------|-----------------------|
| TP1 | Price = **1.5× entry** (+50%) | Sell **40%** of position | 20% trailing on remainder |
| TP2 | Price = **2.5× entry** (+150%) | Sell **35%** of remaining | 15% trailing on remainder |
| TP3 | Price = **5.0× entry** (+400%) | Sell **25%** of remaining | 10% trailing on remainder |
| Moon | Price > 5× | Hold remainder with tight 10% trail | — |

### Stale Position Rotation
**Dead money is opportunity cost.** Any position that is flat gets ejected to free capital.
```
UNDERPERFORMER_FLAT_HOURS = 4.0   # Was 12h — now 3× faster rotation
UNDERPERFORMER_FLAT_PCT   = 2.5   # ±2.5% = "flat" (was ±5%)
```
If a position hasn't moved more than ±2.5% within **4 hours**, it is sold and capital is redeployed.

### Position Sizing
```
MAX_POSITION_SIZE_PERCENT = 5.0%   # Per-position cap as % of portfolio
MAX_PORTFOLIO_EXPOSURE    = 75.0%  # Max total deployed capital
```

### Pyramiding Amounts of Daily Goals
The bot operates in phased financial goals that "pyramid" as capital grows. It leverages realized gains to increase buying power and dynamic position sizing for exponential compounding:
- **Phase 1 (Seed):** $500/day Target (Survival & consistency)
- **Phase 2 (Growth):** $1,000/day Target (Activates past the first $10K milestone)
- **Phase 3 (Acceleration):** $5,000/day Target (Heavy nuclear wallet leverage)
- **Phase 4 (Compound/Whale):** $10,000+/day Target (Full auto-tune scaling)

---

## 🛠 Data Providers (ALL LIVE)

| File | What It Provides |
|------|-----------------|
| `moralis_money.py` | Buying pressure, filtered tokens, whale accumulation, trending, gainers/losers |
| `moralis_solana.py` | Pump.fun graduated tokens, Solana-specific discovery |
| `moralis_wallet.py` | Wallet balances, token holdings, net worth |
| `moralis_price.py` | Token prices, OHLCV via Moralis |
| `dexscreener.py` | Token profiles, boosts, CTO, ads, pair data |
| `goplus.py` | Security checks: honeypot, taxes, ownership, rug patterns |
| `grok_sentiment.py` | Narrative/sentiment scoring via Grok API |
| `binance_pulse.py` | Smart Money, Social Hype, Unified Rank from Binance Web3 |
| `holder_analysis.py` | Holder count growth, concentration analysis |
| `smart_money.py` | Tracked wallet buy/sell detection |
| `social_scoring.py` | Twitter/TG mention velocity |
| `copycat_detector.py` | Detects fake/clone tokens |
| `ohlcv_provider.py` | OHLCV candlesticks for TA engine |
| `coingecko.py` | Market cap, historical data |
| `defillama.py` | TVL, protocol revenue |
| `oneinch.py` | 1inch quote/swap routing for EVM |
| `token_unlocks.py` | Unlock schedule risk detection |
| `dev_wallet_history.py` | Dev wallet behavior patterns |

---

## ⚙️ Core Engine Modules

| Module | Role |
|--------|------|
| `core/signal_engine.py` | 29-indicator composite scoring (RSI, MACD, BB, EMA, ADX, OBV, VWAP, ATR, Stoch, Fib…) |
| `core/executor.py` | EVM trade execution via 1inch / Uniswap |
| `core/solana_executor.py` | Solana execution via Jupiter V6 Swap API |
| `core/wallet_router.py` | Routes trades to correct wallet (Primary / B / C) |
| `core/mev_protection.py` | Flashbots / private mempool for front-run protection |
| `core/position_monitor.py` | TP tiers, trailing stops, stale rotation, pyramid scaling |
| `core/risk.py` | Portfolio exposure caps, daily loss limits |
| `core/safety.py` | Pre-trade safety gate orchestration |
| `core/adaptive_mode.py` | Capital Recovery Mode — tightens scoring on losing streaks |
| `core/offensive_guardrails.py` | Win-streak cascade boost, express lane, overdrive mode |
| `core/fib_hunter.py` | Fibonacci retracement zone detection |
| `core/moonshot_allocator.py` | Allocates extra sizing to ultra-high-score tokens |
| `core/regime_filter.py` | Market regime detection (bull/bear/sideways) |
| `core/portfolio_rebalancer.py` | Cross-wallet rebalancing and profit sweeps |
| `core/balance_fetcher.py` | Real-time balance fetching across all wallets/chains |
| `core/reconciliation.py` | Trade reconciliation and PnL tracking |

---

## 🔄 Adaptive Trading Modes

### Capital Recovery Mode
Triggered when portfolio is below baseline. Bot becomes **more selective**:
- `MIN_GEM_SCORE` raised to `CAPITAL_RECOVERY_MIN_SCORE = 62.0`
- Position sizes reduced
- Cascade boost disabled

### Cascade Boost (Win Streak Mode)
Triggered after consecutive wins. Score floor is relaxed slightly:
- Floor never drops below `CASCADE_BOOST_FLOOR_SCORE = 58.0`
- Max reduction: `CASCADE_BOOST_MAX_REDUCTION = 5.0 pts`
- Per-win reduction: `CASCADE_BOOST_PER_WIN = 0.75 pts`

### Express Overdrive
After a strong win, slippage tolerance is raised to capture fast-moving plays:
- `EXPRESS_OVERDRIVE_ENABLED = true`
- `EXPRESS_OVERDRIVE_EXTRA_SLIPPAGE_BPS = 150`

---

## 🚀 Execution Stack

### EVM Chains (Ethereum, Base, Arbitrum, Polygon, BSC)
```python
# core/executor.py → core/wallet_router.py
# Routes: 1inch Aggregator (best price) or direct Uniswap V3
# MEV protection: Flashbots bundle submission on Ethereum
# Slippage: configurable per-chain, default 1–3%
```

### Solana
```python
# core/solana_executor.py
# Router: Jupiter V6 Swap API (best aggregated route)
# Wallet: SOLANA_WALLET_ADDRESS / SOLANA_PRIVATE_KEY from env
# Priority fee: dynamic based on network congestion
```

---

## 📊 Dashboard (LIVE at http://5.161.126.32:3000)

Built with Reflex. 6 pages:

| Page | Content |
|------|---------|
| 🏠 Command Center | Portfolio P&L, active trades, scan activity |
| 🔍 Gem Scanner | Live gem feed, score distribution, filter controls |
| 📊 Analytics | Session stats, win rate, Fibonacci zone breakdown |
| 💰 Positions | Open positions with real-time PnL |
| 🏥 System Health | API status, scraper health, Docker container states |
| 👛 Wallet Overview | Balance across all wallets and chains |

---

## 🔑 Environment Variables (Required)

```bash
# Wallets
WALLET_PRIVATE_KEY_PRIMARY=       # Primary EVM wallet
WALLET_PRIVATE_KEY_B=             # Wallet B
WALLET_PRIVATE_KEY_C=             # Wallet C
SOLANA_PRIVATE_KEY=               # Solana wallet

# APIs
MORALIS_API_KEY=                  # Primary discovery + enrichment
GROK_API_KEY=                     # Sentiment scoring
DEXSCREENER_API_KEY=              # Token data (most endpoints free)
GOPLUS_API_KEY=                   # Safety checks
ONEINCH_API_KEY=                  # EVM swap routing
BINANCE_PULSE_API_KEY=            # Binance Web3 trending

# Chains
ACTIVE_CHAINS=ethereum,base,arbitrum,polygon,bsc,solana

# Scoring
MIN_GEM_SCORE=65.0
CAPITAL_RECOVERY_MIN_SCORE=62.0
CASCADE_BOOST_FLOOR_SCORE=58.0

# Position Management
UNDERPERFORMER_FLAT_HOURS=4.0
UNDERPERFORMER_FLAT_PCT=2.5
MAX_POSITION_SIZE_PERCENT=5.0
MAX_PORTFOLIO_EXPOSURE_PCT=75.0
```

---

## 🏛 Prime Directives for Manus

1. **Never lower score floors below 58** — the cascade boost has a hard floor. Do not override it.
2. **GoPlus safety is non-negotiable** — every EVM buy must pass safety checks before execution.
3. **Solana age gate is inviolable** — no Solana token under 2 hours old, ever.
4. **Moralis is the primary discovery source** — DexScreener feeds the pipeline but Moralis filters by smart money. Wire them together, not against each other.
5. **Stale positions must be ejected** — dead money kills compounding. 4h flat = rotate.
6. **TP tiers are sacred** — never exit 100% in one shot unless stop-loss triggers. The pyramid is how you capture moonshots.
7. **The .env on the server is the source of truth** — settings.py defaults can be overridden. Always check both.
8. **Never touch private keys in code** — all secrets via env vars only.
9. **Test on paper mode first** — `PAPER_TRADING=true` before any new execution logic goes live.
10. **The signal engine has 29 indicators** — do not add more without removing something. Complexity kills speed.
11. **Trading-as-Git Auto-Tuning (OpenAlice Architecture)** — The `LLMAutoTuner` manages parameter adjustments dynamically in paper mode. We must continually learn from the [OpenAlice](https://github.com/TraderAlice/OpenAlice) repo. Rely on its JSON commits rather than hard-coding static trailing stops when possible, and refer to OpenAlice when tuning AI reasoning models.
12. **Defend the Daily Goal** — Do not override `ShamrockGuard`. If the bot is within striking distance of the daily profit target, allow "Bank-It Mode" to scale back risk.

---

## 📦 Deployment

```bash
# Running on Hetzner VPS (root@5.161.126.32)
# Four Docker containers:
#   shamrock-bot        — main trading engine
#   shamrock-dashboard  — Reflex UI on :3000
#   shamrock-health     — health monitoring
#   shamrock-db         — local data persistence

# Deploy new code:
cd /root/shamrock-trading-bot
git pull origin main
docker compose down
docker compose build --no-cache bot
docker compose up -d
docker compose logs -f --tail=40 bot

# Update .env settings (gitignored — must update server directly):
sed -i 's/OLD_VALUE/NEW_VALUE/' /root/shamrock-trading-bot/.env
docker compose restart bot
```

---

## 🔍 What Manus Should Focus On Next

| Priority | Task | Why |
|----------|------|-----|
| 🔴 High | Improve TP exit timing using Grok sentiment reversals | Exit when narrative turns, not just price |
| 🔴 High | AI-Driven Auto-Tuning Adjustments | The LLMAutoTuner is running, but we need to monitor its decisions and optimize its prompt to hit $500/day consistently |
| 🟠 Medium | `getDiscoveryToken` deep intel pre-entry | 60+ data points per token before buy |
| 🟠 Medium | Sharpen Pump.fun graduation filter | Add liquidity + holder minimum to graduated tokens |
| 🟡 Low | Per-chain win rate analytics | Some chains may be systematically worse |
| 🟡 Low | Watchlist promotion tuning | Near-misses need faster re-evaluation cycle |
