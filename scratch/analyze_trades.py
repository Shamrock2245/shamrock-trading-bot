import pandas as pd
import sys

def analyze(csv_file):
    df = pd.read_csv(csv_file)
    
    # Filter only 'Close' actions to get realized PnL
    closes = df[df['dir'].str.contains('Close')]
    
    total_pnl = closes['closedPnl'].sum()
    win_trades = closes[closes['closedPnl'] > 0]
    loss_trades = closes[closes['closedPnl'] <= 0]
    
    win_rate = len(win_trades) / len(closes) if len(closes) > 0 else 0
    
    avg_win = win_trades['closedPnl'].mean()
    avg_loss = loss_trades['closedPnl'].mean()
    
    print(f"Total Trades: {len(closes)}")
    print(f"Win Rate: {win_rate*100:.1f}%")
    print(f"Total PnL: ${total_pnl:.2f}")
    print(f"Avg Win: ${avg_win:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f}")
    
    # Profit Factor
    gross_profit = win_trades['closedPnl'].sum()
    gross_loss = abs(loss_trades['closedPnl'].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    print(f"Profit Factor: {pf:.2f}")
    
    print("\nPnL by Coin:")
    coin_pnl = closes.groupby('coin')['closedPnl'].sum().sort_values()
    print(coin_pnl)
    
    print("\nPnL by Direction:")
    closes['side'] = closes['dir'].apply(lambda x: 'Long' if 'Long' in x else 'Short')
    dir_pnl = closes.groupby('side')['closedPnl'].sum()
    print(dir_pnl)

if __name__ == "__main__":
    analyze(sys.argv[1])
