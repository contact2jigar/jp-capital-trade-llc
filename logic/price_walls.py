"""Price Wall Map engine — gamma exposure, Put/Call Wall, Gamma Flip, regime.

Convention (standard GEX):
  - Dealers are net **short calls** and **long puts** (rough simplification).
  - Net dealer gamma per strike = call_γ × call_OI − put_γ × put_OI
  - Positive cumulative gamma above spot → dealers buy dips / sell rips (dampening).
  - Negative cumulative gamma → dealers chase moves (explosive, trending).
  - Gamma Flip = spot level where total signed dealer gamma crosses zero.

Pure: all math runs off the chain DataFrame produced by
services.option_chain.load_chain(). No Streamlit, no fetching.
"""

from __future__ import annotations

import math
from datetime import date as _date

import numpy as np
import pandas as pd

RISK_FREE = 0.04
EPS = 1e-6


def _bs_gamma(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
        return pdf / (S * sigma * math.sqrt(T))
    except Exception:
        return 0.0


def analyze(chain: pd.DataFrame, regime_band_pct: float = 1.0) -> dict | None:
    """Full Price Wall analysis on a chain DataFrame. Returns dict with spot ·
    call_wall · put_wall · gamma_flip · regime · gamma_decay · bands · peaks ·
    per_strike. None if the chain is empty or unusable."""
    if chain is None or chain.empty:
        return None
    spot = float(chain["spot"].iloc[0] or 0)
    if spot <= 0:
        return None

    today = _date.today()
    rows = []
    for _, r in chain.iterrows():
        try:
            exp_d = _date.fromisoformat(r["expiry"])
        except Exception:
            continue
        T = max((exp_d - today).days / 365.0, 1 / 365)
        iv = float(r["iv"] or 0)
        if iv <= 0 or iv > 5:
            continue
        oi = int(r["oi"] or 0)
        if oi <= 0:
            continue
        volume = int(r["volume"] or 0)
        g = _bs_gamma(spot, float(r["strike"]), T, iv)
        gex = g * oi * 100.0 * spot * spot
        signed = gex if r["type"] == "call" else -gex
        rows.append({
            "strike": float(r["strike"]), "type": r["type"], "expiry": r["expiry"],
            "dte": int(r["dte"]), "oi": oi, "volume": volume, "iv": iv, "T": T,
            "gex": gex, "signed": signed,
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)

    per_strike = df.groupby("strike", as_index=False).agg(
        call_gex=("gex",    lambda s: s[df.loc[s.index, "type"] == "call"].sum()),
        put_gex =("gex",    lambda s: s[df.loc[s.index, "type"] == "put"].sum()),
        call_oi =("oi",     lambda s: s[df.loc[s.index, "type"] == "call"].sum()),
        put_oi  =("oi",     lambda s: s[df.loc[s.index, "type"] == "put"].sum()),
        call_vol=("volume", lambda s: s[df.loc[s.index, "type"] == "call"].sum()),
        put_vol =("volume", lambda s: s[df.loc[s.index, "type"] == "put"].sum()),
        net     =("signed", "sum"),
    ).sort_values("strike").reset_index(drop=True)

    above = per_strike[per_strike["strike"] > spot]
    below = per_strike[per_strike["strike"] < spot]
    call_wall = _wall_pick(above, "call_gex", spot, sign=+1, oi_col="call_oi", vol_col="call_vol")
    put_wall  = _wall_pick(below, "put_gex",  spot, sign=-1, oi_col="put_oi",  vol_col="put_vol")
    gamma_flip = _gamma_flip_by_spot(df, spot)

    dist_to_flip = (spot - gamma_flip["strike"]) / spot * 100 if gamma_flip else 0
    if gamma_flip is None:
        regime = "Neutral"
    elif abs(dist_to_flip) < regime_band_pct:
        regime = "Neutral"
    elif dist_to_flip >= 0:
        regime = "Dampening"
    else:
        regime = "Explosive"

    decay = (df.groupby(["expiry", "dte"], as_index=False)
               .agg(gex_total=("gex", "sum")).sort_values("dte"))
    if not decay.empty:
        max_g = max(float(decay["gex_total"].max()), 1.0)
        decay["intensity"] = decay["gex_total"] / max_g
    decay_list = [
        {"bucket": f"{int(r['dte'])}d", "date": r["expiry"],
         "intensity": float(r["intensity"]), "gex": float(r["gex_total"])}
        for _, r in decay.iterrows()
    ]

    cw_strike = (call_wall or {}).get("strike", spot)
    high_band = (per_strike[per_strike["strike"] > cw_strike]
                 .sort_values("call_gex", ascending=False).head(3)["strike"].tolist())
    pw_strike = (put_wall or {}).get("strike", spot)
    low_band = (per_strike[per_strike["strike"] < pw_strike]
                .sort_values("put_gex", ascending=False).head(3)["strike"].tolist())

    def _peak(sub: pd.DataFrame, col: str) -> dict | None:
        if sub is None or sub.empty or sub[col].sum() <= 0:
            return None
        row = sub.loc[sub[col].astype(float).idxmax()]
        return {"strike": float(row["strike"]), "value": int(row[col])}

    return {
        "spot": spot, "call_wall": call_wall, "put_wall": put_wall,
        "gamma_flip": gamma_flip, "regime": regime, "gamma_decay": decay_list,
        "high_band": high_band, "low_band": low_band,
        "oi_peak_below": _peak(below, "put_oi"), "oi_peak_above": _peak(above, "call_oi"),
        "vol_peak_below": _peak(below, "put_vol"), "vol_peak_above": _peak(above, "call_vol"),
        "per_strike": per_strike,
    }


def _wall_pick(df: pd.DataFrame, col: str, spot: float, sign: int,
               oi_col: str | None = None, vol_col: str | None = None) -> dict | None:
    """Strike with the largest magnitude in `col`, packaged with its raw OI/volume
    so a dollar-gamma wall can be cross-checked against raw open interest."""
    if df is None or df.empty:
        return None
    idx = df[col].astype(float).idxmax()
    row = df.loc[idx]
    strike = float(row["strike"])
    return {
        "strike": strike,
        "gamma": float(row[col]),
        "oi": int(row[oi_col]) if oi_col and oi_col in row else None,
        "volume": int(row[vol_col]) if vol_col and vol_col in row else None,
        "dist_pct": (strike - spot) / spot * 100 * (1 if sign > 0 else -1) * (1 if (strike - spot) * sign >= 0 else -1),
    }


def _gamma_flip_by_spot(df: pd.DataFrame, spot: float,
                        span_pct: float = 0.30, steps: int = 121) -> dict | None:
    """Spot level S* at which total signed dealer gamma equals zero. Sweeps S
    across a ±span_pct band and returns the zero-crossing nearest spot."""
    if df is None or df.empty:
        return None
    K = df["strike"].to_numpy(dtype=float)
    iv = df["iv"].to_numpy(dtype=float)
    T = df["T"].to_numpy(dtype=float)
    oi = df["oi"].to_numpy(dtype=float)
    sign = np.where(df["type"].to_numpy() == "call", 1.0, -1.0)

    lo, hi = spot * (1 - span_pct), spot * (1 + span_pct)
    S_grid = np.linspace(lo, hi, steps)

    totals = np.zeros_like(S_grid)
    sqrt_T = np.sqrt(np.maximum(T, 1e-9))
    for j, S in enumerate(S_grid):
        if S <= 0:
            continue
        d1 = (np.log(S / np.maximum(K, EPS))
              + (RISK_FREE + 0.5 * iv * iv) * T) / np.maximum(iv * sqrt_T, EPS)
        pdf = np.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
        gamma = pdf / np.maximum(S * iv * sqrt_T, EPS)
        gex = gamma * oi * 100.0 * S * S * sign
        totals[j] = gex.sum()

    crossings: list[float] = []
    for i in range(1, len(totals)):
        a, b = totals[i - 1], totals[i]
        if (a < 0 < b) or (a > 0 > b):
            x0, x1 = S_grid[i - 1], S_grid[i]
            crossings.append(x0 + (0 - a) * (x1 - x0) / (b - a))
    if crossings:
        flip = min(crossings, key=lambda x: abs(x - spot))
    else:
        j = int(np.argmin(np.abs(totals)))
        flip = float(S_grid[j])
    return {"strike": float(flip), "dist_pct": (flip - spot) / spot * 100}
