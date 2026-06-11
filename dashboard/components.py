"""
dashboard/components.py — Reusable UI components for the Shamrock Dashboard.

Premium, composable building blocks that eliminate inline HTML sprawl
and enforce visual consistency across all pages.
"""

import streamlit as st
from styles import ACCENT, DANGER, WARNING, INFO, CHAIN_COLORS, CHAIN_EMOJI


# ─────────────────────────────────────────────────────────────────────────────
# KPI / Stat Cards
# ─────────────────────────────────────────────────────────────────────────────

def render_kpi_row(metrics: list[dict]):
    """
    Render a row of KPI cards using native st.metric with glassmorphism styling.

    Each metric dict:
      label, value, delta (optional), delta_color (optional: "normal"|"inverse"|"off")
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                delta_color=m.get("delta_color", "normal"),
                border=True,
            )


def stat_card_html(icon: str, label: str, value: str, delta: str = "",
                   delta_class: str = "neutral") -> str:
    """Return HTML for a premium stat card (for custom HTML rendering)."""
    return (
        f'<div class="stat-card">'
        f'<div class="stat-icon">{icon}</div>'
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value">{value}</div>'
        f'<div class="stat-delta {delta_class}">{delta}</div>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# P&L Hero
# ─────────────────────────────────────────────────────────────────────────────

def render_pnl_hero(realized_pnl: float, total_trades: int, win_rate: float,
                    unrealized_pnl: float = 0.0, open_positions: int = 0):
    """Render the hero P&L display — the centerpiece of the command center."""
    pnl_class = "positive" if realized_pnl > 0 else ("negative" if realized_pnl < 0 else "zero")
    pnl_sign = "+" if realized_pnl > 0 else ""

    # Unrealized section
    unr_html = ""
    if open_positions > 0:
        unr_sign = "+" if unrealized_pnl >= 0 else ""
        unr_color = ACCENT if unrealized_pnl >= 0 else DANGER
        unr_html = (
            f'<div style="display:flex;justify-content:center;gap:24px;margin-top:12px;'
            f'padding-top:12px;border-top:1px solid rgba(48,54,61,0.4);">'
            f'<div style="text-align:center;">'
            f'<div style="color:#484F58;font-size:0.6rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.1em;">Unrealized</div>'
            f'<div style="color:{unr_color};font-size:1.1rem;font-weight:700;'
            f'font-family:JetBrains Mono,monospace;">{unr_sign}{unrealized_pnl:.2f}%</div>'
            f'</div>'
            f'<div style="text-align:center;">'
            f'<div style="color:#484F58;font-size:0.6rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.1em;">Open</div>'
            f'<div style="color:#E6EDF3;font-size:1.1rem;font-weight:700;'
            f'font-family:JetBrains Mono,monospace;">{open_positions}</div>'
            f'</div>'
            f'</div>'
        )

    subtitle = (
        f"{total_trades} trades · {win_rate:.0f}% win rate"
        if total_trades > 0 else "Awaiting first trade"
    )

    st.markdown(
        f'<div class="pnl-hero">'
        f'<div class="pnl-label">Realized P&L</div>'
        f'<div class="pnl-value {pnl_class}">{pnl_sign}${abs(realized_pnl):,.2f}</div>'
        f'<div class="pnl-subtitle">{subtitle}</div>'
        f'{unr_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Mode Banner
# ─────────────────────────────────────────────────────────────────────────────

def render_strategy_banner(mode: str, god_mode: bool = False,
                           consec_wins: int = 0, consec_losses: int = 0,
                           house_pool: float = 0, drawdown: float = 0,
                           hwm: float = 0, current_cap: float = 0,
                           session_pnl: float = 0):
    """Render the strategy mode ticker / status banner."""
    mode_upper = mode.upper()
    _mode_colors = {
        "LIVE": ("#00D09C", "rgba(0,208,156,0.06)"),
        "PAPER": ("#FFB84D", "rgba(255,184,77,0.06)"),
        "GOD MODE": ("#FFD700", "rgba(255,215,0,0.08)"),
        "RECOVERY": ("#FF4757", "rgba(255,71,87,0.06)"),
        "EXPANSION": ("#58A6FF", "rgba(88,166,255,0.06)"),
        "CONSERVATIVE": ("#FFB84D", "rgba(255,184,77,0.06)"),
    }
    mc, mbg = _mode_colors.get(mode_upper, ("#8B949E", "rgba(139,148,158,0.06)"))

    # Build ticker items
    items = []
    if god_mode:
        items.append('<span style="color:#FFD700;font-weight:800;">⚡ GOD MODE</span>')
    if consec_wins >= 2:
        items.append(f'<span style="color:#00D09C;">🔥 {consec_wins}-WIN STREAK</span>')
    if consec_losses >= 2:
        items.append(f'<span style="color:#FF4757;">⚠️ {consec_losses} CONSECUTIVE LOSSES</span>')
    if house_pool > 1:
        items.append(f'<span style="color:#58A6FF;">🏦 House: ${house_pool:.2f}</span>')
    if drawdown > 50:
        items.append(f'<span style="color:#FF4757;">📉 DD: {drawdown:.1f}%</span>')

    # Always show capital info
    items.append(
        f'<span style="color:#484F58;">Capital: ${current_cap:.2f} · '
        f'HWM: ${hwm:.2f} · Session: '
        f'{"+" if session_pnl >= 0 else ""}${session_pnl:.4f}</span>'
    )

    st.markdown(
        f'<div style="background:{mbg};border:1px solid {mc}33;border-radius:10px;'
        f'padding:10px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">'
        f'<span style="background:{mc}22;color:{mc};font-size:0.68rem;font-weight:800;'
        f'text-transform:uppercase;letter-spacing:0.1em;padding:3px 10px;border-radius:20px;'
        f'border:1px solid {mc}44;white-space:nowrap;">● {mode_upper}</span>'
        + " &nbsp;·&nbsp; ".join(items)
        + '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Macro Market Regime
# ─────────────────────────────────────────────────────────────────────────────

def render_macro_regime(regime: str, multiplier: float, min_score: float,
                        fg_value: int, fg_label: str, btc_dom: str,
                        coins: dict = None, cached: bool = False):
    """Render the macro market regime widget."""
    _regime_colors = {
        "BULL": ("#00D09C", "rgba(0,208,156,0.06)", "rgba(0,208,156,0.25)"),
        "NEUTRAL": ("#8B949E", "rgba(139,148,158,0.04)", "rgba(139,148,158,0.15)"),
        "BEAR": ("#FF4757", "rgba(255,71,87,0.06)", "rgba(255,71,87,0.25)"),
        "EXTREME_FEAR": ("#FF4757", "rgba(255,71,87,0.10)", "rgba(255,71,87,0.40)"),
    }
    rc, rbg, rborder = _regime_colors.get(regime, _regime_colors["NEUTRAL"])
    _regime_icons = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴", "EXTREME_FEAR": "🚨"}
    regime_icon = _regime_icons.get(regime, "🟡")

    # Fear & Greed color
    fg_color = (
        "#FF4757" if fg_value <= 25
        else "#FFB84D" if fg_value <= 45
        else "#8B949E" if fg_value <= 55
        else "#58A6FF" if fg_value <= 75
        else "#00D09C"
    )

    mult_color = "#00D09C" if multiplier >= 1.0 else ("#FF4757" if multiplier < 0.85 else "#FFB84D")
    cached_str = ' <span style="color:#30363D;font-size:0.6rem;">(cached)</span>' if cached else ''

    # Build coin pills
    coin_pills = ""
    if coins:
        for sym, cr in coins.items():
            cc = "#00D09C" if cr.regime == "BULL" else ("#FF4757" if cr.regime == "BEAR" else "#8B949E")
            ema_icon = "▲" if cr.above_ema200 else "▼"
            coin_pills += (
                f'<div style="background:rgba(255,255,255,0.03);border:1px solid {cc}33;'
                f'border-radius:8px;padding:6px 10px;min-width:90px;">'
                f'<div style="color:#484F58;font-size:0.58rem;font-weight:700;'
                f'text-transform:uppercase;">{sym}</div>'
                f'<div style="color:{cc};font-size:0.82rem;font-weight:700;'
                f'font-family:monospace;">{ema_icon} {cr.chg_7d_pct:+.1f}%</div>'
                f'<div style="color:#30363D;font-size:0.58rem;">'
                f'7d · EMA200 {"above" if cr.above_ema200 else "below"}</div>'
                f'</div>'
            )

    # Quick stats row
    stats_html = (
        f'<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">'
        f'<div style="text-align:center;">'
        f'<div style="color:#484F58;font-size:0.55rem;font-weight:700;'
        f'text-transform:uppercase;">Multiplier</div>'
        f'<div style="color:{mult_color};font-size:1.0rem;font-weight:800;'
        f'font-family:monospace;">{multiplier:.2f}×</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="color:#484F58;font-size:0.55rem;font-weight:700;'
        f'text-transform:uppercase;">Min Score</div>'
        f'<div style="color:#E6EDF3;font-size:1.0rem;font-weight:800;'
        f'font-family:monospace;">{min_score:.0f}</div></div>'
        f'<div style="text-align:center;">'
        f'<div style="color:#484F58;font-size:0.55rem;font-weight:700;'
        f'text-transform:uppercase;">Fear & Greed</div>'
        f'<div style="color:{fg_color};font-size:1.0rem;font-weight:800;'
        f'font-family:monospace;">{fg_value} <span style="font-size:0.7rem;">'
        f'{fg_label}</span></div></div>'
        f'<div style="text-align:center;">'
        f'<div style="color:#484F58;font-size:0.55rem;font-weight:700;'
        f'text-transform:uppercase;">BTC Dom</div>'
        f'<div style="color:#8B949E;font-size:0.78rem;font-weight:700;">'
        f'{btc_dom.replace("_"," ")}</div></div>'
        f'</div>'
    )

    st.markdown(
        f'<div style="background:{rbg};border:1px solid {rborder};border-radius:12px;'
        f'padding:12px 18px;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'flex-wrap:wrap;gap:10px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:1.2rem;">{regime_icon}</span>'
        f'<div>'
        f'<div style="color:#484F58;font-size:0.6rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.1em;">Macro Regime{cached_str}</div>'
        f'<div style="color:{rc};font-size:1.05rem;font-weight:800;'
        f'letter-spacing:0.05em;">{regime}</div>'
        f'</div></div>'
        f'{stats_html}'
        f'</div>'
        + (f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">'
           f'{coin_pills}</div>' if coin_pills else '')
        + f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Trade Feed
# ─────────────────────────────────────────────────────────────────────────────

def render_trade_row(trade: dict):
    """Render a single trade row with direction badge, symbol, chain, P&L."""
    direction = trade.get("direction", trade.get("action", "buy")).lower()
    symbol = trade.get("symbol", trade.get("token_symbol", "???"))
    chain = trade.get("chain", "")
    pnl = float(trade.get("pnl_usd", 0))
    ts = trade.get("timestamp", "")[:16]
    emoji = CHAIN_EMOJI.get(chain, "⬡")

    if direction == "buy":
        dir_badge = ('<span style="background:rgba(0,208,156,0.12);color:#00D09C;'
                     'font-size:0.62rem;font-weight:800;padding:1px 6px;'
                     'border-radius:4px;">BUY</span>')
        pnl_html = ""
    else:
        dir_badge = ('<span style="background:rgba(255,71,87,0.12);color:#FF4757;'
                     'font-size:0.62rem;font-weight:800;padding:1px 6px;'
                     'border-radius:4px;">SELL</span>')
        pnl_color = "#00D09C" if pnl >= 0 else "#FF4757"
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_html = (f'<span style="color:{pnl_color};font-size:0.72rem;'
                    f'font-weight:700;font-family:monospace;">'
                    f'{pnl_sign}${abs(pnl):,.2f}</span>')

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;'
        f'border-bottom:1px solid rgba(48,54,61,0.3);">'
        f'{dir_badge}'
        f'<span style="color:#E6EDF3;font-size:0.78rem;font-weight:600;">{symbol}</span>'
        f'<span style="color:#484F58;font-size:0.65rem;">{emoji} {chain[:3]}</span>'
        f'<span style="flex:1;"></span>'
        f'{pnl_html}'
        f'<span style="color:#30363D;font-size:0.6rem;font-family:monospace;">'
        f'{ts[11:]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_trade_feed(trades: list, max_items: int = 12):
    """Render a feed of recent trades."""
    if not trades:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:2rem;">'
            '<div style="font-size:1.4rem;margin-bottom:6px;">📜</div>'
            '<div style="color:#8B949E;">No trades yet</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    recent = sorted(trades, key=lambda t: t.get("timestamp", ""), reverse=True)[:max_items]
    for t in recent:
        render_trade_row(t)


# ─────────────────────────────────────────────────────────────────────────────
# Win/Loss Summary Bar
# ─────────────────────────────────────────────────────────────────────────────

def render_winloss_bar(trades: list):
    """Render a compact win/loss summary bar."""
    sells = [t for t in trades if t.get("direction") == "sell"
             or str(t.get("action", "")).upper() == "SELL"]
    buys = [t for t in trades if t.get("direction") == "buy"
            or str(t.get("action", "")).upper() == "BUY"]
    wins = len([t for t in sells if float(t.get("pnl_usd", 0)) > 0])
    losses = len(sells) - wins
    total = max(wins + losses, 1)
    w_pct = (wins / total) * 100

    st.markdown(
        f'<div style="margin-top:10px;">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
        f'<span style="color:#00D09C;font-size:0.68rem;font-weight:700;">✅ {wins} wins</span>'
        f'<span style="color:#FF4757;font-size:0.68rem;font-weight:700;">❌ {losses} losses</span>'
        f'</div>'
        f'<div style="height:6px;background:rgba(255,71,87,0.3);border-radius:3px;overflow:hidden;">'
        f'<div style="width:{w_pct:.0f}%;height:100%;background:#00D09C;border-radius:3px;"></div>'
        f'</div>'
        f'<div style="color:#484F58;font-size:0.62rem;text-align:center;margin-top:4px;">'
        f'{len(buys)} buys · {len(sells)} sells · {w_pct:.0f}% win rate</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page Header
# ─────────────────────────────────────────────────────────────────────────────

def render_page_header(icon: str, title: str, subtitle: str = "",
                       badge_text: str = "", badge_color: str = ""):
    """Render a consistent page header with optional badge."""
    badge_html = ""
    if badge_text:
        bc = badge_color or "#FFB84D"
        badge_html = (
            f'<div style="margin-left:auto;">'
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'background:rgba({_hex_to_rgb(bc)},0.1);border:1px solid rgba({_hex_to_rgb(bc)},0.25);'
            f'border-radius:20px;padding:4px 14px;font-size:0.72rem;font-weight:700;'
            f'color:{bc};text-transform:uppercase;letter-spacing:0.08em;">'
            f'{badge_text}</span></div>'
        )

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:1rem;">'
        f'<span style="font-size:2rem;">{icon}</span>'
        f'<div>'
        f'<h1 style="margin:0;padding:0;font-size:1.5rem;font-weight:800;'
        f'background:linear-gradient(135deg,#00D09C,#00E6AC);'
        f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;">'
        f'{title}</h1>'
        + (f'<span style="color:#8B949E;font-size:0.8rem;">{subtitle}</span>' if subtitle else '')
        + f'</div>'
        f'{badge_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _hex_to_rgb(hex_color: str) -> str:
    """Convert #RRGGBB to 'R,G,B' string."""
    h = hex_color.lstrip('#')
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"


