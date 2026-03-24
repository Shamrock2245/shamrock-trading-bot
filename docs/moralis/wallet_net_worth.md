# Moralis Wallet Net Worth API
<!-- Paste the Wallet Net Worth endpoint documentation here -->
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Net Worth

export const CUs_0 = 250

export const unit_0 = "chain"

<Warning>
  **Dynamic endpoint cost:** {CUs_0} CUs per {unit_0}. The total cost scales based on the number of {unit_0}s included in the request. [Learn more about dynamic endpoints](/get-started/pricing#dynamic-endpoints).
</Warning>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/net-worth
openapi: 3.0.0
info:
  title: EVM API
  version: '2.2'
servers:
  - url: https://deep-index.moralis.io/api/v2.2
security:
  - ApiKeyAuth: []
tags: []
paths:
  /wallets/{address}/net-worth:
    get:
      tags:
        - Wallets
      summary: Get wallet net worth
      description: >-
        Calculate the total net worth of a wallet in USD, with options to
        exclude spam tokens for accuracy. Options to query cross-chain using the
        `chains` parameter, as well as additional options to exclude spam
        tokens, low-liquidity tokens and inactive tokens.
      operationId: getWalletNetWorth
      parameters:
        - in: query
          name: chains
          description: The chains to query
          required: false
          schema:
            type: array
            items:
              $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The wallet address
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: exclude_spam
          description: Exclude spam tokens from the result
          required: false
          schema:
            type: boolean
            default: false
            example: true
        - in: query
          name: exclude_unverified_contracts
          description: Exclude unverified contracts from the result
          required: false
          schema:
            type: boolean
            default: false
            example: true
        - in: query
          name: max_token_inactivity
          description: Exclude tokens inactive for more than the given amount of days
          required: false
          schema:
            type: number
            example: 1
        - in: query
          name: min_pair_side_liquidity_usd
          description: >-
            Exclude tokens with liquidity less than the specified amount in USD.
            This parameter refers to the liquidity on a single side of the pair.
          required: false
          schema:
            type: number
            example: 1000
      responses:
        '200':
          description: Returns the net worth of a wallet in USD
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/netWorthResult'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainList:
      type: string
      example: eth
      default: eth
      enum:
        - eth
        - '0x1'
        - sepolia
        - '0xaa36a7'
        - polygon
        - '0x89'
        - bsc
        - '0x38'
        - bsc testnet
        - '0x61'
        - avalanche
        - '0xa86a'
        - fantom
        - '0xfa'
        - cronos
        - '0x19'
        - arbitrum
        - '0xa4b1'
        - chiliz
        - '0x15b38'
        - chiliz testnet
        - '0x15b32'
        - gnosis
        - '0x64'
        - gnosis testnet
        - '0x27d8'
        - base
        - '0x2105'
        - base sepolia
        - '0x14a34'
        - optimism
        - '0xa'
        - polygon amoy
        - '0x13882'
        - linea
        - '0xe708'
        - moonbeam
        - '0x504'
        - moonriver
        - '0x505'
        - moonbase
        - '0x507'
        - linea sepolia
        - '0xe705'
        - flow
        - '0x2eb'
        - flow-testnet
        - '0x221'
        - ronin
        - '0x7e4'
        - ronin-testnet
        - '0x7e5'
        - lisk
        - '0x46f'
        - lisk-sepolia
        - '0x106a'
        - pulse
        - '0x171'
        - sei-testnet
        - '0x530'
        - sei
        - '0x531'
        - monad
        - '0x8f'
    netWorthResult:
      required:
        - total_networth_usd
        - chains
      properties:
        total_networth_usd:
          type: string
          description: The total networth in USD
          example: '3879851.41'
        chains:
          type: array
          items:
            $ref: '#/components/schemas/chainNetWorth'
        unsupported_chain_ids:
          type: array
          items:
            type: string
          description: The chain ids that are not supported
        unavailable_chains:
          type: array
          items:
            $ref: '#/components/schemas/unavailableChainNetWorth'
          description: The chains that are not available during the request
    chainNetWorth:
      required:
        - chain
        - native_balance
        - native_balance_formatted
        - native_balance_usd
        - token_balance_usd
        - networth_usd
      properties:
        chain:
          type: string
          description: The chain
          example: eth
        native_balance:
          type: string
          description: The native balance
          example: '1085513807021271641379'
        native_balance_formatted:
          type: string
          description: The native balance formatted
          example: '1085.513807021271641379'
        native_balance_usd:
          type: string
          description: The native balance in USD
          example: '3158392.48'
        token_balance_usd:
          type: string
          description: The token balance in USD
          example: '721458.93'
        networth_usd:
          type: string
          description: The networth in USD
          example: '3879851.41'
    unavailableChainNetWorth:
      required:
        - chain_id
      properties:
        chain_id:
          type: string
          description: The chain id
          example: '0x1'
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).

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

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Transactions (Raw)

