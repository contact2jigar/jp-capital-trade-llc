"""🧭 Sector Scoreboard — how every S&P sector SPDR has performed vs the SPY
benchmark: YTD · 1y · 3y · 5y · 10y · 20y, all TOTAL RETURN (dividends reinvested),
annualized for the multi-year columns. Computed live from Yahoo adjusted-close
history — never hardcoded, so it never goes stale.

XLC launched Jun 2018 and XLRE Oct 2015, so their deep-history columns read N/A
(we never fabricate history that doesn't exist). Mirrors the iPhone card.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services import yahoo

# SPY benchmark first, then the 11 Select Sector SPDRs (sector, ticker, what it covers).
SECTORS = [
    ("S&P 500",                "SPY",  "Broad market (500 largest U.S. companies)"),
    ("Technology",             "XLK",  "Software, semiconductors & tech hardware"),
    ("Financials",             "XLF",  "Banks, insurers & financial services"),
    ("Industrials",            "XLI",  "Capital goods, transport & commercial services"),
    ("Consumer Discretionary", "XLY",  "Retail, autos, hotels & leisure"),
    ("Health Care",            "XLV",  "Pharma, biotech, medical devices & services"),
    ("Energy",                 "XLE",  "Oil, gas & energy equipment"),
    ("Materials",              "XLB",  "Chemicals, metals, mining & packaging"),
    ("Communication Services", "XLC",  "Media, entertainment & telecom"),
    ("Utilities",              "XLU",  "Electric, gas & water utilities"),
    ("Consumer Staples",       "XLP",  "Food, beverages, household & personal products"),
    ("Real Estate",            "XLRE", "REITs & real-estate companies"),
]


def _ann(closes: pd.Series, years: float) -> float | None:
    """Trailing annualized total return over `years`; None when history is too short."""
    if closes.empty:
        return None
    now, now_t = float(closes.iloc[-1]), closes.index[-1]
    if now <= 0:
        return None
    target = now_t - pd.Timedelta(days=years * 365.25)
    if closes.index[0] > target + pd.Timedelta(days=45):     # not enough history → N/A
        return None
    pos = closes.index.get_indexer([target], method="nearest")[0]
    past = float(closes.iloc[pos])
    if past <= 0:
        return None
    return (now / past) ** (1.0 / years) - 1


def _ytd(closes: pd.Series) -> float | None:
    """YTD total return: latest close vs the last close of the prior calendar year."""
    if closes.empty:
        return None
    now, now_t = float(closes.iloc[-1]), closes.index[-1]
    prior = closes[closes.index.year < now_t.year]
    if prior.empty or now <= 0:
        return None
    base = float(prior.iloc[-1])
    return now / base - 1 if base > 0 else None


def _dotcom_dd(closes: pd.Series) -> float | None:
    """Worst peak-to-trough drawdown during the dot-com bust (2000–2002). Negative.
    None for sectors that didn't exist yet (XLC 2018, XLRE 2015)."""
    if closes.empty:
        return None
    win = closes[(closes.index >= pd.Timestamp("2000-01-01")) &
                 (closes.index <= pd.Timestamp("2002-12-31"))]
    if win.empty or win.index[0] > pd.Timestamp("2000-09-01"):   # must cover the peak
        return None
    dd = (win / win.cummax() - 1.0).min()
    return float(dd)


@st.cache_data(ttl=3600, show_spinner=False)
def rows() -> list[dict]:
    """Per-sector trailing total returns + dot-com drawdown, from full monthly history.
    Full history (not 20y) is needed so the 2000–2002 drawdown window is covered."""
    out = []
    for sector, ticker, covers in SECTORS:
        df = yahoo.get_history(ticker, period="max", interval="1mo", auto_adjust=True)
        closes = df["Close"].dropna() if not df.empty and "Close" in df else pd.Series(dtype=float)
        if not closes.empty and getattr(closes.index, "tz", None) is not None:
            closes.index = closes.index.tz_localize(None)   # Yahoo index is tz-aware; naive for compares
        out.append({
            "sector": sector, "ticker": ticker, "covers": covers,
            "benchmark": ticker == "SPY",
            "ytd": _ytd(closes),
            "r1": _ann(closes, 1), "r3": _ann(closes, 3), "r5": _ann(closes, 5),
            "r10": _ann(closes, 10), "dd": _dotcom_dd(closes),
        })
    return out


