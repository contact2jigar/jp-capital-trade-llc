"""Google Sheet — read-only pull. One door.

Two supported modes (whichever is configured in secrets):
  1. Published CSV URL  → gsheet.csv_url   (simplest, no auth)
  2. Service account    → [gsheet.service_account] + gsheet.sheet_id (gspread)

Returns a DataFrame. Empty DataFrame if not configured / on failure.
"""

from __future__ import annotations

import pandas as pd

from config import settings
from config import sheet as _sheet
from services.cache import TTL, cached


@cached(TTL["gsheet"])
def read_sheet(worksheet: str = "Sheet1") -> pd.DataFrame:
    cfg = settings.gsheet_config()

    # Mode 1 — published CSV URL (no auth needed).
    if cfg.get("csv_url"):
        try:
            return pd.read_csv(cfg["csv_url"])
        except Exception:
            return pd.DataFrame()

    # Mode 2 — service account via gspread.
    if cfg.get("service_account") and cfg.get("sheet_id"):
        try:
            import gspread
            gc = gspread.service_account_from_dict(dict(cfg["service_account"]))
            ws = gc.open_by_key(cfg["sheet_id"]).worksheet(worksheet)
            return pd.DataFrame(ws.get_all_records())
        except Exception:
            return pd.DataFrame()

    return pd.DataFrame()


def is_configured() -> bool:
    cfg = settings.gsheet_config()
    return bool(cfg.get("csv_url") or (cfg.get("service_account") and cfg.get("sheet_id")))


# JP Capital WatchList tab (published to web): Stock · Stock Type · % Off High …
# Workbook id + tab gids live in ONE place — config/sheet.py — so replacing the
# sheet after a fresh copy is a single-line edit there.
_WATCHLIST_SHEET_ID = _sheet.WORKBOOK_ID
# The standalone WatchList tab was consolidated into TradeRadar (same Stock /
# Stock Type columns), so the universe now reads from there.
_WATCHLIST_GID = _sheet.gid("traderadar")


def watchlist() -> pd.DataFrame:
    """The shared WatchList tab (used by Bottom Finder and Price Wall Map)."""
    return read_published_csv(_WATCHLIST_SHEET_ID, _WATCHLIST_GID)


def _fetch_csv(url: str, retries: int = 3) -> str:
    """GET a Google CSV / gviz export with retries. RAISES on failure so neither
    the caller nor st.cache_data ever stores a transient empty — the next render
    just retries. On first load the app fires ~6 exports at once; one getting
    rate-limited used to brick the whole page. A sign-in HTML page (sharing lost)
    also counts as a failure."""
    import time
    import certifi
    import requests
    last = "no attempt"
    for i in range(retries):
        try:
            r = requests.get(url, verify=certifi.where(), timeout=15)   # certifi SSL — the proven path
            if r.status_code == 200 and r.text and r.text.lstrip()[:1] != "<":
                return r.text
            last = f"HTTP {r.status_code}" if r.status_code != 200 else "non-CSV (sign-in page?)"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.7 * (i + 1))
    raise RuntimeError(last)


@cached(TTL["gsheet"])
def _read_grid_cached(gid: str) -> pd.DataFrame:
    """Cached inner: raises on failure so failures are NOT cached (st.cache_data
    skips exceptions). Only a good read lands in the 120s cache."""
    import csv
    import io
    text = _fetch_csv(f"https://docs.google.com/spreadsheets/d/{_sheet.WORKBOOK_ID}"
                      f"/export?format=csv&gid={gid}")
    rows = list(csv.reader(io.StringIO(text)))                      # csv module handles ragged + quotes
    if not rows:
        raise RuntimeError("empty grid")
    w = max(len(x) for x in rows)
    return pd.DataFrame([x + [""] * (w - len(x)) for x in rows]).fillna("")