# ─────────────────────────────────────────────────────────────────────────────
# Guardian / Anchor Cards
# ─────────────────────────────────────────────────────────────────────────────

def render_guardian_card(label: str, value: str, subtitle: str = "",
                         status_text: str = "", status_color: str = "",
                         is_preservation: bool = False):
    """Render a guardian/anchor status card."""
    card_class = "preservation" if is_preservation else "healthy"
    status_html = ""
    if status_text:
        sc = status_color or ACCENT
        status_html = (
            f'<div style="margin-top:6px;font-size:0.7rem;font-weight:700;'
            f'color:{sc};">{status_text}</div>'
        )

    st.markdown(
        f'<div class="guardian-card {card_class}">'
        f'<div class="guardian-label">{label}</div>'
        f'<div class="guardian-value">{value}</div>'
        f'<div class="guardian-sub">{subtitle}</div>'
        f'{status_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Navigation Cards
# ─────────────────────────────────────────────────────────────────────────────

def render_nav_card(href: str, icon: str, title: str, desc: str,
                    badge: str = "", active: bool = False):
    """Render a navigation card with optional badge and active state."""
    badge_html = f'<div class="nav-badge">{badge}</div>' if badge else ""
    active_style = (
        'border-color:rgba(0,208,156,0.2);'
        'background:linear-gradient(145deg,rgba(0,208,156,0.03),rgba(13,17,23,0.98));'
    ) if active else ""

    st.markdown(
        f'<a href="{href}" target="_self" class="nav-card" style="{active_style}">'
        f'{badge_html}'
        f'<span class="nav-icon">{icon}</span>'
        f'<div class="nav-title">{title}</div>'
        f'<div class="nav-desc">{desc}</div>'
        f'</a>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Empty States
# ─────────────────────────────────────────────────────────────────────────────

def render_empty_state(icon: str, title: str, subtitle: str = ""):
    """Render a beautiful empty state placeholder."""
    sub_html = (
        f'<div style="color:#484F58;font-size:0.75rem;margin-top:4px;">'
        f'{subtitle}</div>'
    ) if subtitle else ""

    st.markdown(
        f'<div class="glass-card" style="text-align:center;padding:3rem;">'
        f'<div style="font-size:2.5rem;margin-bottom:8px;">{icon}</div>'
        f'<div style="color:#8B949E;font-size:1rem;">{title}</div>'
        f'{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Section Headers (Zone Dividers)
# ─────────────────────────────────────────────────────────────────────────────

def render_section_header(icon: str, title: str, subtitle: str = ""):
    """Render a premium section header / zone divider.
    
    Used to visually separate logical zones on the Command Center
    (Portfolio Overview, Market Intelligence, Active Trading, etc.)
    
    Args:
        icon:     Emoji or icon string.
        title:    Section title (rendered uppercase).
        subtitle: Optional right-aligned subtitle text.
    """
    sub_html = (
        f'<span class="zone-subtitle">{subtitle}</span>'
    ) if subtitle else ""

    st.markdown(
        f'<div class="zone-header">'
        f'<span class="zone-icon">{icon}</span>'
        f'<span class="zone-title">{title}</span>'
        f'{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_zone_start(zone_class: str = ""):
    """Open a zone container div for visual grouping.
    
    Args:
        zone_class: Optional CSS class suffix (e.g., "trading", "intelligence", "system")
    """
    cls = f"zone-container zone-{zone_class}" if zone_class else "zone-container"
    st.markdown(f'<div class="{cls}">', unsafe_allow_html=True)


def render_zone_end():
    """Close a zone container div."""
    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Management Cards
# ─────────────────────────────────────────────────────────────────────────────

def render_wallet_card_html(
    address: str,
    label: str = "",
    chain_type: str = "evm",
    source: str = "system",
) -> str:
    """Return HTML for a single wallet card (for use in Alpha Wallets page).
    
    Args:
        address:    Wallet address.
        label:      Human-readable label.
        chain_type: "evm" or "solana".
        source:     "system", "dashboard", or "vip".
    
    Returns:
        HTML string for the wallet card.
    """
    # Avatar icon based on chain
    avatar_icon = "⟠" if chain_type == "evm" else "◎"
    avatar_bg = (
        "rgba(98,126,234,0.12)" if chain_type == "evm"
        else "rgba(153,69,255,0.12)"
    )
    avatar_border = (
        "rgba(98,126,234,0.25)" if chain_type == "evm"
        else "rgba(153,69,255,0.25)"
    )

    # Source badge
    badge_map = {
        "system": ("SYSTEM", "badge-system"),
        "dashboard": ("CUSTOM", "badge-custom"),
        "vip": ("⭐ VIP", "badge-vip"),
    }
    badge_text, badge_class = badge_map.get(source, ("SYSTEM", "badge-system"))

    # Display label or truncated address
    display_label = label if label else f"{address[:6]}...{address[-4:]}"
    display_addr = f"{address[:8]}...{address[-6:]}"

    return (
        f'<div class="wallet-card">'
        f'<div class="wallet-avatar" style="background:{avatar_bg};'
        f'border-color:{avatar_border};">{avatar_icon}</div>'
        f'<div class="wallet-info">'
        f'<div class="wallet-label">{display_label}</div>'
        f'<div class="wallet-address">{display_addr}</div>'
        f'</div>'
        f'<span class="wallet-badge {badge_class}">{badge_text}</span>'
        f'</div>'
    )

