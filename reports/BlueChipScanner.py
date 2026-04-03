import io
import os
import sys
from datetime import datetime, timedelta
import certifi
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ==========================================
# 🛠️ DYNAMIC PATHING 
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

if current_dir not in sys.path:
    sys.path.append(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from reports.engine import *
except ModuleNotFoundError:
    try:
        from engine import *
    except ModuleNotFoundError:
        pass  

# ==========================
# 🎨 UI & STATE MANAGEMENT
# ==========================
if 'scan_results' not in st.session_state: 
    st.session_state.scan_results = None
if 'selected_ticker' not in st.session_state:
    st.session_state.selected_ticker = None

st.title("💎 Blue Chip Scanner")

# ==========================================
# 📥 DATA & FETCHING UTILS
# ==========================================
SPREADSHEET_ID = "1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M"

@st.cache_data(ttl=300)
def get_tickers_from_sheets(tab_name):
    # We are overriding the tab request to point strictly to your WatchList gid
    # grid id 337359953 maps directly to your WatchList tab
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid=337359953"
    try:
        response = requests.get(url, verify=certifi.where(), timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            
            # Standardize column headers to combat case sensitivity
            df.columns = df.columns.str.strip().str.replace(r'[^\w\s]', '', regex=True)
            return df
        else:
            st.error(f"Failed to fetch sheet. Status code: {response.status_code}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching sheet: {e}")
        return pd.DataFrame()

# ==========================
# 🎨 TABLE ROW STYLER
# ==========================
def style_table_rows(df):
    bg_color = "#dee3e8"
    text_color = "#000000"
    style_matrix = pd.DataFrame('', index=df.index, columns=df.columns)
    
    for idx, row in df.iterrows():
        base_style = f'background-color: {bg_color}; color: {text_color};' if idx % 2 == 0 else ''
        style_matrix.loc[idx] = base_style
        
        chg_val = str(row.get('Chg', ''))
        if '+' in chg_val:
            style_matrix.loc[idx, 'Chg'] = f'{base_style} color: #16a34a; font-weight: bold;'
        elif '-' in chg_val:
            style_matrix.loc[idx, 'Chg'] = f'{base_style} color: #dc2626; font-weight: bold;'
            
    return style_matrix

# ==========================
# 📅 DATE LOOKBACK HELPER
# ==========================
def get_prior_expiries(selected_expiry_str, num_weeks=3):
    selected_dt = datetime.strptime(selected_expiry_str, "%Y-%m-%d")
    expiries = []
    for i in range(num_weeks):
        target_dt = selected_dt - timedelta(weeks=i)
        if target_dt.weekday() == 4:
            expiries.append(target_dt.strftime("%Y-%m-%d"))
    return expiries

# ==========================
# 🛠️ SCANNER FILTERS
# ==========================
indices = {
    "S&P 500": "SP500",      
    "Nasdaq 100": "Nasdaq",   
    "MyWatchList": "WatchList" 
}

try:
    third_friday = get_next_third_friday()
    available_fridays = get_fridays()
except NameError:
    third_friday = "2026-04-17"
    available_fridays = ["2026-04-17", "2026-05-15"]

if third_friday not in available_fridays:
    available_fridays.insert(0, third_friday)

with st.expander("🛠️ Scanner Filters", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1: 
        market = st.selectbox("📊 Market", list(indices.keys()), index=2) # Defaulted to MyWatchList
    with col2: 
        default_idx = available_fridays.index(third_friday) if third_friday in available_fridays else 0
        expiry = st.selectbox("📅 Expiry", available_fridays, index=default_idx)
    with col3: 
        depth = st.selectbox("🔍 Depth", [10, 20, 30, 50, 100], index=3) # Extended depth options
    with col4: 
        max_price = st.number_input("💰 Max $", min_value=10, max_value=2000, value=400, step=10)

    col5, col6 = st.columns(2)
    with col5: manual_tickers = st.text_input("🎯 Manual Tickers (CSV)", placeholder="AAPL, MSFT")
    with col6: min_iv = st.number_input("⚡ Min IV%", min_value=0, value=35, step=5)

# ==========================
# 🚀 ACTION BUTTON & RESULTS
# ==========================
col_btn, col_res = st.columns([3, 1])
found_count = len(st.session_state.scan_results) if st.session_state.scan_results is not None else 0

with col_btn:
    run_scan = st.button(f"🚀 Scan {market}", use_container_width=True)

with col_res:
    st.markdown(
        f"<div style='background-color: #1b381e; color: #ffffff; text-align: center; "
        f"padding: 10px; border-radius: 5px; font-weight: bold; border: 1px solid #2e7d32;'>"
        f"Found: {found_count}</div>", 
        unsafe_allow_html=True
    )

# ==========================
# ⚙️ MAIN SCANNER EXECUTION
# ==========================
if run_scan:
    with st.spinner(f"Fetching {market} tickers from Google Sheets..."):
        target_tab = indices[market]
        df_sheet = get_tickers_from_sheets(target_tab)
        
    if not df_sheet.empty:
        raw_list = df_sheet.iloc[:, 0]
        raw_list = raw_list.astype(str).str.strip().str.upper()
        raw_list = raw_list.replace(['NAN', 'NONE', 'CASH', ''], np.nan).dropna()
        scan_list = raw_list.unique().tolist()
        
        st.write("Debug Raw List:", ", ".join(scan_list))
        scan_list = scan_list[:depth]
        
        if manual_tickers:
            manual_list = [t.strip().upper() for t in manual_tickers.split(",") if t.strip()]
            if manual_list: scan_list = manual_list
                
        results = []
        prog_bar = st.progress(0, "Scanning stocks...")
        live_grid = st.empty()
        
        current_rank = 1
        current_year = datetime.now().year

        for i, ticker in enumerate(scan_list, start=1):
            if not ticker or len(ticker) > 5 or ticker == 'STOCK':
                continue
                
            prog_bar.progress(i / len(scan_list), f"Scanning {ticker} ({i}/{len(scan_list)})")
            
            try:
                t_obj = yf.Ticker(ticker)
                curr_px = t_obj.fast_info['lastPrice']
                
                chain = t_obj.option_chain(expiry)
                if chain.puts.empty or chain.calls.empty:
                    continue
                    
                hist = t_obj.history(period="1y")
                mkt_cap = t_obj.fast_info.get('marketCap', 0)
                
                if not hist.empty:
                    prev_close = hist['Close'].iloc[-2]
                    diff = curr_px - prev_close
                    chg_display = f"{diff:+.2f}" if diff != 0 else "0.00"
                    
                    ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                    ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
                    ma100 = hist['Close'].rolling(window=100).mean().iloc[-1]
                    ma200 = hist['Close'].rolling(window=200).mean().iloc[-1]
                    
                    # 🔥 YTD High and Low (Only data from Jan 1st onward)
                    ytd_data = hist[hist.index >= f"{current_year}-01-01"]
                    if not ytd_data.empty:
                        high_ytd = ytd_data['High'].max()
                        low_ytd = ytd_data['Low'].min()
                        high_low_combined = f"${high_ytd:,.2f} / ${low_ytd:,.2f}"
                    else:
                        high_low_combined = "None"
                    
                    results.append({
                        "Rank": f"#{current_rank}",
                        "Ticker": ticker,
                        "Market Cap": mkt_cap,
                        "Current Price": f"${curr_px:,.2f}",
                        "Last Close": f"${prev_close:,.2f}",
                        "Chg": chg_display,
                        "20D MA": f"${ma20:,.2f}" if pd.notnull(ma20) else "None",
                        "50D MA": f"${ma50:,.2f}" if pd.notnull(ma50) else "None",
                        "100D MA": f"${ma100:,.2f}" if pd.notnull(ma100) else "None",
                        "200D MA": f"${ma200:,.2f}" if pd.notnull(ma200) else "None",
                        "YTD High/Low": high_low_combined
                    })
                    
                    current_rank += 1
                    current_df = pd.DataFrame(results).drop(columns=['Market Cap'])
                    live_grid.dataframe(current_df, use_container_width=True, hide_index=True, height=350)
                    
            except Exception:
                continue
                
        prog_bar.empty()
        
        if results:
            raw_df = pd.DataFrame(results)
            raw_df = raw_df.sort_values(by="Market Cap", ascending=False).reset_index(drop=True)
            raw_df['Rank'] = [f"#{x}" for x in range(1, len(raw_df) + 1)]
            raw_df = raw_df.drop(columns=['Market Cap'])
            
            st.session_state.scan_results = raw_df
            st.rerun()

# ==========================
# 📋 RESULTS & OPTION CHAIN UI
# ==========================
if st.session_state.scan_results is not None:
    styled_df = st.session_state.scan_results.style.apply(style_table_rows, axis=None)
    
    st.markdown(f"### 📋 {market} Scanned Results")
    
    event = st.dataframe(
        styled_df, 
        use_container_width=True, 
        hide_index=True,
        height=350,
        on_select="rerun"
    )
    
    if event is not None and "selection" in event:
        rows = event["selection"].get("rows", [])
        if rows:
            clicked_row_idx = rows[0]
            st.session_state.selected_ticker = st.session_state.scan_results.iloc[clicked_row_idx]['Ticker']

    if st.session_state.selected_ticker is not None:
        sel_t = st.session_state.selected_ticker
        target_expiries = get_prior_expiries(expiry, num_weeks=3)
        
        st.markdown(f"### ⛓️ Option Chains for **{sel_t}** (Lookback View)")
        tab_puts, tab_calls = st.tabs(["📉 Puts (CSP)", "📈 Calls (Covered Calls)"])
        
        t_obj = yf.Ticker(sel_t)
        px = t_obj.fast_info['lastPrice']
        
        def render_chain_view(opt_chain_df, side, exp_date_str):
            processed_list = []
            applied_min_iv = min_iv / 100
            
            exp_dt = datetime.strptime(exp_date_str, "%Y-%m-%d").replace(hour=16)
            days_to_exp = max((exp_dt - datetime.now()).days, 1)
            T = max((exp_dt - datetime.now()).total_seconds() / 31536000.0, 0.001)
            
            for _, row in opt_chain_df.iterrows():
                strike = float(row['strike'])
                bid = float(row['bid'])
                ask = float(row['ask'])
                mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else row.get('lastPrice', bid)
                
                try:
                    iv, delta = find_iv_and_delta(mid, px, strike, T, 0.043, side)
                except NameError:
                    delta = 0.30 if side == 'put' else -0.30
                    iv = 0.40
                
                delta_mag = abs(delta)
                roi_decimal = (bid / strike) if side == 'put' else (bid / px)
                roi_pct = roi_decimal * 100
                aor_pct = ((1 + roi_decimal)**(365 / days_to_exp) - 1) * 100
                
                if (0.10 <= delta_mag <= 0.50):
                    processed_list.append({
                        "Strike": strike,
                        "Bid": bid,
                        "Volume": int(row.get('volume', 0)),
                        "OI": int(row.get('openInterest', 0)),
                        "Delta": round(delta_mag, 2),
                        "IV%": iv * 100,
                        "ROI%": roi_pct,
                        "AOR%": aor_pct,
                        "raw_iv": iv
                    })
                    
            if processed_list:
                final_df = pd.DataFrame(processed_list)
                strict_df = final_df[final_df['raw_iv'] >= applied_min_iv]
                output_df = strict_df if not strict_df.empty else final_df
                
                if strict_df.empty:
                    st.caption(f"⚠️ Showing available chains outside target IV floor ({min_iv}%).")
                    
                output_df = output_df.drop(columns=['raw_iv']).sort_values(by="Delta", ascending=False)
                
                output_df['Strike'] = output_df['Strike'].apply(lambda x: f"${x:,.2f}")
                output_df['Bid'] = output_df['Bid'].apply(lambda x: f"${x:.2f}")
                output_df['IV%'] = output_df['IV%'].apply(lambda x: f"{x:.1f}%")
                output_df['ROI%'] = output_df['ROI%'].apply(lambda x: f"{x:.2f}%")
                output_df['AOR%'] = output_df['AOR%'].apply(lambda x: f"{x:.1f}%")
                
                styled_output = output_df.style.bar(
                    subset=['Volume'], color='#fff3cd', vmin=0
                ).bar(
                    subset=['OI'], color='#fff3cd', vmin=0
                )
                
                st.dataframe(styled_output, use_container_width=True, hide_index=True)
            else:
                st.info(f"No contracts found in the 0.10 to 0.50 Delta range for {exp_date_str}.")

        with tab_puts:
            for exp_dt in target_expiries:
                st.markdown(f"**📅 Expiration: {exp_dt}**")
                try:
                    chain_data = t_obj.option_chain(exp_dt)
                    otm_puts = chain_data.puts[chain_data.puts['strike'] <= px]
                    render_chain_view(otm_puts, 'put', exp_dt)
                except Exception:
                    st.error(f"Could not load puts for {exp_dt}")
                st.divider()
                
        with tab_calls:
            for exp_dt in target_expiries:
                st.markdown(f"**📅 Expiration: {exp_dt}**")
                try:
                    chain_data = t_obj.option_chain(exp_dt)
                    otm_calls = chain_data.calls[chain_data.calls['strike'] >= px]
                    render_chain_view(otm_calls, 'call', exp_dt)
                except Exception:
                    st.error(f"Could not load calls for {exp_dt}")
                st.divider()