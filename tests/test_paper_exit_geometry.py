"""Paper-only exit geometry: fee-covering BE floor, stretched-TP demotion, no-op SL spam."""
import threading
from pathlib import Path

import pytest

import core.hl_perps_scanner as sc
import core.hyperliquid_executor as hx
import core.profit_lock_manager as plm
import core.winning_risk_manager as wrm


@pytest.mark.parametrize("mod,var", [(wrm, "FAST_BREAK_EVEN_SL_OFFSET"), (plm, "PROFIT_LOCK_BE_BUFFER_PCT")])
def test_be_buffer_floor_paper_only(monkeypatch, mod, var):
    monkeypatch.setenv(var, "0.05")
    monkeypatch.delenv("PAPER_BREAK_EVEN_BUFFER_PCT", raising=False)
    monkeypatch.setattr(mod, "_paper_mode_active", lambda: True)
    assert mod.default_config().be_buffer_pct == pytest.approx(0.12)
    # configured above the floor wins
    monkeypatch.setenv(var, "0.2")
    assert mod.default_config().be_buffer_pct == pytest.approx(0.2)
    # live: configured value untouched
    monkeypatch.setenv(var, "0.05")
    monkeypatch.setattr(mod, "_paper_mode_active", lambda: False)
    assert mod.default_config().be_buffer_pct == pytest.approx(0.05)


def test_be_floor_clamped(monkeypatch):
    monkeypatch.setattr(wrm, "_paper_mode_active", lambda: True)
    monkeypatch.setenv("FAST_BREAK_EVEN_SL_OFFSET", "0.05")
    monkeypatch.setenv("PAPER_BREAK_EVEN_BUFFER_PCT", "5")
    assert wrm.default_config().be_buffer_pct == pytest.approx(1.0)


def test_be_sl_covers_fees_in_paper(monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(wrm, "_paper_mode_active", lambda: True)
    monkeypatch.setenv("FAST_BREAK_EVEN_SL_OFFSET", "0.05")
    now = datetime.now(timezone.utc)
    d = wrm.evaluate_position(coin="INJ", current_price=100.8, entry_price=100.0,
                              entry_time=now - timedelta(minutes=20), side="long",
                              peak_price=100.8, current_sl=98.0, now=now)
    assert d.sl_price is not None and d.sl_price >= 100.0 * 1.0012 - 1e-9


@pytest.mark.parametrize("src,stretched", [
    ("fib", False), ("fixed", False), ("fib+rr_fallback", True),
    ("fib+rr_stretch", True), ("fib+rr_fallback+rr_stretch", True), ("", False),
])
def test_stretched_tp_penalty(monkeypatch, src, stretched):
    monkeypatch.setattr(sc, "_paper_mode_active", lambda: True)
    monkeypatch.setattr(sc, "HL_PERPS_PAPER_STRETCHED_TP_PENALTY", 10.0)
    assert sc.paper_stretched_tp_penalty(src) == (10.0 if stretched else 0.0)
    monkeypatch.setattr(sc, "_paper_mode_active", lambda: False)
    assert sc.paper_stretched_tp_penalty(src) == 0.0  # live: never


def test_stretched_penalty_disabled(monkeypatch):
    monkeypatch.setattr(sc, "_paper_mode_active", lambda: True)
    monkeypatch.setattr(sc, "HL_PERPS_PAPER_STRETCHED_TP_PENALTY", 0.0)
    assert sc.paper_stretched_tp_penalty("fib+rr_fallback") == 0.0


def _exec(monkeypatch, tmp_path, paper=True):
    monkeypatch.setattr(hx, "_TRAILING_STATE_FILE", tmp_path / "trail.json")
    monkeypatch.setattr(hx, "_PAPER_POSITIONS_FILE", tmp_path / "pp.json")
    e = hx.HyperliquidExecutor.__new__(hx.HyperliquidExecutor)
    e.positions = {}
    e._lock = threading.RLock()
    e._info = None
    monkeypatch.setattr(hx.HyperliquidExecutor, "is_paper", property(lambda self: paper))
    monkeypatch.setattr(e, "_get_sz_decimals", lambda c: 2, raising=False)
    return e


def test_noop_ratchet_is_silent(monkeypatch, tmp_path, caplog):
    e = _exec(monkeypatch, tmp_path)
    e.positions["INJ"] = hx.HLPosition(coin="INJ", side="long", entry_price=8.75495, size=1,
                                       size_usd=8.75, leverage=5, stop_loss_price=8.7593)
    saves = []
    monkeypatch.setattr(e, "_save_trailing_state", lambda: saves.append(1), raising=False)
    caplog.set_level("INFO")
    for _ in range(5):
        assert e.update_trailing_stop("INJ", 8.75932747) is True
    assert "TRAILING STOP RATCHETED" not in caplog.text
    assert saves == []
    # A real move still ratchets and logs once
    assert e.update_trailing_stop("INJ", 8.80) is True
    assert caplog.text.count("TRAILING STOP RATCHETED") == 1
    assert e.positions["INJ"].stop_loss_price == pytest.approx(8.80)


def test_three_file_rule():
    env = Path(".env.example").read_text()
    ci = Path(".github/workflows/ci.yml").read_text()
    for k in ("PAPER_BREAK_EVEN_BUFFER_PCT=0.12", "HL_PERPS_PAPER_STRETCHED_TP_PENALTY=10"):
        assert k in env and k in ci
