#!/usr/bin/env python3
"""
scripts/reviewer.py — "Get It Right" post-deploy reviewer.

After a deploy completes, SSH into the Hetzner server, tail bot logs,
and grade the deployment as:

  pass  — Bot is healthy, logs look clean, no errors detected
  warn  — Bot running but with non-fatal issues (degraded behaviour)
  fail  — Critical errors, crash, or bot not running at all

Structured feedback is written to output/review_report.json and printed
to stdout. The deploy workflow uses the exit code:
  0 = pass
  1 = warn (human review recommended but bot is running)
  2 = fail (trigger rollback)

Usage:
  python scripts/reviewer.py
  python scripts/reviewer.py --tail-lines 120
  python scripts/reviewer.py --wait 15   # Wait N seconds before checking (let bot stabilize)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
REVIEW_REPORT_FILE = OUTPUT_DIR / "review_report.json"
PREFLIGHT_REPORT_FILE = OUTPUT_DIR / "preflight_report.json"

SSH_KEY  = PROJECT_ROOT / ".shamrock_deploy_key"
SERVER   = "root@46.62.231.43"
REPO_DIR = "/root/shamrock-trading-bot"
SSH_OPTS = ["-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15"]

# Colours
USE_COLOUR = sys.stdout.isatty()
GREEN  = "\033[92m" if USE_COLOUR else ""
RED    = "\033[91m" if USE_COLOUR else ""
YELLOW = "\033[93m" if USE_COLOUR else ""
CYAN   = "\033[96m" if USE_COLOUR else ""
BOLD   = "\033[1m"  if USE_COLOUR else ""
RESET  = "\033[0m"  if USE_COLOUR else ""

PASS_MARK = f"{GREEN}✓ PASS{RESET}"
FAIL_MARK = f"{RED}✗ FAIL{RESET}"
WARN_MARK = f"{YELLOW}⚠ WARN{RESET}"

# ── Patterns that indicate fatal problems ────────────────────────────────────
CRITICAL_PATTERNS = [
    "Traceback (most recent call last)",
    "CRITICAL",
    "SystemExit",
    "ModuleNotFoundError",
    "ImportError",
    "SyntaxError",
    "KeyboardInterrupt",
    "Address already in use",
    "Permission denied",
    "docker: Error",
    "container exited",
    "OOMKilled",
]

# Patterns that indicate warnings (non-fatal)
WARN_PATTERNS = [
    "WARNING",
    "failed to fetch",
    "rate limit",
    "timeout",
    "retrying",
    "connection refused",
    "ssl.SSLCertVerificationError",
]

# Patterns that confirm the bot is alive and well
HEALTHY_PATTERNS = [
    "scan cycle complete",
    "Bot cycle",
    "Starting scan",
    "Shamrock Trading Bot",
    "Watchdog",
    "✅",
    "scanner started",
    "bot started",
    "cycle complete",
]


# ─────────────────────────────────────────────────────────────────────────────
# SSH helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ssh(command: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command on the Hetzner server via SSH. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["ssh"] + SSH_OPTS + [SERVER, command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def _header(text: str) -> None:
    width = 70
    print(f"\n{BOLD}{CYAN}{'─' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * width}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

def check_containers() -> dict:
    """Verify all Docker containers are in the 'Up' state."""
    _header("CHECK 1 / 3 — CONTAINER STATUS")
    rc, stdout, stderr = _ssh(f"cd {REPO_DIR} && docker compose ps --format json 2>/dev/null || docker compose ps")

    all_up = True
    containers = []
    issues = []

    # Try JSON format first (newer docker compose)
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    try:
        # docker compose ps --format json outputs one JSON object per line
        for line in lines:
            try:
                obj = json.loads(line)
                name   = obj.get("Name", obj.get("Service", "?"))
                state  = obj.get("State", obj.get("Status", "?"))
                health = obj.get("Health", "")
                is_up  = state.lower() in ("running", "up")
                containers.append({"name": name, "state": state, "health": health, "up": is_up})
                status_mark = PASS_MARK if is_up else FAIL_MARK
                print(f"  {status_mark}  {name:20s}  {state}  {health}")
                if not is_up:
                    all_up = False
                    issues.append(f"{name} is {state}")
            except json.JSONDecodeError:
                pass
    except Exception:
        pass

    # Fallback: parse table output
    if not containers:
        for line in lines:
            if "Up" in line or "running" in line.lower():
                print(f"  {PASS_MARK}  {line[:60]}")
            elif line and not line.startswith("NAME") and not line.startswith("---"):
                print(f"  {FAIL_MARK}  {line[:60]}")
                all_up = False
                issues.append(line[:80])

    if rc != 0:
        all_up = False
        issues.append(f"docker compose ps failed: {stderr.strip()[:200]}")
        print(f"  {FAIL_MARK}  Could not get container status: {stderr.strip()[:100]}")

    return {
        "name": "containers",
        "passed": all_up,
        "containers": containers,
        "issues": issues,
        "summary": "All containers running" if all_up else f"Issues: {'; '.join(issues)}",
    }


def check_bot_logs(tail_lines: int = 80) -> dict:
    """
    Tail bot logs and scan for critical errors, warnings, and health signals.
    """
    _header(f"CHECK 2 / 3 — BOT LOGS (last {tail_lines} lines)")
    rc, stdout, stderr = _ssh(
        f"cd {REPO_DIR} && docker compose logs --tail={tail_lines} bot 2>&1",
        timeout=30,
    )

    log_text = stdout + stderr
    lines = log_text.splitlines()

    found_critical = []
    found_warnings = []
    found_healthy  = []

    import re as _re
    for line in lines:
        ll = line.lower()

        # Detect log-level field (e.g. "| CRITICAL |" or "| WARNING |")
        lm = _re.search(r'\|\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|', line, _re.IGNORECASE)
        log_level = lm.group(1).upper() if lm else None

        # Positional criticals — hard failures regardless of message position
        POSITIONAL_CRITICALS = [
            "Traceback (most recent call last)",
            "SystemExit",
            "ModuleNotFoundError",
            "ImportError",
            "SyntaxError",
            "KeyboardInterrupt",
            "Address already in use",
            "docker: Error",
            "container exited",
            "OOMKilled",
        ]

        is_critical = (log_level == "CRITICAL") or any(p in line for p in POSITIONAL_CRITICALS)
        if is_critical:
            found_critical.append(line.strip()[:200])
        else:
            WARN_KEYWORDS = ["failed to fetch", "rate limit", "timeout", "retrying",
                             "connection refused", "ssl.SSLCertVerificationError"]
            is_warn = (log_level in ("WARNING", "ERROR")) or any(k in ll for k in WARN_KEYWORDS)
            if is_warn:
                found_warnings.append(line.strip()[:200])

        for p in HEALTHY_PATTERNS:
            if p.lower() in ll:
                found_healthy.append(line.strip()[:200])
                break

    # Deduplicate while preserving order
    found_critical = list(dict.fromkeys(found_critical))[:10]
    found_warnings = list(dict.fromkeys(found_warnings))[:10]
    found_healthy  = list(dict.fromkeys(found_healthy))[:5]

    # Print last N lines of log
    display_lines = lines[-40:] if len(lines) > 40 else lines
    for line in display_lines:
        colour = ""
        stripped = line.strip()
        if any(p.lower() in stripped.lower() for p in CRITICAL_PATTERNS):
            colour = RED
        elif any(p.lower() in stripped.lower() for p in WARN_PATTERNS):
            colour = YELLOW
        elif any(p.lower() in stripped.lower() for p in HEALTHY_PATTERNS):
            colour = GREEN
        print(f"  {colour}{stripped[:120]}{RESET}")

    print()
    if found_critical:
        print(f"  {FAIL_MARK}  {len(found_critical)} critical issue(s) detected in logs")
    if found_warnings:
        print(f"  {WARN_MARK}  {len(found_warnings)} warning(s) in logs")
    if found_healthy:
        print(f"  {PASS_MARK}  Bot shows healthy activity signals")

    passed    = len(found_critical) == 0
    has_warns = len(found_warnings) > 0

    return {
        "name": "bot_logs",
        "passed": passed,
        "has_warnings": has_warns,
        "critical_lines": found_critical,
        "warning_lines": found_warnings,
        "healthy_signals": found_healthy,
        "log_lines": len(lines),
        "summary": (
            f"{len(found_critical)} critical error(s)"
            if not passed else
            ("All clear (with warnings)" if has_warns else "Clean — bot looks healthy")
        ),
    }


def check_git_state() -> dict:
    """Verify the server is on the expected commit."""
    _header("CHECK 3 / 3 — SERVER GIT STATE")

    # Get local commit
    try:
        local_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True
        ).strip()
        local_msg = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=str(PROJECT_ROOT), text=True
        ).strip()
    except Exception:
        local_sha = "unknown"
        local_msg = ""

    # Get server commit
    rc, stdout, stderr = _ssh(f"cd {REPO_DIR} && git rev-parse --short HEAD && git log -1 --pretty=%s")
    server_lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    server_sha = server_lines[0] if server_lines else "unknown"
    server_msg = server_lines[1] if len(server_lines) > 1 else ""

    in_sync = local_sha != "unknown" and server_sha == local_sha

    print(f"  Local:  {CYAN}{local_sha}{RESET}  {local_msg}")
    print(f"  Server: {CYAN}{server_sha}{RESET}  {server_msg}")
    print()

    if in_sync:
        print(f"  {PASS_MARK}  Server is on the expected commit.")
    else:
        print(f"  {FAIL_MARK}  SHA mismatch — server may still be on old code.")

    return {
        "name": "git_state",
        "passed": in_sync,
        "local_sha": local_sha,
        "server_sha": server_sha,
        "local_message": local_msg,
        "server_message": server_msg,
        "summary": "In sync" if in_sync else f"Mismatch: local={local_sha}, server={server_sha}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate verdict
# ─────────────────────────────────────────────────────────────────────────────

def _determine_grade(checks: dict) -> tuple[str, str]:
    """
    Compute grade and strategy:
      pass  — Everything is clean.
      warn  — Running but with non-fatal issues.
      fail  — Critical problems. Rollback recommended.

    Returns (grade, strategy)
    """
    containers_ok = checks["containers"]["passed"]
    logs_ok       = checks["bot_logs"]["passed"]
    git_ok        = checks["git_state"]["passed"]
    has_warns     = checks["bot_logs"].get("has_warnings", False)

    if not containers_ok or not logs_ok:
        return "fail", "rollback"
    if not git_ok:
        return "fail", "rollback"
    if has_warns:
        return "warn", "monitor"
    return "pass", "continue"


def run_review(tail_lines: int = 80, wait_seconds: int = 0) -> int:
    """Run all review checks, print report, write JSON. Returns exit code."""
    started_at = datetime.now(timezone.utc)

    banner = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════╗
║          🔍  SHAMROCK TRADING BOT — POST-DEPLOY REVIEW               ║
║          "Get It Right" deployment reviewer                           ║
╚══════════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

    if wait_seconds > 0:
        print(f"  {YELLOW}Waiting {wait_seconds}s for bot to stabilize...{RESET}")
        time.sleep(wait_seconds)

    # Load preflight context if available
    preflight_context = None
    if PREFLIGHT_REPORT_FILE.exists():
        try:
            preflight_context = json.loads(PREFLIGHT_REPORT_FILE.read_text())
            pf_git = preflight_context.get("git", {})
            print(f"  {BOLD}Preflight:{RESET} {pf_git.get('sha', '?')} — {pf_git.get('message', '?')}")
        except Exception:
            pass

    # Run checks
    container_result = check_containers()
    logs_result      = check_bot_logs(tail_lines=tail_lines)
    git_result       = check_git_state()

    checks = {
        "containers": container_result,
        "bot_logs":   logs_result,
        "git_state":  git_result,
    }

    grade, strategy = _determine_grade(checks)

    # ── Final verdict ────────────────────────────────────────────────────────
    _header("REVIEW VERDICT")

    for name, c in checks.items():
        mark = PASS_MARK if c["passed"] else FAIL_MARK
        print(f"  {mark}  {name.upper():15s}  {c['summary']}")

    print()

    if grade == "pass":
        print(f"{BOLD}{GREEN}  ✅ GRADE: PASS — Deployment is healthy. No action needed.{RESET}")
        exit_code = 0
    elif grade == "warn":
        print(f"{BOLD}{YELLOW}  ⚠️  GRADE: WARN — Bot is running but has warnings. Monitor closely.{RESET}")
        exit_code = 1
    else:
        print(f"{BOLD}{RED}  ❌ GRADE: FAIL — Critical issues detected. Recommend rollback.{RESET}")
        print(f"{BOLD}{RED}     Run: python scripts/rollback.py{RESET}")
        exit_code = 2

    # Generate structured feedback (the "bridge" to the next iteration)
    feedback_lines = []
    for name, c in checks.items():
        if not c["passed"]:
            feedback_lines.append(f"[{name}] FAILED: {c['summary']}")
            if "issues" in c:
                feedback_lines.extend([f"  - {i}" for i in c["issues"][:5]])
            if "critical_lines" in c:
                feedback_lines.extend([f"  - LOG: {l}" for l in c["critical_lines"][:5]])
    if logs_result.get("has_warnings"):
        feedback_lines.append(f"[bot_logs] WARNINGS: {len(logs_result['warning_lines'])} warning(s)")
        feedback_lines.extend([f"  - {l}" for l in logs_result["warning_lines"][:3]])

    feedback = "\n".join(feedback_lines) if feedback_lines else "No issues found."

    # ── Write JSON report ────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "grade": grade,
        "strategy": strategy,
        "exit_code": exit_code,
        "timestamp": started_at.isoformat(),
        "feedback": feedback,
        "checks": checks,
        "preflight_sha": preflight_context.get("git", {}).get("sha") if preflight_context else None,
    }
    REVIEW_REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(f"\n  Report written → {REVIEW_REPORT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"\n  {BOLD}Feedback (for next iteration):{RESET}")
    print(f"  {YELLOW}{feedback[:500]}{RESET}")
    print()

    return exit_code


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shamrock post-deploy reviewer")
    parser.add_argument("--tail-lines", type=int, default=80, help="Log lines to review (default: 80)")
    parser.add_argument("--wait", type=int, default=0, help="Seconds to wait before reviewing (default: 0)")
    args = parser.parse_args()
    sys.exit(run_review(tail_lines=args.tail_lines, wait_seconds=args.wait))
