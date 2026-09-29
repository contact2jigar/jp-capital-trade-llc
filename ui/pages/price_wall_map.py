"""Price Wall Map — where dealer hedging concentrates (Put/Call Wall as
support/resistance, Gamma Flip splits dampening vs explosive regime).

Chain via services.option_chain (RH→Yahoo); gamma math via logic.price_walls;
entry RSI/BB/earnings via services.yahoo + logic. Rendering (palette-fixed dark
HTML) carried over from the original view.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

import pandas as pd

from logic import price_walls as engine
from services import gsheet, option_chain, yahoo


def _compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Standard Wilder RSI on close prices."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period, min_periods=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

_BG, _CARD_BG, _BORDER = "#0f1419", "#161b22", "#1F2937"
_TEXT_DIM, _TEXT, _TEXT_STRONG = "#94A3B8", "#E5E7EB", "#F8FAFC"
_GREEN, _YELLOW, _PURPLE, _RED, _BLUE = "#34d399", "#facc15", "#a78bfa", "#f87171", "#60a5fa"
_REGIME_COLORS = {"Dampening": _GREEN, "Neutral": _BLUE, "Explosive": _RED}
_SRC_LABELS = {"RH": "Live · Robinhood", "yfinance": "Live · yfinance OI (EOD, RH fallback)"}

_MOCK_GLW = {
    "spot": 174.83,
    "call_wall": {"strike": 200.00, "gamma": 8560, "oi": 4120, "volume": 380, "dist_pct": +11.0},
    "put_wall":  {"strike": 160.00, "gamma": 8650, "oi": 3860, "volume": 295, "dist_pct": -11.2},
    "gamma_flip": {"strike": 195.30, "dist_pct": -10.5},
    "regime": "Dampening",
    "gamma_decay": [{"bucket": "11d", "date": "2026-05-29", "intensity": 0.55},
                    {"bucket": "31d", "date": "2026-06-18", "intensity": 0.85},
                    {"bucket": "39d", "date": "2026-06-26", "intensity": 0.95}],
    "high_band": [199.11, 190.00, 185.00],
    "low_band":  [155.00, 150.00, 145.00],
}


def render(c: dict) -> None:
    st.markdown("# 🧱 Price Wall Map")
    st.caption("Where dealer hedging concentrates — Put Wall / Call Wall act as "
               "support and resistance · Gamma Flip splits stabilizing vs amplifying regime.")

    types, by_type = gsheet.watchlist_by_type()

    c1, c2, c3, c4 = st.columns([1.4, 1.9, 1, 1.2])
    with c1:
        stype = st.selectbox("Stock type", types, key="pwm_type")
    with c2:
        stocks = by_type.get(stype, [])
        stock = st.selectbox("Stock", stocks or ["—"], key=f"pwm_stock_{stype}")
    with c3:
        max_dte = st.selectbox(
            "DTE window", [7, 14, 21, 30, 60, 90, 180], index=3, key="pwm_dte",
            format_func=lambda d: {7: "7 (this Fri)", 14: "14 (next Fri)"}.get(d, str(d)),
            help="Cap on expiries in the gamma calc. 7 ≈ this Friday's weekly chain, "
                 "14 ≈ next Friday — tightest dealer-pin picture near-term.")
    with c4:
        st.write(""); st.write("")
        build = st.button("🧱 Build Price Wall", type="primary",
                          use_container_width=True, disabled=not stocks)

    if build and stocks:
        st.session_state["pwm_built"] = {"ticker": stock, "dte": int(max_dte)}

    built = st.session_state.get("pwm_built")
    if not built:
        st.info("Pick a **stock type** and **stock**, then **Build Price Wall**.")
        return
    _render_walls(built["ticker"], built["dte"])


def _render_walls(ticker: str, max_dte: int) -> None:
    if st.button("↻ Refresh chain", key=f"pwm_refresh_{ticker}"):
        option_chain.load_chain.clear()
        st.rerun()

    data, src = None, "mock"
    with st.spinner(f"Loading {ticker} option chain (≤{max_dte}d)…"):
        chain = option_chain.load_chain(ticker, max_dte=int(max_dte))
        if chain is not None and not chain.empty:
            data = engine.analyze(chain)
            if data:
                src = str(chain["source"].iloc[0]) if "source" in chain.columns else "live"
    if data is None:
        data = _MOCK_GLW
        st.warning(f"Live chain unavailable for **{ticker}** — showing mock data. "
                   "Try another ticker, widen the DTE window, or hit Refresh.")

    chart_col, side_col = st.columns([3, 1])
    with chart_col:
        st.markdown(_chart_html(ticker, data, src), unsafe_allow_html=True)
    with side_col:
        st.markdown(_regime_card(data), unsafe_allow_html=True)
        st.markdown(_closest_levels(data, ticker), unsafe_allow_html=True)
        st.markdown(_gamma_decay(data), unsafe_allow_html=True)


# ─── entry signals (services + logic, replaces stock_scanner.wheel) ──────────
def _entry_signals(ticker: str) -> dict:
    df = yahoo.get_history(ticker, period="6mo", interval="1d")
    if df.empty or "Close" not in df:
        return {}
    close = df["Close"].dropna()
    rsi_s = _compute_rsi(close, 14).dropna()
    rsi = float(rsi_s.iloc[-1]) if not rsi_s.empty else None
    bb = None
    if len(close) >= 20:
        mid = close.rolling(20).mean()
        sd = close.rolling(20).std()
        bb = float(((mid + 2 * sd) - (mid - 2 * sd)).iloc[-1] / mid.iloc[-1] * 100)
    ed = yahoo.get_earnings_date(ticker)
    edays = (ed - date.today()).days if ed else None
    return {"rsi": rsi, "bb_width_pct": bb, "earnings_days": edays}


# ─── Chart panel ─────────────────────────────────────────────────────────────
def _chart_html(ticker: str, d: dict, src: str = "live") -> str:
    spot = d["spot"]
    cw = float((d.get("call_wall") or {}).get("strike") or spot * 1.05)
    pw = float((d.get("put_wall") or {}).get("strike") or spot * 0.95)
    flip = float((d.get("gamma_flip") or {}).get("strike") or spot)

    levels: list[tuple] = []
    for px in d.get("high_band") or []:
        levels.append((float(px), _YELLOW, 0.35, f"${px:.2f}", "", True, False, False))
    levels.append((cw, _YELLOW, 0.95, f"${cw:.2f}", "Call Wall (resistance)", False, False, False))
    levels.append((flip, _PURPLE, 0.85, f"${flip:.2f}", "Gamma Flip", False, True, False))
    levels.append((spot, _BLUE, 0.7, f"${spot:.2f}", f"{ticker} spot", False, False, True))
    levels.append((pw, _GREEN, 0.95, f"${pw:.2f}", "Put Wall (support)", False, False, False))
    for px in d.get("low_band") or []:
        levels.append((float(px), _GREEN, 0.35, f"${px:.2f}", "", True, False, False))
    levels.sort(key=lambda x: -x[0])
    rows = "".join(_wall_row(*lv) for lv in levels)

    return (
        f'<div style="background:{_CARD_BG};border:1px solid {_BORDER};border-radius:10px;padding:16px;">'
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px;">'
        f'<span style="font-size:14px;font-weight:700;color:{_TEXT_STRONG};">'
        f'Price · {ticker} Gamma Heat Zones</span>'
        f'<span style="font-size:11px;color:{_TEXT_DIM};">⏱ {_SRC_LABELS.get(src, "POC mock")}</span>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;gap:6px;padding:14px 6px;min-height:480px;">'
        f'{rows}</div>'
        f'<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:{_TEXT_DIM};margin-top:8px;">'
        f'{_legend_dot(_GREEN, "Put Wall (support)")}{_legend_dot(_YELLOW, "Call Wall (resistance)")}'
        f'{_legend_dot(_PURPLE, "Gamma Flip")}{_legend_dot(_BLUE, "Spot")}</div></div>'
    )


def _wall_row(price, color, alpha, label, subtitle="", thin=False, dashed=False, marker=False) -> str:
    height = "3px" if thin else ("2px" if marker else "10px")
    border = f"1px dashed {color}" if dashed else "none"
    bg = "transparent" if dashed else color
    pill = (f'<span style="background:{color}33;color:{color};font-weight:800;font-size:12px;'
            f'padding:4px 10px;border:1px solid {color}88;border-radius:4px;white-space:nowrap;'
            f'text-shadow:0 1px 2px rgba(0,0,0,0.4);">{label}</span>')
    sub = (f'<span style="color:{_TEXT};font-size:12px;font-weight:600;margin-left:10px;">{subtitle}</span>'
           if subtitle else "")
    return (
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="flex:1;height:{height};background:{bg};border-top:{border};opacity:{alpha};'
        f'border-radius:2px;box-shadow:0 0 18px {color}55;"></div>'
        f'<div style="display:flex;align-items:center;min-width:170px;">{pill}{sub}</div></div>'
    )


def _legend_dot(color, label) -> str:
    return (f'<span><span style="display:inline-block;width:10px;height:10px;background:{color};'
            f'border-radius:2px;vertical-align:middle;margin-right:6px;"></span>{label}</span>')


# ─── Sidebar cards ───────────────────────────────────────────────────────────
def _regime_card(d: dict) -> str:
    regime = d["regime"]
    color = _REGIME_COLORS.get(regime, _BLUE)
    note = {
        "Dampening": "Dealers are positioned to suppress moves. Expect mean-reverting, range-bound action.",
        "Neutral": "Dealer positioning is balanced — no strong directional bias.",
        "Explosive": "Dealers are positioned to amplify moves. Expect trend continuation and wider swings.",
    }.get(regime, "")
    return (
        f'<div style="background:{_CARD_BG};border:1px solid {_BORDER};border-radius:10px;'
        f'padding:12px 14px;margin-bottom:10px;">'
        f'<div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:{_TEXT_DIM};">'
        f'Volatility Regime</div>'
        f'<div style="font-size:22px;font-weight:800;color:{color};margin-top:4px;">{regime}</div>'
        f'<div style="font-size:11px;color:{_TEXT_DIM};margin-top:6px;line-height:1.45;">{note}</div>'
        f'<div style="height:6px;border-radius:3px;margin-top:10px;'
        f'background:linear-gradient(to right,{_RED},{_BLUE},{_GREEN});position:relative;">'
        f'<div style="position:absolute;top:-3px;width:12px;height:12px;left:{_regime_pct(regime)}%;'
        f'background:{color};border-radius:50%;border:2px solid {_BG};transform:translateX(-6px);"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:9px;color:{_TEXT_DIM};margin-top:4px;">'
        f'<span>Explosive</span><span>Dampening</span></div></div>'
    )


def _regime_pct(regime: str) -> int:
    return {"Explosive": 15, "Neutral": 50, "Dampening": 85}.get(regime, 50)


def _closest_levels(d: dict, ticker: str) -> str:
    flip = d.get("gamma_flip") or {}
    cw = d.get("call_wall") or {}
    pw = d.get("put_wall") or {}
    parts = [
        f'<div style="background:{_CARD_BG};border:1px solid {_BORDER};border-radius:10px;'
        f'padding:12px 14px;margin-bottom:10px;">'
        f'<div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:{_TEXT_DIM};'
        f'margin-bottom:8px;">Closest Levels</div>'
    ]
    if flip:
        parts.append(_level_row("∞", "Gamma Flip", flip["strike"], flip.get("dist_pct", 0), _PURPLE,
                                "Spot is {pct} the flip · below flip dealers amplify moves"))

    def _gtxt(g):
        return (f"${g/1e9:.2f}B gamma" if g >= 1e9 else
                f"${g/1e6:.2f}M gamma" if g >= 1e6 else f"${g/1e3:.2f}K gamma")

    if cw:
        oivol = f" · OI {cw['oi']:,} · Vol {cw['volume']:,}" if cw.get("oi") is not None else ""
        parts.append(_level_row("↑", "Call Wall", cw["strike"], cw.get("dist_pct", 0), _YELLOW,
                                f"{_gtxt(cw.get('gamma', 0))} · resistance{oivol}"))
    if pw:
        oivol = f" · OI {pw['oi']:,} · Vol {pw['volume']:,}" if pw.get("oi") is not None else ""
        parts.append(_level_row("↓", "Put Wall", pw["strike"], pw.get("dist_pct", 0), _GREEN,
                                f"{_gtxt(pw.get('gamma', 0))} · support{oivol}"))

    spot = d.get("spot", 0)
    dist = lambda s: ((s - spot) / spot * 100) if spot else 0
    oi_b, vol_b = d.get("oi_peak_below"), d.get("vol_peak_below")
    if oi_b and pw and abs(oi_b["strike"] - pw["strike"]) > 0.01:
        parts.append(_level_row("↓", "OI Peak (below)", oi_b["strike"], dist(oi_b["strike"]), _TEXT_DIM,
                                f"{oi_b['value']:,} put OI — biggest raw open interest, differs from the gamma wall"))
    if vol_b and pw and abs(vol_b["strike"] - pw["strike"]) > 0.01:
        parts.append(_level_row("↓", "Volume Peak (below)", vol_b["strike"], dist(vol_b["strike"]), _TEXT_DIM,
                                f"{vol_b['value']:,} contracts traded today — most active strike below spot"))

    parts.append(_entry_flag_rows(ticker))
    parts.append("</div>")
    return "".join(parts)


def _level_row(arrow, label, strike, dist, color, note) -> str:
    dist_str = f"{abs(dist):.1f}% {'above' if dist > 0 else 'below'} spot"
    note = note.format(pct=dist_str)
    return (
        f'<div style="border-top:1px solid {_BORDER};padding:8px 0;">'
        f'<div style="display:flex;align-items:baseline;gap:8px;">'
        f'<span style="color:{color};font-weight:700;">{arrow}</span>'
        f'<span style="font-size:13px;font-weight:700;color:{_TEXT_STRONG};">{label}</span>'
        f'<span style="font-size:13px;color:{color};font-weight:700;">@ ${strike:.2f}</span></div>'
        f'<div style="font-size:11px;color:{_TEXT_DIM};margin-top:2px;">{note}</div></div>'
    )


def _entry_flag_rows(ticker: str) -> str:
    sig = _entry_signals(ticker)
    rsi, bb, edays = sig.get("rsi"), sig.get("bb_width_pct"), sig.get("earnings_days")

    def _rsi_flag(v):
        if v is None: return (_TEXT_DIM, "—", "no data")
        if 30 <= v <= 45: return (_GREEN, f"{v:.0f}", "in your entry zone (30-45)")
        if v > 75: return (_RED, f"{v:.0f}", "overbought — extended, wait")
        if v < 25: return (_RED, f"{v:.0f}", "falling knife — wary")
        return (_YELLOW, f"{v:.0f}", "neutral — outside the 30-45 zone")

    def _earn_flag(v):
        if v is None: return (_TEXT_DIM, "—", "no data")
        if v <= 30: return (_RED, f"{v}d", "within 30d — entry rule veto")
        return (_GREEN, f"{v}d", "clear — 30d+ away")

    rsi_c, rsi_v, rsi_note = _rsi_flag(rsi)
    earn_c, earn_v, earn_note = _earn_flag(edays)
    bb_v = f"{bb:.1f}%" if bb is not None else "—"

    def _flag_row(label, color, val, note):
        return (
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding:6px 0;border-top:1px solid {_BORDER};">'
            f'<div><span style="font-size:12px;font-weight:700;color:{_TEXT_STRONG};">{label}</span>'
            f'<div style="font-size:10px;color:{_TEXT_DIM};margin-top:2px;">{note}</div></div>'
            f'<span style="font-size:13px;font-weight:800;color:{color};background:{color}22;'
            f'border:1px solid {color}66;border-radius:4px;padding:3px 8px;white-space:nowrap;">{val}</span></div>'
        )

    return (f'{_flag_row("RSI", rsi_c, rsi_v, rsi_note)}'
            f'{_flag_row("Earnings", earn_c, earn_v, earn_note)}'
            f'{_flag_row("BB Width", _BLUE, bb_v, "volatility band — narrower = tighter squeeze")}')


def _gamma_decay(d: dict) -> str:
    rows = ""
    for r in d["gamma_decay"]:
        bar_w = int(r["intensity"] * 100)
        rows += (
            f'<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-top:1px solid {_BORDER};">'
            f'<span style="font-size:11px;color:{_TEXT_STRONG};font-weight:700;min-width:30px;">{r["bucket"]}</span>'
            f'<span style="font-size:10px;color:{_TEXT_DIM};min-width:80px;">{r["date"]}</span>'
            f'<div style="flex:1;height:6px;background:rgba(148,163,184,0.15);border-radius:3px;">'
            f'<div style="width:{bar_w}%;height:100%;background:{_YELLOW};border-radius:3px;"></div></div></div>'
        )
    return (
        f'<div style="background:{_CARD_BG};border:1px solid {_BORDER};border-radius:10px;padding:12px 14px;">'
        f'<div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:{_TEXT_DIM};'
        f'margin-bottom:4px;">Gamma Decay Over Time</div>{rows}</div>'
    )
