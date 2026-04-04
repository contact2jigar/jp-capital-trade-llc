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
@st.cache_data(ttl=60)  # Caches for 60 seconds across the whole app
def calculate_live_balances(sheet_data):
    """Calculates live account totals (Cash + Equity) by fetching current

    prices.
    """
    if sheet_data.empty:
        return {}

    open_trades = sheet_data[sheet_data["Status"] == "Open"].copy()

    # Apply your standard data cleanup from the live sheet
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

    open_trades["Qty"] = (
        pd.to_numeric(open_trades["Qty"], errors="coerce").fillna(0).abs()
    )
    open_trades["Stock"] = open_trades["Stock"].astype(str).str.upper()
    open_trades["Opt Typ"] = open_trades["Opt Typ"].astype(str).str.upper()
    open_trades["Cash Reserve"] = (
        pd.to_numeric(open_trades["Cash Reserve"], errors="coerce")
        .fillna(0.0)
        .abs()
    )

    # 1. Identify Cash
    cash_rows = open_trades[open_trades["Stock"] == "CASH"]
    account_cash = (
        cash_rows.groupby("Account")["Qty"].sum().to_dict()
        if not cash_rows.empty
        else {}
    )

    # 2. Identify and Group Assets
    stock_rows = open_trades[open_trades["Stock"] != "CASH"]
    grouped_assets = (
        stock_rows.groupby(["Account", "Stock", "Opt Typ", "Strike"])[
            ["Qty", "Cash Reserve"]
        ]
        .sum()
        .reset_index()
    )

    account_equity = {}

    # Calculate equity for each grouped holding
    for _, row in grouped_assets.iterrows():
        acct = row["Account"]
        ticker = row["Stock"]
        opt_type = row["Opt Typ"]
        strike = row["Strike"]
        total_qty = row["Qty"]
        static_cash_reserve = row["Cash Reserve"]

        if opt_type == "HOLD":
            current_value = static_cash_reserve
        else:
            try:
                # Fast info fetch
                stock_obj = yf.Ticker(ticker)
                live_price = stock_obj.fast_info["lastPrice"]

                # Capping values based on option types (your exact logic)
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
                current_value = 0.0

        account_equity[acct] = account_equity.get(acct, 0.0) + current_value

    # 3. Combine Cash and Equity
    live_balances = {}
    all_accounts = set(account_cash.keys()).union(set(account_equity.keys()))

    for acct in all_accounts:
        total_worth = account_cash.get(acct, 0.0) + account_equity.get(
            acct, 0.0
        )
        live_balances[acct] = total_worth

    return live_balances