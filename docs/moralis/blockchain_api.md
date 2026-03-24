> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Blockchain API

> Low-level blockchain access made simple - query raw blocks, transactions, logs, and events with consistent, multi-chain APIs.

## Overview

The **Blockchain API** provides low-level access to raw blockchain data including blocks, transactions, and logs.

Query the blockchain directly without running your own nodes - get block data, transaction details, and decoded contract interactions across all supported EVM chains.

***

## What Is the Blockchain API?

The Blockchain API lets you query:

* **Blocks** - Block data by hash, number, or timestamp
* **Transactions** - Raw and decoded transaction details
* **Address Activity** - All transactions for a specific address
* **Logs** - Event logs and contract emissions
* **Internal Transactions** - Contract-to-contract calls

***

## Key Features

The Blockchain API includes:

* **Block Lookups** - Query blocks by hash or find blocks by timestamp
* **Transaction Details** - Full transaction data including gas and status
* **Decoded Transactions** - Human-readable interpretation of contract calls
* **Address History** - Complete transaction history for any address
* **Multi-Chain** - Consistent interface across all EVM chains
* **Latest Block** - Get the current block number for any chain

***

## Common Use Cases

The Blockchain API is commonly used for:

* **Block Explorers**\
  (display block and transaction data)
* **Address Monitoring**\
  (track transactions for specific wallets)
* **Historical Analysis**\
  (query blockchain state at specific times)
* **Transaction Verification**\
  (confirm transaction status and details)
* **Data Indexing**\
  (build custom indexes from raw data)
* **Debugging**\
  (inspect failed transactions and logs)

***

## Popular Endpoints

| Endpoint                                                                    | Description                         |
| --------------------------------------------------------------------------- | ----------------------------------- |
| [Get Block by Hash](/data-api/evm/blockchain/block-by-hash)                 | Retrieve block data by hash         |
| [Get Block by Date](/data-api/evm/blockchain/block-by-date)                 | Find block closest to a timestamp   |
| [Get Transaction](/data-api/evm/blockchain/transaction-by-hash)             | Get transaction details by hash     |
| [Decoded Transaction](/data-api/evm/blockchain/transaction-by-hash-decoded) | Get decoded transaction data        |
| [Address Transactions](/data-api/evm/blockchain/address-transactions)       | Get all transactions for an address |

***

## Get Started

Explore some of the popular Blockchain API endpoints:

* [Get Block by Hash](/data-api/evm/blockchain/block-by-hash)
* [Get Block by Date](/data-api/evm/blockchain/block-by-date)
* [Get Transaction](/data-api/evm/blockchain/transaction-by-hash)
* [Get Address Transactions](/data-api/evm/blockchain/address-transactions)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Block by Hash or Number

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /block/{block_number_or_hash}
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
  /block/{block_number_or_hash}:
    get:
      tags:
        - Block
      summary: Get block by hash
      description: Get the contents of a block given the block hash.
      operationId: getBlock
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: block_number_or_hash
          description: The block number or block hash
          required: true
          schema:
            type: string
            example: '15863321'
        - in: query
          name: include
          description: If the result should contain the internal transactions.
          required: false
          schema:
            $ref: '#/components/schemas/includeList'
      responses:
        '200':
          description: Returns the contents of a block
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/block'
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
    block:
      type: object
      required:
        - timestamp
        - number
        - hash
        - parent_hash
        - nonce
        - sha3_uncles
        - logs_bloom
        - transactions_root
        - state_root
        - receipts_root
        - miner
        - difficulty
        - total_difficulty
        - size
        - extra_data
        - gas_limit
        - gas_used
        - transaction_count
        - transactions
      properties:
        timestamp:
          type: string
          description: The block timestamp
          example: '2021-05-07T11:08:35.000Z'
        number:
          type: string
          description: The block number
          example: 12386788
        hash:
          type: string
          description: The block hash
          example: '0x9b559aef7ea858608c2e554246fe4a24287e7aeeb976848df2b9a2531f4b9171'
        parent_hash:
          type: string
          description: The block hash of the parent block
          example: '0x011d1fc45839de975cc55d758943f9f1d204f80a90eb631f3bf064b80d53e045'
        nonce:
          type: string
          description: The nonce
          example: '0xedeb2d8fd2b2bdec'
        sha3_uncles:
          type: string
          example: '0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347'
        logs_bloom:
          type: string
          example: >-
            0xdde5fc46c5d8bcbd58207bc9f267bf43298e23791a326ff02661e99790da9996b3e0dd912c0b8202d389d282c56e4d11eb2dec4898a32b6b165f1f4cae6aa0079498eab50293f3b8defbf6af11bb75f0408a563ddfc26a3323d1ff5f9849e95d5f034d88a757ddea032c75c00708c9ff34d2207f997cc7d93fd1fa160a6bfaf62a54e31f9fe67ab95752106ba9d185bfdc9b6dc3e17427f844ee74e5c09b17b83ad6e8fc7360f5c7c3e4e1939e77a6374bee57d1fa6b2322b11ad56ad0398302de9b26d6fbfe414aa416bff141fad9d4af6aea19322e47595e342cd377403f417dfd396ab5f151095a5535f51cbc34a40ce9648927b7d1d72ab9daf253e31daf
        transactions_root:
          type: string
          example: '0xe4c7bf3aff7ad07f9e80d57f7189f0252592fee6321c2a9bd9b09b6ce0690d27'
        state_root:
          type: string
          example: '0x49e3bfe7b618e27fde8fa08884803a8458b502c6534af69873a3cc926a7c724b'
        receipts_root:
          type: string
          example: '0x7cf43d7e837284f036cf92c56973f5e27bdd253ca46168fa195a6b07fa719f23'
        miner:
          type: string
          description: The address of the miner
          example: '0xea674fdde714fd979de3edf0f56aa9716b898ec8'
        difficulty:
          type: string
          description: The difficulty of the block
          example: '7253857437305950'
        total_difficulty:
          type: string
          description: The total difficulty
          example: '24325637817906576196890'
        size:
          type: string
          description: The block size
          example: '61271'
        extra_data:
          type: string
          example: '0x65746865726d696e652d6575726f70652d7765737433'
        gas_limit:
          type: string
          description: The gas limit
          example: '14977947'
        gas_used:
          type: string
          description: The gas used
          example: '14964688'
        transaction_count:
          type: string
          description: The number of transactions in the block
          example: '252'
        transactions:
          type: array
          description: The transactions in the block
          items:
            $ref: '#/components/schemas/blockTransaction'
    blockTransaction:
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
        - block_timestamp
        - block_number
        - block_hash
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
          nullable: true
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
          nullable: true
          example: null
        receipt_root:
          type: string
          nullable: true
          example: null
        receipt_status:
          type: string
          example: '1'
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
            $ref: '#/components/schemas/log'
        internal_transactions:
          type: array
          description: The internal transactions of the transaction
          items:
            $ref: '#/components/schemas/internalTransaction'
    log:
      type: object
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
          nullable: true
          example: '0x000000000000000000000000031002d15b0d0cd7c9129d6f644446368deae391'
        topic2:
          type: string
          nullable: true
          example: '0x000000000000000000000000d25943be09f968ba740e0782a34e710100defae9'
        topic3:
          type: string
          nullable: true
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

