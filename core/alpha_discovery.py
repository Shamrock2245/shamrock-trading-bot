"""
core/alpha_discovery.py — Continuous alpha discovery worker for Hyperliquid perps.

Ranks every HL perp on free, keyless data and writes the ranked list with a
per-factor score breakdown to data/dashboard/discovery.json.

Signals (all free, no API keys):
  * Hyperliquid info API (metaAndAssetCtxs, candleSnapshot):
      momentum (24h + 4h/24h trend), volume, open interest, funding crowding,
      liquidity (impact spread), volume quality (vol/OI), listing age.
  * CoinGecko /search/trending (public, keyless): social/search sentiment.
Holder concentration / token unlocks: no reliable free source for perps ->
reported as "unavailable", never guessed. Moralis is NOT used and never pads
scores (MORALIS_ENABLED stays false; Moralis is veto/wallet quality only).

How candidates reach trades (paper only, Predator unchanged):
  * Allowlisted, non-banned coins: the HL scanner may scan them in discovery
    rank order (DISCOVERY_FEED_SCANNER). Every entry still goes through
    scan_coin -> Predator v1 -> risk gates. Discovery never opens positions.
  * Off-allowlist coins: "promotion_proposals" only. Adding a coin to the
    allowlist is a human decision. Nothing here edits .env or stops.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
CG_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"

# Weights sum to 100. Fundamentals/liquidity carry real weight so pure pumps
# on thin books cannot top the list.
WEIGHTS = {
    "momentum": 25.0,
    "volume": 15.0,
    "open_interest": 10.0,
    "funding": 10.0,
    "sentiment": 10.0,
    "liquidity": 15.0,
    "volume_quality": 10.0,
    "listing_age": 5.0,
}


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def enabled() -> bool:
    return _flag("DISCOVERY_ENABLED", "true")


def feed_scanner() -> bool:
    return _flag("DISCOVERY_FEED_SCANNER", "true")


def interval_sec() -> int:
    return max(120, int(_f("DISCOVERY_INTERVAL_SEC", "900")))


def top_n() -> int:
    return max(5, int(_f("DISCOVERY_TOP_N", "25")))


def min_day_volume_usd() -> float:
    return _f("DISCOVERY_MIN_DAY_VOLUME_USD", "5000000")


def max_abs_funding_hourly() -> float:
    # 0.0005/h ~ 438% APR: crowded, veto.
    return _f("DISCOVERY_MAX_ABS_FUNDING", "0.0005")


def output_path() -> Path:
    return Path(os.getenv("DASHBOARD_STATE_DIR", "./data/dashboard")) / "discovery.json"


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Candidate:
    coin: str
    score: float
    breakdown: dict
    metrics: dict
    vetoes: list = field(default_factory=list)
    on_allowlist: bool = False
    hard_banned: bool = False
    route: str = "watch"  # "predator_gate" | "promotion_proposal" | "watch" | "vetoed"


# ─── pure scoring (unit-tested) ───────────────────────────────────────────────

def score_coin(ctx: dict, *, median_volume: float, trending_rank: Optional[int],
               candle_closes: Optional[list] = None, listing_age_days: Optional[float] = None) -> tuple[float, dict, dict, list]:
    """Return (score 0-100, breakdown, metrics, vetoes) for one perp context."""
    mark = float(ctx.get("markPx") or 0) or 0.0
    prev = float(ctx.get("prevDayPx") or 0) or 0.0
    vol = float(ctx.get("dayNtlVlm") or 0)
    oi_usd = float(ctx.get("openInterest") or 0) * mark
    funding = float(ctx.get("funding") or 0)
    impact = ctx.get("impactPxs") or []
    chg24 = (mark / prev - 1.0) if prev > 0 and mark > 0 else 0.0

    spread_bps = None
    if len(impact) == 2 and mark > 0:
        try:
            spread_bps = (float(impact[1]) - float(impact[0])) / mark * 1e4
        except (TypeError, ValueError):
            spread_bps = None

    trend = None
    if candle_closes and len(candle_closes) >= 24 and candle_closes[-24] > 0:
        c4 = candle_closes[-1] / candle_closes[-5] - 1 if candle_closes[-5] > 0 else 0
        trend = c4

    # Momentum: reward +2%..+15% day with confirming 4h; punish blow-off >40% and dumps.
    m = _clip((chg24 + 0.02) / 0.17)
    if chg24 > 0.40:
        m *= 0.4
    if trend is not None:
        m = 0.6 * m + 0.4 * _clip((trend + 0.01) / 0.05)
    vol_ratio = vol / median_volume if median_volume > 0 else 0
    v = _clip(math.log10(1 + vol_ratio) / math.log10(11))  # 10x median -> 1.0
    o = _clip(math.log10(1 + oi_usd / 1e6) / math.log10(201))  # $200M OI -> 1.0
    # Funding: neutral/negative = room to run for longs; crowded positive = fade.
    fnd = _clip(1.0 - max(0.0, funding) / max_abs_funding_hourly())
    s = 0.0 if trending_rank is None else _clip(1.0 - trending_rank / 15.0) * 0.5 + 0.5
    if spread_bps is None:
        liq = 0.3
    else:
        liq = _clip(1.0 - spread_bps / 30.0)  # >=30bps impact spread -> 0
    vq_ratio = vol / oi_usd if oi_usd > 0 else 0
    # Healthy turnover ~0.5-5x OI/day. >15x = wash/churn; <0.2 = dead.
    if vq_ratio <= 0:
        vq = 0.0
    elif vq_ratio < 0.2:
        vq = vq_ratio / 0.2 * 0.5
    elif vq_ratio <= 5:
        vq = 1.0
    else:
        vq = _clip(1.0 - (vq_ratio - 5) / 10)
    age = 0.5 if listing_age_days is None else _clip(listing_age_days / 90.0)

    parts = {"momentum": m, "volume": v, "open_interest": o, "funding": fnd,
             "sentiment": s, "liquidity": liq, "volume_quality": vq, "listing_age": age}
    breakdown = {k: round(parts[k] * WEIGHTS[k], 2) for k in WEIGHTS}
    score = round(sum(breakdown.values()), 2)

    vetoes = []
    if vol < min_day_volume_usd():
        vetoes.append("low_volume")
    if abs(funding) > max_abs_funding_hourly():
        vetoes.append("extreme_funding")
    if spread_bps is not None and spread_bps > 50:
        vetoes.append("thin_book")
    if listing_age_days is not None and listing_age_days < 7:
        vetoes.append("new_listing_lt_7d")
    if chg24 < -0.15:
        vetoes.append("dumping")

    metrics = {
        "mark_px": mark, "change_24h_pct": round(chg24 * 100, 2),
        "trend_4h_pct": None if trend is None else round(trend * 100, 2),
        "day_volume_usd": round(vol), "open_interest_usd": round(oi_usd),
        "funding_hourly": funding, "funding_apr_pct": round(funding * 24 * 365 * 100, 1),
        "impact_spread_bps": None if spread_bps is None else round(spread_bps, 1),
        "vol_to_oi": round(vq_ratio, 2), "listing_age_days": listing_age_days,
        "coingecko_trending_rank": trending_rank,
        "holder_unlock_risk": "unavailable (no free source for perps)",
    }
    return score, breakdown, metrics, vetoes


def route_for(coin: str, vetoes: list, allow: set, ban: set) -> str:
    if coin in ban:
        return "vetoed"
    if vetoes:
        return "vetoed"
    if coin in allow:
        return "predator_gate"
    return "promotion_proposal"


# ─── data fetch (free endpoints) ──────────────────────────────────────────────

def _post(body: dict, timeout: float = 15.0):
    import requests
    r = requests.post(HL_INFO_URL, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_hl_contexts() -> dict[str, dict]:
    meta, ctxs = _post({"type": "metaAndAssetCtxs"})
    out = {}
    for asset, ctx in zip(meta.get("universe", []), ctxs):
        if asset.get("isDelisted"):
            continue
        out[str(asset["name"])] = ctx
    return out


def fetch_closes_and_age(coin: str) -> tuple[list, Optional[float]]:
    now_ms = int(time.time() * 1000)
    closes = []
    try:
        cs = _post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h",
                    "startTime": now_ms - 48 * 3600_000, "endTime": now_ms}})
        closes = [float(c["c"]) for c in cs]
    except Exception as e:
        logger.debug(f"discovery: candles {coin} failed: {e}")
    age = None
    try:
        ds = _post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d",
                    "startTime": now_ms - 120 * 86400_000, "endTime": now_ms}})
        if ds:
            age = round((now_ms - int(ds[0]["t"])) / 86400_000, 1)
    except Exception as e:
        logger.debug(f"discovery: daily candles {coin} failed: {e}")
    return closes, age


def fetch_trending_symbols() -> dict[str, int]:
    try:
        import requests
        r = requests.get(CG_TRENDING_URL, timeout=10)
        r.raise_for_status()
        coins = r.json().get("coins", [])
        return {str(c["item"]["symbol"]).upper(): i for i, c in enumerate(coins)}
    except Exception as e:
        logger.info(f"discovery: CoinGecko trending unavailable ({e}) — sentiment=0")
        return {}


def _norm_symbol(coin: str) -> str:
    # HL 1000x tickers: kPEPE -> PEPE (lowercase k only; KAITO stays KAITO)
    return (coin[1:] if coin.startswith("k") else coin).upper()


# ─── cycle ────────────────────────────────────────────────────────────────────

def run_discovery_cycle(
    fetch_ctx: Callable[[], dict] = fetch_hl_contexts,
    fetch_trending: Callable[[], dict] = fetch_trending_symbols,
    fetch_detail: Callable[[str], tuple] = fetch_closes_and_age,
    write: bool = True,
) -> dict:
    from core.predator_v1 import allowlist, hard_ban

    allow, ban = allowlist(), hard_ban()
    ctxs = fetch_ctx()
    trending = fetch_trending()
    vols = sorted(float(c.get("dayNtlVlm") or 0) for c in ctxs.values())
    median = vols[len(vols) // 2] if vols else 0.0

    # Cheap pass on all perps, then candle detail for the top slice + allowlist.
    prelim = []
    for coin, ctx in ctxs.items():
        s, *_ = score_coin(ctx, median_volume=median, trending_rank=trending.get(_norm_symbol(coin)))
        prelim.append((s, coin))
    prelim.sort(reverse=True)
    detail_set = {c for _, c in prelim[: top_n() * 2]} | {c for c in ctxs if c.upper() in allow}

    cands: list[Candidate] = []
    for coin, ctx in ctxs.items():
        closes, age = fetch_detail(coin) if coin in detail_set else (None, None)
        s, br, met, vet = score_coin(ctx, median_volume=median,
                                     trending_rank=trending.get(_norm_symbol(coin)),
                                     candle_closes=closes, listing_age_days=age)
        if coin.upper() in ban:
            vet = vet + ["hard_banned"]
        cands.append(Candidate(coin=coin, score=s, breakdown=br, metrics=met, vetoes=vet,
                               on_allowlist=coin.upper() in allow, hard_banned=coin.upper() in ban,
                               route=route_for(coin.upper(), vet, allow, ban)))
    cands.sort(key=lambda c: c.score, reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(ctxs),
        "weights": WEIGHTS,
        "sources": {"hyperliquid_info": True, "coingecko_trending": bool(trending),
                    "moralis": False, "holder_unlock": "unavailable"},
        "feed_scanner": feed_scanner(),
        "note": "Paper only. Discovery ranks; Predator v1 + risk gates decide. "
                "Off-allowlist coins are proposals for human review, never auto-traded.",
        "top": [asdict(c) for c in cands[: top_n()]],
        "predator_queue": [c.coin for c in cands if c.route == "predator_gate"],
        "promotion_proposals": [
            {"coin": c.coin, "score": c.score} for c in cands
            if c.route == "promotion_proposal"][:10],
    }
    if write:
        p = output_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(p)
    return payload


def priority_order(scan_list: list[str]) -> list[str]:
    """Reorder an (already allowlist-filtered) scan list by discovery rank.

    Never adds coins: membership is unchanged, only order. Stale (>1h) or
    missing discovery data -> original order.
    """
    if not (enabled() and feed_scanner()):
        return scan_list
    try:
        p = output_path()
        if not p.exists() or time.time() - p.stat().st_mtime > 3600:
            return scan_list
        rank = {c: i for i, c in enumerate(json.loads(p.read_text()).get("predator_queue", []))}
    except Exception:
        return scan_list
    big = len(rank) + 1
    return sorted(scan_list, key=lambda c: (rank.get(c, big), scan_list.index(c)))


_thread: Optional[threading.Thread] = None


def start_worker() -> Optional[threading.Thread]:
    global _thread
    if not enabled():
        logger.info("Alpha discovery disabled (DISCOVERY_ENABLED=false)")
        return None
    if _thread and _thread.is_alive():
        return _thread

    def _loop():
        while True:
            try:
                pl = run_discovery_cycle()
                top = ", ".join(f"{c['coin']}:{c['score']:.0f}" for c in pl["top"][:5])
                logger.info(f"🔭 Discovery: {pl['universe_size']} perps ranked | top {top} | "
                            f"predator_queue={pl['predator_queue'][:5]}")
            except Exception as e:
                logger.warning(f"Discovery cycle failed: {e}")
            time.sleep(interval_sec())

    _thread = threading.Thread(target=_loop, daemon=True, name="alpha-discovery")
    _thread.start()
    return _thread
