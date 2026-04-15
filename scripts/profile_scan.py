#!/usr/bin/env python3
"""
scripts/profile_scan.py — Profile the gem scan pipeline.

Usage:
    python scripts/profile_scan.py                # cProfile top-30 report
    python scripts/profile_scan.py --flamegraph   # Save .prof for flamegraph

Outputs:
    output/profile_scan.prof   — Binary profile data (viewable with snakeviz/flamegraph)
    Console                    — Top 30 functions by cumulative time

Requires: pip install snakeviz  (optional, for visualization)
    snakeviz output/profile_scan.prof
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

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MODE", "paper")

from config import settings
from scanner.gem_scanner import GemScanner


def profile_scan_cycle():
    """Run one scan cycle under cProfile and report results."""
    scanner = GemScanner()

    print("☘️  Shamrock Scan Profiler")
    print("=" * 60)
    print(f"Chains: {', '.join(settings.ACTIVE_CHAINS)}")
    print(f"Min score: {settings.MIN_GEM_SCORE}")
    print()

    # ── Profile the scan ──────────────────────────────────────────────────────
    profiler = cProfile.Profile()

    print("⏱️  Starting profiled scan cycle...")
    t0 = time.perf_counter()

    profiler.enable()
    candidates = asyncio.run(scanner.scan_all_chains())
    profiler.disable()

    elapsed = time.perf_counter() - t0

    # ── Results ───────────────────────────────────────────────────────────────
    print(f"\n✅ Scan complete in {elapsed:.2f}s — {len(candidates)} candidates found")
    print()

    # Print top 30 by cumulative time
    print("=" * 60)
    print("TOP 30 FUNCTIONS BY CUMULATIVE TIME")
    print("=" * 60)
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs()
    stats.sort_stats("cumulative")
    stats.print_stats(30)
    print(stream.getvalue())

    # ── Per-source breakdown ──────────────────────────────────────────────────
    print("=" * 60)
    print("PER-SOURCE TIMING (from scan metadata)")
    print("=" * 60)
    for c in candidates[:10]:
        src = c.discovery_source if hasattr(c, "discovery_source") else "unknown"
        sym = c.symbol if hasattr(c, "symbol") else "?"
        score = c.gem_score if hasattr(c, "gem_score") else 0
        print(f"  {sym:>12s} | score={score:5.1f} | source={src}")

    # ── Save .prof for flamegraph ─────────────────────────────────────────────
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    prof_path = output_dir / "profile_scan.prof"
    profiler.dump_stats(str(prof_path))
    print(f"\n📊 Profile saved to {prof_path}")
    print(f"   Visualize: python -m snakeviz {prof_path}")

    return elapsed, len(candidates)


def main():
    parser = argparse.ArgumentParser(description="Profile the gem scan pipeline")
    parser.add_argument("--flamegraph", action="store_true", help="Save .prof file only")
    args = parser.parse_args()

    elapsed, count = profile_scan_cycle()

    # ── Performance summary ───────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"  Total scan time:    {elapsed:.2f}s")
    print(f"  Candidates found:   {count}")
    print(f"  Time per candidate: {elapsed/max(count,1):.3f}s")
    print()

    # Thresholds
    if elapsed > 30:
        print("  ⚠️  SLOW: Scan takes >30s — review network calls and API batching")
    elif elapsed > 15:
        print("  🟡 MODERATE: Scan takes >15s — room for optimization")
    else:
        print("  🟢 FAST: Scan completes in <15s — healthy!")


if __name__ == "__main__":
    main()
