"""
notifications/email_notifier.py — Email notification service for Shamrock Trading Bot.

Supports sending high-priority email alerts to admin@shamrockbailbonds.biz
when profitability milestones are reached, when paper-to-live promotion gates pass,
or when critical system alerts fire.

Delivery Mechanisms:
  1. Standard SMTP (smtplib with TLS/SSL) when SMTP_* env vars are set.
  2. SendGrid / Mailgun / Custom Webhook proxy fallback.
  3. Google Apps Script Email Webhook fallback if configured.

Environment Variables:
  NOTIFY_EMAIL_RECIPIENT   — Default: admin@shamrockbailbonds.biz
  SMTP_HOST                — e.g., smtp.gmail.com or mail.shamrockbailbonds.biz
  SMTP_PORT                — Default: 587 (TLS) or 465 (SSL)
  SMTP_USER                — Username / Email
  SMTP_PASSWORD            — App Password / API Key
  SMTP_FROM_EMAIL          — Sender address (default: bot@shamrockbailbonds.biz)
  EMAIL_WEBHOOK_URL        — Optional HTTP POST proxy URL for email dispatch
"""

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any

from data.http_session import get_session

logger = logging.getLogger("email_notifier")

# Default recipient requested by user
DEFAULT_RECIPIENT = "admin@shamrockbailbonds.biz"
NOTIFY_EMAIL_RECIPIENT = os.getenv("NOTIFY_EMAIL_RECIPIENT", DEFAULT_RECIPIENT).strip()

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "bot@shamrockbailbonds.biz")
EMAIL_WEBHOOK_URL = os.getenv("EMAIL_WEBHOOK_URL", "")