export const CUs_0 = 30

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}
openapi: 3.0.0
info:
  title: EVM API
  version: '2.2'
servers:
  - url: https://deep-index.moralis.io/api/v2.2
security:
  - ApiKeyAuth: []
tags: []
paths:
  /{address}:
    get:
      tags:
        - Transaction
      summary: Get native transactions by wallet
      description: Get raw native transactions ordered by block number in descending order.
      operationId: getWalletTransactions
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: from_block
          description: >
            The minimum block number from which to get the transactions

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: to_block
          description: |
            The maximum block number from which to get the transactions.
            * Provide the param 'to_block' or 'to_date'
            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: from_date
          description: >
            The start date from which to get the transactions (format in seconds
            or datestring accepted by momentjs)

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: to_date
          description: >
            Get the transactions up to this date (format in seconds or
            datestring accepted by momentjs)

            * Provide the param 'to_block' or 'to_date'

            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          schema:
            type: string
        - in: path
          name: address
          description: The address of the wallet
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: include
          description: If the result should contain the internal transactions.
          required: false
          schema:
            $ref: '#/components/schemas/includeList'
      responses:
        '200':
          description: Returns a collection of native transactions.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/transactionCollection'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainList:
      type: string
      example: eth
      default: eth
      enum:
        - eth
        - '0x1'
        - sepolia
        - '0xaa36a7'
        - polygon
        - '0x89'
        - bsc
        - '0x38'
        - bsc testnet
        - '0x61'
        - avalanche
        - '0xa86a'
        - fantom
        - '0xfa'
        - cronos
        - '0x19'
        - arbitrum
        - '0xa4b1'
        - chiliz
        - '0x15b38'
        - chiliz testnet
        - '0x15b32'
        - gnosis
        - '0x64'
        - gnosis testnet
        - '0x27d8'
        - base
        - '0x2105'
        - base sepolia
        - '0x14a34'
        - optimism
        - '0xa'
        - polygon amoy
        - '0x13882'
        - linea
        - '0xe708'
        - moonbeam
        - '0x504'
        - moonriver
        - '0x505'
        - moonbase
        - '0x507'
        - linea sepolia
        - '0xe705'
        - flow
        - '0x2eb'
        - flow-testnet
        - '0x221'
        - ronin
        - '0x7e4'
        - ronin-testnet
        - '0x7e5'
        - lisk
        - '0x46f'
        - lisk-sepolia
        - '0x106a'
        - pulse
        - '0x171'
        - sei-testnet
        - '0x530'
        - sei
        - '0x531'
        - monad
        - '0x8f'
    orderList:
      type: string
      example: DESC
      default: DESC
      enum:
        - ASC
        - DESC
    includeList:
      type: string
      example: ''
      default: ''
      enum:
        - internal_transactions
    transactionCollection:
      required:
        - result
      properties:
        cursor:
          type: string
          description: The cursor to get to the next page
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        result:
          type: array
          items:
            $ref: '#/components/schemas/transaction'
    transaction:
      required:
        - hash
        - nonce
        - transaction_index
        - from_address
        - value
        - gas
        - gas_price
        - input
        - receipt_cumulative_gas_used
        - receipt_gas_used
        - receipt_contract_address
        - receipt_root
        - receipt_status
        - block_timestamp
        - block_number
        - block_hash
      properties:
        hash:
          type: string
          description: The hash of the transaction
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        nonce:
          type: string
          description: The nonce of the transaction
          example: 326595425
        transaction_index:
          type: string
          description: The transaction index
          example: 25
        from_address_entity:
          type: string
          description: The from address entity
          example: Opensea
        from_address_entity_logo:
          type: string
          description: The logo of the from address entity
          example: https://opensea.io/favicon.ico
        from_address:
          type: string
          description: The sender
          example: '0xd4a3BebD824189481FC45363602b83C9c7e9cbDf'
        from_address_label:
          type: string
          nullable: true
          description: The label of the from address
          example: Binance 1
        to_address_entity:
          type: string
          description: The to address entity
          example: Beaver Build
        to_address_entity_logo:
          type: string
          description: The logo of the to address entity
          example: https://beaverbuild.com/favicon.ico
        to_address:
          type: string
          description: The recipient
          example: '0xa71db868318f0a0bae9411347cd4a6fa23d8d4ef'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
        value:
          type: string
          description: The value that was transferred (in wei)
          example: 650000000000000000
        gas:
          type: string
          description: The gas of the transaction
          example: 6721975
        gas_price:
          type: string
          description: The gas price
          example: 20000000000
        input:
          type: string
          description: The input
        receipt_cumulative_gas_used:
          type: string
          description: The receipt cumulative gas used
          example: 1340925
        receipt_gas_used:
          type: string
          description: The receipt gas used
          example: 1340925
        receipt_contract_address:
          type: string
          description: The receipt contract address
          example: '0x1d6a4cf64b52f6c73f201839aded7379ce58059c'
        receipt_root:
          type: string
          description: The receipt root
        receipt_status:
          type: string
          description: The receipt status
          example: 1
        transaction_fee:
          type: string
          description: The transaction fee
          example: '0.00034'
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2021-04-02T10:07:54.000Z'
        block_number:
          type: string
          description: The block number
          example: 12526958
        block_hash:
          type: string
          description: The block hash
          example: '0x0372c302e3c52e8f2e15d155e2c545e6d802e479236564af052759253b20fd86'
        internal_transactions:
          type: array
          description: The internal transaction
          items:
            $ref: '#/components/schemas/internalTransaction'
    internalTransaction:
      type: object
      required:
        - transaction_hash
        - block_number
        - block_hash
        - type
        - from
        - to
        - value
        - gas
        - gas_used
        - input
        - output
        - error
      properties:
        transaction_hash:
          type: string
          description: The hash of the transaction
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        block_number:
          type: string
          description: The block number
          example: 12526958
        block_hash:
          type: string
          description: The block hash
          example: '0x0372c302e3c52e8f2e15d155e2c545e6d802e479236564af052759253b20fd86'
        type:
          type: string
          description: Call type
          example: CALL
        from:
          type: string
          description: The sender
          example: '0xd4a3BebD824189481FC45363602b83C9c7e9cbDf'
        to:
          type: string
          description: The recipient
          example: '0xa71db868318f0a0bae9411347cd4a6fa23d8d4ef'
        value:
          type: string
          description: The value that was transfered (in wei)
          example: '650000000000000000'
        gas:
          type: string
          description: The gas of the transaction
          example: '6721975'
        gas_used:
          type: string
          description: The used gas
          example: '6721975'
        input:
          type: string
          description: The input
          example: 0x
        output:
          type: string
          description: The output
          example: 0x
        error:
          type: string
          nullable: true
          description: Error message if the internal transaction failed
          example: Execution reverted
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Transactions (Decoded)

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/verbose
openapi: 3.0.0
info:
  title: EVM API
  version: '2.2'
