# ORDER EXECUTION — Speed is Money

## The Speed Edge
In crypto gem sniping, **the first buyer wins**. A token that's 5 minutes old is INFINITELY more profitable than the same token at 60 minutes old. Every second of execution delay costs real money.

## Execution Flow (Optimized for Speed)
```
Signal confirmed (≤1s)
  → Risk check (≤50ms — in-memory)
  → Safety gate (≤2s — parallel API calls, cached 5min)
  → Offensive sizing (≤10ms — multiplier stack)
  → Route selection (≤100ms — chain + wallet profile lookup)
  → Submit tx (≤3s — depends on chain)
  → Confirm (chain dependent)
  → Log + notify (async, non-blocking)

Total target: < 5 seconds from signal to submitted tx
```

## Express Lane Execution (Score ≥ 82 Conservative / ≥ 90 Nuclear)
- **Skip TA pipeline** — saves 3-5 seconds
- **Parallel safety checks** — GoPlus + Honeypot + TokenSniffer simultaneously
- Goal: **Signal to tx in under 3 seconds**

### God Signal Execution (Score ≥ 85)
- Everything Express Lane does PLUS:
- **1.5x gas bribe** for next-block inclusion (MEV protection)
- **Express Overdrive sizing** — 1.5x–2.0x position
- **Wider slippage** — +100bps tolerance to guarantee entry

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

### Avalanche (🥉 C-Chain — Fast & Growing)
| Setting | Value |
|---------|-------|
| DEX | Trader Joe V2 / 1inch fallback |
| Confirmation | ~2 seconds |
| Gas | ~$0.03 |
| Min position | $25 |
| PoA middleware | Enabled for C-Chain |
| Executor | `core/executor.py` |

### BSC / Arbitrum / Polygon
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

## Dual-Wallet Execution Routing

Both wallets can fire on the same token in the same cycle:

| Score Range | Primary (Conservative) | Wallet B (Nuclear) |
|-------------|----------------------|-------------------|
| ≥ 90 | ✅ 5% position | ✅ 60% position (Express Overdrive) |
| 85–89 | ✅ 5% position | ✅ 60% position (God Signal) |
| 82–84 | ✅ 5% position | ✅ 60% position |
| 65–81 | ✅ Standard | ❌ Below nuclear minimum |
| 45–64 | ✅ TA-confirmed | ❌ Below nuclear minimum |

## Token Approval (EVM Only)
- Approve **exact trade amount** only — NEVER `uint256.max`
- Check existing allowance first — skip if sufficient
- Approval TX adds ~$0.50-2.00 gas on L2s, $3-15 on Ethereum

## Slippage Settings
| Profile | Buy Slippage | Sell Slippage | Stop-Loss Slippage |
|---------|-------------|--------------|-------------------|
| Conservative | 5% | 5% | 8% |
| Nuclear | **8%** | **8%** | **12%** |
| Express Overdrive | +100bps on top | — | — |

## Failure Handling (Don't Lose Opportunities)
| Failure | Action | Resume |
|---------|--------|--------|
| TX reverted | Log, skip, move to next candidate | Immediately |
| Slippage exceeded | Log, retry with +0.5% wider slippage ONCE | Immediately |
| Timeout (120s) | Check tx status on explorer | After resolution |
| Insufficient balance | Alert, pause that chain | After deposit |
| RPC error | Retry with backup RPC (max 3) | Immediately |
| Rate limited | Back off 5s, continue other chains | After backoff |
| Deduplication hit | Skip (same token within cooldown) | Next cycle |

## Gas Optimization
- **Solana/Base/AVAX:** Gas is negligible — execute without delay
- **Ethereum:** Best gas windows: 2-6 AM UTC (weekdays), all day Sunday
- **God Signal (≥85):** Pay gas premium — next-block inclusion is worth it
- **Never pay > 2% of position size in gas** — kills the edge
