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
if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None

st.title("💎 Blue Chip Scanner")

# ==========================================
# 📥 DATA & FETCHING UTILS
# ==========================================
SPREADSHEET_ID = "1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M"

@st.cache_data(ttl=300)
def get_tickers_from_sheets(tab_name):
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid=337359953"
    try:
        response = requests.get(url, verify=certifi.where(), timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            df.columns = df.columns.str.strip().str.replace(r"[^\w\s]", "", regex=True)
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
def style_table_rows(df, min_roi_threshold):
    style_matrix = pd.DataFrame("", index=df.index, columns=df.columns)

    for idx, row in df.iterrows():
        try:
            roi_val = float(str(row.get("ROI%", "0")).replace("%", "")) if row.get("ROI%") != "N/A" else 0
        except ValueError:
            roi_val = 0

        # 🟢 DYNAMIC GREEN: Contract yields at least your chosen Min ROI
        if roi_val >= min_roi_threshold:
            base_style = "background-color: #d1fae5; color: #065f46;"  # Soft green
        else:
            base_style = "background-color: #dee3e8; color: #000000;" if idx % 2 == 0 else "background-color: #ffffff; color: #000000;"

        style_matrix.loc[idx] = base_style

        # Retain direction colors for the Change column
        chg_val = str(row.get("Chg", ""))
        if "+" in chg_val:
            style_matrix.loc[idx, "Chg"] = f"{base_style} color: #16a34a; font-weight: bold;"
        elif "-" in chg_val:
            style_matrix.loc[idx, "Chg"] = f"{base_style} color: #dc2626; font-weight: bold;"

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
    "MyWatchList": "WatchList",
}

try:
    third_friday = get_next_third_friday()
    available_fridays = get_fridays()
except NameError:
    third_friday = "2026-04-17"
    available_fridays = ["2026-04-17", "2026-04-24", "2026-05-15"]

if third_friday not in available_fridays:
    available_fridays.insert(0, third_friday)

