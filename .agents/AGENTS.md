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
# Agents

This project uses the **Reflex agent skills** — up-to-date knowledge for building full-stack Python web apps with [Reflex](https://reflex.dev). Install them first, then use them as described below.

## Installing the Skills

Before working on this project, make sure the Reflex skills are available to you.

### Claude Code

If the skills are not already available, install them yourself by running these shell commands:

```bash
claude plugin marketplace add reflex-dev/agent-skills
claude plugin install reflex@reflex-agent-skills
```

Newly installed plugins load on the next session. After installing, tell the user to restart the session so the skills auto-load; until then, read the skill files directly from `~/.claude/plugins/` when you need them.

### Other agents (Cursor, OpenCode, Codex, Pi)

```
npx skills add reflex-dev/agent-skills
```

Or clone https://github.com/reflex-dev/agent-skills and copy the `skills/` folders into your agent's skill directory (see the repo README for paths).

### Verifying

Before writing or editing any Reflex code, confirm these three skills are available: `reflex-docs`, `setup-python-env`, and `reflex-process-management`. If they are not, STOP and run the install step above — do not proceed without them.

## Using the Skills

### Reflex documentation

For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs.

### Initializing a new Reflex project

When starting a new Reflex project or setting up a development environment, you **must** follow the **setup-python-env** skill before doing anything else.

Do not skip any steps. Do not assume a virtual environment or Reflex is already available — always verify first by following the skill's instructions in order.

After the environment is ready and Reflex is installed, run:

```bash
reflex init
```

Then proceed with the user's request.

### Managing a Reflex process

When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps.

## Moralis CU Budget Protection
- **Rule**: Never attempt to build manual API delays or sleep loops to protect the Moralis CU budget. The bot has a globally enforced `MoralisCUBudgetManager` (`core/moralis_cu_budget.py`).
- **Enforcement**: The `@track_cu` decorator automatically intercepts expensive API calls when the bot approaches its monthly budget (e.g., dropping into `CONSERVATIVE` or `EMERGENCY` modes). It is safe to run aggressively fast scan intervals (e.g., 15 seconds) because this manager acts as an absolute failsafe to prevent budget overages.

## Machine Learning Auto-Tuner Guardrails
- **Rule**: The XGBoost auto-tuner (`ml/optuna_optimizer.py` and `ml/weight_optimizer.py`) requires a minimum of 30 finalized trades in `output/trades.json` containing complete `signal_scores` arrays. If trades are not being logged with `signal_scores`, the ML pipeline will silently skip optimization and fallback to static weights.
- **Enforcement**: When modifying the `scanner` pipeline (e.g., `gem_scanner.py`), ALWAYS ensure that the `signal_scores` dict is injected into the `GemCandidate` object before returning it to the `PositionMonitor`. Furthermore, ensure `MAX_TRADES_PER_DAY` in `.env` is high enough (e.g., 250) to quickly aggregate the required 30 trades during live execution, especially when operating on lower timeframes.
