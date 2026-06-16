"""
core/coinbase_client.py — Coinbase Advanced Trade API Integration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Provides a unified interface to the Coinbase Advanced Trade API for:
  1. Price feeds  — real-time bid/ask/mid prices for any Coinbase-listed pair
  2. Account data — balances across all Coinbase wallets
  3. Order exec   — market/limit orders with paper mode simulation
  4. Product data — list tradable pairs, fee tiers, min sizes

Auth: CDP API Key (ECDSA EC private key) → JWT signed per-request.
Uses the official `coinbase-advanced-py` SDK.

Integration points:
  - arb_price_feed.py — adds Coinbase as a CEX price source
  - stat_arb.py       — alternative to HL for CEX leg of arb
  - main.py           — CEX/DEX arb scanner daemon

Fee structure (Coinbase Advanced Trade):
  - Taker: 0.60% (<$10K volume), 0.40% ($10K-$50K), decreasing with volume
  - Maker: 0.40% (<$10K volume), 0.25% ($10K-$50K), decreasing with volume
  - Stable pairs: 0.00% maker (USDC/USD, etc.)
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy SDK import (graceful fallback if not installed)
# ─────────────────────────────────────────────────────────────────────────────
_rest_client = None
_sdk_available = False

try:
    from coinbase.rest import RESTClient
    _sdk_available = True
except ImportError:
    logger.warning("coinbase-advanced-py not installed. Coinbase integration disabled.")
    RESTClient = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
COINBASE_API_KEY = getattr(settings, "COINBASE_API_KEY_NAME", "") or os.getenv("COINBASE_API_KEY_NAME", "")
COINBASE_API_SECRET = getattr(settings, "COINBASE_API_PRIVATE_KEY", "") or os.getenv("COINBASE_API_PRIVATE_KEY", "")
COINBASE_ENABLED = bool(COINBASE_API_KEY and COINBASE_API_SECRET and _sdk_available)

# Taker fee (conservative estimate for position sizing)
COINBASE_TAKER_FEE_PCT = float(os.getenv("COINBASE_TAKER_FEE_PCT", "0.006"))  # 0.60%
COINBASE_MAKER_FEE_PCT = float(os.getenv("COINBASE_MAKER_FEE_PCT", "0.004"))  # 0.40%

# Price cache TTL
_PRICE_CACHE_TTL = 5.0  # seconds
_price_cache: dict[str, tuple[float, float]] = {}  # product_id -> (price, timestamp)

# Tracked products for arb scanning
COINBASE_ARB_PAIRS = os.getenv(
    "COINBASE_ARB_PAIRS",
    "BTC-USD,ETH-USD,SOL-USD,AVAX-USD,LINK-USD,MATIC-USD,ARB-USD,OP-USD,DOGE-USD,XRP-USD"
).split(",")


@dataclass
class CoinbasePrice:
    """Price snapshot from Coinbase."""
    product_id: str
    bid: float
    ask: float
    mid: float
    last: float
    volume_24h: float
    timestamp: float = field(default_factory=time.time)

    @property
    def spread_pct(self) -> float:
        if self.mid <= 0:
            return 0.0
        return (self.ask - self.bid) / self.mid * 100


@dataclass
class CoinbaseBalance:
    """Account balance on Coinbase."""
    currency: str
    available: float
    hold: float
    total: float


@dataclass
class CoinbaseOrder:
    """Order result from Coinbase."""
    order_id: str
    product_id: str
    side: str
    size: float
    price: float
    status: str
    is_paper: bool = False
    fee: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Client Initialization
# ─────────────────────────────────────────────────────────────────────────────

def _get_client() -> Optional["RESTClient"]:
    """Get or create the Coinbase REST client (singleton)."""
    global _rest_client
    if not COINBASE_ENABLED:
        return None
    if _rest_client is None:
        try:
            _rest_client = RESTClient(
                api_key=COINBASE_API_KEY,
                api_secret=COINBASE_API_SECRET,
                timeout=10,
            )
            logger.info("Coinbase Advanced Trade client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Coinbase client: {e}")
            return None
    return _rest_client


# ─────────────────────────────────────────────────────────────────────────────
# Price Feed
# ─────────────────────────────────────────────────────────────────────────────

def get_price(product_id: str = "BTC-USD") -> Optional[CoinbasePrice]:
    """Get current price for a Coinbase product (e.g., 'BTC-USD', 'SOL-USD').

    Uses SDK's get_product() for price + volume, then get_best_bid_ask()
    for accurate bid/ask spread.
    Results are cached for 5 seconds to avoid rate limits.
    """
    # Check cache
    cached = _price_cache.get(product_id)
    if cached and (time.time() - cached[1]) < _PRICE_CACHE_TTL:
        return cached[0]

    client = _get_client()
    if not client:
        return None

    try:
        product = client.get_product(product_id)
        price = float(getattr(product, "price", 0) or 0)
        vol = float(getattr(product, "volume_24h", 0) or 0)

        # Get real bid/ask via best_bid_ask (pass as list for proper URL encoding)
        best_bid = price
        best_ask = price
        try:
            ticker = client.get_best_bid_ask(product_ids=[product_id])
            if hasattr(ticker, "pricebooks") and ticker.pricebooks:
                pb = ticker.pricebooks[0]
                bids = getattr(pb, "bids", [])
                asks = getattr(pb, "asks", [])
                if bids:
                    best_bid = float(bids[0].get("price", price) if isinstance(bids[0], dict)
                                    else getattr(bids[0], "price", price))
                if asks:
                    best_ask = float(asks[0].get("price", price) if isinstance(asks[0], dict)
                                    else getattr(asks[0], "price", price))
        except Exception:
            pass  # Fallback to mid price from get_product

        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else price

        result = CoinbasePrice(
            product_id=product_id,
            bid=best_bid,
            ask=best_ask,
            mid=mid,
            last=price,
            volume_24h=vol,
        )
        _price_cache[product_id] = (result, time.time())
        return result

    except Exception as e:
        logger.warning(f"Coinbase price fetch failed for {product_id}: {e}")
        return None


def get_prices_batch(product_ids: list[str] = None) -> dict[str, CoinbasePrice]:
    """Fetch prices for multiple products efficiently.

    Uses the SDK's get_best_bid_ask() which properly handles repeated
    product_ids query params.
    """
    if product_ids is None:
        product_ids = COINBASE_ARB_PAIRS

    results = {}
    client = _get_client()
    if not client:
        return results

    try:
        # SDK method properly encodes repeated product_ids params
        ticker = client.get_best_bid_ask(product_ids=product_ids)
        if hasattr(ticker, "pricebooks"):
            for pb in ticker.pricebooks:
                pid = getattr(pb, "product_id", "")
                if not pid:
                    continue
                bids = getattr(pb, "bids", [])
                asks = getattr(pb, "asks", [])
                best_bid = float(bids[0].get("price", 0) if isinstance(bids[0], dict)
                                else getattr(bids[0], "price", 0)) if bids else 0
                best_ask = float(asks[0].get("price", 0) if isinstance(asks[0], dict)
                                else getattr(asks[0], "price", 0)) if asks else 0
                mid = (best_bid + best_ask) / 2
                results[pid] = CoinbasePrice(
                    product_id=pid,
                    bid=best_bid,
                    ask=best_ask,
                    mid=mid,
                    last=mid,
                    volume_24h=0,
                )
                _price_cache[pid] = (results[pid], time.time())
    except Exception as e:
        logger.warning(f"Coinbase batch price fetch failed: {e}")
        # Fallback: fetch individually
        for pid in product_ids[:5]:  # Limit to avoid rate limits
            p = get_price(pid)
            if p:
                results[pid] = p

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Account / Balances
# ─────────────────────────────────────────────────────────────────────────────

def get_balances() -> list[CoinbaseBalance]:
    """Fetch all account balances with non-zero holdings."""
    client = _get_client()
    if not client:
        return []

    try:
        accounts = client.get_accounts()
        results = []
        for acct in getattr(accounts, "accounts", []):
            avail_bal = getattr(acct, "available_balance", {})
            hold_bal = getattr(acct, "hold", {})
            available = float(avail_bal.get("value", 0) if isinstance(avail_bal, dict)
                            else getattr(avail_bal, "value", 0) or 0)
            hold = float(hold_bal.get("value", 0) if isinstance(hold_bal, dict)
                        else getattr(hold_bal, "value", 0) or 0)
            total = available + hold
            if total > 0.001:  # Skip dust
                currency = (avail_bal.get("currency", "") if isinstance(avail_bal, dict)
                          else getattr(avail_bal, "currency", ""))
                results.append(CoinbaseBalance(
                    currency=currency,
                    available=available,
                    hold=hold,
                    total=total,
                ))
        return results
    except Exception as e:
        logger.error(f"Coinbase balance fetch failed: {e}")
        return []


def get_usd_balance() -> float:
    """Get available USD balance on Coinbase."""
    for bal in get_balances():
        if bal.currency in ("USD", "USDC"):
            return bal.available
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Order Execution
# ─────────────────────────────────────────────────────────────────────────────

def market_buy(product_id: str, quote_size: float, is_paper: bool = True) -> Optional[CoinbaseOrder]:
    """Place a market buy order (quote_size in USD).

    Args:
        product_id: e.g., 'BTC-USD', 'SOL-USD'
        quote_size: USD amount to spend
        is_paper: if True, simulate only (no real order)
    """
    if is_paper:
        price_data = get_price(product_id)
        price = price_data.ask if price_data else 0
        size = quote_size / price if price > 0 else 0
        fee = quote_size * COINBASE_TAKER_FEE_PCT
        logger.info(f"[PAPER] Coinbase BUY {product_id}: ${quote_size:.2f} @ ${price:.2f} "
                    f"({size:.6f} units, fee=${fee:.4f})")
        return CoinbaseOrder(
            order_id=f"paper-{uuid.uuid4().hex[:12]}",
            product_id=product_id,
            side="BUY",
            size=size,
            price=price,
            status="FILLED",
            is_paper=True,
            fee=fee,
        )

    client = _get_client()
    if not client:
        return None

    try:
        order = client.market_order_buy(
            client_order_id=str(uuid.uuid4()),
            product_id=product_id,
            quote_size=str(round(quote_size, 2)),
        )
        order_dict = order.to_dict() if hasattr(order, "to_dict") else {}
        logger.info(f"[LIVE] Coinbase BUY {product_id}: ${quote_size:.2f} — {order_dict}")
        return CoinbaseOrder(
            order_id=order_dict.get("order_id", "unknown"),
            product_id=product_id,
            side="BUY",
            size=float(order_dict.get("filled_size", 0)),
            price=float(order_dict.get("average_filled_price", 0)),
            status=order_dict.get("status", "UNKNOWN"),
            is_paper=False,
        )
    except Exception as e:
        logger.error(f"Coinbase market buy failed: {e}")
        return None


def market_sell(product_id: str, base_size: float, is_paper: bool = True) -> Optional[CoinbaseOrder]:
    """Place a market sell order (base_size in token units).

    Args:
        product_id: e.g., 'BTC-USD', 'SOL-USD'
        base_size: amount of base asset to sell
        is_paper: if True, simulate only (no real order)
    """
    if is_paper:
        price_data = get_price(product_id)
        price = price_data.bid if price_data else 0
        value = base_size * price
        fee = value * COINBASE_TAKER_FEE_PCT
        logger.info(f"[PAPER] Coinbase SELL {product_id}: {base_size:.6f} @ ${price:.2f} "
                    f"(${value:.2f}, fee=${fee:.4f})")
        return CoinbaseOrder(
            order_id=f"paper-{uuid.uuid4().hex[:12]}",
            product_id=product_id,
            side="SELL",
            size=base_size,
            price=price,
            status="FILLED",
            is_paper=True,
            fee=fee,
        )

    client = _get_client()
    if not client:
        return None

    try:
        order = client.market_order_sell(
            client_order_id=str(uuid.uuid4()),
            product_id=product_id,
            base_size=str(base_size),
        )
        order_dict = order.to_dict() if hasattr(order, "to_dict") else {}
        logger.info(f"[LIVE] Coinbase SELL {product_id}: {base_size} — {order_dict}")
        return CoinbaseOrder(
            order_id=order_dict.get("order_id", "unknown"),
            product_id=product_id,
            side="SELL",
            size=base_size,
            price=float(order_dict.get("average_filled_price", 0)),
            status=order_dict.get("status", "UNKNOWN"),
            is_paper=False,
        )
    except Exception as e:
        logger.error(f"Coinbase market sell failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Product Discovery
# ─────────────────────────────────────────────────────────────────────────────

def list_tradable_products(quote_currency: str = "USD") -> list[str]:
    """List all tradable product IDs with a specific quote currency."""
    client = _get_client()
    if not client:
        return []

    try:
        products = client.get_products()
        result = []
        for p in getattr(products, "products", []):
            pid = getattr(p, "product_id", "")
            status = getattr(p, "status", "")
            quote = getattr(p, "quote_currency_id", "")
            if status == "ONLINE" and quote == quote_currency:
                result.append(pid)
        return sorted(result)
    except Exception as e:
        logger.error(f"Coinbase product list failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

def health_check() -> dict:
    """Quick health check — verify auth and return summary."""
    if not COINBASE_ENABLED:
        return {"status": "disabled", "reason": "Missing API credentials or SDK"}

    try:
        client = _get_client()
        if not client:
            return {"status": "error", "reason": "Client init failed"}

        # Test with a simple product fetch
        product = client.get_product("BTC-USD")
        price = float(getattr(product, "price", 0) or 0)

        balances = get_balances()
        total_usd = sum(b.total for b in balances if b.currency in ("USD", "USDC"))

        return {
            "status": "ok",
            "btc_price": price,
            "balances": len(balances),
            "usd_available": total_usd,
            "tradable_pairs": len(COINBASE_ARB_PAIRS),
        }
    except Exception as e:
        return {"status": "error", "reason": str(e)}
