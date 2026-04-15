import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import io
import calendar
from datetime import datetime, timedelta
from scipy.stats import norm
from scipy.optimize import brentq
import math

# =========================
# 🎨 MEANINGFUL COLOR VARIABLES
# =========================
ACTION_BUTTON_BG = "#05081D"
SCAN_COUNT_BADGE_BG = "#0b3e17"
WARNING_FLASH_TEXT = "#cc5353"
WARNING_FLASH_BG = "#fff5f5"
WARNING_FLASH_BORDER = "#feb2b2"
EXPANDER_BORDER = "#b1b5ba"
EXPANDER_BG = "#ffffff"
HEADER_TEXT_GREY = "#4a5568"

TABLE_HEADER_GRADIENT_TOP = "#f8fafc"
TABLE_HEADER_GRADIENT_BOTTOM = "#f1f5f9"
TABLE_HEADER_TEXT = "#1f2937"
TABLE_HEADER_BORDER_BOTTOM = "#e5e7eb"

BEST_ROW_TEXT = "#16a34a"
SAFE_ROW_TEXT = "#2563eb"
AGGR_ROW_TEXT = "#ca8a04"

SLIDER_GRADIENT_START = "#16a34a" 
SLIDER_GRADIENT_MID = "#facc15"    
SLIDER_GRADIENT_END = "#dc2626"    
SLIDER_AVG_MARKER = "#2563eb"     
SLIDER_BG_BORDER = "#e2e8f0"
SLIDER_LABEL_GREY = "#64748b"

RANK_BUY_BG = "#dcfce7"
RANK_BUY_TEXT = "#166534"
RANK_HOLD_BG = "#fef3c7"
RANK_HOLD_TEXT = "#92400e"
RANK_SELL_BG = "#fee2e2"
RANK_SELL_TEXT = "#991b1b"

# =========================
# 🎨 STYLING & CONFIG
# =========================
st.set_page_config(layout="wide", page_title="Options Scanner")

st.markdown(f"""
<style>
    /* Fix: Align all input widgets (Selectbox, Number, Text) to the bottom of the row */
    [data-testid="column"] {{
        display: flex;
        align-items: flex-end;
    }}

    /* Standardize heights for all input types */
    .stSelectbox, .stNumberInput, .stTextInput {{
        width: 100%;
        margin-bottom: 0px !important;
    }}

    .stExpander {{ border: 1px solid {EXPANDER_BORDER}; border-radius: 8px; background-color: {EXPANDER_BG}; margin-bottom: 8px; }}
    
    div.stButton > button:first-child {{ 
        background-color: {ACTION_BUTTON_BG}; 
        color: white; 
        border-radius: 8px; 
        height: 3rem; /* Matches input height better */
    }}
    
    .result-badge {{ background-color: {SCAN_COUNT_BADGE_BG}; color: white; padding: 8px 16px; border-radius: 8px; font-weight: bold; text-align: center; }}
    .header-info {{ color: {HEADER_TEXT_GREY}; font-size: 0.9rem; font-weight: bold; margin-bottom: 5px; margin-top: 10px; }}
    
    @keyframes blinker {{ 50% {{ opacity: 0.2; }} }}
    .flash-warning {{ color: {WARNING_FLASH_TEXT}; font-weight: bold; animation: blinker 2s linear infinite; padding: 10px; background-color: {WARNING_FLASH_BG}; border-radius: 5px; border: 1px solid {WARNING_FLASH_BORDER}; margin-bottom: 10px; }}
    
    table thead tr th {{
        background: linear-gradient(145deg, {TABLE_HEADER_GRADIENT_TOP}, {TABLE_HEADER_GRADIENT_BOTTOM}) !important;
        color: {TABLE_HEADER_TEXT} !important;
        font-weight: 700 !important;
        border-bottom: 2px solid {TABLE_HEADER_BORDER_BOTTOM} !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), inset 0 -1px 0 rgba(0,0,0,0.6), 0 2px 4px rgba(0,0,0,0.25);
        border-radius: 6px !important;
    }}
</style>
""", unsafe_allow_html=True)

