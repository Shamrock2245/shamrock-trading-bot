"""Walk-forward tuner guardrails. Recommendations are never applied."""
import ast
import json
from pathlib import Path

import pytest

from core.walk_forward_tuner import (
    SLIPPAGE,
    TAKER_FEE,
    DipParams,
    _close_trade,
    assemble_recommendation,
    current_dip_params,
    judge,
    pnl_metrics,
    simulate_dip,
    tune_predator,
    tune_rsi_dip,
)
from scripts.walk_forward_tuner import run_once

_REPO = Path(__file__).resolve().parents[1]
_GUARDS = {
    "min_oos_trades": 30,
    "min_is_trades": 20,
    "pf_margin": 0.15,
    "min_oos_pf": 1.0,
    "train_days": 60,
    "test_days": 20,
}


def _cand(key, params, is_pnls, oos_pnls):
    return {"key": key, "params": params, "is_pnls": list(is_pnls), "oos_pnls": list(oos_pnls)}


def _fold(candidates, current_key, current_oos):
    return {
        "candidates": candidates,
        "current_key": current_key,
        "current_oos_pnls": list(current_oos),
    }


def test_no_recommendation_when_oos_does_not_beat_current():
    """The in-sample winner is judged on unseen trades. A luckier OOS row is ignored."""
    current_oos = [1.0] * 22 + [-1.0] * 14  # PF 1.57, n 36
    loose_oos = [1.0] * 18 + [-1.0] * 18     # PF 1.00, does not clear 1.57 + 0.15
    lucky_oos = [1.0] * 34 + [-1.0] * 6      # PF 5.67, but worse in-sample
    fold = _fold(
        [
            _cand("loose", {"rsi_entry": 30}, [1.0] * 40, loose_oos),
            _cand("current", {"rsi_entry": 20}, [1.0] * 14 + [-1.0] * 10, current_oos),
            _cand("lucky", {"rsi_entry": 25}, [1.0] * 22 + [-1.0] * 8, lucky_oos),
        ],
        "current",
        current_oos,
    )
    rec = assemble_recommendation("rsi_dip_v1", [fold], {"rsi_entry": 20}, _GUARDS)
    assert rec["recommend"] is False
    assert rec["applied"] is False
    assert rec["reason"] == "oos_pf_margin"
    assert rec["candidate_params"]["rsi_entry"] == 30
    assert rec["oos"]["pf"] == pytest.approx(1.0, abs=0.01)
    assert rec["current_oos"]["pf"] > rec["oos"]["pf"]


def test_oos_below_the_floor_is_not_recommended_even_if_it_beats_a_loser():
    current_oos = [-1.0] * 40
    candidate_oos = [1.0] * 12 + [-1.0] * 28  # PF 0.43, better than 0, still a loser
    fold = _fold(
        [
            _cand("loose", {"rsi_entry": 30}, [1.0] * 30, candidate_oos),
            _cand("current", {"rsi_entry": 20}, [1.0] * 12 + [-1.0] * 12, current_oos),
        ],
        "current",
        current_oos,
    )
    rec = assemble_recommendation("rsi_dip_v1", [fold], {"rsi_entry": 20}, _GUARDS)
    assert rec["recommend"] is False
    assert rec["reason"] == "oos_pf_floor"


def test_recommendation_when_oos_beats_current_by_the_margin():
    current_oos = [1.0] * 20 + [-1.0] * 16   # PF 1.25, n 36
    candidate_oos = [1.0] * 30 + [-1.0] * 10  # PF 3.0, n 40
    fold = _fold(
        [
            _cand("better", {"rsi_entry": 25}, [1.0] * 30, candidate_oos),
            _cand("current", {"rsi_entry": 20}, [1.0] * 12 + [-1.0] * 10, current_oos),
        ],
        "current",
        current_oos,
    )
    rec = assemble_recommendation("rsi_dip_v1", [fold], {"rsi_entry": 20}, _GUARDS)
    assert rec["recommend"] is True
    assert rec["reason"] == "oos_improved"
    assert rec["applied"] is False
    assert rec["candidate_params"]["rsi_entry"] == 25
    assert rec["oos"]["n"] >= 30
    assert rec["oos"]["pf"] >= rec["current_oos"]["pf"] + 0.15


