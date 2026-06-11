"""
dashboard/styles.py — Premium dark-mode CSS for Shamrock Trading Dashboard.

Fortune 50-grade glassmorphism, animated gradients, glow effects,
and custom component styling. Every pixel is intentional.
"""

PREMIUM_CSS = """
<style>
/* ── Import Google Font ──────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ── Root Variables ──────────────────────────────────────────────────────── */
:root {
    --bg-primary: #06090F;
    --bg-secondary: #0D1117;
    --bg-card: rgba(13, 17, 23, 0.75);
    --bg-card-hover: rgba(13, 17, 23, 0.92);
    --bg-elevated: rgba(22, 27, 34, 0.9);
    --border-subtle: rgba(0, 208, 156, 0.08);
    --border-glow: rgba(0, 208, 156, 0.25);
    --border-default: rgba(48, 54, 61, 0.6);
    --accent: #00D09C;
    --accent-bright: #00FFB8;
    --accent-dim: rgba(0, 208, 156, 0.12);
    --accent-glow: rgba(0, 208, 156, 0.35);
    --text-primary: #E6EDF3;
    --text-secondary: #8B949E;
    --text-muted: #484F58;
    --success: #00D09C;
    --danger: #FF4757;
    --warning: #FFB84D;
    --info: #58A6FF;
    --purple: #A371F7;
    --radius: 16px;
    --radius-sm: 10px;
    --radius-xs: 6px;
}

/* ── Global ──────────────────────────────────────────────────────────────── */
* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.main .block-container {
    padding-top: 1rem !important;
    padding-bottom: 2rem !important;
    max-width: 1440px !important;
}

/* Hide Streamlit branding */
#MainMenu, footer, header {
    visibility: hidden !important;
}

.stApp > header {
    background-color: transparent !important;
}

/* App background with subtle gradient */
.stApp {
    background: linear-gradient(180deg, #06090F 0%, #0A0E14 30%, #080C12 100%) !important;
}

/* ── Glass Card (THE core component) ─────────────────────────────────────── */
.glass-card {
    background: var(--bg-card) !important;
    backdrop-filter: blur(24px) !important;
    -webkit-backdrop-filter: blur(24px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem 1.5rem !important;
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow:
        0 4px 24px rgba(0, 0, 0, 0.4),
        inset 0 1px 0 rgba(255, 255, 255, 0.03) !important;
}

.glass-card:hover {
    border-color: var(--border-glow) !important;
    box-shadow:
        0 8px 40px rgba(0, 208, 156, 0.08),
        inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    transform: translateY(-1px) !important;
}

/* ── Hero P&L Display ────────────────────────────────────────────────────── */
.pnl-hero {
    text-align: center;
    padding: 2rem 1.5rem;
    background: linear-gradient(135deg, rgba(13,17,23,0.95), rgba(6,9,15,0.98));
    border: 1px solid var(--border-subtle);
    border-radius: 20px;
    position: relative;
    overflow: hidden;
}

.pnl-hero::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
}

.pnl-hero .pnl-label {
    color: var(--text-secondary);
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 0.5rem;
}

.pnl-hero .pnl-value {
    font-family: 'JetBrains Mono', 'Inter', monospace !important;
    font-size: 3rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.1;
    margin-bottom: 0.25rem;
}

.pnl-hero .pnl-value.positive {
    background: linear-gradient(135deg, #00D09C, #00FFB8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 40px rgba(0, 208, 156, 0.3);
}

.pnl-hero .pnl-value.negative {
    background: linear-gradient(135deg, #FF4757, #FF6B7A);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.pnl-hero .pnl-value.zero {
    color: var(--text-secondary);
}

.pnl-hero .pnl-subtitle {
    color: var(--text-muted);
    font-size: 0.78rem;
    font-weight: 500;
}

/* ── Stat Card ───────────────────────────────────────────────────────────── */
.stat-card {
    background: var(--bg-card);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 1.1rem 1.3rem;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 2px 16px rgba(0, 0, 0, 0.3);
    position: relative;
    overflow: hidden;
}

.stat-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--border-glow), transparent);
    opacity: 0;
    transition: opacity 0.3s ease;
}

.stat-card:hover {
    border-color: var(--border-glow);
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0, 208, 156, 0.1);
}

.stat-card:hover::after {
    opacity: 1;
}

.stat-card .stat-icon {
    font-size: 1.4rem;
    margin-bottom: 0.6rem;
}

.stat-card .stat-label {
    color: var(--text-secondary);
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.stat-card .stat-value {
    color: var(--text-primary);
    font-family: 'JetBrains Mono', 'Inter', monospace !important;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin: 0.15rem 0;
}

.stat-card .stat-delta {
    font-size: 0.75rem;
    font-weight: 600;
}

.stat-card .stat-delta.positive { color: var(--success); }
.stat-card .stat-delta.negative { color: var(--danger); }
.stat-card .stat-delta.neutral { color: var(--text-secondary); }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A0E14 0%, #06090F 100%) !important;
    border-right: 1px solid rgba(0, 208, 156, 0.06) !important;
}

[data-testid="stSidebar"] .stMarkdown h1 {
    background: linear-gradient(135deg, #00D09C, #00E6AC, #00FFB8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 900 !important;
    font-size: 1.5rem !important;
    letter-spacing: 0.05em;
}

/* ── Metric Cards Override ───────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    padding: 1.1rem 1.3rem !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.02) !important;
}

[data-testid="stMetric"]:hover {
    border-color: var(--border-glow) !important;
    box-shadow: 0 8px 32px rgba(0, 208, 156, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
    transform: translateY(-2px) !important;
}

[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}

[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-family: 'JetBrains Mono', 'Inter', monospace !important;
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}

[data-testid="stMetricDelta"] {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #00D09C, #00B884) !important;
    color: #06090F !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.55rem 1.3rem !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 15px rgba(0, 208, 156, 0.3) !important;
}

.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 24px rgba(0, 208, 156, 0.45) !important;
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
    font-size: 0.82rem !important;
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

/* ── Select boxes & Sliders ──────────────────────────────────────────────── */
[data-baseweb="select"] {
    border-radius: var(--radius-sm) !important;
}

/* ── Dividers ────────────────────────────────────────────────────────────── */
hr {
    border-color: rgba(48, 54, 61, 0.3) !important;
    margin: 1.5rem 0 !important;
}

/* ── Live Dot (Pulsing) ──────────────────────────────────────────────────── */
.live-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #00D09C;
    box-shadow: 0 0 8px rgba(0, 208, 156, 0.6);
    animation: live-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes live-pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(0, 208, 156, 0.6); }
    50% { opacity: 0.5; box-shadow: 0 0 16px rgba(0, 208, 156, 0.3); }
}

/* ── Page Header ─────────────────────────────────────────────────────────── */
.page-header {
    position: relative;
    padding: 1.2rem 0 1rem 0;
    margin-bottom: 1.5rem;
}

.page-header::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, var(--accent), transparent 70%);
    opacity: 0.4;
}

.page-header h1 {
    margin: 0 !important;
    padding: 0 !important;
    font-size: 1.5rem !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #00D09C, #00E6AC, #00FFB8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
}

.page-header .subtitle {
    color: var(--text-secondary);
    font-size: 0.8rem;
    margin-top: 2px;
}

/* ── Chain Pills ─────────────────────────────────────────────────────────── */
.chain-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}

.chain-eth  { background: rgba(98,126,234,0.12); color: #627EEA; border: 1px solid rgba(98,126,234,0.25); }
.chain-base { background: rgba(0,82,255,0.12);   color: #0052FF; border: 1px solid rgba(0,82,255,0.25); }
.chain-arb  { background: rgba(40,160,240,0.12); color: #28A0F0; border: 1px solid rgba(40,160,240,0.25); }
.chain-poly { background: rgba(130,71,229,0.12); color: #8247E5; border: 1px solid rgba(130,71,229,0.25); }
.chain-bsc  { background: rgba(240,185,11,0.12); color: #F0B90B; border: 1px solid rgba(240,185,11,0.25); }
.chain-sol  { background: rgba(153,69,255,0.12); color: #9945FF; border: 1px solid rgba(153,69,255,0.25); }
.chain-avax { background: rgba(232,65,66,0.12);  color: #E84142; border: 1px solid rgba(232,65,66,0.25); }

/* ── Score Badges ────────────────────────────────────────────────────────── */
.score-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700;
    font-size: 0.82rem;
    padding: 3px 10px;
    border-radius: 8px;
    letter-spacing: -0.01em;
}

.score-high  { background: rgba(0,208,156,0.12); color: #00D09C; border: 1px solid rgba(0,208,156,0.25); }
.score-mid   { background: rgba(255,184,77,0.12); color: #FFB84D; border: 1px solid rgba(255,184,77,0.25); }
.score-low   { background: rgba(255,71,87,0.12); color: #FF4757; border: 1px solid rgba(255,71,87,0.25); }

/* ── Status Badges ───────────────────────────────────────────────────────── */
.status-live {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(0, 208, 156, 0.1);
    border: 1px solid rgba(0, 208, 156, 0.25);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #00D09C;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.status-paper {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 184, 77, 0.1);
    border: 1px solid rgba(255, 184, 77, 0.25);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #FFB84D;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* ── Gem Row Card ────────────────────────────────────────────────────────── */
.gem-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    margin-bottom: 6px;
    transition: all 0.2s ease;
}

.gem-row:hover {
    border-color: var(--border-glow);
    background: var(--bg-card-hover);
}

/* ── API Health Card ─────────────────────────────────────────────────────── */
.api-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 14px 16px;
    margin-bottom: 8px;
    transition: all 0.2s ease;
}

.api-card:hover {
    border-color: var(--border-default);
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(0, 208, 156, 0.2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(0, 208, 156, 0.4); }

/* ── Code blocks ─────────────────────────────────────────────────────────── */
.stCode {
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
}

/* ── LEGIBILITY FIXES — Streamlit dark-mode overrides ───────────────────── */

/* Force all text to be bright on our dark background */
.stApp, .stApp p, .stApp span, .stApp li, .stApp label,
.stApp .stMarkdown, .stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p {
    color: var(--text-primary) !important;
}

/* Markdown headings — bright gradient or solid white */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
    color: #E6EDF3 !important;
    font-weight: 700 !important;
}

/* Override Streamlit's dark theme muted small text */
.stApp small, .stApp .caption, .stApp figcaption {
    color: var(--text-secondary) !important;
}

/* ── DataFrames: header + cells must be high-contrast ───────────────────── */
[data-testid="stDataFrame"] th,
[data-testid="stDataFrame"] [role="columnheader"] {
    background: rgba(13, 17, 23, 0.95) !important;
    color: #E6EDF3 !important;
    font-weight: 700 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    border-bottom: 2px solid rgba(0, 208, 156, 0.15) !important;
}

[data-testid="stDataFrame"] td,
[data-testid="stDataFrame"] [role="gridcell"] {
    color: #C9D1D9 !important;
    font-family: 'JetBrains Mono', 'Inter', monospace !important;
    font-size: 0.8rem !important;
    background: rgba(6, 9, 15, 0.6) !important;
    border-bottom: 1px solid rgba(48, 54, 61, 0.3) !important;
}

[data-testid="stDataFrame"] [role="row"]:hover td,
[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
    background: rgba(0, 208, 156, 0.04) !important;
}

/* Glide (Streamlit data grid) overrides */
.dvn-scroller {
    background: rgba(6, 9, 15, 0.8) !important;
}

/* ── Selectbox, multiselect, slider labels ──────────────────────────────── */
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stSlider"] label,
[data-testid="stToggle"] label,
[data-testid="stNumberInput"] label,
[data-testid="stTextInput"] label,
.stSelectbox label,
.stSlider label {
    color: var(--text-secondary) !important;
    font-weight: 600 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* Selectbox dropdown text */
[data-baseweb="select"] [data-testid="stMarkdownContainer"],
[data-baseweb="select"] span,
[data-baseweb="select"] div {
    color: #E6EDF3 !important;
}

[data-baseweb="select"] [role="option"] {
    color: #E6EDF3 !important;
    background: #0D1117 !important;
}

[data-baseweb="select"] [role="option"]:hover {
    background: rgba(0, 208, 156, 0.08) !important;
}

[data-baseweb="select"] [data-baseweb="popover"] {
    background: #0D1117 !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
}

/* ── Slider thumb and track ─────────────────────────────────────────────── */
[data-testid="stSlider"] [role="slider"] {
    background: var(--accent) !important;
}

[data-testid="stSlider"] [data-testid="stThumbValue"] {
    color: #E6EDF3 !important;
    font-weight: 600 !important;
}

/* ── Expanders ─ ensure text inside is bright ───────────────────────────── */
.streamlit-expanderContent p,
.streamlit-expanderContent span,
.streamlit-expanderContent div,
[data-testid="stExpander"] p,
[data-testid="stExpander"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
    color: #C9D1D9 !important;
}

[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderToggleDetails"],
.streamlit-expanderHeader {
    color: #E6EDF3 !important;
    font-weight: 600 !important;
}

/* ── Toggle switch labels ───────────────────────────────────────────────── */
[data-testid="stToggle"] span {
    color: var(--text-primary) !important;
}

/* ── Tooltips and help text ──────────────────────────────────────────────── */
[data-testid="stTooltipIcon"] {
    color: var(--text-muted) !important;
}

/* ── Select slider formatted values ─────────────────────────────────────── */
[data-testid="stTickBarMin"],
[data-testid="stTickBarMax"] {
    color: var(--text-secondary) !important;
}

/* ── Alert/info/warning boxes ────────────────────────────────────────────── */
.stAlert p, .stAlert span {
    color: #E6EDF3 !important;
}

/* ── Plotly modebar — hide extra buttons ─────────────────────────────────── */
.modebar { display: none !important; }

/* ── War Room / Trading Terminal Components ─────────────────────────────── */

/* Pulse animation for live indicators */
@keyframes pulse-live {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
}

.pulse-dot {
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block;
    animation: pulse-live 1.8s ease-in-out infinite;
}

/* Heat bar for portfolio health visualization */
.heat-bar {
    height: 4px;
    border-radius: 2px;
    overflow: hidden;
    background: rgba(48,54,61,0.5);
}

.heat-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.6s cubic-bezier(.4,0,.2,1);
}

/* Signal strength indicator (1-5 bars) */
.signal-bars {
    display: inline-flex;
    align-items: flex-end;
    gap: 2px;
    height: 14px;
}

.signal-bar {
    width: 3px;
    border-radius: 1px;
    transition: height 0.3s ease, background 0.3s ease;
}

/* Quick action buttons row */
.quick-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 8px;
}

.quick-action-btn {
    background: rgba(0,208,156,0.06);
    border: 1px solid rgba(0,208,156,0.15);
    border-radius: 8px;
    padding: 6px 12px;
    color: #00D09C;
    font-size: 0.68rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.quick-action-btn:hover {
    background: rgba(0,208,156,0.12);
    border-color: rgba(0,208,156,0.35);
    transform: translateY(-1px);
}

.quick-action-btn.danger {
    background: rgba(255,71,87,0.06);
    border-color: rgba(255,71,87,0.15);
    color: #FF4757;
}

.quick-action-btn.danger:hover {
    background: rgba(255,71,87,0.12);
    border-color: rgba(255,71,87,0.35);
}

/* Nuclear mode glow */
@keyframes nuclear-glow {
    0%, 100% { box-shadow: 0 0 8px rgba(255,215,0,0.15); }
    50% { box-shadow: 0 0 24px rgba(255,215,0,0.3); }
}

.nuclear-active {
    animation: nuclear-glow 2s ease-in-out infinite;
    border-color: rgba(255,215,0,0.4) !important;
}

/* Section divider label */
.section-label {
    color: #30363D;
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin: 18px 0 10px;
    padding-left: 2px;
}

/* Compact info pill */
.info-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(48,54,61,0.5);
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.65rem;
    font-weight: 600;
    color: #8B949E;
}

/* ── Section Headers (Zone Dividers) ─────────────────────────────────────── */
.zone-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 0 8px 0;
    margin: 28px 0 16px 0;
    position: relative;
}

.zone-header::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, var(--accent), rgba(48,54,61,0.3) 60%, transparent);
    opacity: 0.5;
}

.zone-header .zone-icon {
    font-size: 1.15rem;
    line-height: 1;
}

.zone-header .zone-title {
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    background: linear-gradient(135deg, #E6EDF3 30%, #8B949E);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.zone-header .zone-subtitle {
    color: var(--text-muted);
    font-size: 0.62rem;
    font-weight: 500;
    margin-left: auto;
}

/* ── Zone Containers (Visual Grouping) ───────────────────────────────────── */
.zone-container {
    background: rgba(255, 255, 255, 0.008);
    border: 1px solid rgba(48, 54, 61, 0.15);
    border-radius: 20px;
    padding: 4px 16px 20px 16px;
    margin-bottom: 24px;
    position: relative;
}

.zone-container.zone-trading {
    border-color: rgba(0, 208, 156, 0.08);
}

.zone-container.zone-intelligence {
    border-color: rgba(88, 166, 255, 0.08);
}

.zone-container.zone-system {
    border-color: rgba(255, 184, 77, 0.08);
}

/* ── Wallet Card (Alpha Wallet Management) ───────────────────────────────── */
.wallet-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 14px;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.wallet-card:hover {
    border-color: var(--border-glow);
    background: var(--bg-card-hover);
    transform: translateY(-1px);
}

.wallet-card .wallet-avatar {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    background: var(--accent-dim);
    border: 1px solid rgba(0, 208, 156, 0.2);
    flex-shrink: 0;
}

.wallet-card .wallet-info {
    flex: 1;
    min-width: 0;
}

.wallet-card .wallet-label {
    color: var(--text-primary);
    font-size: 0.82rem;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.wallet-card .wallet-address {
    color: var(--text-muted);
    font-size: 0.65rem;
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.wallet-card .wallet-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    flex-shrink: 0;
}

.wallet-badge.badge-system {
    background: rgba(88, 166, 255, 0.1);
    color: #58A6FF;
    border: 1px solid rgba(88, 166, 255, 0.2);
}

.wallet-badge.badge-custom {
    background: rgba(0, 208, 156, 0.1);
    color: #00D09C;
    border: 1px solid rgba(0, 208, 156, 0.2);
}

.wallet-badge.badge-vip {
    background: rgba(255, 215, 0, 0.1);
    color: #FFD700;
    border: 1px solid rgba(255, 215, 0, 0.2);
}

/* ── Nav Group Divider ───────────────────────────────────────────────────── */
.nav-group-divider {
    width: 1px;
    height: 20px;
    background: rgba(48, 54, 61, 0.5);
    margin: 0 6px;
    flex-shrink: 0;
}

.nav-group-label {
    color: #30363D;
    font-size: 0.5rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    white-space: nowrap;
    flex-shrink: 0;
    padding: 0 2px;
}

/* ── Fade-In Animation ───────────────────────────────────────────────────── */
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.fade-in {
    animation: fadeInUp 0.4s ease-out forwards;
}

.fade-in-delay-1 { animation-delay: 0.05s; opacity: 0; }
.fade-in-delay-2 { animation-delay: 0.10s; opacity: 0; }
.fade-in-delay-3 { animation-delay: 0.15s; opacity: 0; }
.fade-in-delay-4 { animation-delay: 0.20s; opacity: 0; }

/* ── Guardian Card Styles ────────────────────────────────────────────────── */
.guardian-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 14px 16px;
    transition: all 0.25s ease;
}

.guardian-card.healthy {
    border-color: rgba(0, 208, 156, 0.12);
}

.guardian-card.preservation {
    border-color: rgba(255, 71, 87, 0.2);
    background: rgba(255, 71, 87, 0.03);
}

.guardian-card .guardian-label {
    color: var(--text-muted);
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}

.guardian-card .guardian-value {
    color: var(--text-primary);
    font-size: 1.15rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}

.guardian-card .guardian-sub {
    color: var(--text-muted);
    font-size: 0.62rem;
    margin-top: 2px;
}

/* ── Responsive fixes for mobile ─────────────────────────────────────────── */
@media (max-width: 768px) {
    .stat-card .stat-value { font-size: 1.2rem; }
    .pnl-hero .pnl-value { font-size: 2rem; }
    .glass-card { padding: 1rem !important; }
    .gem-row { flex-direction: column; gap: 8px; }
    .zone-container { padding: 4px 10px 16px 10px; }
    .wallet-card { flex-direction: column; text-align: center; }
    .zone-header .zone-subtitle { display: none; }
}

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
        gridcolor="rgba(255,255,255,0.03)",
        zerolinecolor="rgba(255,255,255,0.05)",
        tickfont=dict(size=11, color="#8B949E"),
    ),
    yaxis=dict(
        gridcolor="rgba(255,255,255,0.03)",
        zerolinecolor="rgba(255,255,255,0.05)",
        tickfont=dict(size=11, color="#8B949E"),
    ),
    showlegend=True,
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        font=dict(size=11, color="#8B949E"),
    ),
    hoverlabel=dict(
        bgcolor="#161B22",
        bordercolor="#00D09C",
        font=dict(family="Inter, sans-serif", size=12, color="#E6EDF3"),
    ),
)

# Horizontal legend variant
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
ACCENT_DIM = "rgba(0, 208, 156, 0.12)"
DANGER = "#FF4757"
WARNING = "#FFB84D"
INFO = "#58A6FF"
PURPLE = "#A371F7"

CHAIN_COLORS = {
    "ethereum": "#627EEA",
    "base": "#0052FF",
    "arbitrum": "#28A0F0",
    "polygon": "#8247E5",
    "bsc": "#F0B90B",
    "solana": "#9945FF",
    "avalanche": "#E84142",
}

CHAIN_EMOJI = {
    "ethereum": "⟠",
    "base": "🔵",
    "arbitrum": "🔷",
    "polygon": "🟣",
    "bsc": "🟡",
    "solana": "◎",
    "avalanche": "🔺",
}