# Block by Date

export const CUs_0 = 1

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /dateToBlock
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
  /dateToBlock:
    get:
      tags:
        - Block
      summary: Get block by date
      description: Find the closest block to a specific date on a blockchain.
      operationId: getDateToBlock
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: date
          description: >-
            Unix date in milliseconds or a datestring (format in seconds or
            datestring accepted by momentjs)
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Returns the block number and corresponding date and timestamp
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/blockDate'
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
    blockDate:
      type: object
      required:
        - date
        - block
        - timestamp
      properties:
        date:
          type: string
          description: The date of the block
          example: '2020-01-01T00:00:00+00:00'
        block:
          type: number
          description: The block number
          example: 9193266
        timestamp:
          type: number
          description: The timestamp of the block
          example: 1577836811
        block_timestamp:
          type: string
          description: The timestamp of the block
          example: '2019-12-31T23:59:45.000Z'
        hash:
          type: string
          description: The block hash
          example: '0x9b559aef7ea858608c2e554246fe4a24287e7aeeb976848df2b9a2531f4b9171'
        parent_hash:
          type: string
          description: The block hash of the parent block
          example: '0x011d1fc45839de975cc55d758943f9f1d204f80a90eb631f3bf064b80d53e045'
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

# Latest Block

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /latestBlockNumber/{chain}
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
  /latestBlockNumber/{chain}:
    get:
      tags:
        - Block
      summary: Get latest block number
      description: Get the most recent block number for a specified blockchain.
      operationId: getLatestBlockNumber
      parameters:
        - in: path
          name: chain
          description: The chain to query
          required: true
          schema:
            $ref: '#/components/schemas/chainList'
            example: '0x1'
      responses:
        '200':
          description: Returns the latest block number.
          content:
            application/json:
              schema:
                type: string
                example: '15863321'
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

# Get Transaction

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /transaction/{transaction_hash}
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
  /transaction/{transaction_hash}:
    get:
      tags:
        - Transaction
      summary: Get transaction by hash
      description: Get the contents of a transaction by the given transaction hash.
      operationId: getTransaction
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: transaction_hash
          description: The transaction hash
          required: true
          schema:
            type: string
            example: '0xfeda0e8f0d6e54112c28d319c0d303c065d1125c9197bd653682f5fcb0a6c81e'
        - in: query
          name: include
          description: If the result should contain the internal transactions.
          required: false
          schema:
            $ref: '#/components/schemas/includeList'
      responses:
        '200':
          description: Transaction details by transaction hash
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/blockTransaction'
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
    blockTransaction:
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
        - block_timestamp
        - block_number
        - block_hash
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
          nullable: true
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
          nullable: true
          example: null
        receipt_root:
          type: string
          nullable: true
          example: null
        receipt_status:
          type: string
          example: '1'
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
            $ref: '#/components/schemas/log'
        internal_transactions:
          type: array
          description: The internal transactions of the transaction
          items:
            $ref: '#/components/schemas/internalTransaction'
    log:
      type: object
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
          nullable: true
          example: '0x000000000000000000000000031002d15b0d0cd7c9129d6f644446368deae391'
        topic2:
          type: string
          nullable: true
          example: '0x000000000000000000000000d25943be09f968ba740e0782a34e710100defae9'
        topic3:
          type: string
          nullable: true
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

# Get Transaction (Decoded)

export const CUs_0 = 20

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /transaction/{transaction_hash}/verbose
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
  /transaction/{transaction_hash}/verbose:
    get:
      tags:
        - Transaction
      summary: Get decoded transaction by hash
      description: >-
        Get the ABI-decoded contents of a transaction by the given transaction
        hash.
      operationId: getTransactionVerbose
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: transaction_hash
          description: The transaction hash
          required: true
          schema:
            type: string
            example: '0xfeda0e8f0d6e54112c28d319c0d303c065d1125c9197bd653682f5fcb0a6c81e'
        - in: query
          name: include
          description: If the result should contain the internal transactions.
          required: false
          schema:
            $ref: '#/components/schemas/includeList'
      responses:
        '200':
          description: Transaction details by transaction hash
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/blockTransactionVerbose'
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

# Address Transactions

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

# Address Transactions (Decoded)

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