"""Wheel Autopilot — CSP GTC Refresh logic (pure; no Streamlit, no I/O).

Standalone version for the rebuild: parse a Fidelity Positions CSV directly (by
column name), keep open short PUTs, and for each compute the DTE-bucketed GTC
buy-back target + a status, so every CSP can sit on a standing GTC.

DTE buckets (target capture → GTC multiplier on the entry premium):
  >21 DTE → 60% · ×0.40   ·  14-21 → 75% · ×0.25
  7-14    → 80% · ×0.20   ·  <7    → 90% · ×0.10

Entry premium & current price are per-share; Fidelity stores option dollars as
$/contract, so totals divide by (qty × 100). Falls back to the spec's simple
"Cost Basis / 100" and "Last Price / 100" when only per-share columns exist.
"""

from __future__ import annotations

import re
from datetime import date

# -{TICKER}{YYMMDD}{C|P}{STRIKE}  e.g. "-TSLA260925P340", "-COIN260918P167.5"
_SYMBOL_RE = re.compile(r"^-?([A-Za-z]+)(\d{6})([CP])(\d+(?:\.\d+)?)$")
_SKIP = {"CASH", "VAULT"}

# status → (sort rank, emoji, action template)
_STATUS = {
    "CLOSE NOW":    (0, "🔴", "Fire market / hit bid"),
    "APPROACHING":  (1, "🟠", "GTC ${t:.2f} — near fill"),
    "SET GTC":      (2, "🟡", "Set GTC ${t:.2f}"),
    "HOLD (early)": (3, "🟢", "Hold — GTC ${t:.2f} (early)"),
}


def bucket_for(dte: int) -> tuple[str, int, float]:
    if dte > 21:
        return ">21", 60, 0.40
    if dte >= 14:
        return "14-21", 75, 0.25
    if dte >= 7:
        return "7-14", 80, 0.20
    return "<7", 90, 0.10


def status_for(current: float, target: float) -> str:
    if current <= target:
        return "CLOSE NOW"
    if current <= target * 1.20:
        return "APPROACHING"
    if current > target * 2:
        return "HOLD (early)"
    return "SET GTC"


def gtc_target(init_prem, dte) -> float | None:
    """GTC buy-back price = entry premium × the DTE-bucket multiplier. None if
    no valid entry premium."""
    e = _num(init_prem)
    if e is None or e <= 0:
        return None
    _, _, mult = bucket_for(int(dte) if dte is not None else 0)
    return round(e * mult, 2)


def from_tradelog(df, today: date | None = None) -> list[dict]:
    """Build GTC rows straight from the sheet's TradeLog — open short PUTs only.
    Uses Init Prem (entry) and Current Prem (live), both already per-share, so no
    Fidelity CSV / ÷100 needed. Returns rows shaped like analyze()."""
    today = today or date.today()
    if df is None or getattr(df, "empty", True):
        return []
    d = df.copy()
    d.columns = [str(c).strip() for c in d.columns]
    out: list[dict] = []
    for _, r in d.iterrows():
        if str(r.get("Opt Typ", "")).strip().upper() != "PUT":
            continue
        if not str(r.get("Status", "")).strip().lower().startswith("open"):
            continue
        tk = str(r.get("Stock", "")).strip().upper()
        if not tk or tk in _SKIP:
            continue
        entry = _num(r.get("Init Prem"))
        current = _num(r.get("Current Prem"))
        if entry is None or entry <= 0 or current is None:
            continue

        dte = _num(r.get("DTE"))
        exp = str(r.get("Exp Date", "")).strip()
        if dte is None:
            try:
                from datetime import datetime
                dte = (datetime.strptime(exp, "%m/%d/%y").date() - today).days
            except ValueError:
                dte = 0
        dte = int(dte)

        label, cap, mult = bucket_for(dte)
        target = round(entry * mult, 2)
        status = status_for(current, target)
        rank, emoji, action_t = _STATUS[status]
        strike = _num(r.get("Strike Price"))
        try:
            qn = abs(int(_num(r.get("Qty")) or 1)) or 1
        except (TypeError, ValueError):
            qn = 1

        out.append({
            "_rank": rank,
            "needs_action": status != "HOLD (early)",
            "Priority": f"{emoji} {status}",
            "Account": str(r.get("Account", "") or "").strip(),
            "Ticker": tk,
            "Strike": f"{_fmt_strike(strike)} P" if strike is not None else "—",
            "Expiry": exp or "—",
            "DTE": dte,
            "Bucket": label,
            "Qty": qn,
            "Entry $": round(entry, 2),
            "Current $": round(current, 2),
            "Target GTC": target,
            "Action": action_t.format(t=target),
        })
    return out


