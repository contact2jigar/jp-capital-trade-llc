"""Entry Setup — the CSP Signal Stack (7 setups + Quality Filter)."""

from __future__ import annotations

import streamlit as st

from ui import components

# Per-setup accent bars (read on both Dark and Grey themes).
_BLUE, _GREEN, _TEAL, _INDIGO, _GOLD, _CORAL, _MAGENTA = (
    "#58a6ff", "#43c463", "#3fd0c9", "#7c8cff", "#e3b23c", "#f2726f", "#c586e0")


def render(c: dict) -> None:
    st.caption("A ticker is a **GO** only when at least one setup fires *and* every "
               "quality check passes.")

    st.markdown(components.entry_setup_card(
        c,
        setups=[
            (_BLUE, "📉", "IV Drop",
             "<b>Full:</b> day change ≤ −(IV ÷ 15)&nbsp;·&nbsp;<b>Approach:</b> ≤ −(IV ÷ 20)",
             "One-day volatility shock"),
            (_GREEN, "🔄", "Reversal",
             "RSI(14) &lt; 40 · lower BB touched · green close",
             "Oversold and turning"),
            (_TEAL, "💎", "Deep Value",
             "RSI(14) &lt; 35 · entire candle below lower BB",
             "Whole candle outside band"),
            (_INDIGO, "🕑", "IV Drop 2-Day",
             "Two-day change ≤ −(IV ÷ 15) · IV higher than prior day",
             "Fast two-day selloff"),
            (_GOLD, "🏅", "Quality Pullback",
             "Beats ≥ 3 · ≥20% off high · RSI ≤ 65 · max once/week",
             "Strong name at a discount"),
            (_CORAL, "🎯", "Mid-Band",
             "Red close · above mid BB · below upper half · RSI ≤ 65",
             "Controlled pullback"),
            (_MAGENTA, "📈", "50-SMA Reclaim",
             "≥20% off 52w high · within −3%/+2% of SMA50 · MACD histogram positive and rising · RSI ≤ 65",
             "Secondary recovery setup"),
        ],
        checks=[
            ("📅", "Earnings", "Outside the CSP expiry window"),
            ("🌡️", "RSI(14)", "≤ 65; not overbought"),
            ("💰", "AOR", "Meets the normal floor"),
            ("Δ", "Delta", "≤ 0.30"),
            ("⏳", "DTE", "21–30 preferred"),
            ("📊", "BB Position", "Not near the upper half"),
        ],
    ), unsafe_allow_html=True)
