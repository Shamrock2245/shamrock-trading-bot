# Moralis Cortex API

> AI-native blockchain intelligence layer — natural language → on-chain insights.
>
> Docs: https://docs.moralis.com/cortex
> GitHub MCP Server: https://github.com/MoralisWeb3/moralis-mcp-server

## What Is Cortex?

Moralis Cortex is an AI-powered interface that translates **natural language prompts** into verified, real-time blockchain data queries. It sits on top of Moralis's full API suite (Wallet, Token, NFT, DeFi, Streams) and returns structured, explainable answers grounded in actual on-chain data — no hallucinations.

Two deployment modes:
1. **Hosted API** — single REST endpoint, zero infra overhead
2. **Self-Hosted MCP Server** — npm package, plug in your own LLM (OpenAI/Claude/open-source)

---

## Hosted API

### Endpoint

```
POST https://cortex-api.moralis.io/chat
```

### Authentication

Standard Moralis API key in the request header:
```
X-API-Key: YOUR_MORALIS_API_KEY
```

### Request Body

| Parameter   | Type    | Required | Description |
|-------------|---------|----------|-------------|
| `prompt`    | string  | ✅       | Natural language query about on-chain data |
| `streaming` | boolean | ❌       | `true` for chunked real-time response (default: `false`) |
| `model`     | string  | ❌       | LLM model to use (`gpt-nano`, `gpt-mini`; more coming) |
| `chatId`    | string  | ❌       | Chat session ID for multi-turn conversations with context |

### Example Request

```bash
curl -X POST https://cortex-api.moralis.io/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MORALIS_API_KEY" \
  -d '{
    "prompt": "What tokens has wallet 0x5c95... been buying in the last 24 hours?",
    "streaming": false,
    "model": "gpt-mini"
  }'
```

### Response

Returns structured JSON with:
- **Summary** — human-readable explanation of the answer
- **Data** — structured blockchain data backing the answer
- **Sources** — which Moralis API endpoints were queried

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Missing or malformed parameters |
| `401` | API key missing or invalid |
| `404` | Resource not found (token, pair, etc.) |
| `429` | Rate limited — upgrade plan or backoff |
| `500` | Internal server error |

---

## Self-Hosted MCP Server

The **Model Context Protocol (MCP) Server** allows you to run Cortex within your own infrastructure with full control over the LLM, data pipeline, and grounding logic.

### Installation

```bash
npm install moralis-mcp-server
```

### Configuration

```json
{
  "moralisApiKey": "YOUR_MORALIS_API_KEY",
  "llm": {
    "provider": "openai",
    "model": "gpt-4o",
    "apiKey": "YOUR_OPENAI_KEY"
  },
  "transport": "stdio"
}
```

### Transport Types

| Transport        | Use Case |
|------------------|----------|
| `stdio`          | CLI tools, local development, piped I/O |
| `web`            | HTTP server for web apps |
| `streamable-http`| Real-time streaming responses |

### Available Tools (Exposed to LLM)

The MCP server exposes the full Moralis API suite as "tools" the LLM can invoke:

| Category | Tools | Example Queries |
|----------|-------|-----------------|
| **Wallet** | History, balances, PnL, chains, net worth, DeFi positions | "Show transaction history for 0x... on Polygon" |
| **Token** | Price, metadata, transfers, holders, trending, swaps | "What's the current price of UNI?" |
| **NFT** | Collections, ownership, transfers, metadata | "Find all NFTs in CryptoPunks collection" |
| **DeFi** | Positions, liquidity, staking, yield | "What DeFi positions does this wallet hold?" |
| **Block** | Block data, timestamps, transactions | "Get block 18000000 details on Ethereum" |
| **Solana** | SPL tokens, portfolio, swaps, snipers | "Show Solana token holdings for wallet..." |

---

## Why This Matters for Shamrock

### Current Integration Opportunities

1. **AI Agent Intelligence** — Cortex can power The Concierge, Manus Brain, and The Analyst with natural language blockchain queries instead of raw API plumbing:
   - "Is this wallet a serial rug deployer?"
   - "Show me the top 10 buyers of token X in the last hour"
   - "What's the profit/loss for wallet 0x... on this token?"

2. **Gem Scanner Enhancement** — Use Cortex for complex multi-step analysis:
   - "Analyze the holder distribution and recent buy/sell pressure for token ABC"
   - "Is there whale accumulation on this token in the last 7 days?"

3. **Risk Assessment** — The Analyst can ask natural language risk questions:
   - "Are there any red flags for this token contract?"
   - "What percentage of liquidity is locked?"

4. **Dev Wallet Profiling** — Natural language dev wallet analysis:
   - "How many tokens has this deployer launched? What happened to them?"

5. **Dashboard Intelligence** — Power a natural language chat interface in the Streamlit dashboard for operators to query the portfolio

### Implementation Priority

| Priority | Use Case | Difficulty |
|----------|----------|------------|
| 🟢 High | Wallet profiling for dev reject scoring | Low — single POST call |
| 🟢 High | Token risk assessment for gem scanner | Low — structured response |
| 🟡 Medium | Multi-turn chat for Telegram bot | Medium — needs session management |
| 🟡 Medium | MCP server for AI agent orchestration | Medium — self-hosted infra |
| 🔵 Low | Dashboard chat widget | Low — UI integration |

---

## Example Prompts for Trading Bot

```python
# Dev wallet analysis
prompt = f"Analyze the deployer wallet {dev_address} on {chain}. How many tokens have they launched? What's their track record?"

# Token risk check
prompt = f"What are the security red flags for token {token_address} on {chain}? Check liquidity lock, holder concentration, and contract verification."

# Whale accumulation signal
prompt = f"Is there smart money accumulation on token {token_address}? Show net experienced buyers over the last 7 days."

# Portfolio P&L
prompt = f"What's the realized and unrealized profit/loss for wallet {wallet_address} on {chain}?"
```

---

## Python Integration Snippet

```python
import requests

CORTEX_URL = "https://cortex-api.moralis.io/chat"

def cortex_query(prompt: str, streaming: bool = False) -> dict:
    """Query Moralis Cortex API with a natural language prompt."""
    response = requests.post(
        CORTEX_URL,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": os.getenv("MORALIS_API_KEY"),
        },
        json={
            "prompt": prompt,
            "streaming": streaming,
            "model": "gpt-mini",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
```

---

## Rate Limits & Pricing

- Cortex API uses the same Moralis API key and plan as other Moralis endpoints
- Rate limits depend on your Moralis plan tier
- Each Cortex query may consume multiple API credits (it chains underlying API calls)
- The `429` status code indicates rate limiting — implement exponential backoff

## Related Docs

- [Wallet API](wallet_api.md) — Underlying wallet data endpoints
- [Solana API](solana_api.md) — Solana-specific token and wallet data
- [Streams API](streams_api.md) — Real-time webhook event streaming
- [DataShare API](datashare_api.md) — Bulk data access
