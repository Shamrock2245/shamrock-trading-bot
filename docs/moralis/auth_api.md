# Moralis Auth API

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Auth API

> Web3 authentication using wallet signatures, built on the EIP-4361 standard for secure off-chain identity verification.

## Overview

Moralis **Auth API** enables secure **Web3 authentication** by letting users prove wallet ownership through message signing.

Instead of managing passwords or OAuth flows, Auth API uses cryptographic signatures to verify that users control their wallets - the native identity primitive of Web3.

***

## What Is Auth API?

Auth API provides a complete **wallet-based authentication flow** that:

* Generates secure challenge messages for users to sign
* Verifies wallet signatures cryptographically
* Returns a unique user identifier (`profileId`) across sessions
* Works with both EVM chains and Solana

The authentication follows the **EIP-4361** standard (Sign-In with Ethereum), ensuring compatibility with wallet apps and established security practices.

***

## How It Works

The authentication flow consists of three steps:

1. **Request Challenge** - Your backend requests a challenge message from Moralis
2. **User Signs** - The user signs the challenge message with their wallet
3. **Verify Signature** - Your backend sends the signature to Moralis for verification

Upon successful verification, you receive a `profileId` that uniquely identifies the user - regardless of which wallet or chain they used to authenticate.

***

## Key Features

Auth API includes:

* **EIP-4361 Standard** - Built on Sign-In with Ethereum for broad wallet compatibility
* **Unified Profile ID** - Single identifier per user across wallets and chains
* **Multi-Wallet Support** - Users can link multiple wallets to one profile
* **Cross-Chain** - Works with EVM chains and Solana
* **Stateless Verification** - No session management required on Moralis side

***

## Supported Networks

Auth API supports wallet authentication across:

* **EVM Chains** - Ethereum, Polygon, BNB Chain, Arbitrum, Optimism, Base, Avalanche, and more
* **Solana** - Full support for Solana wallet signatures

***

## Wallet Integrations

Auth API works with popular wallet connection libraries:

* MetaMask
* WalletConnect
* RainbowKit
* Coinbase Wallet
* Web3Auth
* Magic.Link
* Particle Network

***

## Common Use Cases

Auth API is commonly used for:

* **dApp Authentication**\
  (secure login without passwords)
* **Gated Content**\
  (verify wallet ownership before granting access)
* **NFT Verification**\
  (prove ownership for holder-only features)
* **Multi-Wallet Accounts**\
  (link multiple wallets to a single user profile)
* **Cross-Chain Identity**\
  (unified identity across EVM and Solana)

***

## Limitations

Auth API currently does **not** support:

* **EIP-1271 Signatures** - Smart contract wallet signatures (e.g., Safe, Argent) are not supported. Only EOA (Externally Owned Account) wallets can authenticate.

***

## Get Started

* [How to Authenticate Users with MetaMask](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask)
* [How to Authenticate Users with RainbowKit](/get-started/tutorials/auth-api/authenticate-users-with-rainbow-kit)
* [How to Authenticate Users with WalletConnect](/get-started/tutorials/auth-api/authenticate-users-with-wallet-connect)
* [How to Authenticate Users with Coinbase Wallet](/get-started/tutorials/auth-api/authenticate-users-with-coinbase-wallet)
* [How to Authenticate Users with Web3Auth](/get-started/tutorials/auth-api/authenticate-users-with-web3-auth)
* [How to Authenticate Users with Magic.Link](/get-started/tutorials/auth-api/authenticate-users-with-magic-link)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Auth API

> Web3 authentication using wallet signatures, built on the EIP-4361 standard for secure off-chain identity verification.

## Overview

Moralis **Auth API** enables secure **Web3 authentication** by letting users prove wallet ownership through message signing.

Instead of managing passwords or OAuth flows, Auth API uses cryptographic signatures to verify that users control their wallets - the native identity primitive of Web3.

***

## What Is Auth API?

Auth API provides a complete **wallet-based authentication flow** that:

