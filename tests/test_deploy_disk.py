"""Deploy disk-space guards.

The paper server (75G) failed image export with ENOSPC because:

* `.dockerignore` `*.db` matches only the context root. `data/optuna_studies.db`
  was sent in the build context (241MB) and unpacked once per service.
* `docker compose build` built bot, dashboard, auto-tuner, health, and
  candle-recorder in parallel, so that layer was extracted five times.
* The pre-build prune used `until=24h`, which freed nothing when the cache
  was from a failed build the same day, and the post-deploy prune never ran.

Runtime files stay on the bind mounts. These tests do not need Docker.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERIGNORE = ROOT / ".dockerignore"
COMPOSE = ROOT / "docker-compose.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DISK_SCRIPT = ROOT / "scripts" / "deploy_disk.sh"

# Characters that are special in a regex but not in Docker's filepath patterns.
_REGEX_ESCAPE = set(".+()|{}$")


def _clean(pattern: str) -> str:
    """Approximate Go's filepath.Clean for slash-separated patterns."""
    pattern = pattern.strip().replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for part in pattern.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _compile(pattern: str) -> re.Pattern[str]:
    """Compile one dockerignore pattern the way moby/patternmatcher does.

    `*` does not match `/`. `**` matches any number of directories, including
    zero. A trailing slash is removed by Clean, and a matching parent directory
    excludes its children.
    """
    parts = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                i += 2
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
                if i >= len(pattern):
                    parts.append(".*")
                else:
                    parts.append("(?:.*/)?")
                continue
            parts.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            parts.append("[^/]")
            i += 1
            continue
        if ch == "\\" and i + 1 < len(pattern):
            parts.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if ch in _REGEX_ESCAPE:
            parts.append("\\" + ch)
        else:
            parts.append(ch)
        i += 1
    parts.append("$")
    return re.compile("".join(parts))


