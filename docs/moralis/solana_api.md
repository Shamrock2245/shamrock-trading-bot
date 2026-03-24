# Moralis Solana API

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana Data API

> A dedicated API for accessing Solana blockchain data with Solana-native semantics and structures.

### Overview

The **Solana Data API** provides **deep, Solana-native access** to Solana blockchain data, standardizing complex on-chain structures into clean, developer-friendly formats.

It is designed specifically around **Solana’s account model, programs, and transaction semantics**, rather than forcing Solana data into an EVM-style abstraction.

***

### What the Solana Data API Is For

The Solana Data API is built for:

* Applications focused exclusively on **Solana**
* Use cases that require **Solana-specific data models**
* Developers who need precise control over Solana program and account data

***

### Relationship to the Universal API

* The Universal API includes **shared EVM + Solana functionality**
* The Solana Data API provides **deeper Solana-specific coverage**
* Some Solana-specific endpoints are not available in the Universal API

As with EVM, not all Solana features are suitable for a fully universal abstraction.

***

### When to Use the Solana Data API

Use the Solana Data API if you:

* Are building a Solana-only application
* Need Solana-specific transaction or account details
* Want the most accurate representation of Solana on-chain behavior


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana Wallet API Overview

> Query Solana wallet data including native SOL balance, SPL token holdings, NFT balances, portfolio overview, and swap history.

## Overview

The **Solana Wallet API** provides complete wallet data for Solana addresses including native SOL balance, SPL token holdings, NFT balances, and trading activity.

Built specifically for Solana's account model, the Wallet API delivers the data you need to build wallets, portfolio trackers, and Solana-native applications.

***

## What Is the Solana Wallet API?

The Solana Wallet API lets you query:

* **Native Balance** - SOL balance for any wallet address
* **Token Balances** - SPL token holdings with metadata and prices
* **NFT Balances** - NFT holdings on Solana
* **Portfolio** - Complete portfolio overview with valuations
* **Swaps** - DEX trading history on Solana

***

## Key Features

* **Native SOL Balance** - Current SOL holdings with USD value
* **SPL Token Support** - All SPL tokens with metadata
* **NFT Holdings** - Solana NFT balances and metadata
* **Portfolio Valuation** - Total portfolio value in USD
* **Swap History** - Trading activity on Solana DEXs
* **Real-Time Data** - Up-to-date wallet state

***

## Common Use Cases

* **Solana Wallets**\
  (display SOL and token balances)
* **Portfolio Trackers**\
  (aggregate holdings with valuations)
* **Trading Apps**\
  (show swap history and activity)
* **NFT Galleries**\
  (display Solana NFT collections)
* **DeFi Dashboards**\
  (track wallet activity on Solana)

***

## Get Started

Explore the Solana Wallet API endpoints:

* [**Native Balance**](/data-api/solana/wallet/native-balance) - Get SOL balance
* [**Token Balances**](/data-api/solana/wallet/token-balances) - Get SPL token holdings
* [**NFT Balances**](/data-api/solana/wallet/nft-balances) - Get NFT holdings
* [**Portfolio**](/data-api/solana/wallet/portfolio) - Get complete portfolio
* [**Wallet Swaps**](/data-api/solana/wallet/wallet-swaps) - Get swap history


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Native Balance

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /account/{network}/{address}/balance
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /account/{network}/{address}/balance:
    get:
      tags:
        - Account
      summary: Gets native balance owned by the given address
      description: Gets native balance owned by the given address
      operationId: balance
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: kXB7FfzdrfZpAZEW3TZcp8a8CwQbsowa6BdfAHZ4gVs
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NativeBalance'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    NativeBalance:
      type: object
      properties:
        solana:
          type: string
        lamports:
          type: string
      required:
        - solana
        - lamports
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Portfolio

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /account/{network}/{address}/portfolio
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /account/{network}/{address}/portfolio:
    get:
      tags:
        - Account
      summary: Gets the portfolio of the given address
      description: Gets all the native and token balances of the given address
      operationId: getPortfolio
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: kXB7FfzdrfZpAZEW3TZcp8a8CwQbsowa6BdfAHZ4gVs
            type: string
        - name: nftMetadata
          required: false
          in: query
          description: Should return the full NFT metadata
          schema:
            default: false
            type: boolean
        - name: mediaItems
          required: false
          in: query
          description: Should return media items
          schema:
            default: false
            type: boolean
        - name: excludeSpam
          required: false
          in: query
          description: Should exclude spam NFTs
          schema:
            default: false
            type: boolean
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Portfolio'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    Portfolio:
      type: object
      properties:
        nativeBalance:
          $ref: '#/components/schemas/NativeBalance'
        nfts:
          type: array
          items:
            $ref: '#/components/schemas/SPLNFT'
        tokens:
          type: array
          items:
            $ref: '#/components/schemas/SPLTokenBalance'
      required:
        - nativeBalance
        - nfts
        - tokens
    NativeBalance:
      type: object
      properties:
        solana:
          type: string
        lamports:
          type: string
      required:
        - solana
        - lamports
    SPLNFT:
      type: object
      properties:
        associatedTokenAddress:
          type: string
        mint:
          type: string
        name:
          type: string
        symbol:
          type: string
        tokenStandard:
          type: number
          nullable: true
        amount:
          type: string
        amountRaw:
          type: string
        decimals:
          type: number
        possibleSpam:
          type: boolean
        totalSupply:
          type: string
        attributes:
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataAttributeDto'
        contract:
          $ref: '#/components/schemas/NFTMetadataContractDto'
        collection:
          $ref: '#/components/schemas/NFTMetadataCollectionDto'
        firstCreated:
          $ref: '#/components/schemas/NFTMetadataFirstCreatedDto'
        creators:
          nullable: true
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataCreatorDto'
        properties:
          type: object
          nullable: true
        media:
          nullable: true
          allOf:
            - $ref: '#/components/schemas/Media'
      required:
        - associatedTokenAddress
        - mint
        - name
        - symbol
        - tokenStandard
        - amount
        - amountRaw
        - decimals
        - possibleSpam
    SPLTokenBalance:
      type: object
      properties:
        associatedTokenAddress:
          type: string
        mint:
          type: string
        name:
          type: string
        symbol:
          type: string
        tokenStandard:
          type: number
          nullable: true
        score:
          type: number
          nullable: true
        amount:
          type: string
        amountRaw:
          type: string
        decimals:
          type: number
        logo:
          type: string
          nullable: true
        isVerifiedContract:
          type: boolean
        possibleSpam:
          type: boolean
      required:
        - associatedTokenAddress
        - mint
        - name
        - symbol
        - tokenStandard
        - score
        - amount
        - amountRaw
        - decimals
        - logo
        - isVerifiedContract
        - possibleSpam
    NFTMetadataAttributeDto:
      type: object
      properties:
        traitType:
          type: string
          nullable: true
        value:
          type: object
      required:
        - traitType
        - value
    NFTMetadataContractDto:
      type: object
      properties:
        type:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
      required:
        - type
        - name
        - symbol
    NFTMetadataCollectionDto:
      type: object
      properties:
        collectionAddress:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        description:
          type: string
          nullable: true
        imageOriginalUrl:
          type: string
          nullable: true
        externalUrl:
          type: string
          nullable: true
        metaplexMint:
          type: string
          nullable: true
        sellerFeeBasisPoints:
          type: number
          nullable: true
      required:
        - collectionAddress
        - name
        - description
        - imageOriginalUrl
        - externalUrl
        - metaplexMint
        - sellerFeeBasisPoints
    NFTMetadataFirstCreatedDto:
      type: object
      properties:
        mintTimestamp:
          type: number
          nullable: true
        mintBlockNumber:
          type: number
          nullable: true
        mintTransaction:
          type: string
          nullable: true
      required:
        - mintTimestamp
        - mintBlockNumber
        - mintTransaction
    NFTMetadataCreatorDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
        share:
          type: number
          nullable: true
        verified:
          type: boolean
          nullable: true
      required:
        - address
        - share
        - verified
    Media:
      type: object
      properties:
        mimetype:
          type: string
        category:
          type: string
        originalMediaUrl:
          type: string
        status:
          type: string
        updatedAt:
          type: string
        mediaCollection:
          $ref: '#/components/schemas/MediaCollection'
    MediaCollection:
      type: object
      properties:
        low:
          $ref: '#/components/schemas/MediaItem'
        medium:
          $ref: '#/components/schemas/MediaItem'
        high:
          $ref: '#/components/schemas/MediaItem'
    MediaItem:
      type: object
      properties:
        width:
          type: number
        height:
          type: number
        url:
          type: string
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Balances

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /account/{network}/{address}/tokens
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /account/{network}/{address}/tokens:
    get:
      tags:
        - Account
      summary: Gets token balances owned by the given address
      description: Gets token balances owned by the given address
      operationId: getSPL
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: kXB7FfzdrfZpAZEW3TZcp8a8CwQbsowa6BdfAHZ4gVs
            type: string
        - name: excludeSpam
          required: false
          in: query
          description: Should exclude spam tokens
          schema:
            default: false
            type: boolean
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/SPLTokenBalance'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SPLTokenBalance:
      type: object
      properties:
        associatedTokenAddress:
          type: string
        mint:
          type: string
        name:
          type: string
        symbol:
          type: string
        tokenStandard:
          type: number
          nullable: true
        score:
          type: number
          nullable: true
        amount:
          type: string
        amountRaw:
          type: string
        decimals:
          type: number
        logo:
          type: string
          nullable: true
        isVerifiedContract:
          type: boolean
        possibleSpam:
          type: boolean
      required:
        - associatedTokenAddress
        - mint
        - name
        - symbol
        - tokenStandard
        - score
        - amount
        - amountRaw
        - decimals
        - logo
        - isVerifiedContract
        - possibleSpam
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# NFT Balances

