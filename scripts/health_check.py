"""
scripts/health_check.py — Shamrock Trading Bot health monitor.

Runs as a long-lived process in the shamrock-health Docker container.
Checks every 60 seconds:
  1. Bot has completed a scan cycle in the last 5 minutes
  2. Dashboard is responding on port 8501
  3. Output files exist and are fresh
  4. Writes health status to output/health.json
  5. Sends Slack alert if any check fails
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
CHECK_INTERVAL_SECONDS = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
BOT_STATUS_FILE = Path(os.getenv("BOT_STATUS_FILE", "/app/output/bot_status.json"))
HEALTH_OUTPUT_FILE = Path(os.getenv("HEALTH_OUTPUT_FILE", "/app/output/health.json"))
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8501")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
MAX_CYCLE_AGE_SECONDS = int(os.getenv("MAX_CYCLE_AGE_SECONDS", "300"))  # 5 min

# Ensure output dir exists
HEALTH_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | health | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("health")

_last_alert_time: dict[str, float] = {}
_ALERT_COOLDOWN = 600  # Don't re-alert same issue within 10 min


def _send_slack_alert(message: str, level: str = "warning") -> None:
    """Send a Slack notification for health issues."""
    if not SLACK_WEBHOOK_URL:
        return
    issue_key = message[:50]
    now = time.time()
    if now - _last_alert_time.get(issue_key, 0) < _ALERT_COOLDOWN:
        return
    _last_alert_time[issue_key] = now
    emoji = "🔴" if level == "critical" else "⚠️"
    try:
        requests.post(
            SLACK_WEBHOOK_URL,
            json={"text": f"{emoji} *Shamrock Health Alert*\n{message}"},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Slack alert failed: {e}")


def check_bot_cycle() -> dict:
    """Check if the bot has completed a cycle recently."""
    result = {"ok": False, "message": "", "last_cycle": None, "age_seconds": None}
    try:
        if not BOT_STATUS_FILE.exists():
            result["message"] = f"Bot status file missing: {BOT_STATUS_FILE}"
            return result

        with open(BOT_STATUS_FILE) as f:
            status = json.load(f)

        last_cycle_str = status.get("last_cycle_at") or status.get("timestamp")
        if not last_cycle_str:
            result["message"] = "No last_cycle_at in bot_status.json"
            return result

        last_cycle = datetime.fromisoformat(last_cycle_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_seconds = (now - last_cycle).total_seconds()

        result["last_cycle"] = last_cycle_str
        result["age_seconds"] = round(age_seconds)

        if age_seconds > MAX_CYCLE_AGE_SECONDS:
            result["message"] = (
                f"Bot last cycle was {age_seconds:.0f}s ago "
                f"(threshold: {MAX_CYCLE_AGE_SECONDS}s)"
            )
        else:
            result["ok"] = True
            result["message"] = f"Bot active — last cycle {age_seconds:.0f}s ago"

    except Exception as e:
        result["message"] = f"Bot cycle check error: {e}"

    return result


def check_dashboard() -> dict:
    """Check if the Streamlit dashboard is responding."""
    result = {"ok": False, "message": "", "status_code": None, "response_ms": None}
    try:
        start = time.time()
        resp = requests.get(f"{DASHBOARD_URL}/_stcore/health", timeout=10)
        elapsed_ms = round((time.time() - start) * 1000)
        result["status_code"] = resp.status_code
        result["response_ms"] = elapsed_ms
        if resp.status_code == 200:
            result["ok"] = True
            result["message"] = f"Dashboard OK ({elapsed_ms}ms)"
        else:
            result["message"] = f"Dashboard returned HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        result["message"] = "Dashboard not reachable (connection refused)"
    except Exception as e:
        result["message"] = f"Dashboard check error: {e}"
    return result


def check_output_files() -> dict:
    """Check that critical output files exist."""
    result = {"ok": True, "message": "All output files present", "missing": []}
    critical_files = [
        Path("/app/output/bot_status.json"),
        Path("/app/logs/bot.log"),
    ]
    missing = [str(f) for f in critical_files if not f.exists()]
    if missing:
        result["ok"] = False
        result["missing"] = missing
        result["message"] = f"Missing files: {', '.join(missing)}"
    return result


def run_health_check() -> dict:
    """Run all health checks and return aggregated status."""
    now = datetime.now(timezone.utc)
    checks = {
        "bot_cycle": check_bot_cycle(),
        "dashboard": check_dashboard(),
        "output_files": check_output_files(),
    }

    all_ok = all(c["ok"] for c in checks.values())
    status = "healthy" if all_ok else "degraded"

    health = {
        "timestamp": now.isoformat(),
        "status": status,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": sum(1 for c in checks.values() if c["ok"]),
            "failed": sum(1 for c in checks.values() if not c["ok"]),
        },
    }

    # Write health file
    try:
        with open(HEALTH_OUTPUT_FILE, "w") as f:
            json.dump(health, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write health file: {e}")

    # Alert on failures
    if not all_ok:
        failed = [
            f"• {name}: {check['message']}"
            for name, check in checks.items()
            if not check["ok"]
        ]
        alert_msg = "Health check failures:\n" + "\n".join(failed)
        logger.warning(alert_msg)
        _send_slack_alert(alert_msg, level="warning")
    else:
        logger.info(f"Health OK — bot_cycle={checks['bot_cycle']['message']}")

    return health


def main():
    logger.info("Shamrock Health Monitor starting...")
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS}s")
    logger.info(f"Bot status file: {BOT_STATUS_FILE}")
    logger.info(f"Dashboard URL: {DASHBOARD_URL}")

    consecutive_failures = 0

    while True:
        try:
            health = run_health_check()
            if health["status"] != "healthy":
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    _send_slack_alert(
                        f"CRITICAL: Bot has been unhealthy for {consecutive_failures} consecutive checks!",
                        level="critical",
                    )
            else:
                consecutive_failures = 0
        except Exception as e:
            logger.error(f"Health check loop error: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
