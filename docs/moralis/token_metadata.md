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