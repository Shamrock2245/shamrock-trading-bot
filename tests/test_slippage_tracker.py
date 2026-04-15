"""
tests/test_slippage_tracker.py — Unit tests for slippage analytics.
"""

import pytest
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSlippageTrackerImport:
    def test_import(self):
        from core.slippage_tracker import record_slippage, get_slippage_summary
        assert callable(record_slippage)
        assert callable(get_slippage_summary)


class TestSlippageRecording:
    def test_record_returns_dict(self, tmp_path, monkeypatch):
        """Recording slippage should return the record dict."""
        monkeypatch.setattr("core.slippage_tracker.SLIPPAGE_FILE", tmp_path / "slip.json")
        from core.slippage_tracker import record_slippage
        result = record_slippage(
            token_symbol="PEPE",
            chain="base",
            direction="buy",
            expected_amount_out=1000.0,
            actual_amount_out=970.0,
            slippage_bps_configured=100,
        )
        assert result is not None
        assert result["slippage_bps"] == pytest.approx(300.0, rel=0.01)  # (1000-970)/1000 * 10000 = 300bps
        assert result["excess_slippage_bps"] == pytest.approx(200.0, rel=0.01)  # 300 - 100

    def test_no_slippage_case(self, tmp_path, monkeypatch):
        """Zero slippage should produce 0 bps."""
        monkeypatch.setattr("core.slippage_tracker.SLIPPAGE_FILE", tmp_path / "slip2.json")
        from core.slippage_tracker import record_slippage
        result = record_slippage(
            token_symbol="WETH",
            chain="ethereum",
            direction="sell",
            expected_amount_out=500.0,
            actual_amount_out=500.0,
        )
        assert result["slippage_bps"] == 0.0
        assert result["excess_slippage_bps"] == 0.0

    def test_invalid_input_returns_none(self, tmp_path, monkeypatch):
        """Zero expected amount should return None."""
        monkeypatch.setattr("core.slippage_tracker.SLIPPAGE_FILE", tmp_path / "slip3.json")
        from core.slippage_tracker import record_slippage
        result = record_slippage(
            token_symbol="ZERO",
            chain="base",
            direction="buy",
            expected_amount_out=0.0,
            actual_amount_out=0.0,
        )
        assert result is None


class TestSlippageSummary:
    def test_empty_summary(self, tmp_path, monkeypatch):
        """Summary with no data should return zero trades."""
        monkeypatch.setattr("core.slippage_tracker.SLIPPAGE_FILE", tmp_path / "empty.json")
        from core.slippage_tracker import get_slippage_summary
        summary = get_slippage_summary(days=7)
        assert summary["total_trades"] == 0

    def test_summary_with_data(self, tmp_path, monkeypatch):
        """Summary after recording should reflect the recorded data."""
        monkeypatch.setattr("core.slippage_tracker.SLIPPAGE_FILE", tmp_path / "full.json")
        from core.slippage_tracker import record_slippage, get_slippage_summary

        record_slippage("TOKEN1", "base", "buy", 100.0, 95.0, 200)
        record_slippage("TOKEN2", "solana", "buy", 200.0, 190.0, 100)

        summary = get_slippage_summary(days=1)
        assert summary["total_trades"] == 2
        assert summary["avg_slippage_bps"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
