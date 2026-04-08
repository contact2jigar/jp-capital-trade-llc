import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import certifi
import numpy as np
from datetime import datetime, timedelta

# ========================================================
# 🎨 UI STYLING & CONFIG
# ========================================================
st.set_page_config(layout="wide", page_title="Live Portfolio Desk")

st.markdown("""
<style>
    [data-testid="stDataFrame"]:first-of-type td, 
    [data-testid="stDataFrame"]:first-of-type th {
        font-size: 18px !important;
    }
    div[data-testid="stDataFrame"] {
        border: 1.5px solid #334155 !important;
        border-radius: 10px !important;
        margin-bottom: 25px;
    }
</style>
""", unsafe_allow_html=True)

# ========================================================
# 📥 DATA LOADING & CACHING
# ========================================================
BASE_URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv"
POSITIONS_GID = "1662549766"
SETTINGS_GID = "153723321" 

@st.cache_data(ttl=300)
def load_live_data():
    try:
        url = f"{BASE_URL}&gid={POSITIONS_GID}"
        response = requests.get(url, verify=certifi.where())
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = df.columns.str.strip()
        stock_col = [c for c in df.columns if "Stock" in c][0]
        df = df.rename(columns={stock_col: "Stock"})
        return df[df["Status"] == "Open"].copy()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_initial_capital():
    try:
        url = f"{BASE_URL}&gid={SETTINGS_GID}"
        response = requests.get(url, verify=certifi.where())
        settings_df = pd.read_csv(io.StringIO(response.text))
        settings_df.columns = settings_df.columns.str.strip()
        settings_df['Account'] = settings_df['Account'].str.strip()
        llc_i = settings_df.loc[settings_df['Account'] == 'LLC - Initial', 'Balance'].values[0]
        ira_i = settings_df.loc[settings_df['Account'] == 'IRA - Initial', 'Balance'].values[0]
        return float(llc_i), float(ira_i)
    except Exception:
        return 639000.0, 807700.0

# ========================================================
# 🛠️ HELPERS
# ========================================================
def get_earn_emoji(date_str):
    if not date_str or str(date_str) == 'nan' or date_str == "None": return ""
    try:
        today = datetime.now().date()
        dt = datetime.strptime(str(date_str), '%Y-%m-%d').date()
        pre_fri = dt - timedelta(days=(dt.isoweekday() - 5))
        days = (pre_fri - today).days
        if days < 0: return f"🔴 ({days}d)"
        elif days < 14: return f"⚪ ({days}d)"
        elif days <= 30: return f"💰 ({days}d)"
        elif days <= 40: return f"🟢 ({days}d)"
        else: return f"🟡 ({days}d)"
    except: return ""

def color_chg(val):
    color = '#008000' if val > 0 else '#FF0000'
    return f'color: {color}; font-weight: bold;'

def color_strike(row):
    styles = [''] * len(row)
    if 'Strike' not in row.index or 'Last Close' not in row.index or 'Type' not in row.index:
        return styles
    idx = row.index.get_loc('Strike')
    strike, price, typ = row['Strike'], row['Last Close'], row['Type']
    if (typ == "PUT" and price < strike) or (typ == "CALL" and price > strike):
        styles[idx] = 'background-color: #FF0000; color: white; font-weight: bold;'
    return styles

@st.cache_data(ttl=300)
def get_market_ribbon():
    ribbon_stats = {}
    for symbol in ["SPY", "QQQ", "^VIX"]:
        try:
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
        except: continue
    return ribbon_stats

# ========================================================
# 🚀 MAIN RENDER
# ========================================================
st.title("📈 Live Portfolio Desk")

