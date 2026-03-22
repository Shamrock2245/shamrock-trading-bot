# EXCHANGES — DEX Routing & Execution

## Routing Priority by Chain

| Chain | Primary DEX | Fallback | MEV Protection |
|-------|------------|----------|----------------|
| **Ethereum** | CoW Protocol | 1inch | ✅ Flashbots + CoW batch auctions |
| **Base** | 1inch | Direct Uniswap V3 | ❌ (L2, less MEV) |
| **Arbitrum** | 1inch | Camelot | ❌ (L2, less MEV) |
| **Polygon** | 1inch | QuickSwap | ❌ |
| **BSC** | 1inch | PancakeSwap V3 | ❌ |
| **Solana** | Jupiter | Raydium | ❌ (native MEV protection via Jito bundles) |

## Why CoW Protocol for Ethereum
- Batch auction model = zero MEV extraction
- Gasless signing (intent-based)
- Solvers compete for best execution
- **Reference:** `core/executor.py`

## Why Jupiter for Solana
- Best route aggregation across all Solana DEXs
- Sub-second confirmation
- Automatic split routing for large orders
- Priority fee management
- **Reference:** `core/solana_executor.py`

## Why 1inch for Everything Else
- Aggregates 300+ DEX pools per chain
- Split routing for best prices
- Partial fill support
- **Reference:** `core/executor.py` (1inch fallback path)

## Execution Rules
1. **Always use aggregators** — never trade against a single pool
2. **Set slippage tolerance to 1-3%** — tighter on large pools, looser on small
3. **Approve exact amounts only** — never `type(uint256).max`
4. **Check estimated output before submitting** — reject if slippage > expected
5. **Use private RPCs on Ethereum** — public RPCs leak your pending txns to MEV bots