def test_starved_baseline_needs_the_absolute_floor():
    thin = _fold(
        [
            _cand("loose", {"exec_score": 52}, [1.0] * 30, [1.0] * 10 + [-1.0] * 30),
            _cand("current", {"exec_score": 60}, [], []),
        ],
        "current",
        [],
    )
    rejected = assemble_recommendation("predator_v1", [thin], {"exec_score": 60}, _GUARDS)
    assert rejected["recommend"] is False
    assert rejected["reason"] == "oos_pf_floor"

    clear = _fold(
        [
            _cand("loose", {"exec_score": 52}, [1.0] * 30, [1.0] * 24 + [-1.0] * 12),
            _cand("current", {"exec_score": 60}, [], []),
        ],
        "current",
        [],
    )
    accepted = assemble_recommendation("predator_v1", [clear], {"exec_score": 60}, _GUARDS)
    assert accepted["recommend"] is True
    assert accepted["reason"] == "oos_improved_starved_baseline"


def test_too_few_oos_trades_is_not_a_recommendation():
    ok, reason = judge([1.0] * 40, [1.0] * 10, min_oos=30, margin=0.15, min_pf=1.0)
    assert ok is False and reason == "oos_trade_count"


def test_unstable_folds_reject_a_lucky_last_window():
    def fold(oos, current_oos):
        return _fold(
            [
                _cand("loose", {"rsi_entry": 30}, [1.0] * 30, oos),
                _cand("current", {"rsi_entry": 20}, [1.0] * 11 + [-1.0] * 10, current_oos),
            ],
            "current",
            current_oos,
        )

    bad = [1.0] * 8 + [-1.0] * 32
    good = [1.0] * 30 + [-1.0] * 10
    current = [1.0] * 20 + [-1.0] * 16
    rec = assemble_recommendation(
        "rsi_dip_v1",
        [fold(bad, current), fold(bad, current), fold(good, current)],
        {"rsi_entry": 20},
        _GUARDS,
    )
    assert rec["recommend"] is False
    assert rec["reason"] == "oos_unstable"
    assert rec["folds"] == 3


def test_current_params_winning_in_sample_is_not_a_change():
    oos = [1.0] * 40
    fold = _fold(
        [
            _cand("current", {"rsi_entry": 20}, [1.0] * 30, oos),
            _cand("other", {"rsi_entry": 30}, [1.0] * 12 + [-1.0] * 12, [-1.0] * 40),
        ],
        "current",
        oos,
    )
    rec = assemble_recommendation("rsi_dip_v1", [fold], {"rsi_entry": 20}, _GUARDS)
    assert rec["recommend"] is False
    assert rec["reason"] == "current_is_best"


def test_predator_grid_does_not_touch_exits_and_rejects_a_weak_oos():
    # One signal stream. A looser bar takes the losers the current bar skips.
    start = 1_700_000_000_000
    hour = 3_600_000
    signals = []
    for i in range(80):
        signals.append({
            "coin": "BTC" if i % 2 == 0 else "AAVE",
            "direction": "long",
            "entry_ms": start + i * 24 * hour,  # one a day, no overlap
            "exit_ms": start + i * 24 * hour + 4 * hour,
            "score": 70 if i < 50 else 54,
            "ta29_trend": 40 if i < 50 else 22,
            "pnl": 1.0 if i < 50 else -1.0,
        })
    # Span is 80 days. Use a short walk so the test has one fold.
    guards = dict(_GUARDS, train_days=40, test_days=20, min_oos_trades=10, min_is_trades=10)
    current = {"exec_score": 60.0, "ta29_long_trend_min": 35.0, "long_only": True}
    grid = [
        current,
        {"exec_score": 52.0, "ta29_long_trend_min": 20.0, "long_only": True},
    ]
    rec = tune_predator(signals, grid=grid, current=current, guards=guards)
    assert rec["applied"] is False
    assert rec["exit_ab"] == "unchanged"
    assert rec["thresholds_only"] == ["exec_score", "ta29_long_trend_min"]
    assert "atr_mult" not in (rec.get("candidate_params") or {})
    assert "timeout_h" not in (rec.get("candidate_params") or {})
    if rec["recommend"]:
        assert rec["oos"]["pf"] >= rec["current_oos"]["pf"] + guards["pf_margin"]
    else:
        assert rec["reason"] in {
            "oos_pf_margin", "oos_pf_floor", "oos_trade_count",
            "current_is_best", "no_is_candidate", "oos_unstable", "insufficient_history",
        }


