"""Paper sleeves that stay off the Predator book.

rsi_dip_v1 is always a sleeve. STRATEGY_TOURNAMENT_SLEEVES can name more.
Predator, the promote gate, autoban, and the hot streak never treat these
rows as their own. The reserved names cannot be opted in.
"""
from __future__ import annotations

import os

DEFAULT_SLEEVES = frozenset({"rsi_dip_v1"})
# The main book and empty tags are not sleeves, even if an env lists them.
RESERVED = frozenset({"predator_v1", "hl_perps", ""})


def sleeve_strategies() -> frozenset[str]:
    raw = os.getenv("STRATEGY_TOURNAMENT_SLEEVES", "rsi_dip_v1")
    names = {s.strip() for s in raw.split(",") if s.strip()}
    names.update(DEFAULT_SLEEVES)
    names.difference_update(RESERVED)
    return frozenset(names)


def is_sleeve_strategy(name: object) -> bool:
    return str(name or "") in sleeve_strategies()
