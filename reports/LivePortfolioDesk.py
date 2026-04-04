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


# Isolated fragment that auto-refreshes every 60 seconds
@st.fragment(run_every=60)
def auto_updating_portfolio(open_trades, account_cash, all_accounts, sheet_data):

    # Move progress bar here so it doesn't flicker the outside page
    prog_bar = st.empty()

    # Place inside the fragment so they remain stable containers
    metrics_container = st.empty()
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
    
    # ⚡ NEW: We calculate the true live balances using the shared engine logic first
    live_balances = calculate_live_balances(sheet_data)

    def update_live_view():
        with metrics_container.container():
            if all_accounts:
                cols = st.columns(len(all_accounts) + 1)
                grand_total = 0.0

                for idx, acct in enumerate(all_accounts):
                    # ⚡ Pull the computed value directly from the shared dict
                    acct_total = live_balances.get(acct, 0.0)
                    grand_total += acct_total

                    # We can isolate cash to solve for equity breakdown display
                    acct_cash = account_cash.get(acct, 0.0)
                    acct_eq = acct_total - acct_cash

                    with cols[idx]:
                        st.metric(
                            label=f"{acct} Worth",
                            value=f"${acct_total:,.2f}",
                            help=f"Eq: ${acct_eq:,.2f} | Cash: ${acct_cash:,.2f}",
                        )
                with cols[-1]:
                    st.metric(
                        label="Grand Total Worth",
                        value=f"${grand_total:,.2f}",
                    )

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
            table_container.dataframe(
                styled_df, use_container_width=True, hide_index=True
            )

    # Trigger baseline view
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

    # Filter out 401k accounts
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

    cash_rows = open_trades[open_trades["Stock"] == "CASH"]
    account_cash = (
        cash_rows.groupby("Account")["Qty"].sum().to_dict()
        if not cash_rows.empty
        else {}
    )

    all_accounts = sorted(
        list(set(open_trades["Account"].unique()) - {"Unknown"})
    )

    st.subheader("📊 Account Breakdown")

    # ⚡ Added sheet_data here so the engine call can evaluate the raw sheet
    auto_updating_portfolio(open_trades, account_cash, all_accounts, sheet_data)


if __name__ == "__main__":
    render_portfolio_desk()