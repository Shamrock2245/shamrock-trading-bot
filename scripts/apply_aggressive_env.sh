#!/bin/bash
# Apply aggressive paper-mode .env settings on Hetzner
# Run: ssh -i $KEY $SERVER 'bash /root/shamrock-trading-bot/scripts/apply_aggressive_env.sh'

set -e
cd /root/shamrock-trading-bot

echo "🔥 Applying AGGRESSIVE paper-mode settings..."

# ── Entry & Sizing ──
sed -i 's/^MAX_POSITION_SIZE_PERCENT=.*/MAX_POSITION_SIZE_PERCENT=8.0/' .env
sed -i 's/^HIGH_CONVICTION_POSITION_PCT=.*/HIGH_CONVICTION_POSITION_PCT=8.0/' .env
sed -i 's/^MAX_CONCURRENT_POSITIONS=.*/MAX_CONCURRENT_POSITIONS=30/' .env
sed -i 's/^SCAN_INTERVAL_SECONDS=.*/SCAN_INTERVAL_SECONDS=30/' .env
sed -i 's/^MIN_GEM_SCORE=.*/MIN_GEM_SCORE=55/' .env
sed -i 's/^EXPRESS_LANE_SCORE=.*/EXPRESS_LANE_SCORE=72/' .env

# ── TP Tiers (hold longer for bigger wins) ──
sed -i 's/^TAKE_PROFIT_TP1_MULT=.*/TAKE_PROFIT_TP1_MULT=2.5/' .env
sed -i 's/^TAKE_PROFIT_TP1_SELL_PCT=.*/TAKE_PROFIT_TP1_SELL_PCT=0.35/' .env
sed -i 's/^TAKE_PROFIT_TP2_MULT=.*/TAKE_PROFIT_TP2_MULT=5.0/' .env
sed -i 's/^TAKE_PROFIT_TP2_SELL_PCT=.*/TAKE_PROFIT_TP2_SELL_PCT=0.40/' .env
# Add TP3 if not present
grep -q '^TAKE_PROFIT_TP3_MULT' .env || echo 'TAKE_PROFIT_TP3_MULT=10.0' >> .env
grep -q '^TAKE_PROFIT_TP3_SELL_PCT' .env || echo 'TAKE_PROFIT_TP3_SELL_PCT=0.30' >> .env

# ── Conviction (lower thresholds, bigger multipliers) ──
sed -i 's/^CONVICTION_HIGH_THRESHOLD=.*/CONVICTION_HIGH_THRESHOLD=75/' .env
sed -i 's/^CONVICTION_MID_THRESHOLD=.*/CONVICTION_MID_THRESHOLD=62/' .env
sed -i 's/^CONVICTION_HIGH_MULTIPLIER=.*/CONVICTION_HIGH_MULTIPLIER=1.25/' .env
sed -i 's/^CONVICTION_MID_MULTIPLIER=.*/CONVICTION_MID_MULTIPLIER=1.0/' .env
sed -i 's/^CONVICTION_LOW_MULTIPLIER=.*/CONVICTION_LOW_MULTIPLIER=0.75/' .env

# ── God Mode ON ──
sed -i 's/^GOD_MODE_ENABLED=.*/GOD_MODE_ENABLED=true/' .env
sed -i 's/^GOD_MODE_DAILY_PNL_THRESHOLD_USD=.*/GOD_MODE_DAILY_PNL_THRESHOLD_USD=50.0/' .env
sed -i 's/^GOD_MODE_KELLY_MULTIPLIER=.*/GOD_MODE_KELLY_MULTIPLIER=2.5/' .env
sed -i 's/^GOD_MODE_TRAILING_STOP_PCT=.*/GOD_MODE_TRAILING_STOP_PCT=8.0/' .env
sed -i 's/^GOD_MODE_MAX_DRAWDOWN_FROM_PEAK_USD=.*/GOD_MODE_MAX_DRAWDOWN_FROM_PEAK_USD=100.0/' .env

