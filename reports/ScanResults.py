from datetime import datetime
import yfinance as yf
from reports.engine import get_option_by_delta
import numpy as np
import pandas as pd
import streamlit as st


# =========================
# 📊 TABLE FORMATTER & STYLER
# =========================
def format_display_table(df):
    # Moved "Delta" to be just before "Qty"
    display_cols = [
        "Ticker",
        "Type",
        "Price",
        "Strike",
        "Chg vs Excel",
        "Excel Strike",
        "Premium",
        "Credit",
        "ROI",
        "AOR",
        "% Disc",
        "Upside",
        "Delta",
        "Qty",
        "Total Value",
    ]
    rename_map = {
        "Type": "Opt Type",
        "Price": "Current Price",
        "Excel Strike": "Current Strike",
    }
    df = df.copy()
    for col in display_cols:
        if col not in df.columns:
            df[col] = ""
    return df[display_cols].rename(columns=rename_map)


# ⚡ Darker alternating row background and dynamic strike coloring
def style_table_rows(df):
    bg_color = "#dee3e8"
    text_color = "#000000"

    style_matrix = pd.DataFrame("", index=df.index, columns=df.columns)

    for idx, row in df.iterrows():
        # Apply base alternating rows
        base_style = (
            f"background-color: {bg_color}; color: {text_color};"
            if idx % 2 == 0
            else ""
        )
        style_matrix.loc[idx] = base_style

        # Color the specific change digits only
        chg_val = str(row.get("Chg vs Excel", ""))
        if "+" in chg_val:
            style_matrix.loc[idx, "Chg vs Excel"] = (
                f"{base_style} color: #16a34a; font-weight: bold;"
            )
        elif "-" in chg_val:
            style_matrix.loc[idx, "Chg vs Excel"] = (
                f"{base_style} color: #dc2626; font-weight: bold;"
            )

    return style_matrix


