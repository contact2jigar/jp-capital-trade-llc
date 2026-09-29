"""LEAP Scanner — find LEAP entries per the Δ0.70 flip doctrine, plus a discovery board.

Setup (from leap_setup.evaluate, on the underlying — the entry trigger):
  • Path A — Reversal   : RSI(14)<40 + lower-BB touch (last 3d) + green candle today
  • Path B — Deep Value : RSI(14)<35 + the whole candle below the lower band

For every name we compute the doctrine target: the ~0.70-delta ITM call at ~2yr DTE
(Black-Scholes with an ATM-IV proxy) — strike, delta, and an ESTIMATED cost. These
are estimates to size against, not a live quote; the real flip is executed manually.

GO / NO comes from the LEAP gates: 2% wheel-capital cap per account AND max 2 active
LEAPs per account. The tool never places an order.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from logic import hm_signal as hm
from logic import leap_pricing, leap_setup
from logic import monitor as mb
from services import gsheet, yahoo
from ui.pages import command_center as cc

_DEFAULT_TYPES = ["01-Growth", "02-Alternate"]

_COLS = ["Ticker", "Type", "Setup", "Price", "Chg%", "Strike", "Δ", "Est Cost",
         "RSI", "BB", "MACD", "% off High", "HM", "Earnings", "IRA", "LLC", "Decision"]
_LEFT = {"Ticker", "Type", "Setup", "BB", "HM", "Earnings"}


# ── small chrome helpers (mirrors csp_scanner) ───────────────────────────────
def _sublabel(c: dict, text: str) -> None:
    st.markdown(f"<div style='font-size:10px;letter-spacing:.09em;text-transform:uppercase;"
                f"color:{c['muted']};font-weight:700;margin:10px 0 2px;'>{text}</div>",
                unsafe_allow_html=True)


def _context(c: dict, tiles: list) -> None:
    html = "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:2px 0 10px;'>"
    for label, val, col in tiles:
        html += (f"<div style='background:{c['panel']};border:1px solid {c['border_soft']};"
                 f"border-radius:10px;padding:8px 13px;'>"
                 f"<div style='font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;"
                 f"color:{c['muted']}'>{label}</div>"
                 f"<div style='font-size:17px;font-weight:800;color:{col};margin-top:2px'>{val}</div></div>")
    st.markdown(html + "</div>", unsafe_allow_html=True)


def _leap_counts(df: pd.DataFrame) -> dict:
    """Active LEAP positions per account (open rows, Opt Typ == LEAP)."""
    od = mb._openrows(df)
    if od.empty or "Opt Typ" not in od or "Account" not in od:
        return {}
    lo = od[od["Opt Typ"].astype(str).str.upper() == "LEAP"]
    return lo["Account"].astype(str).str.upper().value_counts().to_dict()


def _setup_label(lr: dict) -> str:
    return {"A": "✓ Reversal", "B": "✓ Deep Value",
            "A+B": "✓ Rev+Deep"}.get(lr.get("path", ""), "✓ Setup")


def _room(gap, count, cost) -> tuple[str, bool | None]:
    """Per-account room for one LEAP: 2% cap (dollar `gap`) + max 2 active."""
    if count >= 2:
        return ("MAX 2", False)
    if cost is None or gap is None:
        return ("—", None)
    if gap >= cost:
        return (f"${gap:,.0f}", True)
    return ("NO ROOM", False)


def render(c: dict) -> None:
    data = cc.board_data()
    if data is None:
        st.warning("Couldn't load the TradeLog tab — LEAP gates need the live board.")
        return
    r, vix, trend = data["r"], data["vix"], data["trend"]
    ira, llc = r["ira"], r["llc"]
    counts = _leap_counts(cc._tradelog_full())

    types, by_type = gsheet.watchlist_by_type()
    cat_map = {tk: t for t, ts in by_type.items() if t != "All" for tk in ts}
    pickable = [t for t in types if t != "All"]
    default = [t for t in _DEFAULT_TYPES if t in pickable] or pickable[:1]

    with st.expander("⚙️  LEAP Scanner Criteria", expanded=True):
        _sublabel(c, "Market Context")
        rc = c["pos"] if trend == "Uptrend" else c["neg"] if trend == "Downtrend" else c["muted"]
        _context(c, [("VIX", f"{vix:.2f}" if vix else "—", c["text"]),
                     ("REGIME", trend, rc),
                     ("IRA LEAPS", f"{int(counts.get('IRA', 0))} / 2", c["text"]),
                     ("LLC LEAPS", f"{int(counts.get('LLC', 0))} / 2", c["text"])])

        _sublabel(c, "Scan Inputs")
        c0, c1, c2, c3 = st.columns([3.4, 1.3, 1.5, 1.6])
        with c0:
            chosen = st.multiselect("Universe (stock types)", pickable, default=default, key="leap_types")
            stocks = sorted({tk for t in chosen for tk in by_type.get(t, [])})
        with c1:
            tdelta = st.number_input("Target Δ", 0.50, 0.90, value=0.70, step=0.05, key="leap_delta",
                                     help="The doctrine flip target — deep-ITM call delta (~0.70).")
        with c2:
            months = st.selectbox("LEAP horizon", [18, 24, 30], index=1, key="leap_months",
                                  format_func=lambda m: f"~{m} mo")
        with c3:
            st.write(""); st.write("")
            scan = st.button("🎯 Run LEAP Hunt", type="primary",
                             use_container_width=True, disabled=not stocks)

        _sublabel(c, "Result Criteria")
        g1, g2, g3 = st.columns([1.6, 1.2, 1.2])
        with g1:
            st.text_input("Search ticker", "", key="leap_f_tkr")
        with g2:
            st.checkbox("Setup ✓ only", value=False, key="leap_f_setup")
        with g3:
            st.checkbox("GO only", value=False, key="leap_f_go")

    if scan and stocks:
        board = {"ira": ira, "llc": llc}
        df, dte, exp = _scan(stocks, cat_map, float(tdelta), int(months), board, counts)
        st.session_state["leap_scan"] = (df, dte, exp, float(tdelta))

    stash = st.session_state.get("leap_scan")
    if stash is None:
        st.info("Pick a universe and hit **Run LEAP Hunt**. Setup ✓ names (Reversal / Deep Value) "
                "are your Δ0.70 flip entries; the rest is a ranked discovery board. Never places an order.")
        return
    _render_results(c, *stash)


def _scan(stocks, cat_map, target_delta, months, board, counts):
    today = date.today()
    exp = leap_pricing.leap_expiry(today, months)
    dte = (exp - today).days
    ira, llc = board["ira"], board["llc"]
    rows = []
    prog = st.progress(0, text="Scanning…")
    n = len(stocks)
    for i, t in enumerate(stocks):
        prog.progress(i / max(n, 1), text=f"[{i+1}/{n}] {t}")
        hist = yahoo.get_history(t, period="2y", interval="1d")
        if hist.empty or "Close" not in hist.columns or len(hist) < 30:
            rows.append({"Ticker": t, "Type": cat_map.get(t, ""), "Setup": "—", "Decision": "—"})
            continue
        lr = leap_setup.evaluate(hist)
        price = lr.get("price")
        iv_pct = yahoo.get_atm_iv(t, price)
        leg = leap_pricing.pick_leap_call(price, iv_pct, dte, target_delta) if (price and iv_pct) else None
        hv = hm.latest_signal(hm.analyze(hist.rename(columns=str.lower)))
        earn = yahoo.get_earnings_date(t)
        edays = (earn - today).days if earn else None
        setup_ok = bool(lr.get("setup_ok"))
        cost = leg.get("cost") if leg else None
        ira_txt, ira_ok = _room(ira.get("leapgap"), counts.get("IRA", 0), cost)
        llc_txt, llc_ok = _room(llc.get("leapgap"), counts.get("LLC", 0), cost)
        room = bool(ira_ok) or bool(llc_ok)
        decision = "GO" if (setup_ok and room) else ("NO" if setup_ok else "—")
        r14 = lr.get("rsi14")
        rows.append({
            "Ticker": t, "Type": cat_map.get(t, ""),
            "Setup": _setup_label(lr) if setup_ok else "—",
            "Price": round(price, 2) if price else None,
            "Chg%": round(lr["chg_pct"], 2) if lr.get("chg_pct") is not None else None,
            "Strike": f"${leg['strike']:.0f}" if leg else "—",
            "Δ": f"{leg['delta']:.2f}" if (leg and leg.get("delta") is not None) else "—",
            "Est Cost": f"${cost:,.0f}" if cost else "—",
            "RSI": f"{r14:.0f}" if r14 is not None else "—",
            "BB": lr.get("bb_pos", "—"),
            "MACD": lr.get("macd_dir", "—"),
            "% off High": round(lr["off_high_pct"], 1) if lr.get("off_high_pct") is not None else None,
            "HM": hv.get("signal", "—"),
            "Earnings": f"{earn:%m/%d} ({edays}d)" if earn else "—",
            "IRA": ira_txt, "LLC": llc_txt, "Decision": decision,
        })
    prog.empty()
    return pd.DataFrame(rows, columns=_COLS), dte, exp


def _scan_html(view: pd.DataFrame, c: dict) -> str:
    hbg, bd, rowbg = c["raised"], c["border"], c["panel"]
    txt, muted, pos, neg, amber = c["text"], c["muted"], c["pos"], c["neg"], c["amber"]

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
        if col == "Decision":
            if s == "GO":
                return f"background:rgba(47,158,68,.20);color:{pos};font-weight:900;"
            if s == "NO":
                return f"background:rgba(242,85,90,.16);color:{neg};font-weight:900;"
            return f"color:{muted};"
        if col in ("IRA", "LLC"):
            if s.startswith("$"):
                return f"color:{pos};font-weight:700;"
            if s in ("NO ROOM", "MAX 2"):
                return f"color:{neg};font-weight:700;"
            return f"color:{muted};"
        if col == "RSI" and n is not None:
            if n < 40:
                return f"color:{pos};font-weight:800;"
            if n > 64:
                return f"color:{neg};font-weight:800;"
        if col == "BB":
            low = s.lower()
            if "lower" in low or "below" in low:
                return f"color:{pos};font-weight:700;"
            if "upper" in low or "above" in low:
                return f"color:{neg};"
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
        if col == "Chg%" and n is not None:
            return f"color:{pos if n >= 0 else neg};font-weight:700;"
        return ""

    head = "".join(
        f"<th style='position:sticky;top:0;z-index:2;background:{hbg};color:{txt};border:1px solid {bd};"
        f"padding:6px 8px;text-align:{'left' if col in _LEFT else 'center'};font-weight:700;"
        f"font-size:11px;white-space:nowrap;'>{col}</th>" for col in _COLS)
    body = ""
    for _, row in view.iterrows():
        tds = ""
        for col in _COLS:
            v = row.get(col)
            align = "left" if col in _LEFT else "center"
            base = (f"border:1px solid {bd};padding:5px 8px;text-align:{align};color:{txt};"
                    f"white-space:nowrap;font-size:11.5px;")
            tds += f"<td style='{base}{color(col, v)}'>{fmt(col, v)}</td>"
        body += f"<tr style='background:{rowbg};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:760px;border:1px solid {bd};border-radius:8px;'>"
            f"<table style='border-collapse:collapse;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _render_results(c: dict, df: pd.DataFrame, dte: int, exp, tdelta: float) -> None:
    st.caption(f"Target = the **Δ ≈ {tdelta:.2f}** ITM call expiring **{exp:%b %Y}** (~{dte}d) · "
               f"strike/cost are Black-Scholes **estimates** (ATM-IV proxy), not a live quote · "
               f"GO = Setup ✓ **and** LEAP room (2% cap + max 2/acct).")

    setup_n = int(df["Setup"].astype(str).str.startswith("✓").sum())
    go_n = int((df["Decision"].astype(str) == "GO").sum())
    st.markdown(f"**{go_n}** GO (setup + room) · **{setup_n}** with a setup · **{len(df)}** scanned")

    df = df.copy()
    rank = {"GO": 0, "NO": 1, "—": 2}
    df["_r"] = df["Decision"].astype(str).map(lambda s: rank.get(s, 2))
    df["_rsi"] = pd.to_numeric(df["RSI"], errors="coerce").fillna(999)
    df = df.sort_values(["_r", "_rsi", "Ticker"]).drop(columns=["_r", "_rsi"]).reset_index(drop=True)

    q = str(st.session_state.get("leap_f_tkr", "")).strip().upper()
    view = df
    if st.session_state.get("leap_f_setup"):
        view = view[view["Setup"].astype(str).str.startswith("✓")]
    if st.session_state.get("leap_f_go"):
        view = view[view["Decision"].astype(str) == "GO"]
    if q:
        view = view[view["Ticker"].astype(str).str.upper().str.contains(q, na=False)]

    st.caption(f"Showing **{len(view)}** of {len(df)} rows")
    st.markdown(_scan_html(view, c), unsafe_allow_html=True)
    st.download_button("Download CSV", df.to_csv(index=False).encode(), "leap_scan.csv", "text/csv")
