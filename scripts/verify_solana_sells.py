#!/usr/bin/env python3
import json
import os
import sys

def main():
    print("=== [1/5] Solana positions in positions.json ===")
    path = '/app/output/positions.json'
    if not os.path.exists(path):
        print('positions.json not found — no positions yet')
    else:
        try:
            positions = json.load(open(path))
            sol = [p for p in positions if p.get('chain','').lower() == 'solana']
            print(f'Total positions: {len(positions)} | Solana: {len(sol)}')
            for p in sol[:10]:
                print(f'  {p.get("token_symbol","?")} status={p.get("status")} qty={p.get("remaining_quantity")} fails={p.get("sell_failure_count",0)}')
        except Exception as e:
            print(f"Error reading positions: {e}")

    print("\n=== [2/5] SOLANA_PRIVATE_KEY env var check ===")
    sk = os.environ.get('SOLANA_PRIVATE_KEY','')
    print(f'SOLANA_PRIVATE_KEY set: {bool(sk)}  length: {len(sk)}')
    sol_addr = os.environ.get('SOLANA_ADDRESS_PRIMARY','')
    print(f'SOLANA_ADDRESS_PRIMARY: {sol_addr or "(not set)"}')
    if not sk:
        print('CRITICAL: SOLANA_PRIVATE_KEY is empty — Solana sells CANNOT sign transactions!')
    else:
        print('OK: private key present')

    print("\n=== [3/5] sell_engine import check ===")
    try:
        from core.sell_engine import execute_sell_solana
        print('import OK')
    except Exception as e:
        print(f"Import failed: {e}")
        sys.exit(1)

    print("\n=== [4/5] Paper-mode Solana sell test ===")
    try:
        result = execute_sell_solana(
            token_mint='So11111111111111111111111111111111111111112',
            token_amount_units=1000,
            wallet_public_key='FzZwd2Zqw7bMpzUoxNA7QwqziAVLddtDftecvs5p8gt2',
            wallet_private_key_env='SOLANA_PRIVATE_KEY',
            is_paper=True
        )
        print(f'success={result.success}')
        print(f'tx_hash={result.tx_hash}')
        print(f'execution_path={result.execution_path}')
        print(f'error={result.error}')
        if result.success and result.tx_hash == 'PAPER_TX':
            print('PAPER SELL: PASS')
        else:
            print('PAPER SELL: FAIL')
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    main()
