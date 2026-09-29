"""Seasonality — pure monthly-return + VIX math (no fetching, no Streamlit).

The caller supplies price series (via services.yahoo); this module computes the
seasonality table and the VIX regime stats. Rendering (heatmap HTML) lives in
the page — this is numbers only.
"""

from __future__ import annotations

import calendar

import pandas as pd

MONTHS = [calendar.month_abbr[m] for m in range(1, 13)]   # Jan..Dec


def seasonality_row(close: pd.Series, years: int, metric: str) -> list[float | None]:
    """One ticker's 12 monthly values (Jan..Dec) from a monthly close series.

    metric: 'Avg Return' | 'Median Return' | '% Positive'. Values in percent.
    None for a month with no data in the window."""
    if close is None or len(close) < 6:
        return [None] * 12
    rets = close.pct_change().dropna() * 100.0
    if rets.empty:
        return [None] * 12
    cutoff = rets.index.max().year - years
    rets = rets[rets.index.year > cutoff]
    by_month = rets.groupby(rets.index.month)
    vals: list[float | None] = []
    for m in range(1, 13):
        if m not in by_month.groups:
            vals.append(None)
            continue
        g = by_month.get_group(m)
        if metric == "Median Return":
            vals.append(float(g.median()))
        elif metric == "% Positive":
            vals.append(float((g > 0).mean() * 100.0))
        else:  # "Avg Return"
            vals.append(float(g.mean()))
    return vals


def build_monthly_table(closes: dict[str, pd.Series], years: int,
                        metric: str) -> pd.DataFrame:
    """Table indexed by ticker, columns Jan..Dec, values = chosen metric."""
    rows = {t: seasonality_row(c, years, metric) for t, c in closes.items()}
    return pd.DataFrame.from_dict(rows, orient="index", columns=MONTHS)


def vix_stats(vix_close: pd.Series, spy_close: pd.Series | None) -> dict | None:
    """Current VIX, 52w IV-rank/hi/lo, and SPY 30-day realized vol (annualized %).
    None if VIX data is too thin."""
    if vix_close is None or len(vix_close) < 20:
        return None
    cur = float(vix_close.iloc[-1])
    hi = float(vix_close.max())
    lo = float(vix_close.min())
    rank = ((cur - lo) / (hi - lo) * 100.0) if hi > lo else 0.0
    rv = None
    if spy_close is not None and len(spy_close) > 31:
        daily = spy_close.pct_change().dropna().tail(30)
        rv = float(daily.std() * (252 ** 0.5) * 100.0)
    return {"cur": cur, "hi": hi, "lo": lo, "rank": rank, "rv": rv}
