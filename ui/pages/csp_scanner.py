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
         "Prem", "AOR", "IV", "RSI", "BB", "MACD", "Chg%", "% off High",
         "Quality", "HM", "Earnings", "Pos", "Financials", "Industry"]


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

    with st.expander("⚙️  Scanner Criteria", expanded=True):
        _sublabel(c, "Market Context")
        _market_context(c, vix, _regime(), floor)

        _sublabel(c, "Scan Inputs")
        cs, c0, c1, c2, c3, c4 = st.columns([1.3, 3.2, 1.8, 0.9, 0.9, 1.7])
        with cs:
            src = st.selectbox("Source", ["WatchList", "Yahoo Most Active"], key="csp_src")
        with c0:
            if src == "WatchList":
                chosen = st.multiselect("Universe (stock types)", pickable, default=default, key="csp_types")
                stocks = sorted({tk for t in chosen for tk in by_type.get(t, [])})
            else:
                n = st.slider("How many", 25, 300, 100, step=25, key="csp_ma_n")
                stocks = screeners.most_active(n)
        with c1:
            exp = st.selectbox("Expiry", exps, index=1, format_func=lambda e: labels[e], key="csp_exp")
        with c2:
            aor_floor = st.number_input("AOR %", 10, 80, value=30, step=5, key="csp_aor")
        with c3:
            tdelta = st.number_input("Δ max", 0.10, 0.50, value=0.30, step=0.05, key="csp_delta",
                                     help="Cap — strikes never exceed this delta (≤ 0.30 keeps you safer).")
        with c4:
            st.write(""); st.write("")
            scan = st.button("🎯 Run Hunt", type="primary",
                             use_container_width=True, disabled=not stocks)
        if src != "WatchList" and not stocks:
            st.warning("Yahoo Most Active returned no names (Yahoo is likely rate-limiting the "
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
        run_hunt({"stocks": stocks, "cat_map": cat_map, "exp_iso": exp.isoformat(),
                  "label": labels[exp], "aor": float(aor_floor), "delta": float(tdelta),
                  "vix": vix, "dte": (exp - today).days})
        # The hunt trigger → hand the results to the Decision Desk and jump there.
        st.query_params["nav"] = "Decision Desk"
        st.rerun()

    df, meta = state.load_hunt()
    if df is None:
        st.info("Set your inputs above and hit **Run Candidate Hunt** — results land on Decision Desk. "
                "The raw scan stays here for browsing.")
        return
    if meta is not None:
        st.session_state["csp_scan_meta"] = meta      # restore caption context after a reload
    _render_results(c, df)


_EMPTY_LEG = {"Strike": "—", "Cushion": "—", "Δ": "—", "Prem": "—", "AOR": None, "iv": None}


def _price_leg(t: str, target_iso: str, target_delta: float) -> dict:
    """The put nearest `target_delta` at the chosen expiry — strike, cushion, Δ, prem,
    AOR, and the put's OWN implied vol (so the IV column matches the priced strike, and
    the IV Drop trigger keys off the real contract). Cushion = how far OTM below spot."""
    ch = option_chain.load_puts_at(t, target_iso)
    spot, dte, puts = ch.get("spot"), ch.get("dte"), ch.get("puts") or []
    if not puts or not spot or not dte:
        return dict(_EMPTY_LEG)
    pick = csp_pricing.pick_by_delta(puts, spot, dte, target_delta)
    if not pick:
        return dict(_EMPTY_LEG)
    d = pick.get("delta")
    cushion = (spot - pick["strike"]) / spot * 100 if spot else None
    iv = pick.get("iv")                                    # decimal from the chain
    return {
        "Strike": f"${pick['strike']:.0f}",
        "Cushion": f"{cushion:.1f}%" if cushion is not None else "—",
        "Δ": f"{abs(d):.2f}" if d is not None else "—",
        "Prem": f"${pick['premium']:.2f}",
        "AOR": round(pick["aor"], 0) if pick.get("aor") is not None else None,
        "iv": round(iv * 100, 1) if iv else None,          # the priced put's IV, %
    }


def run_hunt(inp: dict) -> None:
    """Run the scan for `inp` and stash results + meta + inputs (so Decision Desk can
    re-run it). Shared by the Candidate Scanner's button and Decision Desk's Run Hunt."""
    scan_df = _scan(inp["stocks"], inp["cat_map"], inp["exp_iso"], inp["aor"], inp["delta"], inp["vix"])
    meta = (inp["label"], inp["aor"], inp["delta"], inp["exp_iso"], inp["dte"])
    st.session_state["csp_scan"] = scan_df
    st.session_state["csp_scan_meta"] = meta
    state.save_hunt(scan_df, meta)
    state.save_hunt_inputs(inp)


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
            rows.append({"Ticker": t, "Type": cat_map.get(t, ""), "Setup": "—", "Quality": "—"})
            continue
        lr = leap_setup.evaluate(hist)
        # Price the ~target-delta put FIRST — its own IV (at the strike/expiry we trade)
        # is the IV we show and the IV that feeds the IV Drop trigger. Fall back to the
        # ATM-chain IV only if the target-expiry put chain is unavailable.
        leg = _price_leg(t, target_iso, target_delta)
        iv_pct = leg.get("iv") or yahoo.get_atm_iv(t, lr.get("price"))
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
            "HM": hv.get("signal", "—"),
            "MACD": lr.get("macd_dir", "—"),
            "Price": round(lr["price"], 2) if lr.get("price") is not None else None,
            "% off High": round(lr["off_high_pct"], 1) if lr.get("off_high_pct") is not None else None,
            "Earnings": (("⛔ " if vetoed else "") + f"{earn:%m/%d} ({edays}d)") if earn else "—",
            "Pos": pos_map.get(t, ""),
            "Financials": fin.get("Financials", ""),
        })
    prog.empty()   # hide the bar once done to save space
    return pd.DataFrame(rows, columns=_COLS)