export const CUs_0 = 10

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /account/{network}/{address}/nft
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /account/{network}/{address}/nft:
    get:
      tags:
        - Account
      summary: Gets NFTs owned by the given address
      description: Gets NFTs owned by the given address
      operationId: getNFTs
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: kXB7FfzdrfZpAZEW3TZcp8a8CwQbsowa6BdfAHZ4gVs
            type: string
        - name: nftMetadata
          required: false
          in: query
          description: Should return the full NFT metadata
          schema:
            default: false
            type: boolean
        - name: mediaItems
          required: false
          in: query
          description: Should return media items
          schema:
            default: false
            type: boolean
        - name: excludeSpam
          required: false
          in: query
          description: Should exclude spam NFTs
          schema:
            default: false
            type: boolean
        - name: includeFungibleAssets
          required: false
          in: query
          description: Should include fungible assets (tokenStandard:1)
          schema:
            default: false
            type: boolean
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/SPLNFT'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SPLNFT:
      type: object
      properties:
        associatedTokenAddress:
          type: string
        mint:
          type: string
        name:
          type: string
        symbol:
          type: string
        tokenStandard:
          type: number
          nullable: true
        amount:
          type: string
        amountRaw:
          type: string
        decimals:
          type: number
        possibleSpam:
          type: boolean
        totalSupply:
          type: string
        attributes:
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataAttributeDto'
        contract:
          $ref: '#/components/schemas/NFTMetadataContractDto'
        collection:
          $ref: '#/components/schemas/NFTMetadataCollectionDto'
        firstCreated:
          $ref: '#/components/schemas/NFTMetadataFirstCreatedDto'
        creators:
          nullable: true
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataCreatorDto'
        properties:
          type: object
          nullable: true
        media:
          nullable: true
          allOf:
            - $ref: '#/components/schemas/Media'
      required:
        - associatedTokenAddress
        - mint
        - name
        - symbol
        - tokenStandard
        - amount
        - amountRaw
        - decimals
        - possibleSpam
    NFTMetadataAttributeDto:
      type: object
      properties:
        traitType:
          type: string
          nullable: true
        value:
          type: object
      required:
        - traitType
        - value
    NFTMetadataContractDto:
      type: object
      properties:
        type:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
      required:
        - type
        - name
        - symbol
    NFTMetadataCollectionDto:
      type: object
      properties:
        collectionAddress:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        description:
          type: string
          nullable: true
        imageOriginalUrl:
          type: string
          nullable: true
        externalUrl:
          type: string
          nullable: true
        metaplexMint:
          type: string
          nullable: true
        sellerFeeBasisPoints:
          type: number
          nullable: true
      required:
        - collectionAddress
        - name
        - description
        - imageOriginalUrl
        - externalUrl
        - metaplexMint
        - sellerFeeBasisPoints
    NFTMetadataFirstCreatedDto:
      type: object
      properties:
        mintTimestamp:
          type: number
          nullable: true
        mintBlockNumber:
          type: number
          nullable: true
        mintTransaction:
          type: string
          nullable: true
      required:
        - mintTimestamp
        - mintBlockNumber
        - mintTransaction
    NFTMetadataCreatorDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
        share:
          type: number
          nullable: true
        verified:
          type: boolean
          nullable: true
      required:
        - address
        - share
        - verified
    Media:
      type: object
      properties:
        mimetype:
          type: string
        category:
          type: string
        originalMediaUrl:
          type: string
        status:
          type: string
        updatedAt:
          type: string
        mediaCollection:
          $ref: '#/components/schemas/MediaCollection'
    MediaCollection:
      type: object
      properties:
        low:
          $ref: '#/components/schemas/MediaItem'
        medium:
          $ref: '#/components/schemas/MediaItem'
        high:
          $ref: '#/components/schemas/MediaItem'
    MediaItem:
      type: object
      properties:
        width:
          type: number
        height:
          type: number
        url:
          type: string
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /account/{network}/{address}/swaps
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /account/{network}/{address}/swaps:
    get:
      tags:
        - Account
      summary: >-
        Get all swap related transactions (buy, sell) for a specific wallet
        address.
      description: >-
        Get all swap related transactions (buy, sell) for a specific wallet
        address.
      operationId: getSwapsByWalletAddress
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: kXB7FfzdrfZpAZEW3TZcp8a8CwQbsowa6BdfAHZ4gVs
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: order
          required: false
          in: query
          description: The order of items
          schema:
            default: DESC
            enum:
              - ASC
              - DESC
            type: string
        - name: fromDate
          required: false
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: toDate
          required: false
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: transactionTypes
          required: false
          in: query
          description: >-
            Transaction types to fetch. Possible values: 'buy','sell' or both
            separated by comma
          schema:
            default: buy,sell
            example: buy,sell
            type: string
        - name: tokenAddress
          required: false
          in: query
          description: Token address to get transactions for
          schema:
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetSwapsByWalletAddressResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetSwapsByWalletAddressResponseDto:
      type: object
      properties:
        page:
          type: number
        pageSize:
          type: number
        cursor:
          type: string
          nullable: true
        result:
          type: array
          items:
            $ref: '#/components/schemas/SwapTransactionForWalletAndTokenDto'
      required:
        - page
        - pageSize
        - cursor
        - result
    SwapTransactionForWalletAndTokenDto:
      type: object
      properties:
        transactionHash:
          type: string
          example: '0xafc66b9b1802618f560be5244395f0fc0b95a1f1fdeee7a206acbb546c9e8a72'
        transactionIndex:
          type: number
          example: 5
        transactionType:
          type: string
          example: buy
        blockNumber:
          type: number
          example: 12345678
        blockTimestamp:
          type: string
          example: '2024-11-21T09:22:28.000Z'
        subCategory:
          type: string
          nullable: true
          example: ACCUMULATION
        walletAddress:
          type: string
          example: '0x1c584a6baecb7c5d51caa0ef3a579e08bd49d4e5'
        pairAddress:
          type: string
          nullable: true
          example: '0xdded227d71a096c6b5d87807c1b5c456771aaa94'
        pairLabel:
          type: string
          nullable: true
          example: USDC/WETH
        exchangeAddress:
          type: string
          nullable: true
          example: '0x1080ee857d165186af7f8d63e8ec510c28a6d1ea'
        exchangeName:
          type: string
          nullable: true
          example: Uniswap
        exchangeLogo:
          type: string
          nullable: true
          example: >-
            https://logo.moralis.io/0xe708_0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f_769a0b766bd3d6d1830f0a95d7b3e313
        baseToken:
          type: string
          nullable: true
          example: ETH
        quoteToken:
          type: string
          nullable: true
          example: USDT
        bought:
          nullable: true
          example:
            address: '0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f'
            name: Wrapped Ether
            symbol: SYM
            logo: https://example.com/logo-token1.png
            amount: '0.000014332429005002'
            usdPrice: 3148.1828278180296
            usdAmount: 1230
            tokenType: token1
          allOf:
            - $ref: '#/components/schemas/SwapTokenMetadataDto'
        sold:
          nullable: true
          example:
            address: '0x176211869ca2b568f2a7d4ee941e073a821ee1ff'
            name: USDC
            symbol: SYM
            logo: https://example.com/logo-token2.png
            amount: '1000'
            usdPrice: 0.9999999999999986
            usdAmount: -0.045138999999999936
            tokenType: token0
          allOf:
            - $ref: '#/components/schemas/SwapTokenMetadataDto'
        baseQuotePrice:
          type: string
          nullable: true
          example: '0.01'
        totalValueUsd:
          type: number
          nullable: true
          example: 1230
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - blockNumber
        - blockTimestamp
        - subCategory
        - walletAddress
        - pairAddress
        - pairLabel
        - exchangeAddress
        - exchangeName
        - exchangeLogo
        - baseToken
        - quoteToken
        - bought
        - sold
        - baseQuotePrice
        - totalValueUsd
    SwapTokenMetadataDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
          example: '0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f'
        name:
          type: string
          nullable: true
          example: Wrapped Ether
        symbol:
          type: string
          nullable: true
          example: WETH
        logo:
          type: string
          nullable: true
          example: >-
            https://logo.moralis.io/0xe708_0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f_769a0b766bd3d6d1830f0a95d7b3e313
        amount:
          type: string
          nullable: true
          example: '0.000014332429005002'
        usdPrice:
          type: number
          nullable: true
          example: 3148.1828278180296
        usdAmount:
          type: number
          nullable: true
          example: 0.0123
        tokenType:
          type: string
          nullable: true
          example: token1
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
        - tokenType
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana Token API Overview

> Comprehensive Solana token data including metadata, prices, holders, swaps, pairs, and advanced analytics for SPL tokens.

## Overview

The **Solana Token API** provides complete SPL token data including metadata, real-time prices, holder analytics, swap history, trading pairs, and advanced market metrics.

From basic token lookups to complex analytics, the Token API delivers everything you need to build trading platforms and token analysis tools on Solana.

***

## What Is the Solana Token API?

The Solana Token API lets you query:

* **Metadata** - Token details including name, symbol, and logo
* **Prices** - Real-time and historical token prices with OHLC data
* **Holders** - Top holders, holder metrics, and historical data
* **Swaps** - DEX trading activity and swap history
* **Pairs** - Trading pairs with liquidity and stats
* **Discovery** - Search tokens, find gainers/losers, track new launches

***

## Key Features

* **Real-Time Prices** - Current token prices with USD values
* **OHLC Data** - Candlestick data for charting
* **Holder Analytics** - Top holders and distribution metrics
* **Historical Holders** - Track holder changes over time
* **Swap Tracking** - DEX trades on Raydium, Orca, and more
* **Pair Stats** - Liquidity, volume, and trading metrics
* **Token Search** - Find tokens by name or address
* **Pump.fun Integration** - Track new and graduated tokens
* **Top Movers** - Discover top gainers and losers
* **Token Score** - Quality and safety metrics

***

## Common Use Cases

* **Trading Platforms**\
  (prices, charts, swap execution)
* **Token Analytics**\
  (holder distribution, volume, metrics)
* **DEX Interfaces**\
  (pair discovery, liquidity data)
* **Token Screeners**\
  (filter and discover tokens)
* **New Token Tracking**\
  (monitor Pump.fun launches)
* **Research Tools**\
  (token metrics and analysis)

***

## Get Started

Explore the Solana Token API endpoints:

* [**Token Metadata**](/data-api/solana/token/token-metadata) - Get token details
* [**Token Price**](/data-api/solana/token/prices/token-price) - Get current price
* [**OHLC**](/data-api/solana/token/prices/ohlc) - Get candlestick data
* [**Top Holders**](/data-api/solana/token/holders/top-holders) - Get holder list
* [**Token Swaps**](/data-api/solana/token/swaps/token-swaps) - Get swap history
* [**Token Pairs**](/data-api/solana/token/pairs/token-pairs) - Get trading pairs
* [**Token Search**](/data-api/solana/token/search-and-discovery/token-search) - Search tokens


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana NFT API Overview

> Query Solana NFT metadata including token details, attributes, and media URLs.

## Overview

The **Solana NFT API** provides NFT metadata for tokens on the Solana blockchain, including attributes, media URLs, and collection information.

Built for Solana's unique NFT standards, the API delivers the data you need to display and work with Solana NFTs.

***

## What Is the Solana NFT API?

The Solana NFT API lets you query:

* **NFT Metadata** - Token metadata including name, symbol, and description
* **Attributes** - NFT traits and properties
* **Media** - Image and media URLs
* **Collection Info** - Collection-level metadata

***

## Key Features

* **Complete Metadata** - Full NFT metadata with all attributes
* **Media Resolution** - Resolved media URLs for display
* **Solana Standards** - Support for Metaplex and other Solana NFT standards
* **Fast Queries** - Optimized for quick metadata retrieval

***

## Common Use Cases

* **NFT Galleries**\
  (display Solana NFT collections)
* **Wallet Apps**\
  (show NFT holdings with metadata)
* **Marketplaces**\
  (NFT listings with full details)
* **Portfolio Trackers**\
  (include NFTs in portfolio views)

***

## Get Started

Explore the Solana NFT API endpoints:

* [**NFT Metadata**](/data-api/solana/nft/nft-metadata) - Get metadata for a Solana NFT


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# NFT Metadata

export const CUs_0 = 20

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /nft/{network}/{address}/metadata
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /nft/{network}/{address}/metadata:
    get:
      tags:
        - NFT
      summary: Get the global metadata for a given contract
      description: >-
        Gets the contract level metadata (mint, standard, name, symbol,
        metaplex) for the given contract
      operationId: getNFTMetadata
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
        - name: mediaItems
          required: false
          in: query
          description: Should return media items
          schema:
            default: true
            type: boolean
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NFTMetadata'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    NFTMetadata:
      type: object
      properties:
        mint:
          type: string
        address:
          type: string
        standard:
          type: string
        name:
          type: string
        symbol:
          type: string
        tokenStandard:
          type: number
          nullable: true
        description:
          type: string
          nullable: true
        imageOriginalUrl:
          type: string
          nullable: true
        externalUrl:
          type: string
          nullable: true
        metadataOriginalUrl:
          type: string
          nullable: true
        totalSupply:
          type: string
        metaplex:
          $ref: '#/components/schemas/NFTMetaplex'
        attributes:
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataAttributeDto'
        contract:
          $ref: '#/components/schemas/NFTMetadataContractDto'
        collection:
          $ref: '#/components/schemas/NFTMetadataCollectionDto'
        firstCreated:
          $ref: '#/components/schemas/NFTMetadataFirstCreatedDto'
        creators:
          nullable: true
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataCreatorDto'
        properties:
          type: object
          nullable: true
        media:
          nullable: true
          allOf:
            - $ref: '#/components/schemas/Media'
        possibleSpam:
          type: boolean
      required:
        - mint
        - address
        - standard
        - name
        - symbol
        - tokenStandard
        - description
        - imageOriginalUrl
        - externalUrl
        - metadataOriginalUrl
        - totalSupply
        - metaplex
        - attributes
        - contract
        - collection
        - firstCreated
        - creators
        - properties
        - media
        - possibleSpam
    NFTMetaplex:
      type: object
      properties:
        metadataUri:
          type: string
          nullable: true
        masterEdition:
          type: boolean
        isMutable:
          type: boolean
        primarySaleHappened:
          type: number
        sellerFeeBasisPoints:
          type: number
        updateAuthority:
          type: string
          nullable: true
      required:
        - metadataUri
        - masterEdition
        - isMutable
        - primarySaleHappened
        - sellerFeeBasisPoints
        - updateAuthority
    NFTMetadataAttributeDto:
      type: object
      properties:
        traitType:
          type: string
          nullable: true
        value:
          type: object
      required:
        - traitType
        - value
    NFTMetadataContractDto:
      type: object
      properties:
        type:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
      required:
        - type
        - name
        - symbol
    NFTMetadataCollectionDto:
      type: object
      properties:
        collectionAddress:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        description:
          type: string
          nullable: true
        imageOriginalUrl:
          type: string
          nullable: true
        externalUrl:
          type: string
          nullable: true
        metaplexMint:
          type: string
          nullable: true
        sellerFeeBasisPoints:
          type: number
          nullable: true
      required:
        - collectionAddress
        - name
        - description
        - imageOriginalUrl
        - externalUrl
        - metaplexMint
        - sellerFeeBasisPoints
    NFTMetadataFirstCreatedDto:
      type: object
      properties:
        mintTimestamp:
          type: number
          nullable: true
        mintBlockNumber:
          type: number
          nullable: true
        mintTransaction:
          type: string
          nullable: true
      required:
        - mintTimestamp
        - mintBlockNumber
        - mintTransaction
    NFTMetadataCreatorDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
        share:
          type: number
          nullable: true
        verified:
          type: boolean
          nullable: true
      required:
        - address
        - share
        - verified
    Media:
      type: object
      properties:
        mimetype:
          type: string
        category:
          type: string
        originalMediaUrl:
          type: string
        status:
          type: string
        updatedAt:
          type: string
        mediaCollection:
          $ref: '#/components/schemas/MediaCollection'
    MediaCollection:
      type: object
      properties:
        low:
          $ref: '#/components/schemas/MediaItem'
        medium:
          $ref: '#/components/schemas/MediaItem'
        high:
          $ref: '#/components/schemas/MediaItem'
    MediaItem:
      type: object
      properties:
        width:
          type: number
        height:
          type: number
        url:
          type: string
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana Price API Overview

