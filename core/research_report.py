"""
core/research_report.py — On-Demand Token Research Report Generator

Generates a comprehensive PDF research report for any gem candidate or token
address. Triggered from the Gem Scanner GUI via a "Generate Report" button.

Report sections:
  1. Executive Summary — score, verdict, key signals
  2. Token Overview — price, market cap, age, chain, DEX
  3. Score Breakdown — all 29 scoring components with bar charts
  4. Safety Analysis — GoPlus, honeypot, taxes, authorities
  5. On-Chain Intelligence — holders, whale activity, sniper detection
  6. Moralis Intelligence — buy pressure, experienced buyers, security score
  7. Macro Context — current market regime, BTC/ETH/SOL trend
  8. Entry Timing — buy pressure trend, volume acceleration, timing score
  9. Risk Assessment — position sizing recommendation, risk level
  10. Appendix — raw signals, data sources used

Output: PDF file saved to output/reports/{symbol}_{timestamp}.pdf
Also returns a dict summary for the dashboard to display inline.
"""

from __future__ import annotations

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from data.models import GemCandidate

# ── Output directory ──────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS_DIR = os.path.join(_BASE, "output", "reports")
os.makedirs(_REPORTS_DIR, exist_ok=True)


# ── Score interpretation helpers ─────────────────────────────────────────────
def _score_label(score: float) -> str:
    if score >= 80: return "EXCELLENT"
    if score >= 65: return "GOOD"
    if score >= 50: return "NEUTRAL"
    if score >= 35: return "WEAK"
    return "POOR"


def _risk_level(gem_score: float) -> tuple[str, str]:
    """Returns (risk_label, risk_color_hex)"""
    if gem_score >= 80: return ("LOW RISK", "#00D09C")
    if gem_score >= 65: return ("MODERATE RISK", "#58A6FF")
    if gem_score >= 55: return ("ELEVATED RISK", "#FFB84D")
    return ("HIGH RISK", "#FF4757")


def _position_size_recommendation(gem_score: float, capital_usd: float) -> dict:
    """Calculate recommended position size based on score and capital."""
    if gem_score >= 80:
        pct = 0.08  # 8% of capital
        label = "Full conviction"
    elif gem_score >= 70:
        pct = 0.05  # 5%
        label = "Standard position"
    elif gem_score >= 65:
        pct = 0.03  # 3%
        label = "Reduced position"
    else:
        pct = 0.02  # 2%
        label = "Minimal / watchlist"

    usd = capital_usd * pct
    return {
        "pct": pct * 100,
        "usd": usd,
        "label": label,
    }


# ── Data fetchers for standalone token lookup ─────────────────────────────────
def _fetch_token_data(token_address: str, chain: str) -> dict:
    """Fetch basic token data from DexScreener for standalone report generation."""
    try:
        from data.http_session import get_session
        r = get_session().get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
            timeout=10,
        )
        if r.status_code == 200:
            pairs = r.json().get("pairs", [])
            if pairs:
                p = pairs[0]
                base = p.get("baseToken", {})
                return {
                    "symbol": base.get("symbol", "UNKNOWN"),
                    "name": base.get("name", "Unknown"),
                    "address": token_address,
                    "chain": chain,
                    "price_usd": float(p.get("priceUsd", 0) or 0),
                    "market_cap": float(p.get("marketCap", 0) or 0),
                    "fdv": float(p.get("fdv", 0) or 0),
                    "liquidity_usd": float(p.get("liquidity", {}).get("usd", 0) or 0),
                    "volume_24h": float(p.get("volume", {}).get("h24", 0) or 0),
                    "price_change_24h": float(p.get("priceChange", {}).get("h24", 0) or 0),
                    "price_change_1h": float(p.get("priceChange", {}).get("h1", 0) or 0),
                    "created_at": p.get("pairCreatedAt", 0),
                    "dex_id": p.get("dexId", ""),
                    "pair_address": p.get("pairAddress", ""),
                    "buys_1h": p.get("txns", {}).get("h1", {}).get("buys", 0),
                    "sells_1h": p.get("txns", {}).get("h1", {}).get("sells", 0),
                    "buys_24h": p.get("txns", {}).get("h24", {}).get("buys", 0),
                    "sells_24h": p.get("txns", {}).get("h24", {}).get("sells", 0),
                }
    except Exception as e:
        logger.debug(f"DexScreener fetch error: {e}")
    return {}


