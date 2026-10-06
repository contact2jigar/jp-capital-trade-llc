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
_WATCHLIST_GID = _sheet.gid("watchlist")


def watchlist() -> pd.DataFrame:
    """The shared WatchList tab (used by Bottom Finder and Price Wall Map)."""
    return read_published_csv(_WATCHLIST_SHEET_ID, _WATCHLIST_GID)


@cached(TTL["gsheet"])
def read_grid(gid: str) -> pd.DataFrame:
    """Read a tab as a RAW, RAGGED grid of strings. The CSV export already quotes
    fields with commas ('$970,176' stays whole), but the MonitorBoard rows have
    different column counts, so pandas' parser chokes — the csv module doesn't.
    Rows are padded to a uniform width. Empty DataFrame on failure."""
    import csv
    import io
    url = (f"https://docs.google.com/spreadsheets/d/{_sheet.WORKBOOK_ID}"
           f"/export?format=csv&gid={gid}")
    try:
        import certifi
        import requests
        r = requests.get(url, verify=certifi.where(), timeout=15)   # certifi SSL — the proven path
        if r.status_code != 200:
            return pd.DataFrame()
        rows = list(csv.reader(io.StringIO(r.text)))                # csv module handles ragged + quotes
        if not rows:
            return pd.DataFrame()
        w = max(len(x) for x in rows)
        return pd.DataFrame([x + [""] * (w - len(x)) for x in rows]).fillna("")
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
def read_grid_by_name(sheet_name: str) -> pd.DataFrame:
    """Read a tab as a raw ragged grid BY NAME (gviz) — no gid needed. Used for the
    Allocation tab (whose gid isn't registered). Empty DataFrame on failure."""
    import csv
    import io
    url = (f"https://docs.google.com/spreadsheets/d/{_sheet.WORKBOOK_ID}"
           f"/gviz/tq?tqx=out:csv&sheet={sheet_name}")
    try:
        import certifi
        import requests
        r = requests.get(url, verify=certifi.where(), timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()
        rows = list(csv.reader(io.StringIO(r.text)))
        if not rows:
            return pd.DataFrame()
        w = max(len(x) for x in rows)
        return pd.DataFrame([x + [""] * (w - len(x)) for x in rows]).fillna("")
    except Exception:
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
           "ytd_start_total": 0.0, "cur_total": 0.0,
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
    out["park_llc"] = kv_num("ytd park llc", "park llc", "llc park") or 0.0   # LLC cash parked elsewhere
    # Optional whole-portfolio totals — if set, the Grand Total uses these (true all-accounts
    # figures) instead of the sum of the tracked accounts, which are estimates.
    out["ytd_start_total"] = kv_num("ytd start total", "total jan 1", "start total", "ytd total") or 0.0
    out["cur_total"] = kv_num("current total", "total now", "cur total", "all accounts") or 0.0
    out["vix"] = num(cell(2, 29))                 # AD3
    out["vix_chg"] = num(cell(3, 29))             # AD4
    trend = cell(7, 29)                            # AD8
    out["trend"] = trend if trend in ("Uptrend", "Downtrend") else None
    return out


def tradelog() -> pd.DataFrame:
    """The TradeLog tab — every wheel/LEAP row (the sheet's source of truth)."""
    return read_published_csv(_sheet.WORKBOOK_ID, _sheet.gid("tradelog"))


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
def read_published_csv(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    """Read one worksheet tab from a Google Sheet published-to-web as CSV, by
    spreadsheet id + gid. No auth (the sheet must be shared/published). Used by
    pages that read a specific tab (e.g. Bottom Finder's WatchList). Empty
    DataFrame on failure. Columns are stripped of surrounding whitespace."""
    url = (f"https://docs.google.com/spreadsheets/d/{sheet_id}"
           f"/export?format=csv&gid={gid}")
    try:
        import certifi
        import requests
        r = requests.get(url, verify=certifi.where(), timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()
        import io
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = df.columns.str.strip()
        return df
    except Exception:
        return pd.DataFrame()
