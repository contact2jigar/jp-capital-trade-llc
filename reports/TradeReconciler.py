#463-276-2996

import io
import pandas as pd
import requests
import streamlit as st

SHEET_URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=1662549766"


@st.cache_data(ttl=60)
def load_sheet_data(url):
    response = requests.get(url, timeout=10)
    df = pd.read_csv(io.BytesIO(response.content))
    df.columns = df.columns.str.strip()
    return df


def parse_custom_fidelity(file_obj):
    file_obj.seek(0)
    lines = [line.decode("utf-8").strip() for line in file_obj.readlines()]
    parsed_rows = []

    for line in lines:
        if not line or len(line.split(",")) < 5:
            continue
        f = [field.strip() for field in line.split(",")]
        if not f[2].startswith("-"):
            continue

        # ⚡ Single-line account mapping
        acc = (
            "IRA"
            if "IRA" in f[1]
            else (
                "LLC"
                if "LLC" in f[1] or "Limited Liability" in f[1]
                else f[1]
            )
        )

        opt = f[2].lstrip("-")
        idx = next((i for i, c in enumerate(opt) if c.isdigit()), 0)
        tick = opt[:idx]

        try:
            p_date = pd.to_datetime(opt[idx : idx + 6], format="%y%m%d")
            f_date = p_date.strftime("%d-%b-%Y").upper()
            leap = (p_date - pd.Timestamp.now()).days > 365
        except:
            f_date, leap = opt[idx : idx + 6], False

        typ = "Put" if opt[idx + 6 : idx + 7] == "P" else "Call"
        typ = (
            "CASH"
            if tick.upper() == "CASH"
            else ("LEAP CALL" if leap else typ)
        )

        parsed_rows.append(
            {
                "Fid_Stock": tick,
                "Fid_Account": acc,
                "Fid_Opt Typ": typ,
                "Fid_Close Date": f_date,
                "Fid_Strike Price": opt[idx + 7 :],
                "Fid_Qty": abs(float(f[4])) if f[4] else 0.0,
            }
        )
    return pd.DataFrame(parsed_rows)


def norm_strike(df, col):
    return (
        pd.to_numeric(df[col], errors="coerce")
        .fillna(0.0)
        .astype(float)
        .round(2)
        .astype(str)
    )

def icon_title(icon, text):
    st.markdown(f'<h1 style="display:flex;align-items:center;gap:12px;font-size:42px;font-weight:700;margin-bottom:0.5rem;"><span class="material-symbols-outlined" style="font-size:42px;">{icon}</span>{text}</h1>', unsafe_allow_html=True)

#icon_title("calculate", "Trade Reconciler")



