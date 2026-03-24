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

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet History

export const CUs_0 = 150

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/history
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
  /wallets/{address}/history:
    get:
      tags:
        - Wallets
      summary: Get the complete decoded transaction history of a wallet
      description: >-
        Get the complete decoded transaction history for a given wallet. All
        transactions are parsed, decoded, categorized and summarized into
        human-readable records.
      operationId: getWalletHistory
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
          name: include_internal_transactions
          description: If the result should contain the internal transactions.
          required: false
          schema:
            type: boolean
        - in: query
          name: nft_metadata
          description: If the result should contain the nft metadata.
          required: false
          schema:
            type: boolean
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
          description: Returns wallet history of a wallet address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletHistory'
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
    walletHistory:
      required:
        - result
        - page
        - page_size
        - cursor
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/walletHistoryTransaction'
    walletHistoryTransaction:
      type: object
      required:
        - hash
        - nonce
        - transaction_index
        - from_address
        - value
        - gas_price
        - receipt_cumulative_gas_used
        - receipt_gas_used
        - receipt_status
        - block_timestamp
        - block_number
        - block_hash
        - category
        - nft_transfers
        - summary
        - erc20_transfers
        - native_transfers
        - contract_interactions
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
          example: '0x9869524fd160fe3adda6218883b6526c0977d3a5'
          nullable: true
        receipt_status:
          type: string
          example: '1'
        transaction_fee:
          type: string
          example: '0.00000000000000063'
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
        internal_transactions:
          type: array
          description: The internal transactions of the transaction
          items:
            $ref: '#/components/schemas/internalTransaction'
        category:
          $ref: '#/components/schemas/ETransactionCategory'
        contract_interactions:
          $ref: '#/components/schemas/ResolveContractInteractionResponse'
          type: array
          description: The contract interactions that happend in the transaction
        possible_spam:
          type: boolean
          description: Is transaction possible spam
          example: 'false'
        method_label:
          type: string
          description: The label of the method called if any called
          example: transfer
        summary:
          type: string
          description: Summary of what happened on the transaction
          example: transfer
        nft_transfers:
          type: array
          items:
            $ref: '#/components/schemas/walletHistoryNftTransfer'
        erc20_transfers:
          type: array
          items:
            $ref: '#/components/schemas/walletHistoryErc20Transfer'
        native_transfers:
          type: array
          items:
            $ref: '#/components/schemas/native_transfer'
        logs:
          type: array
          items:
            $ref: '#/components/schemas/logVerbose'
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
    ETransactionCategory:
      type: string
      enum:
        - send
        - receive
        - token send
        - token receive
        - nft send
        - nft receive
        - token swap
        - deposit
        - withdraw
        - nft purchase
        - nft sale
        - airdrop
        - mint
        - burn
        - borrow
        - contract interaction
      description: Defines the category of the transaction.
    ResolveContractInteractionResponse:
      oneOf:
        - $ref: '#/components/schemas/ApprovalResponse'
        - $ref: '#/components/schemas/RevokeResponse'
        - $ref: '#/components/schemas/SetApprovalAllResponse'
        - $ref: '#/components/schemas/SetRevokeAllResponse'
    walletHistoryNftTransfer:
      required:
        - token_address
        - token_id
        - log_index
        - contract_type
        - possible_spam
        - value
        - amount
        - transaction_type
        - direction
        - from_address
        - verified
      properties:
        token_address:
          type: string
          description: The address of the NFT contract
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        token_id:
          type: string
          description: The token ID of the NFT
          example: '15'
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
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
          description: The address that sent the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          description: The address that received the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
        value:
          type: string
          description: The value that was sent in the transaction (ETH/BNB/etc..)
          example: '1000000000000000'
        amount:
          type: string
          description: The number of tokens transferred
          example: '1'
        contract_type:
          type: string
          description: The type of NFT contract standard
          example: ERC721
        transaction_type:
          type: string
          description: The transaction type
        log_index:
          type: integer
          description: The log index
        operator:
          type: string
          description: The operator present only for ERC1155 transfers
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_collection:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
        direction:
          type: string
          description: The direction of the transfer
          example: outgoing
        collection_logo:
          type: string
          description: The logo of the collection
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        collection_banner_image:
          type: string
          description: The banner image of the collection
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        normalized_metadata:
          $ref: '#/components/schemas/normalizedMetadata'
          description: A normalized metadata version of the NFT's metadata.
    walletHistoryErc20Transfer:
      required:
        - token_name
        - token_symbol
        - token_logo
        - token_decimals
        - value_formatted
        - address
        - from_address
        - value
        - transaction_index
        - log_index
        - possible_spam
        - verified_contract
      properties:
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
        token_logo:
          type: string
          example: https://cdn.moralis.io/images/325/large/Tether-logo.png?1598003707
        token_decimals:
          type: string
          example: '6'
        address:
          type: string
          description: The address of the token
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2021-04-02T10:07:54.000Z'
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
          example: '0x62AED87d21Ad0F3cdE4D147Fdcc9245401Af0044'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
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
        value:
          type: string
          description: The value that was transfered (in wei)
          example: 650000000000000000
        value_formatted:
          type: string
          description: The value that was transfered decimal format
          example: '1.033'
        log_index:
          type: integer
          description: The log index of the transfer within the block
          example: 2
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
    native_transfer:
      required:
        - from_address
        - value
        - value_formatted
        - internal_transaction
        - token_symbol
        - token_logo
      properties:
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
          description: The address that sent the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          description: The address that received the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
        value:
          type: string
          description: The value that was sent in the transaction (ETH/BNB/etc..)
          example: '1000000000000000'
        value_formatted:
          type: string
          description: >-
            The value that was sent in the transaction (ETH/BNB/etc..) in
            decimal format
          example: '0.1'
        direction:
          type: string
          description: The direction of the transfer
          example: outgoing
        internal_transaction:
          type: boolean
          description: Indicates if the transaction is internal
          example: 'false'
        token_symbol:
          type: string
          description: The symbol of the token transferred
          example: ETH
        token_logo:
          type: string
          description: The logo of the token transferred
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
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
    ApprovalResponse:
      type: object
      properties:
        approvals:
          type: array
          items:
            $ref: '#/components/schemas/ApprovalData'
    RevokeResponse:
      type: object
      properties:
        revokes:
          type: array
          items:
            $ref: '#/components/schemas/ApprovalData'
    SetApprovalAllResponse:
      type: object
      properties:
        set_approvals_all:
          type: array
          items:
            $ref: '#/components/schemas/SetApprovalAllData'
    SetRevokeAllResponse:
      type: object
      properties:
        set_revokes_all:
          type: array
          items:
            $ref: '#/components/schemas/SetApprovalAllData'
    normalizedMetadata:
      properties:
        name:
          type: string
          description: The name or title of the NFT
          example: Moralis Mug
        description:
          type: string
          description: A detailed description of the NFT
          example: >-
            Moralis Coffee nug 3D Asset that can be used in 3D worldspaces. This
            NFT is presented as a flat PNG, a Unity3D Prefab and a standard fbx.
        image:
          type: string
          description: The URL of the NFT's image
          example: >-
            https://arw2wxg84h6b.moralishost.com:2053/server/files/tNJatzsHirx4V2VAep6sc923OYGxvkpBeJttR7Ks/de504bbadadcbe30c86278342fcf2560_moralismug.png
        external_link:
          type: string
          description: A link to additional information
          example: https://giphy.com/gifs/loop-recursion-ting-aaODAv1iuQdgI
        external_url:
          type: string
          description: A link to additional information
          example: https://giphy.com/gifs/loop-recursion-ting-aaODAv1iuQdgI
        animation_url:
          type: string
          description: An animated version of the NFT's image
          example: https://giphy.com/gifs/food-design-donuts-o9ngTPVYW4qo8
        attributes:
          type: array
          items:
            $ref: '#/components/schemas/normalizedMetadataAttribute'
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
    ApprovalData:
      type: object
      properties:
        value:
          type: string
        value_formatted:
          type: string
          nullable: true
        token:
          $ref: '#/components/schemas/TokenDetails'
        spender:
          $ref: '#/components/schemas/SpenderDetails'
    SetApprovalAllData:
      type: object
      properties:
        token:
          $ref: '#/components/schemas/TokenDetails'
        operator:
          $ref: '#/components/schemas/SpenderDetails'
    normalizedMetadataAttribute:
      properties:
        trait_type:
          type: string
          description: The trait title or descriptor
          example: Eye Color
        value:
          type: object
          description: The value of the attribute
          example: hazel
        display_type:
          type: string
          description: The type the attribute value should be displayed as
          example: string
        max_value:
          type: number
          description: For numeric values, the upper range
          example: 100
        trait_count:
          type: number
          description: The number of possible values for this trait
          example: 7
        order:
          type: number
          description: Order the trait should appear in the attribute list.
          example: 1
    TokenDetails:
      type: object
      properties:
        address:
          type: string
        address_label:
          type: string
          nullable: true
        token_name:
          type: string
        token_logo:
          type: string
        token_symbol:
          type: string
    SpenderDetails:
      type: object
      properties:
        address:
          type: string
        address_label:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        logo:
          type: string
          nullable: true
        entity:
          type: string
          nullable: true
        entity_logo:
          type: string
          nullable: true
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

# Token Transfers

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/erc20/transfers
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
  /{address}/erc20/transfers:
    get:
      tags:
        - Token
        - Get Transactions
      summary: Get ERC20 token transfers by wallet address
      description: >-
        Get all ERC20 token transfers for a given wallet address, sorted by
        block number (newest first).
      operationId: getWalletTokenTransfers
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
          name: contract_addresses
          description: List of contract addresses of transfers
          required: false
          schema:
            type: array
            items:
              type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
      responses:
        '200':
          description: Returns a collection of token transactions.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20TransactionCollection'
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
    erc20TransactionCollection:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/erc20Transaction'
    erc20Transaction:
      required:
        - token_name
        - token_symbol
        - token_decimals
        - value_decimal
        - transaction_hash
        - address
        - block_timestamp
        - block_number
        - block_hash
        - from_address
        - value
        - transaction_index
        - log_index
        - possible_spam
        - verified_contract
      properties:
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
        token_logo:
          type: string
          example: cdn.moralis.io/325/large/Tether-logo.png?1598003707
        token_decimals:
          type: string
          example: '6'
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
        address:
          type: string
          description: The address of the token
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          example: '0x62AED87d21Ad0F3cdE4D147Fdcc9245401Af0044'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
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
        value:
          type: string
          description: The value that was transfered (in wei)
          example: 650000000000000000
        transaction_index:
          type: integer
          description: The transaction index of the transfer within the block
          example: 12
        log_index:
          type: integer
          description: The log index of the transfer within the block
          example: 2
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
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

# Token Transfers

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/erc20/transfers
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
  /{address}/erc20/transfers:
    get:
      tags:
        - Token
        - Get Transactions
      summary: Get ERC20 token transfers by wallet address
      description: >-
        Get all ERC20 token transfers for a given wallet address, sorted by
        block number (newest first).
      operationId: getWalletTokenTransfers
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
          name: contract_addresses
          description: List of contract addresses of transfers
          required: false
          schema:
            type: array
            items:
              type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
      responses:
        '200':
          description: Returns a collection of token transactions.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20TransactionCollection'
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
    erc20TransactionCollection:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/erc20Transaction'
    erc20Transaction:
      required:
        - token_name
        - token_symbol
        - token_decimals
        - value_decimal
        - transaction_hash
        - address
        - block_timestamp
        - block_number
        - block_hash
        - from_address
        - value
        - transaction_index
        - log_index
        - possible_spam
        - verified_contract
      properties:
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
        token_logo:
          type: string
          example: cdn.moralis.io/325/large/Tether-logo.png?1598003707
        token_decimals:
          type: string
          example: '6'
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
        address:
          type: string
          description: The address of the token
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          example: '0x62AED87d21Ad0F3cdE4D147Fdcc9245401Af0044'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
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
        value:
          type: string
          description: The value that was transfered (in wei)
          example: 650000000000000000
        transaction_index:
          type: integer
          description: The transaction index of the transfer within the block
          example: 12
        log_index:
          type: integer
          description: The log index of the transfer within the block
          example: 2
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
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

# Token Transfers

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/erc20/transfers
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
  /{address}/erc20/transfers:
    get:
      tags:
        - Token
        - Get Transactions
      summary: Get ERC20 token transfers by wallet address
      description: >-
        Get all ERC20 token transfers for a given wallet address, sorted by
        block number (newest first).
      operationId: getWalletTokenTransfers
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
          name: contract_addresses
          description: List of contract addresses of transfers
          required: false
          schema:
            type: array
            items:
              type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
      responses:
        '200':
          description: Returns a collection of token transactions.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20TransactionCollection'
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
    erc20TransactionCollection:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/erc20Transaction'
    erc20Transaction:
      required:
        - token_name
        - token_symbol
        - token_decimals
        - value_decimal
        - transaction_hash
        - address
        - block_timestamp
        - block_number
        - block_hash
        - from_address
        - value
        - transaction_index
        - log_index
        - possible_spam
        - verified_contract
      properties:
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
        token_logo:
          type: string
          example: cdn.moralis.io/325/large/Tether-logo.png?1598003707
        token_decimals:
          type: string
          example: '6'
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
        address:
          type: string
          description: The address of the token
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          example: '0x62AED87d21Ad0F3cdE4D147Fdcc9245401Af0044'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
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
        value:
          type: string
          description: The value that was transfered (in wei)
          example: 650000000000000000
        transaction_index:
          type: integer
          description: The transaction index of the transfer within the block
          example: 12
        log_index:
          type: integer
          description: The log index of the transfer within the block
          example: 2
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
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

# NFT Transfers

