"""
tests/test_self_improving_agent.py — Unit Tests for Self-Improving AI Agent (OpenAlice style).
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.self_improving_agent import SelfImprovingAgent, get_openai_client


@pytest.fixture
def tmp_trades_file(tmp_path):
    trades = [
        {
            "token_symbol": "KAITO",
            "pnl_usd": -4.50,
            "pnl_pct": -1.2,
            "holding_duration_seconds": 2400,  # Hope trade (>30m)
            "entry_time": "2026-07-22T09:30:00Z",  # Toxic hour
            "exit_reason": "Stop Loss Hit"
        },
        {
            "token_symbol": "KAITO",
            "pnl_usd": -12.00,
            "pnl_pct": -3.5,
            "holding_duration_seconds": 600,
            "entry_time": "2026-07-22T10:00:00Z",  # Toxic hour
            "exit_reason": "SL hit"
        },
        {
            "token_symbol": "PEPE",
            "pnl_usd": 25.00,
            "pnl_pct": 5.0,
            "holding_duration_seconds": 900,
            "entry_time": "2026-07-22T15:00:00Z",
            "exit_reason": "Take Profit 1"
        },
        {
            "token_symbol": "DOGE",
            "pnl_usd": -2.00,
            "pnl_pct": -0.8,
            "holding_duration_seconds": 1200,
            "entry_time": "2026-07-22T16:00:00Z",
            "exit_reason": "Trailing Stop"
        }
    ]
    file_path = tmp_path / "trades.json"
    file_path.write_text(json.dumps(trades, indent=2))
    return str(file_path)


def test_load_trade_history(tmp_trades_file):
    agent = SelfImprovingAgent(history_file=tmp_trades_file)
    trades = agent.load_trade_history()
    assert len(trades) == 4
    assert trades[0]["token_symbol"] == "KAITO"


def test_calculate_metrics(tmp_trades_file):
    agent = SelfImprovingAgent(history_file=tmp_trades_file)
    trades = agent.load_trade_history()
    metrics = agent.calculate_metrics(trades)

    assert metrics["trade_count"] == 4
    assert metrics["winning_trades"] == 1
    assert metrics["losing_trades"] == 3
    assert metrics["win_rate"] == 25.0
    assert metrics["total_pnl"] == 6.50  # 25.0 - 4.5 - 12.0 - 2.0
    assert metrics["avg_win_usd"] == 25.0


def test_identify_failure_modes(tmp_trades_file):
    agent = SelfImprovingAgent(history_file=tmp_trades_file)
    trades = agent.load_trade_history()
    failure_data = agent.identify_failure_modes(trades)

    assert failure_data["small_loss_count"] >= 1
    assert failure_data["hope_trade_count"] == 1
    assert failure_data["toxic_loss_count"] == 2
    assert "KAITO" in failure_data["repeat_losers"]


def test_deterministic_fallback_when_no_openai_key(tmp_trades_file, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = SelfImprovingAgent(history_file=tmp_trades_file)
    
    trades = agent.load_trade_history()
    metrics = agent.calculate_metrics(trades)
    failure_data = agent.identify_failure_modes(trades)

    correction = agent.get_llm_correction(metrics, failure_data)
    assert isinstance(correction, dict)
    assert "rationale" in correction
    assert "Deterministic Fallback Audit" in correction["rationale"]
    assert "KAITO" in correction["blacklist_candidates"]


def test_apply_correction_and_audit_persistence(tmp_path, monkeypatch):
    audit_file = tmp_path / "audit.json"
    monkeypatch.setenv("SELF_IMPROVING_AUDIT_FILE", str(audit_file))
    
    agent = SelfImprovingAgent()
    update = {
        "new_params": {"VOLUME_FLOOR_USD": 1500000},
        "blacklist_candidates": ["KAITO_TEST"],
        "rationale": "Unit test commitment."
    }
    
    with patch("core.hl_scanner_winning_tuning.winning_entry_filter.update_blacklist") as mock_blacklist:
        agent.apply_correction(update)
        mock_blacklist.assert_called_once_with("KAITO_TEST", sl_count=3)

    assert audit_file.exists()
    content = json.loads(audit_file.read_text())
    assert content["update"]["rationale"] == "Unit test commitment."


def test_cooldown_lock(tmp_trades_file, tmp_path, monkeypatch):
    lock_file = tmp_path / "lock.json"
    audit_file = tmp_path / "audit.json"
    monkeypatch.setenv("SELF_IMPROVING_LOCK_FILE", str(lock_file))
    monkeypatch.setenv("SELF_IMPROVING_AUDIT_FILE", str(audit_file))
    monkeypatch.setenv("SELF_IMPROVEMENT_INTERVAL_SECONDS", "3600")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = SelfImprovingAgent(history_file=tmp_trades_file)

    # First audit cycle (should execute)
    first_res = agent.run_self_audit(force=False)
    assert first_res is not None

    # Immediate second cycle (should skip due to cooldown)
    second_res = agent.run_self_audit(force=False)
    assert second_res is None

    # Forced cycle (should bypass cooldown)
    third_res = agent.run_self_audit(force=True)
    assert third_res is not None


def test_llm_correction_with_mocked_openai(tmp_trades_file, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-test-key")
    agent = SelfImprovingAgent(history_file=tmp_trades_file)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "new_params": {"VOLUME_FLOOR_USD": 2000000},
            "blacklist_candidates": ["KAITO"],
            "rationale": "LLM Test rationale: tightening volume floor."
        })))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    with patch("core.self_improving_agent.get_openai_client", return_value=mock_client):
        metrics = {"win_rate": 25.0, "total_pnl": 6.5, "trade_count": 4}
        failure_data = {"repeat_losers": ["KAITO"]}
        res = agent.get_llm_correction(metrics, failure_data)

    assert res["new_params"]["VOLUME_FLOOR_USD"] == 2000000
    assert "KAITO" in res["blacklist_candidates"]
    assert "LLM Test rationale" in res["rationale"]
