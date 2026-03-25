# Moralis Data API (EVM)

> Comprehensive EVM blockchain data — wallets, tokens, NFTs, transactions, DeFi, blocks.
>
> Docs: https://docs.moralis.com/web3-data-api/evm
> Swagger: https://deep-index.moralis.io/api-docs-2.2/

## Overview

The Moralis Web3 Data API for EVM chains provides a unified REST interface for accessing decoded, enriched on-chain data across **40+ EVM-compatible blockchains**. It eliminates the need to run your own indexers or parse raw transaction data — everything comes back structured with human-readable metadata, USD valuations, and cross-chain support.

---

## Authentication

All requests require a Moralis API key:
```
X-API-Key: YOUR_MORALIS_API_KEY
```

Base URL: `https://deep-index.moralis.io/api/v2.2`

---

## API Categories

### 1. Wallet API

Comprehensive wallet data — balances, history, PnL, net worth, DeFi positions.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/wallets/{address}/tokens` | GET | Token balances with USD prices |
| `/wallets/{address}/history` | GET | Full decoded transaction history |
| `/wallets/{address}/net-worth` | GET | Total portfolio value across chains |
| `/wallets/{address}/profitability/summary` | GET | Realized + unrealized P&L |
| `/wallets/{address}/defi/summary` | GET | DeFi positions across protocols |
| `/wallets/{address}/defi/positions` | GET | Detailed DeFi position breakdown |
| `/wallets/{address}/chains` | GET | Chains the wallet is active on |
| `/wallets/{address}/swaps` | GET | DEX swap history |
| `/wallets/{address}/nfts` | GET | NFT holdings |
| `/wallets/{address}/approvals` | GET | Token approval data (security) |

See: [wallet_api.md](wallet_api.md), [wallet_pnl.md](wallet_pnl.md), [wallet_net_worth.md](wallet_net_worth.md)

---

### 2. Token API

ERC-20 token data — prices, metadata, holders, transfers, liquidity, swaps.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/erc20/{address}/price` | GET | Current token price (USD + native) |
| `/erc20/prices` | POST | Batch prices for up to 100 tokens |
| `/erc20/{address}/price/ohlcv` | GET | OHLCV candlestick data |
| `/erc20/metadata` | GET | Token name, symbol, decimals, logo |
| `/erc20/{address}/holders` | GET | Token holder list + distribution |
| `/erc20/{address}/transfers` | GET | Token transfer history |
| `/erc20/{address}/top-gainers` | GET | Tokens with highest price gains |
| `/erc20/{address}/pairs` | GET | DEX trading pairs for a token |
| `/erc20/{address}/stats` | GET | Token statistics (volume, liquidity) |
| `/erc20/{address}/owners` | GET | Holder count and top holders |

See: [price_api.md](price_api.md), [price_ohlcv.md](price_ohlcv.md), [token_metadata.md](token_metadata.md), [token_prices_batch.md](token_prices_batch.md)

---

### 3. NFT API

NFT data — ownership, metadata, trades, collections, transfers.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/nft/{address}` | GET | NFTs in a collection |
| `/nft/{address}/{token_id}` | GET | Single NFT metadata |
| `/nft/{address}/{token_id}/owners` | GET | NFT current owner(s) |
| `/nft/{address}/{token_id}/transfers` | GET | NFT transfer history |
| `/nft/{address}/trades` | GET | NFT trade history with prices |
| `/nft/{address}/collections` | GET | Collection metadata |
| `/{address}/nft` | GET | NFTs owned by a wallet |
| `/{address}/nft/transfers` | GET | NFT transfers for a wallet |

---

### 4. DeFi API

DeFi position data across 100+ protocols — Aave, Compound, Uniswap, Lido, etc.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/wallets/{address}/defi/summary` | GET | High-level DeFi overview (total value, protocol count) |
| `/wallets/{address}/defi/positions` | GET | Detailed positions: deposits, borrows, rewards, LP |
| `/wallets/{address}/defi/{protocol}/positions` | GET | Positions for a specific protocol |

