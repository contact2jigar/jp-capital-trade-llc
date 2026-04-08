from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# Pulled your newly added function here
from reports.engine import calculate_live_balances, calculate_projections
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
                ytd = (
                    ((current - start_year["Close"].iloc[0]) / start_year["Close"].iloc[0]) * 100
                    if not start_year.empty
                    else 0
                )
            else:
                ytd = 0
            data[ticker] = {"price": current, "ytd": ytd}
        except:
            data[ticker] = {"price": 0, "ytd": 0}
    return data


def render_portfolio_snapshot(df_raw, load_balances):

    # =========================================================
    # 💰 LOAD BALANCES
    # =========================================================
    # ⚡ NEW: Calculating your LLC and IRA balances dynamically
    live_balances = calculate_live_balances(df_raw)
    llc_c = live_balances.get("LLC", 0.0)
    ira_c = live_balances.get("IRA", 0.0)

    # We still use the fallback file for targets and initial capital
    bal_df = load_balances()

    def get_val(label):
        try:
            return float(bal_df[bal_df["Account"] == label]["Balance"].values[0])
        except:
            return 0.0

    if not bal_df.empty:
        k401_c = get_val("401 - Current")
        llc_i = get_val("LLC - Initial")
        ira_i = get_val("IRA - Initial")
        k401_i = get_val("401 - Initial")
        k401_target = get_val("401 - 2026 Target")
    else:
        k401_c = k401_target = 0.0
        llc_i = ira_i = k401_i = 0.0

    # =========================
    # 📊 NEW HEADER LAYOUT
    # =========================
    col1, col2 = st.columns([1, 1])
    market = get_market_data()

    with col1:
        st.markdown("### 🎯 Criteria")
        active_expiry = st.session_state.get("current_exp", "2026-04-17")
        active_call = st.session_state.get("last_g_call", 0.15)
        active_put = st.session_state.get("last_g_put", 0.30)
        st.markdown(
            f"**Expiry:** `{active_expiry}` | **Call Δ:** `{active_call:.2f}` | **Put Δ:** `{active_put:.2f}`"
        )

    with col2:
        st.markdown("### 📈 Market Watch")

        def fmt_ticker(symbol):
            data = market.get(symbol, {"price": 0, "ytd": 0})
            price = data["price"]
            ytd = data["ytd"]
            color = "red" if ytd < 0 else "green"
            if symbol == "^VIX":
                return f"*{symbol.replace('^', '')}* `${price:,.2f}`"
            return f"*{symbol}* `${price:,.2f}` <span style='color:{color};'>({ytd:+.2f}%)</span>"

        ticker_line = f"{fmt_ticker('SPY')} &nbsp;&nbsp;&nbsp;&nbsp; {fmt_ticker('QQQ')} &nbsp;&nbsp;&nbsp;&nbsp; {fmt_ticker('^VIX')}"
        st.markdown(ticker_line, unsafe_allow_html=True)

    st.divider()
    top_progress_placeholder = st.empty()

    try:
        vix_val = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
        vix_label = f" (VIX: {vix_val:.2f})"
    except:
        vix_label = ""

    st.markdown(f"### 🚀 Performance Projection")
    proj_area = st.empty()

    # =========================================================
    # 📊 PROJECTION FUNCTION (CUSTOM HTML WITH BORDERS & ZEBRA)
    # =========================================================
    def render_projection(l_m, i_m, llc_value=0, ira_value=0):
        calc = calculate_projections(
            l_m,
            i_m,
            llc_c,
            ira_c,
            k401_c,
            k401_target,
            llc_i,
            ira_i,
            k401_i,
            st.session_state.current_exp,
        )

        exp_date = datetime.strptime(st.session_state.current_exp, "%Y-%m-%d")
        exp_month = exp_date.strftime("%B")

        # Core calculations
        llc_monthly_roi = (l_m / llc_value * 100) if llc_value != 0 else 0
        ira_monthly_roi = (i_m / ira_value * 100) if ira_value != 0 else 0
        total_monthly_income = l_m + i_m
        total_monthly_base = llc_value + ira_value + k401_c
        total_monthly_roi = (
            (total_monthly_income / total_monthly_base * 100)
            if total_monthly_base != 0
            else 0
        )

        llc_aor = llc_monthly_roi * 12
        ira_aor = ira_monthly_roi * 12
        total_aor = total_monthly_roi * 12

        total_c = llc_c + ira_c + k401_c
        total_i = llc_i + ira_i + k401_i

        # Helper function for tracking capital deltas
        def get_diff_metrics(curr, initial):
            diff = curr - initial
            pct = (diff / initial * 100) if initial != 0 else 0
            color = "#16a34a" if diff >= 0 else "#dc2626"
            sign = "+" if diff >= 0 else ""
            return f'<div style="color:{color}; font-size:11px; margin-top:2px;">{sign}${diff:,.0f} | {pct:+.2f}%</div>'

        # Direct pure HTML generation matching LLC table aesthetics
        html_table = f"""
        <style>
            .table-container {{
                width: 100%;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                margin-top: 10px;
                border: 1px solid #000000; /* Solid black border */
                border-radius: 4px;
            }}
            .custom-table {{
                width: 100%;
                min-width: 600px; 
                border-collapse: collapse;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
            }}
            .custom-table th {{
                text-align: left;
                padding: 10px 12px;
                background-color: #f1f5f9; /* Flat header color like positions tables */
                color: #0f172a;
                font-weight: 700;
                border-bottom: 1px solid #000000;
            }}
            .custom-table td {{
                padding: 10px 12px;
                border-bottom: 1px solid #e2e8f0;
                color: #334155;
                vertical-align: top;
            }}
            /* Alternating row styling (Zebra stripes) */
            .custom-table tr:nth-child(even) {{
                background-color: #fafafa;
            }}
            .custom-table tr:nth-child(odd) {{
                background-color: #ffffff;
            }}
            /* Last row (TOTAL) styling */
            .custom-table tr:last-child td {{
                border-bottom: none;
                font-weight: 700;
                background-color: #f1f5f9; 
                color: #0f172a;
            }}
        </style>
        <div class="table-container">
            <table class="custom-table">
                <thead>
                    <tr>
                        <th style="width: 11%;">Account</th>
                        <th style="width: 17%;">Monthly</th>
                        <th style="width: 14%;">Est. {exp_month[:3]}</th>
                        <th style="width: 17%;">Est. YE</th>
                        <th style="width: 15%;">Current</th>
                        <th style="width: 15%;">Capital</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>🏢 LLC</td>
                        <td>
                            ${l_m:,.0f}
                            <div style="color:#16a34a; font-size:11px; margin-top:2px; font-weight:500;">+{llc_monthly_roi:.2f}% ROI | {llc_aor:+.2f}%</div>
                        </td>
                        <td>${llc_value:,.0f}</td>
                        <td>
                            ${calc['l_eoy']:,.0f}
                            <div style="color:#16a34a; font-size:11px; margin-top:2px;">+${calc['llc_growth']:,.0f} | {calc['llc_aor']:+.2f}%</div>
                        </td>
                        <td>
                            ${llc_c:,.0f}
                            {get_diff_metrics(llc_c, llc_i)}
                        </td>
                        <td>${llc_i:,.0f}</td>
                    </tr>
                    <tr>
                        <td>💼 IRA</td>
                        <td>
                            ${i_m:,.0f}
                            <div style="color:#16a34a; font-size:11px; margin-top:2px; font-weight:500;">+{ira_monthly_roi:.2f}% ROI | {ira_aor:+.2f}%</div>
                        </td>
                        <td>${ira_value:,.0f}</td>
                        <td>
                            ${calc['i_eoy']:,.0f}
                            <div style="color:#16a34a; font-size:11px; margin-top:2px;">+${calc['ira_growth']:,.0f} | {calc['ira_aor']:+.2f}%</div>
                        </td>
                        <td>
                            ${ira_c:,.0f}
                            {get_diff_metrics(ira_c, ira_i)}
                        </td>
                        <td>${ira_i:,.0f}</td>
                    </tr>
                    <tr>
                        <td>🏦 401</td>
                        <td>N/A</td>
                        <td>${k401_c:,.0f}</td>
                        <td>
                            ${k401_target:,.0f}
                            <div style="color:#64748b; font-size:11px; margin-top:2px;">Target</div>
                        </td>
                        <td>
                            ${k401_c:,.0f}
                            {get_diff_metrics(k401_c, k401_i)}
                        </td>
                        <td>${k401_i:,.0f}</td>
                    </tr>
                    <tr>
                        <td>🧮 TOTAL</td>
                        <td>
                            ${total_monthly_income:,.0f}
                            <div style="color:#16a34a; font-size:11px; margin-top:2px; font-weight:700;">+{total_monthly_roi:.2f}% ROI | {total_aor:+.2f}%</div>
                        </td>
                        <td>${(llc_value + ira_value + k401_c):,.0f}</td>
                        <td>
                            ${calc['final_predictor']:,.0f}
                            <div style="color:#16a34a; font-size:11px; margin-top:2px;">+${calc['total_gain_rem']:,.0f} | {calc['total_aor']:+.2f}%</div>
                        </td>
                        <td>
                            ${total_c:,.0f}
                            {get_diff_metrics(total_c, total_i)}
                        </td>
                        <td>${total_i:,.0f}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """

        with proj_area.container():
            st.markdown(html_table, unsafe_allow_html=True)

    # =========================
    # 🔄 CALL SCAN MODULE
    # =========================
    render_scan_results(df_raw, render_projection, top_progress_placeholder)