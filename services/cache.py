"""Shared cache TTLs + helpers. Every service caches through here so refresh
behavior is consistent and tunable in one place.

    from services.cache import TTL, cached

    @cached(TTL["price"])
    def get_price(ticker): ...
"""

from __future__ import annotations

import streamlit as st

# Seconds. Tune here, everywhere follows.
TTL = {
    "price":        30,      # live-ish quotes
    "option":       30,      # delta / premium / bid-ask
    "chain":        60,      # full option chain
    "history":      900,     # OHLC bars (15 min)
    "fundamentals": 3600,    # slow-moving company data (1 h)
    "earnings":     3600,
    "gsheet":       120,     # read-only sheet pull (2 min)
}


def cached(ttl: int, show_spinner: bool = False):
    """Thin wrapper over st.cache_data with a standard signature."""
    return st.cache_data(ttl=ttl, show_spinner=show_spinner)
