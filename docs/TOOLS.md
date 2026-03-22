# TOOLS — External APIs & Data Sources

## Data Providers (Read-Only)

| Tool | Purpose | Rate Limit | Key Required |
|------|---------|------------|-------------|
| **DexScreener** | Token discovery, pairs, boosts, CTOs, ads | 60-300/min | ❌ Free |
| **GeckoTerminal** | OHLCV candle data for TA | 30/min | ❌ Free |
| **CoinGecko** | Market data, social signals | 30/min | Optional |
| **CoinMarketCap** | Market cap, volume validation | 30/min | ✅ `CMC_API_KEY` |
| **LunarCrush** | Social sentiment scoring | 4/min (100/day) | ✅ `LUNARCRUSH_API_KEY` |
| **DefiLlama** | TVL scoring | 500/min | ❌ Free |
| **Moralis** | Wallet/holder analysis | 25/min | ✅ `MORALIS_API_KEY` |
| **Etherscan** | Contract verification, holder data | 5/sec | ✅ `ETHERSCAN_API_KEY` |

## Safety APIs (Pre-Trade Gates)

| Tool | Purpose | Action on Fail |
|------|---------|---------------|
| **GoPlus** | Token security audit (honeypot, ownership, tax) | **REJECT trade** |
| **Honeypot.is** | Live swap simulation | **REJECT trade** |
| **Token Sniffer** | Scam pattern detection (score < 50 = reject) | **REJECT trade** |

## Execution APIs (Write — Real $$$)

| Tool | Chains | Purpose |
|------|--------|---------|
| **CoW Protocol** | Ethereum | MEV-protected batch auctions |
| **1inch Aggregator** | Base, Arbitrum, Polygon, BSC | Best-price routing |
| **Jupiter** | Solana | SOL DEX aggregation |
| **Flashbots** | Ethereum | Private tx submission (MEV protection) |

## Notification APIs

| Tool | Purpose |
|------|---------|
| **Slack Webhooks** | Trade alerts, errors, daily summaries |
| **Telegram Bot** | Mobile trade notifications |

## Rate Limit Policy
- **Always respect rate limits** — getting banned kills scanning
- **Prioritize DexScreener** — it's our primary signal source
- **LunarCrush is precious** — only 100 calls/day, use only for base_score ≥ 45 candidates
- **Cache aggressively** — don't re-fetch data that hasn't changed
