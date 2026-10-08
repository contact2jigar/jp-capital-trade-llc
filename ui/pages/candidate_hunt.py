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
    # Freeze panes: header row sticks on vertical scroll; the first column sticks on
    # horizontal scroll; the first-column header (corner) sticks for both.
    head = ""
    for i, h in enumerate(cols):
        stick = (f"position:sticky;top:0;left:0;z-index:5;box-shadow:1px 1px 0 {c['border']};" if i == 0
                 else f"position:sticky;top:0;z-index:3;box-shadow:0 1px 0 {c['border']},0 -1px 0 {c['border']};")
        head += (f"<th style='{stick}background:{c['raised']};color:{c['text']};"
                 f"border:1px solid {c['border']};padding:7px 9px;text-align:{aligns.get(h, 'left')};"
                 f"font-weight:700;font-size:11px;white-space:nowrap;'>{h}</th>")
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
            f"<td style='{base}font-weight:800;position:sticky;left:0;z-index:1;"
            f"background:{c['raised']};box-shadow:1px 0 0 {c['border']};'>{r['ticker']}</td>"
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
    cols = ["Ticker", "Setup", "Type", "Current", "%Chg", "Off High", "4mo ↓", "Strike", "Strike ↓",
            "Expiry", "Δ", "Prem", "AOR", "IV", "P/E", "RSI", "BB", "Earnings", "Financials", "Cash",
            "IRA", "LLC", "Decision", "Industry", "Why", "Company"]
    aligns = {"Current": "right", "%Chg": "right", "Off High": "right", "4mo ↓": "right",
              "Strike": "right", "Strike ↓": "right", "Δ": "center", "Prem": "right", "AOR": "center",
              "IV": "center", "P/E": "center", "RSI": "center", "Cash": "right", "IRA": "center",
              "LLC": "center", "Decision": "center"}
    # Freeze panes: header row sticks on vertical scroll; the first column sticks on
    # horizontal scroll; the first-column header (corner) sticks for both.
    head = ""
    for i, h in enumerate(cols):
        stick = (f"position:sticky;top:0;left:0;z-index:5;box-shadow:1px 1px 0 {c['border']};" if i == 0
                 else f"position:sticky;top:0;z-index:3;box-shadow:0 1px 0 {c['border']},0 -1px 0 {c['border']};")
        head += (f"<th style='{stick}background:{c['raised']};color:{c['text']};"
                 f"border:1px solid {c['border']};padding:7px 9px;text-align:{aligns.get(h, 'left')};"
                 f"font-weight:700;font-size:11px;white-space:nowrap;'>{h}</th>")

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
        # %Chg = today's move, coloured the conventional way: up = green, down = red.
        chgv = r.get("chg")
        if chgv is None:
            chg_td = f"<td style='{base}text-align:right;color:{c['muted']};'>—</td>"
        else:
            chg_col = c["pos"] if chgv > 0 else c["neg"] if chgv < 0 else c["muted"]
            chg_td = (f"<td style='{base}text-align:right;font-weight:700;color:{chg_col};'>"
                      f"{chgv:+.1f}%</td>")
        # 4mo ↓ = % down from the 4-month high; ≥20% = meaningful pullback (Quality Pullback zone).
        o4 = r.get("off4")
        if o4 is None:
            off4_td = f"<td style='{base}text-align:right;color:{c['muted']};'>—</td>"
        else:
            o4col, o4w = (c["pos"], "700") if o4 >= 20 else (c["text"], "400")
            off4_td = f"<td style='{base}text-align:right;font-weight:{o4w};color:{o4col};'>{o4:.1f}%</td>"
        # Off High = % down from the 52-week high; ≥20% = the quality-veto discount threshold.
        oh = r.get("offhigh")
        if oh is None:
            offhigh_td = f"<td style='{base}text-align:right;color:{c['muted']};'>—</td>"
        else:
            ohcol, ohw = (c["pos"], "700") if oh >= 20 else (c["text"], "400")
            offhigh_td = f"<td style='{base}text-align:right;font-weight:{ohw};color:{ohcol};'>{oh:.1f}%</td>"
        # Strike ↓ = how far the strike sits BELOW current price (the cushion the lower strike gives).
        cu = r.get("cush")
        if cu is None:
            cush_td = f"<td style='{base}text-align:right;color:{c['muted']};'>—</td>"
        else:
            cucol, cuw = (c["pos"], "700") if cu >= 10 else (c["text"], "400")
            cush_td = f"<td style='{base}text-align:right;font-weight:{cuw};color:{cucol};'>{cu:.1f}%</td>"
        dlt = f"{r['delta']:.2f}" if r.get("delta") is not None else "—"
        prem = f"${r['prem']:.2f}" if r.get("prem") is not None else "—"
        aor = f"{r['aor']:.0f}%" if r.get("aor") is not None else "—"
        # AOR: ≥50 green · ≥45 gold · else regular
        aorv = r.get("aor") or 0
        aor_col = c["pos"] if aorv >= 50 else (c["amber"] if aorv >= 45 else c["text"])
        aor_w = "800" if aor_col != c["text"] else "600"
        # IV: ≥45% green (roster-grade premium) · else regular
        ivv = r.get("iv")
        iv = f"{ivv:.0f}%" if ivv is not None else "—"
        iv_col = c["pos"] if (ivv is not None and ivv >= 45) else c["text"]
        iv_w = "700" if iv_col != c["text"] else "400"
        # Cash = net cash (cash − debt), $B: green when net cash, red when net debt.
        cashv = r.get("cash")
        if cashv is None:
            cash_td = f"<td style='{base}text-align:right;color:{c['muted']};'>—</td>"
        else:
            ccol = c["pos"] if cashv >= 0 else c["neg"]
            ctxt = f"+${cashv:.1f}B" if cashv >= 0 else f"−${abs(cashv):.1f}B"
            cash_td = f"<td style='{base}text-align:right;font-weight:800;color:{ccol};'>{ctxt}</td>"
        # RSI: <45 green · >64 red · else regular
        try:
            rsiv = float(r["rsi"])
        except (TypeError, ValueError):
            rsiv = None
        rsi_col = (c["pos"] if (rsiv is not None and rsiv < 45)
                   else c["neg"] if (rsiv is not None and rsiv > 64) else c["text"])
        rsi_w = "700" if rsi_col != c["text"] else "400"
        # P/E: amber when loss-making (≤0) or richly valued (>100), else regular. Blank = —
        pev = r.get("pe")
        if pev is None:
            pe_td = f"<td style='{base}text-align:center;color:{c['muted']};'>—</td>"
        else:
            pe_col = c["amber"] if (pev <= 0 or pev > 100) else c["text"]
            pe_w = "700" if pe_col != c["text"] else "400"
            pe_td = f"<td style='{base}text-align:center;font-weight:{pe_w};color:{pe_col};'>{pev:.1f}</td>"
        # Earnings: red only if it lands ON/BEFORE expiry (a real veto), else regular
        earn_raw = str(r.get("earn", "")).replace("⛔", "").strip()
        earn_disp = "Clear" if (not earn_raw or earn_raw == "—") else earn_raw
        earn_col = c["neg"] if not r["earn_ok"] else c["text"]
        earn_w = "700" if not r["earn_ok"] else "400"

        # BB %B (0-100): precise position in the band next to the coarse label.
        bbp = r.get("bbpct")
        bb_suffix = (f" <span style='color:{c['muted']};font-weight:400;font-size:10px'>{bbp:.0f}</span>"
                     if bbp is not None else "")
        type_td = f"<td style='{base}font-size:11px;color:{c['muted']};'>{r.get('stype') or '—'}</td>"

        def cap(a):
            return (_cap_cell(c, a) if a else
                    f"<td style='{base}text-align:center;color:{c['muted']};'>—</td>")

        tds = (
            f"<td style='{base}font-weight:800;position:sticky;left:0;z-index:1;"
            f"background:{c['raised']};box-shadow:1px 0 0 {c['border']};'>{r['ticker']}</td>"
            f"<td style='{base}font-size:11px;padding-left:6px;padding-right:6px;'>"
            f"{icon} {r.get('setup_full') or r['setup']}</td>"
            f"{type_td}"
            f"<td style='{base}text-align:right;'>{cur}</td>"
            f"{chg_td}"
            f"{offhigh_td}"
            f"{off4_td}"
            f"<td style='{base}text-align:right;'>${r['strike']:.0f}</td>"
            f"{cush_td}"
            f"<td style='{base}'>{r.get('expiry') or '—'}</td>"
            f"<td style='{base}text-align:center;'>{dlt}</td>"
            f"<td style='{base}text-align:right;'>{prem}</td>"
            f"<td style='{base}text-align:center;font-weight:{aor_w};color:{aor_col};'>{aor}</td>"
            f"<td style='{base}text-align:center;font-weight:{iv_w};color:{iv_col};'>{iv}</td>"
            f"{pe_td}"
            f"<td style='{base}text-align:center;font-weight:{rsi_w};color:{rsi_col};'>{r['rsi']}</td>"
            f"<td style='{base}font-weight:700;color:{rg(r['bb_ok'])};'>{r['bb']}{bb_suffix}</td>"
            f"<td style='{base}font-weight:{earn_w};color:{earn_col};'>{earn_disp}</td>"
            f"<td style='{base}font-size:11.5px;'>{r.get('fin') or '—'}</td>"
            f"{cash_td}"
            f"{cap(r['ira'])}{cap(r['llc'])}"
            f"<td style='{base}text-align:center;'>{dchip}</td>"
            f"<td style='{base}font-size:11.5px;color:{c['muted']};'>{r.get('industry') or '—'}</td>"
            f"<td style='{base}color:{c['muted']};font-size:11.5px;'>{r['why']}</td>"
            f"<td style='{base}font-size:11.5px;color:{c['muted']};'>{r.get('name') or '—'}</td>")
        body += f"<tr>{tds}</tr>"
    return (f"<div style='overflow:auto;max-height:560px;border:1px solid {c['border']};border-radius:10px;'>"
            f"<table style='border-collapse:collapse;font-size:12.5px;width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def _decisions_csv(rows) -> str:
    """Flat CSV of the ranked decisions — the same fields as the table, plus the
    per-account contract count and held %, so a hunt can be saved / shared."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ticker", "Setup", "Current", "%Chg", "Strike", "Expiry", "Δ", "Prem",
                "AOR%", "IV%", "P/E", "RSI", "BB", "Earnings", "Financials", "Cash $B", "Industry",
                "GTC", "IRA Max", "IRA Held%", "LLC Max", "LLC Held%", "Decision", "Why"])

    def num(v, fmt):
        return (fmt % v) if v is not None else ""

    for r in rows:
        ira, llc = r.get("ira"), r.get("llc")
        w.writerow([
            r.get("ticker", ""), r.get("setup", ""),
            num(r.get("cur"), "%.2f"), num(r.get("chg"), "%+.1f"), num(r.get("strike"), "%.0f"),
            r.get("expiry", ""), num(r.get("delta"), "%.2f"), num(r.get("prem"), "%.2f"),
            num(r.get("aor"), "%.0f"), num(r.get("iv"), "%.0f"), num(r.get("pe"), "%.1f"),
            r.get("rsi", ""), r.get("bb", ""), r.get("earn", ""),
            r.get("fin", ""), num(r.get("cash"), "%.2f"), r.get("industry", ""),
            num(r.get("gtc"), "%.2f"),
            (ira["n"] if ira else ""), num(ira.get("held_pct") if ira else None, "%.1f"),
            (llc["n"] if llc else ""), num(llc.get("held_pct") if llc else None, "%.1f"),
            r.get("decision", ""), r.get("why", ""),
        ])
    return buf.getvalue()


def _apply_decision_filters(rows):
    """Apply the Decision Desk result-criteria widgets (Setup · Min AOR · Max RSI ·
    Max Δ · BB zone · Financials must-pass · Avoid earnings) to the ranked rows."""
    pick = st.session_state.get("dd_f_setup", []) or []
    min_aor = st.session_state.get("dd_f_aor", 0)
    max_rsi = st.session_state.get("dd_f_rsi", 100)
    max_dlt = st.session_state.get("dd_f_delta", 0.0)
    bb_sel = st.session_state.get("dd_f_bb", []) or []
    fin_sel = st.session_state.get("dd_f_finsel", []) or []
    no_earn = st.session_state.get("dd_f_noearn", False)
    out = []
    for x in rows:
        if pick and not any(p.lower() in str(x.get("setup", "")).lower() for p in pick):
            continue
        if fin_sel:                                            # tokens space-separated → FCF ≠ CF
            toks = set(str(x.get("fin", "")).split())
            if not all(f"{chk}✅" in toks for chk in fin_sel):
                continue
        if bb_sel and str(x.get("bb", "")) not in bb_sel:
            continue
        if no_earn and not x.get("earn_ok", True):             # hide earnings-in-window names
            continue
        if min_aor > 0 and (x.get("aor") or -1) < min_aor:
            continue
        if max_dlt > 0:
            dv = x.get("delta")
            if dv is not None and abs(dv) > max_dlt:           # cap |Δ| ≤ Max Δ
                continue
        if max_rsi < 100:
            try:
                rv = float(x.get("rsi"))
            except (TypeError, ValueError):
                rv = None
            if rv is not None and rv > max_rsi:
                continue
        out.append(x)
    return out


def _apply_scan_filters(cands):
    """Filter Table 2 (All Scan Results) by its own RSI / BB / Earnings widgets. Mirrors the
    Decision-box filters but runs on the full-scan DataFrame. No-RSI rows are kept."""
    import pandas as pd
    v = cands
    min_aor = st.session_state.get("sr_aor", 0)
    max_rsi = st.session_state.get("sr_rsi", 100)
    bb_sel = st.session_state.get("sr_bb", []) or []
    no_earn = st.session_state.get("sr_earn", False)
    if min_aor > 0 and "AOR" in v.columns:
        av = pd.to_numeric(v["AOR"].astype(str).str.replace("%", "", regex=False), errors="coerce")
        v = v[av >= min_aor]                               # drops blanks (no priced option)
    if max_rsi < 100 and "RSI" in v.columns:
        rv = pd.to_numeric(v["RSI"], errors="coerce")
        v = v[~(rv > max_rsi)]                              # keep ≤ max and blanks (NaN)
    if bb_sel and "BB" in v.columns:
        v = v[v["BB"].astype(str).isin(bb_sel)]
    if no_earn and "Earnings" in v.columns:
        v = v[~v["Earnings"].astype(str).str.contains("⛔", na=False)]   # drop the earnings veto
    return v


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

    # The hunt is optional — the rest of the desk works without it.
    cands, meta = state.load_hunt()
    r = None
    if cands is not None and meta is not None:
        min_aor = float(meta[1]) if len(meta) > 1 else 40.0
        dte = int(meta[4]) if len(meta) > 4 else 28
        expiry = str(meta[3]) if len(meta) > 3 and meta[3] else ""
        r = hunt.size(cands, df, ath_ira, ath_llc, vix, vix_chg, trend, dte, min_aor, expiry)

    # ── Ranked New CSP Decisions · always run against the WatchList ──
    st.write("")
    from ui.pages import csp_scanner
    _cnt = (f"  <span style='font-size:12px;color:{c['muted']};'>Sorted by AOR · "
            f"{r['n_tradable']} GO · {r['n_blocked']} NO</span>") if r else ""
    st.markdown(f"#### 🎯 Ranked New CSP Decisions{_cnt}", unsafe_allow_html=True)

    # Line 1 — INPUT: WatchList types (wide) + Min DTE + ▶ Run (all aligned via top labels).
    lt, ldte, lrun = st.columns([4.7, 1.0, 1.1])
    with lt:
        all_types = csp_scanner.watchlist_types()
        dflt = [t for t in csp_scanner._DEFAULT_TYPES if t in all_types] or all_types
        picks = st.multiselect("WatchList types", all_types, default=dflt, key="dd_types",
                               placeholder="types to scan")
    with ldte:
        min_dte = st.number_input("Min DTE", 1, 90, 23, step=1, key="dd_min_dte",
                                  help="Price the first weekly expiry ≥ this many days out. "
                                       "Takes effect on ▶ Run.")
    with lrun:
        st.markdown("<div style='font-size:0.875rem;margin-bottom:0.25rem'>&nbsp;</div>",
                    unsafe_allow_html=True)
        run_click = st.button("▶ Run", type="primary", use_container_width=True, key="dd_run",
                              help="Price the selected WatchList buckets at your Min DTE expiry "
                                   "— the daily CSP run.")

    # Line 2 — RESULT FILTERS (one row, only once a run exists).
    if r is not None and r["rows"]:
        bb_opts = sorted({str(x.get("bb", "")) for x in r["rows"] if x.get("bb")})
        g1, g2, g3, g4, g5, g6, g7 = st.columns([1.5, 0.85, 0.85, 0.85, 1.25, 1.65, 0.95])
        with g1:
            st.multiselect("Setup", ["Reversal", "Deep Value", "IV Drop", "Mid-Band",
                                     "50SMA Reclaim"], key="dd_f_setup", placeholder="Any")
        with g2:
            st.number_input("Min AOR", 0, 200, 30, step=5, key="dd_f_aor")
        with g3:
            st.number_input("Max RSI", 0, 100, 65, step=5, key="dd_f_rsi")
        with g4:
            st.number_input("Max Δ", 0.0, 1.0, 0.0, step=0.05, key="dd_f_delta",
                            help="Cap |Δ| ≤ this (0 = no filter).")
        with g5:
            st.multiselect("BB zone", bb_opts, key="dd_f_bb", placeholder="Any")
        with g6:
            st.multiselect("Financials", ["Rev", "Inc", "CF", "FCF", "A>L"], key="dd_f_finsel",
                           placeholder="must pass ✅",
                           help="Keep names whose selected checks are ✅ — Rev up · Net income >0 · "
                                "Op cash flow >0 · Free cash flow >0 · Assets > Liabilities.")
        with g7:
            st.markdown("<div style='font-size:0.875rem;margin-bottom:0.25rem'>&nbsp;</div>",
                        unsafe_allow_html=True)
            st.checkbox("No earnings", value=True, key="dd_f_noearn",
                        help="Hide names with earnings on/before the expiry (the earnings veto).")

    if run_click:
        run_inp = csp_scanner.default_hunt_inputs(types=picks or None, min_dte=int(min_dte))
        if run_inp:
            csp_scanner.run_hunt(run_inp, c=c)       # results stream in live during the scan
            st.rerun()
        else:
            st.error("Couldn't build the run — the WatchList looks empty.")

    if r is None:
        st.info("Hit **▶ Run** to price your WatchList and rank the CSP decisions. "
                "To add new names, use **🔎 Candidate Scanner** (now under Tools).")
    elif not r["rows"]:
        st.info("The last run found no setup-fired names.")
    else:
        rows = _apply_decision_filters(r["rows"])
        st.markdown(_decisions_table(c, rows), unsafe_allow_html=True)
        st.download_button(
            "⬇︎ Download CSV", data=_decisions_csv(rows),
            file_name=f"csp_decisions_{meta[3]}.csv", mime="text/csv",
            key="dd_csv", help="The rows currently shown (respects every filter above).")
        st.caption(f"Hunt priced at **{meta[0]}** (Δ ≤ {meta[2]:.2f}, ≥{min_aor:.0f}% AOR) · sized against "
                   f"5% name cap · Layer 2.5% · CSP room · CC Breaker · IV ≥ 45% = roster-grade premium. "
                   f"**Never places an order.**")

    # ── Table 2 — the full scan result: every selected name, all columns ──
    if cands is not None and not cands.empty:
        st.write("")
        st.markdown("#### 📋 All Scan Results", unsafe_allow_html=True)
        # RESULT FILTERS for Table 2 — RSI · BB · Earnings (independent of the Decision-box filters).
        bb_opts2 = sorted({str(x).strip() for x in cands.get("BB", [])
                           if str(x).strip() and str(x).strip() not in ("nan", "None", "—")})
        s0, s1, s2, s3, _sp = st.columns([0.85, 0.85, 1.6, 1.0, 3.7])
        with s0:
            st.number_input("Min AOR", 0, 200, 25, step=5, key="sr_aor")
        with s1:
            st.number_input("Max RSI", 0, 100, 70, step=5, key="sr_rsi")
        with s2:
            st.multiselect("BB zone", bb_opts2, key="sr_bb", placeholder="Any")
        with s3:
            st.markdown("<div style='font-size:0.875rem;margin-bottom:0.25rem'>&nbsp;</div>",
                        unsafe_allow_html=True)
            st.checkbox("No earnings", value=False, key="sr_earn",
                        help="Hide names with an earnings veto (⛔ on/before expiry).")
        shown = _apply_scan_filters(cands)
        tail = (f"{len(shown)} of {len(cands)} names"
                if len(shown) != len(cands) else f"{len(cands)} names priced")
        st.markdown(f"<span style='font-size:12px;color:{c['muted']}'>{tail}</span>",
                    unsafe_allow_html=True)
        _exp = str(meta[3]) if (meta and len(meta) > 3 and meta[3]) else "—"
        st.markdown(csp_scanner.scan_table_html(shown, c, _exp), unsafe_allow_html=True)
