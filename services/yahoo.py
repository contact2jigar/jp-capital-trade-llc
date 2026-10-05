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


def _market_open_now() -> bool:
    """True during US cash-session hours (ET weekday 09:30–16:00)."""
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return False
    if now.weekday() >= 5:                                  # Sat/Sun
        return False
    t = now.hour * 60 + now.minute
    return 570 <= t < 960                                   # 9:30 → 16:00 ET


@cached(TTL["price"])
def index_quotes() -> dict:
    """SPY & QQQ for the VIX strip. During cash hours → the ETF's own last/prev
    (regular-session % change). When closed → the index future (ES=F / NQ=F) so a
    pre-open read shows where the market is pointing. Each value:
    {px, chg, fut} — chg is a fraction, fut True when it's the futures proxy.
    {} on total failure so the caller can hide the chips."""
    live = _market_open_now()
    pairs = {"SPY": "SPY", "QQQ": "QQQ"} if live else {"SPY": "ES=F", "QQQ": "NQ=F"}
    out: dict = {}
    try:
        import yfinance as yf
        for label, sym in pairs.items():
            try:
                fi = yf.Ticker(sym).fast_info
                last = fi.get("last_price") if isinstance(fi, dict) else fi.last_price
                prev = fi.get("previous_close") if isinstance(fi, dict) else fi.previous_close
                if last and prev:
                    out[label] = {"px": float(last),
                                  "chg": float(last) / float(prev) - 1,
                                  "fut": not live}
            except Exception:
                continue
    except Exception:
        return {}
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
    """NEXT (today-or-future) earnings date, or None.

    yfinance's `calendar` often reports the LAST reported earnings, not the next one
    (e.g. a date 30 days in the past). A stale past date read as the next earnings is
    dangerous — the board would call a name 'clear' when it could report inside the
    holding window — so a past date is rejected and we fall back to the dated list
    (which carries upcoming dates). None means genuinely unknown, not 'no earnings'."""
    today = dt.date.today()
    cand = None
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        val = None
        if isinstance(cal, dict):
            val = cal.get("Earnings Date")
            if isinstance(val, (list, tuple)) and val:
                val = val[0]
        elif hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
            val = cal.loc["Earnings Date"][0]
        if val:
            cand = pd.to_datetime(val).date()
    except Exception:
        cand = None
    if cand and cand >= today:
        return cand
    # calendar missing or stale (past) → first future date from the dated list
    try:
        for d in get_earnings_dates(ticker):            # sorted ascending
            if d >= today:
                return d
    except Exception:
        pass
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
