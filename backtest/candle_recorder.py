"""Record our own Hyperliquid candles + asset contexts going forward.

Hyperliquid's candleSnapshot only serves the most recent 5000 bars per interval
(~208 days of 1h, ~52 days of 15m) and S3 has no candles, so we keep our own.
Runs as the isolated `candle-recorder` compose service (no .env, no keys, no
trading imports). Each pass merges the latest bars into data/candles/*.csv and
appends one funding/OI/premium snapshot per coin to data/candles/asset_ctxs.csv.

    python3 -m backtest.candle_recorder --once
    python3 -m backtest.candle_recorder --loop --every-min 60
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from backtest import hl_data

log = logging.getLogger("candle_recorder")

# Predator allowlist + hard bans + majors: enough breadth to re-test the allowlist OOS.
DEFAULT_COINS = (
    "BTC,AAVE,MON,DYDX,VVV,XMR,TNSR,VIRTUAL,BANANA,RESOLV,LTC,JUP,PUMP,AERO,INJ,LINK,SKY,SYRUP,"
    "KAITO,APE,HEMI,ONDO,GRASS,TRB,HMSTR,FARTCOIN,MET,EIGEN,MORPHO,LIT,HYPE,BRETT,POPCAT,MEME,"
    "JTO,ENA,ZEC,ETH,BSV,CRV,PENDLE,UNI,ACE,ADA,STABLE,SUI,LDO,ETHFI,SOL,TRX,XRP,DOGE,AVAX,NEAR,ARB"
)
INTERVALS = ("1h", "15m")
LOOKBACK_BARS = 48
CTX_FIELDS = ("ts", "coin", "funding", "premium", "openInterest", "markPx", "oraclePx", "dayNtlVlm")


def coins_from_env() -> list[str]:
    raw = os.getenv("CANDLE_RECORDER_COINS", DEFAULT_COINS)
    return [c.strip().upper() for c in raw.split(",") if c.strip()]


def record_candles(coins, root: Path, now_ms: int | None = None) -> int:
    now_ms = now_ms or int(time.time() * 1000)
    written = 0
    for coin in coins:
        for iv in INTERVALS:
            start = now_ms - LOOKBACK_BARS * hl_data.INTERVAL_MS[iv]
            try:
                fresh = hl_data.fetch_candles(coin, iv, start, now_ms)
            except Exception as e:  # keep recording other coins
                log.warning("candles %s %s failed: %s", coin, iv, e)
                continue
            merged = hl_data.merge_candles(hl_data.read_cache(coin, iv, root), fresh)
            hl_data.write_cache(coin, iv, merged, root)
            written += len(fresh)
            time.sleep(0.4)
    return written


def record_asset_ctxs(coins, root: Path) -> int:
    res = hl_data._post({"type": "metaAndAssetCtxs"})
    if not res or len(res) < 2:
        return 0
    meta, ctxs = res[0], res[1]
    want = set(coins)
    ts = datetime.now(timezone.utc).isoformat()
    p = Path(root) / "asset_ctxs.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    n = 0
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CTX_FIELDS)
        if new:
            w.writeheader()
        for asset, ctx in zip(meta.get("universe", []), ctxs):
            name = str(asset.get("name", "")).upper()
            if name in want and ctx:
                w.writerow({"ts": ts, "coin": name, **{k: ctx.get(k) for k in CTX_FIELDS[2:]}})
                n += 1
    return n


def run_once(root: Path) -> None:
    coins = coins_from_env()
    c = record_candles(coins, root)
    a = record_asset_ctxs(coins, root)
    write_heartbeat(root, candles=c, ctxs=a, coins=len(coins))
    log.info("recorded %d candle rows, %d ctx rows for %d coins → %s", c, a, len(coins), root)


HEARTBEAT = ".recorder_heartbeat"


def write_heartbeat(root: Path, **stats) -> Path:
    """Touch a heartbeat file the compose healthcheck reads (age < 3h = healthy)."""
    p = Path(root) / HEARTBEAT
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(" ".join([datetime.now(timezone.utc).isoformat()] + [f"{k}={v}" for k, v in stats.items()]) + "\n")
    return p


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getenv("CANDLE_RECORDER_DIR", "data/candles"))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true")
    g.add_argument("--loop", action="store_true")
    ap.add_argument("--every-min", type=float, default=float(os.getenv("CANDLE_RECORDER_EVERY_MIN", "60")))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root = Path(a.root)
    if not a.loop:
        run_once(root)
        return
    while True:
        try:
            run_once(root)
        except Exception as e:
            log.warning("recorder pass failed: %s", e)
        time.sleep(max(5.0, a.every_min * 60.0))


if __name__ == "__main__":
    main()
