# Handoff: MEV Sandwich & Liquidation Engine
**ECC Skill:** `mev-sandwich-liquidator`
**Commit:** `66998ea` — pushed to `main` on `Shamrock2245/shamrock-trading-bot`
**File:** `core/mev_extractor.py` (1,326 lines, fully coded — zero stubs)
**Tests:** `tests/test_mev_extractor.py` — 19/19 passing

---

## What Was Built

Three classes working together inside `core/mev_extractor.py`:

| Class | Role |
|---|---|
| `ProfitGate` | Evaluates every opportunity — executes ONLY if `net_profit > MEV_MIN_NET_PROFIT_USD` |
| `SandwichBot` | Monitors Base mempool + submits Flashbots/Jito bundles |
| `LiquidationHunter` | Monitors Hyperliquid WS + Aave V3 events + executes liquidations |
| `MEVExtractorEngine` | Orchestrates both strategies as concurrent `asyncio` tasks |

---

## Strategy 1 — Sandwich Bot

### Base Chain (Flashbots)
1. Subscribes to `eth_subscribe newPendingTransactions` via `BASE_WS_RPC_URL` (Alchemy/QuickNode WebSocket)
2. Filters for calls to Aerodrome Router (`0xcF77...`) or Uniswap V3 Router Base (`0x2626...`) with `value > $10,000 USD`
3. Decodes calldata: Aerodrome selector `0x8e0d1a5c` → extracts `token_out` + `amountOutMin` slippage; Uniswap V3 selector `0x414bf389` → extracts `tokenOut` + `amountOutMinimum`; falls back to heuristic (2.5–3.5%) for unknown selectors
4. Rejects if `slippage < MEV_SLIPPAGE_THRESHOLD_PCT` (default 2%)
5. Builds **front-run BUY** via `_build_aerodrome_buy_calldata()` → ABI-encodes `swapExactETHForTokens`
6. Builds **back-run SELL** via `_build_aerodrome_sell_calldata()` → ABI-encodes `swapExactTokensForETH`
7. Assembles bundle `[front-run, victim_raw_tx, back-run]`
8. Simulates via `eth_callBundle` on Flashbots relay — discards if `coinbaseDiff ≤ 0`
9. Submits via `eth_sendBundle` with EIP-191 Flashbots signature header

