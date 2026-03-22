# STRATEGIES — How We Make Money

## Strategy 1: GemSnipe (Primary — `strategies/gem_snipe.py`)

### The Playbook
1. **Discover** — DexScreener new profiles, boosts, CTOs, ads
2. **Score** — 13-signal weighted scoring (0–100)
3. **Validate** — TA confirmation + Fibonacci support levels
4. **Execute** — Buy at support, set stop-loss below structure

### Signal Weights (Total = 100%)
| Signal | Weight | Source |
|--------|--------|--------|
| Volume spike | 17% | DexScreener hourly vs 24h avg |
| Liquidity depth | 13% | DexScreener pair liquidity |
| Token age | 12% | DexScreener pair creation time |
| Contract verified | 8% | GoPlus API |
| Holder distribution | 8% | Moralis/Etherscan |
| Buy/sell tax | 8% | GoPlus API |
| Social signals | 8% | LunarCrush + CoinGecko + DexScreener |
| TVL (DefiLlama) | 5% | DefiLlama protocol data |
| Social sentiment | 5% | LunarCrush galaxy score |
| DexScreener boost | 4% | DexScreener boost amount |
| Smart money | 4% | Wallet overlap with known whales |
| Holder concentration | 4% | Top 10 holder % |
| Unlock/dilution risk | 4% | Token unlock schedule |

### Express Lane (Score ≥ 82)
- **Skip full TA pipeline** — these are high-conviction plays
- **Execute within seconds** — speed = profit on these gems
- **Higher position sizing** — conviction high multiplier (1.0x of max)

### Standard Lane (Score 55–81)
- **Full TA analysis** — RSI, MACD, Bollinger Bands, OBV
- **Fibonacci confirmation** — price must be near a fib support level
- **Lower position sizing** — conviction-adjusted (0.5x–0.75x)

## Strategy 2: Momentum Scalp (Planned)
- Ride volume breakouts on existing positions
- Enter on 5x hourly volume spike
- Exit on momentum fade (OBV divergence)

## Strategy 3: Smart Money Follow (Planned)
- Mirror buys from tracked whale wallets
- Enter after whale accumulation detected
- Exit on whale distribution

## Which Strategy When?
```
High gem score (82+) → Express GemSnipe (instant entry)
Good gem score (55-81) → Standard GemSnipe (TA confirmed)
Volume breakout on held token → Momentum Scale-up
Whale accumulation detected → Smart Money Follow
```

## Anti-Strategies (NEVER Do This)
- ❌ **Revenge trade** — never re-enter a losing position immediately
- ❌ **FOMO chase** — never buy a token that already pumped 10x
- ❌ **Average down** — never add to a losing position
- ❌ **Ignore stops** — if stop-loss is hit, exit. Period.
- ❌ **Overtrade** — max 3 entries per scan cycle