# =========================
# 📊 MAIN SCANNER FUNCTION
# =========================
def render_scan_results(df_raw, render_projection, prog_bar):
    llc_header, tbl_llc = st.empty(), st.empty()
    ira_header, tbl_ira = st.empty(), st.empty()

    if st.session_state.get("scanning_now", False):

        if "pending_df" in st.session_state:
            df = st.session_state.pending_df
            select_col = "Select" if "Select" in df.columns else "Process?"
            active_trades = df[df[select_col] == True]
        else:
            active_trades = pd.DataFrame()

        if active_trades.empty:
            st.session_state.scanning_now = False
            st.warning(
                "No trades selected to scan. Please select trades in the Trade Setup tab."
            )
            return

        results = []

        for i, (_, row) in enumerate(active_trades.iterrows(), start=1):
            result_row = None
            opt_type_str = str(row["Opt Typ"]).upper()

            # --- 🟡 CASH LOGIC ---
            if "CASH" in opt_type_str:
                prog_bar.progress(
                    i / len(active_trades),
                    f"Processing {row['Stock']} ({i}/{len(active_trades)}) | Cash",
                )
                try:
                    orig_row = df_raw[
                        (df_raw["Stock"] == row["Stock"])
                        & (df_raw["Account"] == row["Account"])
                        & (df_raw["Opt Typ"] == row["Opt Typ"])
                    ].iloc[0]
                    cash_val = float(
                        str(orig_row["Profit Loss"]).replace(",", "")
                    )
                except:
                    cash_val = 0
                result_row = {
                    "Account": row["Account"],
                    "Ticker": "CASH",
                    "Price": "",
                    "Type": "CASH",
                    "Excel Strike": "",
                    "Strike": "",
                    "% Disc": "",
                    "Upside": "",
                    "Chg vs Excel": "",
                    "Premium": "",
                    "Credit": f"${cash_val:,.2f}",
                    "Credit_Raw": 0,
                    "Qty": 1,
                    "Total Value": f"${cash_val:,.0f}",
                    "Strike_Val_Raw": cash_val,
                    "Delta": "",
                    "ROI": "",
                    "AOR": "",
                }

            # --- 🔵 HOLD LOGIC ---
            elif "HOLD" in opt_type_str:
                prog_bar.progress(
                    i / len(active_trades),
                    f"Processing {row['Stock']} ({i}/{len(active_trades)}) | Hold",
                )
                try:
                    orig_row = df_raw[
                        (df_raw["Stock"] == row["Stock"])
                        & (df_raw["Account"] == row["Account"])
                        & (df_raw["Opt Typ"] == row["Opt Typ"])
                    ].iloc[0]

                    if "Cash Reserve" in orig_row:
                        cash_res_val = float(
                            str(orig_row["Cash Reserve"])
                            .replace("$", "")
                            .replace(",", "")
                        )
                    else:
                        cash_res_val = float(
                            str(orig_row["Profit Loss"])
                            .replace("$", "")
                            .replace(",", "")
                        )

                    ex_strike = float(orig_row["Strike Price"])
                    result_row = {
                        "Account": row["Account"],
                        "Ticker": row["Stock"],
                        "Price": "",
                        "Type": row["Opt Typ"],
                        "Excel Strike": f"{ex_strike:.2f}",
                        "Strike": f"{ex_strike:.2f}",
                        "% Disc": "",
                        "Upside": "",
                        "Chg vs Excel": "",
                        "Premium": 0,
                        "Credit": "$0.00",
                        "Credit_Raw": 0,
                        "Qty": row["Qty"],
                        "Total Value": f"${cash_res_val:,.0f}",
                        "Strike_Val_Raw": cash_res_val,
                        "Delta": "",
                        "ROI": "0.00%",
                        "AOR": "0.00%",
                    }
                except:
                    pass

            # --- 🟢 OPTION SCANNING FLOW ---
            else:
                row_id = f"{row['Stock']}_{row['Account']}_{row['Opt Typ']}".replace(
                    " ", "_"
                )
                default_target = (
                    st.session_state.put_delta
                    if "PUT" in opt_type_str
                    else st.session_state.call_delta
                )
                current_target = st.session_state.row_deltas.get(
                    row_id, default_target
                )

                try:
                    t_obj = yf.Ticker(row["Stock"])
                    curr_px = t_obj.fast_info["lastPrice"]
                    side = "put" if "PUT" in opt_type_str else "call"
                    e_strike, e_bid, e_delta = get_option_by_delta(
                        row["Stock"],
                        st.session_state.current_exp,
                        side,
                        current_target,
                    )

                    status_msg = f"Scanning {row['Stock']} ({i}/{len(active_trades)}) | Strike: {e_strike:.2f} | Δ: {e_delta:.2f} | Prem: ${e_bid:.2f}"
                    prog_bar.progress(i / len(active_trades), status_msg)

                    excel_strike = 0
                    try:
                        orig_row = df_raw[
                            (df_raw["Stock"] == row["Stock"])
                            & (df_raw["Account"] == row["Account"])
                            & (df_raw["Opt Typ"] == row["Opt Typ"])
                        ].iloc[0]
                        excel_strike = float(orig_row["Strike Price"])
                    except:
                        pass

                    if "PUT" in opt_type_str:
                        strike = e_strike if e_strike > 0 else excel_strike
                    else:
                        strike = e_strike

                    if strike > 0:
                        credit = e_bid * row["Qty"] * 100
                        total_val = strike * row["Qty"] * 100
                        roi = e_bid / strike * 100
                        days = max(
                            (
                                datetime.strptime(
                                    st.session_state.current_exp, "%Y-%m-%d"
                                )
                                - datetime.now()
                            ).days,
                            1,
                        )

                        chg_display = ""
                        if excel_strike > 0 and strike != excel_strike:
                            diff = strike - excel_strike
                            chg_display = f"{int(diff):+d}"

                        # Put Discount Calculation
                        discount_str = ""
                        if "PUT" in opt_type_str and curr_px > 0:
                            discount_pct = (
                                (curr_px - strike) / curr_px
                            ) * 100
                            discount_str = f"{discount_pct:.2f}%"

                        # Call Upside Calculation
                        upside_str = ""
                        if "CALL" in opt_type_str and curr_px > 0:
                            upside_pct = ((strike - curr_px) / curr_px) * 100
                            upside_str = f"{upside_pct:.2f}%"

                        result_row = {
                            "Account": row["Account"],
                            "Ticker": row["Stock"],
                            "Price": f"${curr_px:,.2f}",
                            "Type": row["Opt Typ"],
                            "Excel Strike": f"{excel_strike:.2f}"
                            if excel_strike > 0
                            else "",
                            "Strike": f"{strike:.2f}",
                            "% Disc": discount_str,
                            "Upside": upside_str,
                            "Chg vs Excel": chg_display,
                            "Premium": e_bid,
                            "Credit": f"${credit:,.2f}",
                            "Credit_Raw": credit,
                            "Qty": row["Qty"],
                            "Total Value": f"${total_val:,.0f}",
                            "Strike_Val_Raw": total_val,
                            "Delta": f"{e_delta:.2f}",
                            "ROI": f"{roi:.2f}%",
                            "AOR": f"{roi * (365/days):.2f}%",
                        }
                except:
                    prog_bar.progress(
                        i / len(active_trades),
                        f"Scanning {row['Stock']} ({i}/{len(active_trades)}) - Fetch Failed",
                    )
                    continue

            if result_row:
                results.append(result_row)
                temp_df = pd.DataFrame(results)

                l_m = (
                    temp_df[temp_df.Account == "LLC"].Credit_Raw.sum()
                    if "LLC" in temp_df.Account.values
                    else 0
                )
                i_m = (
                    temp_df[temp_df.Account == "IRA"].Credit_Raw.sum()
                    if "IRA" in temp_df.Account.values
                    else 0
                )

                l_t = (
                    temp_df[temp_df.Account == "LLC"].Strike_Val_Raw.sum()
                    if "LLC" in temp_df.Account.values
                    else 0
                )
                i_t = (
                    temp_df[temp_df.Account == "IRA"].Strike_Val_Raw.sum()
                    if "IRA" in temp_df.Account.values
                    else 0
                )

                llc_header.markdown(f"### 🏢 LLC | 💰 ${l_t:,.0f}")
                ira_header.markdown(f"### 🎯 IRA | 💰 ${i_t:,.0f}")
                render_projection(l_m, i_m, l_t, i_t)

                llc_fmt = format_display_table(
                    temp_df[temp_df.Account == "LLC"]
                ).reset_index(drop=True)
                ira_fmt = format_display_table(
                    temp_df[temp_df.Account == "IRA"]
                ).reset_index(drop=True)

                llc_styled = (
                    llc_fmt.style.apply(style_table_rows, axis=None)
                    .format(
                        {"Premium": "{:.2f}", "Qty": "{:,.0f}"}, na_rep=""
                    )
                )
                ira_styled = (
                    ira_fmt.style.apply(style_table_rows, axis=None)
                    .format(
                        {"Premium": "{:.2f}", "Qty": "{:,.0f}"}, na_rep=""
                    )
                )

                tbl_llc.dataframe(
                    llc_styled, use_container_width=True, hide_index=True
                )
                tbl_ira.dataframe(
                    ira_styled, use_container_width=True, hide_index=True
                )

        st.session_state.scan_results = pd.DataFrame(results)
        st.session_state.scanning_now = False
        prog_bar.empty()
        st.rerun()

    elif st.session_state.get("scan_results") is not None:
        res = st.session_state.scan_results
        llc_res, ira_res = res[res.Account == "LLC"], res[res.Account == "IRA"]
        l_t, i_t = llc_res.Strike_Val_Raw.sum(), ira_res.Strike_Val_Raw.sum()
        llc_header.markdown(f"### 🏢 LLC | 💰 ${l_t:,.0f}")
        ira_header.markdown(f"### 🎯 IRA | 💰 ${i_t:,.0f}")

        render_projection(
            llc_res.Credit_Raw.sum(), ira_res.Credit_Raw.sum(), l_t, i_t
        )

        llc_fmt = format_display_table(llc_res).reset_index(drop=True)
        ira_fmt = format_display_table(ira_res).reset_index(drop=True)

        llc_styled = (
            llc_fmt.style.apply(style_table_rows, axis=None)
            .format({"Premium": "{:.2f}", "Qty": "{:,.0f}"}, na_rep="")
        )
        ira_styled = (
            ira_fmt.style.apply(style_table_rows, axis=None)
            .format({"Premium": "{:.2f}", "Qty": "{:,.0f}"}, na_rep="")
        )

        tbl_llc.dataframe(
            llc_styled, use_container_width=True, hide_index=True
        )
        tbl_ira.dataframe(
            ira_styled, use_container_width=True, hide_index=True
        )

        # --- CONSOLIDATED VIEW ---
        st.markdown("---")
        st.markdown("### 📊 Consolidated Portfolio")

        agg_df = res[
            ~res["Type"].str.contains("CASH|HOLD", case=False, na=False)
        ].copy()

        if not agg_df.empty:

            def clean_v(v):
                return (
                    float(str(v).replace("$", "").replace(",", ""))
                    if v and v != ""
                    else 0
                )

            summary = (
                agg_df.groupby(["Ticker", "Type"])
                .agg({"Price": "first", "Strike": "first", "Qty": "sum"})
                .reset_index()
            )
            summary["Total Mkt Val"] = summary.apply(
                lambda x: clean_v(x["Price"]) * x["Qty"] * 100, axis=1
            )
            summary["Total Strike Val"] = summary.apply(
                lambda x: clean_v(x["Strike"]) * x["Qty"] * 100, axis=1
            )
            summary["Total Mkt Val"] = summary["Total Mkt Val"].map(
                "${:,.0f}".format
            )
            summary["Total Strike Val"] = summary["Total Strike Val"].map(
                "${:,.0f}".format
            )

            summary_styled = (
                summary.reset_index(drop=True)
                .style.apply(style_table_rows, axis=None)
                .format({"Qty": "{:,.0f}"}, na_rep="")
            )
            st.dataframe(
                summary_styled, use_container_width=True, hide_index=True
            )