servers:
  - url: https://deep-index.moralis.io/api/v2.2
security:
  - ApiKeyAuth: []
tags: []
paths:
  /{address}/verbose:
    get:
      tags:
        - Transaction
      summary: Get decoded transactions by wallet
      description: >-
        Get ABI-decoded native transactions ordered by block number in
        descending order.
      operationId: getWalletTransactionsVerbose
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: from_block
          description: >
            The minimum block number from which to get the transactions

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: to_block
          description: |
            The maximum block number from which to get the transactions.
            * Provide the param 'to_block' or 'to_date'
            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: from_date
          description: >
            The start date from which to get the transactions (format in seconds
            or datestring accepted by momentjs)

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: to_date
          description: >
            Get the transactions up to this date (format in seconds or
            datestring accepted by momentjs)

            * Provide the param 'to_block' or 'to_date'

            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          schema:
            type: string
        - in: path
          name: address
          description: The address of the wallet
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: include
          description: If the result should contain the internal transactions.
          required: false
          schema:
            $ref: '#/components/schemas/includeList'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
      responses:
        '200':
          description: Returns a collection of native transactions.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/transactionCollectionVerbose'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainList:
      type: string
      example: eth
      default: eth
      enum:
        - eth
        - '0x1'
        - sepolia
        - '0xaa36a7'
        - polygon
        - '0x89'
        - bsc
        - '0x38'
        - bsc testnet
        - '0x61'
        - avalanche
        - '0xa86a'
        - fantom
        - '0xfa'
        - cronos
        - '0x19'
        - arbitrum
        - '0xa4b1'
        - chiliz
        - '0x15b38'
        - chiliz testnet
        - '0x15b32'
        - gnosis
        - '0x64'
        - gnosis testnet
        - '0x27d8'
        - base
        - '0x2105'
        - base sepolia
        - '0x14a34'
        - optimism
        - '0xa'
        - polygon amoy
        - '0x13882'
        - linea
        - '0xe708'
        - moonbeam
        - '0x504'
        - moonriver
        - '0x505'
        - moonbase
        - '0x507'
        - linea sepolia
        - '0xe705'
        - flow
        - '0x2eb'
        - flow-testnet
        - '0x221'
        - ronin
        - '0x7e4'
        - ronin-testnet
        - '0x7e5'
        - lisk
        - '0x46f'
        - lisk-sepolia
        - '0x106a'
        - pulse
        - '0x171'
        - sei-testnet
        - '0x530'
        - sei
        - '0x531'
        - monad
        - '0x8f'
    includeList:
      type: string
      example: ''
      default: ''
      enum:
        - internal_transactions
    orderList:
      type: string
      example: DESC
      default: DESC
      enum:
        - ASC
        - DESC
    transactionCollectionVerbose:
      required:
        - result
      properties:
        cursor:
          type: string
          description: The cursor to get to the next page
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        result:
          type: array
          items:
            $ref: '#/components/schemas/blockTransactionVerbose'
    blockTransactionVerbose:
      type: object
      required:
        - hash
        - nonce
        - transaction_index
        - from_address
        - value
        - gas_price
        - input
        - receipt_cumulative_gas_used
        - receipt_gas_used
        - receipt_status
        - transaction_fee
        - block_timestamp
        - block_number
        - block_hash
        - logs
        - decoded_call
      properties:
        hash:
          type: string
          description: The hash of the transaction
          example: '0x1ed85b3757a6d31d01a4d6677fc52fd3911d649a0af21fe5ca3f886b153773ed'
        nonce:
          type: string
          description: The nonce
          example: '1848059'
        transaction_index:
          type: string
          example: '108'
        from_address_entity:
          type: string
          description: The from address entity
          example: Opensea
        from_address_entity_logo:
          type: string
          description: The logo of the from address entity
          example: https://opensea.io/favicon.ico
        from_address:
          type: string
          description: The from address
          example: '0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0'
        from_address_label:
          type: string
          nullable: true
          description: The label of the from address
          example: Binance 1
        to_address_entity:
          type: string
          description: The to address entity
          example: Beaver Build
        to_address_entity_logo:
          type: string
          description: The logo of the to address entity
          example: https://beaverbuild.com/favicon.ico
        to_address:
          type: string
          description: The to address
          example: '0x003dde3494f30d861d063232c6a8c04394b686ff'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
        value:
          type: string
          description: The value sent
          example: '115580000000000000'
        gas:
          type: string
          example: '30000'
        gas_price:
          type: string
          description: The gas price
          example: '52500000000'
        input:
          type: string
          example: 0x
        receipt_cumulative_gas_used:
          type: string
          example: '4923073'
        receipt_gas_used:
          type: string
          example: '21000'
        receipt_contract_address:
          type: string
          example: null
        receipt_root:
          type: string
          example: null
        receipt_status:
          type: string
          example: '1'
        transaction_fee:
          type: string
          example: '0.00034'
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2021-05-07T11:08:35.000Z'
        block_number:
          type: string
          description: The block number
          example: '12386788'
        block_hash:
          type: string
          description: The hash of the block
          example: '0x9b559aef7ea858608c2e554246fe4a24287e7aeeb976848df2b9a2531f4b9171'
        logs:
          type: array
          description: The logs of the transaction
          items:
            $ref: '#/components/schemas/logVerbose'
        decoded_call:
          $ref: '#/components/schemas/decodedCall'
          type: object
          description: The decoded data of the transaction
    logVerbose:
      required:
        - log_index
        - transaction_hash
        - transaction_index
        - address
        - data
        - topic0
        - block_timestamp
        - block_number
        - block_hash
        - decoded_event
      properties:
        log_index:
          type: string
          example: '273'
        transaction_hash:
          type: string
          description: The hash of the transaction
          example: '0xdd9006489e46670e0e85d1fb88823099e7f596b08aeaac023e9da0851f26fdd5'
        transaction_index:
          type: string
          example: '204'
        address:
          type: string
          description: The address of the contract
          example: '0x3105d328c66d8d55092358cf595d54608178e9b5'
        data:
          type: string
          description: The data of the log
          example: >-
            0x00000000000000000000000000000000000000000000000de05239bccd4d537400000000000000000000000000024dbc80a9f80e3d5fc0a0ee30e2693781a443
        topic0:
          type: string
          example: '0x2caecd17d02f56fa897705dcc740da2d237c373f70686f4e0d9bd3bf0400ea7a'
        topic1:
          type: string
          example: '0x000000000000000000000000031002d15b0d0cd7c9129d6f644446368deae391'
        topic2:
          type: string
          example: '0x000000000000000000000000d25943be09f968ba740e0782a34e710100defae9'
        topic3:
          type: string
          example: null
        block_timestamp:
          type: string
          description: The timestamp of the block
          example: '2021-05-07T11:08:35.000Z'
        block_number:
          type: string
          description: The block number
          example: '12386788'
        block_hash:
          type: string
          description: The hash of the block
          example: '0x9b559aef7ea858608c2e554246fe4a24287e7aeeb976848df2b9a2531f4b9171'
        decoded_event:
          $ref: '#/components/schemas/decodedEvent'
          type: object
          description: The decoded data of the log
    decodedCall:
      type: object
      properties:
        signature:
          type: string
          example: transfer(address,uint256)
        label:
          type: string
          example: transfer
        type:
          type: string
          example: function
        params:
          type: array
          items:
            type: object
            properties:
              name:
                type: string
                example: _to
              value:
                type: string
                example: '0x1CA455A55108874A95C84620dDA2566c54D17953'
              type:
                type: string
                example: address
    decodedEvent:
      type: object
      properties:
        signature:
          type: string
          example: Transfer(address,address,uint256)
        label:
          type: string
          example: Transfer
        type:
          type: string
          example: event
        params:
          type: array
          items:
            type: object
            properties:
              name:
                type: string
                example: from
              value:
                type: string
                example: '0x26C5011483Add49801eA8E3Ee354fE013895aCe5'
              type:
                type: string
                example: address
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Stats

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/stats
openapi: 3.0.0
info:
  title: EVM API
  version: '2.2'