mkt_data = get_market_ribbon()
if mkt_data:
    display_list = []
    for ticker, stats in mkt_data.items():
        clean_name = ticker.replace("^", "")
        d_clr = "#00c805" if stats['day_pct'] >= 0 else "#ff4b4b"
        y_clr = "#00c805" if stats['ytd_pct'] >= 0 else "#ff4b4b"
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
    df_raw["Cash Reserve"] = pd.to_numeric(df_raw["Cash Reserve"], errors="coerce").fillna(0.0)

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

        # Space-saving columns for buttons: Fetch first, Sync second
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            run_scan = st.button("📡 Fetch Live Quotes", use_container_width=True)
        with btn_col2:
            if st.button("🔄 Sync Google Sheets", use_container_width=True):
                st.cache_data.clear()
                st.toast("Syncing...", icon="📥")

    df = df_raw.copy()
    if filter_acct != "All": df = df[df["Account"] == filter_acct]
    if filter_date != "All": df = df[df["Close Date"] == filter_date]
    if filter_type != "All": df = df[df["Opt Typ"] == filter_type]
    
    df = df[~df["Account"].str.contains("401", na=False)]
    df["Strike"] = pd.to_numeric(df["Strike Price"], errors="coerce").fillna(0)
    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0).abs()
    df["Stock"] = df["Stock"].astype(str).str.upper()

    if run_scan:
        llc_initial, ira_initial = load_initial_capital()
        total_initial = llc_initial + ira_initial

        tickers = [t for t in df["Stock"].unique() if t != "CASH"]
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        st.markdown("### 🏦 Account Summary")
        summary_spot = st.empty()
        st.markdown("### 📊 Active Trade Positions")
        queue_spot = st.empty()

        live_results = []
        
        cash_df = df[df["Stock"] == "CASH"]
        for _, row in cash_df.iterrows():
            live_results.append({
                "Ticker": "CASH", "Account": row["Account"], "Type": "CASH",
                "Last Close": 1.0, "Strike": 0.0, "Chg": 0.0, "Chg (%)": 0.0,
                "Qty": row["Qty"], "Market Value": row["Cash Reserve"], "Earn": "", "Close Date": "None"
            })

        for i, t in enumerate(tickers):
            status_text.text(f"🔍 Fetching Market Data: {t} ({i+1}/{len(tickers)})")
            progress_bar.progress((i + 1) / len(tickers))
            try:
                tk = yf.Ticker(t)
                hist = tk.history(period="1y") 
                if not hist.empty:
                    px, prev = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
                    ticker_rows = df[df["Stock"] == t]
                    for _, row in ticker_rows.iterrows():
                        o, s, q = row["Opt Typ"], row["Strike"], row["Qty"]
                        if o == "HOLD": mkt_val = row["Cash Reserve"] 
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
            
            def get_val(acct, typ=None):
                tmp = current_df
                if acct != "Total": tmp = tmp[tmp["Account"].str.contains(acct, na=False)]
                if typ: tmp = tmp[tmp["Type"] == typ]
                return tmp["Market Value"].sum()

            l_total, i_total = get_val("LLC"), get_val("IRA")
            grand_total = l_total + i_total

            def fmt_html_cell(val, acct_total, color=None):
                pct = (val / acct_total * 100) if acct_total > 0 else 0
                style = f"font-size:11px; margin-top:2px; font-weight:600;"
                if color == "green": style += " color:#16a34a;"
                elif color == "red": style += " color:#dc2626;"
                else: style += " color:#64748b;"
                return f'${val:,.0f}<div style="{style}">{pct:.1f}%</div>'

            def fmt_current_val_with_pl(curr, initial):
                diff = curr - initial
                pct = (diff / initial * 100) if initial > 0 else 0
                color = "#16a34a" if diff >= 0 else "#dc2626"
                sign = "+" if diff >= 0 else ""
                return f"""
                <div style="font-weight:700;">${curr:,.0f}</div>
                <div style="color:{color}; font-size:11px; font-weight:600; margin-top:2px;">
                    {sign}${diff:,.0f} | {pct:+.2f}%
                </div>
                """

            html_table = f"""
            <style>
                .table-container {{ width: 100%; overflow-x: auto; margin-top: 10px; border: 1px solid #000; border-radius: 4px; }}
                .custom-table {{ width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; }}
                .custom-table th {{ text-align: left; padding: 12px; background-color: #f1f5f9; border-bottom: 1px solid #000; font-weight: 700; }}
                .custom-table td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; }}
                .metric-col {{ background-color: #f8fafc; font-weight: 600; width: 20%; }}
                .zebra {{ background-color: #fafafa; }}
            </style>
            <div class="table-container">
                <table class="custom-table">
                    <thead>
                        <tr><th>Metrics</th><th>🏢 LLC</th><th>💼 IRA</th><th>🧮 TOTAL</th></tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td class="metric-col">📈 Current Value</td>
                            <td>{fmt_current_val_with_pl(l_total, llc_initial)}</td>
                            <td>{fmt_current_val_with_pl(i_total, ira_initial)}</td>
                            <td>{fmt_current_val_with_pl(grand_total, total_initial)}</td>
                        </tr>
                        <tr class="zebra">
                            <td class="metric-col">🛡️ Puts</td>
                            <td>{fmt_html_cell(get_val("LLC", "PUT"), l_total, "green")}</td>
                            <td>{fmt_html_cell(get_val("IRA", "PUT"), i_total, "green")}</td>
                            <td>{fmt_html_cell(get_val("Total", "PUT"), grand_total, "green")}</td>
                        </tr>
                        <tr>
                            <td class="metric-col">🚀 Calls</td>
                            <td>{fmt_html_cell(get_val("LLC", "CALL"), l_total, "red")}</td>
                            <td>{fmt_html_cell(get_val("IRA", "CALL"), i_total, "red")}</td>
                            <td>{fmt_html_cell(get_val("Total", "CALL"), grand_total, "red")}</td>
                        </tr>
                        <tr class="zebra">
                            <td class="metric-col">💵 Cash</td>
                            <td>{fmt_html_cell(get_val("LLC", "CASH"), l_total)}</td>
                            <td>{fmt_html_cell(get_val("IRA", "CASH"), i_total)}</td>
                            <td>{fmt_html_cell(get_val("Total", "CASH"), grand_total)}</td>
                        </tr>
                        <tr>
                            <td class="metric-col">🛡️ Puts + 💵 Cash</td>
                            <td>{fmt_html_cell(get_val("LLC", "PUT") + get_val("LLC", "CASH"), l_total, "green")}</td>
                            <td>{fmt_html_cell(get_val("IRA", "PUT") + get_val("IRA", "CASH"), i_total, "green")}</td>
                            <td>{fmt_html_cell(get_val("Total", "PUT") + get_val("Total", "CASH"), grand_total, "green")}</td>
                        </tr>
                        <tr style="background-color:#f0f9ff; border-top: 2px solid #000;">
                            <td class="metric-col" style="background-color:#f0f9ff; font-weight:bold;">💰 Capital (Initial)</td>
                            <td>${llc_initial:,.0f}</td>
                            <td>${ira_initial:,.0f}</td>
                            <td>${total_initial:,.0f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
            summary_spot.markdown(html_table, unsafe_allow_html=True)

            queue_df = current_df.copy()
            if not queue_df.empty:
                queue_df['Earning Alert'] = queue_df['Earn'].apply(get_earn_emoji)
                f_cols = ["Ticker", "Account", "Type", "Last Close", "Close Date", "Strike", "Market Value", "Chg", "Chg (%)", "Earn", "Earning Alert", "20D MA", "50D MA", "100D MA", "200D MA", "Qty"]
                disp = queue_df.sort_values(by="Ticker")[[c for c in f_cols if c in queue_df.columns]]
                styled = disp.style.apply(color_strike, axis=1)
                if 'Chg' in disp.columns: styled = styled.map(color_chg, subset=['Chg', 'Chg (%)'])
                f_m = {"Strike": "${:.2f}", "Market Value": "${:,.2f}", "Last Close": "${:.2f}", "Chg": "${:.2f}", "20D MA": "${:.2f}", "50D MA": "${:.2f}", "100D MA": "${:.2f}", "200D MA": "${:.2f}", "Chg (%)": "{:.2f}%", "Qty": "{:.0f}"}
                queue_spot.dataframe(styled.format({k: v for k, v in f_m.items() if k in disp.columns}), hide_index=True, use_container_width=True)

        status_text.empty()
        progress_bar.empty()
    else:
        st.info("💡 Adjust parameters above and click 'Fetch Live Quotes' to refresh.")