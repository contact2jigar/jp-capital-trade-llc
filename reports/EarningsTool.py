import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.title("🛡️ Batch Earnings Logic Tool")
st.write("Using the exact 'Institutional CSP Engine' logic to calculate statuses and dates.")

# Input area for pasting
raw_input = st.text_area("Paste Tickers from Sheet:", height=150, placeholder="NVDA\nMETA\nMSFT")

if st.button("🚀 Process Earnings"):
    if raw_input:
        tickers = [t.strip().upper() for t in raw_input.split('\n') if t.strip()]
        results = []
        prog = st.progress(0)
        
        for i, symbol in enumerate(tickers):
            try:
                tk = yf.Ticker(symbol)
                earn_dates = tk.get_earnings_dates(limit=1)
                
                earn_str = "🔴 N/A" 
                raw_date = "N/A"

                if earn_dates is not None and not earn_dates.empty:
                    # Logic directly from your provided code:
                    dt = earn_dates.index[0].to_pydatetime().replace(tzinfo=None)
                    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    # 1. Standardize date label
                    date_label = dt.strftime('%Y-%m-%d')
                    
                    # 2. Weekday calculation used in your program
                    # (dt.weekday() + 1) % 7 + 1 matches the Sheets-style weekday logic
                    sheets_weekday = (dt.weekday() + 1) % 7 + 1
                    pre_friday = dt - timedelta(days=(sheets_weekday - 6))
                    days_left = (pre_friday - today).days
                    
                    # 3. Status logic mapping
                    if pre_friday <= today: 
                        status = "🔴 (Expired/Due)"
                    elif days_left < 14: 
                        status = "⚪ (Impending)"
                    elif days_left <= 30: 
                        status = "💰 (Prime CSP)"
                    elif days_left <= 40: 
                        status = "🟢 (Safe)"
                    else: 
                        status = "🟡 (Far)"
                    
                    earn_str = f"{status} | {days_left}d left"
                    raw_date = date_label
                
                results.append({
                    "Ticker": symbol, 
                    "Earning Date": raw_date, 
                    "CSP Signal": earn_str
                })
            except:
                results.append({"Ticker": symbol, "Earning Date": "Error", "CSP Signal": "Error"})
            
            prog.progress((i + 1) / len(tickers))

        # Display results
        df = pd.DataFrame(results)
        st.subheader("Analysis Results")
        st.dataframe(df, use_container_width=True)

        # Output text for Google Sheets (Date only)
        st.subheader("Copy to Sheet (Column G)")
        copy_text = "\n".join(df["Earning Date"].tolist())
        st.text_area("Click to copy all dates:", value=copy_text, height=200)

    else:
        st.error("Please enter at least one ticker.")