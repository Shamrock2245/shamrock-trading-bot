"""tests/test_hot_streak.py — HotStreakAmplifier arm/disarm/cap/never-bypass."""

from __future__ import annotations

from core.hot_streak import (
    HotStreakAmplifier,
    ladder_multiplier,
    parse_mult_ladder,
    reset_amplifier_for_tests,
)


def _amp(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("HOT_STREAK_ENABLED", "true")
    monkeypatch.setenv("HOT_STREAK_MIN_WINS", "3")
    monkeypatch.setenv("HOT_STREAK_MULT_LADDER", "3:1.25,5:1.5,7:1.75")
    monkeypatch.setenv("HOT_STREAK_MAX_MULT", "2.0")
    monkeypatch.setenv("HOT_STREAK_DISARM_DD_PCT", "3.0")
    monkeypatch.setenv("HOT_STREAK_ROLLING_CONFIRM", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    path = tmp_path / "hot_streak.json"
    return reset_amplifier_for_tests(path)


def test_parse_ladder_and_cap():
    ladder = parse_mult_ladder("3:1.25,5:1.5,7:1.75")
    assert ladder == [(3, 1.25), (5, 1.5), (7, 1.75)]
    assert ladder_multiplier(0, ladder, 2.0) == 1.0
    assert ladder_multiplier(3, ladder, 2.0) == 1.25
    assert ladder_multiplier(5, ladder, 2.0) == 1.5
    assert ladder_multiplier(7, ladder, 2.0) == 1.75
    assert ladder_multiplier(20, ladder, 2.0) == 1.75  # ladder max before hard cap
    assert ladder_multiplier(20, ladder, 1.4) == 1.4  # hard CAP wins


def test_arms_after_n_consecutive_wins(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    for i in range(2):
        amp.record_close(True, pnl_usd=10.0, coin="AAVE", on_allowlist=True)
        assert amp.get_state()["armed"] is False
    amp.record_close(True, pnl_usd=10.0, coin="BTC", on_allowlist=True)
    st = amp.get_state()
    assert st["armed"] is True
    assert st["consecutive_wins"] == 3
    assert st["multiplier"] == 1.25


def test_ladder_steps_and_hard_cap(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch, HOT_STREAK_MAX_MULT="2.0")
    for _ in range(5):
        amp.record_close(True, pnl_usd=5.0, coin="LINK", on_allowlist=True)
    assert amp.get_state()["multiplier"] == 1.5
    for _ in range(2):
        amp.record_close(True, pnl_usd=5.0, coin="LINK", on_allowlist=True)
    assert amp.get_state()["multiplier"] == 1.75
    # Cap: even with a taller ladder, never above MAX_MULT
    amp2 = _amp(
        tmp_path,
        monkeypatch,
        HOT_STREAK_MAX_MULT="2.0",
        HOT_STREAK_MULT_LADDER="3:1.25,5:1.5,7:1.75,10:3.0",
    )
    for _ in range(10):
        amp2.record_close(True, pnl_usd=1.0, coin="INJ", on_allowlist=True)
    assert amp2.get_state()["multiplier"] == 2.0


def test_instant_disarm_on_closed_loss(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    for _ in range(3):
        amp.record_close(True, pnl_usd=8.0, coin="AAVE", on_allowlist=True)
    assert amp.get_state()["armed"] is True
    amp.record_close(False, pnl_usd=-4.0, coin="AAVE", on_allowlist=True)
    st = amp.get_state()
    assert st["armed"] is False
    assert st["consecutive_wins"] == 0
    assert st["multiplier"] == 1.0
    assert st["disarm_reason"] == "closed_loss"


def test_disarm_on_day_net_negative(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    amp.record_close(True, pnl_usd=5.0, coin="AAVE", on_allowlist=True)
    amp.record_close(True, pnl_usd=5.0, coin="AAVE", on_allowlist=True)
    # Big loss that doesn't zero streak via won=False path alone... use won=True
    # with negative pnl? Primary path is won=False. Simulate day going negative
    # after being armed via update_open_equity.
    amp.record_close(True, pnl_usd=5.0, coin="AAVE", on_allowlist=True)
    assert amp.get_state()["armed"] is True
    amp.update_open_equity(-1.0)
    st = amp.get_state()
    assert st["armed"] is False
    assert st["consecutive_wins"] == 0
    assert st["disarm_reason"] == "day_net_negative"


def test_disarm_on_drawdown_from_peak(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch, HOT_STREAK_DISARM_DD_PCT="3.0")
    for _ in range(3):
        amp.record_close(True, pnl_usd=10.0, coin="BTC", on_allowlist=True)
    assert amp.get_state()["armed"] is True
    # Peak = 30. Drop to 28.9 => DD ~3.67% > 3%
    amp.update_open_equity(28.9)
    st = amp.get_state()
    assert st["armed"] is False
    assert st["disarm_reason"] == "drawdown"
    assert st["consecutive_wins"] == 0


def test_non_allowlist_closes_do_not_count(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    for _ in range(5):
        amp.record_close(True, pnl_usd=10.0, coin="DOGE", on_allowlist=False)
    st = amp.get_state()
    assert st["consecutive_wins"] == 0
    assert st["armed"] is False


def test_amplify_respects_caps_and_predator_deny(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    for _ in range(3):
        amp.record_close(True, pnl_usd=10.0, coin="AAVE", on_allowlist=True)
    # Predator denied → no amplify
    size, lev, mult = amp.amplify(
        100.0, 4,
        max_leverage=15,
        max_notional=350.0,
        max_position_usd=150.0,
        predator_allowed=False,
    )
    assert (size, lev, mult) == (100.0, 4, 1.0)

    size, lev, mult = amp.amplify(
        100.0, 4,
        max_leverage=15,
        max_notional=350.0,
        max_position_usd=150.0,
        predator_allowed=True,
    )
    assert mult == 1.25
    assert lev == 5  # 4 * 1.25 = 5
    # size 100*1.25=125, but notional cap 350/5=70 → size capped to 70
    assert size == 70.0


def test_amplify_never_exceeds_max_leverage(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    for _ in range(7):
        amp.record_close(True, pnl_usd=3.0, coin="LINK", on_allowlist=True)
    assert amp.get_state()["multiplier"] == 1.75
    size, lev, mult = amp.amplify(
        50.0, 10,
        max_leverage=12,
        max_notional=1000.0,
        max_position_usd=200.0,
        predator_allowed=True,
    )
    assert mult == 1.75
    assert lev == 12  # capped, not 17
    assert size <= 200.0


def test_disabled_is_noop(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch, HOT_STREAK_ENABLED="false")
    for _ in range(5):
        amp.record_close(True, pnl_usd=10.0, coin="AAVE", on_allowlist=True)
    assert amp.get_multiplier() == 1.0
    size, lev, mult = amp.amplify(
        100.0, 3,
        max_leverage=15,
        max_notional=350.0,
        max_position_usd=150.0,
        predator_allowed=True,
    )
    assert (size, lev, mult) == (100.0, 3, 1.0)


def test_rolling_confirm_optional(tmp_path, monkeypatch):
    amp = _amp(
        tmp_path,
        monkeypatch,
        HOT_STREAK_ROLLING_CONFIRM="true",
        HOT_STREAK_ROLLING_M="5",
        HOT_STREAK_ROLLING_WR="0.55",
        HOT_STREAK_ROLLING_PF="1.2",
        HOT_STREAK_MIN_WINS="3",
    )
    # 3 wins but rolling window not full → not armed
    for _ in range(3):
        amp.record_close(True, pnl_usd=10.0, coin="AAVE", on_allowlist=True)
    assert amp.get_state()["armed"] is False
    # Fill rolling with enough WR/PF
    for _ in range(2):
        amp.record_close(True, pnl_usd=10.0, coin="AAVE", on_allowlist=True)
    assert amp.get_state()["armed"] is True


def test_persist_and_dashboard_helper(tmp_path, monkeypatch):
    amp = _amp(tmp_path, monkeypatch)
    for _ in range(3):
        amp.record_close(True, pnl_usd=4.0, coin="BTC", on_allowlist=True)
    path = tmp_path / "hot_streak.json"
    assert path.exists()
    from core.hot_streak import get_hot_streak_state
    st = get_hot_streak_state()
    assert st["armed"] is True
    assert st["paper_only"] is True


def test_predator_gates_still_independent(monkeypatch):
    """Hot streak must not weaken Predator deny paths."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from core.predator_v1 import evaluate_entry

    ET = ZoneInfo("America/New_York")
    monkeypatch.setenv("PREDATOR_V1_ENABLED", "true")
    monkeypatch.setenv("PREDATOR_EXPANSION_ONLY", "true")
    monkeypatch.setenv("HL_PERPS_ALLOWLIST", "AAVE")
    monkeypatch.setenv("HOT_STREAK_ENABLED", "true")
    # Chop still denied even if streak would be hot
    v = evaluate_entry(
        "AAVE", "long", "Choppy",
        now=datetime(2026, 7, 21, 3, 0, tzinfo=ET),
        persist=False,
    )
    assert v.allow is False
    assert v.reason == "regime_chop"
    # Hard ban still denied
    v2 = evaluate_entry(
        "TRB", "long", "Trending",
        now=datetime(2026, 7, 21, 3, 0, tzinfo=ET),
        persist=False,
    )
    assert v2.allow is False
    assert v2.reason == "hard_banned"