export const CUs_0 = 20

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/nft/transfers
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
  /{address}/nft/transfers:
    get:
      tags:
        - NFT
        - Get Transfers
      summary: Get NFT Transfers by wallet address
      description: >-
        Get NFT transfers for a wallet, with filters like `contract_addresses`
        and other parameters. Supports ERC-721, ERC-1155 as well as custom
        contracts such as CryptoPunks and CryptoKitties.
      operationId: getWalletNFTTransfers
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The wallet address of the sender or recipient of the transfers
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: contract_addresses
          description: List of contract addresses of transfers
          required: false
          schema:
            type: array
            items:
              type: string
        - in: query
          name: format
          description: The format of the token ID
          required: false
          schema:
            type: string
            example: decimal
            default: decimal
            enum:
              - decimal
              - hex
        - in: query
          name: from_block
          description: >
            The minimum block number from which to get the transfers

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: to_block
          description: To get the reserves at this block number
          required: false
          schema:
            type: string
        - in: query
          name: from_date
          description: >
            The date from where to get the transfers (format in seconds or
            datestring accepted by momentjs)

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: to_date
          description: >
            Get transfers up until this date (format in seconds or datestring
            accepted by momentjs)

            * Provide the param 'to_block' or 'to_date'

            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          required: false
          schema:
            type: string
        - in: query
          name: include_prices
          description: Should NFT last sale prices be included in the result?
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
      responses:
        '200':
          description: Returns a collection of NFT transfers
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/nftTransferCollection'
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
    nftTransferCollection:
      required:
        - page
        - page_size
        - cursor
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/nftTransfer'
        block_exists:
          type: boolean
          description: Indicator if the block exists
          example: true
        index_complete:
          type: boolean
          description: Indicator if the block is fully indexed
          example: true
    nftTransfer:
      required:
        - token_address
        - token_id
        - transaction_hash
        - log_index
        - contract_type
        - block_timestamp
        - block_number
        - block_hash
        - possible_spam
      properties:
        token_address:
          type: string
          description: The address of the NFT contract
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        token_id:
          type: string
          description: The token ID of the NFT
          example: '15'
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
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
          description: The address that sent the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          description: The address that received the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
        value:
          type: string
          description: The value that was sent in the transaction (ETH/BNB/etc..)
          example: '1000000000000000'
        amount:
          type: string
          description: The number of tokens transferred
          example: '1'
        contract_type:
          type: string
          description: The type of NFT contract standard
          example: ERC721
        block_number:
          type: string
          description: The block number of the transaction
          example: '88256'
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2021-06-04T16:00:15'
        block_hash:
          type: string
          description: The block hash of the transaction
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        transaction_type:
          type: string
          description: The transaction type
        transaction_index:
          type: integer
          description: The transaction index
        log_index:
          type: integer
          description: The log index
        operator:
          type: string
          description: The operator present only for ERC1155 transfers
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_collection:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
        last_sale:
          type: object
          description: Details about the most recent sale involving this token.
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - buyer_address
            - seller_address
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
              example: >-
                0x19e14f34b8f120c980f7ba05338d64c00384857fb9c561e2c56d0f575424a95c
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
              example: '2023-04-04T15:59:11.000Z'
            buyer_address:
              type: string
              description: The buyer address of the last sale
              example: '0xcb1c1fde09f811b294172696404e88e658659905'
            seller_address:
              type: string
              description: The seller address of the last sale
              example: '0x497a7dee2f13db161eb2fec060fa783cb041419f'
            price:
              type: string
              description: The price of the last sale
              example: '7300000000000000'
            price_formatted:
              type: string
              description: The formatted price of the last sale
              example: '0.0073'
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale
              example: '13.61'
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
              example: '15.53'
            token_address:
              type: string
              description: The token address that is sold
              example: '0xe8778996e096b39705c6a0a937eb587a1ebbda17'
            token_id:
              type: string
              description: The token ID that is sold
              example: '170'
            payment_token:
              type: object
              description: The ERC20 token that is being traded with
              required:
                - token_name
                - token_symbol
                - token_logo
                - token_decimals
                - token_address
              properties:
                token_name:
                  type: string
                  description: The token name
                  example: Ether
                token_symbol:
                  type: string
                  description: The token symbol
                  example: ETH
                token_logo:
                  type: string
                  description: The token logo
                  example: https://cdn.moralis.io/eth/0x.png
                token_decimals:
                  type: string
                  description: The token decimals
                  example: '18'
                token_address:
                  type: string
                  description: The token address
                  example: '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
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

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Balances

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/tokens
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
  /wallets/{address}/tokens:
    get:
      tags:
        - Wallets
      summary: Get token balances with prices by wallet address
      description: >-
        Fetch ERC20 and native token balances for a given wallet address,
        including their USD prices. Each token returned includes on-chain
        metadata, as well as off-chain metadata, logos, spam status and more.
        Additional options to exclude spam tokens, low-liquidity tokens and
        inactive tokens.
      operationId: getWalletTokenBalancesPrice
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address from which token balances will be checked
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: to_block
          description: The block number up to which the balances will be checked.
          required: false
          schema:
            type: number
        - in: query
          name: token_addresses
          description: The addresses to get balances for (optional)
          required: false
          schema:
            type: array
            maxItems: 10
            items:
              type: string
        - in: query
          name: exclude_spam
          description: Exclude spam tokens from the result
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: exclude_unverified_contracts
          description: Exclude unverified contracts from the result
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: exclude_native
          description: Exclude native balance from the result
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: max_token_inactivity
          description: Exclude tokens inactive for more than the given amount of days
          required: false
          schema:
            type: number
        - in: query
          name: min_pair_side_liquidity_usd
          description: >-
            Exclude tokens with liquidity less than the specified amount in USD.
            This parameter refers to the liquidity on a single side of the pair.
          required: false
          schema:
            type: number
      responses:
        '200':
          description: Returns token balances with prices for a specific address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20TokenBalanceWithPriceResult'
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
    erc20TokenBalanceWithPriceResult:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        block_number:
          type: string
          description: The block number of the transaction
          example: '13680123'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/erc20TokenBalanceWithPrice'
    erc20TokenBalanceWithPrice:
      type: object
      required:
        - name
        - symbol
        - decimals
        - balance
        - possible_spam
        - usd_price
        - usd_price_24hr_percent_change
        - usd_price_24hr_usd_change
        - use_value_24hr_usd_change
        - usd_value
        - portfolio_percentage
        - balance_formatted
        - native_token
      properties:
        token_address:
          type: string
          description: The address of the token contract
        name:
          type: string
          description: The name of the token
        symbol:
          type: string
          description: The symbol of the token
        logo:
          type: string
          description: The logo of the token
        thumbnail:
          type: string
          description: The thumbnail of the token logo
        decimals:
          type: integer
          description: The number of decimals on the token
        balance:
          type: string
          description: The balance of the token
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
        usd_price:
          type: string
          description: USD price of the token
        usd_price_24hr_percent_change:
          type: string
          description: 24-hour percent change in USD price of the token
        usd_price_24hr_usd_change:
          type: string
          description: 24-hour change in USD price of the token
        usd_value_24hr_usd_change:
          type: string
          description: 24-hour change in USD value of the token based on the balance
        usd_value:
          type: number
          description: USD value of the token balance
        portfolio_percentage:
          type: number
          description: Percentage of the token in the entire portfolio
        balance_formatted:
          type: string
          description: Balance of the token in decimal format
        native_token:
          type: boolean
          description: Indicates if the token is a native coin
        total_supply:
          type: string
          description: Total supply of the token
        total_supply_formatted:
          type: string
          description: Total supply of the token in decimal format
        percentage_relative_to_total_supply:
          type: number
          description: Percentage of the token in the total supply
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

# Native Balance

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/balance
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
  /{address}/balance:
    get:
      tags:
        - Balance
      summary: Get native balance by wallet
      description: Check the native token balance (e.g. ETH) for a specific wallet.
      operationId: getNativeBalance
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address from which the native balance will be checked
          required: true
          schema:
            type: string
            example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        - in: query
          name: to_block
          description: The block number up to which the balances will be checked.
          required: false
          schema:
            type: number
      responses:
        '200':
          description: Returns the native balance for a specific address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/nativeBalance'
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
    nativeBalance:
      type: object
      required:
        - balance
      properties:
        balance:
          type: string
          description: The balance
          example: '1234567890'
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

# Native Balance

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/balance
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
  /{address}/balance:
    get:
      tags:
        - Balance
      summary: Get native balance by wallet
      description: Check the native token balance (e.g. ETH) for a specific wallet.
      operationId: getNativeBalance
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address from which the native balance will be checked
          required: true
          schema:
            type: string
            example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        - in: query
          name: to_block
          description: The block number up to which the balances will be checked.
          required: false
          schema:
            type: number
      responses:
        '200':
          description: Returns the native balance for a specific address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/nativeBalance'
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
    nativeBalance:
      type: object
      required:
        - balance
      properties:
        balance:
          type: string
          description: The balance
          example: '1234567890'
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

# Token Approvals

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/approvals
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
  /wallets/{address}/approvals:
    get:
      tags:
        - Wallets
      summary: Get ERC20 approvals by wallet
      description: >-
        List active ERC20 token approvals for a wallet, showing which contracts
        have access.
      operationId: getWalletApprovals
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: path
          name: address
          description: >-
            The wallet address from which to retrieve active ERC20 token
            approvals
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
      responses:
        '200':
          description: >-
            Returns active ERC20 token approvals for the specified wallet
            address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletApprovals'
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
    walletApprovals:
      required:
        - result
        - page
        - page_size
        - cursor
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/tokenApproval'
    tokenApproval:
      type: object
      required:
        - block_number
        - value
        - token
        - spender
      properties:
        block_number:
          type: string
          description: The block number
          example: 12526958
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2021-04-02T10:07:54.000Z'
          nullable: true
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
          nullable: true
        value:
          type: string
          description: The native price of the token
          example: '8409770570506626'
        value_formatted:
          type: string
          description: >-
            The value that was sent in the transaction (ETH/BNB/etc..) in
            decimal format
          example: '0.1'
          nullable: true
        token:
          type: object
          properties:
            address:
              type: string
              description: The address of the token
              example: '0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c'
            address_label:
              type: string
              nullable: true
              description: The label of the token
            name:
              type: string
              nullable: true
              description: The name of the token
              example: Tether USD
            symbol:
              type: string
              nullable: true
              description: The symbol of the token
              example: USDT
            logo:
              type: string
              nullable: true
              description: The logo of the token
              example: https://opensea.io/favicon.ico
            possible_spam:
              type: boolean
              description: Indicates if the token is a possible spam
              example: false
            verified_contract:
              type: boolean
              description: Indicates if the token is verified
              example: false
            current_balance:
              type: string
              nullable: true
              description: The current balance of the token
              example: '1000000000000000'
            current_balance_formatted:
              type: string
              nullable: true
              description: The current balance of the token in decimal format
              example: '0.1'
            usd_price:
              type: string
              nullable: true
              description: The current price of the token in USD
              example: '1000000000000000'
            usd_at_risk:
              type: string
              nullable: true
              description: The amount of USD approve potentially at risk
              example: '1000000000000000'
        spender:
          type: object
          properties:
            address:
              type: string
              description: The address of the spender
              example: '0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c'
            address_label:
              type: string
              nullable: true
              description: The label of the spender
              example: Binance 1
            entity:
              type: string
              nullable: true
              description: The entity of the spender
              example: Opensea
            entity_logo:
              type: string
              nullable: true
              description: The logo of the spender
              example: https://opensea.io/favicon.ico
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

# Token Approvals

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/approvals
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
  /wallets/{address}/approvals:
    get:
      tags:
        - Wallets
      summary: Get ERC20 approvals by wallet
      description: >-
        List active ERC20 token approvals for a wallet, showing which contracts
        have access.
      operationId: getWalletApprovals
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: path
          name: address
          description: >-
            The wallet address from which to retrieve active ERC20 token
            approvals
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
      responses:
        '200':
          description: >-
            Returns active ERC20 token approvals for the specified wallet
            address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletApprovals'
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
    walletApprovals:
      required:
        - result
        - page
        - page_size
        - cursor
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/tokenApproval'
    tokenApproval:
      type: object
      required:
        - block_number
        - value
        - token
        - spender
      properties:
        block_number:
          type: string
          description: The block number
          example: 12526958
        block_timestamp:
          type: string
          description: The block timestamp
          example: '2021-04-02T10:07:54.000Z'
          nullable: true
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
          nullable: true
        value:
          type: string
          description: The native price of the token
          example: '8409770570506626'
        value_formatted:
          type: string
          description: >-
            The value that was sent in the transaction (ETH/BNB/etc..) in
            decimal format
          example: '0.1'
          nullable: true
        token:
          type: object
          properties:
            address:
              type: string
              description: The address of the token
              example: '0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c'
            address_label:
              type: string
              nullable: true
              description: The label of the token
            name:
              type: string
              nullable: true
              description: The name of the token
              example: Tether USD
            symbol:
              type: string
              nullable: true
              description: The symbol of the token
              example: USDT
            logo:
              type: string
              nullable: true
              description: The logo of the token
              example: https://opensea.io/favicon.ico
            possible_spam:
              type: boolean
              description: Indicates if the token is a possible spam
              example: false
            verified_contract:
              type: boolean
              description: Indicates if the token is verified
              example: false
            current_balance:
              type: string
              nullable: true
              description: The current balance of the token
              example: '1000000000000000'
            current_balance_formatted:
              type: string
              nullable: true
              description: The current balance of the token in decimal format
              example: '0.1'
            usd_price:
              type: string
              nullable: true
              description: The current price of the token in USD
              example: '1000000000000000'
            usd_at_risk:
              type: string
              nullable: true
              description: The amount of USD approve potentially at risk
              example: '1000000000000000'
        spender:
          type: object
          properties:
            address:
              type: string
              description: The address of the spender
              example: '0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c'
            address_label:
              type: string
              nullable: true
              description: The label of the spender
              example: Binance 1
            entity:
              type: string
              nullable: true
              description: The entity of the spender
              example: Opensea
            entity_logo:
              type: string
              nullable: true
              description: The logo of the spender
              example: https://opensea.io/favicon.ico
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

