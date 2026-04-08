from datetime import datetime, timedelta
from scipy.optimize import brentq
from scipy.stats import norm
import numpy as np
import pandas as pd  # Added for data cleaning in calculate_live_balances
import streamlit as st
import yfinance as yf


# =========================
# 📅 DATE HELPERS
# =========================
def get_fridays(n=8):
    d, out = datetime.now(), []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() == 4:
            out.append(d.strftime("%Y-%m-%d"))
    return out


def get_next_third_friday():
    today = datetime.today()
    for i in range(12):
        month = (today.month - 1 + i) % 12 + 1
        year = today.year + ((today.month - 1 + i) // 12)
        d = datetime(year, month, 1)
        while d.weekday() != 4:
            d += timedelta(days=1)
        third_friday = d + timedelta(days=14)
        if third_friday.date() > today.date():
            return third_friday.strftime("%Y-%m-%d")


# =========================
# 📊 OPTIONS MATH
# =========================
def bs_metrics(S, K, T, r, sigma, option_type="put"):
    if T <= 0:
        return 0.0, 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type.lower() == "put":
        return (
            K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1),
            -norm.cdf(-d1),
        )

    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2), norm.cdf(d1)


def find_iv_and_delta(mkt_px, S, K, T, r, opt_type):
    try:
        iv = brentq(
            lambda sig: bs_metrics(S, K, T, r, sig, opt_type)[0] - mkt_px,
            0.0001,
            4.0,
        )
        return iv, bs_metrics(S, K, T, r, iv, opt_type)[1]
    except:
        return 0.01, 0.0


def get_option_by_delta(ticker, expiry, side, target_delta):
    """Finds the strike closest to target_delta.

    Side should be 'put' or 'call'. Target delta is expected as a positive
    float (e.g., 0.15).
    """
    try:
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry)
        opts = chain.puts if side.lower() == "put" else chain.calls
        px = t.fast_info["lastPrice"]

        # Calculate Time to Expiration
        exp_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(hour=16)
        T = max((exp_dt - datetime.now()).total_seconds() / 31536000.0, 0.001)

        # 🎯 Filter for Out-of-the-Money options only
        if side.lower() == "put":
            opts = opts[opts["strike"] <= px]
        else:
            opts = opts[opts["strike"] >= px]

        if opts.empty:
            return 0.0, 0.0, 0.0

        target = -target_delta if side.lower() == "put" else target_delta
        best, best_diff = None, float("inf")

        for _, row in opts.iterrows():
            strike, bid, ask = (
                float(row["strike"]),
                float(row["bid"]),
                float(row["ask"]),
            )
            # Use mid price for IV/Delta calculation
            mid = (
                (bid + ask) / 2
                if (bid > 0 and ask > 0)
                else row.get("lastPrice", bid)
            )

            if mid <= 0:
                continue

            iv, delta = find_iv_and_delta(mid, px, strike, T, 0.043, side)
            diff = abs(delta - target)

            if diff < best_diff:
                best_diff = diff
                best = (strike, bid, delta)

        return best if best else (0.0, 0.0, 0.0)
    except:
        return 0.0, 0.0, 0.0


def calculate_projections(
    l_m,
    i_m,
    llc_curr,
    ira_curr,
    k401_curr,
    k401_target_val,
    l_init,
    i_init,
    k_init,
    current_exp,
    llc_strike_total=0,  # ⚡ Added to accept strike totals safely
    ira_strike_total=0,  # ⚡ Added to accept strike totals safely
):
    from datetime import datetime

    total_monthly = l_m + i_m

    exp_date = datetime.strptime(current_exp, "%Y-%m-%d")
    months_rem = max(0, 12 - exp_date.month)

    llc_growth = l_m * months_rem
    ira_growth = i_m * months_rem

    l_eoy = llc_curr + llc_growth
    i_eoy = ira_curr + ira_growth

    total_gain_rem = total_monthly * months_rem
    final_predictor = l_eoy + i_eoy + k401_target_val

    llc_aor = ((l_eoy - l_init) / l_init * 100) if l_init != 0 else 0
    ira_aor = ((i_eoy - i_init) / i_init * 100) if i_init != 0 else 0

    total_initial_basis = l_init + i_init + k_init
    total_aor = (
        ((final_predictor - total_initial_basis) / total_initial_basis * 100)
        if total_initial_basis > 0
        else 0
    )

    return {
        "total_monthly": total_monthly,
        "llc_growth": llc_growth,
        "ira_growth": ira_growth,
        "l_eoy": l_eoy,
        "i_eoy": i_eoy,
        "total_gain_rem": total_gain_rem,
        "final_predictor": final_predictor,
        "llc_aor": llc_aor,
        "ira_aor": ira_aor,
        "total_aor": total_aor,
    }


