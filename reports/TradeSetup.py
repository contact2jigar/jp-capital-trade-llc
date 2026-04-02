import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from reports.engine import get_fridays, get_next_third_friday

# ========================================================
# ⚡ CACHED YAHOO FINANCE DATA FETCHER
# ========================================================
@st.cache_data(ttl=300)
def fetch_ticker_metrics(ticker_list):
    metrics_dict = {}
    
    for ticker in ticker_list:
        if ticker == "CASH" or not ticker:
            continue
            
        try:
            t_obj = yf.Ticker(ticker)
            hist = t_obj.history(period="1y")
            
            if not hist.empty:
                last_close = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else last_close
                
                chg = last_close - prev_close
                chg_pct = (chg / prev_close) * 100
                
                ma20 = hist['Close'].rolling(window=20).mean().iloc[-1] if len(hist) >= 20 else last_close
                ma50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else last_close
                ma100 = hist['Close'].rolling(window=100).mean().iloc[-1] if len(hist) >= 100 else last_close
                ma200 = hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else last_close
                
                earnings_str = ""
                cal = t_obj.calendar
                if cal is not None and 'Earnings Date' in cal:
                    e_dates = cal['Earnings Date']
                    if e_dates:
                        earnings_str = e_dates[0].strftime('%Y-%m-%d')
                
                metrics_dict[ticker] = {
                    'Last Close': last_close,
                    'Chg': chg,
                    'Chg (%)': chg_pct,
                    '20D MA': ma20,
                    '50D MA': ma50,
                    '100D MA': ma100,
                    '200D MA': ma200,
                    'Earnings': earnings_str
                }
        except:
            metrics_dict[ticker] = {
                'Last Close': 0, 'Chg': 0, 'Chg (%)': 0,
                '20D MA': 0, '50D MA': 0, '100D MA': 0, '200D MA': 0,
                'Earnings': ""
            }
            
    return metrics_dict

# ========================================================
# 🧠 EARNINGS ALERT LOGIC
# ========================================================
def compute_earning_alert(earn_date_str):
    if not earn_date_str:
        return "🔴"
        
    try:
        today = datetime.now().date()
        earn_date = datetime.strptime(earn_date_str, '%Y-%m-%d').date()
        
        weekday_val = earn_date.isoweekday()
        offset = weekday_val - 5
        pre_friday = earn_date - timedelta(days=offset)
        
        days_left = (pre_friday - today).days
        
        if pre_friday <= today:
            return f"🔴 ({days_left}d)"
        elif days_left < 14:
            return f"⚪ ({days_left}d)"
        elif days_left <= 30:
            return f"💰 ({days_left}d)"
        elif days_left <= 40:
            return f"🟢 ({days_left}d)"
        else:
            return f"🟡 ({days_left}d)"
    except Exception:
        return "🔴"

