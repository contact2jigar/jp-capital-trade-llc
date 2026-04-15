import streamlit as st
import yfinance as yf
import pandas as pd
import math
from datetime import datetime, timedelta
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

# =========================
# 🎨 COLOR CONFIG
# =========================
COLOR_BTN = "#1e3a8a"
COLOR_BTN_HOVER = "#1d4ed8"
COLOR_TAG_BG = "#e0ecff"
COLOR_TAG_TEXT = "#1e40af"
COLOR_TAB_BG = "#f1f5f9"
COLOR_TAB_BORDER = "#e2e8f0"
COLOR_TAB_BTN = "#ffffff"
COLOR_TAB_BTN_BORDER = "#d1d5db"
COLOR_TAB_HOVER = "#e5e7eb"
COLOR_TAB_ACTIVE = "#2563eb"
COLOR_HEADER_BG = "#0f172a"
COLOR_HEADER_TEXT = "#f6f1f1"
COLOR_WHITE = "#ffffff" 
COLOR_GROUP_LIGHT = "#ffffff"
COLOR_GROUP_DARK = "#f1f5f9"
COLOR_POSITIVE = "#c5e2cf"
COLOR_NEGATIVE = "#e4cccc"

st.set_page_config(page_title="JP Capital Scanner", layout="wide")

st.markdown(f"""
<style>
div.stButton > button {{
    background-color: {COLOR_BTN};
    color: white;
    font-weight: 600;
    border-radius: 6px;
    border: none;
}}
div.stButton > button:hover {{
    background-color: {COLOR_BTN_HOVER};
}}
[data-baseweb="tag"] {{
    background-color: {COLOR_TAG_BG} !important;
    color: {COLOR_TAG_TEXT} !important;
    font-weight: 600;
    border-radius: 6px;
}}
div[data-baseweb="tab-list"] {{
    background-color: {COLOR_TAB_BG};
    padding: 8px;
    border-radius: 8px;
    border: 1px solid {COLOR_TAB_BORDER};
}}
button[data-baseweb="tab"] {{
    background-color: {COLOR_TAB_BTN};
    border: 1px solid {COLOR_TAB_BTN_BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    margin-right: 6px;
    font-weight: 600;
    box-shadow: 0 3px 0 #cbd5e1;
}}
button[data-baseweb="tab"]:hover {{
    background-color: {COLOR_TAB_HOVER};
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    background-color: {COLOR_TAB_ACTIVE};
    color: white;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.25);
}}
thead th {{
    position: sticky !important;
    top: 0;
    background-color: {COLOR_HEADER_BG} !important;
    color: {COLOR_HEADER_TEXT} !important;
    z-index: 2;
}}
</style>
""", unsafe_allow_html=True)

SP20_LIST = "NVDA,AAPL,GOOGL,MSFT,AMZN,META,AVGO,TSLA,BRK-B,WMT,LLY,JPM,XOM,V,JNJ,MU,COST,ORCL,MA,NFLX"
NASDAQ20_LIST = "NVDA,AAPL,MSFT,AMZN,META,AVGO,TSLA,COST,AMD,NFLX,INTC,ADBE,CSCO,AMAT,QCOM,TXN,INTU,MU,PANW,AMGN"
YAHOO_ACTIVE = "NVDA,TSLA,AAPL,AMD,PLTR,AMZN,INTC,MARA,SOFI,MSFT,META,NIO,F,PFE,GOOGL,BAC,AAL,VALE,CCL,COIN"

# =========================
# 📈 FINANCIAL MATH (Broker Calibrated)
# =========================
def bs_price(S, K, T, r, sigma, mode='put'):
    if T <= 0: return max(0, K - S) if mode == 'put' else max(0, S - K)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if mode == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def find_implied_vol(market_price, S, K, T, r, mode='put'):
    if market_price <= 0.005 or T <= 0: return 0.01
    intrinsic = max(0, K - S) if mode == 'put' else max(0, S - K)
    if market_price <= intrinsic + 0.01: return 0.01
    try:
        # Calibrated search range for short-dated options
        return brentq(lambda sig: bs_price(S, K, T, r, sig, mode) - market_price, 0.0001, 4.0, xtol=1e-5)
    except:
        return 0.01

