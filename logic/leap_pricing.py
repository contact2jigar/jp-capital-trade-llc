"""Analytical LEAP-call pricing (Black-Scholes) for the Δ0.70 flip doctrine.

The app's option pricing is short-dated puts only, so the LEAP Scanner needs a
call-side target: given a spot, an IV, and a long DTE, find the deep-ITM strike
whose call delta ≈ the doctrine target (~0.70) and estimate its premium/cost.

These are ESTIMATES (ATM-IV proxy, no skew) — a target to size against, not a
live quote. The real 0.70 flip is executed manually off the broker chain.
"""

from __future__ import annotations

import math
from datetime import date, timedelta


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1(spot: float, strike: float, t: float, iv: float, r: float) -> float:
    return (math.log(spot / strike) + (r + iv * iv / 2.0) * t) / (iv * math.sqrt(t))


def bs_call_delta(spot, strike, dte, iv, r: float = 0.04):
    """Black-Scholes call delta (0..1). `iv` and `dte` are annualized-decimal / days."""
    if not (spot and strike and dte and iv) or spot <= 0 or strike <= 0 or iv <= 0:
        return None
    t = dte / 365.0
    return _norm_cdf(_d1(spot, strike, t, iv, r))


def bs_call_price(spot, strike, dte, iv, r: float = 0.04):
    """Black-Scholes call premium (per share)."""
    if not (spot and strike and dte and iv) or spot <= 0 or strike <= 0 or iv <= 0:
        return None
    t = dte / 365.0
    d1 = _d1(spot, strike, t, iv, r)
    d2 = d1 - iv * math.sqrt(t)
    return spot * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)


def _round_strike(k: float) -> float:
    """Snap to a plausible listed increment (looser as price rises)."""
    if k >= 200:
        return round(k / 5.0) * 5.0
    if k >= 50:
        return round(k)
    return round(k * 2.0) / 2.0        # nearest 0.50 under $50


def leap_expiry(today: date | None = None, months: int = 24) -> date:
    """Third Friday of the month ~`months` out — a stand-in LEAP expiry (~2yr)."""
    today = today or date.today()
    y = today.year + (today.month - 1 + months) // 12
    m = (today.month - 1 + months) % 12 + 1
    first = date(y, m, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def pick_leap_call(spot, iv, dte, target_delta: float = 0.70, r: float = 0.04) -> dict | None:
    """The ITM call whose delta ≈ `target_delta` at `dte` days. `iv` accepts a percent
    (e.g. 45) or a decimal (0.45). Returns {strike, delta, premium, cost}. Delta is
    monotically decreasing in strike, so a binary search converges fast."""
    if not (spot and iv and dte) or spot <= 0 or iv <= 0 or dte <= 0:
        return None
    ivd = iv / 100.0 if iv > 3.0 else float(iv)            # percent → decimal
    lo, hi = spot * 0.2, spot * 1.5                        # deep ITM … OTM
    for _ in range(60):
        mid = (lo + hi) / 2.0
        d = bs_call_delta(spot, mid, dte, ivd, r)
        if d is None:
            return None
        if d > target_delta:                              # too much delta → raise strike
            lo = mid
        else:
            hi = mid
    strike = _round_strike((lo + hi) / 2.0)
    d = bs_call_delta(spot, strike, dte, ivd, r)
    prem = bs_call_price(spot, strike, dte, ivd, r)
    return {"strike": strike, "delta": d, "premium": prem,
            "cost": prem * 100.0 if prem else None}
