"""Risk Gates — the 7 portfolio gates. All must stay green before any new CSP."""

from __future__ import annotations

import streamlit as st

from ui import components

# Per-gate accent bars (read on both Dark and Grey themes).
_BLUE, _GREEN, _GOLD, _TEAL, _CORAL, _MAGENTA, _INDIGO = (
    "#58a6ff", "#43c463", "#e3b23c", "#3fd0c9", "#f2726f", "#c586e0", "#7c8cff")


def render(c: dict) -> None:
    st.caption("Portfolio-level guardrails — miss any and it's **roll-only until green**.")

    st.markdown(components.gates_table_card(
        c,
        gates=[
            (_BLUE, "⚖️", "VIX Allocation",
             "Follow the VIX-Flex regime band. Up/Down regime uses SPY versus its 100-day SMA; "
             "remain within the Monitor Board target.",
             "Controls total deployment by market regime"),
            (_GREEN, "💰", "AOR",
             "AOR above 40% · Delta ≤ 0.30 · 21–30 DTE. Hyperscalers may use only the approved exception.",
             "Requires sufficient return for the risk taken"),
            (_GOLD, "🚦", "CC Breaker",
             "CC + ITM puts below 45% of Wheel Capital; LEAP excluded. 30–45% is elite-only; "
             "≥45% freezes new CSPs.",
             "Prevents covered-call and assignment congestion"),
            (_TEAL, "⚓", "Name Cap",
             "Total exposure below 5% of capital per stock — CSP + LEAP + owned shares combined. "
             "Only a fresh name's first lot may reach 7%; never top a position past 5%.",
             "Limits single-name concentration"),
            (_CORAL, "🪜", "Layer Deployment",
             "Max 2.5% per account, per stock, on the same day across both accounts. "
             "Layer 2/3 requires ≥1 week, ≥5% decline and a fresh setup.",
             "Stops premature averaging and oversized entries"),
            (_MAGENTA, "🚀", "LEAP",
             "Max two positions per account and ≤2% of Wheel Capital per account. "
             "Separate category · Delta 0.70 flip · GTC exit at 10–15%.",
             "Keeps directional exposure separate and bounded"),
            (_INDIGO, "🏛️", "Cash Vault",
             "Cash must remain ≥30% of the account's own all-time high. "
             "Falling below the floor freezes new trades; never relaxed.",
             "Protects liquidity and assignment capacity"),
        ],
        footer="MISS ANY → NO NEW CSP · Roll-only until green",
    ), unsafe_allow_html=True)
