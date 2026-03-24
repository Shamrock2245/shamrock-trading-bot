# ⚔️ Shamrock Trading Bot: Offensive Playbook

This document defines the **aggressive, profit-seeking logic** of the Shamrock Trading Bot. While the defensive guardrails (`GUARDRAILS.md`, `RISK_MANAGEMENT.md`) protect capital, this playbook dictates how we *make money*.

The bot operates on a **Confluence Entry System**, meaning it requires multiple independent signals to align before deploying capital. When confluence is achieved, the bot strikes aggressively, utilizing MEV protection to ensure optimal execution.

---

## 1. The Alpha Edge: Data Confluence

We do not rely on a single data source. Our edge comes from cross-referencing on-chain realities with market momentum.

### Primary Data Sources
1. **Moralis Money (The Spine):** Provides deep on-chain analytics. We look for tokens with high "Experienced Net Buyers" (smart money accumulation) and strong "On-Chain Strength" scores.
2. **DexScreener (The Pulse):** Provides real-time volume spikes, liquidity depth, and community momentum (Boosts).
3. **GeckoTerminal (The Backup):** Validates trending pools and provides fallback OHLCV data.
4. **GoPlus Security (The Shield):** Instant honeypot and malicious contract detection.

### The "God Signal" (Score ≥ 85)
A token achieves the "God Signal" when:
- **Smart Money is Buying:** Moralis shows >10 experienced buyers in the last hour.
- **Volume is Exploding:** DexScreener shows a 1h volume spike >5x the 24h average.
- **Liquidity is Solid:** >$100k in the pool (prevents massive slippage).
- **Contract is Clean:** GoPlus score >90 (no honeypot, taxes <5%, renounced ownership).
- **Freshness:** Token is <72 hours old (maximum upside potential).

*Action:* When a God Signal is detected, the bot enters **Express Overdrive**, increasing position size by 1.5x and executing immediately via private mempool.

---

## 2. Entry Triggers & TA Confluence

The bot uses a weighted scoring system (0-100). A score of **≥75 triggers a standard BUY**.

### Technical Analysis (TA) Weights
| Signal | Weight | Bullish Trigger |
| :--- | :--- | :--- |
| **Volume Spike** | 25% | 1h volume > 3x the 24h average hourly volume. |
| **Buy Pressure** | 20% | 1h Buy/Sell ratio > 65%. |
| **Momentum (1h)** | 20% | Price up >10% in the last hour. |
| **Trend (6h)** | 15% | Price up >15% over 6 hours (sustained move). |
| **Liquidity** | 10% | Pool > $100,000 USD. |
| **Age** | 5% | < 24 hours old. |
| **FDV Ratio** | 5% | Market Cap / FDV > 0.60 (low inflation risk). |

### Moralis Enrichment Bonus
Tokens receive up to **+15 bonus points** for strong on-chain metrics:
- +8 points for >10 experienced buyers (1h).
- +5 points for positive net buyers.
- +5 points for On-Chain Strength > 70.

---

## 3. Position Sizing (The Attack)

Capital deployment is dynamic, based on the conviction score and the specific wallet's role.

### Wallet B (The Sniper - AVAX Focus)
- **Base Capital:** ~60 AVAX + ~$376 USDC.
- **Standard Snipe (Score 75-84):** Deploy 2.0% of total wallet capital.
- **High Conviction (Score 85+):** Deploy 3.5% of total wallet capital.
- **Asset Preference:** Deploy USDC first. If USDC is depleted, use native AVAX.

### Sizing Rules
1. **Never all-in:** Maximum exposure to a single asset is capped at 5% of the portfolio.
2. **Gas Reserve:** Always leave at least 0.5 AVAX (or equivalent native token) for gas.
3. **Dynamic Scaling:** If the bot is on a winning streak (3+ profitable trades), base position size increases by 10%. On a losing streak, it decreases by 20%.

---

## 4. Execution & MEV Protection

Getting the signal is only half the battle; executing without getting front-run is the other half.

### Routing Strategy
- **Avalanche:** Route through **Trader Joe V2.1** or **Pharaoh Exchange**.
- **Base:** Route through **Aerodrome** or **Uniswap V3**.
- **Ethereum:** Route through **CoW Protocol** (MEV protected by default) or **1inch**.

### Anti-MEV Tactics
1. **Private RPCs:** On Ethereum, all transactions are routed through Flashbots or MEV-Blocker RPCs. This hides the transaction from the public mempool, preventing sandwich attacks.
2. **Slippage Control:** 
   - Standard trades: 1.5% slippage tolerance.
   - High-volatility snipes: 3.0% slippage tolerance.
   - *Never* use "auto-slippage" on DEX UIs, as this invites MEV bots.
3. **Gas Bribes:** For God Signals (Score 85+), the bot automatically adds a 15% premium to the base fee to ensure next-block inclusion.

---

## 5. Exit Rules (Taking Profits)

We do not marry our bags. We are mercenaries.

### The "House Money" Strategy
1. **+100% (2x):** Sell 50% of the position immediately. The remaining 50% is now "house money."
2. **+200% (3x):** Sell another 25% of the original position.
3. **Trailing Stop:** For the remaining 25%, activate a 15% trailing stop-loss. Let the runner run, but cut it the moment momentum breaks.

### The "Cut the Bleeding" Strategy (Stop Loss)
1. **Hard Stop:** -25% from entry price. No exceptions, no hoping for a bounce. Sell immediately.
2. **Time-Based Stop:** If the token has not moved >+10% within 12 hours of entry, liquidate the position. Dead capital is wasted capital.
3. **Liquidity Drain:** If pool liquidity drops by >30% in a 1h period, trigger an emergency market sell. This often precedes a rug pull.

---

## 6. Continuous Rebalancing

The bot actively monitors the portfolio and prunes weak assets to free up capital for new opportunities.

- **Dust Sweeping:** Tokens worth <$5 with low liquidity are ignored (not worth the gas to sell).
- **Underperformer Liquidation:** Tokens down >30% with <$20k liquidity are market-sold back to the native asset (e.g., AVAX) to be redeployed.
- **USDC Deployment:** Idle stablecoins are actively pushed into top-scoring gems. Cash is trash; deployed capital is king.
