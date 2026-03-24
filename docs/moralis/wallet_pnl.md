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