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
            f"<span class='ck-tag' style='color:{P['ink']};background:{P['steel']}33;"
            f"border:1px solid {P['steel']}88'>{icon_label}</span>"
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


def _breaker_card(r: dict, P: dict) -> str:
    """CC Breaker — all three gauges (IRA · LLC · Total), the exact Cockpit semicircle."""
    def one(name, a):
        brk = (a.get("ccbrk") or 0) * 100
        zc = P["green"] if brk < 30 else P["amber"] if brk < 45 else P["red"]
        gap = a.get("brkgap", 0)                            # $ headroom to the 45% cap
        return (f"<div class='ck-bg'><div class='ck-bglabel'>{name}</div>"
                f"{ck._gauge(brk, P, 'b' + name)}"
                f"<div class='ck-gv'>{brk:.1f}%</div>"
                f"<div class='ck-gz' style='color:{zc}'>{_m(gap)} <span>gap</span></div></div>")
    accts = [("IRA", r["ira"]), ("LLC", r["llc"]), ("Total", r["total"])]
    return (f"<div class='ck-card ck-brkcard'>{_btag('🚦 CC BREAKER', 'Cap 45% · Safe &lt; 30%', P)}"
            f"<div class='ck-bgrow'>{''.join(one(n, a) for n, a in accts)}</div></div>")


def _money_card(r: dict, P: dict) -> str:
    """Money — Capital · All Time High · Cash Vault (30% ATH), IRA/LLC with $ and %."""
    accts = [("IRA", r["ira"]), ("LLC", r["llc"])]
    rows_def = [("Capital", "cap"), ("All Time High", "ath"), ("Cash Vault · 30% ATH", "vault")]
    cells = ("<div class='ck-mh ck-mhl'>Money</div>"
             + "".join(f"<div class='ck-mh'>{n}</div>" for n, _ in accts))
    for lbl, key in rows_def:
        cells += f"<div class='ck-ml'>{lbl}</div>"
        for _, a in accts:
            val = _m(a.get(key) or 0)
            # At a new all-time high when the account value has caught up to the ATH ratchet.
            if key == "ath" and abs((a.get("cap") or 0) - (a.get("ath") or 0)) < 1:
                cells += f"<div class='ck-mv ck-athflash'>🏆 {val}</div>"
            else:
                cells += f"<div class='ck-mv'>{val}</div>"
    return (f"<div class='ck-card ck-bcard'>{_btag('💰 MONEY', 'Capital · ATH · Vault', P)}"
            f"<div class='ck-mgrid'>{cells}</div></div>")


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
            if k == "ready":                               # green/red badge, black text (bright in both themes)
                bg = "#43c463" if amt >= 0 else "#f2555a"
                cells += (f"<div class='ck-wc ck-kcell'><span class='ck-rbadge' style='background:{bg}'>"
                          f"<b>{_m(amt)}</b><em>{pct:.1f}%</em></span></div>")
                continue
            cls = "ck-wc ck-kcell" if isk else "ck-wc"
            cells += (f"<div class='{cls}'><span class='ck-wca'>{_m(amt)}</span>"
                      f"<span class='ck-wcp'>{pct:.1f}%</span></div>")
    return (f"<div class='ck-card ck-fcard'>{_btag('📊 WHEEL SUMMARY', 'Capital · Deploy · Ready · Cash · CSP ITM · Positions', P)}"
            f"<div class='ck-sgrid'>{cells}</div></div>")


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


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _perf_grid(mdf, P: dict, year: int) -> str:
    """Performance for one year — IRA/LLC/SPY/QQQ rows, a FIXED Jan…Dec column set so both
    year cards align for easy comparison (months with no data show —)."""
    tag = _btag(f"📈 PERFORMANCE {year}", "Monthly Return · vs Indexes", P)
    if mdf is None or getattr(mdf, "empty", True):
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub'>No performance data.</div></div>"
    recs = {rr["date"].month: rr for rr in mdf.to_dict("records") if rr["date"].year == year}
    if not recs:
        return f"<div class='ck-card ck-fcard'>{tag}<div class='ck-sub'>No {year} data.</div></div>"

    def pc(end, start):
        return (float(end) / float(start) - 1) * 100 if (start and end) else None

    series = [("IRA", P["blue"], "IRA", "ira_start"), ("LLC", P["purple"], "LLC", "llc_start"),
              ("SPY", P["mid"], "SPY", "spy_start"), ("QQQ", P["mid"], "QQQ", "qqq_start")]
    cells = ("<div class='ck-fh ck-fhl'>Series</div>"
             + "".join(f"<div class='ck-fh'>{m}</div>" for m in reversed(_MONTHS))
             + "<div class='ck-fh ck-khf'>Total</div>")
    for name, col, endk, startk in series:
        cells += f"<div class='ck-fa' style='color:{col}'>{name}</div>"
        for mi in range(12, 0, -1):
            rr = recs.get(mi)
            v = pc(rr.get(endk), rr.get(startk)) if rr else None
            if v is None:
                cells += f"<div class='ck-pcell' style='color:{P['mut']}'>—</div>"
            else:
                cc = P["green"] if v >= 0 else P["red"]
                cells += f"<div class='ck-pcell' style='color:{cc}'>{v:+.1f}%</div>"
        # Year total = point-to-point (Jan start → latest month end), matching the sheet header.
        base = recs[1].get(startk) if 1 in recs else None
        lm = max(recs) if recs else None
        cur = recs[lm].get(endk) if lm else None
        tv = (float(cur) / float(base) - 1) * 100 if (base and cur) else None
        if tv is None:
            cells += f"<div class='ck-pcell ck-ptot' style='color:{P['mut']}'>—</div>"
        else:
            tc = P["green"] if tv >= 0 else P["red"]
            cells += f"<div class='ck-pcell ck-ptot' style='color:{tc}'>{tv:+.1f}%</div>"
    return (f"<div class='ck-card ck-fcard'>{tag}"
            f"<div class='ck-pgw'><div class='ck-pgrid' "
            f"style='grid-template-columns:auto repeat(12,minmax(50px,1fr)) minmax(66px,1.1fr)'>"
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
.ck-arow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;margin-bottom:14px;align-items:start}}
.ck-fcard{{padding:10px 15px 12px;margin-bottom:14px}}
.ck-fgrid{{display:grid;grid-template-columns:auto repeat(6,1fr);gap:1px;background:{P['line']};
  border:1px solid {P['line']};border-radius:8px;overflow:hidden;margin-top:8px}}