def table_html(c: dict) -> str:
    """Full sector table: SECTOR · TICKER · YTD · 1Y · 3Y · 5Y · 10Y · .COM DD · WHAT IT COVERS."""
    def ret(v):
        if v is None:
            return f"<td style='text-align:right;padding:9px 12px;border-bottom:1px solid {c['border_soft']};color:{c['muted']};font-variant-numeric:tabular-nums;'>N/A</td>"
        col = c["pos"] if v >= 0 else c["neg"]
        return (f"<td style='text-align:right;padding:9px 12px;border-bottom:1px solid {c['border_soft']};"
                f"color:{col};font-weight:700;font-variant-numeric:tabular-nums;'>{v * 100:+.1f}%</td>")

    def dd(v):   # dot-com drawdown — always a loss, shown in red
        if v is None:
            return f"<td style='text-align:right;padding:9px 12px;border-bottom:1px solid {c['border_soft']};color:{c['muted']};font-variant-numeric:tabular-nums;'>N/A</td>"
        return (f"<td style='text-align:right;padding:9px 12px;border-bottom:1px solid {c['border_soft']};"
                f"color:{c['neg']};font-weight:700;font-variant-numeric:tabular-nums;'>{v * 100:.1f}%</td>")

    th = (f"position:sticky;top:0;z-index:2;background:{c['raised']};color:{c['muted']};"
          f"font-size:10px;letter-spacing:.4px;text-transform:uppercase;font-weight:700;"
          f"padding:9px 12px;border-bottom:2px solid {c['border']};white-space:nowrap;")
    head = (f"<tr>"
            f"<th style='{th}text-align:left;'>Sector</th>"
            f"<th style='{th}text-align:left;'>Ticker</th>"
            f"<th style='{th}text-align:right;'>YTD</th>"
            f"<th style='{th}text-align:right;'>1Y</th>"
            f"<th style='{th}text-align:right;'>3Y</th>"
            f"<th style='{th}text-align:right;'>5Y</th>"
            f"<th style='{th}text-align:right;'>10Y</th>"
            f"<th style='{th}text-align:right;'>.com DD</th>"
            f"<th style='{th}text-align:left;'>What it covers</th>"
            f"</tr>")

    body = []
    for r in rows():
        bg = c["raised"] if r["benchmark"] else c["panel"]
        name_w = "800" if r["benchmark"] else "700"
        td = f"padding:9px 12px;border-bottom:1px solid {c['border_soft']};font-size:13px;"
        body.append(
            f"<tr style='background:{bg};'>"
            f"<td style='{td}color:{c['text']};font-weight:{name_w};white-space:nowrap;'>{r['sector']}</td>"
            f"<td style='{td}color:{c['mid']};font-weight:700;'>{r['ticker']}</td>"
            f"{ret(r['ytd'])}{ret(r['r1'])}{ret(r['r3'])}{ret(r['r5'])}{ret(r['r10'])}{dd(r['dd'])}"
            f"<td style='{td}color:{c['mid']};'>{r['covers']}</td>"
            f"</tr>"
        )

    return (
        f"<div style='border:1px solid {c['border']};border-radius:12px;overflow:hidden;"
        f"max-height:620px;overflow-y:auto;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"
        f"<div style='color:{c['muted']};font-size:11px;margin-top:6px;'>"
        f"Total return · annualized for ≥1y · <b>.com DD</b> = worst drawdown in the 2000–2002 bust · "
        f"live from Yahoo · XLC (2018) & XLRE (2015) didn't exist then → N/A</div>"
    )