# NFT Balances

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/nft
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
  /{address}/nft:
    get:
      tags:
        - NFT
        - Get NFTs
      summary: Get NFTs by wallet address
      description: >-
        Fetch all NFTs held by a specified wallet address. Use `token_addresses`
        to filter by one or many specific contract(s). Each NFT returned
        includes on-chain metadata as well as off-chain metadata, floor prices,
        rarity and more where available.
      operationId: getWalletNFTs
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address of the wallet
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: format
          description: The format of the token ID
          required: false
          schema:
            type: string
            example: decimal
            default: decimal
            enum:
              - decimal
              - hex
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: exclude_spam
          description: Should spam NFTs be excluded from the result?
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: token_addresses
          description: The addresses to get balances for (optional)
          required: false
          schema:
            type: array
            maxItems: 10
            items:
              type: string
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: normalizeMetadata
          description: Should normalized metadata be returned?
          required: false
          schema:
            type: boolean
            default: true
        - in: query
          name: media_items
          description: Should preview media data be returned?
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: include_prices
          description: Should NFT last sale prices be included in the result?
          required: false
          schema:
            type: boolean
            default: false
      responses:
        '200':
          description: Returns a collection of NFT owners
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/nftOwnerCollection'
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
    nftOwnerCollection:
      required:
        - result
      properties:
        status:
          type: string
          description: The syncing status of the address [SYNCING/SYNCED]
          example: SYNCING
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/nftOwner'
    nftOwner:
      required:
        - token_address
        - token_id
        - contract_type
        - name
        - block_number
        - block_number_minted
        - owner_of
        - symbol
        - token_hash
        - last_token_uri_sync
        - last_metadata_sync
        - possible_spam
      properties:
        token_address:
          type: string
          description: The address of the NFT contract
          example: '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB'
        token_id:
          type: string
          description: The token ID of the NFT
          example: '15'
        contract_type:
          type: string
          description: The type of NFT contract standard
          example: ERC721
        owner_of:
          type: string
          description: The wallet address of the owner of the NFT
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
        block_number:
          type: string
          description: The block number when the amount or owner changed
          example: '88256'
        block_number_minted:
          type: string
          description: The block number when the NFT was minted
          example: '88256'
        token_uri:
          type: string
          description: The URI to the metadata of the token
        metadata:
          type: string
          description: The metadata of the token
        normalized_metadata:
          $ref: '#/components/schemas/normalizedMetadata'
          description: A normalized metadata version of the NFT's metadata.
        media:
          $ref: '#/components/schemas/media'
          description: A set of links to 'thumbnail / preview' media files
        amount:
          type: string
          description: The number of this item the user owns (used by ERC1155)
          example: '1'
        name:
          type: string
          description: The name of the NFT contract
          example: CryptoKitties
        symbol:
          type: string
          description: The symbol of the NFT contract
          example: RARI
        token_hash:
          type: string
          description: The token hash
          example: 502cee781b0fb40ea02508b21d319ced
        rarity_rank:
          type: number
          description: The rarity rank
          example: 21669
        rarity_percentage:
          type: number
          description: The rarity percentage
          example: 98
        rarity_label:
          type: string
          description: The rarity label
          example: Top 98%
        last_token_uri_sync:
          type: string
          description: When the token_uri was last updated
          example: '2021-02-24T00:47:26.647Z'
        last_metadata_sync:
          type: string
          description: When the metadata was last updated
          example: '2021-02-24T00:47:26.647Z'
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_collection:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
        floor_price:
          type: string
          description: The floor price of the NFT
          example: '12345'
        floor_price_usd:
          type: string
          description: The floor price of the NFT in USD
          example: '12345.4899'
        floor_price_currency:
          type: string
          description: The currency of the floor price
          example: eth
        last_sale:
          type: object
          description: Details about the most recent sale involving this token.
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - buyer_address
            - seller_address
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
              example: >-
                0x19e14f34b8f120c980f7ba05338d64c00384857fb9c561e2c56d0f575424a95c
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
              example: '2023-04-04T15:59:11.000Z'
            buyer_address:
              type: string
              description: The buyer address of the last sale
              example: '0xcb1c1fde09f811b294172696404e88e658659905'
            seller_address:
              type: string
              description: The seller address of the last sale
              example: '0x497a7dee2f13db161eb2fec060fa783cb041419f'
            price:
              type: string
              description: The price of the last sale
              example: '7300000000000000'
            price_formatted:
              type: string
              description: The formatted price of the last sale
              example: '0.0073'
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale
              example: '13.61'
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
              example: '15.53'
            token_address:
              type: string
              description: The token address that is sold
              example: '0xe8778996e096b39705c6a0a937eb587a1ebbda17'
            token_id:
              type: string
              description: The token ID that is sold
              example: '170'
            payment_token:
              type: object
              description: The ERC20 token that is being traded with
              required:
                - token_name
                - token_symbol
                - token_logo
                - token_decimals
                - token_address
              properties:
                token_name:
                  type: string
                  description: The token name
                  example: Ether
                token_symbol:
                  type: string
                  description: The token symbol
                  example: ETH
                token_logo:
                  type: string
                  description: The token logo
                  example: https://cdn.moralis.io/eth/0x.png
                token_decimals:
                  type: string
                  description: The token decimals
                  example: '18'
                token_address:
                  type: string
                  description: The token address
                  example: '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
    normalizedMetadata:
      properties:
        name:
          type: string
          description: The name or title of the NFT
          example: Moralis Mug
        description:
          type: string
          description: A detailed description of the NFT
          example: >-
            Moralis Coffee nug 3D Asset that can be used in 3D worldspaces. This
            NFT is presented as a flat PNG, a Unity3D Prefab and a standard fbx.
        image:
          type: string
          description: The URL of the NFT's image
          example: >-
            https://arw2wxg84h6b.moralishost.com:2053/server/files/tNJatzsHirx4V2VAep6sc923OYGxvkpBeJttR7Ks/de504bbadadcbe30c86278342fcf2560_moralismug.png
        external_link:
          type: string
          description: A link to additional information
          example: https://giphy.com/gifs/loop-recursion-ting-aaODAv1iuQdgI
        external_url:
          type: string
          description: A link to additional information
          example: https://giphy.com/gifs/loop-recursion-ting-aaODAv1iuQdgI
        animation_url:
          type: string
          description: An animated version of the NFT's image
          example: https://giphy.com/gifs/food-design-donuts-o9ngTPVYW4qo8
        attributes:
          type: array
          items:
            $ref: '#/components/schemas/normalizedMetadataAttribute'
    media:
      properties:
        mimetype:
          type: string
          description: >-
            The mimetype of the media file [see
            https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types]
        category:
          enum:
            - image
            - audio
            - video
        status:
          enum:
            - success
            - processing
            - unsupported_media
            - invalid_url
            - host_unavailable
            - temporarily_unavailable
          description: >-
            <table><tr><td>success</td><td>The NFT Preview was created /
            retrieved successfully</td></tr><tr><td>processing</td><td>The NFT
            Preview was not found and has been submitted for
            generation.</td></tr><tr><td>unsupported_media</td><td>The mime-type
            of the NFT's media file indicates a type not currently
            supported.</td></tr><tr><td>invalid_url</td><td>The 'image' URL from
            the NFT's metadata is not a valid URL and cannot be
            processed.</td></tr><tr><td>host_unavailable</td><td>The 'image' URL
            from the NFT's metadata returned an HttpCode indicating the host /
            file is not
            available.</td></tr><tr><td>temporarily_unavailable</td><td>The
            attempt to load / parse the NFT media file failed (usually due to
            rate limiting) and will be tried again at next
            request.</td></tr></table>
        original_media_url:
          type: string
          description: The url of the original media file.
        updatedAt:
          type: string
          description: The timestamp of the last update to this NFT media record.
        parent_hash:
          type: string
          description: Hash value of the original media file.
        media_collection:
          $ref: '#/components/schemas/mediaCollection'
          description: Preview item associated with the original
    normalizedMetadataAttribute:
      properties:
        trait_type:
          type: string
          description: The trait title or descriptor
          example: Eye Color
        value:
          type: object
          description: The value of the attribute
          example: hazel
        display_type:
          type: string
          description: The type the attribute value should be displayed as
          example: string
        max_value:
          type: number
          description: For numeric values, the upper range
          example: 100
        trait_count:
          type: number
          description: The number of possible values for this trait
          example: 7
        order:
          type: number
          description: Order the trait should appear in the attribute list.
          example: 1
    mediaCollection:
      properties:
        low:
          $ref: '#/components/schemas/mediaItem'
          description: Preview media file, lowest quality (for images 100px x 100px)
        medium:
          $ref: '#/components/schemas/mediaItem'
          description: Preview media file, medium quality (for images 250px x 250px)
        high:
          $ref: '#/components/schemas/mediaItem'
          description: Preview media file, highest quality (for images 500px x 500px)
      required:
        - original
        - low
        - medium
        - high
    mediaItem:
      properties:
        width:
          type: integer
          description: The width of the preview image.
        height:
          type: integer
          description: The height of the preview image.
        url:
          type: string
          description: The url of the preview file.
      required:
        - width
        - height
        - url
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

# NFT Collections

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /{address}/nft/collections
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
  /{address}/nft/collections:
    get:
      tags:
        - NFT
        - Get Collections
      summary: Get NFT collections by wallet address
      description: >-
        Fetch all NFT Collections held by a specified wallet address. Each
        Collection returned includes on-chain metadata as well as off-chain
        metadata, floor prices and more where available.
      operationId: getWalletNFTCollections
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The wallet address of the owner of NFTs in the collections
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
        - in: query
          name: include_prices
          description: Should NFT last sale prices be included in the result?
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: exclude_spam
          description: Should spam NFTs be excluded from the result?
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: token_counts
          description: Should token counts per collection be included in the response?
          required: false
          schema:
            type: boolean
            default: false
      responses:
        '200':
          description: Returns the NFT collections owned by a wallet
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/nftWalletCollections'
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
    nftWalletCollections:
      required:
        - result
      properties:
        status:
          type: string
          description: The syncing status of the address [SYNCING/SYNCED]
          example: SYNCING
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/nftCollections'
    nftCollections:
      required:
        - token_address
        - contract_type
        - name
        - symbol
        - possible_spam
        - verified_collection
      properties:
        token_address:
          type: string
          description: The address of the NFT contract
          example: '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB'
        contract_type:
          type: string
          description: The type of NFT contract standard
          example: ERC721
        name:
          type: string
          description: The name of the NFT contract
          example: CryptoKitties
        symbol:
          type: string
          description: The symbol of the NFT contract
          example: RARI
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_collection:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
        count:
          type: integer
          description: The number of tokens the wallet holds in this collection
          example: 5
        collection_logo:
          type: string
          description: The logo of the collection
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        collection_banner_image:
          type: string
          description: The banner image of the collection
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        floor_price:
          type: string
          description: The floor price of the contract
          example: '12345'
        floor_price_usd:
          type: string
          description: The floor price of the contract in USD
          example: '12345.4899'
        floor_price_currency:
          type: string
          description: The currency of the floor price
          example: eth
        last_sale:
          type: object
          description: Details about the most recent sale involving this token.
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - buyer_address
            - seller_address
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
              example: >-
                0x19e14f34b8f120c980f7ba05338d64c00384857fb9c561e2c56d0f575424a95c
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
              example: '2023-04-04T15:59:11.000Z'
            buyer_address:
              type: string
              description: The buyer address of the last sale
              example: '0xcb1c1fde09f811b294172696404e88e658659905'
            seller_address:
              type: string
              description: The seller address of the last sale
              example: '0x497a7dee2f13db161eb2fec060fa783cb041419f'
            price:
              type: string
              description: The price of the last sale
              example: '7300000000000000'
            price_formatted:
              type: string
              description: The formatted price of the last sale
              example: '0.0073'
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale
              example: '13.61'
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
              example: '15.53'
            token_address:
              type: string
              description: The token address that is sold
              example: '0xe8778996e096b39705c6a0a937eb587a1ebbda17'
            token_id:
              type: string
              description: The token ID that is sold
              example: '170'
            payment_token:
              type: object
              description: The ERC20 token that is being traded with
              required:
                - token_name
                - token_symbol
                - token_logo
                - token_decimals
                - token_address
              properties:
                token_name:
                  type: string
                  description: The token name
                  example: Ether
                token_symbol:
                  type: string
                  description: The token symbol
                  example: ETH
                token_logo:
                  type: string
                  description: The token logo
                  example: https://cdn.moralis.io/eth/0x.png
                token_decimals:
                  type: string
                  description: The token decimals
                  example: '18'
                token_address:
                  type: string
                  description: The token address
                  example: '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
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

# Wallet Protocols

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/defi/summary
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
  /wallets/{address}/defi/summary:
    get:
      tags:
        - Wallets
      summary: Get the DeFi summary of a wallet
      description: >-
        Summarize a wallet’s DeFi activity, including total USD value, unclaimed
        rewards and active protocols.
      operationId: getDefiSummary
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
            example: '0xd100d8b69c5ae23d6aa30c6c3874bf47539b95fd'
      responses:
        '200':
          description: Returns the defi summary for the wallet address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletDefiSummary'
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
    walletDefiSummary:
      required:
        - active_protocols
        - total_positions
        - total_usd_value
        - protocols
      properties:
        active_protocols:
          type: number
          description: The number of active protocols
          example: '10'
        total_positions:
          type: number
          description: The number of total positions
          example: '100'
        total_usd_value:
          type: number
          description: The total USD value of the wallet
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the wallet
          example: '1000000'
        protocols:
          type: array
          items:
            $ref: '#/components/schemas/defiProtocolBalance'
    defiProtocolBalance:
      required:
        - total_usd_value
        - positions
      properties:
        total_usd_value:
          type: number
          description: The total USD value of the protocol
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the protocol
          example: '1000000'
        positions:
          type: number
          description: The number of positions
          example: '100'
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

