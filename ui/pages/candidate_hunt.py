"""✅ Decision Desk — WheelEngine's flagship.

Reads the last Candidate Hunt (run from the Candidate Scanner) + the live account
capacity, sizes every candidate against the gates, ranks by AOR, and shows the
verdict. Never places an order — it finds · sizes · ranks; you execute.
"""

from __future__ import annotations

import streamlit as st

from logic import action_queue as aq
from logic import candidate_hunt as hunt
from logic import gtc_orders as gtco
from logic import monitor as mb
from services import gsheet, yahoo
from ui import state

_SETUP_ICON = {"IV Drop": "📄", "IV Drop 2-Day": "📄", "Reversal": "🔄",
               "Deep Value": "💎", "Quality Pullback": "🏅", "Mid-Band": "🎯",
               "50SMA Reclaim": "📈", "IV🟢": "📄", "IV🟠": "📄"}


@st.cache_data(ttl=120, show_spinner=False)
def _tradelog():
    df = gsheet.tradelog()
    if not df.empty:
        df.columns = [str(x).strip() for x in df.columns]
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _externals():
    return gsheet.monitor_externals()


@st.cache_data(ttl=120, show_spinner=False)
def _market():
    return yahoo.market_context()


def _m0(v) -> str:
    v = float(v or 0)
    return f"−${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def _card(c, label, value, sub, vcolor=None, wide=False, accent=False):
    vcolor = vcolor or c["text"]
    border = c["accent"] if accent else c["border"]
    return (f"<div style='flex:{2 if wide else 1};min-width:{200 if wide else 150}px;"
            f"background:{c['panel']};border:1px solid {border};border-radius:12px;padding:14px 16px;'>"
            f"<div style='font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;"
            f"color:{c['muted']};font-weight:700;'>{label}</div>"
            f"<div style='font-size:{22 if wide else 21}px;font-weight:800;color:{vcolor};"
            f"margin-top:3px;line-height:1.15;'>{value}</div>"
            f"<div style='font-size:11px;color:{c['muted']};margin-top:3px;'>{sub}</div></div>")


def _capacity_cards(c, board):
    I, L, T = board["ira"], board["llc"], board["total"]
    ccbrk = T["ccbrk"]
    brk_col = c["pos"] if ccbrk < 0.30 else (c["amber"] if ccbrk < 0.45 else c["neg"])
    brk_note = ("Below 30% caution level" if ccbrk < 0.30
                else ("Watch band 30–45%" if ccbrk < 0.45 else "≥45% — CSPs frozen"))
    vault_pass = I["cih"] >= 0 and L["cih"] >= 0
    cards = [
        _card(c, "IRA CSP Room", _m0(I["rtd"]), f"{I['rtd'] / I['wcap'] * 100:.1f}% of IRA wheel capital",
              c["pos"] if I["rtd"] >= 0 else c["neg"]),
        _card(c, "LLC CSP Room", _m0(L["rtd"]), f"{L['rtd'] / L['wcap'] * 100:.1f}% of LLC wheel capital",
              c["pos"] if L["rtd"] >= 0 else c["amber"]),
        _card(c, "CC Breaker", f"{ccbrk * 100:.1f}%", brk_note, brk_col),
        _card(c, "Cash Vault", "PASS" if vault_pass else "FAIL",
              "Both accounts at or above 30% ATH" if vault_pass else "Cash below the 30% ATH vault",
              c["pos"] if vault_pass else c["neg"]),
    ]
    return f"<div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px;'>{''.join(cards)}</div>"


def _answer(c, q, title, number, ncolor, ctx, kind="plain"):
    border = {"primary": c["accent"], "action": c["neg"], "warning": c["amber"]}.get(kind, c["border"])
    bg = c["nav_active_bg"] if kind == "primary" else c["panel"]
    return (f"<div style='min-height:112px;padding:14px 15px;border:1px solid {border};border-radius:9px;"
            f"background:{bg};display:flex;flex-direction:column;'>"
            f"<div style='font-size:9px;font-weight:900;letter-spacing:.06em;text-transform:uppercase;"
            f"color:{c['muted']};'>{q}</div>"
            f"<div style='margin-top:6px;font-size:11px;font-weight:850;color:{c['text']};'>{title}</div>"
            f"<div style='margin-top:auto;font-size:19px;font-weight:950;line-height:1.15;color:{ncolor};'>{number}</div>"
            f"<div style='margin-top:5px;font-size:10px;color:{c['muted']};line-height:1.3;'>{ctx}</div></div>")


