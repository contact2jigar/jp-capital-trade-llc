"""Risk Gates — the 8 portfolio gates (v17, Oct 2 2026). All must stay green before any new CSP."""

from __future__ import annotations

import streamlit as st

from ui import components

# Per-gate accent bars (read on both Dark and Grey themes).
_BLUE, _GREEN, _GOLD, _TEAL, _CORAL, _MAGENTA, _INDIGO, _SLATE = (
    "#58a6ff", "#43c463", "#e3b23c", "#3fd0c9", "#f2726f", "#c586e0", "#7c8cff", "#8aa0b2")


def render(c: dict) -> None:
    st.caption("Portfolio-level guardrails — miss any and it's **roll-only until green**.")

    st.markdown(components.gates_table_card(
        c,
        gates=[
            (_BLUE, "⚖️", "VIX Allocation",
             "Trend · UP = SPY ≥ 100 SMA, DOWN = SPY < 100 SMA · Board shows target %",
             "Controls total deployment according to market risk"),
            (_TEAL, "🎯", "Entry Setup",
             "IV Drop → Reversal → Deep Value → IV Drop 2-Day → Quality Pullback → 50-SMA Recovery "
             "→ Mid-Band · Reference page shows detail",
             "Defines when a new entry is technically valid"),
            (_GREEN, "💰", "AOR",
             "MEGA ≥ 27% · PLTR > 40% · Rest > 47% · GOAL — 1.51% of ATH",
             "Requires enough premium to reach 1.5% of ATH with less deployment"),
            (_GOLD, "🚦", "CC Breaker",
             "Max 40% of wheel capital (CC + ITM puts), LEAP excluded · 5 zones: &lt;25 normal · "
             "25–30 caution · 30–35 elite (60%+ AOR) · 35–40 exceptional + alert · ≥40 ⛔ FREEZE (hard stop)",
             "Keeps capital out of share form — and opens the LEAP lane at the bottom"),
            (_CORAL, "⚓", "Name Cap",
             "< 5% per stock — CSP + LEAP + shares combined · 7% for a 1-lot starter only · "
             "< 4% per stock for Speculation",
             "Don't bet too much on one stock"),
            (_MAGENTA, "🪜", "Layer",
             "2.5% max per stock per week, per account · unless 1 contract",
             "Go in slowly, not all at once"),
            (_INDIGO, "🚀", "LEAP",
             "MEGA or quality names only · TQQQ allowed at VIX ≥ 30 · 2% of wheel capital per account · "
             "max 2 per account · Δ0.70 flip · GTC exit 10-15% · unlock to 5% at 45% breaker and/or VIX ≥ 30",
             "The lane for big names whose IV is too low to pay a CSP"),
            (_SLATE, "🏛️", "Cash Vault",
             "cash ≥ 30% of the account's own ATH · below → freeze · never relaxed",
             "Keeps us safe in a crash and earns 3.1% quietly — never deployed"),
        ],
        footer="MISS ANY → NO NEW CSP · Roll-only until green",
    ), unsafe_allow_html=True)
