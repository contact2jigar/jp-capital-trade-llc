##https://jp-capital-trade-llc.streamlit.app/

import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="JP Capital & Trade LLC",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Track Active Page in Session State
if "active_menu" not in st.session_state:
    st.session_state.active_menu = "Premium Estimator"

# 3. Handle Sidebar Clicks via Query Params
params = st.query_params
if "nav" in params:
    st.session_state.active_menu = params["nav"]

# 4. Sidebar Navigation with Clean CSS
with st.sidebar:
    st.markdown("### JP Capital & Trade LLC")
    st.write("") # Spacer
    
    # Load Google Material Symbols stylesheet and style the custom links
    st.markdown("""
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />
    <style>
    .sidebar-nav-item {
        display: flex;
        align-items: center;
        padding: 10px 15px;
        margin-bottom: 5px;
        color: #1f1f1f !important;
        text-decoration: none !important;
        border-radius: 6px;
        font-size: 0.95rem;
        font-weight: 500;
        transition: background-color 0.2s;
    }
    .sidebar-nav-item:hover {
        background-color: #e2e8f0;
    }
    .sidebar-nav-active {
        background-color: #4c2c17 !important; /* Rich Dark Brown */
        color: #ffffff !important; /* Clean white text */
    }
    .sidebar-nav-active .material-symbols-outlined {
        color: #ffffff !important; /* Keep icon white when active */
    }
    .material-symbols-outlined {
        margin-right: 12px;
        font-size: 20px;
        color: #444746; /* Subtle dark gray for inactive icons */
    }
    </style>
    """, unsafe_allow_html=True)

    # Dictionary of display names and their mapped Material Symbol names
    pages = {
        "Premium Estimator": "trending_up",     # Chart going up
        "Watchlist": "star",                    # Clean star
        "Blue Chip Scanner": "diamond",          # Diamond shape
        "Trade Reconciler": "calculate",         # Calculator
        "Stock Scanner": "monitoring"            # Analytics dashboard
    }

    # Render each link dynamically
    for page_name, icon_name in pages.items():
        is_active = "sidebar-nav-active" if st.session_state.active_menu == page_name else ""
        
        # We inject the material-symbols HTML tag here instead of an emoji
        st.markdown(
            f'''
            <a href="?nav={page_name}" target="_self" class="sidebar-nav-item {is_active}">
                <span class="material-symbols-outlined">{icon_name}</span>
                {page_name}
            </a>
            ''', 
            unsafe_allow_html=True
        )

# 5. Dynamic Page Routing
ROUTES = {
    "Premium Estimator": "reports/PremiumEstimator.py",
    "Watchlist": "reports/WatchList.py",
    "Blue Chip Scanner": "reports/BlueChipScanner.py",
    "Trade Reconciler": "reports/TradeReconciler.py",
    "Stock Scanner": "reports/stock_scanner.py"
}

current_page = st.session_state.active_menu

try:
    if current_page in ROUTES:
        file_path = ROUTES[current_page]
        
        with open(file_path, "r", encoding="utf-8") as f:
            exec(f.read(), globals())
            
except FileNotFoundError:
    st.error(f"Routing Error: The file at '{ROUTES[current_page]}' was not found.")
except Exception as e:
    st.error(f"System Execution Error: {e}")