"""Shared cached Fundamental Card fetch — used by both Wheel Scanner and LEAP
Scanner so a ticker's ~5 yfinance statement calls happen once per 6h, not once
per page."""

from __future__ import annotations

import streamlit as st


@st.cache_data(ttl=21600, show_spinner=False)   # 6h — fundamentals move slowly
def fund_row(ticker: str) -> dict:
    from logic import fundamental as f
    return f._row_from_result(f.score_ticker(ticker))
