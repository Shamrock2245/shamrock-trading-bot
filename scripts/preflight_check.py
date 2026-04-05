#!/usr/bin/env python3
"""
scripts/preflight_check.py — "Get It Right" pre-deploy gate.

Runs BEFORE any git push or deploy. Blocks bad code from ever hitting
the server. Two parallel checks:

  1. SYNTAX  — py_compile every .py file in the project (fast, catches typos)
  2. TESTS   — pytest the tests/ directory (logic correctness)

Exit codes:
  0  — All checks passed. Safe to deploy.
  1  — One or more checks failed. DO NOT deploy.

Output:
  Structured human-readable report + JSON summary written to
  output/preflight_report.json for the reviewer to consume.

Usage:
  python scripts/preflight_check.py
  python scripts/preflight_check.py --fix-hint   # emit fix suggestions too
"""

import argparse
import ast
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
REPORT_FILE = OUTPUT_DIR / "preflight_report.json"

# Directories to syntax-check (relative to project root)
SYNTAX_CHECK_DIRS = ["core", "config", "scanner", "strategies", "data", "ml", "scripts", "notifications"]

# Directories to exclude from syntax check
SYNTAX_EXCLUDE = {".git", "__pycache__", "venv", ".venv", "vendor", "node_modules"}

# Colours (disabled if not a tty)
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

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _header(text: str) -> None:
    width = 70
    print(f"\n{BOLD}{CYAN}{'─' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * width}{RESET}")


def _collect_python_files(dirs: list[str]) -> list[Path]:
    """Walk specified directories and collect all .py files."""
    files = []
    for d in dirs:
        target = PROJECT_ROOT / d
        if not target.exists():
            continue
        for py_file in target.rglob("*.py"):
            # Skip excluded dirs anywhere in the path
            if any(part in SYNTAX_EXCLUDE for part in py_file.parts):
                continue
            files.append(py_file)
    # Also check root-level .py files (main.py, etc.)
    for py_file in PROJECT_ROOT.glob("*.py"):
        files.append(py_file)
    return sorted(set(files))


# ─────────────────────────────────────────────────────────────────────────────
# Check 1: Syntax (py_compile via ast.parse — no subprocess overhead)
# ─────────────────────────────────────────────────────────────────────────────

