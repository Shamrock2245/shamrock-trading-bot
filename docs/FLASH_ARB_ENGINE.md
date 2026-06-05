# Zero-Risk Flash Arb Engine

## Overview

The Flash Arb Engine upgrades `core/arb_executor.py` to execute arbitrage opportunities
**atomically via flash loans** — borrowing the maximum possible capital, executing the arb
path, repaying the loan, and keeping the profit, all in a single transaction that
**mathematically reverts if the arb is not profitable**.

No wallet capital is at risk. If the arb fails for any reason, the entire transaction
reverts and you pay only the gas cost of the failed transaction.

---

## Architecture

```
ArbOpportunity (from arb_scanner.py)
        │
        ▼
ArbExecutor.execute()
        │
        ├─ Gate 1: Not expired
        ├─ Gate 2: Net profit ≥ 1.5% (FLASH_ARB_MIN_PROFIT_PCT)
        ├─ Gate 3: Gas/profit ratio ≤ 50%
        └─ Gate 4: Live spread re-check (live mode only)
                │
                ├─ cross_dex ──────► _execute_flash_cross_dex()
                │                         │
                ├─ triangular ────────► _execute_flash_triangular()
                │                         │
                └─ cross_chain ───────► _execute_cross_chain_legacy()
                                          (bridge breaks atomicity — no flash loan)

_execute_flash_cross_dex / _execute_flash_triangular:
        │
        ├─ calculate_max_flash_size()  ← max(DEX liquidity × 30%, hard cap $500k)
        ├─ build_oneinch_swap_payload() ← 1inch V6 calldata for each leg
        └─ _dispatch_flash_loan()
                │
                ├─ Balancer V2 (preferred — 0% fee)
                │     └─ FlashArbReceiver.executeBalancerFlashArb()
                │
                └─ Aave V3 fallback (0.05% fee)
                      └─ FlashArbReceiver.executeAaveFlashArb()

FlashArbReceiver.sol (on-chain):
  1. Receive borrowed tokens from Balancer/Aave
  2. Execute all swap legs via 1inch router
  3. Check: endBalance ≥ repaymentAmount  → REVERT if not
  4. Check: netProfit ≥ minExpectedProfit → REVERT if not
  5. Repay flash loan
  6. Transfer profit to owner wallet
```

---

## Flash Loan Providers

| Provider | Fee | Chains | Notes |
|---|---|---|---|
| **Balancer V2** | **0%** | ETH, Base, Arbitrum, Polygon, Avalanche | Preferred — same vault address on all chains |
| **Aave V3** | 0.05% | ETH, Base, Arbitrum, Polygon, Avalanche | Fallback when Balancer unavailable |

**Balancer Vault V2 (canonical address):** `0xBA12222222228d8Ba445958a75a0704d566BF2C8`

---

## Solana Flash Arb

Solana does not have native flash loans. Instead, the engine uses:

1. **Jupiter V6 Route Arb** (primary) — routes `USDC → A → B → USDC` in a **single atomic
   transaction**. Inherently atomic: any hop failure reverts the entire tx.
2. **Kamino Flash Borrow** (large-size arb) — uses `flashBorrowReserveLiquidity` +
   `flashRepayReserveLiquidity` instructions in the same tx. Falls back to Jupiter route
   arb until the Kamino TypeScript SDK is integrated for instruction building.

All Solana arb transactions are submitted via **Jito bundles** for MEV protection.

---

## Deployment Steps

### 1. Deploy FlashArbReceiver.sol

```bash
# Install Foundry
curl -L https://foundry.paradigm.xyz | bash && foundryup

# Deploy to each chain
forge create contracts/FlashArbReceiver.sol:FlashArbReceiver \
  --rpc-url $ETH_RPC_URL \
  --private-key $WALLET_PRIVATE_KEY_PRIMARY \
  --constructor-args \
    "0xBA12222222228d8Ba445958a75a0704d566BF2C8" \
    "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2" \
    "0x1111111254EEB25477B68fb85Ed929f73A960582"

# Repeat for Base, Arbitrum, Polygon with their respective addresses
```

