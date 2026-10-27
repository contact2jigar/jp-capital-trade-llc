"""BB Reversion — lower-Bollinger mean-reversion entry scanner + history.

Signal (validated on 10 names, 3y): enter when the close pierces the LOWER band
(%B < 0) with RSI(14) below a threshold (default 40); exit when it reaches the
UPPER band (%B ≥ 1) — or a mid-band / N-day cap. Pooled +20d edge was 73% green /
+7.0% avg vs a 62% / +3.6% baseline. This is the framework's Path-B / Quality-
Pullback CSP entry, quantified. Caveat: the 3y window was bull-leaning — mean
reversion catches falling knives in a sustained downtrend, so pair with the Gates.
"""
from __future__ import annotations

from math import erf, exp, sqrt

import numpy as np
import pandas as pd
import streamlit as st

from services import gsheet
from ui.pages.stock_scope import _bars   # shared cached Yahoo OHLC loader


# ── ATM cash-secured-put economics (estimate) ─────────────────────────────────
# Black-Scholes ATM put priced off 20-day realized vol (IV proxy, NOT a live chain)
# for a ~30-DTE put. AOR = premium / strike annualized = the wheel's return metric.
_DTE = 30
def _ncdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))

def _rvol(closes: np.ndarray, win: int = 20) -> float:
    if len(closes) < win + 1:
        return 0.0
    rets = np.diff(np.log(closes[-(win + 1):]))
    return float(np.std(rets, ddof=0) * sqrt(252))

def _atm_put(S: float, sigma: float, dte: int = _DTE, r: float = 0.04) -> float:
    """Per-share ATM (K=S) put premium."""
    T = dte / 365
    if sigma <= 0 or T <= 0 or S <= 0:
        return 0.0
    d1 = (r + sigma * sigma / 2) * T / (sigma * sqrt(T))   # S == K
    d2 = d1 - sigma * sqrt(T)
    return S * exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)

def _atm_aor(S: float, sigma: float, dte: int = _DTE) -> tuple:
    prem = _atm_put(S, sigma, dte)
    aor = (prem / S) * (365 / dte) if S > 0 else 0.0
    return prem, aor


