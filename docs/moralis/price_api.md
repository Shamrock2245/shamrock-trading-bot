# Moralis Price API
<!-- Paste the Price API documentation here (Token Prices, OHLCV, Batch Prices) -->
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Price API

> Real-time crypto prices, OHLC, trading volume.

## Overview

The **Price API** provides real-time and historical pricing data for tokens and NFTs across all supported EVM chains.

Get current prices, OHLC candlestick data, floor prices, and trading volume without managing your own price feeds or aggregation infrastructure.

***

## What Is the Price API?

The Price API lets you query:

* **Token Prices** - Current USD prices for any ERC-20 token
* **OHLC Data** - Candlestick data for charting and technical analysis
* **NFT Floor Prices** - Current and historical floor prices by collection
* **Sale Prices** - Recent NFT sales with transaction details
* **Batch Queries** - Fetch prices for multiple tokens in one request

***

## Key Features

The Price API includes:

* **Real-Time Prices** - Current token prices with USD values
* **Historical Data** - Price history for trend analysis
* **OHLC Candles** - Open, high, low, close data for charting
* **Floor Price History** - Track NFT collection floor over time
* **Batch Support** - Query multiple tokens efficiently
* **Multi-Chain** - Consistent pricing across all EVM chains

***

## Common Use Cases

The Price API is commonly used for:

* **Price Feeds**\
  (display current token prices in apps)
* **Trading Charts**\
  (OHLC data for candlestick visualizations)
* **Portfolio Valuation**\
  (calculate holdings value in USD)
* **NFT Analytics**\
  (track floor price trends)
* **Alerts & Notifications**\
  (trigger on price thresholds)
* **Market Data Dashboards**\
  (aggregate pricing across tokens)

***

## Popular Endpoints

| Endpoint                                                              | Description                    |
| --------------------------------------------------------------------- | ------------------------------ |
| [Token Price](/data-api/evm/token/prices/token-price)                 | Get current price for a token  |
| [Token Prices (Batch)](/data-api/evm/token/prices/token-prices-batch) | Get prices for multiple tokens |
| [OHLC](/data-api/evm/price/ohlc)                                      | Candlestick data for charting  |
| [Collection Floor Price](/data-api/evm/price/collection-floor-price)  | Current NFT floor price        |
| [Historical Floor Price](/data-api/evm/price/timeseries-floor-price)  | Floor price over time          |


Built with [Mintlify](https://mintlify.com).