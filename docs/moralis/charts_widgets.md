# Moralis Charts & Widgets

> Embeddable, real-time crypto price charts powered by TradingView.
>
> Docs: https://docs.moralis.com/charts-widgets
> Widget Builder: https://moralis.com/charts

## Overview

Moralis provides a **Crypto Price Chart Widget** that embeds interactive, customizable TradingView-powered candlestick charts into any website or app. Supply a token address or pair address and get professional OHLCV charts with zero backend work.

---

## Widget Configuration

### Input Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `chainId` | string | Blockchain network (e.g., `0x1` for Ethereum, `0x38` for BSC) |
| `tokenAddress` | string | Contract address of the token to chart |
| `pairAddress` | string | Alternative: DEX pair address for the trading pair |
| `defaultInterval` | string | Default candle interval (`1D`, `4H`, `1H`, `15M`, `5M`, `1M`) |
| `theme` | string | `dark` or `light` |

### Customization Options

| Option | Description |
|--------|-------------|
| `backgroundColor` | Chart background color (hex) |
| `upCandleColor` | Color for bullish candles |
| `downCandleColor` | Color for bearish candles |
| `textColor` | Label and axis text color |
| `hideLeftToolbar` | Hide/show left drawing tools panel |
| `hideTopToolbar` | Hide/show top timeframe selector |
| `hideBottomToolbar` | Hide/show bottom timeline bar |
| `currencyToggle` | Enable USD/native currency toggle |

---

## HTML Embed

```html
<!-- Container for chart -->
<div id="moralis-chart" style="width:100%; height:500px;"></div>

<!-- Moralis Chart Widget Script -->
<script src="https://moralis.com/static/embed/chart.js"></script>
<script>
  createMyWidget("moralis-chart", {
    chainId: "0x1",
    tokenAddress: "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
    defaultInterval: "1D",
    theme: "dark",
    backgroundColor: "#0d1117",
    upCandleColor: "#00c853",
    downCandleColor: "#ff1744",
    textColor: "#c9d1d9"
  });
</script>
```

## React Embed

```jsx
import { useEffect, useRef } from 'react';

function MoralisChart({ tokenAddress, chainId = "0x1" }) {
  const chartRef = useRef(null);

  useEffect(() => {
    if (window.createMyWidget && chartRef.current) {
      window.createMyWidget(chartRef.current.id, {
        chainId,
        tokenAddress,
        defaultInterval: "1H",
        theme: "dark",
      });
    }
  }, [tokenAddress, chainId]);

  return <div id="moralis-chart" ref={chartRef} style={{ width: '100%', height: 500 }} />;
}
```

---

## Supported Chains

| Chain | chainId |
|-------|---------|
| Ethereum | `0x1` |
| BSC | `0x38` |
| Polygon | `0x89` |
| Arbitrum | `0xa4b1` |
| Base | `0x2105` |
| Avalanche | `0xa86a` |
| Optimism | `0xa` |
| Fantom | `0xfa` |

Full list: 40+ EVM chains supported.

---

## Why This Matters for Shamrock

### Integration Opportunities

1. **Streamlit Dashboard Charts** — Embed real-time token price charts for active positions directly in the ops dashboard
2. **Gem Scanner Visualization** — Chart candidate tokens before entry to visually confirm breakouts and volume patterns
3. **Portfolio P&L Charts** — Historical candlestick view of held tokens for performance review
4. **Post-Trade Analysis** — Chart entry/exit points on historical data for trade review
5. **Telegram Mini-App** — Embed charts in the Telegram Web App for on-the-go position monitoring

### Implementation Priority

| Priority | Use Case | Effort |
|----------|----------|--------|
| 🟢 High | Streamlit dashboard token charts | Low — iframe/HTML embed |
| 🟡 Medium | Gem scanner pre-entry visualization | Medium — dynamic token input |
| 🟡 Medium | Telegram Mini-App charts | Medium — responsive embed |
| 🔵 Low | Post-trade analysis charts | Low — static historical view |

---

## Related Docs

- [Price API](price_api.md) — Underlying price data endpoints
- [Price OHLCV](price_ohlcv.md) — Candlestick data API
- [Token Metadata](token_metadata.md) — Token name, symbol, logo
