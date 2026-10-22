"""Hyperliquid public market data for offline research (no keys, read-only)."""
from __future__ import annotations

import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

API_URL = "https://api.hyperliquid.xyz/info"
INTERVAL_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
CANDLE_FIELDS = ("t", "T", "o", "h", "l", "c", "v", "n")
DEFAULT_CACHE = Path("data/candles")


def _post(payload: dict, retries: int = 6, timeout: float = 20.0):
    body = json.dumps(payload).encode()
    delay = 1.0
    for attempt in range(retries):
        req = urllib.request.Request(API_URL, body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
    return None


def normalize_candle(c: dict) -> dict:
    out = {"t": int(c["t"]), "T": int(c.get("T", 0) or 0)}
    for k in ("o", "h", "l", "c", "v"):
        out[k] = float(c[k])
    out["n"] = int(c.get("n", 0) or 0)
    return out


def fetch_candles(coin: str, interval: str, start_ms: int, end_ms: Optional[int] = None,
                  pause: float = 0.6) -> list[dict]:
    """Page candleSnapshot forward from start_ms (HL serves ≤5000 bars per call)."""
    step = INTERVAL_MS[interval]
    end_ms = end_ms or int(time.time() * 1000)
    out: dict[int, dict] = {}
    cursor = int(start_ms)
    while cursor < end_ms:
        batch = _post({"type": "candleSnapshot",
                       "req": {"coin": coin, "interval": interval, "startTime": cursor, "endTime": end_ms}}) or []
        if not batch:
            break
        for c in batch:
            n = normalize_candle(c)
            out[n["t"]] = n
        last = max(int(c["t"]) for c in batch)
        if last + step <= cursor:
            break
        cursor = last + step
        if len(batch) < 4000:
            break
        time.sleep(pause)
    return [out[k] for k in sorted(out)]


def fetch_funding_history(coin: str, start_ms: int, end_ms: Optional[int] = None,
                          pause: float = 0.6) -> list[dict]:
    """Hourly funding history (fundingHistory pages ≤500 rows)."""
    end_ms = end_ms or int(time.time() * 1000)
    rows: dict[int, dict] = {}
    cursor = int(start_ms)
    while cursor < end_ms:
        batch = _post({"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms}) or []
        if not batch:
            break
        for r in batch:
            rows[int(r["time"])] = {"time": int(r["time"]), "funding": float(r["fundingRate"]),
                                    "premium": float(r.get("premium") or 0.0)}
        last = max(int(r["time"]) for r in batch)
        if last <= cursor:
            break
        cursor = last + 1
        if len(batch) < 450:
            break
        time.sleep(pause)
    return [rows[k] for k in sorted(rows)]


def cache_path(coin: str, interval: str, root: Path = DEFAULT_CACHE) -> Path:
    return Path(root) / f"{coin.upper()}_{interval}.csv"


def read_cache(coin: str, interval: str, root: Path = DEFAULT_CACHE) -> list[dict]:
    p = cache_path(coin, interval, root)
    if not p.exists():
        return []
    with p.open(newline="") as f:
        return [normalize_candle(r) for r in csv.DictReader(f)]


def merge_candles(*series: Iterable[dict]) -> list[dict]:
    merged: dict[int, dict] = {}
    for s in series:
        for c in s:
            merged[int(c["t"])] = c  # later series win (fresher bar)
    return [merged[k] for k in sorted(merged)]


def write_cache(coin: str, interval: str, candles: list[dict], root: Path = DEFAULT_CACHE) -> Path:
    p = cache_path(coin, interval, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CANDLE_FIELDS)
        w.writeheader()
        for c in candles:
            w.writerow({k: c.get(k, 0) for k in CANDLE_FIELDS})
    tmp.replace(p)
    return p


def load_history(coin: str, interval: str, start_ms: int, root: Path = DEFAULT_CACHE,
                 refresh: bool = True) -> list[dict]:
    """Recorder cache ∪ fresh API pull, persisted back to the cache."""
    cached = read_cache(coin, interval, root)
    fresh = fetch_candles(coin, interval, start_ms) if refresh else []
    merged = merge_candles(cached, fresh)
    if fresh:
        write_cache(coin, interval, merged, root)
    return [c for c in merged if c["t"] >= start_ms]
