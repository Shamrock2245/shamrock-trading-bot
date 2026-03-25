# Moralis Price API

> Real-time and historical token prices, updated every block, across 40+ EVM chains and Solana.
>
> Docs: https://docs.moralis.com/web3-data-api/evm/reference/price

## Overview

The Moralis Price API provides instant token price data in both USD and native currency, with 24-hour percent change, security scores, and token metadata included in every response. Prices update with every new block, making it one of the fastest on-chain price feeds available.

---

## Authentication

```
X-API-Key: YOUR_MORALIS_API_KEY
```

Base URL: `https://deep-index.moralis.io/api/v2.2`

---

## Endpoints

### 1. Get Token Price (Single)

```
GET /erc20/{address}/price
```

Returns the current price of a single ERC-20 token.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `address` | string | ✅ | Token contract address |
| `chain` | string | ❌ | Chain ID (`eth`, `bsc`, `polygon`, `0x1`, `0x38`, etc.) |
| `exchange` | string | ❌ | Preferred DEX for price source |
| `to_block` | integer | ❌ | Historical price at specific block number |
| `include` | string | ❌ | `percent_change` to include 24hr change |

#### Example Request

```bash
curl -X GET \
  "https://deep-index.moralis.io/api/v2.2/erc20/0x6982508145454Ce325dDbE47a25d4ec3d2311933/price?chain=eth&include=percent_change" \
  -H "X-API-Key: $MORALIS_API_KEY"
```

#### Example Response

```json
{
  "tokenName": "Pepe",
  "tokenSymbol": "PEPE",
  "tokenLogo": "https://cdn.moralis.io/...",
  "tokenDecimals": "18",
  "tokenAddress": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
  "usdPrice": 0.00001234,
  "usdPriceFormatted": "0.00001234",
  "24hrPercentChange": "12.45",
  "nativePrice": {
    "value": "5432100000000",
    "decimals": 18,
    "name": "Ether",
    "symbol": "ETH",
    "address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
  },
  "exchangeName": "Uniswap v3",
  "exchangeAddress": "0x1f98431c8ad98523631ae4a59f267346ea31f984",
  "securityScore": 85
}
```

---

### 2. Get Multiple Token Prices (Batch)

```
POST /erc20/prices
```

Fetch prices for up to **100 tokens** in a single request.

#### Request Body

```json
{
  "tokens": [
    {
      "token_address": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
      "exchange": "uniswapv3"
    },
    {
      "token_address": "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    }
  ]
}
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tokens` | array | ✅ | Array of token objects (max 100) |
| `tokens[].token_address` | string | ✅ | Token contract address |
| `tokens[].exchange` | string | ❌ | Preferred exchange for price |
| `tokens[].to_block` | integer | ❌ | Block number for historical price |
| `chain` | string | ❌ | Chain ID (query param) |
| `include` | string | ❌ | `percent_change` for 24hr % |

#### Response

Returns an array of price objects (same format as single token).

See: [token_prices_batch.md](token_prices_batch.md)

---

### 3. Get OHLCV Data

```
GET /erc20/{address}/price/ohlcv
```

Candlestick data for charting.

| Parameter | Type | Description |
|-----------|------|-------------|
| `address` | string | Token contract address |
| `chain` | string | Chain ID |
| `timeframe` | string | Candle interval (`1h`, `4h`, `1d`, `1w`) |
| `from_date` | string | Start date (ISO 8601) |
| `to_date` | string | End date (ISO 8601) |
| `currency` | string | `usd` or native |

Response includes: `open`, `high`, `low`, `close`, `volume`, `timestamp`

See: [price_ohlcv.md](price_ohlcv.md)

---

### 4. Solana Token Price

```
GET /solana/token/{address}/price
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `address` | string | SPL token mint address |
| `network` | string | `mainnet` or `devnet` |

Same response format as EVM but for Solana tokens.

---

## Response Fields Reference

| Field | Type | Description |
|-------|------|-------------|
| `usdPrice` | number | Price in USD |
| `usdPriceFormatted` | string | Formatted USD price string |
| `24hrPercentChange` | string | 24-hour USD price change (%) |
| `nativePrice.value` | string | Price in native currency (wei/lamports) |
| `nativePrice.symbol` | string | Native currency symbol (ETH, BNB, etc.) |
| `tokenName` | string | Full token name |
| `tokenSymbol` | string | Token ticker symbol |
| `tokenDecimals` | string | Token decimal places |
| `tokenLogo` | string | URL to token logo image |
| `tokenAddress` | string | Contract address |
| `exchangeName` | string | Price source exchange |
| `exchangeAddress` | string | Exchange contract address |
| `securityScore` | integer | Token security score (0-100) |
| `blockTimestamp` | string | Timestamp of price data |

---

## Supported Chains

All 40+ EVM chains supported. Common values for the `chain` parameter:

| Chain | Values |
|-------|--------|
| Ethereum | `eth`, `0x1` |
| BSC | `bsc`, `0x38` |
| Polygon | `polygon`, `0x89` |
| Arbitrum | `arbitrum`, `0xa4b1` |
| Base | `base`, `0x2105` |
| Avalanche | `avalanche`, `0xa86a` |
| Optimism | `optimism`, `0xa` |
| Fantom | `fantom`, `0xfa` |

---

## Rate Limits & Compute Units

| Endpoint | CU Cost |
|----------|---------|
| Single token price | 3 CU |
| Batch token prices (up to 100) | 10 CU |
| OHLCV data | 5 CU |
| Solana token price | 3 CU |

---

## Why This Matters for Shamrock

### Current Usage

The trading bot **already uses** the Price API heavily:
- **Entry pricing**: `getTokenPrice` before every buy order
- **Position monitoring**: Periodic price checks for TP/stop evaluation
- **Gem scanner scoring**: Price and 24hr % change as scoring inputs
- **Batch pricing**: Portfolio valuation in the Streamlit dashboard

### Integration Opportunities

| Priority | Use Case | Endpoint |
|----------|----------|----------|
| 🟢 Active | Real-time entry/exit pricing | Single token price |
| 🟢 Active | Dashboard portfolio valuation | Batch prices |
| 🟢 Active | Scanner price change signals | 24hr percent change |
| 🟡 Medium | Historical price analysis | OHLCV data |
| 🟡 Medium | Security scoring enrichment | `securityScore` field |

---

## Python Usage

```python
import requests

MORALIS_URL = "https://deep-index.moralis.io/api/v2.2"

def get_token_price(token_address: str, chain: str = "eth") -> dict:
    """Get current price for a single ERC-20 token."""
    resp = requests.get(
        f"{MORALIS_URL}/erc20/{token_address}/price",
        params={"chain": chain, "include": "percent_change"},
        headers={"X-API-Key": os.getenv("MORALIS_API_KEY")},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

def get_batch_prices(tokens: list[dict], chain: str = "eth") -> list[dict]:
    """Get prices for multiple tokens (max 100)."""
    resp = requests.post(
        f"{MORALIS_URL}/erc20/prices",
        params={"chain": chain, "include": "percent_change"},
        headers={
            "X-API-Key": os.getenv("MORALIS_API_KEY"),
            "Content-Type": "application/json",
        },
        json={"tokens": tokens},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
```

---

## Related Docs

- [Token Prices Batch](token_prices_batch.md) — Detailed batch pricing documentation
- [Price OHLCV](price_ohlcv.md) — Candlestick data for charting
- [Charts & Widgets](charts_widgets.md) — Embeddable TradingView charts
- [Token Metadata](token_metadata.md) — Token name, symbol, decimals, logo