.ck-fh{{font-size:9.5px;text-transform:uppercase;letter-spacing:.04em;color:{P['mid']};font-weight:700;
  line-height:1.1;text-align:center;padding:6px 8px;background:{P['plo']}}}
.ck-fhl{{text-align:left}}
.ck-fa{{font-weight:700;font-size:12px;line-height:1.1;padding:8px 11px;text-align:left;
  background:{P['plo']};color:{P['ink']}}}
.ck-fg{{text-align:center;padding:8px 8px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:700;font-size:12px;line-height:1.1;background:{P['green']}22;color:{P['green']}}}
.ck-fn{{text-align:center;padding:8px 8px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:700;font-size:12px;line-height:1.1;background:{P['phi']};color:{P['ink']}}}
.ck-fr{{text-align:center;padding:8px 8px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:700;font-size:12px;line-height:1.1;background:{P['red']}26;color:{P['red']}}}
.ck-wgrid{{display:grid;grid-template-columns:auto repeat(8,1fr);gap:1px;background:{P['line']};
  border:1px solid {P['line']};border-radius:8px;overflow:hidden;margin-top:8px}}
.ck-sgrid{{display:grid;grid-template-columns:auto repeat(9,1fr);gap:1px;background:{P['line']};
  border:1px solid {P['line']};border-radius:8px;overflow:hidden;margin-top:8px}}
.ck-pgw{{overflow-x:auto;margin-top:8px}}
.ck-pgrid{{display:grid;gap:1px;background:{P['line']};border:1px solid {P['line']};
  border-radius:8px;overflow:hidden;min-width:100%}}
.ck-pcell{{text-align:center;padding:5px 6px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-weight:600;font-size:11px;background:{P['phi']};line-height:1.1;white-space:nowrap}}
.ck-ptot{{background:{P['glow']}!important;font-weight:800!important;font-size:11.5px}}
.ck-khf{{color:{P['ink']}!important;font-weight:800!important;
  background:linear-gradient(rgba(0,0,0,.07),rgba(0,0,0,.07)),{P['plo']}!important}}
