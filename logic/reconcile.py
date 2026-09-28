"""Reconcile — compare tracked positions (TradeLog) vs a Fidelity CSV export.

Ported from the legacy Wheel Dashboard. Answers Q2 ("is the book clean?"): every
open short put/call is matched to Fidelity by acct·ticker·type·expiry·strike;
anything that doesn't line up (qty off, in Fidelity only, or tracked only) is flagged.
Pure — no Streamlit, no fetching.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

# Fidelity account number → our label. EDIT to your current numbers (a fresh
# Fidelity export can change these). Accounts not listed here are skipped.
ACCOUNT_MAP = {"Z52229635": "LLC", "148537624": "IRA", "X77951079": "IRA"}

_OPT_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])([\d.]+)$")


def _num(v) -> float:
    """'$1,234.56' / '(1,234)' / '+90' → float; 0.0 on failure (Fidelity notation)."""
    try:
        s = str(v).replace("$", "").replace(",", "").replace("+", "").strip()
        if s.startswith("(") and s.endswith(")"):
            val = -float(s[1:-1])
        else:
            val = float(s)
        return 0.0 if val != val else val
    except (TypeError, ValueError):
        return 0.0


def _parse_opt_symbol(raw: str):
    """' -AMZN260501C230' → {underlying, expiry(YYYY-MM-DD), kind, strike} or None."""
    s = raw.strip().lstrip("-").strip()
    m = _OPT_RE.match(s)
    if not m:
        return None
    ticker, dt6, k, strike_s = m.groups()
    try:
        return {"underlying": ticker,
                "expiry": datetime.strptime(dt6, "%y%m%d").strftime("%Y-%m-%d"),
                "kind": "CALL" if k == "C" else "PUT",
                "strike": float(strike_s)}
    except ValueError:
        return None


def parse_fidelity(content: bytes, account_map: dict | None = None) -> list:
    """Fidelity positions CSV (bytes) → list of position dicts (options·shares·cash).
    Line-by-line to dodge pandas column-shift on the ragged export."""
    amap = account_map or ACCOUNT_MAP
    out = []
    try:
        lines = content.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        f = [x.strip().strip('"') for x in line.split(",")]
        if len(f) < 5:
            continue
        acct_num = f[0].strip()
        if acct_num not in amap:
            continue
        acct = amap[acct_num]
        symbol = f[2].strip() if len(f) > 2 else ""
        if not symbol:
            continue
        # Skip metadata rows (valid tickers are uppercase; options start with '-')
        if " " in symbol or (not symbol.startswith("-") and not symbol.replace("*", "").isupper()):
            continue

        def g(i):
            return f[i] if len(f) > i else ""
        qty, last, cur_v = _num(g(4)), _num(g(5)), _num(g(7))
        tot_gl, cost_t, avg_c = _num(g(10)), _num(g(13)), _num(g(14))

        if "**" in symbol or "MONEY MARKET" in symbol.upper():
            out.append({"acct": acct, "underlying": "CASH", "pos_type": "CASH",
                        "qty": 1, "expiry": None, "strike": None, "cur_val": cur_v,
                        "last_px": 1.0, "avg_cost": 1.0, "cost_total": cur_v, "total_gl": 0.0})
            continue
        if symbol.startswith("-"):
            opt = _parse_opt_symbol(symbol)
            if not opt:
                continue
            out.append({"acct": acct, "underlying": opt["underlying"], "pos_type": opt["kind"],
                        "qty": int(abs(qty)) if qty else 1, "short": qty < 0,
                        "expiry": opt["expiry"], "strike": opt["strike"], "last_px": last,
                        "avg_cost": avg_c, "cost_total": cost_t, "cur_val": cur_v, "total_gl": tot_gl})
            continue
        out.append({"acct": acct, "underlying": symbol, "pos_type": "SHARE",
                    "qty": int(abs(qty)) if qty else 0, "expiry": None, "strike": None,
                    "last_px": last, "avg_cost": avg_c, "cost_total": cost_t,
                    "cur_val": cur_v, "total_gl": tot_gl})
    return out


def _exp_iso(v) -> str:
    d = pd.to_datetime(str(v), errors="coerce")
    return "" if pd.isna(d) else d.strftime("%Y-%m-%d")


def tracked_from_tradelog(df: pd.DataFrame) -> list:
    """Open option/share positions from the TradeLog, in reconcile shape."""
    if df.empty:
        return []
    d = df.copy()
    d.columns = [str(c).strip() for c in d.columns]
    d = d[d.get("Status", "").astype(str).str.upper().str.startswith("OPEN")]
    out = []
    for _, r in d.iterrows():
        stock = str(r.get("Stock", "")).strip().upper()
        typ = str(r.get("Opt Typ", "")).strip().upper()
        if stock in ("", "CASH", "VAULT") or typ not in ("PUT", "CALL", "LEAP"):
            continue
        out.append({"acct": str(r.get("Account", "")).strip().upper(),
                    "underlying": stock, "pos_type": typ,
                    "qty": int(_num(r.get("Qty")) or 0),
                    "expiry": _exp_iso(r.get("Exp Date")),
                    "strike": round(_num(r.get("Strike Price")), 2)})
    return out


def _key(p) -> tuple:
    pt = "CALL" if p["pos_type"] in ("LEAP", "CALL") else p["pos_type"]   # Fidelity reports LEAP as CALL
    return (p["acct"], p["underlying"], pt, p.get("expiry") or "",
            round(float(p.get("strike") or 0), 2))


def reconcile(tracked: list, fidelity: list) -> dict:
    """Compare tracked vs Fidelity options. Returns rows + summary counts + cash."""
    fid_opts = [p for p in fidelity if p["pos_type"] in ("PUT", "CALL")]
    fid_idx = {_key(fp): fp for fp in fid_opts}
    tr_keys = {_key(p) for p in tracked}
    rows = []
    for p in tracked:
        fp = fid_idx.get(_key(p))
        matched = fp is not None
        qty_fid = fp["qty"] if fp else None
        rows.append({"acct": p["acct"], "ticker": p["underlying"], "type": p["pos_type"],
                     "strike": p.get("strike"), "expiry": p.get("expiry"),
                     "qty_gs": p["qty"], "qty_fid": qty_fid, "matched": matched,
                     "qty_ok": bool(matched and qty_fid == p["qty"]),
                     "state": ("MATCHED" if (matched and qty_fid == p["qty"]) else
                               "MISMATCH" if matched else "TRACKED_ONLY")})
    for fp in fid_opts:
        if _key(fp) not in tr_keys:
            rows.append({"acct": fp["acct"], "ticker": fp["underlying"], "type": fp["pos_type"],
                         "strike": fp.get("strike"), "expiry": fp.get("expiry"),
                         "qty_gs": None, "qty_fid": fp["qty"], "matched": False,
                         "qty_ok": False, "state": "FID_ONLY"})

    def count(s):
        return sum(1 for r in rows if r["state"] == s)
    summary = {"total": len(rows), "matched": count("MATCHED"), "mismatch": count("MISMATCH"),
               "fid_only": count("FID_ONLY"), "tracked_only": count("TRACKED_ONLY"),
               "fid_positions": len(fidelity)}
    # Cash by account: Fidelity SPAXX vs nothing-to-compare (tracked cash lives in the sheet).
    fid_cash = {}
    for p in fidelity:
        if p["pos_type"] == "CASH":
            fid_cash[p["acct"]] = fid_cash.get(p["acct"], 0.0) + p["cur_val"]
    return {"rows": rows, "summary": summary, "fid_cash": fid_cash}
