# On-Chain Skills & Intelligence Playbook

> A living reference for on-chain capabilities available to the Shamrock Trading Bot. Each skill maps a Moralis/RPC endpoint to a concrete trading edge.

---

## 🎯 Solana-Specific Skills

### 1. Sniper Detection
**Endpoint**: `GET /token/{network}/pairs/{pairAddress}/snipers`
**CU Cost**: 50
**Edge**: Identify wallets that bought within the first few blocks of a token launch. High sniper count = likely insider/dev dump incoming. Use as a **negative signal** in gem scoring.

**Integration Points**:
- `gem_scanner.py` → Add sniper count to safety check
- `AI_FlightRisk.js` → Factor into risk assessment
- Slack alert when a position's token has >10 snipers

### 2. Wallet Swap History
**Endpoint**: `GET /account/{network}/{address}/swaps`
**CU Cost**: 50
**Edge**: Track our own trade history on-chain. Reconcile what the bot thinks it did vs. what actually happened. Also useful for analyzing smart money wallets.

**Integration Points**:
- `position_monitor.py` → Trade reconciliation
- Dashboard → Trade history verification
- Sniper wallet profiling

### 3. SPL Token Portfolio
**Endpoint**: `GET /account/{network}/{address}/portfolio`
**CU Cost**: 10
**Edge**: Full portfolio snapshot including native SOL + all SPL tokens + NFTs. Better than raw RPC for our dashboard.

**Integration Points**:
- `5_👛_Wallet_Overview.py` → Replace raw RPC with richer data
- `moralis_wallet.py` → Add Solana portfolio method

### 4. Token Top Holders
**Endpoint**: `GET /token/{network}/{address}/top-holders`
**CU Cost**: 50
**Edge**: See who owns the most. If top 10 holders own >80%, it's a rug risk. If smart money wallets appear, it's bullish signal.

**Integration Points**:
- `gem_scanner.py` → Holder concentration check
- `smart_money.py` → Cross-reference with known wallets

### 5. Pump.fun Graduated Tokens
**Endpoint**: `GET /token/{network}/exchange/pumpfun/graduated`
**CU Cost**: 25
**Edge**: Monitor tokens graduating from Pump.fun bonding curve to Raydium. This is THE moment for early entry — the token just proved it has demand.

**Integration Points**:
- `gem_scanner.py` → New signal source for Solana gems
- Could power a dedicated "Pump Graduate" strategy

### 6. Token Pairs & Liquidity
**Endpoint**: `GET /token/{network}/{address}/pairs`
**CU Cost**: 25
**Edge**: Find all DEX pairs for a token. Check liquidity depth before entering. Low liquidity = high slippage risk.

**Integration Points**:
- `solana_executor.py` → Route selection (best pair for lowest slippage)
- Pre-trade liquidity check

### 7. Token OHLCV (Candlestick Data)
**Endpoint**: `GET /token/{network}/ohlcv`
**CU Cost**: 10
**Edge**: Native Solana candlestick data from Moralis. Eliminates need for GeckoTerminal fallback on Solana tokens.

**Integration Points**:
- `ohlcv_provider.py` → Add Moralis Solana as OHLCV source
- `signal_scorer.py` → Better TA data for Solana gems

### 8. Token Historical Holders
**Endpoint**: `GET /token/{network}/{address}/top-holders/historical`
**CU Cost**: 100
**Edge**: Track holder count over time. Rising holders = growing adoption. Falling holders = distribution/dump.

**Integration Points**:
- `gem_scanner.py` → Holder growth rate signal
- Position exit signal: holder count dropping rapidly

---

## 🔗 EVM Skills (Already Integrated)

### 9. Wallet Net Worth (Multi-Chain)
**Endpoint**: `GET /wallets/{address}/net-worth`
**Status**: ✅ Active in `moralis_wallet.py`
**Used By**: Wallet Overview dashboard

### 10. Token Price (Batch)
**Endpoint**: `POST /erc20/prices`
**Status**: ✅ Active in `moralis_wallet.py`
**Used By**: Position valuation, P&L calculation

### 11. Wallet Token Balances
**Endpoint**: `GET /wallets/{address}/tokens`
**Status**: ✅ Active in `moralis_wallet.py`
**Used By**: Wallet Overview token table

### 12. Wallet PnL Summary (Lightweight)
**Endpoint**: `GET /wallets/{address}/profitability/summary`
**Status**: ✅ Active in `moralis_wallet.py` — 30 CU (cheaper than 50 CU breakdown)
**Used By**: Dashboard P&L display, aggregate performance tracking

### 13. Enhanced Token Balances v2
**Endpoint**: `GET /wallets/{address}/tokens`
**Status**: ✅ Active in `moralis_wallet.py` — 100 CU with spam/liquidity/inactivity filters + portfolio %
**Used By**: Wallet Overview, portfolio analysis

### 14. Wallet Stats (Smart Money Profiling)
**Endpoint**: `GET /wallets/{address}/stats`
**Status**: ✅ Active in `moralis_wallet.py` → wired into `smart_money.py`
**Used By**: Smart money detection — profiles top holders by TX count

