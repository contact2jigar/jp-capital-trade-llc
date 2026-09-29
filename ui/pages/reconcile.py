"""🔄 Reconcile — tracked positions (TradeLog) vs a Fidelity CSV export.

Answers Q2: is the book clean? Upload today's Fidelity positions CSV once; it's
kept app-wide for the session (survives tab switches). Every open put/call is
matched by acct·ticker·type·expiry·strike; qty gaps, Fidelity-only and
tracked-only rows are flagged.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from logic import reconcile as rc
from services import gsheet
from ui import state


@st.cache_data(ttl=120, show_spinner=False)
def _tradelog():
    df = gsheet.tradelog()
    if not df.empty:
        df.columns = [str(x).strip() for x in df.columns]
    return df


_STATE_LABEL = {"MATCHED": "MATCHED", "MISMATCH": "MISMATCH",
                "FID_ONLY": "FID ONLY", "TRACKED_ONLY": "TRACKED ONLY"}


def _chip(c, label, n, active, key):
    # A filter as a real button so the click is handled server-side.
    return st.button(f"{label} {n}", key=key, use_container_width=True,
                     type="primary" if active else "secondary")


def _table(c, rows):
    cols = ["Ticker", "State", "Acct", "Type", "Expiry", "Strike", "Tracked Qty",
            "Fidelity Qty", "Δ Qty", "Tracked $", "Fidelity $", "Δ $"]
    aligns = {"Strike": "right", "Tracked Qty": "center", "Fidelity Qty": "center",
              "Δ Qty": "center", "Tracked $": "right", "Fidelity $": "right", "Δ $": "right"}
    head = "".join(
        f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:7px 9px;text-align:{aligns.get(h, 'left')};"
        f"font-weight:700;font-size:11px;white-space:nowrap;'>{h}</th>" for h in cols)
    body = ""
    for r in rows:
        base = f"border:1px solid {c['border']};padding:6px 9px;color:{c['text']};white-space:nowrap;"
        st_key = r["state"]
        badge_bg, badge_fg = {
            "MATCHED": ("rgba(67,196,99,.16)", c["pos"]),
            "MISMATCH": ("rgba(227,166,58,.18)", c["amber"]),
            "FID_ONLY": ("rgba(242,85,90,.14)", c["neg"]),
            "TRACKED_ONLY": ("rgba(125,139,154,.18)", c["muted"]),
        }[st_key]
        badge = (f"<span style='background:{badge_bg};color:{badge_fg};font-weight:800;"
                 f"padding:2px 7px;border-radius:6px;font-size:10.5px;'>{_STATE_LABEL[st_key]}</span>")
        qg = "—" if r["qty_gs"] is None else str(r["qty_gs"])
        qf = "—" if r["qty_fid"] is None else str(r["qty_fid"])
        dq = ""
        if r["qty_gs"] is not None and r["qty_fid"] is not None:
            d = r["qty_fid"] - r["qty_gs"]
            dq = "0" if d == 0 else f"{d:+d}"
        elif r["qty_fid"] is not None:
            dq = f"+{r['qty_fid']}"
        elif r["qty_gs"] is not None:
            dq = f"−{r['qty_gs']}"
        dq_col = c["pos"] if dq in ("0", "") else c["neg"]
        strike = f"${r['strike']:.2f}" if r.get("strike") else "—"
        tv, fv = r.get("tracked_val"), r.get("fid_val")
        tv_s = f"${tv:,.0f}" if tv is not None else "—"
        fv_s = f"${fv:,.0f}" if fv is not None else "—"
        dv = (fv or 0) - (tv or 0)
        # Δ$ only means something for a discrepancy — a clean match has none.
        dv_s = "—" if (r["state"] == "MATCHED" or (tv is None and fv is None)) else f"${dv:+,.0f}"
        dv_col = c["amber"] if (dv_s != "—") else c["muted"]
        tds = (
            f"<td style='{base}font-weight:800;'>{r['ticker']}</td>"
            f"<td style='{base}'>{badge}</td>"
            f"<td style='{base}'>{r['acct']}</td>"
            f"<td style='{base}'>{r['type']}</td>"
            f"<td style='{base}'>{r.get('expiry') or '—'}</td>"
            f"<td style='{base}text-align:right;'>{strike}</td>"
            f"<td style='{base}text-align:center;'>{qg}</td>"
            f"<td style='{base}text-align:center;'>{qf}</td>"
            f"<td style='{base}text-align:center;color:{dq_col};font-weight:700;'>{dq}</td>"
            f"<td style='{base}text-align:right;'>{tv_s}</td>"
            f"<td style='{base}text-align:right;'>{fv_s}</td>"
            f"<td style='{base}text-align:right;color:{dv_col};font-weight:700;'>{dv_s}</td>")
        body += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:560px;border:1px solid {c['border']};border-radius:8px;'>"
            f"<table style='border-collapse:collapse;font-size:12.5px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def render(c: dict) -> None:
    df = _tradelog()

    up = st.file_uploader("Upload / re-sync Fidelity CSV", type=["csv"], key="fid_up",
                          help="Fidelity → Positions → Download. Kept app-wide for this session.")
    if up is not None:
        fid = rc.parse_fidelity(up.getvalue())
        meta = {"name": up.name, "time": datetime.now().strftime("%Y-%m-%d %I:%M %p")}
        state.save_fidelity(fid, meta)

    fid, meta = state.load_fidelity()
    if not fid:
        st.info("Upload your **Fidelity positions CSV** to reconcile against the tracked book. "
                "It stays loaded across tabs for this session.")
        return

    tracked = rc.tracked_from_tradelog(df)
    r = rc.reconcile(tracked, fid)
    s = r["summary"]

    # Status line — loaded count · filename · last uploaded.
    fname = meta.get("name", "Fidelity CSV") if meta else "Fidelity CSV"
    ftime = meta.get("time", "") if meta else ""
    st.markdown(
        f"<div style='display:flex;gap:14px;flex-wrap:wrap;align-items:center;padding:8px 0 2px;'>"
        f"<span style='color:{c['pos']};font-weight:800;'>✓ Loaded {s['fid_positions']}</span>"
        f"<span style='color:{c['muted']};'>{fname} · Last uploaded: {ftime}</span>"
        f"<span style='color:{c['muted']};'>Fidelity cash — "
        + " · ".join(f"{a} ${v:,.0f}" for a, v in sorted(r['fid_cash'].items())) + "</span></div>",
        unsafe_allow_html=True)

    # Filter chips (buttons).
    st.write("")
    chips = [("All", s["total"], "All"), ("✓ Matched", s["matched"], "MATCHED"),
             ("⚠️ Mismatched", s["mismatch"], "MISMATCH"),
             ("📥 Fidelity Only", s["fid_only"], "FID_ONLY"),
             ("📋 Tracked Only", s["tracked_only"], "TRACKED_ONLY")]
    # Default to the problems if there are any, else show everything (a clean book
    # shouldn't land on an empty "Mismatched 0" and look like nothing happened).
    if "recon_filter" not in st.session_state:
        st.session_state["recon_filter"] = (
            "MISMATCH" if (s["mismatch"] or s["fid_only"] or s["tracked_only"]) else "All")
    cur = st.session_state["recon_filter"]
    cboxes = st.columns(len(chips))
    for (label, n, key), col in zip(chips, cboxes):
        with col:
            if _chip(c, label, n, cur == key, f"recon_{key}"):
                st.session_state["recon_filter"] = key
                cur = key

    rows = r["rows"]
    if cur == "MISMATCH":                      # umbrella — every non-clean row
        rows = [x for x in rows if x["state"] != "MATCHED"]
    elif cur != "All":
        rows = [x for x in rows if x["state"] == cur]
    # Mismatched-looking first, then by ticker.
    order = {"MISMATCH": 0, "FID_ONLY": 1, "TRACKED_ONLY": 2, "MATCHED": 3}
    rows = sorted(rows, key=lambda x: (order.get(x["state"], 9), x["ticker"]))

    if not rows:
        st.success("Nothing to show for this filter — the book is clean here. ✅")
        return
    st.markdown(_table(c, rows), unsafe_allow_html=True)
    st.caption("Matched by account · ticker · type · expiry · strike. Mismatched = every non-clean "
               "row (qty off · Fidelity only · tracked only). Tracked $ = collateral (strike×100×qty), "
               "Fidelity $ = current option value. (LEAP counts as CALL, "
               "as Fidelity reports it). Δ Qty = Fidelity − Tracked. **Never places an order.**")
