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

# Floor Price by Collection

export const CUs_0 = 30

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /nft/{address}/floor-price
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
  /nft/{address}/floor-price:
    get:
      tags:
        - NFT
        - Get Floor Price
      summary: Get NFT floor price by contract
      description: Get floor price for a given collection. Refreshes every 30 minutes.
      operationId: getNFTFloorPriceByContract
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address of the NFT contract
          required: true
          schema:
            type: string
            example: '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'
      responses:
        '200':
          description: Returns the conract's floor price
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/contractFloorPrice'
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
    contractFloorPrice:
      required:
        - address
        - last_updated
      properties:
        address:
          type: string
          description: The address of the NFT contract
          example: '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'
        floor_price:
          type: string
          description: The floor price of the contract
          example: '0.2176'
        floor_price_usd:
          type: string
          description: The floor price of the contract in USD
          example: '564.24'
        currency:
          type: string
          description: The currency of the floor price
          example: eth
        marketplace:
          $ref: '#/components/schemas/marketplace'
          description: The marketplace in which the floor price is present
        last_updated:
          type: string
          description: The timestamp of when the floor price was last updated
          example: '2024-08-21T15:59:11.000Z'
    marketplace:
      required:
        - name
      properties:
        name:
          type: string
          description: The name of the marketplace
          example: blur
        logo:
          type: string
          description: The logo of the marketplace
          example: https://cdn.moralis.io/marketplaces/blur.png
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

# Floor Price by Token ID

export const CUs_0 = 30

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /nft/{address}/{token_id}/floor-price
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
  /nft/{address}/{token_id}/floor-price:
    get:
      tags:
        - NFT
        - Get Floor Price
      summary: Get NFT floor price by token
      description: >-
        Get the floor price for a specific NFT, defined by its contract and
        token ID. Refreshes every 30 minutes.
      operationId: getNFTFloorPriceByToken
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: path
          name: address
          description: The address of the NFT contract
          required: true
          schema:
            type: string
            example: '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'
        - in: path
          name: token_id
          description: The token ID of the NFT
          required: true
          schema:
            type: string
            example: '2441'
      responses:
        '200':
          description: Returns the token's floor price
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/tokenFloorPrice'
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
    tokenFloorPrice:
      required:
        - address
        - token_id
      properties:
        address:
          type: string
          description: The address of the NFT contract
          example: '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'
        token_id:
          type: string
          description: The token ID of the NFT
          example: '2441'
        floor_price:
          type: string
          description: The floor price of the contract
          example: '0.2176'
        floor_price_usd:
          type: string
          description: The floor price of the contract in USD
          example: '564.24'
        currency:
          type: string
          description: The currency of the floor price
          example: eth
        marketplace:
          $ref: '#/components/schemas/marketplace'
          description: The marketplace in which the floor price is present
        last_updated:
          type: string
          description: The timestamp of when the floor price was last updated
          example: '2024-08-21T15:59:11.000Z'
    marketplace:
      required:
        - name
      properties:
        name:
          type: string
          description: The name of the marketplace
          example: blur
        logo:
          type: string
          description: The logo of the marketplace
          example: https://cdn.moralis.io/marketplaces/blur.png
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

# Timeseries Floor Price by Contract

export const CUs_0 = 50

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /nft/{address}/floor-price/historical
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
  /nft/{address}/floor-price/historical:
    get:
      tags:
        - NFT
        - Get Floor Price
      summary: Get historical NFT floor price by contract
      description: >-
        Get timeseries historical floor prices for a given NFT collection.
        Refreshes every 30 minutes.
      operationId: getNFTHistoricalFloorPriceByContract
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: interval
          description: The duration to query
          required: true
          schema:
            $ref: '#/components/schemas/nftFloorPriceIntervalList'
        - in: path
          name: address
          description: The address of the NFT contract
          required: true
          schema:
            type: string
            example: '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'
        - in: query
          name: cursor
          description: >-
            The cursor returned in the previous response (used for getting the
            next page).
          schema:
            type: string
      responses:
        '200':
          description: Returns the conract's historical floor price
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/historicalContractFloorResponse'
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
    nftFloorPriceIntervalList:
      type: string
      example: 1d
      default: 1d
      enum:
        - 1d
        - 7d
        - 30d
        - 60d
        - 90d
        - 1y
        - all
    historicalContractFloorResponse:
      required:
        - result
      properties:
        page:
          type: integer
          description: The current page of the result
          example: '1'
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
            $ref: '#/components/schemas/historicalContractFloorPrice'
          description: List of historical contract floor prices at various intervals.
    historicalContractFloorPrice:
      required:
        - timestamp
      properties:
        floor_price:
          type: string
          description: The floor price of the contract
          example: '0.2176'
        floor_price_usd:
          type: string
          description: The floor price of the contract in USD
          example: '564.24'
        currency:
          type: string
          description: The currency of the floor price
          example: eth
        marketplace:
          type: string
          description: The marketplace in which the floor price is present
          example: blur
        timestamp:
          type: string
          description: The timestamp of when the floor price was last updated
          example: '2024-08-21T15:59:11.000Z'
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

