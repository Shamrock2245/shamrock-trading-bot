# Shamrock Trading Bot: Profit-Lock & High-Frequency Alpha Upgrade

**Date:** July 20, 2026  
**Status:** Ready for Integration  
**Target:** Increase win rate to >55% and trade frequency to 10-15 trades/day

---

## Overview

This upgrade implements two critical enhancements to transform the bot into a consistent "money-making machine":

1. **Dynamic Profit-Lock Manager** (`core/profit_lock_manager.py`)
   - Break-even stop at +1.5% profit
   - Trailing profit ratchet at +3% profit
   - Hard time-out for positions in loss > 4 hours

2. **High-Frequency Moralis Scanner** (`core/moralis_hf_scanner.py`)
   - Scans every 5 minutes for tokens with >50% volume spike
   - Filters by liquidity ($100k+) and narrative alignment
   - Feeds high-confidence signals to the Hyperliquid executor

---

## Key Improvements

### Trade History Analysis (v28)
- **Previous Win Rate:** 25.97%
- **Previous Avg PnL:** -$1.01 per trade
- **Problem:** Long-duration losses (AAVE, GRASS, EIGEN) drained capital
- **Solution:** Profit-lock and time-out logic prevent capital bleed

### Expected Outcomes
- **Win Rate Target:** >55% (by locking break-even and cutting time-outs)
- **Trade Frequency:** 10-15 trades/day (vs. 2 trades/day previously)
- **Daily Profit Target:** $500+ (consistent sweep to L1 Paycheck Wallet)

---

## Integration Steps

### 1. Merge New Modules
```bash
# Already added to core/:
# - core/profit_lock_manager.py
# - core/moralis_hf_scanner.py
```

### 2. Update `core/executor.py`
Add profit-lock integration to the position update loop:
```python
from core.profit_lock_manager import profit_lock_manager

def update_position_stops(position):
    """Update stops using profit-lock logic."""
    updated_state = profit_lock_manager.process_position(
        coin=position['coin'],
        current_price=position['current_price'],
        entry_price=position['entry_price'],
        entry_time=position['entry_time'],
        side=position['side']
    )
    
    if updated_state['status'] == 'timeout_close':
        # Close position to free capital
        logger.warning(f"Closing {position['coin']} due to hard time-out")
        close_position(position)
    else:
        # Update on-chain SL
        position['sl_price'] = updated_state['sl_price']
```

### 3. Update `core/hl_perps_scanner.py`
Integrate high-frequency Moralis scanner:
```python
from core.moralis_hf_scanner import hf_moralis_scanner

def get_entry_candidates():
    """Get candidates from both traditional and HF scanners."""
    # Existing logic
    traditional_candidates = scan_convergence_gate()
    
    # New: High-frequency Moralis alpha
    hf_candidates = hf_moralis_scanner.scan_for_alpha()
    
    # Merge and prioritize
    all_candidates = traditional_candidates + hf_candidates
    return sorted(all_candidates, key=lambda x: x.get('confidence_score', 0), reverse=True)
```

### 4. Update `.env`
Add new configuration flags:
```env
# Profit-Lock Manager
PROFIT_LOCK_ENABLED=true
PROFIT_LOCK_STATE_FILE=/app/data/hl_trailing_state.json

# High-Frequency Moralis Scanner
HF_MORALIS_SCANNER_ENABLED=true
HF_SCANNER_INTERVAL=300  # 5 minutes

# Moralis Trending Narratives
TRENDING_NARRATIVES=memes,ai,depin,hyperliquid,prediction
```

### 5. Deployment
```bash
# Run preflight check
python3 scripts/preflight_check.py

# Build and deploy
docker compose build --no-cache
docker compose up -d

# Monitor logs
docker compose logs -f shamrock-bot
```

---

## Profit-Lock Logic Explained

### Break-even Lock (+1.5%)
When a position reaches +1.5% profit:
- Move Stop-Loss to Entry + 0.1% (covers fees)
- Ensures winning trades don't turn into losses

### Trailing Profit Ratchet (+3%)
When a position reaches +3% profit:
- Lock in 1.5% trailing stop from peak
- As price climbs, trailing stop follows
- Captures upside while protecting gains

### Hard Time-Out (>4 hours in loss)
If a position is in loss for more than 4 hours:
- Automatically close to free capital
- Prevents "zombie" positions from draining resources
- Redirects capital to fresh alpha opportunities

---

## Moralis Integration Strategy

### Token Discovery Endpoints (Moralis API)
- **`/discovery/tokens/trending`** — Get trending tokens by volume
- **`/token/{address}/price`** — Fetch real-time prices
- **`/token/{address}/owners`** — Identify whale accumulation
- **`/pairs/{address}/snipers`** — Detect early accumulation

### Narrative Alignment (2026 Trends)
- **Memes:** +220% YTD (BONK, BRETT, FARTCOIN)
- **AI x DePIN:** Strong narrative (RNDR, BITTENSOR)
- **Hyperliquid Native:** Social dominance spike (HYPE)
- **Prediction Markets:** High engagement (RESOLV)

### CU Budget Optimization
- Scan every 5 minutes (not continuous)
- Limit to top 5 trending tokens per cycle
- Cache results to reduce API calls
- Estimated monthly CU usage: ~50k (well within Business plan)

---

## Testing & Validation

### Local Testing
```python
# Test profit-lock logic
python3 -c "
from core.profit_lock_manager import ProfitLockManager
from datetime import datetime

manager = ProfitLockManager('/tmp/test_state.json')

# Simulate entry at $100
manager.process_position('BTC', 100, 100, datetime.utcnow())

# Price moves to $102 (+2%)
state = manager.process_position('BTC', 102, 100, datetime.utcnow())
print(f'At +2%: SL = {state[\"sl_price\"]}')  # Should be Entry + 0.1%

# Price moves to $105 (+5%)
state = manager.process_position('BTC', 105, 100, datetime.utcnow())
print(f'At +5%: SL = {state[\"sl_price\"]}')  # Should be trailing 1.5%
"
```

### Preflight Check
The existing `scripts/preflight_check.py` will validate:
- ✅ Profit-lock state file creation
- ✅ Moralis API connectivity
- ✅ Position persistence logic
- ✅ Stop-loss update calculations

---

## Rollback Plan

If issues arise:
```bash
# Revert to previous version
git revert HEAD

# Rebuild without new modules
docker compose build --no-cache
docker compose up -d
```

---

## Next Steps

1. **Merge this PR** to `main`
2. **Run preflight check** locally
3. **Deploy to Hetzner** with `deploy_now.sh`
4. **Monitor for 7 days** to validate win rate improvement
5. **Scale capital** from $150 to $1k-$5k once consistent profitability is confirmed

---

## Questions?

Refer to:
- `GUARDRAILS.md` — Safety constraints
- `CURRENT_STATUS.md` — System state
- `README.md` — Architecture overview