servers:
  - url: https://deep-index.moralis.io/api/v2.2
security:
  - ApiKeyAuth: []
tags: []
paths:
  /wallets/{address}/stats:
    get:
      tags:
        - Wallets
      summary: Get summary stats by wallet address
      description: >-
        Retrieve key statistics for a wallet, such as total transaction count
        and activity.
      operationId: getWalletStats
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: Wallet address
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
      responses:
        '200':
          description: Returns the stats for the wallet address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletStat'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainList:
      type: string
      example: eth
      default: eth
      enum:
        - eth
        - '0x1'
        - sepolia
        - '0xaa36a7'
        - polygon
        - '0x89'
        - bsc
        - '0x38'
        - bsc testnet
        - '0x61'
        - avalanche
        - '0xa86a'
        - fantom
        - '0xfa'
        - cronos
        - '0x19'
        - arbitrum
        - '0xa4b1'
        - chiliz
        - '0x15b38'
        - chiliz testnet
        - '0x15b32'
        - gnosis
        - '0x64'
        - gnosis testnet
        - '0x27d8'
        - base
        - '0x2105'
        - base sepolia
        - '0x14a34'
        - optimism
        - '0xa'
        - polygon amoy
        - '0x13882'
        - linea
        - '0xe708'
        - moonbeam
        - '0x504'
        - moonriver
        - '0x505'
        - moonbase
        - '0x507'
        - linea sepolia
        - '0xe705'
        - flow
        - '0x2eb'
        - flow-testnet
        - '0x221'
        - ronin
        - '0x7e4'
        - ronin-testnet
        - '0x7e5'
        - lisk
        - '0x46f'
        - lisk-sepolia
        - '0x106a'
        - pulse
        - '0x171'
        - sei-testnet
        - '0x530'
        - sei
        - '0x531'
        - monad
        - '0x8f'
    walletStat:
      required:
        - nfts
        - collections
        - transactions
        - nft_transfers
        - token_transfers
      properties:
        nfts:
          type: string
          description: The number of NFTs owned by a wallet
          example: '100'
        collections:
          type: string
          description: The number of unique NFT collections owned by a wallet
          example: '10'
        transactions:
          type: object
          description: Transaction stats
          required:
            - total
          properties:
            total:
              type: string
              description: The number of transactions sent by a wallet
              example: '1000'
        nft_transfers:
          type: object
          description: NFT transfer stats
          required:
            - total
          properties:
            total:
              type: string
              description: The number of NFT transfers of a wallet
              example: '1000'
        token_transfers:
          type: object
          description: Token transfer stats
          required:
            - total
          properties:
            total:
              type: string
              description: The number of ERC20 token transfers of a wallet
              example: '1000'
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Chain Activity

