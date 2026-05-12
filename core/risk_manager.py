"""
core/risk_manager.py — Compatibility shim for test imports.

The canonical implementation lives in core/risk.py.
This module re-exports RiskManager and RiskCheck so that any code
importing from ``core.risk_manager`` continues to work without change.
"""
from core.risk import RiskManager, RiskCheck, risk_manager  # noqa: F401

__all__ = ["RiskManager", "RiskCheck", "risk_manager"]