def get_delta(S, K, T, r, sigma, mode='put'):
    if T <= 0 or sigma <= 0: return -1.0 if (mode == 'put' and S < K) else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) if mode == 'call' else norm.cdf(d1) - 1

def fetch_earnings(ticker_obj):
    try:
        ed = ticker_obj.earnings_dates
        if ed is not None and not ed.empty: return ed.index[0].strftime('%m/%d')
    except: pass
    return "N/A"

def get_next_fridays(n=4):
    fridays = []
    today = datetime.now()
    days_until_friday = (4 - today.weekday() + 7) % 7
    if days_until_friday == 0: days_until_friday = 7
    first_friday = today + timedelta(days=days_until_friday)
    for i in range(n):
        fridays.append((first_friday + timedelta(weeks=i)).strftime('%Y-%m-%d'))
    return fridays

# =========================
# 💾 SESSION STATE
# =========================
if "ss_watch" not in st.session_state:
    st.session_state["ss_watch"] = "TSLA,NVDA,AMD,PLTR,SOFI"
for k in ["ss_sp20", "ss_nasdaq", "ss_active", "ss_final", "ss_ticker_list"]:
    if k not in st.session_state: st.session_state[k] = ""

# =========================
# 🏗️ TABS
# =========================
tab1, tab2 = st.tabs(["🏗️ SETUP UNIVERSE", "📊 RUN SCANNER"])

with tab1:
    c1, c2 = st.columns([2, 8]); c1.markdown('**⭐ Watch List**')
    st.session_state.ss_watch = c2.text_area("W", value=st.session_state.ss_watch, label_visibility="collapsed")
    
    c3, c4 = st.columns([2, 8])
    if c3.button("Get S&P 20 🚀", use_container_width=True): 
        st.session_state.ss_sp20 = SP20_LIST
        st.rerun()
    st.session_state.ss_sp20 = c4.text_area("S", value=st.session_state.ss_sp20, label_visibility="collapsed")

    c5, c6 = st.columns([2, 8])
    if c5.button("Get Nasdaq ⚡", use_container_width=True): 
        st.session_state.ss_nasdaq = NASDAQ20_LIST
        st.rerun()
    st.session_state.ss_nasdaq = c6.text_area("N", value=st.session_state.ss_nasdaq, label_visibility="collapsed")

    c7, c8 = st.columns([2, 8])
    if c7.button("Get Yahoo 🔥", use_container_width=True): 
        st.session_state.ss_active = YAHOO_ACTIVE
        st.rerun()
    st.session_state.ss_active = c8.text_area("Y", value=st.session_state.ss_active, label_visibility="collapsed")

    if st.button("✨ Merge & De-duplicate All Lists", use_container_width=True):
        raw = f"{st.session_state.ss_watch},{st.session_state.ss_sp20},{st.session_state.ss_nasdaq},{st.session_state.ss_active}"
        st.session_state.ss_final = ",".join(sorted(list(set([t.strip().upper() for t in raw.split(",") if t.strip()]))))
        st.rerun()

    st.session_state.ss_final = st.text_area("Final Trading Universe", value=st.session_state.ss_final, height=80)
    if st.button("✅ LOCK UNIVERSE & READY", type="primary", use_container_width=True):
        st.session_state.ss_ticker_list = [t.strip().upper() for t in st.session_state.ss_final.split(",") if t.strip()]
        st.success("Universe Locked.")

