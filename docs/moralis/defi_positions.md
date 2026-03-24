> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# DeFi API

> Track DeFi positions, balances, rewards, and protocol interactions with enriched, protocol-aware data across supported chains.

## Overview

The **DeFi API** provides detailed insights into wallet positions across DeFi protocols including lending, borrowing, staking, and liquidity pools.

Query a wallet's DeFi exposure without manually integrating with each protocol - get a unified view of positions, balances, and rewards across supported protocols.

***

## What Is the DeFi API?

The DeFi API lets you query:

* **Protocol Summary** - Overview of all DeFi protocols a wallet uses
* **Positions** - Detailed position data per protocol
* **Position Details** - Enhanced breakdown with underlying assets
* **Multi-Protocol** - Support for major DeFi protocols

***

## Key Features

The DeFi API includes:

* **Protocol Detection** - Automatically identifies which protocols a wallet uses
* **Position Breakdown** - Detailed view of deposits, borrows, and rewards
* **USD Valuations** - Position values calculated in USD
* **Multi-Chain** - Track positions across supported EVM chains
* **Unified Format** - Consistent data structure across protocols

***

## Supported Protocols

The DeFi API supports major protocols including:

* Aave
* Compound
* Uniswap
* Lido
* Rocket Pool
* Eigenlayer
* And more

***

## Common Use Cases

The DeFi API is commonly used for:

* **Portfolio Trackers**\
  (show DeFi positions alongside tokens and NFTs)
* **DeFi Dashboards**\
  (aggregate positions across protocols)
* **Risk Monitoring**\
  (track lending health factors and exposure)
* **Yield Tracking**\
  (monitor staking rewards and LP positions)
* **Tax Reporting**\
  (calculate DeFi gains and income)

***

## Popular Endpoints

| Endpoint                                                           | Description                           |
| ------------------------------------------------------------------ | ------------------------------------- |
| [Wallet Protocols](/data-api/evm/defi/wallet-protocols)            | Summary of protocols used by a wallet |
| [Wallet Positions](/data-api/evm/defi/wallet-positions)            | Detailed positions per protocol       |
| [Detailed Positions](/data-api/evm/defi/wallet-positions-detailed) | Enhanced position breakdown           |

***

## Get Started

* [Get Wallet Protocols](/data-api/evm/defi/wallet-protocols)
* [Get Wallet Positions](/data-api/evm/defi/wallet-positions)
* [Get Detailed Positions](/data-api/evm/defi/wallet-positions-detailed)


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

