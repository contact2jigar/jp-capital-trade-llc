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
                metrics_dict[ticker] = {
                    'Last Close': last_close,
                    'Chg': last_close - prev_close,
                    'Chg (%)': ((last_close - prev_close) / prev_close) * 100,
                    '20D MA': hist['Close'].rolling(window=20).mean().iloc[-1] if len(hist) >= 20 else last_close,
                    '50D MA': hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else last_close,
                    '100D MA': hist['Close'].rolling(window=100).mean().iloc[-1] if len(hist) >= 100 else last_close,
                    '200D MA': hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else last_close,
                    'Earnings': t_obj.calendar['Earnings Date'][0].strftime('%Y-%m-%d') if t_obj.calendar and 'Earnings Date' in t_obj.calendar else ""
                }
        except:
            metrics_dict[ticker] = {'Last Close': 0, 'Chg': 0, 'Chg (%)': 0, '20D MA': 0, '50D MA': 0, '100D MA': 0, '200D MA': 0, 'Earnings': ""}
    return metrics_dict

# ========================================================
# 🧠 EARNINGS ALERT LOGIC
# ========================================================
def compute_earning_alert(earn_date_str):
    if not earn_date_str: return "🔴"
    try:
        today = datetime.now().date()
        earn_date = datetime.strptime(earn_date_str, '%Y-%m-%d').date()
        pre_friday = earn_date - timedelta(days=(earn_date.isoweekday() - 5))
        days_left = (pre_friday - today).days
        if pre_friday <= today: return f"🔴 ({days_left}d)"
        elif days_left < 14: return f"⚪ ({days_left}d)"
        elif days_left <= 30: return f"💰 ({days_left}d)"
        elif days_left <= 40: return f"🟢 ({days_left}d)"
        else: return f"🟡 ({days_left}d)"
    except: return "🔴"

