import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import certifi
import numpy as np
from datetime import datetime, timedelta

# ========================================================
# 🎨 UI STYLING
# ========================================================
st.set_page_config(layout="wide", page_title="Live Portfolio Desk")

st.markdown("""
<style>
    [data-testid="stDataFrame"]:first-of-type td, 
    [data-testid="stDataFrame"]:first-of-type th {
        font-size: 20px !important;
        height: 50px !important;
    }
    div[data-testid='stDataFrame'] th {
        text-align: center !important; 
        background-color: #f1f5f9 !important;
        font-weight: bold !important;
    }
    div[data-testid="stDataFrame"] {
        border: 1.5px solid #334155 !important;
        border-radius: 10px !important;
        margin-bottom: 25px;
    }
</style>
""", unsafe_allow_html=True)

# ========================================================
# 📥 DATA LOADING & HELPERS
# ========================================================
URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=1662549766"

@st.cache_data(ttl=300)
def load_live_data():
    try:
        response = requests.get(URL, verify=certifi.where())
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = df.columns.str.strip()
        stock_col = [c for c in df.columns if "Stock" in c][0]
        df = df.rename(columns={stock_col: "Stock"})
        return df[df["Status"] == "Open"].copy()
    except Exception:
        return pd.DataFrame()

def get_earn_emoji(date_str):
    if not date_str: return "🔴"
    try:
        today = datetime.now().date()
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        pre_fri = dt - timedelta(days=(dt.isoweekday() - 5))
        days = (pre_fri - today).days
        if days < 0: return f"🔴 ({days}d)"
        elif days < 14: return f"⚪ ({days}d)"
        elif days <= 30: return f"💰 ({days}d)"
        elif days <= 40: return f"🟢 ({days}d)"
        else: return f"🟡 ({days}d)"
    except: return "🔴"

def color_chg(val):
    color = '#008000' if val > 0 else '#FF0000'
    return f'color: {color}; font-weight: bold;'

def color_strike(row):
    """Targeted Cell Styling: Red background if ITM/In Danger"""
    styles = [''] * len(row)
    if 'Strike' not in row.index or 'Last Close' not in row.index or 'Type' not in row.index:
        return styles
        
    idx = row.index.get_loc('Strike')
    strike = row['Strike']
    price = row['Last Close']
    typ = row['Type']
    
    # PUT: Danger if Price < Strike | CALL: Danger if Price > Strike
    if (typ == "PUT" and price < strike) or (typ == "CALL" and price > strike):
        styles[idx] = 'background-color: #FF0000; color: white; font-weight: bold;'
    return styles

# --- HELPERS SECTION ---
@st.cache_data(ttl=300)
def get_market_ribbon():
    """Fetches Price, Daily %, and YTD % for SPY, QQQ, VIX safely."""
    ribbon_stats = {}
    for symbol in ["SPY", "QQQ", "^VIX"]:
        try:
            # Use period='ytd' directly for more reliable data fetching
            tk = yf.Ticker(symbol)
            hist = tk.history(period="ytd")
            
            if not hist.empty and len(hist) >= 2:
                latest_price = hist['Close'].iloc[-1]
                previous_close = hist['Close'].iloc[-2]
                year_start_price = hist['Close'].iloc[0]
                
                ribbon_stats[symbol] = {
                    "last_px": latest_price,
                    "day_pct": ((latest_price - previous_close) / previous_close) * 100,
                    "ytd_pct": ((latest_price - year_start_price) / year_start_price) * 100
                }
        except Exception:
            continue # Silently skip failed tickers to prevent 'd' error
    return ribbon_stats

# --- RENDER SECTION ---
st.title("📈 Live Portfolio Desk")

# Compact Market Ribbon
mkt_data = get_market_ribbon()
if mkt_data:
    display_list = []
    for ticker, stats in mkt_data.items():
        clean_name = ticker.replace("^", "")
        
        # Determine colors for each metric individually
        d_clr = "#00c805" if stats['day_pct'] >= 0 else "#ff4b4b"
        y_clr = "#00c805" if stats['ytd_pct'] >= 0 else "#ff4b4b"
        
        # Build HTML with separate color spans
        ticker_html = (
            f"**{clean_name}**: {stats['last_px']:,.2f} "
            f"<span style='color:{d_clr}; font-size: 0.85em;'>{stats['day_pct']:+.2f}% (D)</span> | "
            f"<span style='color:{y_clr}; font-size: 0.85em;'>{stats['ytd_pct']:+.2f}% (YTD)</span>"
        )
        display_list.append(ticker_html)
    
    st.markdown(f"<h6>{' &nbsp;&nbsp; | &nbsp;&nbsp; '.join(display_list)}</h6>", unsafe_allow_html=True)
st.divider()

df_raw = load_live_data()