# ── House Money (compound harder) ──
sed -i 's/^HOUSE_MONEY_REINVEST_PCT=.*/HOUSE_MONEY_REINVEST_PCT=60.0/' .env
sed -i 's/^HOUSE_MONEY_MAX_POOL_USD=.*/HOUSE_MONEY_MAX_POOL_USD=10000.0/' .env
sed -i 's/^HOUSE_MONEY_MIN_DEPLOY_USD=.*/HOUSE_MONEY_MIN_DEPLOY_USD=3.0/' .env
sed -i 's/^HOUSE_MONEY_MAX_DEPLOY_PCT=.*/HOUSE_MONEY_MAX_DEPLOY_PCT=75.0/' .env
sed -i 's/^HOUSE_MONEY_MAX_POSITION_MULT=.*/HOUSE_MONEY_MAX_POSITION_MULT=2.5/' .env

# ── Cascade Boost (deeper score reduction on streaks) ──
sed -i 's/^CASCADE_BOOST_PER_WIN=.*/CASCADE_BOOST_PER_WIN=1.5/' .env
sed -i 's/^CASCADE_BOOST_MAX_REDUCTION=.*/CASCADE_BOOST_MAX_REDUCTION=10.0/' .env
sed -i 's/^CASCADE_BOOST_RECOVERY_PER_LOSS=.*/CASCADE_BOOST_RECOVERY_PER_LOSS=1.0/' .env
sed -i 's/^CASCADE_BOOST_FLOOR_SCORE=.*/CASCADE_BOOST_FLOOR_SCORE=50.0/' .env

# ── Blitz Mode ON + Momentum ──
sed -i 's/^BLITZ_MODE_ENABLED=.*/BLITZ_MODE_ENABLED=true/' .env
sed -i 's/^BLITZ_MODE_MULTIPLIER=.*/BLITZ_MODE_MULTIPLIER=1.5/' .env
sed -i 's/^MOMENTUM_REENTRY_VOLUME_MULT=.*/MOMENTUM_REENTRY_VOLUME_MULT=2.0/' .env
sed -i 's/^MOMENTUM_REENTRY_MAX_AGE_MINUTES=.*/MOMENTUM_REENTRY_MAX_AGE_MINUTES=60.0/' .env
sed -i 's/^MOMENTUM_REENTRY_SIZE_MULT=.*/MOMENTUM_REENTRY_SIZE_MULT=1.5/' .env
sed -i 's/^OFFENSIVE_MAX_POSITION_USD=.*/OFFENSIVE_MAX_POSITION_USD=2000.0/' .env

# ── Loss streak cooling (softer) + Exposure ──
sed -i 's/^LOSS_STREAK_SCORE_PENALTY=.*/LOSS_STREAK_SCORE_PENALTY=2.0/' .env
sed -i 's/^LOSS_STREAK_MAX_PENALTY=.*/LOSS_STREAK_MAX_PENALTY=8.0/' .env
sed -i 's/^MAX_PORTFOLIO_EXPOSURE_PCT=.*/MAX_PORTFOLIO_EXPOSURE_PCT=90.0/' .env
sed -i 's/^MAX_TRADES_PER_CYCLE=.*/MAX_TRADES_PER_CYCLE=12/' .env
sed -i 's/^CAPITAL_RECOVERY_THRESHOLD_USD=.*/CAPITAL_RECOVERY_THRESHOLD_USD=3/' .env
sed -i 's/^CAPITAL_RECOVERY_MIN_SCORE=.*/CAPITAL_RECOVERY_MIN_SCORE=45/' .env
grep -q '^MAX_TRADES_PER_DAY' .env || echo 'MAX_TRADES_PER_DAY=100' >> .env

echo ""
echo "✅ Aggressive paper-mode settings applied!"
echo ""
echo "Key changes:"
echo "  🔓 GOD_MODE=true | BLITZ_MODE=true"
echo "  📉 MIN_GEM_SCORE=55 | EXPRESS_LANE=72"
echo "  🎯 TP tiers: 2.5x → 5x → 10x"
echo "  💰 MAX_EXPOSURE=90% | 30 concurrent positions"
echo "  ⚡ Scan every 30s | 12 trades/cycle | 100 trades/day"
echo ""
echo "Verify critical settings:"
grep -E '^(GOD_MODE_ENABLED|BLITZ_MODE_ENABLED|MIN_GEM_SCORE|EXPRESS_LANE_SCORE|MAX_CONCURRENT|MAX_PORTFOLIO)' .env
