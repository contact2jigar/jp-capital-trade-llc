import io
from datetime import datetime
import certifi
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ⚡ Import the shared calculation function from engine
from reports.engine import calculate_live_balances

# Pulling from your exact sheet and active open tab
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=1662549766"


@st.cache_data(ttl=10)
def load_live_data(url):
    try:
        response = requests.get(url, verify=certifi.where(), timeout=10)
        df = pd.read_csv(io.BytesIO(response.content))
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Failed to fetch sheet data: {e}")
        return pd.DataFrame()


def color_movement(val):
    if "▲" in str(val):
        return "color: #00cc66; font-weight: bold;"
    elif "▼" in str(val):
        return "color: #ff4d4d; font-weight: bold;"
    return "color: #888888;"


def highlight_breaches(row):
    styles = [""] * len(row)
    try:
        col_strike_idx = row.index.get_loc("Strike")
    except KeyError:
        return styles

    opt_type = str(row["Opt Type"]).upper()
    current_price = row["Current Price"]
    strike = row["Strike"]

    if pd.isna(current_price) or pd.isna(strike):
        return styles

    if (opt_type == "CALL" and current_price > strike) or (
        opt_type == "PUT" and current_price < strike
    ):
        styles[col_strike_idx] = (
            "background-color: #ffe6e6; color: #cc0000; font-weight: bold;"
        )

    return styles