if not df_raw.empty:
    df_raw["Account"] = df_raw["Account"].astype(str).str.strip()
    df_raw["Opt Typ"] = df_raw["Opt Typ"].astype(str).str.upper()
    df_raw["Close Date"] = df_raw["Close Date"].astype(str).str.strip()

    with st.expander("🔍 Trade Position Parameters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            acct_list = ["All"] + sorted(df_raw["Account"].unique().tolist())
            filter_acct = st.selectbox("Select Account", acct_list)
        with col2:
            date_list = ["All"] + sorted([d for d in df_raw["Close Date"].unique() if str(d) != 'nan'])
            filter_date = st.selectbox("Select Close Date", date_list)
        with col3:
            type_list = ["All"] + sorted(df_raw["Opt Typ"].unique().tolist())
            filter_type = st.selectbox("Select Option Type", type_list)

        run_scan = st.button("📡 Fetch Live Quotes", use_container_width=True)

    # Filter Setup
    df = df_raw.copy()
    if filter_acct != "All": df = df[df["Account"] == filter_acct]
    if filter_date != "All": df = df[df["Close Date"] == filter_date]
    if filter_type != "All": df = df[df["Opt Typ"] == filter_type]

    df = df[~df["Account"].str.contains("401", na=False)]
    df["Strike"] = pd.to_numeric(df["Strike Price"], errors="coerce").fillna(0)
    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0).abs()
    df["Stock"] = df["Stock"].astype(str).str.upper()

    if run_scan:
        tickers = [t for t in df["Stock"].unique() if t != "CASH"]
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        st.markdown("### 🏦 Account Summary")
        summary_spot = st.empty()
        st.markdown("### 📊 Active Trade Positions")
        queue_spot = st.empty()

        live_results = []
        cash_rows = df[df["Stock"] == "CASH"]
        for _, row in cash_rows.iterrows():
            live_results.append({
                "Ticker": "CASH", "Account": row["Account"], "Type": "CASH",
                "Market Value": row["Qty"], "Qty": row["Qty"],
                "Last Close": 0.0, "Strike": 0.0, "Chg": 0.0, "Chg (%)": 0.0
            })

        for i, t in enumerate(tickers):
            status_text.text(f"🔍 Fetching Market Data: {t} ({i+1}/{len(tickers)})")
            progress_bar.progress((i + 1) / len(tickers))
            
            try:
                tk = yf.Ticker(t)
                hist = tk.history(period="1y") 
                if not hist.empty:
                    px = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2]
                    
                    ticker_rows = df[df["Stock"] == t]
                    for _, row in ticker_rows.iterrows():
                        o, s, q = row["Opt Typ"], row["Strike"], row["Qty"]
                        
                        if o == "HOLD": mkt_val = row.get("Cash Reserve", 0.0)
                        elif o == "CALL": mkt_val = (q * min(px, s) * 100)
                        elif o == "PUT": mkt_val = (q * (px if px < s else s) * 100)
                        else: mkt_val = (q * px * 100)
                        
                        live_results.append({
                            "Ticker": t, "Account": row["Account"], "Type": o,
                            "Last Close": px, "Close Date": row["Close Date"], "Strike": s,
                            "Chg": px - prev, "Chg (%)": ((px - prev) / prev) * 100,
                            "Qty": q, "Market Value": mkt_val,
                            "20D MA": hist['Close'].rolling(20).mean().iloc[-1],
                            "50D MA": hist['Close'].rolling(50).mean().iloc[-1],
                            "100D MA": hist['Close'].rolling(100).mean().iloc[-1],
                            "200D MA": hist['Close'].rolling(200).mean().iloc[-1],
                            "Earn": tk.calendar['Earnings Date'][0].strftime('%Y-%m-%d') if tk.calendar and 'Earnings Date' in tk.calendar else ""
                        })
            except: continue

            current_df = pd.DataFrame(live_results)
            
            # Summary Table
            l_total = current_df[current_df["Account"].str.contains("LLC", na=False)]["Market Value"].sum()
            i_total = current_df[current_df["Account"].str.contains("IRA", na=False)]["Market Value"].sum()
            p_tot = current_df[current_df["Type"] == "PUT"]["Market Value"].sum()
            c_tot = current_df[current_df["Type"] == "CALL"]["Market Value"].sum()

            summary_df = pd.DataFrame([
                {"Account": "Total Value", "LLC": l_total, "IRA": i_total, "Total": l_total + i_total},
                {"Account": "Total Puts", "LLC": p_tot if filter_acct != "IRA" else 0, "IRA": p_tot if filter_acct != "LLC" else 0, "Total": p_tot},
                {"Account": "Total Calls", "LLC": c_tot if filter_acct != "IRA" else 0, "IRA": c_tot if filter_acct != "LLC" else 0, "Total": c_tot}
            ])
            summary_spot.dataframe(summary_df.style.format({"LLC": "${:,.2f}", "IRA": "${:,.2f}", "Total": "${:,.2f}"}), hide_index=True, use_container_width=True)

            # Trade Positions Table
            queue_df = current_df[current_df["Ticker"] != "CASH"].copy()
            if not queue_df.empty:
                queue_df['Earning Alert'] = queue_df['Earn'].apply(get_earn_emoji)
                final_cols = ["Ticker", "Account", "Type", "Last Close", "Close Date", "Strike", 
                              "Chg", "Chg (%)", "Earn", "Earning Alert", 
                              "20D MA", "50D MA", "100D MA", "200D MA", "Qty"]
                
                existing_cols = [c for c in final_cols if c in queue_df.columns]
                display_df = queue_df.sort_values(by="Ticker")[existing_cols]
                
                styled_df = display_df.style.apply(color_strike, axis=1) # Applied to whole row, logic handles cell
                
                subset_chg = [c for c in ['Chg', 'Chg (%)'] if c in display_df.columns]
                if subset_chg:
                    styled_df = styled_df.applymap(color_chg, subset=subset_chg)
                
                f_map = {"Strike": "${:.2f}", "Last Close": "${:.2f}", "Chg": "${:.2f}", 
                         "20D MA": "${:.2f}", "50D MA": "${:.2f}", "100D MA": "${:.2f}", 
                         "200D MA": "${:.2f}", "Chg (%)": "{:.2f}%", "Qty": "{:.0f}"}
                
                styled_df = styled_df.format({k: v for k, v in f_map.items() if k in display_df.columns})
                queue_spot.dataframe(styled_df, hide_index=True, use_container_width=True)

        status_text.empty()
        progress_bar.empty()
    else:
        st.info("💡 Adjust parameters above and click 'Fetch Live Quotes' to refresh the desk.")