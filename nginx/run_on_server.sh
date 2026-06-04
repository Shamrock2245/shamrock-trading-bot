#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Run Postiz SSL setup remotely on the Hetzner VPS
#
# Run this from your LOCAL machine (where .shamrock_deploy_key lives):
#   cd ~/Desktop/shamrock-trading-bot && bash nginx/run_on_server.sh
#
# Or from any directory with the key:
#   bash run_on_server.sh /path/to/.shamrock_deploy_key
# ═══════════════════════════════════════════════════════════════════════════════
set -e

KEY="${1:-/Users/brendan/Desktop/shamrock-trading-bot/.shamrock_deploy_key}"
SERVER="root@5.161.126.32"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🍀 SHAMROCK — Remote Postiz SSL Deploy                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Server:  $SERVER"
echo "  SSH Key: $KEY"
echo ""

if [ ! -f "$KEY" ]; then
    echo "❌ SSH key not found at: $KEY"
    echo "   Usage: bash run_on_server.sh /path/to/.shamrock_deploy_key"
    exit 1
fi

chmod 600 "$KEY"

# ── Step 1: Copy the setup script to the server ───────────────────────────────
echo "📤 Uploading setup script to server..."
scp -i "$KEY" -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/setup_postiz_ssl.sh" \
    "$SERVER:/root/setup_postiz_ssl.sh"
echo "   ✅ Script uploaded"
echo ""

# ── Step 2: Copy the Nginx config to the server ───────────────────────────────
echo "📤 Uploading Nginx config to server..."
scp -i "$KEY" -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/social.shamrockbailbonds.biz.conf" \
    "$SERVER:/tmp/social.shamrockbailbonds.biz.conf"
echo "   ✅ Nginx config uploaded"
echo ""

# ── Step 3: Run the setup script on the server ────────────────────────────────
echo "🚀 Running setup on server (this will take ~2 minutes)..."
echo "────────────────────────────────────────────────────────────────"
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "bash /root/setup_postiz_ssl.sh"
echo "────────────────────────────────────────────────────────────────"
echo ""
echo "✅ Remote setup complete!"
echo ""
echo "🌐 Postiz should now be live at: https://social.shamrockbailbonds.biz"
echo ""
echo "🔍 Quick verification:"
echo "   curl -I https://social.shamrockbailbonds.biz"
