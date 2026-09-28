"""tests/test_predator_v1.py — Predator v1 gate unit tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from core.predator_v1 import evaluate_entry

ET = ZoneInfo("America/New_York")


def _noon_et():
    return datetime(2026, 7, 21, 3, 0, tzinfo=ET)


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "false")
    v = evaluate_entry("TRB", "long", "Choppy", persist=False)
    assert v.allow is True
    assert v.reason == "predator_disabled"


def test_hard_ban_trb(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    v = evaluate_entry("TRB", "long", "Trending", now=_noon_et(), persist=False)
    assert v.allow is False
    assert v.reason == "hard_banned"


def test_grass_hard_banned(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    v = evaluate_entry("GRASS", "long", "Trending", now=_noon_et(), persist=False)
    assert v.allow is False
    assert v.reason == "hard_banned"


def test_allowlist_miss(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE,VVV")
    v = evaluate_entry("DOGE", "long", "Trending", now=_noon_et(), persist=False)
    assert v.allow is False
    assert v.reason == "not_on_allowlist"


def test_chop_is_a_skip_not_a_half_size(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("PREDATOR_EXPANSION_ONLY", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    v = evaluate_entry("AAVE", "long", "Choppy", now=_noon_et(), persist=False)
    assert v.allow is False
    assert v.reason == "regime_chop"


def test_expansion_clear(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("PREDATOR_EXPANSION_ONLY", "true")
    monkeypatch.setenv("PREDATOR_BLOCK_TOXIC_HOURS", "false")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE,VVV")
    v = evaluate_entry("AAVE", "long", "Trending", now=_noon_et(), persist=False)
    assert v.allow is True
    assert v.reason == "expansion_clear"


def test_toxic_hour_blocks(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("PREDATOR_BLOCK_TOXIC_HOURS", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    toxic = datetime(2026, 7, 22, 10, 0, tzinfo=ET)
    v = evaluate_entry("AAVE", "long", "Trending", now=toxic, persist=False)
    assert v.allow is False
    assert v.reason.startswith("toxic_hour")


def test_daily_cap(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("PREDATOR_BLOCK_TOXIC_HOURS", "false")
    monkeypatch.setenv("PREDATOR_MAX_OPENS_PER_DAY", "2")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    v = evaluate_entry(
        "AAVE", "long", "Trending", opens_today=2, now=_noon_et(), persist=False
    )
    assert v.allow is False
    assert v.reason == "daily_open_cap"


def test_unknown_regime_fail_closed(monkeypatch):
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("PREDATOR_EXPANSION_ONLY", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    v = evaluate_entry("AAVE", "long", None, now=_noon_et(), persist=False)
    assert v.allow is False
    assert v.reason == "regime_unknown"


# ── Scanner wiring: Predator must FAIL CLOSED when enabled ───────────────────

import importlib
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[1]


def _reload_scanner(monkeypatch, **env):
    base = {
        "HL_PERPS_UNIVERSE": "full",
        "HL_PERPS_EXPECTANCY_GATE_ENABLED": "false",
        "HL_PERPS_HARD_BAN_COINS": "KAITO,APE",
        "HL_PERPS_TOXIC_COINS": "",
        "WINNING_ENTRY_FILTER_ENABLED": "false",
        "HL_PERPS_LONG_ONLY": "true",
        "HL_PERPS_REGIME_GATE_ENABLED": "false",
        "HL_PERPS_BLOCKED_HOURS_ET": "",
        "PREDATOR_BLOCK_TOXIC_HOURS": "false",
        "HL_PERPS_ALLOWLIST": "GMX",
    }
    base.update(env)
    for k, v in base.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import core.hl_perps_scanner as sc
    return importlib.reload(sc)


def _ready_scanner(sc):
    scanner = sc.HLPerpsScanner(hl_executor=MagicMock())
    scanner.hl_executor.is_available.return_value = True
    scanner.hl_executor.positions = {}
    scanner.hl_executor.get_balance.return_value = {"account_value": 1700.0}
    scanner.hl_executor.open_long = MagicMock(return_value={"coin": "GMX"})
    return scanner


def _gmx_signal():
    return SimpleNamespace(
        coin="GMX",
        direction="long",
        score=80.0,
        leverage=3,
        position_size_usd=150.0,
        entry_price=6.5,
        stop_loss_price=6.3,
        take_profit_price=6.9,
        components={},
    )


def _patch_regime(monkeypatch, name):
    import core.regime_filter as rf

    monkeypatch.setattr(
        rf, "get_regime", lambda *a, **k: SimpleNamespace(regime=rf.Regime[name])
    )


@pytest.fixture(autouse=False)
def _no_snapshot(monkeypatch, tmp_path):
    import core.predator_v1 as pv1

    monkeypatch.setattr(pv1, "_SNAPSHOT", tmp_path / "predator_v1.json")


def test_scanner_predator_allows_trending_allowlisted(monkeypatch, _no_snapshot):
    sc = _reload_scanner(monkeypatch, PREDATOR_V1_ENABLED="true")
    _patch_regime(monkeypatch, "TRENDING")
    scanner = _ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is True
    scanner.hl_executor.open_long.assert_called_once()


def test_scanner_predator_blocks_chop(monkeypatch, _no_snapshot):
    sc = _reload_scanner(monkeypatch, PREDATOR_V1_ENABLED="true")
    _patch_regime(monkeypatch, "CHOPPY")
    scanner = _ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_scanner_predator_blocks_off_allowlist(monkeypatch, _no_snapshot):
    sc = _reload_scanner(
        monkeypatch, PREDATOR_V1_ENABLED="true", HL_PERPS_ALLOWLIST="AAVE"
    )
    _patch_regime(monkeypatch, "TRENDING")
    scanner = _ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_scanner_predator_regime_fetch_error_fails_closed(monkeypatch, _no_snapshot):
    sc = _reload_scanner(monkeypatch, PREDATOR_V1_ENABLED="true")
    import core.regime_filter as rf

    def _boom(*a, **k):
        raise RuntimeError("binance down")

    monkeypatch.setattr(rf, "get_regime", _boom)
    scanner = _ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_scanner_predator_evaluate_exception_fails_closed(monkeypatch, _no_snapshot, caplog):
    sc = _reload_scanner(monkeypatch, PREDATOR_V1_ENABLED="true")
    _patch_regime(monkeypatch, "TRENDING")
    import core.predator_v1 as pv1

    def _boom(*a, **k):
        raise ValueError("kaboom")

    monkeypatch.setattr(pv1, "evaluate_entry", _boom)
    scanner = _ready_scanner(sc)
    with caplog.at_level("ERROR"):
        assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()
    assert any("[PREDATOR]" in r.getMessage() and "fail-closed" in r.getMessage()
               for r in caplog.records)


def test_scanner_predator_import_failure_fails_closed(monkeypatch, _no_snapshot):
    sc = _reload_scanner(monkeypatch, PREDATOR_V1_ENABLED="true")
    _patch_regime(monkeypatch, "TRENDING")
    import core

    monkeypatch.delattr(core, "predator_v1", raising=False)
    monkeypatch.setitem(sys.modules, "core.predator_v1", None)
    scanner = _ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is False
    scanner.hl_executor.open_long.assert_not_called()


def test_scanner_predator_disabled_is_legacy(monkeypatch, _no_snapshot):
    sc = _reload_scanner(
        monkeypatch, PREDATOR_V1_ENABLED="false", HL_PERPS_ALLOWLIST="AAVE"
    )
    _patch_regime(monkeypatch, "CHOPPY")
    scanner = _ready_scanner(sc)
    assert scanner._execute_signal(_gmx_signal()) is True


# ── Three-File Update Rule + paper-lock guards ───────────────────────────────

def _env_example() -> dict:
    out = {}
    for line in (_REPO / ".env.example").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _ci_sets() -> dict:
    """Values the deploy step forces into the server .env via sed."""
    ci = (_REPO / ".github/workflows/ci.yml").read_text()
    return dict(re.findall(r"s[/|]\^([A-Z0-9_]+)=\.\*[/|]\1=([^/|]*)[/|]", ci))


def _csv(v: str) -> set:
    return {c.strip().upper() for c in v.split(",") if c.strip()}


def test_three_file_rule_predator_vars():
    import core.predator_v1 as pv1

    env = _env_example()
    ci = _ci_sets()
    for key in (
        "PREDATOR_V1_ENABLED",
        "PREDATOR_EXPANSION_ONLY",
        "PREDATOR_BLOCK_TOXIC_HOURS",
        "PREDATOR_TOXIC_HOURS_ET",
        "PREDATOR_MAX_OPENS_PER_DAY",
        "HL_PERPS_ALLOWLIST",
        "HL_PERPS_HARD_BAN_COINS",
    ):
        assert key in env, f"{key} missing from .env.example"
        assert key in ci, f"{key} missing from CI deploy sed block"
        assert env[key] == ci[key], f"{key}: .env.example={env[key]!r} ci={ci[key]!r}"
    assert ci["PREDATOR_V1_ENABLED"] == "true"
    assert _csv(env["HL_PERPS_ALLOWLIST"]) == _csv(pv1._DEFAULT_ALLOWLIST)
    assert _csv(env["HL_PERPS_HARD_BAN_COINS"]) == _csv(pv1._DEFAULT_HARD_BAN)


def test_predator_defaults_match_scanner_defaults(monkeypatch):
    import core.predator_v1 as pv1

    sc = _reload_scanner(
        monkeypatch, HL_PERPS_ALLOWLIST=None, HL_PERPS_HARD_BAN_COINS=None
    )
    assert sc.HL_PERPS_ALLOWLIST == _csv(pv1._DEFAULT_ALLOWLIST)
    assert sc.HL_PERPS_HARD_BAN_COINS == _csv(pv1._DEFAULT_HARD_BAN)
    assert not (sc.HL_PERPS_ALLOWLIST & sc.HL_PERPS_HARD_BAN_COINS)


def test_ci_deploy_keeps_paper_lock_and_moralis_off():
    ci_text = (_REPO / ".github/workflows/ci.yml").read_text()
    ci = _ci_sets()
    assert ci.get("MODE") == "paper"
    assert ci.get("PAPER_MODE_LOCKED") == "true"
    assert ci.get("MORALIS_ENABLED") == "false"
    assert "MODE=live" not in ci_text
    assert "PAPER_MODE_LOCKED=false" not in ci_text
    assert "MORALIS_ENABLED=true" not in ci_text
