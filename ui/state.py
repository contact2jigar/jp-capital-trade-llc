"""Cross-page state that survives a full reload.

The top-nav tabs are anchor links, so clicking one does a real browser navigation
that wipes ``st.session_state``. A ``cache_resource`` dict lives in the server
process instead, so the last Candidate Hunt (scan + meta) persists across tab
switches. Single-user app, so a shared store is fine.
"""

from __future__ import annotations

import streamlit as st


@st.cache_resource(show_spinner=False)
def hunt_store() -> dict:
    return {}


def save_hunt(scan, meta) -> None:
    s = hunt_store()
    s["scan"], s["meta"] = scan, meta


def load_hunt():
    """(scan_df, meta) — from session_state first (same session), else the store."""
    scan = st.session_state.get("csp_scan")
    meta = st.session_state.get("csp_scan_meta")
    if scan is None:
        s = hunt_store()
        scan, meta = s.get("scan"), s.get("meta")
    return scan, meta


def save_fidelity(positions: list, meta: dict) -> None:
    """Uploaded Fidelity positions — kept app-wide for the life of the server."""
    s = hunt_store()
    s["fidelity"], s["fidelity_meta"] = positions, meta


def load_fidelity():
    """(positions, meta) or (None, None) — usable by any panel, survives tab switches."""
    s = hunt_store()
    return s.get("fidelity"), s.get("fidelity_meta")


def save_hunt_inputs(inp: dict) -> None:
    """The last Candidate-Hunt scan inputs, so Decision Desk can re-run the hunt."""
    hunt_store()["inputs"] = inp


def load_hunt_inputs():
    return hunt_store().get("inputs")