### 2. Set Environment Variables

Add to `.env`:

```env
# Flash Arb Receiver contract addresses (set after deployment)
FLASH_ARB_RECEIVER_ETHEREUM=0x...
FLASH_ARB_RECEIVER_BASE=0x...
FLASH_ARB_RECEIVER_ARBITRUM=0x...
FLASH_ARB_RECEIVER_POLYGON=0x...
FLASH_ARB_RECEIVER_BSC=0x...

# Flash Arb Configuration
FLASH_ARB_MIN_PROFIT_PCT=1.5        # Minimum net profit % to execute
FLASH_ARB_MAX_POSITION_USD=500000   # Hard cap on flash loan size
FLASH_ARB_LIQUIDITY_FRACTION=0.30   # Max % of pool liquidity to use
FLASH_ARB_SAFETY_MARGIN_PCT=0.10    # Safety haircut on minExpectedProfit
FLASH_ARB_PREFER_BALANCER=true      # Use Balancer (0% fee) over Aave (0.05%)

# 1inch API (for swap payload building)
ONEINCH_API_KEY=your_key_here
```

### 3. Verify Paper Mode First

```bash
# Ensure PAPER_TRADE=true in .env
# Run the bot and check output/arb_trades.csv for simulated flash arb results
# Look for flash_provider="paper_balancer" entries
```

### 4. Go Live

```bash
# Set PAPER_TRADE=false in .env
# The bot will now execute real flash loans when spread ≥ 1.5%
```

---

## Configuration Reference

| Setting | Default | Description |
|---|---|---|
| `FLASH_ARB_MIN_PROFIT_PCT` | `1.5` | Minimum net profit % required to execute |
| `FLASH_ARB_MAX_POSITION_USD` | `500,000` | Hard cap on flash loan size in USD |
| `FLASH_ARB_LIQUIDITY_FRACTION` | `0.30` | Max fraction of DEX liquidity to borrow |
| `FLASH_ARB_SAFETY_MARGIN_PCT` | `0.10` | Safety haircut applied to `minExpectedProfit` |
| `FLASH_ARB_PREFER_BALANCER` | `true` | Prefer Balancer (0% fee) over Aave (0.05%) |
| `ARB_MAX_GAS_TO_PROFIT_RATIO` | `0.50` | Reject if gas > 50% of expected profit |
| `ARB_SLIPPAGE_BPS` | `50` | Slippage tolerance (0.5%) for swap payloads |

---

## Safety Guarantees

| Guarantee | Mechanism |
|---|---|
| **Atomic revert** | On-chain `require(netProfit >= minExpectedProfit)` — entire tx reverts if not met |
| **Zero capital at risk** | Flash loan borrowed and repaid in same tx — wallet funds never leave |
| **Gas-profit gate** | Python-layer check: gas > 50% of profit → abort before tx |
| **Spread re-check** | Live price re-fetched before dispatching flash loan |
| **MEV protection** | Ethereum: Flashbots private mempool; L2s: direct RPC |
| **Min profit floor** | 1.5% net profit required (configurable) |
| **Max size cap** | Bounded by DEX liquidity (30%) and hard cap ($500k) |

---

## Files Changed

| File | Change |
|---|---|
| `core/arb_executor.py` | Full rewrite — flash loan integration, max-size calc, Balancer/Aave dispatch |
| `core/solana_flash_arb.py` | New — Jupiter route arb + Kamino flash borrow for Solana |
| `contracts/FlashArbReceiver.sol` | New — Solidity contract for atomic on-chain arb execution |
| `tests/test_flash_arb_executor.py` | New — 33 unit tests covering all gates and strategies |
| `docs/FLASH_ARB_ENGINE.md` | New — this document |
