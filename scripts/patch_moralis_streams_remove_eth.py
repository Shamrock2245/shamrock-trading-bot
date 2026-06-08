#!/usr/bin/env python3
"""
scripts/patch_moralis_streams_remove_eth.py
One-shot script to update existing live Moralis streams to remove Ethereum (0x1)
from their chainIds. Run this once on the VPS after deploying the code changes.

Usage:
    python3 scripts/patch_moralis_streams_remove_eth.py
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import requests

MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
BASE_URL = "https://api.moralis-streams.com"

# Chains we WANT to keep (Ethereum 0x1 intentionally excluded)
TARGET_CHAIN_IDS = ["0x2105", "0xa4b1"]  # Base, Arbitrum only

HEADERS = {
    "x-api-key": MORALIS_API_KEY,
    "Content-Type": "application/json",
}

def get_all_streams():
    resp = requests.get(f"{BASE_URL}/streams/evm", headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        print(f"ERROR fetching streams: {resp.status_code} {resp.text[:200]}")
        return []
    data = resp.json()
    return data.get("result", [])

def patch_stream_chains(stream_id: str, new_chain_ids: list, tag: str):
    body = {"chainIds": new_chain_ids}
    resp = requests.put(
        f"{BASE_URL}/streams/evm/{stream_id}",
        headers=HEADERS,
        json=body,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        print(f"  ✅ Patched stream '{tag}' ({stream_id[:12]}...) → chains: {new_chain_ids}")
        return True
    else:
        print(f"  ❌ Failed to patch '{tag}' ({stream_id[:12]}...): {resp.status_code} {resp.text[:200]}")
        return False

def main():
    if not MORALIS_API_KEY:
        print("ERROR: MORALIS_API_KEY not set. Run from project root with .env loaded.")
        sys.exit(1)

    print("Fetching all EVM Moralis streams...")
    streams = get_all_streams()
    print(f"Found {len(streams)} streams.\n")

    patched = 0
    skipped = 0

    for stream in streams:
        stream_id = stream.get("id", "")
        tag = stream.get("tag", "")
        current_chains = stream.get("chainIds", [])

        if "0x1" not in current_chains:
            print(f"  ⏭  Stream '{tag}' ({stream_id[:12]}...) — no ETH chain, skipping")
            skipped += 1
            continue

        # Remove 0x1 (Ethereum) from the chain list
        new_chains = [c for c in current_chains if c != "0x1"]
        # If nothing left, use our target chains
        if not new_chains:
            new_chains = TARGET_CHAIN_IDS

        print(f"  🔧 Patching '{tag}': {current_chains} → {new_chains}")
        if patch_stream_chains(stream_id, new_chains, tag):
            patched += 1

    print(f"\nDone. Patched: {patched} | Skipped (no ETH): {skipped}")
    print("Ethereum (0x1) removed from all active Moralis streams.")
    print("CU burn from ETH mainnet alpha-wallet events will stop immediately.")

if __name__ == "__main__":
    main()
