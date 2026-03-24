> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Streams

> Real-time blockchain webhooks for wallets, contracts, and on-chain events with guaranteed delivery and flexible filtering.

## Overview

Moralis **Streams** lets you receive **real-time blockchain events** directly in your backend via webhooks.

Instead of polling APIs or indexing chains yourself, Streams pushes on-chain activity to you the moment it happens - based on rules you define.

***

## What Is Moralis Streams?

Moralis Streams allows you to **listen to blockchain activity in real time**, including:

* Wallet activity (transfers, swaps, interactions)
* Contract events (via ABI decoding)
* NFT and token transfers
* Native and internal transactions
* Custom on-chain conditions using filters

When a matching event occurs, Moralis delivers a **webhook** to your server with a structured data payload.

***

## How Streams Works

At a high level:

1. A new block is produced on-chain
2. Moralis processes and evaluates the block
3. Your stream rules are applied
4. Matching events are detected
5. A webhook is delivered to your endpoint

All delivery is handled by Moralis - no nodes, polling, or infrastructure required.

***

## What You Can Listen To

With Streams, you can:

* Monitor one address or **millions of addresses** with a single stream
* Listen to **all contract events** or only specific ABI events
* Track transfers, swaps, mints, burns, and internal transactions
* Apply **advanced filters** (amounts, addresses, tokens, contracts)
* Run **read-only smart contract functions** as part of event processing
* Enrich events with balances and decoded data

***

## Common Use Cases

Streams is commonly used for:

* **Real-time wallet notifications**\
  (send, receive, swap, stake, burn)
* **Asset monitoring**\
  (token or NFT movement, price-sensitive events)
* **Games & apps**\
  (in-game actions, state changes, achievements)
* **Token sales & launches**\
  (participation tracking, contribution thresholds)
* **Protocol monitoring**\
  (liquidity events, contract interactions)

***

## Working With Webhooks

Streams delivers events via **HTTP webhooks**:

* Webhooks are sent using `POST` requests
* Payloads include decoded, structured event data
* Delivery is retried automatically on failure
* Events can be replayed manually if needed

To ensure correctness, Moralis sends a **mandatory test webhook** whenever a stream is created or updated.

***

## Reliability & Guarantees

Streams is built for production workloads:

* Guaranteed webhook delivery with retries
* Automatic backoff if your service is unavailable
* Manual replay support
* Spam detection and filtering
* Secure webhook signing

***

## When to Use Streams

Use Streams if you need:

* Real-time blockchain events
* Push-based architecture
* Low-latency notifications
* Reliable delivery without running infrastructure

If you only need historical data, use the [**Data APIs**](/data-api/overview) instead.

***

## Get Started

* **Quickstart**
* **Stream Configuration**
* **Webhooks**
* **Tutorials**

***

## Streams API Overview Video

<iframe src="https://www.youtube.com/embed/k_hk9Pchjc8" title="Monitor Onchain Events" width="100%" height="400" frameBorder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Pricing

> Understand how Streams API usage is calculated using records and compute units, and learn how to optimize your costs.

## Records

Records are the fundamental unit for calculating Streams API usage. A **record** is one of the following:

* A transaction (`txs`)
* A log event (`logs`)
* An internal transaction (`txsInternal`)

The total record count for a webhook equals the sum of all three: **txs + logs + txsInternal**.

## Charging Structure

Each record costs **10 Compute Units (CUs)**. The `x-records-charged` header in webhook responses shows the exact record count for that delivery.

<Info>Only webhooks with `confirmed: true` incur charges. Unconfirmed webhooks (`confirmed: false`) have `x-records-charged: 0` and are free.</Info>

For each transaction, you receive two webhooks:

1. **Unconfirmed** — Sent when the transaction is included in a block (free).
2. **Confirmed** — Sent once the block is considered final (charged).

## Records by Transaction Type

The number of records charged varies depending on transaction complexity:

| Transaction Type             | Records Charged |
| ---------------------------- | --------------- |
| Native transfer              | 1 record        |
| ERC20 transfer               | 2 records       |
| Single NFT transfer (ERC721) | 11 records      |
| Batch NFT transfer (ERC1155) | 2 records       |
| ERC721 minting (100 tokens)  | 100 records     |

## Decoded Logs Are Free

Moralis automatically decodes standardized contract events at **no additional cost**. These do **not** count as records:

* `erc20Transfers`
* `erc20Approvals`
* `nftTransfers`

## Monitoring Your Usage

Use the `/status` endpoint ([Get Stats](/streams/api-reference/stats/get-stats)) to track your consumption. It provides:

* `totalLogsProcessed`
* `totalTxsProcessed`
* `totalTxsInternalProcessed`

Sum these values to determine total records consumed during your billing period.

## Plan Limits

