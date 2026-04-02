import streamlit as st
from streamlit_option_menu import option_menu

st.set_page_config(
    page_title="JP Capital & Trade LLC",
    page_icon="🏢",
    layout="wide",
)

THEME = {
    "PRIMARY": "#334155",
    "PRIMARY_HOVER": "#1e293b",
    "PRIMARY_LIGHT": "#f1f5f9",
    "SECONDARY": "#9eb2cd",
    "BG_MAIN": "#ffffff",
    "BG_SIDEBAR": "#f8fafc",
    "TEXT_PRIMARY": "#000000",
    "TEXT_SECONDARY": "#64748b",
    "BORDER": "#e2e8f0"
}

# Adjusted CSS for a top-navigation layout + MOBILE optimization
st.markdown(f"""
<style>
.main .block-container {{ 
    padding-top: 1rem !important; 
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    background-color: {THEME["BG_MAIN"]};
}}
section.main > div {{
    max-width: 100% !important;
}}
/* Hide standard streamlit headers and toolbars */
header {{ visibility: hidden; }}
div[data-testid="stToolbar"] {{ visibility: hidden; }}

/* Style the horizontal option menu to look like a nav bar */
.nav-link {{
    font-size: 0.9rem !important;
    padding: 8px 12px !important;
}}

/* 📱 MOBILE FIX: Stacks buttons when screen width is less than 768px */
@media (max-width: 768px) {{
    .nav-item {{
        width: 100% !important;
        display: block !important;
        margin-bottom: 4px !important;
    }}
    .nav-link {{
        text-align: left !important;
        padding: 12px !important;
    }}
}}
</style>
""", unsafe_allow_html=True)

# 1. Top Header Branding
col_brand, col_refresh = st.columns([3, 1])
with col_brand:
    st.markdown(
        f'<h2 style="font-size:1.5rem; color:{THEME["PRIMARY"]}; font-weight:bold; margin-bottom:5px;">JP Capital & Trade LLC</h2>',
        unsafe_allow_html=True
    )
with col_refresh:
    # Moved your refresh button to the top right to save space
    st.button("🔄", help="Refresh Application", use_container_width=True)

# 2. Top Navigation Menu (Horizontal by default, stacks on mobile)
active_menu = option_menu(
    menu_title=None,
    options=[
        "Premium Estimator",
        "Trade Reconciler",
        "Watchlist",
        "Stock Scanner",
        "Blue Chip Scanner"
    ],
    icons=["arrow-repeat", "calculator", "star", "cpu", "gem"],
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "0px", "background-color": THEME["BG_SIDEBAR"], "border": f"1px solid {THEME['BORDER']}"},
        "icon": {"font-size": "1rem"},
        "nav-link": {
            "margin": "0px",
            "color": THEME["TEXT_PRIMARY"],
            "border-radius": "4px",
            "text-align": "center",
        },
        "nav-link-selected": {
            "background-color": THEME["PRIMARY"],
            "color": "white",
            "font-weight": "bold"
        }
    }
)

st.divider()

# 3. Dynamic Page Routing
ROUTES = {
    "Trade Reconciler": "reports/TradeReconciler.py",
    "Premium Estimator": "reports/PremiumEstimator.py",
    "Watchlist": "reports/Watchlist.py",
    "Stock Scanner": "reports/stock_scanner.py",
    "Blue Chip Scanner": "reports/index_stock_screener.py"
}

try:
    if active_menu in ROUTES:
        file_path = ROUTES[active_menu]
        
        with open(file_path, "r", encoding="utf-8") as f:
            exec(f.read(), globals())
            
except FileNotFoundError:
    st.error(f"Routing Error: The file for '{active_menu}' was not found.")
except Exception as e:
    st.error(f"System Execution Error: {e}")