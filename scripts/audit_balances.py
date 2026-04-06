import requests, sys

RPCS = {
    'ethereum': 'https://ethereum.publicnode.com',
    'base':     'https://mainnet.base.org',
    'arbitrum': 'https://arb1.arbitrum.io/rpc',
    'bsc':      'https://bsc-dataseed.binance.org',
    'avalanche':'https://api.avax.network/ext/bc/C/rpc',
}
USDC = {
    'ethereum': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
    'base':     '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
    'arbitrum': '0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
    'bsc':      '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
    'avalanche':'0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E',
}
WALLETS = {
    'Primary':  '0x3eb320fad3f51fe4f2a4531f911ef56694346eef',
    'Wallet_B': '0x0835eb8447f3ac90351951bb5d22e77afd9b81c0',
}
SYM = {'ethereum':'ETH','base':'ETH','arbitrum':'ETH','bsc':'BNB','avalanche':'AVAX'}
PRICES = {'ethereum':1800,'base':1800,'arbitrum':1800,'bsc':600,'avalanche':20}
try:
    r = requests.get('https://min-api.cryptocompare.com/data/pricemulti?fsyms=ETH,BNB,AVAX&tsyms=USD',timeout=8).json()
    PRICES.update({'ethereum':r['ETH']['USD'],'base':r['ETH']['USD'],'arbitrum':r['ETH']['USD'],'bsc':r['BNB']['USD'],'avalanche':r['AVAX']['USD']})
    print("ETH=${:.0f}  BNB=${:.0f}  AVAX=${:.2f}".format(PRICES['ethereum'],PRICES['bsc'],PRICES['avalanche']))
except Exception as e:
    print("Price fallback (using defaults): {}".format(e))

def native(addr, rpc):
    try:
        return int(requests.post(rpc,json={'jsonrpc':'2.0','method':'eth_getBalance','params':[addr,'latest'],'id':1},timeout=6).json().get('result','0x0'),16)/1e18
    except:
        return 0.0

def usdc_bal(addr, ctr, rpc):
    data = '0x70a08231' + addr[2:].zfill(64)
    try:
        res = requests.post(rpc,json={'jsonrpc':'2.0','method':'eth_call','params':[{'to':ctr,'data':data},'latest'],'id':1},timeout=6).json().get('result','0x0')
        return int(res,16)/1e6 if res and res != '0x' else 0.0
    except:
        return 0.0

total = 0.0
for wname, addr in WALLETS.items():
    print("\n{} ({})".format(wname, addr))
    for chain, rpc in RPCS.items():
        n = native(addr, rpc)
        u = usdc_bal(addr, USDC[chain], rpc)
        p = PRICES[chain]
        usd = n * p + u
        if usd > 0.50:
            print("  {:12s}: {:.6f} {} (~${:.2f}) + ${:.2f} USDC = ${:.2f}".format(chain, n, SYM[chain], n*p, u, usd))
            total += usd
        else:
            print("  {:12s}: (dust)".format(chain))

print("\nGRAND TOTAL: ${:.2f}".format(total))