> Real-time and historical price data for Solana SPL tokens including current prices, batch queries, and OHLC candlestick data.

## Overview

The **Solana Price API** provides real-time and historical pricing data for SPL tokens on Solana, including current prices, batch queries, and OHLC candlestick data for charting.

Get accurate token prices without managing your own price feeds or aggregation infrastructure.

***

## What Is the Solana Price API?

The Solana Price API lets you query:

* **Token Prices** - Current USD prices for any SPL token
* **Batch Prices** - Fetch prices for multiple tokens in one request
* **OHLC Data** - Candlestick data for charting and technical analysis

***

## Key Features

* **Real-Time Prices** - Current token prices with USD values
* **Batch Support** - Query multiple tokens efficiently
* **OHLC Candles** - Open, high, low, close data for charts
* **Historical Data** - Price history for trend analysis
* **Fast Response** - Optimized for low-latency queries

***

## Common Use Cases

* **Price Feeds**\
  (display current token prices)
* **Trading Charts**\
  (OHLC data for candlestick visualizations)
* **Portfolio Valuation**\
  (calculate holdings value in USD)
* **Price Alerts**\
  (trigger notifications on price changes)
* **Market Dashboards**\
  (aggregate pricing across tokens)

***

## Get Started

Explore the Solana Price API endpoints:

* [**Token Price**](/data-api/solana/price/token-price) - Get current price for a token
* [**Token Prices (Batch)**](/data-api/solana/price/token-prices-batch) - Get prices for multiple tokens
* [**OHLC**](/data-api/solana/price/ohlc) - Get candlestick data for charting


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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/{address}/price
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/{address}/price:
    get:
      tags:
        - Token
      summary: Get token price
      description: >-
        Gets the token price (usd and native) for a given contract address and
        network.
      operationId: getTokenPrice
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
      responses:
        '200':
          description: ''
        default:
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SPLTokenPrice'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SPLTokenPrice:
      type: object
      properties:
        tokenAddress:
          type: string
        pairAddress:
          type: string
        nativePrice:
          $ref: '#/components/schemas/SPLNativePrice'
        usdPrice:
          type: number
        exchangeAddress:
          type: string
        exchangeName:
          type: string
        logo:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        score:
          type: number
          nullable: true
        usdPrice24h:
          type: number
          nullable: true
        usdPrice24hrUsdChange:
          type: number
          nullable: true
        usdPrice24hrPercentChange:
          type: number
          nullable: true
        isVerifiedContract:
          type: boolean
          nullable: true
    SPLNativePrice:
      type: object
      properties:
        value:
          type: string
        decimals:
          type: number
        name:
          type: string
        symbol:
          type: string
      required:
        - value
        - decimals
        - name
        - symbol
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Price (Batch)

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json POST /token/{network}/prices
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/prices:
    post:
      tags:
        - Token
      summary: Get token price
      description: >-
        Gets the token price (usd and native) for a given contract address and
        network.
      operationId: getMultipleTokenPrices
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GetMultipleTokenPricesRequest'
      responses:
        '201':
          description: ''
        default:
          description: ''
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/SPLTokenPrice'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetMultipleTokenPricesRequest:
      type: object
      properties:
        addresses:
          minItems: 1
          maxItems: 100
          type: array
          items:
            type: string
      required:
        - addresses
    SPLTokenPrice:
      type: object
      properties:
        tokenAddress:
          type: string
        pairAddress:
          type: string
        nativePrice:
          $ref: '#/components/schemas/SPLNativePrice'
        usdPrice:
          type: number
        exchangeAddress:
          type: string
        exchangeName:
          type: string
        logo:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        score:
          type: number
          nullable: true
        usdPrice24h:
          type: number
          nullable: true
        usdPrice24hrUsdChange:
          type: number
          nullable: true
        usdPrice24hrPercentChange:
          type: number
          nullable: true
        isVerifiedContract:
          type: boolean
          nullable: true
    SPLNativePrice:
      type: object
      properties:
        value:
          type: string
        decimals:
          type: number
        name:
          type: string
        symbol:
          type: string
      required:
        - value
        - decimals
        - name
        - symbol
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/pairs/{address}/ohlcv
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/pairs/{address}/ohlcv:
    get:
      tags:
        - Token
      summary: Get candlesticks for a pair address
      description: Gets the candlesticks for a specific pair address
      operationId: getCandleSticks
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: fromDate
          required: true
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            default: '2024-10-09'
            type: string
        - name: toDate
          required: true
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            default: '2024-10-10'
            type: string
        - name: timeframe
          required: true
          in: query
          description: The interval of the candle stick
          schema:
            default: 1min
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
            type: string
        - name: currency
          required: true
          in: query
          description: The currency format
          schema:
            default: usd
            enum:
              - usd
              - native
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 1000
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetCandleSticksResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetCandleSticksResponse:
      type: object
      properties:
        cursor:
          type: string
          nullable: true
          description: The cursor to the next page
        page:
          type: number
          description: The page number
        pairAddress:
          type: string
          description: The pair address
        tokenAddress:
          type: string
          nullable: true
          description: The token address
        timeframe:
          type: string
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
          description: The interval of the candle stick
          default: 1min
        currency:
          type: string
          default: usd
          enum:
            - usd
            - native
          description: The currency format
        result:
          description: An array of candlesticks
          type: array
          items:
            $ref: '#/components/schemas/Ohlcv'
      required:
        - page
        - pairAddress
        - tokenAddress
        - timeframe
        - currency
    Ohlcv:
      type: object
      properties:
        timestamp:
          type: string
          nullable: true
          description: ''
        open:
          type: number
          nullable: true
          description: ''
        close:
          type: number
          nullable: true
          description: ''
        high:
          type: number
          nullable: true
          description: ''
        low:
          type: number
          nullable: true
          description: ''
        volume:
          type: number
          nullable: true
          description: ''
        trades:
          type: number
          description: ''
      required:
        - timestamp
        - open
        - close
        - high
        - low
        - volume
        - trades
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/{address}/top-holders
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/{address}/top-holders:
    get:
      tags:
        - Token
      summary: Get paginated top holders for a given token.
      operationId: getTopHolders
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
            type: string
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetTopHoldersResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetTopHoldersResponseDto:
      type: object
      properties:
        result:
          default: []
          description: The list of top holders
          type: array
          items:
            $ref: '#/components/schemas/TopHolderResultDto'
        cursor:
          type: string
          description: The cursor to fetch the next page
        page:
          type: number
          description: The page number
        pageSize:
          type: number
          description: The page size
        totalSupply:
          type: string
          description: The total supply of the token
      required:
        - result
        - page
        - pageSize
        - totalSupply
    TopHolderResultDto:
      type: object
      properties:
        balance:
          type: string
        balanceFormatted:
          type: string
        isContract:
          type: boolean
        ownerAddress:
          type: string
        usdValue:
          type: string
          nullable: true
          default: null
        percentageRelativeToTotalSupply:
          type: number
      required:
        - balance
        - balanceFormatted
        - isContract
        - ownerAddress
        - usdValue
        - percentageRelativeToTotalSupply
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/holders/{address}
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/holders/{address}:
    get:
      tags:
        - Token
      summary: Get the summary of holders for a given token token.
      operationId: getTokenHolders
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: 6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetTokenHoldersResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetTokenHoldersResponseDto:
      type: object
      properties:
        totalHolders:
          type: number
          example: 5000
        holdersByAcquisition:
          $ref: '#/components/schemas/HoldersByAcquisitionDto'
        holderChange:
          $ref: '#/components/schemas/HolderChangeSummaryDTO'
        holderDistribution:
          $ref: '#/components/schemas/HolderDistributionDto'
        holderSupply:
          $ref: '#/components/schemas/HolderSupplyDto'
      required:
        - totalHolders
        - holdersByAcquisition
        - holderChange
        - holderDistribution
        - holderSupply
    HoldersByAcquisitionDto:
      type: object
      properties:
        swap:
          type: number
          example: 150
        transfer:
          type: number
          example: 50
        airdrop:
          type: number
          example: 20
      required:
        - swap
        - transfer
        - airdrop
    HolderChangeSummaryDTO:
      type: object
      properties:
        5min:
          $ref: '#/components/schemas/HolderChangeDto'
        1h:
          $ref: '#/components/schemas/HolderChangeDto'
        6h:
          $ref: '#/components/schemas/HolderChangeDto'
        24h:
          $ref: '#/components/schemas/HolderChangeDto'
        3d:
          $ref: '#/components/schemas/HolderChangeDto'
        7d:
          $ref: '#/components/schemas/HolderChangeDto'
        30d:
          $ref: '#/components/schemas/HolderChangeDto'
      required:
        - 5min
        - 1h
        - 6h
        - 24h
        - 3d
        - 7d
        - 30d
    HolderDistributionDto:
      type: object
      properties:
        whales:
          type: number
          example: 150
        sharks:
          type: number
          example: 150
        dolphins:
          type: number
          example: 150
        fish:
          type: number
          example: 150
        octopus:
          type: number
          example: 150
        crabs:
          type: number
          example: 150
        shrimps:
          type: number
          example: 150
      required:
        - whales
        - sharks
        - dolphins
        - fish
        - octopus
        - crabs
        - shrimps
    HolderSupplyDto:
      type: object
      properties:
        top10:
          $ref: '#/components/schemas/HolderSupplyChangeDto'
        top25:
          $ref: '#/components/schemas/HolderSupplyChangeDto'
        top50:
          $ref: '#/components/schemas/HolderSupplyChangeDto'
        top100:
          $ref: '#/components/schemas/HolderSupplyChangeDto'
        top250:
          $ref: '#/components/schemas/HolderSupplyChangeDto'
        top500:
          $ref: '#/components/schemas/HolderSupplyChangeDto'
      required:
        - top10
        - top25
        - top50
        - top100
        - top250
        - top500
    HolderChangeDto:
      type: object
      properties:
        change:
          type: number
          example: 50
        changePercent:
          type: number
          example: 2.5
      required:
        - change
        - changePercent
    HolderSupplyChangeDto:
      type: object
      properties:
        supply:
          type: string
          example: '1000000.123456'
        supplyPercent:
          type: number
          example: 12.5
      required:
        - supply
        - supplyPercent
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Historical Token Holders

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/holders/{address}/historical
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/holders/{address}/historical:
    get:
      tags:
        - Token
      summary: Get token holders overtime for a given tokens
      operationId: getHistoricalTokenHolders
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: 6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN
            type: string
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: timeFrame
          required: true
          in: query
          description: The interval of the holders data
          schema:
            default: 1min
            enum:
              - 1min
              - 5min
              - 10min
              - 30min
              - 1h
              - 4h
              - 12h
              - 1d
              - 1w
              - 1m
            type: string
        - name: fromDate
          required: true
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: toDate
          required: true
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page depending on the plan
          schema:
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetHistoricalHoldersResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetHistoricalHoldersResponseDto:
      type: object
      properties:
        cursor:
          type: string
          description: The cursor to the next page
        result:
          type: array
          items:
            $ref: '#/components/schemas/HolderTimelineItemDto'
        page:
          type: number
          description: The current page number
      required:
        - result
        - page
    HolderTimelineItemDto:
      type: object
      properties:
        timestamp:
          type: string
          example: '2025-02-25T00:00:00Z'
        totalHolders:
          type: number
          example: 2000
        netHolderChange:
          type: number
          example: 50
        holderPercentChange:
          type: number
          example: 2.5
        newHoldersByAcquisition:
          $ref: '#/components/schemas/NewHoldersByAcquisitionDTO'
        holdersIn:
          $ref: '#/components/schemas/HolderCategoryDTO'
        holdersOut:
          $ref: '#/components/schemas/HolderCategoryDTO'
      required:
        - timestamp
        - totalHolders
        - netHolderChange
        - holderPercentChange
        - newHoldersByAcquisition
        - holdersIn
        - holdersOut
    NewHoldersByAcquisitionDTO:
      type: object
      properties:
        swap:
          type: number
          example: 150
        transfer:
          type: number
          example: 50
        airdrop:
          type: number
          example: 20
      required:
        - swap
        - transfer
        - airdrop
    HolderCategoryDTO:
      type: object
      properties:
        whales:
          type: number
          example: 5
        sharks:
          type: number
          example: 12
        dolphins:
          type: number
          example: 20
        fish:
          type: number
          example: 100
        octopus:
          type: number
          example: 50
        crabs:
          type: number
          example: 200
        shrimps:
          type: number
          example: 1000
      required:
        - whales
        - sharks
        - dolphins
        - fish
        - octopus
        - crabs
        - shrimps
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/{address}/swaps
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/{address}/swaps:
    get:
      tags:
        - Token
      summary: Get all swap related transactions (buy, sell)
      description: >-
        Get all swap related transactions (buy, sell) for a specific token
        address.
      operationId: getSwapsByTokenAddress
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: fromDate
          required: false
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: toDate
          required: false
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: order
          required: false
          in: query
          description: The order of the results, in ascending (ASC) or descending (DESC).
          schema:
            default: DESC
            example: DESC
            enum:
              - ASC
              - DESC
            type: string
        - name: transactionTypes
          required: false
          in: query
          description: >-
            Transaction types to fetch. Possible values: 'buy','sell' or both
            separated by comma
          schema:
            default: buy,sell
            example: buy,sell
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetSwapsByTokenAddressResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetSwapsByTokenAddressResponseDto:
      type: object
      properties:
        page:
          type: number
          example: 1
        pageSize:
          type: number
          example: 100
        cursor:
          type: string
          nullable: true
          example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...Caaw
        result:
          type: array
          items:
            $ref: '#/components/schemas/SwapTransactionForWalletAndTokenDto'
      required:
        - page
        - pageSize
        - cursor
        - result
    SwapTransactionForWalletAndTokenDto:
      type: object
      properties:
        transactionHash:
          type: string
          example: '0xafc66b9b1802618f560be5244395f0fc0b95a1f1fdeee7a206acbb546c9e8a72'
        transactionIndex:
          type: number
          example: 5
        transactionType:
          type: string
          example: buy
        blockNumber:
          type: number
          example: 12345678
        blockTimestamp:
          type: string
          example: '2024-11-21T09:22:28.000Z'
        subCategory:
          type: string
          nullable: true
          example: ACCUMULATION
        walletAddress:
          type: string
          example: '0x1c584a6baecb7c5d51caa0ef3a579e08bd49d4e5'
        pairAddress:
          type: string
          nullable: true
          example: '0xdded227d71a096c6b5d87807c1b5c456771aaa94'
        pairLabel:
          type: string
          nullable: true
          example: USDC/WETH
        exchangeAddress:
          type: string
          nullable: true
          example: '0x1080ee857d165186af7f8d63e8ec510c28a6d1ea'
        exchangeName:
          type: string
          nullable: true
          example: Uniswap
        exchangeLogo:
          type: string
          nullable: true
          example: >-
            https://logo.moralis.io/0xe708_0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f_769a0b766bd3d6d1830f0a95d7b3e313
        baseToken:
          type: string
          nullable: true
          example: ETH
        quoteToken:
          type: string
          nullable: true
          example: USDT
        bought:
          nullable: true
          example:
            address: '0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f'
            name: Wrapped Ether
            symbol: SYM
            logo: https://example.com/logo-token1.png
            amount: '0.000014332429005002'
            usdPrice: 3148.1828278180296
            usdAmount: 1230
            tokenType: token1
          allOf:
            - $ref: '#/components/schemas/SwapTokenMetadataDto'
        sold:
          nullable: true
          example:
            address: '0x176211869ca2b568f2a7d4ee941e073a821ee1ff'
            name: USDC
            symbol: SYM
            logo: https://example.com/logo-token2.png
            amount: '1000'
            usdPrice: 0.9999999999999986
            usdAmount: -0.045138999999999936
            tokenType: token0
          allOf:
            - $ref: '#/components/schemas/SwapTokenMetadataDto'
        baseQuotePrice:
          type: string
          nullable: true
          example: '0.01'
        totalValueUsd:
          type: number
          nullable: true
          example: 1230
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - blockNumber
        - blockTimestamp
        - subCategory
        - walletAddress
        - pairAddress
        - pairLabel
        - exchangeAddress
        - exchangeName
        - exchangeLogo
        - baseToken
        - quoteToken
        - bought
        - sold
        - baseQuotePrice
        - totalValueUsd
    SwapTokenMetadataDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
          example: '0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f'
        name:
          type: string
          nullable: true
          example: Wrapped Ether
        symbol:
          type: string
          nullable: true
          example: WETH
        logo:
          type: string
          nullable: true
          example: >-
            https://logo.moralis.io/0xe708_0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f_769a0b766bd3d6d1830f0a95d7b3e313
        amount:
          type: string
          nullable: true
          example: '0.000014332429005002'
        usdPrice:
          type: number
          nullable: true
          example: 3148.1828278180296
        usdAmount:
          type: number
          nullable: true
          example: 0.0123
        tokenType:
          type: string
          nullable: true
          example: token1
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
        - tokenType
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/pairs/{pairAddress}/swaps
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/pairs/{pairAddress}/swaps:
    get:
      tags:
        - Token
      summary: >-
        Get all swap related transactions (buy, sell, add liquidity & remove
        liquidity)
      description: >-
        Get all swap related transactions (buy, sell, add liquidity & remove
        liquidity) for a specific pair address.
      operationId: getSwapsByPairAddress
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: pairAddress
          required: true
          in: path
          description: The address of the pair to query
          schema:
            example: Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: order
          required: false
          in: query
          description: The order of items
          schema:
            default: DESC
            enum:
              - ASC
              - DESC
            type: string
        - name: fromDate
          required: false
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: toDate
          required: false
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: transactionTypes
          required: false
          in: query
          description: >-
            Transaction types to fetch. Possible values: 'buy', 'sell',
            'addLiquidity' or 'removeLiquidity' separated by comma
          schema:
            default: buy,sell,addLiquidity,removeLiquidity
            example: buy,sell,addLiquidity,removeLiquidity
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetSwapsByPairAddressResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetSwapsByPairAddressResponse:
      type: object
      properties:
        page:
          type: number
          example: 1
        pageSize:
          type: number
          example: 100
        cursor:
          type: string
          nullable: true
          example: >-
            eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...kJ8E_653QrA4Q8zb_9OCn6opE9aBo8PjqLeQU_VCaaw
        exchangeName:
          type: string
          nullable: true
          example: Raydium AMM v4
        exchangeLogo:
          type: string
          nullable: true
          example: https://entities-logos.s3.amazonaws.com/raydium.png
        exchangeAddress:
          type: string
          nullable: true
          example: 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
        pairLabel:
          type: string
          nullable: true
          example: BREAD/SOL
        pairAddress:
          type: string
          nullable: true
          example: ALeyWh7zN979ZHUWY6YTMJC8wWowzdYqi8RRPRyB3LAd
        baseToken:
          $ref: '#/components/schemas/SwapsByPairAddressTokenMetadata'
        quoteToken:
          $ref: '#/components/schemas/SwapsByPairAddressTokenMetadata'
        result:
          type: array
          items:
            $ref: '#/components/schemas/SwapTransaction'
      required:
        - page
        - pageSize
        - cursor
        - exchangeName
        - exchangeLogo
        - exchangeAddress
        - pairLabel
        - pairAddress
        - baseToken
        - quoteToken
        - result
    SwapsByPairAddressTokenMetadata:
      type: object
      properties:
        address:
          type: string
          nullable: true
          example: madHpjRn6bd8t78Rsy7NuSuNwWa2HU8ByPobZprHbHv
        name:
          type: string
          nullable: true
          example: MAD
        symbol:
          type: string
          nullable: true
          example: MAD
        logo:
          type: string
          nullable: true
          example: >-
            https://ipfs.io/ipfs/QmeCR6o1FrYjczPdDDDm4623usKksjj9BQLu89WqV8jFZW?filename=MAD.jpg
        decimals:
          type: string
          nullable: true
          example: '18'
      required:
        - address
        - name
        - symbol
        - logo
        - decimals
    SwapTransaction:
      type: object
      properties:
        transactionHash:
          type: string
          nullable: true
          example: >-
            3o9NfCBWaDEb8JLJGdp8tfWwXURNokanCvUJf9A9f5nFqmZkRvWcfhkek4t47UhRDSGKHsSzi8MBusin8H7x7YYD
        transactionType:
          type: string
          nullable: true
          example: sell
        transactionIndex:
          type: number
          nullable: true
          example: 250
        subCategory:
          type: string
          nullable: true
          example: sellAll
        blockTimestamp:
          type: string
          nullable: true
          example: '2024-11-28T09:44:55.000Z'
        blockNumber:
          type: number
          example: 304108120
        walletAddress:
          type: string
          nullable: true
          example: A8GVZWGMxRAouFQymPoMKx527JhHKrBRuqFx7NET4j22
        baseTokenAmount:
          type: string
          nullable: true
          example: '199255.444466200'
        quoteTokenAmount:
          type: string
          nullable: true
          example: '0.007374998'
        baseTokenPriceUsd:
          type: number
          example: 0.000008794
        quoteTokenPriceUsd:
          type: number
          example: 237.60336565
        baseQuotePrice:
          type: string
          nullable: true
          example: '0.0000000370127'
        totalValueUsd:
          type: number
          example: 1.752324346
      required:
        - transactionHash
        - transactionType
        - transactionIndex
        - subCategory
        - blockTimestamp
        - blockNumber
        - walletAddress
        - baseTokenAmount
        - quoteTokenAmount
        - baseTokenPriceUsd
        - quoteTokenPriceUsd
        - baseQuotePrice
        - totalValueUsd
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Wallet Swaps

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /account/{network}/{address}/swaps
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /account/{network}/{address}/swaps:
    get:
      tags:
        - Account
      summary: >-
        Get all swap related transactions (buy, sell) for a specific wallet
        address.
      description: >-
        Get all swap related transactions (buy, sell) for a specific wallet
        address.
      operationId: getSwapsByWalletAddress
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            example: kXB7FfzdrfZpAZEW3TZcp8a8CwQbsowa6BdfAHZ4gVs
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: order
          required: false
          in: query
          description: The order of items
          schema:
            default: DESC
            enum:
              - ASC
              - DESC
            type: string
        - name: fromDate
          required: false
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: toDate
          required: false
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            type: string
        - name: transactionTypes
          required: false
          in: query
          description: >-
            Transaction types to fetch. Possible values: 'buy','sell' or both
            separated by comma
          schema:
            default: buy,sell
            example: buy,sell
            type: string
        - name: tokenAddress
          required: false
          in: query
          description: Token address to get transactions for
          schema:
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetSwapsByWalletAddressResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetSwapsByWalletAddressResponseDto:
      type: object
      properties:
        page:
          type: number
        pageSize:
          type: number
        cursor:
          type: string
          nullable: true
        result:
          type: array
          items:
            $ref: '#/components/schemas/SwapTransactionForWalletAndTokenDto'
      required:
        - page
        - pageSize
        - cursor
        - result
    SwapTransactionForWalletAndTokenDto:
      type: object
      properties:
        transactionHash:
          type: string
          example: '0xafc66b9b1802618f560be5244395f0fc0b95a1f1fdeee7a206acbb546c9e8a72'
        transactionIndex:
          type: number
          example: 5
        transactionType:
          type: string
          example: buy
        blockNumber:
          type: number
          example: 12345678
        blockTimestamp:
          type: string
          example: '2024-11-21T09:22:28.000Z'
        subCategory:
          type: string
          nullable: true
          example: ACCUMULATION
        walletAddress:
          type: string
          example: '0x1c584a6baecb7c5d51caa0ef3a579e08bd49d4e5'
        pairAddress:
          type: string
          nullable: true
          example: '0xdded227d71a096c6b5d87807c1b5c456771aaa94'
        pairLabel:
          type: string
          nullable: true
          example: USDC/WETH
        exchangeAddress:
          type: string
          nullable: true
          example: '0x1080ee857d165186af7f8d63e8ec510c28a6d1ea'
        exchangeName:
          type: string
          nullable: true
          example: Uniswap
        exchangeLogo:
          type: string
          nullable: true
          example: >-
            https://logo.moralis.io/0xe708_0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f_769a0b766bd3d6d1830f0a95d7b3e313
        baseToken:
          type: string
          nullable: true
          example: ETH
        quoteToken:
          type: string
          nullable: true
          example: USDT
        bought:
          nullable: true
          example:
            address: '0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f'
            name: Wrapped Ether
            symbol: SYM
            logo: https://example.com/logo-token1.png
            amount: '0.000014332429005002'
            usdPrice: 3148.1828278180296
            usdAmount: 1230
            tokenType: token1
          allOf:
            - $ref: '#/components/schemas/SwapTokenMetadataDto'
        sold:
          nullable: true
          example:
            address: '0x176211869ca2b568f2a7d4ee941e073a821ee1ff'
            name: USDC
            symbol: SYM
            logo: https://example.com/logo-token2.png
            amount: '1000'
            usdPrice: 0.9999999999999986
            usdAmount: -0.045138999999999936
            tokenType: token0
          allOf:
            - $ref: '#/components/schemas/SwapTokenMetadataDto'
        baseQuotePrice:
          type: string
          nullable: true
          example: '0.01'
        totalValueUsd:
          type: number
          nullable: true
          example: 1230
      required:
        - transactionHash
        - transactionIndex
        - transactionType
        - blockNumber
        - blockTimestamp
        - subCategory
        - walletAddress
        - pairAddress
        - pairLabel
        - exchangeAddress
        - exchangeName
        - exchangeLogo
        - baseToken
        - quoteToken
        - bought
        - sold
        - baseQuotePrice
        - totalValueUsd
    SwapTokenMetadataDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
          example: '0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f'
        name:
          type: string
          nullable: true
          example: Wrapped Ether
        symbol:
          type: string
          nullable: true
          example: WETH
        logo:
          type: string
          nullable: true
          example: >-
            https://logo.moralis.io/0xe708_0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f_769a0b766bd3d6d1830f0a95d7b3e313
        amount:
          type: string
          nullable: true
          example: '0.000014332429005002'
        usdPrice:
          type: number
          nullable: true
          example: 3148.1828278180296
        usdAmount:
          type: number
          nullable: true
          example: 0.0123
        tokenType:
          type: string
          nullable: true
          example: token1
      required:
        - address
        - name
        - symbol
        - logo
        - amount
        - usdPrice
        - usdAmount
        - tokenType
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Pairs

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/{address}/pairs
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/{address}/pairs:
    get:
      tags:
        - Token
      summary: Get token pairs by address
      description: Get the supported pairs for a specific token address.
      operationId: getTokenPairs
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 50
            default: 50
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SupportedPairResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SupportedPairResponse:
      type: object
      properties:
        cursor:
          type: string
          nullable: true
        pageSize:
          type: number
        page:
          type: number
        pairs:
          type: array
          items:
            $ref: '#/components/schemas/SupportedPairInfo'
      required:
        - cursor
        - pageSize
        - page
        - pairs
    SupportedPairInfo:
      type: object
      properties:
        exchangeAddress:
          type: string
        exchangeName:
          type: string
          nullable: true
        exchangeLogo:
          type: string
          nullable: true
        pairAddress:
          type: string
        pairLabel:
          type: string
          nullable: true
        usdPrice:
          type: number
          nullable: true
        usdPrice24hrPercentChange:
          type: number
          nullable: true
        usdPrice24hrUsdChange:
          type: number
          nullable: true
        volume24hrNative:
          type: number
          nullable: true
        volume24hrUsd:
          type: number
          nullable: true
        liquidityUsd:
          type: number
          nullable: true
        inactivePair:
          type: boolean
          nullable: true
        baseToken:
          type: string
        quoteToken:
          type: string
        pair:
          type: array
          items:
            $ref: '#/components/schemas/PairInfo'
      required:
        - exchangeAddress
        - exchangeName
        - exchangeLogo
        - pairAddress
        - pairLabel
        - usdPrice
        - usdPrice24hrPercentChange
        - usdPrice24hrUsdChange
        - volume24hrNative
        - volume24hrUsd
        - liquidityUsd
        - inactivePair
        - baseToken
        - quoteToken
        - pair
    PairInfo:
      type: object
      properties:
        tokenAddress:
          type: string
        tokenName:
          type: string
          nullable: true
        tokenSymbol:
          type: string
          nullable: true
        tokenLogo:
          type: string
          nullable: true
        tokenDecimals:
          type: string
          nullable: true
        pairTokenType:
          type: string
        liquidityUsd:
          type: number
          nullable: true
      required:
        - tokenAddress
        - tokenName
        - tokenSymbol
        - tokenLogo
        - tokenDecimals
        - pairTokenType
        - liquidityUsd
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/pairs/{pairAddress}/stats
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/pairs/{pairAddress}/stats:
    get:
      tags:
        - Token
      summary: Get stats for a pair address
      description: Gets the stats for a specific pair address
      operationId: getPairStats
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: pairAddress
          required: true
          in: path
          description: The address of the pair to query
          schema:
            example: Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE
            type: string
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetPairStatsResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetPairStatsResponse:
      type: object
      properties:
        tokenAddress:
          type: string
          description: The token address
        tokenName:
          type: string
          nullable: true
          description: The token name
        tokenSymbol:
          type: string
          nullable: true
          description: The token symbol
        tokenLogo:
          type: string
          nullable: true
          description: The token logo
        pairCreated:
          type: string
          nullable: true
          description: The timestamp when pair is created
        pairLabel:
          type: string
          nullable: true
          description: The pair label
        pairAddress:
          type: string
          description: The pair address
        exchange:
          type: string
          nullable: true
          description: The exchange name
        exchangeAddress:
          type: string
          description: The exchange address
        exchangeLogo:
          type: string
          nullable: true
          description: The exchange logo
        exchangeUrl:
          type: string
          nullable: true
          description: The exchange url
        currentUsdPrice:
          type: string
          nullable: true
          description: The current usd price of the token
        currentNativePrice:
          type: string
          nullable: true
          description: The current native price of the token
        totalLiquidityUsd:
          type: string
          nullable: true
          description: The total liquidity of the pair in USD
        pricePercentChange:
          description: The price percent change stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        liquidityPercentChange:
          description: The liquidity change stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        buys:
          description: The total buys stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        sells:
          description: The total sells stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        totalVolume:
          description: The total volume stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        buyVolume:
          description: The total buy volume stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        sellVolume:
          description: The total sell volume stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        buyers:
          description: The total unique buyers stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
        sellers:
          description: The total unique sellers stats
          allOf:
            - $ref: '#/components/schemas/PairStats'
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
    PairStats:
      type: object
      properties:
        5min:
          type: number
          nullable: true
          description: The 5 minutes timeframe data
        1h:
          type: number
          nullable: true
          description: The 1 hour timeframe data
        4h:
          type: number
          nullable: true
          description: The 4 hours timeframe data
        24h:
          type: number
          nullable: true
          description: The 24 hours timeframe data
      required:
        - 5min
        - 1h
        - 4h
        - 24h
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Analytics