export const CUs_0 = 50

export const unit_0 = "chain"

<Warning>
  **Dynamic endpoint cost:** {CUs_0} CUs per {unit_0}. The total cost scales based on the number of {unit_0}s included in the request. [Learn more about dynamic endpoints](/get-started/pricing#dynamic-endpoints).
</Warning>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/chains
openapi: 3.0.0
info:
  title: EVM API
  version: '2.2'
servers:
  - url: https://deep-index.moralis.io/api/v2.2
security:
  - ApiKeyAuth: []
tags: []
paths:
  /wallets/{address}/chains:
    get:
      tags:
        - Wallets
      summary: Get active chains by wallet address
      description: >-
        List the blockchain networks a wallet is active on, including their
        first and last seen timestamps. Options to query cross-chain using the
        `chains` parameter.
      operationId: getWalletActiveChains
      parameters:
        - in: path
          name: address
          description: Wallet address
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: chains
          description: The chains to query
          required: false
          schema:
            type: array
            items:
              $ref: '#/components/schemas/chainList'
      responses:
        '200':
          description: Returns the active chains for the wallet address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletActiveChains'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainList:
      type: string
      example: eth
      default: eth
      enum:
        - eth
        - '0x1'
        - sepolia
        - '0xaa36a7'
        - polygon
        - '0x89'
        - bsc
        - '0x38'
        - bsc testnet
        - '0x61'
        - avalanche
        - '0xa86a'
        - fantom
        - '0xfa'
        - cronos
        - '0x19'
        - arbitrum
        - '0xa4b1'
        - chiliz
        - '0x15b38'
        - chiliz testnet
        - '0x15b32'
        - gnosis
        - '0x64'
        - gnosis testnet
        - '0x27d8'
        - base
        - '0x2105'
        - base sepolia
        - '0x14a34'
        - optimism
        - '0xa'
        - polygon amoy
        - '0x13882'
        - linea
        - '0xe708'
        - moonbeam
        - '0x504'
        - moonriver
        - '0x505'
        - moonbase
        - '0x507'
        - linea sepolia
        - '0xe705'
        - flow
        - '0x2eb'
        - flow-testnet
        - '0x221'
        - ronin
        - '0x7e4'
        - ronin-testnet
        - '0x7e5'
        - lisk
        - '0x46f'
        - lisk-sepolia
        - '0x106a'
        - pulse
        - '0x171'
        - sei-testnet
        - '0x530'
        - sei
        - '0x531'
        - monad
        - '0x8f'
    walletActiveChains:
      required:
        - address
        - active_chains
      properties:
        address:
          type: string
          description: The address of the wallet
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        active_chains:
          type: array
          items:
            $ref: '#/components/schemas/walletActiveChain'
    walletActiveChain:
      required:
        - chain
        - chain_id
      properties:
        chain:
          type: string
          description: The chain name
          example: eth
        chain_id:
          type: string
          description: The chain id
          example: '0x1'
        first_transaction:
          $ref: '#/components/schemas/transactionTimestamp'
        last_transaction:
          $ref: '#/components/schemas/transactionTimestamp'
    transactionTimestamp:
      required:
        - block_number
        - block_timestamp
      properties:
        block_number:
          type: string
          description: The block number
          example: '123456789'
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2022-08-23T20:58:31.000Z'
        transaction_hash:
          type: string
          description: The hash of the transaction
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).