# Wallet Protocols

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/defi/summary
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
  /wallets/{address}/defi/summary:
    get:
      tags:
        - Wallets
      summary: Get the DeFi summary of a wallet
      description: >-
        Summarize a wallet’s DeFi activity, including total USD value, unclaimed
        rewards and active protocols.
      operationId: getDefiSummary
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
            example: '0xd100d8b69c5ae23d6aa30c6c3874bf47539b95fd'
      responses:
        '200':
          description: Returns the defi summary for the wallet address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletDefiSummary'
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
    walletDefiSummary:
      required:
        - active_protocols
        - total_positions
        - total_usd_value
        - protocols
      properties:
        active_protocols:
          type: number
          description: The number of active protocols
          example: '10'
        total_positions:
          type: number
          description: The number of total positions
          example: '100'
        total_usd_value:
          type: number
          description: The total USD value of the wallet
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the wallet
          example: '1000000'
        protocols:
          type: array
          items:
            $ref: '#/components/schemas/defiProtocolBalance'
    defiProtocolBalance:
      required:
        - total_usd_value
        - positions
      properties:
        total_usd_value:
          type: number
          description: The total USD value of the protocol
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the protocol
          example: '1000000'
        positions:
          type: number
          description: The number of positions
          example: '100'
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

# Wallet Protocols

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/defi/summary
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
  /wallets/{address}/defi/summary:
    get:
      tags:
        - Wallets
      summary: Get the DeFi summary of a wallet
      description: >-
        Summarize a wallet’s DeFi activity, including total USD value, unclaimed
        rewards and active protocols.
      operationId: getDefiSummary
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
            example: '0xd100d8b69c5ae23d6aa30c6c3874bf47539b95fd'
      responses:
        '200':
          description: Returns the defi summary for the wallet address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/walletDefiSummary'
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
    walletDefiSummary:
      required:
        - active_protocols
        - total_positions
        - total_usd_value
        - protocols
      properties:
        active_protocols:
          type: number
          description: The number of active protocols
          example: '10'
        total_positions:
          type: number
          description: The number of total positions
          example: '100'
        total_usd_value:
          type: number
          description: The total USD value of the wallet
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the wallet
          example: '1000000'
        protocols:
          type: array
          items:
            $ref: '#/components/schemas/defiProtocolBalance'
    defiProtocolBalance:
      required:
        - total_usd_value
        - positions
      properties:
        total_usd_value:
          type: number
          description: The total USD value of the protocol
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the protocol
          example: '1000000'
        positions:
          type: number
          description: The number of positions
          example: '100'
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

# Wallet PnL Summary

export const CUs_0 = 30

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/profitability/summary
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
  /wallets/{address}/profitability/summary:
    get:
      tags:
        - Wallets
      summary: Get profit and loss summary by wallet address
      description: >-
        Get a profit and loss summary for a given wallet, over a specified
        timeframe (`days`).
      operationId: getWalletProfitabilitySummary
      parameters:
        - in: path
          name: address
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
          description: >-
            The wallet address for which profitability summary is to be
            retrieved.
        - in: query
          name: days
          required: false
          schema:
            type: string
          description: >-
            Timeframe in days for the profitability summary. Options include
            'all', '7', '30', '60', '90' default is 'all'.
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
      responses:
        '200':
          description: Successful response with the profitability summary.
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_count_of_trades:
                    type: number
                    description: Total count of trades executed by the wallet.
                  total_trade_volume:
                    type: string
                    description: Total trade volume managed by the wallet.
                  total_realized_profit_usd:
                    type: string
                    description: Total realized profit in USD for the wallet.
                  total_realized_profit_percentage:
                    type: number
                    description: Total realized profit as a percentage.
                  total_buys:
                    type: number
                    description: Total number of buy transactions.
                  total_sells:
                    type: number
                    description: Total number of sell transactions.
                  total_sold_volume_usd:
                    type: string
                    description: Total USD volume of tokens sold by the wallet.
                  total_bought_volume_usd:
                    type: string
                    description: Total USD volume of tokens bought by the wallet.
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

# Wallet PnL Breakdown

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/profitability
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
  /wallets/{address}/profitability:
    get:
      tags:
        - Wallets
      summary: Get detailed profit and loss by wallet address
      description: >-
        Get a detailed profit and loss breakdown by token for a given wallet,
        over a specified timeframe (`days`). Optionally filter by
        `token_addresses` for specific tokens.
      operationId: getWalletProfitability
      parameters:
        - in: path
          name: address
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
          description: The wallet address for which profitability is to be retrieved.
        - in: query
          name: days
          required: false
          schema:
            type: string
          description: >-
            Timeframe in days for which profitability is calculated, Options
            include 'all', '7', '30', '60', '90' default is 'all'.
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: token_addresses
          description: The token addresses list to filter the result with
          required: false
          schema:
            type: array
            maxItems: 25
            items:
              type: string
      responses:
        '200':
          description: Successful response with profitability data.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/WalletProfitabilityResponse'
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
    WalletProfitabilityResponse:
      type: object
      properties:
        result:
          type: array
          items:
            $ref: '#/components/schemas/WalletProfitabilityTokenData'
          description: List of tokens traded with their respective profitability data.
    WalletProfitabilityTokenData:
      type: object
      required:
        - token_address
        - avg_buy_price_usd
        - avg_sell_price_usd
        - total_usd_invested
        - total_tokens_sold
        - total_tokens_bought
        - total_sold_usd
        - avg_cost_of_quantity_sold
        - count_of_trades
        - realized_profit_usd
        - realized_profit_percentage
        - total_buys
        - total_sells
        - name
        - symbol
        - decimals
        - logo
        - possible_spam
      properties:
        token_address:
          type: string
          description: The address of the traded token.
        avg_buy_price_usd:
          type: string
          description: Average buy price in USD.
        avg_sell_price_usd:
          type: string
          description: Average sell price in USD.
        total_usd_invested:
          type: string
          description: Total USD invested.
        total_tokens_sold:
          type: string
          description: Total tokens sold.
        total_tokens_bought:
          type: string
          description: Total tokens bought.
        total_sold_usd:
          type: string
          description: Total USD received from selling tokens.
        avg_cost_of_quantity_sold:
          type: string
          description: Average cost of sold quantity.
        count_of_trades:
          type: number
          description: Count of trades for the token.
        realized_profit_usd:
          type: string
          description: Realized profit in USD for the token.
        realized_profit_percentage:
          type: number
          description: Realized profit percentage for the token.
        total_buys:
          type: number
          description: Total number of buys.
        total_sells:
          type: number
          description: Total number of sells.
        name:
          type: string
          description: Name of the token.
        symbol:
          type: string
          description: Symbol of the token.
        decimals:
          type: string
          description: Decimals of the token.
        logo:
          type: string
          description: Logo URL of the token.
        possible_spam:
          type: boolean
          description: Indicates whether the token is possibly spam.
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

# Wallet PnL Breakdown

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/profitability
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
  /wallets/{address}/profitability:
    get:
      tags:
        - Wallets
      summary: Get detailed profit and loss by wallet address
      description: >-
        Get a detailed profit and loss breakdown by token for a given wallet,
        over a specified timeframe (`days`). Optionally filter by
        `token_addresses` for specific tokens.
      operationId: getWalletProfitability
      parameters:
        - in: path
          name: address
          required: true
          schema:
            type: string
            example: '0xcB1C1FdE09f811B294172696404e88E658659905'
          description: The wallet address for which profitability is to be retrieved.
        - in: query
          name: days
          required: false
          schema:
            type: string
          description: >-
            Timeframe in days for which profitability is calculated, Options
            include 'all', '7', '30', '60', '90' default is 'all'.
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: token_addresses
          description: The token addresses list to filter the result with
          required: false
          schema:
            type: array
            maxItems: 25
            items:
              type: string
      responses:
        '200':
          description: Successful response with profitability data.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/WalletProfitabilityResponse'
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
    WalletProfitabilityResponse:
      type: object
      properties:
        result:
          type: array
          items:
            $ref: '#/components/schemas/WalletProfitabilityTokenData'
          description: List of tokens traded with their respective profitability data.
    WalletProfitabilityTokenData:
      type: object
      required:
        - token_address
        - avg_buy_price_usd
        - avg_sell_price_usd
        - total_usd_invested
        - total_tokens_sold
        - total_tokens_bought
        - total_sold_usd
        - avg_cost_of_quantity_sold
        - count_of_trades
        - realized_profit_usd
        - realized_profit_percentage
        - total_buys
        - total_sells
        - name
        - symbol
        - decimals
        - logo
        - possible_spam
      properties:
        token_address:
          type: string
          description: The address of the traded token.
        avg_buy_price_usd:
          type: string
          description: Average buy price in USD.
        avg_sell_price_usd:
          type: string
          description: Average sell price in USD.
        total_usd_invested:
          type: string
          description: Total USD invested.
        total_tokens_sold:
          type: string
          description: Total tokens sold.
        total_tokens_bought:
          type: string
          description: Total tokens bought.
        total_sold_usd:
          type: string
          description: Total USD received from selling tokens.
        avg_cost_of_quantity_sold:
          type: string
          description: Average cost of sold quantity.
        count_of_trades:
          type: number
          description: Count of trades for the token.
        realized_profit_usd:
          type: string
          description: Realized profit in USD for the token.
        realized_profit_percentage:
          type: number
          description: Realized profit percentage for the token.
        total_buys:
          type: number
          description: Total number of buys.
        total_sells:
          type: number
          description: Total number of sells.
        name:
          type: string
          description: Name of the token.
        symbol:
          type: string
          description: Symbol of the token.
        decimals:
          type: string
          description: Decimals of the token.
        logo:
          type: string
          description: Logo URL of the token.
        possible_spam:
          type: boolean
          description: Indicates whether the token is possibly spam.
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

# Resolve Address from ENS Domain

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /resolve/ens/{domain}
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
  /resolve/ens/{domain}:
    get:
      tags:
        - Resolve Web3 Domain
      summary: ENS lookup by domain
      description: Resolve an ENS domain to its associated Ethereum address.
      operationId: resolveENSDomain
      parameters:
        - in: path
          name: domain
          description: The domain to be resolved
          required: true
          schema:
            type: string
            example: vitalik.eth
      responses:
        '200':
          description: Returns an address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/resolve'
        '404':
          description: Returns an address
          content:
            application/json:
              schema:
                type: object
      security:
        - ApiKeyAuth: []
components:
  schemas:
    resolve:
      required:
        - address
      properties:
        address:
          type: string
          description: Resolved domain address
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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

# Resolve ENS Domain from Address

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /resolve/{address}/reverse
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
  /resolve/{address}/reverse:
    get:
      tags:
        - Resolve Web3 Domain
      summary: ENS lookup by address
      description: Convert an Ethereum address to its associated ENS domain, if registered.
      operationId: resolveAddress
      parameters:
        - in: path
          name: address
          description: The address to be resolved
          required: true
          schema:
            type: string
            example: '0xd8da6bf26964af9d7eed9e03e53415d37aa96045'
      responses:
        '200':
          description: Returns an ENS
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ens'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    ens:
      required:
        - name
      properties:
        name:
          type: string
          description: Resolved ENS address
          example: Vitalik.eth
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

# Token API Overview

> The most powerful Token API in Web3 - fetch, analyse, and monitor ERC20 tokens across multiple chains, covering prices, balances, transfers, liquidity, holders, volume, profitability, and advanced safety signals through a single unified interface.

## Overview

The **Token API** provides comprehensive ERC-20 token data including prices, balances, transfers, holders, liquidity, swaps, and advanced analytics across all supported EVM chains.

From simple balance queries to complex token analytics, the Token API delivers the data you need to build trading platforms, portfolio trackers, and token analysis tools.

***

## What Is the Token API?

The Token API lets you query:

* **Balances** - Token holdings for any wallet address
* **Transfers** - Transfer history by wallet or token contract
* **Prices** - Real-time and historical token prices
* **Holders** - Token holder lists and distribution analytics
* **Swaps** - DEX trading activity and swap history
* **Liquidity** - Trading pairs, reserves, and liquidity data
* **Metadata** - Token details including name, symbol, decimals, and logo

***

## Key Features

* **Real-Time Prices** - Current token prices with USD values
* **Historical Data** - Price history and OHLC candlestick data
* **Holder Analytics** - Top holders, holder counts, and distribution
* **Swap Tracking** - DEX trades with token pairs and values
* **Pair Discovery** - Find trading pairs across DEXs
* **Token Search** - Search tokens by name or symbol
* **Safety Signals** - Token security analysis and risk indicators
* **Multi-Chain** - Consistent data across all EVM chains

***

## Common Use Cases

* **Trading Platforms**\
  (real-time prices, charts, swap history)
* **Portfolio Trackers**\
  (token balances with USD valuations)
* **Token Analytics**\
  (holder distribution, volume, liquidity)
* **DEX Aggregators**\
  (pair discovery, liquidity analysis)
* **Wallet Apps**\
  (display token holdings and transfers)
* **Research Tools**\
  (token metrics and safety analysis)

***

## Get Started

Explore some of the popular Token API endpoints:

* [Token Balances](/data-api/evm/wallet/token-balances) - Get token holdings for a wallet
* [Token Search](/data-api/data-features/search-and-discovery/token-search) - Search for tokens
* [Token Price](/data-api/evm/price/token-price) - Get current token price
* [Token Transfers](/data-api/evm/wallet/token-transfers) - Get transfer history
* [Token Metadata](/data-api/evm/token/metadata/token-metadata) - Get token details
* [Token Pairs](/data-api/evm/token/swaps/token-pairs) - Get trading pairs


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Metadata

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/metadata
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
  /erc20/metadata:
    get:
      tags:
        - Token
        - Get Metadata
      summary: Get ERC20 token metadata by contract
      description: >-
        Retrieve metadata (name, symbol, decimals, logo) for an ERC20 token
        contract, as well as off-chain metadata, total supply, categories,
        logos, spam status and more.
      operationId: getTokenMetadata
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: addresses
          description: The addresses to get metadata for
          required: true
          schema:
            type: array
            maxItems: 10
            items:
              type: string
              example: '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0'
      responses:
        '200':
          description: >-
            Get the metadata for a given ERC20 token contract address (name,
            symbol, decimals, logo).
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/erc20Metadata'
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
    erc20Metadata:
      type: object
      required:
        - address
        - name
        - symbol
        - decimals
        - created_at
        - possible_spam
      properties:
        address:
          type: string
          description: The address of the token contract
          example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
        address_label:
          type: string
          nullable: true
          description: The label of the address
          example: Binance 1
        name:
          type: string
          description: The name of the token contract
          example: Kylin Network
        symbol:
          type: string
          description: The symbol of the NFT contract
          example: KYL
        decimals:
          type: string
          description: The number of decimals on the token
          example: '18'
        logo:
          type: string
          nullable: true
          description: The logo of the token
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        logo_hash:
          type: string
          nullable: true
          description: The logo hash
          example: ee7aa2cdf100649a3521a082116258e862e6971261a39b5cd4e4354fcccbc54d
        thumbnail:
          type: string
          nullable: true
          description: The thumbnail of the logo
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c_thumb.png
        total_supply:
          type: string
          nullable: false
          description: Total tokens created minus any that have been burned
          example: '420689899999994793099999999997400'
        total_supply_formatted:
          type: string
          nullable: false
          description: >-
            Total tokens created minus any that have been burned (decimal
            formatted)
          example: '420689899999994.7930999999999974'
        implementations:
          type: array
          items:
            description: The token addresses of the same symbol from another chains
            required:
              - chainId
              - address
            properties:
              chainId:
                type: string
                description: The chain id
                example: '0x1'
              chain:
                type: string
                description: The chain name
                example: eth
              chainName:
                type: string
                description: The chain name
                example: Ethereum
              address:
                type: string
                description: The token address
                example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
        fully_diluted_valuation:
          type: string
          nullable: false
          description: >-
            Fully Diluted Valuation (FDV), this represents the token's Current
            Price x Total Supply
          example: '3407271444.05'
        block_number:
          type: string
        validated:
          type: number
        created_at:
          type: string
          description: The timestamp of when the erc20 token was created
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
          example: false
        categories:
          type: array
          items:
            type: string
          nullable: true
          description: Categories of the token
          example:
            - stablecoin
        links:
          $ref: '#/components/schemas/discoveryTokenLinks'
        circulating_supply:
          type: string
          description: The circulating supply of the token
          example: '4206864.7489303'
        market_cap:
          type: string
          description: The market cap of the token
          example: '3407271444.05'
    discoveryTokenLinks:
      type: object
      required:
        - bitbucket
        - discord
        - facebook
        - github
        - instagram
        - linkedin
        - medium
        - reddit
        - telegram
        - tiktok
        - twitter
        - website
        - youtube
      properties:
        bitbucket:
          type: string
          description: The link of the token on the platform
        discord:
          type: string
          description: The link of the token on the platform
        facebook:
          type: string
          description: The link of the token on the platform
        github:
          type: string
          description: The link of the token on the platform
        instagram:
          type: string
          description: The link of the token on the platform
        linkedin:
          type: string
          description: The link of the token on the platform
        medium:
          type: string
          description: The link of the token on the platform
        reddit:
          type: string
          description: The link of the token on the platform
        telegram:
          type: string
          description: The link of the token on the platform
        tiktok:
          type: string
          description: The link of the token on the platform
        twitter:
          type: string
          description: The link of the token on the platform
        website:
          type: string
          description: The link of the token on the platform
        youtube:
          type: string
          description: The link of the token on the platform
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

# Token Score

> Retrieve a score for a specific token along with detailed metrics including price, volume, liquidity, transaction counts, and supply information.

export const CUs_0 = 100

<Note>
  **Premium endpoint:** This endpoint requires an API key on the **Pro plan** or above.
</Note>

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /tokens/{tokenAddress}/score
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
  /tokens/{tokenAddress}/score:
    get:
      tags:
        - Token
      summary: Get token score by token address
      description: >-
        Retrieve a score for a specific token along with detailed metrics
        including price, volume, liquidity, transaction counts, and supply
        information.
      operationId: getTokenScore
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainListWithSolana'
        - in: path
          name: tokenAddress
          description: The token address to query
          required: true
          schema:
            type: string
            example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenScoreResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainListWithSolana:
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
        - solana
    TokenScoreResponse:
      type: object
      properties:
        tokenAddress:
          type: string
          example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
        chainId:
          type: string
          example: '0x1'
        score:
          type: integer
          example: 94
        updatedAt:
          type: string
          example: '2025-12-03T21:10:28Z'
        metrics:
          $ref: '#/components/schemas/TokenScoreMetrics'
          nullable: true
    TokenScoreMetrics:
      type: object
      properties:
        usdPrice:
          type: number
          example: 0.00000647147501365255
        liquidityUsd:
          type: number
          example: 10890420.9
        volumeUsd:
          $ref: '#/components/schemas/TokenScoreVolumeUsd'
        transactions:
          $ref: '#/components/schemas/TokenScoreTransactions'
        supply:
          $ref: '#/components/schemas/TokenScoreSupply'
    TokenScoreVolumeUsd:
      type: object
      properties:
        10m:
          type: number
          example: 17506.72
        30m:
          type: number
          example: 974862.35
        1h:
          type: number
          example: 88701.15
        4h:
          type: number
          example: 84547204.23
        12h:
          type: number
          example: 974862.35
        1d:
          type: number
          example: 1971902.13
        7d:
          type: number
          example: 4571941.67
        30d:
          type: number
          example: 445.57
    TokenScoreTransactions:
      type: object
      properties:
        10m:
          type: number
          example: 54
        30m:
          type: number
          example: 132
        1h:
          type: number
          example: 3040
        4h:
          type: number
          example: 85301
        12h:
          type: number
          example: 1602
        1d:
          type: number
          example: 602
        7d:
          type: number
          example: 15328
        30d:
          type: number
          example: 25
    TokenScoreSupply:
      type: object
      properties:
        total:
          type: number
          example: 420689899653542.56
        top10Percent:
          type: number
          example: 41.03
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

# Token Score - Timeseries

export const CUs_0 = 150

<Note>
  **Premium endpoint:** This endpoint requires an API key on the **Pro plan** or above.
</Note>

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /tokens/{tokenAddress}/score/historical
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
  /tokens/{tokenAddress}/score/historical:
    get:
      tags:
        - Token
      summary: Get historical token score by token address
      description: Retrieve historical score data for a specific token over time.
      operationId: getHistoricalTokenScore
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainListWithSolana'
        - in: path
          name: tokenAddress
          description: The token address to query
          required: true
          schema:
            type: string
            example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
        - in: query
          name: timeframe
          description: The timeframe to query
          required: true
          schema:
            type: string
            example: 1d
            default: 1d
            enum:
              - 1d
              - 7d
              - 30d
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HistoricalTokenScoreResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    chainListWithSolana:
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
        - solana
    HistoricalTokenScoreResponse:
      type: object
      properties:
        chainId:
          type: string
          example: '0x1'
        tokenAddress:
          type: string
          example: '0xdac17f958d2ee523a2206206994597c13d831ec7'
        timeseries:
          type: array
          items:
            type: object
            properties:
              timestamp:
                type: string
                example: '2022-02-22T00:00:00Z'
              score:
                type: number
                example: 85
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

# Token Price

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/{address}/price
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
  /erc20/{address}/price:
    get:
      tags:
        - Token
        - Get Market Data
      summary: Get ERC20 token price
      description: >-
        Retrieve the current or historical price of an ERC20 token in the
        blockchain’s native currency and USD. Each token returned includes
        on-chain metadata, as well as off-chain metadata, logos, spam status and
        more. Additional options to exclude low-liquidity tokens and inactive
        tokens.
      operationId: getTokenPrice
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address of the token contract
          required: true
          schema:
            type: string
            example: '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0'
        - in: query
          name: exchange
          description: The factory name or address of the token exchange
          required: false
          schema:
            type: string
        - in: query
          name: to_block
          description: The block number from which the token price should be checked
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: include
          description: >-
            This parameter is now deprecated as percentage change are included
            by default
          required: false
          deprecated: true
          schema:
            type: string
            example: ''
            default: ''
            enum:
              - percent_change
        - in: query
          name: max_token_inactivity
          description: Exclude tokens inactive for more than the given amount of days
          required: false
          schema:
            type: number
        - in: query
          name: min_pair_side_liquidity_usd
          description: >-
            Exclude tokens with liquidity less than the specified amount in USD.
            This parameter refers to the liquidity on a single side of the pair.
          required: false
          schema:
            type: number
      responses:
        '200':
          description: >-
            Returns the price denominated in the blockchain's native token and
            USD for a given token contract address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20Price'
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
    erc20Price:
      required:
        - usdPrice
        - possibleSpam
        - verifiedContract
      properties:
        tokenName:
          type: string
          description: The name of the token
          example: Kylin Network
        tokenSymbol:
          type: string
          description: The symbol of the token
          example: KYL
        tokenLogo:
          type: string
          description: The logo of the token
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        tokenDecimals:
          type: string
          description: The number of decimals of the token
          example: '18'
        nativePrice:
          $ref: '#/components/schemas/nativeErc20Price'
        usdPrice:
          type: number
          format: double
          description: The price in USD for the token
          example: 19.722370676
        usdPriceFormatted:
          type: string
          description: The price in USD for the token in string format
          example: '19.722370676'
        24hrPercentChange:
          type: string
          description: The 24hr percent change of the token
          example: '-0.8842730258590583'
        exchangeAddress:
          type: string
          description: The address of the exchange used to calculate the price
          example: '0x1f98431c8ad98523631ae4a59f267346ea31f984'
        exchangeName:
          type: string
          description: The name of the exchange used to calculate the price
          example: Uniswap v3
        tokenAddress:
          type: string
          description: The address of the token
          example: '0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c'
        toBlock:
          type: string
          description: toBlock
          example: '16314545'
        possibleSpam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verifiedContract:
          type: boolean
          description: Indicates if the contract is verified
          example: true
        pairAddress:
          type: string
          description: The address of the pair
          example: '0x1f98431c8ad98523631ae4a59f267346ea31f984'
        pairTotalLiquidityUsd:
          type: string
          description: The total liquidity in USD of the pair
          example: '123.45'
        usdPrice24h:
          type: number
          description: The USD price 24 hours ago
          example: 1
        usdPrice24hrUsdChange:
          type: number
          description: The USD change in price over the last 24 hours
          example: -0.00008615972490000345
        usdPrice24hrPercentChange:
          type: number
          description: The percent change in USD price over the last 24 hours
          example: -0.008615972490000345
        securityScore:
          type: number
          description: >-
            A number between 0 and 100 that defines the trust level of this
            specific token
          example: 1
    nativeErc20Price:
      required:
        - value
        - decimals
        - name
        - symbol
        - address
      properties:
        value:
          type: string
          description: The native price of the token
          example: '8409770570506626'
        decimals:
          type: integer
          description: The number of decimals on the token
          example: 18
        name:
          type: string
          description: The name of the token
          example: Ether
        symbol:
          type: string
          description: The symbol of the token
          example: ETH
        address:
          type: string
          description: The address of the native token
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

# Token Prices (Batch)

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json POST /erc20/prices
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
  /erc20/prices:
    post:
      tags:
        - Token
        - Get Market Data
      summary: Get Multiple ERC20 token prices
      description: >-
        Retrieve the current or historical prices for multiple ERC20 tokens in
        the blockchain’s native currency and USD. Accepts an array of up to 100
        `tokens`, each requiring `token_address` and optional fields such as
        `to_block` or `exchange`. Each token returned includes on-chain
        metadata, as well as off-chain metadata, logos, spam status and more.
        Additional options to exclude low-liquidity tokens and inactive tokens.
      operationId: getMultipleTokenPrices
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: include
          description: >-
            This parameter is now deprecated as percentage change are included
            by default
          required: false
          deprecated: true
          schema:
            type: string
            example: ''
            default: ''
            enum:
              - percent_change
        - in: query
          name: max_token_inactivity
          description: Exclude tokens inactive for more than the given amount of days
          required: false
          schema:
            type: number
        - in: query
          name: min_pair_side_liquidity_usd
          description: >-
            Exclude tokens with liquidity less than the specified amount in USD.
            This parameter refers to the liquidity on a single side of the pair.
          required: false
          schema:
            type: number
      requestBody:
        description: Body
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GetMultipleTokenPricesDto'
      responses:
        '200':
          description: >-
            Returns an array of token prices denominated in the blockchain's
            native token and USD for a given token contract address
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/erc20Price'
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
    GetMultipleTokenPricesDto:
      required:
        - tokens
      properties:
        tokens:
          type: array
          maxItems: 30
          description: The tokens to be fetched
          example:
            - token_address: '0xdac17f958d2ee523a2206206994597c13d831ec7'
            - token_address: '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
            - token_address: '0xae7ab96520de3a18e5e111b5eaab095312d7fe84'
              exchange: uniswapv2
              to_block: '16314545'
            - token_address: '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0'
          items:
            $ref: '#/components/schemas/tokenPriceItem'
    erc20Price:
      required:
        - usdPrice
        - possibleSpam
        - verifiedContract
      properties:
        tokenName:
          type: string
          description: The name of the token
          example: Kylin Network
        tokenSymbol:
          type: string
          description: The symbol of the token
          example: KYL
        tokenLogo:
          type: string
          description: The logo of the token
          example: >-
            https://cdn.moralis.io/eth/0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c.png
        tokenDecimals:
          type: string
          description: The number of decimals of the token
          example: '18'
        nativePrice:
          $ref: '#/components/schemas/nativeErc20Price'
        usdPrice:
          type: number
          format: double
          description: The price in USD for the token
          example: 19.722370676
        usdPriceFormatted:
          type: string
          description: The price in USD for the token in string format
          example: '19.722370676'
        24hrPercentChange:
          type: string
          description: The 24hr percent change of the token
          example: '-0.8842730258590583'
        exchangeAddress:
          type: string
          description: The address of the exchange used to calculate the price
          example: '0x1f98431c8ad98523631ae4a59f267346ea31f984'
        exchangeName:
          type: string
          description: The name of the exchange used to calculate the price
          example: Uniswap v3
        tokenAddress:
          type: string
          description: The address of the token
          example: '0x67b6d479c7bb412c54e03dca8e1bc6740ce6b99c'
        toBlock:
          type: string
          description: toBlock
          example: '16314545'
        possibleSpam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verifiedContract:
          type: boolean
          description: Indicates if the contract is verified
          example: true
        pairAddress:
          type: string
          description: The address of the pair
          example: '0x1f98431c8ad98523631ae4a59f267346ea31f984'
        pairTotalLiquidityUsd:
          type: string
          description: The total liquidity in USD of the pair
          example: '123.45'
        usdPrice24h:
          type: number
          description: The USD price 24 hours ago
          example: 1
        usdPrice24hrUsdChange:
          type: number
          description: The USD change in price over the last 24 hours
          example: -0.00008615972490000345
        usdPrice24hrPercentChange:
          type: number
          description: The percent change in USD price over the last 24 hours
          example: -0.008615972490000345
        securityScore:
          type: number
          description: >-
            A number between 0 and 100 that defines the trust level of this
            specific token
          example: 1
    tokenPriceItem:
      required:
        - token_address
      properties:
        token_address:
          type: string
          description: The contract address
          example: '0x06012c8cf97bead5deae237070f9587f8e7a266d'
        exchange:
          type: string
          description: The exchange
          example: uniswapv3
        to_block:
          type: string
          description: The block number
          example: 12526958
    nativeErc20Price:
      required:
        - value
        - decimals
        - name
        - symbol
        - address
      properties:
        value:
          type: string
          description: The native price of the token
          example: '8409770570506626'
        decimals:
          type: integer
          description: The number of decimals on the token
          example: 18
        name:
          type: string
          description: The name of the token
          example: Ether
        symbol:
          type: string
          description: The symbol of the token
          example: ETH
        address:
          type: string
          description: The address of the native token
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

