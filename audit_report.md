# Shamrock Trading Bot: Deep Codebase Audit Report

**Date:** June 2026  
**Auditor:** Senior Staff Software Engineer (Manus)  

This report outlines the findings from a deep "Code Gap & Hardening Audit" conducted on the recently modified files of the Shamrock Trading Bot. The audit focused on identifying silent failures, race conditions, and edge cases, particularly within the newly integrated Moralis streams, ML auto-tuner pipeline, and Hyperliquid execution logic.

## 1. Audit Findings & Identified Gaps

### 1.1. Data Pipeline Integrity: ML Auto-Tuner `signal_scores` Dropped
**Vulnerability:** The ML auto-tuner relies on `signal_scores` injected into trade records to optimize weights dynamically. While the standard scanner pipeline injects these correctly, the `mempool_alpha_sniper.py` execution path (driven by Moralis alpha-wallet webhooks) was hardcoding `signal_scores={}` when registering new positions. 
**Impact:** Positions opened via the alpha sniper path lost all attribution features before reaching the `position_monitor`. Consequently, downstream SELL records lacked these features, causing the auto-tuner to silently miss valuable training data from live, fast-execution trades.
**Status:** **Patched.** 

### 1.2. API Timeouts & Rate Limits: Moralis Stream Lifecycle Mutations Unprotected
**Vulnerability:** The `data/http_session.py` wrapper provides connection pooling, explicit timeouts, and a retry policy for robustness. However, the `allowed_methods` for the `Retry` adapter only included `["GET", "POST"]`. The Moralis Streams manager relies on `PUT` (create), `PATCH` (replace addresses), and `DELETE` (cleanup) operations.
**Impact:** Transient 5xx or 429 rate-limit errors from the Moralis API during stream creation or address synchronization would fail immediately without retries. This could lead to silent state drift where the bot believes a stream is active or updated, but Moralis rejected the mutation.
**Status:** **Patched.** 

### 1.3. State Leaks & Ghost Data: Active Position Syncing Swallows Exceptions
**Vulnerability:** In `core/position_monitor.py`, the `save_positions` function attempts to synchronize active positions with Moralis Streams for real-time contract security monitoring (e.g., detecting honeypot contract changes). If this sync failed, the exception was caught and logged at the `debug` level.
**Impact:** If the Moralis sync fails (e.g., due to the un-retried network errors mentioned above), the bot silently loses contract-security coverage for those open positions. The user is unaware that the security net is down because the error is buried in debug logs.
**Status:** **Patched.** (Elevated log level to `warning` to surface failures; combined with the HTTP session patch, this path is now much more resilient).

## 2. Patches Applied

The following targeted patches were applied directly to the codebase to resolve the identified gaps, adhering strictly to the project's guardrails:

1.  **`core/mempool_alpha_sniper.py`:** Modified `_register` to correctly pass `signal_scores=getattr(candidate, "signal_scores", {})` instead of an empty dictionary when calling `register_position`.
2.  **`data/http_session.py`:** Updated the `Retry` configuration in `get_session` to include `PUT`, `PATCH`, and `DELETE` in the `allowed_methods` list, ensuring Moralis stream lifecycle operations benefit from exponential backoff.
3.  **`core/position_monitor.py`:** Changed the exception handler in `save_positions` for Moralis active position syncing from `logger.debug` to `logger.warning` to ensure visibility of security monitoring failures.

## 3. Operational Recommendations

*   **Monitor ML Training:** Verify that the auto-tuner begins incorporating features from alpha sniper trades now that the `signal_scores` are properly persisted.
*   **Log Review:** Keep an eye on the logs for "Failed to sync active positions to Moralis Streams" warnings. If they occur frequently despite the new retry logic, it may indicate a deeper API quota or connectivity issue that needs addressing.
*   **Hyperliquid Sweeper:** The autonomous profit sweeper logic in `hl_perps_scanner.py` looks robust, triggering when withdrawable balance exceeds `$25,000 + Sweep`. Monitor its first live execution closely to ensure the cross-chain bridge logic executes flawlessly.
