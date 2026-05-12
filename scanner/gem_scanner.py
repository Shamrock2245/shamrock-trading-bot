# Integration hook for rebalancer on sweep
# Add to sweep trigger:
if is_liquidity_sweep(...):
    await rebalancer.check_and_rebalance(wallets)