# Wallet Positions

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/defi/positions
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
  /wallets/{address}/defi/positions:
    get:
      tags:
        - Wallets
      summary: Get DeFi positions of a wallet
      description: >-
        Get a concise overview of a wallet’s DeFi positions across all
        protocols.
      operationId: getDefiPositionsSummary
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
          description: Returns all defi positions for the wallet address.
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/defiPositionSummaryResponse'
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
    defiPositionSummaryResponse:
      properties:
        protocol_name:
          type: string
          description: The name of the protocol
          example: Uniswap v2
        protocol_id:
          type: string
          description: The id of the protocol
          example: uniswap-v2
        protocol_url:
          type: string
          description: The url of the protocol
          example: https://app.uniswap.org/pools/v2
        protocol_logo:
          type: string
          description: The logo of the protocol
          example: https://cdn.moralis.io/defi/uniswap.png
        position:
          $ref: '#/components/schemas/defiProtocolPosition'
          type: object
          description: The position of the protocol
    defiProtocolPosition:
      required:
        - label
        - tokens
        - balance_usd
        - total_unclaimed_usd_value
      properties:
        label:
          type: string
          description: The label of the position
          example: liquidity
        tokens:
          type: array
          items:
            $ref: '#/components/schemas/defiTokenBalance'
        address:
          type: string
          description: The address of the position
          example: '0x06012c8cf97bead5deae237070f9587f8e7a266d'
        balance_usd:
          type: number
          description: The balance in USD
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the position
          example: '1000000'
        position_details:
          $ref: '#/components/schemas/defiPositionDetails'
          type: object
          description: The details of the position
    defiTokenBalance:
      required:
        - name
        - decimals
        - symbol
        - contract_address
        - token_type
        - balance
        - balance_formatted
      properties:
        token_type:
          type: string
          description: The token type (supply/defi/borrow token)
          example: defi-token
        name:
          type: string
          description: The name of the token
          example: Wrapped Ether
        symbol:
          type: string
          description: The symbol of the token
          example: WETH
        contract_address:
          type: string
          description: The contract address
          example: '0x06012c8cf97bead5deae237070f9587f8e7a266d'
        decimals:
          type: number
          description: The decimals of the token
          example: '18'
        logo:
          type: string
          description: The logo of the token
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        thumbnail:
          type: string
          description: The thumbnail of the token
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        balance:
          type: string
          description: The balance of the token
          example: '1000000'
        balance_formatted:
          type: string
          description: The balance of the token formatted
          example: '1.000000'
        usd_price:
          type: number
          description: The USD price of the token
          example: '1000000'
        usd_value:
          type: number
          description: The USD value of the token
          example: '1000000'
    defiPositionDetails:
      properties:
        fee_tier:
          type: number
          nullable: true
          description: The fee tier of the position
        range_tnd:
          type: number
          nullable: true
          description: The range trend of the position
        reserves:
          type: array
          nullable: true
          items:
            type: string
          description: The reserves of the position
        current_price:
          type: number
          nullable: true
          description: The current price of the position
        is_in_range:
          type: boolean
          nullable: true
          description: Whether the position is in range
        price_upper:
          type: number
          nullable: true
          description: The upper price of the range
        price_lower:
          type: number
          nullable: true
          description: The lower price of the range
        price_label:
          type: string
          nullable: true
          description: The price label
        liquidity:
          type: number
          nullable: true
          description: The liquidity of the position
        range_start:
          type: number
          nullable: true
          description: The start of the range
        pool_address:
          type: string
          nullable: true
          description: The address of the pool
        position_key:
          type: string
          nullable: true
          description: The key of the position
        nft_metadata:
          type: object
          nullable: true
          additionalProperties: true
          description: Metadata of the NFT
        asset_standard:
          type: string
          nullable: true
          description: The standard of the asset
        apy:
          type: number
          nullable: true
          description: The annual percentage yield
        is_debt:
          type: boolean
          nullable: true
          description: Whether the position is a debt
        is_variable_debt:
          type: boolean
          nullable: true
          description: Whether the position is a variable debt
        is_stable_debt:
          type: boolean
          nullable: true
          description: Whether the position is a stable debt
        shares:
          type: string
          nullable: true
          description: The shares of the position
        reserve0:
          type: string
          nullable: true
          description: The first reserve of the position
        reserve1:
          type: string
          nullable: true
          description: The second reserve of the position
        factory:
          type: string
          description: The factory of the position
        pair:
          type: string
          nullable: true
          description: The pair of the position
        share_of_pool:
          type: number
          nullable: true
          description: The share of the pool
        no_price_available:
          type: boolean
          nullable: true
          description: Whether the price is available
        shares_in_strategy:
          type: string
          nullable: true
          description: The shares in the strategy
        strategy_address:
          type: string
          nullable: true
          description: The address of the strategy
        base_type:
          type: string
          nullable: true
          description: The base type of the position
        health_factor:
          type: number
          nullable: true
          description: The health factor of the position in percent
        is_enabled_collateral:
          type: boolean
          nullable: true
          description: Whether the supply position is enabled as collateral
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

# Detailed Positions