def _answer_cards(c, board, aqres, best, has_fid):
    prem = {k: v for k, v in board["premium"]}
    wk_e, wk_g = prem["💰 Wk Earned"], prem["🎯 Wk Goal"]
    wk_gap = prem["⏳ Wk Gap"]
    mo_e, mo_g = prem["💰 Mo Earned"], prem["🎯 Mo Goal"]
    mo_gap = prem["⏳ Mo Gap"]
    stuck, gtc, cc = aqres["cards"]["stuck"], aqres["cards"]["gtc"], aqres["cards"]["cc"]

    def prem_card(q, title, earned, gap):
        ahead = gap <= 0
        col = c["pos"] if ahead else c["amber"]
        ctx = (f"Goal ${(earned + gap):,.0f} · "
               + (f"Ahead by ${-gap:,.0f}" if ahead else f"Behind by ${gap:,.0f}"))
        return _answer(c, q, title, f"${earned:,.0f} {'this week' if 'Wk' in q else 'this month'}",
                       col, ctx, "warning" if not ahead else "plain")

    # 2 · What's stuck
    if not has_fid:
        c2 = _answer(c, "2 · What is stuck?", "Book Health", "Upload Fidelity", c["muted"],
                     "Reconcile a Fidelity CSV to see stuck capital", "plain")
    else:
        c2 = _answer(c, "2 · What is stuck?", "Book Health",
                     f"${stuck['value']:,.0f} · {stuck['count']} positions",
                     c["amber"] if stuck["count"] else c["pos"],
                     "Assigned below basis or without a clean exit", "warning" if stuck["count"] else "plain")
    # 3 · Best available trade
    if best:
        icon = _SETUP_ICON.get(best["setup"], "•")
        n = best[best["best"].lower()]["n"]
        c3 = _answer(c, "3 · Candidate, account and size?", "Best Available Trade",
                     f"{best['ticker']} · {best['best']} · Max {n}", c["accent"],
                     (f"{best['aor']:.0f}% AOR · {icon} {best['setup']} · GTC close ${best['gtc']:.2f}"
                      if best['gtc'] is not None else f"{best['aor']:.0f}% AOR"), "primary")
    else:
        c3 = _answer(c, "3 · Candidate, account and size?", "Best Available Trade",
                     "Run a hunt", c["muted"], "Set inputs on Candidate Scanner → Run Candidate Hunt", "primary")
    # 4 · Missing GTCs — needs GTC data (uploaded CSV) to know what's placed at broker
    if not gtc.get("has_data"):
        c4 = _answer(c, "4 · Which GTCs are missing?", "GTC Coverage", "Upload GTC CSV", c["muted"],
                     "Fill the GTC template to check broker coverage", "plain")
    else:
        c4 = _answer(c, "4 · Which GTCs are missing?", "GTC Coverage",
                     f"{gtc['missing']} missing" if gtc["missing"] else "All covered",
                     c["neg"] if gtc["missing"] else c["pos"],
                     "Not placed at the broker" if gtc["missing"] else "Every open put has its GTC",
                     "action" if gtc["missing"] else "plain")
    # 5 · Shares needing a call
    if not has_fid:
        c5 = _answer(c, "5 · Which shares need a call?", "CC to Write", "Upload Fidelity", c["muted"],
                     "Reconcile a Fidelity CSV to find uncovered shares", "plain")
    else:
        c5 = _answer(c, "5 · Which shares need a call?", "CC to Write",
                     f"{cc['shares']} shares · Max {cc['max']}" if cc["shares"] else "None",
                     c["neg"] if cc["shares"] else c["pos"],
                     "Uncovered shares eligible for review", "action" if cc["shares"] else "plain")

    cards = [prem_card("1A · Are we earning?", "Weekly Premium Tracker", wk_e, wk_gap),
             prem_card("1B · Are we earning?", "Monthly Premium Tracker", mo_e, mo_gap),
             c2, c3, c4, c5]
    return ("<div style='display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;"
            "margin-bottom:14px;'>" + "".join(cards) + "</div>")