# ========================================================
# 🎨 MAIN RENDER FUNCTION
# ========================================================
def render_trade_setup(df_raw):
    st.markdown("<style>div[data-testid='stDataEditor'] th {text-align: center !important; white-space: normal !important;}</style>", unsafe_allow_html=True)
    
    if "last_g_call" not in st.session_state: st.session_state.last_g_call = 0.25
    if "last_g_put" not in st.session_state: st.session_state.last_g_put = 0.25
    if "row_deltas" not in st.session_state: st.session_state.row_deltas = {}

    with st.expander("🛠️ Control Panel", expanded=True):
        col1, col2, col3, col4, col5 = st.columns([1.8, 1.8, 1.8, 1.8, 2])
        with col1:
            fridays = get_fridays()
            st.session_state.current_exp = st.selectbox("Expiry", fridays, index=fridays.index(get_next_third_friday()) if get_next_third_friday() in fridays else 0)
        with col2:
            call_delta = st.number_input("Call Delta", value=0.15, step=0.05)
            put_delta = st.number_input("Put Delta", value=0.30, step=0.05)
        with col3:
            sel_close_date = st.selectbox("Close Date", ["All Dates"] + sorted(df_raw['Close Date'].unique().tolist()) if not df_raw.empty else ["All Dates"])
        with col4:
            sel_acc = st.selectbox("Account", ["All Accounts"] + sorted(df_raw['Account'].unique().tolist()) if not df_raw.empty else ["All Accounts"])
        with col5:
            st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
            a1, a2, a3 = st.columns(3)
            run_pressed, select_all = a1.button("▶️"), a2.toggle("", value=True)
            if a3.button("🔄"): st.cache_data.clear(); st.rerun()

    df_filtered = df_raw.copy()
    if not df_filtered.empty:
        if sel_close_date != "All Dates":
            df_filtered = df_filtered[df_filtered['Close Date'] == sel_close_date]

        # ========================================================
        # 🏦 ACCOUNT SUMMARY TABLE (With Custom Valuation Rules)
        # ========================================================
        st.markdown("### 🏦 Account Summary")
        
        summary_calc = df_filtered.copy()
        
        # APPLYING CUSTOM RULES:
        # Put: min(Strike, Current) | Call: min(Current, Strike) 
        # (Both effectively use the minimum of the two for a conservative "At Risk" value)
        def apply_valuation_price(row):
            cp = row['Current Price']
            sp = row['Strike Price']
            opt_type = str(row['Opt Typ']).upper()
            
            if "PUT" in opt_type:
                return sp if sp < cp else cp
            elif "CALL" in opt_type:
                return cp if cp < sp else sp
            return cp # Default/Cash
            
        summary_calc['Effective Price'] = summary_calc.apply(apply_valuation_price, axis=1)
        summary_calc['Val'] = summary_calc['Qty'] * summary_calc['Effective Price'] * 100
        
        def get_sums(df_sub):
            llc = df_sub[df_sub['Account'].str.contains('LLC', case=False, na=False)]['Val'].sum()
            ira = df_sub[df_sub['Account'].str.contains('IRA', case=False, na=False)]['Val'].sum()
            return llc, ira, llc + ira

        t_llc, t_ira, t_tot = get_sums(summary_calc)
        p_llc, p_ira, p_tot = get_sums(summary_calc[summary_calc['Opt Typ'].str.upper() == 'PUT'])
        c_llc, c_ira, c_tot = get_sums(summary_calc[summary_calc['Opt Typ'].str.upper() == 'CALL'])

        summary_display = pd.DataFrame({
            "Account": ["Market Value", "Total Puts", "Total Calls"],
            "LLC": [t_llc, p_llc, c_llc],
            "IRA": [t_ira, p_ira, c_ira],
            "Total": [t_tot, p_tot, c_tot]
        })

        st.dataframe(
            summary_display, hide_index=True, use_container_width=True,
            column_config={c: st.column_config.NumberColumn(c, format="$%.2f") for c in ["LLC", "IRA", "Total"]}
        )

        # ========================================================
        # 🔗 TRADE SETUP QUEUE
        # ========================================================
        st.markdown("### 📊 Trade Setup Queue")
        
        display_df = df_filtered.copy()
        if sel_acc != "All Accounts":
            display_df = display_df[display_df['Account'] == sel_acc]
            
        agg_setup = display_df.groupby(['Stock','Account','Opt Typ'], as_index=False).agg({
            'Qty': 'sum', 'Current Price': 'first', 'Strike Price': 'first', 'Close Date': 'first'
        })
        agg_setup["Process?"] = select_all
        
        live_metrics = fetch_ticker_metrics(agg_setup['Stock'].unique().tolist())
        for m in ['Last Close', 'Chg', 'Chg (%)', '20D MA', '50D MA', '100D MA', '200D MA', 'Earnings']:
            agg_setup[m] = agg_setup['Stock'].apply(lambda x: live_metrics.get(x, {}).get(m, ""))
        
        agg_setup['Earning Alert'] = agg_setup['Earnings'].apply(compute_earning_alert)
        agg_setup = agg_setup.rename(columns={'Stock': 'Ticker', 'Opt Typ': 'Type', 'Strike Price': 'Strike'})
        
        cols = ["Ticker", "Account", "Type", "Current Price", "Close Date", "Strike", "Chg", "Chg (%)", "Last Close", "Earnings", "Earning Alert", "20D MA", "50D MA", "100D MA", "200D MA", "Qty", "Process?"]
        for c in cols: 
            if c not in agg_setup.columns: agg_setup[c] = ""
        
        t_config = {c: st.column_config.NumberColumn(c, format="$%.2f") for c in ["Current Price", "Strike", "Last Close", "Chg", "20D MA", "50D MA", "100D MA", "200D MA"]}
        t_config["Chg (%)"] = st.column_config.NumberColumn("Chg (%)", format="%.2f%%")
        t_config["Process?"] = st.column_config.CheckboxColumn("Select", default=True)
        t_config["Qty"] = st.column_config.NumberColumn("Qty", format="%d")

        edited = st.data_editor(
            agg_setup[cols], hide_index=True, use_container_width=True, 
            column_config=t_config, key="setup_grid",
            disabled=[c for c in cols if c not in ["Process?", "Qty"]]
        )
        st.session_state.pending_df = edited.rename(columns={'Ticker': 'Stock', 'Type': 'Opt Typ', 'Process?': 'Select'})

    if run_pressed:
        st.session_state.active_tab = "📊 Portfolio Snapshot"
        st.session_state.scanning_now = True
        st.rerun()