def _actionable(df: pd.DataFrame) -> pd.Series:
    return (df["Setup"].astype(str).str.startswith("✓")
            & (df["Quality"].astype(str) == "✓")
            & ~df["Earnings"].astype(str).str.startswith("⛔"))


_SCAN_LEFT = {"Ticker", "Type", "BB", "HM", "Earnings", "Financials", "Industry"}


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
        if col == "Chg%" and n is not None:
            return f"color:{pos if n >= 0 else neg};font-weight:700;"
        return ""

    head = "".join(
        f"<th style='position:sticky;top:0;z-index:2;background:{hbg};color:{txt};border:1px solid {bd};"
        f"padding:6px 8px;text-align:{'left' if col in _SCAN_LEFT else 'center'};font-weight:700;"
        f"font-size:11px;white-space:nowrap;'>{col}</th>" for col in _COLS)
    body = ""
    for _, row in view.iterrows():
        tds = ""
        for col in _COLS:
            v = row.get(col)
            align = "left" if col in _SCAN_LEFT else "center"
            base = (f"border:1px solid {bd};padding:5px 8px;text-align:{align};color:{txt};"
                    f"white-space:nowrap;font-size:11.5px;")
            tds += f"<td style='{base}{color(col, v)}'>{fmt(col, v)}</td>"
        body += f"<tr style='background:{rowbg};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:760px;border:1px solid {bd};border-radius:8px;'>"
            f"<table style='border-collapse:collapse;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _render_results(c: dict, df: pd.DataFrame) -> None:
    meta = st.session_state.get("csp_scan_meta")
    if meta:
        tgt = meta[2] if len(meta) > 2 else 0.30
        st.caption(f"Pricing at **{meta[0]}** · Strike/Prem = the richest put with **Δ ≤ {tgt:.2f}** "
                   f"· Prem = mid (bid+ask)/2 · AOR green when ≥ **{meta[1]:.0f}%** floor.")

    act = _actionable(df)
    st.markdown(f"**{int(act.sum())}** actionable (Setup ✓ + Quality ✓, no veto) · "
                f"**{int(df['Setup'].astype(str).str.startswith('✓').sum())}** with a Setup · "
                f"**{len(df)}** scanned")

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

    st.caption(f"Showing **{len(view)}** of {len(df)} rows")

    floor = meta[1] if meta else 30.0
    st.markdown(_scan_html(view, c, float(floor)), unsafe_allow_html=True)

    st.download_button("Download CSV", df.to_csv(index=False).encode(),
                       "csp_scan.csv", "text/csv")
