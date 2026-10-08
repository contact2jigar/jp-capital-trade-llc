"""LEAP Setup filter — Rule 4 of the Hyperscaler LEAP Doctrine (pure).

The Setup is the ONLY gate. Two valid paths (either qualifies):
  Path A — Stretch + Turn: RSI(9 or 14) < 40 AND touched lower BB(20,2) in the
           last ~3 days AND a green candle today (the turn).
  Path B — Deep Stretch:   RSI(9 or 14) < 35 AND close BELOW the lower band
           (outside — magnitude alone qualifies, no candle needed).
  Setup ✓ = Path A OR Path B.

HM / 20SMA / MACD are confirmation ("icing") — computed here for display but
they NEVER gate the setup. Entry execution is fixed (Δ0.70 flip) and manual, so
this module only decides whether a name is a valid setup right now.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_TOUCH_LOOKBACK = 3


def _wilder_rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _pctb(c, lb, ub):
    """Bollinger %B = (close - lower) / (upper - lower). None if not computable."""
    if lb is None or ub is None or ub <= lb:
        return None
    return (c - lb) / (ub - lb)


def _bb_position(c, hi, lo, lb, mb, ub) -> str:
    """Readable BB stage. The lower stages read the CANDLE (matches "completely
    out of the band"): whole candle below vs straddling. Upper stages read the
    close via %B."""
    if None in (lb, mb, ub):
        return "—"
    if hi is not None and hi < lb:
        return "Below Band"          # whole candle below the band → completely out
    if lo is not None and lo <= lb:
        return "At Lower"            # band runs through the candle (touch / straddle)
    p = _pctb(c, lb, ub)
    if p is None:
        return "—"
    if p >= 1.0:
        return "Above Upper"
    if p >= 0.75:
        return "Upper Half"          # top quarter of the band — the Gate 3 veto zone
    if p >= 0.45:
        return "Mid Band"            # above mid but not near the top — actionable
    return "Lower Half"


def evaluate(df: pd.DataFrame) -> dict:
    """df: daily OHLC (any case), ≥ ~30 bars. Returns the Setup verdict + the
    LEAP Scanner columns (RSI9/14, BB, path, 52W discount, 20SMA, MACD)."""
    d = df.copy()
    d.columns = [c.lower() for c in d.columns]
    if "close" not in d or len(d) < 30:
        return {"setup_ok": False, "path": "—", "rsi14": None, "bb_pos": "—"}

    close, high, low, opn = d["close"], d["high"], d["low"], d["open"]
    rsi14 = _wilder_rsi(close, 14)                            # standard RSI, only one
    mid = close.rolling(20).mean()
    sd = close.rolling(20).std()
    lower, upper = mid - 2 * sd, mid + 2 * sd

    c = float(close.iloc[-1])
    o = float(opn.iloc[-1])
    hi = float(high.iloc[-1])
    lo = float(low.iloc[-1])
    prev = float(close.iloc[-2])
    prev2 = float(close.iloc[-3]) if len(close) >= 3 else prev   # for the 2-day change (IV Drop 2-Day)
    c1w = float(close.iloc[-6]) if len(close) >= 6 else None     # ~1 trading week ago
    c1m = float(close.iloc[-22]) if len(close) >= 22 else None   # ~1 trading month ago
    r14 = None if pd.isna(rsi14.iloc[-1]) else float(rsi14.iloc[-1])
    lb = None if pd.isna(lower.iloc[-1]) else float(lower.iloc[-1])
    mb = None if pd.isna(mid.iloc[-1]) else float(mid.iloc[-1])
    ub = None if pd.isna(upper.iloc[-1]) else float(upper.iloc[-1])

    def rsi_lt(thr):
        return r14 is not None and r14 < thr

    green = c > o
    touched = bool((low.iloc[-_TOUCH_LOOKBACK:] <= lower.iloc[-_TOUCH_LOOKBACK:]).any())
    fully_below = bool(lb is not None and hi < lb)            # whole candle below the band

    path_a = bool(rsi_lt(40) and touched and green)          # Stretch + Turn
    path_b = bool(rsi_lt(35) and fully_below)                # Deep Stretch (completely out)
    setup_ok = path_a or path_b
    path = "A+B" if (path_a and path_b) else ("A" if path_a else ("B" if path_b else "—"))

    # ── Icing: MACD(12,26,9) direction + price-vs-20/50 SMA ──
    macd = _ema(close, 12) - _ema(close, 26)
    hist = macd - _ema(macd, 9)
    macd_rising = bool(len(hist) >= 2 and hist.iloc[-1] > hist.iloc[-2])
    macd_dir = "▲" if macd_rising else "▼"
    macd_hist = None if pd.isna(hist.iloc[-1]) else float(hist.iloc[-1])

    sma50 = close.rolling(50).mean()
    s50 = None if pd.isna(sma50.iloc[-1]) else float(sma50.iloc[-1])

    hi52 = float(high.tail(252).max())
    off_high = (hi52 - c) / hi52 * 100 if hi52 else None

    return {
        "price": c,
        "chg_pct": (c - prev) / prev * 100 if prev else None,
        "chg_2d_pct": (c - prev2) / prev2 * 100 if prev2 else None,   # 2-day cumulative change
        "chg_1w_pct": (c - c1w) / c1w * 100 if c1w else None,         # ~1-week change
        "chg_1m_pct": (c - c1m) / c1m * 100 if c1m else None,         # ~1-month change
        "rsi14": r14,
        "bb_pos": _bb_position(c, hi, lo, lb, mb, ub),
        "bb_pct": (lambda p: None if p is None else round(p * 100))(_pctb(c, lb, ub)),  # %B 0-100
        "path": path, "setup_ok": setup_ok,
        "green": green, "touched": touched, "fully_below": fully_below,
        "high_52w": hi52, "off_high_pct": off_high,
        "sma20_above": None if mb is None else bool(c > mb),   # BB mid = 20-day SMA
        "sma50": s50,
        "macd_dir": macd_dir, "macd_hist": macd_hist, "macd_rising": macd_rising,
    }