def test_simulate_dip_is_net_of_fees_and_obeys_the_stop_cooldown():
    start = 1_700_000_000_000
    closes = [100.0] * 30
    px = 100.0
    for _ in range(25):
        px -= 0.8
        closes.append(px)
    bars = []
    for i, cl in enumerate(closes):
        t = start + i * 3_600_000
        bars.append({"t": t, "o": cl, "h": cl * 1.002, "l": cl * 0.998, "c": cl, "v": 1})
    last = bars[-1]
    bars.append({
        "t": last["t"] + 3_600_000,
        "o": last["c"],
        "h": last["c"],
        "l": last["c"] * 0.4,
        "c": last["c"] * 0.5,
        "v": 1,
    })
    # Stay weak so a second dip would signal inside the cooldown if it were ignored.
    for i in range(10):
        cl = bars[-1]["c"]
        t = bars[-1]["t"] + 3_600_000
        bars.append({"t": t, "o": cl, "h": cl * 1.001, "l": cl * 0.999, "c": cl, "v": 1})
    params = DipParams(
        rsi_entry=30, rsi_exit=90, atr_mult=1.0, max_hold_hours=48,
        cooldown_hours=6, rearm_rsi=0,
    )
    trades = simulate_dip({"AAVE": bars}, params, max_concurrent=3)
    assert trades
    assert trades[0]["pnl"] < 0
    stops = [t for t in trades if t["reason"] == "stop"]
    assert stops
    nxt = [t for t in trades if t["entry_ms"] > stops[0]["exit_ms"]]
    for trade in nxt:
        assert trade["entry_ms"] >= stops[0]["exit_ms"] + 6 * 3_600_000


def test_flat_round_trip_cannot_show_a_profit_after_costs():
    """Same raw price in and out still pays taker fees and adverse slippage."""
    metrics = pnl_metrics([-0.2, 0.5, -0.1])
    assert metrics["n"] == 3
    assert metrics["pf"] == pytest.approx(0.5 / 0.3, abs=0.001)
    raw = 100.0
    trade = _close_trade(
        "AAVE",
        {"entry": raw * (1.0 + SLIPPAGE), "entry_ms": 0},
        raw * (1.0 - SLIPPAGE),
        "rsi_revert",
        {"t": 0},
        TAKER_FEE,
    )
    assert trade["pnl"] < 0
    assert TAKER_FEE == 0.00045 and SLIPPAGE == 0.0005


def test_empty_cache_writes_a_recommendation_and_applies_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("WALK_FORWARD_TUNER_PREDATOR_REPLAY", "false")
    root = tmp_path / "candles"
    root.mkdir()
    out = tmp_path / "tuner_recommendation.json"
    report = run_once(root, out)
    assert report["applied"] is False
    assert report["changes_applied"] is False
    assert report["exit_ab"] == "unchanged"
    saved = json.loads(out.read_text())
    assert saved["applied"] is False
    assert saved["strategies"]["rsi_dip_v1"]["recommend"] is False
    assert saved["strategies"]["predator_v1"]["recommend"] is False
    assert saved["research"]["funding_carry"]["added"] is False
    written = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert written == ["tuner_recommendation.json"] or set(written) <= {
        "tuner_recommendation.json",
    }


