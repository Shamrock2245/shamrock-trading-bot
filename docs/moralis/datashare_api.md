# Moralis Datashare API

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Datashare

> Moralis DataShare is a blockchain data export service that delivers massive, decoded datasets across supported chains. Users can export historical data in formats like Parquet, CSV, or JSON, either as downloadable files or to supported S3-compatible storage. These outputs can then be ingested into data platforms like BigQuery, Snowflake, or Databricks for analytics and downstream workflows.

### At a glance

<Columns cols={3}>
  <Card title="Cross-chain Data" icon="layer-group" />

  <Card title="Historical Exports" icon="file-export" />

  <Card title="Flexible Output Formats" icon="file-lines" />

  <Card title="S3 Export Support" icon="bucket" />

  <Card title="Prebuilt Schemas" icon="table-list" />

  <Card title="Decoded Data" icon="sparkles" />
</Columns>

### Types of use cases

* Export historical blockchain data for analytics and reporting
* Generate datasets in Parquet, CSV, or JSON for downstream processing
* Load exported data into warehouses like BigQuery or Snowflake
* Use prebuilt schemas for common datasets (transfers, swaps, NFTs)
* Access decoded, structured data across supported chains
* Run large-scale backfills over custom date ranges

### For which teams

* **Data engineering** teams needing reliable blockchain data in internal stores
* **Analytics & BI** teams working with crypto or on-chain datasets
* **AI/ML teams** building models leveraging historical blockchain data
* **Compliance & security** teams needing traceable on-chain data for monitoring and reporting
* **Quants and trading desks** building strategic models or backtests

### Tutorials

<Columns cols={2}>
  <Card title="Set Up an S3 Bucket for Datashare" icon="bucket" href="/datashare/s3-bucket-setup">
    Step-by-step guide to configuring an AWS S3 bucket to receive Datashare exports.
  </Card>

  <Card title="Export Bulk Blockchain Data" icon="video" href="https://www.youtube.com/watch?v=8QvGFGz2-Vo">
    Video tutorial on exporting bulk blockchain data using Moralis Datashare.
  </Card>
</Columns>

***

## Datashare Tutorial Video

<iframe src="https://www.youtube.com/embed/8QvGFGz2-Vo" title="Export Blockchain Data Sets to CSV" width="100%" height="400" frameBorder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Export Your First Dataset

> Learn how to create your first Datashare export, from selecting data to verifying output in your S3 bucket.

### Dashboard Overview

The Datashare dashboard is your export control panel. It displays all historical and active jobs, with options to:

* **Search** by Job ID to find specific exports
* **Filter** by status: Pending, Running, Completed, or Failed
* **View credits** — your GB balance is shown in the top-right corner
* **Create Export** — start a new export job

### Create Export Workflow

The Create Export screen has a three-panel layout:

| Panel                              | Purpose                                                                 |
| ---------------------------------- | ----------------------------------------------------------------------- |
| **Schema Explorer** (left)         | Select chain, dataset type, and fields                                  |
| **Filters & Destination** (middle) | Set date range, wallet/token filters, output format, and S3 destination |
| **Preview & Export** (right)       | View estimate, preview sample rows, and trigger the export              |

The workflow is: **select data → scope with filters → choose destination → estimate → export**.

***

### Step 1: Select Your Data

**Choose a chain** — one chain per export job. See [Supported Chains](/datashare/supported-chains) for the full list.

**Choose a dataset** — see [Supported Data](/datashare/supported-data) for available types (Token Transfers, Native Transfers, NFT Transfers, Swap Events, Liquidity Events, plus raw data).

**Select fields** — after choosing a dataset, expand the field list and select only the fields you need. More fields increase export size and GB consumption proportionally.

<Warning>
  DataShare exports raw on-chain data. Token names, symbols, logos, spam labels, and metadata enrichment are **not included**. Plan for separate metadata enrichment post-export if needed.
</Warning>

***

### Step 2: Apply Filters

Set date range, wallet address, and token address filters to control the scope and cost of your export. See [Filters & Scoping](/datashare/filters-and-scoping) for full details.

***

### Step 3: Choose Destination & Format

**Output Format**

| Format      | Best For                        | Notes                                                           |
| ----------- | ------------------------------- | --------------------------------------------------------------- |
| **Parquet** | Athena, Spark, DuckDB, BigQuery | Columnar, highly compressed (5–10x). Recommended for analytics. |
| **CSV**     | Excel, general compatibility    | Larger files than Parquet. Compresses well with gzip.           |
| **JSON**    | Debugging, human inspection     | Largest output. Useful for spot-checking data.                  |

**S3 Destination**

Select a saved destination or add a new one. Destination profiles are reusable across future jobs. See [S3 Bucket Setup](/datashare/s3-bucket-setup) for configuration instructions, or [Export Options](/datashare/export-options) for all supported providers.

***

### Step 4: Estimate

Click **Estimate** before triggering the export. This gives you:

* The GB of credits the export will consume
* A sample row preview to verify your schema

Estimates are **free** and can be run as many times as needed.

***

### Step 5: Export

Once you click **Export**, the system locks your configuration and begins processing.

<Warning>
  There is a **5-minute export window** after clicking Export. Top up credits and finalize your S3 configuration before this step. Navigating away or session timeout during this window may require re-running the estimate.
</Warning>

***

### Your First Export Recipe

Use this minimal configuration to validate the end-to-end flow without significant credit spend:

| Setting        | Value                                                     | Rationale                                     |
| -------------- | --------------------------------------------------------- | --------------------------------------------- |
| Chain          | Ethereum                                                  | Highest activity; good scale test             |
| Dataset        | Token Transfers                                           | Most commonly used; well-understood schema    |
| Date Range     | Last 24 hours                                             | Smallest reasonable validation window         |
| Wallet Address | 1 recognized address                                      | Verify output matches known activity          |
| Fields         | `from`, `to`, `value`, `token_address`, `block_timestamp` | Minimal schema confirming data delivery       |
| Format         | Parquet                                                   | Smallest files; compatible with DuckDB/Athena |

**After exporting:**

1. Check your S3 bucket for output files
2. Query locally with DuckDB:

```sql  theme={null}
SELECT * FROM read_parquet('*.parquet') LIMIT 10;
```

3. Or use Athena to query directly from S3
4. Confirm rows match the expected wallet activity


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Datashare Supported Data

> Data types available through Moralis Datashare for bulk historical exports.

### Supported Data Types

Moralis Datashare provides access to two categories of blockchain data: **decoded data** with enriched, human-readable information, and **raw data** for lower-level blockchain primitives.

***

## Decoded Data

Decoded data is processed and enriched blockchain data that has been parsed, labeled, and normalized for easier analysis. These datasets include contextual information such as token metadata, event types, and standardized schemas.

| Data Type            | Description                                                                                   |
| -------------------- | --------------------------------------------------------------------------------------------- |
| **Liquidity Events** | DEX liquidity pool additions and removals, including pool addresses, token pairs, and amounts |
| **Native Transfers** | Transfers of native blockchain currencies (ETH, MATIC, BNB, etc.) between addresses           |
| **NFT Transfers**    | ERC-721 and ERC-1155 token transfers with collection metadata and token IDs                   |
| **Swap Events**      | DEX swap transactions including input/output tokens, amounts, and exchange rates              |
| **Token Transfers**  | ERC-20 token transfers with token metadata, amounts, and decimal normalization                |

***

## Raw Data

Raw data provides direct access to blockchain primitives as they exist on-chain. These datasets are useful for custom parsing, low-level analysis, or when you need complete blockchain state data.

| Data Type                 | Description                                                                               |
| ------------------------- | ----------------------------------------------------------------------------------------- |
| **Blocks**                | Block headers including timestamps, gas limits, miner/validator info, and block hashes    |
| **Transactions**          | Complete transaction data including sender, recipient, value, gas, input data, and status |
| **Internal Transactions** | Trace-level internal calls and value transfers within transaction execution               |
| **Logs**                  | Event logs emitted by smart contracts, including topics and raw data fields               |

***

### Field Selection

When creating an export, you can select specific fields from each dataset. More fields increase export size and GB consumption proportionally — start with the minimum fields you actually need.

<Warning>
  DataShare exports raw on-chain data. Token names, symbols, logos, spam labels, and metadata enrichment are **not included**. Plan for separate metadata enrichment post-export if needed.
</Warning>

***

### Data Availability

Data availability varies by chain. See the [Supported Chains](/datashare/supported-chains) page for a complete breakdown of which data types are available for each blockchain.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Datashare Export Options

> Supported export destinations for Moralis Datashare bulk data exports.

### Export Destinations

Moralis Datashare supports exporting blockchain data directly to a variety of S3-compatible object storage providers. This enables seamless integration with your existing data infrastructure and analytics pipelines.

| Provider                           | Description                                                     |
| ---------------------------------- | --------------------------------------------------------------- |
| **AWS S3**                         | Amazon Web Services Simple Storage Service                      |
| **Google Cloud Storage**           | Google Cloud Platform object storage                            |
| **Cloudflare R2**                  | Cloudflare's S3-compatible object storage with zero egress fees |
| **Backblaze B2**                   | Cost-effective cloud storage with S3-compatible API             |
| **DigitalOcean Spaces**            | Simple object storage from DigitalOcean                         |
| **Wasabi**                         | High-performance cloud storage with no egress fees              |
| **MinIO**                          | Self-hosted, high-performance object storage                    |
| **Linode (Akamai) Object Storage** | Akamai's S3-compatible cloud storage                            |
| **Vultr Object Storage**           | S3-compatible storage from Vultr                                |
| **Scaleway Object Storage**        | European cloud provider's object storage solution               |

***

### Configuration

All export destinations use S3-compatible credentials and endpoints. When setting up an export, you'll need to provide:

* **Bucket name** - The destination bucket for your data
* **Access key** - Your storage provider access key ID
* **Secret key** - Your storage provider secret access key
* **Endpoint URL** - The S3-compatible endpoint (required for non-AWS providers)
* **Region** - The storage region (where applicable)

***

### Output Formats

Choose an output format based on your analytics tooling and use case.

| Format      | Best For                        | Notes                                                                     |
| ----------- | ------------------------------- | ------------------------------------------------------------------------- |
| **Parquet** | Athena, Spark, DuckDB, BigQuery | Columnar, highly compressed (5–10x). Recommended for analytics workloads. |
| **CSV**     | Excel, general compatibility    | Larger files than Parquet. Compresses well with gzip.                     |
| **JSON**    | Debugging, human inspection     | Largest output format. Useful for spot-checking data.                     |

<Note>
  Export size estimates are based on **uncompressed** data size. Parquet typically achieves 5–10x compression, and CSV with gzip also compresses significantly. Credits are calculated on uncompressed volume regardless of the format you choose.
</Note>

***

### Getting Started

To request access to Datashare and configure your export destination, see the [Early Access](/datashare/early-access) page.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Filters & Scoping

> Control the scope and cost of your Datashare exports using date range, wallet, and token filters.

Filters determine how much data your export includes — and how many credits it consumes. Apply filters to narrow exports to exactly the data you need.

***

### Date Range (Required)

The date range is the **single biggest driver of export size**. Wider ranges mean more rows, more GB, and higher credit cost.

* Start with a **single day or week** for initial runs
* Use the **"Current"** button to set the end date to the present
* Supports **datetime values** for hourly precision

<Warning>
  An unfiltered Ethereum Token Transfers job spanning a month will be very large. Always estimate before you run.
</Warning>

***

### Wallet Address (Optional)

Filter results to activity involving specific wallet addresses.

* Supports up to **500 addresses** per job
* Useful for verifying output against known wallet activity
* If no addresses are specified, the export includes **all addresses** on the chain — useful for full-chain data pulls, but expect significantly larger exports

***

### Token Address (Optional)

Filter to specific token contracts — for example, USDC or WETH. This is useful when you only need transfer or swap data for particular tokens rather than all activity on the chain.

***

### Field Selection

When creating an export, you can select specific fields from each dataset. More fields increase export size and GB consumption **proportionally**.

Start with the minimum fields you actually need. You can always run additional exports with more fields later.

***

### Scoping Best Practices

| Approach                   | Impact                                          |
| -------------------------- | ----------------------------------------------- |
| Narrow date range          | Fewer rows, lower credit cost                   |
| Add wallet or token filter | Targets specific activity instead of full chain |
| Select fewer fields        | Smaller file size per row                       |
| Combine all three          | Minimal, focused export for validation          |

<Note>
  You can run **estimates as many times as you want at no cost**. Use estimates to iterate on your filters before committing credits.
</Note>


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Credits & Pricing

> How Datashare's prepaid GB credit model works, including top-ups, tiered pricing, and credit consumption.

Datashare operates on a **prepaid GB credit model**. You purchase credits in advance, and they are consumed when exports complete.

***

### How Credits Work

* Credits are consumed upon **export completion**, not when you run an estimate
* Your current **GB balance** is displayed in the top-right corner of the Datashare dashboard
* Estimates are **free** — run as many as you need before committing

***

### Credit Consumption

Credit usage is based on **uncompressed data size**, regardless of the output format you choose.

| Factor                           | Impact on Credits                                            |
| -------------------------------- | ------------------------------------------------------------ |
| Wider date range                 | More rows = more GB consumed                                 |
| More selected fields             | Larger row size = more GB consumed                           |
| No wallet/token filters          | Full chain activity = significantly more GB                  |
| Output format (Parquet/CSV/JSON) | No impact — credits always calculated on uncompressed volume |

<Note>
  Parquet typically achieves 5–10x compression, so the actual files in your S3 bucket will be much smaller than the credited amount. CSV with gzip also compresses significantly.
</Note>

***

### Topping Up Credits

1. Click **Top Up** in the top-right of the Datashare main screen
2. Enter the GB quantity you need
3. Tiered pricing applies — higher volumes receive a **lower per-GB cost**
4. Top-ups are **manually approved** with confirmation

***

### Mid-Process Top-Up

If you realize you have insufficient credits while configuring an export:

1. Request a top-up and wait for approval
2. Return to **Create Export**
3. Re-run the estimate
4. Proceed with the export

<Warning>
  Always ensure you have sufficient credits **before** clicking Export. If credits run out mid-job, the export may fail, and the 5-minute export window may expire.
</Warning>


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Datashare Supported Chains

> Blockchains supported by Moralis DataShare for bulk historical data exports.

### Datashare Supported Chains

Moralis Datashare provides **bulk access to historical blockchain data**, designed for analytics, data science, and large-scale ingestion workflows.

Datashare chain support depends on:

* Availability of complete historical datasets
* Storage and export readiness
* Data normalization maturity

Use the table below to see which chains are supported for Datashare and what datasets are available per chain.

| Chain Name                  | Chain ID            | Token Transfers | NFT Transfers | Native Transfers | Swaps | Liquidity Events |
| --------------------------- | ------------------- | --------------- | ------------- | ---------------- | ----- | ---------------- |
| Ethereum Mainnet            | 0x1 (1)             | ✓               | ✓             | ✓                | ✓     | ✗                |
| Ethereum Sepolia            | 0xaa36a7 (11155111) | ✓               | ✓             | ✓                | ✗     | ✗                |
| Polygon Mainnet             | 0x89 (137)          | ✓               | ✓             | ✓                | ✓     | ✗                |
| Polygon Amoy                | 0x13882 (80002)     | ✓               | ✓             | ✓                | ✗     | ✗                |
| Binance Smart Chain Mainnet | 0x38 (56)           | ✓               | ✓             | ✓                | ✓     | ✗                |
| Binance Smart Chain Testnet | 0x61 (97)           | ✓               | ✓             | ✓                | ✗     | ✗                |
| Arbitrum                    | 0xa4b1 (42161)      | ✓               | ✓             | ✓                | ✓     | ✗                |
| Base                        | 0x2105 (8453)       | ✓               | ✓             | ✓                | ✓     | ✗                |
| Base Sepolia                | 0x14a34 (84532)     | ✓               | ✓             | ✓                | ✗     | ✗                |
| Optimism                    | 0xa (10)            | ✓               | ✓             | ✓                | ✓     | ✗                |
| Linea                       | 0xe708 (59144)      | ✓               | ✓             | ✓                | ✓     | ✗                |
| Linea Sepolia               | 0xe705 (59141)      | ✓               | ✓             | ✓                | ✗     | ✗                |
| Avalanche                   | 0xa86a (43114)      | ✓               | ✓             | ✓                | ✓     | ✗                |
| Fantom Mainnet              | 0xfa (250)          | ✓               | ✓             | ✓                | ✓     | ✗                |
| Cronos Mainnet              | 0x19 (25)           | ✓               | ✓             | ✓                | ✓     | ✗                |
| Gnosis                      | 0x64 (100)          | ✓               | ✓             | ✓                | ✓     | ✗                |
| Gnosis Chiado               | 0x27d8 (10200)      | ✓               | ✓             | ✓                | ✗     | ✗                |
| Chiliz Mainnet              | 0x15b38 (88888)     | ✓               | ✓             | ✓                | ✗     | ✗                |
| Chiliz Testnet              | 0x15b32 (88882)     | ✓               | ✓             | ✓                | ✗     | ✗                |
| Moonbeam                    | 0x504 (1284)        | ✓               | ✓             | ✓                | ✗     | ✗                |
| Moonriver                   | 0x505 (1285)        | ✓               | ✓             | ✓                | ✗     | ✗                |
| Moonbase                    | 0x507 (1287)        | ✓               | ✓             | ✓                | ✗     | ✗                |
| Flow                        | 0x2eb (747)         | ✓               | ✓             | ✓                | ✗     | ✗                |
| Flow Testnet                | 0x221 (545)         | ✓               | ✓             | ✓                | ✗     | ✗                |
| Ronin                       | 0x7e4 (2020)        | ✓               | ✓             | ✓                | ✓     | ✗                |
| Ronin Saigon Testnet        | 0x7e5 (2021)        | ✓               | ✓             | ✓                | ✗     | ✗                |
| Lisk                        | 0x46f (1135)        | ✓               | ✓             | ✓                | ✗     | ✗                |
| Lisk Sepolia Testnet        | 0x106a (4202)       | ✓               | ✓             | ✓                | ✗     | ✗                |
| Pulsechain                  | 0x171 (369)         | ✓               | ✓             | ✓                | ✓     | ✗                |
| Sei                         | 0x531 (1329)        | ✓               | ✓             | ✓                | ✓     | ✗                |
| Sei Testnet                 | 0x530 (1328)        | ✓               | ✓             | ✓                | ✗     | ✗                |
| Monad                       | 0x8f (143)          | ✓               | ✓             | ✓                | ✓     | ✗                |
| Solana Mainnet              | mainnet             | ✓               | ✓             | ✓                | ✓     | ✗                |


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Datashare Early Access

> Request early access to Moralis Datashare, a platform for exporting large-scale onchain datasets into data warehouses for analytics, ML, and compliance.

### Request Datashare early access

Datashare is currently available via **early access**.

We’re opening Datashare to a small number of teams who need **large-scale onchain datasets** for analytics, machine learning, compliance, or internal data platforms - and who want to help shape the product as it evolves.

### What early access means

Early access gives you:

* Priority access to Datashare as features roll out
* Direct collaboration with the Moralis product and data teams
* The ability to influence supported datasets, schemas, and delivery options
* Early visibility into upcoming capabilities and roadmap

Datashare is being built with **real production use cases in mind**, and early access allows us to validate those needs closely with customers.

### How to request access

If Datashare sounds like a fit, request early access using the form below.

We review requests on a rolling basis and prioritize teams with **clear use cases** and **production data needs**.

