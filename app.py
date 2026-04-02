import streamlit as st
from streamlit_option_menu import option_menu

st.set_page_config(
    page_title="JP Capital & Trade LLC",
    page_icon="💼",
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
    "BORDER": "#cbd5e1"  # Slightly darker border to match the background
}

# 🚀 Pushed as high as possible by zeroing out the padding-top!
st.markdown(f"""
<style>
.main .block-container {{ 
    padding-top: 0rem !important; 
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    background-color: {THEME["BG_MAIN"]};
}}
section.main > div {{
    max-width: 100% !important;
}}
/* Hide standard streamlit headers and toolbars */
header {{ visibility: hidden; height: 0px !important; }}
div[data-testid="stToolbar"] {{ visibility: hidden; }}

/* Style the horizontal option menu to look like a nav bar on Desktop */
.nav-link {{
    font-size: 0.85rem !important;
    padding: 6px 10px !important;
}}

/* Eliminate bottom margin from the menu component to pull the page content UP */
div.stElementContainer {{
    margin-bottom: 0px !important;
}}

/* 📱 MOBILE CSS FIX: Forces a clean vertical stack on small screens */
@media (max-width: 768px) {{
    /* Forces the flexbox container to stack vertically instead of wrapping */
    .nav-pills {{
        display: flex !important;
        flex-direction: column !important;
        width: 100% !important;
    }}
    
    .nav-item {{
        width: 100% !important;
        margin-bottom: 4px !important;
    }}
    
    .nav-link {{
        text-align: left !important; /* Left-align for better list readability */
        padding: 10px 15px !important; /* Bigger tap targets for thumbs */
        font-size: 0.8rem !important; /* Slightly smaller text to prevent text wrapping */
        display: flex !important;
        align-items: center !important;
    }}
}}
</style>
""", unsafe_allow_html=True)

# 1. Full-Width Navigation Menu with Darker Background & Heavy Shadow
active_menu = option_menu(
    menu_title=None,
    options=[
        "Premium Estimator",
        "Watchlist",
        "Blue Chip Scanner",
        "Trade Reconciler",
        "Stock Scanner"
    ],
    icons=["arrow-repeat", "star", "gem", "calculator", "cpu"],
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {
            "padding": "4px 8px !important", 
            "background-color": "#e2e8f0 !important",  # 🎨 Darker cool slate-gray background
            "border": f"1px solid {THEME['BORDER']} !important",
            "box-shadow": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05) !important", # 🕶️ Heavier 3D shadow
            "border-radius": "8px !important",
            "margin-top": "0px !important"
        },
        "icon": {"font-size": "0.9rem", "margin-right": "8px"},
        "nav-link": {
            "margin": "2px 4px",
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

# 2. Dynamic Page Routing
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