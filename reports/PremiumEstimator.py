import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ssl
import certifi
from datetime import datetime, timedelta
from scipy.stats import norm
from scipy.optimize import brentq
import io
import requests
import random
from reports.engine import *
from reports.TradeSetup import render_trade_setup
from reports.PortfolioSnapshot import render_portfolio_snapshot

# Minimalist Slate Theme
THEME = {
    "PRIMARY": "#334155",
    "PRIMARY_HOVER": "#1e293b",
    "PRIMARY_LIGHT": "#f1f5f9",
    "SECONDARY": "#9eb2cd",
    "BORDER_ACTIVE": "#334155",
}

# =========================
# 🎨 UI STYLING
# =========================
st.markdown(f"""
<style>

/* =========================
   🎯 YOUR EXISTING STYLING
========================= */
div[data-testid="stBaseButton-segmented_control"] button[aria-checked="true"] {{
    background-color: {THEME["PRIMARY_LIGHT"]} !important;
    color: {THEME["PRIMARY"]} !important;
    border: 2px solid {THEME["PRIMARY"]} !important;
}}

div.stButton > button {{
    background: transparent !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    min-width: 30px !important; 
    width: 100% !important;
    max-width: 42px !important;
    height: 34px !important;
    padding: 0 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    color: {THEME["PRIMARY"]} !important;
}}

div.stButton > button p {{
    font-size: 32px !important;
    margin: 0 !important;
    line-height: 1 !important;
}}

[data-testid="stMetricValue"] {{ 
    color: {THEME["PRIMARY"]} !important; 
    font-weight: 700 !important; 
    font-size: 22px !important; 
}}

div[data-testid="stContainer"], 
div[data-testid="stExpander"], 
div[data-testid="stDataFrame"] {{
    border: 1.5px solid #334155 !important;
    border-radius: 10px !important;
}}

/* Reduce vertical gap between rows */
div[data-testid="stHorizontalBlock"] {{
    margin-bottom: -12px;
}}

/* Tighten metric box */
div[data-testid="metric-container"] {{
    padding: 4px 8px !important;
}}

/* Reduce label spacing */
div[data-testid="stMetricLabel"] {{
    margin-bottom: 2px !important;
    font-size: 12px !important;
}}

/* Reduce value spacing */
div[data-testid="stMetricValue"] {{
    margin-bottom: 2px !important;
}}

/* Reduce delta spacing */
div[data-testid="stMetricDelta"] {{
    margin-top: 0px !important;
    font-size: 12px !important;
}}

/* 🔥 Increase Sidebar Width */
section[data-testid="stSidebar"] {{
    width: 270px !important;
}}

section[data-testid="stSidebar"] > div {{
    width: 270px !important;
}}

</style>
""", unsafe_allow_html=True)

# =========================
# 📥 DATA & MATH UTILS
# =========================
URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=1662549766"
BALANCE_URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=332171000"

@st.cache_data(ttl=300)
def load_data():
    try:
        response = requests.get(URL, verify=certifi.where())
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = df.columns.str.strip()
        stock_col = [c for c in df.columns if c.startswith('Stock')][0]
        df = df.rename(columns={stock_col: 'Stock'})
        return df[df['Status'] == 'Open'].copy()
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def load_balances():
    try:
        response = requests.get(BALANCE_URL, verify=certifi.where())
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = df.columns.str.strip()
        return df
    except: return pd.DataFrame()

