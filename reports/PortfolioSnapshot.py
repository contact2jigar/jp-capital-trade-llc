import streamlit as st
import yfinance as yf
from datetime import datetime

from reports.engine import *
from reports.ScanResults import render_scan_results

@st.cache_data(ttl=300)
def get_market_data():
    data = {}
    for ticker in ["SPY", "QQQ", "^VIX"]:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            current = hist["Close"].iloc[-1]

            if ticker != "^VIX":
                start_year = hist[hist.index >= f"{datetime.now().year}-01-01"]
                ytd = ((current - start_year["Close"].iloc[0]) / start_year["Close"].iloc[0]) * 100 if not start_year.empty else 0
            else:
                ytd = 0  # VIX no YTD needed

            data[ticker] = {"price": current, "ytd": ytd}
        except:
            data[ticker] = {"price": 0, "ytd": 0}
    return data

def render_portfolio_snapshot(df_raw, load_balances):

    # =========================================================
    # 🔥 TOP PROGRESS BAR (Absolute Top of Page)
    # =========================================================
    top_progress_placeholder = st.empty()

    # =========================================================
    # 💰 LOAD BALANCES
    # =========================================================
    bal_df = load_balances()

    def get_val(label):
        try:
            return float(bal_df[bal_df['Account'] == label]['Balance'].values[0])
        except:
            return 0.0

    if not bal_df.empty:
        llc_c = get_val("LLC - Current")
        ira_c = get_val("IRA - Current")
        k401_c = get_val("401 - Current")

        llc_i = get_val("LLC - Initial")
        ira_i = get_val("IRA - Initial")
        k401_i = get_val("401 - Initial")

        k401_target = get_val("401 - 2026 Target")
    else:
        llc_c = ira_c = k401_c = k401_target = 0.0
        llc_i = ira_i = k401_i = 0.0

    # =========================
    # 📊 NEW HEADER LAYOUT
    # =========================
    col1, col2 = st.columns([1, 1])

    # Fetching fresh market data once for both columns
    market = get_market_data()

    with col1:
        st.markdown("### 🎯 Criteria")
        
        # Pulling dynamically from session state
        active_expiry = st.session_state.get('current_exp', '2026-04-17')
        
        # ⚡ Points to your custom Fine-Tune persistence keys to prevent reset to .30
        active_call = st.session_state.get('last_g_call', 0.15)
        active_put = st.session_state.get('last_g_put', 0.30)
        
        # Render the combined single-line display
        st.markdown(f"**Expiry:** `{active_expiry}` | **Call Δ:** `{active_call:.2f}` | **Put Δ:** `{active_put:.2f}`")

    with col2:
        st.markdown("### 📈 Market Watch")

        def fmt_ticker(symbol):
            data = market.get(symbol, {"price": 0, "ytd": 0})
            price = data['price']
            ytd = data['ytd']
            color = "red" if ytd < 0 else "green"
            
            if symbol == "^VIX":
                return f"*{symbol.replace('^', '')}* `${price:,.2f}`"
                
            return f"*{symbol}* `${price:,.2f}` <span style='color:{color};'>({ytd:+.2f}%)</span>"

        # Combine into a clean single line using the exact style as Column 1
        ticker_line = f"{fmt_ticker('SPY')} &nbsp;&nbsp;&nbsp;&nbsp; {fmt_ticker('QQQ')} &nbsp;&nbsp;&nbsp;&nbsp; {fmt_ticker('^VIX')}"
        
        # Render the line
        st.markdown(ticker_line, unsafe_allow_html=True)

    st.divider()

    # =========================
    # 📉 VIX DISPLAY
    # =========================
    try:
        vix_val = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
        vix_label = f" (VIX: {vix_val:.2f})"
    except:
        vix_label = ""

    # =========================
    # 📊 PROJECTION CONTAINER
    # =========================
    with st.expander(f"🚀 2026 Performance Projection{vix_label}", expanded=True):
        proj_area = st.empty()

    # =========================
    # 📊 PROJECTION FUNCTION
    # =========================
    def render_projection(l_m, i_m, llc_value=0, ira_value=0):

        calc = calculate_projections(
            l_m, i_m,
            llc_c, ira_c, k401_c,
            k401_target,
            llc_i, ira_i, k401_i,
            st.session_state.current_exp
        )

        def get_ytd(curr, initial):
            diff = curr - initial
            pct = (diff / initial * 100) if initial != 0 else 0
            return f"${diff:,.2f} ({pct:+.2f}%)"

        llc_ytd = get_ytd(llc_c, llc_i)
        ira_ytd = get_ytd(ira_c, ira_i)
        k401_ytd = get_ytd(k401_c, k401_i)

        exp_date = datetime.strptime(st.session_state.current_exp, '%Y-%m-%d')
        exp_month = exp_date.strftime("%B")

        # Calculate custom Monthly ROI based on Projected Month Base
        llc_monthly_roi = (l_m / llc_value * 100) if llc_value != 0 else 0
        ira_monthly_roi = (i_m / ira_value * 100) if ira_value != 0 else 0
        
        total_monthly_income = l_m + i_m
        total_monthly_base = llc_value + ira_value + k401_c
        total_monthly_roi = (total_monthly_income / total_monthly_base * 100) if total_monthly_base != 0 else 0

        # Calculate Annualized Operations Return (AOR)
        llc_aor = llc_monthly_roi * 12
        ira_aor = ira_monthly_roi * 12
        total_aor = total_monthly_roi * 12

        with proj_area.container():

            # ======================
            # HEADER
            # ======================
            h1, h2, h3, h4 = st.columns([1, 1, 1, 1.2])
            h1.markdown("### 🏢 LLC")
            h2.markdown("### 💼 IRA")
            h3.markdown("### 🏦 401")
            h4.markdown("### 🧮 TOTAL")

            # ======================
            # MONTHLY
            # ======================
            m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])
            m1.metric("Monthly", f"${l_m:,.0f}", f"+{llc_monthly_roi:+.2f}% ROI | {llc_aor:+.2f}% AOR")
            m2.metric("Monthly", f"${i_m:,.0f}", f"+{ira_monthly_roi:+.2f}% ROI | {ira_aor:+.2f}% AOR")
            m3.metric("Monthly", "")
            m4.metric("Monthly", f"${total_monthly_income:,.0f}", f"+{total_monthly_roi:+.2f}% ROI | {total_aor:+.2f}% AOR")

            # ======================
            # EXPIRY VALUE
            # ======================
            m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])
            m1.metric(f"Est. {exp_month}", f"${llc_value:,.0f}")
            m2.metric(f"Est. {exp_month}", f"${ira_value:,.0f}")
            m3.metric(f"Est. {exp_month}", f"${k401_c:,.0f}")
            m4.metric(f"Est. {exp_month}", f"${llc_value + ira_value + k401_c:,.0f}")

            # ======================
            # YEAR-END
            # ======================
            m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])

            m1.metric("Est. Year-End", f"${calc['l_eoy']:,.0f}", f"+${calc['llc_growth']:,.0f} ({calc['llc_aor']:+.2f}%)")
            m2.metric("Est. Year-End", f"${calc['i_eoy']:,.0f}", f"+${calc['ira_growth']:,.0f} ({calc['ira_aor']:+.2f}%)")
            m3.metric("Est. Year-End", f"${k401_target:,.0f}", "Target")
            m4.metric("Est. Year-End", f"${calc['final_predictor']:,.0f}", f"+${calc['total_gain_rem']:,.0f} ({calc['total_aor']:+.2f}%)")

            # ======================
            # CAPITAL / YTD
            # ======================
            m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])
            m1.metric("Capital", f"${llc_i:,.0f}")
            m2.metric("Capital", f"${ira_i:,.0f}")
            m3.metric("Capital", f"${k401_i:,.0f}")
            m4.metric("Capital", f"${(llc_i + ira_i + k401_i):,.0f}")

            # ======================
            # CURRENT BALANCE (NEW)
            # ======================
            llc_diff = llc_c - llc_i
            ira_diff = ira_c - ira_i
            k401_diff = k401_c - k401_i

            llc_pct = (llc_diff / llc_i * 100) if llc_i != 0 else 0
            ira_pct = (ira_diff / ira_i * 100) if ira_i != 0 else 0
            k401_pct = (k401_diff / k401_i * 100) if k401_i != 0 else 0

            total_c = llc_c + ira_c + k401_c
            total_i = llc_i + ira_i + k401_i

            total_diff = total_c - total_i
            total_pct = (total_diff / total_i * 100) if total_i != 0 else 0
            m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])

            m1.metric("Current", f"${llc_c:,.0f}", f"{llc_diff:+,.0f} ({llc_pct:+.2f}%)")
            m2.metric("Current", f"${ira_c:,.0f}", f"{ira_diff:+,.0f} ({ira_pct:+.2f}%)")
            m3.metric("Current", f"${k401_c:,.0f}", f"{k401_diff:+,.0f} ({k401_pct:+.2f}%)")
            m4.metric("Current", f"${total_c:,.0f}", f"{total_diff:+,.0f} ({total_pct:+.2f}%)")    

    # =========================
    # 🔄 CALL SCAN MODULE
    # =========================
    render_scan_results(df_raw, render_projection, top_progress_placeholder)