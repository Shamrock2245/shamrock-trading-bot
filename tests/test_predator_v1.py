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
