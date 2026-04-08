import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
from datetime import datetime

# ========================================================
# 📥 DATA LOADING
# ========================================================
WATCHLIST_URL = "https://docs.google.com/spreadsheets/d/1x61uDuDKopnn9-DSuX5E3mAiMWk7-g4bPqbVH3D-q7M/export?format=csv&gid=337359953"

@st.cache_data(ttl=600)
def load_watchlist_data():
    try:
        response = requests.get(WATCHLIST_URL, verify=False, timeout=10)
        df = pd.read_csv(io.BytesIO(response.content))
        df.columns = df.columns.str.strip()
        df_clean = df.dropna(subset=[df.columns[0]]).copy()
        df_clean = df_clean.rename(columns={df.columns[0]: 'Stock', df.columns[1]: 'Stock Type'})
        df_clean['Stock'] = df_clean['Stock'].astype(str).str.strip().str.upper()
        df_clean['Stock Type'] = df_clean['Stock Type'].astype(str).str.strip()
        df_clean = df_clean[~df_clean['Stock'].isin(['STOCK', 'TICKER', 'CASH'])]
        return df_clean[['Stock', 'Stock Type']]
    except:
        return pd.DataFrame(columns=['Stock', 'Stock Type'])

def is_third_friday(date_str):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return d.weekday() == 4 and 15 <= d.day <= 21

@st.cache_data(ttl=3600)
def get_comprehensive_metrics(symbol):
    try:
        tk = yf.Ticker(symbol)
        expirations = tk.options
        if not expirations: return []
        
        monthly_expiries = [e for e in expirations if is_third_friday(e)]
        data_list = []
        
        for i, date_str in enumerate(monthly_expiries[:12]):
            opt = tk.option_chain(date_str)
            c_vol = opt.calls['volume'].sum()
            p_vol = opt.puts['volume'].sum()
            pcr = round(p_vol / c_vol if c_vol > 0 else 0, 2)
            
            # Risk Metrics for the closest monthly only
            iv, skew = 0.0, 0.0
            if i == 0:
                iv = opt.calls['impliedVolatility'].mean() * 100
                skew = (opt.puts['impliedVolatility'].mean() - opt.calls['impliedVolatility'].mean()) * 100

            data_list.append({
                "Stock": symbol,
                "Expiration": date_str,
                "PCR": pcr,
                "IV": round(iv, 2),
                "Skew": round(skew, 2)
            })
        return data_list
    except:
        return []

# ========================================================
# 🚀 UI RENDER
# ========================================================
st.set_page_config(layout="wide", page_title="Momentum Tracker")
st.title("🎯 Institutional Momentum & Risk Desk")

df_wl = load_watchlist_data()

if not df_wl.empty:
    # --- FILTERS ---
    col1, col2 = st.columns(2)
    with col1:
        u_types = sorted(df_wl['Stock Type'].unique().tolist())
        sel_types = st.multiselect("1. Filter by Stock Type", options=u_types)
    
    avail_df = df_wl[df_wl['Stock Type'].isin(sel_types)] if sel_types else df_wl
    with col2:
        u_stocks = sorted(avail_df['Stock'].unique().tolist())
        sel_stocks = st.multiselect("2. Select Specific Stocks", options=u_stocks)

    to_scan = sel_stocks if sel_stocks else avail_df['Stock'].tolist()

    if st.button(f"📡 Run Advanced Scan ({len(to_scan)} Tickers)", use_container_width=True):
        all_results = []
        status = st.empty()
        p_bar = st.progress(0)
        
        for i, t in enumerate(to_scan):
            status.text(f"Analyzing {t}...")
            p_bar.progress((i + 1) / len(to_scan))
            all_results.extend(get_comprehensive_metrics(t))
            
        status.empty()
        p_bar.empty()

        if all_results:
            master_df = pd.DataFrame(all_results)
            master_df['Exp_Date'] = pd.to_datetime(master_df['Expiration'])
            
            # --- TABLE 1: RISK & VELOCITY (CURRENT MONTH) ---
            st.subheader("🛡️ Immediate Risk & Velocity (Next 30 Days)")
            curr_expiry = master_df.sort_values('Exp_Date')['Expiration'].iloc[0]
            risk_df = master_df[master_df['Expiration'] == curr_expiry].copy()
            
            # Calculate Delta (Current PCR vs Next Month PCR)
            unique_exps = sorted(master_df['Expiration'].unique())
            if len(unique_exps) > 1:
                next_expiry = unique_exps[1]
                next_vals = master_df[master_df['Expiration'] == next_expiry].set_index('Stock')['PCR']
                risk_df['PCR Delta'] = risk_df.apply(lambda x: round(x['PCR'] - next_vals.get(x['Stock'], x['PCR']), 2), axis=1)
            else:
                risk_df['PCR Delta'] = 0.0

            def style_risk(v, col):
                if col == 'Skew' and v > 5: return 'background-color: #4c1d1d; color: white'
                if col == 'PCR Delta' and v > 0: return 'color: #ef4444' # Trend getting more bearish
                if col == 'PCR Delta' and v < 0: return 'color: #10b981' # Trend getting more bullish
                return ''

            st.dataframe(
                risk_df[['Stock', 'PCR', 'PCR Delta', 'IV', 'Skew']].style.apply(
                    lambda x: [style_risk(v, x.name) for v in x], axis=0
                ).format(precision=2), 
                use_container_width=True, hide_index=True
            )

            # --- TABLE 2: 1-YEAR MATRIX ---
            st.write("---")
            st.subheader("📅 1-Year Sentiment Lifecycle")
            master_df['Exp_Label'] = master_df['Exp_Date'].dt.strftime('%m/%y')
            matrix = master_df.pivot(index='Stock', columns='Exp_Label', values='PCR')
            matrix['Avg PCR'] = matrix.mean(axis=1)
            matrix = matrix.reset_index()

            def style_matrix(v):
                if pd.isna(v) or v == 0: return 'color: #727272'
                if v > 1.2: return 'background-color: #7f1d1d; color: white; font-weight: bold'
                if v < 0.6: return 'background-color: #064e3b; color: white; font-weight: bold'
                return 'color: #9ca3af'

            st.dataframe(
                matrix.style.applymap(style_matrix, subset=matrix.columns[1:])
                .format(precision=2), 
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("No data found for selected tickers.")
else:
    st.error("Watchlist could not be loaded.")