import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import io
import time
import random
from scipy.stats import norm
from datetime import datetime, timedelta

# ========================================================
# 🎨 STYLE ENGINE: DUAL-AXIS SCROLL & STICKY HEADERS
# ========================================================
st.set_page_config(layout="wide", page_title="Institutional CSP Engine")

def styled_table(df):
    html = df.to_html(index=False, escape=False, classes='table table-dark table-striped')
    return f'<div class="table-container">{html}</div>'

st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 16px; }
    .reportview-container .main .block-container{ max-width: 98%; padding-top: 1rem; }
    
    .streamlit-expanderHeader {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border-radius: 5px;
    }
    .streamlit-expanderContent {
        background-color: #121212 !important;
        color: #ffffff !important;
        border: 1px solid #333;
    }          
              
    .table-container {
        max-height: 600px; 
        overflow-y: auto;
        overflow-x: auto;
        border: 1px solid #444;
        border-radius: 8px;
        background-color: #000000;
    }

    table { width: 100%; border-collapse: collapse; min-width: 2000px; color: #ffffff; }

    th { 
        position: sticky; top: 0; z-index: 10;
        text-align: left !important; background-color: #222222 !important; color: #ffffff !important; 
        border: 1px solid #444; padding: 12px !important; font-size: 13px !important;
        text-transform: uppercase; letter-spacing: 1px;
    }

    td { 
        font-family: 'Roboto', sans-serif; 
        border: 1px solid #333 !important; 
        padding: 10px !important; font-size: 14px !important; font-weight: 500;
        vertical-align: middle; white-space: nowrap; color: #ffffff !important;
    }
    
    tr:hover td { background-color: #1a1a1a !important; }

    .price-font { font-family: 'Courier New', monospace; font-weight: bold; }
    .pos { color: #00ff41 !important; font-weight: bold; } 
    .neg { color: #ff3131 !important; font-weight: bold; }
    
    .csp-strong { background-color: #008f39; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    .csp-avoid { background-color: #b22222; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    .h-score { font-weight: bold; padding: 4px 8px; border-radius: 4px; color: white; display: inline-block; min-width: 35px; text-align: center; }

    div.stButton > button:first-child { margin-top: 28px; width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# ========================================================
# 🛠️ GREEKS & INDICATORS
# ========================================================
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_delta(S, K, T, r, sigma):
    if T <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) - 1

def get_best_put_by_delta(tk, target_expiry, current_price, target_delta=-0.30):
    try:
        available = tk.options
        match = [d for d in available if d.startswith(target_expiry[:7])]
        if not match: return None
        chain = tk.option_chain(match[0])
        puts = chain.puts
        otm_puts = puts[puts['strike'] < current_price]
        if otm_puts.empty: return None
        avg_iv = otm_puts['impliedVolatility'].median()
        dte = max((datetime.strptime(match[0], '%Y-%m-%d') - datetime.now()).days, 1)
        T, r = dte / 365.0, 0.04  
        puts['delta'] = puts.apply(lambda row: calculate_delta(current_price, row['strike'], T, r, avg_iv), axis=1)
        puts['delta_diff'] = (puts['delta'] - target_delta).abs()
        best_put = puts.sort_values('delta_diff').iloc[0]
        premium = (best_put['bid'] + best_put['ask']) / 2
        roi = (premium / best_put['strike']) * 100
        aor = roi * (365 / dte)
        return {"Strike": best_put['strike'], "Premium": f"${premium:.2f}", "ROI": f"{roi:.2f}%", "AOR": f"{aor:.1f}%"}
    except: return None

# ========================================================
# ⚡ CACHED ANALYSIS ENGINE (Fixes Cloud Timeouts)
# ========================================================
@st.cache_data(ttl=3600, show_spinner=False)
def analyze_stock_full(symbol, target_expiry):
    try:
        tk = yf.Ticker(symbol)
        # Use a longer period to ensure we get enough data for Moving Averages
        hist_1y = tk.history(period="2y") 
        
        if hist_1y.empty or len(hist_1y) < 10: 
            return None
        
        close = hist_1y['Close']
        curr_p, prev_p = close.iloc[-1], close.iloc[-2]
        info = tk.info if tk.info else {}

        # --- 1. TECHNICAL INDICATORS ---
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_status = "▲" if macd.iloc[-1] > signal_line.iloc[-1] else "▼"
        
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        lower_bb = sma20 - (std20 * 2)
        upper_bb = sma20 + (std20 * 2)
        bb_status = "MID"
        if curr_p <= lower_bb.iloc[-1]: bb_status = "🟢LOW"
        elif curr_p >= upper_bb.iloc[-1]: bb_status = "🔴UPR"
        
        tech_alert = f"{macd_status} | {bb_status}"

        # --- 2. MOVING AVERAGES (Safety Logic Included) ---
        ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else 0
        ma100 = close.rolling(100).mean().iloc[-1] if len(close) >= 100 else 0
        ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else 0
        
        def format_ma(p, ma, color):
            if ma == 0: return "N/A"
            if abs(p - ma) / ma <= 0.015: 
                return f"<span style='color:{color}; font-weight:bold; border-bottom:2px solid {color}'>${ma:.1f}</span>"
            return f"${ma:.1f}"
        ma_display = f"{format_ma(curr_p, ma50, '#3b82f6')} | {format_ma(curr_p, ma100, '#f59e0b')} | {format_ma(curr_p, ma200, '#10b981')}"

        # --- 3. EARNINGS (Wrapped in Try/Except) ---
        earn_date_str, earn_alert = "N/A", "🟢"
        try:
            earn_dates = tk.get_earnings_dates(limit=1)
            if earn_dates is not None and not earn_dates.empty:
                dt = earn_dates.index[0].to_pydatetime().replace(tzinfo=None)
                days_left = (dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
                earn_date_str = dt.strftime('%m-%d')
                earn_alert = f"🔴 ({days_left}d)" if days_left < 14 else f"🟢 ({days_left}d)"
        except: pass

        # --- 4. RSI & FINANCIAL HEALTH ---
        rsi_val = calculate_rsi(close).iloc[-1]
        rsi_display = f"<span style='color:{('#ff3131' if rsi_val > 70 else '#00ff41' if rsi_val < 30 else '#ffffff')}; font-weight:bold;'>{rsi_val:.1f}</span>"

        # Health Logic
        rev_v, ni_v, fcf_v, al_v = "🟡", "🟡", "🟡", "🟡"
        try:
            inc = tk.quarterly_financials
            cf = tk.quarterly_cashflow
            rev_v = "✅" if inc.loc['Total Revenue'].iloc[0] > inc.loc['Total Revenue'].iloc[4] else "❌"
            ni_v = "✅" if inc.loc['Net Income'].iloc[0] > 0 else "❌"
            fcf_v = "✅" if cf.loc['Free Cash Flow'].iloc[0] > 0 else "❌"
            al_v = "✅" if info.get('currentRatio', 0) > 1.1 else "❌"
        except: pass

        score = int(([rev_v, ni_v, fcf_v, al_v].count("✅") / 4) * 100)
        s_clr = "#008f39" if score >= 75 else "#f97316" if score >= 50 else "#b22222"
        score_html = f"<span class='h-score' style='background-color: {s_clr}'>{score}</span>"

        # --- 5. SIGNAL & OPTIONS ---
        roe = info.get('returnOnEquity', 0) * 100
        eps = info.get('trailingEps', 0)
        high_52 = close.max()
        uw = ((curr_p - high_52) / high_52) * 100
        chg_p = ((curr_p - prev_p) / prev_p) * 100
        
        opt = get_best_put_by_delta(tk, target_expiry, curr_p)
        action = "<span class='csp-strong'>STRONG CSP</span>" if (uw < -15 and roe > 8 and fcf_v == "✅") else "NEUTRAL"
        
        c_class = 'pos' if (curr_p - prev_p) >= 0 else 'neg'
        chg_display = f"<span class={c_class}>{(curr_p - prev_p):+.2f} ({chg_p:+.2f}%)</span>"

        return {
            "Ticker": f"<b>{symbol}</b>", 
            "Price": f"<span class='price-font'>${curr_p:.2f}</span>",
            "Change (%)": chg_display,
            "50|100|200 MA": ma_display,
            "Earn Date": earn_date_str,
            "Earn Alert": earn_alert,
            "Tech (MACD|BB)": tech_alert,
            "Signal": action, 
            "RSI": rsi_display,
            "Score": score_html, 
            "Rev": rev_v, "Inc": ni_v, "Cash": fcf_v, "Solv": al_v,
            "Strike (.30Δ)": f"${opt['Strike']:.1f}" if opt else "N/A",
            "Premium": opt['Premium'] if opt else "N/A", 
            "ROI | AOR": f"<b>{opt['ROI']} | {opt['AOR']}</b>" if opt else "N/A",
            "UW %": f"{uw:.1f}%",
            "ROE": f"{roe:.1f}%",
            "EPS": f"${eps:.2f}"
        }
    except Exception as e:
        return None

WATCHLIST_URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=337359953"

@st.cache_data(ttl=600)
def load_watchlist_data():
    try:
        response = requests.get(WATCHLIST_URL, verify=False, timeout=10)
        df = pd.read_csv(io.BytesIO(response.content))
        df.columns = df.columns.str.strip()
        df_clean = df.dropna(subset=[df.columns[0]]).copy()
        df_clean = df_clean.rename(columns={df.columns[0]: 'Stock', df.columns[1]: 'Stock Type'})
        df_clean['Stock'] = df_clean['Stock'].astype(str).str.strip().str.upper()
        return df_clean[['Stock', 'Stock Type']]
    except: return pd.DataFrame(columns=['Stock', 'Stock Type'])

def get_detailed_health_grid(symbol):
    try:
        tk = yf.Ticker(symbol)
        inc, bal, cf = tk.quarterly_financials, tk.quarterly_balance_sheet, tk.quarterly_cashflow
        health_data = []
        cols = inc.columns[:8]
        for i in range(len(cols)):
            date = cols[i]
            rev = inc.loc['Total Revenue', date] if 'Total Revenue' in inc.index else 0
            rev_up = "✅"
            if i < len(cols) - 1:
                prev_rev = inc.loc['Total Revenue', cols[i+1]] if 'Total Revenue' in inc.index else 0
                rev_up = "✅" if rev > prev_rev else "❌"
            ni = inc.loc['Net Income', date] if 'Net Income' in inc.index else 0
            fcf = cf.loc['Free Cash Flow', date] if 'Free Cash Flow' in cf.index else 0
            asst = bal.loc['Total Assets', date] if 'Total Assets' in bal.index else 0
            liab = bal.loc['Total Liabilities Net Minority Interest', date] if 'Total Liabilities Net Minority Interest' in bal.index else 1
            health_data.append({
                "QUARTER": date.strftime('%Y-%m'), "REVENUE UP": rev_up, "INCOME > 0": "✅" if ni > 0 else "❌",
                "CASH FLOW > 0": "✅" if fcf > 0 else "❌", "ASSET > LIAB": "✅" if asst > liab else "❌",
                "REVENUE": f"${rev/1e9:.2f}B", "NET INCOME": f"${ni/1e9:.2f}B"
            })
        return pd.DataFrame(health_data)
    except: return None

def get_all_fridays():
    fridays = []
    current_date = datetime.now()
    for _ in range(365):
        if current_date.weekday() == 4:
            fridays.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)
    return fridays

# ========================================================
# 🚀 APP EXECUTION
# ========================================================
df_wl = load_watchlist_data()

if not df_wl.empty:
    with st.expander("🛠️ Analysis Configuration", expanded=True):
        c1, c2, c3, c4 = st.columns([0.4, 1, 0.4, 0.4])
        with c1: 
            sel_types = st.multiselect("Filter Sector", sorted(df_wl['Stock Type'].unique()))
        with c2:
            all_ticks = df_wl[df_wl['Stock Type'].isin(sel_types)]['Stock'] if sel_types else df_wl['Stock']
            sel_stocks = st.multiselect("Select Tickers", sorted(all_ticks.unique()))
        with c3:
            expiry_list = get_all_fridays()
            selected_expiry = st.selectbox("Target Expiry", expiry_list)
        with c4:
            run_analysis = st.button("🚀 RUN ANALYSIS")

    status_placeholder = st.empty()
    progress_placeholder = st.empty()
    table_placeholder = st.empty()

    if run_analysis:
        st.session_state.last_results = [] 
        p_bar = progress_placeholder.progress(0)
        to_scan = sel_stocks if sel_stocks else all_ticks.tolist()
        to_scan = [t for t in to_scan if t.upper() != "CASH"] 
        
        for i, t in enumerate(to_scan):
            status_placeholder.markdown(f"🔍 **Scanning:** `{t}` | {i+1}/{len(to_scan)}")
            res = analyze_stock_full(t, selected_expiry)
            if res:
                st.session_state.last_results.append(res)
                table_placeholder.markdown(styled_table(pd.DataFrame(st.session_state.last_results)), unsafe_allow_html=True)
            
            # Small jitter delay to look more human and avoid IP blocking on Cloud
            time.sleep(random.uniform(0.3, 0.8))
            p_bar.progress((i + 1) / len(to_scan))
        
        status_placeholder.empty()
        progress_placeholder.empty()

    if "last_results" in st.session_state and st.session_state.last_results:
        table_placeholder.markdown(styled_table(pd.DataFrame(st.session_state.last_results)), unsafe_allow_html=True)
        st.divider()
        with st.expander("🔍 Financial Health Drilldown", expanded=False):
            st.write("Click a ticker to view the 8-Quarter breakdown.")
            cols = st.columns(10)
            for i, r in enumerate(st.session_state.last_results):
                raw_t = r['Ticker'].replace("<b>", "").replace("</b>", "")
                if cols[i % 10].button(f"📊 {raw_t}", key=f"btn_{raw_t}"):
                    st.session_state.active_health = raw_t
            if "active_health" in st.session_state:
                target = st.session_state.active_health
                detailed_df = get_detailed_health_grid(target)
                if detailed_df is not None:
                    st.markdown(f"### 🏢 {target} Quarterly Health Metrics")
                    st.markdown(styled_table(detailed_df), unsafe_allow_html=True)