* Generates secure challenge messages for users to sign
* Verifies wallet signatures cryptographically
* Returns a unique user identifier (`profileId`) across sessions
* Works with both EVM chains and Solana

The authentication follows the **EIP-4361** standard (Sign-In with Ethereum), ensuring compatibility with wallet apps and established security practices.

***

## How It Works

The authentication flow consists of three steps:

1. **Request Challenge** - Your backend requests a challenge message from Moralis
2. **User Signs** - The user signs the challenge message with their wallet
3. **Verify Signature** - Your backend sends the signature to Moralis for verification

Upon successful verification, you receive a `profileId` that uniquely identifies the user - regardless of which wallet or chain they used to authenticate.

***

## Key Features

Auth API includes:

* **EIP-4361 Standard** - Built on Sign-In with Ethereum for broad wallet compatibility
* **Unified Profile ID** - Single identifier per user across wallets and chains
* **Multi-Wallet Support** - Users can link multiple wallets to one profile
* **Cross-Chain** - Works with EVM chains and Solana
* **Stateless Verification** - No session management required on Moralis side

***

## Supported Networks

Auth API supports wallet authentication across:

* **EVM Chains** - Ethereum, Polygon, BNB Chain, Arbitrum, Optimism, Base, Avalanche, and more
* **Solana** - Full support for Solana wallet signatures

***

## Wallet Integrations

Auth API works with popular wallet connection libraries:

* MetaMask
* WalletConnect
* RainbowKit
* Coinbase Wallet
* Web3Auth
* Magic.Link
* Particle Network

***

## Common Use Cases

Auth API is commonly used for:

* **dApp Authentication**\
  (secure login without passwords)
* **Gated Content**\
  (verify wallet ownership before granting access)
* **NFT Verification**\
  (prove ownership for holder-only features)
* **Multi-Wallet Accounts**\
  (link multiple wallets to a single user profile)
* **Cross-Chain Identity**\
  (unified identity across EVM and Solana)

***

## Limitations

Auth API currently does **not** support:

* **EIP-1271 Signatures** - Smart contract wallet signatures (e.g., Safe, Argent) are not supported. Only EOA (Externally Owned Account) wallets can authenticate.

***

## Get Started

