# ORDER EXECUTION — Speed is Money

## The Speed Edge
In crypto gem sniping, **the first buyer wins**. A token that's 5 minutes old is INFINITELY more profitable than the same token at 60 minutes old. Every second of execution delay costs real money.

## Execution Flow (Optimized for Speed)
```
Signal confirmed (≤1s)
  → Risk check (≤50ms — in-memory)
  → Safety gate (≤2s — parallel API calls)
  → Size calculation (≤10ms — arithmetic)
  → Route selection (≤100ms — chain lookup)
  → Submit tx (≤3s — depends on chain)
  → Confirm (chain dependent)
  → Log + notify (async, non-blocking)

Total target: < 5 seconds from signal to submitted tx
```

## Express Lane Execution (Score ≥ 80)
- **Skip TA pipeline** — saves 3-5 seconds
- **Parallel safety checks** — GoPlus + Honeypot + TokenSniffer simultaneously
- **Pre-built tx templates** — reduce serialization time
- Goal: **Signal to tx in under 3 seconds**

## Chain-Specific Execution

### Solana (🥇 Priority — Cheapest, Fastest)
| Setting | Value |
|---------|-------|
| DEX | Jupiter Aggregator |
| Confirmation | ~400ms |
| Gas | ~$0.001 |
| Priority fee | Auto (moderate) |
| Min position | $10 |
| Executor | `core/solana_executor.py` |

### Base (🥈 Secondary — Great Balance)
| Setting | Value |
|---------|-------|
| DEX | 1inch Aggregator |
| Confirmation | ~2 seconds |
| Gas | ~$0.01 |
| Min position | $25 |
| Executor | `core/executor.py` |

### Arbitrum / BSC / Polygon
| Setting | Value |
|---------|-------|
| DEX | 1inch Aggregator |
| Confirmation | 2-5 seconds |
| Gas | $0.05-0.30 |
| Min position | $25 |
| Executor | `core/executor.py` |

### Ethereum (⚠️ Phase 2+ Only)
| Setting | Value |
|---------|-------|
| DEX | CoW Protocol → 1inch fallback |
| Confirmation | ~15 seconds |
| Gas | $5-50 |
| MEV protection | ✅ Flashbots + CoW |
| Min position | $500 |
| Executor | `core/executor.py` |

## Token Approval (EVM Only)
- Approve **exact trade amount** only — NEVER `uint256.max`
- Check existing allowance first — skip if sufficient
- Approval TX adds ~$0.50-2.00 gas on L2s, $3-15 on Ethereum

## Slippage Settings (Phase 1 — Optimized for Small Caps)
| Liquidity Range | Buy Slippage | Sell Slippage (normal) | Sell Slippage (stop-loss) |
|----------------|-------------|----------------------|--------------------------|
| > $500K | 1.0% | 1.0% | 2.0% |
| $200K–$500K | 1.5% | 1.5% | 2.5% |
| $100K–$200K | 2.0% | 2.0% | 3.0% |
| $50K–$100K | 2.5% | 2.5% | 3.5% |
| $15K–$50K | 3.0% | 3.0% | 5.0% |
| < $15K | **DO NOT TRADE** | — | — |

## Failure Handling (Don't Lose Opportunities)
| Failure | Action | Resume |
|---------|--------|--------|
| TX reverted | Log, skip, move to next candidate | Immediately |
| Slippage exceeded | Log, retry with +0.5% wider slippage ONCE | Immediately |
| Timeout (120s) | Check tx status on explorer | After resolution |
| Insufficient balance | Alert, pause that chain | After deposit |
| RPC error | Retry with backup RPC (max 3) | Immediately |
| Rate limited | Back off 5s, continue other chains | After backoff |

## Gas Optimization
- **Solana/Base:** Gas is negligible — execute without delay
- **Ethereum:** Best gas windows: 2-6 AM UTC (weekdays), all day Sunday
- **Bundle multiple exits together** when possible (save gas on Ethereum)
- **Never pay > 2% of position size in gas** — kills the edge
