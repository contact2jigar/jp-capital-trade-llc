import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# =========================
# 🎨 UI STYLING & COLOR CONFIG
# =========================
st.markdown("""
<style>
    .scanner-card { background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .market-label { font-weight: 500; color: #334155; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
    .found-badge { background-color: #064e3b; color: #ffffff; padding: 10px 25px; border-radius: 8px; font-weight: bold; min-width: 120px; text-align: center; border: 1px solid #065f46; height: 45px; display: flex; align-items: center; justify-content: center; }
    div.stButton > button { width: 100% !important; background-color: #334155 !important; color: white !important; border: none !important; height: 45px !important; border-radius: 8px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)

# Dynamic List Constants
SP20_LIST = "NVDA,AAPL,GOOGL,MSFT,AMZN,META,AVGO,TSLA,BRK-B,WMT,LLY,JPM,XOM,V,JNJ,MU,COST,ORCL,MA,NFLX"
NASDAQ20_LIST = "NVDA,AAPL,MSFT,AMZN,META,AVGO,TSLA,COST,AMD,NFLX,INTC,ADBE,CSCO,AMAT,QCOM,TXN,INTU,MU,PANW,AMGN"
YAHOO_ACTIVE = "NVDA,TSLA,AAPL,AMD,PLTR,AMZN,INTC,MARA,SOFI,MSFT,META,NIO,F,PFE,GOOGL,BAC,AAL,VALE,CCL,COIN"

# =========================
# 📊 DYNAMIC DATA LOGIC
# =========================
def get_dynamic_tickers(market, count):
    """Returns a list of tickers based on selected market source."""
    if market == "S&P 500":
        raw = SP20_LIST
    elif market == "Nasdaq 100":
        raw = NASDAQ20_LIST
    elif market == "Yahoo Active":
        raw = YAHOO_ACTIVE
    else: # Merge All Logic
        raw = f"{SP20_LIST},{NASDAQ20_LIST},{YAHOO_ACTIVE}"
    
    # De-duplicate and Clean
    clean_list = sorted(list(set([t.strip().upper() for t in raw.split(",") if t.strip()])))
    return clean_list[:count]

def build_scan_table(tickers):
    results = []
    today = datetime.now()
    three_months_ago = today - timedelta(days=90)
    start_of_year = datetime(today.year, 1, 1)

    for tkr in tickers:
        try:
            # Fetch 1y of data to cover YTD and 3M High
            df_hist = yf.download(tkr, period="1y", progress=False)
            if df_hist.empty: continue

            curr_px = df_hist["Close"].iloc[-1]
            prev_close = df_hist["Close"].iloc[-2]
            
            # Calculations
            change = curr_px - prev_close
            pct_change = (change / prev_close) * 100
            
            mask_3m = df_hist.index >= pd.Timestamp(three_months_ago)
            high_3m = df_hist.loc[mask_3m, "High"].max()

            ytd_data = df_hist[df_hist.index >= pd.Timestamp(start_of_year)]
            ytd_start_price = ytd_data["Open"].iloc[0]
            pct_ytd = ((curr_px - ytd_start_price) / ytd_start_price) * 100

            results.append({
                "Stock": tkr,
                "Current Price": round(float(curr_px), 2),
                "Change": round(float(change), 2),
                "% Change": round(float(pct_change), 2),
                "High (3M)": round(float(high_3m), 2),
                "% YTD": round(float(pct_ytd), 2)
            })
        except: continue
    return pd.DataFrame(results)

# =========================
# 🏗️ UI RENDER
# =========================
with st.container():
    st.markdown('<div class="scanner-card">', unsafe_allow_html=True)
    
    col_mkt, col_qty = st.columns([7, 3])
    
    with col_mkt:
        st.markdown('<div class="market-label">📊 Market</div>', unsafe_allow_html=True)
        market_choice = st.selectbox("Market", ["S&P 500", "Nasdaq 100", "Yahoo Active", "Merge All"], label_visibility="collapsed")
    
    with col_qty:
        st.markdown('<div class="market-label">🔢 Stock Count</div>', unsafe_allow_html=True)
        stock_count = st.selectbox("Count", [10, 20, 50, 100], index=1, label_visibility="collapsed")

    col_btn, col_badge = st.columns([8.5, 1.5])

    with col_btn:
        scan_clicked = st.button(f"🚀 Scan {market_choice}")

    with col_badge:
        st.markdown(f'<div class="found-badge">Found: {st.session_state.get("found_count", 0)}</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# 🚀 EXECUTION
# =========================
if scan_clicked:
    with st.spinner(f"Scanning {market_choice}..."):
        ticker_list = get_dynamic_tickers(market_choice, stock_count)
        df_results = build_scan_table(ticker_list)
        
        st.session_state.found_count = len(df_results)
        
        if not df_results.empty:
            # Color coding for readability
            def color_negative_red(val):
                color = '#e4cccc' if val < 0 else '#c5e2cf'
                return f'background-color: {color}'

            st.dataframe(
                df_results.style.format({
                    "Current Price": "${:,.2f}",
                    "Change": "{:+,.2f}",
                    "% Change": "{:+.2f}%",
                    "High (3M)": "${:,.2f}",
                    "% YTD": "{:+.2f}%"
                }).applymap(color_negative_red, subset=['% Change', '% YTD']),
                use_container_width=True,
                height=500,
                hide_index=True
            )
        else:
            st.error("No data found.")