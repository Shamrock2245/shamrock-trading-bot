"""
dashboard/nav.py — Persistent navigation bar for every page.

Renders a Binance/Dexscreener-style top nav bar that appears on all pages.
Import and call `render_nav()` at the top of each page module.
"""

import streamlit as st

# Page registry: (label, emoji, url_path)
# url_path must match the Streamlit multipage filename convention
PAGES = [
    ("Command Center", "☘️", "/"),
    ("Scanner", "🔍", "/Gem_Scanner"),
    ("Analytics", "📊", "/Analytics"),
    ("Gem Advisor", "🧠", "/Gem_Advisor"),
    ("Positions", "💰", "/Positions"),
    ("Health", "🏥", "/System_Health"),
    ("Wallets", "👛", "/Wallet_Overview"),
    ("Alpha", "🤝", "/Alpha_Wallets"),
    ("Sniper", "🎯", "/Sniper_Wallets"),
    ("Paycheck", "🏦", "/Paycheck_Wallet"),
    ("Paper P&L", "📈", "/Paper_PnL"),
]

# CSS for the nav bar — injected once per page
_NAV_CSS = """
<style>
/* ── Persistent Top Nav ──────────────────────────────────────────────────── */
.shamrock-nav {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 6px 8px;
    background: rgba(13, 17, 23, 0.92);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(48, 54, 61, 0.5);
    border-radius: 12px;
    margin-bottom: 16px;
    overflow-x: auto;
    -ms-overflow-style: none;
    scrollbar-width: none;
    position: sticky;
    top: 0;
    z-index: 999;
}
.shamrock-nav::-webkit-scrollbar { display: none; }

.shamrock-nav-brand {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px 6px 8px;
    margin-right: 4px;
    border-right: 1px solid rgba(48, 54, 61, 0.6);
    text-decoration: none !important;
    white-space: nowrap;
    flex-shrink: 0;
}
.shamrock-nav-brand span.brand-icon { font-size: 1.3rem; }
.shamrock-nav-brand span.brand-text {
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    background: linear-gradient(135deg, #00D09C, #00FFB8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.shamrock-nav a.nav-link {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 10px;
    border-radius: 8px;
    text-decoration: none !important;
    color: #8B949E;
    font-size: 0.68rem;
    font-weight: 600;
    white-space: nowrap;
    transition: all 0.18s ease;
    flex-shrink: 0;
}
.shamrock-nav a.nav-link:hover {
    background: rgba(0, 208, 156, 0.08);
    color: #E6EDF3;
}
.shamrock-nav a.nav-link.active {
    background: rgba(0, 208, 156, 0.12);
    color: #00D09C;
    font-weight: 700;
}
.shamrock-nav a.nav-link .nav-emoji {
    font-size: 0.82rem;
    line-height: 1;
}

/* ── Live Pulse ────────────────────────────────────────────────────── */
.nav-live-dot {
    width: 6px; height: 6px;
    background: #00D09C;
    border-radius: 50%;
    margin-left: auto;
    flex-shrink: 0;
    animation: nav-pulse 2s ease-in-out infinite;
    box-shadow: 0 0 6px rgba(0, 208, 156, 0.6);
}
@keyframes nav-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}
</style>
"""


def render_nav(current_page: str = ""):
    """Render the persistent top navigation bar.
    
    Args:
        current_page: The label of the currently active page (e.g. "Analytics").
                      Used to highlight the active nav link.
    """
    links_html = ""
    for label, emoji, path in PAGES:
        is_active = "active" if label == current_page else ""
        links_html += (
            f'<a class="nav-link {is_active}" href="{path}">'
            f'<span class="nav-emoji">{emoji}</span>{label}</a>'
        )

    nav_html = (
        f'{_NAV_CSS}'
        f'<div class="shamrock-nav">'
        f'<a class="shamrock-nav-brand" href="/">'
        f'<span class="brand-icon">☘️</span>'
        f'<span class="brand-text">SHAMROCK</span>'
        f'</a>'
        f'{links_html}'
        f'<div class="nav-live-dot"></div>'
        f'</div>'
    )
    st.markdown(nav_html, unsafe_allow_html=True)