# =====================================================
# 🛠️ MOCK TESTING FUNCTION
# =====================================================
def mock_option_chain_test(ticker_symbol):
    """Fetches real option data, or falls back to mock data if Yahoo returns empty."""
    st.write(f"Querying Yahoo Finance for: **{ticker_symbol}**...")
    
    ticker = yf.Ticker(ticker_symbol)
    try:
        # Get live spot price
        spot_price = ticker.history(period="1d")['Close'].iloc[-1]
    except Exception:
        spot_price = 150.00  # Fallback stock price
        
    try:
        expirations = ticker.options
        if not expirations:
            raise ValueError("No expirations returned from Yahoo Finance.")
            
        target_date = expirations[0]
        opt_chain = ticker.option_chain(target_date)
        
        # Check if calls or puts are actually populated
        if opt_chain.calls.empty and opt_chain.puts.empty:
            raise ValueError("Option chain returned empty data frames.")
            
        st.success(f"✅ Success! Received **Live** Option Chain data.")
        return opt_chain.calls, spot_price, "Live"
        
    except Exception as e:
        st.warning(f"⚠️ Live data unavailable or empty (Yahoo delay). Generating **Mock Data** for testing. Reason: {e}")
        
        # Generate fake data mimicking yfinance structure
        strikes = [int(spot_price * 0.95), int(spot_price), int(spot_price * 1.05)]
        mock_calls = pd.DataFrame({
            'contractSymbol': [f"{ticker_symbol}260401C00150000"] * 3,
            'strike': strikes,
            'lastPrice': [10.5, 5.2, 1.1],
            'bid': [10.3, 5.0, 1.0],
            'ask': [10.7, 5.4, 1.2],
            'volume': [150, 500, 200],
            'impliedVolatility': [0.25, 0.22, 0.28]
        })
        return mock_calls, spot_price, "Mock"

# =====================================================
# 🔄 STATE MANAGEMENT
# =====================================================
if 'row_deltas' not in st.session_state: st.session_state.row_deltas = {}
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'active_tab' not in st.session_state: st.session_state.active_tab = "💼 Trade Setup"
if 'pending_df' not in st.session_state: st.session_state.pending_df = pd.DataFrame()

# =========================
# 🧭 HEADER (TABS + LOGO)
# =========================

col1, col2 = st.columns([7, 5])

# 🔥 LEFT: Tabs
with col1:
    st.session_state.active_tab = st.segmented_control(
        "Navigation",
        options=["💼 Trade Setup", "📊 Portfolio Snapshot", "🔬 Mock Tester"],
        selection_mode="single",
        default=st.session_state.active_tab,
        label_visibility="collapsed"
    )

# 🔥 RIGHT: Title
with col2:
    st.markdown(f"""
    <div style="
        text-align:right;
        font-size:22px;
        font-weight:700;
        color:{THEME["PRIMARY"]};
        padding-top:6px;
    ">
        
    </div>
    """, unsafe_allow_html=True)

df_raw = load_data()

# ============================================================
# 📈 Trade Setup
# ============================================================
if st.session_state.active_tab == "💼 Trade Setup":
    render_trade_setup(df_raw)

# ============================================================
# 📈 TAB: Portfolio Snapshot
# ============================================================
elif st.session_state.active_tab == "📊 Portfolio Snapshot":
    render_portfolio_snapshot(df_raw, load_balances)