_AQ_BADGE = {"good": ("rgba(67,196,99,.16)",), "bad": ("rgba(242,85,90,.16)",),
             "warn": ("rgba(227,166,58,.18)",), "na": ("transparent",)}


def _aq_table(c, rows):
    cols = ["Ticker", "Account", "Opt Type", "Current Price", "Strike", "Qty", "Expiry", "GTC", "Action"]
    aligns = {"Current Price": "right", "Strike": "right", "Qty": "center", "GTC": "center", "Action": "center"}
    head = "".join(
        f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:7px 9px;text-align:{aligns.get(h, 'left')};"
        f"font-weight:700;font-size:11px;white-space:nowrap;'>{h}</th>" for h in cols)
    opt_col = {"PUT": c["blue"], "CALL": c["amber"]}
    body = ""
    for r in rows:
        base = f"border:1px solid {c['border']};padding:6px 9px;color:{c['text']};white-space:nowrap;"
        typ = r["type"]
        tcol = opt_col.get(typ, c["muted"])
        type_td = f"<td style='{base}text-align:center;color:{tcol};font-weight:800;'>{typ}</td>"

        def badge(label, stt):
            col = {"good": c["pos"], "bad": c["neg"], "warn": c["amber"], "na": c["muted"]}[stt]
            bg = _AQ_BADGE[stt][0]
            return (f"<span style='background:{bg};color:{col};font-weight:800;padding:3px 8px;"
                    f"border-radius:6px;font-size:10.5px;'>{label}</span>" if stt != "na" else
                    f"<span style='color:{c['muted']};'>{label}</span>")
        acct_bg = "#5b9bd5" if r["acct"] == "IRA" else "#a480c9"
        tds = (
            f"<td style='{base}font-weight:800;'>{r['ticker']}</td>"
            f"<td style='{base}'><span style='background:{acct_bg};color:#101417;font-weight:900;"
            f"padding:2px 9px;border-radius:999px;font-size:10.5px;'>{r['acct']}</span></td>"
            f"{type_td}"
            f"<td style='{base}text-align:right;'>{('$%.2f' % r['cur']) if r['cur'] else '—'}</td>"
            f"<td style='{base}text-align:right;'>{('$%g' % r['strike']) if r['strike'] else '—'}</td>"
            f"<td style='{base}text-align:center;'>{r['qty']}</td>"
            f"<td style='{base}'>{r['expiry'] or '—'}</td>"
            f"<td style='{base}text-align:center;'>{badge(r['gtc'], r['gtc_state'])}</td>"
            f"<td style='{base}text-align:center;'>{badge(r['action'], r['action_state'])}</td>")
        body += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:460px;border:1px solid {c['border']};border-radius:10px;'>"
            f"<table style='border-collapse:collapse;font-size:12.5px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _cap_cell(c, acct_res):
    held = acct_res.get("held_pct", 0) or 0
    sub = (f"<div style='font-size:9.5px;font-weight:800;color:{c['muted']};margin-top:1px;'>held {held:.1f}%</div>"
           if held > 0.05 else "")
    if acct_res["n"] > 0:
        return (f"<td style='border:1px solid {c['border']};padding:6px 9px;text-align:center;"
                f"background:rgba(67,196,99,.16);color:{c['pos']};font-weight:800;'>MAX {acct_res['n']}{sub}</td>")
    return (f"<td style='border:1px solid {c['border']};padding:6px 9px;text-align:center;"
            f"background:rgba(242,85,90,.14);color:{c['neg']};font-weight:800;'>NO ROOM{sub}</td>")