# ── indicators ────────────────────────────────────────────────────────────────
def _wilder(c: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up = np.clip(d, 0, None); dn = np.clip(-d, 0, None)
    ru = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().values
    rd = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().values
    rs = np.where(rd == 0, 100, ru / np.where(rd == 0, 1, rd))
    r = 100 - 100 / (1 + rs); r[:n] = np.nan
    return r


def _ind(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"].values
    sma = pd.Series(c).rolling(20).mean().values
    sd = pd.Series(c).rolling(20).std(ddof=0).values
    up, lo = sma + 2 * sd, sma - 2 * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        pctb = np.where((up - lo) > 0, (c - lo) / (up - lo), np.nan)
    macd = pd.Series(c).ewm(span=12, adjust=False).mean().values \
        - pd.Series(c).ewm(span=26, adjust=False).mean().values
    sig = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    d = df.copy()
    d["pctb"] = pctb
    d["rsi"] = _wilder(c, 14)
    d["mhist"] = macd - sig
    return d


# ── round-trip trades ─────────────────────────────────────────────────────────
def _trades(d: pd.DataFrame, rsi_thr: float, exit_pctb: float, cap: int,
            years: int = 3) -> list:
    c = d["close"].values; pb = d["pctb"].values; rs = d["rsi"].values
    idx = d.index; n = len(c)
    cutoff = idx[-1] - pd.DateOffset(years=years)
    out, i = [], 20
    while i < n:
        if idx[i] >= cutoff and pb[i] < 0 and rs[i] < rsi_thr:
            j = i + 1; xp = min(i + cap, n - 1); is_open = True
            while j <= min(i + cap, n - 1):
                if pb[j] >= exit_pctb:
                    xp = j; is_open = False; break
                j += 1
            if xp == n - 1 and is_open:          # ran out of bars → still open
                is_open = True
            else:
                is_open = False if pb[xp] >= exit_pctb else (xp >= n - 1)
            out.append({"entry": idx[i], "ep": float(c[i]), "rsi": rs[i], "pctb": pb[i],
                        "exit": idx[xp], "xp": float(c[xp]), "ret": c[xp] / c[i] - 1,
                        "days": (idx[xp] - idx[i]).days,
                        "open": is_open and pb[xp] < exit_pctb})
            i = xp + 1
        else:
            i += 1
    out.reverse()
    return out


# ── universe scan ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _scan(tickers: tuple, rsi_thr: float) -> list:
    rows = []
    for t in tickers:
        df = _bars(t)
        if df is None or len(df) < 40:
            continue
        d = _ind(df)
        last = d.iloc[-1]
        pb, rsi, mh = last["pctb"], last["rsi"], last["mhist"]
        if pd.isna(pb) or pd.isna(rsi):
            continue
        firing = pb < 0 and rsi < rsi_thr
        setup = (not firing) and pb < 0.15 and rsi < 50
        prem, aor = _atm_aor(float(last["close"]), _rvol(d["close"].values))
        rows.append({"t": t, "price": float(last["close"]), "pctb": float(pb),
                     "rsi": float(rsi), "mhist": float(mh), "prem": prem, "aor": aor,
                     "state": "FIRING" if firing else ("setup" if setup else "")})
    rows.sort(key=lambda r: (r["state"] != "FIRING", r["state"] != "setup", r["pctb"]))
    return rows


_CSS = """
<style>
.bbx{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px;margin:4px 0 14px;width:100%;max-width:720px}
.bbx th{text-align:right;color:#8a97a6;font-size:10px;font-weight:700;padding:5px 9px;border-bottom:1px solid #8a97a655;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap}
.bbx th:first-child{text-align:left}
.bbx td{text-align:right;padding:6px 9px;border-bottom:1px solid #8a97a618;white-space:nowrap}
.bbx td.l{text-align:left;font-weight:700}
.bbx tr:hover td{background:#8a97a614}
.bbx td.fire{color:#e0484e;font-weight:800}.bbx td.setup{color:#d98a1f;font-weight:700}
.bbx td.up{color:#2f9e52;font-weight:800}.bbx td.dn{color:#e0484e;font-weight:800}
.bbx td.cold{color:#3f86d6;font-weight:700}.bbx td.hot{color:#e0484e;font-weight:700}
</style>
"""


def _fmt(v, pct=False):
    if v is None or pd.isna(v):
        return "—"
    return f"{v*100:+.1f}%" if pct else f"{v:,.0f}"


def render(c: dict) -> None:
    st.markdown("#### ⤵️ BB Reversion — lower-band oversold entries")
    st.caption("Enter when the close pierces the **lower** Bollinger band (%B < 0) with "
               "RSI below the threshold · exit at the **upper** band. The framework's "
               "Path-B / Quality-Pullback CSP entry, quantified.")

    a, b, cc, dd = st.columns(4)
    rsi_thr = float(a.radio("RSI entry <", ["35", "40", "45"], index=1, horizontal=True,
                            key="bb_rsi"))
    exit_lab = b.radio("Exit at", ["Upper BB", "Mid BB"], index=0, horizontal=True,
                       key="bb_exit")
    exit_pctb = 1.0 if exit_lab == "Upper BB" else 0.5
    cap_lab = cc.radio("Max hold", ["40d", "60d", "None"], index=0, horizontal=True,
                       key="bb_cap", help="None = wait patiently to the upper band, "
                       "however long — the point of entering quality names.")
    cap = 100000 if cap_lab == "None" else int(cap_lab[:-1])
    yrs = int(dd.radio("Lookback", ["2y", "3y", "5y"], index=1, horizontal=True,
                       key="bb_years")[:-1])

    try:
        _, by = gsheet.watchlist_by_type()
        uni = by.get("All", [])
    except Exception:
        uni = []
    uni = ["QQQ", "SPY"] + [t for t in uni if t not in ("QQQ", "SPY")]

    # ── live scan ──
    st.markdown("##### 🔍 Scan — what's oversold right now")
    if st.button("Run scan across universe", key="bb_scan_btn") or st.session_state.get("bb_scanned"):
        st.session_state["bb_scanned"] = True
        with st.spinner(f"Scanning {len(uni)} names…"):
            rows = _scan(tuple(uni), rsi_thr)
        fire = [r for r in rows if r["state"] == "FIRING"]
        setup = [r for r in rows if r["state"] == "setup"]
        st.markdown(f"**{len(fire)} firing** (%B<0 · RSI<{rsi_thr:.0f})  ·  "
                    f"{len(setup)} setting up  ·  {len(rows)} scanned  ·  "
                    f"<span style='color:#8a97a6'>ATM = est. 30-DTE at-the-money put "
                    f"(realized-vol proxy, not a live chain)</span>", unsafe_allow_html=True)
        show = fire + setup if (fire or setup) else rows[:12]
        tr = []
        for r in show:
            scls = "fire" if r["state"] == "FIRING" else ("setup" if r["state"] == "setup" else "")
            stx = "● FIRING" if r["state"] == "FIRING" else ("○ setup" if r["state"] == "setup" else "—")
            rcls = "cold" if r["rsi"] <= 35 else ("hot" if r["rsi"] >= 70 else "")
            bbv = f'{r["pctb"]:.2f}'
            bcls = "cold" if r["pctb"] < 0 else ("hot" if r["pctb"] >= 1 else "")
            aor = r.get("aor", 0) * 100
            acls = "up" if aor >= 40 else ""
            tr.append(f'<tr><td class="l">{r["t"]}</td><td>${r["price"]:,.0f}</td>'
                      f'<td class="{bcls}">{bbv}</td><td class="{rcls}">{int(round(r["rsi"]))}</td>'
                      f'<td>${r.get("prem",0)*100:,.0f}</td><td class="{acls}">{aor:.0f}%</td>'
                      f'<td class="{scls}">{stx}</td></tr>')
        head = "".join(f"<th>{h}</th>" for h in
                       ["Ticker", "Price", "%B", "RSI", "ATM $", "ATM AOR", "State"])
        st.markdown(_CSS + f'<table class="bbx"><tr>{head}</tr>{"".join(tr)}</table>',
                    unsafe_allow_html=True)

    # ── ticker history ──
    st.markdown("##### 📜 History — round-trip trades (enter lower-BB → exit upper-BB)")
    pick = st.selectbox("Ticker", uni, index=(uni.index("COST") if "COST" in uni else 0),
                        key="bb_pick")
    df = _bars(pick)
    if df is None or df.empty:
        st.warning(f"No data for {pick}.")
        return
    d = _ind(df)
    trades = _trades(d, rsi_thr, exit_pctb, cap, years=yrs)
    if not trades:
        st.info(f"No lower-BB + RSI<{rsi_thr:.0f} entries for {pick} in the last {yrs}y.")
        return
    done = [t for t in trades if not t["open"]]
    wins = sum(1 for t in done if t["ret"] > 0)
    avg = (sum(t["ret"] for t in done) / len(done) * 100) if done else 0
    pct = f"{round(100*wins/len(done))}%" if done else "—"
    hold = (sum(t["days"] for t in done) / len(done)) if done else 0
    # compounded P&L (one position at a time, non-overlapping) on $10K — like TradingView
    cum = float(np.prod([1 + t["ret"] for t in done])) if done else 1.0
    total_pct = (cum - 1) * 100
    pnl = 10000 * (cum - 1)
    gross_win = sum(t["ret"] for t in done if t["ret"] > 0)
    gross_loss = -sum(t["ret"] for t in done if t["ret"] < 0)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    cap_txt = "patient (to upper BB)" if cap_lab == "None" else f"{cap_lab} cap"
    st.markdown(f"###### {pick} · enter %B<0 + RSI<{rsi_thr:.0f} · exit {exit_lab} · {cap_txt} · {yrs}y")
    m = st.columns(4)
    m[0].metric("P&L on $10K", f"${pnl:,.0f}", f"{total_pct:+.1f}%")
    m[1].metric("Win rate", pct, f"{wins}/{len(done)} trades")
    m[2].metric("Avg / trade", f"{avg:+.1f}%", f"~{hold:.0f}d hold")
    m[3].metric("Profit factor", "∞" if pf == float("inf") else f"{pf:.1f}",
                "gross win ÷ loss")
    tr = []
    for t in trades:
        ex = "— open —" if t["open"] else t["exit"].strftime("%-m/%-d/%y")
        xp = "—" if t["open"] else f"${t['xp']:,.0f}"
        rsi = "—" if pd.isna(t["rsi"]) else str(int(round(t["rsi"])))
        rcls = "cold" if (not pd.isna(t["rsi"]) and t["rsi"] <= 35) else ""
        pbv = "" if pd.isna(t["pctb"]) else f'{t["pctb"]:.2f}'
        rcell = "…" if t["open"] else _fmt(t["ret"], pct=True)
        dcls = "" if t["open"] else ("up" if t["ret"] >= 0 else "dn")
        tr.append(f'<tr><td class="l">{t["entry"].strftime("%-m/%-d/%y")}</td><td>${t["ep"]:,.0f}</td>'
                  f'<td class="cold">{rsi}</td><td class="cold">{pbv}</td>'
                  f'<td class="l">{ex}</td><td>{xp}</td>'
                  f'<td class="{dcls}">{rcell}</td><td>{t["days"]}d</td></tr>')
    head = "".join(f"<th>{h}</th>" for h in ["BUY", "$", "RSI", "%B", "EXIT", "$", "Ret", "Hold"])
    st.markdown(_CSS + f'<table class="bbx"><tr>{head}</tr>{"".join(tr)}</table>',
                unsafe_allow_html=True)
