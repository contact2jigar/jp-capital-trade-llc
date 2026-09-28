"""🧮 Allocation — per-account capital allocation by stock, mirrored from the
sheet's Allocation tab (LLC cols A–H, IRA cols K–S). Read-only."""

from __future__ import annotations

import streamlit as st

from services import gsheet

# Column indices in the raw Allocation grid.
_LLC = [0, 1, 2, 3, 4, 5, 6, 7]                 # Group·Stock·P/L·%Alloc·CashRes·CurPx·Qty·Strike
_IRA = [10, 11, 12, 13, 14, 15, 16, 17, 18]     # …·%Ret·Strike (IRA has the extra %Ret col)
_LLC_HEAD = ["", "Stock", "Profit Loss", "% Alloc", "Cash Reserve", "Current Price", "Qty", "Strike"]
_IRA_HEAD = ["", "Stock", "Profit Loss", "% Alloc", "Cash Reserve", "Current Price", "Qty", "% Ret", "Strike"]
_RIGHT = {"Profit Loss", "% Alloc", "Cash Reserve", "Current Price", "Qty", "% Ret", "Strike"}
_COLOR = {"Profit Loss", "% Ret"}               # green/red by sign


@st.cache_data(ttl=300, show_spinner=False)
def _grid():
    return gsheet.allocation()


def _neg(s: str) -> bool:
    return str(s).strip().startswith("-")


def _table(c, head, cols, rows):
    hh = "".join(
        f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:6px 8px;text-align:{'right' if h in _RIGHT else 'left'};"
        f"font-weight:700;font-size:10.5px;white-space:nowrap;'>{h}</th>" for h in head)
    body = ""
    for r in rows:
        vals = [str(r[i]).strip() if i < len(r) else "" for i in cols]
        if not any(vals):
            continue
        is_total = "Total" in vals[0] or "Grand" in vals[0]
        grp = vals[0] and "Total" not in vals[0] and "Grand" not in vals[0]  # a group header label
        tds = ""
        for h, v in zip(head, vals):
            base = (f"border:1px solid {c['border']};padding:5px 8px;color:{c['text']};"
                    f"white-space:nowrap;text-align:{'right' if h in _RIGHT else 'left'};font-size:11.5px;")
            if is_total:
                base += f"font-weight:800;background:{c['raised']};"
            elif grp and h == "":
                base += "font-weight:800;"
            if h in _COLOR and v and v not in ("0", "0.00%", "—"):
                base += f"color:{c['neg'] if _neg(v) else c['pos']};font-weight:700;"
            tds += f"<td style='{base}'>{v or ''}</td>"
        body += f"<tr>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:640px;border:1px solid {c['border']};border-radius:9px;'>"
            f"<table style='border-collapse:collapse;font-size:12px;width:100%;background:{c['panel']};'>"
            f"<thead><tr>{hh}</tr></thead><tbody>{body}</tbody></table></div>")


def render(c: dict) -> None:
    st.caption("Per-account capital allocation by stock — mirrored live from the sheet's Allocation tab.")
    grid = _grid()
    if grid.empty or len(grid) < 2:
        st.warning("Couldn't load the Allocation tab.")
        return
    rows = grid.values.tolist()[1:]     # skip the LLC/IRA/Stock header row
    left, right = st.columns(2)
    with left:
        st.markdown(f"##### 🟤 LLC")
        st.markdown(_table(c, _LLC_HEAD, _LLC, rows), unsafe_allow_html=True)
    with right:
        st.markdown(f"##### 🟡 IRA")
        st.markdown(_table(c, _IRA_HEAD, _IRA, rows), unsafe_allow_html=True)