For details on CU allocations, throughput limits, and plan comparisons, visit the [Moralis Pricing Page](https://moralis.io/pricing).


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Streams Supported Chains

> Blockchains supported by Moralis Streams for real-time onchain event and activity monitoring.

### Streams Supported Chains

Moralis Streams provide **real-time onchain data delivery** via webhooks, allowing you to react to blockchain activity as it happens.

Streams support a subset of chains where:

* Real-time indexing is available
* Finality and reorg handling meet production requirements

Use the table below to see which chains are supported for Streams and what types of events can be monitored.

| Chain Name                  | Type    | Chain ID              | Streams Supported | Internal Txs | Blocks Until Confirmed |
| --------------------------- | ------- | --------------------- | ----------------- | ------------ | ---------------------- |
| Ethereum Mainnet            | Mainnet | 0x1 (1)               | ✓                 | ✓            | 12                     |
| Ethereum Sepolia            | Testnet | 0xaa36a7 (11155111)   | ✓                 | ✓            | 18                     |
| Polygon Mainnet             | Mainnet | 0x89 (137)            | ✓                 | ✓            | 100                    |
| Polygon Amoy                | Testnet | 0x13882 (80002)       | ✓                 | ✓            | 100                    |
| Binance Smart Chain Mainnet | Mainnet | 0x38 (56)             | ✓                 | ✓            | 18                     |
| Binance Smart Chain Testnet | Testnet | 0x61 (97)             | ✓                 | ✓            | 18                     |
| Arbitrum                    | Mainnet | 0xa4b1 (42161)        | ✓                 | ✓            | 18                     |
| Arbitrum Sepolia            | Testnet | 0x66eee (421614)      | ✓                 | ✓            | 600                    |
| Base                        | Mainnet | 0x2105 (8453)         | ✓                 | ✓            | 100                    |
| Base Sepolia                | Testnet | 0x14a34 (84532)       | ✓                 | ✓            | 100                    |
| Optimism                    | Mainnet | 0xa (10)              | ✓                 | ✓            | 500                    |
| Optimism Sepolia            | Testnet | 0xaa37dc (11155420)   | ✓                 | ✓            | 600                    |
| Linea                       | Mainnet | 0xe708 (59144)        | ✓                 | ✓            | 100                    |
| Linea Sepolia               | Testnet | 0xe705 (59141)        | ✓                 | ✓            | 100                    |
| Avalanche                   | Mainnet | 0xa86a (43114)        | ✓                 | ✓            | 100                    |
| Fantom Mainnet              | Mainnet | 0xfa (250)            | ✓                 | ✓            | 100                    |
| Fantom Testnet              | Testnet | 0xfa2 (4002)          | ✓                 | ✓            | 100                    |
| Cronos Mainnet              | Mainnet | 0x19 (25)             | ✓                 | ✗            | 100                    |
| Gnosis                      | Mainnet | 0x64 (100)            | ✓                 | ✗            | 100                    |
| Gnosis Chiado               | Testnet | 0x27d8 (10200)        | ✓                 | ✗            | 100                    |
| Chiliz Mainnet              | Mainnet | 0x15b38 (88888)       | ✓                 | ✓            | 100                    |
| Chiliz Testnet              | Testnet | 0x15b32 (88882)       | ✓                 | ✓            | 100                    |
| Moonbeam                    | Mainnet | 0x504 (1284)          | ✓                 | ✗            | 100                    |
| Moonriver                   | Testnet | 0x505 (1285)          | ✓                 | ✗            | 100                    |
| Moonbase                    | Testnet | 0x507 (1287)          | ✓                 | ✗            | 100                    |
| Blast                       | Mainnet | 0x13e31 (81457)       | ✗                 | ✗            | N/A                    |
| Blast Sepolia               | Testnet | 0xa0c71fd (168587773) | ✗                 | ✗            | N/A                    |
| zkSync                      | Mainnet | 0x144 (324)           | ✗                 | ✗            | N/A                    |
| zkSync Sepolia              | Testnet | 0x12c (300)           | ✗                 | ✗            | N/A                    |
| Mantle                      | Mainnet | 0x1388 (5000)         | ✗                 | ✗            | N/A                    |
| Mantle Sepolia              | Testnet | 0x138b (5003)         | ✗                 | ✗            | N/A                    |
| opBNB                       | Mainnet | 0xcc (204)            | ✗                 | ✗            | N/A                    |
| Polygon zkEVM               | Mainnet | 0x44d (1101)          | ✗                 | ✗            | N/A                    |
| Polygon zkEVM Cardona       | Testnet | 0x98a (2442)          | ✗                 | ✗            | N/A                    |
| Zetachain                   | Mainnet | 0x1b58 (7000)         | ✗                 | ✗            | N/A                    |
| Zetachain Testnet           | Testnet | 0x1b59 (7001)         | ✗                 | ✗            | N/A                    |
| Flow                        | Mainnet | 0x2eb (747)           | ✓                 | ✓            | 100                    |
| Flow Testnet                | Testnet | 0x221 (545)           | ✓                 | ✓            | 100                    |
| Ronin                       | Mainnet | 0x7e4 (2020)          | ✓                 | ✓            | 100                    |
| Ronin Saigon Testnet        | Testnet | 0x7e5 (2021)          | ✓                 | ✓            | 100                    |
| Lisk                        | Mainnet | 0x46f (1135)          | ✓                 | ✓            | 100                    |
| Lisk Sepolia Testnet        | Testnet | 0x106a (4202)         | ✓                 | ✓            | 100                    |
| Pulsechain                  | Mainnet | 0x171 (369)           | ✓                 | ✗            | 100                    |
| HyperEVM                    | Mainnet | 0x3e7 (999)           | ✓                 | ✓            | 100                    |
| Sei                         | Mainnet | 0x531 (1329)          | ✓                 | ✗            | N/A                    |
| Sei Testnet                 | Testnet | 0x530 (1328)          | ✓                 | ✗            | N/A                    |
| Monad                       | Mainnet | 0x8f (143)            | ✓                 | ✓            | 100                    |


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Streams Supported Chains

> Blockchains supported by Moralis Streams for real-time onchain event and activity monitoring.

### Streams Supported Chains

Moralis Streams provide **real-time onchain data delivery** via webhooks, allowing you to react to blockchain activity as it happens.

Streams support a subset of chains where:

* Real-time indexing is available
* Finality and reorg handling meet production requirements

Use the table below to see which chains are supported for Streams and what types of events can be monitored.

| Chain Name                  | Type    | Chain ID              | Streams Supported | Internal Txs | Blocks Until Confirmed |
| --------------------------- | ------- | --------------------- | ----------------- | ------------ | ---------------------- |
| Ethereum Mainnet            | Mainnet | 0x1 (1)               | ✓                 | ✓            | 12                     |
| Ethereum Sepolia            | Testnet | 0xaa36a7 (11155111)   | ✓                 | ✓            | 18                     |
| Polygon Mainnet             | Mainnet | 0x89 (137)            | ✓                 | ✓            | 100                    |
| Polygon Amoy                | Testnet | 0x13882 (80002)       | ✓                 | ✓            | 100                    |
| Binance Smart Chain Mainnet | Mainnet | 0x38 (56)             | ✓                 | ✓            | 18                     |
| Binance Smart Chain Testnet | Testnet | 0x61 (97)             | ✓                 | ✓            | 18                     |
| Arbitrum                    | Mainnet | 0xa4b1 (42161)        | ✓                 | ✓            | 18                     |
| Arbitrum Sepolia            | Testnet | 0x66eee (421614)      | ✓                 | ✓            | 600                    |
| Base                        | Mainnet | 0x2105 (8453)         | ✓                 | ✓            | 100                    |
| Base Sepolia                | Testnet | 0x14a34 (84532)       | ✓                 | ✓            | 100                    |
| Optimism                    | Mainnet | 0xa (10)              | ✓                 | ✓            | 500                    |
| Optimism Sepolia            | Testnet | 0xaa37dc (11155420)   | ✓                 | ✓            | 600                    |
| Linea                       | Mainnet | 0xe708 (59144)        | ✓                 | ✓            | 100                    |
| Linea Sepolia               | Testnet | 0xe705 (59141)        | ✓                 | ✓            | 100                    |
| Avalanche                   | Mainnet | 0xa86a (43114)        | ✓                 | ✓            | 100                    |
| Fantom Mainnet              | Mainnet | 0xfa (250)            | ✓                 | ✓            | 100                    |
| Fantom Testnet              | Testnet | 0xfa2 (4002)          | ✓                 | ✓            | 100                    |
| Cronos Mainnet              | Mainnet | 0x19 (25)             | ✓                 | ✗            | 100                    |
| Gnosis                      | Mainnet | 0x64 (100)            | ✓                 | ✗            | 100                    |
| Gnosis Chiado               | Testnet | 0x27d8 (10200)        | ✓                 | ✗            | 100                    |
| Chiliz Mainnet              | Mainnet | 0x15b38 (88888)       | ✓                 | ✓            | 100                    |
| Chiliz Testnet              | Testnet | 0x15b32 (88882)       | ✓                 | ✓            | 100                    |
| Moonbeam                    | Mainnet | 0x504 (1284)          | ✓                 | ✗            | 100                    |
| Moonriver                   | Testnet | 0x505 (1285)          | ✓                 | ✗            | 100                    |
| Moonbase                    | Testnet | 0x507 (1287)          | ✓                 | ✗            | 100                    |
| Blast                       | Mainnet | 0x13e31 (81457)       | ✗                 | ✗            | N/A                    |
| Blast Sepolia               | Testnet | 0xa0c71fd (168587773) | ✗                 | ✗            | N/A                    |
| zkSync                      | Mainnet | 0x144 (324)           | ✗                 | ✗            | N/A                    |
| zkSync Sepolia              | Testnet | 0x12c (300)           | ✗                 | ✗            | N/A                    |
| Mantle                      | Mainnet | 0x1388 (5000)         | ✗                 | ✗            | N/A                    |
| Mantle Sepolia              | Testnet | 0x138b (5003)         | ✗                 | ✗            | N/A                    |
| opBNB                       | Mainnet | 0xcc (204)            | ✗                 | ✗            | N/A                    |
| Polygon zkEVM               | Mainnet | 0x44d (1101)          | ✗                 | ✗            | N/A                    |
| Polygon zkEVM Cardona       | Testnet | 0x98a (2442)          | ✗                 | ✗            | N/A                    |
| Zetachain                   | Mainnet | 0x1b58 (7000)         | ✗                 | ✗            | N/A                    |
| Zetachain Testnet           | Testnet | 0x1b59 (7001)         | ✗                 | ✗            | N/A                    |
| Flow                        | Mainnet | 0x2eb (747)           | ✓                 | ✓            | 100                    |
| Flow Testnet                | Testnet | 0x221 (545)           | ✓                 | ✓            | 100                    |
| Ronin                       | Mainnet | 0x7e4 (2020)          | ✓                 | ✓            | 100                    |
| Ronin Saigon Testnet        | Testnet | 0x7e5 (2021)          | ✓                 | ✓            | 100                    |
| Lisk                        | Mainnet | 0x46f (1135)          | ✓                 | ✓            | 100                    |
| Lisk Sepolia Testnet        | Testnet | 0x106a (4202)         | ✓                 | ✓            | 100                    |
| Pulsechain                  | Mainnet | 0x171 (369)           | ✓                 | ✗            | 100                    |
| HyperEVM                    | Mainnet | 0x3e7 (999)           | ✓                 | ✓            | 100                    |
| Sei                         | Mainnet | 0x531 (1329)          | ✓                 | ✗            | N/A                    |
| Sei Testnet                 | Testnet | 0x530 (1328)          | ✓                 | ✗            | N/A                    |
| Monad                       | Mainnet | 0x8f (143)            | ✓                 | ✓            | 100                    |


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Receive Your First Webhook

> Understand the webhook lifecycle, payload structure, and how to handle confirmed and unconfirmed webhooks from Moralis Streams.

Once your stream is active, Moralis will send webhook `POST` requests to your configured URL whenever monitored addresses are involved in on-chain events.

## Mandatory Test Webhook

Whenever you create or update a stream, you will receive a **test webhook**. You must return a `200` status code (or any `2xx` code) for the stream to start delivering real data.

The test body looks like this:

```json  theme={null}
{
  "abi": {},
  "block": {
    "hash": "",
    "number": "",
    "timestamp": ""
  },
  "txs": [],
  "txsInternal": [],
  "logs": [],
  "chainId": "",
  "tag": "",
  "streamId": "",
  "confirmed": true,
  "retries": 0,
  "erc20Approvals": [],
  "erc20Transfers": [],
  "nftApprovals": [],
  "nftTransfers": []
}
```

<Note>No response body is required — only the status code matters. See [Test Webhooks](/streams/webhooks/test-webhooks) for more details.</Note>

## Two Webhooks Per Event

You will receive **two webhooks** for each event:

1. **Unconfirmed** (`confirmed: false`) — Sent as soon as the transaction is included in a block. The block may still be dropped due to a chain reorganization. You are **not charged** for unconfirmed webhooks.

2. **Confirmed** (`confirmed: true`) — Sent once enough blocks have been mined to consider the block final. Only confirmed webhooks count toward your [billing](/streams/pricing).

<Warning>In rare cases, the confirmed webhook may arrive before the unconfirmed one. Make sure your application handles this scenario.</Warning>

## Webhook Payload Structure

The webhook body contains all the data for the block event. The key fields are:

| Field            | Description                                      |
| ---------------- | ------------------------------------------------ |
| `chainId`        | The chain ID (e.g., `0x1` for Ethereum)          |
| `block`          | Block metadata (number, hash, timestamp)         |
| `txs`            | Array of native transactions                     |
| `txsInternal`    | Array of internal transactions                   |
| `logs`           | Array of raw event logs                          |
| `erc20Transfers` | Decoded ERC20 transfer events (free)             |
| `erc20Approvals` | Decoded ERC20 approval events (free)             |
| `nftTransfers`   | Decoded NFT transfer events (free)               |
| `nftApprovals`   | Decoded NFT approval events (free)               |
| `tag`            | Your user-defined stream tag                     |
| `streamId`       | The ID of the stream that triggered this webhook |
| `confirmed`      | Whether the block is confirmed                   |
| `retries`        | Number of delivery retries                       |

## Example: Native Transaction Webhook

```json  theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "abi": [],
  "streamId": "c28d9e2e-ae9d-4fe6-9fc0-5fcde2dcdd17",
  "tag": "my_stream",
  "retries": 0,
  "block": {
    "number": "15988759",
    "hash": "0x3aa07bd98e328db97ec273ce06b3a15fc645931fbd26337fe20c48b274277f76",
    "timestamp": "1668676247"
  },
  "logs": [],
  "txs": [
    {
      "hash": "0xd68700a0e2abd9c041eb236812e4194bf91c8182a2b03065887ab0f33d5c2958",
      "gas": "149200",
      "gasPrice": "13670412399",
      "nonce": "57995",
      "input": "0x...",
      "transactionIndex": "52",
      "fromAddress": "0x839d4641f97153b0ff26ab837860c479e2bd0242",
      "toAddress": "0x1111111254eeb25477b68fb85ed929f73a960582",
      "value": "0",
      "type": "2",
      "receiptCumulativeGasUsed": "3131649",
      "receiptGasUsed": "113816",
      "receiptStatus": "1"
    }
  ],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": { "ERC1155": [], "ERC721": [] },
  "nftTransfers": []
}
```

## Verifying Webhook Signatures

Every webhook includes an `x-signature` header — a SHA3 hash of the body combined with your API key. Always verify this signature to ensure the webhook is from Moralis.

<Tabs>
  <Tab title="JavaScript">
    ```javascript  theme={null}
    import Moralis from "moralis";

    const { headers, body } = request;

    Moralis.Streams.verifySignature({
      body,
      signature: headers["x-signature"],
    }); // throws error if not valid
    ```
  </Tab>

  <Tab title="Python">
    ```python  theme={null}
    from web3 import Web3

    def verify_signature(req, secret):
        provided_signature = req.headers.get("x-signature")
        if not provided_signature:
            raise TypeError("Signature not provided")

        data = req.data + secret.encode()
        signature = Web3.keccak(text=data.decode()).hex()

        if provided_signature != signature:
            raise ValueError("Invalid Signature")
    ```
  </Tab>
</Tabs>

For full details, see [Webhook Security](/streams/security-and-reliability/webhook-security).

## Decoded Data (Free)

Moralis automatically decodes standard contract events at no additional cost:

* **ERC20 Transfers** — Includes `tokenName`, `tokenSymbol`, `tokenDecimals`, `from`, `to`, `value`, and `contract` address.
* **ERC20 Approvals** — Includes `owner`, `spender`, `value`, and token metadata.
* **NFT Transfers** — Includes `tokenId`, `tokenName`, `tokenContractType` (ERC721/ERC1155), `from`, `to`, `amount`, and `contract` address.

These decoded fields are included in both confirmed and unconfirmed payloads and do **not** count as records for billing purposes.

## Next Steps

* [Webhook Payloads](/streams/webhooks/webhook-payloads) — Detailed reference for all payload types.
* [Confirmation and Finality](/streams/webhooks/confirmation-and-finality) — How block confirmations work across chains.
* [Pricing](/streams/pricing) — Understand how records and compute units are calculated.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Receive Your First Webhook

> Understand the webhook lifecycle, payload structure, and how to handle confirmed and unconfirmed webhooks from Moralis Streams.

Once your stream is active, Moralis will send webhook `POST` requests to your configured URL whenever monitored addresses are involved in on-chain events.

## Mandatory Test Webhook

Whenever you create or update a stream, you will receive a **test webhook**. You must return a `200` status code (or any `2xx` code) for the stream to start delivering real data.

The test body looks like this:

```json  theme={null}
{
  "abi": {},
  "block": {
    "hash": "",
    "number": "",
    "timestamp": ""
  },
  "txs": [],
  "txsInternal": [],
  "logs": [],
  "chainId": "",
  "tag": "",
  "streamId": "",
  "confirmed": true,
  "retries": 0,
  "erc20Approvals": [],
  "erc20Transfers": [],
  "nftApprovals": [],
  "nftTransfers": []
}
```

<Note>No response body is required — only the status code matters. See [Test Webhooks](/streams/webhooks/test-webhooks) for more details.</Note>

## Two Webhooks Per Event

You will receive **two webhooks** for each event:

1. **Unconfirmed** (`confirmed: false`) — Sent as soon as the transaction is included in a block. The block may still be dropped due to a chain reorganization. You are **not charged** for unconfirmed webhooks.

2. **Confirmed** (`confirmed: true`) — Sent once enough blocks have been mined to consider the block final. Only confirmed webhooks count toward your [billing](/streams/pricing).

<Warning>In rare cases, the confirmed webhook may arrive before the unconfirmed one. Make sure your application handles this scenario.</Warning>

## Webhook Payload Structure

The webhook body contains all the data for the block event. The key fields are:

| Field            | Description                                      |
| ---------------- | ------------------------------------------------ |
| `chainId`        | The chain ID (e.g., `0x1` for Ethereum)          |
| `block`          | Block metadata (number, hash, timestamp)         |
| `txs`            | Array of native transactions                     |
| `txsInternal`    | Array of internal transactions                   |
| `logs`           | Array of raw event logs                          |
| `erc20Transfers` | Decoded ERC20 transfer events (free)             |
| `erc20Approvals` | Decoded ERC20 approval events (free)             |
| `nftTransfers`   | Decoded NFT transfer events (free)               |
| `nftApprovals`   | Decoded NFT approval events (free)               |
| `tag`            | Your user-defined stream tag                     |
| `streamId`       | The ID of the stream that triggered this webhook |
| `confirmed`      | Whether the block is confirmed                   |
| `retries`        | Number of delivery retries                       |

## Example: Native Transaction Webhook

```json  theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "abi": [],
  "streamId": "c28d9e2e-ae9d-4fe6-9fc0-5fcde2dcdd17",
  "tag": "my_stream",
  "retries": 0,
  "block": {
    "number": "15988759",
    "hash": "0x3aa07bd98e328db97ec273ce06b3a15fc645931fbd26337fe20c48b274277f76",
    "timestamp": "1668676247"
  },
  "logs": [],
  "txs": [
    {
      "hash": "0xd68700a0e2abd9c041eb236812e4194bf91c8182a2b03065887ab0f33d5c2958",
      "gas": "149200",
      "gasPrice": "13670412399",
      "nonce": "57995",
      "input": "0x...",
      "transactionIndex": "52",
      "fromAddress": "0x839d4641f97153b0ff26ab837860c479e2bd0242",
      "toAddress": "0x1111111254eeb25477b68fb85ed929f73a960582",
      "value": "0",
      "type": "2",
      "receiptCumulativeGasUsed": "3131649",
      "receiptGasUsed": "113816",
      "receiptStatus": "1"
    }
  ],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": { "ERC1155": [], "ERC721": [] },
  "nftTransfers": []
}
```

## Verifying Webhook Signatures

Every webhook includes an `x-signature` header — a SHA3 hash of the body combined with your API key. Always verify this signature to ensure the webhook is from Moralis.

<Tabs>
  <Tab title="JavaScript">
    ```javascript  theme={null}
    import Moralis from "moralis";

    const { headers, body } = request;

    Moralis.Streams.verifySignature({
      body,
      signature: headers["x-signature"],
    }); // throws error if not valid
    ```
  </Tab>

  <Tab title="Python">
    ```python  theme={null}
    from web3 import Web3

    def verify_signature(req, secret):
        provided_signature = req.headers.get("x-signature")
        if not provided_signature:
            raise TypeError("Signature not provided")

        data = req.data + secret.encode()
        signature = Web3.keccak(text=data.decode()).hex()

        if provided_signature != signature:
            raise ValueError("Invalid Signature")
    ```
  </Tab>
</Tabs>

For full details, see [Webhook Security](/streams/security-and-reliability/webhook-security).

## Decoded Data (Free)

Moralis automatically decodes standard contract events at no additional cost:

* **ERC20 Transfers** — Includes `tokenName`, `tokenSymbol`, `tokenDecimals`, `from`, `to`, `value`, and `contract` address.
* **ERC20 Approvals** — Includes `owner`, `spender`, `value`, and token metadata.
* **NFT Transfers** — Includes `tokenId`, `tokenName`, `tokenContractType` (ERC721/ERC1155), `from`, `to`, `amount`, and `contract` address.

These decoded fields are included in both confirmed and unconfirmed payloads and do **not** count as records for billing purposes.

## Next Steps

* [Webhook Payloads](/streams/webhooks/webhook-payloads) — Detailed reference for all payload types.
* [Confirmation and Finality](/streams/webhooks/confirmation-and-finality) — How block confirmations work across chains.
* [Pricing](/streams/pricing) — Understand how records and compute units are calculated.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Stream Lifecycle

> Learn how to manage Streams throughout their lifecycle, including monitoring status, updating configuration, changing regions, and pausing or resuming streams.

## Overview

Moralis Streams can be **created, monitored, updated, paused, and resumed** at any time - either programmatically or via the Moralis dashboard.

This gives you full control over how streams behave in production and allows you to safely manage changes without deleting or recreating streams.

***

## Stream States

Each stream has a lifecycle state that indicates whether it is actively delivering events.

### Supported statuses

| Status       | Description                                                      |
| :----------- | :--------------------------------------------------------------- |
| `active`     | Stream is live and delivering webhooks                           |
| `paused`     | Stream is temporarily disabled                                   |
| `error`      | Stream encountered a configuration or delivery error             |
| `terminated` | Stream was automatically stopped after 24 hours in `error` state |

The current status is returned when listing or fetching streams.

***

## Listing Streams

You can retrieve all streams associated with your account to inspect their configuration and status.

```javascript  theme={null}
const streams = await Moralis.Streams.getAll({
  limit: 100,
});
```

Each stream includes metadata such as:

* Webhook URL
* Enabled chains
* Status
* Filters and ABI configuration
* Region and delivery settings

Streams can also be viewed and managed from the dashboard.

***

## Updating Stream Configuration

Streams can be updated at any time to reflect changes such as:

* Webhook URL updates
* Adding or removing chains
* Adjusting filters or ABIs
* Changing stream behavior

Example: updating a webhook URL

```javascript  theme={null}
await Moralis.Streams.update({
  id: "STREAM_ID",
  webhook: "https://your-new-webhook-url",
});
```

Updates take effect immediately and do not require stream recreation.

***

## Pausing and Resuming Streams

Streams can be paused without deleting them. This is useful for:

* Maintenance windows
* Incident response
* Temporary traffic reduction

### Pause a stream

```javascript  theme={null}
await Moralis.Streams.updateStatus({
  id: "STREAM_ID",
  status: "paused",
});
```

### Resume a stream

```javascript  theme={null}
await Moralis.Streams.updateStatus({
  id: "STREAM_ID",
  status: "active",
});
```

Paused streams do not process events and do not send webhooks.

***

## Stream Regions

Each stream runs in a specific region to optimise webhook delivery latency.

Available regions include:

* `us-east-1`
* `us-west-2`
* `eu-central-1`

You can update the region at any time:

```javascript  theme={null}
await Moralis.Streams.setSettings({
  region: "eu-central-1",
});
```

For best performance, choose the region closest to your backend infrastructure.

***

## Error Handling

If a stream enters the `error` state:

* The stream stops delivering events
* A status message is provided explaining the issue
* Configuration must be corrected before resuming

Common causes include:

* Invalid ABI definitions
* Invalid filters
* Unreachable webhook endpoints

Read more about [Error Handling](/streams/streams-concepts/error-handling).

***

## Terminated State

If a stream remains in the `error` state for **24 hours**, it is automatically **terminated**.

A terminated stream:

* Does **not** send webhooks
* Does **not** process new blocks
* Drops all events that occur after termination
* Cannot be automatically resumed

When a stream is terminated, an **email notification** is sent to the account owner.

Read more about [Terminated States](/streams/streams-concepts/error-handling).

***

## Best Practices

* Pause streams instead of deleting them when troubleshooting
* Monitor stream status regularly in production
* Keep webhook URLs and regions aligned with your deployment setup
* Use descriptive stream tags to identify purpose and ownership


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Filters

> Learn how to filter Streams events using logical operators, value comparisons, and special stream variables to control exactly which on-chain events trigger webhooks.

## Overview

Streams filters allow you to **control exactly which events trigger webhooks** by applying logical conditions to on-chain data.

Filters are evaluated **before** a webhook is delivered. Events that do not match your filter rules are ignored and do not consume usage.

***

## How Filters Work

Filters are defined as a **JSON expression** using logical operators and comparison rules.

* Filters apply to **decoded event data**
* Filters require a **valid ABI** for the event being filtered
* All conditions must resolve to `true` for the event to trigger a webhook

***

## Supported Operators

### Logical operators

| Operator | Description                              | Notes                   | Example                                     |
| :------- | :--------------------------------------- | ----------------------- | ------------------------------------------- |
| `and`    | All nested conditions must match         | Need at least 2 filters | `{ "or" : [ {..filter1}, {...filter2} ]}`   |
| `or`     | At least one nested condition must match | Need at least 2 filters | `{ "and" : [ {..filter1}, {...filter2} ]}	` |

### Comparison operators

| Operator | Description           | Notes               | Example                                |
| :------- | :-------------------- | :------------------ | -------------------------------------- |
| `eq`     | Equal to              |                     | `{ "eq": ["value", "1000"] }`          |
| `ne`     | Not equal to          |                     | `{ "ne": ["address", "0x...325"] }`    |
| `lt`     | Less than             | Numeric values only | `{ "lt": ["amount", "50"] }`           |
| `gt`     | Greater than          | Numeric values only | `{ "gt": ["price", "500000"] }`        |
| `lte`    | Less than or equal    | Numeric values only | `{ "lte": ["amount", "100"] }`         |
| `gte`    | Greater than or equal | Numeric values only | `{ "gte": ["amount", "100"] }`         |
| `in`     | Value exists in array | Array required      | `{ "in": ["name": ["alice", "bob"]]}`  |
| `nin`    | Value not in array    | Array required      | `{ "nin": ["name": ["bob", "alice"]]}` |

***

## Special Stream Variables

Moralis provides special variables that can be used in filters to access stream-level metadata.

| Variable                           | Description                               |
| :--------------------------------- | :---------------------------------------- |
| `moralis_streams_contract_address` | Contract emitting the event (lowercase)   |
| `moralis_streams_chain_id`         | Chain ID for the event                    |
| `moralis_streams_possibleSpam`     | Indicates if the event is flagged as spam |

### Example: filter by contract address

```javascript  theme={null}
{
  "eq": ["moralis_streams_contract_address", "0x0000000000000000000000000000000000000000"]
}
```

<Info>
  Note: contract addresses must be lowercase.
</Info>

***

## Filtering Possible Spam Events

Some contract addresses are associated with spam, phishing attempts, or other suspicious activity. Moralis identifies these and flags them with `possibleSpam = true`.

You can exclude these events entirely by enabling:

```javascript  theme={null}
"filterPossibleSpamAddresses": true
```

When enabled:

* Events involving contracts flagged as possible spam are excluded
* No webhook is sent
* No usage is consumed

By default, `filterPossibleSpamAddresses` is set to `false`.

Learn more about spam detection in the **Safety & Trust** section.

***

## Example: Different Rules per Contract

You can apply different thresholds depending on which contract emitted the event.

```javascript  theme={null}
{
  "or": [
    {
      "and": [
        { "eq": ["moralis_streams_contract_address", "0x1"] },
        { "gte": ["value", 1000000000] }
      ]
    },
    {
      "and": [
        { "eq": ["moralis_streams_contract_address", "0x2"] },
        { "gte": ["value", 1000000000000000000000] }
      ]
    }
  ]
}
```

This is useful when monitoring multiple tokens with different decimals or value semantics.

***

## Example: Filtering by Value Range

Filter transfers where the amount is between two values:

```javascript  theme={null}
{
  "and": [
    { "gt": ["value", 5000000000] },
    { "lt": ["value", 50000000000] }
  ]
}
```

> Example assumes a token with 6 decimals (e.g. USDC).

***

## Example: Mint and Burn Detection

A zero address indicates:

* **Mint** when used as `from`
* **Burn** when used as `to`

```javascript  theme={null}
{
  "or": [
    {
      "and": [
        { "eq": ["from", "0x0000000000000000000000000000000000000000"] },
        { "gte": ["value", 10000000000] }
      ]
    },
    {
      "and": [
        { "eq": ["to", "0x0000000000000000000000000000000000000000"] },
        { "gte": ["value", 10000000000] }
      ]
    }
  ]
}
```

***

## Important Notes

* Filters require a **valid ABI** for the event being filtered
* Filters are evaluated **before webhook delivery**
* Invalid filters will prevent the stream from working
* Filters use **AND / OR logic only** (no implicit precedence)

***

## When to Use Filters

Use filters to:

* Reduce webhook volume
* Exclude spam or low-value events
* Trigger alerts only for meaningful activity
* Apply different logic per contract or chain


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Filters

> Learn how to filter Streams events using logical operators, value comparisons, and special stream variables to control exactly which on-chain events trigger webhooks.

## Overview

Streams filters allow you to **control exactly which events trigger webhooks** by applying logical conditions to on-chain data.

Filters are evaluated **before** a webhook is delivered. Events that do not match your filter rules are ignored and do not consume usage.

***

## How Filters Work

Filters are defined as a **JSON expression** using logical operators and comparison rules.

* Filters apply to **decoded event data**
* Filters require a **valid ABI** for the event being filtered
* All conditions must resolve to `true` for the event to trigger a webhook

***

## Supported Operators

### Logical operators

| Operator | Description                              | Notes                   | Example                                     |
| :------- | :--------------------------------------- | ----------------------- | ------------------------------------------- |
| `and`    | All nested conditions must match         | Need at least 2 filters | `{ "or" : [ {..filter1}, {...filter2} ]}`   |
| `or`     | At least one nested condition must match | Need at least 2 filters | `{ "and" : [ {..filter1}, {...filter2} ]}	` |

### Comparison operators

| Operator | Description           | Notes               | Example                                |
| :------- | :-------------------- | :------------------ | -------------------------------------- |
| `eq`     | Equal to              |                     | `{ "eq": ["value", "1000"] }`          |
| `ne`     | Not equal to          |                     | `{ "ne": ["address", "0x...325"] }`    |
| `lt`     | Less than             | Numeric values only | `{ "lt": ["amount", "50"] }`           |
| `gt`     | Greater than          | Numeric values only | `{ "gt": ["price", "500000"] }`        |
| `lte`    | Less than or equal    | Numeric values only | `{ "lte": ["amount", "100"] }`         |
| `gte`    | Greater than or equal | Numeric values only | `{ "gte": ["amount", "100"] }`         |
| `in`     | Value exists in array | Array required      | `{ "in": ["name": ["alice", "bob"]]}`  |
| `nin`    | Value not in array    | Array required      | `{ "nin": ["name": ["bob", "alice"]]}` |

***

## Special Stream Variables

Moralis provides special variables that can be used in filters to access stream-level metadata.

| Variable                           | Description                               |
| :--------------------------------- | :---------------------------------------- |
| `moralis_streams_contract_address` | Contract emitting the event (lowercase)   |
| `moralis_streams_chain_id`         | Chain ID for the event                    |
| `moralis_streams_possibleSpam`     | Indicates if the event is flagged as spam |

### Example: filter by contract address

```javascript  theme={null}
{
  "eq": ["moralis_streams_contract_address", "0x0000000000000000000000000000000000000000"]
}
```

<Info>
  Note: contract addresses must be lowercase.
</Info>

***

## Filtering Possible Spam Events

Some contract addresses are associated with spam, phishing attempts, or other suspicious activity. Moralis identifies these and flags them with `possibleSpam = true`.

You can exclude these events entirely by enabling:

```javascript  theme={null}
"filterPossibleSpamAddresses": true
```

When enabled:

* Events involving contracts flagged as possible spam are excluded
* No webhook is sent
* No usage is consumed

By default, `filterPossibleSpamAddresses` is set to `false`.

Learn more about spam detection in the **Safety & Trust** section.

***

## Example: Different Rules per Contract

You can apply different thresholds depending on which contract emitted the event.

```javascript  theme={null}
{
  "or": [
    {
      "and": [
        { "eq": ["moralis_streams_contract_address", "0x1"] },
        { "gte": ["value", 1000000000] }
      ]
    },
    {
      "and": [
        { "eq": ["moralis_streams_contract_address", "0x2"] },
        { "gte": ["value", 1000000000000000000000] }
      ]
    }
  ]
}
```

This is useful when monitoring multiple tokens with different decimals or value semantics.

***

## Example: Filtering by Value Range

Filter transfers where the amount is between two values:

```javascript  theme={null}
{
  "and": [
    { "gt": ["value", 5000000000] },
    { "lt": ["value", 50000000000] }
  ]
}
```

> Example assumes a token with 6 decimals (e.g. USDC).

***

## Example: Mint and Burn Detection

A zero address indicates:

* **Mint** when used as `from`
* **Burn** when used as `to`

```javascript  theme={null}
{
  "or": [
    {
      "and": [
        { "eq": ["from", "0x0000000000000000000000000000000000000000"] },
        { "gte": ["value", 10000000000] }
      ]
    },
    {
      "and": [
        { "eq": ["to", "0x0000000000000000000000000000000000000000"] },
        { "gte": ["value", 10000000000] }
      ]
    }
  ]
}
```

***

## Important Notes

* Filters require a **valid ABI** for the event being filtered
* Filters are evaluated **before webhook delivery**
* Invalid filters will prevent the stream from working
* Filters use **AND / OR logic only** (no implicit precedence)

***

## When to Use Filters

Use filters to:

* Reduce webhook volume
* Exclude spam or low-value events
* Trigger alerts only for meaningful activity
* Apply different logic per contract or chain


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Re-org Handling

> Learn how Moralis Streams detects and handles blockchain reorganizations to ensure reliable and consistent event delivery.

### Overview

A blockchain reorganization (re-org) occurs when a previously accepted block is replaced by another block at the same height.

Re-orgs are a normal part of blockchain operation, especially on:

* High-throughput chains
* L2s
* Testnets

Moralis Streams is designed to **handle re-orgs safely and transparently**.

***

### How Streams Handles Re-orgs

When a re-org occurs:

1. Streams detects the replaced block
2. Events from the dropped block are invalidated
3. Replacement block events are processed
4. Confirmation logic is recalculated

You do **not** need to manually detect or resolve re-orgs.

***

### Impact on Webhooks

Re-org handling is reflected through:

* `confirmed: false` events that may not be finalized
* `confirmed: true` events only sent after finality

If a transaction is removed due to a re-org:

* It will **not** receive a confirmed webhook
* Replacement transactions will be delivered instead

See also:

* [**Confirmation & Finality**](/streams/webhooks/confirmation-and-finality)
* [**Webhook Delivery**](/streams/webhooks/webhook-delivery)

***

### Why This Matters

Without re-org handling, applications risk:

* Double-counting transactions
* Incorrect balances
* Invalid ownership state

Streams ensures:

* Only finalized state is confirmed
* Re-orgs do not corrupt downstream systems

***

### Replays & Recovery

If your system was offline during a re-org:

* You can replay affected blocks
* You can replay failed webhooks

See also:

* [**Retries & Replays**](/streams/webhooks/retries-and-replays)

***

### Best Practices

* Treat `confirmed: false` as provisional
* Persist only confirmed state
* Make handlers idempotent
* Use replays for recovery, not polling


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Rate Limits

> Understand Streams rate limits, address management constraints, and how stream reloads impact webhook delivery.

## Rate Limits & Address Management

Streams rate limits primarily apply to **stream configuration changes**, not event delivery.

The most important limits to understand relate to **adding addresses to a stream**, as these operations trigger internal reloads that affect when monitoring becomes active.

***

## Address Management & Stream Reloads

When you add new addresses to a stream, Moralis must **reload the stream configuration** to include those addresses in monitoring.

This reload:

* Is asynchronous
* Takes longer as the number of addresses increases
* Must complete before new blocks are processed for the added addresses

During a reload, the stream may temporarily be unable to detect events for newly added addresses.

***

## Rate Limits for Adding Addresses

### Address add rate limit

* **Maximum:** 5 requests per 5 minutes
* Each request may include **multiple addresses**

If you need to add many addresses, always batch them into as few requests as possible.

***

## Impact on Webhook Delivery

### Reload timing

If an address is added shortly before a block is produced:

* The stream may not finish reloading in time
* Events involving the new address in that block may be missed
* No webhook will be sent for those events

This is more likely when:

* The stream already contains many addresses
* Multiple address updates are submitted close together

***

### Reload loops

Submitting many small address-addition requests can:

* Trigger repeated reloads
* Slow down activation of new addresses
* Cause you to hit the rate limit
* Delay effective monitoring

***

## Best Practices

### Batch address updates

Always batch addresses into a single request when possible.\
This reduces reloads and speeds up activation.

***

### Plan address additions ahead of time

If you expect activity on a new address:

* Add it **well before** the expected transaction
* Avoid last-second updates near block times

Streams are not designed for ultra-last-second address registration.

***

## Handling Missed Events

If you believe events were missed due to reload timing:

### 1. Verify address addition

Confirm the address was successfully added using the **Get Stream Info** endpoint.

### 2. Replay affected blocks

Use the **Replay Block** endpoint with:

* The affected block number
* The relevant stream ID

This allows Moralis to reprocess the block and resend applicable webhooks.

***

## What Rate Limits Do *Not* Apply To

* Event delivery volume
* Number of webhooks received
* Number of monitored events per block

These are governed by stream configuration and pricing, not per-request rate limits.

***

## Summary

* Address additions trigger stream reloads
* Reloads are not instantaneous
* Address add requests are rate limited
* Batch updates and planning ahead are essential
* Missed events can be recovered using block replay


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Error Handling

> Understand how Streams handles webhook failures, retries, error states, termination, and how to recover from delivery issues safely.

## Overview

Streams is designed for **reliable, at-least-once delivery** of webhook events.\
While Moralis handles retries and failure recovery automatically, errors can still occur—most commonly due to webhook endpoint availability or throughput constraints.

This page explains:

* How delivery failures are handled
* When streams enter error or terminated states
* How retries, replays, and recovery work
* What actions you should take in production

***

## Delivery Guarantees (Important Context)

Moralis guarantees **at-least-once delivery** of webhooks while a stream is active.

This means:

* Webhooks may be retried
* Duplicate deliveries are possible
* Your webhook handler **must be idempotent**

Correctness is prioritised over strict ordering.

***

## Automatic Webhook Retries

If a webhook delivery fails (timeout, network error, non-2xx response), Moralis automatically retries delivery using an exponential backoff strategy.

### Retry schedule

| Attempt | Interval   |
| :------ | :--------- |
| 0       | 1 minute   |
| 1       | 10 minutes |
| 2       | 1 hour     |
| 3       | 2 hours    |
| 4       | 6 hours    |
| 5       | 12 hours   |
| 6       | 24 hours   |

Retries apply only to **delivery failures**.\
They do not reprocess blocks or regenerate events.

***

## Error State

A stream may enter the `error` state under the following conditions:

### 1. Low webhook success rate

If the webhook success rate for a stream drops **below 70%**, the stream enters the error state.

### 2. Delivery backlog (queue saturation)

If your server cannot consume webhooks fast enough:

* A delivery queue builds up
* The queue reaches its maximum size (10,000 events)
* The stream is placed into the error state

You can monitor queue pressure using the `x-queue-size` response header.

***

### Behaviour in Error State

When a stream is in the `error` state:

* Webhook delivery is **paused**
* Events are **not delivered**
* Blocks are **still evaluated**
* Retry scheduling resumes once the stream is reactivated

An **email notification** is sent when a stream enters this state.

***

## Terminated State

If a stream remains in the `error` state for **24 hours**, it is automatically **terminated**.

### Behaviour in Terminated State

A terminated stream:

* Does **not** send webhooks
* Does **not** process new blocks
* Drops all subsequent events permanently
* Cannot be resumed

An **email notification** is sent when termination occurs.

To recover, a **new stream must be created**.

***

## Webhook Success Rate

Each stream tracks a webhook success rate per webhook URL:

* Starts at **100%**
* Each failed delivery reduces the rate by **1%**
* Each successful delivery increases the rate by **1%**
* Capped between **0% and 100%**

If the success rate falls below **70%**, the stream enters the error state.

***

## Viewing Failed Webhooks

Failed webhook deliveries are retained for a limited time (plan-dependent, up to 7 days).

### Retrieve failed deliveries

```javascript  theme={null}
const history = await Moralis.Streams.getHistory({ limit: 100 });
```

Each failed delivery includes:

* Webhook payload
* Error message
* Stream ID
* Timestamp
* Unique history ID

***

## Replaying Failed Webhooks

Failed webhooks can be replayed manually.

### Replay a failed webhook

```javascript  theme={null}
await Moralis.Streams.retry({
  id: "HISTORY_ID",
  streamId: "STREAM_ID",
});
```

Replayed webhooks are delivered with the same payload as the original attempt.

<Note>
  Replays do not regenerate events or reprocess blocks.
</Note>

For block-level recovery, use **Replay Block** (see *Retries & Replays*).

***

## Best Practices to Avoid Errors

* Ensure webhook endpoints respond quickly and consistently
* Treat webhook handling as **idempotent**
* Monitor `x-queue-size` headers
* Choose a stream region close to your backend
* Pause streams during planned outages
* Act promptly on error-state email notifications

***

## Summary

* Delivery failures trigger automatic retries
* Prolonged failures cause streams to enter `error`
* Error state pauses delivery but preserves configuration
* 24 hours in error results in termination
* Failed deliveries can be replayed
* Block-level recovery requires replay


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Advanced Options

> Configure advanced Streams options to control which transactions, logs, and events are included in webhook payloads.

## Overview

Streams provides several advanced configuration options that allow you to **fine-tune which on-chain data is included in your webhook payloads**.

These options control:

* Which transaction types are included
* Whether contract logs and internal transactions are captured
* How specific events are filtered at a granular level

Used correctly, they help reduce noise while ensuring you receive all relevant data.

***

## Global Stream Options

These options apply at the **stream level** and affect the overall webhook payload.

***

### Include Contract Logs

```javascript  theme={null}
includeContractLogs: true
```

When enabled:

* All contract logs are included in webhook payloads
* Required when monitoring **specific contracts**
* Useful when monitoring wallets that interact with contracts

If you are only monitoring wallet activity, this can be disabled unless contract interaction details are required.

***

### Include Internal Transactions

```javascript  theme={null}
includeInternalTxs: true
```

When enabled:

* Includes internal transactions (contract-to-contract calls)
* Useful for tracing value movement inside smart contracts
* Particularly relevant for DeFi protocols and complex contract interactions

***

### Include Native Transactions

```javascript  theme={null}
includeNativeTxs: true
```

When enabled:

* Includes native currency transfers (e.g. ETH, MATIC)
* Useful for tracking wallet balance changes or native payments

***

### Include All Transaction Logs

```javascript  theme={null}
includeAllTxLogs: true
```

When enabled:

* Includes **all logs related to a transaction** if *any* log or transaction matches your stream configuration
* Expands the webhook payload to include full transaction context

**Requirements:**

* Must be used together with either:
  * `includeNativeTxs`, or
  * `includeContractLogs`

**Plan availability:**\
Available on **Pro plans and higher**.

***

## Advanced Options (Per-Event Configuration)

The `advancedOptions` field allows you to define **event-specific rules** that override or refine the global stream configuration.

Each entry targets a specific event signature and optionally applies filters.

***

### Advanced Option Structure

```javascript  theme={null}
{
  "topic0": "string",
  "filter": { },
  "includeNativeTxs": boolean
}
```

***

### Fields Explained

#### `topic0`

The event signature to listen for (e.g. `Transfer(address,address,uint256)`).

* Required
* Determines which decoded event the option applies to

***

#### `filter`

A filter expression applied **only to this event**.

* Uses the same filter syntax described in **Filters**
* Allows precise inclusion logic per event

***

#### `includeNativeTxs`

Controls whether native transactions should be included **alongside this specific event**.

***

## Example: Filtered ERC-20 Transfers

```javascript  theme={null}
{
  "topic0": "Transfer(address,address,uint256)",
  "filter": {
    "and": [
      { "eq": ["from", "0x283af0b28c62c092c9727f1ee09c02ca627eb7f5"] },
      { "gt": ["amount", "100000000000000000000"] }
    ]
  },
  "includeNativeTxs": false
}
```

This configuration:

* Listens only to ERC-20 `Transfer` events
* Filters transfers from a specific address
* Requires the transferred amount to exceed a threshold
* Excludes native transactions

<Info>
  Amounts must be expressed in the token’s base units (e.g. wei).
</Info>

***

## When to Use Advanced Options

Advanced options are useful when you want to:

* Apply **different rules per event type**
* Reduce webhook payload size
* Filter high-value or high-signal events
* Track contract activity with precision

For simpler use cases, global stream options are usually sufficient.

***

## Best Practices

* Start with global options, then refine with `advancedOptions`
* Avoid overlapping filters that can be hard to reason about
* Keep filters simple where possible
* Test changes in a non-production stream first

***

## Summary

* Global options control overall stream behaviour
* `advancedOptions` enable per-event customization
* Filters and advanced options work together
* Proper configuration reduces noise and improves reliability


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Advanced Options

> Configure advanced Streams options to control which transactions, logs, and events are included in webhook payloads.

## Overview

Streams provides several advanced configuration options that allow you to **fine-tune which on-chain data is included in your webhook payloads**.

These options control:

* Which transaction types are included
* Whether contract logs and internal transactions are captured
* How specific events are filtered at a granular level

Used correctly, they help reduce noise while ensuring you receive all relevant data.

***

## Global Stream Options

These options apply at the **stream level** and affect the overall webhook payload.

***

### Include Contract Logs

```javascript  theme={null}
includeContractLogs: true
```

When enabled:

* All contract logs are included in webhook payloads
* Required when monitoring **specific contracts**
* Useful when monitoring wallets that interact with contracts

If you are only monitoring wallet activity, this can be disabled unless contract interaction details are required.

***

### Include Internal Transactions

```javascript  theme={null}
includeInternalTxs: true
```

When enabled:

* Includes internal transactions (contract-to-contract calls)
* Useful for tracing value movement inside smart contracts
* Particularly relevant for DeFi protocols and complex contract interactions

***

### Include Native Transactions

```javascript  theme={null}
includeNativeTxs: true
```

When enabled:

* Includes native currency transfers (e.g. ETH, MATIC)
* Useful for tracking wallet balance changes or native payments

***

### Include All Transaction Logs

```javascript  theme={null}
includeAllTxLogs: true
```

When enabled:

* Includes **all logs related to a transaction** if *any* log or transaction matches your stream configuration
* Expands the webhook payload to include full transaction context

**Requirements:**

* Must be used together with either:
  * `includeNativeTxs`, or
  * `includeContractLogs`

**Plan availability:**\
Available on **Pro plans and higher**.

***

## Advanced Options (Per-Event Configuration)

The `advancedOptions` field allows you to define **event-specific rules** that override or refine the global stream configuration.

Each entry targets a specific event signature and optionally applies filters.

***

### Advanced Option Structure

```javascript  theme={null}
{
  "topic0": "string",
  "filter": { },
  "includeNativeTxs": boolean
}
```

***

### Fields Explained

#### `topic0`

The event signature to listen for (e.g. `Transfer(address,address,uint256)`).

* Required
* Determines which decoded event the option applies to

***

#### `filter`

A filter expression applied **only to this event**.

* Uses the same filter syntax described in **Filters**
* Allows precise inclusion logic per event

***

#### `includeNativeTxs`

Controls whether native transactions should be included **alongside this specific event**.

***

## Example: Filtered ERC-20 Transfers

```javascript  theme={null}
{
  "topic0": "Transfer(address,address,uint256)",
  "filter": {
    "and": [
      { "eq": ["from", "0x283af0b28c62c092c9727f1ee09c02ca627eb7f5"] },
      { "gt": ["amount", "100000000000000000000"] }
    ]
  },
  "includeNativeTxs": false
}
```

This configuration:

* Listens only to ERC-20 `Transfer` events
* Filters transfers from a specific address
* Requires the transferred amount to exceed a threshold
* Excludes native transactions

<Info>
  Amounts must be expressed in the token’s base units (e.g. wei).
</Info>

***

## When to Use Advanced Options

Advanced options are useful when you want to:

* Apply **different rules per event type**
* Reduce webhook payload size
* Filter high-value or high-signal events
* Track contract activity with precision

For simpler use cases, global stream options are usually sufficient.

***

## Best Practices

* Start with global options, then refine with `advancedOptions`
* Avoid overlapping filters that can be hard to reason about
* Keep filters simple where possible
* Test changes in a non-production stream first

***

## Summary

* Global options control overall stream behaviour
* `advancedOptions` enable per-event customization
* Filters and advanced options work together
* Proper configuration reduces noise and improves reliability


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Webhook Payload

> Understand the structure of Streams webhook payloads, including transactions, transfers, logs, confirmations, retries, and signature verification.

## Overview

Every Streams webhook delivers a **JSON payload** containing the on-chain events that match your stream configuration.

A single payload may include:

* Native transactions
* Internal transactions
* ERC-20 transfers and approvals
* NFT transfers and approvals
* Smart contract event logs

The exact contents depend on the options enabled when the stream was created.

***

## Top-Level Payload Structure

All webhook payloads share the same top-level fields:

```javascript  theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "streamId": "uuid",
  "tag": "string",
  "retries": 0,
  "block": { },
  "logs": [],
  "txs": [],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftTransfers": [],
  "nftApprovals": { "ERC721": [], "ERC1155": [] }
}
```

If you’re unfamiliar with any of these fields, see:

* [**Parsed Data**](/streams/streams-concepts/parsed-data)
* [**Advanced Options**](/streams/streams-concepts/advanced-options)

### Key Fields

| Field         | Description                      |
| :------------ | :------------------------------- |
| `confirmed`   | Whether the block is finalized   |
| `chainId`     | Chain the event occurred on      |
| `streamId`    | Unique stream identifier         |
| `tag`         | Optional stream tag              |
| `retries`     | Number of delivery attempts      |
| `block`       | Block metadata                   |
| `logs`        | Raw smart contract logs          |
| `txs`         | Native transactions              |
| `txsInternal` | Internal (contract) transactions |

***

## Confirmed vs Unconfirmed Events

Streams sends **two webhook payloads per event**:

1. **Unconfirmed (**`confirmed: false`**)**\
   Sent as soon as the block is mined.
2. **Confirmed (**`confirmed: true`**)**\
   Sent once finality is reached.

This design allows you to:

* React instantly to on-chain activity
* Safely update state once finality is guaranteed

<Note>
  For chain-specific confirmation rules, see [**Supported Chains**](/streams/supported-chains).

  For how reorgs are handled, see [**Re-org Handling**](/streams/streams-concepts/re-org-handling).
</Note>

***

## Verifying Webhook Authenticity

Every webhook includes an `x-signature` header.

You **must verify this signature** to ensure the payload originated from Moralis.

Signature verification is covered in detail here:

* [**Webhook Security**](/streams/security-and-reliability/webhook-security)

Basic flow:

1. Read the raw request body
2. Hash it together with your Streams secret
3. Compare against `x-signature`

***

## Native Transactions (`txs`)

Included when `includeNativeTxs` is enabled.

Native transactions include:

* Sender and recipient
* Value transferred
* Gas usage and receipt fields

These are useful for:

* Wallet balance tracking
* Payment monitoring
* Base-layer activity analysis

**Example:**

```javascript expandable theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "abi": [],
  "streamId": "c28d9e2e-ae9d-4fe6-9fc0-5fcde2dcdd17",
  "tag": "native_transactions",
  "retries": 0,
  "block": {
    "number": "15988759",
    "hash": "0x3aa07bd98e328db97ec273ce06b3a15fc645931fbd26337fe20c48b274277f76",
    "timestamp": "1668676247"
  },
  "logs": [],
  "txs": [
    {
      "hash": "0xd68700a0e2abd9c041eb236812e4194bf91c8182a2b03065887ab0f33d5c2958",
      "gas": "149200",
      "gasPrice": "13670412399",
      "nonce": "57995",
      "input": "0xf78dc253000000000000000000000000d9408f29026e32852aff8c5c9c8ea834b44b4e1c000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb4800000000000000000000000000000000000000000000000000000000109fad200000000000000000000000000000000000000000000009ab31572a589a72a11900000000000000000000000000000000000000000000000000000000000000a0000000000000000000000000000000000000000000000000000000000000000180000000000000003b6d0340a5c475167f03b1556c054e0da78192cd2779087fcfee7c08",
      "transactionIndex": "52",
      "fromAddress": "0x839d4641f97153b0ff26ab837860c479e2bd0242",
      "toAddress": "0x1111111254eeb25477b68fb85ed929f73a960582",
      "value": "0",
      "type": "2",
      "v": "1",
      "r": "46904304245026065492026869531757792493071866863221741878090753056388581469881",
      "s": "17075445080437932806356212399757328600893345374993510540712828450455909549452",
      "receiptCumulativeGasUsed": "3131649",
      "receiptGasUsed": "113816",
      "receiptContractAddress": null,
      "receiptRoot": null,
      "receiptStatus": "1"
    }
  ],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": []
}
```

***

## Contract Logs (`logs`)

Included when `includeContractLogs` is enabled.

Logs contain:

* Raw topics and data
* Emitting contract address
* Transaction hash and log index

Logs are automatically decoded into higher-level objects when applicable (see below).

**Example:**

```javascript expandable theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "abi": [
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": false,
          "name": "reserve0",
          "type": "uint112"
        },
        {
          "indexed": false,
          "name": "reserve1",
          "type": "uint112"
        }
      ],
      "name": "Sync",
      "type": "event"
    }
  ],
  "streamId": "6378fe38-54c7-4816-8d61-fca8e128e260",
  "tag": "test_events",
  "retries": 1,
  "block": {
    "number": "15984246",
    "hash": "0x7f8d8285b572a60f6a14d5f1dcbd40e487ccffd9ec78f8dfbccb49aa191fbb95",
    "timestamp": "1668621827"
  },
  "logs": [
    {
      "logIndex": "320",
      "transactionHash": "0xf1682fa49b83689093b467ac6937785102895fc3ba418624c28d04f9af6e5e2b",
      "address": "0x4cd36d6f32586177e36179a810595a33163a20bf",
      "data": "0x00000000000000000000000000000000000000000000944ad388817e590ab6070000000000000000000000000000000000000000000000000000008a602de18e",
      "topic0": "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1",
      "topic1": null,
      "topic2": null,
      "topic3": null
    }
  ],
  "txs": [],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": []
}
```

***

## ERC-20 Transfers

ERC-20 transfers are **automatically decoded** from logs and included at no additional cost.

Each transfer includes:

* `from`, `to`, `value`
* Token metadata (`name`, `symbol`, `decimals`)
* Human-readable `valueWithDecimals`

Transfers appear in both confirmed and unconfirmed payloads.

**Example:**

```javascript expandable theme={null}
{
  "confirmed": false,
  "chainId": "0x5",
  "abi": [],
  "streamId": "c4cf9b1a-0cb3-4c79-9ca3-04f11856c555",
  "tag": "ChrisWallet",
  "retries": 0,
  "block": {
    "number": "8037952",
    "hash": "0x607ff512f17f890bf9ee6206e2029cd8530819ab72b2b9161f9b90d18ece8e03",
    "timestamp": "1669667244"
  },
  "logs": [
    {
      "logIndex": "132",
      "transactionHash": "0x1642a3b9b39e63d7fe571e7c22b80a5b059d2647fe4866d3f7105630f822d833",
      "address": "0x0041ebd11f598305d401cc1052df49219630ab79",
      "data": "0x0000000000000000000000000000000000000000000069e10006afc3291c0000",
      "topic0": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
      "topic1": "0x0000000000000000000000000a46413965858a6ac4ed5184d7643dc055a4fea3",
      "topic2": "0x000000000000000000000000e496601436da37a045d8e88bbd6b2c2e17d8fe33",
      "topic3": null
    }
  ],
  "txs": [
    {
      "hash": "0x1642a3b9b39e63d7fe571e7c22b80a5b059d2647fe4866d3f7105630f822d833",
      "gas": "85359",
      "gasPrice": "6129141152",
      "nonce": "88",
      "input": "0xa9059cbb000000000000000000000000e496601436da37a045d8e88bbd6b2c2e17d8fe330000000000000000000000000000000000000000000069e10006afc3291c0000",
      "transactionIndex": "49",
      "fromAddress": "0x0a46413965858a6ac4ed5184d7643dc055a4fea3",
      "toAddress": "0x0041ebd11f598305d401cc1052df49219630ab79",
      "value": "0",
      "type": "2",
      "v": "1",
      "r": "86947778944630951418310264989677611886333891146913483133255814972120449355054",
      "s": "7019311275916215306620036726907048105130260362064080269753410507440852031640",
      "receiptCumulativeGasUsed": "11882265",
      "receiptGasUsed": "56906",
      "receiptContractAddress": null,
      "receiptRoot": null,
      "receiptStatus": "1"
    }
  ],
  "txsInternal": [],
  "erc20Transfers": [
    {
      "transactionHash": "0x1642a3b9b39e63d7fe571e7c22b80a5b059d2647fe4866d3f7105630f822d833",
      "logIndex": "132",
      "contract": "0x0041ebd11f598305d401cc1052df49219630ab79",
      "from": "0x0a46413965858a6ac4ed5184d7643dc055a4fea3",
      "to": "0xe496601436da37a045d8e88bbd6b2c2e17d8fe33",
      "value": "499999000000000000000000",
      "tokenName": "Example Token",
      "tokenSymbol": "Token",
      "tokenDecimals": "18",
      "possibleSpam": false,
      "valueWithDecimals": "499999"
    }
  ],
  "erc20Approvals": [],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": []
}
```

***

## ERC-20 Approvals

ERC-20 approvals are also automatically decoded and include:

* Owner and spender
* Approved amount
* Token metadata

**Example:**

```javascript expandable theme={null}
{
  "confirmed": true,
  "chainId": "0x1",
  "abi": [],
  "streamId": "c28d9e2e-ae9d-4fe6-9fc0-5fcde2dcdd17",
  "tag": "native_transactions_with_logs",
  "retries": 0,
  "block": {
    "number": "15988780",
    "hash": "0xf40d623518fa16c20614278656e426721820031913fd9c670330d4b2b751d50e",
    "timestamp": "1668676499"
  },
  "logs": [
    {
      "logIndex": "135",
      "transactionHash": "0x59cd370a41c699bdb77a020b3a27735bb7442ace68ec8313040b8b9ee2672244",
      "address": "0x96beaa1316f85fd679ec49e5a63dacc293b044be",
      "data": "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "topic0": "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925",
      "topic1": "0x0000000000000000000000001748789703159580520cc2ce6d1ba01e7359c44c",
      "topic2": "0x0000000000000000000000001111111254eeb25477b68fb85ed929f73a960582",
      "topic3": null
    }
  ],
  "txs": [
    {
      "hash": "0x0bd4d05cfee0107ac69f7add8e21d66c3e4fd014b7aad595d6336910a6bfee39",
      "gas": "109803",
      "gasPrice": "13481860832",
      "nonce": "291",
      "input": "0x12aa3caf00000000000000000000000053222470cdcfb8081c0e3a50fd106f0d69e63f20000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee00000000000000000000000053222470cdcfb8081c0e3a50fd106f0d69e63f200000000000000000000000003ec92c9d09403a76bda445ffdfaf6de59717219f00000000000000000000000000000000000000000000000e56d1e2316582742700000000000000000000000000000000000000000000000e53262757bf439a6f0000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000001600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000000000006200003c4121c02aaa39b223fe8d0a0e5c4f27ead9083c756cc200042e1a7d4d0000000000000000000000000000000000000000000000000000000000000000e0201111111254eeb25477b68fb85ed929f73a960582000000000000000e56d1e23165827427e26b9977",
      "transactionIndex": "92",
      "fromAddress": "0x3ec92c9d09403a76bda445ffdfaf6de59717219f",
      "toAddress": "0x1111111254eeb25477b68fb85ed929f73a960582",
      "value": "0",
      "type": "2",
      "v": "0",
      "r": "5776335037912114053229884461119750189570811705028494471955321961511802532800",
      "s": "50481622078880425443801093626517935308993319586804232237135731552994210947860",
      "receiptCumulativeGasUsed": "7225224",
      "receiptGasUsed": "70168",
      "receiptContractAddress": null,
      "receiptRoot": null,
      "receiptStatus": "1"
    }
  ],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [
    {
      "transactionHash": "0x59cd370a41c699bdb77a020b3a27735bb7442ace68ec8313040b8b9ee2672244",
      "logIndex": "135",
      "contract": "0x96beaa1316f85fd679ec49e5a63dacc293b044be",
      "owner": "0x1748789703159580520cc2ce6d1ba01e7359c44c",
      "spender": "0x1111111254eeb25477b68fb85ed929f73a960582",
      "value": "115792089237316195423570985008687907853269984665640564039457584007913129639935",
      "tokenName": "This Is Not Alpha",
      "tokenSymbol": "TINA",
      "tokenDecimals": "18",
      "valueWithDecimals": "1.15792089237316195423570985008687907853269984665640564039457584007913129639935e+59"
    }
  ],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": []
}
```

***

## NFT Transfers

NFT transfers are automatically decoded for both ERC-721 and ERC-1155 tokens.

Each NFT transfer includes:

* `tokenName`: the name of the NFT
* `tokenSymbol`: the symbol of the NFT (only for [ERC721](https://eips.ethereum.org/EIPS/eip-721))
* `tokenContractType`: the type of the NFT (either [ERC721](https://eips.ethereum.org/EIPS/eip-721) or [ERC1155](https://eips.ethereum.org/EIPS/eip-1155))
* `to`: the receiver address of the NFT transfer
* `from`: the sender address of the NFT transfer
* `amount`: the amount of NFT transferred in the transaction (`1` for [ERC721](https://eips.ethereum.org/EIPS/eip-721))
* `transactionHash`: the transaction hash of the NFT transfer on the blockchain
* `tokenId`: the token ID of the NFT transferred
* `operator`: a third party address that has been approved to manage NFTs owned by `from` address. You can read more about operator in the [EIP1155 standard](https://eips.ethereum.org/EIPS/eip-1155).
* `contract`: the contract address of the NFT transferred

**Example:**

```javascript expandable theme={null}
{
  "confirmed": false,
  "chainId": "0x13881",
  "abi": [],
  "streamId": "c4cf9b1a-0cb3-4c79-9ca3-04f11856c555",
  "tag": "ChrisWallet",
  "retries": 0,
  "block": {
    "number": "29381772",
    "hash": "0xdd64099df718e2a439a9805d25a3ab88e943a8c713f2259d9777460d7051572c",
    "timestamp": "1669640635"
  },
  "logs": [
    {
      "logIndex": "72",
      "transactionHash": "0x5ecd6b57593ab2f4f3e39fbb3318a3933e2cf9fdcf5b7ca671fb0fc2ce9dc4b5",
      "address": "0x26b4e79bca1a550ab26a8e533be97c40973b2671",
      "data": "0x",
      "topic0": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
      "topic1": "0x00000000000000000000000074f64bebb1a9615fc7c2ead9c894b6ffd1803582",
      "topic2": "0x000000000000000000000000e496601436da37a045d8e88bbd6b2c2e17d8fe33",
      "topic3": "0x0000000000000000000000000000000000000000000000000000000000000000"
    }
  ],
  "txs": [],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": [
    {
      "operator": null,
      "from": "0x74f64bebb1a9615fc7c2ead9c894b6ffd1803582",
      "to": "0xe496601436da37a045d8e88bbd6b2c2e17d8fe33",
      "tokenId": "0",
      "amount": "1",
      "transactionHash": "0x5ecd6b57593ab2f4f3e39fbb3318a3933e2cf9fdcf5b7ca671fb0fc2ce9dc4b5",
      "logIndex": "72",
      "contract": "0x26b4e79bca1a550ab26a8e533be97c40973b2671",
      "possibleSpam": false,
      "tokenName": "Test",
      "tokenSymbol": "SYMBOL",
      "tokenContractType": "ERC721"
    }
  ]
}
```

***

## NFT Approvals

Approval events for ERC-721 and ERC-1155 tokens are grouped under `nftApprovals` and decoded automatically.

***

## Smart Contract Events Only

If you configure a stream to listen only to specific contract events:

* Only `logs` will be populated
* ABI decoding is applied using the ABI you provide
* No token or transaction arrays are included unless explicitly enabled

**Example:**

```javascript expandable theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "abi": [
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": false,
          "name": "reserve0",
          "type": "uint112"
        },
        {
          "indexed": false,
          "name": "reserve1",
          "type": "uint112"
        }
      ],
      "name": "Sync",
      "type": "event"
    }
  ],
  "streamId": "6378fe38-54c7-4816-8d61-fca8e128e260",
  "tag": "test_events",
  "retries": 1,
  "block": {
    "number": "15984246",
    "hash": "0x7f8d8285b572a60f6a14d5f1dcbd40e487ccffd9ec78f8dfbccb49aa191fbb95",
    "timestamp": "1668621827"
  },
  "logs": [
    {
      "logIndex": "320",
      "transactionHash": "0xf1682fa49b83689093b467ac6937785102895fc3ba418624c28d04f9af6e5e2b",
      "address": "0x4cd36d6f32586177e36179a810595a33163a20bf",
      "data": "0x00000000000000000000000000000000000000000000944ad388817e590ab6070000000000000000000000000000000000000000000000000000008a602de18e",
      "topic0": "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1",
      "topic1": null,
      "topic2": null,
      "topic3": null
    }
  ],
  "txs": [],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": []
}
```

***

## Internal Transactions (`txsInternal`)

Internal transactions represent value transfers occurring **inside contract execution**.

Included when `includeInternalTxs` is enabled.

Useful for:

* DeFi protocol tracing
* Understanding internal fund movement
* Advanced analytics

**Example:**

```javascript expandable theme={null}
{
  "confirmed": false,
  "chainId": "0x1",
  "abi": [],
  "streamId": "c28d9e2e-ae9d-4fe6-9fc0-5fcde2dcdd17",
  "tag": "internal transactions",
  "retries": 0,
  "block": {
    "number": "15988462",
    "hash": "0xa4520ca85758374d05c31f6e6869f081997daa6e6b18449d49cfac4558f9e7f8",
    "timestamp": "1668672659"
  },
  "logs": [],
  "txs": [],
  "txsInternal": [
    {
      "from": "0x1111111254eeb25477b68fb85ed929f73a960582",
      "to": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
      "value": "11000000000000000",
      "gas": "117885",
      "transactionHash": "0x0e5c3114c0ee7d29cca17aa0b8e790c4d7d25b4789bd14150f113956b5ce94de"
    }
  ],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftApprovals": {
    "ERC1155": [],
    "ERC721": []
  },
  "nftTransfers": []
}
```

***

## Retry Metadata

If a webhook delivery fails:

* `retries` increments
* The event is retried automatically
* Failed deliveries are retained for replay (plan-dependent)

See [**Retries & Replays**](/streams/webhooks/retries-and-replays) for full recovery behavior.

***

## Common Next Steps

Depending on what you’re building:

* Need cleaner decoded data? Explore [Parsed Data](/streams/streams-concepts/parsed-data)
* Need fine-grained filtering? Explore [Filters](/streams/streams-concepts/filters)
* Need on-chain lookups inside webhooks? Explore [Triggers](/streams/streams-concepts/triggers)
* Handling high throughput? Explore [Rate Limits](/streams/streams-concepts/rate-limits)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Confirmation & Finality

> Understand how blockchain confirmations work, how Moralis defines finality, and how confirmed and unconfirmed webhooks should be handled.

### Overview

Blockchains are probabilistic systems. A transaction may appear in a block and later be removed due to a chain reorganization (re-org).

To handle this safely, Moralis Streams distinguishes between **unconfirmed** and **confirmed** events and delivers both to your backend.

This page explains **what confirmation and finality mean**, and how they are exposed through Streams.

***

### What Is Confirmation?

When a transaction is included in a newly mined block, it is considered **unconfirmed**.

At this stage:

* The block may still be replaced
* Transactions may be reordered or dropped
* State changes are *not final*

Streams delivers these events with:

```javascript  theme={null}
"confirmed": false
```

This enables **low-latency, real-time reactions**.

See also:

* [**Webhook Delivery**](/streams/webhooks/webhook-delivery)
* [**Webhook Payload**](/streams/webhooks/webhook-payloads)

***

### What Is Finality?

A transaction becomes **confirmed** once enough blocks have been mined on top of it.

At this point:

* The risk of re-org is extremely low
* State can be safely persisted
* Balances and ownership can be finalized

Streams delivers a second webhook with:

```javascript  theme={null}
"confirmed": true
```

Confirmation thresholds vary by chain. See [**Supported Chains**](/streams/supported-chains)**.**

***

### Why Streams Sends Two Webhooks

Streams intentionally sends **both states** so you can:

* React instantly (unconfirmed)
* Persist safely (confirmed)

This avoids the need to:

* Poll block explorers
* Manually track confirmations
* Reconcile state after re-orgs

For how Streams handles re-orgs internally:

* [**Re-org Handling**](/streams/streams-concepts/re-org-handling)

***

### Ordering & Edge Cases

In rare cases:

* A `confirmed: true` webhook may arrive before `confirmed: false`

This can occur due to:

* Network latency
* Retry behavior
* Regional delivery differences

Your system should:

* Treat each webhook independently
* Use transaction hash + confirmation flag
* Be idempotent

***

### Common Patterns

**Real-time UX**

* Act on `confirmed: false`
* Update UI optimistically

**Accounting / Persistence**

* Only persist on `confirmed: true`

**Analytics**

* Use both, but deduplicate by transaction hash

***

### Next Steps

* How re-orgs are handled internally → Explore [Re-org Handling](/streams/streams-concepts/re-org-handling)
* How delivery works end-to-end →  Explore [Webhook Delivery](/streams/webhooks/webhook-delivery)
* How to replay affected blocks → Explore [Retries & Replays](/streams/webhooks/retries-and-replays)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Test Webhooks

> Learn how Moralis uses test webhooks to validate your endpoint when creating or updating a stream, and how to handle them correctly.

## Overview

Whenever you **create or update a stream**, Moralis sends a **test webhook** to your configured webhook URL.

This test verifies that:

* Your endpoint is reachable
* Your server responds correctly
* Webhook delivery can safely begin

If the test webhook is **not acknowledged successfully**, the stream will **not start**.

***

## When Test Webhooks Are Sent

A test webhook is sent when you:

* Create a new stream
* Update an existing stream (e.g. webhook URL, filters, addresses, chains)
* Reactivate a paused stream

This happens **before** any real on-chain events are delivered.

***

## Required Response

To pass the test webhook:

* Your server **must return a 2xx HTTP status code**
* Common examples: `200`, `201`, `202`

Any non-2xx response will cause the test to fail.

<Note>
  No response body is required - only the status code matters.
</Note>

***

## Test Webhook Payload

The test webhook uses the **same payload structure** as real webhooks, but contains **empty data**.

Example:

```javascript  theme={null}
{
  "confirmed": true,
  "chainId": "",
  "streamId": "",
  "tag": "",
  "retries": 0,
  "block": {
    "number": "",
    "hash": "",
    "timestamp": ""
  },
  "logs": [],
  "txs": [],
  "txsInternal": [],
  "erc20Transfers": [],
  "erc20Approvals": [],
  "nftTransfers": [],
  "nftApprovals": {
    "ERC721": [],
    "ERC1155": []
  },
  "abi": {}
}
```

Important notes:

* No on-chain data is included
* No transactions or logs are present
* This payload **should not be persisted**

For full payload documentation, explore [Webhook Payload](/streams/webhooks/webhook-payloads).

***

## How to Handle Test Webhooks

Your webhook handler should:

1. Accept the request
2. Optionally log it
3. Return a 2xx response
4. Skip any application-specific processing

A simple approach is to:

* Detect empty payloads
* Short-circuit processing

***

## Security Considerations

Test webhooks:

* Include an `x-signature` header
* Should be verified the same way as real webhooks

For signature verification, explore [**Webhook Security**](/streams/security-and-reliability/webhook-security)**.**

***

## Common Pitfalls

### Stream does not start

Usually caused by:

* Webhook endpoint returning non-2xx
* Endpoint timing out
* Server not reachable from the internet

### Test webhook processed as real data

Avoid:

* Writing empty events to your database
* Triggering business logic on test payloads

***

## Relationship to Retries & Replays

Test webhooks:

* Are **not retried**
* Are **not stored in history**
* Cannot be replayed

[Retries and Replays](/streams/webhooks/retries-and-replays) apply only to **real event webhooks**.

***

## Next Steps

* Understand delivery guarantees → Explore [Webhook Delivery](/streams/webhooks/webhook-delivery)
* Inspect real payloads → Explore [Webhook Payload](/streams/webhooks/webhook-payloads)
* Secure your endpoint → Explore [Webhook Security](/streams/security-and-reliability/webhook-security)
* Handle failures and recovery →  Explore [Error Handling](/streams/streams-concepts/error-handling)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Retries & Replays

> Recover missed Streams events by replaying blocks and streams, and understand how Moralis handles retries, failures, and recovery scenarios.

## Overview

Streams is designed for **reliable, real-time delivery**, but there are situations where events may need to be replayed or recovered.

Moralis provides **manual replay mechanisms** to help you recover missed webhooks caused by configuration changes, reload timing, or temporary failures.

***

## When Replays Are Needed

You may need to replay events if:

* A stream was reloading when a block was produced
* Addresses were added shortly before on-chain activity
* A webhook endpoint was temporarily unavailable
* A stream was paused or in an error state
* You are recovering from an incident or deployment issue

Replays allow you to **reprocess past blocks** and receive the webhooks that would have been delivered.

***

## Replay Block

The **Replay Block** feature reprocesses a specific block for a given stream.

When replayed:

* The block is re-evaluated against the stream configuration
* Matching events trigger webhooks again
* Webhooks are delivered as if the block just occurred

This is the most precise way to recover missed events.

***

### When to Use Block Replay

Use block replay when:

* You know the exact block number that was missed
* Only a small time window was affected
* You want to avoid duplicate data outside that block

***

## Replay Best Practices

* Always confirm the stream configuration before replaying
* Replays respect the **current** stream configuration
* Ensure your webhook handler is **idempotent**
* Avoid replaying large numbers of blocks unnecessarily

***

## Webhook Retries vs Replays

It’s important to distinguish between **automatic retries** and **manual replays**.

### Automatic retries

* Triggered when your webhook endpoint returns an error or times out
* Handled automatically by Moralis
* Occur shortly after the initial delivery attempt
* Do **not** require manual intervention

### Manual replays

* Triggered by you
* Used to recover missed events
* Can replay historical blocks
* Useful after configuration changes or outages

***

## Recovery After Stream Reloads

When addresses are added to a stream, a reload is required.

If activity occurs before the reload completes:

* The event may not trigger a webhook
* The block can be recovered using replay

This is a normal and expected edge case for dynamic address management.

***

## Recovery After Errors or Termination

* Streams in the `error` state stop delivering events
* Streams in the `terminated` state stop permanently

In both cases:

* Events occurring during downtime are not queued
* Replays can be used to recover missed blocks
* Terminated streams require creating a new stream before replaying

***

## Designing for Recovery

To make recovery safe and predictable:

* Treat webhook processing as **idempotent**
* Use transaction hashes + log indexes as unique identifiers
* Log replayed events separately if needed
* Avoid assuming delivery order

Streams prioritises **correctness over ordering**.

***

## What Cannot Be Recovered

Replays cannot recover:

* Events that occurred before a stream existed
* Events filtered out by stream configuration
* Events dropped intentionally (e.g. spam filtering)

***

## Summary

* Streams delivers events in real time, with retries
* Reloads and failures can cause missed events
* Block replay allows precise recovery
* Recovery is explicit and controlled
* Idempotent webhook handling is essential


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Webhook Security

> Learn how Moralis secures webhook delivery using request signatures, and how to verify webhook authenticity in your backend.

## Overview

All Moralis webhooks are **cryptographically signed** to ensure authenticity and integrity.

By verifying each webhook signature, you can be confident that:

* The request was sent by Moralis
* The payload was not tampered with
* Your application is protected against spoofed requests

Signature verification is **strongly recommended** for all production environments.

***

## How Webhook Signing Works

Every webhook request includes a signature in the HTTP headers:

```text  theme={null}
x-signature
```

This signature is generated by:

1. Serializing the webhook payload
2. Appending your account’s secret
3. Computing a Keccak-256 hash (via `web3.utils.sha3`)

Conceptually:

```javascript  theme={null}
signature = sha3(JSON.stringify(body) + secret)
```

The generated signature is then sent with the webhook request.

***

## What Is the Secret Key?

The **secret key** is a Streams-specific credential associated with your Moralis account.

* It is **not** your API key
* It is used **only** for webhook verification
* It can be retrieved via the Streams settings endpoint

***

## Verifying Webhook Signatures

To verify a webhook:

1. Read the `x-signature` header
2. Recompute the signature using the request body and your secret
3. Compare the two values
4. Reject the request if they do not match

Verification should happen **before** processing the payload.

***

## Example: Node.js (Express)

```javascript  theme={null}
import { Web3 } from "web3";

function verifySignature(req, secret) {
  const providedSignature = req.headers["x-signature"];
  if (!providedSignature) {
    throw new Error("Missing signature");
  }

  const web3 = new Web3();
  const expectedSignature = web3.utils.sha3(
    JSON.stringify(req.body) + secret
  );

  if (expectedSignature !== providedSignature) {
    throw new Error("Invalid signature");
  }
}
```

Use this check at the start of your webhook handler.

For handling test webhooks safely, explore [Test Webhooks](/streams/webhooks/test-webhooks).

***

## Security Best Practices

### Always verify signatures

Do not trust:

* Source IP
* User-Agent headers
* Payload structure alone

***

### Use HTTPS

Webhook endpoints must be served over HTTPS to prevent interception or replay.

***

### Keep handlers lightweight

Slow responses can cause retries or queue buildup. Explore [Webhook Delivery](/streams/webhooks/webhook-delivery) to learn how to handle this.

***

### Make handlers idempotent

Retries may result in duplicate payloads. Read more about [Retries & Replays](/streams/webhooks/retries-and-replays).

***

## What Happens If Verification Fails?

If your endpoint:

* Rejects the request (non-2xx)
* Throws an error
* Times out

Then:

* The webhook is considered failed
* Automatic retries will occur
* The stream’s success rate may drop

Read [Error Handling](/streams/streams-concepts/error-handling) for more on failure handling.

***

## Relationship to Other Webhook Concepts

| Topic                    | Page                                                                       |
| :----------------------- | :------------------------------------------------------------------------- |
| Delivery guarantees      | [**Webhook Delivery**](/streams/webhooks/webhook-delivery)                 |
| Confirmed vs unconfirmed | [**Confirmation & Finality**](/streams/webhooks/confirmation-and-finality) |
| Test requests            | [**Test Webhooks**](/streams/webhooks/test-webhooks)                       |
| Retries & recovery       | [**Retries & Replays**](/streams/webhooks/retries-and-replays)             |
| Failure states           | [**Error Handling**](/streams/streams-concepts/error-handling)             |


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Spam Detection

> Learn how Moralis Streams identifies and flags potential spam contracts in webhook payloads, helping you filter or handle suspicious on-chain activity safely.

<Warning>
  Streams currently uses a legacy spam detection system. This will be upgraded to align with the newer Moralis [API Spam Detection](/data-api/resources/spam-filtering) in a future release.
</Warning>

Spam detection in Moralis Streams provides an **additional safety signal** that helps you identify contracts associated with spam, phishing, or suspicious activity.

This feature allows you to:

* Detect potentially malicious contracts in real time
* Filter or suppress spam-related events
* Warn users about risky interactions

***

## How Spam Detection Works

When spam detection is enabled, Streams adds a boolean field called:

```javascript  theme={null}
possibleSpam
```

This field is attached to the following webhook objects:

* `erc20Transfers`
* `erc20Approvals`
* `nftTransfers`
* `nftApprovals`

The value indicates whether the contract involved in the event is **potentially associated with spam or malicious behavior**.

Example:

```javascript  theme={null}
{
  "contract": "0x...",
  "possibleSpam": true
}
```

***

## How to Use Spam Signals

The `possibleSpam` flag is designed as a **signal**, not a hard block.

Common usage patterns include:

* Hiding spam tokens or NFTs from user interfaces
* Suppressing notifications for spam-related activity
* Flagging risky activity for manual review
* Applying stricter filters to spam-flagged events

Filtering options:

* [**Filters**](/streams/streams-concepts/filters)

***

## Filtering Out Spam Events

You can configure Streams to **exclude spam-related events entirely**.

By enabling the `filterPossibleSpamAddresses` option:

* Events involving contracts flagged as spam will not trigger webhooks
* These events will not consume stream usage

This is useful if you want to:

* Reduce noise
* Avoid processing low-quality or malicious activity

Related configuration:

* [**Filters**](/streams/streams-concepts/filters)
* [**Advanced Options**](/streams/streams-concepts/advanced-options)

***

## How Contracts Are Classified

Contracts flagged as spam are evaluated against a set of internal criteria, including:

* Compliance with token and NFT standards
* Minting and transfer behavior (e.g. honeypot patterns)
* Copycat or impersonation signals
* Other proprietary heuristics

Classification is **continuously updated** as new data becomes available.

***

## Supported Chains

Spam detection in Streams is supported on **all EVM-compatible chains**, with the strongest initial coverage on:

* Ethereum Mainnet
* Polygon Mainnet
* BNB Chain

***

## Relationship to API Spam Detection

Streams spam detection is **separate from** the newer Moralis API [Spam Filtering](/data-api/resources/spam-filtering) and [Token Safety](/data-api/data-features/token-scores) features.

Key differences:

* Streams uses a legacy classification system
* API spam detection includes richer metadata and filtering
* The two systems will be unified in a future update

API spam features:

* [**Spam Filtering**](/data-api/resources/spam-filtering)
* [**Token Scores**](/data-api/data-features/token-scores)

***

## Best Practices

* Treat `possibleSpam` as a signal, not absolute truth
* Combine spam flags with confirmation state
* Avoid persisting spam events unless required
* Prefer filtering spam at the stream level when possible

***

## Related Pages

* [**Streams Filters**](/streams/streams-concepts/filters)
* [**Advanced Options**](/streams/streams-concepts/advanced-options)
* [**Webhook Payload**](/streams/webhooks/webhook-payloads)
* [**API Spam Filtering**](/data-api/resources/spam-filtering)
* [**Delivery Guarantees**](/streams/security-and-reliability/delivery-guarantees)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Delivery Guarantees

> Learn how Moralis reliably delivers blockchain data, including retry behavior, durability, and how events are protected from data loss.

## Overview

Moralis is built to deliver blockchain data **reliably**, even in the presence of network issues, server downtime, or blockchain reorganizations.

This page explains:

* What Moralis guarantees
* How delivery failures are handled
* What you should expect when consuming events at scale

***

## Reliable Event Delivery

Moralis ensures that **eligible blockchain events are not silently lost**.

If a webhook delivery fails (for example, due to a timeout or server error), Moralis will **automatically retry delivery** until the event is acknowledged or the retry window expires.

As a result:

* Events are delivered reliably
* Temporary failures do not cause data loss
* Duplicate deliveries are possible and expected in failure scenarios

Delivery mechanics:

* [**Webhook Delivery**](/streams/webhooks/webhook-delivery)
* [**Retries & Replays**](/streams/webhooks/retries-and-replays)

***

## What This Means in Practice

Under normal operation:

* Each event is delivered once

If delivery fails:

* The event is retried automatically
* The same payload may be sent again
* Your system should handle duplicates safely

This design favors **correctness and completeness** over strict delivery assumptions.

Guidance on safe handling:

* [**Ordering & Idempotency**](/streams/security-and-reliability/ordering-and-idempotency)

***

## Durable Storage & Recovery

When delivery issues occur:

* Failed webhook deliveries are retained (plan-dependent)
* Events can be replayed manually if needed
* Delivery resumes automatically once issues are resolved

Recovery options:

* [**Retries & Replays**](/streams/webhooks/retries-and-replays)
* [**Error Handling**](/streams/streams-concepts/error-handling)

***

## Blockchain Reorganization Safety

Blockchains are probabilistic systems. Transactions may appear in a block and later be removed due to reorganization.

Moralis handles this by:

* Delivering provisional events (`confirmed: false`)
* Finalizing only confirmed events (`confirmed: true`)
* Preventing invalidated data from being treated as final

More details:

* [**Confirmation & Finality**](/streams/webhooks/confirmation-and-finality)
* [**Re-org Handling**](/streams/streams-concepts/re-org-handling)

***

## What Moralis Does *Not* Guarantee

### Strict ordering

Events may arrive:

* Out of order
* With retries interleaved
* With confirmed events preceding unconfirmed ones (rare)

Ordering is intentionally relaxed to ensure reliability.

Ordering strategies:

* [**Ordering & Idempotency**](/streams/security-and-reliability/ordering-and-idempotency)

***

### Reliable Delivery with Retries

Moralis does not attempt to deliver each event *exactly once*.

Exactly-once delivery is not realistically achievable across network boundaries and webhook-based systems. Instead, Moralis guarantees **reliable delivery with retries**, and expects consumers to be idempotent.

***

## Operational Safeguards

To protect delivery reliability, Moralis includes:

* Automatic retry schedules
* Delivery queue limits and backpressure
* Stream health monitoring
* Error and termination states
* Email notifications on critical failures

Operational details:

* [**Error Handling**](/streams/streams-concepts/error-handling)
* [**Stream Lifecycle**](/streams/streams-concepts/stream-lifecycle-and-management)

***

## Best Practices

To fully benefit from Moralis’ delivery guarantees:

* Make webhook handlers idempotent
* Persist state only for confirmed events
* Monitor queue size headers
* Use replays for recovery, not polling

***

## Related Pages

* [**Ordering & Idempotency**](/streams/security-and-reliability/ordering-and-idempotency)
* [**Webhook Delivery**](/streams/webhooks/webhook-delivery)
* [**Retries & Replays**](/streams/webhooks/retries-and-replays)
* [**Error Handling**](/streams/streams-concepts/error-handling)
* [**Confirmation & Finality**](/streams/webhooks/confirmation-and-finality)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Delivery Guarantees

> Learn how Moralis reliably delivers blockchain data, including retry behavior, durability, and how events are protected from data loss.

## Overview

Moralis is built to deliver blockchain data **reliably**, even in the presence of network issues, server downtime, or blockchain reorganizations.

This page explains:

* What Moralis guarantees
* How delivery failures are handled
* What you should expect when consuming events at scale

***

## Reliable Event Delivery

Moralis ensures that **eligible blockchain events are not silently lost**.

If a webhook delivery fails (for example, due to a timeout or server error), Moralis will **automatically retry delivery** until the event is acknowledged or the retry window expires.

As a result:

* Events are delivered reliably
* Temporary failures do not cause data loss
* Duplicate deliveries are possible and expected in failure scenarios

Delivery mechanics:

* [**Webhook Delivery**](/streams/webhooks/webhook-delivery)
* [**Retries & Replays**](/streams/webhooks/retries-and-replays)

***

## What This Means in Practice

Under normal operation:

* Each event is delivered once

If delivery fails:

* The event is retried automatically
* The same payload may be sent again
* Your system should handle duplicates safely

This design favors **correctness and completeness** over strict delivery assumptions.

Guidance on safe handling:

* [**Ordering & Idempotency**](/streams/security-and-reliability/ordering-and-idempotency)

***

## Durable Storage & Recovery

When delivery issues occur:

* Failed webhook deliveries are retained (plan-dependent)
* Events can be replayed manually if needed
* Delivery resumes automatically once issues are resolved

Recovery options:

* [**Retries & Replays**](/streams/webhooks/retries-and-replays)
* [**Error Handling**](/streams/streams-concepts/error-handling)

***

## Blockchain Reorganization Safety

Blockchains are probabilistic systems. Transactions may appear in a block and later be removed due to reorganization.

Moralis handles this by:

* Delivering provisional events (`confirmed: false`)
* Finalizing only confirmed events (`confirmed: true`)
* Preventing invalidated data from being treated as final

More details:

* [**Confirmation & Finality**](/streams/webhooks/confirmation-and-finality)
* [**Re-org Handling**](/streams/streams-concepts/re-org-handling)

***

## What Moralis Does *Not* Guarantee

### Strict ordering

Events may arrive:

* Out of order
* With retries interleaved
* With confirmed events preceding unconfirmed ones (rare)

Ordering is intentionally relaxed to ensure reliability.

Ordering strategies:

* [**Ordering & Idempotency**](/streams/security-and-reliability/ordering-and-idempotency)

***

### Reliable Delivery with Retries

Moralis does not attempt to deliver each event *exactly once*.

Exactly-once delivery is not realistically achievable across network boundaries and webhook-based systems. Instead, Moralis guarantees **reliable delivery with retries**, and expects consumers to be idempotent.

***

## Operational Safeguards

To protect delivery reliability, Moralis includes:

* Automatic retry schedules
* Delivery queue limits and backpressure
* Stream health monitoring
* Error and termination states
* Email notifications on critical failures

Operational details:

* [**Error Handling**](/streams/streams-concepts/error-handling)
* [**Stream Lifecycle**](/streams/streams-concepts/stream-lifecycle-and-management)

***

## Best Practices

To fully benefit from Moralis’ delivery guarantees:

* Make webhook handlers idempotent
* Persist state only for confirmed events
* Monitor queue size headers
* Use replays for recovery, not polling

***

## Related Pages

* [**Ordering & Idempotency**](/streams/security-and-reliability/ordering-and-idempotency)
* [**Webhook Delivery**](/streams/webhooks/webhook-delivery)
* [**Retries & Replays**](/streams/webhooks/retries-and-replays)
* [**Error Handling**](/streams/streams-concepts/error-handling)
* [**Confirmation & Finality**](/streams/webhooks/confirmation-and-finality)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Create Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml PUT /streams/evm
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm:
    put:
      tags:
        - EVM Streams
      summary: Create stream
      description: Creates a new evm stream.
      operationId: CreateStream
      parameters: []
      requestBody:
        description: Provide a Stream Model
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/StreamsModelCreate'
              description: Provide a Stream Model
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    StreamsModelCreate:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
      required:
        - webhookUrl
        - description
        - chainIds
      type: object
      additionalProperties: false
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Update Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /streams/evm/{id}
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}:
    post:
      tags:
        - EVM Streams
      summary: Update stream
      description: Updates a specific evm stream.
      operationId: UpdateStream
      parameters:
        - description: The id of the stream to update
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      requestBody:
        description: Provide a Stream Model
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Partial_StreamsModelCreate_'
              description: Provide a Stream Model
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    Partial_StreamsModelCreate_:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi: {}
        advancedOptions: {}
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          description: triggers
      type: object
      description: Make all properties in T optional
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Delete Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml DELETE /streams/evm/{id}
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}:
    delete:
      tags:
        - EVM Streams
      summary: Delete stream
      description: Delete a specific evm stream.
      operationId: DeleteStream
      parameters:
        - description: The id of the stream to delete
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Stream by ID



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /streams/evm/{id}
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}:
    get:
      tags:
        - EVM Streams
      summary: Get a specific evm stream.
      description: Get a specific evm stream.
      operationId: GetStream
      parameters:
        - description: The id of the stream to get
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get All Streams



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /streams/evm
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm:
    get:
      tags:
        - EVM Streams
      summary: Get streams
      description: >-
        Get all the evm streams for the current project based on the project
        api-key .
      operationId: GetStreams
      parameters:
        - description: Limit response results max value 100
          in: query
          name: limit
          required: true
          schema:
            type: number
            format: double
        - description: Cursor for fetching next page
          in: query
          name: cursor
          required: false
          schema:
            type: string
        - in: query
          name: status
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsResponse'
      security:
        - x-api-key: []
components:
  schemas:
    StreamsResponse:
      properties:
        result:
          items:
            $ref: '#/components/schemas/StreamsModel'
          type: array
          description: Array of project Streams
        cursor:
          type: string
          description: Cursor for fetching next page
        total:
          type: number
          format: double
          description: Total count of streams on the project
      required:
        - result
        - total
      type: object
      additionalProperties: false
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Duplicate Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /streams/evm/{id}/duplicate
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/duplicate:
    post:
      tags:
        - EVM Streams
      summary: Duplicate stream
      description: Duplicate a specific evm stream.
      operationId: DuplicateStream
      parameters:
        - description: The id of the stream to duplicate
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Update Stream Status



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /streams/evm/{id}/status
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/status:
    post:
      tags:
        - EVM Streams
      summary: Update stream status
      description: Updates the status of specific evm stream.
      operationId: UpdateStreamStatus
      parameters:
        - description: The id of the stream to update
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      requestBody:
        description: Provide a Stream Model
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/StreamsStatusUpdate'
              description: Provide a Stream Model
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsStatusUpdate:
      properties:
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
      required:
        - status
      type: object
      additionalProperties: false
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Update Stream Status



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /streams/evm/{id}/status
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/status:
    post:
      tags:
        - EVM Streams
      summary: Update stream status
      description: Updates the status of specific evm stream.
      operationId: UpdateStreamStatus
      parameters:
        - description: The id of the stream to update
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      requestBody:
        description: Provide a Stream Model
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/StreamsStatusUpdate'
              description: Provide a Stream Model
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StreamsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    StreamsStatusUpdate:
      properties:
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
      required:
        - status
      type: object
      additionalProperties: false
    StreamsModel:
      properties:
        webhookUrl:
          type: string
          description: Webhook URL where moralis will send the POST request.
        description:
          type: string
          description: A description for this stream
        tag:
          type: string
          description: >-
            A user-provided tag that will be send along the webhook, the user
            can use this tag to identify the specific stream if multiple streams
            are present
        topic0:
          items:
            type: string
          type: array
          nullable: true
          description: >-
            An Array of topic0's in string-signature format ex:
            ['FunctionName(address,uint256)']
        allAddresses:
          type: boolean
          description: >-
            Include events for all addresses (only applied when abi and topic0
            is provided)
        includeNativeTxs:
          type: boolean
          description: Include or not native transactions defaults to false
        includeContractLogs:
          type: boolean
          description: Include or not logs of contract interactions defaults to false
        includeInternalTxs:
          type: boolean
          description: Include or not include internal transactions defaults to false
        includeAllTxLogs:
          type: boolean
          description: >-
            Include all logs if atleast one value in tx or log matches stream
            config
        getNativeBalances:
          items:
            $ref: '#/components/schemas/getNativeBalances'
          type: array
          description: Include native balances for each address in the webhook
        abi:
          nullable: true
        advancedOptions:
          nullable: true
        chainIds:
          items:
            type: string
          type: array
          description: 'The ids of the chains for this stream in hex Ex: ["0x1","0x38"]'
        filterPossibleSpamAddresses:
          type: boolean
          description: Indicator if it is a demo stream
        demo:
          type: boolean
          description: Filter possible spam addresses
        triggers:
          items:
            $ref: '#/components/schemas/StreamsTrigger'
          type: array
          nullable: true
          description: triggers
        id:
          $ref: '#/components/schemas/UUID'
          description: The unique uuid of the stream
        status:
          $ref: '#/components/schemas/StreamsStatus'
          description: The status of the stream.
        statusMessage:
          type: string
          description: Description of current status of stream.
        updatedAt:
          type: string
          format: date-time
          description: Last Updated Date.
        amountOfAddresses:
          type: number
          format: double
          description: Amount of Addresses.
      required:
        - webhookUrl
        - description
        - chainIds
        - id
        - status
        - statusMessage
        - updatedAt
        - amountOfAddresses
      type: object
      additionalProperties: false
    StreamsStatus:
      description: |-
        The stream status:
        [active] The Stream is healthy and processing blocks
        [paused] The Stream is paused and is not processing blocks
        [error] The Stream has encountered an error and is not processing blocks
      enum:
        - active
        - paused
        - error
        - terminated
      type: string
      example: {}
    getNativeBalances:
      properties:
        selectors:
          items:
            type: string
          type: array
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
            - internalTx
      required:
        - selectors
        - type
      type: object
      additionalProperties: false
    StreamsTrigger:
      description: Trigger
      properties:
        type:
          type: string
          enum:
            - tx
            - log
            - erc20transfer
            - erc20approval
            - nfttransfer
        contractAddress:
          type: string
        inputs:
          items:
            anyOf:
              - type: string
              - items: {}
                type: array
          type: array
        functionAbi:
          $ref: '#/components/schemas/AbiItem'
        topic0:
          type: string
        callFrom:
          type: string
      required:
        - type
        - contractAddress
        - functionAbi
      type: object
      additionalProperties: false
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Send Webhook Data by Block Number



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /streams/evm/{chainId}/block-to-webhook/{blockNumber}/{streamId}
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{chainId}/block-to-webhook/{blockNumber}/{streamId}:
    post:
      tags:
        - EVM Streams
      summary: >-
        Send webhook based on a specific block number using stream config and
        addresses.
      description: Execute.
      operationId: GetStreamBlockDataToWebhookByNumber
      parameters:
        - in: path
          name: chainId
          required: true
          schema:
            type: string
        - in: path
          name: blockNumber
          required: true
          schema:
            type: number
            format: double
        - in: path
          name: streamId
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                type: number
                enum:
                  - null
                nullable: true
      security:
        - x-api-key: []
components:
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Addresses by Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /streams/evm/{id}/address
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/address:
    get:
      tags:
        - EVM Streams
      summary: Get addresses by stream
      description: Get all addresses associated with a specific stream.
      operationId: GetAddresses
      parameters:
        - description: the id of the stream to get the addresses from
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
        - description: Limit response results max value 100
          in: query
          name: limit
          required: true
          schema:
            type: number
            format: double
        - description: Cursor for fetching next page
          in: query
          name: cursor
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AddressesResponse'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    AddressesResponse:
      properties:
        result:
          items:
            $ref: '#/components/schemas/Addresses'
          type: array
          description: Array of project Streams
        cursor:
          type: string
          description: Cursor for fetching next page
        total:
          type: number
          format: double
          description: Total count of streams on the project
      required:
        - result
        - total
      type: object
      additionalProperties: false
    Addresses:
      properties:
        address:
          type: string
          description: Address
      required:
        - address
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Add Address to Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /streams/evm/{id}/address
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/address:
    post:
      tags:
        - EVM Streams
      summary: Add address to stream
      description: Adds an address to a Stream.
      operationId: AddAddressToStream
      parameters:
        - description: The id of the stream to add the address to
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      requestBody:
        description: Provide a Address Model
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AddressesAdd'
              description: Provide a Address Model
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AddressResponse'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    AddressesAdd:
      properties:
        address:
          anyOf:
            - type: string
            - items:
                type: string
              type: array
          description: The address or a list of addresses to be added to the Stream.
      required:
        - address
      type: object
      additionalProperties: false
    AddressResponse:
      properties:
        streamId:
          type: string
          description: The streamId
        address:
          anyOf:
            - type: string
            - items:
                type: string
              type: array
          description: Address
      required:
        - streamId
        - address
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Replace Address on Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml PATCH /streams/evm/{id}/address
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/address:
    patch:
      tags:
        - EVM Streams
      summary: Replaces address from stream
      description: Replaces address from a Stream.
      operationId: ReplaceAddressFromStream
      parameters:
        - description: The id of the stream to replace the address from
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      requestBody:
        description: Provide a Address Model
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AddressesRemove'
              description: Provide a Address Model
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AddressResponse'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    AddressesRemove:
      properties:
        address:
          anyOf:
            - type: string
            - items:
                type: string
              type: array
          description: The address or a list of addresses to be removed from the Stream.
      required:
        - address
      type: object
      additionalProperties: false
    AddressResponse:
      properties:
        streamId:
          type: string
          description: The streamId
        address:
          anyOf:
            - type: string
            - items:
                type: string
              type: array
          description: Address
      required:
        - streamId
        - address
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Delete Address from Stream



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml DELETE /streams/evm/{id}/address
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /streams/evm/{id}/address:
    delete:
      tags:
        - EVM Streams
      summary: Delete address from stream
      description: Deletes an address from a Stream.
      operationId: DeleteAddressFromStream
      parameters:
        - description: The id of the stream to delete the address from
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AddressResponse'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    AddressResponse:
      properties:
        streamId:
          type: string
          description: The streamId
        address:
          anyOf:
            - type: string
            - items:
                type: string
              type: array
          description: Address
      required:
        - streamId
        - address
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get History



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /history
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /history:
    get:
      tags:
        - History
      summary: Get history
      description: Get all history
      operationId: GetHistory
      parameters:
        - in: query
          name: limit
          required: true
          schema:
            type: number
            format: double
        - in: query
          name: cursor
          required: false
          schema:
            type: string
        - in: query
          name: transactionHash
          required: false
          schema:
            type: string
        - in: query
          name: excludePayload
          required: false
          schema:
            type: boolean
        - in: query
          name: streamId
          required: false
          schema:
            type: string
        - in: query
          name: chainId
          required: false
          schema:
            items:
              type: string
            type: array
        - in: query
          name: blockNumber
          required: false
          schema:
            type: array
            items:
              type: number
              format: double
        - in: query
          name: fromTimestamp
          required: false
          schema:
            type: number
            format: double
        - in: query
          name: toTimestamp
          required: false
          schema:
            type: number
            format: double
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HistoryResponse'
      security:
        - x-api-key: []
components:
  schemas:
    HistoryResponse:
      properties:
        result:
          items:
            $ref: '#/components/schemas/HistoryModel'
          type: array
        cursor:
          type: string
        total:
          type: number
          format: double
      required:
        - result
        - total
      type: object
      additionalProperties: false
    HistoryModel:
      properties:
        id:
          $ref: '#/components/schemas/UUID'
        date:
          type: string
          format: date-time
        payload:
          anyOf:
            - $ref: '#/components/schemas/IWebhookUnParsed'
            - $ref: '#/components/schemas/AptosWebhook'
        tinyPayload:
          $ref: '#/components/schemas/ITinyPayload'
        errorMessage:
          type: string
        webhookUrl:
          type: string
        streamId:
          type: string
        tag:
          type: string
      required:
        - id
        - date
        - tinyPayload
        - errorMessage
        - webhookUrl
        - streamId
      type: object
      additionalProperties: false
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    IWebhookUnParsed:
      properties:
        block:
          $ref: '#/components/schemas/Block'
        chainId:
          type: string
        logs:
          items:
            $ref: '#/components/schemas/Log'
          type: array
        txs:
          items:
            $ref: '#/components/schemas/Transaction'
          type: array
        txsInternal:
          items:
            $ref: '#/components/schemas/InternalTransaction'
          type: array
        abi:
          items:
            $ref: '#/components/schemas/AbiItem'
          type: array
        retries:
          type: number
          format: double
        confirmed:
          type: boolean
        tag:
          type: string
        streamId:
          type: string
      required:
        - block
        - chainId
        - logs
        - txs
        - txsInternal
        - abi
        - retries
        - confirmed
        - tag
        - streamId
      type: object
      additionalProperties: false
    AptosWebhook:
      properties:
        block:
          $ref: '#/components/schemas/AptosBlock'
        changes:
          items:
            properties:
              txHash:
                type: string
            additionalProperties: {}
            required:
              - txHash
            type: object
          type: array
        coinDeposits:
          items:
            $ref: '#/components/schemas/AptosCoinDeposit'
          type: array
        coinTransfers:
          items:
            $ref: '#/components/schemas/AptosCoinTransfer'
          type: array
        coinWithdrawals:
          items:
            $ref: '#/components/schemas/AptosCoinWithdrawal'
          type: array
        events:
          items:
            properties:
              txHash:
                type: string
            additionalProperties: {}
            required:
              - txHash
            type: object
          type: array
        network:
          type: string
          enum:
            - mainnet
            - testnet
        payloads:
          items:
            properties:
              txHash:
                type: string
            additionalProperties: {}
            required:
              - txHash
            type: object
          type: array
        retries:
          type: number
          format: double
        streamId:
          type: string
        tag:
          type: string
        transactions:
          items:
            $ref: '#/components/schemas/AptosTransaction'
          type: array
      required:
        - block
        - changes
        - coinDeposits
        - coinTransfers
        - coinWithdrawals
        - events
        - network
        - payloads
        - retries
        - streamId
        - tag
        - transactions
      type: object
      additionalProperties: false
    ITinyPayload:
      properties:
        chainId:
          type: string
        confirmed:
          type: boolean
        block:
          type: string
        records:
          type: number
          format: double
        retries:
          type: number
          format: double
      required:
        - chainId
        - confirmed
        - block
        - records
        - retries
      type: object
      additionalProperties: false
    Block:
      properties:
        number:
          type: string
        hash:
          type: string
        timestamp:
          type: string
      required:
        - number
        - hash
        - timestamp
      type: object
      additionalProperties: false
    Log:
      properties:
        triggers:
          items:
            $ref: '#/components/schemas/TriggerOutput'
          type: array
        logIndex:
          type: string
        transactionHash:
          type: string
        address:
          type: string
        data:
          type: string
        topic0:
          type: string
          nullable: true
        topic1:
          type: string
          nullable: true
        topic2:
          type: string
          nullable: true
        topic3:
          type: string
          nullable: true
        triggered_by:
          items:
            type: string
          type: array
          nullable: true
      required:
        - logIndex
        - transactionHash
        - address
        - data
        - topic0
        - topic1
        - topic2
        - topic3
      type: object
      additionalProperties: false
    Transaction:
      properties:
        triggers:
          items:
            $ref: '#/components/schemas/TriggerOutput'
          type: array
        hash:
          type: string
        gas:
          type: string
          nullable: true
        gasPrice:
          type: string
          nullable: true
        nonce:
          type: string
          nullable: true
        input:
          type: string
          nullable: true
        transactionIndex:
          type: string
        fromAddress:
          type: string
        toAddress:
          type: string
          nullable: true
        value:
          type: string
          nullable: true
        type:
          type: string
          nullable: true
        v:
          type: string
          nullable: true
        r:
          type: string
          nullable: true
        s:
          type: string
          nullable: true
        receiptCumulativeGasUsed:
          type: string
          nullable: true
        receiptGasUsed:
          type: string
          nullable: true
        receiptContractAddress:
          type: string
          nullable: true
        receiptRoot:
          type: string
          nullable: true
        receiptStatus:
          type: string
          nullable: true
        triggered_by:
          items:
            type: string
          type: array
          nullable: true
      required:
        - hash
        - gas
        - gasPrice
        - nonce
        - input
        - transactionIndex
        - fromAddress
        - toAddress
        - value
        - type
        - v
        - r
        - s
        - receiptCumulativeGasUsed
        - receiptGasUsed
        - receiptContractAddress
        - receiptRoot
        - receiptStatus
      type: object
      additionalProperties: false
    InternalTransaction:
      properties:
        from:
          type: string
          nullable: true
        to:
          type: string
          nullable: true
        value:
          type: string
          nullable: true
        transactionHash:
          type: string
        gas:
          type: string
          nullable: true
        triggered_by:
          items:
            type: string
          type: array
          nullable: true
      required:
        - from
        - to
        - value
        - transactionHash
        - gas
      type: object
      additionalProperties: false
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AptosBlock:
      properties:
        lastVersion:
          type: string
        firstVersion:
          type: string
        hash:
          type: string
        timestamp:
          type: string
        number:
          type: string
      required:
        - lastVersion
        - firstVersion
        - hash
        - timestamp
        - number
      type: object
    AptosCoinDeposit:
      properties:
        txHash:
          type: string
        sequenceNumber:
          type: string
        valueWithDecimals:
          type: string
        coin:
          $ref: '#/components/schemas/AptosCoin'
        address:
          type: string
        value:
          type: string
      required:
        - txHash
        - sequenceNumber
        - valueWithDecimals
        - coin
        - address
        - value
      type: object
    AptosCoinTransfer:
      properties:
        txHash:
          type: string
        transaction:
          type: string
        valueWithDecimals:
          type: number
          format: double
        from:
          type: string
        value:
          type: string
        to:
          type: string
        coin:
          $ref: '#/components/schemas/AptosCoin'
      required:
        - txHash
        - transaction
        - valueWithDecimals
        - from
        - value
        - to
        - coin
      type: object
    AptosCoinWithdrawal:
      properties:
        txHash:
          type: string
        sequenceNumber:
          type: string
        valueWithDecimals:
          type: string
        coin:
          $ref: '#/components/schemas/AptosCoin'
        address:
          type: string
        value:
          type: string
      required:
        - txHash
        - sequenceNumber
        - valueWithDecimals
        - coin
        - address
        - value
      type: object
    AptosTransaction:
      properties:
        gasUnitPrice:
          type: string
        type:
          type: string
        gasUsed:
          type: string
        eventChangeHash:
          type: string
        stateChangeHash:
          type: string
        gasLimit:
          type: string
        sender:
          type: string
        success:
          type: boolean
        hash:
          type: string
      required:
        - gasUnitPrice
        - type
        - gasUsed
        - eventChangeHash
        - stateChangeHash
        - gasLimit
        - sender
        - success
        - hash
      type: object
    TriggerOutput:
      properties:
        value: {}
        name:
          type: string
      required:
        - value
        - name
      type: object
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AptosCoin:
      properties:
        symbol:
          type: string
        decimals:
          type: number
          format: double
        name:
          type: string
      required:
        - symbol
        - decimals
        - name
      type: object
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Replay History



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml POST /history/replay/{streamId}/{id}
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /history/replay/{streamId}/{id}:
    post:
      tags:
        - History
      summary: Replay history
      description: Replay a specific history.
      operationId: ReplayHistory
      parameters:
        - description: The id of the stream the history will be replayed
          in: path
          name: streamId
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
        - description: The id of the history to replay
          in: path
          name: id
          required: true
          schema:
            $ref: '#/components/schemas/UUID'
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HistoryModel'
      security:
        - x-api-key: []
components:
  schemas:
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
    HistoryModel:
      properties:
        id:
          $ref: '#/components/schemas/UUID'
        date:
          type: string
          format: date-time
        payload:
          anyOf:
            - $ref: '#/components/schemas/IWebhookUnParsed'
            - $ref: '#/components/schemas/AptosWebhook'
        tinyPayload:
          $ref: '#/components/schemas/ITinyPayload'
        errorMessage:
          type: string
        webhookUrl:
          type: string
        streamId:
          type: string
        tag:
          type: string
      required:
        - id
        - date
        - tinyPayload
        - errorMessage
        - webhookUrl
        - streamId
      type: object
      additionalProperties: false
    IWebhookUnParsed:
      properties:
        block:
          $ref: '#/components/schemas/Block'
        chainId:
          type: string
        logs:
          items:
            $ref: '#/components/schemas/Log'
          type: array
        txs:
          items:
            $ref: '#/components/schemas/Transaction'
          type: array
        txsInternal:
          items:
            $ref: '#/components/schemas/InternalTransaction'
          type: array
        abi:
          items:
            $ref: '#/components/schemas/AbiItem'
          type: array
        retries:
          type: number
          format: double
        confirmed:
          type: boolean
        tag:
          type: string
        streamId:
          type: string
      required:
        - block
        - chainId
        - logs
        - txs
        - txsInternal
        - abi
        - retries
        - confirmed
        - tag
        - streamId
      type: object
      additionalProperties: false
    AptosWebhook:
      properties:
        block:
          $ref: '#/components/schemas/AptosBlock'
        changes:
          items:
            properties:
              txHash:
                type: string
            additionalProperties: {}
            required:
              - txHash
            type: object
          type: array
        coinDeposits:
          items:
            $ref: '#/components/schemas/AptosCoinDeposit'
          type: array
        coinTransfers:
          items:
            $ref: '#/components/schemas/AptosCoinTransfer'
          type: array
        coinWithdrawals:
          items:
            $ref: '#/components/schemas/AptosCoinWithdrawal'
          type: array
        events:
          items:
            properties:
              txHash:
                type: string
            additionalProperties: {}
            required:
              - txHash
            type: object
          type: array
        network:
          type: string
          enum:
            - mainnet
            - testnet
        payloads:
          items:
            properties:
              txHash:
                type: string
            additionalProperties: {}
            required:
              - txHash
            type: object
          type: array
        retries:
          type: number
          format: double
        streamId:
          type: string
        tag:
          type: string
        transactions:
          items:
            $ref: '#/components/schemas/AptosTransaction'
          type: array
      required:
        - block
        - changes
        - coinDeposits
        - coinTransfers
        - coinWithdrawals
        - events
        - network
        - payloads
        - retries
        - streamId
        - tag
        - transactions
      type: object
      additionalProperties: false
    ITinyPayload:
      properties:
        chainId:
          type: string
        confirmed:
          type: boolean
        block:
          type: string
        records:
          type: number
          format: double
        retries:
          type: number
          format: double
      required:
        - chainId
        - confirmed
        - block
        - records
        - retries
      type: object
      additionalProperties: false
    Block:
      properties:
        number:
          type: string
        hash:
          type: string
        timestamp:
          type: string
      required:
        - number
        - hash
        - timestamp
      type: object
      additionalProperties: false
    Log:
      properties:
        triggers:
          items:
            $ref: '#/components/schemas/TriggerOutput'
          type: array
        logIndex:
          type: string
        transactionHash:
          type: string
        address:
          type: string
        data:
          type: string
        topic0:
          type: string
          nullable: true
        topic1:
          type: string
          nullable: true
        topic2:
          type: string
          nullable: true
        topic3:
          type: string
          nullable: true
        triggered_by:
          items:
            type: string
          type: array
          nullable: true
      required:
        - logIndex
        - transactionHash
        - address
        - data
        - topic0
        - topic1
        - topic2
        - topic3
      type: object
      additionalProperties: false
    Transaction:
      properties:
        triggers:
          items:
            $ref: '#/components/schemas/TriggerOutput'
          type: array
        hash:
          type: string
        gas:
          type: string
          nullable: true
        gasPrice:
          type: string
          nullable: true
        nonce:
          type: string
          nullable: true
        input:
          type: string
          nullable: true
        transactionIndex:
          type: string
        fromAddress:
          type: string
        toAddress:
          type: string
          nullable: true
        value:
          type: string
          nullable: true
        type:
          type: string
          nullable: true
        v:
          type: string
          nullable: true
        r:
          type: string
          nullable: true
        s:
          type: string
          nullable: true
        receiptCumulativeGasUsed:
          type: string
          nullable: true
        receiptGasUsed:
          type: string
          nullable: true
        receiptContractAddress:
          type: string
          nullable: true
        receiptRoot:
          type: string
          nullable: true
        receiptStatus:
          type: string
          nullable: true
        triggered_by:
          items:
            type: string
          type: array
          nullable: true
      required:
        - hash
        - gas
        - gasPrice
        - nonce
        - input
        - transactionIndex
        - fromAddress
        - toAddress
        - value
        - type
        - v
        - r
        - s
        - receiptCumulativeGasUsed
        - receiptGasUsed
        - receiptContractAddress
        - receiptRoot
        - receiptStatus
      type: object
      additionalProperties: false
    InternalTransaction:
      properties:
        from:
          type: string
          nullable: true
        to:
          type: string
          nullable: true
        value:
          type: string
          nullable: true
        transactionHash:
          type: string
        gas:
          type: string
          nullable: true
        triggered_by:
          items:
            type: string
          type: array
          nullable: true
      required:
        - from
        - to
        - value
        - transactionHash
        - gas
      type: object
      additionalProperties: false
    AbiItem:
      description: The abi to parse the log object of the contract
      properties:
        anonymous:
          type: boolean
        constant:
          type: boolean
        inputs:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        name:
          type: string
        outputs:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        payable:
          type: boolean
        stateMutability:
          type: string
        type:
          type: string
        gas:
          type: number
          format: double
      required:
        - type
      type: object
      additionalProperties: false
      example: {}
    AptosBlock:
      properties:
        lastVersion:
          type: string
        firstVersion:
          type: string
        hash:
          type: string
        timestamp:
          type: string
        number:
          type: string
      required:
        - lastVersion
        - firstVersion
        - hash
        - timestamp
        - number
      type: object
    AptosCoinDeposit:
      properties:
        txHash:
          type: string
        sequenceNumber:
          type: string
        valueWithDecimals:
          type: string
        coin:
          $ref: '#/components/schemas/AptosCoin'
        address:
          type: string
        value:
          type: string
      required:
        - txHash
        - sequenceNumber
        - valueWithDecimals
        - coin
        - address
        - value
      type: object
    AptosCoinTransfer:
      properties:
        txHash:
          type: string
        transaction:
          type: string
        valueWithDecimals:
          type: number
          format: double
        from:
          type: string
        value:
          type: string
        to:
          type: string
        coin:
          $ref: '#/components/schemas/AptosCoin'
      required:
        - txHash
        - transaction
        - valueWithDecimals
        - from
        - value
        - to
        - coin
      type: object
    AptosCoinWithdrawal:
      properties:
        txHash:
          type: string
        sequenceNumber:
          type: string
        valueWithDecimals:
          type: string
        coin:
          $ref: '#/components/schemas/AptosCoin'
        address:
          type: string
        value:
          type: string
      required:
        - txHash
        - sequenceNumber
        - valueWithDecimals
        - coin
        - address
        - value
      type: object
    AptosTransaction:
      properties:
        gasUnitPrice:
          type: string
        type:
          type: string
        gasUsed:
          type: string
        eventChangeHash:
          type: string
        stateChangeHash:
          type: string
        gasLimit:
          type: string
        sender:
          type: string
        success:
          type: boolean
        hash:
          type: string
      required:
        - gasUnitPrice
        - type
        - gasUsed
        - eventChangeHash
        - stateChangeHash
        - gasLimit
        - sender
        - success
        - hash
      type: object
    TriggerOutput:
      properties:
        value: {}
        name:
          type: string
      required:
        - value
        - name
      type: object
    AbiInput:
      properties:
        name:
          type: string
        type:
          type: string
        indexed:
          type: boolean
        components:
          items:
            $ref: '#/components/schemas/AbiInput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AbiOutput:
      properties:
        name:
          type: string
        type:
          type: string
        components:
          items:
            $ref: '#/components/schemas/AbiOutput'
          type: array
        internalType:
          type: string
      required:
        - name
        - type
      type: object
      additionalProperties: false
    AptosCoin:
      properties:
        symbol:
          type: string
        decimals:
          type: number
          format: double
        name:
          type: string
      required:
        - symbol
        - decimals
        - name
      type: object
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Logs



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /history/logs
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /history/logs:
    get:
      tags:
        - History
      summary: Get logs
      description: Get All logs.
      operationId: GetLogs
      parameters:
        - in: query
          name: limit
          required: true
          schema:
            type: number
            format: double
        - in: query
          name: cursor
          required: false
          schema:
            type: string
        - in: query
          name: streamId
          required: false
          schema:
            type: string
        - in: query
          name: transactionHash
          required: false
          schema:
            type: string
        - in: query
          name: deliveryStatus
          required: false
          schema:
            items:
              type: string
            type: array
        - in: query
          name: chainId
          required: false
          schema:
            items:
              type: string
            type: array
        - in: query
          name: blockNumber
          required: false
          schema:
            type: array
            items:
              type: number
              format: double
        - in: query
          name: fromTimestamp
          required: false
          schema:
            type: number
            format: double
        - in: query
          name: toTimestamp
          required: false
          schema:
            type: number
            format: double
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/IWebhookDeliveryLogsResponse'
      security:
        - x-api-key: []
components:
  schemas:
    IWebhookDeliveryLogsResponse:
      properties:
        result:
          items:
            $ref: '#/components/schemas/IWebhookDeliveryLogsModel'
          type: array
        cursor:
          type: string
        total:
          type: number
          format: double
      required:
        - result
        - total
      type: object
      additionalProperties: false
    IWebhookDeliveryLogsModel:
      properties:
        id:
          $ref: '#/components/schemas/UUID'
        streamId:
          type: string
        chain:
          type: string
        webhookUrl:
          type: string
        tag:
          type: string
        retries:
          type: number
          format: double
        deliveryStatus:
          type: string
          enum:
            - failed
            - success
        blockNumber:
          type: number
          format: double
        errorMessage:
          type: string
        type:
          type: string
          enum:
            - evm
            - aptos
        createdAt:
          type: string
          format: date-time
      required:
        - id
        - streamId
        - chain
        - webhookUrl
        - retries
        - deliveryStatus
        - blockNumber
        - errorMessage
        - type
        - createdAt
      type: object
      additionalProperties: false
    UUID:
      type: string
      format: uuid
      description: |-
        Stringified UUIDv4.
        See [RFC 4112](https://tools.ietf.org/html/rfc4122)
      pattern: >-
        [0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Project Settings



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /settings
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /settings:
    get:
      tags:
        - Project
      summary: Get project settings
      description: Get the settings for the current project based on the project api-key.
      operationId: GetSettings
      parameters: []
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SettingsModel'
      security:
        - x-api-key: []
components:
  schemas:
    SettingsModel:
      properties:
        region:
          $ref: '#/components/schemas/SettingsRegion'
          description: >-
            The region from where all the webhooks will be posted for this
            project
        secretKey:
          type: string
          description: The secret key to validate the webhooks
      type: object
      additionalProperties: false
    SettingsRegion:
      enum:
        - us-east-1
        - us-west-2
        - eu-central-1
        - ap-southeast-1
      type: string
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Set Project Settings



## OpenAPI

````yaml /openapi-files/streams-api/streams.json POST /settings
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /settings:
    post:
      tags:
        - Project
      summary: Set project settings
      description: Set the settings for the current project based on the project api-key.
      operationId: SetSettings
      parameters: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SettingsModel'
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SettingsModel'
      security:
        - x-api-key: []
components:
  schemas:
    SettingsModel:
      properties:
        region:
          $ref: '#/components/schemas/SettingsRegion'
          description: >-
            The region from where all the webhooks will be posted for this
            project
        secretKey:
          type: string
          description: The secret key to validate the webhooks
      type: object
      additionalProperties: false
    SettingsRegion:
      enum:
        - us-east-1
        - us-west-2
        - eu-central-1
        - ap-southeast-1
      type: string
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Stats



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /stats
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /stats:
    get:
      tags:
        - Stats
      summary: Get project stats
      description: Get the global stats for the account.
      operationId: GetStats
      parameters: []
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UsageStatsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UsageStatsModel:
      properties:
        totalWebhooksDelivered:
          type: number
          format: double
          description: The total amount of webhooks delivered across all streams
        totalWebhooksFailed:
          type: number
          format: double
          description: The total amount of failed webhooks across all streams
        totalLogsProcessed:
          type: number
          format: double
          description: >-
            The total amount of logs processed across all streams, this includes
            failed webhooks
        totalTxsProcessed:
          type: number
          format: double
          description: >-
            The total amount of txs processed across all streams, this includes
            failed webhooks
        totalTxsInternalProcessed:
          type: number
          format: double
          description: >-
            The total amount of internal txs processed across all streams, this
            includes failed webhooks
        streams:
          items:
            $ref: '#/components/schemas/UsageStatsStreams'
          type: array
          description: Array of stream stats
        createdAt:
          type: string
          format: date-time
          description: The date since this stats are being counted
        updatedAt:
          type: string
          format: date-time
          description: The date since this stats were last updated
      required:
        - totalWebhooksDelivered
        - totalWebhooksFailed
        - totalLogsProcessed
        - totalTxsProcessed
        - totalTxsInternalProcessed
      type: object
      additionalProperties: false
    UsageStatsStreams:
      properties:
        totalWebhooksDelivered:
          type: number
          format: double
          description: The total amount of webhooks delivered across all streams
        totalWebhooksFailed:
          type: number
          format: double
          description: The total amount of failed webhooks across all streams
        totalLogsProcessed:
          type: number
          format: double
          description: >-
            The total amount of logs processed across all streams, this includes
            failed webhooks
        totalTxsProcessed:
          type: number
          format: double
          description: >-
            The total amount of txs processed across all streams, this includes
            failed webhooks
        totalTxsInternalProcessed:
          type: number
          format: double
          description: >-
            The total amount of internal txs processed across all streams, this
            includes failed webhooks
        streamId:
          type: string
          description: The stream id
      required:
        - totalWebhooksDelivered
        - totalWebhooksFailed
        - totalLogsProcessed
        - totalTxsProcessed
        - totalTxsInternalProcessed
        - streamId
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Stats



## OpenAPI

````yaml /openapi-files/streams-api/streams.yaml GET /stats
openapi: 3.0.0
info:
  title: Streams Api
  version: 1.0.0
  description: API that provides access to Moralis Streams
  contact: {}
servers:
  - url: https://api.moralis-streams.com
security: []
paths:
  /stats:
    get:
      tags:
        - Stats
      summary: Get project stats
      description: Get the global stats for the account.
      operationId: GetStats
      parameters: []
      responses:
        '200':
          description: Ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UsageStatsModel'
      security:
        - x-api-key: []
components:
  schemas:
    UsageStatsModel:
      properties:
        totalWebhooksDelivered:
          type: number
          format: double
          description: The total amount of webhooks delivered across all streams
        totalWebhooksFailed:
          type: number
          format: double
          description: The total amount of failed webhooks across all streams
        totalLogsProcessed:
          type: number
          format: double
          description: >-
            The total amount of logs processed across all streams, this includes
            failed webhooks
        totalTxsProcessed:
          type: number
          format: double
          description: >-
            The total amount of txs processed across all streams, this includes
            failed webhooks
        totalTxsInternalProcessed:
          type: number
          format: double
          description: >-
            The total amount of internal txs processed across all streams, this
            includes failed webhooks
        streams:
          items:
            $ref: '#/components/schemas/UsageStatsStreams'
          type: array
          description: Array of stream stats
        createdAt:
          type: string
          format: date-time
          description: The date since this stats are being counted
        updatedAt:
          type: string
          format: date-time
          description: The date since this stats were last updated
      required:
        - totalWebhooksDelivered
        - totalWebhooksFailed
        - totalLogsProcessed
        - totalTxsProcessed
        - totalTxsInternalProcessed
      type: object
      additionalProperties: false
    UsageStatsStreams:
      properties:
        totalWebhooksDelivered:
          type: number
          format: double
          description: The total amount of webhooks delivered across all streams
        totalWebhooksFailed:
          type: number
          format: double
          description: The total amount of failed webhooks across all streams
        totalLogsProcessed:
          type: number
          format: double
          description: >-
            The total amount of logs processed across all streams, this includes
            failed webhooks
        totalTxsProcessed:
          type: number
          format: double
          description: >-
            The total amount of txs processed across all streams, this includes
            failed webhooks
        totalTxsInternalProcessed:
          type: number
          format: double
          description: >-
            The total amount of internal txs processed across all streams, this
            includes failed webhooks
        streamId:
          type: string
          description: The stream id
      required:
        - totalWebhooksDelivered
        - totalWebhooksFailed
        - totalLogsProcessed
        - totalTxsProcessed
        - totalTxsInternalProcessed
        - streamId
      type: object
      additionalProperties: false
  securitySchemes:
    x-api-key:
      type: apiKey
      name: x-api-key
      in: header

````

Built with [Mintlify](https://mintlify.com).
