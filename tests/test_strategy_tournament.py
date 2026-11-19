"""Paper sleeve tournament. Predator is reported and never paused."""
import json

from core.predator_v1 import get_paper_metrics
from core.strategy_tournament import publish, slot_cap


def _close(symbol, pnl, strategy, i):
    return {
        "chain": "hyperliquid",
        "action": "SELL",
        "is_paper": True,
        "token_symbol": symbol,
        "strategy": strategy,
        "pnl_usd": pnl,
        "reason": "paper_close",
        "timestamp": f"2026-11-01T00:{i % 60:02d}:{i // 60:02d}+00:00",
    }


def _write(tmp_path, monkeypatch, rows):
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(rows))
    monkeypatch.setenv("TRADES_FILE", str(path))
    monkeypatch.setenv("STRATEGY_TOURNAMENT_STATUS_FILE", str(tmp_path / "tournament.json"))
    monkeypatch.setenv("STRATEGY_TOURNAMENT_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_MIN_CLOSES", "20")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_PF_FLOOR", "0.80")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_WINDOW", "30")
    monkeypatch.setenv("STRATEGY_TOURNAMENT_SHIFT_SLOTS", "true")
    monkeypatch.setenv("PAPER_MODE_LOCKED", "true")
    monkeypatch.setenv("MODE", "paper")
    return path


def test_pauses_a_sleeve_below_the_floor_after_enough_closes(tmp_path, monkeypatch):
    rows = [_close("AAVE", -1.0, "rsi_dip_v1", i) for i in range(20)]
    rows += [_close("BTC", 2.0, "rsi_dip_v1", 20 + i) for i in range(4)]
    _write(tmp_path, monkeypatch, rows)
    status = publish()
    sleeve = status["sleeves"]["rsi_dip_v1"]
    # 4 wins and 20 losses in the last 30 → PF 8/20 = 0.4
    assert sleeve["trades"] == 24
    assert sleeve["profit_factor"] < 0.80
    assert sleeve["paused"] is True
    assert sleeve["managed"] is True
    assert slot_cap("rsi_dip_v1", 3) == 0
    saved = json.loads((tmp_path / "tournament.json").read_text())
    assert saved["applied_to_live"] is False
    assert saved["paper_only"] is True
    assert saved["sleeves"]["rsi_dip_v1"]["win_rate"] == round(4 / 24, 4)


def test_does_not_pause_before_the_minimum_sample(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [_close("AAVE", -1.0, "rsi_dip_v1", i) for i in range(8)])
    status = publish()
    assert status["sleeves"]["rsi_dip_v1"]["paused"] is False
    assert slot_cap("rsi_dip_v1", 3) == 3


def test_predator_book_is_not_paused(tmp_path, monkeypatch):
    rows = [_close("BTC", -2.0, "", i) for i in range(32)]
    rows += [_close("SYRUP", 3.0, "rsi_dip_v1", 40 + i) for i in range(22)]
    _write(tmp_path, monkeypatch, rows)
    status = publish()
    predator = status["sleeves"]["predator_v1"]
    assert predator["trades"] == 30  # rolling window
    assert predator["profit_factor"] == 0.0
    assert predator["managed"] is False
    assert predator["paused"] is False
    assert status["sleeves"]["rsi_dip_v1"]["paused"] is False
    assert slot_cap("predator_v1", 4) == 4
    assert slot_cap("rsi_dip_v1", 3) == 3


def test_live_mode_does_not_pause(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [_close("AAVE", -1.0, "rsi_dip_v1", i) for i in range(25)])
    monkeypatch.setenv("PAPER_MODE_LOCKED", "false")
    monkeypatch.setenv("MODE", "live")
    status = publish()
    assert status["enabled"] is False
    assert status["sleeves"]["rsi_dip_v1"]["paused"] is False
    assert slot_cap("rsi_dip_v1", 3) == 3


def test_slot_shift_gives_the_weaker_sleeve_fewer_slots(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_TOURNAMENT_SLEEVES", "rsi_dip_v1,alpha_v2")
    rows = [_close("AAVE", 2.0, "rsi_dip_v1", i) for i in range(20)]
    rows += [_close("SKY", 1.0, "alpha_v2", i) for i in range(12)]
    rows += [_close("SKY", -1.0, "alpha_v2", 12 + i) for i in range(8)]
    _write(tmp_path, monkeypatch, rows)
    monkeypatch.setenv("STRATEGY_TOURNAMENT_SLEEVES", "rsi_dip_v1,alpha_v2")
    status = publish()
    assert status["sleeves"]["rsi_dip_v1"]["paused"] is False
    assert status["sleeves"]["alpha_v2"]["paused"] is False
    assert status["sleeves"]["alpha_v2"]["profit_factor"] < status["sleeves"]["rsi_dip_v1"]["profit_factor"]
    assert slot_cap("rsi_dip_v1", 3) == 3
    assert slot_cap("alpha_v2", 3) == 1


def test_naming_predator_in_the_sleeve_env_does_not_manage_it(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_TOURNAMENT_SLEEVES", "predator_v1,rsi_dip_v1")
    _write(tmp_path, monkeypatch, [_close("BTC", -1.0, "predator_v1", i) for i in range(25)])
    monkeypatch.setenv("STRATEGY_TOURNAMENT_SLEEVES", "predator_v1,rsi_dip_v1")
    status = publish()
    assert status["sleeves"]["predator_v1"]["managed"] is False
    assert status["sleeves"]["predator_v1"]["paused"] is False


def test_extra_sleeve_stays_out_of_the_predator_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_TOURNAMENT_SLEEVES", "rsi_dip_v1,alpha_v2")
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([
        {"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": 3.0,
         "reason": "paper_close"},
        {"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": -9.0,
         "reason": "paper_close", "strategy": "alpha_v2"},
        {"chain": "hyperliquid", "is_paper": True, "action": "SELL", "pnl_usd": -4.0,
         "reason": "paper_close", "strategy": "rsi_dip_v1"},
    ]))
    monkeypatch.setenv("TRADES_FILE", str(path))
    metrics = get_paper_metrics()
    assert metrics["closed_trades"] == 1
    assert metrics["net_pnl"] == 3.0
    assert (metrics["gates"]["min_trades"], metrics["gates"]["min_wr"], metrics["gates"]["min_pf"]) == (
        50, 0.50, 1.30,
    )
