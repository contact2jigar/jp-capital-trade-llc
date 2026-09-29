"""📊 Board — a tabular re-imagining of the Cockpit: everything as $ + % tables.

Same live numbers as the Cockpit (command_center.board_data), but organized as the
MonitorBoard tables Jigar lives in: Premium Goals, Wheel Capital, the Focus Matrix
(gaps · breaker · itm · leap), and monthly Performance. Reuses the Cockpit's VIX
strip + shared styling and adds compact board tables. Never places an order.

This is the in-progress replacement for the Cockpit; both run side by side for now.
"""

from __future__ import annotations

import streamlit as st

from logic import monitor as engine
from services import yahoo
from ui import benchmark
from ui.pages import command_center as cc
from ui.pages import cockpit as ck        # shared palettes + helpers (VIX strip, perf, css)

_m = ck._m


def _btag(icon_label: str, sub: str, P: dict) -> str:
    return (f"<div class='ck-chead'><div class='ck-acct'>"
            f"<span class='ck-tag' style='color:{P['steel']};background:{P['steel']}22;"
            f"border:1px solid {P['steel']}66'>{icon_label}</span>"
            f"<span class='ck-sub'>{sub}</span></div></div>")


def _goals(prem: list, P: dict, mo_earned: float | None = None) -> str:
    """Premium goals — Week & Month: Goal / Earned / Gap ($) + run-rate %."""
    d = {}
    for lbl, val in prem or []:
        s = str(lbl).lower()
        per = "wk" if ("wk" in s or "week" in s) else "mo"
        kind = "goal" if "goal" in s else "earned" if "earn" in s else "gap" if "gap" in s else None
        if kind:
            d[f"{per}_{kind}"] = float(val or 0)
    if mo_earned is not None:
        d["mo_earned"] = mo_earned

    def row(per, name):
        goal = d.get(f"{per}_goal", 0) or 1
        earned = d.get(f"{per}_earned", 0)
        gap = goal - earned
        rate = earned / goal * 100
        rc = P["green"] if rate >= 90 else "#facc15" if rate >= 50 else "#3b82f6"
        gaptxt = f"+{_m(-gap)}" if gap < 0 else _m(gap)
        gcol = P["green"] if gap < 0 else P["amber"]
        return (f"<tr><td class='ck-btl'>{name}</td><td>{_m(goal)}</td>"
                f"<td style='color:{rc}'>{_m(earned)}</td>"
                f"<td style='color:{gcol}'>{gaptxt}</td>"
                f"<td style='color:{rc}'>{rate:.0f}%</td></tr>")

    head = "<tr><th>Period</th><th>Goal</th><th>Earned</th><th>Gap</th><th>Rate</th></tr>"
    return (f"<div class='ck-card ck-bcard'>{_btag('🎯 PREMIUM GOALS', 'week · month', P)}"
            f"<table class='ck-btbl'><thead>{head}</thead>"
            f"<tbody>{row('wk', 'Week')}{row('mo', 'Month')}</tbody></table></div>")


def _wheel_table(r: dict, P: dict) -> str:
    """Wheel-capital breakdown — Capital…Ready-to-Deploy, per account, $ + %."""
    I, L = r["ira"], r["llc"]
    ks = ["cap", "ath", "vault", "wcap", "cih", "dep", "csp", "cc", "leap", "rtd"]
    T = {k: (I.get(k) or 0) + (L.get(k) or 0) for k in ks}
    accts = [("IRA", I), ("LLC", L), ("Total", T)]
    rows_def = [("Capital", "wcap", "cap"), ("Cash Vault", "vault", "ath"),
                ("Cash in Hand", "cih", "wcap"), ("Deployed", "dep", "wcap"),
                ("CSP", "csp", "wcap"), ("CC", "cc", "wcap"),
                ("LEAP", "leap", "wcap"), ("Ready to Deploy", "rtd", "wcap")]
    head = "<tr><th>Wheel capital</th>" + "".join(f"<th>{n}</th>" for n, _ in accts) + "</tr>"
    body = ""
    for lbl, key, base in rows_def:
        hi = key == "rtd"
        cells = ""
        for _, a in accts:
            amt = a.get(key) or 0
            b = a.get(base) or 0
            pct = (amt / b * 100) if b else 0
            cells += (f"<td><div class='ck-wamt' style='color:{P['green'] if hi else P['ink']}'>{_m(amt)}</div>"
                      f"<div class='ck-wpct' style='color:{P['green'] if hi else P['mut']}'>{pct:.1f}%</div></td>")
        body += f"<tr class='{'ck-wrtd' if hi else ''}'><td class='ck-btl'>{lbl}</td>{cells}</tr>"
    return (f"<div class='ck-card ck-bcard'>{_btag('💰 WHEEL CAPITAL', '$ · % · per account', P)}"
            f"<table class='ck-btbl ck-wtbl'><thead>{head}</thead><tbody>{body}</tbody></table></div>")


