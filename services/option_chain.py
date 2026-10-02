"""Option-chain loader — the single door for full chains (Price Wall Map).

Robinhood first (the broker's real data), yfinance fallback so the tool degrades
gracefully. Returns one DataFrame:
  ticker · expiry · dte · type · strike · oi · volume · iv · last · spot · source

RH is dormant until login is configured (services.rh) — yfinance serves until then.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date

import pandas as pd

from services import rh as rh_svc
from services.cache import TTL, cached

# Only price strikes within ±this fraction of spot (RH is one round-trip per
# contract; the walls live near the money so far-OTM strikes add cost, not signal).
_RH_STRIKE_BAND = 0.20


def _safe_int(v, default: int = 0) -> int:
    try:
        if v is None or v != v:      # NaN != NaN
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


@cached(TTL["chain"])
def load_chain(ticker: str, max_dte: int = 90) -> pd.DataFrame:
    """Option chain for `ticker`, expiries within `max_dte` days. RH first,
    yfinance fallback. A 'source' column marks which one served. Empty only if
    both fail."""
    df = _load_chain_rh(ticker, max_dte)
    if df is not None and not df.empty:
        df["source"] = "RH"
        return df
    df = _load_chain_yfinance(ticker, max_dte)
    if not df.empty:
        df["source"] = "yfinance"
    return df


# ─── Robinhood (primary) ─────────────────────────────────────────────────────
def _load_chain_rh(ticker: str, max_dte: int) -> pd.DataFrame | None:
    if not rh_svc._ensure_login():     # dormant until RH login is configured
        return None
    try:
        import robin_stocks.robinhood as rh

        price_list = rh.get_latest_price(ticker)
        spot = _safe_float(price_list[0]) if price_list else 0.0
        if not spot:
            return None
        lo, hi = spot * (1 - _RH_STRIKE_BAND), spot * (1 + _RH_STRIKE_BAND)

        chain_info = rh.get_chains(ticker)
        exp_dates = (chain_info or {}).get("expiration_dates") or []
        today = _date.today()

        targets = []
        for exp in exp_dates:
            try:
                exp_d = _date.fromisoformat(exp)
            except Exception:
                continue
            dte = (exp_d - today).days
            if dte < 0 or dte > max_dte:
                continue
            try:
                instruments = rh.find_tradable_options(ticker, expirationDate=exp) or []
            except Exception:
                continue
            for inst in instruments:
                strike = _safe_float(inst.get("strike_price"))
                if strike > 0 and lo <= strike <= hi and inst.get("id"):
                    targets.append((exp, dte, inst))

        def _fetch(t):
            exp, dte, inst = t
            try:
                md_list = rh.get_option_market_data_by_id(inst["id"]) or []
            except Exception:
                md_list = []
            return exp, dte, inst, (md_list[0] if md_list else {})

        rows: list[dict] = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            for exp, dte, inst, md in ex.map(_fetch, targets):
                rows.append({
                    "ticker": ticker.upper(), "expiry": exp, "dte": dte,
                    "type": "call" if str(inst.get("type", "")).lower() == "call" else "put",
                    "strike": _safe_float(inst.get("strike_price")),
                    "oi": _safe_int(md.get("open_interest")),
                    "volume": _safe_int(md.get("volume")),
                    "iv": _safe_float(md.get("implied_volatility")),
                    "last": _safe_float(md.get("last_trade_price")),
                    "spot": spot,
                })
        return pd.DataFrame(rows) if rows else None
    except Exception:
        return None


# ─── yfinance (fallback) ─────────────────────────────────────────────────────
def _load_chain_yfinance(ticker: str, max_dte: int) -> pd.DataFrame:
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        spot = _spot_price(tk)
        if not spot:
            return pd.DataFrame()
        today = _date.today()
        rows: list[dict] = []
        for exp in (tk.options or []):
            try:
                exp_d = _date.fromisoformat(exp)
            except Exception:
                continue
            dte = (exp_d - today).days
            if dte < 0 or dte > max_dte:
                continue
            try:
                chain = tk.option_chain(exp)
            except Exception:
                continue
            for kind, cdf in (("call", chain.calls), ("put", chain.puts)):
                if cdf is None or cdf.empty:
                    continue
                for _, r in cdf.iterrows():
                    strike = float(r.get("strike", 0) or 0)
                    if strike <= 0:
                        continue
                    rows.append({
                        "ticker": ticker.upper(), "expiry": exp, "dte": dte,
                        "type": kind, "strike": strike,
                        "oi": _safe_int(r.get("openInterest")),
                        "volume": _safe_int(r.get("volume")),
                        "iv": float(r.get("impliedVolatility", 0) or 0),
                        "last": float(r.get("lastPrice", 0) or 0),
                        "spot": spot,
                    })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@cached(TTL["chain"])
def load_puts_at(ticker: str, target_iso: str, tol_days: int | None = None) -> dict:
    """Lean single-expiry PUT chain for the CSP Scanner (yfinance).

    Snaps to the available expiry nearest `target_iso` (YYYY-MM-DD), since not
    every name has a weekly on the exact target Friday. Returns
    {puts: [{strike, premium, last, bid, ask, iv}], expiry, spot, dte} with a mid
    (bid+ask)/2 premium and IV as a DECIMAL. Empty puts if unavailable.

    `tol_days` guards against monthly-only names: when the nearest expiry sits
    more than tol_days from the target (no weekly in the window), the chain is
    NOT priced — it returns {no_weekly: True} with the offending expiry, so the
    scanner can exclude the name instead of pricing a different Friday as if it
    were the target. None = snap at any distance (the original behaviour)."""
    empty = {"puts": [], "expiry": None, "spot": None, "dte": None}
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        exps = list(tk.options or [])
        if not exps:
            return empty
        tgt = _date.fromisoformat(target_iso)

        def _dist(e: str) -> int:
            try:
                return abs((_date.fromisoformat(e) - tgt).days)
            except Exception:
                return 10 ** 6

        exp = min(exps, key=_dist)
        if tol_days is not None and _dist(exp) > tol_days:
            dte = (_date.fromisoformat(exp) - _date.today()).days
            return {**empty, "expiry": exp, "dte": dte, "no_weekly": True}
        spot = _spot_price(tk)
        try:
            chain = tk.option_chain(exp)
        except Exception:
            return {**empty, "expiry": exp, "spot": spot}

        puts = []
        cdf = chain.puts
        if cdf is not None and not cdf.empty:
            for _, r in cdf.iterrows():
                strike = _safe_float(r.get("strike"))
                if strike <= 0:
                    continue
                bid = _safe_float(r.get("bid"))
                ask = _safe_float(r.get("ask"))
                last = _safe_float(r.get("lastPrice"))
                mid = round((bid + ask) / 2, 2) if (bid or ask) else last
                puts.append({
                    "strike": strike, "premium": mid, "last": last,
                    "bid": bid, "ask": ask,
                    "iv": _safe_float(r.get("impliedVolatility")),
                })
        dte = (_date.fromisoformat(exp) - _date.today()).days
        return {"puts": puts, "expiry": exp, "spot": spot, "dte": dte}
    except Exception:
        return empty


def _spot_price(tk) -> float | None:
    try:
        info = tk.fast_info if hasattr(tk, "fast_info") else {}
        if hasattr(info, "get"):
            v = info.get("lastPrice")
            if v:
                return float(v)
    except Exception:
        pass
    try:
        h = tk.history(period="1d", interval="1d")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return None