@st.cache_data(ttl=300)
def get_market_data():
    import yfinance as yf
    from datetime import datetime

    data = {}

    for ticker in ["SPY", "QQQ", "^VIX"]:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")

            current = hist["Close"].iloc[-1]

            if ticker != "^VIX":
                start_year = hist[hist.index >= f"{datetime.now().year}-01-01"]
                ytd = (
                    (
                        (current - start_year["Close"].iloc[0])
                        / start_year["Close"].iloc[0]
                    )
                    * 100
                    if not start_year.empty
                    else 0
                )
            else:
                ytd = 0

            data[ticker] = {"price": current, "ytd": ytd}

        except:
            data[ticker] = {"price": 0, "ytd": 0}

    return data


# =========================================================
# 💰 DYNAMIC BALANCE CALCULATIONS (SHARED)
# =========================================================
@st.cache_data(ttl=60)
def calculate_live_balances(sheet_data):
    """
    Calculates live account totals using logic synchronized with Live Portfolio Desk.
    CASH and HOLD use Cash Reserve; Options use (Qty * Price * 100).
    """
    if sheet_data.empty:
        return {}

    # 1. Clean and filter the raw data
    df = sheet_data[sheet_data["Status"] == "Open"].copy()
    df["Account"] = df["Account"].astype(str).str.strip()
    df["Opt Typ"] = df["Opt Typ"].astype(str).str.upper().str.strip()
    df["Stock"] = df["Stock"].astype(str).str.upper().str.strip()
    
    # Filter out 401k accounts
    df = df[~df["Account"].str.contains("401", na=False)]
    
    # Ensure numeric types
    df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0).abs()
    df["Strike"] = pd.to_numeric(df["Strike Price"], errors="coerce").fillna(0)
    df["Cash Reserve"] = pd.to_numeric(df["Cash Reserve"], errors="coerce").fillna(0.0)
    df["Current Price"] = pd.to_numeric(df["Current Price"], errors="coerce").fillna(0.0)

    live_balances = {}

    # 2. Process every row with the correct valuation rule
    for _, row in df.iterrows():
        acct = row["Account"]
        ticker = row["Stock"]
        opt_type = row["Opt Typ"]
        qty = row["Qty"]
        strike = row["Strike"]
        reserve = row["Cash Reserve"]
        
        row_value = 0.0

        # --- Rule A: CASH or HOLD (Direct Value) ---
        if ticker == "CASH" or opt_type == "HOLD":
            row_value = reserve
            
        # --- Rule B: Options/Stocks (Market Calculation) ---
        else:
            try:
                # Attempt live price fetch
                tk = yf.Ticker(ticker)
                # Using fast_info for speed, mirroring your desk app's px logic
                px = tk.fast_info["lastPrice"]

                if opt_type == "CALL":
                    effective_price = min(px, strike)
                elif opt_type == "PUT":
                    effective_price = px if px < strike else strike
                else:
                    # Default for regular stock assignments or other types
                    effective_price = px
                
                row_value = (qty * effective_price * 100)
            except:
                # Fallback to spreadsheet price if Yahoo fails
                fallback_px = row["Current Price"]
                row_value = (qty * fallback_px * 100)

        # 3. Aggregate by Account
        live_balances[acct] = live_balances.get(acct, 0.0) + row_value

    return live_balances

def get_live_positions_df(df):
    results = []
    # Ensure standard cleanup
    df = df.copy()
    df["Stock"] = df["Stock"].astype(str).str.upper().str.strip()
    df["Opt Typ"] = df["Opt Typ"].astype(str).str.upper().str.strip()
    
    for _, row in df.iterrows():
        ticker = row["Stock"]
        o_type = row["Opt Typ"]
        reserve = pd.to_numeric(row["Cash Reserve"], errors='coerce') or 0.0
        qty = abs(pd.to_numeric(row["Qty"], errors='coerce') or 0)
        strike = pd.to_numeric(row["Strike Price"], errors='coerce') or 0.0

        if ticker == "CASH" or o_type == "HOLD":
            results.append({
                "Ticker": ticker, "Account": row["Account"], "Type": "CASH" if ticker=="CASH" else "HOLD",
                "Last Close": 1.0, "Strike": 0.0, "Chg": 0.0, "Chg (%)": 0.0,
                "Qty": qty, "Market Value": reserve, "Close Date": row.get("Close Date", "N/A")
            })
        else:
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="2d")
                px = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                
                if o_type == "CALL": mkt_val = (qty * min(px, strike) * 100)
                elif o_type == "PUT": mkt_val = (qty * (px if px < strike else strike) * 100)
                else: mkt_val = (qty * px * 100)

                results.append({
                    "Ticker": ticker, "Account": row["Account"], "Type": o_type,
                    "Last Close": px, "Strike": strike, "Chg": px - prev, 
                    "Chg (%)": ((px - prev) / prev) * 100, "Qty": qty, 
                    "Market Value": mkt_val, "Close Date": row.get("Close Date", "N/A")
                })
            except:
                continue
    return pd.DataFrame(results)