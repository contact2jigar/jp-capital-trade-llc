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
_SESSION_SEEDED = False


def _creds_configured() -> bool:
    creds = settings.rh_credentials()
    return bool(creds.get("username") and creds.get("password"))


def is_configured() -> bool:
    """True when we can reach RH: a token in the RHSecret tab, or username/password."""
    if _creds_configured():
        return True
    try:
        from services import gsheet
        return bool(gsheet.rh_token().get("RH_ACCESS"))
    except Exception:
        return False


def _seed_from_sheet() -> bool:
    """Seed the robin_stocks session straight from the RHSecret tab's access token
    (no MFA — same approach as the iPhone app). The token lives in the sheet, so a
    refresh there is picked up on the next pull."""
    global _SESSION_SEEDED
    try:
        from services import gsheet
        access = str(gsheet.rh_token().get("RH_ACCESS") or "").strip()
    except Exception:
        access = ""
    if not access:
        return False
    try:
        import robin_stocks.robinhood  # noqa: F401  (ensure package/session loaded)
        from robin_stocks.robinhood import helper
        helper.update_session("Authorization", f"Bearer {access}")
        helper.set_login_state(True)
        _SESSION_SEEDED = True
        return True
    except Exception:
        return False


def _ensure_login() -> bool:
    """Lazy session. Prefers the RHSecret-tab token (no MFA); falls back to a
    username/password login if creds are set.

    MFA (fallback path) is handled from the `robinhood.mfa` secret:
      • a base32 authenticator seed  → a fresh TOTP code each login (headless-safe)
      • a short all-digit string     → a one-time code (manual run)
    """
    global _LOGGED_IN
    if _LOGGED_IN:
        return True
    if _seed_from_sheet():                               # token from RHSecret tab
        _LOGGED_IN = True
        return True
    if not _creds_configured():
        return False
    try:
        import robin_stocks.robinhood as r
        creds = settings.rh_credentials()
        kwargs = {"store_session": True}
        mfa = str(creds.get("mfa") or "").strip()
        if mfa:
            if mfa.isdigit() and len(mfa) <= 8:
                kwargs["mfa_code"] = mfa                 # one-time code (manual)
            else:
                import pyotp                             # authenticator seed → live code
                kwargs["mfa_code"] = pyotp.TOTP(mfa.replace(" ", "")).now()
        r.login(creds["username"], creds["password"], **kwargs)
        _LOGGED_IN = True
        return True
    except Exception:
        _LOGGED_IN = False
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


@cached(TTL["price"])
def extended_quotes(symbols: tuple[str, ...]) -> dict:
    """{SYM: {price, prev, move, ext}} using the extended-hours price vs previous
    close — the pre-market / after-hours move each ticker is showing. `symbols` is
    a tuple so the result caches. Used by the Day Predictor."""
    syms = tuple(sorted({s.upper().strip() for s in symbols if s and str(s).strip()}))
    if not syms or not _ensure_login():
        return {}
    try:
        import robin_stocks.robinhood as r
        data = r.stocks.get_quotes(list(syms))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for q in (data or []):
        if not q:
            continue
        sym = str(q.get("symbol") or "").upper()
        try:
            prev_close = float(q.get("previous_close") or q.get("adjusted_previous_close") or 0)
            last = float(q.get("last_trade_price") or 0)             # yesterday's close (pre-mkt) / live (open)
            ext_raw = q.get("last_extended_hours_trade_price")
            ext = float(ext_raw) if ext_raw else None
        except (TypeError, ValueError):
            continue
        # Early trend = current price vs YESTERDAY's close, not the 2-sessions-ago previous_close.
        # Pre/after-market: current = ext, base = last regular close. Market hours: current = last, base = prev close.
        if ext:
            price, base = ext, last
        else:
            price, base = last, prev_close
        if price > 0 and base > 0:
            out[sym] = {"price": price, "prev": base,
                        "move": (price - base) / base, "ext": bool(ext)}
    return out


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