def _fetch_goplus_safety(token_address: str, chain: str) -> dict:
    """Fetch GoPlus safety data for the report."""
    try:
        from data.providers.goplus import check_token_safety
        result = check_token_safety(token_address, chain)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.debug(f"GoPlus fetch error: {e}")
    return {}


def _fetch_macro_context() -> dict:
    """Fetch current macro regime for the report."""
    try:
        from core.macro_filter import get_macro_regime
        mr = get_macro_regime()
        return {
            "regime": mr.regime,
            "multiplier": mr.score_multiplier,
            "fear_greed": mr.fear_greed_value,
            "fear_greed_label": mr.fear_greed_label,
            "btc_dominance_signal": mr.btc_dominance_signal,
            "coins": {
                sym: {
                    "regime": cr.regime,
                    "chg_7d_pct": cr.chg_7d_pct,
                    "above_ema200": cr.above_ema200,
                }
                for sym, cr in mr.coins.items()
            },
        }
    except Exception as e:
        logger.debug(f"Macro context fetch error: {e}")
    return {"regime": "UNKNOWN", "multiplier": 1.0, "fear_greed": 50}


# ── PDF Generation ────────────────────────────────────────────────────────────
def _generate_pdf(report: dict, output_path: str) -> bool:
    """Generate a formatted PDF report using fpdf2."""
    try:
        from fpdf import FPDF

        class ShamrockReport(FPDF):
            def header(self):
                self.set_font("Helvetica", "B", 10)
                self.set_text_color(0, 208, 156)  # Shamrock green
                self.cell(0, 8, "☘ SHAMROCK TRADING BOT — TOKEN RESEARCH REPORT", align="C")
                self.ln(4)
                self.set_draw_color(48, 54, 61)
                self.line(10, self.get_y(), 200, self.get_y())
                self.ln(4)

            def footer(self):
                self.set_y(-15)
                self.set_font("Helvetica", "I", 7)
                self.set_text_color(139, 148, 158)
                self.cell(0, 10, f"Generated {report.get('generated_at', '')} | NOT FINANCIAL ADVICE | Page {self.page_no()}", align="C")

        pdf = ShamrockReport()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # ── Title ──────────────────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(230, 237, 243)
        symbol = report.get("symbol", "UNKNOWN")
        pdf.cell(0, 12, f"{symbol} — Research Report", ln=True)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(139, 148, 158)
        pdf.cell(0, 6, f"{report.get('name', '')} | {report.get('chain', '').upper()} | {report.get('dex', '')}", ln=True)
        pdf.ln(4)

        # ── Executive Summary ─────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "EXECUTIVE SUMMARY", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        gem_score = report.get("gem_score", 0)
        risk_label, _ = _risk_level(gem_score)
        verdict = report.get("verdict", "NEUTRAL")

        pdf.set_font("Helvetica", "B", 28)
        score_color = (0, 208, 156) if gem_score >= 65 else (255, 184, 77) if gem_score >= 55 else (255, 71, 87)
        pdf.set_text_color(*score_color)
        pdf.cell(40, 14, f"{gem_score:.1f}", ln=False)

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(230, 237, 243)
        pdf.set_y(pdf.get_y() + 2)
        pdf.cell(0, 6, f"/ 100 — {verdict}", ln=True)
        pdf.set_y(pdf.get_y() - 4)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(139, 148, 158)
        pdf.cell(0, 5, f"Risk Level: {risk_label} | Strategy: {report.get('strategy_tag', 'gem_snipe').upper()}", ln=True)
        pdf.ln(3)

        # Key metrics row
        metrics = [
            ("Price", f"${report.get('price_usd', 0):.6f}"),
            ("Market Cap", f"${report.get('market_cap', 0):,.0f}"),
            ("Liquidity", f"${report.get('liquidity_usd', 0):,.0f}"),
            ("24h Volume", f"${report.get('volume_24h', 0):,.0f}"),
            ("Age", f"{report.get('age_hours', 0):.1f}h"),
            ("24h Change", f"{report.get('price_change_24h', 0):+.1f}%"),
        ]
        col_w = 32
        for i, (label, value) in enumerate(metrics):
            if i % 6 == 0 and i > 0:
                pdf.ln(10)
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(72, 79, 88)
            pdf.cell(col_w, 4, label.upper(), ln=False)
        pdf.ln(4)
        for i, (label, value) in enumerate(metrics):
            if i % 6 == 0 and i > 0:
                pdf.ln(10)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(230, 237, 243)
            pdf.cell(col_w, 5, value, ln=False)
        pdf.ln(8)

        # ── Score Breakdown ───────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "SCORE BREAKDOWN (29 INDICATORS)", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        score_components = report.get("score_components", {})
        for label, score in score_components.items():
            score_val = float(score or 0)
            bar_width = int((score_val / 100) * 100)  # max 100mm bar
            color = (0, 208, 156) if score_val >= 65 else (255, 184, 77) if score_val >= 45 else (255, 71, 87)

            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(139, 148, 158)
            pdf.cell(55, 5, label, ln=False)

            # Bar background
            pdf.set_fill_color(22, 27, 34)
            pdf.rect(65, pdf.get_y() + 1, 100, 3, "F")
            # Bar fill
            pdf.set_fill_color(*color)
            if bar_width > 0:
                pdf.rect(65, pdf.get_y() + 1, bar_width, 3, "F")

            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*color)
            pdf.set_x(170)
            pdf.cell(20, 5, f"{score_val:.0f}", ln=True)

        pdf.ln(4)

        # ── Safety Analysis ───────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "SAFETY ANALYSIS", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        safety = report.get("safety", {})
        safety_items = [
            ("Honeypot", safety.get("is_honeypot", "Unknown"), False),
            ("Buy Tax", f"{safety.get('buy_tax', 0)*100:.1f}%", safety.get('buy_tax', 0) > 0.10),
            ("Sell Tax", f"{safety.get('sell_tax', 0)*100:.1f}%", safety.get('sell_tax', 0) > 0.10),
            ("Ownership Renounced", safety.get("ownership_renounced", "Unknown"), False),
            ("Liquidity Locked", safety.get("lp_locked", "Unknown"), False),
            ("GoPlus Score", f"{safety.get('goplus_score', 0)}/100", safety.get('goplus_score', 100) < 60),
        ]
        for label, value, is_risk in safety_items:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(139, 148, 158)
            pdf.cell(70, 5, label, ln=False)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(255, 71, 87) if is_risk else pdf.set_text_color(0, 208, 156)
            pdf.cell(0, 5, str(value), ln=True)

        pdf.ln(4)

        # ── On-Chain Intelligence ─────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "ON-CHAIN INTELLIGENCE", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        onchain = report.get("on_chain", {})
        onchain_items = [
            ("Experienced Buyers (1h)", onchain.get("exp_buyers_1h", "N/A")),
            ("Net Experienced Buyers (1d)", onchain.get("exp_net_buyers_1d", "N/A")),
            ("Holder Count Change (1d)", onchain.get("holders_change_1d", "N/A")),
            ("Moralis Security Score", f"{onchain.get('security_score', 0)}/100"),
            ("Buy Pressure Ratio", f"{onchain.get('buy_pressure', 0.5)*100:.0f}%"),
            ("Sniper Count", onchain.get("sniper_count", "N/A")),
            ("Sniper Risk", onchain.get("sniper_risk", "unknown").upper()),
            ("Top-10 Holder %", f"{onchain.get('top10_holder_pct', 0):.1f}%"),
        ]
        if report.get("chain") == "solana":
            helius = report.get("helius_enrichment", {})
            if helius:
                onchain_items += [
                    ("Helius: Mutable Metadata", str(helius.get("is_mutable_metadata", "N/A"))),
                    ("Helius: Mint Authority", str(helius.get("is_mint_authority_set", "N/A"))),
                    ("Helius: Freeze Authority", str(helius.get("is_freeze_authority", "N/A"))),
                    ("Helius: Holder Count", str(helius.get("holder_count", "N/A"))),
                    ("Helius: Data Source", helius.get("data_source", "none")),
                ]

        for label, value in onchain_items:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(139, 148, 158)
            pdf.cell(80, 5, label, ln=False)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(230, 237, 243)
            pdf.cell(0, 5, str(value), ln=True)

        pdf.ln(4)

        # ── Macro Context ─────────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "MACRO MARKET CONTEXT", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        macro = report.get("macro", {})
        regime = macro.get("regime", "UNKNOWN")
        regime_color = (0, 208, 156) if regime == "BULL" else (255, 71, 87) if regime in ("BEAR", "EXTREME_FEAR") else (255, 184, 77)

        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*regime_color)
        pdf.cell(0, 8, f"Market Regime: {regime}", ln=True)

        macro_items = [
            ("Score Multiplier", f"{macro.get('multiplier', 1.0):.2f}×"),
            ("Fear & Greed Index", f"{macro.get('fear_greed', 50)} ({macro.get('fear_greed_label', 'Neutral')})"),
            ("BTC Dominance Signal", macro.get("btc_dominance_signal", "NEUTRAL")),
        ]
        for sym, coin_data in macro.get("coins", {}).items():
            macro_items.append((
                f"{sym} 7d Change",
                f"{coin_data.get('chg_7d_pct', 0):+.1f}% ({'above' if coin_data.get('above_ema200') else 'below'} EMA200)"
            ))

        for label, value in macro_items:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(139, 148, 158)
            pdf.cell(70, 5, label, ln=False)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(230, 237, 243)
            pdf.cell(0, 5, str(value), ln=True)

        pdf.ln(4)

        # ── Position Sizing Recommendation ───────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "POSITION SIZING RECOMMENDATION", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        sizing = report.get("position_sizing", {})
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(230, 237, 243)
        pdf.cell(0, 6, f"{sizing.get('label', 'Standard position')} — {sizing.get('pct', 5):.0f}% of capital", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(139, 148, 158)
        pdf.cell(0, 5, f"Recommended size: ${sizing.get('usd', 0):,.0f} (based on current capital)", ln=True)
        pdf.ln(3)

        # TP/SL levels
        price = report.get("price_usd", 0)
        if price > 0:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(0, 208, 156)
            pdf.cell(0, 5, "Take Profit Targets:", ln=True)
            tp_levels = [
                ("TP1 (+50%)", price * 1.5, "Sell 40%"),
                ("TP2 (+150%)", price * 2.5, "Sell 35% of remainder"),
                ("TP3 (+400%)", price * 5.0, "Sell 25% of remainder"),
            ]
            for label, tp_price, action in tp_levels:
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(139, 148, 158)
                pdf.cell(40, 5, label, ln=False)
                pdf.set_text_color(230, 237, 243)
                pdf.cell(50, 5, f"${tp_price:.6f}", ln=False)
                pdf.set_text_color(88, 166, 255)
                pdf.cell(0, 5, action, ln=True)

        pdf.ln(4)

        # ── Key Signals Summary ───────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 208, 156)
        pdf.cell(0, 8, "KEY SIGNALS", ln=True)
        pdf.set_draw_color(0, 208, 156)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

        signals = report.get("key_signals", [])
        for signal in signals:
            icon = "+" if signal.get("positive") else "-"
            pdf.set_font("Helvetica", "", 8)
            color = (0, 208, 156) if signal.get("positive") else (255, 71, 87)
            pdf.set_text_color(*color)
            pdf.cell(0, 5, f"  {icon} {signal.get('text', '')}", ln=True)

        pdf.ln(4)

        # ── Disclaimer ────────────────────────────────────────────────────────
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(72, 79, 88)
        pdf.multi_cell(
            0, 4,
            "DISCLAIMER: This report is generated by an automated AI trading system for informational purposes only. "
            "It does not constitute financial advice. Cryptocurrency trading involves significant risk of loss. "
            "Past performance does not guarantee future results. Always do your own research.",
            ln=True
        )

        pdf.output(output_path)
        return True

    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        return False


# ── Main Report Generation Function ──────────────────────────────────────────
def generate_token_report(
    token_address: str,
    chain: str,
    candidate: Optional["GemCandidate"] = None,
    capital_usd: float = 5000.0,
) -> dict:
    """
    Generate a comprehensive research report for a token.

    Args:
        token_address: Token contract address
        chain: Chain name (ethereum, base, solana, etc.)
        candidate: Optional GemCandidate object (if already scored)
        capital_usd: Current capital for position sizing recommendation

    Returns:
        dict with:
          - pdf_path: Absolute path to generated PDF
          - summary: Key metrics dict for inline dashboard display
          - success: bool
          - error: str (if failed)
    """
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        # ── Gather data ───────────────────────────────────────────────────────
        if candidate:
            token = candidate.token
            symbol = token.symbol
            name = token.name
            price_usd = token.price_usd or 0
            market_cap = token.market_cap or 0
            fdv = token.fdv or 0
            liquidity_usd = token.liquidity_usd or 0
            volume_24h = token.volume_24h or 0
            price_change_24h = token.price_change_24h or 0
            price_change_1h = token.price_change_1h or 0
            age_hours = token.age_hours or 0
            dex = token.dex_id or ""
            gem_score = candidate.gem_score
            strategy_tag = candidate.strategy_tag or "gem_snipe"

            score_components = {
                "Volume Score": candidate.volume_score,
                "Whale/Holder Score": candidate.holder_score,
                "Liquidity Score": candidate.liquidity_score,
                "Safety Score": candidate.contract_score,
                "TA/Momentum Score": candidate.smart_money_score,
                "Boost/CTO Score": candidate.boost_score,
                "Age Score": candidate.age_score,
                "Social Score": candidate.social_score,
                "Grok Sentiment": candidate.grok_sentiment_score,
                "Moralis Intelligence": candidate.moralis_enrichment_score,
                "Dev Wallet Score": candidate.dev_wallet_score,
                "Buy Pressure Score": candidate.buy_pressure_score,
                "Timing Score": candidate.timing_score,
                "Price Context Score": candidate.price_context_score,
                "Sniper Score": candidate.sniper_score,
                "Holder Concentration": candidate.holder_concentration_score,
            }

            on_chain = {
                "exp_buyers_1h": candidate.moralis_buyers_1h,
                "exp_net_buyers_1d": candidate.moralis_exp_net_buyers_1d,
                "holders_change_1d": candidate.moralis_holders_change_1d,
                "security_score": candidate.moralis_security_score,
                "buy_pressure": candidate.moralis_buy_pressure,
                "sniper_count": candidate.sniper_count,
                "sniper_risk": candidate.sniper_risk,
                "top10_holder_pct": candidate.moralis_top10_pct * 100 if candidate.moralis_top10_pct else 0,
                "is_pumpfun_graduate": candidate.is_pumpfun_graduate,
            }

            helius_enrichment = getattr(candidate, "helius_enrichment", {})

            safety = {
                "is_honeypot": not candidate.is_safe,
                "buy_tax": 0,
                "sell_tax": 0,
                "ownership_renounced": candidate.moralis_verified,
                "lp_locked": candidate.moralis_liquidity_locked_pct > 0,
                "goplus_score": candidate.moralis_security_score,
            }

        else:
            # Fetch from DexScreener
            dex_data = _fetch_token_data(token_address, chain)
            symbol = dex_data.get("symbol", "UNKNOWN")
            name = dex_data.get("name", "Unknown")
            price_usd = dex_data.get("price_usd", 0)
            market_cap = dex_data.get("market_cap", 0)
            fdv = dex_data.get("fdv", 0)
            liquidity_usd = dex_data.get("liquidity_usd", 0)
            volume_24h = dex_data.get("volume_24h", 0)
            price_change_24h = dex_data.get("price_change_24h", 0)
            price_change_1h = dex_data.get("price_change_1h", 0)
            created_at = dex_data.get("created_at", 0)
            age_hours = (time.time() * 1000 - created_at) / 3_600_000 if created_at else 0
            dex = dex_data.get("dex_id", "")
            gem_score = 0.0
            strategy_tag = "standalone_lookup"
            score_components = {}
            on_chain = {}
            helius_enrichment = {}
            safety = _fetch_goplus_safety(token_address, chain)

        # ── Macro context ─────────────────────────────────────────────────────
        macro = _fetch_macro_context()

        # ── Position sizing ───────────────────────────────────────────────────
        sizing = _position_size_recommendation(gem_score, capital_usd)

        # ── Verdict ───────────────────────────────────────────────────────────
        if gem_score >= 80:
            verdict = "STRONG BUY"
        elif gem_score >= 65:
            verdict = "BUY"
        elif gem_score >= 55:
            verdict = "WATCHLIST"
        elif gem_score > 0:
            verdict = "AVOID"
        else:
            verdict = "UNSCORED"

        # ── Key signals ───────────────────────────────────────────────────────
        key_signals = []
        if candidate:
            if candidate.moralis_buyers_1h > 20:
                key_signals.append({"text": f"Strong buying: {candidate.moralis_buyers_1h} experienced buyers in 1h", "positive": True})
            if candidate.moralis_exp_net_buyers_1d > 10:
                key_signals.append({"text": f"Whale accumulation: {candidate.moralis_exp_net_buyers_1d} net experienced buyers (1d)", "positive": True})
            if candidate.is_pumpfun_graduate:
                key_signals.append({"text": "Pump.fun graduate — bonding curve complete, Raydium listed", "positive": True})
            if candidate.binance_smart_money_confirmed:
                key_signals.append({"text": f"Binance smart money confirmed (rank #{candidate.binance_smart_money_rank})", "positive": True})
            if candidate.sniper_count >= 5:
                key_signals.append({"text": f"HIGH SNIPER RISK: {candidate.sniper_count} snipers detected", "positive": False})
            if candidate.moralis_top10_pct > 0.5:
                key_signals.append({"text": f"High whale concentration: top 10 hold {candidate.moralis_top10_pct*100:.0f}%", "positive": False})
            if candidate.is_near_ath:
                key_signals.append({"text": "Near 7-day ATH — FOMO entry risk", "positive": False})
            if candidate.is_accumulation_zone:
                key_signals.append({"text": "In accumulation zone (bottom 30% of 7d range)", "positive": True})
            if candidate.grok_sentiment_score > 70:
                key_signals.append({"text": f"Strong Grok sentiment: {candidate.grok_sentiment_score:.0f}/100", "positive": True})
            if macro.get("regime") == "BEAR":
                key_signals.append({"text": "MACRO WARNING: Bear market regime — elevated risk for altcoins", "positive": False})
            elif macro.get("regime") == "BULL":
                key_signals.append({"text": "Macro tailwind: Bull market regime active", "positive": True})

        # ── Build report dict ─────────────────────────────────────────────────
        report = {
            "symbol": symbol,
            "name": name,
            "address": token_address,
            "chain": chain,
            "dex": dex,
            "price_usd": price_usd,
            "market_cap": market_cap,
            "fdv": fdv,
            "liquidity_usd": liquidity_usd,
            "volume_24h": volume_24h,
            "price_change_24h": price_change_24h,
            "price_change_1h": price_change_1h,
            "age_hours": age_hours,
            "gem_score": gem_score,
            "verdict": verdict,
            "strategy_tag": strategy_tag,
            "score_components": score_components,
            "on_chain": on_chain,
            "helius_enrichment": helius_enrichment,
            "safety": safety,
            "macro": macro,
            "position_sizing": sizing,
            "key_signals": key_signals,
            "generated_at": generated_at,
        }

        # ── Generate PDF ──────────────────────────────────────────────────────
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_symbol = "".join(c for c in symbol if c.isalnum() or c in "_-")[:20]
        filename = f"{safe_symbol}_{chain}_{ts}.pdf"
        pdf_path = os.path.join(_REPORTS_DIR, filename)

        pdf_ok = _generate_pdf(report, pdf_path)

        # ── Save JSON summary ─────────────────────────────────────────────────
        json_path = pdf_path.replace(".pdf", ".json")
        try:
            with open(json_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
        except Exception:
            pass

        return {
            "success": pdf_ok,
            "pdf_path": pdf_path if pdf_ok else None,
            "json_path": json_path,
            "symbol": symbol,
            "gem_score": gem_score,
            "verdict": verdict,
            "generated_at": generated_at,
            "error": None if pdf_ok else "PDF generation failed",
            "summary": {
                "symbol": symbol,
                "score": gem_score,
                "verdict": verdict,
                "price": price_usd,
                "market_cap": market_cap,
                "liquidity": liquidity_usd,
                "regime": macro.get("regime", "UNKNOWN"),
                "sizing_label": sizing["label"],
                "sizing_usd": sizing["usd"],
            },
        }

    except Exception as e:
        logger.error(f"Research report generation failed: {e}", exc_info=True)
        return {
            "success": False,
            "pdf_path": None,
            "error": str(e),
            "symbol": token_address[:8],
            "gem_score": 0,
            "verdict": "ERROR",
        }


# ── List recent reports ───────────────────────────────────────────────────────
def list_recent_reports(limit: int = 20) -> list[dict]:
    """Return list of recently generated reports for the dashboard."""
    reports = []
    try:
        for fname in sorted(os.listdir(_REPORTS_DIR), reverse=True):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(_REPORTS_DIR, fname)) as f:
                        data = json.load(f)
                    pdf_name = fname.replace(".json", ".pdf")
                    pdf_path = os.path.join(_REPORTS_DIR, pdf_name)
                    reports.append({
                        "symbol": data.get("symbol", "?"),
                        "chain": data.get("chain", "?"),
                        "gem_score": data.get("gem_score", 0),
                        "verdict": data.get("verdict", "?"),
                        "generated_at": data.get("generated_at", ""),
                        "pdf_path": pdf_path if os.path.exists(pdf_path) else None,
                        "filename": fname,
                    })
                    if len(reports) >= limit:
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return reports