def _decisions_table(c, rows):
    cols = ["Ticker", "Setup", "Current", "Strike", "Expiry", "Δ", "Prem", "AOR",
            "RSI", "BB", "Earnings", "GTC", "IRA", "LLC", "Decision", "Why"]
    aligns = {"Current": "right", "Strike": "right", "Δ": "center", "Prem": "right",
              "AOR": "center", "RSI": "center", "GTC": "right", "IRA": "center",
              "LLC": "center", "Decision": "center"}
    head = "".join(
        f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:7px 9px;text-align:{aligns.get(h, 'left')};"
        f"font-weight:700;font-size:11px;white-space:nowrap;'>{h}</th>" for h in cols)

    def rg(ok):                                   # red / green text per gate
        return c["pos"] if ok else c["neg"]

    body = ""
    for r in rows:
        base = f"border:1px solid {c['border']};padding:6px 9px;color:{c['text']};white-space:nowrap;"
        icon = _SETUP_ICON.get(r["setup"], "")
        go = r["go"]
        dchip = (f"<span style='background:rgba(67,196,99,.18);color:{c['pos']};font-weight:900;"
                 f"padding:3px 11px;border-radius:6px;font-size:11px;letter-spacing:.03em;'>GO</span>" if go
                 else f"<span style='background:rgba(242,85,90,.16);color:{c['neg']};font-weight:900;"
                 f"padding:3px 11px;border-radius:6px;font-size:11px;letter-spacing:.03em;'>NO</span>")
        cur = f"${r['cur']:.2f}" if r.get("cur") else "—"
        dlt = f"{r['delta']:.2f}" if r.get("delta") is not None else "—"
        prem = f"${r['prem']:.2f}" if r.get("prem") is not None else "—"
        aor = f"{r['aor']:.0f}%" if r.get("aor") is not None else "—"
        # AOR: ≥50 green · ≥45 gold · else regular
        aorv = r.get("aor") or 0
        aor_col = c["pos"] if aorv >= 50 else (c["amber"] if aorv >= 45 else c["text"])
        aor_w = "800" if aor_col != c["text"] else "600"
        # RSI: <45 green · >64 red · else regular
        try:
            rsiv = float(r["rsi"])
        except (TypeError, ValueError):
            rsiv = None
        rsi_col = (c["pos"] if (rsiv is not None and rsiv < 45)
                   else c["neg"] if (rsiv is not None and rsiv > 64) else c["text"])
        rsi_w = "700" if rsi_col != c["text"] else "400"
        # Earnings: red only if it lands ON/BEFORE expiry (a real veto), else regular
        earn_raw = str(r.get("earn", "")).replace("⛔", "").strip()
        earn_disp = "Clear" if (not earn_raw or earn_raw == "—") else earn_raw
        earn_col = c["neg"] if not r["earn_ok"] else c["text"]
        earn_w = "700" if not r["earn_ok"] else "400"

        def cap(a):
            return (_cap_cell(c, a) if a else
                    f"<td style='{base}text-align:center;color:{c['muted']};'>—</td>")

        tds = (
            f"<td style='{base}font-weight:800;'>{r['ticker']}</td>"
            f"<td style='{base}'>{icon} {r['setup']}</td>"
            f"<td style='{base}text-align:right;'>{cur}</td>"
            f"<td style='{base}text-align:right;'>${r['strike']:.0f}</td>"
            f"<td style='{base}'>{r.get('expiry') or '—'}</td>"
            f"<td style='{base}text-align:center;'>{dlt}</td>"
            f"<td style='{base}text-align:right;'>{prem}</td>"
            f"<td style='{base}text-align:center;font-weight:{aor_w};color:{aor_col};'>{aor}</td>"
            f"<td style='{base}text-align:center;font-weight:{rsi_w};color:{rsi_col};'>{r['rsi']}</td>"
            f"<td style='{base}font-weight:700;color:{rg(r['bb_ok'])};'>{r['bb']}</td>"
            f"<td style='{base}font-weight:{earn_w};color:{earn_col};'>{earn_disp}</td>"
            f"<td style='{base}text-align:right;'>{('$%.2f' % r['gtc']) if r['gtc'] is not None else '—'}</td>"
            f"{cap(r['ira'])}{cap(r['llc'])}"
            f"<td style='{base}text-align:center;'>{dchip}</td>"
            f"<td style='{base}color:{c['muted']};font-size:11.5px;'>{r['why']}</td>")
        body += f"<tr>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:1160px;border:1px solid {c['border']};border-radius:10px;'>"
            f"<table style='border-collapse:collapse;font-size:12.5px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def render(c: dict) -> None:
    df = _tradelog()
    if df.empty:
        st.warning("Couldn't load the TradeLog tab.")
        return
    ext = _externals()
    mkt = _market()
    vix = mkt.get("vix") or ext.get("vix") or 16.57
    vc = mkt.get("vix_chg")
    vix_chg = vc if vc is not None else (ext.get("vix_chg") or 0.0)
    trend = mkt.get("trend") or ext.get("trend") or "Uptrend"
    ath_ira, ath_llc = ext.get("ath_ira", 0), ext.get("ath_llc", 0)

    board = mb.monitor_board(df, ath_ira, ath_llc, vix, vix_chg, trend)
    fid, fid_meta = state.load_fidelity()
    gtc_saved = state.load_gtc_placed()
    aqres = aq.build(df, fid, gtc_placed=(set(gtc_saved) if gtc_saved is not None else None))

    # The hunt (Q3 + Part 3) is optional — the rest of the desk works without it.
    cands, meta = state.load_hunt()
    r = None
    if cands is not None and meta is not None:
        min_aor = float(meta[1]) if len(meta) > 1 else 40.0
        dte = int(meta[4]) if len(meta) > 4 else 28
        expiry = str(meta[3]) if len(meta) > 3 and meta[3] else ""
        r = hunt.size(cands, df, ath_ira, ath_llc, vix, vix_chg, trend, dte, min_aor, expiry)

    # ── Part 1 — the five answers ──
    st.markdown(_answer_cards(c, board, aqres, (r["best"] if r else None), aqres["has_fidelity"]),
                unsafe_allow_html=True)

    # ── Part 2 — Portfolio Action Queue ──
    src = (f"{fid_meta['name']} · Last uploaded: {fid_meta['time']}" if fid_meta
           else "TradeLog only — upload a Fidelity CSV on Reconcile for stuck & CC flags")
    st.markdown(f"#### 🧾 Portfolio Action Queue  <span style='font-size:11px;color:{c['muted']};'>"
                f"{src}</span>", unsafe_allow_html=True)

    # ── GTC coverage (Fidelity can't export open orders — maintain a small CSV) ──
    put_rows = [x for x in aqres["rows"] if x["type"] == "PUT"]
    with st.expander("🎯 GTC coverage — which puts have a live order at the broker", expanded=False):
        st.caption("Fidelity can't export open orders. Download the template, fill a **GTC Price** "
                   "for each put you've actually placed (from Fidelity → Activity & Orders → Pending), "
                   "and re-upload. Blank = **MISSING**.")
        dl, up = st.columns([1, 2])
        with dl:
            st.download_button("⬇︎ Template", data=gtco.template_csv(put_rows),
                               file_name="gtc_orders.csv", mime="text/csv",
                               disabled=not put_rows, use_container_width=True)
        with up:
            f = st.file_uploader("Upload filled GTC CSV", type=["csv"], key="gtc_csv",
                                 label_visibility="collapsed")
        if f is not None:
            try:
                keys = gtco.parse_gtc_csv(f)
            except Exception as e:  # noqa: BLE001
                st.error(f"Couldn't read that CSV: {e}")
                keys = None
            if keys is not None and not keys:
                st.warning("No GTC prices found in that file. This uploader needs the **filled "
                           "template** — not a Fidelity export. Click **⬇︎ Template** above, type a "
                           "GTC Price next to each put you've placed, save, and upload that file.")
            elif keys:
                if set(gtc_saved or []) != keys:
                    state.save_gtc_placed(list(keys))
                    st.success(f"Loaded {len(keys)} placed GTC(s).")
                    st.rerun()
                st.caption(f"✓ {len(keys)} GTC(s) marked as placed.")
        if gtc_saved is not None:
            if st.button("Clear GTC data", key="gtc_clear"):
                state.hunt_store().pop("gtc_placed", None)
                st.rerun()

    exps = sorted({x["expiry"] for x in aqres["rows"] if x["expiry"]})
    fa, ft, fe, faction = st.columns([1, 1, 1.2, 1.4])
    with fa:
        acct_f = st.selectbox("Account", ["All", "IRA", "LLC"], key="aq_acct")
    with ft:
        type_f = st.selectbox("Opt Type", ["All", "PUT", "CALL", "SHARES"], key="aq_type")
    with fe:
        exp_f = st.selectbox("Expiry", ["All"] + exps, key="aq_exp")
    with faction:
        aqf = st.selectbox("Action", ["All", "Stuck", "Missing GTC", "Calls to Write"],
                           key="aq_filter")
    arows = aqres["rows"]
    fmap = {"Stuck": "stuck", "Missing GTC": "gtc", "Calls to Write": "cc"}
    if acct_f != "All":
        arows = [x for x in arows if x["acct"] == acct_f]
    if type_f != "All":
        arows = [x for x in arows if x["type"] == type_f]
    if exp_f != "All":
        arows = [x for x in arows if x["expiry"] == exp_f]
    if aqf in fmap:
        arows = [x for x in arows if fmap[aqf] in x["flags"]]
    arows = sorted(arows, key=lambda x: (0 if x["action_state"] == "bad" else 1 if x["action_state"] == "warn" else 2,
                                         x["ticker"]))
    if arows:
        st.markdown(_aq_table(c, arows), unsafe_allow_html=True)
    else:
        st.success("Nothing in the queue for this filter — the book is clean here. ✅")

    # ── Part 3 — Ranked New CSP Decisions (the hunt) ──
    st.write("")
    inp = state.load_hunt_inputs()
    hdr, runcol = st.columns([4, 1])
    with hdr:
        if r is None:
            st.markdown("#### 🎯 Ranked New CSP Decisions")
        else:
            st.markdown(f"#### 🎯 Ranked New CSP Decisions  <span style='font-size:12px;color:{c['muted']};'>"
                        f"Sorted by AOR · {r['n_tradable']} GO · {r['n_blocked']} NO</span>",
                        unsafe_allow_html=True)
    with runcol:
        if st.button("🎯 Run Hunt", type="primary", use_container_width=True,
                     disabled=inp is None, key="dd_run",
                     help="Re-run the last hunt (same universe · expiry · min AOR · Δ)."):
            from ui.pages import csp_scanner
            with st.spinner("Running hunt…"):
                csp_scanner.run_hunt(inp)
            st.rerun()
    if r is None:
        st.info("No hunt yet. Hit **Run Hunt** to re-run the last one, or set fresh inputs on "
                "**🎯 Candidate Scanner** (Universe · Expiry · Min AOR · Δ).")
        return
    _, right = st.columns([2.2, 1.6])
    with right:
        flt = st.radio("Filter", ["All", "GO", "NO", "IRA", "LLC"],
                       horizontal=True, label_visibility="collapsed", key="dd_filter")
    if not r["rows"]:
        st.info("The last hunt found no setup-fired names.")
        return
    rows = r["rows"]
    if flt == "GO":
        rows = [x for x in rows if x["go"]]
    elif flt == "NO":
        rows = [x for x in rows if not x["go"]]
    elif flt == "IRA":
        rows = [x for x in rows if x["ira"] and x["ira"]["n"] > 0]
    elif flt == "LLC":
        rows = [x for x in rows if x["llc"] and x["llc"]["n"] > 0]
    st.markdown(_decisions_table(c, rows), unsafe_allow_html=True)
    st.caption(f"Hunt priced at **{meta[0]}** (Δ ≤ {meta[2]:.2f}, ≥{min_aor:.0f}% AOR) · sized against "
               f"5% name cap · Layer 2.5% · CSP room · CC Breaker. **Never places an order.**")