with tab2:
    if not st.session_state.ss_ticker_list:
        st.warning("Please lock your ticker list in the Setup tab."); st.stop()

    with st.expander("🛠️ Scanner Filters", expanded=True):
        f1, f2, f3 = st.columns(3)
        mode_opt = f1.selectbox("Type", ["CSP (Put)", "CC (Call)"])
        min_d, max_d = f2.slider("Delta Range", 0.05, 0.60, (0.15, 0.45))
        selected_exp = f3.selectbox("Expiry", get_next_fridays(4))
        subset = st.multiselect("Scan Subset", st.session_state.ss_ticker_list, default=st.session_state.ss_ticker_list)

    if st.button("🚀 EXECUTE SCAN", type="primary", use_container_width=True):
        results = []; pb = st.progress(0)
        for idx, tkr in enumerate(subset):
            try:
                stock = yf.Ticker(tkr); px = stock.fast_info['lastPrice']
                hist = stock.history(period="2d"); yesterday = hist['Close'].iloc[-2]
                pct_change = ((px - yesterday) / yesterday) * 100
                earn_dt = fetch_earnings(stock)
                
                if selected_exp in stock.options:
                    # CALC TIME REMAINING IN MINUTES (Fidelity/IBKR Method)
                    now = datetime.now()
                    expiry_dt = datetime.strptime(selected_exp, "%Y-%m-%d").replace(hour=16, minute=0)
                    time_diff = expiry_dt - now
                    
                    # Convert to precise year fraction (525600 mins per year)
                    minutes_to_expiry = max(1, time_diff.total_seconds() / 60)
                    t_years = minutes_to_expiry / 525600.0
                    raw_dte = max(0, time_diff.days)
                    
                    chain = stock.option_chain(selected_exp)
                    options = (chain.puts if "CSP" in mode_opt else chain.calls).copy()
                    options["dist"] = abs(options["strike"] - px)
                    options = options.sort_values("dist").head(25)
                    
                    for _, row in options.iterrows():
                        # BID PRICE ONLY (Matches IV Bid column)
                        bid = row.get("bid", 0)
                        calc_price = bid if bid > 0 else (row["lastPrice"] * 0.95)
                        
                        if calc_price <= 0: continue

                        r = 0.043 # Market risk-free rate
                        m = 'put' if "CSP" in mode_opt else 'call'

                        iv_val = find_implied_vol(calc_price, px, row["strike"], t_years, r, m)
                        d_val = get_delta(px, row["strike"], t_years, r, iv_val, m)
                        
                        if min_d <= abs(d_val) <= max_d:
                            roi = (calc_price / (row["strike"] if "CSP" in mode_opt else px)) * 100
                            results.append({
                                "Ticker": tkr, "Price": px, "% Change": pct_change,
                                "Strike": row["strike"], "Prem": calc_price, "Delta": d_val,
                                "ROI%": roi, "Annual%": roi * (365 / max(1, raw_dte)), "IV%": iv_val * 100,
                                "Vol": row["volume"], "OI": row["openInterest"], "DTE": raw_dte, "Earnings": earn_dt
                            })
            except: pass
            pb.progress((idx + 1) / len(subset))

        if results:
            df = pd.DataFrame(results).sort_values(by=["Ticker", "Strike"], ascending=[True, False])
            
            def color_rows(df_in):
                styles = []; prev = None; dark = False
                for _, row in df_in.iterrows():
                    if prev != row["Ticker"]: dark = not dark; prev = row["Ticker"]
                    bg = COLOR_GROUP_DARK if dark else COLOR_GROUP_LIGHT
                    row_style = [f'background-color: {bg}'] * len(row)
                    if row["% Change"] > 0: row_style[0] = f'background-color: {COLOR_POSITIVE}; font-weight: 600'
                    elif row["% Change"] < 0: row_style[0] = f'background-color: {COLOR_NEGATIVE}; font-weight: 600'
                    styles.append(row_style)
                return pd.DataFrame(styles, index=df_in.index, columns=df_in.columns)

            st.dataframe(df.style.apply(color_rows, axis=None).format({
                "Price": "{:.2f}", "% Change": "{:.2f}%", "Strike": "{:.2f}", 
                "Prem": "{:.2f}", "ROI%": "{:.2f}%", "Annual%": "{:.1f}%", 
                "Delta": "{:.3f}", "IV%": "{:.1f}", "Vol": "{:,.0f}", "OI": "{:,.0f}"}), 
                use_container_width=True, height=600, hide_index=True)