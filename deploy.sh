#!/bin/bash
# deploy.sh — Pull latest code and restart the bot on Hetzner VPS
# Run as: bash deploy.sh
set -e

REPO_DIR="/root/shamrock-trading-bot"
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"

echo "🚀 Shamrock Trading Bot — Deploy Script"
echo "======================================="
echo ""

# 1. Pull latest code from GitHub
echo "📥 Pulling latest code from GitHub..."
cd "$REPO_DIR"
git pull origin main
echo "✅ Code updated to: $(git rev-parse --short HEAD)"
echo ""

# 2. Show what changed
echo "📋 Recent commits:"
git log --oneline -5
echo ""

# 3. Restart the Docker containers
echo "🔄 Restarting Docker containers..."
docker compose -f "$COMPOSE_FILE" pull 2>/dev/null || true
docker compose -f "$COMPOSE_FILE" up -d --build
echo ""

# 4. Show running containers
echo "📊 Running containers:"
docker compose -f "$COMPOSE_FILE" ps
echo ""

# 5. Tail logs briefly
echo "📜 Latest logs (last 30 lines):"
docker compose -f "$COMPOSE_FILE" logs --tail=30
echo ""
echo "✅ Deploy complete!"
