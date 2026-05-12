# Updated with rebalance hooks
# ... existing code plus
import from core.wallet_rebalancer

async def on_regime_flip(new_regime):
    if new_regime == 'EXPANSION':
        await rebalancer.check_and_rebalance(wallets)  # Trigger rebalance