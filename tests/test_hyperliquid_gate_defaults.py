"""Guardrails for Hyperliquid scanner/executor gate defaults."""

import importlib


def test_hyperliquid_executor_and_scanner_default_scores_match(monkeypatch):
    """Executor default must not exceed the scanner-approved execution score."""
    monkeypatch.delenv("HL_PERPS_EXEC_SCORE", raising=False)
    monkeypatch.delenv("HYPERLIQUID_MIN_GEM_SCORE", raising=False)

    import config.settings as settings
    import core.hl_perps_scanner as hl_perps_scanner

    settings = importlib.reload(settings)
    hl_perps_scanner = importlib.reload(hl_perps_scanner)

    assert float(settings.HYPERLIQUID_MIN_GEM_SCORE) == float(
        hl_perps_scanner.HL_PERPS_EXEC_SCORE
    ) == 55.0