* [How to Authenticate Users with MetaMask](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask)
* [How to Authenticate Users with RainbowKit](/get-started/tutorials/auth-api/authenticate-users-with-rainbow-kit)
* [How to Authenticate Users with WalletConnect](/get-started/tutorials/auth-api/authenticate-users-with-wallet-connect)
* [How to Authenticate Users with Coinbase Wallet](/get-started/tutorials/auth-api/authenticate-users-with-coinbase-wallet)
* [How to Authenticate Users with Web3Auth](/get-started/tutorials/auth-api/authenticate-users-with-web3-auth)
* [How to Authenticate Users with Magic.Link](/get-started/tutorials/auth-api/authenticate-users-with-magic-link)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Verify EVM challenge



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /challenge/verify/evm
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /challenge/verify/evm:
    post:
      tags:
        - Challenge
      summary: Verify EVM challenge
      operationId: verifyChallengeEvm
      parameters: []
      requestBody:
        required: true
        description: Verify EVM challenge message.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/EvmCompleteChallengeRequestDto'
      responses:
        '201':
          description: The token to be used to call the third party API from the client
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EvmCompleteChallengeResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    EvmCompleteChallengeRequestDto:
      type: object
      properties:
        message:
          type: string
          description: Message that needs to be signed by the end user.
          example: |-
            defi.finance wants you to sign in with your Ethereum account:
            0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B


            URI: https://defi.finance
            Version: 1
            Chain ID: 1
            Nonce: Px7Nh1RPzlCLwqgOb
            Issued At: 2022-11-30T10:20:00.262Z
        signature:
          type: string
          description: >-
            EIP-191 compliant signature signed by the Ethereum account address
            requesting authentication.
          example: >-
            0xa8f89a58bf9b433d3100f9e41ee35b5e31fb8c7cd62547acb113162ec6f2e4140207e2dfbd4e387e1801ebc7f08a9dd105ac1d22b2e2ff0df5fa8b6d9bdcfe491c
      required:
        - message
        - signature
    EvmCompleteChallengeResponseDto:
      type: object
      properties:
        id:
          type: string
          maxLength: 64
          minLength: 8
          description: >-
            17-characters Alphanumeric string Secret Challenge ID used to
            identify this particular request. Is should be used at the backend
            of the calling service to identify the completed request.
          example: fRyt67D3eRss3RrX
          pattern: ^[a-zA-Z0-9]{8,64}$
        domain:
          type: string
          description: RFC 4501 dns authority that is requesting the signing.
          example: defi.finance
          format: hostname
        statement:
          type: string
          description: >-
            Human-readable ASCII assertion that the user will sign, and it must
            not contain `

            `.
          example: Please confirm
        uri:
          type: string
          format: uri
          example: https://defi.finance/
          description: >-
            RFC 3986 URI referring to the resource that is the subject of the
            signing (as in the __subject__ of a claim).
        expirationTime:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message is no longer valid.
        notBefore:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message will become valid.
        resources:
          example:
            - https://docs.moralis.io/
          description: >-
            List of information or references to information the user wishes to
            have resolved as part of authentication by the relying party. They
            are expressed as RFC 3986 URIs separated by `

            - `.
          type: array
          items:
            type: string
        version:
          type: string
          example: '1.0'
          description: >-
            EIP-155 Chain ID to which the session is bound, and the network
            where Contract Accounts must be resolved.
        nonce:
          type: string
          example: '0x1234567890abcdef0123456789abcdef1234567890abcdef'
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
        chainId:
          type: string
          enum:
            - '1'
            - '5'
            - '10'
            - '25'
            - '56'
            - '97'
            - '100'
            - '137'
            - '250'
            - '338'
            - '420'
            - '1284'
            - '1285'
            - '1287'
            - '1337'
            - '8453'
            - '10200'
            - '43113'
            - '43114'
            - '80001'
            - '80002'
            - '84531'
            - '88882'
            - '88888'
            - '11155111'
          example: 1
          description: >-
            EIP-155 Chain ID to which the session is bound, and the network
            where Contract Accounts must be resolved.
        address:
          type: string
          example: '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B'
          description: >-
            Ethereum address performing the signing conformant to capitalization
            encoded checksum specified in EIP-55 where applicable.
      required:
        - id
        - domain
        - uri
        - version
        - nonce
        - profileId
        - chainId
        - address
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Request Solana challenge



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /challenge/request/solana
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /challenge/request/solana:
    post:
      tags:
        - Challenge
      summary: Request Solana challenge
      operationId: requestChallengeSolana
      parameters: []
      requestBody:
        required: true
        description: Request Solana challenge message.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SolanaChallengeRequestDto'
      responses:
        '201':
          description: >-
            The back channel challenge containing the id to store on the api and
            the message to be signed by the user
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SolanaChallengeResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SolanaChallengeRequestDto:
      type: object
      properties:
        domain:
          type: string
          description: RFC 4501 dns authority that is requesting the signing.
          example: defi.finance
          format: hostname
        statement:
          type: string
          description: >-
            Human-readable ASCII assertion that the user will sign, and it must
            not contain `

            `.
          example: Please confirm
        uri:
          type: string
          format: uri
          example: https://defi.finance/
          description: >-
            RFC 3986 URI referring to the resource that is the subject of the
            signing (as in the __subject__ of a claim).
        expirationTime:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message is no longer valid.
        notBefore:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message will become valid.
        resources:
          example:
            - https://docs.moralis.io/
          description: >-
            List of information or references to information the user wishes to
            have resolved as part of authentication by the relying party. They
            are expressed as RFC 3986 URIs separated by new lines.
          type: array
          items:
            type: string
        timeout:
          type: number
          minimum: 15
          default: 15
          maximum: 120
          example: 15
          description: Time in seconds before the challenge is expired
        network:
          type: string
          enum:
            - mainnet
            - testnet
            - devnet
          example: mainnet
          description: The network where Contract Accounts must be resolved.
        address:
          type: string
          example: 26qv4GCcx98RihuK3c4T6ozB3J7L6VwCuFVc7Ta2A3Uo
          description: >-
            Solana address with a length of 32 - 44 characters that is used to
            perform the signing
      required:
        - domain
        - uri
        - timeout
        - network
        - address
    SolanaChallengeResponseDto:
      type: object
      properties:
        id:
          type: string
          maxLength: 64
          minLength: 8
          description: >-
            17-characters Alphanumeric string Secret Challenge ID used to
            identify this particular request. Is should be used at the backend
            of the calling service to identify the completed request.
          example: fRyt67D3eRss3RrXa
          pattern: ^[a-zA-Z0-9]{8,64}$
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
        message:
          type: string
          description: Message that needs to be signed by the end user
          example: |-
            defi.finance wants you to sign in with your Solana account:
            26qv4GCcx98RihuK3c4T6ozB3J7L6VwCuFVc7Ta2A3Uo

            I am a third party API

            URI: http://defi.finance
            Version: 1
            Network: mainnet
            Nonce: PYxxb9msdjVXsMQ9x
            Issued At: 2022-08-25T11:02:34.097Z
            Expiration Time: 2022-08-25T11:12:38.243Z
            Resources:
            - https://docs.moralis.io/
      required:
        - id
        - profileId
        - message
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Verify Solana challenge



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /challenge/verify/solana
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /challenge/verify/solana:
    post:
      tags:
        - Challenge
      summary: Verify Solana challenge
      operationId: verifyChallengeSolana
      parameters: []
      requestBody:
        required: true
        description: Verify Solana challenge message.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SolanaCompleteChallengeRequestDto'
      responses:
        '201':
          description: The token to be used to call the third party API from the client
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SolanaCompleteChallengeResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    SolanaCompleteChallengeRequestDto:
      type: object
      properties:
        message:
          type: string
          description: Message that needs to be signed by the end user
          example: |-
            defi.finance wants you to sign in with your Solana account:
            26qv4GCcx98RihuK3c4T6ozB3J7L6VwCuFVc7Ta2A3Uo

            I am a third party API

            URI: http://defi.finance
            Version: 1
            Network: mainnet
            Nonce: PYxxb9msdjVXsMQ9x
            Issued At: 2022-08-25T11:02:34.097Z
            Expiration Time: 2022-08-25T11:12:38.243Z
            Resources:
            - https://docs.moralis.io/
        signature:
          type: string
          description: Base58 signature that needs to be used to verify end user
          example: >-
            2pH9DqD5rve2qV4yBDshcAjWd2y8TqMx8BPb7f3KoNnuLEhE5JwjruYi4jaFaD4HN6wriLz2Vdr32kRBAJmHcyny
      required:
        - message
        - signature
    SolanaCompleteChallengeResponseDto:
      type: object
      properties:
        id:
          type: string
          maxLength: 64
          minLength: 8
          description: >-
            17-characters Alphanumeric string Secret Challenge ID used to
            identify this particular request. Is should be used at the backend
            of the calling service to identify the completed request.
          example: fRyt67D3eRss3RrX
          pattern: ^[a-zA-Z0-9]{8,64}$
        domain:
          type: string
          description: RFC 4501 dns authority that is requesting the signing.
          example: defi.finance
          format: hostname
        statement:
          type: string
          description: >-
            Human-readable ASCII assertion that the user will sign, and it must
            not contain `

            `.
          example: Please confirm
        uri:
          type: string
          format: uri
          example: https://defi.finance/
          description: >-
            RFC 3986 URI referring to the resource that is the subject of the
            signing (as in the __subject__ of a claim).
        expirationTime:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message is no longer valid.
        notBefore:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message will become valid.
        resources:
          example:
            - https://docs.moralis.io/
          description: >-
            List of information or references to information the user wishes to
            have resolved as part of authentication by the relying party. They
            are expressed as RFC 3986 URIs separated by `

            - `.
          type: array
          items:
            type: string
        version:
          type: string
          example: '1.0'
          description: >-
            EIP-155 Chain ID to which the session is bound, and the network
            where Contract Accounts must be resolved.
        nonce:
          type: string
          example: '0x1234567890abcdef0123456789abcdef1234567890abcdef'
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
        network:
          type: string
          enum:
            - mainnet
            - testnet
            - devnet
          example: mainnet
          description: The network where Contract Accounts must be resolved.
        address:
          type: string
          example: 26qv4GCcx98RihuK3c4T6ozB3J7L6VwCuFVc7Ta2A3Uo
          description: >-
            Solana address with a length of 32 - 44 characters that is used to
            perform the signing
      required:
        - id
        - domain
        - uri
        - version
        - nonce
        - profileId
        - network
        - address
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Request Aptos challenge



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /challenge/request/aptos
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /challenge/request/aptos:
    post:
      tags:
        - Challenge
      summary: Request Aptos challenge
      operationId: requestChallengeAptos
      parameters: []
      requestBody:
        required: true
        description: Request Aptos challenge message.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AptosChallengeRequestDto'
      responses:
        '201':
          description: >-
            The back channel challenge containing the id to store on the api and
            the message to be signed by the user
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AptosChallengeResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    AptosChallengeRequestDto:
      type: object
      properties:
        domain:
          type: string
          description: RFC 4501 dns authority that is requesting the signing.
          example: defi.finance
          format: hostname
        statement:
          type: string
          description: >-
            Human-readable ASCII assertion that the user will sign, and it must
            not contain `

            `.
          example: Please confirm
        uri:
          type: string
          format: uri
          example: https://defi.finance/
          description: >-
            RFC 3986 URI referring to the resource that is the subject of the
            signing (as in the __subject__ of a claim).
        expirationTime:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message is no longer valid.
        notBefore:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message will become valid.
        resources:
          example:
            - https://docs.moralis.io/
          description: >-
            List of information or references to information the user wishes to
            have resolved as part of authentication by the relying party. They
            are expressed as RFC 3986 URIs separated by new lines.
          type: array
          items:
            type: string
        timeout:
          type: number
          minimum: 15
          default: 15
          maximum: 120
          example: 15
          description: Time in seconds before the challenge is expired
        network:
          type: string
          enum:
            - mainnet
            - testnet
          example: mainnet
          description: The network where Contract Accounts must be resolved.
        address:
          type: string
          example: '0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d'
          description: Aptos address performing the signing conformant.
        publicKey:
          type: string
          example: '0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d'
          description: Aptos public key performing the signing conformant.
      required:
        - domain
        - uri
        - timeout
        - network
        - address
        - publicKey
    AptosChallengeResponseDto:
      type: object
      properties:
        id:
          type: string
          maxLength: 64
          minLength: 8
          description: >-
            17-characters Alphanumeric string Secret Challenge ID used to
            identify this particular request. Is should be used at the backend
            of the calling service to identify the completed request.
          example: fRyt67D3eRss3RrXa
          pattern: ^[a-zA-Z0-9]{8,64}$
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
        message:
          type: string
          description: Message that needs to be signed by the end user
          example: |-
            defi.finance wants you to sign in with your Aptos account:
            0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d

            Please confirm

            URI: https://defi.finance/
            Version: 1
            Chain ID: 1
            Nonce: DbU1DCTmdzR4lg3wi
            Issued At: 2022-06-12T12:15:31.290Z
            Expiration Time: 2020-01-01T00:00:00.000Z
            Not Before: 2020-01-01T00:00:00.000Z
            Resources:
            - https://docs.moralis.io/
      required:
        - id
        - profileId
        - message
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Verify Aptos challenge



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /challenge/verify/aptos
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /challenge/verify/aptos:
    post:
      tags:
        - Challenge
      summary: Verify Aptos challenge
      operationId: verifyChallengeAptos
      parameters: []
      requestBody:
        required: true
        description: Verify Aptos challenge message.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AptosCompleteChallengeRequestDto'
      responses:
        '201':
          description: The token to be used to call the third party API from the client
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AptosCompleteChallengeResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    AptosCompleteChallengeRequestDto:
      type: object
      properties:
        message:
          type: string
          description: Message that needs to be signed by the end user.
          example: |-
            defi.finance wants you to sign in with your Aptos account:
            0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d


            URI: https://defi.finance
            Version: 1
            Chain ID: 1
            Nonce: Px7Nh1RPzlCLwqgOb
            Issued At: 2022-11-30T10:20:00.262Z
        signature:
          type: string
          description: >-
            EIP-191 compliant signature signed by the Aptos account address
            requesting authentication.
          example: >-
            0xa8f89a58bf9b433d3100f9e41ee35b5e31fb8c7cd62547acb113162ec6f2e4140207e2dfbd4e387e1801ebc7f08a9dd105ac1d22b2e2ff0df5fa8b6d9bdcfe491c
      required:
        - message
        - signature
    AptosCompleteChallengeResponseDto:
      type: object
      properties:
        id:
          type: string
          maxLength: 64
          minLength: 8
          description: >-
            17-characters Alphanumeric string Secret Challenge ID used to
            identify this particular request. Is should be used at the backend
            of the calling service to identify the completed request.
          example: fRyt67D3eRss3RrX
          pattern: ^[a-zA-Z0-9]{8,64}$
        domain:
          type: string
          description: RFC 4501 dns authority that is requesting the signing.
          example: defi.finance
          format: hostname
        statement:
          type: string
          description: >-
            Human-readable ASCII assertion that the user will sign, and it must
            not contain `

            `.
          example: Please confirm
        uri:
          type: string
          format: uri
          example: https://defi.finance/
          description: >-
            RFC 3986 URI referring to the resource that is the subject of the
            signing (as in the __subject__ of a claim).
        expirationTime:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message is no longer valid.
        notBefore:
          type: string
          format: date-time
          example: '2020-01-01T00:00:00.000Z'
          description: >-
            ISO 8601 datetime string that, if present, indicates when the signed
            authentication message will become valid.
        resources:
          example:
            - https://docs.moralis.io/
          description: >-
            List of information or references to information the user wishes to
            have resolved as part of authentication by the relying party. They
            are expressed as RFC 3986 URIs separated by `

            - `.
          type: array
          items:
            type: string
        version:
          type: string
          example: '1.0'
          description: >-
            EIP-155 Chain ID to which the session is bound, and the network
            where Contract Accounts must be resolved.
        nonce:
          type: string
          example: '0x1234567890abcdef0123456789abcdef1234567890abcdef'
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
        network:
          type: string
          enum:
            - mainnet
            - testnet
          example: mainnet
          description: The network where Contract Accounts must be resolved.
        address:
          type: string
          example: '0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d'
          description: Aptos address performing the signing conformant.
        publicKey:
          type: string
          example: '0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d'
          description: Aptos public key performing the signing conformant.
      required:
        - id
        - domain
        - uri
        - version
        - nonce
        - profileId
        - network
        - address
        - publicKey
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Get addresses that are bound to the specific profileId



