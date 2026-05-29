# Manus Task: BTC Wealth Retention Engine + Moralis API Upgrade Sprint

## Context
Read `CURRENT_STATUS.md` first — it has the full pipeline status.

The Shamrock Trading Bot is LIVE on Hetzner VPS (`5.161.126.32`), cycling in PAPER mode with all systems green. The entire discovery → scoring → execution pipeline is operational. **What's missing is the wealth retention layer** — the bot trades altcoins/memecoins but has no mechanism to rotate gains into BTC for long-term wealth preservation. Additionally, Moralis has shipped several NEW APIs we aren't using that would give us a massive edge.

**Goal: Make this bot famously profitable by adding wealth retention + 5 new Moralis-powered intelligence layers.**

---

## P0: Bitcoin Wealth Retention Engine (Moralis Bitcoin Streams + Price API)

### The Problem
The bot compounds gains in volatile altcoins/memecoins across Solana, Base, BSC, and Avalanche. When trades win, profits sit in the same volatile tokens or get swept to Wallet C as stablecoins. **There is no BTC accumulation strategy.** Bitcoin is the ultimate store-of-value in crypto — we need to systematically rotate a portion of realized gains into BTC during favorable conditions.

### What To Build

#### A. `core/btc_wealth_engine.py` (NEW FILE)
A daemon that runs alongside the main bot loop. Responsibilities:

1. **BTC Price Intelligence** — Use the **Moralis Bitcoin Price API** (`chain=bitcoin`) to fetch:
   - Real-time BTC/USD price
   - 24h sparkline for trend detection
   - 7d and 30d historical price data for moving average calculation
   - Calculate BTC's own EMA20/EMA50/EMA200 to detect accumulation zones

2. **Accumulation Signal Logic** — Determine when to rotate gains into BTC:
   - **DCA baseline**: Always rotate 10% of realized profits into BTC (wrapped — WBTC on EVM, via Jupiter on Solana)
   - **Dip accumulation**: Increase to 25% when BTC is >5% below its 7d EMA
   - **Deep dip**: Increase to 40% when BTC is >15% below its 30d EMA
   - **Euphoria brake**: Reduce to 5% when BTC is >20% above its 30d EMA (overheated)
   - **Regime override**: If `macro_filter.py` reports BEAR, increase base to 20% (flee to safety)

3. **Execution** — Swap altcoin profits → WBTC (EVM chains) or BTC via Jupiter (Solana):
   - Use existing `core/executor.py` and `core/solana_executor.py` for the swaps
   - Track all BTC accumulation in `output/btc_wealth_ledger.json`
   - Log every rotation to Slack (`#btc-accumulation` channel)

#### B. `data/providers/moralis_bitcoin.py` (NEW FILE)
Moralis Bitcoin Data API wrapper. Endpoints to implement:

| Endpoint | Use |
|----------|-----|
| `GET /v2/market-data/erc20s/top-tokens` with `chain=bitcoin` | BTC market overview |
| Bitcoin Price API endpoints | Real-time + historical BTC price, sparklines |
| Bitcoin Wallet API | Monitor our own BTC address balances |
| Bitcoin Blockchain API | Block data for confirmation tracking |

Use the existing `MORALIS_API_KEY` from `.env`. Base URL: `https://deep-index.moralis.io/api/v2.2/`.

#### C. Bitcoin Streams Integration
Add a new stream in `core/moralis_streams_manager.py`:

```python
TAG_BTC_WHALE_WATCH = "shamrock-btc-whales"
```

- Monitor 5-10 known BTC whale addresses for large movements (>100 BTC transfers)
- When whales accumulate → increase our BTC rotation percentage
- When whales distribute → pause BTC rotation, stay in stablecoins
- Webhook handling: Add a `_handle_btc_event()` method to `core/moralis_streams.py`
- Bitcoin Stream payloads have `vin`/`vout` arrays (UTXO model, not ERC20 transfers) — parse accordingly
- Dual-phase notifications: handle both mempool (unconfirmed) and block-confirmed events
- Use `block.hash === "mempool"` to distinguish

#### D. Integration Points
- `main.py`: After each profitable trade closes in `position_monitor`, call `btc_wealth_engine.evaluate_rotation(realized_pnl_usd)`
- `core/capital_compounder.py`: Before profit sweep to Wallet C, pass through BTC rotation first
- `core/macro_filter.py`: Expose `get_btc_regime()` method that `btc_wealth_engine` can consume
- `dashboard/pages/`: Add BTC Accumulation widget showing: total BTC accumulated, cost basis, current value, unrealized PnL
- `config/settings.py`: Add `BTC_ROTATION_ENABLED`, `BTC_ROTATION_BASE_PCT`, `BTC_DIP_THRESHOLD_7D`, `BTC_DEEP_DIP_THRESHOLD_30D`, `BTC_EUPHORIA_THRESHOLD_30D`

