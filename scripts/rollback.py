#!/usr/bin/env python3
"""
scripts/rollback.py — "Get It Right" rollback agent.

The refactor step — analogous to the refactorer.md in get-it-right.
Does NOT reimplement anything. It ONLY undoes the bad deployment
by reverting the server to the previously known-good git commit.

Strategy:
  1. Find the last commit on the server that was tagged as "good"
     (via git log looking for last non-current commit)
  2. git reset --hard to that commit on the server
  3. Rebuild and restart Docker containers
  4. Run a quick sanity check (container up + brief log tail)
  5. Write rollback_report.json with what happened

Exit codes:
  0 — Rollback successful, server restored to previous commit
  1 — Rollback failed (requires manual intervention)

Usage:
  python scripts/rollback.py
  python scripts/rollback.py --dry-run   # Show what would happen, don't do it
  python scripts/rollback.py --to SHA    # Roll back to a specific commit SHA
"""

import argparse
import json
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
ROLLBACK_REPORT_FILE = OUTPUT_DIR / "rollback_report.json"
REVIEW_REPORT_FILE   = OUTPUT_DIR / "review_report.json"

SSH_KEY  = PROJECT_ROOT / ".shamrock_deploy_key"
SERVER   = "root@178.156.179.237"
REPO_DIR = "/opt/shamrock-trading-bot"
SSH_OPTS = ["-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15"]

# Colours
USE_COLOUR = sys.stdout.isatty()
GREEN  = "\033[92m" if USE_COLOUR else ""
RED    = "\033[91m" if USE_COLOUR else ""
YELLOW = "\033[93m" if USE_COLOUR else ""
CYAN   = "\033[96m" if USE_COLOUR else ""
BOLD   = "\033[1m"  if USE_COLOUR else ""
RESET  = "\033[0m"  if USE_COLOUR else ""


def _header(text: str) -> None:
    width = 70
    print(f"\n{BOLD}{CYAN}{'─' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * width}{RESET}")