def parse_symbol(sym) -> dict | None:
    """Fidelity option symbol → {ticker, expiry, type, strike}. None if not an option."""
    m = _SYMBOL_RE.match(str(sym).strip())
    if not m:
        return None
    tk, ymd, cp, strike = m.groups()
    try:
        exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError:
        return None
    return {"ticker": tk.upper(), "expiry": exp,
            "type": "PUT" if cp == "P" else "CALL", "strike": float(strike)}


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace("$", "").replace(",", "").replace("%", "")
    if s.lower() in ("", "--", "n/a", "nan", "none"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def _fmt_strike(x) -> str:
    try:
        return str(int(x)) if float(x).is_integer() else f"{float(x):g}"
    except (TypeError, ValueError):
        return str(x)


def _find_col(columns, *cands) -> str | None:
    low = {str(c).lower().strip(): c for c in columns}
    for cand in cands:
        if cand.lower() in low:
            return low[cand.lower()]
    for cand in cands:
        for k, orig in low.items():
            if cand.lower() in k:
                return orig
    return None


def analyze(rows, today: date | None = None) -> list[dict]:
    """`rows`: iterable of dict-like Fidelity position rows (e.g. df.to_dict('records')).
    Returns one GTC row per open short PUT (unsorted)."""
    today = today or date.today()
    rows = list(rows)
    cols = list(rows[0].keys()) if rows else []
    c_sym = _find_col(cols, "Symbol")
    c_qty = _find_col(cols, "Quantity", "Qty")
    c_cost_t = _find_col(cols, "Cost Basis Total", "Cost Basis")
    c_cost_ps = _find_col(cols, "Cost Basis Per Share", "Average Cost Basis")
    c_curval = _find_col(cols, "Current Value", "Current Val")
    c_last = _find_col(cols, "Last Price", "Last")
    c_acct = _find_col(cols, "Account Name", "Account")

    out: list[dict] = []
    for r in rows:
        p = parse_symbol(r.get(c_sym)) if c_sym else None
        if not p or p["type"] != "PUT" or p["ticker"] in _SKIP:
            continue
        qty = _num(r.get(c_qty))
        if qty is None or qty >= 0:               # short positions only
            continue
        qn = abs(int(qty)) or 1

        cost_t = _num(r.get(c_cost_t)) if c_cost_t else None
        cost_ps = _num(r.get(c_cost_ps)) if c_cost_ps else None
        curval = _num(r.get(c_curval)) if c_curval else None
        last = _num(r.get(c_last)) if c_last else None

        entry = (abs(cost_t) / (qn * 100) if cost_t else
                 (abs(cost_ps) / 100.0 if cost_ps else None))
        current = (abs(curval) / (qn * 100) if curval else
                   (abs(last) / 100.0 if last is not None else None))
        if entry is None or current is None or entry <= 0:
            continue

        dte = (p["expiry"] - today).days
        label, cap, mult = bucket_for(dte)
        target = round(entry * mult, 2)
        status = status_for(current, target)
        rank, emoji, action_t = _STATUS[status]

        out.append({
            "_rank": rank,
            "needs_action": status != "HOLD (early)",
            "Priority": f"{emoji} {status}",
            "Account": str(r.get(c_acct, "") or "").strip(),
            "Ticker": p["ticker"],
            "Strike": f"{_fmt_strike(p['strike'])} P",
            "Expiry": f"{p['expiry'].month}/{p['expiry'].day}",
            "DTE": dte,
            "Bucket": label,
            "Qty": qn,
            "Entry $": round(entry, 2),
            "Current $": round(current, 2),
            "Target GTC": target,
            "Action": action_t.format(t=target),
        })
    return out