Features:
- **Auto-detection**: Identifies which protocols a wallet uses
- **Position breakdown**: Deposits, borrows, LP positions, staking, rewards
- **USD valuations**: Real-time dollar values for all positions
- **100+ protocols**: Aave, Compound, Uniswap, Curve, Lido, Yearn, MakerDAO, etc.

See: [defi_positions.md](defi_positions.md)

---

### 5. Blockchain API

Block and transaction data.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/block/{block_number_or_hash}` | GET | Block details + transactions |
| `/block/{block_number_or_hash}/nft/transfers` | GET | NFT transfers in a block |
| `/transaction/{transaction_hash}` | GET | Decoded transaction details |
| `/{address}` | GET | Native balance for an address |
| `/dateToBlock` | GET | Block number from a date/timestamp |

See: [blockchain_api.md](blockchain_api.md)

---

### 6. Streams API

Real-time webhook events for on-chain activity.

| Feature | Description |
|---------|-------------|
| **Contract events** | Monitor specific smart contract events |
| **Wallet activity** | Get notified on wallet transactions |
| **Token transfers** | Track ERC-20/ERC-721/ERC-1155 transfers |
| **Native transfers** | Monitor ETH/MATIC/BNB sends |
| **Custom filters** | Filter by amount, address, function signature |

See: [streams_api.md](streams_api.md)

---

### 7. Auth API

Web3 authentication flow.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/requestMessage` | POST | Request a sign-in message |
| `/auth/verify` | POST | Verify signed message + get profile |

See: [auth_api.md](auth_api.md)

---

## Supported Chains

| Chain | ID | Status |
|-------|----|--------|
| Ethereum | `0x1` | ✅ |
| BSC | `0x38` | ✅ |
| Polygon | `0x89` | ✅ |
| Arbitrum | `0xa4b1` | ✅ |
| Base | `0x2105` | ✅ |
| Avalanche | `0xa86a` | ✅ |
| Optimism | `0xa` | ✅ |
| Fantom | `0xfa` | ✅ |
| Cronos | `0x19` | ✅ |
| Linea | `0xe708` | ✅ |

**40+ chains total** — including all major L1s and L2s.

---

## Common Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `chain` | string | Chain identifier (`eth`, `bsc`, `polygon`, `0x1`, etc.) |
| `from_date` / `to_date` | string | ISO 8601 date range filter |
| `from_block` / `to_block` | integer | Block range filter |
| `limit` | integer | Results per page (max 100) |
| `cursor` | string | Pagination cursor for next page |
| `order` | string | `ASC` or `DESC` sort order |

---

## Rate Limits

| Plan | Requests/sec | Compute Units/day |
|------|-------------|-------------------|
| Free | 25 | 40,000 |
| Starter | 25 | 100,000 |
| Growth | 25 | 350,000 |
| Business | 50 | 1,000,000+ |
| Enterprise | Custom | Custom |

Each endpoint has a different **compute unit (CU) cost** — simple lookups cost 1-5 CU, complex queries 10-25 CU.

---

## Why This Matters for Shamrock

### Current Usage

The trading bot already uses these endpoints via the Moralis provider modules:
- **Token prices** — `erc20/{address}/price` for entry/exit pricing
- **Wallet balances** — `wallets/{address}/tokens` for position tracking
- **Token metadata** — `erc20/metadata` for symbol/decimals in logging

### Integration Opportunities

| Priority | Use Case | Endpoint |
|----------|----------|----------|
| 🟢 High | Dev wallet profiling | `/wallets/{address}/history` + `/tokens` |
| 🟢 High | Token holder distribution | `/erc20/{address}/holders` |
| 🟡 Medium | DeFi protocol exposure | `/wallets/{address}/defi/positions` |
| 🟡 Medium | Whale transfer monitoring | Streams API webhook |
| 🔵 Low | Cross-chain wallet tracking | `/wallets/{address}/chains` |

---

## Related Docs

- [Solana API](solana_api.md) — Solana-specific endpoints (SPL tokens, snipers, OHLCV)
- [DataShare API](datashare_api.md) — Bulk data access for large-scale analysis
- [Cortex API](cortex_api.md) — AI-powered natural language blockchain queries
