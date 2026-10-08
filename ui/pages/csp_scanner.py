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

from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from logic import csp_pricing
from logic import csp_setup
from logic import hm_signal as hm
from logic import leap_setup
from services import gsheet, option_chain, screeners, yahoo
from ui import state
from ui.fundamentals_cache import fund_row as _fund_row

_DEFAULT_TYPES = ["01-Growth", "01-Core", "02-Alternate", "03-Speculation", "04-Scanner"]
_VETO_DTE = 30

# Column order (Jigar's layout): identity → pricing → signal → context.
# Price(current) → Strike → Cushion(% below current) → 3mo↓(% below 3-month high).
_COLS = ["Ticker", "Type", "Setup", "Price", "Strike", "Cushion", "3mo ↓", "Δ",
         "Prem", "AOR", "IV", "IV/RV", "RSI", "BB", "MACD", "Chg%", "% off High", "Off4mo",
         "Quality", "HM", "Earnings", "Pos", "Financials", "Cash", "Trend", "P/E", "Industry",
         "Name", "Note"]


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
    """Ryan's Principle 1 — uptrend over the past 1.5 years, from the SAME 2y history
    (no extra fetch). 1.5yr SMA (≈375 trading days) + its 3-month slope:
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
    if len(close) < 438:                       # need 375 (1.5yr MA) + 63 (3mo slope) clean bars
        return "new"
    sma = close.rolling(375).mean()
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


def _card_header(c: dict, title: str, sub: str) -> None:
    """Stage-card header — bold numbered title + muted one-line description."""
    st.markdown(
        f"<div style='font-weight:800;font-size:13px;color:{c['text']};margin:-2px 0 6px'>"
        f"{title} <span style='color:{c['muted']};font-weight:400'>— {sub}</span></div>",
        unsafe_allow_html=True)


def _chips_html(cells: list) -> str:
    """Summary badge row — list of (label, color); None cells skipped."""
    row = "<div style='display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:8px 0;'>"
    for cell in cells:
        if not cell:
            continue
        lbl, col = cell
        row += (f"<span style='background:{col}18;color:{col};border:1px solid {col}44;"
                f"border-radius:6px;padding:2px 9px;font-size:12px;font-weight:700;'>{lbl}</span>")
    return row + "</div>"


def _stage1_scan(rows: list, target_iso: str, c: dict) -> pd.DataFrame:
    """Stage 1 — the cheap narrowing pass. Per (ticker, sector): tradability (weekly
    options via the expiry LIST only) + RSI / BB / Chg% + 1.5yr Trend + % off High, all
    from one 2y history pull. No chain pricing, no fundamentals — that heavy quality work
    waits for the 💎 Quality step on the (filtered) shortlist. The summary badges update
    live (cheap HTML, no iframe) so the scan shows real progress, not a dead bar."""
    tmap = {"weekly": "✓ weekly", "monthly": "monthly", "none": "no-opt"}
    out = []
    badge = st.empty()
    prog = st.progress(0, text="Searching — tradability + technicals…")
    n = len(rows)
    n_week = n_mon = n_none = 0
    for i, (t, sector) in enumerate(rows):
        prog.progress(i / max(n, 1), text=f"[{i + 1}/{n}] {t}")
        status = option_chain.expiry_status(t, target_iso, _WEEKLY_TOL_DAYS)
        n_week += status == "weekly"
        n_mon += status == "monthly"
        n_none += status == "none"
        badge.markdown(_chips_html([
            (f"{i + 1} / {n} scanned", c["muted"]), (f"{n_week} tradable", c["pos"]),
            (f"{n_mon} monthly", c["amber"]) if n_mon else None,
            (f"{n_none} no-opt", c["muted"]) if n_none else None]), unsafe_allow_html=True)
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
    badge.empty()
    return pd.DataFrame(out, columns=_S1COLS)


_S1_DISPLAY = ["Ticker", "Sector", "Price", "Trend", "Chg%", "Off High",
               "RSI", "BB", "P/E", "Financials", "Cash",
               "Strike", "Disc%", "Expiry", "Δ", "Prem", "AOR", "IV", "Industry"]


def _stage1_grid(view: pd.DataFrame, c: dict, cols: list | None = None) -> None:
    """Themed, click-to-sort grid — native st.dataframe ignores the app theme and renders
    dark, so we emit our own compact HTML table (in a components iframe) that follows the
    Grey/any theme, with JS header-sort. Numeric columns sort numerically (blanks last);
    Trend / Chg% / RSI / BB / P/E / Cash / AOR carry the cockpit's colors. `cols` is the
    column order to show (defaults to the base set; Stage-3 adds the option columns)."""
    import html as _html
    cols = cols or _S1_DISPLAY
    # Keep EqAssets/IsFinancial alongside the shown columns — the Cash cell reads them
    # to show equity/assets for financials instead of (meaningless) net cash.
    df = view.reindex(columns=list(cols) + ["EqAssets", "IsFinancial"]).copy()
    num_cols = {"Price", "Chg%", "Off High", "RSI", "P/E", "Cash",
                "Strike", "Disc%", "Δ", "Prem", "AOR", "IV"}
    left_cols = {"Ticker", "Sector", "Industry", "Financials"}
    for col in num_cols:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    def disp(col, v):
        if col in num_cols:
            if pd.isna(v):
                return "—"
            if col == "Price":    return f"${v:,.2f}"
            if col == "Chg%":     return f"{v:+.1f}%"
            if col == "Off High": return f"{v:.0f}%"
            if col == "RSI":      return f"{v:.0f}"
            if col == "P/E":      return f"{v:.1f}"
            if col == "Cash":     return f"+${v:.1f}B" if v >= 0 else f"−${abs(v):.1f}B"
            if col == "Strike":   return f"${v:,.0f}"
            if col == "Disc%":    return f"{v:.1f}%"
            if col == "Prem":     return f"${v:.2f}"
            if col == "Δ":        return f"{v:.2f}"
            if col == "AOR":      return f"{v:.0f}%"
            if col == "IV":       return f"{v:.0f}%"
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        s = str(v).strip()
        return s if s and s.lower() not in ("nan", "none") else "—"

    def sortkey(col, v):
        if col in num_cols:
            return "" if pd.isna(v) else f"{float(v):.6f}"
        return disp(col, v).lower()

    def cash_cell(r):
        """Financials → 'X.X% eq' (equity/assets); everyone else → net cash '$B'.
        Same column, unit suffix so the two solvency measures never blur."""
        eq = r.get("EqAssets")
        if bool(r.get("IsFinancial")) and eq is not None and not pd.isna(eq):
            return f"{float(eq):.1f}% eq", f"{float(eq):.6f}", f"color:{c['mid']};font-weight:700"
        v = r.get("Cash")
        if v is None or pd.isna(v):
            return "—", "", ""
        d = f"+${v:.1f}B" if v >= 0 else f"−${abs(v):.1f}B"
        return d, f"{float(v):.6f}", f"color:{c['pos'] if v >= 0 else c['neg']};font-weight:700"

    def cell_style(col, v):
        if col == "Ticker":
            return f"font-weight:800;color:{c['text']}"
        if col == "Trend":
            s = str(v)
            tc = (c["pos"] if s.startswith("▲") else c["neg"] if s.startswith("▼")
                  else c["amber"] if s.startswith("◆") else c["muted"])
            return f"color:{tc};font-weight:700"
        if col == "Chg%":
            return "" if pd.isna(v) else f"color:{c['pos'] if v > 0 else c['neg']};font-weight:700"
        if col == "RSI":
            if pd.isna(v):
                return ""
            if v > 64:
                return f"color:{c['neg']};font-weight:700"
            if v <= 45:
                return f"color:{c['pos']};font-weight:700"
            return ""
        if col == "BB":
            low = str(v).lower()
            if "lower" in low or "below" in low:
                return f"color:{c['pos']}"
            if "upper" in low or "above" in low:
                return f"color:{c['neg']}"
            return ""
        if col == "P/E":
            return f"color:{c['amber']};font-weight:700" if (not pd.isna(v) and (v <= 0 or v > 100)) else ""
        if col == "Cash":
            return "" if pd.isna(v) else f"color:{c['pos'] if v >= 0 else c['neg']};font-weight:700"
        if col == "AOR":
            return "" if pd.isna(v) else f"color:{c['pos']};font-weight:800"
        if col == "IV":
            return f"color:{c['amber']};font-weight:700" if (not pd.isna(v) and v >= 45) else ""
        return ""

    ths = ""
    for col in cols:
        align = "left" if col in left_cols else "right"
        num = "1" if col in num_cols else "0"
        ths += (f"<th data-num='{num}' style='text-align:{align}'>"
                f"{_html.escape(col)}<span class='ar'></span></th>")
    trs = ""
    for _, r in df.iterrows():
        tds = ""
        for col in cols:
            v = r[col]
            align = "left" if col in left_cols else "right"
            if col == "Cash":
                d_s, k_s, st_s = cash_cell(r)
            else:
                d_s, k_s, st_s = disp(col, v), sortkey(col, v), cell_style(col, v)
            tds += (f"<td data-v=\"{_html.escape(k_s)}\" "
                    f"style='text-align:{align};{st_s}'>{_html.escape(d_s)}</td>")
        trs += f"<tr>{tds}</tr>"

    head_bg, row_bg, bd, txt = c["raised"], c["panel"], c["border"], c["text"]
    doc = f"""<!doctype html><html><head><meta charset='utf-8'><style>
      *{{box-sizing:border-box}}
      body{{margin:0;background:{c['bg']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
      .wrap{{max-height:520px;overflow:auto;border:1px solid {bd};border-radius:8px}}
      table{{border-collapse:separate;border-spacing:0;width:100%;font-size:11.5px;font-variant-numeric:tabular-nums}}
      th,td{{padding:3px 9px;white-space:nowrap;border-bottom:1px solid {bd};color:{txt}}}
      thead th{{position:sticky;top:0;z-index:2;background:{head_bg};color:{txt};font-weight:700;
               cursor:pointer;user-select:none;padding:6px 9px;font-size:11px}}
      thead th:hover{{color:{c['accent']}}}
      tbody tr{{background:{row_bg}}}
      tbody tr:hover{{background:{c['nav_hover']}}}
      .ar{{color:{c['accent']};font-weight:800}}
    </style></head><body>
      <div class='wrap'><table id='g'>
        <thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>
      <script>
      (function(){{
        var t=document.getElementById('g'),tb=t.tBodies[0],hs=t.querySelectorAll('th'),cur=-1,asc=true;
        hs.forEach(function(th,i){{th.addEventListener('click',function(){{
          asc=(cur===i)?!asc:true;cur=i;var num=th.dataset.num==='1';
          var rs=[].slice.call(tb.querySelectorAll('tr'));
          rs.sort(function(a,b){{
            var x=a.children[i].dataset.v,y=b.children[i].dataset.v;
            if(num){{var nx=x===''?NaN:+x,ny=y===''?NaN:+y;
              if(isNaN(nx)&&isNaN(ny))return 0;if(isNaN(nx))return 1;if(isNaN(ny))return -1;
              return asc?nx-ny:ny-nx;}}
            return asc?x.localeCompare(y):y.localeCompare(x);}});
          rs.forEach(function(r){{tb.appendChild(r);}});
          hs.forEach(function(h){{h.querySelector('.ar').textContent='';}});
          th.querySelector('.ar').textContent=asc?' ▲':' ▼';
        }});}});
      }})();
      </script>
    </body></html>"""
    components.html(doc, height=540, scrolling=False)


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

    # ── Card ② — Quality filter: narrow the tradable list, then 💎 score it ──
    with st.container(border=True):
        _card_header(c, "② Quality filter", "narrow the tradable list on Price / Trend / "
                     "Financials, then 💎 score what's left")
        g1, g2, g3, g4, g5 = st.columns([0.9, 1.2, 0.8, 0.8, 1.7])
        with g1:
            max_rsi = st.number_input("Max RSI", 0, 100, 100, step=5, key="s1_rsi")
        with g2:
            chg = st.selectbox("Change", ["Any", "Down today", "Down > 2%", "Up today"], key="s1_chg")
        with g3:
            min_px = st.number_input("Min $", 0, 100000, 0, step=5, key="s1_pmin")
        with g4:
            max_px = st.number_input("Max $", 0, 100000, 0, step=5, key="s1_pmax", help="0 = no max")
        with g5:
            trend_sel = st.multiselect("Trend", ["▲ Up", "◆ Mixed", "▼ Down", "new"],
                                        default=[], key="s1_trend", placeholder="All trends",
                                        help="Ryan #1 — keep only the trends you want (▲ Up = uptrend over "
                                             "~1.5 years; never wheel a falling knife). Empty = all trends.")

        view = s1[s1["Tradable"].astype(str).str.contains("weekly")].copy()   # tradable only
        if trend_sel and "Trend" in view:
            view = view[view["Trend"].astype(str).isin(trend_sel)]
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

        # Financials filter (ALWAYS visible) + 💎 Quality button on one row. The filter
        # only bites once Quality has run (the badges don't exist before that).
        fg, bg = st.columns([3.2, 1.5])
        with fg:
            fin_sel = st.multiselect(
                "Financials must pass", ["Rev", "Inc", "CF", "FCF", "A>L"], default=[],
                key="s1_fin", placeholder="Any financials — applies after 💎 Quality",
                help="Keep only names whose selected checks are ✅ — Rev up · Net income >0 · "
                     "Op cash flow >0 (TTM) · Free cash flow >0 (TTM) · Assets > Liabilities. "
                     "Takes effect once Quality has scored the list.")
        with bg:
            st.write("")
            load_q = st.button(f"💎 Quality  ({len(view)})", type="primary",
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
        # Industry = Yahoo's broad sector (Technology); Sector = short thematic
        # bucket from Yahoo's industry (Chips). Overwrites the FinViz sector with
        # the Yahoo-sourced theme once Quality has run.
        view["Industry"] = view["Ticker"].map(lambda t: _safe_fund(t, "Sector"))
        view["Sector"] = view["Ticker"].map(
            lambda t: _safe_fund(t, "Theme")).fillna(view["Sector"])
        # For financials the Cash cell shows equity/assets instead of (meaningless) net cash.
        view["EqAssets"] = view["Ticker"].map(lambda t: _safe_fund(t, "EqAssets"))
        view["IsFinancial"] = view["Ticker"].map(lambda t: bool(_safe_fund(t, "IsFinancial")))
        # Financials filter — tokens are space-separated so FCF never matches CF.
        if fin_sel:
            def _fin_pass(s):
                toks = set(str(s).split())
                return all(f"{chk}✅" in toks for chk in fin_sel)
            view = view[view["Financials"].map(_fin_pass)]

    # ── Card ③ — Option chain: ⛓ price the shortlist (Strike · Δ · Prem · AOR · IV) ──
    # Prices ONLY the current (filtered) shortlist, exactly like 💎 Quality. DTE selectable
    # (default 21); Δ is the cap (richest put with |Δ| ≤ Δ). Scanned params freeze in session
    # so changing DTE/Δ doesn't re-hit chains until you press ⛓ again.
    with st.container(border=True):
        _card_header(c, "③ Option chain", "price the shortlist at your DTE / Δ, then filter "
                     "on Min AOR — the slow step, so filter hard in ② first")
        oc1, oc2, oc3, oc4 = st.columns([0.9, 0.9, 0.9, 1.7])
        with oc1:
            opt_dte = st.number_input("DTE", 5, 90, 23, step=1, key="s1_dte",
                                      help="Target days to expiry — snaps to the nearest weekly. Default 23.")
        with oc2:
            opt_delta = st.number_input("Max Δ", 0.05, 0.60, 0.40, step=0.05, key="s1_delta",
                                        help="Delta CAP — the richest real put with |Δ| ≤ this, never over "
                                             "(e.g. 0.40 → NVDA 230 @ Δ0.33, since 235 is Δ0.44).")
        with oc3:
            min_aor = st.number_input("Min AOR %", 0, 200, 0, step=5, key="s1_minaor",
                                      help="Keep only names with AOR ≥ this (applies after the chain "
                                           "scan). 0 = no filter.")
        with oc4:
            st.write("")
            load_opt = st.button(f"⛓ Chain  ({len(view)})", type="primary",
                                 use_container_width=True, disabled=view.empty, key="s1_loadopt",
                                 help="Price the filtered shortlist at your DTE/Δ — adds "
                                      "Strike · Expiry · Δ · Prem · AOR · IV.")
    if load_opt:
        e_iso = (date.today() + timedelta(days=int(opt_dte))).isoformat()
        st.session_state["s1_opt_params"] = (e_iso, float(opt_delta))
        tk = list(view["Ticker"])
        prog = st.progress(0, text="⛓ Option chain…")
        for i, t in enumerate(tk):
            prog.progress(i / max(len(tk), 1), text=f"[{i + 1}/{len(tk)}] {t}")
            _opt_leg(t, e_iso, float(opt_delta))           # warm the 10m cache
        prog.empty()
        st.session_state["s1_opt_on"] = True
        st.rerun()
    # The option columns are always shown (like P/E · Financials · Cash) — blank until the
    # ⛓ Chain scan fills them for the filtered shortlist.
    opt_cols = ["Strike", "Disc%", "Expiry", "Δ", "Prem", "AOR", "IV"]
    show_opt = (st.session_state.get("s1_opt_on") and st.session_state.get("s1_opt_params")
                and not view.empty)
    if show_opt:
        e_iso, dl = st.session_state["s1_opt_params"]
        legs = {t: _opt_leg(t, e_iso, dl) for t in view["Ticker"]}      # cache hits
        for col in opt_cols:
            view[col] = view["Ticker"].map(lambda t, _c=col: legs.get(t, {}).get(_c))
        # Min-AOR filter — only meaningful once chains are priced. Drops names whose
        # best put (at your Δ cap) can't clear the yield you want.
        if min_aor > 0:
            view = view[pd.to_numeric(view["AOR"], errors="coerce").fillna(-1) >= min_aor]

    st.markdown(_chips_html([
        (f"{n_total} scanned", c["muted"]), (f"{n_weekly} tradable", c["pos"]),
        (f"{n_monthly} monthly", c["amber"]) if n_monthly else None,
        (f"{n_noopt} no-opt", c["muted"]) if n_noopt else None,
        (f"{len(view)} shortlist", c["accent"])]), unsafe_allow_html=True)

    st.caption("**Click any column header to sort.** Filter → **💎 Quality** (P/E · Financials · "
               "Cash) → **⛓ Chain** (Strike · Δ · Prem · AOR · IV) → add the winners to your "
               "WatchList sheet. The Decision Desk works the WatchList.")
    _stage1_grid(view, c)

    export = view.reindex(columns=_S1_DISPLAY + (["EqAssets"] if "EqAssets" in view else []))
    st.download_button("⬇ Download CSV", export.to_csv(index=False).encode(),
                       "candidates.csv", "text/csv", key="s1_csv")


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

    # ONE discovery surface — find quality companies to add to the WatchList. No tabs:
    # discovery (this page) and execution (the Decision Desk, which prices the WatchList)
    # are deliberately separate, so the Scanner's only job is sourcing new names.
    _tab_discovery(c, ctx)


_DISC_SOURCES = ["FinViz — full universe", "Yahoo — Most Active", "Yahoo — Day Losers"]


def _tab_discovery(c: dict, ctx: dict) -> None:
    """Discovery — surface quality companies to ADD to the WatchList, then the Decision
    Desk prices them. Source = FinViz (the full ~915 screen, sector-filterable, sector
    free from the scrape) or a live Yahoo screen (Most Active / Day Losers). Narrow →
    tradability + 1.5yr Trend + RSI/BB/Chg%; then 💎 Quality → P/E · Financials · Cash.
    No option-chain pricing here — that lives at the Decision Desk."""
    exps, labels, today = ctx["exps"], ctx["labels"], ctx["today"]
    # Weekly-tradability target (~21 DTE). No picker — discovery only needs "has weeklies
    # at the horizon I wheel," and that's stable week to week. The specific contract/date
    # is chosen at the Decision Desk, which prices the WatchList.
    exp = exps[1]
    with st.expander("①  Search — source & universe", expanded=True):
        # Sectors wide on the left; Source + 🔎 Search on one small line, right.
        left, right = st.columns([3.9, 1.15])
        with right:
            rs, rb = st.columns([2.0, 1.0])
            with rs:
                source = st.selectbox("Source", _DISC_SOURCES, key="disc_src",
                                      help="Where new names come from. FinViz = the full ~915 "
                                           "screen (sector-filterable); Yahoo = today's live movers.")
            with rb:
                # Match the selectbox's label row so the button aligns with the Source box.
                st.markdown("<div style='font-size:0.875rem;margin-bottom:0.25rem;"
                            "line-height:1.6'>Search</div>", unsafe_allow_html=True)
                run = st.button("🔎", type="primary", use_container_width=True,
                                help="Search — drops non-tradable names and shows "
                                     "Trend · Price · Chg% · RSI · BB.")
        is_fv = source.startswith("FinViz")
        if is_fv:
            fv_rows = _finviz_rows("FinViz 1-1200")             # the whole screen (~915)
            all_secs = sorted({s for _, s in fv_rows if s})
            with left:
                picked = st.multiselect("Sectors", all_secs, default=all_secs, key="fv_secs",
                                        help="Free, no Yahoo calls — narrow before the tradability check.")
            rows = [(t, s) for t, s in fv_rows if (not picked or s in picked)]
            st.caption(f"Universe **{len(fv_rows)}** → **{len(rows)}** after sector filter. "
                       f"Search checks tradability + Trend + RSI/BB/Chg%, drops monthly-only.")
        else:
            with left:
                n = st.slider("How many", 25, 300, 150, step=25, key="disc_n",
                              help="Names pulled from the live Yahoo screen.")
            rows = [(t, "") for t in _screen_source(
                "Yahoo Day Losers" if "Day Losers" in source else "Yahoo Most Active", n)]
            st.caption(f"**{len(rows)}** names from {source}. "
                       f"Search checks tradability + Trend + RSI/BB/Chg%, drops monthly-only.")
            if not rows:
                st.warning(f"{source} returned no names (Yahoo is likely rate-limiting). "
                           "Try again in a moment, lower the count, or use FinViz.")

    meta = {"cat_map": ctx["cat_map"], "exp_iso": exp.isoformat(), "label": labels[exp],
            "aor": 30.0, "delta": 0.30, "vix": ctx["vix"], "dte": (exp - today).days}
    if run and rows:
        df1 = _stage1_scan(rows, exp.isoformat(), c)
        st.session_state["csp_s1"], st.session_state["csp_s1_meta"] = df1, meta
        st.session_state["s1_qual_on"] = False             # a fresh search clears old quality
        st.session_state["s1_opt_on"] = False              # …and the old option scan
        state.save_stage1(df1, meta)                       # persist so it survives navigation
        st.rerun()
    s1, s1_meta = state.load_stage1()
    if s1 is None:
        st.info("Pick a source and hit **🔎 Search** — it drops non-tradable names and shows "
                "Trend · Price · Chg% · RSI · BB. Then filter + **💎 Quality detail**, and add the "
                "winners to your WatchList. The **Decision Desk** works the WatchList.")
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


@st.cache_data(ttl=600, show_spinner=False)   # 10m — option quotes move intraday
def _opt_leg(t: str, target_iso: str, delta: float) -> dict:
    """Stage-3 option leg for the scanner: the richest real put with |Δ| ≤ `delta`
    (a CAP — never over the delta you set) at the expiry nearest target_iso. With a
    coarse yfinance grid this is the highest-delta strike still under the cap (e.g. NVDA
    230 @ Δ0.33 when 235 is Δ0.44). Returns RAW numbers (so the grid sorts numerically)
    plus the snapped expiry — Strike · Disc% · Expiry · Δ · Prem · AOR · IV. Empty dict
    when the chain can't be priced (not optionable / no weekly / no tradeable OTM put)."""
    try:
        ch = option_chain.load_puts_at(t, target_iso, tol_days=_WEEKLY_TOL_DAYS)
        if ch.get("no_options") or ch.get("no_weekly"):
            return {}
        spot, dte = ch.get("spot"), ch.get("dte")
        puts, exp = ch.get("puts") or [], ch.get("expiry")
        if not puts or not spot or not dte:
            return {}
        pick = csp_pricing.pick_by_delta(puts, spot, dte, delta)   # |Δ| ≤ delta cap
        if not pick:
            return {}
        iv = _atm_iv(puts, spot) or pick.get("iv")
        d = pick.get("delta")
        disc = (spot - float(pick["strike"])) / spot * 100 if spot else None   # strike below spot
        return {
            "Strike": float(pick["strike"]),
            "Disc%": round(disc, 1) if disc is not None else None,
            "Expiry": exp,
            "Δ": round(abs(d), 2) if d is not None else None,
            "Prem": round(float(pick["premium"]), 2),
            "AOR": round(pick["aor"], 0) if pick.get("aor") is not None else None,
            "IV": round(iv * 100, 1) if iv else None,
        }
    except Exception:
        return {}


def watchlist_types() -> list:
    """The WatchList stock-type buckets (e.g. 01-Growth, 02-Alternate, 03-Speculation)
    for the Decision Desk's type picker."""
    types, _ = gsheet.watchlist_by_type()
    return [t for t in types if t != "All"]


def default_hunt_inputs(types: list | None = None, min_dte: int = 22) -> dict | None:
    """WatchList hunt inputs for the Decision Desk's ▶ Run — the Decision Desk always runs
    the WatchList (never a Scanner result). `types` picks the buckets (default Growth/Alt/
    Spec). Prices the first weekly expiry ≥ `min_dte` DTE, AOR 30, Δ 0.30. None if the
    WatchList/expiry list is empty."""
    _, by_type = gsheet.watchlist_by_type()
    cat_map = {tk: t for t, ts in by_type.items() if t != "All" for tk in ts}
    want = types if types else _DEFAULT_TYPES
    chosen = [t for t in want if t in by_type] or [t for t in by_type if t != "All"][:1]
    stocks = sorted({tk for t in chosen for tk in by_type.get(t, [])})
    today = date.today()
    exps = csp_pricing.expiry_choices(today, int(min_dte))
    if not stocks or not exps:
        return None
    exp = exps[1] if len(exps) > 1 else exps[0]        # matches the scanner's default (index=1)
    return {"stocks": stocks, "cat_map": cat_map, "exp_iso": exp.isoformat(),
            "label": f"{exp:%b %d} ({(exp - today).days}d)", "aor": 30.0, "delta": 0.30,
            "vix": _current_vix(), "dte": (exp - today).days}


def run_hunt(inp: dict, to_desk: bool = True, c: dict | None = None) -> None:
    """Run the scan for `inp` and stash the result.

    to_desk=True (the Decision Desk's ▶ Run) stores it in the shared hunt store that the
    Decision Desk reads. to_desk=False (the Candidate Scanner's own exploration) keeps it
    in a SEPARATE scanner slot, so discovery never overwrites the daily WatchList run —
    the two tools are fully independent."""
    scan_df = _scan(inp["stocks"], inp["cat_map"], inp["exp_iso"], inp["aor"], inp["delta"],
                    inp["vix"], c=c)
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
          target_delta: float, vix: float | None = None, c: dict | None = None) -> pd.DataFrame:
    """Price the WatchList. PARALLEL (bounded thread pool — the work is network-bound, so
    threads cut the run 3-5×) and LIVE: when a theme `c` is passed, the result table grows
    in place as each name completes, so you watch results stream in instead of waiting.
    Streamlit's script context is attached to the workers so st.cache_data stays correct
    on Streamlit Cloud."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:                                               # attach ctx so cache works in threads
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        _ctx = get_script_run_ctx()
    except Exception:
        add_script_run_ctx, _ctx = None, None
    iv_map, pos_map = _sheet_maps()
    today = date.today()

    def _one(t):
        try:
            hist = yahoo.get_history(t, period="2y", interval="1d")
            if hist.empty or "Close" not in hist.columns or len(hist) < 30:
                return {"Ticker": t, "Type": cat_map.get(t, ""), "Setup": "—",
                        "Quality": "—", "Note": "no price data"}
            lr = leap_setup.evaluate(hist)
            # Price the ~target-delta put FIRST — its own IV (at the strike/expiry we trade)
            # is the IV we show and that feeds the IV Drop trigger; ATM-chain IV is fallback.
            leg = _price_leg(t, target_iso, target_delta)
            if leg.get("excluded"):
                return {"Ticker": t, "Type": cat_map.get(t, ""), "Setup": "—",
                        "Quality": "—", "Industry": "—", "Note": leg["excluded"]}
            iv_pct = leg.get("iv") or yahoo.get_atm_iv(t, lr.get("price"))
            # Realized vol (annualised, ~21d) vs IV. IV ≫ RV = the option is pricing an EVENT.
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
            fin = _fund_row(t)                             # before evaluate — Quality Pullback needs it
            _fstr = str(fin.get("Financials", ""))         # 'Rev✅ Inc✅ CF✅ FCF✅ A>L✅'
            _fin_ok = ("Rev✅" in _fstr) and ("Inc✅" in _fstr) and ("FCF✅" in _fstr)
            cs = csp_setup.evaluate(lr, iv_pct, chg, earnings_days=edays, vix=vix, fin_ok=_fin_ok)
            hv = hm.latest_signal(hm.analyze(hist.rename(columns=str.lower)))
            r14 = lr.get("rsi14")
            disc3 = None                               # strike vs 3-month high (~63 trading days)
            try:
                hi3m = float(hist["Close"].tail(63).max())
                sk = float(str(leg["Strike"]).replace("$", "").replace(",", ""))
                if hi3m > 0 and sk > 0:
                    disc3 = (hi3m - sk) / hi3m * 100
            except (TypeError, ValueError):
                disc3 = None
            off4 = None                                # current price vs 4-month high (~84 bars)
            try:
                hcol = "High" if "High" in hist.columns else "Close"
                hi4 = float(hist[hcol].tail(84).max())
                curp = float(lr.get("price") or hist["Close"].iloc[-1])
                if hi4 > 0:
                    off4 = (hi4 - curp) / hi4 * 100
            except (TypeError, ValueError):
                off4 = None
            vetoed = bool(cs.get("earnings_veto"))
            return {
                "Ticker": t, "Type": cat_map.get(t, ""),
                "Industry": fin.get("Industry", "") or "—",
                "Setup": (f"✓ {' · '.join(cs['setups'])}" if cs.get("setup_ok") else "—"),
                "Quality": "✓" if cs.get("quality_ok") else "—",
                "RSI": f"{r14:.0f}" if r14 is not None else "—",
                "BB": lr.get("bb_pos", "—"),
                "%B": lr.get("bb_pct"),                 # 0-100 position in the band (precise vs the label)
                "Chg%": round(chg, 2) if chg is not None else None,
                "IV": f"{iv_pct:.0f}%" if iv_pct else "—",
                "Strike": leg["Strike"], "Cushion": leg["Cushion"],
                "3mo ↓": f"{disc3:.1f}%" if disc3 is not None else "—",
                "Δ": leg["Δ"], "Prem": leg["Prem"], "AOR": leg["AOR"],
                "IV/RV": round(iv_rv, 2) if iv_rv is not None else None,
                "HM": hv.get("signal", "—"), "MACD": lr.get("macd_dir", "—"),
                "Price": round(lr["price"], 2) if lr.get("price") is not None else None,
                "% off High": round(lr["off_high_pct"], 1) if lr.get("off_high_pct") is not None else None,
                "Off4mo": round(off4, 1) if off4 is not None else None,
                "Earnings": (("⛔ " if vetoed else "") + f"{earn:%m/%d} ({edays}d)") if earn else "unknown",
                "Pos": pos_map.get(t, ""), "Financials": fin.get("Financials", ""),
                "Cash": fin.get("Cash"), "Trend": _trend_15y(hist),
                "P/E": fin.get("P/E"), "Name": fin.get("Name", ""), "Note": "",
            }
        except Exception as e:                         # one bad name never kills the run
            return {"Ticker": t, "Type": cat_map.get(t, ""), "Setup": "—",
                    "Quality": "—", "Note": f"error: {type(e).__name__}"}

    n = len(stocks)
    prog = st.progress(0, text="Scanning…")
    live = st.empty() if c is not None else None
    rows = []
    _init = (lambda: add_script_run_ctx(threading.current_thread(), _ctx)) \
        if (add_script_run_ctx and _ctx) else None
    with ThreadPoolExecutor(max_workers=6, initializer=_init) as ex:   # bounded: no rate-limit
        futs = [ex.submit(_one, t) for t in stocks]
        for i, fut in enumerate(as_completed(futs)):
            rows.append(fut.result())
            done = i + 1
            prog.progress(done / max(n, 1), text=f"Scanning… {done}/{n}")
            if live is not None and (done % 3 == 0 or done == n):   # grow the table live
                dfl = pd.DataFrame(rows, columns=_COLS).sort_values(
                    "AOR", key=lambda s: pd.to_numeric(s, errors="coerce"),
                    ascending=False, na_position="last")
                live.markdown(scan_table_html(dfl, c, target_iso, scanning=f"{done}/{n}"),
                              unsafe_allow_html=True)
    prog.empty()
    if live is not None:
        live.empty()
    return pd.DataFrame(rows, columns=_COLS)


# (display label, source column in the scan df) — "__exp__" is filled with the hunt expiry.
_SCAN_VIEW = [("Ticker", "Ticker"), ("Setup", "Setup"), ("Type", "Type"), ("Price", "Price"),
              ("Chg%", "Chg%"), ("Strike", "Strike"), ("Disc%", "Cushion"), ("Off High", "% off High"),
              ("4mo↓", "Off4mo"), ("RSI", "RSI"), ("BB", "BB"), ("MACD", "MACD"),
              ("Earnings", "Earnings"), ("Δ", "Δ"), ("Prem", "Prem"), ("AOR", "AOR"),
              ("Expiry", "__exp__"), ("Trend", "Trend"), ("HM", "HM"), ("Financials", "Financials"),
              ("P/E", "P/E"), ("IV", "IV"), ("Industry", "Industry"),
              ("Company", "Name")]
_SCAN_RIGHT = {"Price", "Chg%", "Strike", "Disc%", "Off High", "4mo↓", "Δ", "Prem", "AOR", "P/E", "IV"}
_SCAN_CENTER = {"RSI", "MACD", "Trend"}


def scan_table_html(df, c: dict, expiry: str = "—", scanning: str | None = None) -> str:
    """Table 2 — the full scan result: every scanned name, all columns, themed. Plain
    st.markdown HTML (no JS) so it can grow live during the scan without iframe flicker."""
    import html as _h
    if df is None or getattr(df, "empty", True):
        return ""

    def _n(v):
        try:
            return float(str(v).replace("%", "").replace("$", "").replace(",", ""))
        except (TypeError, ValueError):
            return None

    def _cell(label, src, row):
        v = expiry if src == "__exp__" else row.get(src)
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "None"):
            return "—", f"color:{c['muted']}"
        s = str(v)
        if label == "Ticker":   return s, f"font-weight:800;color:{c['text']}"
        if label == "Price":    x = _n(v); return (f"${x:,.2f}" if x is not None else s), ""
        if label == "Chg%":
            x = _n(v)
            return (f"{x:+.1f}%" if x is not None else s), \
                (f"color:{c['pos'] if x>0 else c['neg'] if x<0 else c['muted']};font-weight:700" if x is not None else "")
        if label == "Off High": x = _n(v); return (f"{x:.0f}%" if x is not None else s), ""
        if label == "4mo↓":
            x = _n(v)
            return (f"{x:.1f}%" if x is not None else s), (f"color:{c['pos']};font-weight:700" if (x is not None and x >= 20) else "")
        if label == "AOR":
            x = _n(v)
            if x is None:
                return s, ""
            col = c["pos"] if x >= 50 else c["amber"] if x >= 45 else c["text"]
            return f"{x:.0f}%", f"color:{col};font-weight:{'800' if col != c['text'] else '600'}"
        if label == "IV":
            x = _n(v); return (f"{x:.0f}%" if x is not None else s), (f"color:{c['pos']};font-weight:700" if (x is not None and x >= 45) else "")
        if label == "P/E":
            x = _n(v); return (f"{x:.1f}" if x is not None else s), (f"color:{c['amber']};font-weight:700" if (x is not None and (x <= 0 or x > 100)) else "")
        if label == "RSI":
            x = _n(v)
            return (f"{x:.0f}" if x is not None else s), \
                ((f"color:{c['neg']};font-weight:700" if x > 64 else f"color:{c['pos']};font-weight:700" if x < 45 else "") if x is not None else "")
        if label == "BB":
            low = s.lower()
            col = c["pos"] if ("lower" in low or "below" in low) else c["neg"] if ("upper" in low or "above" in low) else ""
            pb = _n(row.get("%B"))                       # precise 0-100 position next to the label
            disp = f"{s} {pb:.0f}" if pb is not None else s
            return disp, (f"color:{col};font-weight:700" if col else "")
        if label == "Trend":
            col = c["pos"] if s.startswith("▲") else c["neg"] if s.startswith("▼") else c["amber"] if s.startswith("◆") else c["muted"]
            return s, f"color:{col};font-weight:700"
        if label == "Earnings": return s, (f"color:{c['neg']};font-weight:700" if "⛔" in s else "")
        if label in ("Type", "Industry"): return s, f"color:{c['muted']}"
        return s, ""

    def _al(label):
        return "center" if label in _SCAN_CENTER else ("right" if label in _SCAN_RIGHT else "left")

    head = "".join(
        f"<th style='position:sticky;top:0;z-index:2;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:6px 8px;text-align:{_al(l)};font-size:10.5px;"
        f"font-weight:700;white-space:nowrap'>{_h.escape(l)}</th>" for l, _ in _SCAN_VIEW)
    body = ""
    for _, row in df.iterrows():
        tds = ""
        for l, src in _SCAN_VIEW:
            disp, stl = _cell(l, src, row)
            base = (f"border:1px solid {c['border']};padding:4px 8px;white-space:nowrap;"
                    f"color:{c['text']};font-size:11px;text-align:{_al(l)};")
            stick = f"position:sticky;left:0;z-index:1;background:{c['panel']};" if l == "Ticker" else ""
            tds += f"<td style='{base}{stick}{stl}'>{_h.escape(disp)}</td>"
        body += f"<tr>{tds}</tr>"
    note = (f"<div style='font-size:11px;color:{c['muted']};padding:3px 2px'>⏳ Scanning… {scanning}</div>"
            if scanning else "")
    return (note + f"<div style='overflow:auto;max-height:620px;border:1px solid {c['border']};border-radius:8px'>"
            f"<table style='border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")