export const CUs_0 = 15

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /wallets/{address}/defi/{protocol}/positions
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
  /wallets/{address}/defi/{protocol}/positions:
    get:
      tags:
        - Wallets
      summary: Get detailed DeFi positions by protocol for a wallet
      description: Fetch detailed DeFi positions for a given wallet and protocol.
      operationId: getDefiPositionsByProtocol
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
        - in: path
          name: protocol
          description: The protocol to query
          required: true
          schema:
            $ref: '#/components/schemas/defiProtocolList'
            example: aave-v3
      responses:
        '200':
          description: Returns the defi positions by protocol for the wallet address.
          content:
            application/json:
              schema:
                type: object
                properties:
                  protocol_name:
                    type: string
                    description: The name of the protocol
                    example: Uniswap v2
                  protocol_id:
                    type: string
                    description: The id of the protocol
                    example: uniswap-v2
                  protocol_url:
                    type: string
                    description: The url of the protocol
                    example: https://app.uniswap.org/pools/v2
                  protocol_logo:
                    type: string
                    description: The logo of the protocol
                    example: https://cdn.moralis.io/defi/uniswap.png
                  total_usd_value:
                    type: number
                    example: 47754.14278954011
                  total_unclaimed_usd_value:
                    type: number
                    nullable: true
                    example: null
                  positions:
                    type: array
                    items:
                      $ref: '#/components/schemas/defiProtocolPosition'
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
    defiProtocolList:
      type: string
      example: uniswap-v3
      default: uniswap-v3
      enum:
        - uniswap-v2
        - uniswap-v3
        - pancakeswap-v2
        - pancakeswap-v3
        - quickswap-v2
        - quickswap-v3
        - sushiswap-v2
        - aave-v2
        - aave-v3
        - aave-lido
        - fraxswap-v1
        - fraxswap-v2
        - lido
        - makerdao
        - eigenlayer
        - pendle
        - etherfi
        - rocketpool
        - sparkfi
        - takara-lend
        - neverland
        - kintsu
    defiProtocolPosition:
      required:
        - label
        - tokens
        - balance_usd
        - total_unclaimed_usd_value
      properties:
        label:
          type: string
          description: The label of the position
          example: liquidity
        tokens:
          type: array
          items:
            $ref: '#/components/schemas/defiTokenBalance'
        address:
          type: string
          description: The address of the position
          example: '0x06012c8cf97bead5deae237070f9587f8e7a266d'
        balance_usd:
          type: number
          description: The balance in USD
          example: '1000000'
        total_unclaimed_usd_value:
          type: number
          description: The total unclaimed USD value of the position
          example: '1000000'
        position_details:
          $ref: '#/components/schemas/defiPositionDetails'
          type: object
          description: The details of the position
    defiTokenBalance:
      required:
        - name
        - decimals
        - symbol
        - contract_address
        - token_type
        - balance
        - balance_formatted
      properties:
        token_type:
          type: string
          description: The token type (supply/defi/borrow token)
          example: defi-token
        name:
          type: string
          description: The name of the token
          example: Wrapped Ether
        symbol:
          type: string
          description: The symbol of the token
          example: WETH
        contract_address:
          type: string
          description: The contract address
          example: '0x06012c8cf97bead5deae237070f9587f8e7a266d'
        decimals:
          type: number
          description: The decimals of the token
          example: '18'
        logo:
          type: string
          description: The logo of the token
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        thumbnail:
          type: string
          description: The thumbnail of the token
          example: >-
            https://cdn.moralis.io/tokens/0x0000000000085d4780b73119b644ae5ecd22b376.png
        balance:
          type: string
          description: The balance of the token
          example: '1000000'
        balance_formatted:
          type: string
          description: The balance of the token formatted
          example: '1.000000'
        usd_price:
          type: number
          description: The USD price of the token
          example: '1000000'
        usd_value:
          type: number
          description: The USD value of the token
          example: '1000000'
    defiPositionDetails:
      properties:
        fee_tier:
          type: number
          nullable: true
          description: The fee tier of the position
        range_tnd:
          type: number
          nullable: true
          description: The range trend of the position
        reserves:
          type: array
          nullable: true
          items:
            type: string
          description: The reserves of the position
        current_price:
          type: number
          nullable: true
          description: The current price of the position
        is_in_range:
          type: boolean
          nullable: true
          description: Whether the position is in range
        price_upper:
          type: number
          nullable: true
          description: The upper price of the range
        price_lower:
          type: number
          nullable: true
          description: The lower price of the range
        price_label:
          type: string
          nullable: true
          description: The price label
        liquidity:
          type: number
          nullable: true
          description: The liquidity of the position
        range_start:
          type: number
          nullable: true
          description: The start of the range
        pool_address:
          type: string
          nullable: true
          description: The address of the pool
        position_key:
          type: string
          nullable: true
          description: The key of the position
        nft_metadata:
          type: object
          nullable: true
          additionalProperties: true
          description: Metadata of the NFT
        asset_standard:
          type: string
          nullable: true
          description: The standard of the asset
        apy:
          type: number
          nullable: true
          description: The annual percentage yield
        is_debt:
          type: boolean
          nullable: true
          description: Whether the position is a debt
        is_variable_debt:
          type: boolean
          nullable: true
          description: Whether the position is a variable debt
        is_stable_debt:
          type: boolean
          nullable: true
          description: Whether the position is a stable debt
        shares:
          type: string
          nullable: true
          description: The shares of the position
        reserve0:
          type: string
          nullable: true
          description: The first reserve of the position
        reserve1:
          type: string
          nullable: true
          description: The second reserve of the position
        factory:
          type: string
          description: The factory of the position
        pair:
          type: string
          nullable: true
          description: The pair of the position
        share_of_pool:
          type: number
          nullable: true
          description: The share of the pool
        no_price_available:
          type: boolean
          nullable: true
          description: Whether the price is available
        shares_in_strategy:
          type: string
          nullable: true
          description: The shares in the strategy
        strategy_address:
          type: string
          nullable: true
          description: The address of the strategy
        base_type:
          type: string
          nullable: true
          description: The base type of the position
        health_factor:
          type: number
          nullable: true
          description: The health factor of the position in percent
        is_enabled_collateral:
          type: boolean
          nullable: true
          description: Whether the supply position is enabled as collateral
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).