# OHLC by Pair Address

export const CUs_0 = 150

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/ohlcv
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
  /pairs/{address}/ohlcv:
    get:
      tags:
        - Token
      summary: Get OHLCV by pair address
      description: >-
        Retrieve OHLCV (Open, High, Low, Close, Volume) candlestick data for a
        token pair.
      operationId: getPairCandlesticks
      parameters:
        - in: path
          name: address
          description: The pair address
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: timeframe
          description: The timeframe
          required: true
          schema:
            type: string
            example: 1h
            default: 1h
            enum:
              - 1s
              - 10s
              - 30s
              - 1min
              - 5min
              - 10min
              - 30min
              - 1h
              - 4h
              - 12h
              - 1d
              - 1w
              - 1M
        - in: query
          name: currency
          description: The currency
          required: true
          schema:
            type: string
            example: usd
            default: usd
            enum:
              - usd
              - native
        - in: query
          name: fromDate
          description: >
            The starting date (format in seconds or datestring accepted by
            momentjs)

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: true
          schema:
            type: string
            example: '2025-01-01T10:00:00.000'
        - in: query
          name: toDate
          description: >
            The ending date (format in seconds or datestring accepted by
            momentjs)

            * Provide the param 'toBlock' or 'toDate'

            * If 'toDate' and 'toBlock' are provided, 'toBlock' will be used.
          required: true
          schema:
            type: string
            example: '2025-01-02T10:00:00.000'
        - in: query
          name: limit
          description: The number of results to return
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page)
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Returns the OHLCV data.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/candleSticksResponse'
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
    candleSticksResponse:
      type: object
      required:
        - page
        - cursor
        - pairAddress
        - timeframe
        - currency
        - result
      properties:
        cursor:
          type: string
          description: The cursor to get to the next page
        page:
          type: integer
          description: The current page of the result
          example: '2'
        pairAddress:
          type: string
          description: The pair address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        tokenAddress:
          type: string
          description: The token address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        timeframe:
          type: string
          description: The timeframe
          example: 30min
        currency:
          type: string
          description: The currency
          example: usd
        result:
          type: array
          items:
            $ref: '#/components/schemas/ohlcv'
    ohlcv:
      type: object
      properties:
        timestamp:
          type: string
        open:
          type: number
        high:
          type: number
        low:
          type: number
        close:
          type: number
        volume:
          type: number
        trades:
          type: number
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

# Token Transfers by Contract

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/{address}/transfers
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
  /erc20/{address}/transfers:
    get:
      tags:
        - Token
        - Get Transactions
      summary: Get ERC20 token transfers by contract address
      description: >-
        Get all ERC20 token transfers for a contract, ordered by block number
        (newest first).
      operationId: getTokenTransfers
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
            The minimum block number from which to get the transfers

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
            The maximum block number from which to get the transfers.
            * Provide the param 'to_block' or 'to_date'
            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: from_date
          description: >
            The start date from which to get the transfers (format in seconds or
            datestring accepted by momentjs)

            * Provide the param 'from_block' or 'from_date'

            * If 'from_date' and 'from_block' are provided, 'from_block' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: to_date
          description: >
            Get transfers up until this date (format in seconds or datestring
            accepted by momentjs)

            * Provide the param 'to_block' or 'to_date'

            * If 'to_date' and 'to_block' are provided, 'to_block' will be used.
          schema:
            type: string
        - in: path
          name: address
          description: The address of the token contract
          required: true
          schema:
            type: string
            example: '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0'
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
      responses:
        '200':
          description: Returns a collection of token contract transactions.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20TransactionCollection'
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
    erc20TransactionCollection:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/erc20Transaction'
    erc20Transaction:
      required:
        - token_name
        - token_symbol
        - token_decimals
        - value_decimal
        - transaction_hash
        - address
        - block_timestamp
        - block_number
        - block_hash
        - from_address
        - value
        - transaction_index
        - log_index
        - possible_spam
        - verified_contract
      properties:
        token_name:
          type: string
          example: Tether USD
        token_symbol:
          type: string
          example: USDT
        token_logo:
          type: string
          example: cdn.moralis.io/325/large/Tether-logo.png?1598003707
        token_decimals:
          type: string
          example: '6'
        transaction_hash:
          type: string
          description: The transaction hash
          example: '0x2d30ca6f024dbc1307ac8a1a44ca27de6f797ec22ef20627a1307243b0ab7d09'
        address:
          type: string
          description: The address of the token
          example: '0x057Ec652A4F150f7FF94f089A38008f49a0DF88e'
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
          example: '0x62AED87d21Ad0F3cdE4D147Fdcc9245401Af0044'
        to_address_label:
          type: string
          nullable: true
          description: The label of the to address
          example: Binance 2
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
        value:
          type: string
          description: The value that was transfered (in wei)
          example: 650000000000000000
        transaction_index:
          type: integer
          description: The transaction index of the transfer within the block
          example: 12
        log_index:
          type: integer
          description: The log index of the transfer within the block
          example: 2
        possible_spam:
          type: boolean
          description: Indicates if a contract is possibly a spam contract
          example: 'false'
        verified_contract:
          type: boolean
          description: Indicates if a contract is verified
          example: 'false'
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

# Top Token Holders

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/{token_address}/owners
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
  /erc20/{token_address}/owners:
    get:
      tags:
        - Token
        - Get Ownership
      summary: Get ERC20 token owners by contract
      description: >-
        Identify the major holders of an ERC20 token and understand their
        ownership percentages. Includes known entities, exchanges and wallet
        labels.
      operationId: getTokenOwners
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: token_address
          description: The address of the token contract
          required: true
          schema:
            type: string
            example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          required: false
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
      responses:
        '200':
          description: Returns a collection of owners of an ERC20 token
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/erc20TokenOwnerCollection'
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
    erc20TokenOwnerCollection:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        page_size:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        total_supply:
          type: string
          description: The total supply of the token
        result:
          type: array
          items:
            $ref: '#/components/schemas/erc20TokenOwner'
    erc20TokenOwner:
      required:
        - owner_address
        - owner_address_label
        - balance
        - balance_formatted
        - usd_value
        - is_contract
        - percentage_relative_to_total_supply
      properties:
        owner_address:
          type: string
          description: The address of the erc20 token owner
          example: 0x244...
        owner_address_label:
          type: string
          description: The label of the owner_address
          example: Coinbase 1
        balance:
          type: string
          description: The amount holding of the ERC20 token
          example: '57888888888888888888880'
        balance_formatted:
          type: string
          description: The amount holding of the ERC20 token in decimaal
          example: '5.78'
        usd_value:
          type: string
          description: The USD value of the balance
          example: '57888888888888888888880'
        is_contract:
          type: boolean
          description: Indicates if the token address is for a contract or not
        percentage_relative_to_total_supply:
          type: number
          example: 10
          description: The percentage of total supply held by the owner
        entity:
          type: string
          description: The owner address entity
          example: Opensea
          nullable: true
        entity_logo:
          type: string
          description: The logo of the owner address entity
          example: https://opensea.io/favicon.ico
          nullable: true
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

# Token Holder Metrics

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/{tokenAddress}/holders
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
  /erc20/{tokenAddress}/holders:
    get:
      tags:
        - Token
      summary: Get a holders summary by token address
      description: >-
        Returns total holders for a given token, as well as aggregated stats
        holder supply, holder trends, holder distribution and holder acquisition
        metrics.
      operationId: getTokenHolders
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: tokenAddress
          description: The token address to get transaction for
          required: true
          schema:
            type: string
            example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
      responses:
        '200':
          description: Returns token holder summary result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenHolderSummaryResult'
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
    TokenHolderSummaryResult:
      required:
        - totalHolders
        - holderSupply
        - holderChange
        - holdersByAcquisition
        - holderDistribution
      properties:
        totalHolders:
          type: number
          description: The total holders of the token
          example: '99999'
        holderSupply:
          $ref: '#/components/schemas/TokenHolderSummarySupply'
          type: object
          description: The holder supply
        holderChange:
          $ref: '#/components/schemas/TokenHolderSummaryHolderChange'
          type: object
          description: The holder change
        holdersByAcquisition:
          $ref: '#/components/schemas/TokenHolderSummaryHolderByAcquisition'
          type: object
          description: The holder change
        holderDistribution:
          $ref: '#/components/schemas/TokenHolderCategory'
          type: object
          description: The holder distribution
    TokenHolderSummarySupply:
      required:
        - top10
        - top25
        - top50
        - top100
        - top250
        - top500
      properties:
        top10:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top25:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 25 holders
        top50:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top100:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top250:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 250 holders
        top500:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 500 holders
    TokenHolderSummaryHolderChange:
      required:
        - 5min
        - 1h
        - 6h
        - 24h
        - 7d
        - 3d
        - 30d
      properties:
        5min:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: The holder change in the last 5 minutes
        1h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 1 hour
        6h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 6 hour
        24h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 24 hour
        3d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 3 days
        7d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 7 days
        30d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 30 days
    TokenHolderSummaryHolderByAcquisition:
      required:
        - swap
        - transfer
        - airdrop
      properties:
        swap:
          type: number
          description: Number of wallets with first interaction as a swap
          example: '10'
        transfer:
          type: number
          description: Number of wallets with first interaction as a transfer
          example: '10'
        airdrop:
          type: number
          description: Number of wallets with first interaction as a airdrop
          example: '10'
    TokenHolderCategory:
      required:
        - whales
        - sharks
        - dolphins
        - fish
        - octopus
        - crabs
        - shrimps
      properties:
        whales:
          type: integer
          description: Number of wallets in the category
          example: '100'
        sharks:
          type: integer
          description: Number of wallets in the category
          example: '100'
        dolphins:
          type: integer
          description: Number of wallets in the category
          example: '100'
        fish:
          type: integer
          description: Number of wallets in the category
          example: '100'
        octopus:
          type: integer
          description: Number of wallets in the category
          example: '100'
        crabs:
          type: integer
          description: Number of wallets in the category
          example: '100'
        shrimps:
          type: integer
          description: Number of wallets in the category
          example: '100'
    TokenHolderSupplyChange:
      required:
        - supply
        - supplyPercent
      properties:
        supply:
          type: string
          description: Net holder change
          example: '10'
        supplyPercent:
          type: number
          description: The percentage change
          example: '0.10'
    TokenHolderChange:
      required:
        - change
        - changePercent
      properties:
        change:
          type: number
          description: Net holder change
          example: '10'
        changePercent:
          type: number
          description: The percentage change
          example: '0.10'
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

# Token Holder Metrics

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/{tokenAddress}/holders
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
  /erc20/{tokenAddress}/holders:
    get:
      tags:
        - Token
      summary: Get a holders summary by token address
      description: >-
        Returns total holders for a given token, as well as aggregated stats
        holder supply, holder trends, holder distribution and holder acquisition
        metrics.
      operationId: getTokenHolders
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: tokenAddress
          description: The token address to get transaction for
          required: true
          schema:
            type: string
            example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
      responses:
        '200':
          description: Returns token holder summary result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenHolderSummaryResult'
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
    TokenHolderSummaryResult:
      required:
        - totalHolders
        - holderSupply
        - holderChange
        - holdersByAcquisition
        - holderDistribution
      properties:
        totalHolders:
          type: number
          description: The total holders of the token
          example: '99999'
        holderSupply:
          $ref: '#/components/schemas/TokenHolderSummarySupply'
          type: object
          description: The holder supply
        holderChange:
          $ref: '#/components/schemas/TokenHolderSummaryHolderChange'
          type: object
          description: The holder change
        holdersByAcquisition:
          $ref: '#/components/schemas/TokenHolderSummaryHolderByAcquisition'
          type: object
          description: The holder change
        holderDistribution:
          $ref: '#/components/schemas/TokenHolderCategory'
          type: object
          description: The holder distribution
    TokenHolderSummarySupply:
      required:
        - top10
        - top25
        - top50
        - top100
        - top250
        - top500
      properties:
        top10:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top25:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 25 holders
        top50:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top100:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top250:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 250 holders
        top500:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 500 holders
    TokenHolderSummaryHolderChange:
      required:
        - 5min
        - 1h
        - 6h
        - 24h
        - 7d
        - 3d
        - 30d
      properties:
        5min:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: The holder change in the last 5 minutes
        1h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 1 hour
        6h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 6 hour
        24h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 24 hour
        3d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 3 days
        7d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 7 days
        30d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 30 days
    TokenHolderSummaryHolderByAcquisition:
      required:
        - swap
        - transfer
        - airdrop
      properties:
        swap:
          type: number
          description: Number of wallets with first interaction as a swap
          example: '10'
        transfer:
          type: number
          description: Number of wallets with first interaction as a transfer
          example: '10'
        airdrop:
          type: number
          description: Number of wallets with first interaction as a airdrop
          example: '10'
    TokenHolderCategory:
      required:
        - whales
        - sharks
        - dolphins
        - fish
        - octopus
        - crabs
        - shrimps
      properties:
        whales:
          type: integer
          description: Number of wallets in the category
          example: '100'
        sharks:
          type: integer
          description: Number of wallets in the category
          example: '100'
        dolphins:
          type: integer
          description: Number of wallets in the category
          example: '100'
        fish:
          type: integer
          description: Number of wallets in the category
          example: '100'
        octopus:
          type: integer
          description: Number of wallets in the category
          example: '100'
        crabs:
          type: integer
          description: Number of wallets in the category
          example: '100'
        shrimps:
          type: integer
          description: Number of wallets in the category
          example: '100'
    TokenHolderSupplyChange:
      required:
        - supply
        - supplyPercent
      properties:
        supply:
          type: string
          description: Net holder change
          example: '10'
        supplyPercent:
          type: number
          description: The percentage change
          example: '0.10'
    TokenHolderChange:
      required:
        - change
        - changePercent
      properties:
        change:
          type: number
          description: Net holder change
          example: '10'
        changePercent:
          type: number
          description: The percentage change
          example: '0.10'
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