# Sale Price by Collection

export const CUs_0 = 1

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /nft/{address}/price
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
  /nft/{address}/price:
    get:
      tags:
        - NFT
        - Get Market Data
      summary: Get NFT sale prices by collection
      description: >-
        Fetch sale prices for NFTs in a contract over a specified number of
        days. Returns the last sale, lowest sale, highest sale, average sale and
        total trades within the specified period.
      operationId: getNFTContractSalePrices
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: days
          description: |
            The number of days to look back to find the lowest price
            If not provided 7 days will be the default and 365 is the maximum
          required: false
          schema:
            type: integer
            minimum: 0
        - in: path
          name: address
          description: The address of the NFT collection
          required: true
          schema:
            type: string
            example: '0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D'
      responses:
        '200':
          description: Returns the sold price details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/soldPrice'
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
    soldPrice:
      required:
        - last_sale
        - highest_sale
        - lowest_sale
        - average_sale
      properties:
        last_sale:
          type: object
          description: The sales price of the NFT collection
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
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
            buyer_address:
              type: string
              description: The buyer address of the last sale
            seller_address:
              type: string
              description: The seller address of the last sale
            price:
              type: string
              description: The price of the last sale
            price_formatted:
              type: string
              description: The formatted price of the last sale
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale at sale time
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
            token_id:
              type: string
              description: The token ID that is sold
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
                token_symbol:
                  type: string
                  description: The token symbol
                token_logo:
                  type: string
                  description: The token logo
                token_decimals:
                  type: string
                  description: The token decimals
                token_address:
                  type: string
                  description: The token address
        lowest_sale:
          type: object
          description: The lowest sale of the NFT collection
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
            buyer_address:
              type: string
              description: The buyer address of the last sale
            seller_address:
              type: string
              description: The seller address of the last sale
            price:
              type: string
              description: The price of the last sale
            price_formatted:
              type: string
              description: The formatted price of the last sale
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale at sale time
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
            token_id:
              type: string
              description: The token ID that is sold
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
                token_symbol:
                  type: string
                  description: The token symbol
                token_logo:
                  type: string
                  description: The token logo
                token_decimals:
                  type: string
                  description: The token decimals
                token_address:
                  type: string
                  description: The token address
        highest_sale:
          type: object
          description: The highest sale of the NFT collection
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
            buyer_address:
              type: string
              description: The buyer address of the last sale
            seller_address:
              type: string
              description: The seller address of the last sale
            price:
              type: string
              description: The price of the last sale
            price_formatted:
              type: string
              description: The formatted price of the last sale
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale at sale time
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
            token_id:
              type: string
              description: The token ID that is sold
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
                token_symbol:
                  type: string
                  description: The token symbol
                token_logo:
                  type: string
                  description: The token logo
                token_decimals:
                  type: string
                  description: The token decimals
                token_address:
                  type: string
                  description: The token address
        average_sale:
          type: object
          description: The average sale of the NFT collection
          nullable: true
          required:
            - price
            - price_formatted
          properties:
            price:
              type: string
              description: The price of the average sale
            price_formatted:
              type: string
              description: The formatted price of the average sale
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
        total_trades:
          type: number
          description: The total trades in the timeframe
          nullable: true
        message:
          type: string
          description: The error message (if any)
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

# Sale Price by Token ID

