from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import io
import ssl
import numpy as np
import pandas as pd
import requests
from scipy.stats import norm
import streamlit as st
import yfinance as yf

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# ==========================================
# 📋 THEME CONFIGURATION
# ==========================================
PRIMARY_COLOR = "#1e3a8a"      
CHIP_COLOR = "#969393"
WHITE_TEXT = "#ffffff"
TABLE_COLUMN_TEXT = "#608d06"
ROW_EVEN_COLOR = "#f8fafc"     

# 🎨 DAILY CHANGE COLORS (Positive / Negative)
BG_GREEN_POS = "#1e3a24"  # Dark forest green for Stock column background
BG_RED_NEG = "#4c1d1d"    # Dark maroon for Stock column background

TXT_GREEN_POS = "#3e7937" # Vibrant green for Chg and Chg (%) text
TXT_RED_NEG = "#cc5353"   # Vibrant red for Chg and Chg (%) text

# 🎨 STOCK TYPE COLORS 
COLOR_CORE_BG = "#dbeafe"
COLOR_CORE_TXT = "#1e3a8a"

COLOR_GROWTH_BG = "#dcfce7"
COLOR_GROWTH_TXT = "#15803d"

COLOR_MOMENTUM_BG = "#fef08a"
COLOR_MOMENTUM_TXT = "#854d0e"

COLOR_RISK_BG = "#fee2e2"
COLOR_RISK_TXT = "#991b1b"

# 📊 MOVING AVERAGE GRADIENT (Darkest to Lightest Green)
MA_200_BG = "#1e3a24"  # Very Dark Green
MA_100_BG = "#2d5a34"  # Dark Green
MA_50_BG = "#3e7937"   # Medium Green
MA_20_BG = "#68a35c"   # Light Green

# ==========================================
# 🚨 SIDEBAR REMOVED
# ==========================================
# We bypassed the option_menu and hardcoded the default page to save space!
selected_menu = "Watchlist Scanner"

# =========================
# 📊 FETCHERS & HELPERS
# =========================