# Token Holder Metrics

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /erc20/{tokenAddress}/holders
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
  /erc20/{tokenAddress}/holders:
    get:
      tags:
        - Token
      summary: Get a holders summary by token address
      description: >-
        Returns total holders for a given token, as well as aggregated stats
        holder supply, holder trends, holder distribution and holder acquisition
        metrics.
      operationId: getTokenHolders
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: tokenAddress
          description: The token address to get transaction for
          required: true
          schema:
            type: string
            example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
      responses:
        '200':
          description: Returns token holder summary result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenHolderSummaryResult'
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
    TokenHolderSummaryResult:
      required:
        - totalHolders
        - holderSupply
        - holderChange
        - holdersByAcquisition
        - holderDistribution
      properties:
        totalHolders:
          type: number
          description: The total holders of the token
          example: '99999'
        holderSupply:
          $ref: '#/components/schemas/TokenHolderSummarySupply'
          type: object
          description: The holder supply
        holderChange:
          $ref: '#/components/schemas/TokenHolderSummaryHolderChange'
          type: object
          description: The holder change
        holdersByAcquisition:
          $ref: '#/components/schemas/TokenHolderSummaryHolderByAcquisition'
          type: object
          description: The holder change
        holderDistribution:
          $ref: '#/components/schemas/TokenHolderCategory'
          type: object
          description: The holder distribution
    TokenHolderSummarySupply:
      required:
        - top10
        - top25
        - top50
        - top100
        - top250
        - top500
      properties:
        top10:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top25:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 25 holders
        top50:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top100:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 10 holders
        top250:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 250 holders
        top500:
          $ref: '#/components/schemas/TokenHolderSupplyChange'
          type: object
          description: The holder breakdown of the top 500 holders
    TokenHolderSummaryHolderChange:
      required:
        - 5min
        - 1h
        - 6h
        - 24h
        - 7d
        - 3d
        - 30d
      properties:
        5min:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: The holder change in the last 5 minutes
        1h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 1 hour
        6h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 6 hour
        24h:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 24 hour
        3d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 3 days
        7d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 7 days
        30d:
          $ref: '#/components/schemas/TokenHolderChange'
          type: object
          description: Net holder change in the last 30 days
    TokenHolderSummaryHolderByAcquisition:
      required:
        - swap
        - transfer
        - airdrop
      properties:
        swap:
          type: number
          description: Number of wallets with first interaction as a swap
          example: '10'
        transfer:
          type: number
          description: Number of wallets with first interaction as a transfer
          example: '10'
        airdrop:
          type: number
          description: Number of wallets with first interaction as a airdrop
          example: '10'
    TokenHolderCategory:
      required:
        - whales
        - sharks
        - dolphins
        - fish
        - octopus
        - crabs
        - shrimps
      properties:
        whales:
          type: integer
          description: Number of wallets in the category
          example: '100'
        sharks:
          type: integer
          description: Number of wallets in the category
          example: '100'
        dolphins:
          type: integer
          description: Number of wallets in the category
          example: '100'
        fish:
          type: integer
          description: Number of wallets in the category
          example: '100'
        octopus:
          type: integer
          description: Number of wallets in the category
          example: '100'
        crabs:
          type: integer
          description: Number of wallets in the category
          example: '100'
        shrimps:
          type: integer
          description: Number of wallets in the category
          example: '100'
    TokenHolderSupplyChange:
      required:
        - supply
        - supplyPercent
      properties:
        supply:
          type: string
          description: Net holder change
          example: '10'
        supplyPercent:
          type: number
          description: The percentage change
          example: '0.10'
    TokenHolderChange:
      required:
        - change
        - changePercent
      properties:
        change:
          type: number
          description: Net holder change
          example: '10'
        changePercent:
          type: number
          description: The percentage change
          example: '0.10'
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

# Pair Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/swaps
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
  /pairs/{address}/swaps:
    get:
      tags:
        - Token
      summary: Get swap transactions by pair address
      description: >-
        Fetch swap transactions (buy, sell, add/remove liquidity) for a specific
        token pair.
      operationId: getSwapsByPairAddress
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The pair address token-transactions are to be retrieved for.
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: fromBlock
          description: >
            The minimum block number from which to get the token transactions

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: toBlock
          description: The block number to get the token transactions from
          required: false
          schema:
            type: string
        - in: query
          name: fromDate
          description: >
            The start date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: toDate
          description: >
            The end date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'toBlock' or 'toDate'

            * If 'toDate' and 'toBlock' are provided, 'toBlock' will be used.
          required: false
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - name: transactionTypes
          in: query
          required: false
          schema:
            type: string
          description: >-
            Array of transaction types. Allowed values are 'buy', 'sell',
            'addLiquidity', 'removeLiquidity'.
      responses:
        '200':
          description: Returns swap transactions by pair address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/getSwapsByPairAddressResponse'
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
    getSwapsByPairAddressResponse:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        pageSize:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        exchangeAddress:
          type: string
          example: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'
        exchangeName:
          type: string
          example: Uniswap v2
        exchangeLogo:
          type: string
          example: https://entities-logos.s3.us-east-1.amazonaws.com/uniswap.png
        pairLabel:
          type: string
          example: BRETT/WETH
        pairAddress:
          type: string
          example: '0x36a46dff597c5a444bbc521d26787f57867d2214'
        baseToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        quoteToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        result:
          type: array
          items:
            $ref: '#/components/schemas/swapsByPairAddressResult'
    TokenTransactionTokenMetadata:
      type: object
      properties:
        address:
          type: string
          description: The address of the token
          example: '0x003dde3494f30d861d063232c6a8c04394b686ff'
        name:
          type: string
          description: The name of the token
          example: BRETT
        symbol:
          type: string
          description: The symbol of the token
          example: BRETT
        logo:
          type: string
          description: The URL of the token's logo
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        amount:
          type: string
          description: The amount of the token
          example: '14811.98'
        usdPrice:
          type: number
          description: The amount of the token
          example: 0.078634
        usdAmount:
          type: number
          description: The amount of the token
          example: 1155.33
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
    swapsByPairAddressResult:
      type: object
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - subCategory
        - blockTimestamp
        - walletAddress
        - baseTokenAmount
        - quoteTokenAmount
        - baseTokenPriceUsd
        - quoteTokenPriceUsd
        - totalValueUsd
        - baseQuotePrice
        - blockNumber
      properties:
        transactionHash:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abecab76c9db813602015b3134ad'
        transactionIndex:
          type: integer
          example: 1
        transactionType:
          type: string
          example: buy
        blockTimestamp:
          type: string
          example: '2022-02-22T00:00:00Z'
        blockNumber:
          type: number
          example: 21093423
        subCategory:
          type: string
          example: accumulation
        walletAddress:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abec'
        baseTokenAmount:
          type: string
          example: '1481.00'
        quoteTokenAmount:
          type: string
          example: '0.634'
        baseTokenPriceUsd:
          type: number
          example: 0.0734634
        quoteTokenPriceUsd:
          type: number
          example: 23330
        baseQuotePrice:
          type: string
          example: '0.00003376480687'
        totalValueUsd:
          type: number
          example: 1165
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

# Pair Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/swaps
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
  /pairs/{address}/swaps:
    get:
      tags:
        - Token
      summary: Get swap transactions by pair address
      description: >-
        Fetch swap transactions (buy, sell, add/remove liquidity) for a specific
        token pair.
      operationId: getSwapsByPairAddress
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The pair address token-transactions are to be retrieved for.
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: fromBlock
          description: >
            The minimum block number from which to get the token transactions

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: toBlock
          description: The block number to get the token transactions from
          required: false
          schema:
            type: string
        - in: query
          name: fromDate
          description: >
            The start date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: toDate
          description: >
            The end date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'toBlock' or 'toDate'

            * If 'toDate' and 'toBlock' are provided, 'toBlock' will be used.
          required: false
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - name: transactionTypes
          in: query
          required: false
          schema:
            type: string
          description: >-
            Array of transaction types. Allowed values are 'buy', 'sell',
            'addLiquidity', 'removeLiquidity'.
      responses:
        '200':
          description: Returns swap transactions by pair address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/getSwapsByPairAddressResponse'
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
    getSwapsByPairAddressResponse:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        pageSize:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        exchangeAddress:
          type: string
          example: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'
        exchangeName:
          type: string
          example: Uniswap v2
        exchangeLogo:
          type: string
          example: https://entities-logos.s3.us-east-1.amazonaws.com/uniswap.png
        pairLabel:
          type: string
          example: BRETT/WETH
        pairAddress:
          type: string
          example: '0x36a46dff597c5a444bbc521d26787f57867d2214'
        baseToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        quoteToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        result:
          type: array
          items:
            $ref: '#/components/schemas/swapsByPairAddressResult'
    TokenTransactionTokenMetadata:
      type: object
      properties:
        address:
          type: string
          description: The address of the token
          example: '0x003dde3494f30d861d063232c6a8c04394b686ff'
        name:
          type: string
          description: The name of the token
          example: BRETT
        symbol:
          type: string
          description: The symbol of the token
          example: BRETT
        logo:
          type: string
          description: The URL of the token's logo
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        amount:
          type: string
          description: The amount of the token
          example: '14811.98'
        usdPrice:
          type: number
          description: The amount of the token
          example: 0.078634
        usdAmount:
          type: number
          description: The amount of the token
          example: 1155.33
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
    swapsByPairAddressResult:
      type: object
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - subCategory
        - blockTimestamp
        - walletAddress
        - baseTokenAmount
        - quoteTokenAmount
        - baseTokenPriceUsd
        - quoteTokenPriceUsd
        - totalValueUsd
        - baseQuotePrice
        - blockNumber
      properties:
        transactionHash:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abecab76c9db813602015b3134ad'
        transactionIndex:
          type: integer
          example: 1
        transactionType:
          type: string
          example: buy
        blockTimestamp:
          type: string
          example: '2022-02-22T00:00:00Z'
        blockNumber:
          type: number
          example: 21093423
        subCategory:
          type: string
          example: accumulation
        walletAddress:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abec'
        baseTokenAmount:
          type: string
          example: '1481.00'
        quoteTokenAmount:
          type: string
          example: '0.634'
        baseTokenPriceUsd:
          type: number
          example: 0.0734634
        quoteTokenPriceUsd:
          type: number
          example: 23330
        baseQuotePrice:
          type: string
          example: '0.00003376480687'
        totalValueUsd:
          type: number
          example: 1165
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

# Pair Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/swaps
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
  /pairs/{address}/swaps:
    get:
      tags:
        - Token
      summary: Get swap transactions by pair address
      description: >-
        Fetch swap transactions (buy, sell, add/remove liquidity) for a specific
        token pair.
      operationId: getSwapsByPairAddress
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The pair address token-transactions are to be retrieved for.
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: fromBlock
          description: >
            The minimum block number from which to get the token transactions

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: toBlock
          description: The block number to get the token transactions from
          required: false
          schema:
            type: string
        - in: query
          name: fromDate
          description: >
            The start date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: toDate
          description: >
            The end date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'toBlock' or 'toDate'

            * If 'toDate' and 'toBlock' are provided, 'toBlock' will be used.
          required: false
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - name: transactionTypes
          in: query
          required: false
          schema:
            type: string
          description: >-
            Array of transaction types. Allowed values are 'buy', 'sell',
            'addLiquidity', 'removeLiquidity'.
      responses:
        '200':
          description: Returns swap transactions by pair address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/getSwapsByPairAddressResponse'
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
    getSwapsByPairAddressResponse:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        pageSize:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        exchangeAddress:
          type: string
          example: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'
        exchangeName:
          type: string
          example: Uniswap v2
        exchangeLogo:
          type: string
          example: https://entities-logos.s3.us-east-1.amazonaws.com/uniswap.png
        pairLabel:
          type: string
          example: BRETT/WETH
        pairAddress:
          type: string
          example: '0x36a46dff597c5a444bbc521d26787f57867d2214'
        baseToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        quoteToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        result:
          type: array
          items:
            $ref: '#/components/schemas/swapsByPairAddressResult'
    TokenTransactionTokenMetadata:
      type: object
      properties:
        address:
          type: string
          description: The address of the token
          example: '0x003dde3494f30d861d063232c6a8c04394b686ff'
        name:
          type: string
          description: The name of the token
          example: BRETT
        symbol:
          type: string
          description: The symbol of the token
          example: BRETT
        logo:
          type: string
          description: The URL of the token's logo
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        amount:
          type: string
          description: The amount of the token
          example: '14811.98'
        usdPrice:
          type: number
          description: The amount of the token
          example: 0.078634
        usdAmount:
          type: number
          description: The amount of the token
          example: 1155.33
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
    swapsByPairAddressResult:
      type: object
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - subCategory
        - blockTimestamp
        - walletAddress
        - baseTokenAmount
        - quoteTokenAmount
        - baseTokenPriceUsd
        - quoteTokenPriceUsd
        - totalValueUsd
        - baseQuotePrice
        - blockNumber
      properties:
        transactionHash:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abecab76c9db813602015b3134ad'
        transactionIndex:
          type: integer
          example: 1
        transactionType:
          type: string
          example: buy
        blockTimestamp:
          type: string
          example: '2022-02-22T00:00:00Z'
        blockNumber:
          type: number
          example: 21093423
        subCategory:
          type: string
          example: accumulation
        walletAddress:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abec'
        baseTokenAmount:
          type: string
          example: '1481.00'
        quoteTokenAmount:
          type: string
          example: '0.634'
        baseTokenPriceUsd:
          type: number
          example: 0.0734634
        quoteTokenPriceUsd:
          type: number
          example: 23330
        baseQuotePrice:
          type: string
          example: '0.00003376480687'
        totalValueUsd:
          type: number
          example: 1165
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