## OpenAPI

````yaml /openapi-files/auth-api/auth.json get /profile/{profileId}/addresses
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /profile/{profileId}/addresses:
    get:
      tags:
        - Profile
      summary: Get addresses that are bound to the specific profileId
      operationId: getAddresses
      parameters:
        - name: profileId
          required: true
          in: path
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
          schema:
            type: string
      responses:
        '201':
          description: The addresses that are bound to the speicifc profileId
          content:
            application/json:
              schema:
                type: array
                items:
                  type: string
      security:
        - ApiKeyAuth: []
components:
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Request bind between profile of two addresses

> Request for message to bind profile that is belong to the two addresses<br>
        All profiles under the addresses will be bound and new profile will be generated.



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /bind/request
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /bind/request:
    post:
      tags:
        - Bind
      summary: Request bind between profile of two addresses
      description: >-
        Request for message to bind profile that is belong to the two
        addresses<br>
                All profiles under the addresses will be bound and new profile will be generated.
      operationId: requestBind
      parameters: []
      requestBody:
        required: true
        description: The two addresses that are required to be bind.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BindRequestDto'
      responses:
        '201':
          description: The messages that is required to be signed by each of the address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BindRequestResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    BindRequestDto:
      type: object
      properties:
        addresses:
          description: An array of addresses that needs to be bind
          minItems: 2
          maxItems: 2
          type: array
          items:
            $ref: '#/components/schemas/AddressInfoDto'
      required:
        - addresses
    BindRequestResponseDto:
      type: object
      properties:
        messages:
          description: Message that needs to be signed by the end user
          example:
            - >-
              Please sign this message to bind:

              Profile Ids:

              -
              0x0b2bbac1251651c0cbbdbbb29fed5a03adc8b05a2a9eb10a02aaa489b9c1f8ff


              with


              Address: 0x6ed338bcB610640e81465FCfb9894DDfA354Cc91

              Nonce: 5pXWu7aGkY2J7II0X
            - >-
              Please sign this message to bind:

              Profile Ids:

              -
              0x0b2bbac1251651c0cbbdbbb29fed5a03adc8b05a2a9eb10a02aaa489b9c1f8ff


              with


              Address: 0x6ed338bcB610640e81465FCfb9894DDfA354Cc91

              Nonce: 5pXWu7aGkY2J7II0X
          type: array
          items:
            type: string
      required:
        - messages
    AddressInfoDto:
      type: object
      properties:
        blockchainType:
          type: string
          enum:
            - evm
            - solana
            - aptos
          description: The chain in which the address belongs to
          example: evm
        address:
          type: string
          description: >-
            Address performing the signing conformant to capitalization encoded
            checksum specified in EIP-55 where applicable.
          example: '0x57af6B90c2237d2F888bf4CAe56f25FE1b14e531'
        publicKey:
          type: string
          example: '0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d'
          description: >-
            Public key performing the signing conformant. (This is only needed
            for Aptos address)
      required:
        - blockchainType
        - address
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Verify bind request



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /bind/request/verify
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /bind/request/verify:
    post:
      tags:
        - Bind
      summary: Verify bind request
      operationId: verifyRequestBind
      parameters: []
      requestBody:
        required: true
        description: Messages and its signatures that is used for verification
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BindVerifyRequestDto'
      responses:
        '201':
          description: The profileId that all the addresses have been bind into.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BindVerifyRequestResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    BindVerifyRequestDto:
      type: object
      properties:
        verifications:
          description: Message that needs to be signed by the end user
          minItems: 2
          maxItems: 2
          type: array
          items:
            $ref: '#/components/schemas/VerificationDto'
      required:
        - verifications
    BindVerifyRequestResponseDto:
      type: object
      properties:
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
      required:
        - profileId
    VerificationDto:
      type: object
      properties:
        message:
          type: string
          description: Message that needs to be signed by the end user
          example: |-
            Please sign this message to bind:
            Profile Ids:
            - 0x0b2bbac1251651c0cbbdbbb29fed5a03adc8b05a2a9eb10a02aaa489b9c1f8ff

            with

            Address: 0x6ed338bcB610640e81465FCfb9894DDfA354Cc91
            Nonce: 5pXWu7aGkY2J7II0X
        signature:
          type: string
          description: >-
            EIP-191 compliant signature signed by the Ethereum account address
            requesting authentication.
          example: >-
            0xc4f2f59d80e036ecab4eaaac5d4ee713ab94264ca584839c98b5743c4f6777322038225a4bc1e0f13b8382166816737369f26bd66f0479cfa80d4c52c02eb2cb1b
      required:
        - message
        - signature
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Request to remove bind of an address from a profile



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /bind/remove
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /bind/remove:
    post:
      tags:
        - Bind
      summary: Request to remove bind of an address from a profile
      operationId: removeBind
      parameters: []
      requestBody:
        required: true
        description: >-
          The address that is required to be removed from the bind of the
          profileId.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BindRemoveDto'
      responses:
        '201':
          description: The messages that is required to be signed by each of the address
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BindRemoveResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    BindRemoveDto:
      type: object
      properties:
        blockchainType:
          type: string
          enum:
            - evm
            - solana
            - aptos
          description: The chain in which the address belongs to
          example: evm
        address:
          type: string
          description: >-
            Address performing the signing conformant to capitalization encoded
            checksum specified in EIP-55 where applicable.
          example: '0x57af6B90c2237d2F888bf4CAe56f25FE1b14e531'
        publicKey:
          type: string
          example: '0xfb2853744bb8afd58d9386d1856afd8e08de135019961dfa3a10d8c9bf83b99d'
          description: >-
            Public key performing the signing conformant. (This is only needed
            for Aptos address)
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
      required:
        - blockchainType
        - address
        - profileId
    BindRemoveResponseDto:
      type: object
      properties:
        message:
          type: string
          description: Message that needs to be signed by the end user
          example: |-
            Please sign this message to unbind:
            Address: 0x6ed338bcB610640e81465FCfb9894DDfA354Cc91
            from
            Profile Id:
            - 0x0b2bbac1251651c0cbbdbbb29fed5a03adc8b05a2a9eb10a02aaa489b9c1f8ff
            Nonce: 5pXWu7aGkY2J7II0X
      required:
        - message
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Verify remove bind request



