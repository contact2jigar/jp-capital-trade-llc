import streamlit as st
from streamlit_option_menu import option_menu

st.set_page_config(
    page_title="JP Capital",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
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

st.markdown(f"""
<style>
.main .block-container {{ 
    padding-top: 1rem !important; 
    padding-left: 0.5rem !important;
    padding-right: 1rem !important;
    background-color: {THEME["BG_MAIN"]};
}}
section.main > div {{
    max-width: 100% !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}}
[data-testid="stAppViewContainer"] > .main,
[data-testid="stAppViewContainer"] {{
    max-width: 100% !important;
}}
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {{
    width: 100% !important;
}}
[data-testid="column"] {{
    width: auto !important;
    flex: 1 1 auto !important;
}}
section[data-testid="stSidebar"] {{
    background-color: {THEME["BG_SIDEBAR"]} !important;
    border-right: 1px solid {THEME["BORDER"]} !important;
    width: 270px !important;
    min-width: 270px !important;
    max-width: 270px !important;
}}
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"] > div:first-child button {{
    display: none !important;
}}
button[kind="header"] {{ display: none !important; }}
header {{ visibility: hidden; }}
div[data-testid="stToolbar"] {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(
        f'<h2 style="font-size:1.2rem; color:{THEME["PRIMARY"]}; font-weight:bold; margin-bottom:15px;">JP Capital</h2>',
        unsafe_allow_html=True
    )

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
        styles={
            "container": {"padding": "0px", "background-color": THEME["BG_SIDEBAR"]},
            "icon": {"font-size": "1.1rem"},
            "nav-link": {
                "margin": "0px",
                "color": THEME["TEXT_PRIMARY"],
                "padding": "10px",
                "border-radius": "8px",
                "white-space": "nowrap"
            },
            "nav-link-selected": {
                "background-color": THEME["PRIMARY"],
                "color": "white",
                "font-weight": "bold"
            }
        }
    )

    st.divider()
    st.caption("Market Data: Mar-23-2026")
    st.button("🔄 Refresh Application", use_container_width=True)

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