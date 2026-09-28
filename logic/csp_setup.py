"""CSP Setup + Quality — the two-pillar CSP entry model (pure, no fetching).

Mirrors the LEAP scanner but CSP has THREE setups and a Quality gate:

Pillar 1 — Setup ✓ (any one):
  • Reversal    — RSI(14)<40 + lower-BB touch + green candle   (= LEAP Path A)
  • Deep Value  — RSI(14)<35 + whole candle below the band     (= LEAP Path B)
  • IV Drop     — red-day, two-tier (matches WatchList.gs IV÷20 + an IV÷15 tier):
        🟢 green  = Chg% ≤ −(IV ÷ 15)          (full)
        🟠 orange = −(IV/15) < Chg% ≤ −(IV/20) (approaching) — still counts

Pillar 2 — Quality ✓ (light scope): RSI(14) < 64 AND not near the high band.
  (AOR-vs-VIX-floor is shown as context now; the full AOR calc is a later scope.)

evaluate() takes a logic.leap_setup.evaluate() result (for RSI/BB/path) plus the
name's IV% and today's Chg%, so it reuses the Reversal/Deep Value math verbatim.
"""

from __future__ import annotations


_LOW_VIX = 17.0   # "Low VIX" cutoff for the Mid-Band Entry setup


def evaluate(leap_result: dict, iv_pct: float | None, chg_pct: float | None,
             earnings_days: int | None = None, veto_dte: int = 30,
             vix: float | None = None) -> dict:
    """leap_result: output of logic.leap_setup.evaluate(). iv_pct/chg_pct in
    percent (e.g. 25.0 and -2.37). earnings_days = days to next earnings. vix =
    current VIX (for the Mid-Band Entry setup). Returns setups + quality + VETO.

    VETO: earnings inside the CSP window (≤ veto_dte days) blocks the entry no
    matter how good the setup — "earnings = enemy of CSP" (a CSP is naked short
    downside into a binary event). Actionable = Setup ✓ AND Quality ✓ AND no veto."""
    path = leap_result.get("path")
    reversal = path in ("A", "A+B")
    deep_value = path in ("B", "A+B")
    rsi14 = leap_result.get("rsi14")
    bb = leap_result.get("bb_pos")

    iv_tier = "—"
    if iv_pct and chg_pct is not None:
        if chg_pct <= -(iv_pct / 15.0):
            iv_tier = "green"
        elif chg_pct <= -(iv_pct / 20.0):
            iv_tier = "orange"

    # Mid-Band Entry — calm-market premium: Low VIX + just above Mid BB + RSI ≤65.
    # (The Δ≥0.20 / AOR≥24% guardrails are verified by the scanner's strike columns.)
    low_vix = vix is not None and vix <= _LOW_VIX
    mid_band = bool(low_vix and bb == "Mid Band" and rsi14 is not None and rsi14 <= 65)

    # 50 SMA Reclaim — a recovery reclaiming its 50-day line, turn confirmed by MACD.
    #   ≥20% off the 52-week high (recovery, not a breakout) · price AT the 50 SMA
    #   (-3%..+2%, not past it) · MACD histogram > 0 and rising · RSI ≤ 65.
    price = leap_result.get("price")
    off_high = leap_result.get("off_high_pct")
    sma50 = leap_result.get("sma50")
    macd_hist = leap_result.get("macd_hist")
    macd_rising = leap_result.get("macd_rising")
    dist50 = ((price - sma50) / sma50 * 100) if (price and sma50) else None
    sma_reclaim = bool(
        off_high is not None and off_high >= 20
        and dist50 is not None and -3.0 <= dist50 <= 2.0
        and macd_hist is not None and macd_hist > 0 and macd_rising
        and rsi14 is not None and rsi14 <= 65
    )

    names = []
    if reversal:
        names.append("Reversal")
    if deep_value:
        names.append("Deep Value")
    if iv_tier == "green":
        names.append("IV🟢")
    elif iv_tier == "orange":
        names.append("IV🟠")
    if mid_band:
        names.append("Mid-Band")
    if sma_reclaim:
        names.append("50SMA Reclaim")
    setup_ok = bool(names)

    rsi_ok = rsi14 is not None and rsi14 < 64
    not_near_high = bb not in ("Upper Half", "Above Upper")
    quality_ok = bool(rsi_ok and not_near_high)

    earnings_veto = earnings_days is not None and 0 <= earnings_days <= veto_dte
    actionable = bool(setup_ok and quality_ok and not earnings_veto)

    return {
        "setups": names,
        "setup_ok": setup_ok,
        "iv_tier": iv_tier,
        "mid_band": mid_band,
        "sma_reclaim": sma_reclaim,
        "quality_ok": quality_ok,
        "rsi_ok": rsi_ok,
        "not_near_high": not_near_high,
        "earnings_veto": earnings_veto,
        "actionable": actionable,
    }


def vix_floor(vix: float | None) -> tuple[str, str]:
    """(regime label, AOR-floor text) per the VIX-regime AOR flex rule."""
    if vix is None:
        return "—", "—"
    if vix <= 17:
        return "VIX ≤17", "24% Growth / 30% hi-IV"
    if vix <= 20:
        return "VIX 17–20", "30% Growth / 40% hi-IV (Δ25–30)"
    return "VIX >20", "40%+"


def vix_floor_default(vix: float | None) -> int:
    """The single numeric AOR floor to seed the scanner from — the Growth (base)
    number of the VIX regime (24 / 30 / 40). 30 when VIX is unknown."""
    if vix is None:
        return 30
    if vix <= 17:
        return 24
    if vix <= 20:
        return 30
    return 40


def parse_iv(raw) -> float | None:
    """'25%' / '0.25' / 25 → 25.0 (percent). None if not parseable."""
    if raw is None:
        return None
    try:
        v = float(str(raw).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None
    if v != v:                                # NaN (e.g. a "nan" cell)
        return None
    return v * 100 if 0 < v < 1.5 else v      # decimal → percent
