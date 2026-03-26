# TOOLS — External APIs & Data Sources

## Data Providers (20 Active)

### Primary Discovery & Enrichment
| # | Provider | Purpose | Rate Limit | Key Required | Provider File |
|---|----------|---------|------------|-------------|--------------|
| 1 | **DexScreener** | Token discovery (5 sources), pairs, boosts, CTOs, ads | 60-300/min | ❌ Free | `dexscreener.py` |
| 2 | **Moralis Money Pro** | Discovery (trending, filtered), analytics, token metadata | 25 CU/call | ✅ `MORALIS_API_KEY` (Pro) | `moralis_money.py` |
| 3 | **Moralis Wallet** | Enhanced token metadata, FDV, spam detection, social links | 25 CU/call | ✅ `MORALIS_API_KEY` | `moralis_wallet.py` |
| 4 | **Moralis Price** | Real-time token prices across EVM + Solana | 25 CU/call | ✅ `MORALIS_API_KEY` | `moralis_price.py` |
| 5 | **Moralis Solana** | Sniper detection, top holders, pair analytics, OHLCV | 25 CU/call | ✅ `MORALIS_API_KEY` | `moralis_solana.py` |
| 6 | **Binance Pulse** | Smart money, social hype, unified rankings | 60/min | ❌ Free | `binance_pulse.py` |
| 7 | **GeckoTerminal** | OHLCV candle data for TA, pair analytics | 30/min | ❌ Free | `ohlcv_provider.py` |

### Scoring & Analysis
| # | Provider | Purpose | Rate Limit | Key Required | Provider File |
|---|----------|---------|------------|-------------|--------------|
| 8 | **Social Scoring** | LunarCrush + CoinGecko + DexScreener profile analysis | 4/min (LC) | ✅ `LUNARCRUSH_API_KEY` | `social_scoring.py` |
| 9 | **Smart Money** | Whale wallet overlap detection | Part of Moralis CU | ✅ `MORALIS_API_KEY` | `smart_money.py` |
| 10 | **Dev Wallet History** | Wallet age, deploy frequency, sell patterns | Part of Moralis CU | ✅ `MORALIS_API_KEY` | `dev_wallet_history.py` |
| 11 | **Copycat Detector** | Fuzzy name/symbol match against 50+ high-profile tokens | Local | ❌ None | `copycat_detector.py` |
| 12 | **Holder Analysis** | Top holder concentration, distribution patterns | Part of Moralis CU | ✅ `MORALIS_API_KEY` | `holder_analysis.py` |
| 13 | **Grok X Sentiment** | Real-time X/Twitter AI sentiment analysis | 30/min | ✅ `GROK_API_KEY` | `grok_sentiment.py` |
| 14 | **CoinGecko** | Market data, volume validation | 30/min | Optional | `coingecko.py` |
| 15 | **CoinMarketCap** | Market cap, volume validation | 30/min | ✅ `CMC_API_KEY` | `coinmarketcap.py` |

### Legacy (Reduced Role — Replaced by Moralis)
| # | Provider | Status | Replaced By |
|---|----------|--------|-------------|
| 16 | **DefiLlama** | Reduced — TVL now from Moralis `liquidity_locked_pct` | Moralis Money Pro |
| 17 | **LunarCrush** | Reduced — sentiment now from Moralis `on_chain_strength` | Moralis Money Pro |
| 18 | **Token Unlocks** | Neutral 50 score — negligible for micro-caps | N/A |
| 19 | **Etherscan** | Still used for contract verification on ETH/L2 | N/A |

## Safety APIs (Pre-Trade Gates)

| Tool | Purpose | Action on Fail | Caching |
|------|---------|---------------|---------|
| **GoPlus** | Token security audit (honeypot, ownership, tax) | **REJECT trade** | 5 min |
| **Honeypot.is** | Live swap simulation | **REJECT trade** | 5 min |
| **Token Sniffer** | Scam pattern detection (score < 50 = reject) | **REJECT trade** | 5 min |
| **Moralis Sniper Detection** | Solana: ≥10 snipers or critical risk | **HARD BLOCK** | Per cycle |

## Execution APIs (Write — Real $$$)

| Tool | Chains | Purpose |
|------|--------|---------|
| **CoW Protocol** | Ethereum | MEV-protected batch auctions |
| **1inch Aggregator** | Base, Arbitrum, Polygon, BSC, Avalanche | Best-price routing |
| **Jupiter** | Solana | SOL DEX aggregation |
| **Trader Joe V2** | Avalanche | AVAX DEX routing |
| **Flashbots** | Ethereum | Private tx submission (MEV protection) |

## Notification APIs

| Tool | Purpose |
|------|---------|
| **Slack Webhooks** | Trade alerts, errors, daily summaries, sniper warnings |
| **Telegram Bot** | Mobile trade notifications |

## Moralis CU Budget (Pro Tier)
| Operation | CU Cost | Frequency |
|-----------|---------|-----------|
| `getFilteredTokens` | 25 CU | Every scan cycle |
| `getTrendingTokens` | 25 CU | Every scan cycle |
| `getDiscoveryToken` | 25 CU | Per candidate enrichment |
| `getTokenMetadata` | 5 CU | Per candidate enrichment |
| `getTokenSnipers` | 10 CU | Per Solana candidate |
| `getTokenTopHolders` | 10 CU | Per Solana candidate |
| `getTokenPrice` | 5 CU | Per position monitor cycle |
| **Estimated daily** | ~50K CU | At ~200 scans/day with 5 enrichments each |

## Rate Limit Policy
- **Moralis is primary** — manage CU budget carefully, 150K CU/day on Pro tier
- **DexScreener is free** — use generously for discovery
- **Binance Pulse is free** — no key needed, but be conservative (60/min)
- **LunarCrush is precious** — only 100 calls/day, used only for social_scoring.py on candidates
- **Cache aggressively** — GoPlus/Honeypot results cached 5 min to reduce API load
