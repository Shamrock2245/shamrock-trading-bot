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
    box-shadow: 0 8px 40px rgba(0, 208, 156, 0.08), 0 4px 24px rgba(0, 0, 0, 0.4) !important;
    transform: translateY(-2px) !important;
}

[data-testid="stMetric"] label {
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-weight: 800 !important;
    font-size: 1.9rem !important;
    letter-spacing: -0.03em !important;
    background: linear-gradient(135deg, #FFFFFF 0%, #C8D6E5 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

[data-testid="stMetric"] [data-testid="stMetricDelta"] > div {
    font-weight: 600 !important;
    font-size: 0.82rem !important;
}

/* ── Data Tables ─────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}

.stDataFrame table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
}

.stDataFrame thead th {
    background: rgba(0, 208, 156, 0.08) !important;
    color: var(--accent) !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.06em !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    padding: 0.75rem 1rem !important;
}

.stDataFrame tbody td {
    border-bottom: 1px solid rgba(255, 255, 255, 0.03) !important;
    padding: 0.65rem 1rem !important;
    font-size: 0.85rem !important;
    transition: background 0.15s ease !important;
}

.stDataFrame tbody tr:hover td {
    background: rgba(0, 208, 156, 0.04) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px !important;
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-sm) !important;
    padding: 4px !important;
    border: 1px solid var(--border-subtle) !important;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    padding: 0.5rem 1.2rem !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    transition: all 0.2s ease !important;
}

.stTabs [aria-selected="true"] {
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
    font-weight: 600 !important;
}

/* ── Expander ────────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

.streamlit-expanderHeader:hover {
    border-color: var(--border-glow) !important;
}

/* ── Plotly Charts ───────────────────────────────────────────────────────── */
.js-plotly-plot .plotly .main-svg {
    border-radius: var(--radius) !important;
}

/* ── Custom Scrollbar ────────────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: var(--bg-primary);
}
::-webkit-scrollbar-thumb {
    background: var(--text-muted);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
}

/* ── Selectbox / Inputs ──────────────────────────────────────────────────── */
[data-baseweb="select"] > div {
    background: var(--bg-card) !important;
    border-color: var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
}

[data-baseweb="select"] > div:focus-within {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #00D09C 0%, #00B386 100%) !important;
    color: #0A0E14 !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.5rem 1.5rem !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 14px rgba(0, 208, 156, 0.25) !important;
    letter-spacing: 0.02em !important;
}

.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0, 208, 156, 0.35) !important;
}

/* ── Section Headers ─────────────────────────────────────────────────────── */
.main h2 {
    color: var(--text-primary) !important;
    font-weight: 700 !important;
    font-size: 1.15rem !important;
    letter-spacing: -0.01em !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    margin-bottom: 1rem !important;
}

.main h3 {
    color: var(--accent) !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

/* ── Status Badges ───────────────────────────────────────────────────────── */
.badge-live {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.badge-success { background: rgba(0, 208, 156, 0.15); color: #00D09C; border: 1px solid rgba(0, 208, 156, 0.3); }
.badge-danger { background: rgba(255, 71, 87, 0.15); color: #FF4757; border: 1px solid rgba(255, 71, 87, 0.3); }
.badge-warning { background: rgba(255, 184, 77, 0.15); color: #FFB84D; border: 1px solid rgba(255, 184, 77, 0.3); }
.badge-info { background: rgba(88, 166, 255, 0.15); color: #58A6FF; border: 1px solid rgba(88, 166, 255, 0.3); }

/* ── Glassmorphism Container ─────────────────────────────────────────────── */
.glass-card {
    background: var(--bg-card);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 1.2rem;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

/* ── Pulse animation for live status ─────────────────────────────────────── */
@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 4px rgba(0, 208, 156, 0.4); }
    50% { box-shadow: 0 0 12px rgba(0, 208, 156, 0.7); }
}

.live-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #00D09C;
    animation: pulse-glow 2s ease-in-out infinite;
    margin-right: 6px;
    vertical-align: middle;
}

/* ── Chain badges ────────────────────────────────────────────────────────── */
.chain-eth { color: #627EEA; }
.chain-base { color: #0052FF; }
.chain-arb { color: #28A0F0; }
.chain-poly { color: #8247E5; }
.chain-bsc { color: #F0B90B; }
</style>
"""


# ── Plotly Chart Theme ───────────────────────────────────────────────────────
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
}
