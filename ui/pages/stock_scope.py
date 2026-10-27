"""Stock Scope — chart (HM+20) + drill-down of how a ticker has moved.

Pick a ticker (QQQ / SPY / any name). Top: the real HM+20 chart — candlesticks,
Bollinger band, BUY/SELL signal markers, HM+20 and RSI(14) panels, pan/scroll into
the past. Below: an expandable Year → Month → Week table (current + last 3 years),
each row's % change with the RSI(14) and BB band at the end of that period.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from services import gsheet
from services.cache import TTL, cached


# ── data ─────────────────────────────────────────────────────────────────────
@cached(TTL["history"])
def _bars(ticker: str) -> pd.DataFrame | None:
    """~5y daily OHLC from Yahoo. DatetimeIndex + open/high/low/close."""
    import certifi
    import requests
    sym = ticker.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                         verify=certifi.where(), timeout=15)
        if r.status_code != 200:
            return None
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        rows = [(dt.datetime.utcfromtimestamp(t).date(), o, h, l, c)
                for t, o, h, l, c in zip(ts, q["open"], q["high"], q["low"], q["close"])
                if c is not None and o is not None]
        if len(rows) < 40:
            return None
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
        df.index = pd.DatetimeIndex(df["date"])
        return df[["open", "high", "low", "close"]]
    except Exception:
        return None


# ── indicator math (list-based; mirrors the iPhone engine) ────────────────────
def _wilder(c: list, n: int) -> list:
    out = [None] * len(c)
    if len(c) <= n:
        return out
    a = 1.0 / n; ag = al = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]; g = max(d, 0.0); l = max(-d, 0.0)
        if i == 1: ag, al = g, l
        else: ag = a * g + (1 - a) * ag; al = a * l + (1 - a) * al
        if i >= n:
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _ema_af(x: list, span: int) -> list:
    a = 2.0 / (span + 1); out = [None] * len(x); prev = None
    for i, v in enumerate(x):
        if v is None: continue
        prev = v if prev is None else a * v + (1 - a) * prev
        out[i] = prev
    return out


def _wma(x: list, p: int) -> list:
    out = [None] * len(x); ws = p * (p + 1) / 2
    for i in range(p - 1, len(x)):
        acc = 0.0; ok = True
        for k in range(p):
            v = x[i - p + 1 + k]
            if v is None: ok = False; break
            acc += v * (k + 1)
        if ok: out[i] = acc / ws
    return out


def _indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    # RSI(14) + Bollinger(20,2) for the drill-down + BB overlay
    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = (100 - 100 / (1 + ag / al.replace(0, float("nan")))).fillna(100.0)
    ma = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    df["bb_up"] = ma + 2 * sd; df["bb_mid"] = ma; df["bb_lo"] = ma - 2 * sd
    width = df["bb_up"] - df["bb_lo"]
    df["pctb"] = ((c - df["bb_lo"]) / width).where(width > 0)

    # HM+20 — RSI(9) / EMA3(RSI9) / WMA21(RSI9) → gold (BUY) / red (SELL)
    closes = c.tolist()
    r9 = _wilder(closes, 9); e3 = _ema_af(r9, 3); w21 = _wma(r9, 21)
    df["hm_rsi9"] = r9; df["hm_wma21"] = w21
    n = len(closes)
    rg = [False] * n; rr = [False] * n
    for i in range(1, n):
        if None in (r9[i], e3[i], w21[i], r9[i - 1], e3[i - 1]):
            continue
        wmaBelow = w21[i] < r9[i] and w21[i] < e3[i]
        gap = min(r9[i], e3[i]) - w21[i]
        deep = w21[i] < 45 and gap >= 8
        mid = 45 <= w21[i] < 65 and gap >= 5
        rising = r9[i] > r9[i - 1] and e3[i] > e3[i - 1]
        rg[i] = wmaBelow and (deep or mid) and rising
        rr[i] = (w21[i] > r9[i] and w21[i] > e3[i]) and (e3[i] < e3[i - 1])
    buy = [False] * n; sell = [False] * n; state = "NONE"
    for i in range(n):
        if rr[i] and state != "RED": sell[i] = True; state = "RED"
        elif rg[i] and state != "GOLD": buy[i] = True; state = "GOLD"
    df["buy"] = buy; df["sell"] = sell
    return df


def _bb_label(pctb) -> str:
    if pctb is None or pd.isna(pctb): return "—"
    return "Lower" if pctb <= 0.20 else ("Upper" if pctb >= 0.80 else "Mid")


def _hm_trades(d: pd.DataFrame, mode: str = "strategy", horizon: int = 20,
               years: int = 3) -> list:
    """HM+20 BUY log, two modes:
    • 'strategy' — reproduces the TradingView strategy P&L exactly: BUY -> next SELL,
      each leg FILLED AT THE NEXT BAR'S OPEN (the Pine script's own convention,
      "fill at the next bar's open"). A gold with no later red stays open.
    • 'hold' — each BUY held a FIXED `horizon` of trading days (the SELL is a poor
      whipsaw exit; the real edge is a held horizon = sell a CSP, hold to expiry)."""
    cutoff = d.index[-1] - pd.DateOffset(years=years)
    n = len(d.index)
    idx = d.index
    opens, closes = d["open"].values, d["close"].values
    rsi, pctb = d["rsi"].values, d["pctb"].values
    buys = [i for i in range(n) if bool(d["buy"].iloc[i])]
    trades = []

    if mode == "hold":
        for e in buys:
            if idx[e] < cutoff:
                continue
            xr = e + horizon
            is_open = xr > n - 1
            x = min(xr, n - 1)
            trades.append({"entry": idx[e], "ep": float(closes[e]), "rsi": rsi[e],
                           "pctb": pctb[e], "exit": idx[x], "xp": float(closes[x]),
                           "ret": (closes[x] / closes[e] - 1) if closes[e] else None,
                           "days": horizon, "open": is_open})
    else:  # strategy — BUY -> next SELL, on the SIGNAL bar (matches the chart labels)
        sells = {i for i in range(n) if bool(d["sell"].iloc[i])}
        seq = sorted([(i, "B") for i in buys] + [(i, "S") for i in sells])
        e = None
        for i, t in seq:
            if t == "B" and e is None:
                e = i
            elif t == "S" and e is not None:
                trades.append(_mk_strat(idx, closes, rsi, pctb, e, i)); e = None
        if e is not None:
            trades.append(_mk_strat(idx, closes, rsi, pctb, e, None))
        trades = [t for t in trades if t["entry"] >= cutoff]

    trades.sort(key=lambda t: t["entry"], reverse=True)
    return trades


def _mk_strat(idx, closes, rsi, pctb, e_pos, s_pos) -> dict:
    # entry/exit on the SIGNAL bar itself (= chart BUY/SELL labels), priced at the
    # 3:45 close. (The Pine P&L fills the NEXT bar's open, so it reads 1 bar later.)
    ep = float(closes[e_pos])
    if s_pos is None:
        return {"entry": idx[e_pos], "ep": ep, "rsi": rsi[e_pos], "pctb": pctb[e_pos],
                "exit": None, "xp": None, "ret": None, "days": 0, "open": True}
    xp = float(closes[s_pos])
    return {"entry": idx[e_pos], "ep": ep, "rsi": rsi[e_pos], "pctb": pctb[e_pos],
            "exit": idx[s_pos], "xp": xp, "ret": (xp / ep - 1) if ep else None,
            "days": (idx[s_pos] - idx[e_pos]).days, "open": False}


# ── HM+20 chart ──────────────────────────────────────────────────────────────
def _chart(c: dict, d: pd.DataFrame, n: int) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    pos, neg = c["pos"], c["neg"]
    txt, mut, blue, gold = c["text"], c["muted"], c["blue"], c["gold"]
    grid = c["border_soft"]

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.60, 0.22, 0.18], vertical_spacing=0.025)

    # Bollinger band (shaded) under the candles
    fig.add_trace(go.Scatter(x=d.index, y=d["bb_up"], line=dict(color=blue, width=0.7, dash="dot"),
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["bb_lo"], line=dict(color=blue, width=0.7, dash="dot"),
                             fill="tonexty", fillcolor="rgba(88,166,255,0.07)",
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["bb_mid"], line=dict(color=mut, width=0.7),
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    # candlesticks
    fig.add_trace(go.Candlestick(x=d.index, open=d["open"], high=d["high"],
                                 low=d["low"], close=d["close"],
                                 increasing_line_color=pos, decreasing_line_color=neg,
                                 increasing_fillcolor=pos, decreasing_fillcolor=neg,
                                 line=dict(width=1), showlegend=False, name=""), row=1, col=1)
    # BUY / SELL markers
    b = d[d["buy"]]; s = d[d["sell"]]
    if not b.empty:
        fig.add_trace(go.Scatter(x=b.index, y=b["low"] * 0.985, mode="markers",
                                 marker=dict(symbol="triangle-up", color=gold, size=11,
                                             line=dict(color=txt, width=0.5)),
                                 name="BUY", hovertemplate="BUY %{x|%b %d %Y}<extra></extra>"),
                      row=1, col=1)
    if not s.empty:
        fig.add_trace(go.Scatter(x=s.index, y=s["high"] * 1.015, mode="markers",
                                 marker=dict(symbol="triangle-down", color=neg, size=11,
                                             line=dict(color=txt, width=0.5)),
                                 name="SELL", hovertemplate="SELL %{x|%b %d %Y}<extra></extra>"),
                      row=1, col=1)
    # HM+20 panel — RSI9 vs WMA21
    fig.add_trace(go.Scatter(x=d.index, y=d["hm_wma21"], line=dict(color=gold, width=1.1),
                             hoverinfo="skip", showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["hm_rsi9"], line=dict(color=txt, width=1.3),
                             name="HM+20", hovertemplate="HM %{y:.0f}<extra></extra>"), row=2, col=1)
    # RSI(14) panel
    fig.add_trace(go.Scatter(x=d.index, y=d["rsi"], line=dict(color=blue, width=1.2),
                             name="RSI14", hovertemplate="RSI %{y:.0f}<extra></extra>"), row=3, col=1)
    fig.add_hline(y=70, line=dict(color=neg, width=0.6, dash="dot"), row=3, col=1)
    fig.add_hline(y=30, line=dict(color=blue, width=0.6, dash="dot"), row=3, col=1)

    # initial window = the chosen range; pan/scroll reveals the rest (5y loaded)
    vis = d.tail(n)
    x0 = vis.index[0]; x1 = d.index[-1]
    pad = (vis["high"].max() - vis["low"].min()) * 0.06
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=6, b=0), showlegend=False,
                      dragmode="pan", hovermode="x unified",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=mut, size=11),
                      xaxis_rangeslider_visible=False)
    fig.update_xaxes(showgrid=False, range=[x0, x1])
    fig.update_yaxes(showgrid=True, gridcolor=grid, zeroline=False)
    fig.update_yaxes(range=[vis["low"].min() - pad, vis["high"].max() + pad], row=1, col=1)
    fig.update_yaxes(range=[0, 100], tickvals=[30, 50, 70], showgrid=False, row=3, col=1)
    st.plotly_chart(fig, use_container_width=True,
                    config={"scrollZoom": True, "displayModeBar": False})


# ── drill-down render helpers ─────────────────────────────────────────────────
def _fmt_ret(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:+.1f}%"


def _cls(v) -> str:
    return "flat" if v is None or pd.isna(v) else ("up" if v >= 0 else "dn")


def _ind_html(rsi, pctb) -> str:
    rsi_s = "—" if pd.isna(rsi) else f"{int(round(rsi))}"
    rsi_c = "hot" if (not pd.isna(rsi) and rsi >= 70) else ("cold" if (not pd.isna(rsi) and rsi <= 35) else "")
    bb = _bb_label(pctb)
    bb_c = {"Lower": "cold", "Upper": "hot"}.get(bb, "")
    return (f'<span class="ind">RSI <b class="{rsi_c}">{rsi_s}</b> · BB <b class="{bb_c}">{bb}</b></span>')


def _row(label, ret, rsi, pctb, level) -> str:
    return (f'<div class="row lv{level}"><span class="per">{label}</span>'
            f'<span class="ret {_cls(ret)}">{_fmt_ret(ret)}</span>{_ind_html(rsi, pctb)}</div>')


def _summary(label, ret, rsi, pctb) -> str:
    return (f'<span class="per">{label}</span>'
            f'<span class="ret {_cls(ret)}">{_fmt_ret(ret)}</span>{_ind_html(rsi, pctb)}')


def render(c: dict) -> None:
    st.markdown("#### 🔎 Stock Scope — chart + how far it's moved")

    try:
        _, by = gsheet.watchlist_by_type()
        uni = by.get("All", [])
    except Exception:
        uni = []
    opts = ["QQQ", "SPY"] + [t for t in uni if t not in ("QQQ", "SPY")]
    cc1, cc2 = st.columns([2, 1])
    with cc1:
        pick = st.selectbox("Ticker", opts, index=0, key="scope_pick")
    with cc2:
        typed = st.text_input("…or type one", value="", key="scope_typed").strip().upper()
    ticker = typed or pick

    df = _bars(ticker)
    if df is None or df.empty:
        st.warning(f"No data for {ticker}.")
        return
    d = _indicators(df)

    last = d.iloc[-1]
    snap = st.columns(4)
    snap[0].metric(ticker, f"${last['close']:,.2f}")
    chg = (d["close"].iloc[-1] / d["close"].iloc[-2] - 1) if len(d) > 1 else 0
    snap[1].metric("Today", f"{chg*100:+.2f}%", delta_color=("normal" if chg >= 0 else "inverse"))
    snap[2].metric("RSI(14)", "—" if pd.isna(last["rsi"]) else f"{int(round(last['rsi']))}")
    snap[3].metric("BB", _bb_label(last["pctb"]))

    rng = st.radio("Range", ["6M", "1Y", "2Y", "5Y"], index=1, horizontal=True,
                   key="scope_range", label_visibility="collapsed")
    st.caption("🔺 gold = HM+20 BUY · 🔻 red = SELL · drag / scroll-zoom to see the past")
    _chart(c, d, {"6M": 126, "1Y": 252, "2Y": 504, "5Y": 100000}[rng])

    # HM+20 BUY log — Strategy (matches TradingView P&L) or Hold Nd (CSP what-if)
    mc, hc = st.columns([2, 1])
    mode_label = mc.radio("Mode", ["Strategy (matches TradingView)", "Hold Nd"],
                          index=0, horizontal=True, key="scope_mode",
                          label_visibility="collapsed")
    mode = "strategy" if mode_label.startswith("Strategy") else "hold"
    horizon = 20
    if mode == "hold":
        horizon = int(hc.radio("Hold", ["10d", "20d", "40d"], index=1, horizontal=True,
                               key="scope_horizon", label_visibility="collapsed")[:-1])
    trades = _hm_trades(d, mode=mode, horizon=horizon, years=3)
    if st.checkbox("Lower / Mid-BB entries only  ·  drop Upper-BB traps",
                   value=False, key="scope_bbfilter"):
        trades = [t for t in trades if _bb_label(t["pctb"]) != "Upper"]
    if trades:
        done = [t for t in trades if not t["open"]]
        wins = sum(1 for t in done if (t["ret"] or 0) > 0)
        avg = (sum(t["ret"] for t in done) / len(done) * 100) if done else 0
        pct = f"{round(100*wins/len(done))}%" if done else "—"
        title = ("HM Strategy · BUY → SELL · signal-day close · matches chart labels"
                 if mode == "strategy" else f"HM+20 BUYs · hold {horizon}d")
        exit_col = "SELL" if mode == "strategy" else f"+{horizon}d"
        st.markdown(f"###### {title} · last 3y  ·  "
                    f"**{wins}/{len(done)} green ({pct})** · avg {avg:+.1f}%")
        tr = []
        for t in trades:
            ex = "— open —" if t["open"] else t["exit"].strftime("%-m/%-d/%y")
            xp = "—" if t["open"] else f"${t['xp']:,.0f}"
            rsi = "—" if pd.isna(t["rsi"]) else str(int(round(t["rsi"])))
            rcls = "hot" if (not pd.isna(t["rsi"]) and t["rsi"] >= 70) else ("cold" if (not pd.isna(t["rsi"]) and t["rsi"] <= 35) else "")
            bb = _bb_label(t["pctb"]); bcls = {"Lower": "cold", "Upper": "hot"}.get(bb, "")
            rcell = "…" if t["open"] else _fmt_ret(t["ret"])
            tr.append(f'<tr><td class="d">{t["entry"].strftime("%-m/%-d/%y")}</td><td>${t["ep"]:,.0f}</td>'
                      f'<td class="{rcls}">{rsi}</td><td class="{bcls}">{bb}</td>'
                      f'<td class="d">{ex}</td><td>{xp}</td>'
                      f'<td class="ret {_cls(None if t["open"] else t["ret"])}">{rcell}</td></tr>')
        head = "".join(f"<th>{h}</th>" for h in ["BUY", "$", "RSI", "BB", exit_col, "$", "Ret"])
        st.markdown(_SIG_CSS + f'<table class="sig"><tr>{head}</tr>{"".join(tr)}</table>', unsafe_allow_html=True)

    st.markdown("###### Drill-down · Year → Month → Week")
    yearly = d.resample("YE").last(); yearly["ret"] = yearly["close"].pct_change()
    monthly = d.resample("ME").last(); monthly["ret"] = monthly["close"].pct_change()
    weekly = d.resample("W-FRI").last(); weekly["ret"] = weekly["close"].pct_change()
    years = sorted({ix.year for ix in yearly.index}, reverse=True)[:4]

    html = ['<div class="scope">']
    for yi, yr in enumerate(years):
        yrow = yearly[yearly.index.year == yr]
        if yrow.empty: continue
        yv = yrow.iloc[-1]
        html.append(f'<details class="yr"{" open" if yi == 0 else ""}>')
        html.append(f'<summary>{_summary(str(yr), yv["ret"], yv["rsi"], yv["pctb"])}</summary>')
        for mix, mrow in monthly[monthly.index.year == yr].sort_index(ascending=False).iterrows():
            html.append('<details class="mo">')
            html.append(f'<summary>{_summary(mix.strftime("%b"), mrow["ret"], mrow["rsi"], mrow["pctb"])}</summary>')
            wmo = weekly[(weekly.index.year == mix.year) & (weekly.index.month == mix.month)].sort_index(ascending=False)
            for wix, wrow in wmo.iterrows():
                html.append(_row("wk " + wix.strftime("%b %-d"), wrow["ret"], wrow["rsi"], wrow["pctb"], 2))
            html.append('</details>')
        html.append('</details>')
    html.append('</div>')
    st.markdown(_CSS + "".join(html), unsafe_allow_html=True)


_CSS = """
<style>
.scope{font-variant-numeric:tabular-nums;margin-top:4px}
.scope details{border:1px solid #26333f44;border-radius:8px;margin:5px 0}
.scope details .mo{margin:5px 8px}
.scope summary{list-style:none;cursor:pointer;padding:9px 12px;display:flex;align-items:center;gap:10px}
.scope summary::-webkit-details-marker{display:none}
.scope summary::before{content:"▸";color:#8a97a6;font-size:11px;transition:transform .15s}
.scope details[open]>summary::before{transform:rotate(90deg)}
.scope .row{display:flex;align-items:center;gap:10px;padding:7px 12px 7px 30px;border-top:1px solid #8a97a622}
.scope .per{font-weight:700;min-width:84px}
.scope .mo .per,.scope .row .per{font-weight:600}
.scope .ret{font-weight:700;min-width:70px;text-align:right}
.scope .ret.up{color:#2f9e52}.scope .ret.dn{color:#e0484e}.scope .ret.flat{color:#8a97a6}
.scope .ind{color:#8a97a6;font-size:12px;margin-left:auto}
.scope .ind b.hot{color:#e0484e}.scope .ind b.cold{color:#3f86d6}
</style>
"""

_SIG_CSS = """
<style>
.sig{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px;margin:4px 0 14px;max-width:660px;width:100%}
.sig th{text-align:right;color:#8a97a6;font-size:10px;font-weight:700;padding:5px 9px;border-bottom:1px solid #8a97a655;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap}
.sig th:first-child,.sig th:nth-child(5){text-align:left}
.sig td{text-align:right;padding:6px 9px;border-bottom:1px solid #8a97a618;white-space:nowrap}
.sig td.d{text-align:left;font-weight:600}
.sig tr:hover td{background:#8a97a614}
.sig td.ret{border-left:1px solid #8a97a622}
.sig td.ret.up{color:#2f9e52;font-weight:800}.sig td.ret.dn{color:#e0484e;font-weight:800}.sig td.ret.flat{color:#8a97a6}
.sig td.hot{color:#e0484e;font-weight:700}.sig td.cold{color:#3f86d6;font-weight:700}
</style>
"""