> Retrieve detailed trading analytics for a specific token, including buy volume, sell volume, buyers, sellers, transactions, liquidity and FDV trends over time.

export const CUs_0 = 80

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /tokens/{tokenAddress}/analytics
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
  /tokens/{tokenAddress}/analytics:
    get:
      tags:
        - Token
      summary: Get token analytics by token address
      description: >-
        Retrieve detailed trading analytics for a specific token, including buy
        volume, sell volume, buyers, sellers, transactions, liquidity and FDV
        trends over time.
      operationId: getTokenAnalytics
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
                $ref: '#/components/schemas/TokenAnalyticsData'
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
    TokenAnalyticsData:
      type: object
      properties:
        categoryId:
          type: string
          example: '0x1'
        totalBuyVolume:
          $ref: '#/components/schemas/VolumeData'
        totalSellVolume:
          $ref: '#/components/schemas/VolumeData'
        totalBuyers:
          $ref: '#/components/schemas/VolumeData'
        totalSellers:
          $ref: '#/components/schemas/VolumeData'
        totalBuys:
          $ref: '#/components/schemas/VolumeData'
        totalSells:
          $ref: '#/components/schemas/VolumeData'
        uniqueWallets:
          $ref: '#/components/schemas/VolumeData'
        pricePercentChange:
          $ref: '#/components/schemas/VolumeData'
        usdPrice:
          type: string
          example: '530'
        totalLiquidity:
          type: string
          example: '530'
        totalFullyDilutedValuation:
          type: string
          example: '530'
    VolumeData:
      type: object
      properties:
        5m:
          type: number
          format: double
          example: 6516719.425429553
        1h:
          type: number
          format: double
          example: 137489621.30780438
        6h:
          type: number
          format: double
          example: 585436101.0503464
        24h:
          type: number
          format: double
          example: 2668170156.0409784
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

# Token Analytics (Batch)

> Fetch analytics for multiple tokens, including buy volume, sell volume, buyers, sellers, transactions, liquidity and FDV trends over time. Accepts an array of up to 200 tokens, each requiring chain and tokenAddress.

export const CUs_0 = 150

<Note>
  **Premium endpoint:** This endpoint requires an API key on the **Pro plan** or above.
</Note>

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json POST /tokens/analytics
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
  /tokens/analytics:
    post:
      tags:
        - Token
      summary: Get token analytics for a list of token addresses
      description: >-
        Fetch analytics for multiple tokens, including buy volume, sell volume,
        buyers, sellers, transactions, liquidity and FDV trends over time.
        Accepts an array of up to 200 `tokens`, each requiring `chain` and
        `tokenAddress`.
      operationId: getMultipleTokenAnalytics
      requestBody:
        description: Body
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GetMultipleTokenAnalyticsDto'
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MultipleTokenAnalyticsData'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetMultipleTokenAnalyticsDto:
      required:
        - tokens
      properties:
        tokens:
          type: array
          maxItems: 30
          description: The tokens to be fetched
          example:
            - chain: '0x1'
              tokenAddress: '0xdac17f958d2ee523a2206206994597c13d831ec7'
            - chain: solana
              tokenAddress: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
          items:
            $ref: '#/components/schemas/tokenAndChainItem'
    MultipleTokenAnalyticsData:
      type: object
      properties:
        categories:
          type: array
          items:
            $ref: '#/components/schemas/TokenAnalyticsData'
    tokenAndChainItem:
      required:
        - chain
        - tokenAddress
      properties:
        chain:
          $ref: '#/components/schemas/chainList'
          type: string
          description: The chain to query
        tokenAddress:
          type: string
          description: The token address
          example: '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0'
    TokenAnalyticsData:
      type: object
      properties:
        categoryId:
          type: string
          example: '0x1'
        totalBuyVolume:
          $ref: '#/components/schemas/VolumeData'
        totalSellVolume:
          $ref: '#/components/schemas/VolumeData'
        totalBuyers:
          $ref: '#/components/schemas/VolumeData'
        totalSellers:
          $ref: '#/components/schemas/VolumeData'
        totalBuys:
          $ref: '#/components/schemas/VolumeData'
        totalSells:
          $ref: '#/components/schemas/VolumeData'
        uniqueWallets:
          $ref: '#/components/schemas/VolumeData'
        pricePercentChange:
          $ref: '#/components/schemas/VolumeData'
        usdPrice:
          type: string
          example: '530'
        totalLiquidity:
          type: string
          example: '530'
        totalFullyDilutedValuation:
          type: string
          example: '530'
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
    VolumeData:
      type: object
      properties:
        5m:
          type: number
          format: double
          example: 6516719.425429553
        1h:
          type: number
          format: double
          example: 137489621.30780438
        6h:
          type: number
          format: double
          example: 585436101.0503464
        24h:
          type: number
          format: double
          example: 2668170156.0409784
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

# Token Analytics - Timeseries

> Fetch timeseries swap buy volume, sell volume, liquidity and FDV for multiple tokens. Accepts an array of up to 200 tokens, each requiring chain and tokenAddress.

export const CUs_0 = 150

<Note>
  **Premium endpoint:** This endpoint requires an API key on the **Pro plan** or above.
</Note>

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json POST /tokens/analytics/timeseries
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
  /tokens/analytics/timeseries:
    post:
      tags:
        - Token
      summary: Retrieve timeseries trading stats by token addresses
      description: >-
        Fetch timeseries buy volume, sell volume, liquidity and FDV for multiple
        tokens. Accepts an array of up to 200 `tokens`, each requiring `chain`
        and `tokenAddress`.
      operationId: getTimeSeriesTokenAnalytics
      parameters:
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
      requestBody:
        description: Body
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GetTimeSeriesTokenAnalyticsDto'
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TimeSeriesByTokensData'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetTimeSeriesTokenAnalyticsDto:
      required:
        - tokens
      properties:
        tokens:
          type: array
          maxItems: 30
          description: The tokens to be fetched
          example:
            - chain: '0x1'
              tokenAddress: '0xdac17f958d2ee523a2206206994597c13d831ec7'
            - chain: solana
              tokenAddress: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
          items:
            $ref: '#/components/schemas/tokenAndChainItem'
    TimeSeriesByTokensData:
      type: object
      properties:
        result:
          type: array
          items:
            $ref: '#/components/schemas/TimeSeriesVolumeByTokenResponse'
    tokenAndChainItem:
      required:
        - chain
        - tokenAddress
      properties:
        chain:
          $ref: '#/components/schemas/chainList'
          type: string
          description: The chain to query
        tokenAddress:
          type: string
          description: The token address
          example: '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0'
    TimeSeriesVolumeByTokenResponse:
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
            $ref: '#/components/schemas/TimeSeriesByTokenData'
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
    TimeSeriesByTokenData:
      type: object
      properties:
        timestamp:
          type: string
          example: '2022-02-22T00:00:00Z'
        buyVolume:
          type: number
          example: 4565
        sellVolume:
          type: number
          example: 4565
        liquidityUsd:
          type: number
          example: 4565
        fullyDilutedValuation:
          type: number
          example: 4565
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

