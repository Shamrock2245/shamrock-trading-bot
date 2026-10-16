"""2026-10-16 paper-only unlock: exec delta, toxic bonus, Moralis gate, sweep log."""

import importlib
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _reload(monkeypatch, mode="paper", **env):
    env.setdefault("HL_PERPS_UNIVERSE", "full")
    env.setdefault("HL_PERPS_EXPECTANCY_GATE_ENABLED", "false")
    env.setdefault("PREDATOR_V1_ENABLED", "false")
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import core.hl_perps_scanner as sc
    sc = importlib.reload(sc)
    from config import settings
    monkeypatch.setattr(settings, "get_current_mode", lambda: mode)
    return sc


def test_defaults(monkeypatch):
    sc = _reload(monkeypatch, HL_PERPS_PAPER_EXEC_SCORE_DELTA=None,
                 HL_PERPS_PAPER_TOXIC_SCORE_BONUS=None, HL_PERPS_TOXIC_SCORE_BONUS=None)
    assert sc.HL_PERPS_PAPER_EXEC_SCORE_DELTA == -5.0
    assert sc.HL_PERPS_PAPER_TOXIC_SCORE_BONUS == 8.0
    assert sc.HL_PERPS_TOXIC_SCORE_BONUS == 20.0


def test_paper_loosens_exec_and_toxic(monkeypatch):
    sc = _reload(monkeypatch, "paper")
    assert sc.apply_paper_exec_delta(61) == 56
    assert sc.apply_paper_exec_delta(55) == 52  # floor
    assert sc.effective_toxic_bonus() == 8.0


@pytest.mark.parametrize("mode", ["live", "weird"])
def test_live_unchanged(monkeypatch, mode):
    sc = _reload(monkeypatch, mode)
    assert sc.apply_paper_exec_delta(61) == 61
    assert sc.effective_toxic_bonus() == 20.0


def test_mode_error_fails_closed(monkeypatch):
    sc = _reload(monkeypatch, "paper")
    from config import settings

    def boom():
        raise RuntimeError("x")
    monkeypatch.setattr(settings, "get_current_mode", boom)
    assert sc.apply_paper_exec_delta(61) == 61
    assert sc.effective_toxic_bonus() == 20.0


def test_positive_delta_cannot_tighten_or_loosen_live(monkeypatch):
    sc = _reload(monkeypatch, "paper", HL_PERPS_PAPER_EXEC_SCORE_DELTA="7")
    assert sc.HL_PERPS_PAPER_EXEC_SCORE_DELTA == 0.0
    assert sc.apply_paper_exec_delta(61) == 61


def test_paper_toxic_bonus_never_exceeds_live(monkeypatch):
    sc = _reload(monkeypatch, "paper", HL_PERPS_PAPER_TOXIC_SCORE_BONUS="30")
    assert sc.effective_toxic_bonus() == 20.0


def test_goal_params_apply_delta_only_in_paper(monkeypatch):
    sc = _reload(monkeypatch, "paper", HL_PERPS_EXEC_SCORE="58")
    s = sc.HLPerpsScanner(hl_executor=MagicMock())
    paper = s._goal_frequency_params()["exec_score"]
    from config import settings
    monkeypatch.setattr(settings, "get_current_mode", lambda: "live")
    live = s._goal_frequency_params()["exec_score"]
    assert paper == max(52.0, live - 5)
    assert paper < live


def _signal(coin="AAVE", score=66.0):
    return SimpleNamespace(coin=coin, direction="long", score=score, leverage=3,
                           position_size_usd=150.0, entry_price=100.0,
                           stop_loss_price=97.0, take_profit_price=106.0, components={})


def _scanner(sc):
    s = sc.HLPerpsScanner(hl_executor=MagicMock())
    s.hl_executor.is_available.return_value = True
    s.hl_executor.positions = {}
    s.hl_executor.get_balance.return_value = {"account_value": 1700.0}
    s.hl_executor.open_long = MagicMock(return_value={"coin": "AAVE"})
    s._goal_frequency_params = lambda: {
        "exec_score": sc.apply_paper_exec_delta(58.0), "reentry_cooldown_min": 0,
        "loss_cooldown_min": 0, "max_positions": 4, "size_multiplier": 1.0,
        "mode": "normal", "progress_pct": 0, "remaining_usd": 0, "behind_pace": False}
    return s


def test_toxic_aave_score66_blocked_live_bar_allowed_paper(monkeypatch, caplog):
    for mode, expect_block in (("live", True), ("paper", False)):
        sc = _reload(monkeypatch, mode, HL_PERPS_TOXIC_COINS="AAVE",
                     HL_PERPS_HARD_BAN_COINS="KAITO", WINNING_ENTRY_FILTER_ENABLED="false")
        s = _scanner(sc)
        caplog.clear()
        with caplog.at_level(logging.INFO):
            s._execute_signal(_signal(score=66.0))
        blocked = any("toxic-list" in r.getMessage() for r in caplog.records)
        assert blocked is expect_block, mode


def test_moralis_never_called_when_disabled(monkeypatch):
    sc = _reload(monkeypatch, "paper", MORALIS_ENABLED="false", HL_PERPS_TOXIC_COINS="",
                 HL_PERPS_HARD_BAN_COINS="KAITO", WINNING_ENTRY_FILTER_ENABLED="true")
    import data.providers.hl_token_resolve as r
    spy = MagicMock(return_value={"score": 90})
    monkeypatch.setattr(r, "moralis_score_for_hl_coin", spy)
    import core.hl_scanner_winning_tuning as wt
    monkeypatch.setattr(wt.winning_entry_filter, "validate_entry",
                        lambda d: {"approved": True, "position_size_multiplier": 1.0})
    s = _scanner(sc)
    s._execute_signal(_signal(coin="GMX", score=80.0))
    spy.assert_not_called()


def test_moralis_enabled_is_veto_only(monkeypatch):
    sc = _reload(monkeypatch, "paper", MORALIS_ENABLED="true", HL_PERPS_TOXIC_COINS="",
                 HL_PERPS_HARD_BAN_COINS="KAITO", WINNING_ENTRY_FILTER_ENABLED="true")
    import data.providers.hl_token_resolve as r
    import core.hl_scanner_winning_tuning as wt
    monkeypatch.setattr(wt.winning_entry_filter, "validate_entry",
                        lambda d: {"approved": True, "position_size_multiplier": 1.0})
    monkeypatch.setattr(r, "moralis_score_for_hl_coin", lambda c: {"score": 20})
    s = _scanner(sc)
    assert s._execute_signal(_signal(coin="GMX", score=80.0)) is False
    s.hl_executor.open_long.assert_not_called()


def test_paper_sweep_logs_once_no_withdrawal(monkeypatch, caplog):
    sc = _reload(monkeypatch, "paper", WALLET_ADDRESS_C="0xabc")
    ex = MagicMock()
    ex.is_paper = True
    ex.is_available.return_value = True
    ex.get_balance.return_value = {"withdrawable": 1e6}
    s = sc.HLPerpsScanner(hl_executor=ex)
    s.enabled = True
    s._initialized = True
    monkeypatch.setattr(s, "_check_daily_reset", MagicMock(side_effect=RuntimeError("stop")))
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            with pytest.raises(RuntimeError):
                s.run_cycle()
    ex.withdraw_profit_usd.assert_not_called()
    msgs = [r.getMessage() for r in caplog.records if "Profit sweep" in r.getMessage()]
    assert len(msgs) == 1
