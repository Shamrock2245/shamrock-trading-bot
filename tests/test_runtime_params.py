"""tests/test_runtime_params.py — live overlay actually mutates settings + profiles."""

import json
from pathlib import Path

import pytest

from config import settings
from config.wallets import CONSERVATIVE_PROFILE, NUCLEAR_PROFILE
from core import runtime_params
from ml.optuna_optimizer import params_are_trustworthy


@pytest.fixture
def restore_live_knobs():
    snapshot = {
        "MIN_GEM_SCORE": settings.MIN_GEM_SCORE,
        "EXPRESS_LANE_SCORE": settings.EXPRESS_LANE_SCORE,
        "STOP_LOSS_PERCENT": settings.STOP_LOSS_PERCENT,
        "HARD_STOP_LOSS_PERCENT": settings.HARD_STOP_LOSS_PERCENT,
        "TAKE_PROFIT_TP1_MULT": settings.TAKE_PROFIT_TP1_MULT,
        "MIN_VOLUME_USD": getattr(settings, "MIN_VOLUME_USD", 500000.0),
        "FAST_BREAK_EVEN_PCT": getattr(settings, "FAST_BREAK_EVEN_PCT", 2.5),
    }
    profile_snap = {
        "c_min": CONSERVATIVE_PROFILE.min_gem_score,
        "c_trail": CONSERVATIVE_PROFILE.trailing_stop_pct,
        "c_tp1": CONSERVATIVE_PROFILE.tp1_mult,
        "n_min": NUCLEAR_PROFILE.min_gem_score,
        "n_trail": NUCLEAR_PROFILE.trailing_stop_pct,
        "n_tp1": NUCLEAR_PROFILE.tp1_mult,
    }
    yield
    for k, v in snapshot.items():
        setattr(settings, k, v)
    CONSERVATIVE_PROFILE.min_gem_score = profile_snap["c_min"]
    CONSERVATIVE_PROFILE.trailing_stop_pct = profile_snap["c_trail"]
    CONSERVATIVE_PROFILE.tp1_mult = profile_snap["c_tp1"]
    NUCLEAR_PROFILE.min_gem_score = profile_snap["n_min"]
    NUCLEAR_PROFILE.trailing_stop_pct = profile_snap["n_trail"]
    NUCLEAR_PROFILE.tp1_mult = profile_snap["n_tp1"]


def test_apply_params_mutates_settings_not_just_env(restore_live_knobs, tmp_path, monkeypatch):
    overlay = tmp_path / "runtime_params.json"
    monkeypatch.setattr(runtime_params, "OVERLAY_PATH", overlay)

    applied = runtime_params.apply_params(
        {"min_gem_score": 71.0, "stop_loss_pct": 11.0},
        source="unit-test",
    )

    assert settings.MIN_GEM_SCORE == 71.0
    assert settings.STOP_LOSS_PERCENT == 11.0
    assert applied["MIN_GEM_SCORE"] == 71.0
    assert overlay.exists()
    disk = json.loads(overlay.read_text())
    assert disk["params"]["MIN_GEM_SCORE"] == 71.0


def test_apply_params_updates_wallet_profiles(restore_live_knobs, tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_params, "OVERLAY_PATH", tmp_path / "runtime_params.json")

    runtime_params.apply_params(
        {"min_gem_score": 70.0, "tp1_mult": 1.6},
        source="unit-test",
    )

    assert CONSERVATIVE_PROFILE.min_gem_score == 70.0
    assert NUCLEAR_PROFILE.min_gem_score == 73.0
    assert CONSERVATIVE_PROFILE.tp1_mult == 1.6
    assert NUCLEAR_PROFILE.tp1_mult == pytest.approx(1.6 * 1.15)


def test_apply_params_clamps_out_of_range(restore_live_knobs, tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_params, "OVERLAY_PATH", tmp_path / "runtime_params.json")
    runtime_params.apply_params({"MIN_GEM_SCORE": 10.0}, source="unit-test")
    assert settings.MIN_GEM_SCORE == 55.0


def test_self_improving_aliases_apply(restore_live_knobs, tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_params, "OVERLAY_PATH", tmp_path / "runtime_params.json")
    runtime_params.apply_params(
        {"VOLUME_FLOOR_USD": 1_500_000, "FAST_BREAK_EVEN_PCT": 0.5},
        source="self-improving-agent",
    )
    assert settings.MIN_VOLUME_USD == 1_500_000
    assert settings.FAST_BREAK_EVEN_PCT == 0.5


def test_reload_overlay_if_newer(restore_live_knobs, tmp_path, monkeypatch):
    overlay = tmp_path / "runtime_params.json"
    monkeypatch.setattr(runtime_params, "OVERLAY_PATH", overlay)
    runtime_params._last_loaded_mtime = 0.0

    overlay.write_text(json.dumps({
        "source": "service",
        "params": {"MIN_GEM_SCORE": 73.0},
    }))
    applied = runtime_params.reload_overlay_if_newer(force=True)
    assert applied["MIN_GEM_SCORE"] == 73.0
    assert settings.MIN_GEM_SCORE == 73.0

    # Second call with same mtime is a no-op
    again = runtime_params.reload_overlay_if_newer(force=False)
    assert again == {}


def test_params_are_trustworthy_rejects_dry_run():
    assert not params_are_trustworthy({
        "n_trials": 5,
        "trade_count": 10,
        "walk_forward_pass": False,
    })
    assert params_are_trustworthy({"walk_forward_pass": True, "n_trials": 5})
    assert params_are_trustworthy({
        "n_trials": 80,
        "trade_count": 40,
        "walk_forward_pass": False,
    })


def test_apply_regime_params_skips_untrustworthy_file(tmp_path, monkeypatch, restore_live_knobs):
    from ml import optuna_optimizer

    fake = tmp_path / "optuna_best_params.json"
    fake.write_text(json.dumps({
        "n_trials": 5,
        "trade_count": 10,
        "walk_forward_pass": False,
        "best_params": {"min_gem_score": 80.0},
        "regime_profiles": {"trending": {"min_gem_score": 80.0}},
    }))
    monkeypatch.setattr(optuna_optimizer, "BEST_PARAMS_PATH", fake)
    before = settings.MIN_GEM_SCORE
    applied = optuna_optimizer.apply_regime_params("trending")
    assert applied == {}
    assert settings.MIN_GEM_SCORE == before