try:
    sheet_data = load_sheet_data(SHEET_URL)
    open_trades = sheet_data[sheet_data["Status"] == "Open"].copy()
    if "Account" in open_trades.columns:
        open_trades = open_trades[
            ~open_trades["Account"].astype(str).str.contains("401", na=False)
        ]

    display_df = open_trades[
        ["Stock", "Account", "Opt Typ", "Close Date", "Strike Price", "Qty"]
    ].copy()
    display_df["Qty"] = pd.to_numeric(display_df["Qty"]).abs()
    display_df["Close Date"] = (
        pd.to_datetime(display_df["Close Date"])
        .dt.strftime("%d-%b-%Y")
        .str.upper()
    )
    display_df["Account"] = display_df["Account"].astype(str).str.upper()

    is_cash = display_df["Stock"].astype(str).str.upper() == "CASH"
    is_hold = display_df["Opt Typ"] == "HOLD"
    display_df.loc[is_cash & is_hold, "Opt Typ"] = "CASH"
    display_df.loc[~is_cash & is_hold, "Opt Typ"] = "LEAP CALL"
    display_df["Original Strike"] = norm_strike(display_df, "Strike Price")

    st.markdown("### 🔍 Filters")
    c1, c2, c3, c4 = st.columns(4)
    # ⚡ Collapsed UI elements into single lines
    with c1:
        sel_acc = st.selectbox(
            "Account",
            ["All"]
            + sorted(display_df["Account"].dropna().unique().tolist()),
        )
    with c2:
        sel_stock = st.multiselect(
            "Stock", sorted(display_df["Stock"].dropna().unique().tolist())
        )
    with c3:
        sel_opt = st.selectbox(
            "Opt Typ",
            ["All"] + sorted(display_df["Opt Typ"].dropna().unique().tolist()),
        )
    with c4:
        sel_date = st.selectbox(
            "Close Date",
            ["All"]
            + sorted(display_df["Close Date"].dropna().unique().tolist()),
        )

    def apply_filters(df, is_fid=False):
        prefix = "Fid_" if is_fid else ""
        if sel_acc != "All":
            df = df[df[f"{prefix}Account"] == str(sel_acc).upper()]
        if sel_stock:
            df = df[df[f"{prefix}Stock"].isin(sel_stock)]
        if sel_opt != "All":
            df = df[df[f"{prefix}Opt Typ"] == sel_opt]
        if sel_date != "All":
            df = df[df[f"{prefix}Close Date"] == sel_date]
        return df

    display_df = apply_filters(display_df)

    st.markdown("---")
    up_col, btn_col = st.columns([4, 1])
    # ⚡ Flattened file uploader
    with up_col:
        fidelity_file = st.file_uploader(
            "Upload Fidelity CSV here", type=["csv"]
        )

    fid_df = None
    if fidelity_file:
        fid_df = apply_filters(
            parse_custom_fidelity(fidelity_file), is_fid=True
        )


    with btn_col:
        st.write("")
        st.write("")
        reconcile_clicked = st.button("🔄 Reconcile", use_container_width=True)
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    tab1, tab2 = st.tabs(["🔄 Reconciliation", "📄 CSV Viewer"])

    # ⚡ Flattened dictionary generators for column configs
    grid_format = {
        col: st.column_config.NumberColumn(col, format="%d")
        for col in ["Qty", "Fid_Qty", "Difference"]
    }
    grid_format.update(
        {
            col: st.column_config.NumberColumn(col, format="%.2f")
            for col in ["Strike Price", "Fid_Strike Price"]
        }
    )

    def highlight_matches(val):
        if "✅" in str(val) or "Found" in str(val):
            return "background-color: #d4edda; color: #155724; font-weight: bold;"
        if "❌" in str(val) or "Missing" in str(val):
            return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
        if "⚠️" in str(val) or "Mismatch" in str(val):
            return "background-color: #fff3cd; color: #856404; font-weight: bold;"
        if "CASH" in str(val):
            return "background-color: #e2e3e5; color: #383d41; font-style: italic;"
        return ""

    reconciled_results = None

    with tab1:
        current_display = display_df.sort_values(by="Stock")

        if reconcile_clicked and fid_df is not None:
            cash_rows = display_df[
                display_df["Stock"].astype(str).str.upper() == "CASH"
            ].copy()
            cash_rows["Fid_Qty"], cash_rows["Difference"], cash_rows[
                "Match Status"
            ] = 0.0, cash_rows["Qty"], "CASH (Skipped)"

            p_sheet = display_df[
                display_df["Stock"].astype(str).str.upper() != "CASH"
            ].copy()
            p_fid = fid_df[
                fid_df["Fid_Stock"].astype(str).str.upper() != "CASH"
            ].copy()

            p_sheet["Strike Price"] = norm_strike(p_sheet, "Strike Price")
            p_fid["Fid_Strike Price"] = norm_strike(p_fid, "Fid_Strike Price")

            p_sheet.loc[
                p_sheet["Opt Typ"] == "LEAP CALL", "Strike Price"
            ] = ""
            p_fid.loc[
                p_fid["Fid_Opt Typ"] == "LEAP CALL", "Fid_Strike Price"
            ] = ""

            fid_grouped = (
                p_fid.groupby(
                    [
                        "Fid_Stock",
                        "Fid_Close Date",
                        "Fid_Opt Typ",
                        "Fid_Account",
                        "Fid_Strike Price",
                    ]
                )["Fid_Qty"]
                .sum()
                .reset_index()
            )

            merged = pd.merge(
                p_sheet,
                fid_grouped,
                left_on=[
                    "Stock",
                    "Close Date",
                    "Opt Typ",
                    "Account",
                    "Strike Price",
                ],
                right_on=[
                    "Fid_Stock",
                    "Fid_Close Date",
                    "Fid_Opt Typ",
                    "Fid_Account",
                    "Fid_Strike Price",
                ],
                how="outer",
            )

            merged["Qty"] = merged["Qty"].fillna(0)
            merged["Fid_Qty"] = merged["Fid_Qty"].fillna(0)
            merged["Difference"] = merged["Qty"] - merged["Fid_Qty"]

            def get_status(row):
                if pd.isna(row["Stock"]) and not pd.isna(row["Fid_Stock"]):
                    return "⚠️ Extra in Fid"
                if pd.isna(row["Fid_Stock"]) and not pd.isna(row["Stock"]):
                    return "❌ Missing in Fid"
                return (
                    "✅ Match"
                    if row["Difference"] == 0
                    else ("❌ Miss" if row["Difference"] > 0 else "⚠️ Extra")
                )

            merged["Match Status"] = merged.apply(get_status, axis=1)
            reconciled_results = merged.copy()

            for c in ["Stock", "Account", "Opt Typ", "Close Date"]:
                merged[c] = merged[c].fillna(merged[f"Fid_{c}"])
            merged["Strike Price"] = merged["Strike Price"].fillna(
                merged["Fid_Strike Price"]
            )

            final_df = merged.drop(
                columns=[
                    f"Fid_{x}"
                    for x in [
                        "Stock",
                        "Close Date",
                        "Opt Typ",
                        "Account",
                        "Strike Price",
                    ]
                ]
            )
            final_df = pd.concat(
                [final_df, cash_rows], ignore_index=True
            ).sort_values(by="Stock")

            # ⚡ Flattened result filter
            sel_match = st.selectbox(
                "📊 Filter by Result Type",
                ["All", "Matches Only", "Mismatches Only"],
            )
            if sel_match == "Matches Only":
                final_df = final_df[final_df["Match Status"] == "✅ Match"]
            elif sel_match == "Mismatches Only":
                final_df = final_df[
                    ~final_df["Match Status"].isin(
                        ["✅ Match", "CASH (Skipped)"]
                    )
                ]

            def add_visual_diff(row):
                if row["Match Status"] in [
                    "CASH (Skipped)",
                    "⚠️ Extra in Fid",
                    "❌ Missing in Fid",
                ]:
                    return row["Match Status"]
                x = row["Difference"]
                return (
                    "✅ Match"
                    if x == 0
                    else (f"❌ Miss ({int(x)})" if x > 0 else f"⚠️ Extra ({int(x)})")
                )

            final_df["Match Status"] = final_df.apply(add_visual_diff, axis=1)
            final_df["Strike Price"] = pd.to_numeric(
                final_df["Strike Price"], errors="coerce"
            ).fillna(0.0)
            current_display = final_df.style.map(
                highlight_matches, subset=["Match Status"]
            )

        elif reconcile_clicked and fid_df is None:
            st.error(
                "Please upload a Fidelity CSV file before hitting Reconcile!"
            )

        st.dataframe(
            current_display,
            use_container_width=True,
            hide_index=True,
            column_config=grid_format,
        )

    with tab2:
        if fid_df is not None:
            st.markdown("### Processed & Filtered CSV Output:")

            if reconcile_clicked and reconciled_results is not None:
                fid_audit = fid_df.copy()
                fid_audit["Fid_Strike Price"] = norm_strike(
                    fid_audit, "Fid_Strike Price"
                )

                audit_map = reconciled_results[
                    [
                        f"Fid_{x}"
                        for x in [
                            "Stock",
                            "Account",
                            "Opt Typ",
                            "Close Date",
                            "Strike Price",
                        ]
                    ]
                    + ["Match Status"]
                ].dropna(subset=["Fid_Stock"])
                audit_map.columns = [
                    "Fid_Stock",
                    "Fid_Account",
                    "Fid_Opt Typ",
                    "Fid_Close Date",
                    "Fid_Strike Price",
                    "Audit Status",
                ]

                # ⚡ Flattened audit mapper
                def map_clean_audit(v):
                    return (
                        "❌ Missing on Sheet"
                        if v == "⚠️ Extra in Fid"
                        else (
                            "✅ Found on Sheet"
                            if v == "✅ Match"
                            else "⚠️ Qty Mismatch"
                        )
                    )

                audit_map["Audit Status"] = audit_map["Audit Status"].apply(
                    map_clean_audit
                )

                fid_final = pd.merge(
                    fid_df,
                    audit_map.drop_duplicates(),
                    on=[
                        "Fid_Stock",
                        "Fid_Account",
                        "Fid_Opt Typ",
                        "Fid_Close Date",
                        "Fid_Strike Price",
                    ],
                    how="left",
                ).fillna({"Audit Status": "✅ Found on Sheet"})
                fid_final["Fid_Strike Price"] = pd.to_numeric(
                    fid_df["Fid_Strike Price"], errors="coerce"
                ).fillna(0.0)

                st.dataframe(
                    fid_final.sort_values(by="Fid_Stock").style.map(
                        highlight_matches, subset=["Audit Status"]
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config=grid_format,
                )
            else:
                st.dataframe(
                    fid_df.sort_values(by="Fid_Stock"),
                    use_container_width=True,
                    hide_index=True,
                    column_config=grid_format,
                )
        else:
            st.info("Upload a CSV file above to view the parsed output here.")

except Exception as e:
    st.error(f"Error: {e}")