.ck-kcell{{background:linear-gradient(rgba(0,0,0,.06),rgba(0,0,0,.06)),{P['phi']}!important}}
.ck-rbadge{{display:inline-flex;flex-direction:column;align-items:center;padding:3px 12px;border-radius:7px;
  color:#0c1116;line-height:1.15}}
.ck-rbadge b{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px;font-weight:800}}
.ck-rbadge em{{font-style:normal;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:9.5px;font-weight:700;opacity:.85}}
.ck-wc,.ck-wc-hi{{display:flex;flex-direction:column;align-items:center;gap:1px;padding:7px 6px;background:{P['phi']}}}
.ck-wc-hi{{background:{P['green']}22}}
.ck-wca{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11.5px;font-weight:500;color:{P['ink']};line-height:1.15}}
.ck-wcp{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:9.5px;font-weight:600;color:{P['subv']};line-height:1.15}}
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
.ck-mpct{{color:{P['mut']}!important;font-weight:600!important}}
.ck-bcard .ck-chead,.ck-brkcard .ck-chead{{margin-bottom:2px}}
@media (max-width:820px){{.ck-brow2{{grid-template-columns:1fr}}}}
.ck-brow{{display:grid;grid-template-columns:1.5fr 1.7fr 0.8fr 0.8fr;gap:11px;margin-bottom:14px;align-items:stretch}}
.ck-seg{{color:#0c1116!important}}
.ck-sd{{opacity:1!important;color:#0c1116!important}}
.ck-goalcard,.ck-brkcard{{padding:10px 14px 10px}}
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
.ck-brkcard .ck-gv{{font-size:16px;margin-top:-14px;line-height:1.1;font-weight:700}}
.ck-brkcard .ck-gz{{font-size:11px;font-weight:700;margin-top:2px;line-height:1.1;
  font-family:'IBM Plex Mono',ui-monospace,monospace}}
.ck-brkcard .ck-gz span{{color:{P['mut']};font-weight:600;font-size:8px;font-family:'IBM Plex Sans',system-ui,sans-serif}}
.ck-brkcard .ck-bglabel{{line-height:1.1}}
@media (max-width:820px){{.ck-brow{{grid-template-columns:1fr}}}}
.ck-bcard{{padding:9px 14px 9px;margin-bottom:14px}}
.ck-mgrid{{display:grid;grid-template-columns:1fr auto auto;column-gap:20px;margin-top:6px}}
.ck-mh{{font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:{P['mut']};font-weight:700;
  line-height:1.1;text-align:right;padding:1px 0 4px;border-bottom:1px solid {P['line']}}}
.ck-mhl{{text-align:left}}
.ck-ml{{font-size:12px;font-weight:600;line-height:1.1;color:{P['ink']};padding:2.5px 0;
  border-bottom:1px solid {P['lsoft']}}}
.ck-mv{{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;font-weight:500;line-height:1.1;
  color:{P['ink']};text-align:right;padding:2.5px 0;border-bottom:1px solid {P['lsoft']}}}
.ck-mgrid > :nth-last-child(-n+3){{border-bottom:none}}
.ck-athflash{{color:#37b24d!important;font-weight:700!important;animation:ck-athpulse 2.6s ease-in-out infinite}}
@keyframes ck-athpulse{{
  0%,78%,100%{{text-shadow:0 0 0 transparent}}
  84%{{text-shadow:0 0 13px rgba(67,196,99,.95),0 0 4px rgba(67,196,99,.9)}}
  90%{{text-shadow:0 0 0 transparent}}}}
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
    _pd = _prem_dict(r.get("premium", []), ck._month_earned())
    _yrs = sorted(set(mdf["date"].dt.year), reverse=True) if (mdf is not None and not getattr(mdf, "empty", True)) else []
    _perf = "".join(_perf_grid(mdf, P, y) for y in _yrs)

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
      <div class="ck-brow">
        {_money_card(r, P)}
        {_breaker_card(r, P)}
        {_period_card('Weekly', _pd.get('wk_earned', 0), _pd.get('wk_goal', 0), P)}
        {_period_card('Monthly', _pd.get('mo_earned', 0), _pd.get('mo_goal', 0), P)}
      </div>
      {_summary_grid(r, P)}
      {_perf}
    </div>"""
    html = "\n".join(line.lstrip() for line in html.splitlines())
    st.markdown(html, unsafe_allow_html=True)
