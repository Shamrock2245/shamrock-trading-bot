import os
import logging
import requests
from typing import Optional

logger = logging.getLogger("telegram")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram_message(text: str, chat_id: Optional[str] = None) -> bool:
    """
    Send a message via Telegram Bot API.
    """
    if not TELEGRAM_BOT_TOKEN:
        return False
        
    target_chat = chat_id or TELEGRAM_CHAT_ID
    if not target_chat:
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            return True
        else:
            logger.debug(f"Telegram API error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.debug(f"Telegram request failed: {e}")
        return False

def notify_trade(action: str, token_symbol: str, chain: str,
                 price: float, amount_usd: float, pnl_pct: Optional[float] = None,
                 tx_hash: str = "") -> bool:
    """Format and send a trade notification."""
    emoji = "🟢" if action.upper() == "BUY" else "🔴"
    if action.upper() == "SELL" and pnl_pct is not None and pnl_pct > 0:
        emoji = "💰"
        
    msg = f"{emoji} <b>{action.upper()} {token_symbol}</b> ({chain.upper()})\n"
    msg += f"Amount: ${amount_usd:.2f}\n"
    msg += f"Price: ${price:.6f}\n"
    
    if pnl_pct is not None:
        msg += f"PnL: {pnl_pct:+.2f}%\n"
        
    if tx_hash:
        msg += f"\n<a href='https://dexscreener.com/{chain}/{token_symbol}'>Chart</a>"
        
    return send_telegram_message(msg)

def notify_alert(title: str, message: str, level: str = "info") -> bool:
    """Format and send a system alert."""
    emoji = "ℹ️"
    if level == "warning":
        emoji = "⚠️"
    elif level == "error":
        emoji = "🚨"
    elif level == "success":
        emoji = "✅"
        
    msg = f"{emoji} <b>{title}</b>\n\n{message}"
    return send_telegram_message(msg)
