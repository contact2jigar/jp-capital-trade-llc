"""Yahoo Finance — THE single door for all Yahoo data.

Every page pulls price/history/fundamentals/earnings through these functions.
Change the source once here, the whole app follows. Caching lives inline.

Functions return plain types (float / DataFrame / dict / date) — no Streamlit
in the return values, so logic/ and tests/ can call them too.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from services.cache import TTL, cached


@cached(TTL["price"])
def get_price(ticker: str) -> float | None:
    """Latest regular-session price. None if unavailable."""
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        px = fi.get("last_price") if isinstance(fi, dict) else fi.last_price
        return float(px) if px else None
    except Exception:
        return None


@cached(TTL["history"])
def get_history(ticker: str, period: str = "6mo", interval: str = "1d",
                auto_adjust: bool = True) -> pd.DataFrame:
    """OHLCV history. Columns: Open High Low Close Volume, DatetimeIndex.
    Empty DataFrame on failure. auto_adjust=False keeps raw (unadjusted) OHLC —
    needed where volume/candle analysis must match the broker's tape."""
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=period, interval=interval,
                                       auto_adjust=auto_adjust)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@cached(TTL["price"])
def market_context() -> dict:
    """Live VIX + SPY 100-day regime for the Monitor Board header.
    {vix, vix_chg, spy, sma100, trend}. Empty values on failure (caller falls
    back to the sheet). Trend = SPY vs its ~100-calendar-day average (2-state)."""
    out = {"vix": None, "vix_chg": None, "spy": None, "sma100": None, "trend": None}
    try:
        vh = get_history("^VIX", period="1mo")
        if not vh.empty:
            closes = vh["Close"].dropna()
            out["vix"] = float(closes.iloc[-1])
            if len(closes) >= 2 and closes.iloc[-2]:
                out["vix_chg"] = float(closes.iloc[-1] / closes.iloc[-2] - 1)
        sh = get_history("SPY", period="8mo")
        if not sh.empty:
            c = sh["Close"].dropna()
            out["spy"] = float(c.iloc[-1])
            cutoff = c.index.max() - pd.Timedelta(days=100)
            win = c[c.index >= cutoff]
            out["sma100"] = float(win.mean()) if len(win) else float(c.tail(70).mean())
            if out["sma100"]:
                out["trend"] = "Uptrend" if out["spy"] > out["sma100"] else "Downtrend"
    except Exception:
        pass
    return out


@cached(TTL["fundamentals"])
def get_fundamentals(ticker: str) -> dict:
    """Company fundamentals (PE, margins, cash, etc.). {} on failure."""
    try:
        import yfinance as yf
        return dict(yf.Ticker(ticker).info or {})
    except Exception:
        return {}


@cached(TTL["earnings"])
def get_earnings_dates(ticker: str, limit: int = 24) -> list:
    """Past + upcoming earnings dates (list of date), newest-sorted ascending.
    [] on failure."""
    try:
        import yfinance as yf
        edf = yf.Ticker(ticker).get_earnings_dates(limit=limit)
        if edf is None or edf.empty:
            return []
        idx = edf.index
        try:
            idx = idx.tz_localize(None)
        except (TypeError, AttributeError):
            try:
                idx = idx.tz_convert(None)
            except (TypeError, AttributeError):
                pass
        return sorted(d.date() if hasattr(d, "date") else d for d in idx)
    except Exception:
        return []


@cached(TTL["fundamentals"])
def get_atm_iv(ticker: str, price: float) -> float | None:
    """At-the-money implied vol (annualized %) from the nearest expiry's calls.
    A free proxy for a name's current IV. None if no chain / on failure."""
    import math
    if price is None or not (isinstance(price, (int, float)) and math.isfinite(price)) or price <= 0:
        return None      # a bad price breaks ATM selection → skip rather than return garbage
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps:
            return None
        calls = tk.option_chain(exps[0]).calls
        if calls is None or calls.empty:
            return None
        atm = calls.assign(_d=(calls["strike"] - price).abs()).sort_values("_d")
        iv = float(atm.iloc[0]["impliedVolatility"])
        return iv * 100 if iv else None
    except Exception:
        return None


@cached(TTL["earnings"])
def get_earnings_date(ticker: str) -> dt.date | None:
    """Next earnings date, or None."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        if isinstance(cal, dict):
            val = cal.get("Earnings Date")
            if isinstance(val, (list, tuple)) and val:
                val = val[0]
            return pd.to_datetime(val).date() if val else None
        if hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
            return pd.to_datetime(cal.loc["Earnings Date"][0]).date()
    except Exception:
        return None
    return None


@cached(TTL["fundamentals"])
def fear_greed() -> dict | None:
    """CNN Fear & Greed Index — current score (0-100) + rating. Unofficial CNN JSON
    endpoint (needs a browser UA); returns None on any failure so callers can hide it."""
    try:
        import requests
        h = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
        r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                         headers=h, timeout=6)
        d = r.json()["fear_and_greed"]
        return {"score": round(float(d["score"])), "rating": str(d.get("rating", "")).title()}
    except Exception:
        return None
