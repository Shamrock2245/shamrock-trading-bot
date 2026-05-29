#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Shamrock Trading Bot — VPS Deploy Script
# Called by the CI/CD pipeline (or manually) to pull, rebuild, and restart.
#
# Usage:
#   bash scripts/deploy.sh
#
# What it does:
#   1. git pull origin main
#   2. docker compose down
#   3. docker system prune -f --volumes  ← free disk space before rebuild
#   4. docker compose build --no-cache
#   5. docker compose up -d
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "📦 Pulling latest code..."
git pull origin main

GIT_SHA=$(git rev-parse --short HEAD)
echo "🔖 Deploying commit: $GIT_SHA"

echo "🛑 Stopping containers..."
docker compose down

echo "🧹 Pruning Docker to free disk space..."
docker system prune -f --volumes 2>/dev/null || true

echo "🔨 Building images (no cache)..."
docker compose build --no-cache

echo "🚀 Starting containers..."
docker compose up -d

echo "✅ Deployed shamrock-bot @ $GIT_SHA"