# Token Search

> Search for tokens using their contract address, pair address, name, or symbol. Cross-chain by default with support to filter by chains. Additional options to sortBy various metrics, such as market cap, liquidity or volume.

export const CUs_0 = 150

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /tokens/search
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
  /tokens/search:
    get:
      tags:
        - Token
      summary: >-
        Search for tokens based on contract address, pair address, token name or
        token symbol.
      description: >-
        Search for tokens using their contract address, pair address, name, or
        symbol. Cross-chain by default with support to filter by `chains`.
        Additional options to `sortBy` various metrics, such as market cap,
        liquidity or volume.
      operationId: searchTokens
      parameters:
        - in: query
          name: chains
          description: The chains to query
          required: false
          schema:
            type: string
        - in: query
          name: query
          description: The query to search
          required: true
          schema:
            type: string
            example: pepe
        - in: query
          name: limit
          description: The desired page size of the result.
          required: false
          schema:
            type: number
        - in: query
          name: isVerifiedContract
          description: True to include only verified contracts
          required: false
          schema:
            type: boolean
            default: false
        - in: query
          name: sortBy
          description: Sort by volume1hDesc, volume24hDesc, liquidityDesc, marketCapDesc
          required: false
          schema:
            type: string
            example: volume1hDesc
            default: volume1hDesc
            enum:
              - volume1hDesc
              - volume24hDesc
              - liquidityDesc
              - marketCapDesc
        - in: query
          name: boostVerifiedContracts
          description: True to boost verified contracts
          required: false
          schema:
            type: boolean
            default: true
      responses:
        '200':
          description: Returns the search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  total:
                    type: integer
                    example: 10000
                  result:
                    type: array
                    items:
                      type: object
                      properties:
                        tokenAddress:
                          type: string
                          example: '0x6982508145454ce325ddbe47a25d4ec3d2311933'
                        chainId:
                          type: string
                          example: '0x1'
                        name:
                          type: string
                          example: Pepe
                        symbol:
                          type: string
                          example: PEPE
                        blockNumber:
                          type: integer
                          example: 17046105
                        blockTimestamp:
                          type: integer
                          example: 1681483883
                        usdPrice:
                          type: number
                          format: float
                          example: 0.000024509478199144
                        marketCap:
                          type: number
                          format: float
                          example: 9825629287.860994
                        experiencedNetBuyers:
                          type: object
                          properties:
                            oneHour:
                              type: integer
                              example: 31
                            oneDay:
                              type: integer
                              example: 51
                            oneWeek:
                              type: integer
                              example: 77
                        netVolumeUsd:
                          type: object
                          properties:
                            oneHour:
                              type: number
                              format: float
                              example: 188552.0639107914
                            oneDay:
                              type: number
                              format: float
                              example: 1188552.0639107914
                        liquidityChangeUSD:
                          type: object
                          properties:
                            oneHour:
                              type: number
                              format: float
                              example: -287308.4496394396
                            oneDay:
                              type: number
                              format: float
                              example: -387308.4496394396
                        usdPricePercentChange:
                          type: object
                          properties:
                            oneHour:
                              type: number
                              format: float
                              example: 1.079210724244654
                            oneDay:
                              type: number
                              format: float
                              example: 2.079210724244654
                        volumeUsd:
                          type: object
                          properties:
                            oneHour:
                              type: number
                              format: float
                              example: 188552.0639107914
                            oneDay:
                              type: number
                              format: float
                              example: 76927981.5281831
                        securityScore:
                          type: integer
                          example: 92
                        logo:
                          type: string
                          nullable: true
                          example: >-
                            https://adds-token-info-29a861f.s3.eu-central-1.amazonaws.com/marketing/evm/0x6982508145454ce325ddbe47a25d4ec3d2311933_icon.png
                        isVerifiedContract:
                          type: boolean
                          example: false
                        fullyDilutedValuation:
                          type: number
                          format: float
                          example: 71242582.97741453
                        totalHolders:
                          type: number
                          format: float
                          example: 18908
                        totalLiquidityUsd:
                          type: number
                          format: float
                          example: 18908.234
                        implementations:
                          type: array
                          items:
                            description: >-
                              The token addresses of the same symbol from
                              another chains
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
      security:
        - ApiKeyAuth: []
components:
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

# Filtered Tokens

export const CUs_0 = 250

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json POST /discovery/tokens
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
  /discovery/tokens:
    post:
      tags:
        - Discovery
      summary: Returns a list of tokens that match the specified filters and criteria
      description: >-
        Fetch a list of tokens across multiple chains, filtered and ranked by
        dynamic on-chain metrics like volume, price change, liquidity, holder
        composition, and more. Supports advanced filters (e.g. “top 10 whales
        hold <40%”), category-based inclusion/exclusion (e.g. “exclude
        stablecoins”), and time-based analytics. Ideal for token discovery,
        investor research, risk analysis, and portfolio tools. Each token
        returned includes detailed trading metrics as well as on-chain and
        off-chain metadata.
      operationId: getFilteredTokens
      parameters: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                chain:
                  type: string
                  example: '0x1'
                  description: The blockchain identifier
                chains:
                  type: array
                  items:
                    $ref: '#/components/schemas/chainListWithSolana'
                filters:
                  type: array
                  description: List of filters to apply
                  items:
                    type: object
                    example:
                      metric: experiencedBuyers
                      timeFrame: oneMonth
                      gt: 100
                    properties:
                      metric:
                        $ref: '#/components/schemas/tokenExplorerMetrics'
                        example: experiencedBuyers
                        description: The metric to filter on
                      timeFrame:
                        $ref: '#/components/schemas/tokenExplorerTimeFrames'
                        type: string
                        example: oneMonth
                        description: The time frame for the filter
                      gt:
                        type: number
                        example: 10
                        description: Greater-than value for the filter
                      lt:
                        type: number
                        example: 10
                        description: Less-than value for the filter
                      eq:
                        type: number
                        example: 10
                        description: Equal-to value for the filter
                    required:
                      - metric
                      - timeFrame
                sortBy:
                  type: object
                  description: Metric and time frame to sort by
                  properties:
                    metric:
                      $ref: '#/components/schemas/tokenExplorerMetrics'
                      type: string
                      example: experiencedBuyers
                      description: The metric to sort by
                    timeFrame:
                      $ref: '#/components/schemas/tokenExplorerTimeFrames'
                      type: string
                      example: oneHour
                      description: The time frame for sorting
                    type:
                      type: string
                      enum:
                        - ASC
                        - DESC
                      example: DESC
                      description: The order of sorting
                  required:
                    - metric
                    - timeFrame
                    - type
                categories:
                  type: object
                  description: Categories to filter tokens
                  properties:
                    include:
                      type: array
                      items:
                        type: string
                    exclude:
                      type: array
                      items:
                        type: string
                timeFramesToReturn:
                  type: array
                  items:
                    $ref: '#/components/schemas/tokenExplorerTimeFrames'
                    type: string
                  example: []
                  description: List of time frames to return in the response
                metricsToReturn:
                  type: array
                  items:
                    $ref: '#/components/schemas/tokenExplorerMetrics'
                    type: string
                  example: []
                  description: List of metrics to return in the response
                excludeMetadata:
                  type: boolean
                  example: false
                  description: Whether to exclude metadata from the response
                limit:
                  type: number
                  example: 100
                  description: Maximum number of results
              required:
                - chain
                - filters
                - sortBy
                - limit
      responses:
        '200':
          description: Returns the token details
          content:
            application/json:
              schema:
                type: object
                properties:
                  metadata:
                    type: object
                    properties:
                      tokenAddress:
                        type: string
                        example: '0x55d398326f99059ff775485246999027b3197955'
                      chainId:
                        type: string
                        example: '0x1'
                      name:
                        type: string
                        example: Tether USD
                      symbol:
                        type: string
                        example: USDT
                      decimals:
                        type: number
                        example: 18
                      logo:
                        type: string
                        example: https://example.com/logo.png
                      blockNumberMinted:
                        type: number
                        example: 176416
                      usdPrice:
                        type: number
                        example: 0.9982436729635321
                      security:
                        type: object
                        properties:
                          isOpenSource:
                            type: boolean
                            example: true
                          isProxy:
                            type: boolean
                            example: false
                          isMintable:
                            type: boolean
                            example: true
                          hiddenOwner:
                            type: boolean
                            example: false
                          buyTax:
                            type: string
                            example: '0'
                          sellTax:
                            type: string
                            example: '0'
                          cannotBuy:
                            type: boolean
                            example: false
                          cannotSellAll:
                            type: boolean
                            example: false
                          isHoneyPot:
                            type: boolean
                            example: false
                          securityScore:
                            type: number
                            example: 70
                          possibleSpam:
                            type: boolean
                            example: false
                      totalSupply:
                        type: string
                        example: '1000000000'
                      fullyDilutedValue:
                        type: number
                        example: 1000000000
                      circulatingSupply:
                        type: number
                        example: 1000000000
                      marketCap:
                        type: number
                        example: 1000000000
                      totalHolders:
                        type: number
                        example: 100000
                      totalLiquidityUsd:
                        type: number
                        example: 100000
                      links:
                        $ref: '#/components/schemas/discoveryTokenLinks'
                      categories:
                        type: array
                        items:
                          type: string
                  metrics:
                    type: object
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
    tokenExplorerMetrics:
      type: string
      enum:
        - experiencedBuyers
        - tokenAge
        - holders
        - buyers
        - sellers
        - netBuyers
        - experiencedSellers
        - netExperiencedBuyers
        - fullyDilutedValuation
        - marketCap
        - usdPrice
        - usdPricePercentChange
        - liquidityChange
        - liquidityChangeUSD
        - volumeUsd
        - buyVolumeUsd
        - sellVolumeUsd
        - netVolumeUsd
        - securityScore
        - totalHolders
        - totalLiquidityUsd
    tokenExplorerTimeFrames:
      type: string
      enum:
        - oneMonth
        - tenMinutes
        - thirtyMinutes
        - oneHour
        - fourHours
        - twelveHours
        - oneDay
        - oneWeek
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

# Top Gainers

export const CUs_0 = 250

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /discovery/tokens/top-gainers
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
  /discovery/tokens/top-gainers:
    get:
      tags:
        - Discovery
      summary: Get tokens with top gainers
      description: Identify tokens with the highest price increases over a period.
      operationId: getTopGainersTokens
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainListWithSolana'
        - in: query
          name: min_market_cap
          description: The minimum market cap in usd of a token
          schema:
            type: number
            example: 50000000
          required: false
        - in: query
          name: security_score
          description: The minimum security score of a token
          schema:
            type: number
            example: 80
          required: false
        - in: query
          name: time_frame
          description: The time frame used for price percent change ordering in response
          required: false
          schema:
            $ref: '#/components/schemas/discoverySupportedTimeFrames'
      responses:
        '200':
          description: Returns the token details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/discoveryTokens'
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
    discoverySupportedTimeFrames:
      type: string
      example: 1d
      enum:
        - 1h
        - 1d
        - 1w
        - 1M
    discoveryTokens:
      type: array
      items:
        required:
          - chain_id
          - token_address
          - token_name
          - token_symbol
          - token_logo
          - price_usd
          - token_age_in_days
          - on_chain_strength_index
          - security_score
          - market_cap
          - fully_diluted_valuation
          - twitter_followers
          - holders_change
          - liquidity_change_usd
          - experienced_net_buyers_change
          - volume_change_usd
          - net_volume_change_usd
          - price_percent_change_usd
        properties:
          chain_id:
            type: string
            description: The chain id of the token
            example: '0x1'
          token_address:
            type: string
            description: The address of the token
            example: '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2'
          token_name:
            type: string
            description: The name of the token contract
            example: Maker
            nullable: true
          token_symbol:
            type: string
            description: The symbol of the token
            example: MKR
            nullable: true
          token_logo:
            type: string
            description: The logo of the token
            nullable: true
          price_usd:
            type: number
            description: The price in USD for the token
            nullable: true
          token_age_in_days:
            type: number
            description: The number of days since the token was created
            nullable: true
          on_chain_strength_index:
            type: number
            description: The score of coin determined by various on chain metrics
            nullable: true
          security_score:
            type: number
            description: >-
              The security score (0-100) given to the token based various
              parameters
            example: 88
            nullable: true
          market_cap:
            type: number
            description: The market cap in USD
            example: 1351767630.85
            nullable: true
          fully_diluted_valuation:
            type: number
            description: The fully diluted valuation in USD
            example: 1363915420.28
            nullable: true
          twitter_followers:
            type: number
            description: The number of followers of the token on twitter
            example: 255217
            nullable: true
          holders_change:
            $ref: '#/components/schemas/timeFrames'
          liquidity_change_usd:
            $ref: '#/components/schemas/timeFrames'
          experienced_net_buyers_change:
            $ref: '#/components/schemas/timeFrames'
          volume_change_usd:
            $ref: '#/components/schemas/timeFrames'
          net_volume_change_usd:
            $ref: '#/components/schemas/timeFrames'
          price_percent_change_usd:
            $ref: '#/components/schemas/timeFrames'
    timeFrames:
      type: object
      required:
        - 1h
        - 1d
        - 1w
        - 1M
      properties:
        1h:
          type: number
          description: The 1 hour change of the token
          example: 14
          nullable: true
        1d:
          type: number
          description: The 1 day change of the token
          example: 14
          nullable: true
        1w:
          type: number
          description: The 1 week change of the token
          example: 162
          nullable: true
        1M:
          type: number
          description: The 1 month change of the token
          example: 162
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