def render_trade_setup(df_raw):
    
    # Inject CSS to wrap and center align headers
    st.markdown(
        """
        <style>
        /* Target data grid headers */
        div[data-testid="stDataEditor"] th {
            text-align: center !important;
            white-space: normal !important;
            vertical-align: middle !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # 1. Initialize Global Trackers
    if "last_g_call" not in st.session_state: st.session_state.last_g_call = 0.25
    if "last_g_put" not in st.session_state: st.session_state.last_g_put = 0.25
    if "row_deltas" not in st.session_state: st.session_state.row_deltas = {}

    with st.expander("🛠️ Control Panel", expanded=True):
        col1, col2, col3, col4, col5 = st.columns([1.8, 1.8, 1.8, 1.8, 2])

        with col1:
            fridays = get_fridays()
            default_exp = get_next_third_friday()
            default_index = fridays.index(default_exp) if default_exp in fridays else 0
            st.session_state.current_exp = st.selectbox("Expiry", fridays, index=default_index)

        with col2:
            call_delta = st.number_input("Call Delta", value=0.15, step=0.05, key="call_delta")
            put_delta = st.number_input("Put Delta", value=0.30, step=0.05, key="put_delta")

        with col3:
            close_dates = ["All Dates"] + sorted(df_raw['Close Date'].unique().tolist()) if not df_raw.empty else ["All Dates"]
            sel_close_date = st.selectbox("Close Date", close_dates)

        with col4:
            acc_list = ["All Accounts"] + sorted(df_raw['Account'].unique().tolist()) if not df_raw.empty else ["All Accounts"]
            sel_acc = st.selectbox("Account", acc_list)

        with col5:
            st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
            a1, a2, a3 = st.columns(3)
            run_pressed = a1.button("▶️")
            select_all = a2.toggle("", value=True, label_visibility="collapsed")

            if a3.button("🔄", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    globals_changed = (st.session_state.last_g_call != call_delta) or (st.session_state.last_g_put != put_delta)

    df_filtered = df_raw.copy()
    if not df_filtered.empty:
        if sel_close_date != "All Dates":
            df_filtered = df_filtered[df_filtered['Close Date'] == sel_close_date]

        with st.expander("🎯 Fine-Tune Custom Deltas", expanded=False):
            search_query = st.text_input("🔍 Search Ticker").upper().strip()
            ft_df = df_filtered.copy()
            if sel_acc != "All Accounts":
                ft_df = ft_df[ft_df['Account'] == sel_acc]

            fine_tune_data = ft_df.groupby(['Stock','Account','Opt Typ'], as_index=False)['Qty'].sum().query("Stock != 'CASH'")
            if search_query:
                fine_tune_data = fine_tune_data[fine_tune_data['Stock'].str.contains(search_query)]

            btn_cols = st.columns(3)
            for i, row in fine_tune_data.iterrows():
                row_id = f"{row['Stock']}_{row['Account']}_{row['Opt Typ']}".replace(" ", "_")
                opt_type = str(row['Opt Typ']).upper()
                default_target = put_delta if "PUT" in opt_type else call_delta

                if row_id not in st.session_state.row_deltas or globals_changed:
                    st.session_state.row_deltas[row_id] = default_target

                with btn_cols[i % 3]:
                    with st.container(border=True):
                        st.write(f"**{row['Stock']}** ({row['Account']})")
                        r1, r2, r3 = st.columns([1.2, 1, 1])
                        r1.metric("Delta", f"{st.session_state.row_deltas[row_id]:.2f}")
                        if r2.button("➕", key=f"inc_{row_id}"):
                            st.session_state.row_deltas[row_id] = round(st.session_state.row_deltas[row_id] + 0.01, 2)
                            st.rerun()
                        if r3.button("➖", key=f"dec_{row_id}"):
                            st.session_state.row_deltas[row_id] = round(st.session_state.row_deltas[row_id] - 0.01, 2)
                            st.rerun()

        st.session_state.last_g_call = call_delta
        st.session_state.last_g_put = put_delta

        # ========================================================
        # 🔗 Consolidated Table with Custom MAs and Sheet Metrics
        # ========================================================
        st.markdown("### 📊 Trade Setup Queue")
        
        display_df = df_filtered.copy()
        if sel_acc != "All Accounts":
            display_df = display_df[display_df['Account'] == sel_acc]
            
        agg_setup = display_df.groupby(['Stock','Account','Opt Typ'], as_index=False).agg({
            'Qty': 'sum',
            'Current Price': 'first',  
            'Strike Price': 'first',
            'Close Date': 'first'
        })
        
        agg_setup["Process?"] = select_all
        
        unique_tickers = agg_setup['Stock'].unique().tolist()
        with st.spinner("Fetching market technicals from Yahoo Finance..."):
            live_metrics = fetch_ticker_metrics(unique_tickers)
            
        for metric in ['Last Close', 'Chg', 'Chg (%)', '20D MA', '50D MA', '100D MA', '200D MA', 'Earnings']:
            agg_setup[metric] = agg_setup['Stock'].apply(lambda x: live_metrics.get(x, {}).get(metric, ""))
        
        agg_setup['Earning Alert'] = agg_setup['Earnings'].apply(compute_earning_alert)
        
        # Renamed 'Current Price' directly here instead of 'Current Px'
        agg_setup = agg_setup.rename(columns={
            'Stock': 'Ticker',
            'Opt Typ': 'Type',
            'Strike Price': 'Strike'
        })
        
        # Array order matches the renamed column
        col_order = [
            "Ticker", "Account", "Type", "Current Price", "Close Date", "Strike", 
            "Chg", "Chg (%)", "Last Close", "Earnings", "Earning Alert",
            "20D MA", "50D MA", "100D MA", "200D MA", "Qty", "Process?"
        ]
        
        for col in col_order:
            if col not in agg_setup.columns:
                agg_setup[col] = ""
                
        agg_setup = agg_setup[col_order]

        # Updated key string in t_config dictionary
        t_config = {
            "Process?": st.column_config.CheckboxColumn("Select", default=True),
            "Qty": st.column_config.NumberColumn("Qty", format="%d"),
            "Current Price": st.column_config.NumberColumn("Current Price", format="$%.2f"),
            "Strike": st.column_config.NumberColumn("Strike", format="$%.2f"),
            "Last Close": st.column_config.NumberColumn("Last Close", format="$%.2f"),
            "Chg": st.column_config.NumberColumn("Chg", format="$%.2f"),
            "Chg (%)": st.column_config.NumberColumn("Chg (%)", format="%.2f%%"),
            "20D MA": st.column_config.NumberColumn("20D MA", format="$%.2f"),
            "50D MA": st.column_config.NumberColumn("50D MA", format="$%.2f"),
            "100D MA": st.column_config.NumberColumn("100D MA", format="$%.2f"),
            "200D MA": st.column_config.NumberColumn("200D MA", format="$%.2f")
        }

        edited_combined = st.data_editor(
            agg_setup, 
            hide_index=True, 
            use_container_width=True, 
            key="edit_combined_grid", 
            column_config=t_config, 
            disabled=[c for c in col_order if c not in ["Process?", "Qty"]]
        )

        edited_combined = edited_combined.rename(columns={'Ticker': 'Stock', 'Type': 'Opt Typ', 'Process?': 'Select'})
        st.session_state.pending_df = edited_combined

    if run_pressed:
        st.session_state.active_tab = "📊 Portfolio Snapshot"
        st.session_state.scanning_now = True
        st.rerun()