"""
data/providers/moralis_datafeeds.py — Moralis Data Feeds (self-hosted) client.

Data Feeds is NOT a REST drop-in. Moralis Continuum sink writes decoded chain
data into YOUR Postgres/ClickHouse. We query those tables with SQL.

Recipes that replace sunsetting REST endpoints (July 31 2026):

  Solana top-holders / holder metrics
    → Token Holders recipe  (table: token_holders)

  Pump.fun new / bonding / graduated + bonding-status
    → Token Bonding Status recipe
      (tables: launchpad_events, token_bonding_status)

  EVM historical holders
    → Historical Balances + Token Transfers recipes

Setup (once you have early access + cm_live_ key):
  1. Admin panel → Data Feeds → generate starter pack for recipes above
  2. docker compose up the sink (Postgres destination)
  3. Set MORALIS_DATAFEEDS_DSN=postgresql://sdf:…@localhost:5544/sdf
  4. Optional: MORALIS_DATAFEEDS_ENABLED=true

When DSN is unset or DB is down, all functions return empty / None and callers
fall through to free alternatives (Helius, DexScreener, public RPC).

CU cost of Data Feeds queries: 0 (local SQL).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# pump.fun program id used as exchange_address in launchpadEvents
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

DATAFEEDS_ENABLED: bool = (
    str(getattr(settings, "MORALIS_DATAFEEDS_ENABLED", "false")).lower() == "true"
    or bool(getattr(settings, "MORALIS_DATAFEEDS_DSN", ""))
)
DATAFEEDS_DSN: str = getattr(settings, "MORALIS_DATAFEEDS_DSN", "") or ""

# Table name overrides (starter packs sometimes rename)
TABLE_TOKEN_HOLDERS = getattr(settings, "MORALIS_DF_TABLE_HOLDERS", "token_holders")
TABLE_LAUNCHPAD_EVENTS = getattr(settings, "MORALIS_DF_TABLE_LAUNCHPAD", "launchpad_events")
TABLE_BONDING_STATUS = getattr(settings, "MORALIS_DF_TABLE_BONDING", "token_bonding_status")

_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, Any]] = {}
_engine = None
_engine_failed = False


def available() -> bool:
    """True if Data Feeds DSN is configured and we can obtain a connection."""
    if not DATAFEEDS_DSN:
        return False
    eng = _get_engine()
    return eng is not None


def _get_engine():
    """Lazy SQLAlchemy engine. Returns None if unavailable."""
    global _engine, _engine_failed
    if _engine is not None:
        return _engine
    if _engine_failed or not DATAFEEDS_DSN:
        return None
    try:
        from sqlalchemy import create_engine
        _engine = create_engine(
            DATAFEEDS_DSN,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
            future=True,
        )
        # Probe
        with _engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        logger.info("DataFeeds: connected to Postgres sink")
        return _engine
    except Exception as e:
        _engine_failed = True
        logger.warning(f"DataFeeds: unavailable ({e}) — using free fallbacks")
        return None


def _cached(key: str):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _set_cache(key: str, val: Any) -> Any:
    _cache[key] = (time.time(), val)
    return val


def _query(sql: str, params: dict | None = None) -> list[dict]:
    eng = _get_engine()
    if eng is None:
        return []
    try:
        from sqlalchemy import text
        with eng.connect() as conn:
            rows = conn.execute(text(sql), params or {})
            cols = list(rows.keys())
            return [dict(zip(cols, row)) for row in rows.fetchall()]
    except Exception as e:
        logger.debug(f"DataFeeds query error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Token Holders (replaces Solana top-holders + EVM owners-style reads)
# ─────────────────────────────────────────────────────────────────────────────
def get_top_holders(token_address: str, limit: int = 10, chain: str = "solana") -> dict:
    """
    Return holder list + concentration in the same shape as
    moralis_solana.get_token_top_holders().

    Solana addresses are case-sensitive base58 — do NOT lower-case.
    """
    if not available() or not token_address:
        return {"holders": [], "top10_concentration": 0.0, "concentration_risk": "unknown", "source": "datafeeds_unavailable"}

    cache_key = f"df_holders_{chain}_{token_address}_{limit}"
    hit = _cached(cache_key)
    if hit is not None:
        return hit

    # Solana mints must match case-sensitive; EVM lowercased in recipe
    addr = token_address if chain == "solana" else token_address.lower()
    rows = _query(
        f"""
        SELECT wallet_address, balance, usd_value
        FROM {TABLE_TOKEN_HOLDERS}
        WHERE token_address = :addr AND balance > 0
        ORDER BY balance DESC
        LIMIT :lim
        """,
        {"addr": addr, "lim": limit},
    )
    if not rows:
        return _set_cache(cache_key, {
            "holders": [],
            "top10_concentration": 0.0,
            "concentration_risk": "unknown",
            "source": "datafeeds_empty",
        })

    # Estimate concentration from relative balances (total supply not always present)
    balances = []
    for r in rows:
        try:
            balances.append(float(r.get("balance") or 0))
        except (TypeError, ValueError):
            balances.append(0.0)
    total = sum(balances) or 1.0
    holders = []
    for r, bal in zip(rows, balances):
        pct = (bal / total) * 100.0
        holders.append({
            "address": r.get("wallet_address") or "",
            "balance": bal,
            "percentage": pct,
            "usd_value": float(r.get("usd_value") or 0),
        })
    top10_pct = sum(h["percentage"] for h in holders[:10])
    if top10_pct >= 80:
        risk = "critical"
    elif top10_pct >= 50:
        risk = "high"
    elif top10_pct >= 30:
        risk = "medium"
    else:
        risk = "low"

    result = {
        "holders": holders,
        "top10_concentration": top10_pct / 100.0,
        "concentration_risk": risk,
        "source": "datafeeds",
    }
    return _set_cache(cache_key, result)


# ─────────────────────────────────────────────────────────────────────────────
# Launchpad / Pump.fun discovery (replaces /exchange/pumpfun/*)
# ─────────────────────────────────────────────────────────────────────────────
def get_pumpfun_new(limit: int = 20) -> list[dict]:
    if not available():
        return []
    cache_key = f"df_pf_new_{limit}"
    hit = _cached(cache_key)
    if hit is not None:
        return hit

    rows = _query(
        f"""
        SELECT token_address,
               MAX(token_name)   AS name,
               MAX(token_symbol) AS symbol,
               MIN(event_ts)     AS created_at
        FROM {TABLE_LAUNCHPAD_EVENTS}
        WHERE exchange_address = :ex
          AND event_type = 'created'
        GROUP BY token_address
        ORDER BY created_at DESC
        LIMIT :lim
        """,
        {"ex": PUMPFUN_PROGRAM_ID, "lim": limit},
    )
    result = [{
        "address": r.get("token_address") or "",
        "token_address": r.get("token_address") or "",
        "symbol": r.get("symbol") or "",
        "name": r.get("name") or "",
        "created_at": str(r.get("created_at") or ""),
        "bonding_pct": 0.0,
        "market_cap": 0.0,
        "volume_24h": 0.0,
        "source": "datafeeds_pumpfun_new",
        "chain": "solana",
    } for r in rows if r.get("token_address")]
    return _set_cache(cache_key, result)


def get_pumpfun_bonding(limit: int = 20) -> list[dict]:
    if not available():
        return []
    cache_key = f"df_pf_bond_{limit}"
    hit = _cached(cache_key)
    if hit is not None:
        return hit

    # Prefer status table if present; fall back to events aggregate
    rows = _query(
        f"""
        SELECT token_address,
               bonding_progress AS bonding_pct,
               token_name AS name,
               token_symbol AS symbol
        FROM {TABLE_BONDING_STATUS}
        WHERE exchange_address = :ex
          AND COALESCE(graduated, false) = false
          AND COALESCE(bonding_progress, 0) < 100
        ORDER BY bonding_progress DESC NULLS LAST
        LIMIT :lim
        """,
        {"ex": PUMPFUN_PROGRAM_ID, "lim": limit},
    )
    if not rows:
        rows = _query(
            f"""
            SELECT token_address,
                   MAX(progress_percentage) AS bonding_pct,
                   MAX(token_name) AS name,
                   MAX(token_symbol) AS symbol
            FROM {TABLE_LAUNCHPAD_EVENTS}
            WHERE exchange_address = :ex
            GROUP BY token_address
            HAVING MAX(CASE WHEN event_type = 'migrated' THEN 1 ELSE 0 END) = 0
            ORDER BY bonding_pct DESC NULLS LAST
            LIMIT :lim
            """,
            {"ex": PUMPFUN_PROGRAM_ID, "lim": limit},
        )

    result = []
    for r in rows:
        pct = float(r.get("bonding_pct") or 0)
        result.append({
            "address": r.get("token_address") or "",
            "token_address": r.get("token_address") or "",
            "symbol": r.get("symbol") or "",
            "name": r.get("name") or "",
            "bonding_pct": pct,
            "market_cap": 0.0,
            "volume_24h": 0.0,
            "near_graduation": pct >= 80,
            "source": "datafeeds_pumpfun_bonding",
            "chain": "solana",
        })
    return _set_cache(cache_key, result)


def get_pumpfun_graduated(limit: int = 20) -> list[dict]:
    if not available():
        return []
    cache_key = f"df_pf_grad_{limit}"
    hit = _cached(cache_key)
    if hit is not None:
        return hit

    rows = _query(
        f"""
        SELECT token_address,
               MIN(CASE WHEN event_type = 'migrated' THEN event_ts END) AS graduated_at,
               MAX(pool_address) AS pair_address,
               MAX(token_name) AS name,
               MAX(token_symbol) AS symbol
        FROM {TABLE_LAUNCHPAD_EVENTS}
        WHERE exchange_address = :ex
        GROUP BY token_address
        HAVING MAX(CASE WHEN event_type = 'migrated' THEN 1 ELSE 0 END) = 1
        ORDER BY graduated_at DESC NULLS LAST
        LIMIT :lim
        """,
        {"ex": PUMPFUN_PROGRAM_ID, "lim": limit},
    )
    result = [{
        "token_address": r.get("token_address") or "",
        "address": r.get("token_address") or "",
        "name": r.get("name") or "",
        "symbol": r.get("symbol") or "",
        "pair_address": r.get("pair_address") or "",
        "price_usd": 0.0,
        "liquidity_usd": 0.0,
        "volume_24h": 0.0,
        "graduated_at": str(r.get("graduated_at") or ""),
        "market_cap": 0.0,
        "source": "datafeeds_pumpfun_graduated",
        "chain": "solana",
    } for r in rows if r.get("token_address")]
    return _set_cache(cache_key, result)


def get_bonding_status(token_address: str) -> Optional[dict]:
    """Per-token bonding status for Solana launchpad mints."""
    if not available() or not token_address:
        return None
    cache_key = f"df_bond_status_{token_address}"
    hit = _cached(cache_key)
    if hit is not None:
        return hit

    rows = _query(
        f"""
        SELECT token_address, bonding_progress, graduated, graduated_at,
               launchpad_platform, exchange_address
        FROM {TABLE_BONDING_STATUS}
        WHERE token_address = :addr
        LIMIT 1
        """,
        {"addr": token_address},
    )
    if not rows:
        rows = _query(
            f"""
            SELECT token_address,
                   MAX(progress_percentage) AS bonding_progress,
                   MAX(CASE WHEN event_type = 'migrated' THEN 1 ELSE 0 END) = 1 AS graduated,
                   MIN(CASE WHEN event_type = 'migrated' THEN event_ts END) AS graduated_at,
                   MAX(launchpad_platform) AS launchpad_platform,
                   MAX(exchange_address) AS exchange_address
            FROM {TABLE_LAUNCHPAD_EVENTS}
            WHERE token_address = :addr
            GROUP BY token_address
            """,
            {"addr": token_address},
        )
    if not rows:
        return _set_cache(cache_key, None)

    r = rows[0]
    graduated = bool(r.get("graduated"))
    progress = float(r.get("bonding_progress") or 0)
    result = {
        "is_bonding": (not graduated) and progress < 100,
        "exchange": r.get("launchpad_platform") or r.get("exchange_address") or "pumpfun",
        "bonding_type": "bonding_curve",
        "bonding_status": "graduated" if graduated else "bonding",
        "graduation_pct": 100.0 if graduated else progress,
        "is_graduated": graduated,
        "source": "datafeeds",
    }
    return _set_cache(cache_key, result)


def status() -> dict:
    """Health snapshot for dashboards / preflight."""
    return {
        "enabled": DATAFEEDS_ENABLED,
        "dsn_configured": bool(DATAFEEDS_DSN),
        "connected": available(),
        "tables": {
            "holders": TABLE_TOKEN_HOLDERS,
            "launchpad": TABLE_LAUNCHPAD_EVENTS,
            "bonding": TABLE_BONDING_STATUS,
        },
    }
