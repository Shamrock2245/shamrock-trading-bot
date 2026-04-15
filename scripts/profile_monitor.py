#!/usr/bin/env python3
"""
scripts/profile_monitor.py — Profile the position monitor loop.

Usage:
    python scripts/profile_monitor.py              # Profile 5 monitor ticks
    python scripts/profile_monitor.py --ticks 10   # Profile N ticks

Outputs:
    output/profile_monitor.prof — Binary profile data
    Console                     — Top 30 functions by cumulative time
"""

import argparse
import asyncio
import cProfile
import os
import pstats
import sys
import time
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MODE", "paper")

from core.position_monitor import PositionMonitor, load_positions


def profile_monitor(ticks: int = 5):
    """Run N monitor ticks under cProfile."""
    monitor = PositionMonitor(is_paper=True)
    positions = load_positions()

    print("☘️  Shamrock Position Monitor Profiler")
    print("=" * 60)
    print(f"Open positions: {len(positions)}")
    print(f"Ticks to profile: {ticks}")
    print()

    if not positions:
        print("⚠️  No open positions found — nothing to profile.")
        print("   Open some positions first, then re-run.")
        return 0, 0

    profiler = cProfile.Profile()
    t0 = time.perf_counter()

    profiler.enable()
    for i in range(ticks):
        try:
            monitor._check_positions_once()
        except AttributeError:
            # Fallback: try the async version
            try:
                asyncio.run(monitor._tick())
            except Exception as e:
                print(f"  Tick {i+1} error: {e}")
                break
    profiler.disable()

    elapsed = time.perf_counter() - t0

    print(f"\n✅ {ticks} ticks complete in {elapsed:.2f}s ({elapsed/ticks:.3f}s per tick)")
    print()

    # Top 30 by cumulative
    print("=" * 60)
    print("TOP 30 FUNCTIONS BY CUMULATIVE TIME")
    print("=" * 60)
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs()
    stats.sort_stats("cumulative")
    stats.print_stats(30)
    print(stream.getvalue())

    # Save profile
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    prof_path = output_dir / "profile_monitor.prof"
    profiler.dump_stats(str(prof_path))
    print(f"📊 Profile saved to {prof_path}")
    print(f"   Visualize: python -m snakeviz {prof_path}")

    return elapsed, ticks


def main():
    parser = argparse.ArgumentParser(description="Profile the position monitor")
    parser.add_argument("--ticks", type=int, default=5, help="Number of monitor ticks to profile")
    args = parser.parse_args()

    elapsed, ticks = profile_monitor(args.ticks)

    if ticks > 0:
        print()
        print("=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)
        per_tick = elapsed / max(ticks, 1)
        print(f"  Total time:     {elapsed:.2f}s")
        print(f"  Per-tick:       {per_tick:.3f}s")
        if per_tick > 5:
            print("  ⚠️  SLOW: >5s per tick — check price fetch calls and RPC latency")
        elif per_tick > 2:
            print("  🟡 MODERATE: >2s per tick — consider caching price data")
        else:
            print("  🟢 FAST: <2s per tick — healthy!")


if __name__ == "__main__":
    main()