# Top Losers

export const CUs_0 = 250

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /discovery/tokens/top-losers
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
  /discovery/tokens/top-losers:
    get:
      tags:
        - Discovery
      summary: Get tokens with top losers
      description: List tokens with the largest price decreases over a period.
      operationId: getTopLosersTokens
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainListWithSolana'
        - in: query
          name: min_market_cap
          description: The minimum market cap in usd of a token
          schema:
            type: number
            example: 50000000
          required: false
        - in: query
          name: security_score
          description: The minimum security score of a token
          schema:
            type: number
            example: 80
          required: false
        - in: query
          name: time_frame
          description: The time frame used for price percent change ordering in response
          required: false
          schema:
            $ref: '#/components/schemas/discoverySupportedTimeFrames'
      responses:
        '200':
          description: Returns the token details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/discoveryTokens'
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
    discoverySupportedTimeFrames:
      type: string
      example: 1d
      enum:
        - 1h
        - 1d
        - 1w
        - 1M
    discoveryTokens:
      type: array
      items:
        required:
          - chain_id
          - token_address
          - token_name
          - token_symbol
          - token_logo
          - price_usd
          - token_age_in_days
          - on_chain_strength_index
          - security_score
          - market_cap
          - fully_diluted_valuation
          - twitter_followers
          - holders_change
          - liquidity_change_usd
          - experienced_net_buyers_change
          - volume_change_usd
          - net_volume_change_usd
          - price_percent_change_usd
        properties:
          chain_id:
            type: string
            description: The chain id of the token
            example: '0x1'
          token_address:
            type: string
            description: The address of the token
            example: '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2'
          token_name:
            type: string
            description: The name of the token contract
            example: Maker
            nullable: true
          token_symbol:
            type: string
            description: The symbol of the token
            example: MKR
            nullable: true
          token_logo:
            type: string
            description: The logo of the token
            nullable: true
          price_usd:
            type: number
            description: The price in USD for the token
            nullable: true
          token_age_in_days:
            type: number
            description: The number of days since the token was created
            nullable: true
          on_chain_strength_index:
            type: number
            description: The score of coin determined by various on chain metrics
            nullable: true
          security_score:
            type: number
            description: >-
              The security score (0-100) given to the token based various
              parameters
            example: 88
            nullable: true
          market_cap:
            type: number
            description: The market cap in USD
            example: 1351767630.85
            nullable: true
          fully_diluted_valuation:
            type: number
            description: The fully diluted valuation in USD
            example: 1363915420.28
            nullable: true
          twitter_followers:
            type: number
            description: The number of followers of the token on twitter
            example: 255217
            nullable: true
          holders_change:
            $ref: '#/components/schemas/timeFrames'
          liquidity_change_usd:
            $ref: '#/components/schemas/timeFrames'
          experienced_net_buyers_change:
            $ref: '#/components/schemas/timeFrames'
          volume_change_usd:
            $ref: '#/components/schemas/timeFrames'
          net_volume_change_usd:
            $ref: '#/components/schemas/timeFrames'
          price_percent_change_usd:
            $ref: '#/components/schemas/timeFrames'
    timeFrames:
      type: object
      required:
        - 1h
        - 1d
        - 1w
        - 1M
      properties:
        1h:
          type: number
          description: The 1 hour change of the token
          example: 14
          nullable: true
        1d:
          type: number
          description: The 1 day change of the token
          example: 14
          nullable: true
        1w:
          type: number
          description: The 1 week change of the token
          example: 162
          nullable: true
        1M:
          type: number
          description: The 1 month change of the token
          example: 162
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

# Pump.fun - New Tokens

> Get the list of new tokens by given exchange. Pump.fun results include only tokens less than 24 hours old. Currently, only Pump.fun is supported.

export const CUs_0 = 1

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/exchange/{exchange}/new
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/exchange/{exchange}/new:
    get:
      tags:
        - Token
      summary: Get new tokens by exchange
      description: Get the list of new tokens by given exchange.
      operationId: getNewTokensByExchange
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: exchange
          required: true
          in: path
          schema:
            type: string
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NewTokensResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    NewTokensResponse:
      type: object
      properties:
        cursor:
          type: string
          nullable: true
        pageSize:
          type: number
        page:
          type: number
        result:
          type: array
          items:
            $ref: '#/components/schemas/NewTokenDto'
      required:
        - cursor
        - pageSize
        - page
        - result
    NewTokenDto:
      type: object
      properties:
        tokenAddress:
          type: string
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        logo:
          type: string
          nullable: true
        decimals:
          type: string
          nullable: true
        priceNative:
          type: string
          nullable: true
        priceUsd:
          type: string
          nullable: true
        liquidity:
          type: string
          nullable: true
        fullyDilutedValuation:
          type: string
          nullable: true
        createdAt:
          type: string
          nullable: false
          example: '2024-11-28T09:44:55.000Z'
      required:
        - tokenAddress
        - name
        - symbol
        - logo
        - decimals
        - priceNative
        - priceUsd
        - liquidity
        - fullyDilutedValuation
        - createdAt
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Pump.fun - Bonding Tokens

> Returns bonding tokens for the specified exchange. For Pump.fun, only tokens with a graduation of 20% or higher are returned, sorted by graduation in descending order. Currently, only Pump.fun is supported.

export const CUs_0 = 1

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/exchange/{exchange}/bonding
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/exchange/{exchange}/bonding:
    get:
      tags:
        - Token
      summary: Get bonding tokens by exchange
      description: Get the list of bonding tokens by given exchange.
      operationId: getBondingTokensByExchange
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: exchange
          required: true
          in: path
          schema:
            type: string
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BondingTokensResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    BondingTokensResponse:
      type: object
      properties:
        cursor:
          type: string
          nullable: true
        pageSize:
          type: number
        page:
          type: number
        result:
          type: array
          items:
            $ref: '#/components/schemas/BondingTokenDto'
      required:
        - cursor
        - pageSize
        - page
        - result
    BondingTokenDto:
      type: object
      properties:
        tokenAddress:
          type: string
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        logo:
          type: string
          nullable: true
        decimals:
          type: string
          nullable: true
        priceNative:
          type: string
          nullable: true
        priceUsd:
          type: string
          nullable: true
        liquidity:
          type: string
          nullable: true
        fullyDilutedValuation:
          type: string
          nullable: true
        bondingCurveProgress:
          type: number
      required:
        - tokenAddress
        - name
        - symbol
        - logo
        - decimals
        - priceNative
        - priceUsd
        - liquidity
        - fullyDilutedValuation
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Pump.fun - Graduated Tokens

> Get the list of graduated tokens by given exchange. Currently, only Pump.fun is supported.

export const CUs_0 = 1

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/exchange/{exchange}/graduated
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/exchange/{exchange}/graduated:
    get:
      tags:
        - Token
      summary: Get graduated tokens by exchange
      description: Get the list of graduated tokens by given exchange.
      operationId: getGraduatedTokensByExchange
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: exchange
          required: true
          in: path
          schema:
            type: string
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 100
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GraduatedTokensResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GraduatedTokensResponse:
      type: object
      properties:
        cursor:
          type: string
          nullable: true
        pageSize:
          type: number
        page:
          type: number
        result:
          type: array
          items:
            $ref: '#/components/schemas/GraduatedTokenDto'
      required:
        - cursor
        - pageSize
        - page
        - result
    GraduatedTokenDto:
      type: object
      properties:
        tokenAddress:
          type: string
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        logo:
          type: string
          nullable: true
        decimals:
          type: string
          nullable: true
        priceNative:
          type: string
          nullable: true
        priceUsd:
          type: string
          nullable: true
        liquidity:
          type: string
          nullable: true
        fullyDilutedValuation:
          type: string
          nullable: true
        graduatedAt:
          type: string
          nullable: false
          example: '2024-11-28T09:44:55.000Z'
      required:
        - tokenAddress
        - name
        - symbol
        - logo
        - decimals
        - priceNative
        - priceUsd
        - liquidity
        - fullyDilutedValuation
        - graduatedAt
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Pump.fun - Bonding Status

> Returns the bonding progress for the specified token. For Pump.fun, only tokens with a graduation of 20% or higher are returned, sorted by graduation in descending order. Currently, only Pump.fun is supported.

export const CUs_0 = 1

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/{address}/bonding-status
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/{address}/bonding-status:
    get:
      tags:
        - Token
      summary: Get Token Bonding Status
      description: >-
        Get the token bonding status for a given network and contract (if
        relevant).
      operationId: getTokenBondingStatus
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
      responses:
        '200':
          description: ''
        default:
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenBondingStatus'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    TokenBondingStatus:
      type: object
      properties:
        mint:
          type: string
          example: So11111111111111111111111111111111111111112
        bondingProgress:
          type: number
          example: 50
        graduatedAt:
          type: string
          example: '2024-11-28T09:44:55.000Z'
      required:
        - mint
        - bondingProgress
        - graduatedAt
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Snipers

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/pairs/{pairAddress}/snipers
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/pairs/{pairAddress}/snipers:
    get:
      tags:
        - Token
      summary: Get snipers by pair address.
      description: Get all snipers.
      operationId: getSnipersByPairAddress
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: pairAddress
          required: true
          in: path
          description: The address of the pair to query
          schema:
            example: Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE
            type: string
        - name: blocksAfterCreation
          required: false
          in: query
          schema:
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetSnipersResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetSnipersResponse:
      type: object
      properties:
        transactionHash:
          type: string
        blockNumber:
          type: number
        blockTimestamp:
          type: string
        result:
          type: array
          items:
            $ref: '#/components/schemas/SniperResponse'
      required:
        - transactionHash
        - blockNumber
        - blockTimestamp
        - result
    SniperResponse:
      type: object
      properties:
        walletAddress:
          type: string
        totalTokensSniped:
          type: number
        totalSnipedUsd:
          type: number
        totalSnipedTransactions:
          type: number
        snipedTransactions:
          type: array
          items:
            $ref: '#/components/schemas/SniperTransaction'
        totalTokensSold:
          type: number
        totalSoldUsd:
          type: number
        totalSellTransactions:
          type: number
        sellTransactions:
          type: array
          items:
            $ref: '#/components/schemas/SniperTransaction'
        currentBalance:
          type: number
        currentBalanceUsdValue:
          type: number
        realizedProfitPercentage:
          type: number
        realizedProfitUsd:
          type: number
      required:
        - walletAddress
        - totalTokensSniped
        - totalSnipedUsd
        - totalSnipedTransactions
        - snipedTransactions
        - totalTokensSold
        - totalSoldUsd
        - totalSellTransactions
        - sellTransactions
        - currentBalance
        - currentBalanceUsdValue
        - realizedProfitPercentage
        - realizedProfitUsd
    SniperTransaction:
      type: object
      properties:
        transactionHash:
          type: string
        transactionTimestamp:
          type: string
        blocksAfterCreation:
          type: number
      required:
        - transactionHash
        - transactionTimestamp
        - blocksAfterCreation
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana NFT API Overview

> Query Solana NFT metadata including token details, attributes, and media URLs.

