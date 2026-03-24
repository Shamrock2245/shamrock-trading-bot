# 🏔️ Avalanche (AVAX) Portfolio Rebalance Strategy

This document outlines the specific strategy for managing and rebalancing **Wallet B** (`0x0835eb8447f3ac90351951bb5d22e77afd9b81c0`) on the Avalanche C-Chain.

## 1. Current State Assessment

As of the latest scan, Wallet B holds approximately **$975** in total capital on Avalanche:
- **Native AVAX:** ~60 AVAX ($570)
- **Stablecoins:** ~376 USDC ($376)
- **Altcoins/Memecoins:** ~$29 total value spread across multiple tokens (BEAM, KIMBO, CATWIF, etc.)

### The Problem
The wallet has accumulated "dust" and underperforming assets that are tying up capital, while a significant portion of USDC is sitting idle instead of being deployed into high-scoring gems.

## 2. The Rebalance Mandate

The goal of the rebalance is to **consolidate capital** into highly liquid, deployable assets (AVAX and USDC) and aggressively deploy that capital into top-tier opportunities.

### Action 1: Liquidate Underperformers
We will ruthlessly cut positions that are not performing or lack sufficient liquidity to justify holding.

- **Target:** `BEAM` (~$22 value).
- **Reason:** Low liquidity ($20k) and negative 24h momentum. It is dead capital.
- **Action:** Market sell `BEAM` for native `AVAX` via Trader Joe V2.

### Action 2: Ignore the Dust
Tokens with negligible value (<$5) or zero liquidity are not worth the gas fees required to sell them.

- **Targets:** `CATWIF`, `SECOND`, `MILK`, `GORC`, `BKG`, `LFG`, `MINIKIMBO`.
- **Action:** Do nothing. Leave them in the wallet. Attempting to sell them will result in a net loss due to gas costs.

### Action 3: Monitor Survivors
Tokens that show slight positive momentum but are too small to significantly impact the portfolio will be held and monitored.

- **Target:** `KIMBO` (~$3 value).
- **Reason:** Positive 24h momentum (+2.7%) and decent liquidity ($62k).
- **Action:** Hold and monitor. If it pumps significantly, liquidate.

## 3. Capital Deployment Strategy

Once the portfolio is consolidated, the bot will shift to an aggressive deployment stance.

### The USDC Deployer
The ~376 USDC sitting in Wallet B is our primary ammunition for new gem snipes on Avalanche.

1. **Primary Route:** The bot will prioritize using USDC for buy orders on Avalanche DEXs (Trader Joe V2, Pharaoh).
2. **Sizing:** Standard snipes will utilize ~2% of total portfolio value (approx. $20 per trade). High-conviction snipes will utilize ~3.5% (approx. $35 per trade).
3. **Execution:** The bot will automatically route USDC through the most efficient path to acquire the target gem, minimizing slippage.

### The AVAX Reserve
The ~60 AVAX serves two purposes:
1. **Gas Reserve:** Ensures the bot always has enough native token to execute trades quickly, especially during network congestion.
2. **Secondary Ammunition:** If the USDC balance is depleted, the bot will seamlessly switch to using native AVAX for gem snipes.

## 4. Automated Rebalance Workflow

The bot will execute this rebalance strategy automatically upon startup:

1. **Scan:** Read current balances via public RPC.
2. **Score:** Evaluate each holding based on current price, liquidity, and 24h volume.
3. **Prune:** Execute market sells for any token flagged as `❌ LIQUIDATE`.
4. **Deploy:** Begin scanning for new gems (Score ≥ 75) and deploy the consolidated USDC/AVAX capital.

This ensures Wallet B is always lean, mean, and ready to strike.
