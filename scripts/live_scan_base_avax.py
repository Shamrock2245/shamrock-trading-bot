"""
scripts/live_scan_base_avax.py — Live gem scan for Base and Avalanche chains.

PRIMARY DATA SOURCE: Moralis Money (discovery, trending, filtered tokens)
SECONDARY SOURCES:   GeckoTerminal (trending/new pools), DexScreener v1 (enrichment)
SECURITY LAYER:      GoPlus Security API (honeypot + contract checks)

Usage:
    python3 scripts/live_scan_base_avax.py

Output:
    - Console table of top candidates with TA scores
    - JSON report saved to reports/live_scan_{timestamp}.json
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("live_scan")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MORALIS_BASE   = "https://deep-index.moralis.io/api/v2.2"
GECKOTERMINAL  = "https://api.geckoterminal.com/api/v2"
DEXSCREENER    = "https://api.dexscreener.com"
GOPLUS_BASE    = "https://api.gopluslabs.io/api/v1"

MORALIS_KEY = os.getenv("MORALIS_API_KEY", "")
MORALIS_HEADERS = {"accept": "application/json", "X-API-Key": MORALIS_KEY} if MORALIS_KEY else {}
GT_HEADERS  = {"accept": "application/json;version=20230302"}
DSC_HEADERS = {"accept": "application/json"}

# Chain configurations
CHAINS = {
    "base": {
        "dex_id": "base",
        "gt_id": "base",
        "chain_id": 8453,
        "chain_hex": "0x2105",
        "moralis_slug": "base",
    },
    "avalanche": {
        "dex_id": "avalanche",
        "gt_id": "avax",
        "chain_id": 43114,
        "chain_hex": "0xa86a",
        "moralis_slug": "avalanche",
    },
}

# Filters
MIN_LIQUIDITY  = 50_000
MIN_VOLUME_24H = 15_000
MIN_SECURITY   = 60
MAX_AGE_HOURS_NEW    = 168   # 7 days — for new gem sniping
MAX_AGE_HOURS_TREND  = 9999  # No cap — trending tokens are established and valid

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def safe_get(url, params=None, headers=None, timeout=12):
    try:
        r = requests.get(url, params=params, headers=headers or DSC_HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"GET {url} failed: {e}")
    return None

def safe_post(url, payload, headers=None, timeout=15):
    try:
        r = requests.post(url, json=payload, headers=headers or DSC_HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"POST {url} failed: {e}")
    return None

def sf(v, d=0.0):
    try: return float(v) if v is not None else d
    except Exception: return d

def si(v, d=0):
    try: return int(v) if v is not None else d
    except Exception: return d

def age_hours(created_ms):
    if not created_ms: return 9999.0
    return (time.time() * 1000 - created_ms) / 3_600_000

# ─────────────────────────────────────────────────────────────────────────────
# Moralis Money (Primary Source)
# ─────────────────────────────────────────────────────────────────────────────
def moralis_top_gainers(chain_slug: str) -> list:
    if not MORALIS_KEY: return []
    data = safe_get(f"{MORALIS_BASE}/discovery/tokens/top-gainers",
                    params={"chain": chain_slug, "time_frame": "1h"},
                    headers=MORALIS_HEADERS)
    tokens = (data or {}).get("result", data if isinstance(data, list) else [])
    logger.info(f"[Moralis] top-gainers {chain_slug}: {len(tokens)}")
    return tokens

def moralis_trending(chain_slug: str) -> list:
    if not MORALIS_KEY: return []
    data = safe_get(f"{MORALIS_BASE}/discovery/tokens/trending",
                    params={"chain": chain_slug},
                    headers=MORALIS_HEADERS)
    tokens = (data or {}).get("result", data if isinstance(data, list) else [])
    logger.info(f"[Moralis] trending {chain_slug}: {len(tokens)}")
    return tokens

def moralis_filtered(chain_hex: str) -> list:
    if not MORALIS_KEY: return []
    payload = {
        "chain": chain_hex,
        "filters": [
            {"metric": "experiencedBuyers", "timeFrame": "oneHour", "gt": 3},
            {"metric": "totalLiquidityUsd", "gt": MIN_LIQUIDITY},
        ],
        "sortBy": {"metric": "experiencedBuyers", "timeFrame": "oneHour", "type": "DESC"},
        "limit": 30,
        "metricsToReturn": [
            "experiencedBuyers", "netBuyers", "volumeUsd",
            "usdPricePercentChange", "totalLiquidityUsd", "securityScore",
        ],
        "timeFramesToReturn": ["oneHour", "oneDay"],
        "excludeMetadata": False,
    }
    data = safe_post(f"{MORALIS_BASE}/discovery/tokens", payload, headers=MORALIS_HEADERS)
    items = (data or {}).get("result", data if isinstance(data, list) else [])
    logger.info(f"[Moralis] filtered {chain_hex}: {len(items)}")
    return items

# ─────────────────────────────────────────────────────────────────────────────
# GeckoTerminal (Secondary Source)
# ─────────────────────────────────────────────────────────────────────────────
def gt_trending(gt_id: str) -> list:
    data = safe_get(f"{GECKOTERMINAL}/networks/{gt_id}/trending_pools",
                    params={"page": 1}, headers=GT_HEADERS)
    pools = (data or {}).get("data", [])
    logger.info(f"[GeckoTerminal] trending {gt_id}: {len(pools)}")
    return pools

def gt_new_pools(gt_id: str) -> list:
    data = safe_get(f"{GECKOTERMINAL}/networks/{gt_id}/new_pools",
                    params={"page": 1}, headers=GT_HEADERS)
    pools = (data or {}).get("data", [])
    logger.info(f"[GeckoTerminal] new_pools {gt_id}: {len(pools)}")
    return pools

def gt_addr(pool: dict) -> str:
    bt = pool.get("relationships", {}).get("base_token", {}).get("data", {})
    raw = bt.get("id", "")
    return raw.split("_")[-1] if "_" in raw else raw

# ─────────────────────────────────────────────────────────────────────────────
# DexScreener v1 (Enrichment Layer)
# ─────────────────────────────────────────────────────────────────────────────
def dsc_pair_data(addr: str, chain: str) -> Optional[dict]:
    """Fetch best pair data for a token using DexScreener v1 API."""
    data = safe_get(f"{DEXSCREENER}/tokens/v1/{chain}/{addr}")
    if not data:
        return None
    pairs = data if isinstance(data, list) else [data]
    chain_pairs = [p for p in pairs if p.get("chainId", "").lower() == chain.lower()]
    if not chain_pairs:
        chain_pairs = pairs
    chain_pairs.sort(key=lambda p: sf(p.get("liquidity", {}).get("usd", 0)), reverse=True)
    return chain_pairs[0] if chain_pairs else None

def dsc_boosts(chain: str) -> list:
    addrs = []
    for ep in ["token-boosts/latest/v1", "token-boosts/top/v1"]:
        data = safe_get(f"{DEXSCREENER}/{ep}")
        items = data if isinstance(data, list) else (data or {}).get("pairs", [])
        for item in items:
            if item.get("chainId", "").lower() == chain.lower():
                addr = item.get("tokenAddress", "")
                if addr:
                    addrs.append(addr)
    return addrs

# ─────────────────────────────────────────────────────────────────────────────
# GoPlus Security
# ─────────────────────────────────────────────────────────────────────────────
def goplus_check(addr: str, chain_id: int) -> tuple[int, list]:
    data = safe_get(f"{GOPLUS_BASE}/token_security/{chain_id}",
                    params={"contract_addresses": addr})
    if not data or data.get("code") != 1:
        return 70, []  # Default neutral if API fails
    info = data.get("result", {}).get(addr.lower(), {})
    if not info:
        return 70, []

    flags = []
    score = 100
    if info.get("is_honeypot") == "1":
        return 0, ["HONEYPOT"]
    if info.get("cannot_sell_all") == "1":
        flags.append("cannot_sell_all"); score -= 40
    if info.get("owner_change_balance") == "1":
        flags.append("owner_drain"); score -= 30
    if info.get("is_open_source") == "0":
        flags.append("unverified"); score -= 20
    buy_tax = sf(info.get("buy_tax", 0))
    sell_tax = sf(info.get("sell_tax", 0))
    if buy_tax > 0.10 or sell_tax > 0.10:
        flags.append(f"high_tax({buy_tax:.0%}/{sell_tax:.0%})"); score -= 25
    elif buy_tax > 0.05 or sell_tax > 0.05:
        flags.append(f"tax({buy_tax:.0%}/{sell_tax:.0%})"); score -= 10
    if info.get("is_blacklisted") == "1":
        flags.append("blacklist"); score -= 15
    if info.get("is_mintable") == "1":
        flags.append("mintable"); score -= 10
    if info.get("hidden_owner") == "1":
        flags.append("hidden_owner"); score -= 15
    return max(0, score), flags

# ─────────────────────────────────────────────────────────────────────────────
# TA Scoring
# ─────────────────────────────────────────────────────────────────────────────
def ta_score(pair: dict) -> dict:
    s = {}
    pc1h  = sf(pair.get("priceChange", {}).get("h1", 0))
    pc6h  = sf(pair.get("priceChange", {}).get("h6", 0))
    vol1h = sf(pair.get("volume", {}).get("h1", 0))
    vol24h= sf(pair.get("volume", {}).get("h24", 0))
    liq   = sf(pair.get("liquidity", {}).get("usd", 0))
    buys  = si((pair.get("txns", {}).get("h1", {}) or {}).get("buys", 0))
    sells = si((pair.get("txns", {}).get("h1", {}) or {}).get("sells", 0))
    mc    = sf(pair.get("marketCap", 0))
    fdv   = sf(pair.get("fdv", 0))
    created = pair.get("pairCreatedAt")
    age_h = age_hours(created)

    avg_h = vol24h / 24 if vol24h > 0 else 0
    spike = vol1h / avg_h if avg_h > 0 else (1.0 if vol24h > 50000 else 0.0)
    total_tx = buys + sells
    buy_ratio = buys / total_tx if total_tx > 0 else 0.5
    fdv_ratio = mc / fdv if fdv > 0 and mc > 0 else 0.5

    s["vol_spike"]    = min(100, spike * 15) if spike > 0 else 20
    s["buy_pressure"] = 100 if buy_ratio>=0.75 else (85 if buy_ratio>=0.65 else (70 if buy_ratio>=0.55 else (50 if buy_ratio>=0.45 else 20)))
    s["momentum"]     = 100 if pc1h>=20 else (80 if pc1h>=10 else (65 if pc1h>=5 else (50 if pc1h>=0 else (30 if pc1h>=-5 else 10))))
    s["trend"]        = 100 if pc6h>=30 else (80 if pc6h>=15 else (65 if pc6h>=5 else (50 if pc6h>=-5 else 20)))
    s["liquidity"]    = 100 if liq>=500000 else (85 if liq>=200000 else (70 if liq>=100000 else (55 if liq>=50000 else 20)))
    s["age"]          = 100 if age_h<=1 else (90 if age_h<=6 else (75 if age_h<=24 else (55 if age_h<=72 else (35 if age_h<=168 else 15))))
    s["fdv_ratio"]    = 100 if fdv_ratio>=0.8 else (80 if fdv_ratio>=0.6 else (60 if fdv_ratio>=0.4 else (40 if fdv_ratio>=0.2 else 20)))

    composite = (
        s["vol_spike"]    * 0.25
        + s["buy_pressure"] * 0.20
        + s["momentum"]     * 0.20
        + s["trend"]        * 0.15
        + s["liquidity"]    * 0.10
        + s["age"]          * 0.05
        + s["fdv_ratio"]    * 0.05
    )
    s["composite"] = round(composite, 1)
    s["_vol1h"] = vol1h; s["_vol24h"] = vol24h; s["_liq"] = liq
    s["_buys"] = buys; s["_sells"] = sells; s["_pc1h"] = pc1h
    s["_pc6h"] = pc6h; s["_pc24h"] = sf(pair.get("priceChange", {}).get("h24", 0))
    s["_age_h"] = round(age_h, 1); s["_spike"] = round(spike, 2)
    s["_buy_ratio"] = round(buy_ratio, 3)
    return s

# ─────────────────────────────────────────────────────────────────────────────
# Chain Scanner
# ─────────────────────────────────────────────────────────────────────────────
def scan_chain(chain_name: str, cfg: dict) -> list:
    gt_id    = cfg["gt_id"]
    chain_id = cfg["chain_id"]
    moralis  = cfg["moralis_slug"]
    chain_hex= cfg["chain_hex"]

    candidates = {}  # addr_lower -> metadata

    def add(addr, source, extra=None):
        k = addr.lower()
        if not k or len(k) < 10: return
        if k not in candidates:
            candidates[k] = {"address": addr, "sources": [], "moralis": {}}
        if source not in candidates[k]["sources"]:
            candidates[k]["sources"].append(source)
        if extra:
            candidates[k]["moralis"].update(extra)

    # ── Moralis Money (PRIMARY) ────────────────────────────────────────────
    for t in moralis_top_gainers(moralis):
        addr = t.get("token_address", "")
        if addr:
            add(addr, "moralis_gainers", {
                "pc1h": sf(t.get("price_percent_change_usd", {}).get("1h", 0)),
                "strength": sf(t.get("on_chain_strength_index", 0)),
                "security": si(t.get("security_score", 0)),
                "mc": sf(t.get("market_cap", 0)),
                "twitter": si(t.get("twitter_followers", 0)),
                "exp_buyers_1h": sf((t.get("experienced_net_buyers_change") or {}).get("1h", 0)),
                "symbol": t.get("symbol", ""),
                "name": t.get("name", ""),
            })

    for t in moralis_trending(moralis):
        addr = t.get("token_address", t.get("address", ""))
        if addr:
            add(addr, "moralis_trending")

    for item in moralis_filtered(chain_hex):
        meta = item.get("metadata", item)
        addr = meta.get("tokenAddress", meta.get("token_address", ""))
        if not addr: continue
        metrics = item.get("metrics", {})
        add(addr, "moralis_filtered", {
            "exp_buyers_1h": si((metrics.get("experiencedBuyers") or {}).get("oneHour", 0)),
            "net_buyers_1h": sf((metrics.get("netBuyers") or {}).get("oneHour", 0)),
            "vol_1h": sf((metrics.get("volumeUsd") or {}).get("oneHour", 0)),
            "security": si((metrics.get("securityScore") or {}).get("oneHour",
                meta.get("security", {}).get("securityScore", 0))),
            "is_honeypot": meta.get("security", {}).get("isHoneyPot", False),
            "buy_tax": sf(meta.get("security", {}).get("buyTax", 0)),
            "sell_tax": sf(meta.get("security", {}).get("sellTax", 0)),
            "symbol": meta.get("symbol", ""),
            "name": meta.get("name", ""),
            "liq": sf(meta.get("totalLiquidityUsd", 0)),
            "mc": sf(meta.get("marketCap", 0)),
        })

    # ── GeckoTerminal (SECONDARY) ──────────────────────────────────────────
    for pool in gt_trending(gt_id):
        addr = gt_addr(pool)
        if addr:
            attrs = pool.get("attributes", {})
            add(addr, "gt_trending", {
                "gt_liq": sf(attrs.get("reserve_in_usd", 0)),
                "gt_vol24h": sf((attrs.get("volume_usd") or {}).get("h24", 0)),
                "gt_pc1h": sf((attrs.get("price_change_percentage") or {}).get("h1", 0)),
            })

    for pool in gt_new_pools(gt_id):
        addr = gt_addr(pool)
        if addr:
            add(addr, "gt_new")

    # ── DexScreener Boosts (TERTIARY) ─────────────────────────────────────
    for addr in dsc_boosts(chain_name):
        add(addr, "dsc_boost")

    logger.info(f"[{chain_name.upper()}] {len(candidates)} unique candidates to score")

    # ── Score each candidate ───────────────────────────────────────────────
    scored = []
    for addr_lower, cand in list(candidates.items()):
        addr = cand["address"]
        m = cand.get("moralis", {})

        # Skip Moralis-flagged honeypots immediately
        if m.get("is_honeypot"):
            continue

        # Fetch DexScreener v1 pair data
        pair = dsc_pair_data(addr, chain_name)
        if pair is None:
            # Build minimal pair from Moralis/GT data
            liq = m.get("liq", m.get("gt_liq", 0))
            vol24h = m.get("vol24h", m.get("gt_vol24h", 0))
            if liq < MIN_LIQUIDITY or vol24h < MIN_VOLUME_24H:
                continue
            pair = {
                "baseToken": {"address": addr, "symbol": m.get("symbol", addr[:8]), "name": m.get("name", "")},
                "liquidity": {"usd": liq},
                "volume": {"h24": vol24h, "h1": m.get("vol_1h", 0)},
                "priceChange": {"h1": m.get("pc1h", m.get("gt_pc1h", 0)), "h6": 0, "h24": 0},
                "txns": {"h1": {"buys": 0, "sells": 0}},
                "priceUsd": "0", "marketCap": m.get("mc", 0), "fdv": m.get("mc", 0),
                "pairCreatedAt": None,
                "url": f"https://dexscreener.com/{chain_name}/{addr}",
            }

        liq   = sf(pair.get("liquidity", {}).get("usd", 0))
        vol24h= sf(pair.get("volume", {}).get("h24", 0))
        if liq < MIN_LIQUIDITY or vol24h < MIN_VOLUME_24H:
            continue
        # Trending tokens (gt_trending, dsc_boost) bypass the age cap
        is_trending = any(s in ("gt_trending", "dsc_boost", "moralis_gainers", "moralis_trending", "moralis_filtered") 
                         for s in cand["sources"])
        age_cap = MAX_AGE_HOURS_TREND if is_trending else MAX_AGE_HOURS_NEW
        if age_hours(pair.get("pairCreatedAt")) > age_cap:
            continue

        # GoPlus security check
        sec_score, flags = goplus_check(addr, chain_id)
        if sec_score == 0 or sec_score < MIN_SECURITY:
            continue

        # TA scoring
        ta = ta_score(pair)

        # Multi-source bonus
        src_count = len(set(cand["sources"]))
        src_bonus = min(15.0, src_count * 5.0)

        # Moralis alpha bonus
        m_bonus = 0.0
        if m.get("exp_buyers_1h", 0) >= 10: m_bonus += 8.0
        elif m.get("exp_buyers_1h", 0) >= 5: m_bonus += 4.0
        if m.get("net_buyers_1h", 0) > 0: m_bonus += 5.0
        if m.get("strength", 0) >= 70: m_bonus += 5.0
        m_bonus = min(15.0, m_bonus)

        final = min(100.0, ta["composite"] + src_bonus + m_bonus)

        bt = pair.get("baseToken", {})
        scored.append({
            "rank": 0,
            "chain": chain_name.upper(),
            "address": addr,
            "symbol": bt.get("symbol", m.get("symbol", addr[:8])),
            "name": bt.get("name", m.get("name", "")),
            "price_usd": sf(pair.get("priceUsd", 0)),
            "market_cap": sf(pair.get("marketCap", 0)),
            "liquidity_usd": liq,
            "volume_1h": ta["_vol1h"],
            "volume_24h": ta["_vol24h"],
            "price_change_1h": ta["_pc1h"],
            "price_change_6h": ta["_pc6h"],
            "price_change_24h": ta["_pc24h"],
            "age_hours": ta["_age_h"],
            "buys_1h": ta["_buys"],
            "sells_1h": ta["_sells"],
            "buy_ratio_1h": ta["_buy_ratio"],
            "volume_spike": ta["_spike"],
            "ta_vol_spike": ta["vol_spike"],
            "ta_buy_pressure": ta["buy_pressure"],
            "ta_momentum": ta["momentum"],
            "ta_trend": ta["trend"],
            "ta_composite": ta["composite"],
            "moralis_exp_buyers_1h": m.get("exp_buyers_1h", 0),
            "moralis_net_buyers_1h": m.get("net_buyers_1h", 0),
            "moralis_strength": m.get("strength", 0),
            "moralis_security": m.get("security", sec_score),
            "moralis_twitter": m.get("twitter", 0),
            "security_score": sec_score,
            "security_flags": flags,
            "sources": list(set(cand["sources"])),
            "source_count": src_count,
            "source_bonus": src_bonus,
            "moralis_bonus": m_bonus,
            "final_score": round(final, 1),
            "dex_url": pair.get("url", f"https://dexscreener.com/{chain_name}/{addr}"),
        })
        time.sleep(0.25)

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    for i, r in enumerate(scored):
        r["rank"] = i + 1
    return scored

# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 90)
    print("  🍀 SHAMROCK TRADING BOT — LIVE GEM SCAN")
    print(f"  Chains: BASE + AVALANCHE    Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Primary Source: {'Moralis Money ✅' if MORALIS_KEY else 'GeckoTerminal (Moralis key not set)'}")
    print("=" * 90)

    all_results = {}
    for chain_name, cfg in CHAINS.items():
        print(f"\n{'─' * 90}")
        print(f"  Scanning {chain_name.upper()}...")
        print(f"{'─' * 90}")
        results = scan_chain(chain_name, cfg)
        all_results[chain_name] = results

        if not results:
            print(f"  No candidates passed filters on {chain_name.upper()}")
            continue

        top = results[:10]
        print(f"\n  TOP {len(top)} GEMS — {chain_name.upper()}\n")
        print(f"  {'#':<3} {'SYMBOL':<10} {'SCORE':>6} {'PRICE':>12} {'LIQ':>12} {'VOL1H':>11} {'SPIKE':>6} {'1H%':>7} {'6H%':>7} {'AGE':>6} {'BUY%':>6}")
        print(f"  {'─'*3} {'─'*10} {'─'*6} {'─'*12} {'─'*12} {'─'*11} {'─'*6} {'─'*7} {'─'*7} {'─'*6} {'─'*6}")
        for r in top:
            liq_s  = f"${r['liquidity_usd']:,.0f}"
            vol_s  = f"${r['volume_1h']:,.0f}"
            pr_s   = f"${r['price_usd']:.6f}" if r['price_usd'] < 0.01 else f"${r['price_usd']:.4f}"
            age_s  = f"{r['age_hours']:.0f}h" if r['age_hours'] < 999 else "old"
            spk_s  = f"{r['volume_spike']:.1f}x"
            print(f"  {r['rank']:<3} {r['symbol']:<10} {r['final_score']:>6.1f} {pr_s:>12} {liq_s:>12} {vol_s:>11} {spk_s:>6} {r['price_change_1h']:>+7.1f}% {r['price_change_6h']:>+7.1f}% {age_s:>6} {r['buy_ratio_1h']:>6.0%}")

        print(f"\n  ── TOP 3 DETAILED ──────────────────────────────────────────────────────────")
        for r in results[:3]:
            sig = "🟢 BUY" if r['final_score'] >= 75 else ("🟡 WATCH" if r['final_score'] >= 60 else "⚪ SKIP")
            print(f"\n  [{sig}] {r['symbol']} — Score {r['final_score']:.1f}/100")
            print(f"    Address:   {r['address']}")
            print(f"    Price:     ${r['price_usd']:.8f}  |  MC: ${r['market_cap']:,.0f}")
            print(f"    Liquidity: ${r['liquidity_usd']:,.0f}  |  Vol 1h: ${r['volume_1h']:,.0f}  |  Spike: {r['volume_spike']:.1f}x")
            print(f"    1h: {r['price_change_1h']:+.2f}%  |  6h: {r['price_change_6h']:+.2f}%  |  Age: {r['age_hours']:.1f}h")
            print(f"    Buys/Sells: {r['buys_1h']}/{r['sells_1h']}  ({r['buy_ratio_1h']:.0%} buys)")
            print(f"    TA:        vol_spike={r['ta_vol_spike']:.0f}  buy_pressure={r['ta_buy_pressure']:.0f}  momentum={r['ta_momentum']:.0f}  trend={r['ta_trend']:.0f}")
            if r.get("moralis_exp_buyers_1h", 0) > 0:
                print(f"    Moralis:   exp_buyers={r['moralis_exp_buyers_1h']}  net_buyers={r['moralis_net_buyers_1h']:.0f}  strength={r['moralis_strength']:.0f}")
            print(f"    Security:  {r['security_score']}/100  flags={r['security_flags'] or 'none'}")
            print(f"    Sources:   {', '.join(r['sources'])}")
            print(f"    Link:      {r['dex_url']}")
            if r['final_score'] >= 75:
                if chain_name == "avalanche":
                    print(f"    ⚡ ACTION: Deploy USDC via Trader Joe V2 / Pharaoh on AVAX")
                else:
                    print(f"    ⚡ ACTION: Deploy ETH/USDC via Aerodrome / Uniswap V3 on Base")

    # Save report
    os.makedirs("reports", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "moralis_enabled": bool(MORALIS_KEY),
        "filters": {"min_liq": MIN_LIQUIDITY, "min_vol24h": MIN_VOLUME_24H, "min_security": MIN_SECURITY},
        "results": all_results,
        "summary": {
            chain: {
                "total": len(r),
                "buy_signals": len([x for x in r if x["final_score"] >= 75]),
                "watchlist": len([x for x in r if 60 <= x["final_score"] < 75]),
                "top_pick": r[0]["symbol"] if r else None,
                "top_score": r[0]["final_score"] if r else 0,
            }
            for chain, r in all_results.items()
        },
    }
    with open(f"reports/live_scan_{ts}.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'=' * 90}")
    print(f"  📊 SCAN SUMMARY")
    print(f"{'─' * 90}")
    for chain, s in report["summary"].items():
        print(f"  {chain.upper():<12} {s['total']:>3} candidates  🟢 {s['buy_signals']} buy  🟡 {s['watchlist']} watch  Top: {s['top_pick'] or 'none'} ({s['top_score']:.1f})")
    print(f"\n  Report: reports/live_scan_{ts}.json")
    print(f"{'=' * 90}\n")
    return report

if __name__ == "__main__":
    main()