# =========================
# 📅 UTILS & LOGIC
# =========================
def get_third_friday(year, month):
    c = calendar.monthcalendar(year, month)
    first_week = c[0]
    second_week = c[1]
    third_week = c[2]
    fourth_week = c[3]
    if first_week[calendar.FRIDAY]:
        friday_date = third_week[calendar.FRIDAY]
    else:
        friday_date = fourth_week[calendar.FRIDAY]
    return datetime(year, month, friday_date)

def get_default_expiry():
    now = datetime.now()
    this_month_friday = get_third_friday(now.year, now.month)
    if now.date() >= this_month_friday.date():
        next_month = now.month + 1 if now.month < 12 else 1
        next_year = now.year if now.month < 12 else now.year + 1
        return get_third_friday(next_year, next_month).strftime('%Y-%m-%d')
    return this_month_friday.strftime('%Y-%m-%d')

def get_all_fridays_3_months():
    fridays = []
    curr = datetime.now()
    curr += timedelta(days=(4 - curr.weekday() + 7) % 7)
    end_date = datetime.now() + timedelta(days=90)
    while curr <= end_date:
        fridays.append(curr.strftime('%Y-%m-%d'))
        curr += timedelta(weeks=1)
    return fridays

def style_liquidity(column):
    is_max = column == column.max()
    return ['background-color: rgba(37, 99, 235, 0.2); font-weight: bold' if v else '' for v in is_max]

def get_institutional_sentiment(stock):
    try:
        opt_dates = stock.options
        if not opt_dates:
            return 1.0, "Neutral", 0, "Neutral"
        
        chain = stock.option_chain(opt_dates[0])

        call_vol = chain.calls['volume'].sum()
        put_vol = chain.puts['volume'].sum()

        ratio = put_vol / call_vol if call_vol > 0 else 1.0

        if ratio < 0.75:
            sentiment = "Bullish"
        elif ratio > 1.1:
            sentiment = "Bearish"
        else:
            sentiment = "Neutral"

        unusual_calls = chain.calls[chain.calls['volume'] > (chain.calls['openInterest'] * 2)]
        unusual_puts  = chain.puts[chain.puts['volume'] > (chain.puts['openInterest'] * 2)]

        unusual_total = len(unusual_calls) + len(unusual_puts)

        if len(unusual_calls) > len(unusual_puts):
            flow_dir = "Bullish"
        elif len(unusual_puts) > len(unusual_calls):
            flow_dir = "Bearish"
        else:
            flow_dir = "Neutral"

        return ratio, sentiment, unusual_total, flow_dir
    except:
        return 1.0, "Neutral", 0, "Neutral"

def highlight_rows(row, b_idx, p_idx, s_idx):
    style = [''] * len(row)
    if row.name == b_idx:
        style = ['color: #16a34a; font-weight: 600'] * len(row)
    elif row.name == p_idx:
        style = ['color: #ca8a04; font-weight: 600'] * len(row)
    elif row.name == s_idx:
        style = ['color: #2563eb; font-weight: 600'] * len(row)

    for i, col in enumerate(row.index):
        if col in ['ROI%', 'AOR%']:
            style[i] += '; font-weight: 700'
    return style

def get_next_earnings_robust(ticker_obj):
    try:
        cal = ticker_obj.calendar
        if cal is not None and isinstance(cal, pd.DataFrame) and not cal.empty:
            return cal.iloc[0, 0].strftime('%Y-%m-%d')
        ed = ticker_obj.earnings_dates
        if ed is not None and not ed.empty:
            future = ed.index[ed.index > pd.Timestamp.now(tz='UTC')]
            if not future.empty: return future[0].strftime('%Y-%m-%d')
    except: pass
    return "N/A"