## Overview

The **Solana NFT API** provides NFT metadata for tokens on the Solana blockchain, including attributes, media URLs, and collection information.

Built for Solana's unique NFT standards, the API delivers the data you need to display and work with Solana NFTs.

***

## What Is the Solana NFT API?

The Solana NFT API lets you query:

* **NFT Metadata** - Token metadata including name, symbol, and description
* **Attributes** - NFT traits and properties
* **Media** - Image and media URLs
* **Collection Info** - Collection-level metadata

***

## Key Features

* **Complete Metadata** - Full NFT metadata with all attributes
* **Media Resolution** - Resolved media URLs for display
* **Solana Standards** - Support for Metaplex and other Solana NFT standards
* **Fast Queries** - Optimized for quick metadata retrieval

***

## Common Use Cases

* **NFT Galleries**\
  (display Solana NFT collections)
* **Wallet Apps**\
  (show NFT holdings with metadata)
* **Marketplaces**\
  (NFT listings with full details)
* **Portfolio Trackers**\
  (include NFTs in portfolio views)

***

## Get Started

Explore the Solana NFT API endpoints:

* [**NFT Metadata**](/data-api/solana/nft/nft-metadata) - Get metadata for a Solana NFT


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# NFT Metadata

export const CUs_0 = 20

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json GET /nft/{network}/{address}/metadata
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /nft/{network}/{address}/metadata:
    get:
      tags:
        - NFT
      summary: Get the global metadata for a given contract
      description: >-
        Gets the contract level metadata (mint, standard, name, symbol,
        metaplex) for the given contract
      operationId: getNFTMetadata
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
        - name: mediaItems
          required: false
          in: query
          description: Should return media items
          schema:
            default: true
            type: boolean
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NFTMetadata'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    NFTMetadata:
      type: object
      properties:
        mint:
          type: string
        address:
          type: string
        standard:
          type: string
        name:
          type: string
        symbol:
          type: string
        tokenStandard:
          type: number
          nullable: true
        description:
          type: string
          nullable: true
        imageOriginalUrl:
          type: string
          nullable: true
        externalUrl:
          type: string
          nullable: true
        metadataOriginalUrl:
          type: string
          nullable: true
        totalSupply:
          type: string
        metaplex:
          $ref: '#/components/schemas/NFTMetaplex'
        attributes:
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataAttributeDto'
        contract:
          $ref: '#/components/schemas/NFTMetadataContractDto'
        collection:
          $ref: '#/components/schemas/NFTMetadataCollectionDto'
        firstCreated:
          $ref: '#/components/schemas/NFTMetadataFirstCreatedDto'
        creators:
          nullable: true
          type: array
          items:
            $ref: '#/components/schemas/NFTMetadataCreatorDto'
        properties:
          type: object
          nullable: true
        media:
          nullable: true
          allOf:
            - $ref: '#/components/schemas/Media'
        possibleSpam:
          type: boolean
      required:
        - mint
        - address
        - standard
        - name
        - symbol
        - tokenStandard
        - description
        - imageOriginalUrl
        - externalUrl
        - metadataOriginalUrl
        - totalSupply
        - metaplex
        - attributes
        - contract
        - collection
        - firstCreated
        - creators
        - properties
        - media
        - possibleSpam
    NFTMetaplex:
      type: object
      properties:
        metadataUri:
          type: string
          nullable: true
        masterEdition:
          type: boolean
        isMutable:
          type: boolean
        primarySaleHappened:
          type: number
        sellerFeeBasisPoints:
          type: number
        updateAuthority:
          type: string
          nullable: true
      required:
        - metadataUri
        - masterEdition
        - isMutable
        - primarySaleHappened
        - sellerFeeBasisPoints
        - updateAuthority
    NFTMetadataAttributeDto:
      type: object
      properties:
        traitType:
          type: string
          nullable: true
        value:
          type: object
      required:
        - traitType
        - value
    NFTMetadataContractDto:
      type: object
      properties:
        type:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
      required:
        - type
        - name
        - symbol
    NFTMetadataCollectionDto:
      type: object
      properties:
        collectionAddress:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        description:
          type: string
          nullable: true
        imageOriginalUrl:
          type: string
          nullable: true
        externalUrl:
          type: string
          nullable: true
        metaplexMint:
          type: string
          nullable: true
        sellerFeeBasisPoints:
          type: number
          nullable: true
      required:
        - collectionAddress
        - name
        - description
        - imageOriginalUrl
        - externalUrl
        - metaplexMint
        - sellerFeeBasisPoints
    NFTMetadataFirstCreatedDto:
      type: object
      properties:
        mintTimestamp:
          type: number
          nullable: true
        mintBlockNumber:
          type: number
          nullable: true
        mintTransaction:
          type: string
          nullable: true
      required:
        - mintTimestamp
        - mintBlockNumber
        - mintTransaction
    NFTMetadataCreatorDto:
      type: object
      properties:
        address:
          type: string
          nullable: true
        share:
          type: number
          nullable: true
        verified:
          type: boolean
          nullable: true
      required:
        - address
        - share
        - verified
    Media:
      type: object
      properties:
        mimetype:
          type: string
        category:
          type: string
        originalMediaUrl:
          type: string
        status:
          type: string
        updatedAt:
          type: string
        mediaCollection:
          $ref: '#/components/schemas/MediaCollection'
    MediaCollection:
      type: object
      properties:
        low:
          $ref: '#/components/schemas/MediaItem'
        medium:
          $ref: '#/components/schemas/MediaItem'
        high:
          $ref: '#/components/schemas/MediaItem'
    MediaItem:
      type: object
      properties:
        width:
          type: number
        height:
          type: number
        url:
          type: string
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Solana Price API Overview

> Real-time and historical price data for Solana SPL tokens including current prices, batch queries, and OHLC candlestick data.

## Overview

The **Solana Price API** provides real-time and historical pricing data for SPL tokens on Solana, including current prices, batch queries, and OHLC candlestick data for charting.

Get accurate token prices without managing your own price feeds or aggregation infrastructure.

***

## What Is the Solana Price API?

The Solana Price API lets you query:

* **Token Prices** - Current USD prices for any SPL token
* **Batch Prices** - Fetch prices for multiple tokens in one request
* **OHLC Data** - Candlestick data for charting and technical analysis

***

## Key Features

* **Real-Time Prices** - Current token prices with USD values
* **Batch Support** - Query multiple tokens efficiently
* **OHLC Candles** - Open, high, low, close data for charts
* **Historical Data** - Price history for trend analysis
* **Fast Response** - Optimized for low-latency queries

***

## Common Use Cases

* **Price Feeds**\
  (display current token prices)
* **Trading Charts**\
  (OHLC data for candlestick visualizations)
* **Portfolio Valuation**\
  (calculate holdings value in USD)
* **Price Alerts**\
  (trigger notifications on price changes)
* **Market Dashboards**\
  (aggregate pricing across tokens)

***

## Get Started

Explore the Solana Price API endpoints:

* [**Token Price**](/data-api/solana/price/token-price) - Get current price for a token
* [**Token Prices (Batch)**](/data-api/solana/price/token-prices-batch) - Get prices for multiple tokens
* [**OHLC**](/data-api/solana/price/ohlc) - Get candlestick data for charting


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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/{address}/price
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/{address}/price:
    get:
      tags:
        - Token
      summary: Get token price
      description: >-
        Gets the token price (usd and native) for a given contract address and
        network.
      operationId: getTokenPrice
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
      responses:
        '200':
          description: ''
        default:
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SPLTokenPrice'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SPLTokenPrice:
      type: object
      properties:
        tokenAddress:
          type: string
        pairAddress:
          type: string
        nativePrice:
          $ref: '#/components/schemas/SPLNativePrice'
        usdPrice:
          type: number
        exchangeAddress:
          type: string
        exchangeName:
          type: string
        logo:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        score:
          type: number
          nullable: true
        usdPrice24h:
          type: number
          nullable: true
        usdPrice24hrUsdChange:
          type: number
          nullable: true
        usdPrice24hrPercentChange:
          type: number
          nullable: true
        isVerifiedContract:
          type: boolean
          nullable: true
    SPLNativePrice:
      type: object
      properties:
        value:
          type: string
        decimals:
          type: number
        name:
          type: string
        symbol:
          type: string
      required:
        - value
        - decimals
        - name
        - symbol
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Price (Batch)

export const CUs_0 = 100

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/solana-api.json POST /token/{network}/prices
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/prices:
    post:
      tags:
        - Token
      summary: Get token price
      description: >-
        Gets the token price (usd and native) for a given contract address and
        network.
      operationId: getMultipleTokenPrices
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GetMultipleTokenPricesRequest'
      responses:
        '201':
          description: ''
        default:
          description: ''
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/SPLTokenPrice'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetMultipleTokenPricesRequest:
      type: object
      properties:
        addresses:
          minItems: 1
          maxItems: 100
          type: array
          items:
            type: string
      required:
        - addresses
    SPLTokenPrice:
      type: object
      properties:
        tokenAddress:
          type: string
        pairAddress:
          type: string
        nativePrice:
          $ref: '#/components/schemas/SPLNativePrice'
        usdPrice:
          type: number
        exchangeAddress:
          type: string
        exchangeName:
          type: string
        logo:
          type: string
          nullable: true
        name:
          type: string
          nullable: true
        symbol:
          type: string
          nullable: true
        score:
          type: number
          nullable: true
        usdPrice24h:
          type: number
          nullable: true
        usdPrice24hrUsdChange:
          type: number
          nullable: true
        usdPrice24hrPercentChange:
          type: number
          nullable: true
        isVerifiedContract:
          type: boolean
          nullable: true
    SPLNativePrice:
      type: object
      properties:
        value:
          type: string
        decimals:
          type: number
        name:
          type: string
        symbol:
          type: string
      required:
        - value
        - decimals
        - name
        - symbol
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

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

````yaml /openapi-files/data-api/solana-api.json GET /token/{network}/pairs/{address}/ohlcv
openapi: 3.0.0
info:
  title: Moralis Solana API
  version: '1.0'
servers:
  - url: https://solana-gateway.moralis.io
security: []
paths:
  /token/{network}/pairs/{address}/ohlcv:
    get:
      tags:
        - Token
      summary: Get candlesticks for a pair address
      description: Gets the candlesticks for a specific pair address
      operationId: getCandleSticks
      parameters:
        - name: network
          required: true
          in: path
          description: The network to query
          schema:
            enum:
              - mainnet
              - devnet
            type: string
        - name: address
          required: true
          in: path
          description: The address to query
          schema:
            type: string
            example: So11111111111111111111111111111111111111112
        - name: cursor
          required: false
          in: query
          description: The cursor to the next page
          schema:
            type: string
        - name: fromDate
          required: true
          in: query
          description: >-
            The starting date (format in seconds or datestring accepted by
            momentjs)
          schema:
            default: '2024-10-09'
            type: string
        - name: toDate
          required: true
          in: query
          description: >-
            The ending date (format in seconds or datestring accepted by
            momentjs)
          schema:
            default: '2024-10-10'
            type: string
        - name: timeframe
          required: true
          in: query
          description: The interval of the candle stick
          schema:
            default: 1min
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
            type: string
        - name: currency
          required: true
          in: query
          description: The currency format
          schema:
            default: usd
            enum:
              - usd
              - native
            type: string
        - name: limit
          required: false
          in: query
          description: The limit per page
          schema:
            minimum: 1
            maximum: 1000
            default: 100
            type: number
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GetCandleSticksResponse'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    GetCandleSticksResponse:
      type: object
      properties:
        cursor:
          type: string
          nullable: true
          description: The cursor to the next page
        page:
          type: number
          description: The page number
        pairAddress:
          type: string
          description: The pair address
        tokenAddress:
          type: string
          nullable: true
          description: The token address
        timeframe:
          type: string
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
          description: The interval of the candle stick
          default: 1min
        currency:
          type: string
          default: usd
          enum:
            - usd
            - native
          description: The currency format
        result:
          description: An array of candlesticks
          type: array
          items:
            $ref: '#/components/schemas/Ohlcv'
      required:
        - page
        - pairAddress
        - tokenAddress
        - timeframe
        - currency
    Ohlcv:
      type: object
      properties:
        timestamp:
          type: string
          nullable: true
          description: ''
        open:
          type: number
          nullable: true
          description: ''
        close:
          type: number
          nullable: true
          description: ''
        high:
          type: number
          nullable: true
          description: ''
        low:
          type: number
          nullable: true
          description: ''
        volume:
          type: number
          nullable: true
          description: ''
        trades:
          type: number
          description: ''
      required:
        - timestamp
        - open
        - close
        - high
        - low
        - volume
        - trades
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key

````

Built with [Mintlify](https://mintlify.com).

