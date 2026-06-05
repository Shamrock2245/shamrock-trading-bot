import requests

def _fetch_kraken_ohlcv(symbol: str, limit: int = 100):
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": symbol, "interval": 60} # 60 minutes
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if not data.get("error"):
        # The data is in data["result"][pair_name]
        pair_key = list(data["result"].keys())[0]
        if pair_key != "last":
            candles = data["result"][pair_key]
            return candles[-limit:]
    return None

btc = _fetch_kraken_ohlcv("XBTUSD")
sol = _fetch_kraken_ohlcv("SOLUSD")
print(f"BTC length: {len(btc) if btc else None}")
print(f"SOL length: {len(sol) if sol else None}")
