# Moralis Workspace Inventory (Shamrock)

Captured from admin.moralis.com screenshots (2026-07-26).  
**Do not put Stream Secret or API keys in this file.** Store secrets only in `.env` / server env.

## Workspace

| Field | Value |
|-------|--------|
| Name | `project_admin@shamrockbailbonds.biz` |
| Workspace ID | `9949f356-2a3e-48c4-82b9-f97eb7580747` |
| Streams region | `us-west-2` |
| Plan CU | ~23M / 500M used (Business) |
| Env vars | `MORALIS_WORKSPACE_NAME`, `MORALIS_WORKSPACE_ID`, `MORALIS_STREAMS_REGION` |

The JWT `MORALIS_API_KEY` `typeId` claim should match Workspace ID (same project).

## Stream Settings → Secret Key

- UI path: **Settings → Workspace → Stream Settings → Secret Key**
- Bot env: `MORALIS_STREAMS_WEBHOOK_SECRET`
- Used by `core/moralis_streams.py` for `x-signature` verification:
  `keccak256(JSON.stringify(body) + secret)`
- **If the secret is ever shown in a screenshot or chat, rotate it in Moralis and update server `.env`.**

## Active Streams (admin.moralis.com/streams)

| Tag | Stream ID | Purpose |
|-----|-----------|---------|
| `shamrock-alpha-wallets` | `ca8ca00b-8b63-4661-8b7e-6409568f3eef` | EVM alpha wallet activity (16 addresses) |
| `shamrock-solana-alpha` | `086633b3-f3c1-4980-b58f-c84df9212ca0` | Solana alpha |
| `shamrock-solana-discovery` | `40a5db4c-e6d1-4d62-9599-e2cc4d563c7e` | Solana discovery |

Env pins (optional): `MORALIS_STREAM_ID_*`

## Webhook URL

| Setting | Correct value |
|---------|----------------|
| `MORALIS_STREAMS_WEBHOOK_URL` | `http://46.62.231.43:8787/moralis/streams` |
| Port | `8787` (docker-compose maps bot) |

**Stale value to avoid:** any `5.161.126.32` host (previous VPS). Moralis will deliver to whatever is configured on each stream — after IP changes, update **both** server `.env` and stream webhook URLs in the Moralis dashboard (or re-run streams manager auto-sync).

## Nodes (admin.moralis.com/nodes)

Dual site per chain → `*_RPC_URL` (site1) + `*_RPC_FALLBACK` (site2):

- Ethereum, BSC, Arbitrum, Avalanche, Base
- Solana: not in Nodes table → Helius / Solana Data API

## Product split (profit architecture)

| Product | Use |
|---------|-----|
| Data API | Token Score, search, PnL, prices (HL quality + gems) |
| Streams | Alpha / discovery push webhooks |
| Nodes | EVM JSON-RPC primary/failover |
| Auth API | Not used for trading |

## After credential changes

1. Update server `.env` and recreate `shamrock-bot`
2. Confirm stream webhook URL in Moralis UI points at current IP
3. Hit test webhook / watch logs for `Test/verification webhook` and signature OK
4. Rotate secret if it was exposed
