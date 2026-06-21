# Hyperliquid API Rate Limits — Key Findings

> Source: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits

## IP-Based Limits (per IP)
- **1200 weight/minute** shared across all REST calls
- Exchange (signed) requests: weight `1 + floor(batch_length / 40)`
- Info requests: weight varies (2 for allMids/l2Book/clearinghouseState, 20 for most others, 60 for userRole)
- WebSocket: max 10 connections, 30 new/min, 1000 subscriptions

## Address-Based Limits (per wallet — THE CRITICAL ONE)
- **1 request per $1 USDC traded cumulatively since address inception**
- **Initial buffer: 10,000 requests** at address creation
- **Does NOT decay over time** — cumulative since inception
- **Does NOT apply to info/read requests** — only signed "actions" (order, cancel, modify)
- When rate limited: **1 request every 10 seconds** allowed
- **Cancels get 2x the limit**: `min(limit + 100000, limit * 2)` — cancels always work!
- **Sub-accounts are treated as separate users** (potential escape hatch)

## Formula
```
cap = 10,000 + cumulative_taker_volume_in_USDC
requests_used = count of all signed actions (orders, cancels, modifications)
deficit = requests_used - cap
```

## Batched Requests
- Count as **1 IP request** but **N address-based requests**
- So batching helps IP limits but NOT address limits

## Implications for Our Bot
1. **Trailing stop spam was catastrophic** — each cancel+replace = 2 requests, at 8s interval = 15/min = 900/hour = 21,600/day
2. **With only ~$2,300 volume**, cap was only 12,300. The 30s poll + 0.15% threshold fix reduces this massively
3. **Info API calls are FREE** — allMids, user_state, open_orders don't count toward address limit
4. **WebSocket is recommended** for price feeds — would eliminate REST polling entirely
5. **Sub-accounts** could be used as a reset if rate limit gets stuck again

## Recovery Strategy
- Close/reopen positions as IOC taker orders to generate volume
- Each $1 of taker volume adds $1 to the cap
- Cancels still work even when rate limited (separate higher limit)
