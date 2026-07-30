# Moralis API Updates & Capabilities Reference (2026)

This document provides a guide to the latest official Moralis API updates, features, and deprecations as of May–July 2026, and details how the Shamrock Trading Bot leverages them to achieve maximum capital efficiency and intelligence.

---

## 0. July 31 2026 Sunset — Shamrock Status (actioned 2026-07-30)

Moralis removes several Solana holder / launchpad discovery endpoints and makes Token Score **EVM-only** on **July 31, 2026**.

| Area | REST (dying) | Shamrock replacement |
|------|--------------|----------------------|
| Solana top holders | `GET /token/{net}/{addr}/top-holders` | Data Feeds `token_holders` SQL → Helius DAS / public RPC |
| Solana holder metrics / historical | `holders/*` | Free cascade / neutral (no CU) |
| Pump.fun new / bonding / graduated | `exchange/pumpfun/*` | Data Feeds `launchpad_events` → DexScreener Solana profiles |
| Solana bonding-status | `…/bonding-status` | Data Feeds `token_bonding_status` |
| Solana Token Score | `/tokens/{addr}/score` on Solana | Skipped (EVM score only) |
| EVM historical holders | `/erc20/…/holders/historical` | Neutral until Data Feeds historical_balances |

**Architecture modules**
- `data/providers/moralis_http.py` — shared GET/POST + live `x-request-weight` CU accounting
- `data/providers/moralis_datafeeds.py` — optional Postgres sink queries (0 CU)
- Soft budget: `MORALIS_MONTHLY_CU_BUDGET` (default 394M of ~500M Business plan)

**Live CU probes (2026-07-30 headers)**
- EVM price → `x-request-weight: 50`
- EVM token score → `x-request-weight: 100`
- Solana price → `X-Request-Weight: 10`
- Solana top-holders / graduated → `50` (still live today; blocked after cutover)

**Data Feeds next step (when access granted)**
1. Admin → Data Feeds → starter packs for **Token Holders** + **Token Bonding Status** (Solana)
2. `docker compose up` sink → Postgres
3. Set `MORALIS_DATAFEEDS_DSN=postgresql://…` and `MORALIS_DATAFEEDS_ENABLED=true`

---

## 1. Major New API Features & Capabilities

### 🟢 Solana DeFi Universal Positions API
* **What it is**: Moralis has expanded its Universal DeFi API to fully support the Solana mainnet. It exposes the exact same unified schema and endpoints as EVM chains.
* **Supported Protocols**: Jito, Marinade, Save (formerly Solend), Jupiter (Lending & Perpetual Exchange), Drift, Orca, Raydium, Kamino, Sanctum, and more.
* **Endpoints**:
  * `GET /wallets/{walletAddress}/defi/positions`
  * `GET /wallets/{walletAddress}/defi/summary`
* **Shamrock Integration**:
  * We have successfully integrated this capability into `get_wallet_defi_positions()` and enabled it in `smart_money.py`.
  * The bot now automatically qualifies top Solana token holders as active **DeFi Whales** if they carry $\ge \$50,000$ in active lending, perpetual, or liquidity pool positions across at least 2 protocols.

### 🟢 Multichain EVM DeFi Aggregation
* **What it is**: The EVM DeFi API supports over 5,000+ protocols across 96% of the market. It now supports consolidated multichain queries.
* **How it works**: By providing the `chains` parameter with a comma-separated list of chain identifiers (e.g., `chains="eth,base,arbitrum,bsc"`), developers can aggregate all of a wallet's DeFi positions across multiple networks in a **single API call**.
* **Value**: Drastically reduces overall latency and saves thousands of API compute units (credits) that would otherwise be consumed by chain-by-chain iteration.

### 🟢 Token Search API
* **What it is**: A new tool designed to instantly find tokens by name, symbol, or contract address across multiple networks.
* **Endpoint**: `GET /tokens/search`
* **Use Case**: Allows quick resolution of candidate gems on both EVM and Solana to populate real-time dashboards and handle natural language queries from operators in chat widgets.

### 🟢 Bitcoin Mempool & Solana Advanced Streams
* **Solana CPI Streams**: Real-time webhook deliveries now support **inner instruction tracing** and **pre/post token balance changes** for Cross-Program Invocations (CPIs). Extremely valuable for advanced alpha wallet/copy-trade tracking on Solana.
* **Bitcoin Mempool Streams**: Real-time unconfirmed mempool transaction notifications via webhooks, allowing unconfirmed BTC movements to be monitored prior to block inclusion.

### 🟢 Utility Protocols Endpoint
* **Endpoint**: `GET /v1/defi/protocols`
* **What it is**: Programmatically lists all currently supported DeFi protocols on a specific network.

---

## 2. Key Deprecations & Retirements

### 🔴 Hosted Cortex AI API (`/cortex/chat`) — Sunset: June 4, 2026
* **Status**: The Hosted Cortex AI REST API is being retired in favor of open-source, project-level **"Onchain Skills"** (designed for developer AI agents like Cursor, Claude, or local frameworks rather than programmatic execution).
* **Shamrock Protection**:
  * We have deactivated `cortex_analyze_token()` inside `moralis_intelligence.py` so it returns `None` immediately.
  * This guarantees that when the endpoint is decomissioned, the bot will experience **zero network timeouts, zero failed requests, and zero latency penalties** in its real-time scanning loop.

### 🔴 Fantom Mainnet (`0xfa`) — Sunset: May 29, 2026
* **Status**: Moralis is sunsetting support for Fantom Mainnet across all API endpoints in 2 days (May 29, 2026).
* **Shamrock Protection**:
  * An audit confirmed that the bot does not actively query, scan, or execute trades on Fantom, ensuring **zero trade disruptions**.

---

## 3. Getting the Most of the Pro Subscription

To maximize ROI on your Moralis Pro subscription, we apply these best practices:
1. **Unified Schema Ingestion**: Use standard universal endpoints (e.g., universal DeFi) rather than chain-specific gateways to keep logic clean and codebase footprints small.
2. **Aggregated Multichain Queries**: Leverage the `chains` query parameter wherever multiple networks are tracked to minimize compute unit consumption.
3. **Mempool/CPI Streaming**: Ensure our webhook streams are bound to high-accuracy triggers (like Solana pre/post balance changes) to act on trading signals seconds before standard RPC nodes propagate them.
