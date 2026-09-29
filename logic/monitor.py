"""MonitorBoard — pure aggregations for the Monitor page (no Streamlit).

First sections built: P/L by Open Date and P/L by Close Date, each drilled
Year → Month → Account → Stock from the TradeLog (the sheet's source of truth).
The Monitor Table / Money Matrix / VIX summary blocks come next.
"""

from __future__ import annotations

import pandas as pd


def _money(v) -> float:
    """'1,027' / '$1,027' / '-155' → float. 0.0 if blank/unparseable."""
    if v is None:
        return 0.0
    s = str(v).strip().replace("$", "").replace(",", "")
    if s in ("", "--", "nan", "None"):
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
    except ValueError:
        return 0.0
    return -f if neg else f


def pl_rollup(df: pd.DataFrame, date_col: str,
              pl_col: str = "Profit Loss", cash_col: str = "Cash Release") -> pd.DataFrame:
    """Tidy P/L rows with parsed Year/Month for `date_col`. One row per trade
    that has a valid date; P/L and Cash numeric. Drops CASH/VAULT spacer rows."""
    if df.empty or date_col not in df.columns:
        return pd.DataFrame(columns=["Year", "Month", "Account", "Stock", "P/L", "Cash Release"])
    d = df.copy()
    d.columns = [str(c).strip() for c in d.columns]
    dt = pd.to_datetime(d[date_col], errors="coerce")
    d = d.assign(_dt=dt)
    d = d[d["_dt"].notna()]
    stock = d.get("Stock", "").astype(str).str.strip().str.upper()
    d = d[~stock.isin(["", "NAN", "CASH", "VAULT"])]
    # P/L is sell-side wheel premium only. A bought LEAP (B / S == "B") carries its
    # debit in "Profit Loss" as a large negative — that's capital deployed, not a
    # P/L event — so the sheet's P/L pivot excludes it and so do we.
    bs = d.get("B / S", "").astype(str).str.strip().str.upper()
    d = d[bs != "B"]
    out = pd.DataFrame({
        "Year": d["_dt"].dt.year,
        "Month": d["_dt"].dt.strftime("%b"),
        "_m": d["_dt"].dt.month,
        "Week": "W" + (((d["_dt"].dt.day - 1) // 7 + 1).astype(int).astype(str)),
        "Account": d.get("Account", "").astype(str).str.strip(),
        "Stock": d.get("Stock", "").astype(str).str.strip().str.upper(),
        "P/L": d.get(pl_col, 0).map(_money),
        "Cash Release": d.get(cash_col, 0).map(_money),
        "Cash Reserve": d.get("Cash Reserve", 0).map(_money),
    })
    return out


def monthly_totals(rollup: pd.DataFrame) -> pd.DataFrame:
    """Year-Month totals from a pl_rollup frame, newest first."""
    if rollup.empty:
        return pd.DataFrame(columns=["Year", "Month", "P/L", "Cash Release", "Trades"])
    g = (rollup.groupby(["Year", "_m", "Month"], as_index=False)
         .agg(**{"P/L": ("P/L", "sum"), "Cash Release": ("Cash Release", "sum"),
                 "Trades": ("Stock", "size")}))
    g = g.sort_values(["Year", "_m"], ascending=[False, False]).drop(columns="_m")
    return g.reset_index(drop=True)


def detail_for(rollup: pd.DataFrame, year: int, month: str) -> pd.DataFrame:
    """Account → Stock detail for one Year/Month, P/L descending."""
    if rollup.empty:
        return rollup
    sel = rollup[(rollup["Year"] == year) & (rollup["Month"] == month)]
    return (sel.groupby(["Account", "Stock"], as_index=False)
            .agg(**{"P/L": ("P/L", "sum"), "Cash Release": ("Cash Release", "sum")})
            .sort_values("P/L", ascending=False).reset_index(drop=True))


# ═══════════════════════════════════════════════════════════════════════════
# MonitorBoard — computed live from the TradeLog (mirrors MonitorBoard.gs v16).
# Every number is derived here, not read from the sheet's MonitorBoard tab; only
# the ATH ratchet (Z4/Z5) and live VIX/SPY come from outside (they can't be
# derived from a TradeLog snapshot). Verified cell-for-cell against the sheet.
# ═══════════════════════════════════════════════════════════════════════════

# VIX 2-state allocation bands (static, from the sheet): Range, Up Min/Max, Dn Min/Max.
BANDS = [
    ("8–13",   0.40, 0.65, 0.60, 0.80),
    ("13–15",  0.30, 0.40, 0.45, 0.60),
    ("15-20",  0.15, 0.25, 0.40, 0.45),
    ("20-25",  0.10, 0.15, 0.35, 0.40),
    ("25-30",  0.05, 0.10, 0.30, 0.35),
    ("30–100", 0.00, 0.05, 0.20, 0.30),
]


def band_index(vix: float) -> int:
    v = float(vix or 0)
    return 0 if v < 13 else 1 if v < 15 else 2 if v < 20 else 3 if v < 25 else 4 if v < 30 else 5


def allocation(vix: float, trend: str) -> float:
    """VIX Allocation % = midpoint of the active band's Up (or Dn) column."""
    b = BANDS[band_index(vix)]
    return (b[1] + b[2]) / 2 if str(trend) == "Uptrend" else (b[3] + b[4]) / 2


def _openrows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.get("Status", "").astype(str).str.upper().str.startswith("OPEN")]


def _sumres(od: pd.DataFrame, account=None, opt=None, stock_eq=None,
            stock_ne=None, itmput=False) -> float:
    """Sum of Cash Reserve over open rows matching the filters (the .gs FILTER())."""
    d = od
    if account:
        d = d[d["Account"].astype(str).str.upper() == account]
    if opt:
        d = d[d["Opt Typ"].astype(str).str.upper() == opt]
    if stock_eq:
        d = d[d["Stock"].astype(str).str.upper() == stock_eq]
    if stock_ne:
        d = d[d["Stock"].astype(str).str.upper() != stock_ne]
    if itmput:
        cp = d["Current Price"].map(_money)
        k = d["Strike Price"].map(_money)
        d = d[(d["Opt Typ"].astype(str).str.upper() == "PUT") & (cp > 0) & (k > cp)]
    return float(d["Cash Reserve"].map(_money).sum()) if "Cash Reserve" in d else 0.0


def _account_money(od: pd.DataFrame, acct: str, ath: float, alloc: float) -> dict:
    cap = _sumres(od, account=acct, stock_ne="VAULT")          # incl. CASH, excl. VAULT
    ath = max(float(ath or 0), cap)                            # ratchet: max(stored, current)
    vault = ath * 0.30                                          # Gate 8 crash brake
    wcap = cap - vault                                         # Wheel Capital
    vtgt = (1 - alloc) * wcap                                  # VIX Target (cash to keep)
    totalcash = _sumres(od, account=acct, stock_eq="CASH")
    cih = totalcash - vault                                    # Cash In Hand
    dep = _sumres(od, account=acct, stock_ne="VAULT") - totalcash  # Deployed
    cc = _sumres(od, account=acct, opt="CALL")
    csp = _sumres(od, account=acct, opt="PUT")
    leap = _sumres(od, account=acct, opt="LEAP")
    itm = _sumres(od, account=acct, itmput=True)               # ITM short-put reserve
    rtd = vtgt - dep                                           # Ready to deploy / CSP Gap
    ccbrk = (cc + itm) / wcap if wcap else 0.0                 # CC Breaker (45% cap)
    return dict(cap=cap, ath=ath, vault=vault, wcap=wcap, vtgt=vtgt, cih=cih, dep=dep,
                cc=cc, csp=csp, leap=leap, itm=itm, rtd=rtd, ccbrk=ccbrk,
                brkgap=(0.45 - ccbrk) * wcap, cspitm=(itm / wcap if wcap else 0.0),
                leappct=(leap / wcap if wcap else 0.0), leapgap=0.02 * wcap - leap)


def _pl_between(df: pd.DataFrame, start, end) -> float:
    """Sum of Profit Loss for rows whose Open Date falls in [start, end] (the
    Premium Tracker's SUMIFS on col N by col G)."""
    if df.empty or "Open Date" not in df or "Profit Loss" not in df:
        return 0.0
    dt = pd.to_datetime(df["Open Date"], errors="coerce", format="mixed").dt.date
    m = (dt >= start) & (dt <= end)
    return float(df.loc[m, "Profit Loss"].map(_money).sum())


def monitor_board(df: pd.DataFrame, ath_ira: float, ath_llc: float,
                  vix: float, vix_chg: float, trend: str) -> dict:
    """Everything the Monitor Board renders, computed from the TradeLog.
    ath_* / vix / trend come from outside (ratchet + live market)."""
    import datetime as _d
    od = _openrows(df)
    alloc = allocation(vix, trend)
    I = _account_money(od, "IRA", ath_ira, alloc)
    L = _account_money(od, "LLC", ath_llc, alloc)
    wsum = I["wcap"] + L["wcap"]

    def wavg(k):
        return (I[k] * I["wcap"] + L[k] * L["wcap"]) / wsum if wsum else 0.0

    total = dict(rtd=I["rtd"] + L["rtd"], ccbrk=wavg("ccbrk"),
                 brkgap=I["brkgap"] + L["brkgap"], cspitm=wavg("cspitm"),
                 leappct=((I["leap"] + L["leap"]) / wsum if wsum else 0.0),
                 leapgap=0.02 * wsum - (I["leap"] + L["leap"]))

    today = _d.date.today()
    monday = today - _d.timedelta(days=today.weekday())
    first = today.replace(day=1)
    wk_goal = wsum * 0.65 * 0.0077
    wk_earn = _pl_between(df, monday, today)
    mo_goal = wk_goal * 4.33
    mo_earn = _pl_between(df, first, today)
    premium = [("🎯 Wk Goal", wk_goal), ("💰 Wk Earned", wk_earn), ("⏳ Wk Gap", wk_goal - wk_earn),
               ("🎯 Mo Goal", mo_goal), ("💰 Mo Earned", mo_earn), ("⏳ Mo Gap", mo_goal - mo_earn)]

    return dict(ira=I, llc=L, total=total, alloc=alloc, vix=vix, vix_chg=vix_chg,
                trend=trend, band=band_index(vix), premium=premium)