def _ssh(command: str, timeout: int = 120) -> tuple[int, str, str]:
    result = subprocess.run(
        ["ssh"] + SSH_OPTS + [SERVER, command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _ssh_stream(command: str, timeout: int = 300) -> int:
    """Run SSH command with live output streaming to stdout."""
    result = subprocess.run(
        ["ssh"] + SSH_OPTS + [SERVER, command],
        timeout=timeout,
    )
    return result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# Steps
# ─────────────────────────────────────────────────────────────────────────────

def get_server_git_history() -> list[dict]:
    """Fetch last 5 commits from the server for choosing rollback target."""
    _header("STEP 1 / 5 — INSPECT SERVER GIT HISTORY")
    rc, stdout, stderr = _ssh(
        f"cd {REPO_DIR} && git log --oneline -5 --format='%H|%h|%s|%ci'"
    )
    commits = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) >= 3:
            commits.append({
                "sha":     parts[0].strip(),
                "short":   parts[1].strip(),
                "message": parts[2].strip(),
                "date":    parts[3].strip() if len(parts) > 3 else "",
            })

    for i, c in enumerate(commits[:5]):
        tag = f"{GREEN}(current){RESET}" if i == 0 else f"{CYAN}(rollback target){RESET}" if i == 1 else ""
        print(f"  {'HEAD' if i == 0 else f'HEAD~{i}':6s}  {CYAN}{c['short']}{RESET}  {c['message'][:60]}  {tag}")

    return commits


def perform_rollback(target_sha: str, dry_run: bool = False) -> dict:
    """Reset the server repo to target_sha, rebuild, restart."""

    _header("STEP 2 / 5 — STOP CONTAINERS")
    if dry_run:
        print(f"  {YELLOW}[DRY RUN] Would run: docker compose down{RESET}")
    else:
        rc, out, err = _ssh(f"cd {REPO_DIR} && docker compose down")
        if rc == 0:
            print(f"  {GREEN}✓ Containers stopped{RESET}")
        else:
            print(f"  {YELLOW}⚠ docker compose down returned {rc}: {err[:100]}{RESET}")

    _header(f"STEP 3 / 5 — GIT RESET TO {target_sha[:8]}")
    reset_cmd = f"cd {REPO_DIR} && git fetch --all && git reset --hard {target_sha}"
    if dry_run:
        print(f"  {YELLOW}[DRY RUN] Would run: {reset_cmd}{RESET}")
        return {"sha_restored": target_sha, "dry_run": True, "success": True}
    else:
        rc, out, err = _ssh(reset_cmd)
        if rc != 0:
            print(f"  {RED}✗ git reset failed: {err[:200]}{RESET}")
            return {"sha_restored": None, "success": False, "error": err[:200]}
        print(f"  {GREEN}✓ Server reset to {target_sha[:8]}{RESET}")
        print(f"  {out[:200]}")

    _header("STEP 4 / 5 — REBUILD & RESTART")
    rebuild_cmd = (
        f"cd {REPO_DIR} && "
        f"docker compose build --no-cache 2>&1 | tail -5 && "
        f"docker compose up -d"
    )
    print(f"  Rebuilding Docker image (this takes ~60-90s)...\n")
    rc = _ssh_stream(rebuild_cmd, timeout=300)
    if rc != 0:
        print(f"\n  {RED}✗ Rebuild failed (exit {rc}){RESET}")
        return {"sha_restored": target_sha, "success": False, "error": f"docker build failed (exit {rc})"}
    print(f"\n  {GREEN}✓ Rebuild complete, containers started{RESET}")

    return {"sha_restored": target_sha, "success": True, "dry_run": False}


def verify_rollback() -> dict:
    """Quick sanity check after rollback."""
    _header("STEP 5 / 5 — VERIFY ROLLBACK")

    time.sleep(10)  # Give containers a moment to start

    # Check containers
    rc, stdout, _ = _ssh(f"cd {REPO_DIR} && docker compose ps")
    all_up = "Up" in stdout or "running" in stdout.lower()
    for line in stdout.splitlines():
        colour = GREEN if ("Up" in line or "running" in line.lower()) else RED
        print(f"  {colour}{line[:80]}{RESET}")

    # Tail logs briefly
    rc2, logs, _ = _ssh(f"cd {REPO_DIR} && docker compose logs --tail=20 bot 2>&1")
    print()
    for line in logs.splitlines()[-15:]:
        print(f"  {CYAN}{line[:100]}{RESET}")

    has_crash = any(p.lower() in logs.lower() for p in [
        "traceback", "critical", "systemExit", "ModuleNotFoundError"
    ])

    passed = all_up and not has_crash
    print()
    if passed:
        print(f"  {GREEN}✓ Rollback verified — bot appears healthy on previous commit{RESET}")
    else:
        print(f"  {RED}✗ Rollback verification failed — manual intervention required{RESET}")

    return {
        "passed": passed,
        "containers_up": all_up,
        "has_crash_in_logs": has_crash,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run_rollback(target_sha: str | None = None, dry_run: bool = False) -> int:
    started_at = datetime.now(timezone.utc)

    banner = f"""
{BOLD}{RED}╔══════════════════════════════════════════════════════════════════════╗
║          🔄  SHAMROCK TRADING BOT — ROLLBACK                         ║
║          "Get It Right" rollback agent — reverting bad deploy        ║
╚══════════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

    if dry_run:
        print(f"  {YELLOW}*** DRY RUN MODE — No changes will be made ***{RESET}\n")

    # Load previous review report for context
    review_context = None
    if REVIEW_REPORT_FILE.exists():
        try:
            review_context = json.loads(REVIEW_REPORT_FILE.read_text())
            print(f"  {BOLD}Rolling back due to:{RESET}")
            print(f"  {RED}{review_context.get('feedback', 'No feedback available')[:400]}{RESET}\n")
        except Exception:
            pass

    # Get server history to find rollback target
    commits = get_server_git_history()
    if not commits:
        print(f"  {RED}✗ Could not fetch server git history. Aborting.{RESET}")
        return 1

    current_sha = commits[0]["sha"]
    current_short = commits[0]["short"]

    if target_sha:
        rollback_to = target_sha
    elif len(commits) >= 2:
        rollback_to = commits[1]["sha"]  # Previous commit
    else:
        print(f"  {RED}✗ No previous commit available to roll back to.{RESET}")
        return 1

    rollback_short = rollback_to[:8]
    print(f"\n  {BOLD}Current commit:{RESET}  {CYAN}{current_short}{RESET}  ({commits[0]['message'][:50]})")
    print(f"  {BOLD}Rolling back:{RESET}   {CYAN}{rollback_short}{RESET}")

    if not dry_run:
        confirm = input(f"\n  {YELLOW}Confirm rollback? (y/N): {RESET}").strip().lower()
        if confirm != "y":
            print(f"  {YELLOW}Rollback cancelled.{RESET}")
            return 0

    # Perform rollback
    rollback_result = perform_rollback(rollback_to, dry_run=dry_run)
    if not rollback_result.get("success"):
        print(f"\n  {RED}✗ Rollback FAILED: {rollback_result.get('error', 'unknown')}{RESET}")
        return 1

    # Verify
    if not dry_run:
        verify_result = verify_rollback()
    else:
        verify_result = {"passed": True, "dry_run": True}

    # Write report
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": started_at.isoformat(),
        "dry_run": dry_run,
        "reverted_from": current_sha,
        "reverted_to": rollback_to,
        "rollback_result": rollback_result,
        "verification": verify_result,
        "review_context": review_context.get("feedback") if review_context else None,
        "success": verify_result.get("passed", False),
    }
    ROLLBACK_REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(f"\n  Report written → {ROLLBACK_REPORT_FILE.relative_to(PROJECT_ROOT)}")

    if verify_result.get("passed"):
        print(f"\n{BOLD}{GREEN}  ✅ ROLLBACK SUCCESS — Server restored. Now fix the code and re-deploy.{RESET}")
        print(f"  {YELLOW}  Tip: Check output/review_report.json for what caused the failure.{RESET}")
        return 0
    else:
        print(f"\n{BOLD}{RED}  ❌ ROLLBACK VERIFICATION FAILED — Manual intervention required.{RESET}")
        print(f"  {YELLOW}  SSH in: ssh -i .shamrock_deploy_key root@178.156.179.237{RESET}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shamrock rollback agent")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without doing it")
    parser.add_argument("--to", dest="sha", default=None, help="Roll back to a specific commit SHA")
    args = parser.parse_args()
    sys.exit(run_rollback(target_sha=args.sha, dry_run=args.dry_run))