## OpenAPI

````yaml /openapi-files/auth-api/auth.json post /bind/remove/verify
openapi: 3.0.0
info:
  title: Auth API
  description: API that provides authentication services for dapps.
  version: '1.0'
  contact: {}
servers:
  - url: https://authapi.moralis.io
security: []
tags: []
externalDocs:
  description: View as JSON
  url: ../api-docs-json
paths:
  /bind/remove/verify:
    post:
      tags:
        - Bind
      summary: Verify remove bind request
      operationId: verifyRemoveBind
      parameters: []
      requestBody:
        required: true
        description: Messages and its signatures that is used for verification
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BindVerifyRemoveDto'
      responses:
        '201':
          description: The new profileId that is being generated for this address.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BindVerifyRemoveResponseDto'
      security:
        - ApiKeyAuth: []
components:
  schemas:
    BindVerifyRemoveDto:
      type: object
      properties:
        message:
          type: string
          description: Message that needs to be signed by the end user
          example: |-
            Please sign this message to unbind:
            Address: 0x6ed338bcB610640e81465FCfb9894DDfA354Cc91
            from
            Profile Id:
            - 0x0b2bbac1251651c0cbbdbbb29fed5a03adc8b05a2a9eb10a02aaa489b9c1f8ff
            Nonce: 5pXWu7aGkY2J7II0X
        signature:
          type: string
          description: >-
            EIP-191 compliant signature signed by the Ethereum account address
            requesting authentication.
          example: >-
            0xc4f2f59d80e036ecab4eaaac5d4ee713ab94264ca584839c98b5743c4f6777322038225a4bc1e0f13b8382166816737369f26bd66f0479cfa80d4c52c02eb2cb1b
      required:
        - message
        - signature
    BindVerifyRemoveResponseDto:
      type: object
      properties:
        profileId:
          type: string
          description: Unique identifier with a length of 66 characters
          example: '0xbfbcfab169c67072ff418133124480fea02175f1402aaa497daa4fd09026b0e1'
      required:
        - profileId
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````

Built with [Mintlify](https://mintlify.com).