def read_grid(gid: str) -> pd.DataFrame:
    """Raw ragged grid for a tab. Retries; only successful reads are cached, so a
    transient Google rate-limit no longer bricks the page. Empty frame on failure."""
    try:
        return _read_grid_cached(gid)
    except Exception as e:
        globals()["_LAST_GRID_ERROR"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


def monitorboard() -> pd.DataFrame:
    """The MonitorBoard tab as a raw grid (Money Matrix · VIX · Premium · gaps)."""
    return read_grid(_sheet.gid("monitorboard"))


def performance() -> pd.DataFrame:
    """The Performance tab as a raw grid: row0 = IRA/LLC/SPY/QQQ/Total summary,
    row1 = column headers, rows 2+ = monthly IRA·LLC·SPY·QQQ·Total (newest first)."""
    return read_grid(_sheet.gid("performance"))


def scoreboard() -> pd.DataFrame:
    """The Scoreboard tab — DAILY rows (oldest first). row0 = headers, then
    Date · J(portfolio) · R(Rayan) · SPY (Start/End/Chg/%) · VIX."""
    return read_grid(_sheet.gid("scoreboard"))


@cached(TTL["gsheet"])
def _read_grid_by_name_cached(sheet_name: str) -> pd.DataFrame:
    import csv
    import io
    text = _fetch_csv(f"https://docs.google.com/spreadsheets/d/{_sheet.WORKBOOK_ID}"
                      f"/gviz/tq?tqx=out:csv&sheet={sheet_name}")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise RuntimeError("empty grid")
    w = max(len(x) for x in rows)
    return pd.DataFrame([x + [""] * (w - len(x)) for x in rows]).fillna("")


def read_grid_by_name(sheet_name: str) -> pd.DataFrame:
    """Read a tab as a raw ragged grid BY NAME (gviz) — no gid needed. Used for the
    Allocation tab (whose gid isn't registered). Retries; empty frame on failure."""
    try:
        return _read_grid_by_name_cached(sheet_name)
    except Exception as e:
        globals()["_LAST_GRID_ERROR"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


def allocation() -> pd.DataFrame:
    """The Allocation tab: LLC table in cols A–H, IRA table in cols K–S (+ scratch)."""
    return read_grid_by_name("Allocation")


@cached(TTL["gsheet"])
def monitor_externals() -> dict:
    """The few Monitor-Board inputs that CAN'T come from a TradeLog snapshot. These live in a
    KEY→VALUE block: column Z = key (label), column AA = value, so new inputs can be added by
    typing a row — no hardcoded cell positions. Keys are matched case/space-insensitively:
      • 'ATH IRA' / 'ATH LLC'              — the auto high-water marks (ratchet).
      • 'YTD Start IRA' / 'YTD Start LLC'  — each account's start-of-year balance (for YTD gain).
    VIX / change / trend still come from the live GOOGLEFINANCE cells (AD3/AD4/AD8), a fallback
    for when the Yahoo pull fails. Everything else on the board is computed from the TradeLog."""
    out = {"ath_ira": 0.0, "ath_llc": 0.0,
           "ytd_ira": 0.0, "ytd_llc": 0.0, "ytd_rollover": 0.0, "ytd_roth": 0.0,
           "cur_rollover": 0.0, "cur_roth": 0.0, "park_llc": 0.0,
           "ytd_start_total": 0.0, "cur_total": 0.0, "this_year": [],
           "vix": None, "vix_chg": None, "trend": None}
    grid = read_grid(_sheet.gid("monitorboard"))
    if grid.empty:
        return out

    def cell(r, col):
        try:
            return str(grid.iat[r, col]).strip()
        except Exception:
            return ""

    def num(s):
        s = str(s).replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    # Z (col 25) = key, AA (col 26) = value — read the whole block into a normalized dict.
    kv = {}
    for rr in range(grid.shape[0]):
        key = " ".join(cell(rr, 25).lower().split())   # lower + collapse any extra spaces
        if key:
            kv[key] = cell(rr, 26)

    def kv_num(*keys):
        for k in keys:
            v = num(kv.get(k, ""))
            if v is not None:
                return v
        return None

    # Key-value first; fall back to the legacy fixed cells (Z4/Z5) so ATH keeps working
    # until the sheet is migrated to the Z=key / AA=value layout.
    out["ath_ira"] = kv_num("ath ira") or num(cell(3, 25)) or 0.0      # else legacy Z4
    out["ath_llc"] = kv_num("ath llc") or num(cell(4, 25)) or 0.0      # else legacy Z5
    out["ytd_ira"] = kv_num("ytd start ira", "ytd ira", "start ira") or 0.0
    out["ytd_llc"] = kv_num("ytd start llc", "ytd llc", "start llc") or 0.0
    out["ytd_rollover"] = kv_num("ytd start rollover", "ytd rollover") or 0.0
    out["ytd_roth"] = kv_num("ytd start roth", "ytd roth") or 0.0
    out["cur_rollover"] = kv_num("current rollover", "rollover current", "cur rollover") or 0.0
    out["cur_roth"] = kv_num("current roth", "roth current", "cur roth") or 0.0
    out["roll_spy"] = kv_num("rollover spy shares", "rollover spy", "roll spy shares") or 0.0
    out["roth_spy"] = kv_num("roth spy shares", "roth spy") or 0.0
    out["park_llc"] = kv_num("leap account", "ytd park llc", "park llc", "llc park") or 0.0   # LLC cash parked elsewhere
    # Optional whole-portfolio totals — if set, the Grand Total uses these (true all-accounts
    # figures) instead of the sum of the tracked accounts, which are estimates.
    out["ytd_start_total"] = kv_num("ytd start total", "total jan 1", "start total", "ytd total") or 0.0
    out["cur_total"] = kv_num("current total", "total now", "cur total", "all accounts") or 0.0
    out["vix"] = num(cell(2, 29))                 # AD3
    out["vix_chg"] = num(cell(3, 29))             # AD4
    trend = cell(7, 29)                            # AD8
    out["trend"] = trend if trend in ("Uptrend", "Downtrend") else None

    # 📅 THIS YEAR — read the block the sheet COMPUTES at S9:W15 (the single source of truth).
    # S=label, T=Start, U=Now, V=Gain. We mirror these verbatim rather than recompute, so the
    # web card and the sheet/mobile can never drift. Labels: IRA, LLC, Wheel Total, Rollover,
    # Roth, Retirement Total, Grand Total. Start/Gain are blank when no Jan anchor is set.
    ty = []
    for rr in range(8, 15):                        # sheet rows 9..15 → grid idx 8..14
        label = cell(rr, 18)                       # col S
        if not label:
            continue
        ty.append({"label": label,
                   "start": num(cell(rr, 19)),     # col T
                   "now": num(cell(rr, 20)),       # col U
                   "gain": num(cell(rr, 21))})     # col V
    out["this_year"] = ty
    return out


@cached(TTL["gsheet"])
def monitor_board_cells() -> dict:
    """The Monitor Board's COMPUTED figures, read straight from the tab — the single source of
    truth that the web overlays onto its TradeLog recompute so web = sheet = mobile. Returns
    DOLLAR values only (Money matrix A3:E14 + Premium Tracker K4:L9); every percentage, gap and
    total is re-derived from these downstream, so the CSV's %-formatting never matters. Empty
    dict on any read failure → callers keep their recomputed numbers (graceful fallback)."""
    grid = read_grid(_sheet.gid("monitorboard"))
    if grid.empty or grid.shape[0] < 14 or grid.shape[1] < 12:
        return {}

    def num(r, c):
        try:
            s = str(grid.iat[r, c]).replace("$", "").replace(",", "").replace("%", "").strip()
            return float(s) if s not in ("", "—", "-", "#REF!", "#N/A", "nan") else None
        except Exception:
            return None

    # Money matrix: label in A, IRA in col B(1), LLC in col D(3). Grid idx = sheet row − 1.
    def acct(col):
        return {"cap": num(2, col), "ath": num(3, col), "vault": num(4, col),
                "wcap": num(6, col), "vtgt": num(7, col), "cih": num(8, col),
                "dep": num(9, col), "cc": num(10, col), "csp": num(11, col),
                "leap": num(12, col), "rtd": num(13, col)}

    out = {"ira": acct(1), "llc": acct(3),
           # Premium Tracker: labels in K(10), values in L(11).
           "premium": {"wk_goal": num(3, 11), "wk_earn": num(4, 11),
                       "mo_goal": num(6, 11), "mo_earn": num(7, 11)}}
    return out


def tradelog() -> pd.DataFrame:
    """The TradeLog tab — every wheel/LEAP row (the sheet's source of truth)."""
    return read_published_csv(_sheet.WORKBOOK_ID, _sheet.gid("tradelog"))


@cached(TTL["price"])        # short TTL so a token refresh in the sheet is picked up quickly
def rh_token() -> dict:
    """RH session token from the 'RHSecret' tab (label in col A, value in col B):
    RH_ACCESS / RH_REFRESH / RH_DEVICE / RH_ACCESS_EXP. Read by GID via the raw-grid
    export (gviz-by-name merges the long rows). {} if the tab is absent/unshared."""
    try:
        df = read_grid(_sheet.gid("rhsecret"))     # raw rows, no header interpretation
    except Exception:
        return {}
    out: dict[str, str] = {}
    if df is None or df.empty:
        return out
    for row in df.itertuples(index=False):
        cells = [str(x).strip() for x in row]
        if len(cells) >= 2 and cells[0]:
            key = cells[0].upper().replace(" ", "")
            if key in ("RH_ACCESS", "RH_REFRESH", "RH_DEVICE", "RH_ACCESS_EXP"):
                out[key] = cells[1]
    return out


@cached(TTL["gsheet"])
def watchlist_by_type() -> tuple[list, dict]:
    """(types, {stock_type -> [tickers]}) from the WatchList tab, plus an 'All'
    bucket. Falls back to config.universe under a single 'Watchlist' type so
    callers never dead-end. Shared by the Stock Type → Stock pickers."""
    df = watchlist()
    if df is None or df.empty or "Stock" not in df or "Stock Type" not in df:
        base = settings.universe()
        return (["Watchlist"], {"Watchlist": base}) if base else ([], {})
    df = df[["Stock", "Stock Type"]].copy()
    df["Stock"] = df["Stock"].astype(str).str.strip().str.upper()
    df["Stock Type"] = df["Stock Type"].astype(str).str.strip()
    df = df[(df["Stock"] != "") & (df["Stock"] != "NAN")]
    by_type: dict[str, list] = {}
    for t, g in df.groupby("Stock Type"):
        if not t or t.lower() == "nan":
            continue
        tickers = sorted(dict.fromkeys(g["Stock"].tolist()))
        if tickers:
            by_type[t] = tickers
    types = ["All"] + sorted(by_type.keys())
    by_type["All"] = sorted(dict.fromkeys(df["Stock"].tolist()))
    return types, by_type


@cached(TTL["gsheet"])
def _read_published_csv_cached(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    import io
    text = _fetch_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id}"
                      f"/export?format=csv&gid={gid}")
    df = pd.read_csv(io.StringIO(text))
    df.columns = df.columns.str.strip()
    if df.empty:
        raise RuntimeError("empty csv")
    return df


def read_published_csv(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    """Read one worksheet tab from a Google Sheet published-to-web as CSV, by
    spreadsheet id + gid. No auth (the sheet must be shared/published). Retries;
    only good reads are cached. Empty DataFrame on failure. Columns stripped."""
    try:
        return _read_published_csv_cached(sheet_id, gid)
    except Exception as e:
        globals()["_LAST_GRID_ERROR"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


@cached(TTL["gsheet"])
def vix_board() -> dict:
    """VIXBoard tab → VIX / VXN / SMH-RV30 volatility regime board (VXN drives the cash
    target). Returns {'indices': [ {key,emoji,universe,value,change,regime,bands,cur} ],
    'you': <cash fraction>} or {} on failure. Mirrors the iPhone VolStore parser."""
    try:
        g = read_grid(_sheet.gid("vixboard"))
    except Exception:
        return {}
    if g.empty or g.shape[0] < 17:
        return {}

    def cell(r, c):
        try:
            return str(g.iat[r, c]).strip()
        except Exception:
            return ""

    def num(s):
        try:
            return float(str(s).replace(",", "").replace("%", "").replace("$", "").strip())
        except Exception:
            return None

    def pct(s):
        v = num(s)
        return v / 100 if v is not None else None

    def prange(s):
        t = str(s).replace(" ", "").replace("%", "")
        if t.startswith("<"):
            return (0.0, num(t[1:]) or 0.0)
        if t.endswith("+"):
            lo = num(t[:-1]) or 0.0
            return (lo, lo + 10)
        if "-" in t:
            a, b = t.split("-", 1)
            return (num(a) or 0.0, num(b) or 0.0)
        v = num(t) or 0.0
        return (v, v + 5)

    palette = [("#ef4444", "#ffffff"), ("#f97316", "#ffffff"), ("#3b82f6", "#ffffff"),
               ("#a3e635", "#365314"), ("#4ade80", "#14532d"), ("#16a34a", "#ffffff")]
    shorts = ["Ext Bull", "Bull", "Normal", "Fear", "Ext Fear", "Panic"]

    def regname(s):
        parts = str(s).split()
        return parts[-1].upper() if parts else str(s).upper()

    cols = [("VIX", "🇺🇸", 1), ("VXN", "💻", 2), ("SMH RV30", "🔬", 3)]
    out = []
    for key, emoji, col in cols:
        bands = []
        for i in range(6):
            r = 11 + i
            lo, hi = prange(cell(r, col))
            bands.append({"regime": cell(r, 0), "short": shorts[i], "lo": lo, "hi": hi,
                          "cmin": pct(cell(r, 4)) or 0.0, "cmax": pct(cell(r, 5)) or 0.0,
                          "color": palette[i][0], "on": palette[i][1]})
        reg = regname(cell(6, col))
        cur = next((i for i, b in enumerate(bands) if regname(b["regime"]) == reg), 2)
        out.append({"key": key, "emoji": emoji, "universe": cell(3, col),
                    "value": num(cell(4, col)), "change": pct(cell(5, col)),
                    "regime": reg, "bands": bands, "cur": cur})
    return {"indices": out, "you": pct(cell(7, 4))}
