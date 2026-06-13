import os
import re
import sys

def update_env(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist.")
        sys.exit(1)
        
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    updates = {
        'ACTIVE_CHAINS': 'ethereum,base,arbitrum,bsc,solana',
        'MORALIS_MONTHLY_CU_BUDGET': '394000000',
        'MORALIS_SAFETY_BUFFER_PCT': '0.01',
        'MORALIS_DEFI_MIN_BASE_SCORE': '20.0',
        'SCAN_INTERVAL_SECONDS': '15',
        'POSITION_CHECK_INTERVAL_SECONDS': '15',
        'MORALIS_STREAMS_FALLBACK_POLL_INTERVAL': '30',
        'MORALIS_BTC_WHALE_MIN_BTC': '1.0',
        'MIN_GEM_SCORE': '68.75',
        'EXPRESS_LANE_SCORE': '85.15',
        'MAX_TOKEN_AGE_HOURS': '168.0',
        'MORALIS_MAX_TRACKED_WALLETS': '500',
        'MIN_LIQUIDITY_USD': '5000',
        'TAKE_PROFIT_TP1_MULT': '1.6425',
        'TAKE_PROFIT_TP1_SELL_PCT': '0.3373',
        'TAKE_PROFIT_TP2_MULT': '3.75',
        'TAKE_PROFIT_TP2_SELL_PCT': '0.444',
        'TAKE_PROFIT_TP3_MULT': '10.1722',
        'STOP_LOSS_PERCENT': '9.0',
        'HARD_STOP_LOSS_PERCENT': '16.5913',
        'PRE_TP1_TRAILING_STOP_PCT': '22.7903',
    }

    new_lines = []
    updated_keys = set()
    for line in lines:
        match = re.match(r'^([A-Za-z0-9_]+)=', line)
        if match:
            key = match.group(1)
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)
        
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
            
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
        
if __name__ == '__main__':
    update_env('.env')
    print("Updated .env successfully.")
