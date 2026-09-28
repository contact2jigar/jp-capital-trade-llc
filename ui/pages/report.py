"""📄 Report — one-click branded PDF of Monitor Board · Decision Desk (Action
Queue) · P/L · Performance · Allocation. Generated server-side with reportlab."""

from __future__ import annotations

import datetime

import streamlit as st

from logic import pdf_report
from ui import state


def render(c: dict) -> None:
    st.caption("A branded PDF snapshot of the whole book — Monitor Board, Decision Desk "
               "(with the Portfolio Action Queue), P/L, Performance and Allocation.")

    fid, _ = state.load_fidelity()
    gtc_saved = state.load_gtc_placed()
    gtc_placed = set(gtc_saved) if gtc_saved is not None else None

    st.markdown(
        f"<div style='background:{c['panel']};border:1px solid {c['border']};border-radius:12px;"
        f"padding:16px 18px;margin:6px 0 14px;'>"
        f"<div style='color:{c['text']};font-weight:800;font-size:15px;'>WheelEngine Portfolio Report</div>"
        f"<div style='color:{c['mid']};font-size:12.5px;margin-top:4px;'>Monitor Board · Decision Desk "
        f"(Action Queue{' + GTC status' if gtc_placed is not None else ''}) · P/L · Performance · Allocation</div>"
        f"<div style='color:{c['muted']};font-size:11px;margin-top:6px;'>Live from the TradeLog + sheet. "
        f"{'Fidelity loaded — stuck/CC flags included.' if fid else 'Upload Fidelity on Reconcile for stuck/CC flags.'}"
        f"</div></div>", unsafe_allow_html=True)

    if st.button("📄 Generate PDF report", type="primary"):
        with st.spinner("Building the report…"):
            try:
                pdf = pdf_report.build_report(fidelity=fid, gtc_placed=gtc_placed)
                st.session_state["_report_pdf"] = pdf
            except Exception as e:  # noqa: BLE001
                st.error(f"Couldn't build the report: {e}")
                st.session_state.pop("_report_pdf", None)

    pdf = st.session_state.get("_report_pdf")
    if pdf:
        fname = f"WheelEngine_Report_{datetime.date.today():%Y-%m-%d}.pdf"
        st.download_button("⬇︎ Download PDF", data=pdf, file_name=fname,
                           mime="application/pdf", type="primary")
        st.success(f"Report ready — {len(pdf) // 1024} KB. Click to download.")