def test_tuner_never_imports_the_promoter_or_writes_live_mode():
    for rel in ("core/walk_forward_tuner.py", "scripts/walk_forward_tuner.py", "core/strategy_tournament.py"):
        text = (_REPO / rel).read_text()
        assert "paper_to_live_promoter" not in text
        assert "MODE=live" not in text
        tree = ast.parse(text)
        assigned = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                assigned.extend(getattr(t, "id", "") for t in node.targets)
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                assigned.append(node.target.id)
        assert "MODE" not in assigned


def test_three_file_rule_for_the_new_settings():
    expected = {
        "RSI_DIP_STOP_COOLDOWN_HOURS": "6",
        "RSI_DIP_STOP_REARM_RSI": "35",
        "STRATEGY_TOURNAMENT_ENABLED": "true",
        "STRATEGY_TOURNAMENT_MIN_CLOSES": "20",
        "STRATEGY_TOURNAMENT_PF_FLOOR": "0.80",
        "STRATEGY_TOURNAMENT_WINDOW": "30",
        "STRATEGY_TOURNAMENT_SHIFT_SLOTS": "true",
        "STRATEGY_TOURNAMENT_SLEEVES": "rsi_dip_v1",
        "WALK_FORWARD_TUNER_ENABLED": "true",
        "WALK_FORWARD_TUNER_INTERVAL_HOURS": "24",
        "WALK_FORWARD_TUNER_MIN_OOS_TRADES": "30",
        "WALK_FORWARD_TUNER_MIN_IS_TRADES": "20",
        "WALK_FORWARD_TUNER_PF_MARGIN": "0.15",
        "WALK_FORWARD_TUNER_MIN_OOS_PF": "1.0",
        "WALK_FORWARD_TUNER_TRAIN_DAYS": "60",
        "WALK_FORWARD_TUNER_TEST_DAYS": "20",
        "WALK_FORWARD_TUNER_PREDATOR_REPLAY": "true",
        "HL_PERPS_TA29_LONG_TREND_MIN": "35",
        "HL_PERPS_TA29_SHORT_TREND_MAX": "65",
    }
    env = {}
    for line in (_REPO / ".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key] = value.strip()
    ci = (_REPO / ".github" / "workflows" / "ci.yml").read_text()
    sources = "\n".join(
        p.read_text()
        for p in (
            _REPO / "core" / "rsi_dip_v1.py",
            _REPO / "core" / "strategy_tournament.py",
            _REPO / "core" / "walk_forward_tuner.py",
            _REPO / "core" / "paper_sleeves.py",
            _REPO / "core" / "hl_perps_scanner.py",
            _REPO / "scripts" / "walk_forward_tuner.py",
        )
    )
    for key, value in expected.items():
        assert env.get(key) == value, key
        assert f"s/^({key})=.*/\\1={value}/".replace("(", "").replace(")", "") in ci or (
            f"s/^{key}=.*/{key}={value}/" in ci
        )
        assert f'"{key}", "{value}"' in sources or f'"{key}", "{value}"' in sources


def test_predator_replay_passes_the_scanner_pair(monkeypatch):
    """replay_coin unpacks the (scanner, module) pair make_scanner returns."""
    seen = {}

    def make_scanner():
        return ("scanner-obj", "module")

    def replay_coin(coin, hourly, start, funding_by_hour=None, scanner=None, warmup_bars=24 * 61):
        seen["scanner"] = scanner
        return []

    monkeypatch.setattr("backtest.replay.make_scanner", make_scanner)
    monkeypatch.setattr("backtest.replay.replay_coin", replay_coin)
    start = 1_700_000_000_000
    bars = [
        {"t": start + i * 3_600_000, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "n": 0}
        for i in range(1600)
    ]
    from scripts.walk_forward_tuner import replay_predator_signals
    assert replay_predator_signals({"BTC": bars}) == []
    assert seen["scanner"] == ("scanner-obj", "module")


def test_tune_rsi_on_no_candles_does_not_recommend():
    rec = tune_rsi_dip({}, current=current_dip_params(), guards=_GUARDS)
    assert rec["recommend"] is False
    assert rec["reason"] == "no_candle_data"
    assert rec["applied"] is False
