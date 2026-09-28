"""Portfolio Action Queue — answers Q2 (stuck), Q4 (missing GTC), Q5 (calls to write).

Source of truth = the TradeLog (open positions), matched back against the uploaded
Fidelity CSV. For each open short PUT we check the GTC (the sheet's set value vs the
DTE-bucket target). Fidelity shares (assigned stock, not in the TradeLog) are checked
for below-basis (stuck) and for being uncovered by a call (CC to write). Pure.
"""

from __future__ import annotations

import pandas as pd

from logic import gtc_refresh
from logic import reconcile as rec


def _num(v):
    return rec._num(v)


def _gtc_status(opt_typ: str, init_prem, dte, set_gtc):
    """(label, state) for the GTC column. state ∈ good/bad/na.
    Only short PUTs carry a CSP GTC ladder; others show '—'."""
    if opt_typ != "PUT":
        return "—", "na"
    target = gtc_refresh.gtc_target(init_prem, gtc_refresh._num(dte))
    s = str(set_gtc or "").replace("$", "").replace(",", "").strip()
    setv = None
    try:
        setv = float(s) if s not in ("", "—", "None", "nan") else None
    except ValueError:
        setv = None
    if setv is None:
        return "MISSING", "bad"
    if target is None:
        return f"${setv:.2f}", "good"
    if abs(setv - target) <= 0.02:
        return f"${setv:.2f}", "good"
    return f"${setv:.2f} ≠ ${target:.2f}", "bad"


def build(tradelog_df: pd.DataFrame, fidelity: list | None) -> dict:
    """Returns {rows, cards, has_fidelity}. rows drive the Action Queue table;
    cards drive answers 2/4/5."""
    fidelity = fidelity or []
    has_fid = bool(fidelity)

    # Fidelity indices: options by reconcile key; shares by (acct,ticker); SHORT calls
    # (the ones that actually cover shares — a long LEAP does not) by (acct,ticker).
    fid_opt = {rec._key(p): p for p in fidelity if p["pos_type"] in ("PUT", "CALL")}
    fid_shares = {(p["acct"], p["underlying"]): p for p in fidelity if p["pos_type"] == "SHARE"}
    short_calls: dict = {}
    for p in fidelity:
        if p["pos_type"] == "CALL" and p.get("short", True):
            k = (p["acct"], p["underlying"])
            short_calls[k] = short_calls.get(k, 0) + p["qty"]

    rows = []
    gtc_missing = 0
    stuck_value, stuck_count = 0.0, 0
    cc_shares, cc_contracts = 0, 0

    # ── TradeLog open options (source of truth), matched back to Fidelity ──
    tr = rec.tracked_from_tradelog(tradelog_df)
    raw = tradelog_df.copy()
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw[raw.get("Status", "").astype(str).str.upper().str.startswith("OPEN")]

    def _rawlookup(acct, tk, typ, strike):
        for _, r in raw.iterrows():
            if (str(r.get("Account", "")).strip().upper() == acct
                    and str(r.get("Stock", "")).strip().upper() == tk
                    and str(r.get("Opt Typ", "")).strip().upper() == typ):
                if abs(_num(r.get("Strike Price")) - strike) <= 0.01:
                    return r
        return None

    for p in tr:
        typ = p["pos_type"] if p["pos_type"] != "LEAP" else "CALL"
        r = _rawlookup(p["acct"], p["underlying"], p["pos_type"], p["strike"])
        init_prem = _num(r.get("Init Prem")) if r is not None else None
        dte = r.get("DTE") if r is not None else None
        set_gtc = r.get("GTC") if r is not None else None
        cur = _num(r.get("Current Price")) if r is not None else None
        matched = rec._key(p) in fid_opt

        gtc_label, gtc_state = _gtc_status(typ, init_prem, dte, set_gtc)
        flags, action, act_state = [], "CLEAR", "good"

        if typ == "PUT":
            if gtc_state == "bad":
                gtc_missing += 1
                flags.append("gtc")
            if has_fid and not matched:
                action, act_state = "NOT IN FIDELITY", "bad"
        else:   # CALL / LEAP — both flags come from the TradeLog CALL vs Fidelity.
            share = fid_shares.get((p["acct"], p["underlying"]))
            avg = share["avg_cost"] if share else None
            below_basis = (avg is not None and avg > 0 and p["strike"] is not None
                           and p["strike"] < avg)                  # STUCK: below-basis CC
            not_placed = has_fid and not matched                   # CC TO WRITE: in TradeLog, not at broker
            parts = []
            if below_basis:
                flags.append("stuck")
                parts.append("STUCK")
                stuck_value += 100 * p["qty"] * (cur or 0)
                stuck_count += 1
            if not_placed:
                flags.append("cc")
                parts.append("CC TO WRITE")
                cc_shares += 100 * p["qty"]
                cc_contracts += p["qty"]
            if parts:
                action = " · ".join(parts)
                act_state = "bad" if below_basis else "warn"

        rows.append({"ticker": p["underlying"], "acct": p["acct"], "type": typ,
                     "cur": cur, "strike": p["strike"], "qty": p["qty"],
                     "expiry": p["expiry"], "gtc": gtc_label, "gtc_state": gtc_state,
                     "action": action, "action_state": act_state, "flags": flags})

    cards = {
        "stuck": {"value": stuck_value, "count": stuck_count},
        "gtc": {"missing": gtc_missing},
        "cc": {"shares": cc_shares, "max": cc_contracts},
    }
    return {"rows": rows, "cards": cards, "has_fidelity": has_fid}
