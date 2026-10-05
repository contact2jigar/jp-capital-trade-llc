"""CSP Scanner — find valid CSP entries across the wheel universe.

Two-pillar model (mirrors the LEAP Scanner, but CSP has THREE setups):

Pillar 1 — Setup ✓ (any one):
  • Reversal   — RSI(14)<40 + lower-BB touch + green candle   (= LEAP Path A)
  • Deep Value — RSI(14)<35 + whole candle below the band     (= LEAP Path B)
  • IV Drop    — red-day, two-tier (matches WatchList.gs):
        🟢 = Chg% ≤ −(IV÷15)   ·   🟠 = −(IV/15) < Chg% ≤ −(IV/20)

Pillar 2 — Quality ✓ (light scope): RSI(14) < 64 AND not near the high band.
Earnings   — the actual date; ⛔ + red when inside 30 days (the CSP veto).
Actionable = Setup ✓ AND Quality ✓ AND no earnings veto.

For each Setup ✓ name we price a put at the chosen expiry (default the first
Friday ≥21 DTE, adjustable ±1 week): the SAFEST strike whose AOR clears the
floor, with its Black-Scholes delta. Setup/RSI/BB from Yahoo; IV + Position from
the sheet; VIX sets the AOR-floor context. Click a row → Ticker Detail.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from logic import csp_pricing
from logic import csp_setup
from logic import hm_signal as hm
from logic import leap_setup
from services import gsheet, option_chain, screeners, yahoo
from ui import state
from ui.fundamentals_cache import fund_row as _fund_row

_DEFAULT_TYPES = ["01-Growth", "02-Alternate", "03-Speculation"]
_VETO_DTE = 30

_SETUP_STYLE = "background-color:rgba(22,163,74,.30);color:#86efac;font-weight:800;text-align:center;"
_QUALITY_STYLE = "background-color:rgba(96,165,250,.20);color:#93c5fd;font-weight:800;text-align:center;"
_VETO_STYLE = "background-color:rgba(239,68,68,.28);color:#fca5a5;font-weight:800;"
_STYLES = {
    "Below Band": "background-color:rgba(168,85,247,.24);color:#d8b4fe;font-weight:800;",
    "At Lower":   "background-color:rgba(96,165,250,.18);color:#93c5fd;font-weight:700;",
    "Mid Band":   "color:#cbd5e1;",
    "BUY":         "background-color:rgba(250,204,21,.20);color:#fde68a;font-weight:700;text-align:center;",
    "STRONG GOLD": "background-color:rgba(234,88,12,.24);color:#fdba74;font-weight:800;text-align:center;",
    "SELL":        "background-color:rgba(239,68,68,.18);color:#fca5a5;text-align:center;",
    "▲": "color:#86efac;font-weight:700;text-align:center;",
    "▼": "color:#fca5a5;font-weight:700;text-align:center;",
}
# Column order (Jigar's layout): identity → pricing → signal → context.
# Price(current) → Strike → Cushion(% below current) → 3mo↓(% below 3-month high).
_COLS = ["Ticker", "Type", "Setup", "Price", "Strike", "Cushion", "3mo ↓", "Δ",
         "Prem", "AOR", "IV", "IV/RV", "RSI", "BB", "MACD", "Chg%", "% off High",
         "Quality", "HM", "Earnings", "Pos", "Financials", "Cash", "Industry", "Note"]


@st.cache_data(ttl=300, show_spinner=False)
def _sheet_maps() -> tuple[dict, dict]:
    """{ticker: IV raw} and {ticker: '✓' if a position is held} from the WatchList."""
    df = gsheet.watchlist()
    iv, pos = {}, {}
    if not df.empty and "Stock" in df.columns:
        for _, r in df.iterrows():
            s = str(r.get("Stock", "")).strip().upper()
            if not s or s == "NAN":
                continue
            _iv = str(r.get("IV", "")).strip()
            iv[s] = "" if _iv.lower() in ("", "nan", "none") else _iv
            cp = r.get("Current Position")
            held = cp is not None and str(cp).strip() and str(cp).strip().lower() != "nan"
            pos[s] = "✓" if held else ""
    return iv, pos


@st.cache_data(ttl=300, show_spinner=False)
def _current_vix() -> float | None:
    df = yahoo.get_history("^VIX", period="1mo", interval="1d", auto_adjust=False)
    if df.empty or "Close" not in df.columns:
        return None
    s = df["Close"].dropna()
    return float(s.iloc[-1]) if len(s) else None


@st.cache_data(ttl=1800, show_spinner=False)
def _regime() -> str:
    """Market regime = SPY vs its 100-day SMA (the framework's Up/Down 2-state)."""
    df = yahoo.get_history("SPY", period="1y", interval="1d", auto_adjust=False)
    if df.empty or "Close" not in df.columns:
        return "—"
    s = df["Close"].dropna()
    if len(s) < 100:
        return "—"
    return "Uptrend" if float(s.iloc[-1]) >= float(s.rolling(100).mean().iloc[-1]) else "Downtrend"


@st.cache_data(ttl=300, show_spinner="Fetching universe…")
def _screen_source(src: str, n: int) -> list:
    """Cached ticker universe for a non-WatchList source (5 min) — avoids re-hitting the
    screener on every rerun (FinViz especially is multi-page).

    FinViz range variants ("FinViz 1-300", "FinViz 301-600", …) return that market-cap
    rank slice of the screen — explicit pages the user scans one at a time, each slice
    small enough to stay under Yahoo's rate limit downstream."""
    if src == "Yahoo Day Losers":
        return screeners.day_losers(n)
    if src.startswith("FinViz"):
        import re
        m = re.search(r"(\d+)\s*-\s*(\d+)", src)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return screeners.finviz_screen(count=hi)[lo - 1:hi]
        return screeners.finviz_screen(n)        # plain "FinViz Quality" (top-n), if used
    return screeners.most_active(n)


@st.cache_data(ttl=300, show_spinner="Fetching universe…")
def _finviz_rows(src: str) -> list:
    """(ticker, sector) for a FinViz range — sector comes free from the scrape, so the
    Stage-1 sector filter costs zero Yahoo calls."""
    import re
    m = re.search(r"(\d+)\s*-\s*(\d+)", src)
    if not m:
        return [(t, "") for t in screeners.finviz_screen(300)]
    lo, hi = int(m.group(1)), int(m.group(2))
    return screeners.finviz_screen_rows(count=hi)[lo - 1:hi]


def _trend_15y(hist) -> str:
    """Ryan's Principle 1 — uptrend over the past ~1.5 years, from the SAME 2y history
    (no extra fetch). 50-week SMA (≈250 trading days) + its 3-month slope:
      ▲ Up    price above the MA AND the MA rising      (ALAB, CLS)
      ▼ Down  price below the MA AND the MA falling      (LULU — the falling knife)
      ◆ Mixed one of the two true
      new     too little history to judge 1.5 years"""
    if hist is None or hist.empty:
        return "—"
    d = hist.copy()
    d.columns = [c.lower() for c in d.columns]
    if "close" not in d:
        return "—"
    close = d["close"].dropna()
    if len(close) < 315:                       # need 250 (MA) + 63 (3mo slope) clean bars
        return "new"
    sma = close.rolling(250).mean()
    s_now, s_old = sma.iloc[-1], sma.iloc[-63]
    if pd.isna(s_now) or pd.isna(s_old):
        return "—"
    above = float(close.iloc[-1]) > float(s_now)
    rising = float(s_now) > float(s_old)
    if above and rising:
        return "▲ Up"
    if (not above) and (not rising):
        return "▼ Down"
    return "◆ Mixed"


_S1COLS = ["Ticker", "Sector", "Tradable", "Price", "Trend", "Chg%", "Off High", "RSI", "BB"]


def _stage1_scan(rows: list, target_iso: str) -> pd.DataFrame:
    """Stage 1 — the cheap narrowing pass. Per (ticker, sector): tradability (weekly
    options via the expiry LIST only) + RSI / BB / Chg% + 1.5yr Trend + % off High, all
    from one 2y history pull. No chain pricing, no fundamentals — that heavy quality work
    waits for the 💎 Quality step on the (filtered) shortlist."""
    tmap = {"weekly": "✓ weekly", "monthly": "monthly", "none": "no-opt"}
    out = []
    prog = st.progress(0, text="Stage 1 — tradability + technicals…")
    n = len(rows)
    for i, (t, sector) in enumerate(rows):
        prog.progress(i / max(n, 1), text=f"[{i + 1}/{n}] {t}")
        status = option_chain.expiry_status(t, target_iso, _WEEKLY_TOL_DAYS)
        hist = yahoo.get_history(t, period="2y", interval="1d")
        lr = leap_setup.evaluate(hist) if (not hist.empty and len(hist) >= 30) else {}
        rsi = lr.get("rsi14")
        oh = lr.get("off_high_pct")
        out.append({
            "Ticker": t, "Sector": sector or "—", "Tradable": tmap.get(status, status),
            "Price": round(lr["price"], 2) if lr.get("price") is not None else None,
            "Trend": _trend_15y(hist),
            "Chg%": round(lr["chg_pct"], 2) if lr.get("chg_pct") is not None else None,
            "Off High": round(oh, 1) if oh is not None else None,
            "RSI": f"{rsi:.0f}" if rsi is not None else "—",
            "BB": lr.get("bb_pos", "—"),
        })
    prog.empty()
    return pd.DataFrame(out, columns=_S1COLS)


_S1_DISPLAY = ["Ticker", "Sector", "Price", "Trend", "Chg%", "Off High",
               "RSI", "BB", "P/E", "Financials", "Cash"]


def _stage1_dataframe(view: pd.DataFrame, c: dict) -> None:
    """Native sortable grid — click ANY column header to sort. Numeric columns stay
    numeric so the header-sort is numeric (not lexical); colors come from a pandas
    Styler (Trend/Chg%/RSI/BB/P/E/Cash), formatting from Styler.format. Trend + Off
    High come from Stage 1; P/E · Financials · Cash fill in on 💎 Quality detail."""
    df = view.reindex(columns=_S1_DISPLAY).copy()
    for col in ["Price", "Chg%", "Off High", "RSI", "P/E", "Cash"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["Ticker", "Sector", "Trend", "BB", "Financials"]:
        df[col] = df[col].astype("object").where(df[col].notna(), "—")

    def _c_trend(v):
        s = str(v)
        tc = (c["pos"] if s.startswith("▲") else c["neg"] if s.startswith("▼")
              else c["amber"] if s.startswith("◆") else c["muted"])
        return f"color:{tc};font-weight:700"

    def _c_chg(v):
        return "" if pd.isna(v) else f"color:{c['pos'] if v > 0 else c['neg']};font-weight:700"

    def _c_rsi(v):
        if pd.isna(v):
            return ""
        if v > 64:
            return f"color:{c['neg']};font-weight:700"
        if v <= 45:
            return f"color:{c['pos']};font-weight:700"
        return ""

    def _c_bb(v):
        low = str(v).lower()
        if "lower" in low or "below" in low:
            return f"color:{c['pos']}"
        if "upper" in low or "above" in low:
            return f"color:{c['neg']}"
        return ""

    def _c_pe(v):
        return f"color:{c['amber']};font-weight:700" if (not pd.isna(v) and (v <= 0 or v > 100)) else ""

    def _c_cash(v):
        return "" if pd.isna(v) else f"color:{c['pos'] if v >= 0 else c['neg']};font-weight:700"

    sty = df.style
    _apply = sty.map if hasattr(sty, "map") else sty.applymap   # pandas ≥2.1 renamed applymap→map
    _apply(lambda v: "font-weight:800", subset=["Ticker"])
    _apply(_c_trend, subset=["Trend"])
    _apply(_c_chg, subset=["Chg%"])
    _apply(_c_rsi, subset=["RSI"])
    _apply(_c_bb, subset=["BB"])
    _apply(_c_pe, subset=["P/E"])
    _apply(_c_cash, subset=["Cash"])
    sty = sty.format({
        "Price": lambda v: "—" if pd.isna(v) else f"${v:,.2f}",
        "Chg%": lambda v: "—" if pd.isna(v) else f"{v:+.1f}%",
        "Off High": lambda v: "—" if pd.isna(v) else f"{v:.0f}%",
        "RSI": lambda v: "—" if pd.isna(v) else f"{v:.0f}",
        "P/E": lambda v: "—" if pd.isna(v) else f"{v:.1f}",
        "Cash": lambda v: "—" if pd.isna(v) else (f"+${v:.1f}B" if v >= 0 else f"−${abs(v):.1f}B"),
    })
    st.dataframe(sty, use_container_width=True, hide_index=True, height=600)


def _safe_fund(t: str, key: str):
    """Cached fundamental field for a ticker (P/E · Financials · Cash), or None."""
    try:
        return _fund_row(t).get(key)
    except Exception:
        return None


def _render_stage1(c: dict, s1: pd.DataFrame, meta: dict) -> None:
    trad = s1["Tradable"].astype(str)
    n_total, n_weekly = len(s1), int(trad.str.contains("weekly").sum())
    n_monthly, n_noopt = int((trad == "monthly").sum()), int((trad == "no-opt").sum())

    # Non-tradable is dropped here (that was the whole point of the narrow); the result
    # filters are RSI · Change · Price · Uptrend (Ryan #1).
    g1, g2, g3, g4 = st.columns([1.1, 1.2, 1.9, 1.1])
    with g1:
        max_rsi = st.number_input("Max RSI", 0, 100, 100, step=5, key="s1_rsi")
    with g2:
        chg = st.selectbox("Change", ["Any", "Down today", "Down > 2%", "Up today"], key="s1_chg")
    with g3:
        pa, pb = st.columns(2)
        min_px = pa.number_input("Min $", 0, 100000, 0, step=5, key="s1_pmin")
        max_px = pb.number_input("Max $", 0, 100000, 0, step=5, key="s1_pmax", help="0 = no max")
    with g4:
        st.write("")
        uptrend = st.checkbox("Uptrend only", value=False, key="s1_up",
                              help="Keep only ▲ Up — Ryan #1: in an uptrend over the past ~1.5 years "
                                   "(never wheel a falling knife).")

    view = s1[s1["Tradable"].astype(str).str.contains("weekly")].copy()   # tradable only
    if uptrend and "Trend" in view:
        view = view[view["Trend"].astype(str) == "▲ Up"]
    if max_rsi < 100:
        view = view[pd.to_numeric(view["RSI"], errors="coerce").fillna(999) <= max_rsi]
    _chg = pd.to_numeric(view["Chg%"], errors="coerce").fillna(0)
    if chg == "Down today":
        view = view[_chg < 0]
    elif chg == "Down > 2%":
        view = view[_chg <= -2]
    elif chg == "Up today":
        view = view[_chg > 0]
    if min_px > 0:
        view = view[pd.to_numeric(view["Price"], errors="coerce").fillna(-1) >= min_px]
    if max_px > 0:
        view = view[pd.to_numeric(view["Price"], errors="coerce").fillna(1e9) <= max_px]

    # 💎 Quality — the heavy fundamentals pull (P/E · Financials · Cash), run ONLY on the
    # shortlist that's left after the filters above. Cached 6h per ticker, so it's a
    # one-time cost; re-filtering just re-maps from cache.
    q1, _q2 = st.columns([1.6, 4.0])
    with q1:
        load_q = st.button(f"💎 Quality detail  ({len(view)})", type="primary",
                           use_container_width=True, disabled=view.empty, key="s1_loadq",
                           help="Pull P/E · Financials · Cash for the filtered names "
                                "(Ryan #2 — business quality).")
    if load_q:
        tickers = list(view["Ticker"])
        prog = st.progress(0, text="💎 Quality — fundamentals…")
        for i, t in enumerate(tickers):
            prog.progress(i / max(len(tickers), 1), text=f"[{i + 1}/{len(tickers)}] {t}")
            _fund_row(t)                                   # populate the 6h cache
        prog.empty()
        st.session_state["s1_qual_on"] = True
        st.rerun()
    if st.session_state.get("s1_qual_on") and not view.empty:
        view["P/E"] = view["Ticker"].map(lambda t: _safe_fund(t, "P/E"))
        view["Financials"] = view["Ticker"].map(lambda t: _safe_fund(t, "Financials"))
        view["Cash"] = view["Ticker"].map(lambda t: _safe_fund(t, "Cash"))

    chips = [(f"{n_total} scanned", c["muted"]), (f"{n_weekly} tradable", c["pos"]),
             (f"{n_monthly} monthly", c["amber"]) if n_monthly else None,
             (f"{n_noopt} no-opt", c["muted"]) if n_noopt else None,
             (f"{len(view)} shortlist", c["accent"])]
    row = "<div style='display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:8px 0;'>"
    for cell in chips:
        if not cell:
            continue
        lbl, col = cell
        row += (f"<span style='background:{col}18;color:{col};border:1px solid {col}44;"
                f"border-radius:6px;padding:2px 9px;font-size:12px;font-weight:700;'>{lbl}</span>")
    row += "</div>"
    st.markdown(row, unsafe_allow_html=True)

    st.caption("**Click any column header to sort.** Filter → hit **💎 Quality detail** to score "
               "the shortlist → **add the quality names to your WatchList sheet**. "
               "The Decision Desk works the WatchList.")
    _stage1_dataframe(view, c)


def _sublabel(c: dict, text: str) -> None:
    st.markdown(f"<div style='font-size:10px;letter-spacing:.09em;text-transform:uppercase;"
                f"color:{c['muted']};font-weight:700;margin:10px 0 2px;'>{text}</div>",
                unsafe_allow_html=True)


def _market_context(c: dict, vix, regime: str, floor: str) -> None:
    rc = c["pos"] if regime == "Uptrend" else c["neg"] if regime == "Downtrend" else c["muted"]
    tiles = [("VIX", f"{vix:.2f}" if vix is not None else "—", c["text"]),
             ("REGIME", regime, rc),
             ("AOR FLOOR", floor, c["amber"])]
    html = "<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:2px 0 10px;'>"
    for label, val, col in tiles:
        html += (f"<div style='background:{c['panel']};border:1px solid {c['border_soft']};"
                 f"border-radius:10px;padding:8px 13px;'>"
                 f"<div style='font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;"
                 f"color:{c['muted']}'>{label}</div>"
                 f"<div style='font-size:17px;font-weight:800;color:{col};margin-top:2px'>{val}</div></div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render(c: dict) -> None:
    vix = _current_vix()
    _, floor = csp_setup.vix_floor(vix)
    types, by_type = gsheet.watchlist_by_type()
    cat_map = {tk: t for t, ts in by_type.items() if t != "All" for tk in ts}
    pickable = [t for t in types if t != "All"]
    default = [t for t in _DEFAULT_TYPES if t in pickable] or pickable[:1]
    today = date.today()
    exps = csp_pricing.expiry_choices(today, 21)
    labels = {e: f"{e:%b %d} ({(e - today).days}d)" for e in exps}
    ctx = dict(vix=vix, floor=floor, by_type=by_type, cat_map=cat_map, pickable=pickable,
               default=default, today=today, exps=exps, labels=labels)

    # Two clearly-separated modes so neither workflow hides inside the other.
    tab_q, tab_fv = st.tabs(["🔎  Quick Scan  —  WatchList · Yahoo",
                             "🏛️  FinViz  —  2-Stage"])
    with tab_q:
        _tab_quick(c, ctx)
    with tab_fv:
        _tab_finviz(c, ctx)


def _tab_quick(c: dict, ctx: dict) -> None:
    """WatchList / Yahoo — one-shot scan straight to the Decision Desk."""
    exps, labels, today = ctx["exps"], ctx["labels"], ctx["today"]
    with st.expander("⚙️  Scan Inputs", expanded=True):
        _market_context(c, ctx["vix"], _regime(), ctx["floor"])
        cs, c0, c1, c2, c3, c4 = st.columns([1.3, 2.6, 1.5, 1.4, 1.4, 1.5])
        with cs:
            src = st.selectbox("Source", ["WatchList", "Yahoo Most Active", "Yahoo Day Losers"],
                               key="csp_src")
        if src == "WatchList":
            with c0:
                chosen = st.multiselect("Universe (stock types)", ctx["pickable"],
                                        default=ctx["default"], key="csp_types")
                stocks = sorted({tk for t in chosen for tk in ctx["by_type"].get(t, [])})
        else:
            with c0:
                n = st.slider("How many", 25, 300, 100, step=25, key="csp_ma_n",
                              help="Names pulled from the Yahoo source.")
                stocks = _screen_source(src, n)
        with c1:
            exp = st.selectbox("Expiry", exps, index=1, format_func=lambda e: labels[e], key="csp_exp")
        with c2:
            aor_floor = st.number_input("AOR %", 10, 80, value=30, step=5, key="csp_aor")
        with c3:
            tdelta = st.number_input("Δ max", 0.10, 0.50, value=0.30, step=0.05, key="csp_delta",
                                     help="Cap — strikes never exceed this delta (≤ 0.30 keeps you safer).")
        with c4:
            st.write(""); st.write("")
            scan = st.button("🎯 Run Hunt", type="primary", use_container_width=True, disabled=not stocks)
        if src.startswith("Yahoo") and not stocks:
            st.warning(f"{src} returned no names (Yahoo is likely rate-limiting the "
                       "screener). Try again in a moment, lower the count, or use WatchList.")

        _sublabel(c, "Result Criteria")
        f1, f2, f3, f4, f5, f6 = st.columns([1.3, 1.7, 0.9, 0.9, 1.4, 1.2])
        with f1:
            st.text_input("Search ticker", "", key="csp_f_tkr")
        with f2:
            st.multiselect("Setup", ["Reversal", "Deep Value", "IV Drop", "Mid-Band", "50SMA Reclaim"],
                           key="csp_f_setup")
        with f3:
            st.number_input("Min AOR", 0, 200, 0, step=5, key="csp_f_aor")
        with f4:
            st.number_input("Max RSI", 0, 100, 100, step=5, key="csp_f_rsi")
        with f5:
            pa, pb = st.columns(2)
            pa.number_input("Min $", 0, 100000, 0, step=5, key="csp_f_pmin")
            pb.number_input("Max $", 0, 100000, 0, step=5, key="csp_f_pmax", help="0 = no max")
        with f6:
            st.write("")
            st.checkbox("Actionable only", value=False, key="csp_f_act")
            st.checkbox("Hide ⛔ earnings", value=False, key="csp_f_veto")

    if scan and stocks:
        run_hunt({"cat_map": ctx["cat_map"], "exp_iso": exp.isoformat(), "label": labels[exp],
                  "aor": float(aor_floor), "delta": float(tdelta), "vix": ctx["vix"],
                  "dte": (exp - today).days, "stocks": stocks}, to_desk=False)
        st.rerun()

    df = st.session_state.get("scn_scan")
    meta = st.session_state.get("scn_meta")
    if df is None:
        st.info("Pick a source and hit **Run Hunt** — results show **here** for you to review. "
                "Add the names you like to your WatchList sheet; the **Decision Desk** then works "
                "the WatchList. (The Scanner no longer feeds the Decision Desk — they're separate.)")
        return
    if meta is not None:
        st.session_state["csp_scan_meta"] = meta
    _render_results(c, df)


def _tab_finviz(c: dict, ctx: dict) -> None:
    """FinViz reducer — pull the whole universe (sector free from the scrape), drop
    non-tradable (weekly check), and show the cheap detail (Price · Chg% · RSI · BB) with
    RSI / Change / Price result filters. No option-chain pricing here — that's the
    Scanner's job (the shortlist feeds it)."""
    exps, labels, today = ctx["exps"], ctx["labels"], ctx["today"]
    with st.expander("⚙️  Narrowing Inputs", expanded=True):
        fv_rows = _finviz_rows("FinViz 1-1200")                # the whole screen (~915)
        all_secs = sorted({s for _, s in fv_rows if s})
        s1c, s2c, s3c = st.columns([3.0, 1.6, 1.2])
        with s1c:
            picked = st.multiselect("Sectors", all_secs, default=all_secs, key="fv_secs",
                                    help="Free, no Yahoo calls — narrow before the tradability check.")
        with s2c:
            exp = st.selectbox("Expiry (for the weekly check)", exps, index=1,
                               format_func=lambda e: labels[e], key="fv_exp")
        with s3c:
            st.write(""); st.write("")
            run = st.button("🔎 Narrow", type="primary", use_container_width=True)
        fv_sel = [(t, s) for t, s in fv_rows if (not picked or s in picked)]
        st.caption(f"Universe **{len(fv_rows)}** → **{len(fv_sel)}** after sector filter. "
                   f"Narrow checks tradability + RSI/BB/Chg% on these, drops monthly-only.")

    meta = {"cat_map": ctx["cat_map"], "exp_iso": exp.isoformat(), "label": labels[exp],
            "aor": 30.0, "delta": 0.30, "vix": ctx["vix"], "dte": (exp - today).days}
    if run and fv_sel:
        df1 = _stage1_scan(fv_sel, exp.isoformat())
        st.session_state["csp_s1"], st.session_state["csp_s1_meta"] = df1, meta
        state.save_stage1(df1, meta)                       # persist so it survives navigation
        st.rerun()
    s1, s1_meta = state.load_stage1()
    if s1 is None:
        st.info("Pick sectors and hit **🔎 Narrow** — it drops non-tradable names and shows "
                "Price · Chg% · RSI · BB (no option pricing yet). Then filter the result below.")
        return
    _render_stage1(c, s1, s1_meta or meta)


_EMPTY_LEG = {"Strike": "—", "Cushion": "—", "Δ": "—", "Prem": "—", "AOR": None, "iv": None}

# How far the nearest expiry may sit from the target Friday before we call a name
# monthly-only (no weekly) and refuse to price it. A weekly name hits the target
# exactly (0d); the nearest monthly is ≥7d off in the ~21-28 DTE window.
_WEEKLY_TOL_DAYS = 3


def _atm_iv(puts: list, spot: float) -> float | None:
    """IV (decimal) of the AT-THE-MONEY put — the strike nearest spot, among puts
    with a sane positive IV. The far-OTM strike we actually trade often has no bid /
    a blown-out ask, so yfinance hands back a garbage IV there (KGC $21 showed 100%
    vs ~55% ATM). The ATM strike is the liquid, representative read."""
    cands = [p for p in puts if (p.get("iv") or 0) > 0]
    if not cands or not spot:
        return None
    return min(cands, key=lambda p: abs(p["strike"] - spot)).get("iv")


def _price_leg(t: str, target_iso: str, target_delta: float) -> dict:
    """The put nearest `target_delta` at the chosen expiry — strike, cushion, Δ, prem,
    AOR. IV comes from the AT-THE-MONEY strike of the same expiry (not the priced
    strike, whose IV is unreliable when illiquid) and feeds the IV Drop trigger.
    Cushion = how far OTM below spot.

    Returns {no_weekly: True} for monthly-only names (no expiry near the target),
    so the scanner can exclude them rather than pricing a fictional target chain."""
    ch = option_chain.load_puts_at(t, target_iso, tol_days=_WEEKLY_TOL_DAYS)
    if ch.get("no_options"):
        return {**_EMPTY_LEG, "excluded": "not optionable"}
    if ch.get("no_weekly"):
        return {**_EMPTY_LEG, "excluded": "monthly only — no weekly"}
    spot, dte, puts = ch.get("spot"), ch.get("dte"), ch.get("puts") or []
    if not puts or not spot or not dte:
        return dict(_EMPTY_LEG)
    pick = csp_pricing.pick_by_delta(puts, spot, dte, target_delta)
    if not pick:
        # No tradeable OTM put under spot with a real bid — a broken/illiquid chain
        # (e.g. LQDA spot $28 but only $45+ ITM strikes). Exclude rather than show a
        # blank/phantom-AOR row that would sort to the top of an AOR-ranked board.
        return {**_EMPTY_LEG, "excluded": "no tradeable OTM put"}
    d = pick.get("delta")
    cushion = (spot - pick["strike"]) / spot * 100 if spot else None
    iv = _atm_iv(puts, spot) or pick.get("iv")             # ATM IV (fallback: picked strike)
    return {
        "Strike": f"${pick['strike']:.0f}",
        "Cushion": f"{cushion:.1f}%" if cushion is not None else "—",
        "Δ": f"{abs(d):.2f}" if d is not None else "—",
        "Prem": f"${pick['premium']:.2f}",
        "AOR": round(pick["aor"], 0) if pick.get("aor") is not None else None,
        "iv": round(iv * 100, 1) if iv else None,          # ATM IV, %
    }


def watchlist_types() -> list:
    """The WatchList stock-type buckets (e.g. 01-Growth, 02-Alternate, 03-Speculation)
    for the Decision Desk's type picker."""
    types, _ = gsheet.watchlist_by_type()
    return [t for t in types if t != "All"]


def default_hunt_inputs(types: list | None = None) -> dict | None:
    """WatchList hunt inputs for the Decision Desk's ▶ Run — the Decision Desk always runs
    the WatchList (never a Scanner result). `types` picks the buckets (default Growth/Alt/
    Spec). First expiry ≥21 DTE, AOR 30, Δ 0.30. None if the WatchList/expiry list is empty."""
    _, by_type = gsheet.watchlist_by_type()
    cat_map = {tk: t for t, ts in by_type.items() if t != "All" for tk in ts}
    want = types if types else _DEFAULT_TYPES
    chosen = [t for t in want if t in by_type] or [t for t in by_type if t != "All"][:1]
    stocks = sorted({tk for t in chosen for tk in by_type.get(t, [])})
    today = date.today()
    exps = csp_pricing.expiry_choices(today, 21)
    if not stocks or not exps:
        return None
    exp = exps[1] if len(exps) > 1 else exps[0]        # matches the scanner's default (index=1)
    return {"stocks": stocks, "cat_map": cat_map, "exp_iso": exp.isoformat(),
            "label": f"{exp:%b %d} ({(exp - today).days}d)", "aor": 30.0, "delta": 0.30,
            "vix": _current_vix(), "dte": (exp - today).days}


def run_hunt(inp: dict, to_desk: bool = True) -> None:
    """Run the scan for `inp` and stash the result.

    to_desk=True (the Decision Desk's ▶ Run) stores it in the shared hunt store that the
    Decision Desk reads. to_desk=False (the Candidate Scanner's own exploration) keeps it
    in a SEPARATE scanner slot, so discovery never overwrites the daily WatchList run —
    the two tools are fully independent."""
    scan_df = _scan(inp["stocks"], inp["cat_map"], inp["exp_iso"], inp["aor"], inp["delta"], inp["vix"])
    meta = (inp["label"], inp["aor"], inp["delta"], inp["exp_iso"], inp["dte"])
    if to_desk:
        st.session_state["csp_scan"] = scan_df
        st.session_state["csp_scan_meta"] = meta
        state.save_hunt(scan_df, meta)
        state.save_hunt_inputs(inp)
    else:
        st.session_state["scn_scan"] = scan_df
        st.session_state["scn_meta"] = meta


def _scan(stocks: list, cat_map: dict, target_iso: str, aor_floor: float,
          target_delta: float, vix: float | None = None) -> pd.DataFrame:
    iv_map, pos_map = _sheet_maps()
    rows = []
    prog = st.progress(0, text="Scanning…")
    n = len(stocks)
    today = date.today()
    for i, t in enumerate(stocks):
        prog.progress(i / max(n, 1), text=f"[{i+1}/{n}] {t}")
        hist = yahoo.get_history(t, period="2y", interval="1d")
        if hist.empty or "Close" not in hist.columns or len(hist) < 30:
            rows.append({"Ticker": t, "Type": cat_map.get(t, ""), "Setup": "—",
                         "Quality": "—", "Note": "no price data"})
            continue
        lr = leap_setup.evaluate(hist)
        # Price the ~target-delta put FIRST — its own IV (at the strike/expiry we trade)
        # is the IV we show and the IV that feeds the IV Drop trigger. Fall back to the
        # ATM-chain IV only if the target-expiry put chain is unavailable.
        leg = _price_leg(t, target_iso, target_delta)
        if leg.get("excluded"):
            # Not tradeable as a weekly CSP — no options at all, or monthly-only (the
            # target Friday's chain doesn't exist). Exclude rather than price a
            # fictional / different expiry (roster rule = weeklies required).
            rows.append({"Ticker": t, "Type": cat_map.get(t, ""),
                         "Setup": "—", "Quality": "—", "Industry": "—",
                         "Note": leg["excluded"]})
            continue
        iv_pct = leg.get("iv") or yahoo.get_atm_iv(t, lr.get("price"))
        # Realized vol (annualised, ~21 trading days) vs IV. IV ≫ RV means the option
        # is pricing an EVENT (merger / litigation / FDA / earnings), not normal vol —
        # KVUE paid like 52% IV on 29% realized. Flag these; don't let them rank.
        rv = None
        try:
            rets = hist["Close"].pct_change().dropna().tail(21)
            if len(rets) >= 10:
                rv = float(rets.std() * (252 ** 0.5) * 100)
        except Exception:
            rv = None
        iv_rv = (iv_pct / rv) if (iv_pct and rv) else None
        chg = lr.get("chg_pct")
        earn = yahoo.get_earnings_date(t)
        edays = (earn - today).days if earn else None
        cs = csp_setup.evaluate(lr, iv_pct, chg, earnings_days=edays, vix=vix)
        hv = hm.latest_signal(hm.analyze(hist.rename(columns=str.lower)))
        fin = _fund_row(t)
        r14 = lr.get("rsi14")
        # 3-month discount: how far the strike sits below the 3-month high (~63 trading days).
        disc3 = None
        try:
            hi3m = float(hist["Close"].tail(63).max())
            sk = float(str(leg["Strike"]).replace("$", "").replace(",", ""))
            if hi3m > 0 and sk > 0:
                disc3 = (hi3m - sk) / hi3m * 100
        except (TypeError, ValueError):
            disc3 = None
        vetoed = bool(cs.get("earnings_veto"))
        rows.append({
            "Ticker": t,
            "Type": cat_map.get(t, ""),
            "Industry": fin.get("Industry", "") or "—",
            "Setup": (f"✓ {' · '.join(cs['setups'])}" if cs.get("setup_ok") else "—"),
            "Quality": "✓" if cs.get("quality_ok") else "—",
            "RSI": f"{r14:.0f}" if r14 is not None else "—",
            "BB": lr.get("bb_pos", "—"),
            "Chg%": round(chg, 2) if chg is not None else None,
            "IV": f"{iv_pct:.0f}%" if iv_pct else "—",
            "Strike": leg["Strike"],
            "Cushion": leg["Cushion"],
            "3mo ↓": f"{disc3:.1f}%" if disc3 is not None else "—",
            "Δ": leg["Δ"],
            "Prem": leg["Prem"],
            "AOR": leg["AOR"],
            "IV/RV": round(iv_rv, 2) if iv_rv is not None else None,
            "HM": hv.get("signal", "—"),
            "MACD": lr.get("macd_dir", "—"),
            "Price": round(lr["price"], 2) if lr.get("price") is not None else None,
            "% off High": round(lr["off_high_pct"], 1) if lr.get("off_high_pct") is not None else None,
            "Earnings": (("⛔ " if vetoed else "") + f"{earn:%m/%d} ({edays}d)") if earn else "unknown",
            "Pos": pos_map.get(t, ""),
            "Financials": fin.get("Financials", ""),
            "Cash": fin.get("Cash"),
            "Note": "",
        })
    prog.empty()   # hide the bar once done to save space
    return pd.DataFrame(rows, columns=_COLS)


def _actionable(df: pd.DataFrame) -> pd.Series:
    return (df["Setup"].astype(str).str.startswith("✓")
            & (df["Quality"].astype(str) == "✓")
            & ~df["Earnings"].astype(str).str.startswith("⛔"))


_SCAN_LEFT = {"Ticker", "Type", "BB", "HM", "Earnings", "Financials", "Industry", "Note"}


def _scan_html(view: pd.DataFrame, c: dict, floor: float) -> str:
    """Themed HTML results table (native st.dataframe can't follow the Grey theme)."""
    hbg, bd, rowbg = c["raised"], c["border"], c["panel"]
    txt, muted, pos, neg, acc, amber = (c["text"], c["muted"], c["pos"], c["neg"],
                                        c["accent"], c["amber"])

    def _num(v):
        try:
            return float(str(v).replace("$", "").replace("%", "").replace(",", "").replace("+", ""))
        except (TypeError, ValueError):
            return None

    def fmt(col, v):
        if v is None or str(v).strip() in ("", "nan", "None"):
            return "—"
        n = _num(v)
        if col == "Price":
            return f"${n:.2f}" if n is not None else str(v)
        if col == "AOR":
            return f"{n:.0f}%" if n is not None else str(v)
        if col == "Chg%":
            return f"{n:+.2f}%" if n is not None else str(v)
        if col == "% off High":
            return f"{n:.1f}%" if n is not None else str(v)
        if col == "IV/RV":
            return f"{n:.2f}×" if n is not None else str(v)
        if col == "Cash":                                  # net cash (cash − debt), $B
            if n is None:
                return "—"
            return f"+${n:.1f}B" if n >= 0 else f"−${abs(n):.1f}B"
        return str(v)

    def color(col, v):
        s = str(v).strip()
        n = _num(v)
        if col == "Setup" and s.startswith("✓"):
            return f"background:rgba(47,158,68,.18);color:{pos};font-weight:800;"
        if col == "Quality" and s == "✓":
            return f"background:rgba(52,127,209,.18);color:{acc};font-weight:800;"
        if col == "AOR":
            return f"color:{pos};font-weight:800;" if (n is not None and n >= floor) else f"color:{muted};"
        if col == "IV/RV" and n is not None:          # IV ≫ RV = event-driven, flag it
            return f"color:{neg};font-weight:800;" if n > 1.5 else f"color:{muted};"
        if col == "Cash" and n is not None:            # net cash green, net debt red
            return f"color:{pos};font-weight:800;" if n >= 0 else f"color:{neg};font-weight:700;"
        if col == "RSI" and n is not None:
            if n > 64:
                return f"color:{neg};font-weight:800;"
            if n <= 50:
                return f"color:{pos};font-weight:800;"
        if col == "BB":
            low = s.lower()
            if "upper" in low or "mid" in low or "above" in low:
                return f"color:{neg};"
            if "lower" in low or "below" in low:
                return f"color:{pos};"
        if col == "MACD":
            if "▲" in s:
                return f"color:{pos};font-weight:700;"
            if "▼" in s:
                return f"color:{neg};font-weight:700;"
        if col == "HM":
            if "STRONG" in s:
                return "color:#d9822b;font-weight:800;"
            if s == "BUY":
                return f"color:{amber};font-weight:700;"
            if s == "SELL":
                return f"color:{neg};font-weight:700;"
        if col == "Earnings" and s.startswith("⛔"):
            return f"background:rgba(242,85,90,.18);color:{neg};font-weight:700;"
        if col == "Earnings" and s.lower() == "unknown":      # can't confirm it's clear
            return f"color:{amber};font-weight:700;"
        if col == "Chg%" and n is not None:
            return f"color:{pos if n >= 0 else neg};font-weight:700;"
        return ""

    # Freeze panes: the header row stays on vertical scroll, the first (Ticker) column
    # stays on horizontal scroll, and the top-left cell stays for both. box-shadow draws
    # the edges (a plain border vanishes under border-collapse on a sticky cell), and each
    # frozen cell gets an opaque background so scrolled content doesn't bleed through.
    head = ""
    for i, col in enumerate(_COLS):
        align = "left" if col in _SCAN_LEFT else "center"
        stick = (f"position:sticky;top:0;left:0;z-index:5;box-shadow:1px 1px 0 {bd};" if i == 0
                 else f"position:sticky;top:0;z-index:3;box-shadow:0 1px 0 {bd};")
        head += (f"<th style='{stick}background:{hbg};color:{txt};border:1px solid {bd};"
                 f"padding:6px 8px;text-align:{align};font-weight:700;"
                 f"font-size:11px;white-space:nowrap;'>{col}</th>")
    body = ""
    for _, row in view.iterrows():
        tds = ""
        for i, col in enumerate(_COLS):
            v = row.get(col)
            align = "left" if col in _SCAN_LEFT else "center"
            base = (f"border:1px solid {bd};padding:5px 8px;text-align:{align};color:{txt};"
                    f"white-space:nowrap;font-size:11.5px;")
            if i == 0:                                   # Ticker — frozen first column, header
                base += (f"position:sticky;left:0;z-index:1;background:{hbg};font-weight:700;"
                         f"box-shadow:1px 0 0 {bd};")   # darker surface to set the column apart
            tds += f"<td style='{base}{color(col, v)}'>{fmt(col, v)}</td>"
        body += f"<tr style='background:{rowbg};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:560px;border:1px solid {bd};border-radius:8px;'>"
            f"<table style='border-collapse:collapse;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _render_results(c: dict, df: pd.DataFrame) -> None:
    # Counts for the single-line findings summary (rendered after result filters below).
    act = _actionable(df)
    note = df["Note"].astype(str) if "Note" in df.columns else pd.Series([""] * len(df))
    n_scanned = len(df)
    n_priced = int(pd.to_numeric(df["AOR"], errors="coerce").notna().sum())
    n_setup = int(df["Setup"].astype(str).str.startswith("✓").sum())
    n_act = int(act.sum())
    n_monthly = int((note == "monthly only — no weekly").sum())
    n_noopt = int((note == "not optionable").sum())
    n_nootm = int((note == "no tradeable OTM put").sum())
    n_nodata = int((note == "no price data").sum())

    df = df.copy()
    df = df.sort_values(["Type", "Ticker"], ascending=[True, True]).reset_index(drop=True)

    # Result-criteria widgets live in the Scanner Criteria card; read their values.
    q = str(st.session_state.get("csp_f_tkr", "")).strip().upper()
    pick = st.session_state.get("csp_f_setup", []) or []
    min_aor = st.session_state.get("csp_f_aor", 0)
    max_rsi = st.session_state.get("csp_f_rsi", 100)
    min_px = st.session_state.get("csp_f_pmin", 0)
    max_px = st.session_state.get("csp_f_pmax", 0)
    only_act = st.session_state.get("csp_f_act", False)
    hide_veto = st.session_state.get("csp_f_veto", False)

    view = df[_actionable(df)] if only_act else df
    if q:
        view = view[view["Ticker"].astype(str).str.upper().str.contains(q, na=False)]
    if pick:
        # a setup label maps to a substring in the Setup cell ("IV Drop" → "IV")
        keys = {"Reversal": "Reversal", "Deep Value": "Deep Value", "IV Drop": "IV",
                "Mid-Band": "Mid-Band", "50SMA Reclaim": "50SMA"}
        pats = [keys[p] for p in pick]
        view = view[view["Setup"].astype(str).apply(lambda s: any(k in s for k in pats))]
    if min_aor > 0:
        view = view[pd.to_numeric(view["AOR"], errors="coerce").fillna(-1) >= min_aor]
    if max_rsi < 100:
        view = view[pd.to_numeric(view["RSI"], errors="coerce").fillna(999) <= max_rsi]
    if min_px > 0:
        view = view[pd.to_numeric(view["Price"], errors="coerce").fillna(-1) >= min_px]
    if max_px > 0:
        view = view[pd.to_numeric(view["Price"], errors="coerce").fillna(10 ** 9) <= max_px]
    if hide_veto:
        view = view[~view["Earnings"].astype(str).str.startswith("⛔")]

    # One compact line with the whole finding — scanned, tradeable, the exclusion
    # buckets (only when non-zero), setup/actionable counts, and the filtered view size.
    cells = [(f"{n_scanned} scanned", c["muted"]),
             (f"{n_priced} tradeable", c["pos"]),
             (f"{n_monthly} monthly", c["amber"]) if n_monthly else None,
             (f"{n_noopt} no-opt", c["muted"]) if n_noopt else None,
             (f"{n_nootm} no-OTM", c["muted"]) if n_nootm else None,
             (f"{n_nodata} no-data", c["neg"]) if n_nodata else None,
             (f"{n_setup} setup", c["muted"]),
             (f"{n_act} actionable", c["pos"])]
    if len(view) != n_scanned:
        cells.append((f"showing {len(view)}", c["muted"]))
    line = "<div style='display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:0 0 8px;'>"
    for cell in cells:
        if not cell:
            continue
        lbl, col = cell
        line += (f"<span style='background:{col}18;color:{col};border:1px solid {col}44;"
                 f"border-radius:6px;padding:2px 9px;font-size:12px;font-weight:700;"
                 f"white-space:nowrap;'>{lbl}</span>")
    line += "</div>"
    st.markdown(line, unsafe_allow_html=True)

    floor = (st.session_state.get("csp_scan_meta") or (None, 30.0))[1] or 30.0
    st.markdown(_scan_html(view, c, float(floor)), unsafe_allow_html=True)

    st.download_button("Download CSV", df.to_csv(index=False).encode(),
                       "csp_scan.csv", "text/csv")