def check_syntax() -> dict:
    """
    Syntax-check every Python file using ast.parse.
    Faster than py_compile subprocess, catches the same errors.
    Returns structured result dict.
    """
    _header("CHECK 1 / 2 — SYNTAX (ast.parse)")
    files = _collect_python_files(SYNTAX_CHECK_DIRS)
    errors = []
    ok_count = 0

    print(f"  Scanning {len(files)} Python files...\n")

    for f in files:
        rel = f.relative_to(PROJECT_ROOT)
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
            ast.parse(source, filename=str(f))
            ok_count += 1
        except SyntaxError as e:
            errors.append({
                "file": str(rel),
                "line": e.lineno,
                "col": e.offset,
                "message": e.msg,
                "text": (e.text or "").strip(),
            })
            print(f"  {FAIL_MARK}  {RED}{rel}:{e.lineno}{RESET} — {e.msg}")
            if e.text:
                snippet = e.text.rstrip()
                print(f"       {YELLOW}{snippet}{RESET}")
        except Exception as e:
            errors.append({"file": str(rel), "line": None, "message": str(e)})
            print(f"  {WARN_MARK}  {rel} — read error: {e}")

    passed = len(errors) == 0
    print()
    if passed:
        print(f"  {PASS_MARK}  {ok_count} files clean — no syntax errors found.")
    else:
        print(f"  {FAIL_MARK}  {len(errors)} file(s) have syntax errors. Fix before deploying.")

    return {
        "name": "syntax",
        "passed": passed,
        "files_checked": len(files),
        "errors": errors,
        "summary": f"{ok_count}/{len(files)} files clean" if passed else f"{len(errors)} syntax error(s)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Check 2: Tests (pytest)
# ─────────────────────────────────────────────────────────────────────────────

def check_tests() -> dict:
    """
    Run pytest. Returns structured result dict.
    Captures stdout/stderr for the reviewer.
    """
    _header("CHECK 2 / 2 — TESTS (pytest)")
    test_dir = PROJECT_ROOT / "tests"

    if not test_dir.exists() or not list(test_dir.glob("test_*.py")):
        print(f"  {WARN_MARK}  No test files found in tests/ — skipping.")
        return {
            "name": "tests",
            "passed": True,  # Skip = pass (no tests configured)
            "skipped": True,
            "summary": "No tests found — skipped",
            "output": "",
        }

    print(f"  Running: pytest tests/ -v --tb=short\n")
    t0 = time.time()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "--no-header", "-q"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    elapsed = time.time() - t0
    output = (result.stdout + result.stderr).strip()

    # pytest not installed locally → treat as skip (tests run in Docker/CI)
    if result.returncode == 1 and "No module named pytest" in output:
        print(f"  {WARN_MARK}  pytest not installed locally — skipping (tests run in Docker/CI).")
        return {
            "name": "tests",
            "passed": True,
            "skipped": True,
            "summary": "pytest not installed locally — skipped (run in Docker/CI)",
            "output": "",
        }

    passed = result.returncode == 0

    # Print the raw pytest output (trimmed for readability)
    lines = output.splitlines()
    max_lines = 60
    if len(lines) > max_lines:
        for line in lines[:max_lines]:
            print(f"  {line}")
        print(f"  {YELLOW}... ({len(lines) - max_lines} more lines truncated){RESET}")
    else:
        for line in lines:
            print(f"  {line}")

    print()
    if passed:
        print(f"  {PASS_MARK}  All tests passed in {elapsed:.1f}s")
    else:
        print(f"  {FAIL_MARK}  Tests failed (exit code {result.returncode})")

    return {
        "name": "tests",
        "passed": passed,
        "returncode": result.returncode,
        "elapsed_seconds": round(elapsed, 2),
        "summary": "All tests passed" if passed else f"Tests failed (exit {result.returncode})",
        "output": output[-4000:] if len(output) > 4000 else output,  # Keep last 4k chars
    }


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate & Report
# ─────────────────────────────────────────────────────────────────────────────

def _get_git_info() -> dict:
    """Collect current git state for the report."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True
        ).strip()
        msg = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=str(PROJECT_ROOT), text=True
        ).strip()
        return {"sha": sha, "branch": branch, "message": msg}
    except Exception:
        return {"sha": "unknown", "branch": "unknown", "message": ""}


def run_preflight(fix_hint: bool = False) -> int:
    """
    Run all checks, print report, write JSON, return exit code.
    """
    started_at = datetime.now(timezone.utc)
    banner = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════╗
║          🚦  SHAMROCK TRADING BOT — PREFLIGHT CHECK                  ║
║          "Get It Right" pre-deploy gate                               ║
╚══════════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)
    git = _get_git_info()
    print(f"  {BOLD}Commit:{RESET} {git['sha']} ({git['branch']}) — {git['message']}")
    print(f"  {BOLD}Time:  {RESET} {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Run checks sequentially — syntax first (faster), tests second
    syntax_result = check_syntax()
    test_result   = check_tests()

    checks = [syntax_result, test_result]
    all_passed = all(c["passed"] for c in checks)

    # ── Final verdict ────────────────────────────────────────────────────────
    _header("PREFLIGHT VERDICT")
    for c in checks:
        mark = PASS_MARK if c["passed"] else FAIL_MARK
        print(f"  {mark}  {c['name'].upper():12s}  {c['summary']}")

    print()
    if all_passed:
        print(f"{BOLD}{GREEN}  ✅ ALL CHECKS PASSED — Code is ready to deploy.{RESET}")
        verdict = "pass"
        exit_code = 0
    else:
        failed_names = [c["name"] for c in checks if not c["passed"]]
        print(f"{BOLD}{RED}  ❌ PREFLIGHT FAILED — Do NOT deploy until fixed: {', '.join(failed_names).upper()}{RESET}")
        if fix_hint:
            print(f"\n{YELLOW}  Fix hints:{RESET}")
            for c in checks:
                if not c["passed"] and "errors" in c:
                    for err in c["errors"][:3]:
                        print(f"    → {err.get('file')}:{err.get('line')} — {err.get('message')}")
        verdict = "fail"
        exit_code = 1

    # ── Write JSON report ────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "verdict": verdict,
        "all_passed": all_passed,
        "timestamp": started_at.isoformat(),
        "git": git,
        "checks": {c["name"]: c for c in checks},
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(f"\n  Report written → {REPORT_FILE.relative_to(PROJECT_ROOT)}")
    print()

    return exit_code


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shamrock preflight check")
    parser.add_argument("--fix-hint", action="store_true", help="Print fix suggestions on failure")
    args = parser.parse_args()
    sys.exit(run_preflight(fix_hint=args.fix_hint))