def _patterns(text: str) -> list[tuple[bool, re.Pattern[str]]]:
    compiled: list[tuple[bool, re.Pattern[str]]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cleaned = _clean(line)
        if not cleaned or cleaned == ".":
            continue
        exclusion = cleaned.startswith("!")
        if exclusion:
            cleaned = _clean(cleaned[1:])
            if not cleaned or cleaned == ".":
                continue
        compiled.append((exclusion, _compile(cleaned)))
    return compiled


def dockerignore_matches(path: str, text: str) -> bool:
    """Return True when Docker would exclude `path` from the build context."""
    path = _clean(path)
    if not path or path == ".":
        return False
    parents: list[str] = []
    acc: list[str] = []
    for part in path.split("/")[:-1]:
        acc.append(part)
        parents.append("/".join(acc))

    matched = False
    for exclusion, pattern in _patterns(text):
        if exclusion != matched:
            continue
        hit = pattern.search(path) is not None
        if not hit:
            hit = any(pattern.search(parent) is not None for parent in parents)
        if hit:
            matched = not exclusion
    return matched


def _ignored(path: str) -> bool:
    return dockerignore_matches(path, DOCKERIGNORE.read_text())


def test_star_does_not_match_across_directories():
    """The bug: a root-only `*.db` leaves data/optuna_studies.db in the context."""
    assert dockerignore_matches("optuna_studies.db", "*.db")
    assert not dockerignore_matches("data/optuna_studies.db", "*.db")
    assert dockerignore_matches("data/optuna_studies.db", "**/*.db")
    assert dockerignore_matches("optuna_studies.db", "**/*.db")
    # Docker's own example: `*.md` ignores the root file, not docs/README.md.
    assert dockerignore_matches("README.md", "*.md")
    assert not dockerignore_matches("docs/README.md", "*.md")
    assert dockerignore_matches("pkg/main.go", "**/*.go")
    assert dockerignore_matches("main.go", "**/*.go")


def test_runtime_data_is_excluded_from_the_image():
    excluded = [
        "data/optuna_studies.db",
        "data/shamrock_trading.db",
        "data/nested/studies.db",
        "optuna_studies.db",
        "data/optuna_studies.db-wal",
        "data/optuna_studies.db-shm",
        "data/optuna_studies.db-journal",
        "data/candles/BTC_1h.csv",
        "data/candles/asset_ctxs.csv",
        "data/dashboard/bot_status.json",
        "data/dashboard/hot_streak.json",
        "data/backtest/report.html",
        "data/trades.jsonl",
        "logs/bot.log",
        "output/trades.json",
        "output/trade_ledger.jsonl",
        "output/hl_fills.jsonl",
        ".env",
        ".env.local",
        ".git/config",
        "tests/test_deploy_disk.py",
        "core/__pycache__/foo.pyc",
        "web/.web/build/index.js",
        "web/node_modules/react/index.js",
    ]
    missed = [path for path in excluded if not _ignored(path)]
    assert missed == []


def test_application_code_is_still_copied():
    """Source under data/ is the import package. Runtime db, candles, and
    dashboard state are the files the bind mount supplies."""
    included = [
        "main.py",
        "requirements.txt",
        "Dockerfile",
        "config/settings.py",
        "data/__init__.py",
        "data/models.py",
        "data/http_session.py",
        "data/providers/__init__.py",
        "data/providers/coingecko.py",
        "scripts/health_check.py",
        "scripts/auto_tuner_service.py",
        "scripts/paper_trade.py",
        "backtest/candle_recorder.py",
        "web/web/web.py",
        "core/hl_perps_scanner.py",
        ".env.example",
    ]
    excluded = [path for path in included if _ignored(path)]
    assert excluded == []


def test_compose_shares_one_image_and_keeps_data_mounts():
    text = COMPOSE.read_text()
    assert text.count("<<: *app-image") == 7
    assert text.count("image: shamrock-app:runtime") == 1
    assert text.count("target: runtime") == 1
    assert "pull_policy: never" in text
    for service in (
        "bot:",
        "paper-trader:",
        "dashboard:",
        "health:",
        "auto-tuner:",
        "candle-recorder:",
        "paper-tuner:",
    ):
        assert service in text
    # db stays the stock alpine volume holder, not the app image.
    assert "image: alpine:3.18" in text
    assert text.count("./data:/app/data") == 7
    assert "./logs:/app/logs" in text
    assert "./output:/app/output" in text
    assert "db-data:/data" in text


def test_workflow_prunes_before_a_single_build_and_keeps_env_patches():
    text = WORKFLOW.read_text()
    pre = text.index("bash scripts/deploy_disk.sh prebuild")
    build = text.index("docker compose build --pull bot")
    up = text.index("docker compose up -d --remove-orphans")
    post = text.index("bash scripts/deploy_disk.sh postdeploy")
    assert pre < build < up < post
    assert "docker compose build --pull\n" not in text
    assert "until=24h" not in text
    assert "--volumes" not in text
    assert "volume prune" not in text
    # Hard constraints: the deploy's .env patch block is untouched.
    assert "s/^MODE=.*/MODE=paper/" in text
    assert "s/^PAPER_MODE_LOCKED=.*/PAPER_MODE_LOCKED=true/" in text
    assert "s/^MORALIS_ENABLED=.*/MORALIS_ENABLED=false/" in text
    assert "s/^RSI_DIP_V1_ENABLED=.*/RSI_DIP_V1_ENABLED=true/" in text
    assert "command_timeout: 40m" in text


def _script_commands(script: str) -> str:
    return "\n".join(
        line for line in script.splitlines() if not line.strip().startswith("#")
    )


def test_disk_script_never_prunes_volumes():
    commands = _script_commands(DISK_SCRIPT.read_text())
    assert "--volumes" not in commands
    assert "volume prune" not in commands
    assert "volume rm" not in commands
    assert "until=" not in commands
    assert "docker builder prune -af" in commands
    assert "docker image prune -af" in commands
    mode = DISK_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def _run_disk(mode: str, avail_kb: int, min_free_gb: str | None = None):
    log = ROOT / ".pytest_cache" / "docker-invocations.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")
    bindir = log.parent / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "docker").write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            echo "$@" >> {log}
            exit 0
            """
        )
    )
    (bindir / "df").write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            if [ "$1" = "-Pk" ]; then
              echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
              echo "/dev/sda1 70000000 20000000 {avail_kb} 30% /"
            else
              echo "Filesystem Size Used Avail Use% Mounted on"
              echo "/dev/sda1 75G 25G 50G 33% /"
            fi
            """
        )
    )
    os.chmod(bindir / "docker", 0o755)
    os.chmod(bindir / "df", 0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    if min_free_gb is None:
        env.pop("DEPLOY_MIN_FREE_GB", None)
    else:
        env["DEPLOY_MIN_FREE_GB"] = min_free_gb
    result = subprocess.run(
        ["bash", str(DISK_SCRIPT), mode],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    invocations = [line.strip() for line in log.read_text().splitlines() if line.strip()]
    return result, invocations


def test_prebuild_prunes_then_fails_when_disk_is_still_low():
    result, invocations = _run_disk("prebuild", avail_kb=1024 * 1024)
    assert result.returncode == 1
    assert "Need at least 12GB free" in result.stdout
    assert "no volumes were pruned" in result.stdout
    assert invocations[0] == "builder prune -af"
    assert invocations[1] == "image prune -f"
    assert all("volume" not in call for call in invocations)


def test_prebuild_passes_when_enough_space_is_free():
    result, invocations = _run_disk("prebuild", avail_kb=40 * 1024 * 1024)
    assert result.returncode == 0, result.stderr
    assert "Pre-build disk check OK" in result.stdout
    assert "builder prune -af" in invocations
    assert any(call.startswith("system df") for call in invocations)


def test_min_free_gb_override_is_not_an_env_file_setting():
    result, _invocations = _run_disk(
        "prebuild", avail_kb=2 * 1024 * 1024, min_free_gb="1"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "minimum 1GB" in result.stdout


def test_postdeploy_prunes_unused_images_and_cache():
    result, invocations = _run_disk("postdeploy", avail_kb=40 * 1024 * 1024)
    assert result.returncode == 0, result.stderr
    assert "image prune -af" in invocations
    assert "builder prune -af" in invocations
    assert all("volume" not in call and "until" not in call for call in invocations)


def test_disk_script_usage():
    result = subprocess.run(
        ["bash", str(DISK_SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "prebuild|postdeploy" in result.stderr