# ⚡ Fragment runs every 300 seconds (5 minutes)
@st.fragment(run_every=300)
def auto_updating_portfolio(open_trades, account_cash, all_accounts, sheet_data):

    # Custom Loading Screen Container
    loading_container = st.empty()
    
    # Render the styled loading screen while the background execution takes place
    loading_container.markdown("""
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #f8fafc; margin-bottom: 20px;">
            <div style="border: 4px solid #f3f3f3; border-top: 4px solid #3b82f6; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite;"></div>
            <p style="margin-top: 16px; font-size: 16px; color: #475569; font-weight: 500; font-family: sans-serif;">Analyzing portfolio holdings & mapping live balances...</p>
            <style>
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        </div>
    """, unsafe_allow_html=True)

    prog_bar = st.empty()

    # Place inside the fragment so they remain stable containers
    top_table_container = st.empty()
    st.divider()
    table_container = st.empty()

    stock_rows = open_trades[open_trades["Stock"] != "CASH"]
    grouped_assets = (
        stock_rows.groupby(["Account", "Stock", "Opt Typ", "Strike"])[
            ["Qty", "Cash Reserve"]
        ]
        .sum()
        .reset_index()
    )
    grouped_assets["Qty"] = grouped_assets["Qty"].astype(int)
    total_assets_count = len(grouped_assets)

    portfolio_assets = []
    
    # Calculate the true live balances using the shared engine logic first
    live_balances = calculate_live_balances(sheet_data)

    # Empty out the loading screen before looping into data rendering
    loading_container.empty()

    def update_live_view():
        # --- GET REAL VALUES FOR TOP PIVOT TABLE ---
        df_assets = pd.DataFrame(portfolio_assets) if portfolio_assets else pd.DataFrame()

        def get_opt_val(acct_name, opt_type):
            if df_assets.empty:
                return 0.0
            if acct_name == "TOTAL":
                filtered = df_assets[df_assets["Opt Type"] == opt_type]
            else:
                filtered = df_assets[(df_assets["Account"] == acct_name) & (df_assets["Opt Type"] == opt_type)]
            return filtered["Live Asset Value"].sum()

        llc_worth = live_balances.get("LLC", 0.0)
        ira_worth = live_balances.get("IRA", 0.0)
        total_worth = llc_worth + ira_worth

        llc_puts = get_opt_val("LLC", "PUT")
        ira_puts = get_opt_val("IRA", "PUT")
        total_puts = llc_puts + ira_puts

        llc_calls = get_opt_val("LLC", "CALL")
        ira_calls = get_opt_val("IRA", "CALL")
        total_calls = llc_calls + ira_calls

        # GRABBING RAW CASH FROM CASH RESERVE (using float cast to ensure accuracy)
        llc_cash = float(account_cash.get("LLC", 0.0))
        ira_cash = float(account_cash.get("IRA", 0.0))
        total_cash = llc_cash + ira_cash

        # Calculate percentages with exact 2 decimal places
        def get_pct_str(val, total, color_scheme="green"):
            if total == 0:
                return ""
            pct = (val / total) * 100
            if color_scheme == "green":
                return f'<span style="display: inline-block; padding: 3px 6px; border-radius: 4px; background-color: #dcfce7; color: #16a34a; font-size: 12px; font-weight: 700; margin-left: 8px;">{pct:.2f}%</span>'
            elif color_scheme == "amber":
                return f'<span style="display: inline-block; padding: 3px 6px; border-radius: 4px; background-color: #fef3c7; color: #d97706; font-size: 12px; font-weight: 700; margin-left: 8px;">{pct:.2f}%</span>'
            else:
                # Gray pill for cash
                return f'<span style="display: inline-block; padding: 3px 6px; border-radius: 4px; background-color: #f1f5f9; color: #475569; font-size: 12px; font-weight: 700; margin-left: 8px;">{pct:.2f}%</span>'

        # --- TOP PIVOT TABLE ---
        top_table_html = f"""
        <style>
            .table-container {{
                width: 100%;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                margin-top: 15px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
            }}
            .custom-table {{
                width: 100%;
                min-width: 600px; 
                border-collapse: collapse;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            .custom-table th {{
                text-align: left;
                padding: 14px 16px;
                background-color: #f8fafc;
                color: #475569;
                font-size: 13px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                border-bottom: 2px solid #e2e8f0;
            }}
            .custom-table td {{
                padding: 16px 16px;
                border-bottom: 1px solid #e2e8f0;
                color: #0f172a;
                vertical-align: middle;
            }}
            /* Alternating row colors for readability */
            .custom-table tbody tr:nth-child(even) {{
                background-color: #f8fafc;
            }}
            .custom-table tbody tr:nth-child(odd) {{
                background-color: #ffffff;
            }}
            .custom-table tbody tr:hover {{
                background-color: #f1f5f9;
            }}
            
            /* Typography hierarchy */
            .row-label {{
                font-weight: 600;
                color: #334155;
                font-size: 14px;
            }}
            .cell-value {{
                font-size: 16px;
                font-weight: 500;
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            }}
            .bold-total {{
                font-size: 16px;
                font-weight: 700;
                color: #0f172a;
            }}

            /* Header badges styling */
            .badge-llc {{ display: inline-block; padding: 5px 10px; border-radius: 6px; background-color: #e0f2fe; color: #0369a1; font-weight: 700; font-size: 12px; }}
            .badge-ira {{ display: inline-block; padding: 5px 10px; border-radius: 6px; background-color: #fef3c7; color: #b45309; font-weight: 700; font-size: 12px; }}
            .badge-total {{ display: inline-block; padding: 5px 10px; border-radius: 6px; background-color: #f1f5f9; color: #0f172a; font-weight: 700; font-size: 12px; }}
        </style>
        ### 📊 Account & Options Breakdown
        <div class="table-container">
            <table class="custom-table">
                <thead>
                    <tr>
                        <th style="width: 25%;">Account</th>
                        <th style="width: 25%;"><span class="badge-llc">🏢 LLC</span></th>
                        <th style="width: 25%;"><span class="badge-ira">💼 IRA</span></th>
                        <th style="width: 25%;"><span class="badge-total">🧮 TOTAL</span></th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="row-label">Worth</td>
                        <td class="cell-value">${int(llc_worth):,}</td>
                        <td class="cell-value">${int(ira_worth):,}</td>
                        <td class="bold-total">${int(total_worth):,}</td>
                    </tr>
                    <tr>
                        <td class="row-label">Put holding</td>
                        <td class="cell-value">${int(llc_puts):,} {get_pct_str(llc_puts, llc_worth, "green")}</td>
                        <td class="cell-value">${int(ira_puts):,} {get_pct_str(ira_puts, ira_worth, "green")}</td>
                        <td class="bold-total">${int(total_puts):,} {get_pct_str(total_puts, total_worth, "green")}</td>
                    </tr>
                    <tr>
                        <td class="row-label">Call holding</td>
                        <td class="cell-value">${int(llc_calls):,} {get_pct_str(llc_calls, llc_worth, "amber")}</td>
                        <td class="cell-value">${int(ira_calls):,} {get_pct_str(ira_calls, ira_worth, "amber")}</td>
                        <td class="bold-total">${int(total_calls):,} {get_pct_str(total_calls, total_worth, "amber")}</td>
                    </tr>
                    <tr>
                        <td class="row-label">Cash</td>
                        <td class="cell-value">${int(llc_cash):,} {get_pct_str(llc_cash, llc_worth, "gray")}</td>
                        <td class="cell-value">${int(ira_cash):,} {get_pct_str(ira_cash, ira_worth, "gray")}</td>
                        <td class="bold-total">${int(total_cash):,} {get_pct_str(total_cash, total_worth, "gray")}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        top_table_container.markdown(top_table_html, unsafe_allow_html=True)

        # --- SECOND TABLE (SAFE STREAMLIT RENDERING) ---
        if portfolio_assets:
            df_assets = pd.DataFrame(portfolio_assets)
            df_assets = df_assets.sort_values(by="Stock", ascending=True)

            styled_df = (
                df_assets.style.apply(highlight_breaches, axis=1)
                .map(color_movement, subset=["Today's Mvmnt"])
                .format(
                    {
                        "Strike": lambda x: f"{x:,.2f}" if pd.notna(x) else "-",
                        "Total Quantity": "{:d}",
                        "Current Price": lambda x: f"${x:,.2f}" if pd.notna(x) else "-",
                        "Live Asset Value": "${:,.2f}",
                    }
                )
            )
            
            with table_container.container():
                st.dataframe(styled_df, use_container_width=True, hide_index=True)

    update_live_view()

    for i, row in grouped_assets.iterrows():
        account = row["Account"]
        ticker = row["Stock"]
        opt_type = row["Opt Typ"]
        strike = row["Strike"]
        total_qty = row["Qty"]
        static_cash_reserve = row["Cash Reserve"]

        current_step = i + 1
        prog_msg = f"Streaming {ticker} ({current_step}/{total_assets_count}) | {account} {opt_type}"
        prog_bar.progress(current_step / total_assets_count, text=prog_msg)

        if opt_type == "HOLD":
            current_value = static_cash_reserve
            live_price = np.nan
            chg_display = "-"
        else:
            try:
                stock_obj = yf.Ticker(ticker)
                live_price = stock_obj.fast_info["lastPrice"]

                hist = stock_obj.history(period="2d")
                prev_close = (
                    hist["Close"].iloc[-2] if len(hist) >= 2 else live_price
                )
                day_diff = live_price - prev_close

                if day_diff > 0:
                    chg_display = f"▲ {day_diff:.2f}"
                elif day_diff < 0:
                    chg_display = f"▼ {abs(day_diff):.2f}"
                else:
                    chg_display = "0.00"

                if opt_type == "CALL":
                    effective_price = min(live_price, strike)
                elif opt_type == "PUT":
                    effective_price = (
                        live_price if live_price < strike else strike
                    )
                else:
                    effective_price = live_price

                current_value = total_qty * effective_price * 100

            except Exception:
                continue

        portfolio_assets.append(
            {
                "Stock": ticker,
                "Account": account,
                "Opt Type": opt_type,
                "Strike": strike,
                "Total Quantity": total_qty,
                "Current Price": live_price,
                "Live Asset Value": current_value,
                "Today's Mvmnt": chg_display,
            }
        )

        update_live_view()

    prog_bar.empty()


def render_portfolio_desk():
    st.title("🖥️ Live Portfolio Desk")

    col_btn, col_blank = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    sheet_data = load_live_data(SHEET_URL)

    if sheet_data.empty:
        st.info("No active data found or connection timed out.")
        return

    open_trades = sheet_data[sheet_data["Status"] == "Open"].copy()

    if "Account" in open_trades.columns:
        open_trades = open_trades[
            ~open_trades["Account"].astype(str).str.contains("401", na=False)
        ]
        open_trades["Account"] = open_trades["Account"].astype(str).str.strip()
    else:
        open_trades["Account"] = "Unknown"

    if "Strike Price" in open_trades.columns:
        open_trades["Strike"] = pd.to_numeric(
            open_trades["Strike Price"], errors="coerce"
        )
    elif "Strike" in open_trades.columns:
        open_trades["Strike"] = pd.to_numeric(
            open_trades["Strike"], errors="coerce"
        )
    else:
        open_trades["Strike"] = np.nan

    if "Opt Typ" not in open_trades.columns:
        open_trades["Opt Typ"] = ""
    if "Cash Reserve" not in open_trades.columns:
        open_trades["Cash Reserve"] = 0.0

    open_trades["Qty"] = (
        pd.to_numeric(open_trades["Qty"], errors="coerce").fillna(0).abs()
    )
    open_trades["Stock"] = open_trades["Stock"].astype(str).str.upper()
    open_trades["Opt Typ"] = open_trades["Opt Typ"].astype(str).str.upper()
    open_trades["Cash Reserve"] = pd.to_numeric(
        open_trades["Cash Reserve"], errors="coerce"
    ).fillna(0.0)

    # Sum up the 'Cash Reserve' column instead of 'Qty' for rows mapped to CASH
    cash_rows = open_trades[open_trades["Stock"] == "CASH"]
    account_cash = (
        cash_rows.groupby("Account")["Cash Reserve"].sum().to_dict()
        if not cash_rows.empty
        else {}
    )

    all_accounts = sorted(
        list(set(open_trades["Account"].unique()) - {"Unknown"})
    )

    # Trigger the fragment
    auto_updating_portfolio(open_trades, account_cash, all_accounts, sheet_data)


if __name__ == "__main__":
    render_portfolio_desk()