"""Day Predictor — if the early tape holds, here's the day + what you can add.

Mirrors the iPhone app:
  • Speedometer capacity — what new CSP you're allowed to add per account
    (room to the 40% breaker cap + cash above the vault; FROZEN when over).
  • Estimated day impact — each held ticker's extended-hours / today move pulled
    live from RH, propagated through your real positions. Deltas are transparent
    estimates (CSP from moneyness · LEAP 0.70 · owned shares full). Not a direction
    call — it propagates the OBSERVED move through the book.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services import rh
import ui.pages.command_center as cc
from ui.pages import cockpit as ck            # shared palettes + base card CSS
from ui.pages import cockpit_board as cb       # reuse the THIS YEAR table renderer


def _reality_html(c: dict, r: dict, ext: dict) -> str:
    """The sheet's 📅 THIS YEAR table (Start · Now · Gain · %, Wheel + Retirement + Grand Total),
    reused verbatim from the Board so the predictor shows the same ground truth. Wrapped in
    .ck-wrap with the cockpit CSS so the card styling applies on this page too."""
    P = ck.LIGHT if ck._is_light(c.get("bg", "")) else ck.DARK
    card = cb._ytd_card(r, ext or {}, P)
    # Rendered with st.html (NOT st.markdown): raw HTML/CSS, no markdown pass that would read the
    # indented CSS as code and no LaTeX pass that would eat the `$123` figures as `$…$` math.
    return f"{ck._css(P)}{cb._extra_css(P)}<div class='ck-wrap'>{card}</div>"


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _exposure(opt: str, qty: float, cur: float, strike: float, invest: str):
    """Signed share-equivalent exposure (+1 share gains $1 when the stock rises $1)."""
    opt = (opt or "").strip().upper()
    # LEAPs carry Opt Typ "LEAP" (not "CALL") and an ordinary Invest Type — detect BOTH, or a
    # long deep-ITM LEAP falls through and is counted as ~1 share (invisible in the day impact).
    if opt == "LEAP" or "LEAP" in (invest or "").upper():
        return 0.70 * 100 * qty, "LEAP", 0.70          # Δ0.70 flip doctrine (long deep-ITM call)
    if opt == "PUT":                                   # short CSP → +delta exposure
        cushion = (cur - strike) / cur if cur else 0.0
        d = min(0.97, max(0.03, 0.5 - 3 * cushion))    # ATM .50 · ~5% OTM .35 · ~10% OTM .20
        return d * 100 * qty, "CSP", d
    if opt == "CALL":
        # Covered call ≡ short put at the same strike (put-call parity): net delta = (1−call_delta)×100,
        # NOT a full 100. Reuse the put-delta curve so the short call caps the upside — an OTM covered
        # call keeps most of the lot's delta (~0.8), a deep-ITM one is nearly frozen (→0.03).
        cushion = (cur - strike) / cur if cur else 0.0
        d = min(0.97, max(0.03, 0.5 - 3 * cushion))
        return d * 100 * qty, "Covered", d
    return qty, (invest or "Shares"), 1.0


def _impact(c: dict, r: dict, df: pd.DataFrame, cfg: dict) -> None:
    if df is None or df.empty:
        st.info("No positions to read."); return
    d = df.copy()
    if "Status" in d:
        d = d[d["Status"].astype(str).str.strip().str.lower().str.startswith("open")]
    if d.empty:
        st.info("No open positions."); return

    syms = tuple(sorted({str(s).strip().upper() for s in d["Stock"] if str(s).strip()}))
    quotes = rh.extended_quotes(syms + ("SPY",))              # +SPY for the Rollover/Roth shares
    if not quotes:
        st.warning("Couldn't pull live RH quotes — check the RHSecret token.")
        return
    any_ext = any(v.get("ext") for v in quotes.values())

    agg: dict[str, dict] = {}
    total = 0.0
    ira_imp = llc_imp = 0.0                      # per-account wheel impact (for the BY ACCOUNT card)
    for _, row in d.iterrows():
        sym = str(row.get("Stock", "")).strip().upper()
        q = quotes.get(sym)
        if not q:
            continue
        opt = str(row.get("Opt Typ", "")).strip().upper()
        qty = _num(row.get("Qty")) or 0.0
        cur = _num(row.get("Current Price")) or 0.0
        strike = _num(row.get("Strike Price")) or 0.0
        invest = str(row.get("Invest Type", "")).strip()
        acct = str(row.get("Account", "")).strip().upper()
        # Moneyness/delta must use the LIVE price, not the TradeLog "Current Price" (stale = prior
        # close pre-market), else deep-OTM puts (e.g. a 150 put with the stock at 183) look near-money
        # and get too much delta — which inflated the estimate.
        live = q["price"] or cur
        exp, kind, _ = _exposure(opt, qty, live, strike, invest)
        impact = exp * (q["price"] - q["prev"])
        a = agg.setdefault(sym, {"impact": 0.0, "move": q["move"], "prev": q["prev"],
                                 "price": q["price"], "ext": bool(q.get("ext")), "kinds": {}})
        a["impact"] += impact
        a["kinds"][kind] = a["kinds"].get(kind, 0) + 1
        total += impact
        if acct == "IRA":
            ira_imp += impact
        elif acct == "LLC":
            llc_imp += impact

    # Rollover IRA + Roth SPY shares — held outside the wheel/TradeLog; they move with SPY, so a
    # whole-portfolio day read must include them (646 + 59 shares ≈ $540K that isn't in the wheel).
    spy = quotes.get("SPY")
    roll_cap = roth_cap = roll_imp = roth_imp = 0.0
    if spy and spy.get("price") and spy.get("prev"):
        dpx = spy["price"] - spy["prev"]
        roll_sh, roth_sh = float(cfg.get("roll_spy") or 0), float(cfg.get("roth_spy") or 0)
        for label, sh in (("SPY · Rollover IRA", roll_sh), ("SPY · Roth", roth_sh)):
            if sh > 0:
                imp = sh * dpx
                agg[label] = {"impact": imp, "move": spy["move"], "prev": spy["prev"],
                              "price": spy["price"], "ext": bool(spy.get("ext")),
                              "kinds": {f"{int(sh)} sh": 1}}
                total += imp
        roll_cap, roth_cap = roll_sh * spy["price"], roth_sh * spy["price"]
        roll_imp, roth_imp = roll_sh * dpx, roth_sh * dpx

    if not agg:
        st.info("No quotes matched the open positions."); return

    # Whole-portfolio capital / ATH = wheel + retirement (Rollover/Roth ≈ at ATH, they're SPY shares).
    wheel_cap = float(r.get("ira", {}).get("cap") or 0) + float(r.get("llc", {}).get("cap") or 0)
    wheel_ath = float(r.get("ira", {}).get("ath") or 0) + float(r.get("llc", {}).get("ath") or 0)
    cap, ath = wheel_cap + roll_cap + roth_cap, wheel_ath + roll_cap + roth_cap
    dd = (((cap + total) - ath) / ath) if ath else 0.0          # whole-portfolio drawdown (framework check)
    wheel_imp = total - roll_imp - roth_imp
    # Headline is WHEEL-ONLY (IRA+LLC), matching the iPhone — the retirement SPY impact lives in the
    # By Account card + the reality card, not in the hero number (keeps the wheel ATH/projection valid).
    w_pct = (wheel_imp / wheel_cap) if wheel_cap else 0.0
    w_proj = wheel_cap + wheel_imp
    w_dd = ((w_proj - wheel_ath) / wheel_ath) if wheel_ath else 0.0

    # Compact one-row stat strip (replaces four tall st.metric tiles) so the table sits higher.
    pos, neg, text, mut = c["pos"], c["neg"], c["text"], c["muted"]
    pcol = pos if wheel_imp >= 0 else neg

    def _stat(lbl, val, col):
        return (f"<div style='min-width:78px'>"
                f"<div style='font-size:9px;color:{mut};text-transform:uppercase;letter-spacing:.4px'>{lbl}</div>"
                f"<div style='font-size:15px;font-weight:800;color:{col};font-variant-numeric:tabular-nums'>{val}</div></div>")

    strip = (f"<div style='display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end;padding:1px 1px 2px'>"
             f"<div style='min-width:120px'>"
             f"<div style='font-size:9px;color:{mut};text-transform:uppercase;letter-spacing:.4px'>Day impact · wheel</div>"
             f"<div style='font-size:21px;font-weight:800;color:{pcol};font-variant-numeric:tabular-nums'>"
             f"${wheel_imp:,.0f} <span style='font-size:11px;font-weight:700'>({w_pct*100:+.2f}%)</span></div></div>"
             + _stat("Projected wheel", f"${w_proj:,.0f}", text)
             + _stat("vs ATH", f"{w_dd*100:+.2f}%", text)
             + "</div>")
    # 🏦 BY ACCOUNT — IRA·LLC wheel + Rollover·Roth SPY + Grand Total (mirrors the iPhone card):
    # each account's estimated day impact and % of that account's value.
    rs, rt = int(float(cfg.get("roll_spy") or 0)), int(float(cfg.get("roth_spy") or 0))
    acct_rows = [("IRA", "wheel", ira_imp, float(r.get("ira", {}).get("cap") or 0)),
                 ("LLC", "wheel", llc_imp, float(r.get("llc", {}).get("cap") or 0))]
    if roll_cap:
        acct_rows.append(("Rollover", f"{rs} SPY", roll_imp, roll_cap))
    if roth_cap:
        acct_rows.append(("Roth", f"{rt} SPY", roth_imp, roth_cap))

    def _arow(name, detail, imp, base, grand=False):
        icol = pos if imp >= 0 else neg
        ptxt = f"{imp / base * 100:+.2f}%" if base else "—"
        w = "800" if grand else "700"
        bg = f"background:{c['raised']};" if grand else ""
        bb = f"border-bottom:1px solid {c['border_soft']}"
        return (f"<tr style='{bg}'><td style='padding:4px 10px;{bb};font-size:12.5px'>"
                f"<span style='font-weight:{w};color:{text}'>{name}</span>"
                f"<span style='color:{mut};font-size:9px;margin-left:5px'>{detail}</span></td>"
                f"<td style='padding:4px 10px;{bb};text-align:right;font-weight:{w};color:{icol};"
                f"font-size:12.5px;font-variant-numeric:tabular-nums'>{imp:+,.0f}</td>"
                f"<td style='padding:4px 10px;{bb};text-align:right;color:{mut};"
                f"font-size:12.5px;font-variant-numeric:tabular-nums'>{ptxt}</td></tr>")

    _ah = (f"text-align:right;padding:4px 10px;color:{mut};font-size:9px;text-transform:uppercase;"
           f"letter-spacing:.4px;border-bottom:2px solid {c['border']}")
    a_head = (f"<tr><th style='{_ah};text-align:left'>Account</th>"
              f"<th style='{_ah}'>Day impact</th><th style='{_ah}'>% acct</th></tr>")
    a_body = "".join(_arow(*a) for a in acct_rows) + _arow("Grand Total", "all accounts", total, cap, grand=True)
    acct_table = (
        f"<table style='border-collapse:collapse;width:100%;max-width:460px;border:1px solid {c['border']};"
        f"border-radius:10px;overflow:hidden;background:{c['panel']}'>"
        f"<thead>{a_head}</thead><tbody>{a_body}</tbody></table>")

    # Two columns (stack when the browser narrows): LEFT = Estimated day impact + By account
    # stacked as separate cards; RIGHT = Where the year actually stands.
    has_year = bool(cfg.get("this_year") or [])
    # Narrow LEFT (the day-impact + by-account tables are compact) / wide RIGHT (the THIS YEAR
    # table is intrinsically wide). Stacks to one column when the browser narrows.
    left, right = (st.columns([1, 2.5], gap="medium") if has_year else (st.container(), None))
    with left:
        with st.container(border=True):
            st.markdown("##### 📊 Estimated day impact", unsafe_allow_html=True)
            st.markdown(strip, unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(acct_table, unsafe_allow_html=True)
    if has_year:
        with right:
            with st.container(border=True):
                # 📅 Reality anchor — the sheet's THIS YEAR table (Wheel + Retirement + Grand Total),
                # same renderer as the Board so the numbers can never drift. overflow-x:auto so the
                # wide table scrolls instead of clipping at intermediate widths.
                st.markdown("##### 📅 Where the year actually stands &nbsp;"
                            "<span style='color:#8a97a6;font-size:11px;font-weight:400'>"
                            "live from the sheet — the Grand Total is today's real base</span>",
                            unsafe_allow_html=True)
                st.html(f"<div style='overflow-x:auto'>{_reality_html(c, r, cfg)}</div>")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Per-ticker tape — Yesterday close + Early (pre-market) price so the estimate is verifiable.
    pos, neg, text, mut = c["pos"], c["neg"], c["text"], c["muted"]
    raised, bsoft, amber = c["raised"], c["border_soft"], c["amber"]
    ordered = sorted(agg.items(), key=lambda kv: abs(kv[1]["impact"]), reverse=True)
    maxmv = (max((abs(a["move"]) for a in agg.values()), default=0) * 100) or 1

    # Assigned strike + break-even per STOCK (combined across accounts), for the Covered rows —
    # same cost-basis reconstruction as the Trade Log: basis = strike − premium, share-weighted.
    bk_k, bk_be, bk_q = {}, {}, {}
    for _, brow in df.iterrows():
        if not str(brow.get("Status", "")).upper().startswith("ASSI"):
            continue
        if "PUT" not in str(brow.get("Opt Typ", "")).upper():
            continue
        k = _num(brow.get("Strike Price")); q = _num(brow.get("Qty")) or 0.0
        s = str(brow.get("Stock", "")).strip().upper()
        if not s or not k or k <= 0 or q <= 0:
            continue
        pm = _num(brow.get("Init Prem")) or 0.0
        bk_k[s] = bk_k.get(s, 0.0) + k * q
        bk_be[s] = bk_be.get(s, 0.0) + (k - pm) * q
        bk_q[s] = bk_q.get(s, 0.0) + q
    basis = {s: (bk_k[s] / q, bk_be[s] / q) for s, q in bk_q.items() if q > 0}

    rws = ""
    for sym, a in ordered:
        kinds = " · ".join(f"{k}×{v}" if v > 1 else k
                           for k, v in sorted(a["kinds"].items(), key=lambda x: -x[1]))
        mv = a["move"] * 100
        mcol, icol = (pos if mv >= 0 else neg), (pos if a["impact"] >= 0 else neg)
        pm = f" <span class='dp-pm'>pre</span>" if a.get("ext") else ""
        w = min(abs(mv) / maxmv * 100, 100)
        rcls = " class='dp-roll'" if sym.startswith("SPY · ") else ""
        bk = basis.get(sym)
        bstrike = f"${bk[0]:,.0f}" if bk else "—"          # assigned strike (cost anchor)
        bbe = f"${bk[1]:,.0f}" if bk else "—"              # break-even = strike − premium
        # tint vs current price (no single CC strike here): green when price is above the level
        # (shares in profit / above cost), red when underwater.
        scol = (pos if a["price"] >= bk[0] else neg) if bk else mut
        bcol = (pos if a["price"] >= bk[1] else neg) if bk else mut
        rws += (f"<tr{rcls}><td class='dp-l'>{sym}</td>"
                f"<td>${a['prev']:,.2f}</td><td>${a['price']:,.2f}{pm}</td>"
                f"<td><div class='dp-mv'><span class='dp-trk'><i style='width:{w:.0f}%;background:{mcol}'></i></span>"
                f"<b style='color:{mcol}'>{mv:+.1f}%</b></div></td>"
                f"<td class='dp-t'>{kinds}</td>"
                f"<td style='color:{scol}'>{bstrike}</td>"
                f"<td style='color:{bcol}'>{bbe}</td>"
                f"<td style='color:{icol};font-weight:700'>${a['impact']:,.0f}</td></tr>")
    css = (f"<style>.dp-wrap{{max-height:720px;overflow:auto;border:1px solid {bsoft};border-radius:10px;margin-top:6px}}"
           f".dp-tbl{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:14.5px}}"
           f".dp-tbl th{{text-align:right;color:{mut};font-size:11px;font-weight:700;letter-spacing:.4px;"
           f"text-transform:uppercase;padding:9px 13px;background:{raised};border-bottom:1px solid {bsoft};"
           f"position:sticky;top:0;z-index:2}}"
           f".dp-tbl th:first-child,.dp-tbl td:first-child{{text-align:left}}"
           f".dp-tbl td{{text-align:right;padding:9px 13px;border-bottom:1px solid {bsoft};color:{text}}}"
           f".dp-tbl td.dp-l{{font-weight:700}}"
           f".dp-tbl td.dp-t{{text-align:left;color:{mut};font-size:13px}}"
           f".dp-mv{{display:flex;align-items:center;gap:8px;justify-content:flex-end}}"
           f".dp-trk{{display:inline-block;width:64px;height:6px;border-radius:3px;background:{bsoft};overflow:hidden}}"
           f".dp-trk>i{{display:block;height:100%;border-radius:3px}}"
           f".dp-roll td{{background:{amber}14}} .dp-roll td.dp-l{{color:{amber}}}"
           f".dp-pm{{font-size:9px;color:{amber};font-weight:700;border:1px solid {amber};"
           f"border-radius:4px;padding:0 3px;margin-left:3px}}</style>")
    head = "".join(f"<th>{h}</th>" for h in
                   ["Ticker", "Yesterday", "Early", "Move", "Type", "Strike", "Break-Even", "Impact $"])
    st.markdown(css + f"<div class='dp-wrap'><table class='dp-tbl'><thead><tr>{head}</tr></thead>"
                f"<tbody>{rws}</tbody></table></div>", unsafe_allow_html=True)


def render(c: dict) -> None:
    data = cc.board_data()
    if data is None:
        st.warning("Couldn't load the TradeLog tab.")
        return
    if not rh.is_configured():
        st.info("Paste your RH token into the **RHSecret** tab of the workbook to pull the live tape.")
    _impact(c, data["r"], data["df"], data.get("ext") or {})
