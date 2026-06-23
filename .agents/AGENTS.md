# Shamrock Trading Bot - Agent Rules

## Network I/O Guardrails
- **Rule**: Every `requests.Session` or `requests.get` call MUST have an explicit `timeout=` parameter (e.g. 15.0). Un-timeouted network calls to external APIs (like Moralis) will silently block connection pools when the API drops packets, permanently freezing the bot's main loop and abandoning active trades on exchanges.
- **Enforcement**: Any `get_session()` wrappers must override the `request()` method to forcefully inject a default timeout. Exceptions must be caught to prevent crashes.

## Trade Execution & Typo Guardrails
- **Rule**: Always verify dataclass property names (like `sl_order_id` vs `sl_oid`) when writing exception-heavy logic like `close_position()`. An `AttributeError` inside a generic try-except will silently fail the trade exit.
- **Enforcement**: When closing a trade, verify you are using the correct field names from `HLPosition`. Typo in a getattr/field name (e.g. `pos.sl_oid` instead of `pos.sl_order_id`) inside a try block within `close_position()` causes the catch-all `except Exception` to silently abort the close attempt, leaving the trade orphaned.

## Hyperliquid API Wallet Troubleshooting
- **Rule**: When encountering the error `"User or API Wallet <address> does not exist."` while executing Hyperliquid trades, it means the private key provided (`HYPERLIQUID_PRIVATE_KEY`) corresponds to a wallet that has not been authorized as an API Wallet for the main trading account (`HYPERLIQUID_WALLET_ADDRESS`).
- **Enforcement**: Hyperliquid requires API wallets to be explicitly approved via the UI settings or an L1 transaction. To fix this error, you must either:
  1. Instruct the user to provide the main wallet's private key.
  2. Instruct the user to manually approve the unauthorized API wallet address in the Hyperliquid UI (Settings -> API -> Enable API). 
  Do not attempt to debug Python SDK initialization parameters before verifying API wallet authorization status.
