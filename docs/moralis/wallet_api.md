# Moralis Wallet API
<!-- Paste the FULL Wallet API documentation here (PnL, Net Worth, Balances, History, Swaps) -->
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet API

> A unified Wallet API to fetch balances, transfers, DeFi positions, PnL, NFTs, and fully decoded wallet activity across multiple chains.

## Overview

The **Wallet API** provides complete wallet intelligence across all activity types - tokens, NFTs, DeFi positions, swaps, and P\&L tracking.

Instead of querying multiple endpoints and aggregating data yourself, the Wallet API gives you a unified view of any wallet's holdings, history, and financial performance across chains.

***

## What Is the Wallet API?

The Wallet API lets you query everything about a wallet address:

* **Asset Holdings** - Token balances, NFT collections, and ownership data
* **Transaction History** - Raw and decoded transactions with human-readable labels
* **DeFi Positions** - Protocol exposure across lending, staking, and liquidity pools
* **Financial Metrics** - Net worth calculations and profit/loss tracking
* **Identity** - ENS name resolution and address labels
* **Approvals** - Token allowances granted to contracts

***

## Key Features

The Wallet API includes:

* **Decoded Transactions** - Human-readable transaction labels and summaries
* **Multi-Chain Support** - Query across all supported EVM chains
* **Net Worth Calculation** - Aggregate USD value of all holdings
* **P\&L Tracking** - Realized and unrealized profit/loss per token
* **Swap History** - DEX trading activity with token pairs and values
* **NFT Trades** - Marketplace activity including buys, sells, and listings
* **Chain Activity** - Identify which chains a wallet is active on

***

## Common Use Cases

The Wallet API is commonly used for:

* **Portfolio Trackers**\
  (display holdings, value, and performance)
* **Wallet Explorers**\
  (transaction history and activity feeds)
* **DeFi Dashboards**\
  (show positions across protocols)
* **Tax Tools**\
  (calculate gains/losses from trading)
* **Security Apps**\
  (monitor approvals and revoke permissions)
* **Identity Resolution**\
  (resolve ENS names and wallet labels)

***

## Popular Endpoints

| Endpoint                                                          | Description                     |
| ----------------------------------------------------------------- | ------------------------------- |
| [Wallet History](/data-api/evm/wallet/wallet-history)             | Complete decoded activity feed  |
| [Token Balances](/data-api/evm/wallet/token-balances)             | Current ERC-20 holdings         |
| [NFT Balances](/data-api/evm/wallet/nft-balances)                 | Current NFT holdings            |
| [Net Worth](/data-api/evm/wallet/net-worth)                       | Total wallet value in USD       |
| [Wallet P\&L](/data-api/evm/wallet/wallet-pnl)                    | Profit/loss per token           |
| [Decoded Transactions](/data-api/evm/wallet/decoded-transactions) | Human-readable transaction data |

***

## Get Started

Explore some of the popular Wallet API endpoints:

* [Token Balances](/data-api/evm/wallet/token-balances)
* [NFT Balances](/data-api/evm/wallet/nft-balances)
* [Wallet History](/data-api/evm/wallet/wallet-history)
* [Net Worth](/data-api/evm/wallet/net-worth)


Built with [Mintlify](https://mintlify.com).