@st.cache_data(ttl=300)
def fetch_top_indices():
    market_data = {}
    tickers = ["SPY", "QQQ", "^VIX"]
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="1y")
            if not hist.empty:
                curr_price = hist['Close'].iloc[-1]
                ytd_est = ((curr_price - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                market_data[t] = {"price": curr_price, "ytd": ytd_est}
        except:
            market_data[t] = {"price": 0.0, "ytd": 0.0}
    return market_data


def compute_earning_alert(earn_date_str):
    if not earn_date_str or earn_date_str == "N/A":
        return "🔴"
        
    try:
        today = datetime.now().date()
        earn_date = datetime.strptime(earn_date_str, '%b %d, %Y').date()
        
        weekday_val = earn_date.isoweekday()
        offset = weekday_val - 5
        pre_friday = earn_date - timedelta(days=offset)
        
        days_left = (pre_friday - today).days
        
        if pre_friday <= today:
            return f"🔴 ({days_left}d)"
        elif days_left < 14:
            return f"⚪ ({days_left}d)"
        elif days_left <= 30:
            return f"💰 ({days_left}d)"
        elif days_left <= 40:
            return f"🟢 ({days_left}d)"
        else:
            return f"🟡 ({days_left}d)"
    except Exception:
        return "🔴"


def fetch_single_ticker(ticker, stock_type, trade_quantities):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="250d")
        
        if not hist.empty:
            cur = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else cur
            chg = cur - prev
            pct_val = ((cur - prev) / prev) * 100
            
            earn = "N/A"
            if stock.calendar is not None and not (isinstance(stock.calendar, pd.DataFrame) and stock.calendar.empty):
                try: earn = stock.calendar.get('Earnings Date', ["N/A"])[0].strftime('%b %d, %Y')
                except: pass

            alert = compute_earning_alert(earn)
            
            qty_val = trade_quantities.get(ticker, 0)
            display_qty = int(qty_val) if qty_val > 0 else "✖"

            return {
                "Stock": ticker, 
                "Stock Type": stock_type,
                "Current Price": round(float(cur), 2), 
                "Chg": round(float(chg), 2),
                "Pct_Raw": round(float(pct_val), 2), 
                "Chg (%)": f"{pct_val:.2f}%", 
                "Qty": display_qty,
                "Last Close": round(float(prev), 2),
                "Earning Date": earn, 
                "Earning Alert": alert, 
                "20 Day MA": round(float(hist['Close'].rolling(20).mean().iloc[-1]), 2),
                "50 Day MA": round(float(hist['Close'].rolling(50).mean().iloc[-1]), 2),
                "100 Day MA": round(float(hist['Close'].rolling(100).mean().iloc[-1]), 2),
                "200 Day MA": round(float(hist['Close'].rolling(200).mean().iloc[-1]), 2)
            }
    except:
        pass
    return None


def style_stock_type(val):
    v = str(val).strip().upper()
    if 'CORE' in v:
        return f'background-color: {COLOR_CORE_BG}; color: {COLOR_CORE_TXT}; font-weight: bold;' 
    elif 'GROWTH' in v:
        return f'background-color: {COLOR_GROWTH_BG}; color: {COLOR_GROWTH_TXT}; font-weight: bold;' 
    elif 'MOMENTUM' in v or 'AGGRESSIVE' in v:
        return f'background-color: {COLOR_MOMENTUM_BG}; color: {COLOR_MOMENTUM_TXT}; font-weight: bold;' 
    elif 'RISK' in v:
        return f'background-color: {COLOR_RISK_BG}; color: {COLOR_RISK_TXT}; font-weight: bold;' 
    return '' 


def highlight_moving_averages(row):
    styles = [''] * len(row)
    
    ma_20 = row['20 Day MA']
    ma_50 = row['50 Day MA']
    ma_100 = row['100 Day MA']
    ma_200 = row['200 Day MA']
    
    idx_20 = 9
    idx_50 = 10
    idx_100 = 11
    idx_200 = 12
    
    if ma_20 > ma_50:
        styles[idx_20] = f'background-color: {MA_20_BG}; color: {WHITE_TEXT}; font-weight: bold;'
        
    if ma_50 > ma_100:
        styles[idx_50] = f'background-color: {MA_50_BG}; color: {WHITE_TEXT}; font-weight: bold;'
        
    if ma_100 > ma_200:
        styles[idx_100] = f'background-color: {MA_100_BG}; color: {WHITE_TEXT}; font-weight: bold;'
        
    if row['Current Price'] > ma_200:
        styles[idx_200] = f'background-color: {MA_200_BG}; color: {WHITE_TEXT}; font-weight: bold;'
        
    return styles

# =========================
# 🎯 WATCHLIST SCANNER
# =========================
if selected_menu == "Watchlist Scanner":
    
    col1, col2 = st.columns([3, 5], vertical_alignment="center")
    
    with col1:
        sub_col1, sub_col2 = st.columns([3, 1], vertical_alignment="center")
        with sub_col1:
            st.markdown("### Google Sheets Watchlist")
        with sub_col2:
            refresh_clicked = st.button("🔄", help="Click to pull list and live data", key="refresh_watchlist")

    with col2:
        market = fetch_top_indices()
        
        def fmt_ticker(symbol):
            data = market.get(symbol, {"price": 0, "ytd": 0})
            price = data['price']
            ytd = data['ytd']
            color = "red" if ytd < 0 else "green"
            
            if symbol == "^VIX":
                return f"*{symbol.replace('^', '')}* `${price:,.2f}`"
                
            return f"*{symbol}* `${price:,.2f}` <span style='color:{color};'>({ytd:+.2f}%)</span>"

        ticker_line = f"{fmt_ticker('SPY')} &nbsp;&nbsp;&nbsp;&nbsp; {fmt_ticker('QQQ')} &nbsp;&nbsp;&nbsp;&nbsp; {fmt_ticker('^VIX')}"
        st.markdown(f"<div style='text-align: right; font-size: 1.1rem;'>{ticker_line}</div>", unsafe_allow_html=True)

    url = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=337359953"
    trade_log_url = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=1662549766"
    
    ticker_type_map = {}
    unique_types = []

    if refresh_clicked or ("ticker_list" not in st.session_state):
        try:
            response = requests.get(url, verify=False, timeout=10)
            df = pd.read_csv(io.BytesIO(response.content))
            df.columns = df.columns.str.strip()
            
            df_cleaned = df.dropna(subset=[df.columns[0]]).copy()
            df_cleaned[df.columns[0]] = df_cleaned[df.columns[0]].astype(str).str.strip().str.upper()
            df_cleaned = df_cleaned[~df_cleaned[df.columns[0]].isin(['STOCK', 'TICKER', 'CASH'])]
            
            for index, row in df_cleaned.iterrows():
                tick = row[df.columns[0]]
                t_type = str(row[df.columns[1]]).strip() if len(df.columns) > 1 else "Unknown"
                ticker_type_map[tick] = t_type
                
            ticker_list = list(ticker_type_map.keys())
            st.session_state["ticker_list"] = ticker_list
            st.session_state["ticker_type_map"] = ticker_type_map
            
            extracted_types = list(set(ticker_type_map.values()))
            st.session_state["unique_types"] = [t for t in extracted_types if t not in ['nan', 'None', '']]
            
            trade_response = requests.get(trade_log_url, verify=False, timeout=10)
            trade_df = pd.read_csv(io.BytesIO(trade_response.content))
            trade_df.columns = trade_df.columns.str.strip()
            
            stock_col = None
            for candidate in ['Stock', 'Ticker', 'STOCK', 'TICKER']:
                if candidate in trade_df.columns:
                    stock_col = candidate
                    break
            if stock_col is None:
                stock_col = trade_df.columns[0]
            
            open_trades = trade_df[(trade_df['Status'] == 'Open') & (trade_df['Opt Typ'] != 'Opt Typ')].copy()
            open_trades['Qty'] = pd.to_numeric(open_trades['Qty'], errors='coerce').fillna(0)
            summed_qty = open_trades.groupby(stock_col)['Qty'].sum().to_dict()
            st.session_state["trade_quantities"] = summed_qty
            
            if refresh_clicked:
                st.success(f"Successfully pulled {len(ticker_list)} tickers!")
                st.cache_data.clear()
            
        except Exception as e:
            st.error(f"Sheet Error: {e}")

    if "ticker_list" in st.session_state and st.session_state["ticker_list"]:
        
        f_col1, f_col2 = st.columns([3, 2])
        
        avail_types = st.session_state.get("unique_types", [])
        with f_col1:
            selected_types = st.multiselect("Filter by Stock Type", options=avail_types, default=avail_types)
        with f_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            exclude_x = st.checkbox("Hide symbols without active quantity (✖)", value=False)
            
        st.write("### Live Metrics for Sheet Tickers")
        
        trade_quantities = st.session_state.get("trade_quantities", {})
        ticker_type_map = st.session_state.get("ticker_type_map", {})
        
        col_order = ("Stock", "Stock Type", "Current Price", "Chg", "Chg (%)", "Qty", "Last Close", "Earning Date", "Earning Alert", "20 Day MA", "50 Day MA", "100 Day MA", "200 Day MA")
        
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        table_placeholder = st.empty()
        streaming_df = pd.DataFrame(columns=col_order)
        
        tickers_to_scan = st.session_state["ticker_list"]
        total = len(tickers_to_scan)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_single_ticker, ticker, ticker_type_map.get(ticker, "N/A"), trade_quantities): ticker for ticker in tickers_to_scan}
            
            for i, future in enumerate(futures):
                ticker = futures[future]
                
                status_text.text(f"Scanning {ticker} ({i + 1}/{total})")
                progress_bar.progress((i + 1) / total)
                
                result = future.result()
                
                if result:
                    new_row = pd.DataFrame([result])
                    streaming_df = pd.concat([streaming_df, new_row], ignore_index=True)
                    
                    filtered_df = streaming_df.copy()
                    
                    if selected_types:
                        filtered_df = filtered_df[filtered_df['Stock Type'].isin(selected_types)]
                        
                    if exclude_x:
                        filtered_df = filtered_df[filtered_df['Qty'] != '✖']
                    
                    if not filtered_df.empty:
                        styler = filtered_df.style.apply(lambda x: [
                            f'background-color: {BG_GREEN_POS if x["Pct_Raw"] >= 0 else BG_RED_NEG}; color: {WHITE_TEXT}; font-weight: bold' if idx == 0 else 
                            f'color: {TXT_GREEN_POS if x["Pct_Raw"] >= 0 else TXT_RED_NEG}; font-weight: bold' if idx in [3, 4] else 
                            f'background-color: {ROW_EVEN_COLOR}' if x.name % 2 != 0 else '' 
                            for idx, v in enumerate(x)], axis=1)
                        
                        styler = styler.map(style_stock_type, subset=['Stock Type'])
                        styler = styler.apply(highlight_moving_averages, axis=1)
                        
                        styler = styler.format({
                            "Current Price": "{:.2f}",
                            "Chg": "{:.2f}",
                            "Last Close": "{:.2f}",
                            "20 Day MA": "{:.2f}",
                            "50 Day MA": "{:.2f}",
                            "100 Day MA": "{:.2f}",
                            "200 Day MA": "{:.2f}"
                        })
                        
                        table_placeholder.dataframe(
                            styler, 
                            use_container_width=True, 
                            hide_index=True, 
                            column_order=col_order
                        )
                    else:
                        table_placeholder.info("No tickers match selected filters.")
            
        status_text.empty()
        progress_bar.empty()
        
    else:
        st.info("Click the button above to load your Google Sheet data.")