---

## P1: Moralis DeFi API — Position Intelligence (NEW)

### What It Is
Moralis now has a **DeFi API** that provides normalized, cross-chain DeFi position data across thousands of protocols (Uniswap, Aave, Lido, Jupiter Lending, Raydium, etc.).

### What To Build: `data/providers/moralis_defi.py` (NEW FILE)

| Endpoint | Purpose |
|----------|---------|
| `GET /wallets/{address}/defi/summary` | Which protocols our wallets interact with |
| `GET /wallets/{address}/defi/positions` | All open DeFi positions with USD values |
| `GET /wallets/{address}/defi/{protocol}/positions` | Deep dive into specific protocol positions |

### Integration
- **Pre-trade intelligence**: Before buying a token, check if smart money wallets (our alpha wallet list) have DeFi positions in that token's protocol → higher conviction signal
- **Portfolio awareness**: Track if our wallets have idle capital sitting in DeFi that could be redeployed
- **Risk layer**: Detect if a token's underlying protocol has massive withdraw activity (exodus signal)
- Wire into `scanner/gem_scanner.py` as a new scoring signal: `defi_protocol_health` (0-10 points)

---

## P2: Moralis Entity API — Smart Money Identity Layer (NEW)

### What It Is
The Entity API groups blockchain addresses under real-world entities (Coinbase, BlackRock, Wintermute, etc.) with metadata like names, logos, categories.

### What To Build: `data/providers/moralis_entity.py` (NEW FILE)

| Endpoint | Purpose |
|----------|---------|
| `GET /entities/search?query=...` | Search for entities by name |
| `GET /entities/{entityId}` | Get entity details + all their addresses |
| `GET /entities/categories/{categoryId}` | List entities by category (exchanges, funds, MEV, etc.) |

