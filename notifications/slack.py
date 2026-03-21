"""
notifications/slack.py — Slack notification service for Shamrock Trading Bot.

Supports two modes:
  1. Bot Token (preferred) — Uses SLACK_BOT_TOKEN to post via Slack API
     Can DM directly to a user or post to a channel.
  2. Webhook (fallback) — Uses SLACK_WEBHOOK_URL for simple channel posting

Environment variables:
  SLACK_BOT_TOKEN        — Bot OAuth token (xoxb-...)
  SLACK_NOTIFY_USER_ID   — Slack user ID to DM (e.g., U09ML5HBBEX)
  SLACK_WEBHOOK_URL      — Incoming webhook URL (fallback)
"""

import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_NOTIFY_USER_ID = os.getenv("SLACK_NOTIFY_USER_ID", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL_TRADES = os.getenv("SLACK_CHANNEL_TRADES", "#shamrock-trades")


def _post_via_bot(text: str, channel: str, blocks: Optional[list] = None) -> bool:
    """Post a message via Slack Bot API (chat.postMessage)."""
    if not SLACK_BOT_TOKEN:
        return False

    payload = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
    }
    if blocks:
        payload["blocks"] = blocks

    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": "Bearer {}".format(SLACK_BOT_TOKEN),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            logger.info("Slack message sent to {}".format(channel))
            return True
        logger.warning("Slack API error: {}".format(data.get("error", "unknown")))
        return False
    except Exception as e:
        logger.error("Slack bot post failed: {}".format(e))
        return False


def _post_via_webhook(text: str) -> bool:
    """Post a message via Slack Incoming Webhook (fallback)."""
    if not SLACK_WEBHOOK_URL or "your/webhook/here" in SLACK_WEBHOOK_URL:
        return False

    try:
        resp = requests.post(
            SLACK_WEBHOOK_URL,
            json={"text": text},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("Slack webhook message sent")
            return True
        logger.warning("Slack webhook error: {} {}".format(resp.status_code, resp.text[:100]))
        return False
    except Exception as e:
        logger.error("Slack webhook failed: {}".format(e))
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def send_slack_message(text: str, channel: Optional[str] = None) -> bool:
    """
    Send a Slack message. Tries bot token first, falls back to webhook.

    Args:
        text: Message text (supports Slack mrkdwn)
        channel: Channel ID or user ID to post to. Defaults to SLACK_NOTIFY_USER_ID (DM).
    """
    target = channel or SLACK_NOTIFY_USER_ID or SLACK_CHANNEL_TRADES

    # Try bot token first (preferred — supports DMs)
    if SLACK_BOT_TOKEN:
        return _post_via_bot(text, target)

    # Fallback to webhook
    return _post_via_webhook(text)


def notify_trade(action: str, token_symbol: str, chain: str,
                 amount_eth: float, score: float,
                 mode: str = "paper", extra: str = "") -> bool:
    """
    Send a formatted trade notification.

    Args:
        action: "BUY" or "SELL"
        token_symbol: Token ticker
        chain: Chain name
        amount_eth: ETH amount
        score: Gem score
        mode: "paper" or "live"
        extra: Additional info
    """
    emoji = "🟢" if action == "BUY" else "🔴"
    mode_badge = "📄 PAPER" if mode == "paper" else "🔴 LIVE"

    msg = (
        "{}  *{} {}* on {} | {}\n"
        "Amount: `{:.4f} ETH` | Gem Score: `{:.0f}/100`"
    ).format(emoji, action, token_symbol, chain.title(), mode_badge, amount_eth, score)

    if extra:
        msg += "\n{}".format(extra)

    return send_slack_message(msg)


def notify_alert(title: str, message: str, level: str = "info") -> bool:
    """
    Send a system alert notification.

    Args:
        title: Alert title
        message: Alert details
        level: "info", "warning", "critical"
    """
    emoji_map = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
    emoji = emoji_map.get(level, "ℹ️")

    msg = "{} *{}*\n{}".format(emoji, title, message)
    return send_slack_message(msg)


def notify_cycle_summary(cycle: int, candidates: int, trades: int,
                         mode: str = "paper") -> bool:
    """
    Send a periodic cycle summary (every N cycles, not every cycle).

    Args:
        cycle: Cycle number
        candidates: Number of gem candidates found
        trades: Number of trades executed
        mode: "paper" or "live"
    """
    mode_badge = "📄 PAPER" if mode == "paper" else "🔴 LIVE"
    msg = (
        "☘️ *Cycle {}* | {}\n"
        "Candidates: `{}` | Trades: `{}`"
    ).format(cycle, mode_badge, candidates, trades)

    return send_slack_message(msg)