### 15. Enhanced Token Metadata
**Endpoint**: `GET /erc20/metadata`
**Status**: ✅ Active in `moralis_wallet.py` → wired into `gem_scanner.py`
**Used By**: FDV/spam/social-link enrichment, contract verification — only 10 CU per batch!

---

## 🧠 Intelligence Combos (Multi-Skill Plays)

### Combo A: "Smart Sniper Filter"
1. Token appears in gem scanner → 2. Check snipers endpoint → 3. If <5 snipers AND holder count rising → 4. Check top holders for concentration → 5. If top 10 < 60% → **BUY signal boosted**
✅ **Partially implemented**: Wallet stats profiling cross-references top holders' TX counts.

### Combo B: "Pump Graduate Catcher"
1. Monitor Pump.fun graduated endpoint every 60s → 2. Filter by initial liquidity > $10K → 3. Check holder count and sniper ratio → 4. If clean → **Auto-enter with micro position**

### Combo C: "Portfolio Reconciliation"
1. Fetch on-chain swap history → 2. Compare vs. `trades.json` → 3. Flag mismatches → 4. Alert on Slack if position exists on-chain but not in bot state
✅ **Partially implemented**: PnL summary endpoint provides aggregate trade data for reconciliation.

---

## 📊 CU Budget Planning

| Skill | CU/Call | Est. Daily Calls | Daily CU |
|-------|---------|------------------|----------|
| Token Price | 10 | 500 | 5,000 |
| Portfolio | 10 | 100 | 1,000 |
| Snipers | 50 | 50 | 2,500 |
| Swap History | 50 | 20 | 1,000 |
| Top Holders | 50 | 50 | 2,500 |
| OHLCV | 10 | 200 | 2,000 |
| Pump.fun Grad | 25 | 100 | 2,500 |
| Token Metadata | 10 | 100 | 1,000 |
| Wallet Stats | 50 | 30 | 1,500 |
| PnL Summary | 30 | 50 | 1,500 |
| **Total** | | | **~22,500** |

---

## 🚧 TODO: Skills to Build

- [x] Wire sniper detection into `gem_scanner.py` safety checks ✅ *(Antigravity — via `moralis_solana.py`)*
- [x] Add Pump.fun graduated token monitor as new signal source ✅ *(Antigravity — via `moralis_solana.py`)*
- [x] Wire enhanced token metadata (FDV/spam/social) into gem scoring ✅ *(Antigravity — `gem_scanner.py`)*
- [x] Add Moralis wallet stats profiling to smart money detection ✅ *(Antigravity — `smart_money.py`)*
- [x] Implement PnL summary endpoint for lightweight portfolio tracking ✅ *(Antigravity — `moralis_wallet.py`)*
- [x] Implement enhanced token balances v2 with spam/liquidity filters ✅ *(Antigravity — `moralis_wallet.py`)*
- [x] Whale accumulation discovery via `netExperiencedBuyers` ✅ *(Antigravity — `moralis_money.py`)*
- [x] Discovery token deep enrichment (security, holders, exp buyers, liquidity) ✅ *(Antigravity — `moralis_money.py`)*
- [x] Whale accumulation signals wired into gem scoring (20% bonus weight) ✅ *(Antigravity — `moralis_money.py`)*
- [x] Security score enforcement — low score penalizes contract_score ✅ *(Antigravity — `gem_scanner.py`)*
- [x] Fix `getFilteredTokens` timeframe bugs (securityScore/totalLiquidityUsd → oneDay) ✅ *(Antigravity — `moralis_money.py`)*
- [x] Implement Moralis Solana OHLCV as primary candlestick provider ✅ *(Manus — `moralis_solana.get_token_ohlcv`, wired into `ohlcv_provider.py` Source 0)*
- [x] Build "Smart Sniper Filter" combo (Combo A) ✅ *(Antigravity)*
- [x] Add holder growth rate to signal scoring ✅ *(Antigravity — via `get_discovery_token_details`)*
- [x] Create trade reconciliation pipeline (Combo C) ✅ *(Antigravity — `core/reconciliation.py`)*
- [x] Upgrade batch analytics to 200 tokens per call (chunked 30/req) ✅ *(Manus — `moralis_money.py`)*
- [x] Replace raw RPC SOL balance with Moralis portfolio endpoint ✅ *(Antigravity — Wallet Overview dashboard)*
- [x] Slack alert integration for reconciliation mismatches and sniper warnings ✅ *(Antigravity — `gem_scanner.py` + `core/reconciliation.py`)*

### 🤖 Manus Tasks (To Hand Off)
- [ ] Wire `getSnipersByPairAddress__solana` into `smart_money.py` for Smart Sniper Filter (Combo A completion)
- [ ] Wire `getCandleSticks__solana` as primary Solana OHLCV provider in `ohlcv_provider.py`
- [ ] Wire `getMultipleTokenAnalytics` for batch enrichment (up to 200 tokens) in gem scanner

