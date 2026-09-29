"""Command Center — Monitor Board + P/L, the daily cockpit view.

P/L drill-downs are live from the sheet's TradeLog (Year → Month → Account → Stock).
The Monitor Board summary (Money Matrix · VIX table · Premium Tracker) mirrors the
sheet's MonitorBoard tab — wiring next (its numbers have commas that split in CSV).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from logic import gtc_refresh
from logic import monitor as engine
from services import gsheet, yahoo

# Column order mirrors the sheet's TradeLog, + Cash Reserve/Release, DTE & Action at the end.
_TL_COLS = ["Stock", "Account", "Status", "Opt Typ", "Close Date", "Open Date", "Exp Date",
            "Current Price", "Strike Price", "Init Prem", "Return", "Qty", "Profit Loss",
            "Cash Reserve", "Cash Release", "Current Prem", "GTC", "% Captured", "Action", "DTE"]


@st.cache_data(ttl=120, show_spinner=False)
def _tradelog() -> pd.DataFrame:
    return gsheet.tradelog()


@st.cache_data(ttl=300, show_spinner=False)
def _mb_externals() -> dict:
    return gsheet.monitor_externals()


@st.cache_data(ttl=120, show_spinner=False)
def _mb_market() -> dict:
    return yahoo.market_context()


# Fixed sheet-brand colors (work on both themes); body follows the palette.
_MB_DARK, _MB_SUB, _MB_GOLD = "#1e2c31", "#444444", "#ffd966"
_MB_BAND = ["#e06666", "#ef9a5c", "#ffd966", "#b7d77a", "#93c47d", "#6aa84f"]
_MB_GREEN, _MB_RED, _MB_YELLOW, _MB_BLUE = "#93c47d", "#d88989", "#ffd966", "#6d9eeb"


def _m0(v) -> str:
    v = float(v or 0)
    return f"−${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def _pc(v) -> str:
    return f"{float(v or 0) * 100:.1f}%"


def _mb_pal(c: dict) -> dict:
    return dict(body=c["panel"], txt=c["text"], bd=c["border"], sect=c["raised"])


def _cell(v, pal, *, align="right", bg=None, fg=None, bold=False, bd=None):
    bd = bd or pal["bd"]
    s = f"border:1px solid {bd};padding:5px 9px;text-align:{align};"
    s += f"background:{bg or pal['body']};color:{fg or pal['txt']};"
    if bold:
        s += "font-weight:700;"
    return f"<td style='{s}white-space:nowrap;'>{v}</td>"


def _money_matrix(r: dict, pal: dict) -> str:
    I, L = r["ira"], r["llc"]

    def rowvals(lbl, iv, ip, lv, lp, ready=False):
        def valcell(v, pct):
            fg = None
            if ready:
                fg = "#2f7e25" if float(v) >= 0 else "#c00000"
            pcell = "—" if pct is None else _pc(pct)
            return (_cell(_m0(v), pal, fg=fg, bold=True)
                    + _cell(pcell, pal, align="center", fg=fg))
        lab = (f"<td style='border:1px solid {pal['bd']};padding:5px 9px;text-align:left;"
               f"background:{pal['sect']};color:{pal['txt']};font-weight:700;white-space:nowrap;'>{lbl}</td>")
        return f"<tr>{lab}{valcell(iv, ip)}{valcell(lv, lp)}</tr>"

    def bar(title):
        return (f"<tr><td colspan='5' style='background:{_MB_DARK};color:#fff;font-weight:700;"
                f"padding:5px 9px;text-align:left;border:1px solid {pal['bd']};'>{title}</td></tr>")

    head = "".join(f"<th style='background:{_MB_SUB};color:#fff;border:1px solid {pal['bd']};"
                   f"padding:6px 9px;text-align:{a};font-weight:700;white-space:nowrap;'>{h}</th>"
                   for h, a in [("Metric", "left"), ("IRA", "right"), ("IRA %", "center"),
                                ("LLC", "right"), ("LLC %", "center")])
    body = bar("💰 MONEY")
    body += rowvals("Capital", I["cap"], 1.0, L["cap"], 1.0)
    body += rowvals("🏔️ All Time High", I["ath"], None, L["ath"], None)
    body += rowvals("🏦 Cash Vault (30% ATH)", I["vault"], I["vault"] / I["cap"], L["vault"], L["vault"] / L["cap"])
    body += bar("🛞 WHEEL")
    body += rowvals("Capital", I["wcap"], I["wcap"] / I["cap"], L["wcap"], L["wcap"] / L["cap"])
    body += rowvals("🎯 VIX Target", I["vtgt"], I["vtgt"] / I["wcap"], L["vtgt"], L["vtgt"] / L["wcap"])
    body += rowvals("💰 Cash In Hand", I["cih"], I["cih"] / I["wcap"], L["cih"], L["cih"] / L["wcap"])
    body += rowvals("Deployed", I["dep"], I["dep"] / I["wcap"], L["dep"], L["dep"] / L["wcap"])
    body += rowvals("📞 CC", I["cc"], I["cc"] / I["wcap"], L["cc"], L["cc"] / L["wcap"])
    body += rowvals("🛡️ CSP", I["csp"], I["csp"] / I["wcap"], L["csp"], L["csp"] / L["wcap"])
    body += rowvals("🚀 LEAP", I["leap"], I["leap"] / I["wcap"], L["leap"], L["leap"] / L["wcap"])
    body += rowvals("💰 Ready to deploy", I["rtd"], I["rtd"] / I["wcap"], L["rtd"], L["rtd"] / L["wcap"], ready=True)
    return (f"<table style='border-collapse:collapse;font-size:14.5px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def _vix_table(r: dict, pal: dict) -> str:
    head = "".join(f"<th style='background:{_MB_SUB};color:#fff;border:1px solid {pal['bd']};"
                   f"padding:8px 11px;text-align:center;font-weight:700;font-size:14px;white-space:nowrap;'>{h}</th>"
                   for h in ["VIX Range", "Up Min", "Up Max", "Dn Min", "Dn Max"])
    up = r["trend"] == "Uptrend"
    body = ""
    for i, b in enumerate(engine.BANDS):
        active = i == r["band"]
        rng = (f"<td style='border:1px solid {pal['bd']};padding:8px 11px;text-align:center;"
               f"background:{_MB_BAND[i]};color:#111;font-weight:700;font-size:14px;'>{b[0]}</td>")
        tds = ""
        for j, val in enumerate(b[1:]):
            hot = active and ((up and j in (0, 1)) or (not up and j in (2, 3)))
            bg = _MB_BLUE if hot else pal["body"]
            fg = "#111" if hot else pal["txt"]
            tds += (f"<td style='border:1px solid {pal['bd']};padding:8px 11px;text-align:center;"
                    f"background:{bg};color:{fg};font-size:14px;{'font-weight:700;' if hot else ''}'>{val * 100:.0f}%</td>")
        body += f"<tr>{rng}{tds}</tr>"
    return (f"<table style='border-collapse:collapse;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def _premium_table(r: dict, pal: dict) -> str:
    head = (f"<th colspan='2' style='background:{_MB_DARK};color:{_MB_GOLD};border:1px solid {pal['bd']};"
            f"padding:8px 11px;text-align:center;font-weight:700;font-size:14px;'>📊 PREMIUM TRACKER</th>")
    body = ""
    for lbl, val in r["premium"]:
        gap = "Gap" in lbl
        bg = pal["body"]
        if gap:
            bg = _MB_GREEN if val <= 0 else _MB_YELLOW
        lab = (f"<td style='border:1px solid {pal['bd']};padding:8px 11px;background:{_MB_SUB};color:#fff;"
               f"font-weight:700;font-size:14px;white-space:nowrap;'>{lbl}</td>")
        val_c = (f"<td style='border:1px solid {pal['bd']};padding:8px 11px;text-align:center;"
                 f"background:{bg};color:{'#111' if gap else pal['txt']};font-size:14px;font-weight:700;'>{_m0(val)}</td>")
        body += f"<tr>{lab}{val_c}</tr>"
    return (f"<table style='border-collapse:collapse;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def _gaps_table(r: dict, pal: dict) -> str:
    cols = ["Account", "CSP Gap", "CC Breaker", "Breaker Gap", "%CSP ITM", "LEAP %", "LEAP Gap"]
    head = "".join(f"<th style='background:{_MB_DARK};color:#fff;border:1px solid {pal['bd']};"
                   f"padding:8px 11px;text-align:center;font-weight:700;font-size:14px;white-space:nowrap;'>{h}</th>"
                   for h in cols)

    def brk_bg(v):
        return _MB_RED if v >= 0.45 else (_MB_YELLOW if v >= 0.30 else _MB_GREEN)

    def rowline(name, d):
        lab = (f"<td style='border:1px solid {pal['bd']};padding:8px 11px;background:{_MB_SUB};color:#fff;"
               f"font-weight:700;text-align:center;font-size:14px;'>{name}</td>")
        cells = [
            (_m0(d["rtd"]), _MB_GREEN if d["rtd"] >= 0 else _MB_RED),
            (_pc(d["ccbrk"]), brk_bg(d["ccbrk"])),
            (_m0(d["brkgap"]), _MB_GREEN if d["brkgap"] >= 0 else _MB_RED),
            (_pc(d["cspitm"]), pal["body"]),
            (_pc(d["leappct"]), pal["body"]),
            (_m0(d["leapgap"]), _MB_GREEN if d["leapgap"] >= 0 else _MB_RED),
        ]
        tds = "".join(f"<td style='border:1px solid {pal['bd']};padding:8px 11px;text-align:center;"
                      f"background:{bg};color:{'#111' if bg != pal['body'] else pal['txt']};"
                      f"font-weight:700;font-size:14px;white-space:nowrap;'>{v}</td>" for v, bg in cells)
        return f"<tr>{lab}{tds}</tr>"

    body = rowline("IRA", r["ira"]) + rowline("LLC", r["llc"]) + rowline("Total", r["total"])
    return (f"<table style='border-collapse:collapse;width:100%;margin-top:8px;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def board_data() -> dict | None:
    """Live Monitor-Board payload (r + market context), shared by the Command Center
    and the Cockpit view so both read the exact same numbers."""
    df = _tradelog_full()
    if df.empty:
        return None
    ext = _mb_externals()
    mkt = _mb_market()
    vix = mkt.get("vix") or ext.get("vix") or 16.57
    vc = mkt.get("vix_chg")
    vix_chg = vc if vc is not None else (ext.get("vix_chg") or 0.0)
    trend = mkt.get("trend") or ext.get("trend") or "Uptrend"
    r = engine.monitor_board(df, ext.get("ath_ira", 0), ext.get("ath_llc", 0), vix, vix_chg, trend)
    return {"r": r, "vix": vix, "vix_chg": vix_chg, "trend": trend, "live": bool(mkt.get("vix"))}


def _monitor_board(c: dict) -> None:
    data = board_data()
    if data is None:
        st.warning("Couldn't load the TradeLog tab.")
        return
    r, vix, vix_chg, trend, mkt = (data["r"], data["vix"], data["vix_chg"],
                                   data["trend"], {"vix": data["live"] or None})
    pal = _mb_pal(c)

    chg_bg = _MB_GREEN if vix_chg <= 0 else _MB_RED
    hdr = (
        f"<div style='display:flex;border-radius:8px;overflow:hidden;margin-bottom:6px;'>"
        f"<div style='flex:2;background:{_MB_DARK};color:#fff;font-weight:800;font-size:15px;"
        f"padding:9px;text-align:center;'>VIX : {vix:.2f}</div>"
        f"<div style='flex:1;background:{chg_bg};color:#00152d;font-weight:800;font-size:14px;"
        f"padding:9px;text-align:center;'>{vix_chg * 100:+.1f}%</div></div>"
        f"<div style='background:{_MB_DARK};color:{_MB_GOLD};font-weight:700;padding:7px;"
        f"text-align:center;border-radius:8px;margin-bottom:10px;'>"
        f"VIX Allocation : {_pc(r['alloc'])}   ·   {trend}</div>")

    board = (
        f"<div style='display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start;'>"
        f"<div style='flex:1;min-width:330px;'>{_money_matrix(r, pal)}</div>"
        f"<div style='flex:1.35;min-width:420px;'>{hdr}"
        f"<div style='margin-bottom:10px;'>{_gaps_table(r, pal)}</div>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start;'>"
        f"<div style='flex:1.4;min-width:250px;'>{_vix_table(r, pal)}</div>"
        f"<div style='flex:1;min-width:170px;'>{_premium_table(r, pal)}</div></div>"
        f"</div></div>")
    st.markdown(board, unsafe_allow_html=True)

    src = "live Yahoo" if mkt.get("vix") else "sheet"
    st.caption(f"All figures computed live from the TradeLog · ATH ratchet + VIX/trend "
               f"from {src}. Mirrors the MonitorBoard sheet cell-for-cell.")


def _sign(c: dict, v):
    try:
        return f"color:{c['pos']}" if float(v) >= 0 else f"color:{c['neg']}"
    except (TypeError, ValueError):
        return ""


_PL_MONEY = {"P/L", "Cash Release"}


def _pl_html(c: dict, df: pd.DataFrame) -> str:
    """Big-font HTML rendering of a P/L frame ($ formatted, P/L colored green/red).
    Replaces st.dataframe so the font is readable — the columns have plenty of room."""
    cols = list(df.columns)
    head = "".join(
        f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:11px 16px;font-weight:800;font-size:14.5px;"
        f"white-space:nowrap;text-align:{'left' if i == 0 else 'right'};'>{col}</th>"
        for i, col in enumerate(cols))
    body = ""
    for _, r in df.iterrows():
        tds = ""
        for i, col in enumerate(cols):
            v = r[col]
            if col in _PL_MONEY:
                try:
                    disp = f"${float(v):,.0f}"
                except (TypeError, ValueError):
                    disp = str(v)
            elif col == "Trades":
                try:
                    disp = f"{int(v):,}"
                except (TypeError, ValueError):
                    disp = str(v)
            else:
                disp = str(v)
            base = (f"border:1px solid {c['border']};padding:10px 16px;color:{c['text']};"
                    f"white-space:nowrap;font-size:15px;text-align:{'left' if i == 0 else 'right'};")
            if col == "P/L":
                base += _sign(c, v) + ";font-weight:800;"
            elif i == 0:
                base += "font-weight:700;"
            tds += f"<td style='{base}'>{disp}</td>"
        body += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:640px;border:1px solid {c['border']};border-radius:9px;'>"
            f"<table style='border-collapse:collapse;font-size:15px;width:max-content;min-width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _pl_stats(c: dict, yt: pd.DataFrame) -> str:
    pl, cr, tr = yt["P/L"].sum(), yt["Cash Release"].sum(), int(yt["Trades"].sum())

    def tile(lbl, val, col):
        return (f"<div style='flex:1;min-width:118px;background:{c['panel']};border:1px solid {c['border']};"
                f"border-radius:12px;padding:13px 15px;'>"
                f"<div style='font-size:10.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;"
                f"color:{c['muted']};'>{lbl}</div>"
                f"<div style='margin-top:5px;font-size:19px;font-weight:800;color:{col};"
                f"white-space:nowrap;font-variant-numeric:tabular-nums;'>{val}</div></div>")
    return (f"<div style='display:flex;gap:11px;flex-wrap:wrap;margin:4px 0 12px;'>"
            f"{tile('Realized P/L', f'${pl:,.0f}', c['pos'] if pl >= 0 else c['neg'])}"
            f"{tile('Cash Released', f'${cr:,.0f}', c['gold'])}"
            f"{tile('Trades', f'{tr:,}', c['blue'])}</div>")


def _pl_bars(c: dict, yt: pd.DataFrame) -> str:
    if yt.empty:
        return ""
    recs = list(reversed(yt.to_dict("records")))            # chronological, Jan→latest
    mx = max((abs(float(r["P/L"])) for r in recs), default=1) or 1
    rows = ""
    for r in recs:
        pl = float(r["P/L"])
        w = abs(pl) / mx * 100
        col = c["pos"] if pl >= 0 else c["neg"]
        rows += (f"<div style='display:flex;align-items:center;gap:10px;margin:6px 0;'>"
                 f"<span style='width:34px;font-size:12.5px;color:{c['mid']};font-weight:700;'>{r['Month']}</span>"
                 f"<div style='flex:1;height:15px;background:{c['raised']};border-radius:5px;overflow:hidden;'>"
                 f"<div style='width:{w:.1f}%;height:100%;background:{col};border-radius:5px;'></div></div>"
                 f"<span style='width:88px;text-align:right;font-size:13px;font-weight:800;color:{col};"
                 f"font-variant-numeric:tabular-nums;'>${pl:,.0f}</span></div>")
    return (f"<div style='background:{c['panel']};border:1px solid {c['border']};border-radius:12px;"
            f"padding:13px 15px;margin-bottom:13px;'>"
            f"<div style='font-size:10.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;"
            f"color:{c['muted']};margin-bottom:6px;'>Monthly P/L</div>{rows}</div>")


def _pl_section(c: dict, icon: str, title: str, sub: str, rollup: pd.DataFrame, key: str) -> None:
    st.markdown(f"##### {icon} {title}")
    st.caption(sub)
    if rollup.empty:
        st.info("No dated rows found.")
        return

    totals = engine.monthly_totals(rollup)
    years = sorted(rollup["Year"].unique(), reverse=True)
    yr = st.selectbox("Year", years, key=f"{key}_yr")
    yt = totals[totals["Year"] == yr].drop(columns="Year").reset_index(drop=True)

    st.markdown(_pl_stats(c, yt) + _pl_bars(c, yt), unsafe_allow_html=True)
    st.markdown(_pl_html(c, yt), unsafe_allow_html=True)

    with st.expander("Drill into a month (account → stock)"):
        months = yt["Month"].tolist()
        if months:
            m = st.selectbox("Month", months, key=f"{key}_mo")
            det = engine.detail_for(rollup, yr, m)
            st.markdown(_pl_html(c, det), unsafe_allow_html=True)


@st.cache_data(ttl=120, show_spinner=False)
def _tradelog_full() -> pd.DataFrame:
    df = gsheet.tradelog()
    if df.empty:
        return df
    df.columns = [str(x).strip() for x in df.columns]
    df["Status"] = df.get("Status", "").astype(str).str.strip()
    df = df[df["Stock"].astype(str).str.strip().ne("")]

    def _gtc(r):
        if (str(r.get("Opt Typ", "")).strip().upper() == "PUT"
                and str(r.get("Status", "")).strip().lower().startswith("open")):
            t = gtc_refresh.gtc_target(r.get("Init Prem"), gtc_refresh._num(r.get("DTE")))
            return f"${t:.2f}" if t is not None else "—"
        return "—"
    df["GTC"] = df.apply(_gtc, axis=1)
    return df


_OPT_STYLE = {
    "Put":  "background-color:rgba(22,163,74,.32);color:#c9f7d6;font-weight:700;text-align:center;",
    "Call": "background-color:rgba(234,179,8,.32);color:#fff0bf;font-weight:700;text-align:center;",
    "LEAP": "background-color:rgba(59,130,246,.30);color:#cfe4ff;font-weight:700;text-align:center;",
    "HOLD": "background-color:rgba(140,105,20,.40);color:#ffd479;font-weight:700;text-align:center;",
}
_POS, _NEG = "color:#43c463;font-weight:700;", "color:#f2555a;font-weight:700;"
_CAP_POS = "background-color:rgba(67,196,99,.22);color:#c9f7d6;font-weight:600;"
_CAP_NEG = "background-color:rgba(242,85,90,.22);color:#ffc9cb;font-weight:600;"


def _n(v):
    try:
        s = str(v).replace("$", "").replace(",", "").replace("%", "").strip()
        return float(s) if s not in ("", "—", "None", "nan") else None
    except (TypeError, ValueError):
        return None


def _f2(v):
    try:
        return f"{float(str(v).replace(',', '')):.2f}"
    except (TypeError, ValueError):
        return "—" if str(v).strip().lower() in ("", "nan", "none") else v


def _f0(v):
    try:
        return f"{float(str(v).replace(',', '')):.0f}"
    except (TypeError, ValueError):
        return "—" if str(v).strip().lower() in ("", "nan", "none") else v


_CASH_ROW = "background-color:rgba(58,44,10,.60);color:#ffd479;font-weight:700;"

# Grey/light = the Google-Sheet's exact colors.
_L_OPT = {
    "Put":  "background-color:#2f7e25;color:#fff;font-weight:700;text-align:center;",
    "Call": "background-color:#d9a400;color:#1a1a1a;font-weight:700;text-align:center;",
    "LEAP": "background-color:#3b78d8;color:#fff;font-weight:700;text-align:center;",
    "HOLD": "background-color:#241a00;color:#ffd066;font-weight:700;text-align:center;",
}
_L_POS, _L_NEG = "color:#188038;font-weight:700;", "color:#c5221f;font-weight:700;"
_L_CAP_POS = "background-color:#b7e1cd;color:#0d652d;font-weight:600;"
_L_CAP_NEG = "background-color:#f4c7c3;color:#a50e0e;font-weight:600;"
_L_PL_NEG = "background-color:#f4c7c3;color:#a50e0e;font-weight:700;"
_L_CASH = "background-color:#241a00;color:#ffd066;font-weight:700;"
_L_ROW = "background-color:#e2e5e7;color:#16212c;"   # light data-row bg (sheet look)


def _is_light(bg: str) -> bool:
    h = str(bg).lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def _tl_styler(vv, cols, light=False):
    OPT = _L_OPT if light else _OPT_STYLE
    POS = _L_POS if light else _POS
    NEG = _L_NEG if light else _NEG
    CAP_POS = _L_CAP_POS if light else _CAP_POS
    CAP_NEG = _L_CAP_NEG if light else _CAP_NEG
    PL_NEG = _L_PL_NEG if light else _NEG            # light sheet reds the P/L cell; dark reds the text
    CASH = _L_CASH if light else _CASH_ROW

    base = _L_ROW if light else ""      # paint every cell light on Grey so it reads like the sheet

    def _rows(row):
        if str(row.get("Stock", "")).strip().upper() in ("CASH", "VAULT"):
            return [CASH] * len(cols)                 # whole cash row highlighted gold
        s = [base] * len(cols)
        cp, k, ot = _n(row.get("Current Price")), _n(row.get("Strike Price")), str(row.get("Opt Typ", "")).strip().upper()
        if "Current Price" in cols and cp is not None and k is not None and ot in ("PUT", "CALL"):
            otm = cp > k if ot == "PUT" else cp < k     # short option safe (OTM) = green
            s[cols.index("Current Price")] = base + (POS if otm else NEG)
        return s

    st = vv.style.apply(_rows, axis=1) \
        .map(lambda v: OPT.get(str(v).strip(), ""), subset=[x for x in ["Opt Typ"] if x in cols]) \
        .map(lambda v: (PL_NEG if (_n(v) or 0) < 0 else ""), subset=[x for x in ["Profit Loss"] if x in cols]) \
        .map(lambda v: (POS if (_n(v) or 0) >= 50 else ""), subset=[x for x in ["Return"] if x in cols]) \
        .map(lambda v: (CAP_NEG if (_n(v) or 0) < 0 else CAP_POS) if _n(v) is not None else "",
             subset=[x for x in ["% Captured"] if x in cols])

    fmt = {col: _f2 for col in ("Current Price", "Strike Price", "Init Prem", "Current Prem") if col in cols}
    if "Qty" in cols:
        fmt["Qty"] = _f0
    return st.format(fmt, na_rep="—")


_RIGHT = {"Current Price", "Strike Price", "Init Prem", "Return", "Qty", "Profit Loss",
          "Cash Reserve", "Cash Release", "Current Prem", "GTC", "% Captured", "DTE"}
_F2SET = {"Current Price", "Strike Price", "Init Prem", "Current Prem"}


def _tl_palette(c, light):
    if light:
        return dict(row="#ffffff", alt="#eef1f3", txt="#16212c", bd="#c7ced3",
                    hbg="#1c2e33", htxt="#ffffff",
                    opt={"Put": ("transparent", "#347fd1"), "Call": ("transparent", "#b8860b"),
                         "LEAP": ("transparent", "#6b3fa0"), "HOLD": ("transparent", "#8a6800")},
                    pos="#188038", neg="#c5221f",
                    cap_pos=("#b7e1cd", "#0d652d"), cap_neg=("#f4c7c3", "#a50e0e"),
                    pl_neg=("#f4c7c3", "#a50e0e"), cash=("#241a00", "#ffd066"))
    return dict(row=c["panel"], alt=c["bg"], txt=c["text"], bd=c["border"],
                hbg=c["raised"], htxt=c["text"],
                opt={"Put": ("transparent", c["blue"]), "Call": ("transparent", c["gold"]),
                     "LEAP": ("transparent", "#a78bfa"), "HOLD": ("transparent", c["amber"])},
                pos="#43c463", neg="#f2555a",
                cap_pos=("rgba(67,196,99,.22)", "#c9f7d6"), cap_neg=("rgba(242,85,90,.22)", "#ffc9cb"),
                pl_neg=("transparent", "#f2555a"), cash=("rgba(58,44,10,.6)", "#ffd479"))


_CHIP_COLORS = ["#2f6fb0", "#7a4fb0", "#2f8f6b", "#b06a2f", "#8a2f4f",
                "#4f6a2f", "#2f7f8a", "#6a2f8a", "#a03a3a", "#3a5aa0"]


def _logo_cell(tk: str, url: str) -> str:
    """A ticker logo that never leaves a blank cell: a colored initials badge with
    the real logo layered on top (background-image). If FMP hotlink-blocks or the
    logo is missing, the layer is transparent and the initials show through."""
    tk = (tk or "").strip().upper()
    if tk in ("CASH", "VAULT"):
        return f"<img src='{url}' style='width:22px;height:22px;vertical-align:middle;'>" if url else ""
    if not tk:
        return ""
    col = _CHIP_COLORS[sum(ord(x) for x in tk) % len(_CHIP_COLORS)]
    logo = (f"<span style='position:absolute;inset:0;border-radius:5px;"
            f"background:center/contain no-repeat url({url});'></span>") if url else ""
    return (f"<span style='position:relative;display:inline-block;width:24px;height:24px;vertical-align:middle;'>"
            f"<span style='position:absolute;inset:0;display:flex;align-items:center;justify-content:center;"
            f"background:{col};border-radius:5px;color:#fff;font-size:8.5px;font-weight:800;'>{tk[:2]}</span>"
            f"{logo}</span>")


def _tl_html(vv, cols, c, light) -> str:
    p = _tl_palette(c, light)
    head = "".join(
        f"<th style='position:sticky;top:0;z-index:2;background:{p['hbg']};color:{p['htxt']};"
        f"border:1px solid {p['bd']};padding:7px 9px;text-align:{'right' if col in _RIGHT else 'left'};"
        f"font-weight:700;white-space:nowrap;'>{'' if col == 'Logo' else col}</th>" for col in cols)
    body = ""
    for _, row in vv.iterrows():
        cash = str(row.get("Stock", "")).strip().upper() in ("CASH", "VAULT")
        tds = ""
        for col in cols:
            v = row.get(col)
            v = "" if v is None else str(v)
            align = "right" if col in _RIGHT else "left"
            base = f"border:1px solid {p['bd']};padding:5px 9px;white-space:nowrap;text-align:{align};color:{p['txt']};"
            if col == "Logo":
                cell = _logo_cell(str(row.get("Stock", "")), v)
                tds += f"<td style='border:1px solid {p['bd']};padding:4px 12px;text-align:center;'>{cell}</td>"
                continue
            disp = _f2(v) if col in _F2SET else (_f0(v) if col == "Qty" else v)
            if disp in ("", "None", "nan"):
                disp = "—"
            if cash:
                bg, tc = p["cash"]
                tds += f"<td style='{base}background:{bg};color:{tc};font-weight:700;'>{disp}</td>"
                continue
            style = base
            if col == "Opt Typ" and v.strip() in p["opt"]:
                bg, tc = p["opt"][v.strip()]
                style = (f"border:1px solid {p['bd']};padding:5px 9px;text-align:center;"
                         f"background:{bg};color:{tc};font-weight:700;")
            elif col == "Current Price":
                cp, k, ot = _n(v), _n(row.get("Strike Price")), str(row.get("Opt Typ", "")).strip().upper()
                if cp is not None and k is not None and ot in ("PUT", "CALL"):
                    otm = cp > k if ot == "PUT" else cp < k
                    style += f"color:{p['pos'] if otm else p['neg']};font-weight:700;"
            elif col == "Profit Loss" and (_n(v) or 0) < 0:
                bg, tc = p["pl_neg"]
                style += f"background:{bg};color:{tc};font-weight:700;"
            elif col == "Return" and (_n(v) or 0) >= 50:
                style += f"color:{p['pos']};font-weight:700;"
            elif col == "% Captured" and _n(v) is not None:
                style += f"color:{p['pos'] if (_n(v) or 0) >= 0 else p['neg']};font-weight:700;"
            tds += f"<td style='{style}'>{disp}</td>"
        body += f"<tr style='background:{p['row']};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:600px;border:1px solid {p['bd']};border-radius:8px;'>"
            f"<table style='border-collapse:collapse;font-size:14.5px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _trade_log(c: dict) -> None:
    df = _tradelog_full()
    if df.empty:
        st.warning("Couldn't load the TradeLog tab.")
        return
    open_mask = df["Status"].str.lower().str.startswith("open")

    # Trade Log shows OPEN orders — the daily working set (Expiry list stays short).
    base = df[open_mask]

    def _uniq(col):
        return sorted(base[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist()) \
            if col in base.columns else []

    a1, a2, a3 = st.columns([1, 1, 2.6])
    with a1:
        acct = st.selectbox("Account", ["All accounts"] + _uniq("Account"), key="cc_tl_acct")
    with a2:
        otf = st.selectbox("Opt Type", ["All types"] + _uniq("Opt Typ"), key="cc_tl_opt")
    with a3:
        exp_vals = sorted(_uniq("Exp Date"), key=lambda x: pd.to_datetime(x, errors="coerce"))
        expf = st.multiselect("Expiry", exp_vals, key="cc_tl_exp",
                              placeholder="All expiries")

    view = base

    def _cash(d):   # CASH / VAULT rows — always kept through Opt Type / Expiry filters
        return d["Stock"].astype(str).str.upper().isin(["CASH", "VAULT"])

    if acct != "All accounts":
        view = view[view["Account"].astype(str).str.strip() == acct]
    if otf != "All types":
        view = view[_cash(view) | (view["Opt Typ"].astype(str).str.strip() == otf)]
    if expf:
        view = view[_cash(view) | (view["Exp Date"].astype(str).str.strip().isin(expf))]

    _MONEY = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/1f4b0.png"  # 💰

    def _logo(t):
        tu = t.upper()
        if tu in ("CASH", "VAULT"):
            return _MONEY
        return f"https://financialmodelingprep.com/image-stock/{t}.png" if t else ""

    view = view.copy()
    view["Logo"] = view["Stock"].astype(str).str.strip().apply(_logo)
    cols = ["Logo"] + [x for x in _TL_COLS if x in view.columns]
    vv = view[cols].reset_index(drop=True)
    st.markdown(_tl_html(vv, cols, c, _is_light(c.get("bg", ""))), unsafe_allow_html=True)

    b1, b2 = st.columns([3, 1])
    with b1:
        st.caption(f"**{len(vv)}** rows · **{int(open_mask.sum())}** open of {len(df)} total")
    with b2:
        st.download_button("Download CSV", vv.to_csv(index=False).encode(),
                           "trade_log.csv", "text/csv", use_container_width=True)


def render(c: dict) -> None:
    """Portfolio Center — the Monitor Board (Trade Position and P/L are their own pages)."""
    _monitor_board(c)


def render_trade_log(c: dict) -> None:
    """Trade Position page."""
    _trade_log(c)


def render_pl(c: dict) -> None:
    """P/L page — Close Date vs Open Date drill-downs."""
    df = _tradelog()
    if df.empty:
        st.warning("Couldn't load the TradeLog tab.")
        return
    col1, col2 = st.columns(2)
    with col1:
        _pl_section(c, "✅", "P/L by Close Date", "Year → Month → Account → Stock (realized).",
                    engine.pl_rollup(df, "Close Date"), "cc_close")
    with col2:
        _pl_section(c, "📆", "P/L by Open Date", "Year → Month → Account → Stock (by entry).",
                    engine.pl_rollup(df, "Open Date"), "cc_open")