@st.cache_data(ttl=3600)
def get_tickers(market_name, url):
    try:
        if market_name == "My Watchlist":
            response = requests.get(url, verify=False, timeout=10)
            df = pd.read_csv(io.BytesIO(response.content))
            tickers = df.iloc[:,0].dropna().astype(str).str.strip().str.upper().tolist()
            return {t: i+1 for i, t in enumerate(tickers)}
            
        df = pd.read_html(requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text)[0]
        df['Symbol'] = df['Symbol'].str.replace('.', '-', regex=False)
        return {row['Symbol']: i+1 for i, row in df.iterrows()}
    except: return {}

def bs_metrics(S, K, T, r, sigma, option_type='put'):
    if T <= 0: return 0.0, 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == 'put':
        delta = -norm.cdf(-d1)
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    else:
        delta = norm.cdf(d1)
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return price, delta

def find_iv_and_delta(mkt_px, S, K, T, r, opt_type):
    if mkt_px <= 0.005 or T <= 0: return 0.01, 0.0
    try:
        iv = brentq(lambda sig: bs_metrics(S, K, T, r, sig, opt_type)[0] - mkt_px, 0.0001, 4.0, xtol=1e-5)
        _, delta = bs_metrics(S, K, T, r, iv, opt_type)
        return iv, delta
    except: return 0.01, 0.0

# =========================
# 🏗️ UI SETUP
# =========================
index_map = {
    "S&P 500": "https://www.slickcharts.com/sp500", 
    "Nasdaq 100": "https://www.slickcharts.com/nasdaq100",
    "My Watchlist": "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=337359953"
}
friday_range = get_all_fridays_3_months()
default_exp = get_default_expiry()
if default_exp not in friday_range: friday_range.insert(0, default_exp)

with st.expander("🛠️ Scanner Filters", expanded=True):
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: selected_index = st.selectbox("📊 Market", list(index_map.keys()))
    with c2: strategy_main = st.selectbox("🎯 Strategy", ["CSP (Puts)", "CC (Calls)"])
    with c3: scan_expiry = st.selectbox("📅 Expiry", friday_range, index=friday_range.index(default_exp))
    with c4: scan_depth = st.selectbox("🔍 Depth", [5, 10, 20, 50, 100, 250, 500], index=2)
    with c5: max_px = st.number_input("💰 Max $", value=400, step=25)

    c5b, c6, c7, c8, c9 = st.columns([1.2, 1, 1, 1, 1])
    with c5b:
        manual_input_raw = st.text_input("🎯 Manual Tickers (CSV)", value="")
        manual_tkr_list = [t.strip().upper() for t in manual_input_raw.split(",") if t.strip()]
    with c6: min_roi = st.number_input("📈 Min ROI%", value=2.0, step=0.1)
    with c7: min_iv = st.number_input("⚡ Min IV%", value=35, step=1)
    with c8: min_vol = st.number_input("📦 Min Volume", value=100, step=50)
    with c9: min_div = st.number_input("💵 Min Dividend %", value=0.0, step=0.1)

btn_col, count_col = st.columns([4, 1])
with btn_col: run_scan = st.button(f"🚀 Scan {selected_index}", use_container_width=True)
with count_col:
    count_placeholder = st.empty()
    count_placeholder.markdown(f'<div class="result-badge">Found: 0</div>', unsafe_allow_html=True)

