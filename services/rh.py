"""Robinhood — THE single door for all RH data.

Delta, expiry, premium, bid/ask, chains, and (after login is implemented)
positions all come through here. One place to change RH behavior.

Login is DEFERRED: _ensure_login() reads creds from config.settings and logs
in lazily on first call. Until creds are set, every function returns None/[]
and never crashes the page.
"""

from __future__ import annotations

import streamlit as st

from config import settings
from services.cache import TTL, cached

_LOGGED_IN = False


def is_configured() -> bool:
    """True when RH credentials are present (login not yet wired to MFA)."""
    creds = settings.rh_credentials()
    return bool(creds.get("username") and creds.get("password"))


def _ensure_login() -> bool:
    """Lazy login. Returns True if a session is available.
    TODO: wire MFA/device-token flow before deploying to a public URL."""
    global _LOGGED_IN
    if _LOGGED_IN:
        return True
    if not is_configured():
        return False
    try:
        import robin_stocks.robinhood as r
        creds = settings.rh_credentials()
        r.login(creds["username"], creds["password"])
        _LOGGED_IN = True
        return True
    except Exception:
        return False


# ── Market data ──────────────────────────────────────────────────────────────
@cached(TTL["price"])
def get_price(ticker: str) -> float | None:
    if not _ensure_login():
        return None
    try:
        import robin_stocks.robinhood as r
        val = r.stocks.get_latest_price(ticker)
        return float(val[0]) if val and val[0] else None
    except Exception:
        return None


@cached(TTL["option"])
def get_option(ticker: str, expiry: str, strike: float, opt_type: str = "put") -> dict | None:
    """One option's live data: delta, premium (mark), bid, ask, IV.
    expiry = 'YYYY-MM-DD'. Returns {} keys or None if unavailable."""
    if not _ensure_login():
        return None
    try:
        import robin_stocks.robinhood as r
        data = r.options.find_options_by_expiration_and_strike(
            ticker, expiry, str(strike), optionType=opt_type
        )
        if not data:
            return None
        o = data[0]
        bid = float(o.get("bid_price") or 0)
        ask = float(o.get("ask_price") or 0)
        return {
            "delta":   float(o["delta"]) if o.get("delta") else None,
            "premium": round((bid + ask) / 2, 2) if (bid or ask) else None,
            "bid":     bid,
            "ask":     ask,
            "iv":      float(o["implied_volatility"]) if o.get("implied_volatility") else None,
            "expiry":  expiry,
            "strike":  float(strike),
            "type":    opt_type,
        }
    except Exception:
        return None


@cached(TTL["chain"])
def get_chain(ticker: str, expiry: str, opt_type: str = "put") -> list[dict]:
    """Full option chain for one expiry. [] if unavailable."""
    if not _ensure_login():
        return []
    try:
        import robin_stocks.robinhood as r
        data = r.options.find_options_by_expiration(
            ticker, expirationDate=expiry, optionType=opt_type
        )
        return data or []
    except Exception:
        return []


@cached(TTL["history"])
def get_daily_bars(ticker: str, span: str = "year") -> list[dict]:
    """Daily bars [{date, close, low}] from RH (the broker's own tape). Empty
    until login is configured — callers fall back to services.yahoo."""
    if not _ensure_login():
        return []
    try:
        import datetime as _dt

        import robin_stocks.robinhood as r
        bars = r.stocks.get_stock_historicals(
            ticker, interval="day", span=span, bounds="regular")
        out = []
        for b in bars or []:
            if not b or b.get("close_price") is None:
                continue
            try:
                d = _dt.datetime.fromisoformat(
                    str(b["begins_at"]).replace("Z", "+00:00")).date()
                close = float(b["close_price"])
                low = float(b.get("low_price") or close)
                out.append({"date": d, "close": close, "low": low})
            except (ValueError, TypeError, KeyError):
                continue
        return out
    except Exception:
        return []


# ── Account (post-login feature) ─────────────────────────────────────────────
def get_positions() -> list[dict]:
    """Open positions. Empty until login is implemented.
    TODO: implement after MFA login flow lands."""
    if not _ensure_login():
        return []
    try:
        import robin_stocks.robinhood as r
        return r.options.get_open_option_positions() or []
    except Exception:
        return []
