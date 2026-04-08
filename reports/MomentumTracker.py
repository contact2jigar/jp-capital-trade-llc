import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
from datetime import datetime

# ========================================================
# 📥 DATA LOADING (Watchlist)
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

@st.cache_data(ttl=3600)
def get_detailed_pcr(symbol):
    """Fetches PCR for the next 12 monthly-style expirations."""
    try:
        tk = yf.Ticker(symbol)
        expirations = tk.options
        if not expirations: return []
        
        monthly_data = []
        # We look at up to 15 expirations to find the main monthlies
        for date_str in expirations[:15]:
            opt = tk.option_chain(date_str)
            c_vol = opt.calls['volume'].sum()
            p_vol = opt.puts['volume'].sum()
            
            if c_vol + p_vol > 50:  # Only include if there is meaningful activity
                pcr = p_vol / c_vol if c_vol > 0 else 0
                monthly_data.append({
                    "Stock": symbol,
                    "Expiration": date_str,
                    "PCR": round(pcr, 2),
                    "Call Vol": int(c_vol),
                    "Put Vol": int(p_vol),
                    "Total Vol": int(c_vol + p_vol)
                })
        return monthly_data
    except:
        return []

# ========================================================
# 🚀 UI RENDER
# ========================================================
st.title("🎯 Multi-Expiry Momentum Tracker")

df_wl = load_watchlist_data()

if not df_wl.empty:
    col1, col2 = st.columns(2)
    with col1:
        u_types = sorted(df_wl['Stock Type'].unique().tolist())
        sel_types = st.multiselect("Filter by Stock Type", options=u_types)
    
    avail_df = df_wl[df_wl['Stock Type'].isin(sel_types)] if sel_types else df_wl

    with col2:
        u_stocks = sorted(avail_df['Stock'].unique().tolist())
        sel_stocks = st.multiselect("Select Specific Stocks", options=u_stocks)

    to_scan = sel_stocks if sel_stocks else avail_df['Stock'].tolist()

    if st.button(f"📡 Analyze Forward Momentum ({len(to_scan)} Tickers)", use_container_width=True):
        all_results = []
        status = st.empty()
        p_bar = st.progress(0)
        
        for i, t in enumerate(to_scan):
            status.text(f"Fetching Forward Chain: {t}...")
            p_bar.progress((i + 1) / len(to_scan))
            data_list = get_detailed_pcr(t)
            all_results.extend(data_list)
            
        status.empty()
        p_bar.empty()

        if all_results:
            final_df = pd.DataFrame(all_results)
            # Convert expiration to datetime for proper sorting
            final_df['Expiration'] = pd.to_datetime(final_df['Expiration'])
            final_df = final_df.sort_values(['Expiration', 'PCR'], ascending=[True, False])
            
            # --- TABBED VIEW BY EXPIRATION ---
            unique_dates = sorted(final_df['Expiration'].unique())
            tabs = st.tabs([d.strftime('%b %Y') for d in unique_dates])

            def style_pcr(v):
                if v > 1.0: return 'background-color: #4c1d1d; color: white; font-weight: bold' 
                if v < 0.6: return 'background-color: #1e3a24; color: white; font-weight: bold'
                return ''

            for i, date_obj in enumerate(unique_dates):
                with tabs[i]:
                    st.write(f"### 🗓️ Expiry: {date_obj.strftime('%Y-%m-%d')} (Monthly Chain)")
                    subset = final_df[final_df['Expiration'] == date_obj].copy()
                    
                    # Graph
                    st.bar_chart(subset.set_index("Stock")["PCR"])
                    
                    # Table
                    st.dataframe(
                        subset.style.applymap(style_pcr, subset=['PCR'])
                        .format({"Call Vol": "{:,.0f}", "Put Vol": "{:,.0f}", "Total Vol": "{:,.0f}"}),
                        use_container_width=True, hide_index=True
                    )
        else:
            st.warning("No options volume found for the selected tickers.")
else:
    st.error("Watchlist data could not be loaded.")