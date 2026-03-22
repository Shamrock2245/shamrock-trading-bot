# ORDER EXECUTION — How Trades Get Placed

## Execution Flow
```
Signal confirmed → Risk check → Safety gate → Size calculation → Route selection → Submit tx → Confirm → Log
```

## Step-by-Step

### 1. Pre-Execution Risk Check
- Portfolio allocation within limits?
- Daily loss limit not hit?
- Gas price acceptable (< 50 gwei)?
- Not at max concurrent positions?

### 2. Route Selection
| Chain | Router | MEV Protection |
|-------|--------|---------------|
| Ethereum | CoW Protocol → 1inch fallback | ✅ Flashbots |
| Base/ARB/POLY/BSC | 1inch Aggregator | ❌ |
| Solana | Jupiter Aggregator | ❌ |

### 3. Token Approval (EVM Only)
- Approve **exact trade amount** only
- NEVER approve `uint256.max` (unlimited)
- Check existing allowance first — skip if sufficient

### 4. Trade Submission
- Build transaction with calculated slippage
- Submit via chain-appropriate method
- Wait for confirmation (timeout: 120 seconds)

### 5. Confirmation & Logging
- Verify transaction receipt
- Log: entry price, amount, gas paid, tx hash
- Create position record in `output/positions.json`
- Send Slack/Telegram notification

## Slippage Settings
| Liquidity Range | Max Slippage |
|----------------|-------------|
| > $500K | 1.0% |
| $100K–$500K | 2.0% |
| $25K–$100K | 3.0% |
| < $25K | **Do not trade** |

## Gas Optimization
- **Ethereum:** Wait for gas < 50 gwei, prefer off-peak hours
- **Base/Arbitrum:** Gas is negligible, execute immediately
- **Solana:** Priority fee auto-calculated by Jupiter
- **BSC/Polygon:** Gas is negligible, execute immediately

## Failure Handling
| Failure | Action |
|---------|--------|
| TX reverted | Log error, refund gas, do NOT retry automatically |
| Slippage exceeded | Reject trade, log, try again with wider slippage on next cycle |
| Timeout (120s) | Check tx status, if pending → wait; if dropped → log and move on |
| Insufficient balance | Alert immediately, pause trading |
| RPC error | Retry with backup RPC (max 3 attempts) |
