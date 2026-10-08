"""📊 Board — a tabular re-imagining of the Cockpit: everything as $ + % tables.

Same live numbers as the Cockpit (command_center.board_data), but organized as the
MonitorBoard tables Jigar lives in: Premium Goals, Wheel Capital, the Focus Matrix
(gaps · breaker · itm · leap), and monthly Performance. Reuses the Cockpit's VIX
strip + shared styling and adds compact board tables. Never places an order.

This is the in-progress replacement for the Cockpit; both run side by side for now.
"""

from __future__ import annotations

import datetime as _dt
import math

import pandas as pd
import streamlit as st

from logic import monitor as engine
from services import yahoo
from ui import benchmark
from ui.pages import command_center as cc
from ui.pages import cockpit as ck        # shared palettes + helpers (VIX strip, perf, css)

_m = ck._m
_MMF_YIELD = 3.1   # money-market 7-day yield (SPAXX-type core) — bump when Fidelity changes it


def _btag(icon_label: str, sub: str, P: dict) -> str:
    emoji, _, label = icon_label.partition(" ")           # enlarge just the leading emoji
    inner = f"<span class='ck-temoji'>{emoji}</span> {label}" if label else icon_label
    return (f"<div class='ck-chead'><div class='ck-acct'>"
            f"<span class='ck-tag' style='color:{P['ink']};background:{P['steel']}33;"
            f"border:1px solid {P['steel']}88'>{inner}</span>"
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


def _goal_card(prem: list, P: dict, mo_earned: float | None = None) -> str:
    """Premium goals merged into ONE compact card — Weekly + Monthly rows, each with the
    earned/goal, gap text, and the blue→yellow→green progress meter."""
    d = {}
    for lbl, val in prem or []:
        s = str(lbl).lower()
        per = "wk" if ("wk" in s or "week" in s) else "mo"
        kind = "goal" if "goal" in s else "earned" if "earn" in s else "gap" if "gap" in s else None
        if kind:
            d[f"{per}_{kind}"] = float(val or 0)
    if mo_earned is not None:
        d["mo_earned"] = mo_earned

    def row(per, title):
        goal = d.get(f"{per}_goal", 0) or 1
        earned = d.get(f"{per}_earned", 0)
        gap = goal - earned
        rate = earned / goal * 100
        w = max(0.0, min(100.0, rate))
        pc = P["green"] if rate >= 90 else "#facc15" if rate >= 50 else "#3b82f6"
        gaptxt = f"Beat goal by · {_m(-gap)}" if gap < 0 else f"Gap to goal · {_m(gap)}"
        gcol = P["green"] if gap < 0 else P["amber"]
        return (f"<div class='ck-grow'>"
                f"<div class='ck-phead'><span class='ck-plabel'>💰 {title}</span>"
                f"<span class='ck-pval'><b style='color:{pc}'>{_m(earned)}</b> "
                f"<span>/ {_m(goal)}</span></span></div>"
                f"<div class='ck-pbot'><span class='ck-pgaptxt' style='color:{gcol}'>{gaptxt}</span>"
                f"<div class='ck-pbar'><div class='ck-pband'></div>"
                f"<div class='ck-pneedle' style='left:{w:.1f}%'></div></div>"
                f"<span class='ck-prpct' style='color:{pc}'>{rate:.0f}%</span></div></div>")

    return (f"<div class='ck-card ck-goalcard'>{_btag('🎯 PREMIUM GOALS', 'weekly · monthly', P)}"
            f"{row('wk', 'Weekly earned')}{row('mo', 'Monthly earned')}</div>")


def _prem_dict(prem: list, mo_earned: float | None = None) -> dict:
    d = {}
    for lbl, val in prem or []:
        s = str(lbl).lower()
        per = "wk" if ("wk" in s or "week" in s) else "mo"
        kind = "goal" if "goal" in s else "earned" if "earn" in s else "gap" if "gap" in s else None
        if kind:
            d[f"{per}_{kind}"] = float(val or 0)
    if mo_earned is not None:
        d["mo_earned"] = mo_earned
    return d


def _period_card(title: str, earned: float, goal: float, P: dict) -> str:
    """Small single-period premium card: label + 💰, earned/goal, run-rate bar + %."""
    goal = goal or 1
    rate = earned / goal * 100
    w = max(0.0, min(100.0, rate))
    rcol = P["green"] if rate >= 100 else P["blue"]        # on track = blue, goal beaten = green
    return (f"<div class='ck-card ck-pcard2'>"
            f"<div class='ck-p2head'><span class='ck-p2label'>{title} earned premium</span>"
            f"<span class='ck-p2icon'>💰</span></div>"
            f"<div class='ck-p2val'><b style='color:{rcol}'>{_m(earned)}</b> <span>/ {_m(goal)}</span></div>"
            f"<div class='ck-p2rate'><span style='color:{rcol}'>{rate:.1f}%</span></div>"
            f"<div class='ck-p2track'><div class='ck-p2fill' style='width:{w:.1f}%'></div></div></div>")


def _meter(frac: float, P: dict, uid: str, zones: list, pace: float | None = None) -> str:
    """Semicircle meter — same geometry as the CC-breaker gauge so the row matches. A dim
    full-arc track, then a colored fill that grows LEFT→RIGHT to `frac`, lighting each
    `zones` colour in turn (red→amber→green), with a needle + arrowhead on top. `pace`
    (0..1) draws a 'today' tick on the arc — where you should be by end of today.
    `zones` = [(start, end, colour), …] as arc fractions 0..1 covering the whole scale."""
    cx, cy, r = 90, 86, 70
    f = max(0.0, min(1.0, float(frac)))

    def pol(deg, rad=r):
        a = math.radians(deg)
        return cx + rad * math.cos(a), cy - rad * math.sin(a)

    def arc(f1, f2, c, w=12):
        if f2 <= f1:
            return ""
        x1, y1 = pol(180 - f1 * 180)
        x2, y2 = pol(180 - f2 * 180)
        return (f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" '
                f'fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>')

    track = arc(0.0, 1.0, P["line"], 12)
    fill = "".join(arc(a, min(b, f), c) for a, b, c in zones if f > a)
    pmark = ""
    if pace is not None:                               # "today" tick on the arc
        pf = max(0.0, min(1.0, float(pace)))
        mx1, my1 = pol(180 - pf * 180, r - 9)
        mx2, my2 = pol(180 - pf * 180, r + 9)
        pmark = (f'<line x1="{mx1:.1f}" y1="{my1:.1f}" x2="{mx2:.1f}" y2="{my2:.1f}" '
                 f'stroke="{P["ink"]}" stroke-width="2.5"/>')
    by = cy - 8                                        # raised, shorter needle so it clears the % below
    ang = math.radians(180 - f * 180)
    nx, ny = cx + 46 * math.cos(ang), by - 46 * math.sin(ang)
    mid = f"mtip{uid}"
    return f"""<svg viewBox="0 0 180 92" width="100%" style="max-width:172px" aria-label="meter {f * 100:.0f}%">
      <defs><marker id="{mid}" markerUnits="userSpaceOnUse" markerWidth="15" markerHeight="15" refX="3" refY="7.5" orient="auto"><path d="M0,0 L15,7.5 L0,15 Z" fill="{P['ink']}"/></marker></defs>
      {track}{fill}{pmark}
      <line x1="{cx}" y1="{by}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{P['ink']}" stroke-width="2.5" stroke-linecap="round" marker-end="url(#{mid})"/>
      <circle cx="{cx}" cy="{by}" r="4" fill="{P['ink']}"/>
      <circle cx="{cx}" cy="{by}" r="7" fill="none" stroke="{P['line']}" stroke-width="1.5"/>
    </svg>"""


def _pace_fracs():
    """How far through the week / month we are, by TRADING days (premium is earned on
    trading days). Weekly = trading days elapsed ÷ 5; Monthly = business days elapsed ÷
    the month's total business days. Used to pro-rate the goal to a 'should be here today'."""
    import calendar
    import datetime as _d
    t = _d.date.today()
    # Mon→1/5 … Fri→5/5, Sat→5/5 (finished week still shown); Sun→0 (new week reset).
    wk = 0.0 if t.weekday() == 6 else min(t.weekday() + 1, 5) / 5.0

    def _bdays(d1, d2):
        n, d = 0, d1
        while d <= d2:
            if d.weekday() < 5:
                n += 1
            d += _d.timedelta(days=1)
        return n
    first = t.replace(day=1)
    last = t.replace(day=calendar.monthrange(t.year, t.month)[1])
    tot = _bdays(first, last)
    mo = (_bdays(first, t) / tot) if tot else 0.0
    return wk, mo


def _year_frac() -> float:
    """Fraction of the YEAR elapsed by trading (business) days — for the yearly goal's pace."""
    import datetime as _d
    t = _d.date.today()

    def _bd(d1, d2):
        n, d = 0, d1
        while d <= d2:
            if d.weekday() < 5:
                n += 1
            d += _d.timedelta(days=1)
        return n
    tot = _bd(_d.date(t.year, 1, 1), _d.date(t.year, 12, 31))
    return (_bd(_d.date(t.year, 1, 1), t) / tot) if tot else 0.0


def _goalmeter_card(pd: dict, P: dict) -> str:
    """Premium Goals — two meter dials (Weekly · Monthly). Needle = run-rate on a 0–100%
    dial where 100% = goal = the far-right end; over-goal pins full right and the % still
    shows the beat. A pace line shows where you should be *today* (goal pro-rated by
    trading days elapsed) and whether you're ahead or behind that."""
    wk_frac, mo_frac = _pace_fracs()

    def one(per, name):
        goal = pd.get(f"{per}_goal", 0) or 1
        earned = pd.get(f"{per}_earned", 0) or 0
        rate = earned / goal * 100
        pace_t = goal * (wk_frac if per == "wk" else mo_frac)      # where you should be today
        # Colour the dial by PACE: how you track vs today's pro-rated target.
        ratio = (earned / pace_t) if pace_t > 0 else (2.0 if earned > 0 else 1.0)  # 0/0 = on pace
        pcol = (P["green"] if ratio >= 1.0 else "#f2c436" if ratio >= 0.75
                else "#f08a24" if ratio >= 0.5 else P["red"])
        zones = [(0.0, 1.0, pcol)]                     # fill length = % of goal · colour = pace
        tag = "ahead" if ratio >= 1.0 else "behind"
        return (f"<div class='ck-bg'><div class='ck-bglabel'>{name}</div>"
                f"{_meter(rate / 100.0, P, 'gl' + per, zones, pace=(wk_frac if per == 'wk' else mo_frac))}"
                f"<div class='ck-gv' style='color:{pcol}'>{rate:.0f}%</div>"
                f"<div class='ck-gz'>{_m(earned)} <span>/ {_m(goal)}</span></div>"
                f"<div style='font-size:9.5px;font-weight:700;color:{pcol};margin-top:1px;'>"
                f"pace {_m(pace_t)} · {tag}</div></div>")
    return (f"<div class='ck-card ck-brkcard ck-gm'>{_btag('🎯 GOALS', '47% AOR · 1.5% ATH', P)}"
            f"<div class='ck-bgrow2'>{one('wk', 'WEEKLY')}{one('mo', 'MONTHLY')}</div></div>")


_PACE_STARTED = 0.05       # below this fraction elapsed, "ahead/behind" is meaningless


def _pace_status(earned: float, goal: float, pf: float, P: dict):
    """(colour, label) for a bar. Colour by how earned tracks today's pace target; the
    label carries the DOLLAR gap vs pace (±$X) — the sign says ahead/behind, the amount
    says whether to push or coast (+$998 on day 2 ≠ +$8,000 on day 12). When the period
    has barely started (pf < 5%) the pace target is ~0, so we show a neutral 'not started'
    instead of pretending a dollar gap is meaningful."""
    pace_t = goal * pf
    if pf < _PACE_STARTED:
        return P["mut"], "not started"
    vs = earned - pace_t
    ratio = (earned / pace_t) if pace_t > 0 else (2.0 if earned > 0 else 1.0)
    col = (P["green"] if ratio >= 1.0 else "#f2c436" if ratio >= 0.75
           else "#f08a24" if ratio >= 0.5 else P["red"])
    return col, f"{'+' if vs >= 0 else '−'}{_m(abs(vs))} vs pace"


def _goalbar_card(pd: dict, P: dict) -> str:
    """Premium Goals as full bullet bars (Monthly + Weekly). The BAR is blue — it shows
    progress toward the goal $ (0 → goal). The 'today' tick marks where you should be by
    end of today, and the AHEAD/BEHIND badge + '±$ vs pace' line are coloured by pace
    (green ahead · warm behind · grey not-started). Each bar also shows % complete and
    $ remaining."""
    wk_frac, mo_frac = _pace_fracs()

    def bar(name, earned, goal, pf):
        goal = goal or 1
        # The BAR carries the status by colour (no pressure number): GREEN when you're ahead of
        # where you should be TODAY (pace) or already past goal, GOLD when a little behind. The
        # right caption says how much is left to reach the full goal.
        pace_t = goal * pf
        pct = earned / goal * 100
        ahead = (earned >= pace_t) or (pct >= 100)
        fill = P["green"] if ahead else P["gold"]
        rem = goal - earned
        rtxt = f"{ck._mk(rem)} to reach · {pct:.0f}%" if rem > 0 else f"goal met · {pct:.0f}% ✓"
        fill_pct = max(0.0, min(100.0, pct))
        mark_pct = max(0.0, min(100.0, pf * 100))
        return (
            f"<div style='margin:6px 8px 5px'>"
            # stats line: earned / goal (left) · remaining-to-reach + % (right)
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:4px'>"
            f"<span style='font-size:13px;font-weight:800;color:{P['ink']};white-space:nowrap'>{_m(earned)} "
            f"<span style='font-size:9.5px;color:{P['mid']};font-weight:600'>/ {_m(goal)}</span></span>"
            f"<span style='font-size:10.5px;color:{P['mut']};white-space:nowrap'>{rtxt}</span></div>"
            # label + colourful (pace-coloured) bar on one line
            f"<div style='display:flex;align-items:center;gap:9px'>"
            f"<span style='font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:{P['mut']};"
            f"font-weight:800;width:54px;flex:none'>{name}</span>"
            f"<div style='position:relative;flex:1;height:11px;background:{P['track']};border-radius:6px'>"
            f"<div style='position:absolute;left:0;top:0;height:100%;width:{fill_pct:.1f}%;background:{fill};"
            f"border-radius:6px'></div>"
            f"<div style='position:absolute;top:-2px;bottom:-2px;left:{mark_pct:.1f}%;width:2px;background:{P['ink']}'></div>"
            f"</div></div></div>")

    mg, me = pd.get("mo_goal", 0) or 1, pd.get("mo_earned", 0) or 0
    wg, we = pd.get("wk_goal", 0) or 1, pd.get("wk_earned", 0) or 0
    yg, ye = pd.get("yr_goal", 0) or 1, pd.get("yr_earned", 0) or 0
    yr_frac = _year_frac()
    sep = f"<div style='border-top:1px solid {P['lsoft']};margin:2px 8px'></div>"
    yearly = f"{bar('YEARLY', ye, yg, yr_frac)}{sep}" if pd.get("yr_goal") else ""
    return (f"<div class='ck-card ck-brkcard'>{_btag('🎯 GOALS', '47% AOR · 1.5% ATH', P)}"
            f"{yearly}"
            f"{bar('MONTHLY', me, mg, mo_frac)}"
            f"{sep}"
            f"{bar('WEEKLY', we, wg, wk_frac)}</div>")


def _breaker_card(r: dict, P: dict) -> str:
    """CC Breaker — all three gauges (IRA · LLC · Total), the exact Cockpit semicircle."""
    def one(name, a):
        brk = (a.get("ccbrk") or 0) * 100
        over = brk > 45                                     # breached the cap
        zc = P["green"] if brk < 30 else P["amber"] if brk < 45 else P["red"]
        gap = a.get("brkgap", 0)                            # $ headroom to the 45% cap (neg = over)
        gv = (f"<div class='ck-gv' style='color:{P['red']}'>{brk:.1f}% "
              f"<span style='font-size:9px;font-weight:900;letter-spacing:.04em;color:#fff;"
              f"background:{P['red']};border-radius:4px;padding:1px 5px;vertical-align:2px;'>OVER CAP</span></div>"
              if over else f"<div class='ck-gv'>{brk:.1f}%</div>")
        return (f"<div class='ck-bg'><div class='ck-bglabel'>{name}</div>"
                f"{ck._gauge(brk, P, 'b' + name)}{gv}"
                f"<div class='ck-gz' style='color:{zc}'>{_m(gap)} <span>gap</span></div></div>")
    accts = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", r["total"])]
    return (f"<div class='ck-card ck-brkcard'>{_btag('🚦 CIRCUIT BREAKER', 'Cap 45%', P)}"
            f"<div class='ck-bgrow'>{''.join(one(n, a) for n, a in accts)}</div></div>")


def _money_card(r: dict, P: dict) -> str:
    """Money — Capital · All Time High · Cash Vault (30% ATH), IRA/LLC with $ and %."""
    _T = {k: (r["ira"].get(k) or 0) + (r["llc"].get(k) or 0)
          for k in ("cap", "ath", "ath0", "vault", "cih", "csp")}
    accts = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", _T)]
    rows_def = [("All Time High", "ath"), ("Capital", "cap"), ("Cash Vault", "vault")]
    cells = ("<div class='ck-mh ck-mhl'>Money</div>"
             + "".join(f"<div class='ck-mh'>{n}</div>" for n, _ in accts))
    for lbl, key in rows_def:
        cells += f"<div class='ck-ml'>{lbl}</div>"
        for _, a in accts:
            val = _m(a.get(key) or 0)
            cap_v, ath_v = (a.get("cap") or 0), (a.get("ath") or 0)
            at_ath = abs(cap_v - ath_v) < 1                 # value has caught up to the ATH ratchet
            delta = cap_v - (a.get("ath0") or 0)            # new ground made today
            if key == "ath" and at_ath:                     # trophy + record on the ATH row
                cells += f"<div class='ck-mv ck-athrow'><span class='ck-athtrophy'>🏆</span> {val}</div>"
            elif key == "cap" and at_ath and delta > 0.5:   # today's gain sits on the Capital row
                comp = f"${delta / 1e6:.1f}M" if delta >= 1e6 else f"${delta / 1e3:.1f}K"
                cells += f"<div class='ck-mv'><span class='ck-athup'>({comp})</span> {val}</div>"
            else:
                cells += f"<div class='ck-mv'>{val}</div>"
    # Cash In Hand row — free cash (not tied in CSP collateral = cih + vault) as a % of each
    # account's own capital; the Total reads the "CASH %" that used to sit in the subtitle.
    cells += "<div class='ck-ml'>Cash In Hand</div>"
    for _, a in accts:
        cap_a = a.get("cap") or 0
        free_a = (a.get("cih") or 0) + (a.get("vault") or 0)
        cells += f"<div class='ck-mv'>{(free_a / cap_a * 100) if cap_a else 0:.0f}%</div>"
    # Money-market cash (CSP collateral + cash in hand + vault) as a share of TOTAL capital.
    _cash = sum((a.get("csp") or 0) + (a.get("cih") or 0) + (a.get("vault") or 0)
                for a in (r["ira"], r["llc"]))
    _cap = sum((a.get("cap") or 0) for a in (r["ira"], r["llc"]))
    _cashp = (_cash / _cap * 100) if _cap else 0
    _ck = f"${_cash / 1e6:.1f}M" if _cash >= 1e6 else f"${_cash / 1e3:.0f}K"
    msub = f"{_cashp:.0f}% ({_ck}) @ ~{_MMF_YIELD:.1f}% · Vault 30%"
    return (f"<div class='ck-card ck-bcard'>{_btag('🏦 MONEY', msub, P)}"
            f"<div class='ck-mgrid'>{cells}</div></div>")


def _perf_ytd(mdf, year: int) -> dict:
    """Per-account (Jan start, latest-month end) for `year` from the Performance tab — the
    SAME point-to-point basis as the Performance grid's Total column, so the THIS YEAR card
    and the Performance card always agree. Returns {'ira': (start, end), 'llc': (start, end)}."""
    if mdf is None or getattr(mdf, "empty", True):
        return {}
    recs = {rr["date"].month: rr for rr in mdf.to_dict("records") if rr["date"].year == year}
    if 1 not in recs:
        return {}
    lm = max(recs)
    out = {}
    for acct, endk, startk in (("ira", "IRA", "ira_start"), ("llc", "LLC", "llc_start")):
        s, e = recs[1].get(startk), recs[lm].get(endk)
        if s and e:
            out[acct] = (float(s), float(e))
    return out


def _ytd_card(r: dict, ext: dict, P: dict, perf: dict | None = None) -> str:
    """📅 THIS YEAR — overall YTD gain across ALL accounts. IRA/LLC come from the PERFORMANCE
    tab (point-to-point Jan start → latest end, so they match the Performance card); the LLC
    end adds the parked $30K. Rollover/Roth come from the Z/AA config. Gain = now − start; only
    accounts with a start value show. Falls back to live capital − Z/AA start if Performance is
    unavailable."""
    ext = ext or {}
    perf = perf or {}
    tag = _btag("📅 THIS YEAR", "from Performance · + parked LLC · Wheel + Retirement", P)
    park = ext.get("park_llc") or 0
    if "ira" in perf and "llc" in perf:                  # Performance basis (preferred)
        ira_s, ira_e = perf["ira"]
        llc_s, llc_e = perf["llc"]
        wheel = [("IRA", ira_e, ira_s), ("LLC", llc_e + park, llc_s)]
    else:                                                 # fallback — live capital − Z/AA start
        llc_cur = (r["llc"].get("cap") or 0) + park
        wheel = [("IRA", (r["ira"].get("cap") or 0), ext.get("ytd_ira") or 0),
                 ("LLC", llc_cur, ext.get("ytd_llc") or 0)]
    groups = [("Wheel", wheel),
              ("Retirement", [("Rollover", ext.get("cur_rollover") or 0, ext.get("ytd_rollover") or 0),
                              ("Roth", ext.get("cur_roth") or 0, ext.get("ytd_roth") or 0)])]
    mono = 'font-family:"IBM Plex Mono",ui-monospace,monospace;'   # DOUBLE quotes inside style=''
    accents = {"Wheel": P["blue"], "Retirement": P["purple"]}
    # Grid columns live in a scoped stylesheet so a media query can stack the two groups and
    # shrink the row on phones (inline styles can't carry media queries). .ytg = the two groups,
    # .ytr = one row (label · Start · Now · YTD Gain).
    css = ("<style>.ytg{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
           ".ytr{display:grid;grid-template-columns:1fr 86px 92px 128px}"
           "@media(max-width:760px){.ytg{grid-template-columns:1fr;gap:4px}"
           ".ytr{grid-template-columns:minmax(34px,1fr) auto auto auto;gap:6px}"
           ".ytr>div{font-size:10.5px !important}.ytr>div>span{font-size:9px !important}}</style>")

    def cell(label, start, gain, accent, kind=""):        # kind: "" (account) | "sub" (group total)
        pc = (gain / start * 100) if start else 0.0
        col = P["green"] if gain >= 0 else P["red"]
        bg = f"background:{accent}22;" if kind == "sub" else ""     # tinted subtotal row
        lw = "800" if kind == "sub" else "600"
        return (f"<div class='ytr' style='align-items:center;gap:10px;"
                f"border-left:3px solid {accent};{bg}padding:3px 11px;border-radius:6px;margin-bottom:3px'>"
                f"<div style='font-weight:{lw};color:{P['ink']};font-size:13px'>{label}</div>"
                f"<div style='{mono}text-align:right;color:{P['mut']};font-size:12px'>{_m(start)}</div>"
                f"<div style='{mono}text-align:right;color:{P['ink']};font-size:12px'>{_m(start + gain)}</div>"
                f"<div style='{mono}text-align:right;color:{col};font-weight:700;font-size:13px'>"
                f"{_m(gain)} <span style='font-size:10px;color:{P['mut']}'>({pc:+.1f}%)</span></div></div>")

    hd = f"font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:{P['mut']};font-weight:700;"
    header = (f"<div class='ytr' style='gap:10px;padding:0 11px 2px'>"
              f"<div style='{hd}'>Account</div><div style='{hd}text-align:right'>Start</div>"
              f"<div style='{hd}text-align:right'>Now</div>"
              f"<div style='{hd}text-align:right'>YTD Gain</div></div>")

    cols_html, all_live = [], []
    for gname, members in groups:
        live = [(n, cur, s) for n, cur, s in members if s > 0]
        if not live:
            continue
        all_live += live
        acc = accents.get(gname, P["blue"])
        body = header + "".join(cell(n, s, cur - s, acc) for n, cur, s in live)
        gstart = sum(s for _, _, s in live)
        body += cell(f"{gname} Total", gstart, sum(cur - s for _, cur, s in live), acc, kind="sub")
        cols_html.append(f"<div>{body}</div>")
    if not all_live:
        return (f"<div class='ck-card ck-bcard'>{tag}<div class='ck-sub' style='margin-top:6px'>"
                f"Fill the <b>YTD Start</b> values in the sheet's Z/AA config to light this up.</div></div>")
    # Grand Total: prefer the TRUE all-accounts start from the config (per-account starts are
    # only estimates that won't sum to the real Jan-1); current = the live sum.
    sum_start = sum(s for _, _, s in all_live)
    sum_cur = sum(cur for _, cur, _ in all_live)
    gstart_all = ext.get("ytd_start_total") or 0.0
    gcur_all = ext.get("cur_total") or 0.0        # optional manual override; else use live sum
    if gstart_all > 0:
        tstart = gstart_all
        tcur = gcur_all if gcur_all > 0 else sum_cur
        glabel = "Grand Total · all accounts"
    else:
        tstart, tcur = sum_start, sum_cur
        glabel = "Grand Total"
    tgain = tcur - tstart
    tpct = (tgain / tstart * 100) if tstart else 0.0
    gc = P["green"] if tgain >= 0 else P["red"]
    head = (f"<div style='display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:2px 0 6px'>"
            f"<span style='font-size:24px;font-weight:800;color:{gc}'>{_m(tgain)}</span>"
            f"<span style='font-size:15px;font-weight:700;color:{gc}'>{tpct:+.1f}%</span>"
            f"<span style='font-size:12px;color:{P['mut']}'>· {_m(tstart)} → {_m(tcur)}</span></div>")
    cols = f"<div class='ytg'>{''.join(cols_html)}</div>"
    ggain = "#4ade80" if tgain >= 0 else "#f87171"     # bright on the dark bar
    grand = (f"<div class='ytr' style='align-items:center;gap:10px;background:#141b2b;"
             f"padding:6px 11px;border-radius:7px;margin-top:5px'>"
             f"<div style='font-weight:800;color:#fff;font-size:13px'>{glabel}</div>"
             f"<div style='{mono}text-align:right;color:#cbd5e1;font-size:12px'>{_m(tstart)}</div>"
             f"<div style='{mono}text-align:right;color:#fff;font-size:12px'>{_m(tcur)}</div>"
             f"<div style='{mono}text-align:right;color:{ggain};font-weight:800;font-size:14px'>"
             f"{_m(tgain)} <span style='font-size:10px;color:#94a3b8'>({tpct:+.1f}%)</span></div></div>")
    return f"{css}<div class='ck-card ck-bcard'>{tag}{head}{cols}{grand}</div>"


def _ccotm(df) -> dict:
    """Per-account $ of covered calls that are OUT of the money (open CALL, strike > current)."""
    od = engine._openrows(df)
    if od.empty or "Opt Typ" not in od:
        return {}
    d = od[od["Opt Typ"].astype(str).str.upper() == "CALL"].copy()
    if d.empty or "Current Price" not in d or "Strike Price" not in d or "Cash Reserve" not in d:
        return {}
    cp = d["Current Price"].map(engine._money)
    k = d["Strike Price"].map(engine._money)
    d = d[(cp > 0) & (k > cp)]
    if d.empty:
        return {}
    res = (d.assign(_r=d["Cash Reserve"].map(engine._money))
           .groupby(d["Account"].astype(str).str.upper())["_r"].sum())
    return res.to_dict()


def _summary_grid(r: dict, P: dict) -> str:
    """One consolidated table — IRA/LLC/Total rows; the 3 decision metrics (Ready · %CSP ITM ·
    CC Breaker) sit in the centre, capital/deploy on the left, positions on the right."""
    accts = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", _total_acct(r["ira"], r["llc"]))]
    # (label, kind, key, base, is_key)  kind: dollar | ready (green $). All show $ + %.
    cols = [("Capital", "dollar", "wcap", "cap", False),
            ("VIX Target", "dollar", "vtgt", "wcap", False),
            ("Deployed", "dollar", "dep", "wcap", False),
            ("Ready to Deploy", "ready", "rtd", "wcap", True),
            ("Cash in Hand", "dollar", "cih", "wcap", True),
            ("CSP ITM", "dollar", "itm", "wcap", True),
            ("CSP", "dollar", "csp", "wcap", False),
            ("CC", "dollar", "cc", "wcap", False),
            ("LEAP", "dollar", "leap", "wcap", False)]
    head = "<div class='ck-fh ck-fhl'>Account</div>"
    head += "".join(f"<div class='ck-fh{' ck-khf' if isk else ''}'>{lbl}</div>"
                    for lbl, k, key, base, isk in cols)
    cells = head
    for name, a in accts:
        cells += f"<div class='ck-fa'>{name}</div>"
        for lbl, k, key, base, isk in cols:
            amt = a.get(key) or 0
            b = a.get(base) or 0
            pct = (amt / b * 100) if b else 0
            if k == "ready":                               # amount in a green/red badge (black text),
                bg = "#43c463" if amt >= 0 else "#f2555a"  # then the % as plain green/red text below
                pcol = "#43c463" if amt >= 0 else "#f2555a"
                cells += (f"<div class='ck-wc ck-kcell'>"
                          f"<span class='ck-rbadge' style='background:{bg}'><b>{_m(amt)}</b></span>"
                          f"<span class='ck-rpct' style='color:{pcol}'>{pct:.1f}%</span></div>")
                continue
            cls = "ck-wc ck-kcell" if isk else "ck-wc"
            cells += (f"<div class='{cls}'><span class='ck-wca'>{_m(amt)}</span>"
                      f"<span class='ck-wcp'>{pct:.1f}%</span></div>")
    T = _total_acct(r["ira"], r["llc"])
    _wc, _dep = (T.get("wcap") or 0), (T.get("dep") or 0)
    _depp = (_dep / _wc * 100) if _wc else 0
    _wck = f"{_wc / 1e3:,.0f}K"
    sub = f"{_depp:.0f}% deployed of Wheel Capital {_wck} · ⏰ check GTC"
    return (f"<div class='ck-card ck-fcard'>{_btag('🛞 WHEEL SUMMARY', sub, P)}"
            f"<div class='ck-sgw'><div class='ck-sgrid'>{cells}</div></div></div>")


def _matrix_grid(r: dict, P: dict) -> str:
    """Focus matrix — IRA/LLC/Total as rows, gates as columns, with green/red cell fills."""
    rows = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", r["total"])]
    cols = ["Account", "CSP Gap", "CC Breaker", "Breaker Gap", "%CSP ITM", "LEAP %", "LEAP Gap"]
    cells = "".join(f"<div class='ck-fh{' ck-fhl' if i == 0 else ''}'>{c}</div>"
                    for i, c in enumerate(cols))
    for name, a in rows:
        rtd, ccb = a.get("rtd", 0), (a.get("ccbrk") or 0) * 100
        brkgap, itm = a.get("brkgap", 0), (a.get("cspitm") or 0) * 100
        lp, lg = (a.get("leappct") or 0) * 100, a.get("leapgap", 0)
        bc = P["green"] if ccb < 30 else P["amber"] if ccb < 45 else P["red"]
        cells += f"<div class='ck-fa'>{name}</div>"
        cells += f"<div class='ck-fg'>{_m(rtd)}</div>"
        cells += f"<div class='ck-fg' style='color:{bc}'>{ccb:.1f}%</div>"
        cells += f"<div class='ck-fg'>{_m(brkgap)}</div>"
        cells += f"<div class='ck-fn'>{itm:.1f}%</div>"
        cells += f"<div class='ck-fn'>{lp:.1f}%</div>"
        cells += f"<div class='ck-{'fg' if lg >= 0 else 'fr'}'>{_m(lg)}</div>"
    return (f"<div class='ck-card ck-fcard'>{_btag('🚦 FOCUS MATRIX', 'gaps · breaker · itm · leap', P)}"
            f"<div class='ck-fgrid'>{cells}</div></div>")


_ITYPE_ORDER = ["01-Growth", "02-Alternate", "03-Speculation",
                "04-WatchList", "04-LEAP", "5-Others"]


def _alloc_groups(df, acct_upper: str) -> list:
    """Per-stock aggregates for one account, grouped by Invest Type (canonical order; the
    X-list cash bucket is excluded). Each stock aggregates its open rows: P/L & Cash Reserve
    & Qty summed, Current Price & Strike averaged. Returns [(invest_type, [stock dicts])]."""
    if df is None or getattr(df, "empty", True):
        return []
    od = engine._openrows(df)
    need = ["Account", "Stock", "Invest Type", "Profit Loss", "Cash Reserve",
            "Current Price", "Strike Price", "Qty"]
    if od.empty or any(cn not in od.columns for cn in need):
        return []
    d = od[od["Account"].astype(str).str.upper() == acct_upper].copy()
    su = d["Stock"].astype(str).str.upper()
    d = d[~su.isin(["", "NAN", "CASH", "VAULT"])]
    if d.empty:
        return []
    d["_stock"] = d["Stock"].astype(str).str.upper()
    d["_it"] = d["Invest Type"].astype(str).str.strip()
    for raw, k in [("Profit Loss", "_pl"), ("Cash Reserve", "_cash"),
                   ("Current Price", "_price"), ("Strike Price", "_strike"), ("Qty", "_qty")]:
        d[k] = d[raw].map(engine._money)
    # Return column = AOR (annualized) per position; _money doesn't strip '%', so do it here.
    has_ret = "Return" in d.columns
    d["_aor"] = (d["Return"].map(lambda v: engine._money(str(v).replace("%", "")))
                 if has_ret else 0.0)
    # Known types in canonical order, then ANY other real category found in the data
    # (e.g. a newly added 04-WatchList / 5-Others), so a bucket never silently vanishes.
    # Only the X-list cash bucket is excluded.
    present = list(dict.fromkeys(d["_it"].tolist()))
    extras = [it for it in present
              if it and it not in _ITYPE_ORDER and not it.upper().startswith("X")]
    out = []
    for it in [t for t in _ITYPE_ORDER if t in present] + extras:
        g = d[d["_it"] == it]
        if g.empty:
            continue
        stocks = []
        for stk, sg in g.groupby("_stock"):
            csum = sg["_cash"].sum()
            waor = float((sg["_aor"] * sg["_cash"]).sum() / csum) if (has_ret and csum) else None
            stocks.append(dict(stock=stk, pl=sg["_pl"].sum(), cash=csum,
                               qty=sg["_qty"].sum(), price=sg["_price"].mean(),
                               strike=sg["_strike"].mean(), aor=waor))
        stocks.sort(key=lambda x: x["stock"])
        out.append((it, stocks))
    return out


def _alloc_card(df, name: str, a: dict, P: dict) -> str:
    """One account's holdings grouped by Invest Type with per-group subtotals:
    Stock · P/L · %Alloc · Cash Reserved · Current · Qty · Strike. %Alloc = Cash Reserve as a
    share of WHEEL capital (after the 30% vault); over the 5% cap shows red."""
    base = a.get("wcap") or 0
    groups = _alloc_groups(df, name.upper())
    cols = ["Stock", "Profit Loss", "% Alloc", "AOR", "Cash Reserved", "Current", "Qty", "Strike"]
    head = "".join(f"<div class='ck-fh{' ck-fhl' if i == 0 else ''}'>{c}</div>"
                   for i, c in enumerate(cols))

    def plcol(v):
        return P["green"] if v >= 0 else P["red"]

    def aor_cell(aor, tot=False):                       # AOR: ≥45 green · <30 orange · else ink
        extra = " ck-xtot" if tot else ""
        if aor is None:
            return f"<div class='ck-ac{extra}' style='color:{P['mut']}'>—</div>"
        col = P["green"] if aor >= 45 else P["orange"] if aor < 30 else P["ink"]
        return f"<div class='ck-ac{extra}' style='color:{col};font-weight:700'>{aor:.0f}%</div>"

    body = ""
    for it, stocks in groups:
        body += f"<div class='ck-xband'>{it}</div>"
        gpl = gcash = gqty = 0.0
        gaor_num = gaor_den = 0.0
        for s in stocks:
            p = (s["cash"] / base * 100) if base else 0
            # % Alloc color: <5% green · 5–7% with a single 1-lot amber (starter) · otherwise red
            if p < 5:
                acol = P["green"]
            elif p <= 7 and s["qty"] <= 1:
                acol = P["gold"]                         # yellow caution (amber reads coppery in Grey)
            else:
                acol = P["red"]
            gpl += s["pl"]; gcash += s["cash"]; gqty += s["qty"]
            if s.get("aor") is not None:
                gaor_num += s["aor"] * s["cash"]; gaor_den += s["cash"]
            body += (f"<div class='ck-fa'>{s['stock']}</div>"
                     f"<div class='ck-ac' style='color:{plcol(s['pl'])}'>{_m(s['pl'])}</div>"
                     f"<div class='ck-ac' style='color:{acol};font-weight:800'>{p:.1f}%</div>"
                     f"{aor_cell(s.get('aor'))}"
                     f"<div class='ck-ac'>{_m(s['cash'])}</div>"
                     f"<div class='ck-ac'>{s['price']:.2f}</div>"
                     f"<div class='ck-ac'>{s['qty']:.0f}</div>"
                     f"<div class='ck-ac'>{s['strike']:.2f}</div>")
        gp = (gcash / base * 100) if base else 0
        gaor = (gaor_num / gaor_den) if gaor_den else None
        body += (f"<div class='ck-fa ck-xtot'>{it.split('-')[-1]} Total</div>"
                 f"<div class='ck-ac ck-xtot' style='color:{plcol(gpl)}'>{_m(gpl)}</div>"
                 f"<div class='ck-ac ck-xtot' style='font-weight:800'>{gp:.1f}%</div>"
                 f"{aor_cell(gaor, tot=True)}"
                 f"<div class='ck-ac ck-xtot'>{_m(gcash)}</div>"
                 f"<div class='ck-ac ck-xtot'></div><div class='ck-ac ck-xtot'>{gqty:.0f}</div>"
                 f"<div class='ck-ac ck-xtot'></div>")
    inner = (head + body) if groups else "<div class='ck-fa'>No open positions.</div>"
    return (f"<div class='ck-card ck-fcard'>"
            f"{_btag(f'🧮 {name} ALLOCATION', '5% Wheel cap · 7% 1 lot', P)}"
            f"<div class='ck-xgw'><div class='ck-xgrid'>{inner}</div></div></div>")


def _combined_alloc_card(df, r, P: dict) -> str:
    """Combined exposure per stock ACROSS both accounts — cash reserve summed over IRA+LLC
    as a % of TOTAL wheel capital. The cap on the combined is a flat 5% (no 7% starter
    exception), so any name over 5% combined shows BOLD red. Just Stock · % Alloc."""
    tag = _btag("🔗 COMBINED BY STOCK", "5% Wheel cap · 7% 1 lot", P)
    if df is None or getattr(df, "empty", True):
        return ""
    base = (r["ira"].get("wcap") or 0) + (r["llc"].get("wcap") or 0)
    od = engine._openrows(df)
    if od.empty or "Stock" not in od.columns or "Cash Reserve" not in od.columns or base <= 0:
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub' style='margin-top:6px'>No data.</div></div>"
    d = od.copy()
    d["_stk"] = d["Stock"].astype(str).str.upper()
    d = d[~d["_stk"].isin(["", "NAN", "CASH", "VAULT"])]
    if d.empty:
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub' style='margin-top:6px'>No open positions.</div></div>"
    d["_cash"] = d["Cash Reserve"].map(engine._money)
    d["_qty"] = d["Qty"].map(engine._money) if "Qty" in d.columns else 0
    d["_pl"] = d["Profit Loss"].map(engine._money) if "Profit Loss" in d.columns else 0.0
    has_ret = "Return" in d.columns
    d["_aor"] = (d["Return"].map(lambda v: engine._money(str(v).replace("%", ""))) if has_ret else 0.0)
    d["_awt"] = d["_aor"] * d["_cash"]                  # collateral-weighted AOR numerator
    g = d.groupby("_stk").agg(_cash=("_cash", "sum"), _qty=("_qty", "sum"),
                              _pl=("_pl", "sum"), _awt=("_awt", "sum")).reset_index()
    g["pct"] = g["_cash"] / base * 100
    g = g.sort_values("pct", ascending=False)

    def aor_html(aor, tot=False):                       # ≥45 green · <30 orange · else ink
        cls = "ck-ca-p ck-ca-tot" if tot else "ck-ca-p"
        if aor is None or pd.isna(aor):
            return f"<div class='{cls}' style='color:{P['mut']}'>—</div>"
        col = P["green"] if aor >= 45 else P["orange"] if aor < 30 else P["ink"]
        return f"<div class='{cls}' style='color:{col};font-weight:700'>{aor:.0f}%</div>"

    head = ("<div class='ck-ca-s ck-ca-h'>Stock</div>"
            "<div class='ck-ca-p ck-ca-h'>P/L</div>"
            "<div class='ck-ca-p ck-ca-h'>Cash Res</div>"
            "<div class='ck-ca-p ck-ca-h'>Qty</div>"
            "<div class='ck-ca-p ck-ca-h'>% Alloc</div>"
            "<div class='ck-ca-p ck-ca-h'>AOR</div>")
    body = ""
    for _, row in g.iterrows():
        pc = row["pct"]
        # % Alloc color: <5% green · 5–7% with a single 1-lot amber (starter) · otherwise red
        if pc < 5:
            col, w = P["green"], "700"
        elif pc <= 7 and row["_qty"] <= 1:
            col, w = P["gold"], "700"                     # yellow caution (amber reads coppery in Grey)
        else:
            col, w = P["red"], "800"
        plc = P["green"] if row["_pl"] >= 0 else P["red"]
        waor = (row["_awt"] / row["_cash"]) if (has_ret and row["_cash"]) else None
        body += (f"<div class='ck-ca-s'>{row['_stk']}</div>"
                 f"<div class='ck-ca-p' style='color:{plc};font-weight:700'>{_m(row['_pl'])}</div>"
                 f"<div class='ck-ca-p'>{_m(row['_cash'])}</div>"
                 f"<div class='ck-ca-p ck-ca-mid'>{row['_qty']:.0f}</div>"
                 f"<div class='ck-ca-p' style='color:{col};font-weight:{w}'>{pc:.1f}%</div>"
                 f"{aor_html(waor)}")
    tcash, tqty, tpl = g["_cash"].sum(), g["_qty"].sum(), g["_pl"].sum()
    tot = tcash / base * 100
    taor = (g["_awt"].sum() / tcash) if (has_ret and tcash) else None
    tplc = P["green"] if tpl >= 0 else P["red"]
    body += (f"<div class='ck-ca-s ck-ca-tot'>Total</div>"
             f"<div class='ck-ca-p ck-ca-tot' style='color:{tplc}'>{_m(tpl)}</div>"
             f"<div class='ck-ca-p ck-ca-tot'>{_m(tcash)}</div>"
             f"<div class='ck-ca-p ck-ca-tot'>{tqty:.0f}</div>"
             f"<div class='ck-ca-p ck-ca-tot'>{tot:.1f}%</div>"
             f"{aor_html(taor, tot=True)}")
    return (f"<div class='ck-card ck-fcard'>{tag}"
            f"<div class='ck-caw'><div class='ck-ca-grid'>{head}{body}</div></div></div>")


def _assignment_card(df, c: dict, r: dict | None = None) -> str:
    """Assignment watch — the Trade Log, filtered to what's about to happen: ITM Puts (price
    below strike → will be ASSIGNED) and ITM Calls (price above strike → CALLED AWAY). Reuses
    command_center._tl_html so every column + the logos/colours match the Trade Log exactly.
    % Alloc = Cash Reserve as a share of that account's wheel capital — how much the position
    weighs on the CC Breaker if it converts."""
    if df is None or getattr(df, "empty", True):
        return ""
    P = ck.LIGHT if ck._is_light(c.get("bg", "")) else ck.DARK
    light = ck._is_light(c.get("bg", ""))
    od = engine._openrows(df).copy()
    if od.empty or "Opt Typ" not in od.columns:
        return ""
    wmap = {"IRA": ((r or {}).get("ira", {}).get("wcap") or 0),
            "LLC": ((r or {}).get("llc", {}).get("wcap") or 0)}
    cp = od["Current Price"].map(engine._money)
    k = od["Strike Price"].map(engine._money)
    typ = od["Opt Typ"].astype(str).str.upper()
    itm_put = (typ == "PUT") & (cp > 0) & (k > cp)          # price below strike → assigned
    itm_call = (typ == "CALL") & (cp > 0) & (cp > k)        # price above strike → called away

    def _alloc(row):                                        # Cash Reserve ÷ account wheel cap
        w = wmap.get(str(row.get("Account", "")).strip().upper(), 0)
        cr = engine._money(row.get("Cash Reserve"))
        return f"{cr / w * 100:.1f}%" if w else "—"

    def section(mask, title, color):
        sub = od[mask].copy()
        if sub.empty:
            return ""
        if "DTE" in sub.columns:
            sub = sub.assign(_d=sub["DTE"].map(engine._money)).sort_values("_d")
        sub["Logo"] = sub["Stock"].astype(str).str.strip().apply(
            lambda t: f"https://financialmodelingprep.com/image-stock/{t}.png" if t else "")
        sub["% Alloc"] = sub.apply(_alloc, axis=1)
        cols = []                                           # insert % Alloc right after Qty
        for col in ["Logo"] + [x for x in cc._TL_COLS if x in sub.columns]:
            cols.append(col)
            if col == "Qty":
                cols.append("% Alloc")
        if "% Alloc" not in cols:                           # fallback when Qty is absent
            cols.append("% Alloc")
        hdr = (f"<div style='background:{color}1f;color:{color};font-weight:800;font-size:13px;"
               f"padding:7px 11px;border-radius:7px;margin:12px 0 6px;letter-spacing:.04em;"
               f"display:inline-block'>{title} · {int(mask.sum())}</div>")
        return hdr + cc._tl_html(sub[cols], cols, c, light)

    body = (section(itm_put, "🔴 ITM Puts · will be assigned", "#f2555a")
            + section(itm_call, "🟠 ITM Calls · called away", "#e3a63a"))
    if not body:
        body = f"<div class='ck-sub' style='margin-top:6px'>No ITM puts or calls right now.</div>"
    return (f"<div class='ck-card ck-fcard'>"
            f"{_btag('📒 ASSIGNMENT WATCH', 'ITM puts → assigned · ITM calls → called away', P)}"
            f"{body}</div>")


def _week_expiry_card(df, c: dict) -> str:
    """This week's expiries — open PUT/CALL positions rolling off in the current calendar
    week (Mon–Sun). A quick bottom-of-Cockpit glance at what needs a decision by Friday.
    Reuses command_center._tl_html so columns / logos / colours match the Trade Log."""
    if df is None or getattr(df, "empty", True):
        return ""
    P = ck.LIGHT if ck._is_light(c.get("bg", "")) else ck.DARK
    light = ck._is_light(c.get("bg", ""))
    od = engine._openrows(df).copy()
    if od.empty or "Exp Date" not in od.columns:
        return ""
    today = _dt.date.today()
    wk_start = today - _dt.timedelta(days=today.weekday())        # Monday
    wk_end = wk_start + _dt.timedelta(days=6)                      # Sunday
    exp = pd.to_datetime(od["Exp Date"], errors="coerce").dt.date
    not_cash = ~od["Stock"].astype(str).str.upper().isin(["CASH", "VAULT"])
    sub = od[not_cash & exp.notna() & (exp >= wk_start) & (exp <= wk_end)].copy()
    if sub.empty:
        body = "<div class='ck-sub' style='margin-top:6px'>No positions expiring this week.</div>"
    else:
        if "DTE" in sub.columns:
            sub = sub.assign(_d=sub["DTE"].map(engine._money)).sort_values("_d")
        sub["Logo"] = sub["Stock"].astype(str).str.strip().apply(
            lambda t: f"https://financialmodelingprep.com/image-stock/{t}.png" if t else "")
        cols = ["Logo"] + [x for x in cc._TL_COLS if x in sub.columns]
        body = cc._tl_html(sub[cols], cols, c, light)
    return (f"<div class='ck-card ck-fcard'>"
            f"{_btag('📅 EXPIRING THIS WEEK', f'open puts/calls rolling off by {wk_end:%b %-d}', P)}"
            f"{body}</div>")


def _expiry_summary_card(df, name: str, c: dict) -> str:
    """Per-expiry rollup for ONE account — each expiry's Qty · P/L · Reserve · % Ret ·
    Release summed across its open rows, EXPANDABLE (native <details>, no JS) to the
    per-stock breakdown under that expiry, with a grand total. Mirrors the sheet's pivot;
    scrolls horizontally on narrow (iPhone) widths."""
    if df is None or getattr(df, "empty", True):
        return ""
    P = ck.LIGHT if ck._is_light(c.get("bg", "")) else ck.DARK
    tag = _btag(f"📆 {name} BY EXPIRY", "P/L · reserve · % ret · release · tap a row for stocks", P)
    od = engine._openrows(df).copy()
    need = ["Account", "Exp Date", "Profit Loss", "Cash Reserve", "Qty", "Stock"]
    if od.empty or any(cn not in od.columns for cn in need):
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub' style='margin-top:6px'>No data.</div></div>"
    d = od[od["Account"].astype(str).str.upper() == name.upper()].copy()
    if d.empty:
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub' style='margin-top:6px'>No open positions.</div></div>"
    has_rel = "Cash Release" in d.columns
    for raw, k in [("Profit Loss", "_pl"), ("Cash Reserve", "_res"), ("Qty", "_qty")]:
        d[k] = d[raw].map(engine._money)
    d["_rel"] = d["Cash Release"].map(engine._money) if has_rel else 0.0
    d["_exp"] = pd.to_datetime(d["Exp Date"], errors="coerce")
    d["_stk"] = d["Stock"].astype(str).str.upper()

    def nums(qty, pl, res, rel):
        ret = (pl / res * 100) if res else 0.0
        plc = P["green"] if pl >= 0 else P["red"]
        retc = P["green"] if ret >= 0 else P["red"]
        return (f"<div class='ck-exn ck-exmid'>{qty:.0f}</div>"
                f"<div class='ck-exn' style='color:{plc};font-weight:700'>{_m(pl)}</div>"
                f"<div class='ck-exn'>{_m(res)}</div>"
                f"<div class='ck-exn' style='color:{retc};font-weight:700'>{ret:.2f}%</div>"
                f"<div class='ck-exn' style='color:{P['gold']}'>{_m(rel)}</div>")

    groups = []
    for exp, sg in d.groupby("Exp Date", dropna=False):
        stocks = [dict(stk=stk, qty=ss["_qty"].sum(), pl=ss["_pl"].sum(),
                       res=ss["_res"].sum(), rel=ss["_rel"].sum())
                  for stk, ss in sg.groupby("_stk")]
        stocks.sort(key=lambda x: -x["res"])
        groups.append(dict(order=sg["_exp"].min(), raw=str(exp), qty=sg["_qty"].sum(),
                           pl=sg["_pl"].sum(), res=sg["_res"].sum(), rel=sg["_rel"].sum(),
                           stocks=stocks))
    groups.sort(key=lambda x: (pd.isna(x["order"]), x["order"]))

    head = ("<div class='ck-exr ck-exh'><div>Expiry</div><div class='ck-exn'>Qty</div>"
            "<div class='ck-exn'>P/L</div><div class='ck-exn'>Reserve</div>"
            "<div class='ck-exn'>% Ret</div><div class='ck-exn'>Release</div></div>")
    body = ""
    tpl = tres = trel = tqty = 0.0
    for g in groups:
        tpl += g["pl"]; tres += g["res"]; trel += g["rel"]; tqty += g["qty"]
        lbl = g["order"].strftime("%-m/%-d/%y") if pd.notna(g["order"]) else g["raw"]
        stk_rows = "".join(
            f"<div class='ck-exr ck-exstk'><div class='ck-exlbl'>{s['stk']}</div>"
            f"{nums(s['qty'], s['pl'], s['res'], s['rel'])}</div>" for s in g["stocks"])
        body += (f"<details class='ck-exg'><summary class='ck-exr ck-exsum'>"
                 f"<div class='ck-exlbl'>{lbl}</div>{nums(g['qty'], g['pl'], g['res'], g['rel'])}"
                 f"</summary>{stk_rows}</details>")
    tret = (tpl / tres * 100) if tres else 0.0
    tplc = P["green"] if tpl >= 0 else P["red"]
    total = (f"<div class='ck-exr ck-extot'><div class='ck-exlbl'>Total</div>"
             f"<div class='ck-exn'>{tqty:.0f}</div>"
             f"<div class='ck-exn' style='color:{tplc}'>{_m(tpl)}</div>"
             f"<div class='ck-exn'>{_m(tres)}</div>"
             f"<div class='ck-exn'>{tret:.2f}%</div>"
             f"<div class='ck-exn' style='color:{P['gold']}'>{_m(trel)}</div></div>")
    tbl = f"<div class='ck-exw'><div class='ck-ext'>{head}{body}{total}</div></div>"
    return f"<div class='ck-card ck-fcard'>{tag}{tbl}</div>"


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@st.cache_data(ttl=900, show_spinner=False)
def _index_monthly_pct() -> dict:
    """SPY & QQQ month-over-month % returns straight from Yahoo (month-end close vs the
    prior month-end). The sheet's SPY/QQQ cells are live GOOGLEFINANCE formulas that do
    NOT evaluate in the public CSV export the app reads, so we source the indexes directly.
    Returns {(year, month): {"SPY": pct, "QQQ": pct}}."""
    out: dict = {}
    for sym in ("SPY", "QQQ"):
        try:
            h = yahoo.get_history(sym, period="3y", interval="1d")
            if h is None or getattr(h, "empty", True) or "Close" not in h:
                continue
            m = h["Close"].resample("ME").last().dropna()   # month-end closes
            for ts, v in (m.pct_change() * 100).items():
                if v == v:                                   # skip the leading NaN
                    out.setdefault((ts.year, ts.month), {})[sym] = float(v)
        except Exception:
            continue
    return out


def _perf_grid(mdf, P: dict, year: int) -> str:
    """Performance for one year — IRA/LLC/SPY/QQQ rows, a FIXED Jan…Dec column set so both
    year cards align for easy comparison (months with no data show —)."""
    tag = _btag(f"📈 PERFORMANCE {year}", "Monthly Return · $ · vs Indexes", P)
    if mdf is None or getattr(mdf, "empty", True):
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub'>No performance data.</div></div>"
    recs = {rr["date"].month: rr for rr in mdf.to_dict("records") if rr["date"].year == year}
    if not recs:
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub'>No {year} data.</div></div>"

    def pc(end, start):
        if not start or not end:
            return None
        r = (float(end) / float(start) - 1) * 100
        return r if r == r else None                   # drop nan (missing SPY/QQQ fetch)

    def vals(rr, endk, startk, combined):
        if combined:                                   # Total row = IRA + LLC
            return ((rr.get("IRA") or 0) + (rr.get("LLC") or 0),
                    (rr.get("ira_start") or 0) + (rr.get("llc_start") or 0))
        return rr.get(endk), rr.get(startk)

    def cell(v, amt_s, cc, extra=""):
        if v is None:
            return f"<div class='ck-pcell {extra}'><span class='ck-pv' style='color:{P['mut']}'>—</span></div>"
        amt_html = f"<span class='ck-pa'>{amt_s}</span>" if amt_s else ""
        return (f"<div class='ck-pcell {extra}'><span class='ck-pv' style='color:{cc}'>{v:+.1f}%</span>"
                f"{amt_html}</div>")

    # name, color, endk, startk, combined, is_index (index rows show % only — no $ meaning)
    series = [("IRA", P["blue"], "IRA", "ira_start", False, False),
              ("LLC", P["purple"], "LLC", "llc_start", False, False),
              ("Total", P["ink"], None, None, True, False),
              ("SPY", P["mid"], "SPY", "spy_start", False, True),
              ("QQQ", P["mid"], "QQQ", "qqq_start", False, True)]
    cells = ("<div class='ck-fh ck-fhl'>Series</div>"
             + "".join(f"<div class='ck-fh'>{m}</div>" for m in reversed(_MONTHS))
             + "<div class='ck-fh ck-khf'>Total</div>")
    lm = max(recs)
    idx = _index_monthly_pct()                             # SPY/QQQ from Yahoo (sheet cells don't export)
    for name, col, endk, startk, combined, is_index in series:
        trow = "ck-prow-tot" if combined else ""
        cells += f"<div class='ck-fa {trow}' style='color:{col}'>{name}</div>"
        for mi in range(12, 0, -1):
            if is_index:                                   # SPY / QQQ — % only, from Yahoo
                v = idx.get((year, mi), {}).get(name)
                cc = P["green"] if (v or 0) >= 0 else P["red"]
                cells += cell(v, "", cc, trow)
                continue
            rr = recs.get(mi)
            if not rr:
                cells += cell(None, "", "", trow)
                continue
            e, s = vals(rr, endk, startk, combined)
            v = pc(e, s)
            cc = P["green"] if (v or 0) >= 0 else P["red"]
            ch = (e - s) if (e is not None and s is not None) else None
            amt = "" if (ch is None or ch != ch) else (f"+{ck._mk(ch)}" if ch >= 0 else ck._mk(ch))
            cells += cell(v, amt, cc, trow)
        # Year total — accounts: point-to-point (Jan start → latest end), $ change YTD.
        #              indexes: compound the year's monthly returns (no $).
        if is_index:
            factor, any_m = 1.0, False
            for mi in range(1, 13):
                mv = idx.get((year, mi), {}).get(name)
                if mv is not None:
                    factor *= 1 + mv / 100
                    any_m = True
            tv = (factor - 1) * 100 if any_m else None
            tc = P["green"] if (tv or 0) >= 0 else P["red"]
            cells += cell(tv, "", tc, f"ck-ptot {trow}")
        elif 1 in recs:
            _, bs = vals(recs[1], endk, startk, combined)
            ce, _ = vals(recs[lm], endk, startk, combined)
            tv = pc(ce, bs)
            tc = P["green"] if (tv or 0) >= 0 else P["red"]
            ch = (ce - bs) if (ce is not None and bs is not None) else None
            amt = "" if (ch is None or ch != ch) else (f"+{ck._mk(ch)}" if ch >= 0 else ck._mk(ch))
            cells += cell(tv, amt, tc, f"ck-ptot {trow}")
        else:
            cells += cell(None, "", "", f"ck-ptot {trow}")
    return (f"<div class='ck-card ck-fcard'>{tag}"
            f"<div class='ck-pgw'><div class='ck-pgrid' "
            f"style='grid-template-columns:auto repeat(12,minmax(40px,1fr)) minmax(54px,1fr)'>"
            f"{cells}</div></div></div>")


def _total_acct(I: dict, L: dict) -> dict:
    ks = ["cap", "wcap", "vtgt", "cih", "dep", "csp", "cc", "leap", "rtd", "brkgap", "leapgap", "itm", "ccotm"]
    T = {k: (I.get(k) or 0) + (L.get(k) or 0) for k in ks}
    w = T["wcap"] or 0
    T["ccbrk"] = ((T["cc"] + T["itm"]) / w) if w else 0.0
    T["cspitm"] = (T["itm"] / w) if w else 0.0
    return T


def _wheel_grid(r: dict, P: dict) -> str:
    """Wheel-capital breakdown — IRA/LLC/Total as rows, Capital…Ready-to-Deploy as columns ($ + %)."""
    accts = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", _total_acct(r["ira"], r["llc"]))]
    metrics = [("Capital", "wcap", "cap"), ("VIX Target", "vtgt", "wcap"),
               ("Cash in Hand", "cih", "wcap"), ("Deployed", "dep", "wcap"),
               ("CSP", "csp", "wcap"), ("CC", "cc", "wcap"),
               ("LEAP", "leap", "wcap"), ("Ready to Deploy", "rtd", "wcap")]
    cells = ("<div class='ck-fh ck-fhl'>Account</div>"
             + "".join(f"<div class='ck-fh'>{m[0]}</div>" for m in metrics))
    for name, a in accts:
        cells += f"<div class='ck-fa'>{name}</div>"
        for lbl, key, base in metrics:
            hi = key == "rtd"
            amt = a.get(key) or 0
            b = a.get(base) or 0
            pct = (amt / b * 100) if b else 0
            cells += (f"<div class='{'ck-wc-hi' if hi else 'ck-wc'}'>"
                      f"<span class='ck-wca'>{_m(amt)}</span>"
                      f"<span class='ck-wcp'>{pct:.1f}%</span></div>")
    return (f"<div class='ck-card ck-fcard'>{_btag('💰 WHEEL CAPITAL', '$ · % · IRA / LLC / Total', P)}"
            f"<div class='ck-wgrid'>{cells}</div></div>")


def _acct_card(name: str, a: dict, accent: str, P: dict) -> str:
    """One account column: the Wheel-capital breakdown + the Focus-matrix gates, $ + %."""
    wcap = a.get("wcap") or 1
    cap = a.get("cap") or wcap
    ink, mut, g = P["ink"], P["mut"], P["green"]

    def pc(v):
        return f"{(v or 0) / wcap * 100:.1f}%" if wcap else "—"

    ccb = (a.get("ccbrk") or 0) * 100
    bc = g if ccb < 30 else P["amber"] if ccb < 45 else P["red"]
    lg = a.get("leapgap", 0)
    rows = [
        ("Capital", _m(a.get("wcap")), ink, f"{wcap / cap * 100:.1f}%", mut),
        ("VIX Target", _m(a.get("vtgt")), ink, pc(a.get("vtgt")), mut),
        ("Cash in Hand", _m(a.get("cih")), ink, pc(a.get("cih")), mut),
        ("Deployed", _m(a.get("dep")), ink, pc(a.get("dep")), mut),
        ("CSP", _m(a.get("csp")), ink, pc(a.get("csp")), mut),
        ("CC", _m(a.get("cc")), ink, pc(a.get("cc")), mut),
        ("LEAP", _m(a.get("leap")), ink, pc(a.get("leap")), mut),
        ("SEP", None, None, None, None),
        ("Ready / CSP Gap", _m(a.get("rtd")), g, pc(a.get("rtd")), g),
        ("CC Breaker", f"{ccb:.1f}%", bc, "", mut),
        ("Breaker Gap", _m(a.get("brkgap")), g, "", mut),
        ("%CSP ITM", f"{(a.get('cspitm') or 0) * 100:.1f}%", ink, "", mut),
        ("LEAP Gap", _m(lg), g if lg >= 0 else P["red"], "", mut),
    ]
    cells = ""
    for lbl, val, vc, pct, pcc in rows:
        if val is None:
            cells += "<div class='ck-asep'></div>"
            continue
        cells += (f"<div class='ck-al'>{lbl}</div>"
                  f"<div class='ck-av' style='color:{vc}'>{val}</div>"
                  f"<div class='ck-ap' style='color:{pcc}'>{pct}</div>")
    badge = (f"<span class='ck-tag' style='color:{accent};background:{accent}22;"
             f"border:1px solid {accent}66'>{name}</span>")
    return (f"<div class='ck-card ck-acard'>"
            f"<div class='ck-chead'><div class='ck-acct'>{badge}"
            f"<span class='ck-sub'>capital · gates</span></div></div>"
            f"<div class='ck-agrid'>{cells}</div></div>")


def _extra_css(P: dict) -> str:
    return f"""<style>
.ck-temoji{{font-size:1.18em;line-height:1;vertical-align:-0.06em}}
.ck-idx{{display:flex;flex-direction:column;gap:3px;justify-content:center;padding-left:4px}}
.ck-ichip{{display:flex;align-items:baseline;gap:6px;line-height:1}}
.ck-il{{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:{P['mut']};font-weight:700;min-width:30px}}
.ck-iv{{font-size:14.5px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
.ck-ifut{{font-size:8px;font-weight:700;letter-spacing:.03em;color:{P['amber']};background:{P['amber']}22;padding:0 3px;border-radius:3px;margin-left:4px;vertical-align:1px}}
.ck-arow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;margin-bottom:14px;align-items:start}}
.ck-fcard{{padding:10px 15px 12px;margin-bottom:14px}}
.ck-fgrid{{display:grid;grid-template-columns:auto repeat(6,1fr);gap:1px;background:{P['line']};
  border:1px solid {P['line']};border-radius:8px;overflow:hidden;margin-top:8px}}
.ck-fh{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:{P['mid']};font-weight:700;
  line-height:1.1;text-align:center;padding:6px 8px;background:{P['plo']}}}
.ck-fhl{{text-align:left}}
.ck-fa{{font-weight:700;font-size:13.5px;line-height:1.1;padding:4px 11px;text-align:left;
  background:{P['plo']};color:{P['ink']}}}
.ck-fg{{text-align:center;padding:8px 8px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:700;font-size:12px;line-height:1.1;background:{P['green']}22;color:{P['green']}}}
.ck-fn{{text-align:center;padding:8px 8px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:700;font-size:12px;line-height:1.1;background:{P['phi']};color:{P['ink']}}}
.ck-fr{{text-align:center;padding:8px 8px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:700;font-size:12px;line-height:1.1;background:{P['red']}26;color:{P['red']}}}
.ck-wgrid{{display:grid;grid-template-columns:auto repeat(8,1fr);gap:1px;background:{P['line']};
  border:1px solid {P['line']};border-radius:8px;overflow:hidden;margin-top:8px}}
.ck-sgw{{overflow-x:auto;overflow-y:hidden;margin-top:8px;border:1px solid {P['line']};
  border-radius:8px;-webkit-overflow-scrolling:touch}}
.ck-sgrid{{display:grid;grid-template-columns:minmax(52px,auto) repeat(9,minmax(76px,1fr));gap:1px;
  background:{P['line']};min-width:100%}}
.ck-pgw{{overflow-x:auto;overflow-y:hidden;margin-top:8px;border:1px solid {P['line']};
  border-radius:8px;-webkit-overflow-scrolling:touch}}
.ck-pgrid{{display:grid;gap:1px;background:{P['line']};min-width:100%}}
.ck-pcell{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  padding:4px 3px;font-family:'IBM Plex Mono',ui-monospace,monospace;background:{P['phi']};
  line-height:1.1;white-space:nowrap}}
.ck-pv{{font-size:12.5px;font-weight:700;line-height:1.1}}
.ck-pa{{font-size:10px;font-weight:600;line-height:1;color:{P['subv']}}}
.ck-ptot{{background:{P['glow']}!important}}
.ck-ptot .ck-pv{{font-weight:800;font-size:13px}}
.ck-pcell.ck-prow-tot{{background:{P['plo']}}}
.ck-fa.ck-prow-tot{{font-weight:800}}
.ck-khf{{color:{P['ink']}!important;font-weight:800!important;
  background:linear-gradient(rgba(0,0,0,.07),rgba(0,0,0,.07)),{P['plo']}!important}}
.ck-kcell{{background:linear-gradient(rgba(0,0,0,.06),rgba(0,0,0,.06)),{P['phi']}!important}}
.ck-rbadge{{display:inline-flex;align-items:center;justify-content:center;padding:3px 12px;border-radius:7px;
  color:#0c1116;line-height:1.15}}
.ck-rbadge b{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13.5px;font-weight:800}}
.ck-rpct{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11px;font-weight:700;margin-top:2px}}
.ck-wc,.ck-wc-hi{{display:flex;flex-direction:column;align-items:center;gap:1px;padding:4px 6px;background:{P['phi']}}}
.ck-wc-hi{{background:{P['green']}22}}
.ck-wca{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;font-weight:500;color:{P['ink']};line-height:1.15}}
.ck-wcp{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11px;font-weight:600;color:{P['subv']};line-height:1.15}}
.ck-wc-hi .ck-wca,.ck-wc-hi .ck-wcp{{color:{P['green']}}}
.ck-acard{{padding:10px 15px 11px}}
.ck-agrid{{display:grid;grid-template-columns:1fr auto auto;column-gap:14px;margin-top:6px}}
.ck-al{{font-size:11.5px;font-weight:600;color:{P['ink']};line-height:1.1;padding:2.5px 0}}
.ck-av{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px;font-weight:700;
  text-align:right;line-height:1.1;padding:2.5px 0}}
.ck-ap{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11px;font-weight:600;
  text-align:right;line-height:1.1;padding:2.5px 0;min-width:44px}}
.ck-asep{{grid-column:1/-1;height:1px;background:{P['line']};margin:4px 0}}
@media (max-width:820px){{.ck-arow{{grid-template-columns:1fr}}}}
.ck-brow2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;align-items:start}}
.ck-salloc{{display:grid;grid-template-columns:auto 1fr 1fr;gap:1px;background:{P['line']};
  border:1px solid {P['line']};border-radius:8px;overflow:hidden;margin-top:8px}}
.ck-ac{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;font-weight:500;text-align:center;
  padding:5px 7px;background:{P['phi']};color:{P['ink']};line-height:1.15;white-space:nowrap}}
.ck-xgw{{overflow-x:auto;overflow-y:hidden;margin-top:8px;border:1px solid {P['line']};
  border-radius:8px;-webkit-overflow-scrolling:touch}}
.ck-xgrid{{display:grid;gap:1px;background:{P['line']};min-width:100%;
  grid-template-columns:minmax(56px,auto) auto auto auto minmax(64px,1.4fr) auto auto auto}}
.ck-xband{{grid-column:1/-1;background:{P['plo']};color:{P['mid']};font-weight:800;font-size:11px;
  letter-spacing:.06em;text-transform:uppercase;padding:5px 11px;line-height:1.1}}
.ck-xtot{{background:{P['glow']}!important;font-weight:800!important}}
.ck-xgrid .ck-fa{{padding:5px 8px;font-size:13.5px;white-space:nowrap}}
.ck-xgrid .ck-fh{{padding:5px 4px;white-space:nowrap}}
.ck-xgrid.ck-itmgrid{{grid-template-columns:minmax(44px,1.1fr) 0.7fr 0.7fr 0.9fr 0.9fr 0.55fr 1.3fr 0.8fr 1fr 0.9fr}}
.ck-mpct{{color:{P['mut']}!important;font-weight:600!important}}
.ck-exw{{overflow-x:auto;overflow-y:hidden;margin-top:8px;border:1px solid {P['line']};
  border-radius:8px;-webkit-overflow-scrolling:touch}}
.ck-ext{{min-width:100%;font-size:12px;font-variant-numeric:tabular-nums}}
.ck-exr{{display:grid;grid-template-columns:minmax(98px,1fr) 44px 82px 96px 64px 88px;
  align-items:center;border-bottom:1px solid {P['line']}}}
.ck-exr>div{{padding:5px 8px;white-space:nowrap}}
.ck-exn{{text-align:right;color:{P['ink']}}}
.ck-exmid{{color:{P['mid']}!important}}
.ck-exh>div{{font-size:10px;text-transform:uppercase;letter-spacing:.03em;color:{P['mut']};font-weight:700}}
.ck-exg{{border:0}}
.ck-exsum{{cursor:pointer;list-style:none;background:{P['phi']}}}
.ck-exsum::-webkit-details-marker{{display:none}}
.ck-exsum .ck-exlbl{{font-weight:700;color:{P['ink']}}}
.ck-exsum .ck-exlbl::before{{content:'▸';display:inline-block;width:11px;color:{P['mut']};font-size:9px;margin-right:3px}}
details[open]>.ck-exsum .ck-exlbl::before{{content:'▾'}}
.ck-exstk{{background:{P['plo']}}}
.ck-exstk .ck-exlbl{{padding-left:24px;color:{P['mid']};font-size:11.5px}}
.ck-extot{{background:{P['glow']};font-weight:800;border-bottom:0}}
.ck-extot .ck-exlbl{{color:{P['ink']}}}
.ck-bcard .ck-chead,.ck-brkcard .ck-chead{{margin-bottom:2px}}
@media (max-width:820px){{.ck-brow2{{grid-template-columns:1fr}}}}
.ck-brow3{{display:grid;grid-template-columns:1.15fr 1fr .9fr;gap:12px;margin-bottom:14px;align-items:start}}
@media (max-width:820px){{.ck-brow3{{grid-template-columns:1fr}}}}
.ck-caw{{overflow-x:auto;overflow-y:hidden;margin-top:8px;border:1px solid {P['line']};
  border-radius:8px;-webkit-overflow-scrolling:touch}}
.ck-ca-grid{{display:grid;grid-template-columns:minmax(52px,1fr) auto auto auto auto auto;gap:1px;
  background:{P['line']};min-width:100%}}
.ck-ca-s{{padding:4px 10px;background:{P['phi']};font-weight:700;font-size:13px;color:{P['ink']};white-space:nowrap}}
.ck-ca-p{{padding:4px 10px;background:{P['phi']};font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:13px;text-align:right;white-space:nowrap}}
.ck-ca-h{{font-size:10px!important;text-transform:uppercase;letter-spacing:.03em;
  color:{P['mut']}!important;font-weight:700!important;font-family:inherit!important}}
.ck-ca-mid{{color:{P['mid']}}}
.ck-ca-tot{{background:{P['glow']}!important;font-weight:800!important;color:{P['ink']}}}
.ck-brow{{display:grid;grid-template-columns:1.5fr 1.55fr 1.35fr;gap:11px;margin-bottom:14px;align-items:stretch}}
.ck-bgrow2{{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:4px;align-items:end}}
.ck-gm .ck-gz{{font-size:12px}}
.ck-gm .ck-gz span{{font-size:11px!important;font-weight:600!important;color:{P['subv']}!important;font-family:'IBM Plex Sans',system-ui,sans-serif!important}}
.ck-seg{{color:#0c1116!important}}
.ck-sd{{opacity:1!important;color:#0c1116!important}}
.ck-goalcard,.ck-brkcard{{padding:7px 14px 7px}}
.ck-grow{{padding:9px 0 7px}}
.ck-grow + .ck-grow{{border-top:1px solid {P['lsoft']}}}
.ck-pcard2{{padding:11px 13px 12px;display:flex;flex-direction:column}}
.ck-p2head{{display:flex;justify-content:space-between;align-items:flex-start;gap:6px}}
.ck-p2label{{font-size:9.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:{P['mid']}}}
.ck-p2icon{{width:26px;height:26px;flex:none;border-radius:8px;display:flex;align-items:center;
  justify-content:center;font-size:13px;background:{P['gold']}1e;border:1px solid {P['gold']}44}}
.ck-p2val{{margin-top:5px;font-family:'IBM Plex Mono',monospace;font-size:19px;font-weight:700;color:{P['gold']}}}
.ck-p2val span{{color:{P['subv']};font-size:12.5px;font-weight:600}}
.ck-p2rate{{display:flex;justify-content:flex-end;align-items:baseline;margin-top:auto;padding-top:8px;
  font-family:'IBM Plex Mono',monospace;font-size:10.5px;font-weight:700}}
.ck-p2track{{height:7px;border-radius:6px;background:{P['track']};border:1px solid {P['lsoft']};
  overflow:hidden;margin-top:4px}}
.ck-p2fill{{height:100%;border-radius:6px;background:linear-gradient(90deg,#e8893a,{P['gold']},{P['green']})}}
.ck-bgrow{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:4px;align-items:end}}
.ck-bg{{display:flex;flex-direction:column;align-items:center;gap:0}}
.ck-bglabel{{font-size:10px;font-weight:700;letter-spacing:.05em;color:{P['mid']};margin-bottom:0}}
.ck-brkcard .ck-bg svg{{max-width:120px!important}}
.ck-brkcard .ck-gv{{font-size:16px;margin-top:-2px;line-height:1.1;font-weight:700}}
.ck-brkcard .ck-gz{{font-size:11px;font-weight:700;margin-top:2px;line-height:1.1;
  font-family:'IBM Plex Mono',ui-monospace,monospace}}
.ck-brkcard .ck-gz span{{color:{P['mut']};font-weight:600;font-size:8px;font-family:'IBM Plex Sans',system-ui,sans-serif}}
.ck-brkcard .ck-bglabel{{line-height:1.1}}
@media (max-width:820px){{.ck-brow{{grid-template-columns:1fr}}}}
.ck-bcard{{padding:7px 14px 7px;margin-bottom:14px}}
.ck-mgrid{{display:grid;grid-template-columns:auto 1fr 1fr 1fr;column-gap:14px;margin-top:6px}}
.ck-mh{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:{P['mut']};font-weight:700;
  line-height:1.1;text-align:right;padding:1px 0 4px;border-bottom:1px solid {P['line']}}}
.ck-mhl{{text-align:left}}
.ck-ml{{font-size:13.5px;font-weight:600;line-height:1.1;color:{P['ink']};padding:1.5px 0;
  border-bottom:1px solid {P['lsoft']}}}
.ck-mv{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:14px;font-weight:500;line-height:1.1;
  color:{P['ink']};text-align:right;padding:1.5px 0;border-bottom:1px solid {P['lsoft']}}}
.ck-mgrid > :nth-last-child(-n+4){{border-bottom:none}}
.ck-athrow{{color:#37b24d!important;font-weight:700!important}}
.ck-athup{{font-size:9px;font-weight:600;color:#37b24d;opacity:.85}}
.ck-athtrophy{{display:inline-block;animation:ck-athpulse 2.6s ease-in-out infinite}}
@keyframes ck-athpulse{{0%,78%,100%{{transform:scale(1);opacity:1}}
  84%{{transform:scale(1.45);opacity:.6}}90%{{transform:scale(1);opacity:1}}}}
@media (prefers-reduced-motion:reduce){{.ck-athtrophy{{animation:none}}}}
@media (prefers-reduced-motion:reduce){{.ck-athflash{{animation:none}}}}
.ck-btbl{{width:100%;border-collapse:collapse;margin-top:5px}}
.ck-btbl th{{font-size:9px!important;text-transform:uppercase;letter-spacing:.05em;color:{P['mut']};
  line-height:1.2!important;font-weight:700;text-align:right;padding:2px 10px 3px!important;
  border-bottom:1px solid {P['line']};white-space:nowrap}}
.ck-btbl th:first-child{{text-align:left}}
.ck-btbl td{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px!important;font-weight:700;
  line-height:1.2!important;text-align:right;padding:2.5px 10px!important;border-bottom:1px solid {P['lsoft']};
  white-space:nowrap;color:{P['ink']}}}
.ck-btbl tbody tr:last-child td{{border-bottom:none}}
.ck-btl{{text-align:left!important;color:{P['ink']}!important;
  font-family:'IBM Plex Sans',system-ui,sans-serif!important;font-weight:600!important}}
.ck-wamt{{font-size:13.5px;font-weight:700}}
.ck-wpct{{font-size:10.5px;font-weight:600;margin-top:1px}}
.ck-wrtd td{{background:{P['green']}14}}
.ck-mtot td{{border-top:1px solid {P['line']};font-weight:800}}
@media (max-width:640px){{.ck-btbl th,.ck-btbl td{{padding:5px 7px;font-size:11.5px}}}}
</style>"""


def _index_chips(P: dict) -> str:
    """SPY & QQQ chips for the VIX strip — the ETF's live % during cash hours,
    the index future (ES=F / NQ=F) % when the market is closed (marked ·fut)."""
    q = yahoo.index_quotes()
    if not q:
        return ""
    chips = ""
    for lbl in ("SPY", "QQQ"):
        d = q.get(lbl)
        if not d:
            continue
        chg = d.get("chg") or 0
        col = P["green"] if chg >= 0 else P["red"]
        tag = "<span class='ck-ifut'>fut</span>" if d.get("fut") else ""
        chips += (f"<div class='ck-ichip'><span class='ck-il'>{lbl}{tag}</span>"
                  f"<span class='ck-iv' style='color:{col}'>{chg * 100:+.2f}%</span></div>")
    return f"<div class='ck-idx'>{chips}</div>" if chips else ""


def _leap_alert(df, P: dict) -> str:
    """Top-of-Cockpit alert when any open LEAP is in the GREEN. The flip doctrine exits a
    LEAP at +10–15% (no time stop), so a profitable LEAP is a decision: ≥10% = exit zone,
    0–10% = watch. % gain = P/L ÷ cost (Cash Reserve holds the LEAP debit). Only green LEAPs
    show; if every LEAP is red the banner is hidden entirely."""
    od = engine._openrows(df)
    if od is None or getattr(od, "empty", True) or "Invest Type" not in od.columns:
        return ""
    if "Profit Loss" not in od.columns or "Cash Reserve" not in od.columns:
        return ""
    d = od[od["Invest Type"].astype(str).str.upper().str.contains("LEAP", na=False)].copy()
    if d.empty:
        return ""
    d["_pl"] = d["Profit Loss"].map(engine._money)
    d["_cost"] = d["Cash Reserve"].map(engine._money)
    g = (d.groupby([d["Stock"].astype(str).str.upper(), d["Account"].astype(str).str.upper()])
         .agg(pl=("_pl", "sum"), cost=("_cost", "sum")).reset_index())
    g.columns = ["stock", "acct", "pl", "cost"]
    g = g[g["pl"] >= 0]                                   # only LEAPs in the green
    if g.empty:
        return ""
    g = g.sort_values("pl", ascending=False)
    chips, exitzone = "", False
    for _, row in g.iterrows():
        pct = (row["pl"] / row["cost"] * 100) if row["cost"] else 0
        hot = pct >= 10                                  # flip doctrine exit band +10–15%
        exitzone = exitzone or hot
        col = P["green"] if hot else P["amber"]
        state = "EXIT ZONE" if hot else "watch"
        chips += (f"<span style='display:inline-flex;align-items:center;gap:7px;background:{col}22;"
                  f"border:1px solid {col}66;border-radius:7px;padding:3px 10px;margin:2px 7px 2px 0;"
                  f"font-size:12px;font-weight:700;color:{P['ink']}'>"
                  f"{row['stock']} <span style='color:{P['mut']};font-weight:600'>{row['acct']}</span> "
                  f"<span style='color:{col}'>{_m(row['pl'])} (+{pct:.1f}%)</span>"
                  f"<span style='color:{col};font-size:9px;text-transform:uppercase;letter-spacing:.04em'>"
                  f"{state}</span></span>")
    accent = P["green"] if exitzone else P["amber"]
    msg = ("exit zone — flip doctrine sells +10–15%, GTC-walk the exit"
           if exitzone else "green — watch for the +10–15% exit")
    return (f"<div class='ck-card' style='border-left:4px solid {accent};padding:9px 14px;margin-bottom:10px'>"
            f"<div style='font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:{P['mut']};"
            f"font-weight:800;margin-bottom:6px'>🚀 LEAP in profit · {msg}</div>{chips}</div>")


def render(c: dict) -> None:
    data = cc.board_data()
    if data is None:
        st.warning("Couldn't load the TradeLog tab.")
        return
    r, vix, vix_chg, trend = data["r"], data["vix"], data["vix_chg"], data["trend"]
    tdf = data.get("df")
    P = ck.LIGHT if ck._is_light(c.get("bg", "")) else ck.DARK
    # Actual cash in hand (free cash + vault) as % of capital — for the VIX marker's status badge.
    _capT = sum((a.get("cap") or 0) for a in (r["ira"], r["llc"]))
    _freeT = sum((a.get("cih") or 0) + (a.get("vault") or 0) for a in (r["ira"], r["llc"]))
    cash_pct = (_freeT / _capT * 100) if _capT else None
    try:
        mdf, _ = benchmark.monthly_df()
    except Exception:
        mdf = None
    _pd = _prem_dict(r.get("premium", []), ck._month_earned())
    _yrs = sorted(set(mdf["date"].dt.year), reverse=True) if (mdf is not None and not getattr(mdf, "empty", True)) else []
    _perf = "".join(_perf_grid(mdf, P, y) for y in _yrs)
    _perf_ytd_d = _perf_ytd(mdf, _dt.date.today().year)       # IRA/LLC YTD on the Performance basis
    # YEARLY goal bar: GOAL = 1.5% of ATH per month → annual target; EARNED = actual YTD gain
    # from the Performance tab (IRA+LLC, Jan → current month). Monthly/Weekly stay premium-based.
    _ath_tot = (r["ira"].get("ath") or 0) + (r["llc"].get("ath") or 0)
    if _ath_tot > 0 and _perf_ytd_d.get("ira") and _perf_ytd_d.get("llc"):
        _pd["yr_goal"] = _ath_tot * 0.015 * 12
        _park = (data.get("ext") or {}).get("park_llc") or 0        # match THIS YEAR Wheel Total (+ park)
        _pd["yr_earned"] = ((_perf_ytd_d["ira"][1] + _perf_ytd_d["llc"][1])
                            - (_perf_ytd_d["ira"][0] + _perf_ytd_d["llc"][0]) + _park)

    band = r.get("band", 2)
    bdef = engine.BANDS[band] if 0 <= band < len(engine.BANDS) else engine.BANDS[2]
    up = str(trend).lower().startswith("up")
    dmin, dmax = (bdef[1] if up else bdef[3]) * 100, (bdef[2] if up else bdef[4]) * 100
    band_lbl = bdef[0]
    chg_col = P["red"] if vix_chg > 0 else P["green"]
    idx_block = _index_chips(P)
    fg = yahoo.fear_greed()
    cols = ["auto"]                                         # VIX now
    if idx_block:
        cols.append("auto")                                # SPY / QQQ chips
    fg_block = ""
    if fg:
        s = fg["score"]
        fgc = (P["red"] if s < 25 else P["amber"] if s < 45 else P["gold"] if s < 55
               else "#7cc47d" if s < 75 else P["green"])
        fg_block = ck._fg_gauge(s, fg["rating"], fgc, P)
        cols.append("auto")                                # Fear & Greed gauge
    cols += ["1fr", "auto"]                                # meter · regime
    vcols = " ".join(cols)
    tc = P["green"] if up else P["red"]
    trend_badge = (f"<span class='ck-trend' style='color:{tc};background:{tc}22;border:1px solid {tc}55'>"
                   f"{'↑' if up else '↓'} {trend}</span>")

    html = f"""{ck._css(P)}{_extra_css(P)}
    <div class="ck-wrap">
      <div class="ck-panel ck-vix" style="grid-template-columns:{vcols}">
        <div class="ck-vixnow"><span class="l">VIX</span><span class="vv">{vix:.2f}</span>
          <span class="ck-chg" style="color:{chg_col};background:{chg_col}22;border:1px solid {chg_col}55">
          {vix_chg * 100:+.1f}%</span></div>
        {idx_block}
        {fg_block}
        <div class="ck-meter">{ck._vix_meter(vix, band, up, cash_pct, P)}</div>
        <div class="ck-regime">
          <div class="ck-tl-row"><span class="ck-tl">Target</span>
            <span class="ck-target">{dmin:.0f}–{dmax:.0f}%</span></div>
          <div style="margin-top:4px">{trend_badge}</div>
        </div>
      </div>
      {_leap_alert(tdf, P)}
      <div class="ck-brow">
        {_money_card(r, P)}
        {_breaker_card(r, P)}
        {_goalbar_card(_pd, P)}
      </div>
      {_summary_grid(r, P)}
      {_perf}
      {_assignment_card(tdf, c, r)}
      {_week_expiry_card(tdf, c)}
      {_ytd_card(r, data.get("ext"), P, _perf_ytd_d)}
      <div class="ck-brow3">
        {_alloc_card(tdf, 'IRA', r['ira'], P)}
        {_alloc_card(tdf, 'LLC', r['llc'], P)}
        {_combined_alloc_card(tdf, r, P)}
      </div>
      <div class="ck-brow2">
        {_expiry_summary_card(tdf, 'LLC', c)}
        {_expiry_summary_card(tdf, 'IRA', c)}
      </div>
    </div>"""
    html = "\n".join(line.lstrip() for line in html.splitlines())
    st.markdown(html, unsafe_allow_html=True)
