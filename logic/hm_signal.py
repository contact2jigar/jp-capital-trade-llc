"""HM signal engine — the "LEAP Traffic Light" (RSI9 + EMA3 + WMA21).

Ported verbatim from the old app's strategies/hm_indicator/engine.py (pure
numpy/pandas — no Streamlit, no fetching). Emits the 5-color state per bar
(GOLD/RED/ORANGE/GREEN/BLUE) plus the de-duplicated gold_trigger / red_trigger /
strong_gold signals. `analyze(df, interval)` is the one entry point; `df` needs
a lowercase 'close' column.

5-color taxonomy:
  GOLD   — entry trigger fired            (chart marker: BUY / STRONG GOLD)
  RED    — exit trigger fired             (chart marker: SELL)
  ORANGE — bottom compression forming
  GREEN  — volume sustained above 50 (hold)
  BLUE   — setup forming, no trigger yet

Source video: https://www.youtube.com/watch?v=IKmNFIGVg8w
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ─── Tunable thresholds ──────────────────────────────────────────────────────
GOLD_COOLDOWN_BARS = 5
RED_COOLDOWN_BARS = 1
FLIP_LOOKBACK_BARS = 5
CROSS_WINDOW_BARS = 3
RSI_MOVE_THRESHOLD = 5.0
GAP_THRESHOLD = 8.0
RED_GAP_THRESHOLD = 5.0


# ─── Trigger de-clustering ───────────────────────────────────────────────────
def _apply_cooldown(triggers: pd.Series, cooldown: int) -> pd.Series:
    out = pd.Series(False, index=triggers.index)
    last_idx = -10**9
    for i, fired in enumerate(triggers.values):
        if bool(fired) and (i - last_idx) > cooldown:
            out.iloc[i] = True
            last_idx = i
    return out


def _apply_window_cooldown(triggers: pd.Series, cooldown: int, fire_days: int = 2) -> pd.Series:
    out = pd.Series(False, index=triggers.index)
    last_initial_idx = -10**9
    n = len(triggers)
    for i, fired in enumerate(triggers.values):
        gap = i - last_initial_idx
        if bool(fired) and gap > cooldown:
            out.iloc[i] = True
            last_initial_idx = i
            for d in range(1, fire_days):
                if i + d < n:
                    out.iloc[i + d] = True
    return out


# ─── Indicator math ──────────────────────────────────────────────────────────
def compute_rsi_wilder(close: pd.Series, period: int = 9) -> pd.Series:
    """Standard Wilder's RSI — matches Yahoo Finance."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_wma(series: pd.Series, period: int = 21) -> pd.Series:
    """Linear-weighted moving average — most recent bar gets highest weight."""
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weight_sum, raw=True)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add rsi9, ema3, wma21 columns to a daily OHLC dataframe ('close' column)."""
    out = df.copy()
    out["rsi9"] = compute_rsi_wilder(out["close"], period=9)
    out["ema3"] = out["rsi9"].ewm(span=3, adjust=False).mean()
    out["wma21"] = compute_wma(out["rsi9"], period=21)
    return out


# ─── Signal detection ────────────────────────────────────────────────────────
def find_gold_triggers(df: pd.DataFrame, interval: str = "1d") -> pd.Series:
    """🟡 GOLD — entry trigger. WMA below fast cluster + WMA-tiered gap + both
    fast lines rising."""
    if interval == "1wk":
        deep_gap_min, mid_gap_min = 6.0, 4.0
    else:
        deep_gap_min, mid_gap_min = 8.0, 5.0

    rsi = df["rsi9"].astype(float)
    ema = df["ema3"].astype(float)
    wma = df["wma21"].astype(float)

    wma_below_fast = (wma < rsi) & (wma < ema)
    gap = np.minimum(rsi, ema) - wma
    deep_tier = (wma < 45.0) & (gap >= deep_gap_min)
    mid_tier = (wma >= 45.0) & (wma < 65.0) & (gap >= mid_gap_min)
    tier_ok = deep_tier | mid_tier
    rising = (rsi > rsi.shift(1)) & (ema > ema.shift(1))
    return (wma_below_fast & tier_ok & rising).fillna(False)


def find_red_triggers(df: pd.DataFrame, interval: str = "1d") -> pd.Series:
    """🔴 RED — exit trigger. WMA above fast cluster + EMA rolling down."""
    rsi = df["rsi9"].astype(float)
    ema = df["ema3"].astype(float)
    wma = df["wma21"].astype(float)
    wma_highest = (wma > rsi) & (wma > ema)
    ema_falling = ema < ema.shift(1)
    return (wma_highest & ema_falling).fillna(False)


def find_red_triggers_legacy(df: pd.DataFrame) -> pd.Series:
    """RED — legacy v21 structural flip only (kept for chart comparison)."""
    rsi = df["rsi9"].astype(float)
    ema = df["ema3"].astype(float)
    wma = df["wma21"].astype(float)
    c1 = (wma > rsi) & (wma > ema)
    rsi_above_ema = rsi > ema
    cross_event = rsi_above_ema != rsi_above_ema.shift(1)
    crossed_recently = cross_event.rolling(CROSS_WINDOW_BARS, min_periods=1).max().astype(bool)
    c2 = crossed_recently & (rsi < rsi.shift(1)) & (ema < ema.shift(1))
    wma_was_below = (wma.shift(1) < rsi.shift(1)) & (wma.shift(1) < ema.shift(1))
    for k in range(2, FLIP_LOOKBACK_BARS + 1):
        wma_was_below = wma_was_below | (
            (wma.shift(k) < rsi.shift(k)) & (wma.shift(k) < ema.shift(k)))
    raw = (c1 & c2 & wma_was_below).fillna(False)
    return _apply_window_cooldown(raw, cooldown=RED_COOLDOWN_BARS, fire_days=2)


def find_orange_states(df: pd.DataFrame) -> pd.Series:
    """🟠 ORANGE — bottom compression (all 3 lines deep-blue <35 and clustered ≤5)."""
    rsi = df["rsi9"].astype(float)
    ema = df["ema3"].astype(float)
    wma = df["wma21"].astype(float)
    triple_max = pd.concat([rsi, ema, wma], axis=1).max(axis=1)
    triple_min = pd.concat([rsi, ema, wma], axis=1).min(axis=1)
    deep_blue = triple_max < 35.0
    tight_cluster = (triple_max - triple_min) <= 5.0
    return (deep_blue & tight_cluster).fillna(False)


# ─── Bar-by-bar color classification ─────────────────────────────────────────
def classify_bars(df: pd.DataFrame, interval: str = "1d") -> pd.Series:
    work = df if "wma21" in df.columns else compute_indicators(df)
    rsi = work["rsi9"].astype(float)
    ema = work["ema3"].astype(float)
    wma = work["wma21"].astype(float)

    gold = find_gold_triggers(work, interval=interval)
    red = find_red_triggers(work, interval=interval)
    orange = find_orange_states(work)
    in_green = (rsi > 50.0) & (ema > 50.0) & (wma < rsi) & (wma < ema)

    out = pd.Series("BLUE", index=df.index, dtype=object)
    out[in_green] = "GREEN"
    out[orange] = "ORANGE"
    out[gold] = "GOLD"
    out[red] = "RED"
    return out


# ─── State-alternation dedupe ────────────────────────────────────────────────
def _alternate_state(raw_gold: pd.Series, raw_red: pd.Series) -> tuple[pd.Series, pd.Series]:
    """One BUY per bottom leg, one SELL per top leg. RED wins same-bar collisions."""
    n = len(raw_gold)
    gold_out = np.zeros(n, dtype=bool)
    red_out = np.zeros(n, dtype=bool)
    state = "NONE"
    g_arr = raw_gold.values
    r_arr = raw_red.values
    for i in range(n):
        if r_arr[i] and state != "RED":
            red_out[i] = True
            state = "RED"
        elif g_arr[i] and state != "GOLD":
            gold_out[i] = True
            state = "GOLD"
    return (pd.Series(gold_out, index=raw_gold.index),
            pd.Series(red_out, index=raw_red.index))


# ─── Strong GOLD — deep-bottom-pop pattern ───────────────────────────────────
STRONG_GOLD_WMA_MAX = 45.0


def find_strong_gold_triggers(gold_triggers: pd.Series, wma_series: pd.Series,
                              wma_max: float = STRONG_GOLD_WMA_MAX) -> pd.Series:
    """🥇 STRONG GOLD — GOLD fired while WMA21 is still deep (<45): room to run."""
    deep_at_fire = (wma_series < float(wma_max)).fillna(False)
    return (gold_triggers & deep_at_fire).fillna(False)


# ─── Convenience: full pipeline ──────────────────────────────────────────────
def analyze(df: pd.DataFrame, interval: str = "1d") -> pd.DataFrame:
    """Take an OHLC dataframe ('close' column), return it with indicator + color
    columns and the FINAL de-duplicated gold_trigger / red_trigger / strong_gold."""
    out = compute_indicators(df)
    raw_gold = find_gold_triggers(out, interval=interval)
    raw_red = find_red_triggers(out, interval=interval)

    gold, red = _alternate_state(raw_gold, raw_red)
    out["gold_trigger"] = gold
    out["red_trigger"] = red
    out["red_trigger_legacy"] = find_red_triggers_legacy(out)
    out["color"] = classify_bars(out, interval=interval)
    out["orange_state"] = find_orange_states(out)
    out["strong_gold"] = find_strong_gold_triggers(gold, out["wma21"])
    return out


# ─── Scanner helper — latest actionable state for one ticker ─────────────────
def latest_signal(adf: pd.DataFrame) -> dict:
    """Summarize the most recent HM state from an analyzed frame (output of
    analyze()). Returns the current state chip + the latest BUY / SELL /
    STRONG GOLD marker and how many bars ago it fired."""
    if adf is None or adf.empty:
        return {}
    last = adf.iloc[-1]
    n = len(adf)

    def _last_true(col):
        hits = np.flatnonzero(adf[col].to_numpy())
        return int(hits[-1]) if len(hits) else None

    g = _last_true("gold_trigger")
    r = _last_true("red_trigger")
    sg = _last_true("strong_gold")

    signal, sig_pos = "—", None
    if g is not None and (r is None or g >= r):
        signal = "STRONG GOLD" if (sg is not None and sg == g) else "BUY"
        sig_pos = g
    elif r is not None:
        signal, sig_pos = "SELL", r

    return {
        "state": str(last["color"]),
        "signal": signal,
        "bars_ago": (n - 1 - sig_pos) if sig_pos is not None else None,
        "signal_date": adf.index[sig_pos] if sig_pos is not None else None,
        "rsi9": float(last["rsi9"]) if pd.notna(last["rsi9"]) else None,
        "ema3": float(last["ema3"]) if pd.notna(last["ema3"]) else None,
        "wma21": float(last["wma21"]) if pd.notna(last["wma21"]) else None,
        "close": float(last["close"]) if pd.notna(last["close"]) else None,
    }
