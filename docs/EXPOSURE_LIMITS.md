# EXPOSURE LIMITS — Don't Put All Eggs in One Basket

## Portfolio Exposure Rules

### Per-Position Exposure
- **Maximum:** 2% of portfolio per position
- **Env var:** `MAX_POSITION_SIZE_PERCENT=2.0`
- **Why:** One rug pull should cost at most 2% of your portfolio

### Total Exposure
- **Maximum:** 20% of portfolio (10 positions × 2%)
- **Env var:** `MAX_CONCURRENT_POSITIONS=10`
- **Why:** 80% of portfolio stays in stable assets (ETH, SOL, stablecoins)

### Per-Chain Exposure
| Chain | Max Positions | Max Exposure |
|-------|-------------|-------------|
| Ethereum | 3 | 6% of portfolio |
| Base | 3 | 6% |
| Arbitrum | 2 | 4% |
| Solana | 3 | 6% |
| BSC | 2 | 4% |
| Polygon | 2 | 4% |

### Per-Category Exposure
| Token Category | Max Positions |
|---------------|-------------|
| Memecoins | 4 |
| DeFi tokens | 4 |
| Gaming/NFT tokens | 2 |
| AI tokens | 3 |

## Why Exposure Limits Matter
```
Scenario A (No limits):
  10 memecoins on BSC, each 5% of portfolio = 50% exposure on one chain
  BSC RPC goes down → Can't exit any positions
  Result: Potential 50% portfolio loss

Scenario B (With limits):
  3 memecoins on BSC, each 2% of portfolio = 6% exposure
  BSC RPC goes down → Only 6% at risk
  Other chains continue trading normally
  Result: Maximum 6% portfolio loss from chain event
```

## Monitoring
- Track total exposure per chain in real-time
- Alert when any chain exceeds its limit
- Block new entries on over-exposed chains
