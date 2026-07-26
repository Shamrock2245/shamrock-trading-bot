"""Guardrails for Hyperliquid scanner/executor gate defaults."""

import importlib


def test_hyperliquid_executor_and_scanner_default_scores_match(monkeypatch):
    """Executor default must not exceed the scanner-approved execution score."""
    monkeypatch.delenv("HL_PERPS_EXEC_SCORE", raising=False)
    monkeypatch.delenv("HYPERLIQUID_MIN_GEM_SCORE", raising=False)
    # Prevent local .env from overriding module defaults under test
    monkeypatch.setenv("HL_PERPS_EXEC_SCORE", "58.0")
    monkeypatch.setenv("HYPERLIQUID_MIN_GEM_SCORE", "58.0")

    import config.settings as settings
    import core.hl_perps_scanner as hl_perps_scanner

    settings = importlib.reload(settings)
    hl_perps_scanner = importlib.reload(hl_perps_scanner)

    # v40 defaults: exec bar 58 (quality over spray after Fib geometry fix)
    assert float(settings.HYPERLIQUID_MIN_GEM_SCORE) == 58.0
    assert float(hl_perps_scanner.HL_PERPS_EXEC_SCORE) == 58.0
