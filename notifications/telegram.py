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


def notify_threshold_breach(
    symbol: str,
    chain: str,
    old_score: float,
    new_score: float,
    timing: str = "flat",
    liquidity_usd: float = 0,
    volume_1h: float = 0,
    buy_pressure: float = 0,
    source: str = "",
) -> bool:
    """
    Alert when a watchlisted token's score crosses above the entry threshold.
    This is the most valuable signal — the moment a near-miss becomes actionable.
    """
    timing_icon = {"accelerating": "🚀", "decelerating": "📉", "flat": "➡️"}.get(timing, "➡️")
    smart_money = "🐋 Confirmed" if buy_pressure >= 0.55 else "📊 Normal"

    msg = (
        f"🚨 <b>THRESHOLD BREACH: ${symbol}</b> ({chain.upper()})\n"
        f"Score: {old_score:.0f} → <b>{new_score:.0f}</b>\n\n"
        f"Timing: {timing_icon} {timing.upper()}\n"
        f"Liquidity: ${liquidity_usd:,.0f}\n"
        f"Volume 1h: ${volume_1h:,.0f}\n"
        f"Buy Pressure: {smart_money} ({buy_pressure:.2f})\n"
    )
    if source:
        msg += f"Source: {source}\n"
    msg += "\n→ Bot will auto-enter next cycle"

    return send_telegram_message(msg)


def notify_conviction_alert(
    symbol: str,
    chain: str,
    score: float,
    strategy_tag: str = "",
    price_usd: float = 0,
    market_cap: float = 0,
    liquidity_usd: float = 0,
) -> bool:
    """
    Alert for all gems that pass the scoring threshold.
    Tiered messaging: EXCEPTIONAL (80+), STRONG (70-79), GOOD (65-69).
    """
    if score >= 80:
        emoji, tier, footer = "🏆", "EXCEPTIONAL", "🔥 Full conviction — express lane"
    elif score >= 70:
        emoji, tier, footer = "💎", "STRONG", "⚡ High conviction entry"
    else:
        emoji, tier, footer = "✅", "GOOD", "📈 Standard entry"

    price_str = f"${price_usd:.8f}" if price_usd < 0.001 else (
        f"${price_usd:.4f}" if price_usd < 1 else f"${price_usd:,.2f}"
    )
    msg = (
        f"{emoji} <b>GEM ALERT: ${symbol}</b> ({chain.upper()})\n"
        f"Score: <b>{score:.0f}/100</b> — {tier}\n\n"
        f"Price: {price_str}\n"
        f"MCap: ${market_cap:,.0f}\n"
        f"Liquidity: ${liquidity_usd:,.0f}\n"
    )
    if strategy_tag:
        msg += f"Strategy: {strategy_tag}\n"
    msg += f"\n{footer}"

    return send_telegram_message(msg)