### Solana (Jito)
1. Triggered by the same mempool monitor (Solana-specific pending tx detection via RPC subscription)
2. Calls `_build_jupiter_swap_tx()` → Jupiter V6 `/quote` then `/swap` API → returns base64 `VersionedTransaction`
3. Builds front-run BUY: `USDC → target_token` (20% of victim's notional, max `MEV_MAX_POSITION_USD`)
4. Builds back-run SELL: `target_token → USDC`
5. Builds Jito tip tx via `_build_jito_tip_tx()` using `solders` library → signs a `SystemProgram.transfer` to a random Jito tip account (1,000,000 lamports ≈ $0.15)
6. Fetches `recent_blockhash` via `getLatestBlockhash` RPC call
7. Submits bundle `[tip_tx, front_run, victim_tx, back_run]` to `JITO_BLOCK_ENGINE_URL` via `sendBundle`

---

## Strategy 2 — Liquidation Hunter

### Hyperliquid
1. Connects to `wss://api.hyperliquid.xyz/ws`
2. Subscribes to `allMids` (oracle price feed) and `userEvents` (our own fills)
3. On every `allMids` update → `_check_hl_at_risk_accounts()` polls each address in `MEV_HL_TRACKED_ACCOUNTS` via `POST /info { type: clearinghouseState }`
4. Computes `margin_ratio = accountValue / maintenanceMarginUsed`
5. If `margin_ratio < 1.0` → finds largest open position by notional size → calls `execute_hyperliquid_liquidation()`
6. **SDK path**: uses `hyperliquid-python-sdk` `Exchange.market_open()` if installed
7. **Fallback path**: `_execute_hl_liquidation_direct()` — constructs and signs the HL action payload directly via EIP-191, posts to `https://api.hyperliquid.xyz/exchange`

### Aave V3 (Base + Ethereum)
1. Subscribes to `eth_subscribe logs` for `LiquidationCall` events on the Aave V3 Pool contract
2. Also runs `_poll_aave_borrowers_loop()` every 30s for all known borrowers
3. On event or poll hit → `check_and_liquidate_aave_user()` calls `getUserAccountData()` on-chain
4. If `healthFactor < 1.0` → `_find_best_liquidation_pair()` queries the Aave subgraph to find the user's largest debt asset and largest collateral asset
5. `execute_aave_liquidation()`:
   - Step 1: `ERC20.approve(aavePool, debtToCover)` — allows pool to pull debt tokens
   - Step 2: `Pool.liquidationCall(collateralAsset, debtAsset, user, debtToCover, false)`
   - Both txs sent with `maxFeePerGas = gasPrice * 2` for priority inclusion

---

## Profit Gate — Every Opportunity Screened

```python
net_profit = gross_profit - gas_cost_usd - bribe_cost_usd
# Execute ONLY if net_profit > MEV_MIN_NET_PROFIT_USD (default $1.00)
```

- **Gas cost**: fetched live from chain RPC (`eth_gasPrice`), falls back to per-chain defaults
- **Bribe cost (Base)**: 50% of gas cost estimate
- **Bribe cost (Solana)**: Jito tip = 1,000,000 lamports converted to USD at live SOL price
- **ETH/SOL prices**: fetched from CoinGecko every 60s, cached between calls
- **EVM simulation**: `eth_callBundle` on Flashbots relay — checks `coinbaseDiff > 0` before submitting

---

## Integration into `main.py`

The engine is started as a non-blocking background `asyncio` task in `run_bot_loop()`:

```python
from core.mev_extractor import get_engine as get_mev_engine

# Inside run_bot_loop() — already added:
mev_engine = get_mev_engine()
asyncio.ensure_future(mev_engine.run())
```

Failure to initialise (missing env vars) logs a warning and **never crashes the main bot loop**.

---

## New `.env` Variables Required

Add these to your `.env` on the Hetzner VPS. All are optional — the engine degrades gracefully if missing.

```bash
# ── Sandwich Bot ──────────────────────────────────────────────────────────────
FLASHBOTS_SIGNING_KEY=0x<your_private_key_hex>   # Used for both Flashbots signing AND Aave/HL signing
FLASHBOTS_RPC_URL=https://relay.flashbots.net    # Default — no change needed
BASE_WS_RPC_URL=wss://base-mainnet.g.alchemy.com/v2/<KEY>   # Alchemy/QuickNode WebSocket
ETH_WS_RPC_URL=wss://eth-mainnet.g.alchemy.com/v2/<KEY>     # For Aave ETH event subscription

# ── Jito (Solana sandwich) ────────────────────────────────────────────────────
# JITO_AUTH_KEY is already set — no change needed
# SOLANA_PRIVATE_KEY is already set — no change needed
# JITO_BLOCK_ENGINE_URL defaults to mainnet.block-engine.jito.wtf — no change needed

JUPITER_API_URL=https://api.jup.ag/swap/v1      # Default — no change needed
JUPITER_API_KEY=                                 # Optional — for higher rate limits

# ── Liquidation Hunter ────────────────────────────────────────────────────────
HYPERLIQUID_ENABLED=true
HYPERLIQUID_WALLET_ADDRESS=0x<your_hl_wallet>
HYPERLIQUID_PRIVATE_KEY=0x<your_hl_private_key>  # Falls back to FLASHBOTS_SIGNING_KEY

# Comma-separated list of HL addresses to poll for liquidation opportunities
# Source these from: https://stats.hyperliquid.xyz (top leverage users)
MEV_HL_TRACKED_ACCOUNTS=0xabc...,0xdef...,0x123...

AAVE_POOL_ADDRESS_BASE=0xA238Dd80C259a72e81d7e4664a9801593F98d1c5   # Default — no change
AAVE_POOL_ADDRESS_ETH=0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2    # Default — no change

# ── Profit Gate ───────────────────────────────────────────────────────────────
MEV_MIN_NET_PROFIT_USD=1.0       # Minimum net profit to execute (raise to $5+ in production)
MEV_MAX_POSITION_USD=500.0       # Max capital per sandwich leg
MEV_SLIPPAGE_THRESHOLD_PCT=2.0   # Minimum victim slippage to target
MEV_SANDWICH_ENABLED=true
MEV_LIQUIDATION_ENABLED=true
```

---

## Deploy Commands (Hetzner VPS)

```bash
# SSH into VPS
ssh root@5.161.126.32

# Pull latest code
cd /root/shamrock-trading-bot
git pull origin main

# Install new optional dependency (Solana sandwich)
pip install solders hyperliquid-python-sdk

# Add new env vars to .env (see section above)
nano .env

# Restart the bot
docker compose up -d --build
docker compose logs -f shamrock-bot | grep -E "MEV|Sandwich|Liquidation"
```

---

## Optional: Populate HL Tracked Accounts

The liquidation hunter is most effective when `MEV_HL_TRACKED_ACCOUNTS` is populated with high-leverage wallets. Sources:

1. **Hyperliquid Leaderboard**: `https://stats.hyperliquid.xyz` → filter by leverage > 20×
2. **REST API**: `POST https://api.hyperliquid.xyz/info` `{"type": "leaderboard"}` → extract top accounts
3. **On-chain analytics**: Nansen, Dune dashboard `hyperliquid_high_leverage_wallets`

The engine will also auto-discover borrowers from Aave `LiquidationCall` events and add them to the polling list at runtime.

---

## Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │         MEVExtractorEngine.run()         │
                    │    (asyncio background task in main.py)  │
                    └────────────┬────────────────┬────────────┘
                                 │                │
               ┌─────────────────▼──┐    ┌────────▼───────────────┐
               │    SandwichBot     │    │   LiquidationHunter    │
               │                   │    │                        │
               │ monitor_base_      │    │ monitor_hyperliquid_ws │
               │   mempool()        │    │   ↳ allMids → poll     │
               │   ↳ WS subscribe   │    │     clearinghouseState │
               │   ↳ parse tx       │    │   ↳ margin_ratio < 1.0 │
               │   ↳ ProfitGate     │    │     → execute_hl_liq() │
               │   ↳ Flashbots      │    │                        │
               │     bundle         │    │ monitor_aave_ws()      │
               │                   │    │   ↳ LiquidationCall evt │
               │ execute_sandwich_  │    │   ↳ poll borrowers/30s │
               │   solana()         │    │   ↳ healthFactor < 1.0 │
               │   ↳ Jupiter V6     │    │     → execute_aave_liq │
               │   ↳ Jito bundle    │    │       approve() + call  │
               └────────────────────┘    └────────────────────────┘
                         │                          │
                    ┌────▼──────────────────────────▼────┐
                    │           ProfitGate               │
                    │  net = gross - gas - bribe         │
                    │  EXECUTE only if net > $1.00       │
                    │  EVM: eth_callBundle simulation    │
                    │  Prices: CoinGecko (60s cache)     │
                    └────────────────────────────────────┘
```

---

## Test Coverage

```
tests/test_mev_extractor.py — 19 tests, all passing

TestProfitGate (6 tests)
  ✅ sandwich_profitable_large_swap
  ✅ sandwich_rejected_unprofitable
  ✅ liquidation_profitable_low_health_factor
  ✅ liquidation_rejected_healthy_position
  ✅ liquidation_rejected_tiny_position
  ✅ gas_cost_base_cheaper_than_ethereum
  ✅ jito_tip_reasonable

TestSandwichBot (5 tests)
  ✅ parse_pending_tx_ignores_non_dex
  ✅ parse_pending_tx_ignores_small_swaps
  ✅ parse_pending_tx_detects_large_swap
  ✅ execute_sandwich_base_paper_mode
  ✅ execute_sandwich_solana_paper_mode

TestLiquidationHunter (4 tests)
  ✅ execute_aave_liquidation_paper_mode
  ✅ execute_hyperliquid_liquidation_paper_mode
  ✅ check_and_liquidate_no_web3
  ✅ liquidation_bonus_mapping

TestMEVExtractorEngine (3 tests)
  ✅ get_status_returns_dict
  ✅ engine_components_initialised
  ✅ profit_gate_is_profitable_property
```