if run_scan:
    ticker_rank_map = get_tickers(selected_index, index_map[selected_index])
    
    if manual_tkr_list:
        tickers = manual_tkr_list
        for t in tickers:
            if t not in ticker_rank_map:
                ticker_rank_map[t] = "Manual"
    else:
        tickers = list(ticker_rank_map.keys())[:scan_depth]

    results_count = 0
    pb = st.progress(0)
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    main_opt_type = 'put' if "CSP" in strategy_main else 'call'
    
    scan_dt = datetime.strptime(scan_expiry, "%Y-%m-%d").replace(hour=16, minute=0)
    t_yrs_scan = max(1, (scan_dt - now).total_seconds() / 60) / 525600.0

    # ==========================================
    # 🐛 ON-SCREEN DEBUGGER EXPANDER
    # ==========================================
    with st.expander("🐛 Live Scan Debugger Logs", expanded=True):
        st.write(f"Total Tickers Pulled to Scan: {len(tickers)}")
        
        for i, tkr in enumerate(tickers):
            try:
                stock = yf.Ticker(tkr)
                px = stock.fast_info['lastPrice']
                
                if px > max_px:
                    st.write(f"❌ {tkr} skipped: Price ${px:.2f} exceeds Max ${max_px}")
                    continue
                
                tkr_options = stock.options
                if scan_expiry not in tkr_options:
                    st.write(f"❌ {tkr} skipped: Expiry date {scan_expiry} not available in options chain.")
                    continue
                
                mkt_rank = ticker_rank_map.get(tkr, "N/A")

                info = stock.info
                company = info.get('shortName') or tkr
                div = info.get('dividendRate', 0.0) or 0.0
                div_yield = (div / px) * 100 if px > 0 else 0.0
                
                if div_yield < min_div:
                    st.write(f"❌ {tkr} skipped: Dividend Yield {div_yield:.2f}% is below Min {min_div}%")
                    continue
                    
                eps = info.get('trailingEps', 0.0)
                pe = info.get('trailingPE', 0.0)
                low_target = info.get('targetLowPrice', px * 0.8)
                avg_target = info.get('targetMeanPrice', px)
                high_target = info.get('targetHighPrice', px * 1.2)
                rec_key = info.get('recommendationKey', 'N/A').replace('_', ' ').title()
                upside = ((avg_target / px) - 1) * 100 if avg_target > 0 else 0

                chain = stock.option_chain(scan_expiry).puts if main_opt_type == 'put' else stock.option_chain(scan_expiry).calls
                valid_chain = chain[(chain['strike'] < px if main_opt_type == 'put' else chain['strike'] > px) & (chain['volume'] >= min_vol)].copy()
                
                if valid_chain.empty:
                    st.write(f"❌ {tkr} skipped: No options found with volume >= {min_vol}")
                    continue
                
                potential = []
                for _, row in valid_chain.iterrows():
                    bid_p = float(row['bid'])
                    iv, delta = find_iv_and_delta(bid_p, px, float(row['strike']), t_yrs_scan, 0.043, main_opt_type)
                    if (main_opt_type == 'put' and delta > -0.45) or (main_opt_type == 'call' and delta < 0.45):
                        potential.append({'strike': float(row['strike']), 'bid': bid_p, 'iv': float(iv), 'delta': float(delta)})
                
                if not potential:
                    st.write(f"❌ {tkr} skipped: No options in chain met Delta thresholds.")
                    continue
                    
                best = sorted(potential, key=lambda x: abs(x['delta'] - (-0.35 if main_opt_type == 'put' else 0.35)))[0]
                roi = (best['bid'] / (best['strike'] if main_opt_type == 'put' else px)) * 100
                
                if roi < min_roi:
                    st.write(f"❌ {tkr} skipped: ROI {roi:.2f}% is below Min {min_roi}%")
                    continue
                if (best['iv'] * 100) < min_iv:
                    st.write(f"❌ {tkr} skipped: IV {best['iv']*100:.2f}% is below Min {min_iv}%")
                    continue

                # If it makes it past everything above, it is a hit
                st.write(f"⭐ **{tkr} PASSED ALL FILTERS** (ROI: {roi:.2f}%, IV: {best['iv']*100:.2f}%)")
                
                # --- Keep original processing to build cards below the debugger logs ---
                results_count += 1
                count_placeholder.markdown(f'<div class="result-badge">Found: {results_count}</div>', unsafe_allow_html=True)
                earn_dt = get_next_earnings_robust(stock)

                days = 30
                exp_move = px * best['iv'] * math.sqrt(days / 365)
                upside_1m = (exp_move / px) * 100

                pc_ratio, sentiment_label, unusual_hits, flow_dir = get_institutional_sentiment(stock)
                unusual_alert = "🔥 HEAVY FLOW" if unusual_hits > 3 else ""

                try:
                    fin = stock.financials.T
                    qfin = stock.quarterly_financials.T
                    if len(fin) >= 2:
                        rev_y1 = fin.iloc[0].get('Total Revenue', 0)
                        rev_y2 = fin.iloc[1].get('Total Revenue', 0)
                        yoy_ok = rev_y1 >= rev_y2
                    else:
                        yoy_ok = True

                    if len(qfin) >= 3:
                        q1 = qfin.iloc[0].get('Total Revenue', 0)
                        q2 = qfin.iloc[1].get('Total Revenue', 0)
                        q3 = qfin.iloc[2].get('Total Revenue', 0)
                        qoq_ok = (q1 >= q2 >= q3)
                    else:
                        qoq_ok = True
                    rev_ok = yoy_ok or qoq_ok
                except:
                    rev_ok = True

                pm = info.get('profitMargins') or 0
                earn_ok = ((info.get('trailingEps') or 0) > 0 and pm > 0.05)
                cf_ok = (info.get('freeCashflow') or 0) > 0

                debt = info.get('debtToEquity') or 0
                debt_ok = debt < 150
                trend_12m = info.get('52WeekChange') or 0
                trend_ok = trend_12m > -0.30
                roe = info.get('returnOnEquity') or 0
                roe_ok = roe > 0.10
                iv_ok = 20 <= (best['iv'] * 100) <= 70

                checks = [rev_ok, earn_ok, cf_ok, debt_ok, trend_ok, iv_ok, roe_ok]
                score = sum(checks)
                ratio = score / len(checks)

                if ratio >= 0.85: verdict = "🟢 Stable"
                elif ratio >= 0.6: verdict = "🟡 OK"
                else: verdict = "🔴 Avoid"

                aor_val = roi / (t_yrs_scan if t_yrs_scan > 0 else 0.001)
                is_urgent = (earn_dt != "N/A" and 0 <= (datetime.strptime(earn_dt, "%Y-%m-%d") - now).days <= 30)
                earn_display = f" 🔴**{earn_dt}**🔴" if is_urgent else f" 📅 {earn_dt}"
                rank_emoji = "🟢🟢" if "Strong Buy" in rec_key else "🟢" if "Buy" in rec_key else "🟡" if "Hold" in rec_key else "🔴"
                rank_display = f"{rank_emoji} {rec_key} ({upside:.1f}%)"
                flow_text = " ⚡ Heavy Flow" if unusual_hits > 3 else ""
                clean_label = sentiment_label.replace("🐂", "").replace("🐻", "").replace("↔️", "").strip()
                sent_emoji = "⬆️" if "Bullish" in clean_label else "⬇️" if "Bearish" in clean_label else "➡️"
                sent_display = f"{sent_emoji} {clean_label} ({pc_ratio:.2f})"
                
                hist_1m = stock.history(period="1mo")
                m_high = hist_1m['High'].max()
                dist_to_high = ((m_high - px) / px) * 100

                header_label = (
                    f"#{mkt_rank} | 📈 {tkr} | 💰 ${px:.0f} (1M Hi: ${m_high:.2f} | Gap: {dist_to_high:.1f}%) | 🎯 {best['strike']:.0f} | "
                    f"ROI {roi:.1f}% | AOR {aor_val:.0f}% | "
                    f"{sent_display} {flow_text} {rank_display} | 📅 {earn_dt}"
                )

                with st.expander(header_label, expanded=False):
                    roi_color = "#16a34a" if roi > 2 else "#facc15" if roi > 1 else "#dc2626"
                    st.markdown(f"""
                        <div style="font-size:0.95rem; font-weight:600; margin-bottom:4px;">
                        📈 <a href="https://finance.yahoo.com/quote/{tkr}/" target="_blank" style="text-decoration:none; color:#1f2937;"><b>{company}</b></a>
                        &nbsp;&nbsp; |&nbsp;
                        <span style="color:{roi_color}; font-weight:700;">ROI {roi:.2f}%</span> &nbsp;|&nbsp;
                        <span style="color:#2563eb; font-weight:700;">Sent: {sentiment_label} ({pc_ratio:.2f})</span> &nbsp;|&nbsp;
                        <span style="color:#dc2626; font-weight:700;">{unusual_alert}</span> &nbsp;|&nbsp;
                        <b>P/E {pe:.2f}</b> &nbsp;|&nbsp;
                        📅 {earn_dt}
                        </div>
                        """, unsafe_allow_html=True)

                    if is_urgent: 
                        st.markdown(f"<div class='flash-warning'>🚨 WARNING: Earnings approaching on {earn_dt}</div>", unsafe_allow_html=True)
                    
                    status_icon = lambda x: "✅" if x else "❌"
                    score_color = "#16a34a" if score >= 6 else "#facc15" if score >= 4 else "#dc2626"
                    st.markdown(f"""
                    | Metric Row | Rev | Earn | CF | Debt | Trend | IV | Score | Verdict |
                    |------------|-----|------|----|------|-------|----|-------|---------|
                    | Status     | {status_icon(rev_ok)} | {status_icon(earn_ok)} | {status_icon(cf_ok)} | {status_icon(debt_ok)} | {status_icon(trend_ok)} | {status_icon(iv_ok)} | **<span style="color:{score_color}">{score}/{len(checks)}</span>** | {verdict} |
                    """, unsafe_allow_html=True)

                    # Price Target Visual
                    range_w = high_target - low_target
                    curr_p = max(0, min(100, ((px - low_target) / range_w) * 100)) if range_w > 0 else 50
                    avg_p = max(0, min(100, ((avg_target - low_target) / range_w) * 100)) if range_w > 0 else 50

                    st.markdown(f'''
                        <div style="display:flex;align-items:center;gap:10px;background:white;padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:6px;">
                        <div style="flex:1.8;position:relative;height:10px;background:linear-gradient(to right,#16a34a,#facc15,#dc2626);border-radius:5px;border:1px solid #e2e8f0;margin:10px 3px;">
                        <div style="position:absolute;left:0;top:-14px;font-size:0.75rem;color:#000;font-weight:700;">L: ${low_target:.0f}</div>
                        <div style="position:absolute;right:0;top:-14px;font-size:0.75rem;color:#000;font-weight:700;">H: ${high_target:.0f}</div>
                        <div style="position:absolute;left:{avg_p}%;top:-5px;transform:translateX(-50%);height:18px;width:2px;background:#2563eb;">
                        <div style="position:absolute;top:-14px;transform:translateX(-50%);font-size:0.7rem;font-weight:700;color:#000;">⭐ ${avg_target:.0f}</div>
                        </div>
                        <div style="position:absolute;left:{curr_p}%;top:-2px;transform:translateX(-50%);">
                        <div style="width:6px;height:6px;background:{'#16a34a' if curr_p < 30 else '#facc15' if curr_p < 60 else '#dc2626'};border-radius:50%;margin:0 auto;"></div>
                        <div style="background:{'#16a34a' if curr_p < 30 else '#facc15' if curr_p < 60 else '#dc2626'};color:white;padding:0 3px;border-radius:3px;font-weight:700;font-size:0.6rem;margin-top:1px;">${px:.1f}</div>
                        </div>
                        </div>
                        <div style="flex:2.5;display:flex;justify-content:space-around;font-size:0.7rem;border-left:1px solid #f1f5f9;padding-left:6px;">
                        <div style="text-align:center;"><b>UP</b><br><span style="color:{'#16a34a' if upside>20 else '#facc15' if upside>5 else '#dc2626'};">{upside:+.1f}%</span></div>
                        <div style="text-align:center;"><b>RANK</b><br><span style="background:{'#dcfce7' if 'Buy' in rec_key else '#fef3c7' if 'Hold' in rec_key else '#fee2e2'};color:{'#166534' if 'Buy' in rec_key else '#92400e' if 'Hold' in rec_key else '#991b1b'};padding:1px 4px;border-radius:3px;font-size:0.6rem;font-weight:700;">{rec_key}</span></div>
                        </div>
                        </div>
                        ''', unsafe_allow_html=True)               

                    tab_csp, tab_cc = st.tabs(["🛡️ CSP (Puts)", "📦 CC (Calls)"])
                    for current_tab, o_type in [(tab_csp, 'put'), (tab_cc, 'call')]:
                        with current_tab:
                            valid_expiries = [e for e in tkr_options if today_str <= e <= scan_expiry and datetime.strptime(e, "%Y-%m-%d").weekday() == 4]
                            display_expiries = valid_expiries[::-1] 

                            for f_exp in display_expiries:
                                try:
                                    f_chain = stock.option_chain(f_exp).puts if o_type == 'put' else stock.option_chain(f_exp).calls
                                    drill = f_chain[f_chain['strike'] <= px if o_type == 'put' else f_chain['strike'] >= px].sort_values('strike', ascending=(o_type=='call')).head(10).copy()
                                    f_t_yrs = (datetime.strptime(f_exp, "%Y-%m-%d").replace(hour=16) - now).total_seconds() / 31536000.0
                                    
                                    m_list = [find_iv_and_delta(r['bid'], px, r['strike'], f_t_yrs, 0.043, o_type) for _, r in drill.iterrows()]
                                    drill['ROI%'] = (drill['bid'] / (drill['strike'] if o_type == 'put' else px)) * 100
                                    drill['AOR%'] = drill['ROI%'] / (f_t_yrs if f_t_yrs > 0 else 0.001)
                                    drill['Delta'] = [m[1] for m in m_list]
                                    drill['IV%'] = [m[0]*100 for m in m_list]
                                    drill = drill.rename(columns={'openInterest': 'OI'})

                                    target = -0.30 if o_type == 'put' else 0.30
                                    drill['DeltaScore'] = abs(drill['Delta'] - target)

                                    b_idx = drill.sort_values(['DeltaScore', 'ROI%'], ascending=[True, False]).index[0]
                                    s_idx = (drill['Delta'] - (target * 0.6)).abs().idxmin()
                                    p_idx = drill['ROI%'].idxmax()

                                    def classify_row(idx):
                                        if idx == b_idx: return f"🎯 {tkr}"
                                        elif idx == s_idx: return f"🟢 {tkr}"
                                        elif idx == p_idx: return f"🚀 {tkr}"
                                        return tkr

                                    drill['TYPE'] = [classify_row(i) if classify_row(i) != "" else tkr for i in drill.index]
                                    
                                    best_row = drill.loc[b_idx]

                                    st.markdown(f"""
                                    <div class="header-info">
                                    📅 Friday Expiry: {f_exp} &nbsp;&nbsp; | &nbsp;&nbsp;
                                    🎯 Best Strike: <b>{best_row['strike']:.0f}</b> &nbsp;&nbsp; | &nbsp;&nbsp;
                                    📊 ROI: <b>{best_row['ROI%']:.2f}%</b>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    styled_df = drill[['TYPE','strike','bid','ask','ROI%','AOR%','Delta','IV%','volume','OI']]\
                                        .style.apply(highlight_rows, axis=1, args=(b_idx, p_idx, s_idx))\
                                        .apply(style_liquidity, subset=['volume', 'OI'])\
                                        .format(precision=2)\
                                        .hide(axis="index")

                                    st.markdown(styled_df.to_html(index=False), unsafe_allow_html=True)
                                except: continue
                
            except Exception as e:
                st.error(f"⚠️ Error processing {tkr}: {e}")
                continue
                
            pb.progress((i + 1) / len(tickers))