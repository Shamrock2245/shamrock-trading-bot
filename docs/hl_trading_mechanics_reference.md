# Hyperliquid Trading Mechanics Reference

This document compiles the critical rules, mechanics, and thresholds from the official Hyperliquid documentation to ensure our trading bot is perfectly tuned and optimized.

## 1. Fees & Rebates
Hyperliquid fees are based on a 14-day rolling volume. Perps and spot volume are combined, with spot counting 2x.
*   **Base Tier (Tier 0, <$5M vol):** 0.045% Taker fee, 0.015% Maker rebate.
*   **Maker Rebates:** Paid continuously on each trade directly to the trading wallet.
*   **Optimization:** When possible, use `Post Only (ALO)` limit orders for entry/exit to capture the 0.015% maker rebate instead of paying the 0.045% taker fee. This creates a massive 0.060% spread difference per trade.

## 2. Order Types & Slippage
*   **TP/SL Slippage:** TP/SL market orders have a hardcoded slippage tolerance of **10%**.
*   **Limit TP/SL:** You can set a limit price on a TP/SL order. The more aggressive the limit, the higher chance of filling but higher potential slippage.
*   **OCO (One-Cancels-Other) Danger:** Child TP/SL orders tied to a parent order are **only** placed if the parent fully fills, OR if it partially fills and is canceled due to insufficient margin. If we manually cancel a partially filled parent, the TP/SL orders are canceled too.
*   **Optimization:** We currently place TP/SL *after* confirming our entry is filled. This is the safest pattern to avoid OCO partial-fill edge cases.

## 3. Margining & Leverage
*   **Cross Margin (Default):** Maximizes capital efficiency. Unrealized PnL is automatically available as initial margin for new positions.
*   **Initial Margin:** `position_size * mark_price / leverage`.
*   **Maintenance Margin:** Half of the initial margin at **max** leverage (varies from 1.25% to 16.7% depending on the asset).
*   **Optimization:** Since we use 2x-3x leverage, our maintenance margin is far below our entry price, giving a wide buffer before liquidation. However, we must ensure our Stop Losses trigger *before* the maintenance margin threshold.

## 4. Liquidations
*   **Trigger:** Triggered using the **Mark Price** (not the instantaneous order book price).
*   **Partial Liquidations:** For positions >$100k USDC, only 20% is liquidated via a market order initially.
*   **Backstop:** If equity drops below 2/3 of maintenance margin without successful book liquidation, the liquidator vault takes over (and you lose the maintenance margin buffer).
*   **Optimization:** Always use strict Stop Losses to exit positions gracefully before the Mark Price nears the liquidation threshold.

## 5. Funding Rates
*   **Baseline:** 0.01% every 8 hours (0.00125% hourly, 11.6% APR) paid from Longs to Shorts.
*   **Premium:** Added to the baseline based on Mark vs Oracle price.
*   **Payout:** Paid **hourly**.
*   **Cap:** Capped at 4% per hour (much higher than CEXs).
*   **Optimization:** The bot should factor in hourly funding costs if holding positions for multiple days, especially on highly skewed pairs.

## 6. Connectivity (REST vs WebSocket)
*   **WebSockets:** Recommended for real-time data (`wss://api.hyperliquid.xyz/ws`). Disconnects must be handled gracefully.
*   **REST Info:** Free from the address-based cumulative rate limit, but subject to the IP limit (1200 weight/min).
*   **Optimization:** Our current 30s REST polling for trailing stops is well within the IP limits and entirely bypasses the address limit. Moving to WebSockets would provide lower latency but requires handling connection drops. The current 30s + 0.15% threshold REST implementation is highly robust for our swing-trading timeframe.

## Summary of Bot Optimizations Achieved
1.  **Rate Limit Safety:** We halted the rapid cancel/replace loop on trailing stops. Modifying an order costs 2 requests against the lifetime address limit. Our new logic batches these updates and only fires when price moves >0.15%, keeping our request footprint minimal.
2.  **Order Placement Strategy:** We use independent market/limit orders followed by explicit TP/SL placement, avoiding the complex pitfalls of OCO parent/child orders.
3.  **Liquidation Avoidance:** Our tight Stop Losses (-5% or Fib-based) guarantee we exit long before Hyperliquid's maintenance margin liquidations can trigger.