def send_email_alert(
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    recipient: Optional[str] = None,
) -> bool:
    """
    Send an email alert to recipient (default: admin@shamrockbailbonds.biz).

    Tries SMTP first if configured, then falls back to EMAIL_WEBHOOK_URL.
    """
    target = recipient or NOTIFY_EMAIL_RECIPIENT or DEFAULT_RECIPIENT

    # 1. Try SMTP if host & credentials provided
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM_EMAIL
            msg["To"] = target

            msg.attach(MIMEText(body_text, "plain"))
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
                server.starttls()

            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [target], msg.as_string())
            server.quit()
            logger.info(f"📧 Email alert sent via SMTP to {target}: {subject}")
            return True
        except Exception as e:
            logger.warning(f"SMTP email dispatch failed: {e}")

    # 2. Try HTTP Webhook proxy if set
    if EMAIL_WEBHOOK_URL:
        try:
            payload = {
                "recipient": target,
                "subject": subject,
                "text": body_text,
                "html": body_html or body_text,
            }
            resp = get_session().post(EMAIL_WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code in (200, 201, 202):
                logger.info(f"📧 Email alert sent via Webhook to {target}: {subject}")
                return True
            logger.warning(f"Email webhook failed with status {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.warning(f"Email webhook dispatch failed: {e}")

    logger.info(
        f"📧 Email alert logged (configure SMTP_HOST / EMAIL_WEBHOOK_URL in .env to dispatch live emails):\n"
        f"To: {target}\nSubject: {subject}\nBody:\n{body_text[:300]}..."
    )
    return False


def notify_profitability_milestone(
    pnl_usd: float,
    milestone_usd: float,
    metrics: Optional[Dict[str, Any]] = None,
    mode: str = "paper",
) -> bool:
    """
    Dispatch profitability milestone alerts to Slack, Telegram, and Email (admin@shamrockbailbonds.biz).
    """
    mode_badge = "📄 PAPER" if mode == "paper" else "🔴 LIVE"
    subject = f"💰 [{mode_badge}] Profitability Milestone Reached: ${pnl_usd:.2f} PnL!"

    win_rate_str = f"{metrics.get('win_rate', 0) * 100:.1f}%" if metrics else "N/A"
    trades_count = metrics.get("closed_trades", "N/A") if metrics else "N/A"
    profit_factor = f"{metrics.get('profit_factor', 0):.2f}" if metrics else "N/A"

    body_text = (
        f"Shamrock Trading Bot — Profitability Alert\n\n"
        f"Status: {mode_badge}\n"
        f"Realized PnL: ${pnl_usd:.2f} (Milestone Threshold: ${milestone_usd:.2f})\n"
        f"Closed Trades: {trades_count}\n"
        f"Win Rate: {win_rate_str}\n"
        f"Profit Factor: {profit_factor}\n\n"
        f"The auto-tuning engine and offensive guardrails are actively running.\n"
        f"Check Slack / Telegram or the dashboard for real-time trade telemetry."
    )

    body_html = f"""
    <h2>💰 [{mode_badge}] Profitability Milestone Reached</h2>
    <p><strong>Realized PnL:</strong> <span style="color:green; font-size:18px;">${pnl_usd:.2f}</span> (Milestone: ${milestone_usd:.2f})</p>
    <ul>
        <li><strong>Mode:</strong> {mode_badge}</li>
        <li><strong>Closed Trades:</strong> {trades_count}</li>
        <li><strong>Win Rate:</strong> {win_rate_str}</li>
        <li><strong>Profit Factor:</strong> {profit_factor}</li>
    </ul>
    <p><em>Shamrock Trading Bot — Auto-Tuned & Compounding.</em></p>
    """

    # Dispatch email
    email_sent = send_email_alert(subject, body_text, body_html)

    # Dispatch Slack & Telegram
    try:
        from notifications.slack import notify_alert as slack_alert
        slack_alert(
            title=f"💰 Profitability Milestone: ${pnl_usd:.2f} PnL",
            message=f"Mode: {mode_badge} | Milestone: ${milestone_usd:.2f}\nTrades: {trades_count} | WR: {win_rate_str} | PF: {profit_factor}",
            level="info",
        )
    except Exception as e:
        logger.debug(f"Slack milestone alert error: {e}")

    try:
        from notifications.telegram import notify_alert as tg_alert
        tg_alert(
            title=f"💰 Profitability Milestone: ${pnl_usd:.2f}",
            message=f"Mode: {mode_badge}\nRealized PnL: ${pnl_usd:.2f}\nTrades: {trades_count} | WR: {win_rate_str}",
            level="success",
        )
    except Exception as e:
        logger.debug(f"Telegram milestone alert error: {e}")

    return email_sent


def notify_live_readiness(
    today_pnl_usd: float,
    checks: Dict[str, Any],
    recipient: Optional[str] = None,
) -> bool:
    """
    Send high-priority alert to admin@shamrockbailbonds.biz when paper trading
    satisfies profitability requirements and is ready for live mode.
    """
    subject = f"🚀 [ACTION REQUIRED] Shamrock Bot Ready For Live Mode — ${today_pnl_usd:.2f} PnL"
    chains_ready = ", ".join(checks.get("chains_with_gas", [])) or "None"
    keys_loaded = len(checks.get("private_keys_present", []))

    body_text = (
        f"🚀 Shamrock Trading Bot — Paper-to-Live Promotion Ready!\n\n"
        f"Paper Trading Profit Today: ${today_pnl_usd:.2f}\n"
        f"Chains with Native Gas: {chains_ready}\n"
        f"Private Keys Verified: {keys_loaded}/3\n\n"
        f"All paper trading readiness criteria have passed.\n"
        f"To switch to live trading: set MODE=live in .env and restart the bot."
    )

    body_html = f"""
    <h2>🚀 Shamrock Trading Bot — Paper-to-Live Readiness</h2>
    <p><strong>Today's Paper PnL:</strong> <span style="color:green; font-size:20px;">${today_pnl_usd:.2f}</span></p>
    <ul>
        <li><strong>Chains Ready:</strong> {chains_ready}</li>
        <li><strong>Private Keys Loaded:</strong> {keys_loaded}/3</li>
        <li><strong>Status:</strong> Ready for Live Trade Execution</li>
    </ul>
    <p><strong>Action Required to Activate Live Mode:</strong></p>
    <pre>MODE=live</pre>
    """

    return send_email_alert(subject, body_text, body_html, recipient=recipient)