export const CUs_0 = 30

<Info>
  **Endpoint cost:** {CUs_0} CUs. [Learn more about compute units](/get-started/pricing).
</Info>


## OpenAPI

````yaml /openapi-files/data-api/api.json GET /nft/{address}/{token_id}/price
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
  /nft/{address}/{token_id}/price:
    get:
      tags:
        - NFT
        - Get Market Data
      summary: Get NFT sale prices by token
      description: >-
        Fetch sale prices for a specific NFT over a specified number of days.
        Returns the last sale, lowest sale, highest sale, average sale and total
        trades within the specified period.
      operationId: getNFTSalePrices
      parameters:
        - in: query
          name: chain
          description: The chain to query
          required: false
          schema:
            $ref: '#/components/schemas/chainList'
        - in: query
          name: days
          description: |
            The number of days to look back to find the lowest price
            If not provided 7 days will be the default and 365 is the maximum
          required: false
          schema:
            type: integer
            minimum: 0
        - in: path
          name: address
          description: The address of the NFT collection
          required: true
          schema:
            type: string
            example: '0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D'
        - in: path
          name: token_id
          description: The token id of the NFT collection
          required: true
          schema:
            type: string
            example: '1'
      responses:
        '200':
          description: Returns the sold price details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/soldPrice'
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
    soldPrice:
      required:
        - last_sale
        - highest_sale
        - lowest_sale
        - average_sale
      properties:
        last_sale:
          type: object
          description: The sales price of the NFT collection
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
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
            buyer_address:
              type: string
              description: The buyer address of the last sale
            seller_address:
              type: string
              description: The seller address of the last sale
            price:
              type: string
              description: The price of the last sale
            price_formatted:
              type: string
              description: The formatted price of the last sale
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale at sale time
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
            token_id:
              type: string
              description: The token ID that is sold
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
                token_symbol:
                  type: string
                  description: The token symbol
                token_logo:
                  type: string
                  description: The token logo
                token_decimals:
                  type: string
                  description: The token decimals
                token_address:
                  type: string
                  description: The token address
        lowest_sale:
          type: object
          description: The lowest sale of the NFT collection
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
            buyer_address:
              type: string
              description: The buyer address of the last sale
            seller_address:
              type: string
              description: The seller address of the last sale
            price:
              type: string
              description: The price of the last sale
            price_formatted:
              type: string
              description: The formatted price of the last sale
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale at sale time
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
            token_id:
              type: string
              description: The token ID that is sold
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
                token_symbol:
                  type: string
                  description: The token symbol
                token_logo:
                  type: string
                  description: The token logo
                token_decimals:
                  type: string
                  description: The token decimals
                token_address:
                  type: string
                  description: The token address
        highest_sale:
          type: object
          description: The highest sale of the NFT collection
          nullable: true
          required:
            - transaction_hash
            - block_timestamp
            - price
            - price_formatted
            - payment_token
          properties:
            transaction_hash:
              type: string
              description: The transaction hash of the last sale
            block_timestamp:
              type: string
              description: The block timestamp of the last sale
            buyer_address:
              type: string
              description: The buyer address of the last sale
            seller_address:
              type: string
              description: The seller address of the last sale
            price:
              type: string
              description: The price of the last sale
            price_formatted:
              type: string
              description: The formatted price of the last sale
            usd_price_at_sale:
              type: string
              description: The USD price of the last sale at sale time
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
            token_id:
              type: string
              description: The token ID that is sold
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
                token_symbol:
                  type: string
                  description: The token symbol
                token_logo:
                  type: string
                  description: The token logo
                token_decimals:
                  type: string
                  description: The token decimals
                token_address:
                  type: string
                  description: The token address
        average_sale:
          type: object
          description: The average sale of the NFT collection
          nullable: true
          required:
            - price
            - price_formatted
          properties:
            price:
              type: string
              description: The price of the average sale
            price_formatted:
              type: string
              description: The formatted price of the average sale
            current_usd_value:
              type: string
              description: The USD price of the last sale at the current value
        total_trades:
          type: number
          description: The total trades in the timeframe
          nullable: true
        message:
          type: string
          description: The error message (if any)
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      x-default: test

````

Built with [Mintlify](https://mintlify.com).
