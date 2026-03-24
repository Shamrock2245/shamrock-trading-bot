# 🔵 Base Chain USDC Deployment Strategy

> **Objective**: Deploy the $1,321 USDC sitting in the Primary Wallet (`0x3eb320fad3f51fe4f2a4531f911ef56694346eef`) on Base chain into high-conviction gem entries and snipes.

---

## 1. Capital Allocation

The Primary Wallet currently holds **$1,321 USDC** and **0.038 ETH** (~$75) for gas on Base.

We will use the USDC as the primary trading capital, bypassing the need to swap ETH -> Token and saving on gas/slippage.

### Position Sizing Tiers
- **God Signal (Score ≥ 85.0)**: $150 USDC per trade (High conviction, heavy momentum)
- **Standard Snipe (Score 75.0 - 84.9)**: $50 USDC per trade (Good setup, standard risk)
- **Below 75.0**: NO TRADE. Hold USDC.

*This sizing allows for ~8-26 concurrent positions depending on signal quality, providing good diversification while keeping enough powder dry for exceptional setups.*

---

## 2. Execution Routing

Base chain liquidity is fragmented. The bot will route USDC trades through the optimal DEX based on where the token's primary liquidity pool lives:

1. **Aerodrome (`0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43`)**: Primary router for most new Base launches and native protocols.
2. **Uniswap V3 (`0x2626664c2603336E57B271c5C0b26F421741e481`)**: Secondary router for established tokens or cross-chain bridged assets.

### Slippage Tolerance
- **God Signals**: 5.0% (500 bps) — Prioritize execution speed and guaranteed entry on fast-moving tokens.
- **Standard Snipes**: 3.0% (300 bps) — Standard protection against MEV and front-running.

---

## 3. The Deployment Pipeline

The deployment process runs fully automated via `scripts/base_usdc_deployer.py`:

1. **Scan**: `live_scan_base_avax.py` runs, pulling data from Moralis Money, DexScreener, and GeckoTerminal.
2. **Score**: Tokens are scored (0-100) based on TA confluence, volume spikes, and smart money flow.
3. **Plan**: `base_usdc_deployer.py` reads the scan results and the $1,321 USDC balance.
4. **Allocate**: It generates `reports/base_deploy_plan.json`, assigning $50-$150 USDC chunks to tokens scoring ≥75.0.
5. **Execute**: The main bot loop reads the plan and fires the USDC -> Token swaps via the appropriate router.

---

## 4. Exit Strategy (House Money)

Once the USDC is deployed into a token, the standard `OFFENSIVE_PLAYBOOK.md` exit rules apply:

- **TP1 (2x / +100%)**: Sell 40% to recoup initial USDC + small profit.
- **TP2 (5x / +400%)**: Sell 35% more.
- **TP3 (10x / +900%)**: Sell 20%, leave 5% moonbag.
- **Stop Loss**: Hard -25% cut to protect the USDC capital.
- **Time Stop**: If no +50% move within 48 hours, exit and free up the USDC for a better setup.