with st.expander("🛠️ Scanner Filters", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        market = st.selectbox("📊 Market", list(indices.keys()), index=2)
    with col2:
        default_idx = available_fridays.index(third_friday) if third_friday in available_fridays else 0
        expiry = st.selectbox("📅 Expiry", available_fridays, index=default_idx)
    with col3:
        depth = st.selectbox("🔍 Depth", [10, 20, 30, 50, 100], index=3)
    with col4:
        max_price = st.number_input("💰 Max $", min_value=10, max_value=2000, value=400, step=10)

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        manual_tickers = st.text_input("🎯 Manual Tickers (CSV)", placeholder="AAPL, MSFT")
    with col6:
        min_iv = st.number_input("⚡ Min IV%", min_value=0, value=35, step=5)
    with col7:
        user_target_delta = st.number_input("🎯 Target Delta", min_value=0.10, max_value=0.50, value=0.25, step=0.05)
    with col8:
        min_target_roi = st.number_input("💸 Min ROI%", min_value=0.5, max_value=10.0, value=2.5, step=0.5)

# ==========================
# 🚀 ACTION BUTTON & RESULTS
# ==========================
col_btn, col_res = st.columns([3, 1])
found_count = len(st.session_state.scan_results) if st.session_state.scan_results is not None else 0

with col_btn:
    run_scan = st.button(f"🚀 Scan {market}", use_container_width=True)

with col_res:
    st.markdown(f"<div style='background-color: #1b381e; color: #ffffff; text-align: center; padding: 10px; border-radius: 5px; font-weight: bold; border: 1px solid #2e7d32;'>Found: {found_count}</div>", unsafe_allow_html=True)

# ==========================
# ⚙️ MAIN SCANNER EXECUTION
# ==========================
if run_scan:
    with st.spinner(f"Fetching {market} tickers from Google Sheets..."):
        target_tab = indices[market]
        df_sheet = get_tickers_from_sheets(target_tab)

    if not df_sheet.empty:
        raw_list = df_sheet.iloc[:, 0].astype(str).str.strip().str.upper()
        raw_list = raw_list.replace(["NAN", "NONE", "CASH", ""], np.nan).dropna()
        scan_list = raw_list.unique().tolist()[:depth]

        if manual_tickers:
            manual_list = [t.strip().upper() for t in manual_tickers.split(",") if t.strip()]
            if manual_list: scan_list = manual_list

        results = []
        prog_bar = st.progress(0, "Scanning stocks...")
        live_grid = st.empty()

        current_rank = 1
        exp_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(hour=16)
        days_to_exp = max((exp_dt - datetime.now()).days, 1)

        for i, ticker in enumerate(scan_list, start=1):
            if not ticker or len(ticker) > 5 or ticker == "STOCK":
                continue

            prog_bar.progress(i / len(scan_list), f"Scanning {ticker} ({i}/{len(scan_list)})")

            try:
                t_obj = yf.Ticker(ticker)
                curr_px = t_obj.fast_info["lastPrice"]
                chain = t_obj.option_chain(expiry)
                
                if chain.puts.empty:
                    continue

                hist = t_obj.history(period="1y")
                mkt_cap = t_obj.fast_info.get("marketCap", 0)

                if not hist.empty:
                    prev_close = hist["Close"].iloc[-2]
                    diff = curr_px - prev_close
                    chg_display = f"{diff:+.2f}" if diff != 0 else "0.00"

                    # Grab Next Earnings Date
                    earnings_date = "N/A"
                    try:
                        cal = t_obj.calendar
                        if cal is not None and "Earnings Date" in cal:
                            dates = cal["Earnings Date"]
                            if dates:
                                earnings_date = dates[0].strftime("%m-%d")
                    except:
                        pass

                    # Option Math setup
                    T = max((exp_dt - datetime.now()).total_seconds() / 31536000.0, 0.001)

                    picked_strike = "N/A"
                    picked_delta = "N/A"
                    picked_roi = "N/A"
                    picked_aor = "N/A"
                    picked_discount = "N/A"

                    viable_puts = chain.puts[chain.puts["strike"] <= curr_px]
                    processed_puts = []

                    for _, p_row in viable_puts.iterrows():
                        strike = float(p_row["strike"])
                        bid = float(p_row["bid"])
                        ask = float(p_row["ask"])
                        mid = ((bid + ask) / 2) if (bid > 0 and ask > 0) else p_row.get("lastPrice", bid)

                        try:
                            iv, delta = find_iv_and_delta(mid, curr_px, strike, T, 0.043, "put")
                        except NameError:
                            delta = -0.30

                        processed_puts.append({"strike": strike, "bid": bid, "delta": abs(delta)})

                    if processed_puts:
                        p_df = pd.DataFrame(processed_puts)
                        # Target Search based on the user's defined target Delta
                        p_df["delta_diff"] = (p_df["delta"] - user_target_delta).abs()
                        best_row = p_df.sort_values("delta_diff").iloc[0]

                        picked_strike = f"${best_row['strike']:,.2f}"
                        picked_delta = f"{best_row['delta']:.2f}"

                        # Target ROI
                        raw_roi = (best_row["bid"] / best_row["strike"]) * 100
                        picked_roi = f"{raw_roi:.2f}%"

                        # Annualized Rate of Return (AOR)
                        raw_aor = ((1 + (best_row["bid"] / best_row["strike"])) ** (365 / days_to_exp) - 1) * 100
                        picked_aor = f"{raw_aor:.1f}%"

                        # % of Discount if Assignment Happens
                        break_even = best_row["strike"] - best_row["bid"]
                        raw_disc = ((curr_px - break_even) / curr_px) * 100
                        picked_discount = f"{raw_disc:.1f}%"

                    results.append({
                        "Rank": f"#{current_rank}",
                        "Ticker": ticker,
                        "Market Cap": mkt_cap,
                        "Current Price": f"${curr_px:,.2f}",
                        "Chg": chg_display,
                        "Strike": picked_strike,
                        "Delta": picked_delta,
                        "ROI%": picked_roi,
                        "AOR%": picked_aor,
                        "Discount%": picked_discount,
                        "Earnings": earnings_date,
                    })

                    current_rank += 1
                    current_df = pd.DataFrame(results).drop(columns=["Market Cap"])
                    live_grid.dataframe(current_df, use_container_width=True, hide_index=True, height=350)

            except Exception:
                continue

        prog_bar.empty()

        if results:
            raw_df = pd.DataFrame(results).sort_values(by="Market Cap", ascending=False).reset_index(drop=True)
            raw_df["Rank"] = [f"#{x}" for x in range(1, len(raw_df) + 1)]
            raw_df = raw_df.drop(columns=["Market Cap"])

            st.session_state.scan_results = raw_df
            st.rerun()

# ==========================
# 📋 RESULTS & OPTION CHAIN UI
# ==========================
if st.session_state.scan_results is not None:
    # Pass the min_target_roi selected by the user to properly color-code rows
    styled_df = st.session_state.scan_results.style.apply(style_table_rows, axis=None, min_roi_threshold=min_target_roi)

    st.markdown(f"### 📋 {market} Scanned Results")
    st.caption(f"🟢 Soft Green = Ideal Wheel Candidate (Target {user_target_delta} Delta yields at least {min_target_roi}% ROI).")

    event = st.dataframe(styled_df, use_container_width=True, hide_index=True, height=350, on_select="rerun")

    if event is not None and "selection" in event:
        rows = event["selection"].get("rows", [])
        if rows:
            clicked_row_idx = rows[0]
            st.session_state.selected_ticker = st.session_state.scan_results.iloc[clicked_row_idx]["Ticker"]

    if st.session_state.selected_ticker is not None:
        sel_t = st.session_state.selected_ticker
        target_expiries = get_prior_expiries(expiry, num_weeks=3)

        st.markdown(f"### ⛓️ Option Chains for **{sel_t}** (Lookback View)")
        tab_puts, tab_calls = st.tabs(["📉 Puts (CSP)", "📈 Calls (Covered Calls)"])

        t_obj = yf.Ticker(sel_t)
        px = t_obj.fast_info["lastPrice"]

        # Dynamic green highlighting for detailed breakdown views too
        def highlight_target_delta(row):
            try:
                delta_val = float(row["Delta"])
                if (user_target_delta - 0.05) <= delta_val <= (user_target_delta + 0.05):
                    return ["background-color: #d1fae5; color: #065f46; font-weight: bold;"] * len(row)
            except:
                pass
            return [""] * len(row)

        def render_chain_view(opt_chain_df, side, exp_date_str):
            processed_list = []
            applied_min_iv = min_iv / 100

            exp_dt = datetime.strptime(exp_date_str, "%Y-%m-%d").replace(hour=16)
            days_to_exp = max((exp_dt - datetime.now()).days, 1)
            T = max((exp_dt - datetime.now()).total_seconds() / 31536000.0, 0.001)

            for _, row in opt_chain_df.iterrows():
                strike = float(row["strike"])
                bid = float(row["bid"])
                ask = float(row["ask"])
                mid = ((bid + ask) / 2) if (bid > 0 and ask > 0) else row.get("lastPrice", bid)

                try:
                    iv, delta = find_iv_and_delta(mid, px, strike, T, 0.043, side)
                except NameError:
                    delta = -0.30 if side == "put" else 0.30
                    iv = 0.40

                delta_mag = abs(delta)
                roi_decimal = (bid / strike) if side == "put" else (bid / px)
                roi_pct = roi_decimal * 100
                aor_pct = ((1 + roi_decimal) ** (365 / days_to_exp) - 1) * 100

                if 0.10 <= delta_mag <= 0.50:
                    processed_list.append({
                        "Strike": strike, "Bid": bid, "Volume": int(row.get("volume", 0)),
                        "OI": int(row.get("openInterest", 0)), "Delta": round(delta_mag, 2),
                        "IV%": iv * 100, "ROI%": roi_pct, "AOR%": aor_pct, "raw_iv": iv,
                    })

            if processed_list:
                final_df = pd.DataFrame(processed_list)
                strict_df = final_df[final_df["raw_iv"] >= applied_min_iv]
                output_df = strict_df if not strict_df.empty else final_df

                if strict_df.empty:
                    st.caption(f"⚠️ Showing available chains outside target IV floor ({min_iv}%).")

                output_df = output_df.drop(columns=["raw_iv"]).sort_values(by="Delta", ascending=False)
                output_df["Strike"] = output_df["Strike"].apply(lambda x: f"${x:,.2f}")
                output_df["Bid"] = output_df["Bid"].apply(lambda x: f"${x:.2f}")
                output_df["IV%"] = output_df["IV%"].apply(lambda x: f"{x:.1f}%")
                output_df["ROI%"] = output_df["ROI%"].apply(lambda x: f"{x:.2f}%")
                output_df["AOR%"] = output_df["AOR%"].apply(lambda x: f"{x:.1f}%")

                styled_output = (
                    output_df.style.apply(highlight_target_delta, axis=1)
                    .bar(subset=["Volume"], color="#fff3cd", vmin=0)
                    .bar(subset=["OI"], color="#fff3cd", vmin=0)
                )

                st.dataframe(styled_output, use_container_width=True, hide_index=True)
            else:
                st.info(f"No contracts found in the 0.10 to 0.50 Delta range for {exp_date_str}.")

        with tab_puts:
            for exp_dt in target_expiries:
                st.markdown(f"**📅 Expiration: {exp_dt}**")
                try:
                    chain_data = t_obj.option_chain(exp_dt)
                    otm_puts = chain_data.puts[chain_data.puts["strike"] <= px]
                    render_chain_view(otm_puts, "put", exp_dt)
                except Exception:
                    st.error(f"Could not load puts for {exp_dt}")
                st.divider()

        with tab_calls:
            for exp_dt in target_expiries:
                st.markdown(f"**📅 Expiration: {exp_dt}**")
                try:
                    chain_data = t_obj.option_chain(exp_dt)
                    otm_calls = chain_data.calls[chain_data.calls["strike"] >= px]
                    render_chain_view(otm_calls, "call", exp_dt)
                except Exception:
                    st.error(f"Could not load calls for {exp_dt}")
                st.divider()