def _matrix_table(r: dict, P: dict) -> str:
    """Focus matrix — the gate/risk table: gaps · breaker · itm · leap, per account."""
    rows = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", r["total"])]
    cols = ["CSP Gap", "CC Breaker", "Breaker Gap", "%CSP ITM", "LEAP %", "LEAP Gap"]
    head = "<tr><th>Account</th>" + "".join(f"<th>{col}</th>" for col in cols) + "</tr>"
    body = ""
    for name, a in rows:
        rtd, ccb = a.get("rtd", 0), (a.get("ccbrk") or 0) * 100
        brkgap, itm = a.get("brkgap", 0), (a.get("cspitm") or 0) * 100
        lp, lg = (a.get("leappct") or 0) * 100, a.get("leapgap", 0)
        bc = P["green"] if ccb < 30 else P["amber"] if ccb < 45 else P["red"]
        lgc = P["green"] if lg >= 0 else P["red"]
        tot = "ck-mtot" if name == "Total" else ""
        body += (f"<tr class='{tot}'><td class='ck-btl'>{name}</td>"
                 f"<td style='color:{P['green']}'>{_m(rtd)}</td>"
                 f"<td style='color:{bc};font-weight:800'>{ccb:.1f}%</td>"
                 f"<td style='color:{P['green']}'>{_m(brkgap)}</td>"
                 f"<td>{itm:.1f}%</td><td>{lp:.1f}%</td>"
                 f"<td style='color:{lgc}'>{_m(lg)}</td></tr>")
    return (f"<div class='ck-card ck-bcard'>{_btag('🚦 FOCUS MATRIX', 'gaps · breaker · itm · leap', P)}"
            f"<table class='ck-btbl'><thead>{head}</thead><tbody>{body}</tbody></table></div>")


def _extra_css(P: dict) -> str:
    return f"""<style>
.ck-bcard{{padding:14px 18px 8px;margin-bottom:14px}}
.ck-btbl{{width:100%;border-collapse:collapse;margin-top:8px}}
.ck-btbl th{{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:{P['mut']};
  font-weight:700;text-align:right;padding:5px 12px;border-bottom:1px solid {P['line']};white-space:nowrap}}
.ck-btbl th:first-child{{text-align:left}}
.ck-btbl td{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;font-weight:700;
  text-align:right;padding:6px 12px;border-bottom:1px solid {P['lsoft']};white-space:nowrap;color:{P['ink']}}}
.ck-btbl tbody tr:last-child td{{border-bottom:none}}
.ck-btl{{text-align:left!important;color:{P['ink']}!important;
  font-family:'IBM Plex Sans',system-ui,sans-serif!important;font-weight:600!important}}
.ck-wamt{{font-size:13.5px;font-weight:700}}
.ck-wpct{{font-size:10.5px;font-weight:600;margin-top:1px}}
.ck-wrtd td{{background:{P['green']}14}}
.ck-mtot td{{border-top:1px solid {P['line']};font-weight:800}}
@media (max-width:640px){{.ck-btbl th,.ck-btbl td{{padding:5px 7px;font-size:11.5px}}}}
</style>"""


def render(c: dict) -> None:
    data = cc.board_data()
    if data is None:
        st.warning("Couldn't load the TradeLog tab.")
        return
    r, vix, vix_chg, trend = data["r"], data["vix"], data["vix_chg"], data["trend"]
    P = ck.LIGHT if ck._is_light(c.get("bg", "")) else ck.DARK
    try:
        mdf, _ = benchmark.monthly_df()
    except Exception:
        mdf = None

    band = r.get("band", 2)
    bdef = engine.BANDS[band] if 0 <= band < len(engine.BANDS) else engine.BANDS[2]
    up = str(trend).lower().startswith("up")
    dmin, dmax = (bdef[1] if up else bdef[3]) * 100, (bdef[2] if up else bdef[4]) * 100
    band_lbl = bdef[0]
    chg_col = P["red"] if vix_chg > 0 else P["green"]
    fg = yahoo.fear_greed()
    fg_block, vcols = "", "auto 1fr auto"
    if fg:
        s = fg["score"]
        fgc = (P["red"] if s < 25 else P["amber"] if s < 45 else P["gold"] if s < 55
               else "#7cc47d" if s < 75 else P["green"])
        fg_block = ck._fg_gauge(s, fg["rating"], fgc, P)
        vcols = "auto auto 1fr auto"
    tc = P["green"] if up else P["red"]
    trend_badge = (f"<span class='ck-trend' style='color:{tc};background:{tc}22;border:1px solid {tc}55'>"
                   f"{'↑' if up else '↓'} {trend}</span>")

    html = f"""{ck._css(P)}{_extra_css(P)}
    <div class="ck-wrap">
      <div class="ck-panel ck-vix" style="grid-template-columns:{vcols}">
        <div class="ck-vixnow"><span class="l">VIX</span><span class="vv">{vix:.2f}</span>
          <span class="ck-chg" style="color:{chg_col};background:{chg_col}22;border:1px solid {chg_col}55">
          {vix_chg * 100:+.1f}%</span></div>
        {fg_block}
        <div class="ck-meter">{ck._vix_meter(vix, band, up)}</div>
        <div class="ck-regime">
          <div class="ck-tl-row"><span class="ck-tl">Target</span>{trend_badge}</div>
          <div class="ck-target">{dmin:.0f}–{dmax:.0f}%</div>
          <div class="s">band {band_lbl} · now {r.get('alloc', 0) * 100:.0f}%</div>
        </div>
      </div>
    </div>"""
    html = "\n".join(line.lstrip() for line in html.splitlines())
    st.markdown(html, unsafe_allow_html=True)
