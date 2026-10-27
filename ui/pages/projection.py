"""🎯 Projection — portfolio what-if: recover each position to its tier target + premium +
401k bounce, vs the portfolio target, with the GAP. Mirrors the mobile Projection page.
Anchored to the real wheel capital (Monitor Board) so magnitudes match the sheet."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services import gsheet


def _num(x) -> float:
    try:
        s = str(x).replace("$", "").replace(",", "").replace("%", "").strip()
        return float(s) if s not in ("", "—", "-", "nan", "#REF!", "#N/A") else 0.0
    except Exception:
        return 0.0


def _cat(invest: str) -> str:
    w = str(invest).upper()
    if "CORE" in w or "VALUE" in w:
        return "Core"
    if "GROWTH" in w:
        return "Growth"
    return "Spec"            # Speculative is the catch-all (only 3 categories)


def _money(v: float) -> str:
    return ("-$" if v < 0 else "$") + f"{abs(v):,.0f}"


def _k(v: float) -> str:
    return ("-$" if v < 0 else "$") + f"{abs(v) / 1000:,.1f}K"


def render(c: dict) -> None:
    # ── Assumptions (editable; Streamlit remembers them in session) ───────────────
    with st.expander("⚙ Assumptions", expanded=False):
        a, b, d = st.columns(3)
        core = a.number_input("Core recovery %", value=10.0, step=1.0, key="pj_core")
        growth = b.number_input("Growth recovery %", value=30.0, step=1.0, key="pj_growth")
        spec = d.number_input("Speculative recovery %", value=15.0, step=1.0, key="pj_spec")
        e, f, g = st.columns(3)
        bounce = e.number_input("401k bounce (S&P) %", value=2.0, step=0.5, key="pj_bounce")
        prem_ira = f.number_input("Premium/mo IRA $", value=2000.0, step=250.0, key="pj_premira")
        prem_llc = g.number_input("Premium/mo LLC $", value=3000.0, step=250.0, key="pj_premllc")
        h, i, j = st.columns(3)
        months = h.number_input("Premium months", value=2.0, step=1.0, key="pj_months")
        other_cash = i.number_input("Other cash $", value=30000.0, step=5000.0, key="pj_cash")
        target = j.number_input("Portfolio target $", value=2280000.0, step=20000.0, key="pj_target")

    up = {"Core": core / 100, "Growth": growth / 100, "Spec": spec / 100}

    # ── Positions + incremental recovery (covered shares rise toward the CC strike) ──
    df = gsheet.tradelog()
    if df.empty:
        st.info("TradeLog is empty.")
        return
    cols = {col.strip(): col for col in df.columns}

    def cell(row, name):
        col = cols.get(name)
        return row[col] if col is not None else ""

    rec = {"IRA": 0.0, "LLC": 0.0}
    lines = []
    for _, row in df.iterrows():
        if not str(cell(row, "Status")).upper().startswith("OPEN"):
            continue
        stock = str(cell(row, "Stock")).strip().upper()
        if stock in ("", "CASH", "VAULT"):
            continue
        acct = str(cell(row, "Account")).strip().upper()
        opt = str(cell(row, "Opt Typ")).upper()
        cat = _cat(cell(row, "Invest Type"))
        cur = _num(cell(row, "Current Price"))
        strike = _num(cell(row, "Strike Price"))
        qty = _num(cell(row, "Qty"))
        is_call, is_put = "CALL" in opt, "PUT" in opt
        tgt = cur * (1 + up.get(cat, spec / 100))
        cap = (min(tgt, strike) if strike > 0 else tgt) if is_call else (strike if is_put else cur)
        sh = 100 * qty
        today = cur * sh if is_call else (strike * sh if is_put else cur * sh)
        proj = cap * sh if is_call else today
        if is_call and acct in rec:
            rec[acct] += proj - today
        note = "CSP" if is_put else ("LEAP" if "LEAP" in opt else ("Capped" if strike > 0 and tgt >= strike else "Room"))
        lines.append((stock, acct, "C" if is_call else "P" if is_put else "L",
                      cur, strike, tgt, cap, today, proj, proj - today, note))

    # ── Anchor "today" to the real wheel capital from the Monitor Board ──
    cells = gsheet.monitor_board_cells()
    cap_ira = (cells.get("ira", {}) or {}).get("cap") or 0.0
    cap_llc = (cells.get("llc", {}) or {}).get("cap") or 0.0
    k401 = 540000.0        # (web: 401k as a fixed assumption; sheet retirement lives on the mobile board)

    stocks_today = cap_ira + cap_llc
    recovery = rec["IRA"] + rec["LLC"]
    premium = (prem_ira + prem_llc) * months
    k401_proj = k401 * (1 + bounce / 100)
    total_today = stocks_today + k401 + other_cash
    total_proj = stocks_today + recovery + premium + k401_proj + other_cash
    gap = total_proj - target

    # ── Headline cards ──
    gap_col = c["pos"] if gap >= 0 else c["neg"]
    hdr = (
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 14px;'>"
        f"<div style='flex:2;min-width:220px;background:{c['panel']};border:1px solid {c['border']};border-radius:11px;padding:14px 16px;'>"
        f"<div style='font-size:10px;font-weight:900;letter-spacing:.06em;color:{c['muted']};'>PROJECTED PORTFOLIO</div>"
        f"<div style='margin-top:3px;font-size:26px;font-weight:950;color:{c['text']};'>{_money(total_proj)}</div>"
        f"<div style='margin-top:2px;font-size:13px;font-weight:800;color:{gap_col};'>"
        f"{'SURPLUS' if gap >= 0 else 'GAP'} {('+' if gap >= 0 else '−')}{_k(abs(gap))} · target {_k(target)}</div></div>"
        f"<div style='flex:1;min-width:120px;background:{c['panel']};border:1px solid {c['border']};border-radius:11px;padding:14px 16px;'>"
        f"<div style='font-size:10px;font-weight:900;color:{c['muted']};'>TODAY</div>"
        f"<div style='margin-top:3px;font-size:18px;font-weight:900;color:{c['text']};'>{_money(total_today)}</div></div>"
        f"<div style='flex:1;min-width:120px;background:{c['panel']};border:1px solid {c['border']};border-radius:11px;padding:14px 16px;'>"
        f"<div style='font-size:10px;font-weight:900;color:{c['muted']};'>RECOVERY</div>"
        f"<div style='margin-top:3px;font-size:18px;font-weight:900;color:{c['pos']};'>+{_k(recovery)}</div></div>"
        f"<div style='flex:1;min-width:120px;background:{c['panel']};border:1px solid {c['border']};border-radius:11px;padding:14px 16px;'>"
        f"<div style='font-size:10px;font-weight:900;color:{c['muted']};'>PREMIUM</div>"
        f"<div style='margin-top:3px;font-size:18px;font-weight:900;color:{c['accent'] if 'accent' in c else c['text']};'>+{_k(premium)}</div></div>"
        f"</div>")
    st.markdown(hdr, unsafe_allow_html=True)

    # ── Breakdown table (IRA / LLC / Total) ──
    def brow(label, ira, llc, tot, strong=False, col=None):
        tc = col or (c["text"] if strong else c["muted"])
        fw = 900 if strong else 600
        tds = "".join(
            f"<td style='border:1px solid {c['border']};padding:8px 14px;text-align:right;"
            f"color:{tc};font-weight:{fw};white-space:nowrap;'>{v}</td>" for v in (ira, llc, tot))
        return (f"<tr><td style='border:1px solid {c['border']};padding:8px 14px;color:{c['text'] if strong else c['muted']};"
                f"font-weight:{fw};'>{label}</td>{tds}</tr>")

    rec_ira, rec_llc = rec["IRA"], rec["LLC"]
    body = "".join([
        brow("Stocks now", _money(cap_ira), _money(cap_llc), _money(stocks_today)),
        brow("+ Recovery", _k(rec_ira), _k(rec_llc), _k(recovery), col=c["pos"]),
        brow("Stocks projected", _money(cap_ira + rec_ira), _money(cap_llc + rec_llc), _money(stocks_today + recovery)),
        brow("+ Premium", _k(prem_ira * months), _k(prem_llc * months), _k(premium), col=c["pos"]),
        brow("401k ↑ bounce", "", "", _money(k401_proj)),
        brow("Other cash", "", "", _money(other_cash)),
        brow("TOTAL now", "", "", _money(total_today), strong=True),
        brow("TOTAL projected", "", "", _money(total_proj), strong=True),
        brow("Target", "", "", _money(target)),
        brow("SURPLUS" if gap >= 0 else "GAP", "", "", ("+" if gap >= 0 else "−") + _money(abs(gap)), strong=True, col=gap_col),
    ])
    head = "".join(f"<th style='border:1px solid {c['border']};background:{c['raised']};color:{c['text']};"
                   f"padding:9px 14px;text-align:{'left' if h == '' else 'right'};font-weight:800;font-size:13px;'>{h}</th>"
                   for h in ("", "IRA", "LLC", "Total"))
    st.markdown("#### Breakdown")
    st.markdown(f"<table style='border-collapse:collapse;font-size:14px;width:100%;'>"
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>", unsafe_allow_html=True)

    # ── Per-position detail (what each tier % means) ──
    st.markdown("#### Positions")
    lines.sort(key=lambda x: x[9], reverse=True)       # by recovery desc
    ph = ("STOCK", "AC", "T", "CUR", "STRIKE", "TARGET", "CAP", "TODAY", "PROJ", "RECOV", "NOTE")
    phead = "".join(f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
                    f"border:1px solid {c['border']};padding:8px 12px;text-align:{'left' if i < 3 or h == 'NOTE' else 'right'};"
                    f"font-weight:800;font-size:12.5px;white-space:nowrap;'>{h}</th>" for i, h in enumerate(ph))
    prows = ""
    for (stock, acct, t, cur, strike, tgt, cap, today, proj, recov, note) in lines:
        note_col = c["pos"] if note == "Room" else (c.get("warn", c["muted"]) if note == "Capped" else c["muted"])
        vals = [
            (stock, "left", c["text"], 800), (acct, "left", c["muted"], 700), (t, "center", c["muted"], 600),
            (_money(cur), "right", c["muted"], 600), (_money(strike), "right", c["text"], 600),
            (_money(tgt), "right", c["text"], 800), (_money(cap), "right", c["muted"], 600),
            (_k(today), "right", c["muted"], 600), (_k(proj), "right", c["text"], 700),
            ("+" + _k(recov) if recov > 0 else "—", "right", c["pos"] if recov > 0 else c["muted"], 800),
            (note, "left", note_col, 800),
        ]
        tds = "".join(f"<td style='border:1px solid {c['border']};padding:7px 12px;text-align:{al};"
                      f"color:{cl};font-weight:{fw};white-space:nowrap;font-size:13px;'>{v}</td>" for v, al, cl, fw in vals)
        prows += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    st.markdown(f"<div style='overflow:auto;max-height:560px;border:1px solid {c['border']};border-radius:9px;'>"
                f"<table style='border-collapse:collapse;width:max-content;min-width:100%;'>"
                f"<thead><tr>{phead}</tr></thead><tbody>{prows}</tbody></table></div>", unsafe_allow_html=True)
    st.caption("target = current × tier % · cap = min(target, CC strike) · recovery = incremental gain toward the strike")