[**Request Datashare early access →**](https://moralis.com/datashare/#request-datashare-access)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# S3 Bucket Setup

This is a comprehensive step-by-step walkthrough on how to set up an AWS S3 bucket for your Datashare exports.

What is Amazon S3?

* [https://www.youtube.com/watch?v=ecv-19sYL3w](https://www.youtube.com/watch?v=ecv-19sYL3w)

**Account Setup**

1. Login into the AWS console / create an Amazon S3 Cloud Objective Storage account here with your IAM user ID or Root User Email: [https://aws.amazon.com/s3/](https://aws.amazon.com/s3/)
   * Note: AWS may require you to have a 2 Factor Authentication method when creating an account. You can download Google Auth or similar to satisfy this account creation requirement

**Creating an S3 Storage Bucket**

2. After you have successfully signed into your account, naviagete to Amazon S3
3. Click the Create bucket button:

   <Frame>
       <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at12.19.45PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=e3b1b13cdea844e253328a1104c01701" alt="Screenshot 2026 03 09 At 12 19 45 PM" width="1806" height="558" data-path="images/Screenshot2026-03-09at12.19.45PM.png" />
   </Frame>
4. When configuring the storage bucket follow these setup steps below:

* General configuration = General Purpose
* Bucket name = anything you want, example: "moralis-datashare-bucket"

<Frame>
    <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at12.28.20PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=51bcf2088ba3f181a442037d4ada6d03" alt="Screenshot 2026 03 09 At 12 28 20 PM" width="2472" height="750" data-path="images/Screenshot2026-03-09at12.28.20PM.png" />
</Frame>

5. Objective Ownership = ACLs disabled (recommended)

   <Frame>
       <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at12.32.21PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=69ac2cc091814669717eeb38ff6119a9" alt="Screenshot 2026 03 09 At 12 32 21 PM" width="1872" height="394" data-path="images/Screenshot2026-03-09at12.32.21PM.png" />
   </Frame>
6. Block Public Access settings for this bucket = True

   <Frame>
       <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at12.36.59PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=d502ffb7c5771e535fdbe8f57640a076" alt="Screenshot 2026 03 09 At 12 36 59 PM" width="2440" height="556" data-path="images/Screenshot2026-03-09at12.36.59PM.png" />
   </Frame>
7. Bucket Versioning = Disabled

   <Frame>
       <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at12.40.08PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=a1fe424bd0eef24ba8d1789007a4fbe7" alt="Screenshot 2026 03 09 At 12 40 08 PM" width="2428" height="280" data-path="images/Screenshot2026-03-09at12.40.08PM.png" />
   </Frame>
8. Tags are optional. Skip or include tags.
9. Default encryption = Keep SSE-S3 selected and Enable Bucket Key

   <Frame>
       <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at12.42.18PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=f12cfeda5db4ec0284d2292f86ae3adb" alt="Screenshot 2026 03 09 At 12 42 18 PM" width="1570" height="468" data-path="images/Screenshot2026-03-09at12.42.18PM.png" />
   </Frame>
10. Click Create Bucket

**Create a Bucket Policy with IAM user**

11. In the Searchbar type "IAM" and select "IAM Manage access to AWS resources"

    * You will be brought to the IAM Dashboard if you are logged in.

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.09.53PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=8bd44bfa8045a02bcb27f8c53b66ed18" alt="Screenshot 2026 03 09 At 1 09 53 PM" width="1712" height="326" data-path="images/Screenshot2026-03-09at1.09.53PM.png" />
    </Frame>
12. On the left sidebar under Access Management, click "Users"

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.20.55PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=f4ff26ab45338f08fa1301f17002103e" alt="Screenshot 2026 03 09 At 1 20 55 PM" width="350" height="148" data-path="images/Screenshot2026-03-09at1.20.55PM.png" />
    </Frame>
13. Click the "Create user" button.

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.21.43PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=6823908fd887671e2abcaff7fd5fe2f2" alt="Screenshot 2026 03 09 At 1 21 43 PM" width="230" height="88" data-path="images/Screenshot2026-03-09at1.21.43PM.png" />
    </Frame>
14. Set the user name, example = "moralis-datashare-bucket-user"
    * Leave unchecked "Provide user access to the AWS Management Console"
    * Click Next

      <Frame>
          <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.24.09PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=8f79463dac32aada25dc26d76ae929c5" alt="Screenshot 2026 03 09 At 1 24 09 PM" width="1990" height="662" data-path="images/Screenshot2026-03-09at1.24.09PM.png" />
      </Frame>
15. Click "Attach policies directly". This is the best approach for a single-purpose user.
16. In the Seachbar type "S3Full" and click Next.

    <Frame>
      <Frame>
            <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.29.20PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=667afecf493e85e7177f8f8b7900946b" alt="Screenshot 2026 03 09 At 1 29 20 PM" width="1840" height="516" data-path="images/Screenshot2026-03-09at1.29.20PM.png" />
      </Frame>
    </Frame>
17. Click "Create user".

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.30.02PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=703bc484aaed90eb043649ace6a622c3" alt="Screenshot 2026 03 09 At 1 30 02 PM" width="2196" height="864" data-path="images/Screenshot2026-03-09at1.30.02PM.png" />

      <Frame>
            <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.31.02PM-1.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=b3a17d6f39998c9a32093d8141aaeb83" alt="Screenshot 2026 03 09 At 1 31 02 PM" width="1092" height="162" data-path="images/Screenshot2026-03-09at1.31.02PM-1.png" />
      </Frame>
    </Frame>

**Access Keys**

18. Next, you need to create Access Keys for this IAM user.

    * Click on your username, example: "moralis-datashare-bucket-user" then go to the "Security credentials" tab.

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.41.50PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=7b9700679912eaad7da2aa62a0f48db9" alt="Screenshot 2026 03 09 At 1 41 50 PM" width="836" height="80" data-path="images/Screenshot2026-03-09at1.41.50PM.png" />
    </Frame>

    * Scroll down on this page, you'll see an "Access keys" section with a "Create access key" button. Click that.

      <Frame>
          <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.42.55PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=4442c91643f9ca8d6705079059eadf6a" alt="Screenshot 2026 03 09 At 1 42 55 PM" width="2130" height="248" data-path="images/Screenshot2026-03-09at1.42.55PM.png" />
      </Frame>
    * Select "Third-party service" — since Moralis Datashare is an external service that will write to your S3 bucket. Then click "Next".

      <Frame>
          <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.44.15PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=1acba5032c9991465cb13ed0c6c476ee" alt="Screenshot 2026 03 09 At 1 44 15 PM" width="1458" height="618" data-path="images/Screenshot2026-03-09at1.44.15PM.png" />
      </Frame>
    * Set description tab, example: "Moralis Datashare S3 export" then click Create access key.
    * You're key has been created.

      <Frame>
          <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.47.40PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=befdb15ea2cda45ded3a5f4029341183" alt="Screenshot 2026 03 09 At 1 47 40 PM" width="1434" height="66" data-path="images/Screenshot2026-03-09at1.47.40PM.png" />
      </Frame>

**Moralis Datashare Dashboard - Configuration**

19. Navigate to the Moralis Datashare Dashboard by clicking on the Create Export button. [https://moralis.com/](https://moralis.com/)

<Frame>
    <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.50.01PM-2.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=202665af8d129843942667825e449f10" alt="Screenshot 2026 03 09 At 1 50 01 PM" width="1063" height="34" data-path="images/Screenshot2026-03-09at1.50.01PM-2.png" />
</Frame>

20. Select the chain and data types that you want to fetch bulk blockchain data for.

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.58.08PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=a7ff4fe35a242fb0c8969f6d96e6f576" alt="Screenshot 2026 03 09 At 1 58 08 PM" width="420" height="948" data-path="images/Screenshot2026-03-09at1.58.08PM.png" />
    </Frame>
21. Set your date range

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at1.59.30PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=54142a84d07efda911d7eb28090ed3dc" alt="Screenshot 2026 03 09 At 1 59 30 PM" width="846" height="252" data-path="images/Screenshot2026-03-09at1.59.30PM.png" />
    </Frame>
22. Add a Wallet or Token Address

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at2.02.46PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=6c31e4d1843e642a6013caead48ef6d9" alt="Screenshot 2026 03 09 At 2 02 46 PM" width="858" height="370" data-path="images/Screenshot2026-03-09at2.02.46PM.png" />
    </Frame>
23. Set a Destination and Output format

    <Frame>
        <img src="https://mintcdn.com/moralis/doRskAvQ2QsOeJg5/images/Screenshot2026-03-09at2.03.38PM.png?fit=max&auto=format&n=doRskAvQ2QsOeJg5&q=85&s=207c56736ce3f4bd6792001dedf08c6d" alt="Screenshot 2026 03 09 At 2 03 38 PM" width="508" height="432" data-path="images/Screenshot2026-03-09at2.03.38PM.png" />
    </Frame>

* Add new S3 compadible storage destination for the export - input your S3 Keys here.

  <Frame>
      <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at2.04.24PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=42a6bda170a69750c32c85792ad4482b" alt="Screenshot 2026 03 09 At 2 04 24 PM" width="854" height="148" data-path="images/Screenshot2026-03-09at2.04.24PM.png" />
  </Frame>

<Frame>
    <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at2.07.50PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=e486a3e5ce60b31082920453eecbc74c" alt="Screenshot 2026 03 09 At 2 07 50 PM" width="806" height="1012" data-path="images/Screenshot2026-03-09at2.07.50PM.png" />
</Frame>

24. Select Destination.

<Frame>
    <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at2.09.12PM-2.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=f98e4e5bcac7550a1548e6b91fee2805" alt="Screenshot 2026 03 09 At 2 09 12 PM" width="542" height="218" data-path="images/Screenshot2026-03-09at2.09.12PM-2.png" />
</Frame>

25. Click "Estimate" to view the required GB for your export.

    <Frame>
        <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/Screenshot2026-03-09at2.10.46PM.png?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=de32eb4484160a7cadab68cdd935607a" alt="Screenshot 2026 03 09 At 2 10 46 PM" width="852" height="166" data-path="images/Screenshot2026-03-09at2.10.46PM.png" />
    </Frame>

**Complete - You can now export Bulk Blockchain Data with Moralis Datashare!**

<Frame>
    <img src="https://mintcdn.com/moralis/5-RjbdiAMQyRzkiU/images/youdidit-1.webp?fit=max&auto=format&n=5-RjbdiAMQyRzkiU&q=85&s=07801bd92c9efb7bf1175b5191abc29d" alt="You Did It" width="641" height="360" data-path="images/youdidit-1.webp" />
</Frame>


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Export Bulk Blockchain Data

> Learn how to export bulk blockchain data using Moralis Datashare.

## Video Tutorial

<iframe width="100%" height="400" src="https://www.youtube.com/embed/8QvGFGz2-Vo" title="Export Bulk Blockchain Data" frameBorder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Migrating from Reservoir to Moralis

> Reservoir is sunsetting its API on October 15th, 2025. Any project using Reservoir API needs a new provider before then. Migrate to Moralis APIs in 4 simple steps!

# Migrating from Reservoir to Moralis

<Warning>
  **URGENT MIGRATION NEEDED** - Reservoir is sunsetting their NFT APIs on October 15th, 2025. Applications and platforms using Reservoir API need to migrate as soon as possible to avoid service disruptions. Moralis APIs offer equivalent functionality, making migration straightforward.
</Warning>

With Reservoir deprecating their API offering, Moralis provides a comprehensive alternative with equivalent functionality. This guide will help you seamlessly transition your projects from Reservoir to Moralis.

## Quick Reference Guide

Make use of the table below to quickly find the Moralis equivalent for each Reservoir endpoint.

### NFT Data API

| Feature             | Reservoir Endpoint                                        | Moralis Equivalent              |
| ------------------- | --------------------------------------------------------- | ------------------------------- |
| Get Multiple NFTs   | `nft.reservoir.tools/reference/gettokensv7`               | [Details](#get-multiple-nfts)   |
| NFT Prices          | `nft.reservoir.tools/reference/gettokensfloorv1`          | [Details](#nft-prices)          |
| Get Token IDs       | `nft.reservoir.tools/reference/gettokensidsv1`            | [Details](#get-token-ids)       |
| Refresh Metadata    | `nft.reservoir.tools/reference/posttokensrefreshv2`       | [Details](#refresh-metadata)    |
| Collection Activity | `nft.reservoir.tools/reference/getcollectionsactivityv6`  | [Details](#collection-activity) |
| User Activity       | `nft.reservoir.tools/reference/getusersactivityv6`        | [Details](#user-activity)       |
| Token Activity      | `nft.reservoir.tools/reference/gettokenstokenactivityv5`  | [Details](#token-activity)      |
| Sales               | `nft.reservoir.tools/reference/getsalesv6`                | [Details](#sales)               |
| NFT Transfers       | `nft.reservoir.tools/reference/gettransfersbulkv2`        | [Details](#nft-transfers)       |
| User Tokens         | `nft.reservoir.tools/reference/getusersusertokensv10`     | [Details](#user-tokens)         |
| User Collections    | `nft.reservoir.tools/reference/getusersusercollectionsv4` | [Details](#user-collections)    |
| Owners              | `nft.reservoir.tools/reference/getownersv2`               | [Details](#owners)              |
| Stats               | `nft.reservoir.tools/reference/getstatsv1`                | [Details](#stats)               |

## Endpoint Details

### Get Multiple NFTs

| Chain | Moralis Equivalent | Moralis URL                                              |
| ----- | ------------------ | -------------------------------------------------------- |
| EVM   | Get Multiple NFTs  | `https://deep-index.moralis.io/api/v2.2/nft/getMultiple` |

### NFT Prices

| Chain | Moralis Equivalent   | Moralis URL                                           |
| ----- | -------------------- | ----------------------------------------------------- |
| EVM   | Get NFTs by Contract | `https://deep-index.moralis.io/api/v2.2/nft/:address` |

### Get Token IDs

| Chain | Moralis Equivalent | Moralis URL                                              |
| ----- | ------------------ | -------------------------------------------------------- |
| EVM   | Get Multiple NFTs  | `https://deep-index.moralis.io/api/v2.2/nft/getMultiple` |

### Refresh Metadata

| Chain | Moralis Equivalent  | Moralis URL                                                                     |
| ----- | ------------------- | ------------------------------------------------------------------------------- |
| EVM   | Resync NFT Metadata | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/metadata/resync` |

**Note**: Refresh entire collection metadata is available as a premium feature.

### Collection Activity

| Chain | Moralis Equivalent         | Moralis URL                                                     |
| ----- | -------------------------- | --------------------------------------------------------------- |
| EVM   | Get NFT Contract Transfers | `https://deep-index.moralis.io/api/v2.2/nft/:address/transfers` |
| EVM   | Get NFT Trades             | `https://deep-index.moralis.io/api/v2.2/nft/:address/trades`    |

### User Activity

| Chain | Moralis Equivalent       | Moralis URL                                                           |
| ----- | ------------------------ | --------------------------------------------------------------------- |
| EVM   | Get NFT Trades by Wallet | `https://deep-index.moralis.io/api/v2.2/wallets/:address/nfts/trades` |
| EVM   | Get Wallet NFT Transfers | `https://deep-index.moralis.io/api/v2.2/:address/nft/transfers`       |
| EVM   | Get Wallet History       | `https://deep-index.moralis.io/api/v2.2/wallets/:address/history`     |

### Token Activity

| Chain | Moralis Equivalent      | Moralis URL                                                               |
| ----- | ----------------------- | ------------------------------------------------------------------------- |
| EVM   | Get NFT Transfers       | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/transfers` |
| EVM   | Get NFT Trades by Token | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/trades`    |

### Sales

| Chain | Moralis Equivalent      | Moralis URL                                                            |
| ----- | ----------------------- | ---------------------------------------------------------------------- |
| EVM   | Get NFT Trades by Token | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/trades` |
| EVM   | Get NFT Trades          | `https://deep-index.moralis.io/api/v2.2/nft/:address/trades`           |

### NFT Transfers

| Chain | Moralis Equivalent         | Moralis URL                                                               |
| ----- | -------------------------- | ------------------------------------------------------------------------- |
| EVM   | Get NFT Contract Transfers | `https://deep-index.moralis.io/api/v2.2/nft/:address/transfers`           |
| EVM   | Get NFT Transfers          | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/transfers` |
| EVM   | Get Wallet NFT Transfers   | `https://deep-index.moralis.io/api/v2.2/:address/nft/transfers`           |

### User Tokens

| Chain | Moralis Equivalent | Moralis URL                                                    |
| ----- | ------------------ | -------------------------------------------------------------- |
| EVM   | Get Wallet NFTs    | `https://deep-index.moralis.io/api/v2.2/wallets/:address/nfts` |

### User Collections

| Chain | Moralis Equivalent         | Moralis URL                                                               |
| ----- | -------------------------- | ------------------------------------------------------------------------- |
| EVM   | Get Wallet NFT Collections | `https://deep-index.moralis.io/api/v2.2/wallets/:address/nft-collections` |

### Owners

| Chain | Moralis Equivalent      | Moralis URL                                                            |
| ----- | ----------------------- | ---------------------------------------------------------------------- |
| EVM   | Get NFT Owners          | `https://deep-index.moralis.io/api/v2.2/nft/:address/owners`           |
| EVM   | Get NFT Token ID Owners | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/owners` |

### Stats

| Chain | Moralis Equivalent           | Moralis URL                                                           |
| ----- | ---------------------------- | --------------------------------------------------------------------- |
| EVM   | Get NFT Contract Sale Prices | `https://deep-index.moralis.io/api/v2.2/nft/:address/sales`           |
| EVM   | Get NFT Sale Prices          | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/sales` |

## Real-time Data

### Webhooks

| Feature          | Moralis Equivalent | Moralis URL                   | Documentation                      |
| ---------------- | ------------------ | ----------------------------- | ---------------------------------- |
| Real-time Events | Streams API        | N/A - Setup through dashboard | [Documentation](/streams/overview) |

**Notes**: Moralis Streams API provides powerful real-time blockchain data capabilities, including filters, webhooks, and managed infrastructure.

## Beyond Reservoir: Exclusive Moralis Capabilities

Moralis offers many additional endpoints and features not available in Reservoir. Here are some of our most popular exclusive endpoints:

### Advanced Wallet Analysis

| Feature              | Endpoint                                                                | Documentation                                        |
| -------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------- |
| **Wallet History**   | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/history`   | [Documentation](/data-api/evm/wallet/wallet-history) |
| **Wallet Approvals** | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/approvals` | [Documentation](/data-api/evm/wallet/approvals)      |
| **Wallet Net Worth** | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/net-worth` | [Documentation](/data-api/evm/wallet/net-worth)      |

### Token Analytics

| Feature                      | Endpoint                                                                             | Documentation                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| **Token Holder Stats**       | `GET https://deep-index.moralis.io/api/v2.2/erc20/:token_address/holders/stats`      | [Documentation](/data-api/evm/token/holders/token-holder-stats)       |
| **Historical Token Holders** | `GET https://deep-index.moralis.io/api/v2.2/erc20/:token_address/holders/historical` | [Documentation](/data-api/evm/token/holders/historical-token-holders) |

### Token Search & Discovery

| Feature             | Endpoint                                                     | Documentation                                                  |
| ------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| **Search Tokens**   | `GET https://deep-index.moralis.io/api/v2.2/tokens/search`   | [Documentation](/data-api/universal/token/search/token-search) |
| **Trending Tokens** | `GET https://deep-index.moralis.io/api/v2.2/tokens/trending` | [Documentation](/data-api/universal/token/trending-tokens)     |

### DEX and Pair Analytics

| Feature                         | Endpoint                                                                | Documentation                                         |
| ------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------- |
| **Pair Stats**                  | `GET https://deep-index.moralis.io/api/v2.2/pairs/:address/stats`       | [Documentation](/data-api/evm/token/swaps/pair-stats) |
| **Aggregated Token Pair Stats** | `GET https://deep-index.moralis.io/api/v2.2/:token_address/pairs/stats` | [Documentation](/data-api/evm/token/swaps/pair-stats) |

### NFT Advanced Capabilities

* **Enriched Metadata**: Access fully enriched and normalized metadata on NFT collections and individual tokens through a single API call
* **Real-time NFT Transfer Data**: Get all the latest NFT transfer data for specific NFTs, wallets, or track real-time transfers
* **Advanced Spam Detection**: Protect your platform from undesirable NFTs with collection spam indicators
* **On-chain Pricing Data**: Incorporate on-chain pricing data including last sale prices and floor prices
* **Optimized Image Previews**: Benefit from dynamically sized image previews and conversions to user-friendly formats

## Getting Started with Moralis

1. **Sign up for a Moralis account**: [https://admin.moralis.com/register](https://admin.moralis.com/register)
2. **Get your API key**: Navigate to the Web3 APIs section in your dashboard
3. **Update your API calls**: Replace Reservoir endpoints with the corresponding Moralis endpoints
4. **Explore the documentation**: [https://docs.moralis.com/](https://docs.moralis.com/)

<Tip>
  **MIGRATION SUPPORT AVAILABLE** - Moralis has a dedicated team to help you migrate smoothly from Reservoir. [Contact our team](https://developers.moralis.com/) for personalized support.
</Tip>


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Migrating from SimpleHash to Moralis

> SimpleHash is shutting down on March 27, 2025. Any project using SimpleHash API needs a new provider before then. Migrate to Moralis APIs in 4 simple steps!

# Migrating from SimpleHash to Moralis

<Warning>
  **URGENT MIGRATION NEEDED** - SimpleHash is shutting down ALL THEIR APIs. Wallet providers and applications using SimpleHash API need to migrate as soon as possible to avoid service disruptions. Moralis APIs are almost an exact match, making migration straightforward.
</Warning>

With SimpleHash deprecating their API offering, Moralis provides a comprehensive alternative with equivalent functionality and additional capabilities. This guide will help you seamlessly transition your projects from SimpleHash to Moralis.

## API Endpoint Equivalence

SimpleHash endpoints can be easily mapped to Moralis equivalents. Below you'll find the mapping organized by API category.

## Quick Reference Guide

Make use of the table below to quickly find the Moralis equivalent for each SimpleHash endpoint by clicking on the Moralis Equivalent column.

### Token API

| Feature                            | SimpleHash Endpoint                                           | Moralis Equivalent                           |
| ---------------------------------- | ------------------------------------------------------------- | -------------------------------------------- |
| Token & Prices                     | `api.simplehash.com/api/v0/fungibles/assets`                  | [Details](#token--prices)                    |
| Token Balances by Wallet(s)        | `api.simplehash.com/api/v0/fungibles/balances`                | [Details](#token-balances-by-wallets)        |
| Token Top Holders                  | `api.simplehash.com/api/v0/fungibles/top_wallets`             | [Details](#token-top-holders)                |
| Swaps & Transfers by Wallet(s)     | `api.simplehash.com/api/v0/fungibles/transfers/wallets`       | [Details](#swaps--transfers-by-wallets)      |
| Swaps & Transfers by Token         | `api.simplehash.com/api/v0/fungibles/transfers/wallets`       | [Details](#swaps--transfers-by-token)        |
| Historical Token Prices            | `api.simplehash.com/api/v0/fungibles/prices_v2/{fungible_id}` | [Details](#historical-token-prices)          |
| Historical Token OHLC              | `api.simplehash.com/api/v0/fungibles/ohlc/{fungible_id}`      | [Details](#historical-token-ohlc)            |
| Native Token Balances by Wallet(s) | `api.simplehash.com/api/v0/native_tokens/balances`            | [Details](#native-token-balances-by-wallets) |

### NFT API

| Feature                            | SimpleHash Endpoint                                                                       | Moralis Equivalent                             |
| ---------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------- |
| NFT by Token ID                    | `api.simplehash.com/api/v0/nfts/{chain}/{contract_address}/{token_id}`                    | [Details](#nft-by-token-id)                    |
| NFTs by Contract                   | `api.simplehash.com/api/v0/nfts/{chain}/{contract_address}`                               | [Details](#nfts-by-contract)                   |
| NFTs by Wallet(s)                  | `api.simplehash.com/api/v0/nfts/owners_v2`                                                | [Details](#nfts-by-wallets)                    |
| Sales & Transfers by Wallet(s)     | `api.simplehash.com/api/v0/nfts/transfers/wallets`                                        | [Details](#sales--transfers-by-wallets)        |
| Sales & Transfers by NFT           | `api.simplehash.com/api/v0/nfts/transfers/{chain}/{contract_address}/{token_id}`          | [Details](#sales--transfers-by-nft)            |
| Sales & Transfers by Contract      | `api.simplehash.com/api/v0/nfts/transfers/{chain}/{contract_address}`                     | [Details](#sales--transfers-by-contract)       |
| Owners by NFT                      | `api.simplehash.com/api/v0/nfts/owners/{chain}/{contract_address}/{token_id}`             | [Details](#owners-by-nft)                      |
| Owners by Contract                 | `api.simplehash.com/api/v0/nfts/owners/{chain}/{contract_address}/`                       | [Details](#owners-by-contract)                 |
| Ownership Summary by Wallet(s)     | `api.simplehash.com/api/v0/nfts/contracts`                                                | [Details](#ownership-summary-by-wallets)       |
| Collections by Wallet(s)           | `api.simplehash.com/api/v0/nfts/collections_by_wallets_v2`                                | [Details](#collections-by-wallets)             |
| Collections by Contract            | `api.simplehash.com/api/v0/nfts/collections/{chain}/{contract_address}`                   | [Details](#collections-by-contract)            |
| Collection Historical Floor Prices | `api.simplehash.com/api/v0/nfts/floor_prices_v2/collection/{collection_id}/{granularity}` | [Details](#collection-historical-floor-prices) |
| Top Collections                    | `api.simplehash.com/api/v0/nfts/collections/top_v2`                                       | [Details](#top-collections)                    |
| Trending Collections               | `api.simplehash.com/api/v0/nfts/collections/trending`                                     | [Details](#trending-collections)               |
| Traits by Collection               | `api.simplehash.com/api/v0/nfts/traits/collection/{collection_id}`                        | [Details](#traits-by-collection)               |
| Wallet Valuation                   | `api.simplehash.com/api/v0/nfts/owners/value`                                             | [Details](#wallet-valuation)                   |
| Refresh NFT Metadata               | `api.simplehash.com/api/v0/nfts/refresh/{chain}/{contract_address}/{token_id}`            | [Details](#refresh-nft-metadata)               |
| Refresh Contract Metadata          | `api.simplehash.com/reference/refresh-contract-metadata`                                  | [Details](#refresh-contract-metadata)          |

## Token API

### Token & Prices

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/assets`

| Chain  | Moralis Equivalent        | Moralis URL                                                       | Documentation                                                  |
| ------ | ------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------- |
| EVM    | Get Token Price           | `https://deep-index.moralis.io/api/v2.2/erc20/:address/price`     | [Documentation](/data-api/evm/token/prices/token-price)        |
| EVM    | Get Multiple Token Prices | `https://deep-index.moralis.io/api/v2.2/erc20/prices`             | [Documentation](/data-api/evm/token/prices/token-prices-batch) |
| Solana | Get Token Price           | `https://solana-gateway.moralis.io/token/:network/:address/price` | [Documentation](/data-api/solana/token/prices/token-price)     |

**Notes**: Moralis also supports historical price lookups by block number and returns additional metadata like links.

### Token Balances by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/balances?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain  | Moralis Equivalent   | Moralis URL                                                             | Documentation                                           |
| ------ | -------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------- |
| EVM    | Get Token Balances   | `https://deep-index.moralis.io/api/v2.2/wallets/:address/tokens`        | [Documentation](/data-api/evm/wallet/token-balances)    |
| Solana | Get Wallet Portfolio | `https://solana-gateway.moralis.io/account/:network/:address/portfolio` | [Documentation](/data-api/solana/wallet/portfolio)      |
| Solana | Get Token Balances   | `https://solana-gateway.moralis.io/account/:network/:address/tokens`    | [Documentation](/data-api/solana/wallet/token-balances) |

### Token Top Holders

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/top_wallets`

| Chain  | Moralis Equivalent       | Moralis URL                                                          | Documentation                                              |
| ------ | ------------------------ | -------------------------------------------------------------------- | ---------------------------------------------------------- |
| EVM    | Get Token Holders        | `https://deep-index.moralis.io/api/v2.2/erc20/:token_address/owners` | [Documentation](/data-api/evm/token/holders/token-holders) |
| Solana | Coming Soon (March 2025) | -                                                                    | -                                                          |

**Notes**: Moralis provides additional endpoints including ERC20 Token Holder Stats and ERC20 Token Holders Timeseries.

#### Swaps & Transfers by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/transfers/wallets?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain  | Moralis Equivalent  | Moralis URL                                                               | Documentation                                         |
| ------ | ------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------- |
| EVM    | Get Swaps by Wallet | `https://deep-index.moralis.io/api/v2.2/wallets/:address/swaps`           | [Documentation](/data-api/evm/wallet/wallet-swaps)    |
| Solana | Get Swaps by Wallet | `https://solana-gateway.moralis.io/account/:network/:walletAddress/swaps` | [Documentation](/data-api/solana/wallet/wallet-swaps) |

**Notes**: Moralis offers additional related endpoints including ERC20 token transfers by wallet and the comprehensive wallet history API.

### Swaps & Transfers by Token

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/transfers/wallets?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain  | Moralis Equivalent         | Moralis URL                                                            | Documentation                                             |
| ------ | -------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------- |
| EVM    | Get Swaps by Token Address | `https://deep-index.moralis.io/api/v2.2/erc20/:address/swaps`          | [Documentation](/data-api/evm/token/swaps/token-swaps)    |
| Solana | Get Swaps by Token Address | `https://solana-gateway.moralis.io/token/:network/:tokenAddress/swaps` | [Documentation](/data-api/solana/token/swaps/token-swaps) |

**Notes**: Moralis provides additional related endpoints including ERC20 token transfers by contract, swaps by pair address, and Solana swaps by pair address.

### Historical Token Prices

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/prices_v2/{fungible_id}`

| Chain | Moralis Equivalent        | Moralis URL                                                   | Documentation                                                  |
| ----- | ------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------- |
| EVM   | Get Token Price           | `https://deep-index.moralis.io/api/v2.2/erc20/:address/price` | [Documentation](/data-api/evm/token/prices/token-price)        |
| EVM   | Get Multiple Token Prices | `https://deep-index.moralis.io/api/v2.2/erc20/prices`         | [Documentation](/data-api/evm/token/prices/token-prices-batch) |

### Historical Token OHLC

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/fungibles/ohlc/{fungible_id}`

| Chain  | Moralis Equivalent        | Moralis URL                                                                 | Documentation                                       |
| ------ | ------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------- |
| EVM    | Get OHLCV by Pair Address | `https://deep-index.moralis.io/api/v2.2/pairs/:address/ohlcv`               | [Documentation](/data-api/evm/token/prices/ohlc)    |
| Solana | Get OHLCV by Pair Address | `https://solana-gateway.moralis.io/token/:network/pairs/:pairAddress/ohlcv` | [Documentation](/data-api/solana/token/prices/ohlc) |

### Native Token Balances by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/native_tokens/balances?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain  | Moralis Equivalent                          | Moralis URL                                                           | Documentation                                               |
| ------ | ------------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------- |
| EVM    | Get Native Balance by Wallet                | `https://deep-index.moralis.io/api/v2.2/:address/balance`             | [Documentation](/data-api/evm/wallet/native-balance)        |
| EVM    | Get Native Balance for Multiple Wallets     | `https://deep-index.moralis.io/api/v2.2/wallets/balances`             | [Documentation](/data-api/evm/wallet/native-balances-batch) |
| EVM    | Get Native & ERC20 Token Balances by Wallet | `https://deep-index.moralis.io/api/v2.2/wallets/:address/tokens`      | [Documentation](/data-api/evm/wallet/token-balances)        |
| Solana | Get Native Token Balance by Wallet          | `https://solana-gateway.moralis.io/account/:network/:address/balance` | [Documentation](/data-api/solana/wallet/native-balance)     |

## NFT API

### NFT by Token ID

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/{chain}/{contract_address}/{token_id}`

| Chain  | Moralis Equivalent | Moralis URL                                                        | Documentation                                            |
| ------ | ------------------ | ------------------------------------------------------------------ | -------------------------------------------------------- |
| EVM    | Get NFT Metadata   | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id`    | [Documentation](/data-api/evm/nft/metadata/nft-metadata) |
| Solana | Get NFT Metadata   | `https://solana-gateway.moralis.io/nft/:network/:address/metadata` | [Documentation](/data-api/solana/nft/nft-metadata)       |

### NFTs by Contract

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/{chain}/{contract_address}`

| Chain | Moralis Equivalent   | Moralis URL                                           | Documentation                                                     |
| ----- | -------------------- | ----------------------------------------------------- | ----------------------------------------------------------------- |
| EVM   | Get NFTs by Contract | `https://deep-index.moralis.io/api/v2.2/nft/:address` | [Documentation](/data-api/evm/nft/collections/nfts-by-collection) |

### NFTs by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/owners_v2?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain  | Moralis Equivalent | Moralis URL                                                       | Documentation                                                 |
| ------ | ------------------ | ----------------------------------------------------------------- | ------------------------------------------------------------- |
| EVM    | Get NFTs by Wallet | `https://deep-index.moralis.io/api/v2.2/:address/nft`             | [Documentation](/data-api/evm/nft/collections/nfts-by-wallet) |
| Solana | Get NFTs by Wallet | `https://solana-gateway.moralis.io/account/:network/:address/nft` | [Documentation](/data-api/solana/wallet/nft-balances)         |

### Sales & Transfers by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/transfers/wallets?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain | Moralis Equivalent       | Moralis URL                                                           | Documentation                                              |
| ----- | ------------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------- |
| EVM   | Get NFT Trades by Wallet | `https://deep-index.moralis.io/api/v2.2/wallets/:address/nfts/trades` | [Documentation](/data-api/evm/wallet/nft-trades-by-wallet) |

**Notes**: Moralis offers additional related endpoints including NFT transfers by wallet and comprehensive wallet history.

### Sales & Transfers by NFT

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/transfers/{chain}/{contract_address}/{token_id}`

| Chain | Moralis Equivalent      | Moralis URL                                                            | Documentation                                                |
| ----- | ----------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| EVM   | Get NFT Trades by Token | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/trades` | [Documentation](/data-api/evm/nft/trades/trades-by-token-id) |

### Sales & Transfers by Contract

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/transfers/{chain}/{contract_address}`

| Chain | Moralis Equivalent         | Moralis URL                                                  | Documentation                                               |
| ----- | -------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------- |
| EVM   | Get NFT Trades by Contract | `https://deep-index.moralis.io/api/v2.2/nft/:address/trades` | [Documentation](/data-api/evm/nft/trades/collection-trades) |

### Owners by NFT

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/owners/{chain}/{contract_address}/{token_id}`

| Chain | Moralis Equivalent         | Moralis URL                                                            | Documentation                                                   |
| ----- | -------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| EVM   | Get NFT Owners by Token ID | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/owners` | [Documentation](/data-api/evm/nft/ownership/owners-by-token-id) |

### Owners by Contract

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/owners/{chain}/{contract_address}/`

| Chain | Moralis Equivalent         | Moralis URL                                                  | Documentation                                                   |
| ----- | -------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------- |
| EVM   | Get NFT Owners by Contract | `https://deep-index.moralis.io/api/v2.2/nft/:address/owners` | [Documentation](/data-api/evm/nft/ownership/owners-by-contract) |

### Ownership Summary by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/contracts?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain | Moralis Equivalent            | Moralis URL                                                       | Documentation                                                            |
| ----- | ----------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| EVM   | Get NFT Collections by Wallet | `https://deep-index.moralis.io/api/v2.2/:address/nft/collections` | [Documentation](/data-api/evm/nft/collections/nft-collections-by-wallet) |

**Notes**: Moralis supports filtering by token address(es).

### Collections by Wallet(s)

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/collections_by_wallets_v2?chains={chains}&wallet_addresses={wallet_addresses}`

| Chain | Moralis Equivalent            | Moralis URL                                                       | Documentation                                                            |
| ----- | ----------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| EVM   | Get NFT Collections by Wallet | `https://deep-index.moralis.io/api/v2.2/:address/nft/collections` | [Documentation](/data-api/evm/nft/collections/nft-collections-by-wallet) |

### Collections by Contract

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/collections/{chain}/{contract_address}`

| Chain | Moralis Equivalent          | Moralis URL                                                    | Documentation                                                   |
| ----- | --------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------- |
| EVM   | Get NFT Collection Metadata | `https://deep-index.moralis.io/api/v2.2/nft/:address/metadata` | [Documentation](/data-api/evm/nft/metadata/collection-metadata) |

### Collection Historical Floor Prices

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/floor_prices_v2/collection/{collection_id}/{granularity}`

| Chain | Moralis Equivalent                         | Moralis URL                                                                  | Documentation                                                    |
| ----- | ------------------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| EVM   | Get NFT Historical Floor Price by Contract | `https://deep-index.moralis.io/api/v2.2/nft/:address/floor-price/historical` | [Documentation](/data-api/evm/nft/prices/historical-floor-price) |

**Notes**: Floor prices are supported on Ethereum & Base. Moralis also offers additional endpoints for NFT Floor Price by Contract, NFT Floor Price by Token ID, Sale Prices by Contract, and Sale Prices by Token ID.

### Trait Floor Prices by NFT

| Chain | Moralis Equivalent | Moralis URL                                                          | Documentation                                            |
| ----- | ------------------ | -------------------------------------------------------------------- | -------------------------------------------------------- |
| EVM   | Get NFTs by Traits | `https://deep-index.moralis.io/api/v2.2/nft/:address/nfts-by-traits` | [Documentation](/data-api/evm/nft/traits/nfts-by-traits) |

### Top Collections

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/collections/top_v2`

| Chain | Moralis Equivalent                    | Moralis URL                                                               | Documentation                                                   |
| ----- | ------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------- |
| EVM   | Get Top NFT Collections by Market Cap | `https://deep-index.moralis.io/api/v2.2/market-data/nfts/top-collections` | [Documentation](/data-api/evm/nft/discovery/nfts-by-market-cap) |

**Notes**: Currently only supports Ethereum.

### Trending Collections

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/collections/trending`

| Chain | Moralis Equivalent                        | Moralis URL                                                                   | Documentation                                               |
| ----- | ----------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------- |
| EVM   | Get Top NFT Collections by Trading Volume | `https://deep-index.moralis.io/api/v2.2/market-data/nfts/hottest-collections` | [Documentation](/data-api/evm/nft/discovery/nfts-by-volume) |

**Notes**: Currently only supports Ethereum.

### Traits by Collection

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/traits/collection/{collection_id}`

| Chain | Moralis Equivalent           | Moralis URL                                                  | Documentation                                                  |
| ----- | ---------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| EVM   | Get NFT Traits by Collection | `https://deep-index.moralis.io/api/v2.2/nft/:address/traits` | [Documentation](/data-api/evm/nft/traits/traits-by-collection) |

**Notes**: Moralis also offers an endpoint to get NFTs by traits.

### Wallet Valuation

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/owners/value`

| Chain | Moralis Equivalent  | Moralis URL                                                         | Documentation                                   |
| ----- | ------------------- | ------------------------------------------------------------------- | ----------------------------------------------- |
| EVM   | Get Wallet Networth | `https://deep-index.moralis.io/api/v2.2/wallets/:address/net-worth` | [Documentation](/data-api/evm/wallet/net-worth) |

**Notes**: Currently calculates based on fungibles.

### Refresh NFT Metadata

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/nfts/refresh/{chain}/{contract_address}/{token_id}`

| Chain | Moralis Equivalent  | Moralis URL                                                                     | Documentation                                                    |
| ----- | ------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| EVM   | Resync NFT Metadata | `https://deep-index.moralis.io/api/v2.2/nft/:address/:token_id/metadata/resync` | [Documentation](/data-api/evm/nft/utilities/resync-nft-metadata) |

### Refresh Contract Metadata

**SimpleHash Endpoint**: `https://docs.simplehash.com/reference/refresh-contract-metadata`

| Chain | Moralis Equivalent            | Moralis URL                   | Documentation                 |
| ----- | ----------------------------- | ----------------------------- | ----------------------------- |
| EVM   | Available as Premium Endpoint | Available as Premium Endpoint | Available as Premium Endpoint |

## Name Resolution

### ENS Lookup

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/ens/lookup`

| Chain | Moralis Equivalent | Moralis URL                                                  | Documentation                                    |
| ----- | ------------------ | ------------------------------------------------------------ | ------------------------------------------------ |
| EVM   | Resolve ENS Domain | `https://deep-index.moralis.io/api/v2.2/resolve/ens/:domain` | [Documentation](/data-api/evm/wallet/ens-lookup) |

**Notes**: Moralis offers additional endpoints for resolving Unstoppable Domains and other resolution services.

### Reverse ENS Lookup

**SimpleHash Endpoint**: `https://api.simplehash.com/api/v0/ens/reverse_lookup`

| Chain | Moralis Equivalent | Moralis URL                                                       | Documentation                                         |
| ----- | ------------------ | ----------------------------------------------------------------- | ----------------------------------------------------- |
| EVM   | Resolve Address    | `https://deep-index.moralis.io/api/v2.2/resolve/:address/reverse` | [Documentation](/data-api/evm/wallet/resolve-address) |

**Notes**: Moralis provides additional endpoints for getting Unstoppable Domain by Address and Address by Unstoppable Domain.

## Real-time Data

### Webhooks

| Feature          | Moralis Equivalent | Moralis URL                   | Documentation                      |
| ---------------- | ------------------ | ----------------------------- | ---------------------------------- |
| Real-time Events | Streams API        | N/A - Setup through dashboard | [Documentation](/streams/overview) |

**Notes**: Moralis Streams API provides powerful real-time blockchain data capabilities, including filters, webhooks, and managed infrastructure. Unlike SimpleHash, Moralis offers comprehensive support for real-time blockchain events tracking.

## Beyond SimpleHash: Exclusive Moralis Capabilities

Moralis offers many additional endpoints and features not available in SimpleHash. Here are some of our most popular exclusive endpoints:

### Advanced Wallet Analysis

| Feature              | Endpoint                                                                | Documentation                                        |
| -------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------- |
| **Wallet History**   | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/history`   | [Documentation](/data-api/evm/wallet/wallet-history) |
| **Wallet Approvals** | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/approvals` | [Documentation](/data-api/evm/wallet/approvals)      |
| **Wallet Net Worth** | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/net-worth` | [Documentation](/data-api/evm/wallet/net-worth)      |

### Token Analytics

| Feature                      | Endpoint                                                                             | Documentation                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| **Token Holder Stats**       | `GET https://deep-index.moralis.io/api/v2.2/erc20/:token_address/holders/stats`      | [Documentation](/data-api/evm/token/holders/token-holder-stats)       |
| **Historical Token Holders** | `GET https://deep-index.moralis.io/api/v2.2/erc20/:token_address/holders/historical` | [Documentation](/data-api/evm/token/holders/historical-token-holders) |

### Token Search & Discovery

| Feature             | Endpoint                                                     | Documentation                                                  |
| ------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| **Search Tokens**   | `GET https://deep-index.moralis.io/api/v2.2/tokens/search`   | [Documentation](/data-api/universal/token/search/token-search) |
| **Trending Tokens** | `GET https://deep-index.moralis.io/api/v2.2/tokens/trending` | [Documentation](/data-api/universal/token/trending-tokens)     |

### DEX and Pair Analytics

| Feature                         | Endpoint                                                                | Documentation                                         |
| ------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------- |
| **Pair Stats**                  | `GET https://deep-index.moralis.io/api/v2.2/pairs/:address/stats`       | [Documentation](/data-api/evm/token/swaps/pair-stats) |
| **Aggregated Token Pair Stats** | `GET https://deep-index.moralis.io/api/v2.2/:token_address/pairs/stats` | [Documentation](/data-api/evm/token/swaps/pair-stats) |

### NFT Advanced Capabilities

* **Enriched Metadata**: Access fully enriched and normalized metadata on NFT collections and individual tokens through a single API call
* **Real-time NFT Transfer Data**: Get all the latest NFT transfer data for specific NFTs, wallets, or track real-time transfers
* **Advanced Spam Detection**: Protect your platform from undesirable NFTs with collection spam indicators
* **On-chain Pricing Data**: Incorporate on-chain pricing data including last sale prices and floor prices
* **Optimized Image Previews**: Benefit from dynamically sized image previews and conversions to user-friendly formats

## Getting Started with Moralis

1. **Sign up for a Moralis account**: [https://admin.moralis.com/register](https://admin.moralis.com/register)
2. **Get your API key**: Navigate to the Web3 APIs section in your dashboard
3. **Update your API calls**: Replace SimpleHash endpoints with the corresponding Moralis endpoints
4. **Explore the documentation**: [https://docs.moralis.com/](https://docs.moralis.com/)

## Why Choose Moralis?

<Tip>
  **MIGRATION SUPPORT AVAILABLE** - Moralis has a dedicated team to help you migrate smoothly from SimpleHash. [Contact our team](https://developers.moralis.com/) for personalized support and to learn about special developer discounts for teams transitioning from SimpleHash.
</Tip>

### Trusted by Industry Leaders

Moralis APIs power some of the biggest names in the crypto space:

* MetaMask
* Kraken
* Blockchain.com
* And many other top wallets and applications

### Migration Support

Our dedicated migration team is ready to help SimpleHash users transition smoothly:

* Technical guidance to map your existing implementation
* Support with API key setup and configuration
* Best practices for optimizing API usage

### Developer Discounts

Contact our team today to learn about special pricing options available for teams migrating from SimpleHash.

Moralis is committed to providing a seamless transition for SimpleHash users with comprehensive support throughout your migration journey.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Migrating from OKLink to Moralis

> OKLink is suspending their Explorer API on May 20th, 2025. Any project using OKLink Explorer API needs a new provider before then. Migrate to Moralis APIs in 4 simple steps!

# Migrating from OKLink to Moralis

<Warning>
  **URGENT MIGRATION NEEDED** - OKLink is suspending all their Explorer APIs on May 20th, 2025. Applications and platforms using OKLink Explorer API need to migrate as soon as possible to avoid service disruptions. Moralis APIs offer equivalent functionality, making migration straightforward.
</Warning>

With OKLink suspending their API offering, Moralis provides a comprehensive alternative with equivalent functionality and additional capabilities. This guide will help you seamlessly transition your projects from OKLink to Moralis.

## API Endpoint Equivalence

OKLink endpoints can be easily mapped to Moralis equivalents. Below you'll find the mapping organized by API category.

## Quick Reference Guide

Make use of the table below to quickly find the Moralis equivalent for each OKLink endpoint by clicking on the Moralis Equivalent column.

### Solana API

| Feature                    | OKLink Endpoint                                                                     | Moralis Equivalent                     |
| -------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------- |
| Get Account Asset Balances | `https://www.oklink.com/docs/en/#sol-data-account-data-get-addresses-asset-balance` | [Details](#get-account-asset-balances) |
| Get SOL Account Balance    | `https://www.oklink.com/docs/en/#sol-data-account-data-get-sol-account-balance`     | [Details](#get-sol-account-balance)    |
| Get Token Balance          | `https://www.oklink.com/docs/en/#sol-data-account-data-get-token-balance`           | [Details](#get-token-balance)          |
| Get Transaction List       | `https://www.oklink.com/docs/en/#sol-data-account-data-get-transaction-list`        | [Details](#get-transaction-list)       |

### NFT API

| Feature                        | OKLink Endpoint                                                           | Moralis Equivalent                         |
| ------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------ |
| Get Collection Overview        | `https://www.oklink.com/docs/en/#nft-data-get-collection-overview`        | [Details](#get-collection-overview)        |
| Get NFT List Within Collection | `https://www.oklink.com/docs/en/#nft-data-get-nft-list-within-collection` | [Details](#get-nft-list-within-collection) |
| Get Holder List for Collection | `https://www.oklink.com/docs/en/#nft-data-get-holder-list-for-collection` | [Details](#get-holder-list-for-collection) |
| Get Collection Floor Price     | `https://www.oklink.com/docs/en/#nft-data-get-collection-floor-price`     | [Details](#get-collection-floor-price)     |
| Get Detailed Data for NFT      | `https://www.oklink.com/docs/en/#nft-data-get-detailed-data-for-nft`      | [Details](#get-detailed-data-for-nft)      |
| Get NFT Holder Address         | `https://www.oklink.com/docs/en/#nft-data-get-nft-holder-address`         | [Details](#get-nft-holder-address)         |
| Get NFT Transaction History    | `https://www.oklink.com/docs/en/#nft-data-get-nft-transaction-history`    | [Details](#get-nft-transaction-history)    |
| Get NFT List Held by Address   | `https://www.oklink.com/docs/en/#nft-data-get-nft-list-held-by-address`   | [Details](#get-nft-list-held-by-address)   |

### Token API

| Feature                           | OKLink Endpoint                                                                            | Moralis Equivalent                            |
| --------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------- |
| Get Token List                    | `https://www.oklink.com/docs/en/#token-price-data-get-token-list`                          | [Details](#get-token-list)                    |
| Get Historical Token Price        | `https://www.oklink.com/docs/en/#token-price-data-get-historical-token-price`              | [Details](#get-historical-token-price)        |
| Get Latest Token Price in Batches | `https://www.oklink.com/docs/en/#token-price-data-get-latest-token-price-in-batches`       | [Details](#get-latest-token-price-in-batches) |
| Get Token Market Data             | `https://www.oklink.com/docs/en/#token-price-data-get-latest-token-price-in-batches`       | [Details](#get-token-market-data)             |
| Check Liquidity Pool Addresses    | `https://www.oklink.com/docs/en/#token-price-data-check-liquidity-pool-addresses-by-token` | [Details](#check-liquidity-pool-addresses)    |
| Get Individual Transaction Data   | `https://www.oklink.com/docs/en/#token-price-data-get-individual-transaction-data`         | [Details](#get-individual-transaction-data)   |

### Other Services

| Feature              | OKLink Endpoint                                                | Moralis Equivalent               |
| -------------------- | -------------------------------------------------------------- | -------------------------------- |
| Webhook Subscription | `https://www.oklink.com/docs/en/#webhook-subscription-service` | [Details](#webhook-subscription) |
| EVM RPC Data         | `https://www.oklink.com/docs/en/#evm-rpc-data`                 | [Details](#evm-rpc-data)         |

## Solana API

### Get Account Asset Balances

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#sol-data-account-data-get-addresses-asset-balance`

| Chain  | Moralis Equivalent     | Documentation                                           |
| ------ | ---------------------- | ------------------------------------------------------- |
| Solana | Get Sol Portfolio      | [Documentation](/data-api/solana/wallet/portfolio)      |
| Solana | Get Wallet NFTs        | [Documentation](/data-api/solana/wallet/nft-balances)   |
| Solana | Get Native SOL Balance | [Documentation](/data-api/solana/wallet/native-balance) |

**Notes**: Moralis provides comprehensive asset balance data including SOL tokens, SPL tokens, and NFTs in a single API call or through dedicated endpoints for each asset type.

### Get SOL Account Balance

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#sol-data-account-data-get-sol-account-balance`

| Chain  | Moralis Equivalent     | Documentation                                           |
| ------ | ---------------------- | ------------------------------------------------------- |
| Solana | Get Native SOL Balance | [Documentation](/data-api/solana/wallet/native-balance) |

**Notes**: This endpoint provides the native SOL balance for a given wallet address.

### Get Token Balance

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#sol-data-account-data-get-token-balance`

| Chain  | Moralis Equivalent | Documentation                                           |
| ------ | ------------------ | ------------------------------------------------------- |
| Solana | Get SPL Token Info | [Documentation](/data-api/solana/wallet/token-balances) |

**Notes**: This endpoint returns detailed information about SPL tokens, including balances, metadata, and more.

### Get Transaction List

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#sol-data-account-data-get-transaction-list`

| Chain  | Moralis Equivalent           | Documentation                                         |
| ------ | ---------------------------- | ----------------------------------------------------- |
| Solana | Get Wallet Swap Transactions | [Documentation](/data-api/solana/wallet/wallet-swaps) |

**Notes**: This endpoint provides swap transaction history for a wallet on Solana.

## NFT API

### Get Collection Overview

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-collection-overview`

| Chain | Moralis Equivalent          | Documentation                                                   |
| ----- | --------------------------- | --------------------------------------------------------------- |
| EVM   | Get NFT Collection Metadata | [Documentation](/data-api/evm/nft/metadata/collection-metadata) |

**Notes**: This endpoint returns comprehensive metadata about an NFT collection, including name, symbol, token standard, and more.

### Get NFT List Within Collection

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-nft-list-within-collection`

| Chain | Moralis Equivalent   | Documentation                                                     |
| ----- | -------------------- | ----------------------------------------------------------------- |
| EVM   | Get NFTs by Contract | [Documentation](/data-api/evm/nft/collections/nfts-by-collection) |

**Notes**: This endpoint retrieves all NFTs within a specific contract with pagination support for large collections.

### Get Holder List for Collection

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-holder-list-for-collection`

| Chain | Moralis Equivalent         | Documentation                                                   |
| ----- | -------------------------- | --------------------------------------------------------------- |
| EVM   | Get NFT Owners by Contract | [Documentation](/data-api/evm/nft/ownership/owners-by-contract) |

**Notes**: This endpoint retrieves the complete list of owners for a specific NFT collection.

### Get Collection Floor Price

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-collection-floor-price`

| Chain | Moralis Equivalent              | Documentation                                                    |
| ----- | ------------------------------- | ---------------------------------------------------------------- |
| EVM   | Get NFT Floor Price by Contract | [Documentation](/data-api/evm/nft/prices/collection-floor-price) |

**Notes**: This endpoint provides floor price data from major marketplaces for a specific NFT collection.

### Get Detailed Data for NFT

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-detailed-data-for-nft`

| Chain  | Moralis Equivalent   | Documentation                                            |
| ------ | -------------------- | -------------------------------------------------------- |
| EVM    | Get NFT Metadata     | [Documentation](/data-api/evm/nft/metadata/nft-metadata) |
| Solana | Get SOL NFT Metadata | [Documentation](/data-api/solana/nft/nft-metadata)       |

**Notes**: These endpoints provide comprehensive metadata for individual NFTs, including attributes, images, and other on-chain data.

### Get NFT Holder Address

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-nft-holder-address`

| Chain | Moralis Equivalent         | Documentation                                                   |
| ----- | -------------------------- | --------------------------------------------------------------- |
| EVM   | Get NFT Owners by Token ID | [Documentation](/data-api/evm/nft/ownership/owners-by-token-id) |

**Notes**: This endpoint retrieves owner information for a specific NFT token ID within a collection.

### Get NFT Transaction History

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-nft-transaction-history`

| Chain | Moralis Equivalent         | Documentation                                                     |
| ----- | -------------------------- | ----------------------------------------------------------------- |
| EVM   | Get NFT Contract Transfers | [Documentation](/data-api/evm/nft/transfers/collection-transfers) |
| EVM   | Get NFT Trades             | [Documentation](/data-api/evm/nft/trades/collection-trades)       |

**Notes**: These endpoints provide comprehensive transfer and trade history for NFTs, including marketplace sales and P2P transfers.

### Get NFT List Held by Address

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#nft-data-get-nft-list-held-by-address`

| Chain  | Moralis Equivalent | Documentation                                                 |
| ------ | ------------------ | ------------------------------------------------------------- |
| EVM    | Get Wallet NFTs    | [Documentation](/data-api/evm/nft/collections/nfts-by-wallet) |
| Solana | Get SOL NFTs       | [Documentation](/data-api/solana/wallet/nft-balances)         |

**Notes**: These endpoints retrieve all NFTs held by a specific wallet address with rich metadata.

## Token API

### Get Token List

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#token-price-data-get-token-list`

| Chain | Moralis Equivalent  | Documentation                                                  |
| ----- | ------------------- | -------------------------------------------------------------- |
| EVM   | Get Filtered Tokens | [Documentation](/data-api/evm/token/discovery/filtered-tokens) |

**Notes**: This endpoint allows retrieving tokens with various filtering options.

### Get Historical Token Price

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#token-price-data-get-historical-token-price`

| Chain  | Moralis Equivalent        | Documentation                                                     |
| ------ | ------------------------- | ----------------------------------------------------------------- |
| EVM    | Get Multiple Token Prices | [Documentation](/data-api/evm/token/prices/token-prices-batch)    |
| EVM    | Get OHLCV by Pair Address | [Documentation](/data-api/evm/token/prices/ohlc)                  |
| Solana | Get Multiple Token Prices | [Documentation](/data-api/solana/token/prices/token-prices-batch) |
| Solana | Get OHLCV by Pair Address | [Documentation](/data-api/solana/token/prices/ohlc)               |

**Notes**: These endpoints provide price history data for tokens across different timeframes.

### Get Latest Token Price in Batches

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#token-price-data-get-latest-token-price-in-batches`

| Chain  | Moralis Equivalent        | Documentation                                                     |
| ------ | ------------------------- | ----------------------------------------------------------------- |
| EVM    | Get Multiple Token Prices | [Documentation](/data-api/evm/token/prices/token-prices-batch)    |
| EVM    | Get OHLCV by Pair Address | [Documentation](/data-api/evm/token/prices/ohlc)                  |
| Solana | Get Multiple Token Prices | [Documentation](/data-api/solana/token/prices/token-prices-batch) |
| Solana | Get OHLCV by Pair Address | [Documentation](/data-api/solana/token/prices/ohlc)               |

**Notes**: These endpoints support batch requests for fetching current prices of multiple tokens in a single API call.

### Get Token Market Data

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#token-price-data-get-latest-token-price-in-batches`

| Chain  | Moralis Equivalent  | Documentation                                                          |
| ------ | ------------------- | ---------------------------------------------------------------------- |
| EVM    | Get Token Metadata  | [Documentation](/data-api/evm/token/metadata/token-metadata)           |
| EVM    | Get Token Analytics | [Documentation](/data-api/evm/token/metadata/token-score)              |
| Solana | Get Token Metadata  | [Documentation](/data-api/solana/token/token-metadata)                 |
| Solana | Get Token Analytics | [Documentation](/data-api/solana/token/market-metrics/token-analytics) |

**Notes**: These endpoints provide comprehensive token metadata including marketcap, supply information, and other analytics.

### Check Liquidity Pool Addresses

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#token-price-data-check-liquidity-pool-addresses-by-token`

| Chain  | Moralis Equivalent         | Documentation                                             |
| ------ | -------------------------- | --------------------------------------------------------- |
| EVM    | Get Token Pairs            | [Documentation](/data-api/evm/token/swaps/token-pairs)    |
| Solana | Get Token Pairs by Address | [Documentation](/data-api/solana/token/pairs/token-pairs) |

**Notes**: These endpoints provide information about liquidity pairs for specific tokens across various DEXes.

### Get Individual Transaction Data

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#token-price-data-get-individual-transaction-data`

| Chain | Moralis Equivalent      | Documentation                                                         |
| ----- | ----------------------- | --------------------------------------------------------------------- |
| EVM   | Get Transaction         | [Documentation](/data-api/evm/blockchain/transaction-by-hash)         |
| EVM   | Get Decoded Transaction | [Documentation](/data-api/evm/blockchain/transaction-by-hash-decoded) |

**Notes**: These endpoints retrieve detailed transaction data, including decoded information for enhanced readability.

## Other Services

### Webhook Subscription

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#webhook-subscription-service`

| Service  | Moralis Equivalent | Documentation                      |
| -------- | ------------------ | ---------------------------------- |
| Webhooks | Streams API        | [Documentation](/streams/overview) |

**Notes**: Moralis Streams API provides powerful real-time blockchain data capabilities, including filters, webhooks, and managed infrastructure.

### EVM RPC Data

**OKLink Endpoint**: `https://www.oklink.com/docs/en/#evm-rpc-data`

| Service | Moralis Equivalent | Documentation                        |
| ------- | ------------------ | ------------------------------------ |
| RPC     | Moralis RPC Nodes  | [Documentation](/rpc-nodes/overview) |

**Notes**: Moralis provides reliable and high-performance RPC nodes across multiple blockchain networks.

## Beyond OKLink: Exclusive Moralis Capabilities

Moralis offers many additional endpoints and features not available in OKLink. Here are some of our most popular exclusive endpoints:

### Advanced Wallet Analysis

| Feature              | Endpoint                                                                | Documentation                                        |
| -------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------- |
| **Wallet History**   | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/history`   | [Documentation](/data-api/evm/wallet/wallet-history) |
| **Wallet Approvals** | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/approvals` | [Documentation](/data-api/evm/wallet/approvals)      |
| **Wallet Net Worth** | `GET https://deep-index.moralis.io/api/v2.2/wallets/:address/net-worth` | [Documentation](/data-api/evm/wallet/net-worth)      |

### Token Analytics

| Feature                      | Endpoint                                                                             | Documentation                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| **Token Holder Stats**       | `GET https://deep-index.moralis.io/api/v2.2/erc20/:token_address/holders/stats`      | [Documentation](/data-api/evm/token/holders/token-holder-stats)       |
| **Historical Token Holders** | `GET https://deep-index.moralis.io/api/v2.2/erc20/:token_address/holders/historical` | [Documentation](/data-api/evm/token/holders/historical-token-holders) |

### Token Search & Discovery

| Feature             | Endpoint                                                     | Documentation                                                  |
| ------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| **Search Tokens**   | `GET https://deep-index.moralis.io/api/v2.2/tokens/search`   | [Documentation](/data-api/universal/token/search/token-search) |
| **Trending Tokens** | `GET https://deep-index.moralis.io/api/v2.2/tokens/trending` | [Documentation](/data-api/universal/token/trending-tokens)     |

### DEX and Pair Analytics

| Feature                         | Endpoint                                                                | Documentation                                         |
| ------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------- |
| **Pair Stats**                  | `GET https://deep-index.moralis.io/api/v2.2/pairs/:address/stats`       | [Documentation](/data-api/evm/token/swaps/pair-stats) |
| **Aggregated Token Pair Stats** | `GET https://deep-index.moralis.io/api/v2.2/:token_address/pairs/stats` | [Documentation](/data-api/evm/token/swaps/pair-stats) |

## Getting Started with Moralis

1. **Sign up for a Moralis account**: [https://admin.moralis.com/register](https://admin.moralis.com/register)
2. **Get your API key**: Navigate to the Web3 APIs section in your dashboard
3. **Update your API calls**: Replace OKLink endpoints with the corresponding Moralis endpoints
4. **Explore the documentation**: [https://docs.moralis.com/](https://docs.moralis.com/)

## Why Choose Moralis?

<Tip>
  **MIGRATION SUPPORT AVAILABLE** - Moralis has a dedicated team to help you migrate smoothly from OKLink. [Contact our team](https://developers.moralis.com/) for personalized support and to learn about special developer discounts for teams transitioning from OKLink.
</Tip>

### Trusted by Industry Leaders

Moralis APIs power some of the biggest names in the crypto space:

* MetaMask
* Kraken
* Blockchain.com
* And many other top wallets and applications

### Migration Support

Our dedicated migration team is ready to help OKLink users transition smoothly:

* Technical guidance to map your existing implementation
* Support with API key setup and configuration
* Best practices for optimizing API usage

### Developer Discounts

Contact our team today to learn about special pricing options available for teams migrating from OKLink.

Moralis is committed to providing a seamless transition for OKLink users with comprehensive support throughout your migration journey.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Embed a TradingView Candlestick Chart for Pump.fun Tokens

> Learn how to embed a real-time TradingView candlestick chart for Pump.fun tokens using the Moralis Price Chart Widget.

## Overview

Want to display real-time price charts for Pump.fun tokens on your website or app? With Moralis' Price Chart Widget, you can easily embed TradingView-style candlestick charts in just a few steps.

### What You Can Do

* Embed real-time price charts for any Pump.fun token
* Customize colors, layout, and time intervals
* Works for pre-bonded Pump.fun tokens too
* Supports HTML & React implementations

***

## Step 1: Configure Your Chart

1. Go to **[Moralis Price Chart Widget](https://moralis.com/widgets/price-chart)**.
2. Enter your **token address or pair address**.
3. Customize your **theme, background, candle colors, text colors, etc.**.
4. Choose a **default time interval** (e.g., `1D`, `1H`, `5M`).
5. Copy the **embed code** for HTML or React.

***

## Step 2: Embed the Chart in Your Project

If you're using a basic website, you can copy and paste the HTML embed code. You can also use the React embed code if you're using a React project.

### HTML Embed Code

```html  theme={null}
<div id="price-chart-widget-container" style="width: 100%; height:100%">
  <script type="text/javascript">
    (function () {
      function loadWidget() {
        if (typeof window.createMyWidget === "function") {
          window.createMyWidget("price-chart-widget-container", {
            width: "980px",
            height: "620px",
            chainId: "solana",
            tokenAddress: "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
            defaultInterval: "1D",
            timeZone:
              Intl.DateTimeFormat().resolvedOptions().timeZone ?? "Etc/UTC",
            theme: "moralis",
            locale: "en",
            backgroundColor: "#071321",
            gridColor: "#0d2035",
            textColor: "#68738D",
            candleUpColor: "#4CE666",
            candleDownColor: "#E64C4C",
            hideLeftToolbar: false,
            hideTopToolbar: false,
            hideBottomToolbar: false,
          });
        } else {
          console.error("createMyWidget function is not defined.");
        }
      }

      if (!document.getElementById("moralis-chart-widget")) {
        var script = document.createElement("script");
        script.id = "moralis-chart-widget";
        script.src = "https://moralis.com/static/embed/chart.js";
        script.type = "text/javascript";
        script.async = true;
        script.onload = loadWidget;
        document.body.appendChild(script);
      } else {
        loadWidget();
      }
    })();
  </script>
</div>
```

## Step 3: Customize Your Chart

You can customize the chart's appearance by tweaking these options:

| Option            | Description                              |
| ----------------- | ---------------------------------------- |
| backgroundColor   | Background color of the chart            |
| candleUpColor     | Color for bullish candles                |
| candleDownColor   | Color for bearish candles                |
| textColor         | Text color for labels                    |
| gridColor         | Gridline color                           |
| defaultInterval   | Default time interval (1D, 1H, 5M, etc.) |
| hideLeftToolbar   | Hide/show the left toolbar               |
| hideTopToolbar    | Hide/show the top toolbar                |
| hideBottomToolbar | Hide/show the bottom toolbar             |

<Tip>
  You can embed charts for pre-bonded Pump.fun tokens the same way. Just enter the pre-bonded token address when configuring the widget.
</Tip>

***

Charts are powered by [TradingView](https://www.tradingview.com/), the leading provider of financial charting tools and trading platform.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# OHLC Chart Configurator

> Learn how to build interactive cryptocurrency candlestick charts using Chart.js or TradingView Lightweight Charts with the Moralis OHLCV API.

## Overview

This tutorial covers two approaches to building crypto candlestick charts with the Moralis OHLCV API:

1. **Chart.js** — A popular, flexible charting library with a custom candlestick plugin
2. **TradingView Lightweight Charts** — A professional-grade charting library built for financial data

Both approaches use React and fetch OHLCV data from the Moralis API.

***

## Option 1: Building with Chart.js

### Prerequisites

* Node.js installed
* Basic understanding of React
* A Moralis API key ([get one free](https://admin.moralis.io))

### Step 1: Project Setup

Create a new React project and install dependencies:

```bash  theme={null}
npx create-react-app chartjs-crypto
cd chartjs-crypto
npm install chart.js react-chartjs-2 axios react-spinners
```

Create a `.env` file in your project root:

```
REACT_APP_MORALIS_API_KEY=YOUR_API_KEY
```

### Step 2: Setup Chart.js Components

Create `src/components/CandlestickChart.js`:

```javascript  theme={null}
import React from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import "chart.js/auto";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const CandlestickChart = ({ candlestickData }) => {
  const formatData = () => {
    const labels = candlestickData.map((data) =>
      new Date(data.time * 1000).toLocaleDateString()
    );

    return {
      labels,
      datasets: [
        {
          label: "High",
          data: candlestickData.map((data) => data.high),
          borderColor: "rgba(75, 192, 192, 1)",
          borderWidth: 1,
          fill: false,
        },
        {
          label: "Low",
          data: candlestickData.map((data) => data.low),
          borderColor: "rgba(255, 99, 132, 1)",
          borderWidth: 1,
          fill: false,
        },
        {
          label: "Open",
          data: candlestickData.map((data) => data.open),
          borderColor: "rgba(54, 162, 235, 1)",
          borderWidth: 1,
          fill: false,
        },
        {
          label: "Close",
          data: candlestickData.map((data) => data.close),
          borderColor: "rgba(255, 206, 86, 1)",
          borderWidth: 1,
          fill: false,
        },
      ],
    };
  };

  const options = {
    responsive: true,
    plugins: {
      legend: { position: "top" },
      title: { display: true, text: "Cryptocurrency Price Chart" },
      tooltip: { mode: "index", intersect: false },
    },
    scales: {
      y: { type: "linear", display: true, position: "left" },
    },
    interaction: { mode: "index", intersect: false },
  };

  return (
    <div className="chart-container">
      <Line options={options} data={formatData()} />
    </div>
  );
};

export default CandlestickChart;
```

### Step 3: Create Custom Candlestick Plugin

Create `src/plugins/candlestickPlugin.js`:

```javascript  theme={null}
const candlestickPlugin = {
  id: "candlestick",
  beforeDatasetsDraw(chart, args, options) {
    const {
      ctx,
      data,
      scales: { x, y },
    } = chart;

    ctx.strokeStyle = options.borderColor || "rgba(0, 0, 0, 0.8)";
    ctx.lineWidth = options.borderWidth || 1;

    const candleWidth = x.getPixelForValue(1) - x.getPixelForValue(0);

    data.datasets[0].data.forEach((point, i) => {
      const open = y.getPixelForValue(data.datasets[2].data[i]);
      const close = y.getPixelForValue(data.datasets[3].data[i]);
      const high = y.getPixelForValue(point);
      const low = y.getPixelForValue(data.datasets[1].data[i]);
      const x1 = x.getPixelForValue(i);

      // Draw the wicks
      ctx.beginPath();
      ctx.moveTo(x1, high);
      ctx.lineTo(x1, Math.min(open, close));
      ctx.moveTo(x1, Math.max(open, close));
      ctx.lineTo(x1, low);
      ctx.stroke();

      // Draw the candle body
      ctx.fillStyle = close > open ? "#26a69a" : "#ef5350";
      ctx.fillRect(
        x1 - candleWidth / 3,
        Math.min(open, close),
        (candleWidth * 2) / 3,
        Math.abs(close - open)
      );
    });
  },
};

export default candlestickPlugin;
```

### Step 4: Update Chart Component with Plugin

Update your CandlestickChart to use the custom plugin:

```javascript  theme={null}
import candlestickPlugin from "../plugins/candlestickPlugin";

const CandlestickChart = ({ candlestickData }) => {
  const options = {
    responsive: true,
    plugins: {
      legend: { display: false },
      candlestick: {
        borderColor: "rgba(0, 0, 0, 0.8)",
        borderWidth: 1,
      },
    },
    scales: {
      y: { type: "linear", position: "left" },
    },
  };

  const formatData = () => {
    const labels = candlestickData.map((data) =>
      new Date(data.time * 1000).toLocaleDateString()
    );

    return {
      labels,
      datasets: [
        { data: candlestickData.map((data) => data.high), yAxisID: "y" },
        { data: candlestickData.map((data) => data.low), yAxisID: "y" },
        { data: candlestickData.map((data) => data.open), yAxisID: "y" },
        { data: candlestickData.map((data) => data.close), yAxisID: "y" },
      ],
    };
  };

  return (
    <div className="chart-container">
      <Line
        options={options}
        data={formatData()}
        plugins={[candlestickPlugin]}
      />
    </div>
  );
};
```

### Step 5: Implement Main App Component

Update `App.js`:

```javascript  theme={null}
import React, { useState, useEffect } from "react";
import axios from "axios";
import CandlestickChart from "./components/CandlestickChart";
import ClipLoader from "react-spinners/ClipLoader";
import "./styles.css";

const App = () => {
  const [candlestickData, setCandlestickData] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchOHLCVData = async () => {
    setLoading(true);
    try {
      const apiKey = process.env.REACT_APP_MORALIS_API_KEY;
      const currentTime = Math.floor(Date.now() / 1000);
      const fromDate = currentTime - 30 * 24 * 60 * 60;

      const response = await axios.get(
        `https://deep-index.moralis.io/api/v2.2/pairs/0xa478c2975ab1ea89e8196811f51a7b7ade33eb11/ohlcv`,
        {
          params: {
            chain: "eth",
            timeframe: "1d",
            currency: "usd",
            fromDate,
            toDate: currentTime,
            limit: 1000,
          },
          headers: { "X-API-Key": apiKey },
        }
      );

      const formattedData = response.data.result.map((item) => ({
        time: Math.floor(new Date(item.timestamp).getTime() / 1000),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      }));

      setCandlestickData(formattedData);
    } catch (error) {
      console.error("Error fetching OHLCV data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOHLCVData();
  }, []);

  return (
    <div className="app-container">
      <h1>Crypto Candlestick Chart</h1>
      {loading ? (
        <div className="loading-spinner">
          <ClipLoader color="#2196f3" size={50} />
        </div>
      ) : (
        candlestickData.length > 0 && (
          <CandlestickChart candlestickData={candlestickData} />
        )
      )}
    </div>
  );
};

export default App;
```

### Step 6: Add Styling

Create `src/styles.css`:

```css  theme={null}
.app-container {
  max-width: 1200px;
  margin: 2rem auto;
  padding: 2rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

.chart-container {
  margin-top: 2rem;
  padding: 1.5rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  height: 500px;
}

.loading-spinner {
  display: flex;
  justify-content: center;
  margin: 2rem 0;
}

h1 {
  text-align: center;
  color: #1a237e;
  margin-bottom: 2rem;
}
```

Run with `npm start`.

***

## Option 2: Building with TradingView Lightweight Charts

### Step 1: Project Setup

```bash  theme={null}
npx create-react-app crypto-charts
cd crypto-charts
npm install lightweight-charts axios react-spinners
```

Create a `.env` file:

```
REACT_APP_MORALIS_API_KEY=YOUR_API_KEY
```

### Step 2: Create Components

**ChainSelector** (`src/components/ChainSelector.js`):

```javascript  theme={null}
import React from "react";

const chains = [
  { id: "eth", name: "Ethereum", icon: "🔷" },
  { id: "bsc", name: "BSC", icon: "💛" },
  { id: "polygon", name: "Polygon", icon: "💜" },
  { id: "arbitrum", name: "Arbitrum", icon: "🔵" },
];

const ChainSelector = ({ onSelect }) => (
  <select onChange={(e) => onSelect(e.target.value)} defaultValue="">
    <option value="" disabled>Select a Chain</option>
    {chains.map((chain) => (
      <option key={chain.id} value={chain.id}>
        {chain.icon} {chain.name}
      </option>
    ))}
  </select>
);

export default ChainSelector;
```

**TokenInput** (`src/components/TokenInput.js`):

```javascript  theme={null}
import React, { useState } from "react";
import axios from "axios";

const TokenInput = ({ chain, onPairsFetched, onReset }) => {
  const [tokenAddress, setTokenAddress] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchPairs = async () => {
    const apiKey = process.env.REACT_APP_MORALIS_API_KEY;
    const url = `https://deep-index.moralis.io/api/v2.2/erc20/${tokenAddress}/pairs?chain=${chain}`;

    setLoading(true);
    try {
      const response = await axios.get(url, {
        headers: { "X-API-Key": apiKey, accept: "application/json" },
      });

      const sortedPairs = response.data.pairs
        .map((pair) => ({
          ...pair,
          liquidity: pair.liquidity_usd || pair.liquidityUsd || 0,
        }))
        .sort((a, b) => b.liquidity - a.liquidity);

      onPairsFetched(sortedPairs);
    } catch (error) {
      console.error("Error fetching token pairs:", error);
      onPairsFetched([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="text"
        placeholder="Enter Token Address"
        value={tokenAddress}
        onChange={(e) => {
          setTokenAddress(e.target.value);
          onReset();
        }}
      />
      <button onClick={fetchPairs} disabled={!tokenAddress || !chain}>
        Fetch Pairs
      </button>
      {loading && <div>Loading pairs...</div>}
    </div>
  );
};

export default TokenInput;
```

### Step 3: Implement the Chart Component

Create `src/components/CandlestickChart.js`:

```javascript  theme={null}
import React, { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

const CandlestickChart = ({ candlestickData }) => {
  const chartContainerRef = useRef();
  const chartRef = useRef();

  useEffect(() => {
    if (!chartRef.current) {
      const chart = createChart(chartContainerRef.current, {
        width: chartContainerRef.current.offsetWidth || 800,
        height: 400,
        layout: {
          backgroundColor: "#ffffff",
          textColor: "#333",
        },
        grid: {
          vertLines: { color: "#f0f3fa" },
          horzLines: { color: "#f0f3fa" },
        },
        timeScale: {
          timeVisible: true,
          borderVisible: true,
        },
      });

      const candlestickSeries = chart.addCandlestickSeries({
        upColor: "#4caf50",
        downColor: "#f44336",
        borderVisible: false,
        wickUpColor: "#4caf50",
        wickDownColor: "#f44336",
      });

      chartRef.current = { chart, candlestickSeries };
    }

    if (candlestickData.length > 0) {
      chartRef.current.candlestickSeries.setData(candlestickData);
    }

    return () => {
      if (chartRef.current) {
        chartRef.current.chart.remove();
        chartRef.current = null;
      }
    };
  }, [candlestickData]);

  return (
    <div
      ref={chartContainerRef}
      style={{ position: "relative", height: "400px" }}
    />
  );
};

export default CandlestickChart;
```

### Step 4: Implement Main App

Update `App.js`:

```javascript  theme={null}
import React, { useState, useEffect } from "react";
import axios from "axios";
import ChainSelector from "./components/ChainSelector";
import TokenInput from "./components/TokenInput";
import CandlestickChart from "./components/CandlestickChart";
import ClipLoader from "react-spinners/ClipLoader";
import "./styles.css";

const App = () => {
  const [chain, setChain] = useState("");
  const [pairs, setPairs] = useState([]);
  const [selectedPair, setSelectedPair] = useState("");
  const [candlestickData, setCandlestickData] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchCandlestickData = async (pairAddress) => {
    if (!pairAddress) return;

    setLoading(true);
    try {
      const apiKey = process.env.REACT_APP_MORALIS_API_KEY;
      const currentTime = Math.floor(Date.now() / 1000);
      const fromDate = currentTime - 30 * 24 * 60 * 60;

      const response = await axios.get(
        `https://deep-index.moralis.io/api/v2.2/pairs/${pairAddress}/ohlcv`,
        {
          params: {
            chain,
            timeframe: "1d",
            currency: "usd",
            fromDate,
            toDate: currentTime,
            limit: 1000,
          },
          headers: { "X-API-Key": apiKey },
        }
      );

      const formattedData = response.data.result.map((item) => ({
        time: Math.floor(new Date(item.timestamp).getTime() / 1000),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      }));

      setCandlestickData(formattedData);
    } catch (error) {
      console.error("Error fetching candlestick data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedPair) {
      fetchCandlestickData(selectedPair);
    }
  }, [selectedPair]);

  return (
    <div className="app-container">
      <h1>Crypto Trading Charts</h1>

      <div className="controls-container">
        <ChainSelector onSelect={setChain} />
        <TokenInput
          chain={chain}
          onPairsFetched={setPairs}
          onReset={() => {
            setPairs([]);
            setSelectedPair("");
            setCandlestickData([]);
          }}
        />
        {pairs.length > 0 && (
          <select
            value={selectedPair}
            onChange={(e) => setSelectedPair(e.target.value)}
          >
            {pairs.map((pair) => (
              <option key={pair.pairAddress} value={pair.pairAddress}>
                {pair.pairLabel} (${Math.round(pair.liquidity).toLocaleString()})
              </option>
            ))}
          </select>
        )}
      </div>

      {loading ? (
        <div className="loading-spinner">
          <ClipLoader color="#2196f3" size={50} />
        </div>
      ) : (
        candlestickData.length > 0 && (
          <CandlestickChart candlestickData={candlestickData} />
        )
      )}
    </div>
  );
};

export default App;
```

### Step 5: Add Styling

Create `src/styles.css`:

```css  theme={null}
.app-container {
  max-width: 1200px;
  margin: 2rem auto;
  padding: 2rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

.controls-container {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 400px;
  margin: 0 auto 2rem auto;
}

select, input {
  width: 100%;
  padding: 0.75rem 1rem;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
}

button {
  background: #2196f3;
  color: white;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}

button:disabled {
  background: #e0e0e0;
  cursor: not-allowed;
}

.chart-container {
  margin-top: 2rem;
  padding: 1.5rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.loading-spinner {
  display: flex;
  justify-content: center;
  margin: 2rem 0;
}
```

### Using the Application

1. Select a blockchain network from the dropdown
2. Enter a token address (e.g., USDT, WETH)
3. Click "Fetch Pairs" to get available trading pairs
4. Select a trading pair to view its price chart
5. The chart will display OHLCV data for the last 30 days


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with Phantom Wallet

This tutorial covers how to create full-stack Web3 authentication for the Phantom wallet, using the popular NextJS framework.

## Introduction

This tutorial shows you how to create a NextJS application that lets users log in using their Phantom wallet.

After Web3 wallet authentication, the [**next-auth**](https://next-auth.js.org/) library creates a session cookie with an encrypted [**JWT**](https://jwt.io/introduction) (**JWE**) stored inside. It contains session info (such as an address, signed message, and expiration time) in the user's browser. It's a secure way to store users' info without a database, and it's impossible to read/modify the **JWT** without a [secret key](https://next-auth.js.org/configuration/options#secret).

Once the user is logged in, they will be able to visit a page that displays all their user data.

<Info>
  You can find the final dapp with implemented style on our [GitHub](https://github.com/JohnVersus/nextjs_solana_auth_api/tree/moralisweb3-next-client-auth).
</Info>

## Prerequisites

1. Create a [Moralis account](https://www.moralis.io).
2. Install and set up [Visual Studio](https://code.visualstudio.com/).
3. Create your NextJS dapp (you can create it using [**create-next-app**](https://nextjs.org/docs/api-reference/create-next-app) or follow the **NextJS dapp** tutorial).

## Install the Required Dependencies

1. Install `@moralisweb3/next` (if not installed), `next-auth` and `@web3uikit/core` dependencies:

```bash npm2yarn theme={null}
npm install @moralisweb3/next next-auth @web3uikit/core
```

2. To process data like the signature of a Solana Web3 wallet (e.g., Phantom), we need the `bs58` package to encode and decode data from the wallet. Let's install the `bs58` package:

```bash npm2yarn theme={null}
npm install bs58
```

3. Add new environment variables in your `.env.local` file in the app root:

* **APP\_DOMAIN**: RFC 4501 DNS authority that is requesting the signing.
* **MORALIS\_API\_KEY**: You can get it [here](https://admin.moralis.com/account/profile).
* **NEXTAUTH\_URL**: Your app address. In the development stage, use [`http://localhost:3000`](http://localhost:3000).
* **NEXTAUTH\_SECRET**: Used for encrypting JWT tokens of users. You can put any value here or generate it on [`https://generate-secret.now.sh/32`](https://generate-secret.now.sh/32). Here's an `.env.local` example:

```text .env.local theme={null}
APP_DOMAIN=amazing.finance
MORALIS_API_KEY=xxxx
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=7197b3e8dbee5ea6274cab37245eec212
```

<Info>
  Keep your `NEXTAUTH_SECRET` value in secret to prevent security problems.\
  \
  Every time you modify the `.env.local` file, you need to restart your dapp.
</Info>

## Wrapping App with `SessionProvider`

4. Create the `pages/_app.jsx` file. We need to wrap our pages with `SessionProvider` ([docs](https://next-auth.js.org/getting-started/client#sessionprovider)):

```javascript  theme={null}
import "../styles/globals.css";
import { SessionProvider } from "next-auth/react";

function MyApp({ Component, pageProps }) {
  return (
    <SessionProvider session={pageProps.session}>
      <Component {...pageProps} />
    </SessionProvider>
  );
}

export default MyApp;
```

<Info>
  NextJS uses the `App` component to initialize pages. You can override it and control the page initialization. Check out the [NextJS docs](https://nextjs.org/docs/advanced-features/custom-app).
</Info>

## Configure Next-Auth and MoralisNextAuth

5. Create a new file, `pages/api/auth/[...nextauth].ts`, with the following content:

<Tabs>
  <Tab title="Tab">
    ```typescript  theme={null}
    import NextAuth from "next-auth";
    import { MoralisNextAuthProvider } from "@moralisweb3/next";

    export default NextAuth({
      providers: [MoralisNextAuthProvider()],
      // adding user info to the user session object
      callbacks: {
        async jwt({ token, user }) {
          if (user) {
            token.user = user;
          }
          return token;
        },
        async session({ session, token }) {
          (session as { user: unknown }).user = token.user;
          return session;
        },
      },
    });
    ```
  </Tab>

  <Tab title="Tab">
    ```javascript Javascript theme={null}
    import NextAuth from "next-auth";
    import { MoralisNextAuthProvider } from "@moralisweb3/next";

    export default NextAuth({
      providers: [MoralisNextAuthProvider()],
      // adding user info to the user session object
      callbacks: {
        async jwt({ token, user }) {
          if (user) {
            token.user = user;
          }
          return token;
        },
        async session({ session, token }) {
          session.user = token.user;
          return session;
        },
      },
    });
    ```
  </Tab>
</Tabs>

6. Add an authenticating config to the `pages/api/moralis/[...moralis].ts`:

<Tabs>
  <Tab title="Tab">
    ```typescript [...moralis].ts theme={null}
    import { MoralisNextApi } from "@moralisweb3/next";

    const DATE = new Date();
    const FUTUREDATE = new Date(DATE);
    FUTUREDATE.setDate(FUTUREDATE.getDate() + 1);

    const { MORALIS_API_KEY, APP_DOMAIN, NEXTAUTH_URL } = process.env;

    if (!MORALIS_API_KEY || !APP_DOMAIN || !NEXTAUTH_URL) {
      throw new Error(
        "Missing env variables. Please add the required env variables."
      );
    }

    export default MoralisNextApi({
      apiKey: MORALIS_API_KEY,
      authentication: {
        timeout: 120,
        domain: APP_DOMAIN,
        uri: NEXTAUTH_URL,
        expirationTime: FUTUREDATE.toISOString(),
        statement: "Sign message to authenticate.",
      },
    });
    ```
  </Tab>

  <Tab title="Tab">
    ```typescript [...moralis].js theme={null}
    import { MoralisNextApi } from "@moralisweb3/next";

    const DATE = new Date();
    const FUTUREDATE = new Date(DATE);
    FUTUREDATE.setDate(FUTUREDATE.getDate() + 1);

    const { MORALIS_API_KEY, APP_DOMAIN, NEXTAUTH_URL } = process.env;

    if (!MORALIS_API_KEY || !APP_DOMAIN || !NEXTAUTH_URL) {
      throw new Error(
        "Missing env variables. Please add the required env variables."
      );
    }

    export default MoralisNextApi({
      apiKey: MORALIS_API_KEY,
      authentication: {
        timeout: 120,
        domain: APP_DOMAIN,
        uri: NEXTAUTH_URL,
        expirationTime: FUTUREDATE.toISOString(),
        statement: "Sign message to authenticate.",
      },
    });
    ```
  </Tab>
</Tabs>

## Create Wallet Component

7. Create a new file under `app/components/loginBtn/phantomBtn.tsx`:

<Tabs>
  <Tab title="Tab">
    ```typescript phantomBtn.tsx theme={null}
    import React from "react";
    import { Button } from "@web3uikit/core";
    import { signIn } from "next-auth/react";
    import base58 from "bs58";
    import { useAuthRequestChallengeSolana } from "@moralisweb3/next";

    export default function PhantomBtn() {
      const { requestChallengeAsync, error } = useAuthRequestChallengeSolana();
      const authenticate = async () => {
        // @ts-ignore
        const provider = window.phantom?.solana;
        const resp = await provider.connect();
        const address = resp.publicKey.toString();
        const chain = "devnet";
        const account = {
          address: address,
          chain: chain,
          network: "solana",
        };
        // const message = "Sign to provide access to app";
        const challenge = await requestChallengeAsync({
          address,
          network: "devnet",
        });
        const encodedMessage = new TextEncoder().encode(challenge?.message);
        const signedMessage = await provider.signMessage(encodedMessage, "utf8");
        const signature = base58.encode(signedMessage.signature);
        try {
          const authResponse = await signIn("moralis-auth", {
            message: challenge?.message,
            signature,
            network: "Solana",
            redirect: false,
          });
          if (authResponse?.error) {
            throw new Error(authResponse.error);
          }
        } catch (e) {
          return;
        }
      };

      return (
        <Button
          text="Phantom"
          theme="primary"
          onClick={() => {
            authenticate();
          }}
        />
      );
    }
    ```
  </Tab>

  <Tab title="Tab">
    ```typescript phantomBtn.jsx theme={null}
    import React from "react";
    import { Button } from "@web3uikit/core";
    import { signIn } from "next-auth/react";
    import base58 from "bs58";
    import { useAuthRequestChallengeSolana } from "@moralisweb3/next";

    export default function PhantomBtn() {
      const { requestChallengeAsync, error } = useAuthRequestChallengeSolana();
      const authenticate = async () => {
        // @ts-ignore
        const provider = window.phantom?.solana;
        const resp = await provider.connect();
        const address = resp.publicKey.toString();
        const chain = "devnet";
        const account = {
          address: address,
          chain: chain,
          network: "solana",
        };
        // const message = "Sign to provide access to app";
        const challenge = await requestChallengeAsync({
          address,
          network: "devnet",
        });
        const encodedMessage = new TextEncoder().encode(challenge?.message);
        const signedMessage = await provider.signMessage(encodedMessage, "utf8");
        const signature = base58.encode(signedMessage.signature);
        try {
          const authResponse = await signIn("credentials", {
            message: challenge?.message,
            signature,
            network: "Solana",
            redirect: false,
          });
          if (authResponse?.error) {
            throw new Error(authResponse.error);
          }
        } catch (e) {
          return;
        }
      };

      return (
        <Button
          text="Phantom"
          theme="primary"
          onClick={() => {
            authenticate();
          }}
        />
      );
    }
    ```
  </Tab>
</Tabs>

## Create Page to Sign-In

8. Create a new page file, `pages/index.jsx`, with the following content:

* You can get the app CSS from [GitHub](https://github.com/JohnVersus/nextjs_solana_auth_api/tree/moralisweb3-next-client-auth/styles) to style the app.

```javascript  theme={null}
import React, { useEffect, useTransition } from "react";
import styles from "../styles/Home.module.css";
import { useRouter } from "next/router";
import { Typography } from "@web3uikit/core";
import { useSession } from "next-auth/react";
import PhantomBtn from "../app/components/loginBtn/phantomBtn";

export default function Home() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    startTransition(() => {
      session && status === "authenticated" && router.push("./user");
    });
  }, [session, status]);

  useEffect(() => {
    startTransition(() => {
      session && console.log(session);
    });
  }, [session]);

  return (
    <div className={styles.body}>
      {!isPending && (
        <div className={styles.card}>
          <>
            {!session ? (
              <>
                <Typography variant="body18">
                  Select Wallet for Authentication
                </Typography>
                <br />
                <PhantomBtn />
              </>
            ) : (
              <Typography variant="caption14">Loading...</Typography>
            )}
          </>
        </div>
      )}
    </div>
  );
}
```

## Logout and User Profile Component

8. Create components to perform the logout operation and to show the user data.

<Tabs>
  <Tab title="Tab">
    ```typescript logoutBtn.js theme={null}
    // File path
    // app/components/logoutBtn/logoutBtn.js

    import React from "react";
    import { Button } from "@web3uikit/core";
    import { signOut } from "next-auth/react";

    export default function LogoutBtn() {
      return (
        <Button text="Logout" theme="outline" onClick={() => signOut()}></Button>
      );
    }
    ```
  </Tab>

  <Tab title="Tab">
    ```typescript userData.js theme={null}
    // File path
    // app/components/logoutBtn/userData.js

    import React from "react";
    import styles from "../../../styles/User.module.css";
    import { Typography } from "@web3uikit/core";
    import { useSession } from "next-auth/react";

    export default function UserData() {
      const { data: session, status } = useSession();

      if (session) {
        return (
          <div className={styles.data}>
            <div className={styles.dataCell}>
              <Typography variant="subtitle2">Profile Id:</Typography>
              <div className={styles.address}>
                <Typography variant="body16">{session?.user.profileId}</Typography>
              </div>
            </div>
            <div className={styles.dataCell}>
              <Typography variant="subtitle2">Account:</Typography>
              <div className={styles.address}>
                {/* account address */}
                <Typography copyable variant="body16">
                  {session?.user.address}
                </Typography>
              </div>
            </div>
            <div className={styles.dataCell}>
              <Typography variant="subtitle2">Network:</Typography>
              <div className={styles.address}>
                <Typography variant="body16">{session?.user.network}</Typography>
              </div>
            </div>
            <div className={styles.dataCell}>
              <Typography variant="subtitle2">ExpTime:</Typography>
              <div className={styles.address}>
                <Typography variant="body16">
                  {session?.user.expirationTime}
                </Typography>
              </div>
            </div>
          </div>
        );
      }
    }
    ```
  </Tab>
</Tabs>

## Showing the User Profile

9. Let's create a `user.jsx` page to view user data when the user is logged in.

```javascript  theme={null}
import React, { useEffect, useTransition } from "react";
import styles from "../styles/User.module.css";
import { getSession, signOut } from "next-auth/react";
import UserData from "../app/components/userData/userData";
import LogoutBtn from "../app/components/logoutBtn/logoutBtn";

export async function getServerSideProps(context) {
  const session = await getSession(context);
  if (!session) {
    return { redirect: { destination: "/" } };
  }
  return {
    props: { userSession: session },
  };
}

export default function Home({ userSession }) {
  if (userSession) {
    return (
      <div className={styles.body}>
        {!isPending && (
          <div className={styles.card}>
            <>
              <UserData />
              <div className={styles.buttonsRow}>
                <LogoutBtn />
              </div>
            </>
          </div>
        )}
      </div>
    );
  }
}
```

## Testing with Phantom Wallet

Visit `http://localhost:3000` to test the authentication.

1. Click on the `Select Wallet` button to select and connect to wallet
2. Connect to the Solana wallet extension
3. Sign the message
4. After successful authentication, you will be redirected to the `/user` page

And that completes the authentication process to Solana wallet using Phantom Wallet.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with Web3Auth

## What is Web3Auth?

<Info>
  Visit [Web3Auth docs](https://web3auth.io/docs/index.html) to get more information.
</Info>

Web3Auth is a pluggable auth infrastructure for Web3 wallets and applications. It streamlines the onboarding of mainstream and crypto-native users in under a minute by providing experiences they're most comfortable with. With support for all social logins, web and mobile-native platforms, wallets, and other key management methods, Web3Auth results in a standard cryptographic key provider specific to the user and application.

## Before Starting

You can start this tutorial if you already have a NextJS dapp with [MetaMask sign-in](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask) functionality.Installing the Web3Auth Wagmi Connector

Install the `@web3auth/web3auth-wagmi-connector` dependency:

```bash npm2yarn theme={null}
npm install @web3auth/web3auth-wagmi-connector@1.0.0
```

## Configuring the Web3Auth Wagmi Connector

1. Open the `pages/signin.jsx` file and add `Web3AuthConnector` as a connector to the `useConnect()` hook:

```javascript  theme={null}
import { Web3AuthConnector } from "@web3auth/web3auth-wagmi-connector";
import { signIn } from "next-auth/react";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useRouter } from "next/router";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect({
    connector: new Web3AuthConnector({
      chains: ["0x1"],
      options: {
        clientId: "YOUR_CLIENT_ID", // Get your own client id from https://dashboard.web3auth.io
      },
    }),
  });
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { push } = useRouter();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm()

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account } = await connectAsync();

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: "0x1",
    });

    const signature = await signMessageAsync({ message });

    // redirect user after success authentication to '/user' page
    const { url } = await signIn("moralis-auth", {
      message,
      signature,
      redirect: false,
      callbackUrl: "/user",
    });
    /**
     * instead of using signIn(..., redirect: "/user")
     * we get the url from callback and push it to the router to avoid page refreshing
     */
    push(url);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={() => handleAuth()}>Authenticate via Web3Auth</button>
    </div>
  );
}

export default SignIn;
```

## Testing the Web3Auth Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin) to test authentication.

1. Click on `Authenticate via Web3Auth`
2. Select the preferred sign-in method
3. After successful authentication, you will be redirected to the `/user` page
4. Visit `http://localhost:3000/user` to test the user session's functionality:

* When a user is authenticated, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page. ([***`Explanation: After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT [JWE] stored inside. It contains session info [such as an address and signed message] in the user's browser.`***](https://jwt.io/introduction))


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with WalletConnect

## Before the Start

You can start this tutorial if you already have a NextJS dapp with [MetaMask](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask) functionality.

## Configuring the WalletConnect Connector

1. Open the`pages/signin.jsx` file and add `WalletConnectConnector` as a connector to `connectAsync()`. You should have your [Project ID](https://cloud.walletconnect.com/sign-in) for the WalletConnect configuration and replace `xxx` with it in the code below.

```javascript  theme={null}
import { WalletConnectConnector } from "wagmi/connectors/walletConnect";
import { signIn } from "next-auth/react";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useRouter } from "next/router";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect({
    connector: new WalletConnectConnector({
      options: { projectId: "xxx", showQrModal: true },
    }),
  });
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();
  const { push } = useRouter();

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account, chain } = await connectAsync();

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: chain.id,
    });

    const signature = await signMessageAsync({ message });

    // redirect user after success authentication to '/user' page
    const { url } = await signIn("moralis-auth", {
      message,
      signature,
      redirect: false,
      callbackUrl: "/user",
    });
    /**
     * instead of using signIn(..., redirect: "/user")
     * we get the url from callback and push it to the router to avoid page refreshing
     */
    push(url);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via WalletConnect</button>
    </div>
  );
}

export default SignIn;
```

## Testing the WalletConnect Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin`) to test authentication.

1. Click on `Authenticate via WalletConnect`
2. Scan the QR code with your wallet
3. Connect your wallet
4. Sign the message:
5. Visit [`http://localhost:3000/user`](http://localhost:3000/user) to test the user session's functionality:

* When a user is authenticated, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page. ([*`Explanation: After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT [JWE] stored inside. It contains session info [such as an address and signed message] in the user's browser.`*](https://jwt.io/introduction))


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with RainbowKit

## Before Starting

You can start this tutorial if you already have a NextJS dapp with [MetaMask sign-in](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask) functionality.

## RainbowKit Installation

```bash npm2yarn theme={null}
npm install @rainbow-me/rainbowkit@latest wagmi viem
```

## RainbowKit Configuration

We are going to modify `pages/_app.jsx` and add the required code to set up RainbowKit Authentication.

<Info>
  You can get your project ID on the [WalletConnect Dashboard](https://cloud.walletconnect.com/).
</Info>

```javascript  theme={null}
import { getDefaultWallets, RainbowKitProvider } from "@rainbow-me/rainbowkit";
import { createConfig, configureChains, WagmiConfig } from "wagmi";
import { mainnet } from "wagmi/chains";
import { publicProvider } from "wagmi/providers/public";
import { SessionProvider } from "next-auth/react";
import "@rainbow-me/rainbowkit/styles.css";

const { chains, publicClient, webSocketPublicClient } = configureChains(
  [mainnet],
  [publicProvider()]
);

const { connectors } = getDefaultWallets({
  appName: "My RainbowKit App",
  projectId: "WALLET_CONNECT_PROJECT_ID", // Get your project ID from https://cloud.walletconnect.com/
  chains,
});

const config = createConfig({
  autoConnect: true,
  publicClient,
  webSocketPublicClient,
  connectors,
});

// added RainbowKitProvider wrapper
function MyApp({ Component, pageProps }) {
  return (
    <WagmiConfig config={config}>
      <SessionProvider session={pageProps.session} refetchInterval={0}>
        <RainbowKitProvider chains={chains}>
          <Component {...pageProps} />
        </RainbowKitProvider>
      </SessionProvider>
    </WagmiConfig>
  );
}

export default MyApp;
```

## Authentication with RainbowKit

The logic we're achieving works as this. A user connects his wallet using `ConnectButton` from `rainbowkit`. Once the wallet is connected, we get `address` and `chain` from the following **wagmi** hooks: `useAccount()` and `useNetwork()`. In case the user is not authenticated, we will start the authentication flow (request and **sign** message).

1. Open the `pages/signin.jsx` file and replace the old `Authenticate via MetaMask` button with `<ConnectButton />` from `@rainbow-me/rainbowkit`:

```javascript  theme={null}
import { ConnectButton } from '@rainbow-me/rainbowkit';
...

return (
  <div>
  	<h3>Web3 Authentication</h3>
    <ConnectButton />
  </div>
);
...
```

2. Edit `handleAuth()` and move it under `useEffect()`:

```javascript  theme={null}
...
  useEffect(() => {
    const handleAuth = async () => {
      const { message } = await requestChallengeAsync({
        address: address,
        chainId: chain.id,
      });

      const signature = await signMessageAsync({ message });

      // redirect user after success authentication to '/user' page
      const { url } = await signIn("moralis-auth", {
        message,
        signature,
        redirect: false,
        callbackUrl: "/user",
      });
      /**
       * instead of using signIn(..., redirect: "/user")
       * we get the url from callback and push it to the router to avoid page refreshing
       */
      push(url);
    };
    if (status === "unauthenticated" && isConnected) {
      handleAuth();
    }
  }, [status, isConnected]);
...
```

3. Update missing imports and add new hooks. This is the final code of `pages/signin.jsx`:

```javascript  theme={null}
import { useRouter } from "next/router";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { signIn, useSession } from "next-auth/react";
import { useAccount, useSignMessage, useNetwork } from "wagmi";
import { useEffect } from "react";

function SignIn() {
  const { isConnected, address } = useAccount();
  const { chain } = useNetwork();
  const { status } = useSession();
  const { signMessageAsync } = useSignMessage();
  const { push } = useRouter();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();

  useEffect(() => {
    const handleAuth = async () => {
      const { message } = await requestChallengeAsync({
        address: address,
        chainId: chain.id,
      });

      const signature = await signMessageAsync({ message });

      // redirect user after success authentication to '/user' page
      const { url } = await signIn("moralis-auth", {
        message,
        signature,
        redirect: false,
        callbackUrl: "/user",
      });
      /**
       * instead of using signIn(..., redirect: "/user")
       * we get the url from callback and push it to the router to avoid page refreshing
       */
      push(url);
    };
    if (status === "unauthenticated" && isConnected) {
      handleAuth();
    }
  }, [status, isConnected]);

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <ConnectButton />
    </div>
  );
}

export default SignIn;
```

## Set Up RainbowKit with NextJS

<Info>
  The Webpack v5 bundler used by Next.js no longer provides Node polyfills, so you'll need to include these modules yourself to satisfy RainbowKit's peer dependencies.
</Info>

In previous versions of RainbowKit that relied on ethers, the fs, net, and tls modules were automatically polyfilled. This is no longer the case with RainbowKit v1 + wagmi v1, which are built on viem.

Open `next.config.js` file in the root of your project and add the following code:

```javascript  theme={null}
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    config.resolve.fallback = { fs: false, net: false, tls: false };
    return config;
  },
};

module.exports = nextConfig;
```

Read more about RainbowKit configuration on the [official documentation](https://www.rainbowkit.com/docs/installation#additional-build-tooling-setup).

## Testing the RainbowKit Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin) to test authentication.

1. Click on `Connect Wallet`
2. Select and connect a wallet you want to use for authentication from the RainbowKit modal
3. Sign the message:
4. After successful authentication, you will be redirected to the `/user` page
5. Visit [`http://localhost:3000/user`](http://localhost:3000/user) to test the user session's functionality:

* When a user is authenticated, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page. ([***`Explanation: After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT [JWE] stored inside. It contains session info [such as an address and signed message] in the user's browser.`***](https://jwt.io/introduction))


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with Particle Network

## What is Particle Network?

<Tip>
  Check the Particle Network [documentation website](https://docs.particle.network/) to get more information.
</Tip>

**Particle Network** is the Intent-Centric, Modular Access Layer of Web3. With Particle's [Smart Wallet-as-a-Service](https://blog.particle.network/announcing-our-smart-wallet-as-a-service-modular-stack-upgrading-waas-with-erc-4337/), developers can curate unparalleled user experience through modular and customizable EOA/AA embedded wallet components. By utilizing MPC-TSS for key management, Particle can streamline onboarding via familiar Web2 accounts—such as Google accounts, email addresses, and phone numbers.

## Prerequisites

### Next.js Dapp with MetaMask Sign-In

Before you begin this tutorial, make sure you have set up a Next.js decentralized application (Dapp) that includes MetaMask sign-in functionality. If you haven't integrated MetaMask sign-in yet, refer to the guide [How to Authenticate Users with MetaMask](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask).

### Install Dependencies

To prepare for this tutorial, you'll need to install the following dependencies for Particle Connect:

* **@particle-network/connect-react-ui**: This package provides React UI components for Particle Connect. You can install it using npm or yarn.

  ```bash  theme={null}
  npm install @particle-network/connect-react-ui
  ```

  or

  ```bash  theme={null}
  yarn add @particle-network/connect-react-ui
  ```
* **@particle-network/connect**: This package is essential for integrating Particle Connect into your Dapp. Install it using npm or yarn.

  ```bash  theme={null}
  npm install @particle-network/connect
  ```

  or

  ```bash  theme={null}
  yarn add @particle-network/connect
  ```
* **@particle-network/chains**: This optional dependency is leveraged for handling blockchain chains within Particle Connect. You can install it using npm or yarn.

  ```bash  theme={null}
  npm install @particle-network/chains
  ```

  or

  ```bash  theme={null}
  yarn add @particle-network/chains
  ```

With these prerequisites organized, you'll be fully prepared to smoothly integrate Particle Connect into your Next.js Dapp.

## Configure Particle Connect

Open the `pages/signin.jsx` file and restructure your code as shown below. This code utilizes Particle Connect's components and hooks for handling the connection process and wallet interactions.

```javascript  theme={null}
import { useRouter } from 'next/router';
import { useEffect } from 'react';
import { useAccount, ConnectButton, useConnectKit, ModalProvider } from '@particle-network/connect-react-ui';
import { useAuthRequestChallengeEvm } from '@moralisweb3/next';
import { signIn } from 'next-auth/react';
import { Ethereum } from '@particle-network/chains';
import { evmWallets } from '@particle-network/connect';
import '@particle-network/connect-react-ui/dist/index.css';

export default function SignIn() {
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();
  const { push } = useRouter();
  const account = useAccount();
  const connect = useConnectKit();

  useEffect(() => {
    if (account) {
      (async () => {
        const { message } = await requestChallengeAsync({
          address: account,
          chainId: '0x1',
        });

        const signature = await connect.particle.evm.personalSign(`0x${Buffer.from(message).toString('hex')}`); // Conversion to hex, then signing with connected Particle account (whether that be through Particle Auth or otherwise)

        const result = await signIn("moralis-auth", {
          message,
          signature,
          redirect: false,
          callbackUrl: '/user',
        });

        if (result && result.url) {
          push(result.url);
        }
      })();
    }
  }, [account]);

  return (
    <ModalProvider
      options={{ // Options for Particle Auth; the projectId, clientKey, and appId can be retrieved from https://dashboard.particle.network/
        projectId: process.env.PARTICLE_PROJECT_ID,
        clientKey: process.env.PARTICLE_CLIENT_KEY,
        appId: process.env.PARTICLE_APP_ID,
        chains: [Ethereum],
        wallets: evmWallets({ showQrModal: true, projectId: process.env.WALLETCONNECT_PROJECT_ID }), // WalletConnect for Web3 wallet connections (non Particle Auth)
      }}
    >
      <div>
        <h3>Web3 Authentication</h3>
        <ConnectButton />
      </div>
    </ModalProvider>
  );
}
```

## Test Particle Connect

To test the authentication process with Particle Connect, follow these steps:

1. **Visit Sign-In Page**: Go to [`http://localhost:3000/signin`](http://localhost:3000/signin).
2. **Connect Wallet**: Click the "Connect Wallet" button to initiate the login process. You can choose to log in through Particle Auth or a supported Web3 (EVM) wallet.
3. **Select Sign-In Method**: Choose your preferred sign-in method from the options provided.
4. **Successful Authentication**: After successful authentication, you will be automatically redirected to the `/user` page.
5. **Test User Session**: Visit [`http://localhost:3000/user`](http://localhost:3000/user) to test the functionality of the user session:
   * When a user is authenticated, their information will be displayed on the page.
   * If a user is not authenticated, they will be redirected to the `/signin` page.
   * Even after refreshing the page, the user's information will still be displayed. (***`Explanation: After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted [JWT] containing session information, stored in the user's browser.`***)


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with MetaMask

## Introduction

This tutorial demonstrates how to create a NextJS application that allows users to log in using their Web3 wallets.

After Web3 wallet authentication, the [**next-auth**](https://next-auth.js.org/) library creates a session cookie with an encrypted [**JWT**](https://jwt.io/introduction) (**JWE**) stored inside. It contains session info (such as an address, signed message, and expiration time) in the user's browser. It's a secure way to store users' info without a database, and it's impossible to read/modify the **JWT** without a [secret key](https://next-auth.js.org/configuration/options#secret).

Once the user is logged in, they will be able to visit a page that displays all their user data.

You can find the repository with the final code [here](https://github.com/MoralisWeb3/demo-apps/tree/main/nextjs_moralis_auth).

<Info>
  You can find the final dapp with implemented style on our [GitHub](https://github.com/MoralisWeb3/Moralis-JS-SDK/tree/beta/demos/nextjs).
</Info>

## Prerequisites

1. Create a [Moralis account](https://www.moralis.io).
2. Install and set up [Visual Studio](https://code.visualstudio.com/).
3. Create your NextJS dapp (you can create it using [**create-next-app**](https://nextjs.org/docs/api-reference/create-next-app) or follow the **NextJS dapp** tutorial).

## Install the Required Dependencies

1. Install `moralis` and `@moralisweb3/next` (if not installed) and `next-auth`dependencies:

```bash npm2yarn theme={null}
npm install moralis @moralisweb3/next next-auth
```

2. To implement authentication using a Web3 wallet (e.g., MetaMask), we need to use a Web3 library. For the tutorial, we will use [wagmi](https://wagmi.sh/docs/getting-started). So, install the `wagmi` dependency:

```bash npm2yarn theme={null}
npm install wagmi viem
```

3. Add new environment variables in your `.env.local` file in the app root:

* **APP\_DOMAIN**: RFC 4501 DNS authority that is requesting the signing.
* **MORALIS\_API\_KEY**: You can get it [here](https://admin.moralis.com/account/profile).
* **NEXTAUTH\_URL**: Your app address. In the development stage, use [`http://localhost:3000`](http://localhost:3000).
* **NEXTAUTH\_SECRET**: Used for encrypting JWT tokens of users. You can put any value here or generate it on [`https://generate-secret.now.sh/32`](https://generate-secret.now.sh/32). Here's an `.env.local` example:

```text .env.local theme={null}
APP_DOMAIN=amazing.finance
MORALIS_API_KEY=xxxx
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=7197b3e8dbee5ea6274cab37245eec212
```

<Warning>
  Keep your `NEXTAUTH_SECRET` value in secret to prevent security problems.\
  \
  Every time you modify the `.env.local` file, you need to restart your dapp.
</Warning>

## Wrapping App with `WagmiConfig` and `SessionProvider`

4. Create the `pages/_app.jsx` file. We need to wrap our pages with `WagmiConfig` ([docs](https://wagmi.sh/docs/WagmiConfig)) and `SessionProvider` ([docs](https://next-auth.js.org/getting-started/client#sessionprovider)):

```javascript  theme={null}
import { createConfig, configureChains, WagmiConfig } from "wagmi";
import { publicProvider } from "wagmi/providers/public";
import { SessionProvider } from "next-auth/react";
import { mainnet } from "wagmi/chains";

const { publicClient, webSocketPublicClient } = configureChains(
  [mainnet],
  [publicProvider()]
);

const config = createConfig({
  autoConnect: true,
  publicClient,
  webSocketPublicClient,
});

function MyApp({ Component, pageProps }) {
  return (
    <WagmiConfig config={config}>
      <SessionProvider session={pageProps.session} refetchInterval={0}>
        <Component {...pageProps} />
      </SessionProvider>
    </WagmiConfig>
  );
}

export default MyApp;
```

<Info>
  NextJS uses the `App` component to initialize pages. You can override it and control the page initialization. Check out the [NextJS docs](https://nextjs.org/docs/advanced-features/custom-app).
</Info>

## Configure Next-Auth and MoralisNextAuth

5. Create a new file, `pages/api/auth/[...nextauth].js`, with the following content:

<Tabs>
  <Tab title="Tab">
    ```javascript Javascript theme={null}
    import NextAuth from "next-auth";
    import { MoralisNextAuthProvider } from "@moralisweb3/next";

    export default NextAuth({
      providers: [MoralisNextAuthProvider()],
      // adding user info to the user session object
      callbacks: {
        async jwt({ token, user }) {
          if (user) {
            token.user = user;
          }
          return token;
        },
        async session({ session, token }) {
          session.user = token.user;
          return session;
        },
      },
    });
    ```
  </Tab>

  <Tab title="Tab">
    ```typescript  theme={null}
    import NextAuth from "next-auth";
    import { MoralisNextAuthProvider } from "@moralisweb3/next";

    export default NextAuth({
      providers: [MoralisNextAuthProvider()],
      // adding user info to the user session object
      callbacks: {
        async jwt({ token, user }) {
          if (user) {
            token.user = user;
          }
          return token;
        },
        async session({ session, token }) {
          (session as { user: unknown }).user = token.user;
          return session;
        },
      },
    });
    ```
  </Tab>
</Tabs>

6. Add an authenticating config to the `pages/api/moralis/[...moralis].ts`:

```javascript  theme={null}
import { MoralisNextApi } from "@moralisweb3/next";

export default MoralisNextApi({
  apiKey: process.env.MORALIS_API_KEY,
  authentication: {
    domain: "amazing.dapp",
    uri: process.env.NEXTAUTH_URL,
    timeout: 120,
  },
});
```

## Create Sign-In Page

7. Create a new page file, `pages/signin.jsx`, with the following content:

```javascript  theme={null}
function SignIn() {
  return (
    <div>
      <h3>Web3 Authentication</h3>
    </div>
  );
}

export default SignIn;
```

8. Let's create a button for enabling our Web3 provider and `console.log` users' information:

```javascript  theme={null}
import { useConnect } from "wagmi";
import { MetaMaskConnector } from "wagmi/connectors/metaMask";

function SignIn() {
  const { connectAsync } = useConnect();

  const handleAuth = async () => {
    const { account, chain } = await connectAsync({
      connector: new MetaMaskConnector(),
    });

    const userData = { address: account, chainId: chain.id };

    console.log(userData);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via Metamask</button>
    </div>
  );
}

export default SignIn;
```

9. Extend the `handleAuth` functionality for calling `useSignMessage()` hook:

```javascript  theme={null}
import { MetaMaskConnector } from "wagmi/connectors/metaMask";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect();
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account, chain } = await connectAsync({
      connector: new MetaMaskConnector(),
    });

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: chain.id,
    });

    const signature = await signMessageAsync({ message });

    console.log(signature);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via Metamask</button>
    </div>
  );
}

export default SignIn;
```

## Secure Authentication after Signing and Verifying the Signed Message

10. Return to the `pages/signin.jsx` file. Let's add the `next-auth` authentication:

```javascript  theme={null}
import { MetaMaskConnector } from "wagmi/connectors/metaMask";
import { signIn } from "next-auth/react";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useRouter } from "next/router";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect();
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();
  const { push } = useRouter();

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account, chain } = await connectAsync({
      connector: new MetaMaskConnector(),
    });

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: chain.id,
    });

    const signature = await signMessageAsync({ message });

    // redirect user after success authentication to '/user' page
    const { url } = await signIn("moralis-auth", {
      message,
      signature,
      redirect: false,
      callbackUrl: "/user",
    });
    /**
     * instead of using signIn(..., redirect: "/user")
     * we get the url from callback and push it to the router to avoid page refreshing
     */
    push(url);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via Metamask</button>
    </div>
  );
}

export default SignIn;
```

## Showing the User Profile

11. Let's create a user page, `pages/user.jsx`, with the following content:

```javascript  theme={null}
import { getSession, signOut } from "next-auth/react";

// gets a prop from getServerSideProps
function User({ user }) {
  return (
    <div>
      <h4>User session:</h4>
      <pre>{JSON.stringify(user, null, 2)}</pre>
      <button onClick={() => signOut({ redirect: "/signin" })}>Sign out</button>
    </div>
  );
}

export async function getServerSideProps(context) {
  const session = await getSession(context);

  // redirect if not authenticated
  if (!session) {
    return {
      redirect: {
        destination: "/signin",
        permanent: false,
      },
    };
  }

  return {
    props: { user: session.user },
  };
}

export default User;
```

## Testing the MetaMask Wallet Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin`) to test the authentication.

1. Click on the `Authenticate via Metamask` button:
2. Connect the MetaMask wallet
3. Sign the message
4. After successful authentication, you will be redirected to the `/user` page
5. Visit [`http://localhost:3000/user`](http://localhost:3000/user`) to test the user session functionality:

* When a user authenticates, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page.
  * (**Explanation:** [*****`After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT (JWE) stored inside. It contains session info [such as an address and signed message] in the user's browser.)`*****](https://jwt.io/introduction)
*


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with MetaMask

## Introduction

This tutorial demonstrates how to create a NextJS application that allows users to log in using their Web3 wallets.

After Web3 wallet authentication, the [**next-auth**](https://next-auth.js.org/) library creates a session cookie with an encrypted [**JWT**](https://jwt.io/introduction) (**JWE**) stored inside. It contains session info (such as an address, signed message, and expiration time) in the user's browser. It's a secure way to store users' info without a database, and it's impossible to read/modify the **JWT** without a [secret key](https://next-auth.js.org/configuration/options#secret).

Once the user is logged in, they will be able to visit a page that displays all their user data.

You can find the repository with the final code [here](https://github.com/MoralisWeb3/demo-apps/tree/main/nextjs_moralis_auth).

<Info>
  You can find the final dapp with implemented style on our [GitHub](https://github.com/MoralisWeb3/Moralis-JS-SDK/tree/beta/demos/nextjs).
</Info>

## Prerequisites

1. Create a [Moralis account](https://www.moralis.io).
2. Install and set up [Visual Studio](https://code.visualstudio.com/).
3. Create your NextJS dapp (you can create it using [**create-next-app**](https://nextjs.org/docs/api-reference/create-next-app) or follow the **NextJS dapp** tutorial).

## Install the Required Dependencies

1. Install `moralis` and `@moralisweb3/next` (if not installed) and `next-auth`dependencies:

```bash npm2yarn theme={null}
npm install moralis @moralisweb3/next next-auth
```

2. To implement authentication using a Web3 wallet (e.g., MetaMask), we need to use a Web3 library. For the tutorial, we will use [wagmi](https://wagmi.sh/docs/getting-started). So, install the `wagmi` dependency:

```bash npm2yarn theme={null}
npm install wagmi viem
```

3. Add new environment variables in your `.env.local` file in the app root:

* **APP\_DOMAIN**: RFC 4501 DNS authority that is requesting the signing.
* **MORALIS\_API\_KEY**: You can get it [here](https://admin.moralis.com/account/profile).
* **NEXTAUTH\_URL**: Your app address. In the development stage, use [`http://localhost:3000`](http://localhost:3000).
* **NEXTAUTH\_SECRET**: Used for encrypting JWT tokens of users. You can put any value here or generate it on [`https://generate-secret.now.sh/32`](https://generate-secret.now.sh/32). Here's an `.env.local` example:

```text .env.local theme={null}
APP_DOMAIN=amazing.finance
MORALIS_API_KEY=xxxx
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=7197b3e8dbee5ea6274cab37245eec212
```

<Warning>
  Keep your `NEXTAUTH_SECRET` value in secret to prevent security problems.\
  \
  Every time you modify the `.env.local` file, you need to restart your dapp.
</Warning>

## Wrapping App with `WagmiConfig` and `SessionProvider`

4. Create the `pages/_app.jsx` file. We need to wrap our pages with `WagmiConfig` ([docs](https://wagmi.sh/docs/WagmiConfig)) and `SessionProvider` ([docs](https://next-auth.js.org/getting-started/client#sessionprovider)):

```javascript  theme={null}
import { createConfig, configureChains, WagmiConfig } from "wagmi";
import { publicProvider } from "wagmi/providers/public";
import { SessionProvider } from "next-auth/react";
import { mainnet } from "wagmi/chains";

const { publicClient, webSocketPublicClient } = configureChains(
  [mainnet],
  [publicProvider()]
);

const config = createConfig({
  autoConnect: true,
  publicClient,
  webSocketPublicClient,
});

function MyApp({ Component, pageProps }) {
  return (
    <WagmiConfig config={config}>
      <SessionProvider session={pageProps.session} refetchInterval={0}>
        <Component {...pageProps} />
      </SessionProvider>
    </WagmiConfig>
  );
}

export default MyApp;
```

<Info>
  NextJS uses the `App` component to initialize pages. You can override it and control the page initialization. Check out the [NextJS docs](https://nextjs.org/docs/advanced-features/custom-app).
</Info>

## Configure Next-Auth and MoralisNextAuth

5. Create a new file, `pages/api/auth/[...nextauth].js`, with the following content:

<Tabs>
  <Tab title="Tab">
    ```javascript Javascript theme={null}
    import NextAuth from "next-auth";
    import { MoralisNextAuthProvider } from "@moralisweb3/next";

    export default NextAuth({
      providers: [MoralisNextAuthProvider()],
      // adding user info to the user session object
      callbacks: {
        async jwt({ token, user }) {
          if (user) {
            token.user = user;
          }
          return token;
        },
        async session({ session, token }) {
          session.user = token.user;
          return session;
        },
      },
    });
    ```
  </Tab>

  <Tab title="Tab">
    ```typescript  theme={null}
    import NextAuth from "next-auth";
    import { MoralisNextAuthProvider } from "@moralisweb3/next";

    export default NextAuth({
      providers: [MoralisNextAuthProvider()],
      // adding user info to the user session object
      callbacks: {
        async jwt({ token, user }) {
          if (user) {
            token.user = user;
          }
          return token;
        },
        async session({ session, token }) {
          (session as { user: unknown }).user = token.user;
          return session;
        },
      },
    });
    ```
  </Tab>
</Tabs>

6. Add an authenticating config to the `pages/api/moralis/[...moralis].ts`:

```javascript  theme={null}
import { MoralisNextApi } from "@moralisweb3/next";

export default MoralisNextApi({
  apiKey: process.env.MORALIS_API_KEY,
  authentication: {
    domain: "amazing.dapp",
    uri: process.env.NEXTAUTH_URL,
    timeout: 120,
  },
});
```

## Create Sign-In Page

7. Create a new page file, `pages/signin.jsx`, with the following content:

```javascript  theme={null}
function SignIn() {
  return (
    <div>
      <h3>Web3 Authentication</h3>
    </div>
  );
}

export default SignIn;
```

8. Let's create a button for enabling our Web3 provider and `console.log` users' information:

```javascript  theme={null}
import { useConnect } from "wagmi";
import { MetaMaskConnector } from "wagmi/connectors/metaMask";

function SignIn() {
  const { connectAsync } = useConnect();

  const handleAuth = async () => {
    const { account, chain } = await connectAsync({
      connector: new MetaMaskConnector(),
    });

    const userData = { address: account, chainId: chain.id };

    console.log(userData);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via Metamask</button>
    </div>
  );
}

export default SignIn;
```

9. Extend the `handleAuth` functionality for calling `useSignMessage()` hook:

```javascript  theme={null}
import { MetaMaskConnector } from "wagmi/connectors/metaMask";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect();
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account, chain } = await connectAsync({
      connector: new MetaMaskConnector(),
    });

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: chain.id,
    });

    const signature = await signMessageAsync({ message });

    console.log(signature);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via Metamask</button>
    </div>
  );
}

export default SignIn;
```

## Secure Authentication after Signing and Verifying the Signed Message

10. Return to the `pages/signin.jsx` file. Let's add the `next-auth` authentication:

```javascript  theme={null}
import { MetaMaskConnector } from "wagmi/connectors/metaMask";
import { signIn } from "next-auth/react";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useRouter } from "next/router";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect();
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();
  const { push } = useRouter();

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account, chain } = await connectAsync({
      connector: new MetaMaskConnector(),
    });

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: chain.id,
    });

    const signature = await signMessageAsync({ message });

    // redirect user after success authentication to '/user' page
    const { url } = await signIn("moralis-auth", {
      message,
      signature,
      redirect: false,
      callbackUrl: "/user",
    });
    /**
     * instead of using signIn(..., redirect: "/user")
     * we get the url from callback and push it to the router to avoid page refreshing
     */
    push(url);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={handleAuth}>Authenticate via Metamask</button>
    </div>
  );
}

export default SignIn;
```

## Showing the User Profile

11. Let's create a user page, `pages/user.jsx`, with the following content:

```javascript  theme={null}
import { getSession, signOut } from "next-auth/react";

// gets a prop from getServerSideProps
function User({ user }) {
  return (
    <div>
      <h4>User session:</h4>
      <pre>{JSON.stringify(user, null, 2)}</pre>
      <button onClick={() => signOut({ redirect: "/signin" })}>Sign out</button>
    </div>
  );
}

export async function getServerSideProps(context) {
  const session = await getSession(context);

  // redirect if not authenticated
  if (!session) {
    return {
      redirect: {
        destination: "/signin",
        permanent: false,
      },
    };
  }

  return {
    props: { user: session.user },
  };
}

export default User;
```

## Testing the MetaMask Wallet Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin`) to test the authentication.

1. Click on the `Authenticate via Metamask` button:
2. Connect the MetaMask wallet
3. Sign the message
4. After successful authentication, you will be redirected to the `/user` page
5. Visit [`http://localhost:3000/user`](http://localhost:3000/user`) to test the user session functionality:

* When a user authenticates, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page.
  * (**Explanation:** [*****`After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT (JWE) stored inside. It contains session info [such as an address and signed message] in the user's browser.)`*****](https://jwt.io/introduction)
*


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with MetaMask using Python and Django

> This tutorial will teach you how Moralis authentication works and demonstrates how to add secure authentication to your Django application by walking you through creating a full-stack Web3 authentication stack using the popular Django web framework.

## Introduction

In this tutorial, we show you how to create a full-stack Django app that allows users to log in using their Web3 wallets, and Django will create a session associated with the individual user. Once logged in, the user can visit a page that displays all their user data.

You can find the repository with the final code [here](https://github.com/MoralisWeb3/demo-apps/tree/main/django_moralis_auth).

## Prerequisites

1. Create a [Moralis account](https://admin.moralis.com/login).
2. Install Python 3 (in case you don't already have it). In this tutorial, we used Python 3.10 on a Windows system.
3. Basic Django knowledge ([Django documentation](https://docs.djangoproject.com/en/dev/intro/tutorial01/)).

## Installing Required Dependencies

1. Create a virtual environment if needed: `python3 -m venv django_web3_auth_env`.
2. Install `django` and `requests` dependencies. Django version 4.1 was used for this tutorial:
   * `django_web3_auth_env\Scripts>pip3.10.exe install django`.
   * `django_web3_auth_env\Scripts>pip3.10.exe install requests`.\
     (These commands, for example, `pip3.10.exe install django`, are meant to be executed in that specific **Scripts** folder from that virtual environment.)

## Creating a Django Project and App

1. Create the Django project:
   * `django_web3_auth_env\Scripts\django-admin startproject moralis_auth` and `django-admin` will be found in the `Scripts` folder: `django_web3_auth_env\Scripts\django-admin.exe`.
2. Create the Django app:
   * `django_web3_auth_env\Scripts\python.exe manage.py startapp web3_auth`.
   * You can move that newly created app folder named `web3_auth` into the same folder where the `moralis_auth` project is in - the same folder where `manage.py` is located.
3. Run database migrations:
   * `django_web3_auth_env\Scripts\python.exe manage.py migrate`. Here, you will have to use the complete path that points to the Python executable in the newly created virtual environment.
4. Create a **super user** (it can be used in the Django admin interface); it is optional:
   * `django_web3_auth_env\Scripts\python.exe manage.py createsuperuser`. Here, you will have to use the complete path that points to the Python executable in the new created virtual environment.

## Edit `moralis_auth` Project Settings

1. Add the newly created app named `web3_auth` to the list of installed apps in `settings.py` at the end of the `INSTALLED_APPS` list:

```python settings.py theme={null}
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'web3_auth'
]
```

2. Include URLs from the newly created app in the new project (here, we also added the URLs from `django.contrib.auth.urls` to be able to use the log-out functionality):

```python urls.py theme={null}
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('web3_auth/', include('web3_auth.urls')),
    path('auth/', include('django.contrib.auth.urls')),
]
```

## Creating the Main *web3\_auth* Application (`urls.py`, `views.py`, and Templates)

1. The contents for `urls.py` (you will have to create this file):

```python urls.py theme={null}
from django.urls import path

from . import views

urlpatterns = [
    path('moralis_auth', views.moralis_auth, name='moralis_auth'),
    path('request_message', views.request_message, name='request_message'),
    path('my_profile', views.my_profile, name='my_profile'),
    path('verify_message', views.verify_message, name='verify_message')
]
```

* `moralis_auth` will contain the data from where a user can authenticate.
* `request_message` will make a request to the Moralis Auth API for a message to be signed.
* `my_profile` will show current profile info for a user when authenticated.
* `verify_message` will be used to verify a message that was signed.

2. The contents for `views.py` (you will need to set your Web3 API key on line nine \[`API_KEY = 'WEB3_API_KEY_HERE'`]):

```python views.py theme={null}
import json
import requests

from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from datetime import datetime, timedelta, timezone

API_KEY = 'WEB3_API_KEY_HERE'
# this is a check to make sure the API key was set
# you have to set the API key only in line 9 above
# you don't have to change the next line
if API_KEY == 'WEB3_API_KEY_HERE':
    print("API key is not set")
    raise SystemExit


def moralis_auth(request):
    return render(request, 'login.html', {})

def my_profile(request):
    return render(request, 'profile.html', {})

def request_message(request):
    data = json.loads(request.body)
    print(data)

    #setting request expiration time to 1 minute after the present->
    present = datetime.now(timezone.utc)
    present_plus_one_m = present + timedelta(minutes=1)
    expirationTime = str(present_plus_one_m.isoformat())
    expirationTime = str(expirationTime[:-6]) + 'Z'

    REQUEST_URL = 'https://authapi.moralis.io/challenge/request/evm'
    request_object = {
      "domain": "defi.finance",
      "chainId": 1,
      "address": data['address'],
      "statement": "Please confirm",
      "uri": "https://defi.finance/",
      "expirationTime": expirationTime,
      "notBefore": "2020-01-01T00:00:00.000Z",
      "timeout": 15
    }
    x = requests.post(
        REQUEST_URL,
        json=request_object,
        headers={'X-API-KEY': API_KEY})

    return JsonResponse(json.loads(x.text))


def verify_message(request):
    data = json.loads(request.body)
    print(data)

    REQUEST_URL = 'https://authapi.moralis.io/challenge/verify/evm'
    x = requests.post(
        REQUEST_URL,
        json=data,
        headers={'X-API-KEY': API_KEY})
    print(json.loads(x.text))
    print(x.status_code)
    if x.status_code == 201:
        # user can authenticate
        eth_address=json.loads(x.text).get('address')
        print("eth address", eth_address)
        try:
            user = User.objects.get(username=eth_address)
        except User.DoesNotExist:
            user = User(username=eth_address)
            user.is_staff = False
            user.is_superuser = False
            user.save()
        if user is not None:
            if user.is_active:
                login(request, user)
                request.session['auth_info'] = data
                request.session['verified_data'] = json.loads(x.text)
                return JsonResponse({'user': user.username})
            else:
                return JsonResponse({'error': 'account disabled'})
    else:
        return JsonResponse(json.loads(x.text))
```

Here we have a view for the main authentication: `moralis_auth`; one view to display the profile info: `my_profile`; and two views specific to authentication: `request_message` and `verify_message`. Furthermore, `verify_message` will request a message from the Moralis Auth API that will be signed with MetaMask, and `verify_message` will validate the received signature and create a user when the validation succeeds. After that, a session is created for that user, and we can add additional info in that session, such as the data that was used specifically for authentication.

3. Templates (you will have to create a folder named templates):

* `login.html`, this template contains all the JavaScript code required to sign a message with MetaMask:

```html login.html theme={null}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Moralis Auth Django Demo</title>
</head>
<body>
    <div>

    {% if user.is_authenticated %}
        <h1>Welcome Moralis Web3 User, {{ user.username }} !</h1>
        <a href="{% url 'logout' %}?next={% url 'moralis_auth' %}">Logout</a>
        <br/>
        <a href="{% url 'my_profile' %}"> My profile </a>
    {% else %}
        <h1>Moralis Web3 Login Django demo</h1>
        <button class="btn" id="auth-metamask">Login with Moralis Web3 API</button>
    {% endif %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <script src="https://cdn.ethers.io/lib/ethers-5.2.umd.min.js" type="application/javascript"></script>

    {% if user.is_authenticated %}
    {% else %}
    <script>
    const elBtnMetamask = document.getElementById('auth-metamask');

    const handleApiPost = async (endpoint, params) => {
      const result = await axios.post(`${endpoint}`, params, {
        headers: {
          'Content-Type': 'application/json',
          "X-CSRFToken": '{{ csrf_token }}'
        },
      });
    
      return result.data;
    };

    const requestMessage = (account, chain) =>
      handleApiPost('{% url 'request_message' %}', {
        address: account,
        chain: chain,
        network: 'evm',
      });

    const verifyMessage = (message, signature) =>
      handleApiPost('{% url 'verify_message' %}', {
        message,
        signature,
        network: 'evm',
      });

    const connectToMetamask = async () => {
      const provider = new ethers.providers.Web3Provider(window.ethereum, 'any');
    
      const [accounts, chainId] = await Promise.all([
        provider.send('eth_requestAccounts', []),
        provider.send('eth_chainId', []),
      ]);

      const signer = provider.getSigner();
      return { signer, chain: chainId, account: accounts[0] };
    };

    const handleAuth = async () => {
      // Connect to Metamask
      const { signer, chain, account } = await connectToMetamask();
      console.log("account", account, "chain", chain)

      if (!account) {
        throw new Error('No account found');
      }
      if (!chain) {
        throw new Error('No chain found');
      }

      const { message } = await requestMessage(account, chain);
      const signature = await signer.signMessage(message);
      const { user } = await verifyMessage(message, signature);
      console.log(user)
      if (user) {
        location.reload();
      }
      else{
        alert("authentication error")
      }
    };


    function init() {
      elBtnMetamask.addEventListener('click', async () => {
        handleAuth().catch((error) => console.log(error));
      });
    }

    window.addEventListener('load', () => {
      init();
    });

    </script>
    {% endif %}
</body>
</html>
```

* `profile.html`, this template only shows current info associated with an authenticated user:

```html profile.html theme={null}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Moralis Auth Django Profile Page Demo</title>
</head>
<body>
    <div>

    {% if user.is_authenticated %}
        <h1>Eth address: {{ user.username }}</h1>
        <h3>Session auth info</h3>
        <table width="200px" border="0px" padding="5px">
        {% for key,value in request.session.auth_info.items %}
            <tr><td>{{key}}</td><td><pre>{{ value }}</pre></td></tr>
        {% endfor %}
        </table>
        <table width="200px" border="0px" padding="0px">
        <h3>Verified user info</h3>
        {% for key,value in request.session.verified_data.items %}
            <tr><td>{{key}}</td><td>{{ value }}</td></tr>
        {% endfor %}

        </table>
        <br/>
        <a href="{% url 'logout' %}?next={% url 'moralis_auth' %}">Logout</a>
    {% else %}
        <a href="{% url 'moralis_auth' %}"> Login page </a>
    {% endif %}
    </div>

</body>
</html>
```

## Starting the Application

* `django_web3_auth_env\Scripts\python.exe manage.py runserver 1000` (this will start a local server on port **1000**).

After the application starts, this is how it should look when you access `http://127.0.0.1:1000/web3_auth/moralis_auth`

This will show when clicking on the above "login" button

After the message is signed and the authentication is successful, you can see the complete profile page:


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with MetaMask using Angular

> Learn how Moralis authentication works and see how to add secure authentication to your Angular dapp. This tutorial covers how to create full-stack Web3 authentication using the popular Angular framework.

## Introduction

This tutorial demonstrates how to create an Angular application that allows users to log in using their Web3 wallets.

After Web3 wallet authentication, the server creates a session cookie with a signed [JWT](https://jwt.io/introduction) stored inside. It contains session info (such as an address, signed message) in the user's browser.

Once the user is logged in, they will be able to visit a page that displays all their user data.

## Prerequisites

1. Follow the Your First Dapp - Angular tutorial to set up your Angular dapp and server

## Install the Required Dependencies

To implement authentication using a Web3 wallet (e.g., MetaMask), we will use a Web3 library. For the tutorial, we will use [@wagmi/core](https://github.com/wagmi-dev/wagmi/tree/main/packages/core).

1. Install `@wagmi/core`, `@wagmi/connectors`, `viem@2.x`, and `axios` dependencies.

```bash npm2yarn theme={null}
npm install @wagmi/core @wagmi/connectors viem@2.x
```

2. Generate an environment file for our Angular app:

```bash npm2yarn theme={null}
ng generate environments
```

3. Open `src/environments/environment.ts` and `src/environments/environment.prod.ts` - add a variable of `SERVER_URL` for our server.

```typescript  theme={null}
export const environment = {
  SERVER_URL: "http://localhost:3000",
};
```

4. We will generate two components (pages) - `/signin` (to authenticate) and `/user` (to show the user profile):

```shell  theme={null}
ng generate component signin
ng generate component user
```

5. Open `src/app/app.routes.ts`, add these two components as routes:

```typescript  theme={null}
import { SigninComponent } from "./signin/signin.component";
import { UserComponent } from "./user/user.component";

const routes: Routes = [
  { path: "signin", component: SigninComponent },
  { path: "user", component: UserComponent },
];
```

## Initial Setup

We will do an initial setup of our `/signin` and `/user` pages to make sure they work before integrating with our server.

1. Open `src/app/signin/signin.component.html` and replace the contents with:

```typescript  theme={null}
<h3>Web3 Authentication</h3>
<button type="button" (click)="handleAuth()">Authenticate via MetaMask</button>
```

2. Open `src/app/signin/signin.component.ts` and add an empty `handleAuth` function below `ngOnInit(): void {}`:

```typescript  theme={null}
ngOnInit(): void {}

async handleAuth() {}
```

3. Run `npm run start` and open [`http://localhost:4200/signin`](http://localhost:4200/signin) in your browser. It should look like:
4. Import `NgIf` in `src/app/user/user.component.ts`:

```typescript  theme={null}
import { Component } from "@angular/core";
import { NgIf } from "@angular/common"; // Import NgIf

@Component({
  selector: "app-user",
  standalone: true,
  imports: [NgIf], // Include NgIf in the imports array
  templateUrl: "./user.component.html",
  styleUrls: ["./user.component.css"],
})
export class UserComponent {}
```

5. Open `src/app/user/user.component.html` and replace the contents with:

```typescript  theme={null}
<div *ngIf="session">
  <h3>User session:</h3>
  <pre>{{ session }}</pre>
  <button type="button" (click)="signOut()">Sign out</button>
</div>
```

6. Open `src/app/user/user.component.ts` and add the variable we used above and an empty `signOut()` function:

```typescript  theme={null}
session = '';

ngOnInit(): void {}

async signOut() {}
```

## Server Setup

Now we will update our server's `index.js` for the code we need for authentication. In this demo, cookies will be used for the user data.

1. Install the required dependencies for our server:

```shell  theme={null}
npm install cookie-parser jsonwebtoken dotenv
```

2. Create a file called `.env` in your server's root directory (where `package.json` is):

* **APP\_DOMAIN**: RFC 4501 DNS authority that is requesting the signing.
* **MORALIS\_API\_KEY**: You can get it [here](https://admin.moralis.com/account/profile).
* **ANGULAR\_URL**: Your app address. By default Angular uses [`http://localhost:4200`](http://localhost:4200/).
* **AUTH\_SECRET**: Used for signing JWT tokens of users. You can put any value here or generate it on [`https://generate-secret.now.sh/32`](https://generate-secret.now.sh/32). Here's an `.env` example:

```
APP_DOMAIN=localhost
MORALIS_API_KEY=xxxx
ANGULAR_URL=http://localhost:4200
AUTH_SECRET=1234
```

3. Open `index.js`. We will create a `/request-message` endpoint for making requests to `Moralis.Auth` to generate a unique message (Angular will use this endpoint on the `/signin` page):

```javascript  theme={null}
// to use our .env variables
require("dotenv").config();

// for our server's method of setting a user session
const cookieParser = require("cookie-parser");
const jwt = require("jsonwebtoken");

const config = {
  domain: process.env.APP_DOMAIN,
  statement: "Please sign this message to confirm your identity.",
  uri: process.env.ANGULAR_URL,
  timeout: 60,
};

app.post("/request-message", async (req, res) => {
  const { address, chain } = req.body;

  try {
    const message = await Moralis.Auth.requestMessage({
      address,
      chain,
      ...config,
    });

    res.status(200).json(message);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});
```

4. We will create a `/verify` endpoint for verifying the signed message from the user. After the user successfully verifies, they will be redirected to the `/user` page where their info will be displayed.

```javascript  theme={null}
app.post("/verify", async (req, res) => {
  try {
    const { message, signature } = req.body;

    const { address, profileId } = (
      await Moralis.Auth.verify({
        message,
        signature,
        networkType: "evm",
      })
    ).raw;

    const user = { address, profileId, signature };

    // create JWT token
    const token = jwt.sign(user, process.env.AUTH_SECRET);

    // set JWT cookie
    res.cookie("jwt", token, {
      httpOnly: true,
    });

    res.status(200).json(user);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});
```

5. We will create an `/authenticate` endpoint for checking the JWT cookie we previously set to allow the user access to the `/user` page:

```javascript  theme={null}
app.get("/authenticate", async (req, res) => {
  const token = req.cookies.jwt;
  if (!token) return res.sendStatus(403); // if the user did not send a jwt token, they are unauthorized

  try {
    const data = jwt.verify(token, process.env.AUTH_SECRET);
    res.json(data);
  } catch {
    return res.sendStatus(403);
  }
});
```

6. Lastly we will create a `/logout` endpoint for removing the cookie.

```javascript  theme={null}
app.get("/logout", async (req, res) => {
  try {
    res.clearCookie("jwt");
    return res.sendStatus(200);
  } catch {
    return res.sendStatus(403);
  }
});
```

Your final `index.js` should look like this:

```javascript  theme={null}
const Moralis = require("moralis").default;

const express = require("express");
const cors = require("cors");
const cookieParser = require("cookie-parser");
const jwt = require("jsonwebtoken");

require("dotenv").config();

const app = express();
const port = 3000;

app.use(express.json());
app.use(cookieParser());

// allow access to Angular app domain
app.use(
  cors({
    origin: process.env.ANGULAR_URL,
    credentials: true,
  })
);

const config = {
  domain: process.env.APP_DOMAIN,
  statement: "Please sign this message to confirm your identity.",
  uri: process.env.ANGULAR_URL,
  timeout: 60,
};

// request message to be signed by client
app.post("/request-message", async (req, res) => {
  const { address, chain } = req.body;

  try {
    const message = await Moralis.Auth.requestMessage({
      address,
      chain,
      ...config,
    });

    res.status(200).json(message);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});

// verify message signed by client
app.post("/verify", async (req, res) => {
  try {
    const { message, signature } = req.body;

    const { address, profileId } = (
      await Moralis.Auth.verify({
        message,
        signature,
        networkType: "evm",
      })
    ).raw;

    const user = { address, profileId, signature };

    // create JWT token
    const token = jwt.sign(user, process.env.AUTH_SECRET);

    // set JWT cookie
    res.cookie("jwt", token, {
      httpOnly: true,
    });

    res.status(200).json(user);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});

// verify JWT cookie to allow access
app.get("/authenticate", async (req, res) => {
  const token = req.cookies.jwt;
  if (!token) return res.sendStatus(403); // if the user did not send a jwt token, they are unauthorized

  try {
    const data = jwt.verify(token, process.env.AUTH_SECRET);
    res.json(data);
  } catch {
    return res.sendStatus(403);
  }
});

// remove JWT cookie
app.get("/logout", async (req, res) => {
  try {
    res.clearCookie("jwt");
    return res.sendStatus(200);
  } catch {
    return res.sendStatus(403);
  }
});

const startServer = async () => {
  await Moralis.start({
    apiKey: process.env.MORALIS_API_KEY,
  });

  app.listen(port, () => {
    console.log(`Example app listening on port ${port}`);
  });
};

startServer();
```

7. Run `npm run start` to make sure your server runs without immediate errors.

```shell  theme={null}
node index.js
```

## Bringing It All Together

Now we will finish setting up our Angular pages to integrate with our server.

1. Open `src/app/signin/signin.component.ts`. Add our required imports:

```typescript  theme={null}
import { Component } from "@angular/core";
// for navigating to other routes
import { Router } from "@angular/router";

// for making HTTP requests
import axios from "axios";

import {
  connect,
  disconnect,
  getAccount,
  injected,
  signMessage,
} from "@wagmi/core";
import { http, createConfig } from "@wagmi/core";
import { mainnet, sepolia } from "@wagmi/core/chains";

import { environment } from "../../environments/environment";
```

2. Add this code to set up the Wagmi client:

```typescript  theme={null}
export const config = createConfig({
  chains: [mainnet, sepolia],
  transports: {
    [mainnet.id]: http(),
    [sepolia.id]: http(),
  },
});
```

3. Replace our empty `handleAuth()` function with the following:

```typescript  theme={null}
  async handleAuth() {
    const { isConnected } = getAccount(config);

    if (isConnected) await disconnect(config); //disconnects the web3 provider if it's already active

    const provider = await connect(config, { connector: injected() }); // enabling the web3 provider metamask

    const userData = {
      address: provider.accounts[0],
      chain: provider.chainId,
    };

    const { data } = await axios.post(
      `${environment.SERVER_URL}/request-message`,
      userData
    );

    const message = data.message;

    const signature = await signMessage(config, { message });

    await axios.post(
      `${environment.SERVER_URL}/verify`,
      {
        message,
        signature,
      },
      { withCredentials: true } // set cookie from Express server
    );

    // redirect to /user
    this.router.navigateByUrl('/user');
  }
```

4. The full `signin.component.ts` should look like:

```typescript  theme={null}
import { Component } from "@angular/core";
// for navigating to other routes
import { Router } from "@angular/router";

// for making HTTP requests
import axios from "axios";

import {
  connect,
  disconnect,
  getAccount,
  injected,
  signMessage,
} from "@wagmi/core";
import { http, createConfig } from "@wagmi/core";
import { mainnet, sepolia } from "@wagmi/core/chains";

import { environment } from "../../environments/environment";

export const config = createConfig({
  chains: [mainnet, sepolia],
  transports: {
    [mainnet.id]: http(),
    [sepolia.id]: http(),
  },
});

@Component({
  selector: "app-signin",
  standalone: true,
  imports: [],
  templateUrl: "./signin.component.html",
  styleUrl: "./signin.component.css",
})
export class SigninComponent {
  constructor(private router: Router) {}
  ngOnInit(): void {}

  async handleAuth() {
    const { isConnected } = getAccount(config);

    if (isConnected) await disconnect(config); //disconnects the web3 provider if it's already active

    const provider = await connect(config, { connector: injected() }); // enabling the web3 provider metamask

    const userData = {
      address: provider.accounts[0],
      chain: provider.chainId,
    };

    const { data } = await axios.post(
      `${environment.SERVER_URL}/request-message`,
      userData
    );

    const message = data.message;

    const signature = await signMessage(config, { message });

    await axios.post(
      `${environment.SERVER_URL}/verify`,
      {
        message,
        signature,
      },
      { withCredentials: true } // set cookie from Express server
    );

    // redirect to /user
    this.router.navigateByUrl("/user");
  }
}
```

5. Open `src/app/user/user.component.ts`. Add our required imports:

```typescript  theme={null}
import { Router } from "@angular/router";

import axios from "axios";

import { environment } from "../../environments/environment";
```

6. Replace `ngOnInit(): void {}` with:

```typescript  theme={null}
async ngOnInit() {
  try {
    const { data } = await axios.get(
      `${environment.SERVER_URL}/authenticate`,
      {
        withCredentials: true,
      }
    );

    const { iat, ...authData } = data; // remove unimportant iat value

    this.session = JSON.stringify(authData, null, 2); // format to be displayed nicely
  } catch (err) {
    // if user does not have a "session" token, redirect to /signin
    this.router.navigateByUrl('/signin');
  }
}
```

7. Replace our empty `signOut()` function with the following:

```typescript  theme={null}
async signOut() {
  await axios.get(`${environment.SERVER_URL}/logout`, {
    withCredentials: true,
  });
  this.router.navigateByUrl('/signin');
}
```

8. The full `user.component.ts` should look like:

```typescript  theme={null}
import { Component } from "@angular/core";
import { NgIf } from "@angular/common"; // Import NgIf
import { Router } from "@angular/router";
import axios from "axios";
import { environment } from "../../environments/environment";

@Component({
  selector: "app-user",
  standalone: true,
  imports: [NgIf], // Include NgIf in the imports array
  templateUrl: "./user.component.html",
  styleUrls: ["./user.component.css"],
})
export class UserComponent {
  constructor(private router: Router) {}

  session = "";

  async ngOnInit() {
    try {
      const { data } = await axios.get(
        `${environment.SERVER_URL}/authenticate`,
        {
          withCredentials: true,
        }
      );

      const { iat, ...authData } = data; // remove unimportant iat value

      this.session = JSON.stringify(authData, null, 2); // format to be displayed nicely
    } catch (err) {
      // if user does not have a "session" token, redirect to /signin
      this.router.navigateByUrl("/signin");
    }
  }

  async signOut() {
    await axios.get(`${environment.SERVER_URL}/logout`, {
      withCredentials: true,
    });
    this.router.navigateByUrl("/signin");
  }
}
```

If you get errors related to default imports, open your `tsconfig.app.json` file and add `"allowSyntheticDefaultImports": true` under `compilerOptions`:

```json  theme={null}
"compilerOptions": {
  "allowSyntheticDefaultImports": true,
  "outDir": "./out-tsc/app",
  "types": []
}
```

## Testing the MetaMask Wallet Connector

Visit [`http://localhost:4200/signin`](http://localhost:4200/signin) to test the authentication.

1. Click on the `Authenticate via MetaMask` button
2. Connect the MetaMask wallet and sign the message
3. After successful authentication, you will be redirected to the `/user` page

* When a user authenticates, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page.


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with Magic.Link

> This tutorial will teach you how to add secure Web3 Moralis authentication to your NextJS application by walking you through the task of creating a full-stack Web3 authentication solution using the popular NextJS framework.

## Before Starting

You can start this tutorial if you already have a NextJS dapp with [MetaMask sign-in](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask) functionality.

## Installing the Magic Connector

[WAGMI Magic Connector](https://www.npmjs.com/package/@everipedia/wagmi-magic-connector) - the easiest way to add [Magic.Link authentication](https://magic.link/auth) for dapps using [wagmi](https://wagmi.sh/):

```bash npm2yarn theme={null}
npm install @everipedia/wagmi-magic-connector
```

## Configuring the Magic Connector

1. Open the`pages/signin.jsx` file and add `MagicConnector` as a connector to the `useConnect()` hook:

```javascript  theme={null}
import { MagicAuthConnector } from "@everipedia/wagmi-magic-connector";
import { signIn } from "next-auth/react";
import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { useRouter } from "next/router";
import { useAuthRequestChallengeEvm } from "@moralisweb3/next";

function SignIn() {
  const { connectAsync } = useConnect({
    connector: new MagicAuthConnector({
      options: {
        apiKey: "YOUR_MAGIC_LINK_API_KEY", //required
      },
    }),
  });
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { requestChallengeAsync } = useAuthRequestChallengeEvm();
  const { push } = useRouter();

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync();
    }

    const { account } = await connectAsync();

    const { message } = await requestChallengeAsync({
      address: account,
      chainId: "0x1",
    });

    const signature = await signMessageAsync({ message });

    // redirect user after success authentication to '/user' page
    const { url } = await signIn("moralis-auth", {
      message,
      signature,
      redirect: false,
      callbackUrl: "/user",
    });
    /**
     * instead of using signIn(..., redirect: "/user")
     * we get the url from callback and push it to the router to avoid page refreshing
     */
    push(url);
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={() => handleAuth()}>Authenticate via Magic.Link</button>
    </div>
  );
}

export default SignIn;
```

## Testing the WalletConnect Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin) to test authentication.

1. Click on `Authenticate via Magic.Link`
2. Enter your email
3. Verify the login from your email
4. After successful authentication, you will be redirected to the `/user` page
5. Visit [`http://localhost:3000/user`](http://localhost:3000/user) to test the user session's functionality:

* When a user is authenticated, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page. ([***`Explanation: After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT [JWE] stored inside. It contains session info [such as an address and signed message] in the user's browser.`***](https://jwt.io/introduction))


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with Coinbase Wallet

> This tutorial will teach you how to add secure Web3 Moralis authentication to your NextJS application by walking you through creating a full-stack Web3 authentication solution using the popular NextJS framework.

## Before Starting

You can start this tutorial if you already have a NextJS dapp with [MetaMask sign-in](/get-started/tutorials/auth-api/authenticate-users-with-meta-mask) functionality.

## Configuring the Coinbase Wallet Connector

1. Open the `pages/signin.jsx` file and add `CoinbaseWalletConnector` as a connector to `connectAsync()`:

```javascript  theme={null}
import { CoinbaseWalletConnector } from 'wagmi/connectors/coinbaseWallet'
import { signIn } from 'next-auth/react'
import { useAccount, useConnect, useSignMessage, useDisconnect } from 'wagmi'
import { useRouter } from 'next/router'
import { useAuthRequestChallengeEvm } from '@moralisweb3/next'

function SignIn() {
  const { connectAsync } = useConnect()
  const { disconnectAsync } = useDisconnect()
  const { isConnected } = useAccount()
  const { signMessageAsync } = useSignMessage()
  const { push } = useRouter()
  const { requestChallengeAsync } = useAuthRequestChallengeEvm()

  const handleAuth = async () => {
    if (isConnected) {
      await disconnectAsync()
    }

    const { account, chain } = await connectAsync({
      connector: new CoinbaseWalletConnector({
        options: {
          appName: 'amazing.finance',
        },
      }),
    })

    const userData = { address: account, chain: chain.id, network: 'evm' }

    const { message } = await requestChallengeAsync(userData)

    const signature = await signMessageAsync({ message })

    // redirect user after success authentication to '/user' page
    const { url } = await signIn('moralis-auth', {
      message,
      signature,
      redirect: false,
      callbackUrl: '/user',
    })
    /**
     * instead of using signIn(..., redirect: "/user")
     * we get the url from callback and push it to the router to avoid page refreshing
     */
    push(url)
  }

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={() => handleAuth()}>Authenticate via Coinbase Wallet</button>
    </div>
  )
}

export default SignIn
```

## Testing the Coinbase Wallet Connector

Visit [`http://localhost:3000/signin`](http://localhost:3000/signin) to test authentication.

1. Click on `Authenticate via Coinbase Wallet`
2. Connect Coinbase Wallet
3. Sign the message
4. After successful authentication, you will be redirected to the `/user` page
5. Visit [`http://localhost:3000/user`](http://localhost:3000/user) to test the user session's functionality:

* When a user is authenticated, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page. ([***`Explanation: After Web3 wallet authentication, the next-auth library creates a session cookie with an encrypted JWT [JWE] stored inside. It contains session info [such as an address and signed message] in the user's browser.`***](https://jwt.io/introduction))


Built with [Mintlify](https://mintlify.com).

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.moralis.com/llms.txt
> Use this file to discover all available pages before exploring further.

# How to Authenticate Users with MetaMask using React

> Learn how Moralis authentication works and see how to add secure authentication to your React dapp. This tutorial covers how to create full-stack Web3 authentication using the popular React framework.

## Introduction

This tutorial demonstrates how to create a React app that allows users to log in using their Web3 wallets.

After Web3 wallet authentication, the server creates a session cookie with a signed [JWT](https://jwt.io/introduction) stored inside. It contains session info (such as an address, signed message) in the user's browser.

Once the user is logged in, they will be able to visit a page that displays all their user data.

## Prerequisites

1. Follow the Your First Dapp - React tutorial to set up your React dapp and server

## Install the Required Dependencies

To implement authentication using a Web3 wallet (e.g., MetaMask), we will use a Web3 library. For the tutorial, we will use [wagmi](https://wagmi.sh).

1. Install `wagmi` and `viem` in your React app:

```bash npm2yarn theme={null}
npm install wagmi viem
```

## Initial Setup

First we will add an environment variable that will be used when calling our API.

1. Create a file called `.env` in the root of your react project (where `package.json` is) and add:

```sh  theme={null}
REACT_APP_SERVER_URL=http://localhost:4000
```

Next we will add the providers required for `wagmi`.

2. Open `src/App.js` and add our required imports:

```javascript  theme={null}
import { createConfig, configureChains, WagmiConfig } from "wagmi";
import { publicProvider } from "wagmi/providers/public";
import { mainnet } from "wagmi/chains";

import Signin from "./signin";
import User from "./user";
```

3. We will add the client and providers, and update the routes for our `/signin` component (to be set up next):

```javascript  theme={null}
const { publicClient, webSocketPublicClient } = configureChains(
  [mainnet],
  [publicProvider()]
);

const config = createConfig({
  autoConnect: true,
  publicClient,
  webSocketPublicClient,
});

const router = createBrowserRouter([
  {
    path: "/signin",
    element: <Signin />,
  },
  {
    path: "/user",
    element: <User />,
  },
  {
    path: "/",
    element: <h1>Home Component</h1>,
  },
]);

function App() {
  return (
    <WagmiConfig config={config}>
      <RouterProvider router={router} />
    </WagmiConfig>
  );
}

export default App;
```

# Your full App.js file should look like this

```javascript  theme={null}
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { createConfig, configureChains, WagmiConfig } from "wagmi";
import { publicProvider } from "wagmi/providers/public";
import { mainnet } from "wagmi/chains";

import Signin from "./signin";
import User from "./user";

const { publicClient, webSocketPublicClient } = configureChains(
  [mainnet],
  [publicProvider()]
);

const config = createConfig({
  autoConnect: true,
  publicClient,
  webSocketPublicClient,
});

const router = createBrowserRouter([
  {
    path: "/signin",
    element: <Signin />,
  },
  {
    path: "/user",
    element: <User />,
  },
  {
    path: "/",
    element: <h1>Home Component</h1>,
  },
]);

function App() {
  return (
    <WagmiConfig config={config}>
      <RouterProvider router={router} />
    </WagmiConfig>
  );
}

export default App;
```

## Server Setup

Back in our server directory we will update our server's `index.js` for the code we need for authentication. In this demo, cookies will be used for the user data.

1. Install the required dependencies for our server:

```shell  theme={null}
npm install cookie-parser jsonwebtoken dotenv
```

2. Create a file called `.env` in your server's root directory (where `package.json` is):

* **APP\_DOMAIN**: RFC 4501 DNS authority that is requesting the signing.
* **MORALIS\_API\_KEY**: You can get it [here](https://admin.moralis.com/account/profile).
* **REACT\_URL**: Your app address. By default React uses [`http://localhost:3000`](http://localhost:3000).
* **AUTH\_SECRET**: Used for signing JWT tokens of users. You can put any value here or generate it on [`https://generate-secret.now.sh/32`](https://generate-secret.now.sh/32).

```
APP_DOMAIN=amazing.finance
MORALIS_API_KEY=xxxx
REACT_URL=http://localhost:3000
AUTH_SECRET=1234
```

3. Open `index.js`. We will create a `/request-message` endpoint for making requests to `Moralis.Auth` to generate a unique message (React will use this endpoint on the `/signin` page):

```javascript  theme={null}
// to use our .env variables
require("dotenv").config();

app.use(express.json());

// for our server's method of setting a user session
const cookieParser = require("cookie-parser");
const jwt = require("jsonwebtoken");

const config = {
  domain: process.env.APP_DOMAIN,
  statement: "Please sign this message to confirm your identity.",
  uri: process.env.REACT_URL,
  timeout: 60,
};

app.post("/request-message", async (req, res) => {
  const { address, chain, network } = req.body;

  try {
    const message = await Moralis.Auth.requestMessage({
      address,
      chain,
      ...config,
    });

    res.status(200).json(message);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});
```

4. We will create a `/verify` endpoint for verifying the signed message from the user. After the user successfully verifies, they will be redirected to the `/user` page where their info will be displayed:

```javascript  theme={null}
app.post("/verify", async (req, res) => {
  try {
    const { message, signature } = req.body;

    const { address, profileId } = (
      await Moralis.Auth.verify({
        message,
        signature,
        networkType: "evm",
      })
    ).raw;

    const user = { address, profileId, signature };

    // create JWT token
    const token = jwt.sign(user, process.env.AUTH_SECRET);

    // set JWT cookie
    res.cookie("jwt", token, {
      httpOnly: true,
    });

    res.status(200).json(user);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});
```

5. We will create an `/authenticate` endpoint for checking the JWT cookie we previously set to allow the user access to the `/user` page:

```javascript  theme={null}
app.get("/authenticate", async (req, res) => {
  const token = req.cookies.jwt;
  if (!token) return res.sendStatus(403); // if the user did not send a jwt token, they are unauthorized

  try {
    const data = jwt.verify(token, process.env.AUTH_SECRET);
    res.json(data);
  } catch {
    return res.sendStatus(403);
  }
});
```

6. Lastly we will create a `/logout` endpoint for removing the cookie:

```javascript  theme={null}
app.get("/logout", async (req, res) => {
  try {
    res.clearCookie("jwt");
    return res.sendStatus(200);
  } catch {
    return res.sendStatus(403);
  }
});
```

Your final `index.js` should look like this:

```javascript  theme={null}
const Moralis = require("moralis").default;

const express = require("express");
const cors = require("cors");
const cookieParser = require("cookie-parser");
const jwt = require("jsonwebtoken");

// to use our .env variables
require("dotenv").config();

const app = express();
const port = 4000;

app.use(express.json());
app.use(cookieParser());

// allow access to React app domain
app.use(
  cors({
    origin: "http://localhost:3000",
    credentials: true,
  })
);

const config = {
  domain: process.env.APP_DOMAIN,
  statement: "Please sign this message to confirm your identity.",
  uri: process.env.REACT_URL,
  timeout: 60,
};

// request message to be signed by client
app.post("/request-message", async (req, res) => {
  const { address, chain, network } = req.body;

  try {
    const message = await Moralis.Auth.requestMessage({
      address,
      chain,
      ...config,
    });

    res.status(200).json(message);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});

app.post("/verify", async (req, res) => {
  try {
    const { message, signature } = req.body;

    const { address, profileId } = (
      await Moralis.Auth.verify({
        message,
        signature,
        networkType: "evm",
      })
    ).raw;

    const user = { address, profileId, signature };

    // create JWT token
    const token = jwt.sign(user, process.env.AUTH_SECRET);

    // set JWT cookie
    res.cookie("jwt", token, {
      httpOnly: true,
    });

    res.status(200).json(user);
  } catch (error) {
    res.status(400).json({ error: error.message });
    console.error(error);
  }
});

app.get("/authenticate", async (req, res) => {
  const token = req.cookies.jwt;
  if (!token) return res.sendStatus(403); // if the user did not send a jwt token, they are unauthorized

  try {
    const data = jwt.verify(token, process.env.AUTH_SECRET);
    res.json(data);
  } catch {
    return res.sendStatus(403);
  }
});

app.get("/logout", async (req, res) => {
  try {
    res.clearCookie("jwt");
    return res.sendStatus(200);
  } catch {
    return res.sendStatus(403);
  }
});

const startServer = async () => {
  await Moralis.start({
    apiKey: process.env.MORALIS_API_KEY,
  });

  app.listen(port, () => {
    console.log(`Example app listening on port ${port}`);
  });
};

startServer();
```

## Bringing It All Together

Now we will finish setting up our React pages to integrate with our server.

1. In `src`, create a file called `signin.jsx` and add:

```javascript  theme={null}
import { useNavigate } from "react-router-dom";

import { useAccount, useConnect, useSignMessage, useDisconnect } from "wagmi";
import { InjectedConnector } from "wagmi/connectors/injected";
import axios from "axios";

export default function SignIn() {
  const navigate = useNavigate();

  const { connectAsync } = useConnect();
  const { disconnectAsync } = useDisconnect();
  const { isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();

  const handleAuth = async () => {
    //disconnects the web3 provider if it's already active
    if (isConnected) {
      await disconnectAsync();
    }
    // enabling the web3 provider metamask
    const { account } = await connectAsync({
      connector: new InjectedConnector(),
    });

    const userData = { address: account, chain: 1 };
    // making a post request to our 'request-message' endpoint
    const { data } = await axios.post(
      `${process.env.REACT_APP_SERVER_URL}/request-message`,
      userData,
      {
        headers: {
          "content-type": "application/json",
        },
      }
    );
    const message = data.message;
    // signing the received message via metamask
    const signature = await signMessageAsync({ message });

    await axios.post(
      `${process.env.REACT_APP_SERVER_URL}/verify`,
      {
        message,
        signature,
      },
      { withCredentials: true } // set cookie from Express server
    );

    // redirect to /user
    navigate("/user");
  };

  return (
    <div>
      <h3>Web3 Authentication</h3>
      <button onClick={() => handleAuth()}>Authenticate via MetaMask</button>
    </div>
  );
}
```

2. Inside `src`, create a new file called `user.jsx` and add:

```js  theme={null}
import { useEffect, useState } from "react";

import { useNavigate } from "react-router-dom";

import axios from "axios";

export default function User() {
  const navigate = useNavigate();

  const [session, setSession] = useState({});

  useEffect(() => {
    axios(`${process.env.REACT_APP_SERVER_URL}/authenticate`, {
      withCredentials: true,
    })
      .then(({ data }) => {
        const { iat, ...authData } = data; // remove unimportant iat value

        setSession(authData);
      })
      .catch((err) => {
        navigate("/signin");
      });
  }, []);

  async function signOut() {
    await axios(`${process.env.REACT_APP_SERVER_URL}/logout`, {
      withCredentials: true,
    });

    navigate("/signin");
  }

  return (
    <div>
      <h3>User session:</h3>
      <pre>{JSON.stringify(session, null, 2)}</pre>
      <button type="button" onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}
```

## Testing the MetaMask Wallet Connector

In your teminal run `npm run start` and visit [`http://localhost:3000/signin`](http://localhost:3000/signin) to test the authentication.

1. Click on the `Authenticate via MetaMask` button

2. Connect the MetaMask wallet and sign the message

3. After successful authentication, you will be redirected to the `/user` page

* When a user authenticates, we show the user's info on the page.
* When a user is not authenticated, we redirect to the `/signin` page.
* When a user is authenticated, we show the user's info on the page, even refreshing after the page.


Built with [Mintlify](https://mintlify.com).

