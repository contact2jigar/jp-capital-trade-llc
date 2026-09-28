"""📈 Performance — monthly IRA · LLC · SPY · QQQ · Total, mirrored from the sheet's
Performance tab. Read-only; the sheet is the source of truth."""

from __future__ import annotations

import re

import streamlit as st

from services import gsheet

# Column groups in the Performance grid (0-indexed): the %-change column of each.
_PCT_COLS = {4, 8, 12, 16, 19}          # IRA/LLC/SPY/QQQ %Chg + Total % Return
_CHG_COLS = {3, 7, 11, 15}              # IRA/LLC/SPY/QQQ Chg
_SUMMARY = [(1, "IRA"), (5, "LLC"), (9, "SPY"), (13, "QQQ"), (17, "Total")]


@st.cache_data(ttl=300, show_spinner=False)
def _grid():
    return gsheet.performance()


def _neg(s: str) -> bool:
    return "-" in str(s) or "(" in str(s)


def _summary_cards(c, row0):
    cards = []
    for col, name in _SUMMARY:
        raw = str(row0[col]).strip() if col < len(row0) else ""
        # "IRA: +$156,222.00 (+19.34%)" → value + pct
        m = re.search(r":\s*(.+?)\s*\((.+?)\)", raw)
        val = m.group(1) if m else raw
        pct = m.group(2) if m else ""
        col_hex = c["neg"] if _neg(val) else c["pos"]
        cards.append(
            f"<div style='flex:1;min-width:150px;background:{c['panel']};border:1px solid {c['border']};"
            f"border-radius:11px;padding:13px 15px;'>"
            f"<div style='font-size:10px;font-weight:900;letter-spacing:.06em;color:{c['muted']};'>{name}</div>"
            f"<div style='margin-top:4px;font-size:20px;font-weight:950;color:{col_hex};'>{val}</div>"
            f"<div style='margin-top:2px;font-size:12px;font-weight:800;color:{col_hex};'>{pct}</div></div>")
    return f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;'>{''.join(cards)}</div>"


def _table(c, header, rows):
    head = "".join(
        f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:7px 9px;text-align:{'left' if i == 0 else 'right'};"
        f"font-weight:700;font-size:10.5px;white-space:nowrap;'>{h}</th>" for i, h in enumerate(header))
    body = ""
    for r in rows:
        tds = ""
        for i, h in enumerate(header):
            v = str(r[i]).strip() if i < len(r) else ""
            base = (f"border:1px solid {c['border']};padding:6px 9px;color:{c['text']};"
                    f"white-space:nowrap;text-align:{'left' if i == 0 else 'right'};font-size:11.5px;")
            if i in _PCT_COLS or i in _CHG_COLS:
                if v and v not in ("0", "0.00%", "—"):
                    base += f"color:{c['neg'] if _neg(v) else c['pos']};font-weight:800;"
            if i == 0:
                base += "font-weight:800;"
            tds += f"<td style='{base}'>{v or '—'}</td>"
        body += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:640px;border:1px solid {c['border']};border-radius:9px;'>"
            f"<table style='border-collapse:collapse;font-size:12px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def render(c: dict) -> None:
    st.caption("Monthly IRA · LLC vs SPY · QQQ — mirrored live from the sheet's Performance tab.")
    grid = _grid()
    if grid.empty or len(grid) < 3:
        st.warning("Couldn't load the Performance tab.")
        return
    rows = grid.values.tolist()
    st.markdown(_summary_cards(c, rows[0]), unsafe_allow_html=True)
    header = [str(x).strip() for x in rows[1]]
    data = [r for r in rows[2:] if str(r[0]).strip()]
    st.markdown(_table(c, header, data), unsafe_allow_html=True)