### Integration — THIS IS A GAME-CHANGER
- **Alpha wallet enrichment**: When `sniper_discovery.py` finds a profitable wallet, check if it belongs to a known entity (fund, exchange, market maker). Wallets belonging to Wintermute, Jump, Alameda successors, etc. get a massive conviction boost.
- **Token buyer analysis**: For any gem candidate, check if its top holders are entities (institutions buying = bullish) vs anonymous wallets
- **MEV detection upgrade**: If a wallet buying a token is tagged as "MEV" category → reduce conviction (they're frontrunning, not investing)
- **Exchange flow**: Track if a token's holders are moving to exchange addresses (sell pressure incoming)
- Wire into `scanner/gem_scanner.py` as: `institutional_interest` signal (0-15 points)
- Wire into `core/wallet_monitor.py`: Tag each alpha wallet with its entity name for better Slack alerts

---

## P3: Moralis Market Metrics API — Market-Wide Radar (NEW)

### What It Is
Aggregated cross-chain market metrics: trading volume, trending tokens, swap activity across all DEXs.

### What To Build
Add to existing `data/providers/moralis_intelligence.py` or create `data/providers/moralis_market_metrics.py`:

- **Market-wide volume trends**: Is overall DEX volume increasing or decreasing? Rising volume = more opportunities, falling = tighten filters
- **Trending tokens cross-chain**: Compare with DexScreener trending — tokens trending on BOTH sources get a conviction boost
- **Swap activity heatmap**: Which chains have the most activity right now? Focus scanning on the hottest chains

### Integration
- `core/regime_filter.py`: Add market volume momentum as a regime signal (currently only uses BTC/ETH/SOL/BNB price)
- `scanner/gem_scanner.py`: Cross-reference Moralis trending with DexScreener trending → dual-source trending = higher score
- `core/adaptive_mode.py`: If market-wide volume is collapsing → enter capital preservation mode automatically

---

## P4: Universal Token API Enhancements (New Features)

### What's New
Moralis has added new features to their Token API. Check and integrate any we're missing:

- **Token security scores** (may be more comprehensive than what we get from `moralis_money.py`)
- **Holder statistics** with time-series data (holder count growth/decline over 7d)
- **Token transfers with decoded data** — more detail than raw transfer events
- **Enriched token metadata** — social links, website, description

### Integration
- Audit `data/providers/moralis_money.py` (103KB — our largest provider) and `data/providers/moralis_intelligence.py` (86KB)
- Check if we're using the latest token metadata endpoints or hitting deprecated ones
- Add holder growth rate as a scoring signal (growing holders = organic interest, shrinking = dump incoming)

---

## P5: Enhanced Macro Intelligence with Bitcoin Price API

### Current Gap
`core/macro_filter.py` uses CoinGecko (free, rate-limited) as primary BTC price source with Moralis as a secondary. **Flip this.** Moralis Bitcoin Price API should be primary — we're paying for it, it's faster, and it includes sparklines.

### Changes
1. In `core/macro_filter.py`: Make Moralis Bitcoin Price API the primary source for BTC 24h/7d/30d data
2. Add BTC dominance tracking (BTC market cap / total crypto market cap) as a regime signal:
   - Rising BTC dominance = alt season ending → tighten alt filters, increase BTC rotation
   - Falling BTC dominance = alt season starting → loosen filters, reduce BTC rotation
3. Use BTC sparkline data for intra-day trend detection (not just daily candles)

---

## File Map

| New File | Purpose |
|----------|---------|
| `core/btc_wealth_engine.py` | BTC accumulation daemon — P0 |
| `data/providers/moralis_bitcoin.py` | Moralis Bitcoin API wrapper — P0 |
| `data/providers/moralis_defi.py` | Moralis DeFi API wrapper — P1 |
| `data/providers/moralis_entity.py` | Moralis Entity API wrapper — P2 |
| `data/providers/moralis_market_metrics.py` | Market Metrics API — P3 |

| Modified File | Changes |
|---------------|---------|
| `core/moralis_streams.py` | Add `_handle_btc_event()` for Bitcoin webhook payloads — P0 |
| `core/moralis_streams_manager.py` | Add `TAG_BTC_WHALE_WATCH` stream — P0 |
| `core/capital_compounder.py` | Route profit sweeps through BTC rotation first — P0 |
| `core/macro_filter.py` | Moralis-primary BTC data + BTC dominance signal — P5 |
| `core/regime_filter.py` | Market volume momentum signal — P3 |
| `scanner/gem_scanner.py` | New signals: `defi_protocol_health`, `institutional_interest`, dual-trending — P1/P2/P3 |
| `core/wallet_monitor.py` | Entity-enriched alpha wallet alerts — P2 |
| `core/sniper_discovery.py` | Entity-check discovered wallets — P2 |
| `config/settings.py` | New BTC rotation + API config vars — P0 |
| `main.py` | Wire `btc_wealth_engine` into the main loop — P0 |

## API Reference
- **Moralis Docs**: https://docs.moralis.com/data-api/overview
- **Bitcoin API**: https://docs.moralis.com/data-api/bitcoin-api/overview
- **Bitcoin Streams**: https://docs.moralis.com/streams-api/bitcoin-streams
- **DeFi API**: https://docs.moralis.com/data-api/defi-api
- **Entity API**: https://docs.moralis.com/data-api/entity-api
- **Market Metrics API**: https://docs.moralis.com/data-api/market-metrics-api
- **Universal Token API**: https://docs.moralis.com/data-api/token-api
- All endpoints use header: `X-API-Key: {MORALIS_API_KEY}` (already in `.env`)

## Hetzner Access
- SSH: `ssh -i ~/.ssh/id_ed25519 root@5.161.126.32`
- Bot directory: `/root/shamrock-trading-bot`
- Rebuild: `docker compose down && docker compose build --no-cache && docker compose up -d`
- Logs: `docker compose logs --tail=100 bot`
- Mode: **PAPER** (safe — no real trades until verified)

## Build Order
1. **P0 first** — BTC Wealth Engine is the highest-value feature. Get `moralis_bitcoin.py` + `btc_wealth_engine.py` working with unit tests.
2. **P2 second** — Entity API is the biggest edge multiplier (institutional signal detection).
3. **P1 third** — DeFi positions for protocol health scoring.
4. **P3 fourth** — Market Metrics for regime enhancement.
5. **P4/P5 last** — Token API audit and macro filter upgrade.

## Success Criteria
- [ ] `btc_wealth_engine.py` runs as a daemon, evaluates BTC rotation after each profitable trade
- [ ] BTC price data fetched from Moralis Bitcoin Price API (primary) with CoinGecko fallback
- [ ] Bitcoin Streams webhook receives whale movement alerts
- [ ] `moralis_entity.py` can identify entities behind alpha wallets
- [ ] `moralis_defi.py` fetches protocol positions for smart money wallets
- [ ] Market Metrics cross-referenced with DexScreener trending
- [ ] All new features have unit tests in `tests/`
- [ ] Dashboard shows BTC accumulation tracker
- [ ] Changes committed, pushed, and deployed to Hetzner
- [ ] Bot completes 3+ full cycles with all new modules active (no crashes)
