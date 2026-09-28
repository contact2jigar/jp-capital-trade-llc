"""CSP pricing — expiry pick, Black-Scholes put delta, AOR, strike selection (pure).

yfinance/RH don't hand back Greeks, but they do give per-contract IV, so we
compute the put delta from Black-Scholes. AOR (annualized option return) is the
governing discipline: pick the SAFEST (lowest) OTM put strike whose AOR still
clears the floor, and report the delta that lands you at — not the other way.

No fetching here; feed it a list of put dicts {strike, premium, iv}.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

_R = 0.04   # risk-free rate (annual); delta is not very sensitive to it


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put_delta(spot, strike, dte, iv, r: float = _R):
    """Black-Scholes put delta (negative). iv as a DECIMAL (0.45 = 45%).
    None if any input is unusable."""
    try:
        spot = float(spot); strike = float(strike); dte = float(dte); iv = float(iv)
    except (TypeError, ValueError):
        return None
    if spot <= 0 or strike <= 0 or dte <= 0 or iv <= 0:
        return None
    t = dte / 365.0
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    return _norm_cdf(d1) - 1.0


def aor(premium, strike, dte):
    """Annualized option return % = (premium / strike) × (365 / dte) × 100.
    Cash-secured: collateral = strike × 100, premium is per share — the 100s cancel."""
    try:
        premium = float(premium); strike = float(strike); dte = float(dte)
    except (TypeError, ValueError):
        return None
    if premium <= 0 or strike <= 0 or dte <= 0:
        return None
    return premium / strike * (365.0 / dte) * 100.0


def target_friday(today: date | None = None, min_dte: int = 21) -> date:
    """First Friday that is at least `min_dte` days out (the standard CSP expiry)."""
    today = today or date.today()
    d = today + timedelta(days=min_dte)
    while d.weekday() != 4:            # Mon=0 … Fri=4
        d += timedelta(days=1)
    return d


def expiry_choices(today: date | None = None, min_dte: int = 21) -> list[date]:
    """The target Friday plus the Fridays a week before / after (for recompute)."""
    base = target_friday(today, min_dte)
    return [base - timedelta(days=7), base, base + timedelta(days=7)]


def pick_by_delta(puts, spot, dte, target_delta: float = 0.30, r: float = _R) -> dict | None:
    """The OTM put with the MOST premium whose |delta| is still **≤ target_delta**
    — a cap, not a nearest-match: never sell above the delta you set (e.g. ≤ 0.30).
    Returns {strike, premium, delta, aor, iv} or None. If no strike sits under the
    cap, falls back to the furthest-OTM (smallest-delta) put available."""
    try:
        spot = float(spot)
    except (TypeError, ValueError):
        return None
    if spot <= 0:
        return None
    under, under_d = None, -1.0        # best (highest |Δ|) at or under the cap
    fallback, fallback_d = None, 1e9   # smallest |Δ| overall, if nothing fits the cap
    for p in puts:
        try:
            k = float(p.get("strike", 0)); prem = float(p.get("premium", 0) or 0)
        except (TypeError, ValueError):
            continue
        if k <= 0 or k >= spot or prem <= 0:
            continue
        d = bs_put_delta(spot, k, dte, p.get("iv"), r)
        if d is None:
            continue
        ad = abs(d)
        row = {"strike": k, "premium": prem, "delta": d, "aor": aor(prem, k, dte), "iv": p.get("iv")}
        if ad <= target_delta and ad > under_d:
            under_d, under = ad, row
        if ad < fallback_d:
            fallback_d, fallback = ad, row
    return under or fallback


def pick_csp_strike(puts, spot, dte, aor_floor, r: float = _R) -> dict | None:
    """From OTM puts, the SAFEST (lowest) strike whose AOR ≥ aor_floor.
    If none clear the floor, fall back to the richest (highest-AOR) OTM strike so
    the row still shows what's available. Returns {strike, premium, aor, delta,
    iv, meets_floor} or None if no usable OTM put.

    puts: iterable of {strike, premium, iv} — premium/strike per share, iv decimal."""
    try:
        spot = float(spot)
    except (TypeError, ValueError):
        return None
    if spot <= 0:
        return None

    cands = []
    for p in puts:
        try:
            k = float(p.get("strike", 0)); prem = float(p.get("premium", 0) or 0)
        except (TypeError, ValueError):
            continue
        if k <= 0 or k >= spot or prem <= 0:       # OTM puts with a real premium only
            continue
        a = aor(prem, k, dte)
        if a is None:
            continue
        cands.append({
            "strike": k, "premium": prem, "aor": a,
            "delta": bs_put_delta(spot, k, dte, p.get("iv"), r),
            "iv": p.get("iv"),
        })
    if not cands:
        return None

    meeting = [c for c in cands if c["aor"] >= aor_floor]
    if meeting:
        best = min(meeting, key=lambda c: c["strike"])    # safest strike still clearing the floor
        best["meets_floor"] = True
        return best
    best = max(cands, key=lambda c: c["aor"])              # nothing clears it → richest available
    best["meets_floor"] = False
    return best