# ============================================================
# 🔬 TAB: Mock Tester
# ============================================================
elif st.session_state.active_tab == "🔬 Mock Tester":
    st.subheader("Option Chain Data Validation")
    st.markdown("Verify your option chain loading logic during off-hours or Yahoo delay periods.")
    
    # Grid layout for inputs
    t_col1, t_col2 = st.columns([3, 1])
    
    with t_col1:
        test_ticker = st.text_input("Enter Stock Ticker:", value="AAPL").upper().strip()
    with t_col2:
        st.markdown("<br>", unsafe_allow_html=True) 
        test_btn = st.button("🔍", help="Validate")
        
    if test_btn and test_ticker:
        st.write(f"Querying Yahoo Finance for: **{test_ticker}**...")
        ticker = yf.Ticker(test_ticker)
        
        try:
            # 1. Get Live Spot Price
            spot_price = ticker.history(period="1d")['Close'].iloc[-1]
            st.metric(label=f"Current Spot Price ({test_ticker})", value=f"${spot_price:.2f}")
            
            # 2. Find Next 3rd Friday
            expirations = ticker.options
            target_expiry = None
            
            if expirations:
                today = datetime.now()
                for exp in expirations:
                    exp_dt = datetime.strptime(exp, "%Y-%m-%d")
                    # Check if it's a Friday and falls between the 15th and 21st
                    if exp_dt.weekday() == 4 and 15 <= exp_dt.day <= 21 and exp_dt >= today:
                        target_expiry = exp
                        break
                
                # Fallback to absolute first expiration if no 3rd Friday found
                if not target_expiry:
                    target_expiry = expirations[0]
            
            if not target_expiry:
                raise ValueError("No valid expiration dates found.")
                
            st.write(f"Pulling chain for expiration: **{target_expiry}**")
            opt_chain = ticker.option_chain(target_expiry)
            calls = opt_chain.calls
            puts = opt_chain.puts
            
            # 3. Join Calls and Puts together on Strike (keeping Last Trade Dates)
            chain_combined = pd.merge(
                calls[['strike', 'bid', 'ask', 'volume', 'impliedVolatility', 'lastTradeDate']], 
                puts[['strike', 'bid', 'ask', 'volume', 'impliedVolatility', 'lastTradeDate']], 
                on='strike', 
                suffixes=('_Call', '_Put')
            )
            
            # Reorder columns to look like standard broker chains
            chain_combined = chain_combined[[
                'bid_Call', 'ask_Call', 'volume_Call', 'impliedVolatility_Call', 'lastTradeDate_Call',
                'strike',
                'bid_Put', 'ask_Put', 'volume_Put', 'impliedVolatility_Put', 'lastTradeDate_Put'
            ]]
            
            # 4. Filter to rows around the current price
            chain_combined['distance'] = (chain_combined['strike'] - spot_price).abs()
            closest_idx = chain_combined['distance'].idxmin()
            
            start_idx = max(0, closest_idx - 4)
            end_idx = min(len(chain_combined), closest_idx + 5)
            final_chain = chain_combined.iloc[start_idx:end_idx].copy()
            
            # 5. 🟢 Dynamic Status Alert
            # Grab the last trade date of the closest ATM call or put
            atm_trade_time = max(final_chain.loc[closest_idx, 'lastTradeDate_Call'], final_chain.loc[closest_idx, 'lastTradeDate_Put'])
            
            if isinstance(atm_trade_time, str):
                cleaned_time = atm_trade_time.split('+')[0]
                atm_datetime = datetime.strptime(cleaned_time, "%Y-%m-%d %H:%M:%S")
            else:
                atm_datetime = pd.to_datetime(atm_trade_time).replace(tzinfo=None)
                
            # Missing pricing entirely (Red)
            if final_chain.loc[closest_idx, 'bid_Call'] == 0 and final_chain.loc[closest_idx, 'ask_Call'] == 0:
                st.error(f"❌ **Feed Status: Frozen.** No active Bid/Ask pricing detected yet. Yahoo's opening feed is inactive.")
            
            # REFINED: If Bid & Ask are populated, it's a pass! (Green)
            elif final_chain.loc[closest_idx, 'bid_Call'] > 0 and final_chain.loc[closest_idx, 'ask_Call'] > 0:
                st.success(f"✅ **Validation Pass.** Live option chain pricing has successfully loaded!")
                
            # Fallback (Blue)
            else:
                st.info(
                    f"ℹ️ **Feed Status: Static.** Pricing data is flowing, but no new trades have cleared since `{atm_datetime.strftime('%H:%M:%S')} UTC`."
                )
            
            # Drop the tracking columns before rendering to clean up UI
            render_chain = final_chain.drop(columns=['distance', 'lastTradeDate_Call', 'lastTradeDate_Put'])
            
            # 6. Row Highlighting Function (Checks for dead zeros)
            def highlight_atm(row):
                distance = abs(row['strike'] - spot_price)
                
                # Check if Yahoo is returning flat zeros on current pricing
                if row['bid_Call'] == 0 and row['ask_Call'] == 0:
                    return ['background-color: #fecaca; color: #991b1b;'] * len(row) 
                    
                # Highlight exact ATM row darker gray
                if distance == render_chain['strike'].sub(spot_price).abs().min():
                    return ['background-color: #cbd5e1; font-weight: bold'] * len(row)
                
                # Highlight near ATM rows lighter gray
                elif distance <= (spot_price * 0.05): 
                    return ['background-color: #f1f5f9'] * len(row)
                return [''] * len(row)

            # Apply styles and format numbers cleanly
            styled_df = render_chain.style.apply(highlight_atm, axis=1).format({
                'bid_Call': '${:.2f}', 'ask_Call': '${:.2f}',
                'bid_Put': '${:.2f}', 'ask_Put': '${:.2f}',
                'impliedVolatility_Call': '{:.2%}', 'impliedVolatility_Put': '{:.2%}'
            })
            
            st.dataframe(styled_df, use_container_width=True)
            
        except Exception as e:
            st.error(f"Error loading option chain: {e}")