# Pair Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/swaps
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
  /pairs/{address}/swaps:
    get:
      tags:
        - Token
      summary: Get swap transactions by pair address
      description: >-
        Fetch swap transactions (buy, sell, add/remove liquidity) for a specific
        token pair.
      operationId: getSwapsByPairAddress
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The pair address token-transactions are to be retrieved for.
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: fromBlock
          description: >
            The minimum block number from which to get the token transactions

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: integer
            minimum: 0
        - in: query
          name: toBlock
          description: The block number to get the token transactions from
          required: false
          schema:
            type: string
        - in: query
          name: fromDate
          description: >
            The start date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'fromBlock' or 'fromDate'

            * If 'fromDate' and 'fromBlock' are provided, 'fromBlock' will be
            used.
          required: false
          schema:
            type: string
        - in: query
          name: toDate
          description: >
            The end date from which to get the token transactions (format in
            seconds or datestring accepted by momentjs)

            * Provide the param 'toBlock' or 'toDate'

            * If 'toDate' and 'toBlock' are provided, 'toBlock' will be used.
          required: false
          schema:
            type: string
        - in: query
          name: order
          description: The order of the result, in ascending (ASC) or descending (DESC)
          required: false
          schema:
            $ref: '#/components/schemas/orderList'
        - name: transactionTypes
          in: query
          required: false
          schema:
            type: string
          description: >-
            Array of transaction types. Allowed values are 'buy', 'sell',
            'addLiquidity', 'removeLiquidity'.
      responses:
        '200':
          description: Returns swap transactions by pair address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/getSwapsByPairAddressResponse'
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
    getSwapsByPairAddressResponse:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '2'
        pageSize:
          type: integer
          description: The number of results per page
          example: '100'
        cursor:
          type: string
          description: The cursor to get to the next page
        exchangeAddress:
          type: string
          example: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'
        exchangeName:
          type: string
          example: Uniswap v2
        exchangeLogo:
          type: string
          example: https://entities-logos.s3.us-east-1.amazonaws.com/uniswap.png
        pairLabel:
          type: string
          example: BRETT/WETH
        pairAddress:
          type: string
          example: '0x36a46dff597c5a444bbc521d26787f57867d2214'
        baseToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        quoteToken:
          $ref: '#/components/schemas/TokenTransactionTokenMetadata'
        result:
          type: array
          items:
            $ref: '#/components/schemas/swapsByPairAddressResult'
    TokenTransactionTokenMetadata:
      type: object
      properties:
        address:
          type: string
          description: The address of the token
          example: '0x003dde3494f30d861d063232c6a8c04394b686ff'
        name:
          type: string
          description: The name of the token
          example: BRETT
        symbol:
          type: string
          description: The symbol of the token
          example: BRETT
        logo:
          type: string
          description: The URL of the token's logo
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        amount:
          type: string
          description: The amount of the token
          example: '14811.98'
        usdPrice:
          type: number
          description: The amount of the token
          example: 0.078634
        usdAmount:
          type: number
          description: The amount of the token
          example: 1155.33
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
    swapsByPairAddressResult:
      type: object
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - subCategory
        - blockTimestamp
        - walletAddress
        - baseTokenAmount
        - quoteTokenAmount
        - baseTokenPriceUsd
        - quoteTokenPriceUsd
        - totalValueUsd
        - baseQuotePrice
        - blockNumber
      properties:
        transactionHash:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abecab76c9db813602015b3134ad'
        transactionIndex:
          type: integer
          example: 1
        transactionType:
          type: string
          example: buy
        blockTimestamp:
          type: string
          example: '2022-02-22T00:00:00Z'
        blockNumber:
          type: number
          example: 21093423
        subCategory:
          type: string
          example: accumulation
        walletAddress:
          type: string
          example: '0x2bfcba4715774420936669cd0ff2241d70e9abec'
        baseTokenAmount:
          type: string
          example: '1481.00'
        quoteTokenAmount:
          type: string
          example: '0.634'
        baseTokenPriceUsd:
          type: number
          example: 0.0734634
        quoteTokenPriceUsd:
          type: number
          example: 23330
        baseQuotePrice:
          type: string
          example: '0.00003376480687'
        totalValueUsd:
          type: number
          example: 1165
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

# Pair Stats

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/stats
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
  /pairs/{address}/stats:
    get:
      tags:
        - Token
      summary: Get stats by pair address
      description: >-
        Access key statistics for a token pair, such as price, buyers, sellers,
        liquidity, volume and more.
      operationId: getPairStats
      parameters:
        - in: path
          name: address
          description: The pair address
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
      responses:
        '200':
          description: Returns the pair stats.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/pairStatsResponse'
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
    pairStatsResponse:
      type: object
      required:
        - tokenAddress
        - tokenName
        - tokenSymbol
        - tokenLogo
        - pairCreated
        - pairLabel
        - pairAddress
        - exchange
        - exchangeAddress
        - exchangeLogo
        - exchangeUrl
        - currentUsdPrice
        - currentNativePrice
        - totalLiquidityUsd
        - pricePercentChange
        - liquidityPercentChange
        - buys
        - sells
        - totalVolume
        - buyVolume
        - sellVolume
        - buyers
        - sellers
      properties:
        tokenAddress:
          type: string
          description: The token address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        tokenName:
          type: string
          description: The token name
          example: Wrapped Ether
          nullable: true
        tokenSymbol:
          type: string
          description: The token symbol
          example: WETH
          nullable: true
        tokenLogo:
          type: string
          description: The token image
          example: https://cdn.moralis.io/coins/images/2518/large/weth.png?1595348880
          nullable: true
        pairCreated:
          type: string
          description: The time when the pair was created
          example: '2021-04-02T10:07:54.000Z'
          nullable: true
        pairLabel:
          type: string
          description: The pair label
          example: WETH/PEPE
          nullable: true
        pairAddress:
          type: string
          description: The pair address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        exchange:
          type: string
          description: The exchange name
          example: Uniswap v2
          nullable: true
        exchangeAddress:
          type: string
          description: The exchange address
          example: '0x101cc05f4a51c0319f570d5e146a8c625198e222'
        exchangeLogo:
          type: string
          description: The exchange logo
          example: uniswap.png
          nullable: true
        exchangeUrl:
          type: string
          description: The exchange url
          example: app.uniswap.com
          nullable: true
        currentUsdPrice:
          type: string
          description: The current usd price
          example: '0.00000194'
          nullable: true
        currentNativePrice:
          type: string
          description: The current native price
          example: '0.0000000042'
          nullable: true
        totalLiquidityUsd:
          type: string
          description: The total liquidity in usd
          example: '43345522'
          nullable: true
        pricePercentChange:
          $ref: '#/components/schemas/candleSummary'
          type: object
        liquidityPercentChange:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buys:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sells:
          $ref: '#/components/schemas/candleSummary'
          type: object
        totalVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buyVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sellVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buyers:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sellers:
          $ref: '#/components/schemas/candleSummary'
          type: object
    candleSummary:
      type: object
      required:
        - 5min
        - 1h
        - 4h
        - 24h
      properties:
        5min:
          type: number
          nullable: true
        1h:
          type: number
          nullable: true
        4h:
          type: number
          nullable: true
        24h:
          type: number
          nullable: true
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

# Pair Stats

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/stats
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
  /pairs/{address}/stats:
    get:
      tags:
        - Token
      summary: Get stats by pair address
      description: >-
        Access key statistics for a token pair, such as price, buyers, sellers,
        liquidity, volume and more.
      operationId: getPairStats
      parameters:
        - in: path
          name: address
          description: The pair address
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
      responses:
        '200':
          description: Returns the pair stats.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/pairStatsResponse'
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
    pairStatsResponse:
      type: object
      required:
        - tokenAddress
        - tokenName
        - tokenSymbol
        - tokenLogo
        - pairCreated
        - pairLabel
        - pairAddress
        - exchange
        - exchangeAddress
        - exchangeLogo
        - exchangeUrl
        - currentUsdPrice
        - currentNativePrice
        - totalLiquidityUsd
        - pricePercentChange
        - liquidityPercentChange
        - buys
        - sells
        - totalVolume
        - buyVolume
        - sellVolume
        - buyers
        - sellers
      properties:
        tokenAddress:
          type: string
          description: The token address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        tokenName:
          type: string
          description: The token name
          example: Wrapped Ether
          nullable: true
        tokenSymbol:
          type: string
          description: The token symbol
          example: WETH
          nullable: true
        tokenLogo:
          type: string
          description: The token image
          example: https://cdn.moralis.io/coins/images/2518/large/weth.png?1595348880
          nullable: true
        pairCreated:
          type: string
          description: The time when the pair was created
          example: '2021-04-02T10:07:54.000Z'
          nullable: true
        pairLabel:
          type: string
          description: The pair label
          example: WETH/PEPE
          nullable: true
        pairAddress:
          type: string
          description: The pair address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        exchange:
          type: string
          description: The exchange name
          example: Uniswap v2
          nullable: true
        exchangeAddress:
          type: string
          description: The exchange address
          example: '0x101cc05f4a51c0319f570d5e146a8c625198e222'
        exchangeLogo:
          type: string
          description: The exchange logo
          example: uniswap.png
          nullable: true
        exchangeUrl:
          type: string
          description: The exchange url
          example: app.uniswap.com
          nullable: true
        currentUsdPrice:
          type: string
          description: The current usd price
          example: '0.00000194'
          nullable: true
        currentNativePrice:
          type: string
          description: The current native price
          example: '0.0000000042'
          nullable: true
        totalLiquidityUsd:
          type: string
          description: The total liquidity in usd
          example: '43345522'
          nullable: true
        pricePercentChange:
          $ref: '#/components/schemas/candleSummary'
          type: object
        liquidityPercentChange:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buys:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sells:
          $ref: '#/components/schemas/candleSummary'
          type: object
        totalVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buyVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sellVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buyers:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sellers:
          $ref: '#/components/schemas/candleSummary'
          type: object
    candleSummary:
      type: object
      required:
        - 5min
        - 1h
        - 4h
        - 24h
      properties:
        5min:
          type: number
          nullable: true
        1h:
          type: number
          nullable: true
        4h:
          type: number
          nullable: true
        24h:
          type: number
          nullable: true
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

# Pair Stats

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /pairs/{address}/stats
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
  /pairs/{address}/stats:
    get:
      tags:
        - Token
      summary: Get stats by pair address
      description: >-
        Access key statistics for a token pair, such as price, buyers, sellers,
        liquidity, volume and more.
      operationId: getPairStats
      parameters:
        - in: path
          name: address
          description: The pair address
          required: true
          schema:
            type: string
            example: '0xa43fe16908251ee70ef74718545e4fe6c5ccec9f'
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
      responses:
        '200':
          description: Returns the pair stats.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/pairStatsResponse'
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
    pairStatsResponse:
      type: object
      required:
        - tokenAddress
        - tokenName
        - tokenSymbol
        - tokenLogo
        - pairCreated
        - pairLabel
        - pairAddress
        - exchange
        - exchangeAddress
        - exchangeLogo
        - exchangeUrl
        - currentUsdPrice
        - currentNativePrice
        - totalLiquidityUsd
        - pricePercentChange
        - liquidityPercentChange
        - buys
        - sells
        - totalVolume
        - buyVolume
        - sellVolume
        - buyers
        - sellers
      properties:
        tokenAddress:
          type: string
          description: The token address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        tokenName:
          type: string
          description: The token name
          example: Wrapped Ether
          nullable: true
        tokenSymbol:
          type: string
          description: The token symbol
          example: WETH
          nullable: true
        tokenLogo:
          type: string
          description: The token image
          example: https://cdn.moralis.io/coins/images/2518/large/weth.png?1595348880
          nullable: true
        pairCreated:
          type: string
          description: The time when the pair was created
          example: '2021-04-02T10:07:54.000Z'
          nullable: true
        pairLabel:
          type: string
          description: The pair label
          example: WETH/PEPE
          nullable: true
        pairAddress:
          type: string
          description: The pair address
          example: '0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'
        exchange:
          type: string
          description: The exchange name
          example: Uniswap v2
          nullable: true
        exchangeAddress:
          type: string
          description: The exchange address
          example: '0x101cc05f4a51c0319f570d5e146a8c625198e222'
        exchangeLogo:
          type: string
          description: The exchange logo
          example: uniswap.png
          nullable: true
        exchangeUrl:
          type: string
          description: The exchange url
          example: app.uniswap.com
          nullable: true
        currentUsdPrice:
          type: string
          description: The current usd price
          example: '0.00000194'
          nullable: true
        currentNativePrice:
          type: string
          description: The current native price
          example: '0.0000000042'
          nullable: true
        totalLiquidityUsd:
          type: string
          description: The total liquidity in usd
          example: '43345522'
          nullable: true
        pricePercentChange:
          $ref: '#/components/schemas/candleSummary'
          type: object
        liquidityPercentChange:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buys:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sells:
          $ref: '#/components/schemas/candleSummary'
          type: object
        totalVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buyVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sellVolume:
          $ref: '#/components/schemas/candleSummary'
          type: object
        buyers:
          $ref: '#/components/schemas/candleSummary'
          type: object
        sellers:
          $ref: '#/components/schemas/candleSummary'
          type: object
    candleSummary:
      type: object
      required:
        - 5min
        - 1h
        - 4h
        - 24h
      properties:
        5min:
          type: number
          nullable: true
        1h:
          type: number
          nullable: true
        4h:
          type: number
          nullable: true
        24h:
          type: number
          nullable: true
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).

