"""
dashboard/styles.py — Premium dark-mode CSS for Shamrock Trading Dashboard.

Injects Fortune 50-grade glassmorphism, glow effects, and custom components.
"""

PREMIUM_CSS = """
<style>
/* ── Import Google Font ──────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ── Root Variables ──────────────────────────────────────────────────────── */
:root {
    --bg-primary: #0A0E14;
    --bg-secondary: #131920;
    --bg-card: rgba(19, 25, 32, 0.85);
    --bg-card-hover: rgba(19, 25, 32, 0.95);
    --border-subtle: rgba(0, 208, 156, 0.12);
    --border-glow: rgba(0, 208, 156, 0.3);
    --accent: #00D09C;
    --accent-dim: rgba(0, 208, 156, 0.15);
    --accent-glow: rgba(0, 208, 156, 0.4);
    --text-primary: #E6EDF3;
    --text-secondary: #8B949E;
    --text-muted: #484F58;
    --success: #00D09C;
    --danger: #FF4757;
    --warning: #FFB84D;
    --info: #58A6FF;
    --radius: 16px;
    --radius-sm: 10px;
}

/* ── Global ──────────────────────────────────────────────────────────────── */
* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.main .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1400px !important;
}

/* Hide Streamlit branding */
#MainMenu, footer, header {
    visibility: hidden !important;
}

.stApp > header {
    background-color: transparent !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D1117 0%, #0A0E14 100%) !important;
    border-right: 1px solid var(--border-subtle) !important;
}

[data-testid="stSidebar"] .stMarkdown h1 {
    background: linear-gradient(135deg, #00D09C, #00E6AC, #00FFB8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
    font-size: 1.6rem !important;
    letter-spacing: -0.02em;
}

/* ── Metric Cards (Hero Stats) ───────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    padding: 1.2rem 1.4rem !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03) !important;
}

[data-testid="stMetric"]:hover {
    border-color: var(--border-glow) !important;
    box-shadow: 0 8px 32px rgba(0, 208, 156, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    transform: translateY(-2px) !important;
}

[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}

[data-testid="stMetricDelta"] {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #00D09C, #00B884) !important;
    color: #0A0E14 !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.5rem 1.2rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 15px rgba(0, 208, 156, 0.3) !important;
}

.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0, 208, 156, 0.45) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-sm) !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid var(--border-subtle) !important;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-secondary) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 1rem !important;
    transition: all 0.2s ease !important;
}

.stTabs [aria-selected="true"] {
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
    font-weight: 700 !important;
}

/* ── DataFrames ──────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}

/* ── Expanders ───────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}

/* ── Dividers ────────────────────────────────────────────────────────────── */
hr {
    border-color: var(--border-subtle) !important;
    margin: 1.5rem 0 !important;
}

/* ── Status Badges ───────────────────────────────────────────────────────── */
.status-live {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(0, 208, 156, 0.12);
    border: 1px solid rgba(0, 208, 156, 0.3);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.75rem;
    font-weight: 700;
    color: #00D09C;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.status-paper {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 184, 77, 0.12);
    border: 1px solid rgba(255, 184, 77, 0.3);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.75rem;
    font-weight: 700;
    color: #FFB84D;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.pulse {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #00D09C;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
}

/* ── Score Badges ────────────────────────────────────────────────────────── */
.score-high {
    background: rgba(0, 208, 156, 0.15);
    color: #00D09C;
    border: 1px solid rgba(0, 208, 156, 0.3);
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 0.85rem;
}

.score-mid {
    background: rgba(255, 184, 77, 0.15);
    color: #FFB84D;
    border: 1px solid rgba(255, 184, 77, 0.3);
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 0.85rem;
}

.score-low {
    background: rgba(255, 71, 87, 0.15);
    color: #FF4757;
    border: 1px solid rgba(255, 71, 87, 0.3);
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 0.85rem;
}

/* ── Chain Pills ─────────────────────────────────────────────────────────── */
.chain-eth  { background: rgba(98,126,234,0.15); color: #627EEA; border: 1px solid rgba(98,126,234,0.3); border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.chain-base { background: rgba(0,82,255,0.15);   color: #0052FF; border: 1px solid rgba(0,82,255,0.3);   border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.chain-arb  { background: rgba(40,160,240,0.15); color: #28A0F0; border: 1px solid rgba(40,160,240,0.3); border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.chain-poly { background: rgba(130,71,229,0.15); color: #8247E5; border: 1px solid rgba(130,71,229,0.3); border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.chain-bsc  { background: rgba(240,185,11,0.15); color: #F0B90B; border: 1px solid rgba(240,185,11,0.3); border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.chain-sol  { background: rgba(153,69,255,0.15); color: #9945FF; border: 1px solid rgba(153,69,255,0.3); border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: rgba(0, 208, 156, 0.3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(0, 208, 156, 0.5); }

</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Shared Plotly layout — use via **PLOTLY_LAYOUT in fig.update_layout()
# NOTE: Do NOT pass legend= separately when using **PLOTLY_LAYOUT; it is
# already included here. To override legend for a specific chart, exclude it:
#   fig.update_layout(**{k: v for k, v in PLOTLY_LAYOUT.items() if k != "legend"}, legend=dict(...))
# ─────────────────────────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#E6EDF3", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    xaxis=dict(
        gridcolor="rgba(255,255,255,0.04)",
        zerolinecolor="rgba(255,255,255,0.06)",
        tickfont=dict(size=11, color="#8B949E"),
    ),
    yaxis=dict(
        gridcolor="rgba(255,255,255,0.04)",
        zerolinecolor="rgba(255,255,255,0.06)",
        tickfont=dict(size=11, color="#8B949E"),
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        font=dict(size=11, color="#8B949E"),
    ),
    hoverlabel=dict(
        bgcolor="#1C2333",
        bordercolor="#00D09C",
        font=dict(family="Inter, sans-serif", size=12, color="#E6EDF3"),
    ),
)

# Horizontal legend variant — use for charts that need legend below the plot
PLOTLY_LAYOUT_HLEGEND = {
    **{k: v for k, v in PLOTLY_LAYOUT.items() if k != "legend"},
    "legend": dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        font=dict(size=11, color="#8B949E"),
    ),
}

ACCENT = "#00D09C"
ACCENT_DIM = "rgba(0, 208, 156, 0.15)"
DANGER = "#FF4757"
WARNING = "#FFB84D"
INFO = "#58A6FF"

CHAIN_COLORS = {
    "ethereum": "#627EEA",
    "base": "#0052FF",
    "arbitrum": "#28A0F0",
    "polygon": "#8247E5",
    "bsc": "#F0B90B",
    "solana": "#9945FF",   # Solana purple
}
