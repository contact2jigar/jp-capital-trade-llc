"""Seasonality — market seasonality heatmap + VIX volatility panel.

Panel 1: average/median monthly return (or % positive) per ticker over an
N-year lookback, colored green/red by sign + magnitude.
Panel 2: current VIX, 52-week IV Rank, 52w hi/lo, SPY 30-day realized vol.

Data through services.yahoo; math through logic.seasonality; rendering here
(palette-driven HTML), matching the look you carried over.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from logic import seasonality as engine
from services import yahoo


def _pal(c: dict) -> dict:
    """Map JPWheelEngine's theme tokens to the keys this page's HTML expects."""
    return {
        "text_strong": c["text"], "text_muted": c["muted"], "text": c["mid"],
        "surface": c["panel"], "surface_alt": c["raised"],
        "positive": c["pos"], "negative": c["neg"], "warning": c["amber"],
        "border": c["border"], "border_soft": c["border_soft"],
    }

_DEFAULT_TICKERS = ["SPY", "QQQ", "IWM", "DIA"]
_TICKER_OPTIONS = sorted(set(_DEFAULT_TICKERS + [
    "SPY", "QQQ", "IWM", "DIA", "XLB", "XLK", "XLE", "XLF",
    "XLV", "XLY", "XLP", "XLU", "XLI", "GLD", "TLT"]))


def render(c: dict) -> None:
    c = _pal(c)
    st.markdown("# 📅 Seasonality")
    st.markdown(
        f'<div style="font-size:13px;color:{c["text_muted"]};margin-bottom:14px;'
        f'line-height:1.55"><b style="color:{c["text_strong"]}">Market '
        f'seasonality</b> · average monthly return per symbol over the lookback '
        f'window. Green = historically positive months, red = negative.</div>',
        unsafe_allow_html=True)

    k1, k2, k3 = st.columns([3, 1.2, 1.2])
    with k1:
        tickers = st.multiselect("Tickers", options=_TICKER_OPTIONS,
                                 default=_DEFAULT_TICKERS, key="seas_tickers")
    with k2:
        metric = st.selectbox("Metric", ["Avg Return", "Median Return", "% Positive"],
                              index=0, key="seas_metric")
    with k3:
        years = int(st.selectbox("Lookback (yrs)", list(range(1, 21)),
                                 index=4, key="seas_years"))   # default 5

    if not tickers:
        st.info("Add at least one ticker to build the heatmap.")
        return

    with st.spinner(f"Computing {years}-year seasonality for {len(tickers)} symbol(s)…"):
        closes = {}
        for t in tickers:
            df = yahoo.get_history(t, period=f"{years + 1}y", interval="1mo")
            closes[t] = df["Close"].dropna() if not df.empty and "Close" in df else pd.Series(dtype=float)
        tbl = engine.build_monthly_table(closes, years, metric)

    st.markdown(_heatmap_html(tbl, c), unsafe_allow_html=True)

    # ── VIX panel ─────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="font-size:13px;color:{c["text_muted"]};margin:22px 0 10px;'
        f'line-height:1.55"><b style="color:{c["text_strong"]}">VIX '
        f'volatility</b> · current implied-vol regime vs its trailing 52 weeks.</div>',
        unsafe_allow_html=True)
    vix_df = yahoo.get_history("^VIX", period="1y", interval="1d", auto_adjust=False)
    spy_df = yahoo.get_history("SPY", period="6mo", interval="1d")
    vix_close = vix_df["Close"].dropna() if not vix_df.empty and "Close" in vix_df else None
    spy_close = spy_df["Close"].dropna() if not spy_df.empty and "Close" in spy_df else None
    vix = engine.vix_stats(vix_close, spy_close)
    if vix is None:
        st.info("VIX data unavailable right now.")
    else:
        st.markdown(_vix_panel_html(vix, c), unsafe_allow_html=True)


# ─── palette-driven HTML rendering ───────────────────────────────────────────
def _cell_bg(v: float | None, c: dict, vmax: float = 4.0) -> str:
    if v is None:
        return c["surface_alt"]
    mag = min(abs(v) / vmax, 1.0)
    alpha = int((0.12 + 0.55 * mag) * 255)
    base = c["positive"] if v >= 0 else c["negative"]
    return f"{base}{alpha:02x}"


def _heatmap_html(tbl: pd.DataFrame, c: dict) -> str:
    th = (f'padding:9px 8px;font-size:11px;font-weight:700;letter-spacing:.04em;'
          f'color:{c["text_muted"]};text-transform:uppercase;text-align:center;'
          f'border-bottom:1px solid {c["border"]}')
    td_t = (f'padding:9px 12px;font-size:13px;font-weight:700;'
            f'color:{c["text_strong"]};text-align:left;'
            f'border-bottom:1px solid {c["border_soft"]}')
    head = f'<th style="{th};text-align:left">Ticker</th>' + "".join(
        f'<th style="{th}">{m}</th>' for m in tbl.columns)
    body = []
    for tkr, row in tbl.iterrows():
        cells = [f'<td style="{td_t}">{tkr}</td>']
        for m in tbl.columns:
            v = row[m]
            bg = _cell_bg(None if pd.isna(v) else float(v), c)
            txt = "—" if pd.isna(v) else f'{v:+.2f}%'
            cells.append(
                f'<td style="padding:9px 8px;font-size:12px;font-weight:600;'
                f'text-align:center;color:{c["text"]};background:{bg};'
                f'border-bottom:1px solid {c["surface"]}">{txt}</td>')
        body.append(f'<tr>{"".join(cells)}</tr>')
    return (
        f'<div style="overflow-x:auto;border:1px solid {c["border"]};'
        f'border-radius:10px;background:{c["surface_alt"]}">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>')


def _vix_panel_html(s: dict, c: dict) -> str:
    def _stat(label, val, val_clr):
        return (
            f'<div style="flex:1;min-width:120px;background:{c["surface"]};'
            f'border:1px solid {c["border_soft"]};border-radius:8px;'
            f'padding:10px 14px">'
            f'<div style="font-size:10px;font-weight:700;letter-spacing:.05em;'
            f'text-transform:uppercase;color:{c["text_muted"]};margin-bottom:4px">'
            f'{label}</div>'
            f'<div style="font-size:20px;font-weight:800;color:{val_clr};'
            f'font-family:monospace">{val}</div></div>')

    rank = s["rank"]
    rank_clr = (c["positive"] if rank < 33 else
                c["warning"] if rank < 66 else c["negative"])
    cur_clr = (c["positive"] if s["cur"] < 15 else
               c["warning"] if s["cur"] < 25 else c["negative"])
    rv = f'{s["rv"]:.1f}' if s["rv"] is not None else "—"
    return (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap">'
        + _stat("Current VIX", f'{s["cur"]:.2f}', cur_clr)
        + _stat("IV Rank (52w)", f'{rank:.0f}', rank_clr)
        + _stat("52W High", f'{s["hi"]:.2f}', c["text_strong"])
        + _stat("52W Low", f'{s["lo"]:.2f}', c["text_strong"])
        + _stat("SPY RV (30d)", rv, c["text_strong"])
        + '</div>')