### 🔮 Future / Phase 2
- [ ] **Phase 2**: Consolidate EVM RPC endpoints under Moralis Nodes (`site1.moralis-nodes.com/{chain}/:apiKey`) — single API key for Base, BSC, Avalanche, Ethereum. Reduces `.env` complexity and provides 99.9% SLA + archive access. Ref: `docs/moralis/RPC_nodes`

> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Onchain Skills

> Give your AI agent the ability to query blockchain data using Moralis APIs. Works with Claude Code, Cursor, Windsurf, GitHub Copilot, Cline, Codex, Gemini, and more.

## What are Onchain Skills?

Onchain Skills is an open-source package that lets AI agents call the [Moralis API](https://admin.moralis.com/register) directly — giving them the ability to query blockchain data from 40+ EVM chains and Solana in real time.

It works with any agent that supports the [Agent Skills](https://skills.sh/) standard, including **Claude Code, Cursor, Windsurf, GitHub Copilot, Cline, Codex, Gemini**, and 18+ others.

<iframe width="100%" height="400" src="https://www.youtube.com/embed/hq-SlxYji4w" title="Build Web3 Apps With AI Using Real Onchain Data | Moralis Onchain Skills" frameBorder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />

***

## Quick Start

### 1. Install the Skills

```bash  theme={null}
npx skills add MoralisWeb3/onchain-skills
```

### 2. Set Your API Key

Get your key from [admin.moralis.com](https://admin.moralis.com/register), then add it to a `.env` file in your project root:

```bash  theme={null}
echo "MORALIS_API_KEY=your_key_here" >> .env
```

That's it — your AI agent can now query blockchain data through Moralis.

***

## Skills Overview

Onchain Skills includes three skills:

| Skill                   | Description                                    | Endpoints |
| ----------------------- | ---------------------------------------------- | --------- |
| **moralis-data-api**    | EVM + Solana blockchain data                   | 136       |
| **moralis-streams-api** | Real-time event monitoring with webhooks       | 20        |
| **learn-moralis**       | Routing, FAQ, pricing, and capability guidance | —         |

### moralis-data-api

Unified skill for all blockchain data queries. Auto-detects EVM vs Solana from address format. For EVM addresses without a specified chain, defaults to Ethereum.

**136 endpoints** (102 EVM + 34 Solana) across these categories:

* **Wallet** (17) — balances, tokens, NFTs, history, profitability, net worth
* **Token** (22) — prices, metadata, pairs, DEX swaps, analytics, security scores, snipers
* **NFT** (22) — metadata, transfers, traits, rarity, floor prices, trades
* **DeFi** (3) — protocol positions, liquidity, exposure
* **Entity** (2) — labeled addresses (exchanges, funds, whales)
* **Price** (4) — OHLCV, token prices, pair prices
* **Blockchain** (5) — blocks, transactions, date-to-block
* **Discovery** (13) — trending tokens, market movers, top gainers/losers
* **Other** (14) — address resolution, token search, bonding, candlesticks, graduated tokens
* **Solana** (34) — native Solana endpoints + EVM endpoints with Solana support

**Example prompts:**

```
/moralis-data-api Get the balance of 0x1234...

/moralis-data-api Get the balance of 0x1234... on Polygon

/moralis-data-api Get the balance of Solana wallet ABC123...
```

### moralis-streams-api

Real-time blockchain event monitoring with webhooks. **20 endpoints** for creating, managing, and monitoring streams.

**Stream types:** `tx`, `log`, `erc20transfer`, `erc20approval`, `nfttransfer`, `internalTx`

**Example prompts:**

```
/moralis-streams-api Create a stream to monitor all ERC20 transfers on Ethereum

/moralis-streams-api Pause the stream with ID abc123
```

### learn-moralis

Knowledge-only skill for answering general questions about Moralis. Routes you to the correct technical skill after answering.

**Example prompts:**

```
/learn-moralis What is Moralis?

/learn-moralis Which Moralis API should I use for tracking wallet activity?
```

***

## Supported Chains

**EVM (40+):** Ethereum, Polygon, BNB Smart Chain, Arbitrum, Optimism, Avalanche, Fantom, Base, Sei, Monad, and more.

**Solana:** Mainnet and Devnet.

For the full list of supported chains, see [Supported Chains](/get-started/supported-chains).

***

## Architecture

* **Zero dependencies** — all API calls use curl
* **Works with 18+ agents** — any agent supporting the Agent Skills standard
* **Auto-detects chain** — determines EVM vs Solana from address format

***

## Resources

* [GitHub Repository](https://github.com/MoralisWeb3/onchain-skills)
* [Get an API Key](https://admin.moralis.com/register)
* [Agent Skills Standard](https://skills.sh/)
* [Video Tutorial: Build Web3 Apps With AI Using Real Onchain Data](https://www.youtube.com/watch?v=hq-SlxYji4w)


Built with [Mintlify](https://mintlify.com).
>>>>>>> 4216179 (feat: Moralis portfolio integration, reconciliation pipeline, sniper alerts, docs)
