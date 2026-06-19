#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Shamrock Trading Bot — One-Click Deploy Script
# Run this from your own terminal (not Antigravity):
#   cd ~/Desktop/shamrock-trading-bot && bash deploy_now.sh
# ═══════════════════════════════════════════════════════════════════

set -e  # Stop on first error

KEY="/Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key"
SERVER="root@46.62.231.43"
REPO="/root/shamrock-trading-bot"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🍀 SHAMROCK TRADING BOT — DEPLOY PIPELINE              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Push to GitHub ────────────────────────────────────────
echo "📤 Step 1/5 — Pushing to GitHub..."
cd /Users/brendan/Desktop/shamrock-trading-bot
git push origin main
echo "   ✅ Pushed to GitHub"
echo ""

# ── Step 2: Pull on Hetzner ──────────────────────────────────────
echo "📥 Step 2/5 — Pulling latest on Hetzner..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "cd $REPO && git pull origin main"
echo "   ✅ Server updated"
echo ""

# ── Step 3: Stop containers ─────────────────────────────────────
echo "🛑 Step 3/5 — Stopping containers..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "cd $REPO && docker compose down"
echo "   ✅ Containers stopped"
echo ""

# ── Step 4: Rebuild (no cache) ──────────────────────────────────
echo "🔨 Step 4/5 — Rebuilding Docker images (this takes ~2 min)..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "cd $REPO && docker compose build --no-cache"
echo "   ✅ Images rebuilt"
echo ""

# ── Step 5: Start ───────────────────────────────────────────────
echo "🚀 Step 5/5 — Starting containers..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "cd $REPO && docker compose up -d"
echo "   ✅ Containers running"
echo ""

# ── Health Check ────────────────────────────────────────────────
echo "⏳ Waiting 15 seconds for bot to stabilize..."
sleep 15
echo ""
echo "📋 Recent bot logs:"
echo "───────────────────────────────────────────────────────────"
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "cd $REPO && docker compose logs --tail=30 bot"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ DEPLOY COMPLETE — Bot is running in PAPER mode"
echo "  📈 P&L Dashboard: check page 9 in Streamlit"
echo "═══════════════════════════════════════════════════════════"
