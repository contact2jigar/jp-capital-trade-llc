"""🎛️ Cockpit — a control-room re-imagining of the Monitor Board.

Same live numbers as the Command Center (via command_center.board_data), rendered
as instrument panels: a VIX regime meter with the deploy-target range, per-account
allocation rings + CC-breaker gauges, and premium bars. Theme-aware (dark + grey),
server-side HTML/SVG (no JS), large type for easy reading."""

from __future__ import annotations

import math

import streamlit as st

from logic import monitor as engine
from services import yahoo
from ui import benchmark
from ui.pages import command_center as cc

# VIX bands: label + segment color (bright in either theme, so dark text on them).
BANDS = [("8–13", "#ef4444"), ("13–15", "#f97316"), ("15–20", "#f5c518"),
         ("20–25", "#84cc16"), ("25–30", "#34c759"), ("30–100", "#16a34a")]
EDGES = [8, 13, 15, 20, 25, 30, 100]

# ── two palettes; data-hues shift darker on the light skin for contrast ──────
DARK = dict(
    bg="#0a0e13", glow="#12202e", phi="#18222e", plo="#0f161e", line="#26333f", lsoft="#1b242f",
    ink="#e9eff5", mid="#aebac7", mut="#6f7d8c", subv="#9aa7b4", steel="#3a4757",
    hole1="#151d27", hole2="#0e141c", track="#0c131b", hi="rgba(255,255,255,.045)",
    gold="#e3b23c", blue="#58a6ff", purple="#a78bfa", green="#43c463", amber="#e3a63a", red="#f2555a",
    orange="#f97316",
    shadow="0 22px 46px -28px rgba(0,0,0,.85)")
LIGHT = dict(
    bg="#eef1f3", glow="#dce7f2", phi="#ffffff", plo="#f2f5f7", line="#c7ced3", lsoft="#dde2e6",
    ink="#16212c", mid="#38454f", mut="#66727d", subv="#5c6873", steel="#9aa7b4",
    hole1="#ffffff", hole2="#eef1f3", track="#e4e8eb", hi="rgba(255,255,255,.7)",
    gold="#b8860b", blue="#2f6fb0", purple="#6b3fa0", green="#2f7e25", amber="#8a6800", red="#b62027",
    orange="#ea580c",
    shadow="0 18px 40px -26px rgba(23,33,44,.35)")


def _is_light(bg: str) -> bool:
    h = str(bg).lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def _m(v) -> str:
    v = float(v or 0)
    return ("−$" + f"{-v:,.0f}") if v < 0 else ("$" + f"{v:,.0f}")


def _mk(v) -> str:
    """Compact dollars for tight one-line rows: 253137 → $253K, 4960 → $5K, 1.6e6 → $1.60M."""
    v = float(v or 0)
    a, s = abs(v), ("−" if v < 0 else "")
    if a >= 1e6:
        return f"{s}${a / 1e6:.2f}M"
    if a >= 1e3:
        return f"{s}${a / 1e3:.0f}K"
    return f"{s}${a:.0f}"


def _pct(part, whole) -> float:
    return (float(part) / float(whole) * 100.0) if whole else 0.0


# (brand mark now comes from ui.brand.gearframe)


# ── semicircle CC-breaker gauge: 45% cap = full deflection (the freeze redline) ─
def _gauge(v: float, P: dict, uid: str = "") -> str:
    cx, cy, r, S = 90, 86, 70, 45.0     # full arc = the 45% breaker cap

    def pol(deg):
        a = math.radians(deg)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    def arc(v1, v2, col):
        x1, y1 = pol(180 - v1 / S * 180)
        x2, y2 = pol(180 - v2 / S * 180)
        return (f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" '
                f'fill="none" stroke="{col}" stroke-width="12" stroke-linecap="round"/>')

    # Zones against the 45% cap: green 0–20, yellow 20–30, orange 30–40, red 40–45.
    gz, yz, oz, rz = "#43c463", "#f2c436", "#f08a24", "#f2555a"

    def lbl(val, col=None):                          # boundary number just outside the arc
        a = math.radians(180 - val / S * 180)
        lx, ly = cx + (r + 9) * math.cos(a), cy - (r + 9) * math.sin(a)
        return (f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="9.5" fill="{col or P['ink']}" '
                f'font-weight="800" text-anchor="middle" dominant-baseline="middle">{val}</text>')
    # 0 (start) + band boundaries + 45 (the cap, in red — the line a crash crosses).
    ticks = lbl(0) + lbl(20) + lbl(30) + lbl(40) + lbl(45, rz)
    by = cy - 8                                     # raised, shorter needle so it clears the % below
    over = v > S                                     # breached the 45% cap (crash)
    ndl = rz if over else P['ink']                   # needle goes red when over the cap
    ang = math.radians(180 - min(v, S) / S * 180)    # needle stops short; arrowhead reaches the band
    nx, ny = cx + 46 * math.cos(ang), by - 46 * math.sin(ang)
    mid = f"ccbrktip{uid}"
    # When breached, a red ">>" sits just past the 45 end — the needle is pinned, so this shows
    # it has run OFF the scale.
    ox, oy = pol(-9)
    overmark = (f'<text x="{ox + 2:.1f}" y="{oy - 10:.1f}" font-size="12" fill="{rz}" '
                f'font-weight="900" text-anchor="middle">»</text>') if over else ""
    return f"""<svg viewBox="0 0 180 94" width="100%" style="max-width:172px" aria-label="CC breaker {v:.1f}% of 45% cap">
      <defs><marker id="{mid}" markerUnits="userSpaceOnUse" markerWidth="15" markerHeight="15" refX="3" refY="7.5" orient="auto"><path d="M0,0 L15,7.5 L0,15 Z" fill="{ndl}"/></marker></defs>
      {arc(0, 19, gz)}{arc(20, 29, yz)}{arc(30, 39, oz)}{arc(40, 45, rz)}{ticks}{overmark}
      <line x1="{cx}" y1="{by}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{ndl}" stroke-width="2.5" stroke-linecap="round" marker-end="url(#{mid})"/>
      <circle cx="{cx}" cy="{by}" r="4" fill="{ndl}"/>
      <circle cx="{cx}" cy="{by}" r="7" fill="none" stroke="{P['line']}" stroke-width="1.5"/>
    </svg>"""


def _fg_gauge(v: float, rating: str, col: str, P: dict) -> str:
    """Compact 0–100 Fear & Greed dial: red → green band with a needle at the score.
    The colored arc is what reads at a glance even at this size; score/label sit below."""
    cx, cy, r, S = 60, 56, 46, 100.0

    def pol(deg):
        a = math.radians(deg)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    def arc(v1, v2, c):
        x1, y1 = pol(180 - v1 / S * 180)
        x2, y2 = pol(180 - v2 / S * 180)
        return (f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" '
                f'fill="none" stroke="{c}" stroke-width="11" stroke-linecap="round"/>')

    # Extreme Fear · Fear · Neutral · Greed · Extreme Greed
    ef, fe, ne, gr, eg = "#f2555a", "#e8893a", "#e6b93e", "#7cc47d", "#43c463"
    ang = math.radians(180 - min(max(v, 0), S) / S * 180)   # needle stops short; arrowhead reaches the band
    nx, ny = cx + 34 * math.cos(ang), cy - 34 * math.sin(ang)
    svg = (f'<svg viewBox="0 0 120 64" width="100%" style="max-width:112px" '
           f'aria-label="Fear and Greed {v:.0f} of 100">'
           f'<defs><marker id="fgtip" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" '
           f'refX="2.5" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="{P["ink"]}"/></marker></defs>'
           f'{arc(0, 22, ef)}{arc(25, 44, fe)}{arc(46, 54, ne)}{arc(56, 74, gr)}{arc(76, 100, eg)}'
           f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{P["ink"]}" '
           f'stroke-width="2.5" stroke-linecap="round" marker-end="url(#fgtip)"/>'
           f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="{P["ink"]}"/></svg>')
    return (f'<div class="ck-fgm">{svg}'
            f'<div class="ck-fgl" style="color:{col}">F&amp;G <b>{v:.0f}</b> · {rating}</div></div>')


def _combined(I: dict, L: dict) -> dict:
    """IRA + LLC summed into one dict shaped for _card: dollar fields added, ratios re-derived
    on the combined wheel capital (matches the board's wcap-weighted total)."""
    def s(k):
        return (I.get(k) or 0) + (L.get(k) or 0)
    wcap = s("wcap")
    return dict(cap=s("cap"), ath=s("ath"), wcap=wcap, dep=s("dep"), cc=s("cc"),
                csp=s("csp"), leap=s("leap"), itm=s("itm"), rtd=s("rtd"), cih=s("cih"),
                cspitm=(s("itm") / wcap if wcap else 0.0),
                ccbrk=((s("cc") + s("itm")) / wcap if wcap else 0.0))


def _perf(mdf, P: dict) -> str:
    """Compact performance summary — last 5 months, IRA/LLC returns next to SPY/QQQ.
    A quick 'how am I doing vs the indexes' glance; the full detail lives on Performance."""
    tag = (f"<div class='ck-chead'><div class='ck-acct'>"
           f"<span class='ck-tag' style='color:{P['steel']};background:{P['steel']}22;"
           f"border:1px solid {P['steel']}66'>PERFORMANCE</span>"
           f"<span class='ck-sub'>monthly · vs indexes</span></div></div>")
    if mdf is None or getattr(mdf, "empty", True):
        return f"<div class='ck-card ck-perf'>{tag}<div class='ck-sub'>No performance data.</div></div>"

    def pc(end, start):
        return (float(end) / float(start) - 1) * 100 if (start and end) else None

    def cell(v):
        if v is None:
            return f"<td style='color:{P['mut']}'>—</td>"
        return f"<td style='color:{P['green'] if v >= 0 else P['red']}'>{v:+.1f}%</td>"

    rows = ""
    for _, rr in mdf.sort_values("date", ascending=False).iterrows():   # all months (scrolls)
        mo = rr["date"].strftime("%b '%y")
        rows += (f"<tr><td class='ck-pfmo'>{mo}</td>"
                 f"{cell(pc(rr['IRA'], rr['ira_start']))}{cell(pc(rr['LLC'], rr['llc_start']))}"
                 f"{cell(pc(rr['SPY'], rr['spy_start']))}{cell(pc(rr['QQQ'], rr['qqq_start']))}</tr>")
    head = (f"<tr><th>Month</th><th style='color:{P['blue']}'>IRA</th>"
            f"<th style='color:{P['purple']}'>LLC</th><th>SPY</th><th>QQQ</th></tr>")
    return (f"<div class='ck-card ck-perf'>{tag}"
            f"<div class='ck-ptwrap'><table class='ck-ptbl'>"
            f"<thead>{head}</thead><tbody>{rows}</tbody></table></div></div>")


def _card(name: str, cls_col: str, d: dict, P: dict) -> str:
    wcap = d.get("wcap") or 0
    csp, ccp = _pct(d.get("csp"), wcap), _pct(d.get("cc"), wcap)
    leap, dep = _pct(d.get("leap"), wcap), _pct(d.get("dep"), wcap)
    cash = max(0.0, 100 - dep)
    rtd, rtdp = d.get("rtd", 0), _pct(d.get("rtd"), wcap)
    itm = float(d.get("cspitm", 0)) * 100          # % of CSP collateral in-the-money
    brk = float(d.get("ccbrk", 0)) * 100
    zc = P["green"] if brk < 30 else P["amber"] if brk < 45 else P["red"]
    ztx = "Safe · below 30%" if brk < 30 else "Caution · elite only" if brk < 45 else "Frozen · CSPs halted"
    ring = (f"conic-gradient({P['blue']} 0 {csp:.2f}%,{P['gold']} {csp:.2f}% {csp + ccp:.2f}%,"
            f"{P['purple']} {csp + ccp:.2f}% {csp + ccp + leap:.2f}%,"
            f"{P['steel']} {csp + ccp + leap:.2f}% 100%)")

    def li(color, lbl, pct, amt):
        return (f"<div class='ck-li'><span class='ck-dot' style='background:{color}'></span>"
                f"<span class='ck-ll'>{lbl}</span>"
                f"<span class='ck-lv'><b>{pct:.1f}%</b><em>{_m(amt)}</em></span></div>")

    return f"""
    <div class="ck-card">
      <div class="ck-chead">
        <div class="ck-acct"><span class="ck-tag" style="color:{cls_col};
             background:{cls_col}22;border:1px solid {cls_col}66">{name}</span>
          <span class="ck-sub">Wheel capital</span></div>
        <div style="text-align:right"><div class="ck-ath">Account {_m(d.get('cap'))}</div>
          <div class="ck-ath">ATH {_m(d.get('ath'))}</div></div>
      </div>
      <div class="ck-cap">{_m(wcap)}</div>
      <div class="ck-inst">
        <div class="ck-ringwrap">
          <div class="ck-ring" style="background:{ring}">
            <div class="ck-rmid"><b>{itm:.1f}%</b><span>CSP ITM</span></div></div>
          <div class="ck-legend">
            {li(P['steel'], 'Cash', cash, d.get('cih'))}{li(P['blue'], 'CSP', csp, d.get('csp'))}
            {li(P['gold'], 'CC', ccp, d.get('cc'))}{li(P['purple'], 'LEAP', leap, d.get('leap'))}
          </div>
        </div>
        <div class="ck-gauge">{_gauge(brk, P, name)}
          <div class="ck-gv">{brk:.1f}%</div>
          <div class="ck-gl">CC Breaker · cap 45%</div>
          <div class="ck-gz" style="color:{zc}">{ztx}</div>
        </div>
      </div>
      <div class="ck-ready">
        <span class="ck-rl">Ready to deploy</span>
        <span><span class="ck-rv">{_m(rtd)}</span><span class="ck-rp">{rtdp:.1f}%</span></span>
      </div>
    </div>"""


def _vix_meter(vix: float, band: int, up: bool, cash_pct: float | None = None, P: dict | None = None) -> str:
    """The VIX strip. The floating marker is the cash-to-HOLD target for the current VIX
    (interpolated within the band). When cash_pct (actual cash in hand, % of capital) + P are
    passed, the marker becomes a status badge: green if actual ≥ target (covered), gold if
    within 5pts under, red if well under — so 'am I holding enough cash for this VIX?' reads
    at a glance."""
    i = max(0, min(band, 5))
    frac = 0.5
    if EDGES[i + 1] > EDGES[i]:
        frac = min(1.0, max(0.0, (vix - EDGES[i]) / (EDGES[i + 1] - EDGES[i])))
    left = (i + frac) / 6 * 100
    segs = ""
    for k, (lbl, col) in enumerate(BANDS):
        b = engine.BANDS[k]
        lo, hi = (b[1], b[2]) if up else (b[3], b[4])
        segs += (f"<div class='ck-seg{'' if k == i else ' ck-dim'}' style='background:{col}'>"
                 f"<span class='ck-sr'>{lbl}</span>"
                 f"<span class='ck-sd'>{lo * 100:.0f}–{hi * 100:.0f}%</span></div>")
    tgt = engine.allocation(vix, "Uptrend" if up else "Downtrend") * 100   # live interpolated cash % target
    # Split the label across the needle (no pill): the colored % on the LEFT, 'CASH 💵' on the
    # RIGHT. Only the % number carries the status color.
    bcol = P["ink"] if P else None
    if cash_pct is not None and P is not None:
        bcol = (P["green"] if cash_pct >= tgt else P["gold"] if cash_pct >= tgt - 5 else P["red"])
    numclr = f"color:{bcol};" if bcol else ""
    base = "background:transparent;border:none;padding:0;"
    num = (f"<div class='ck-npct' style='left:{left:.1f}%;{base}transform:translateX(calc(-100% - 7px))'>"
           f"<span style='font-weight:800;{numclr}'>{tgt:.0f}%</span></div>")
    lab = (f"<div class='ck-npct' style='left:{left:.1f}%;{base}transform:translateX(7px)'>"
           f"<span style='font-size:8px;font-weight:700;letter-spacing:.03em;opacity:.6'>CASH</span> 💵</div>")
    return (f"<div class='ck-segs'>{segs}</div>"
            f"<div class='ck-needle' style='left:{left:.1f}%'></div>"
            f"{num}{lab}")


def _month_earned() -> float | None:
    """Current month's earned premium from the P/L (Open Date) month table — premium is
    earned when a CSP/CC is opened, so we group by open date. The MonitorBoard's own
    monthly-premium figure is unreliable, so we read it from the P/L page's source."""
    try:
        from datetime import date
        tot = engine.monthly_totals(engine.pl_rollup(cc._tradelog(), "Open Date"))
        if tot.empty:
            return None
        today = date.today()
        row = tot[(tot["Year"] == today.year) & (tot["Month"] == today.strftime("%b"))]
        # A fresh month with no opens yet earns $0 — do NOT fall back to the prior month
        # (that made Oct 1 read September's premium, ~111% of goal on day one).
        return float(row["P/L"].iloc[0]) if not row.empty else 0.0
    except Exception:
        return None


def _premium(prem: list, P: dict, mo_earned: float | None = None) -> str:
    d = {}
    for lbl, val in prem or []:
        s = str(lbl).lower()
        per = "wk" if ("wk" in s or "week" in s) else "mo"
        kind = "goal" if "goal" in s else "earned" if "earn" in s else "gap" if "gap" in s else None
        if kind:
            d[f"{per}_{kind}"] = float(val or 0)

    if mo_earned is not None:
        d["mo_earned"] = mo_earned                          # from the P/L month table

    def card(per, title):
        goal = d.get(f"{per}_goal", 0) or 1
        earned = d.get(f"{per}_earned", 0)
        rate = earned / goal * 100                          # true run rate (can exceed 100)
        w = max(0.0, min(100.0, rate))                       # bar width, capped
        gap = goal - earned
        # Horizontal meter zones: blue while ramping (0–50) → yellow on track (50–90) → green
        # near/at goal (90–100). The % text takes the zone color the pointer sits in.
        pc = P["green"] if rate >= 90 else "#facc15" if rate >= 50 else "#3b82f6"
        rcol = pc
        gaptxt = (f"Beat goal by · {_m(-gap)}" if gap < 0 else f"Gap to goal · {_m(gap)}")
        gcol = P["green"] if gap < 0 else P["amber"]
        return (f"<div class='ck-pcard'>"
                f"<div class='ck-phead'>"
                f"<span class='ck-plabel'>💰 {title} earned premium</span>"
                f"<span class='ck-pval'><b style='color:{pc}'>{_m(earned)}</b> "
                f"<span>/ {_m(goal)}</span></span></div>"
                f"<div class='ck-pbot'><span class='ck-pgaptxt' style='color:{gcol}'>{gaptxt}</span>"
                f"<div class='ck-pbar'><div class='ck-pband'></div>"
                f"<div class='ck-pneedle' style='left:{w:.1f}%'></div></div>"
                f"<span class='ck-prpct' style='color:{rcol}'>{rate:.0f}%</span></div></div>")

    return f"<div class='ck-prow'>{card('wk', 'Weekly')}{card('mo', 'Monthly')}</div>"


def _css(P: dict) -> str:
    return f"""<style>
.ck-wrap{{font-family:'IBM Plex Sans',system-ui,sans-serif;color:{P['ink']};
  background:radial-gradient(1000px 420px at 72% -12%,{P['glow']} 0%,transparent 60%),transparent;
  padding:4px 0 8px;margin-top:2px}}
.ck-cap,.ck-vv,.ck-ath,.ck-rv,.ck-gv,.ck-v,.ck-rp,.ck-seg,.ck-tag,.ck-target,.ck-lv b,.ck-lv em,.ck-gap,.ck-rmid b{{
  font-family:'IBM Plex Mono',ui-monospace,monospace}}
.ck-top{{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:18px}}
.ck-brand{{display:flex;align-items:center;gap:14px}}
.ck-brand h2{{margin:0;font-size:21px;font-weight:700;letter-spacing:-.01em}}
.ck-brand h2 .g{{color:{P['gold']}}}
.ck-brand p{{margin:3px 0 0;font-size:11.5px;color:{P['mut']};letter-spacing:.15em;text-transform:uppercase}}
.ck-chip{{font-size:11px;color:{P['mut']};border:1px dashed {P['line']};border-radius:999px;padding:5px 12px;
  letter-spacing:.08em;text-transform:uppercase}}
.ck-panel,.ck-card,.ck-pcard{{border:1px solid {P['line']};border-radius:16px;
  background:linear-gradient(155deg,{P['phi']},{P['plo']});
  box-shadow:inset 0 1px 0 {P['hi']},{P['shadow']}}}
.ck-vix{{padding:9px 20px;margin-bottom:11px;display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center}}
.ck-vixnow{{display:flex;align-items:baseline;gap:9px}}
.ck-vixnow .l{{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:{P['mut']}}}
.ck-vixnow .vv{{font-size:26px;font-weight:600;letter-spacing:-.02em}}
.ck-chg{{font-size:13px;font-weight:600;padding:3px 9px;border-radius:6px}}
.ck-fgm{{display:flex;flex-direction:column;align-items:center;justify-self:center}}
.ck-fgl{{font-size:10.5px;font-weight:600;letter-spacing:.02em;white-space:nowrap;margin-top:-5px}}
.ck-fgl b{{font-family:'IBM Plex Mono',monospace;font-weight:700}}
.ck-meter{{position:relative}}
.ck-segs{{display:flex;height:38px;border-radius:9px;overflow:hidden;border:1px solid {P['line']}}}
.ck-seg{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  color:#12181f;line-height:1.1}}
.ck-seg.ck-dim{{opacity:.85}}
.ck-sr{{font-size:12.5px;font-weight:700;white-space:nowrap}}
.ck-sd{{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;opacity:.82;white-space:nowrap}}
.ck-seg:not(.ck-dim) .ck-sd{{opacity:1}}
.ck-needle{{position:absolute;top:-7px;bottom:-7px;width:2.5px;background:{P['ink']};border-radius:2px;
  box-shadow:0 0 0 1px {P['bg']}}}
.ck-needle::before{{content:"";position:absolute;top:-5px;left:50%;transform:translateX(-50%);
  border:5px solid transparent;border-top-color:{P['ink']}}}
.ck-npct{{position:absolute;top:-19px;transform:translateX(-50%);
  font-size:12px;font-weight:800;color:{P['ink']};background:{P['bg']};
  padding:0 5px;border-radius:5px;white-space:nowrap;line-height:1.4;z-index:4}}
.ck-regime{{text-align:right;white-space:nowrap}}
.ck-tl-row{{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-bottom:1px}}
.ck-trend{{font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  padding:3px 9px;border-radius:999px;white-space:nowrap}}
.ck-tl{{font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;color:{P['mut']}}}
.ck-target{{font-size:22px;font-weight:600;color:{P['gold']};line-height:1.05;margin:1px 0}}
.ck-regime .s{{font-size:12.5px;color:{P['mut']};margin-top:2px}}
.ck-cards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.ck-totalwrap{{margin-bottom:16px}}
.ck-totalwrap .ck-card{{border-color:{P['steel']}66}}
.ck-card{{padding:20px}}
.ck-chead{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}
.ck-acct{{display:flex;align-items:center;gap:10px}}
.ck-tag{{font-weight:700;font-size:13px;letter-spacing:.06em;padding:3px 10px;border-radius:7px;white-space:nowrap}}
.ck-sub{{font-size:13px;color:{P['mut']}}}
.ck-ath{{font-size:13.5px;color:{P['mid']};margin-top:3px}}
.ck-cap{{font-size:29px;font-weight:600;letter-spacing:-.02em}}
.ck-inst{{display:grid;grid-template-columns:1.18fr 0.82fr;gap:14px;align-items:center;margin:10px 0 16px}}
.ck-ringwrap{{display:flex;align-items:center;gap:14px}}
.ck-ring{{width:120px;height:120px;border-radius:50%;flex:none;position:relative;
  box-shadow:0 10px 26px -14px rgba(0,0,0,.5),inset 0 0 0 1px {P['hi']}}}
.ck-ring::after{{content:"";position:absolute;inset:16px;border-radius:50%;
  background:radial-gradient(circle at 50% 35%,{P['hole1']},{P['hole2']});border:1px solid {P['lsoft']}}}
.ck-rmid{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:1}}
.ck-rmid b{{font-size:21px;font-weight:600;line-height:1}}
.ck-rmid span{{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:{P['mut']};margin-top:3px}}
.ck-legend{{display:flex;flex-direction:column;gap:10px;flex:1;min-width:0}}
.ck-li{{display:flex;align-items:center;gap:8px;color:{P['mid']}}}
.ck-dot{{width:11px;height:11px;border-radius:3px;flex:none}}
.ck-ll{{font-size:13.5px;font-weight:600;min-width:38px}}
.ck-lv{{margin-left:auto;display:flex;align-items:baseline;gap:8px}}
.ck-lv b{{color:{P['ink']};font-weight:700;font-size:15px}}
.ck-lv em{{font-style:normal;color:{P['subv']};font-size:12.5px;min-width:66px;text-align:right}}
.ck-gauge{{display:flex;flex-direction:column;align-items:center;gap:2px;padding-left:22px}}
.ck-gv{{font-size:23px;font-weight:600;margin-top:-28px}}
.ck-gl{{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:{P['mut']};margin-top:5px;white-space:nowrap}}
.ck-gz{{font-size:12.5px;font-weight:600;margin-top:3px}}
.ck-ready{{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-radius:11px;
  background:{P['green']}1e;border:1px solid {P['green']}55}}
.ck-rl{{font-size:12.5px;letter-spacing:.09em;text-transform:uppercase;color:{P['green']};font-weight:600}}
.ck-rv{{font-size:21px;font-weight:700;color:{P['green']}}}
.ck-rp{{font-size:13.5px;color:{P['green']};margin-left:8px}}
.ck-prow{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.ck-sumrow{{align-items:start}}                     /* COMBINED + PERF size to their own content */
.ck-ptwrap{{max-height:285px;overflow-y:auto;margin-top:8px}}
.ck-ptbl{{width:100%;border-collapse:collapse}}
.ck-ptbl th{{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:{P['mut']};
  font-weight:700;text-align:right;padding:4px 12px;border-bottom:1px solid {P['line']};
  position:sticky;top:0;background:{P['phi']};z-index:1;white-space:nowrap}}
.ck-ptbl th:first-child{{text-align:left}}
.ck-ptbl td{{font-family:'IBM Plex Mono',monospace;font-size:12.5px;font-weight:700;text-align:right;
  padding:2.5px 12px;border-bottom:1px solid {P['lsoft']};white-space:nowrap}}
.ck-ptbl tr:last-child td{{border-bottom:none}}
.ck-pfmo{{text-align:left!important;color:{P['ink']};font-family:'IBM Plex Sans',system-ui,sans-serif}}
.ck-pcard{{padding:11px 20px 12px}}
.ck-phead{{display:flex;justify-content:space-between;align-items:baseline;gap:12px}}
.ck-plabel{{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:{P['mut']};white-space:nowrap}}
.ck-pval{{font-family:'IBM Plex Mono',monospace;font-size:20px;font-weight:700;color:{P['gold']};white-space:nowrap}}
.ck-pval span{{color:{P['subv']};font-size:14px;font-weight:600}}
.ck-prpct{{font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:700;white-space:nowrap}}
.ck-pbot{{display:flex;align-items:center;gap:12px;margin-top:9px}}
.ck-pgaptxt{{font-family:'IBM Plex Mono',monospace;font-size:12px;white-space:nowrap}}
.ck-pbar{{flex:1;position:relative;height:18px;display:flex;align-items:center}}
.ck-pband{{width:100%;height:15px;border-radius:999px;border:1px solid {P['lsoft']};
  box-shadow:inset 0 1px 3px rgba(0,0,0,.28),inset 0 -1px 0 rgba(255,255,255,.2);
  background:linear-gradient(90deg,#3b82f6 0 50%,#facc15 50% 90%,{P['green']} 90% 100%)}}
.ck-pneedle{{position:absolute;top:-3px;bottom:-3px;width:3px;border-radius:3px;background:{P['ink']};
  transform:translateX(-50%);box-shadow:0 0 0 2px {P['bg']},0 1px 4px rgba(0,0,0,.45)}}
.ck-pneedle::before{{content:"";position:absolute;top:-7px;left:50%;transform:translateX(-50%);
  border:5px solid transparent;border-top-color:{P['ink']}}}
@media (max-width:820px){{.ck-vix,.ck-cards,.ck-prow,.ck-inst{{grid-template-columns:1fr!important}}
  .ck-regime{{text-align:left}}.ck-tl-row{{justify-content:flex-start}}.ck-fgm{{align-items:flex-start}}}}
@media (max-width:520px){{.ck-segs{{height:50px}}.ck-sr{{font-size:11px}}.ck-sd{{font-size:9px}}
  .ck-cap{{font-size:26px}}.ck-target{{font-size:24px}}}}
</style>"""


def render(c: dict) -> None:
    data = cc.board_data()
    if data is None:
        st.warning("Couldn't load the TradeLog tab.")
        return
    r, vix, vix_chg, trend = data["r"], data["vix"], data["vix_chg"], data["trend"]
    P = LIGHT if _is_light(c.get("bg", "")) else DARK
    try:
        _mdf, _ = benchmark.monthly_df()               # monthly returns for the Performance summary
    except Exception:
        _mdf = None
    band = r.get("band", 2)
    bdef = engine.BANDS[band] if 0 <= band < len(engine.BANDS) else engine.BANDS[2]
    up = str(trend).lower().startswith("up")
    dmin, dmax = (bdef[1] if up else bdef[3]) * 100, (bdef[2] if up else bdef[4]) * 100
    band_lbl = bdef[0]
    chg_col = P["red"] if vix_chg > 0 else P["green"]
    fg = yahoo.fear_greed()                                # CNN Fear & Greed (None if unavailable)
    fg_block, vcols = "", "auto 1fr auto"
    if fg:
        s = fg["score"]
        fgc = (P["red"] if s < 25 else P["amber"] if s < 45 else P["gold"] if s < 55
               else "#7cc47d" if s < 75 else P["green"])
        fg_block = _fg_gauge(s, fg["rating"], fgc, P)
        vcols = "auto auto 1fr auto"                        # add a column for the F&G dial

    tc = P["green"] if up else P["red"]                    # trend badge — green up / red down
    trend_badge = (f"<span class='ck-trend' style='color:{tc};background:{tc}22;border:1px solid {tc}55'>"
                   f"{'↑' if up else '↓'} {trend}</span>")

    html = f"""{_css(P)}
    <div class="ck-wrap">
      <div class="ck-panel ck-vix" style="grid-template-columns:{vcols}">
        <div class="ck-vixnow"><span class="l">VIX</span><span class="vv">{vix:.2f}</span>
          <span class="ck-chg" style="color:{chg_col};background:{chg_col}22;border:1px solid {chg_col}55">
          {vix_chg * 100:+.1f}%</span></div>
        {fg_block}
        <div class="ck-meter">{_vix_meter(vix, band, up)}</div>
        <div class="ck-regime">
          <div class="ck-tl-row"><span class="ck-tl">Target</span>{trend_badge}</div>
          <div class="ck-target">{dmin:.0f}–{dmax:.0f}%</div>
          <div class="s">band {band_lbl} · now {r.get('alloc', 0) * 100:.0f}%</div>
        </div>
      </div>
      {_premium(r.get('premium', []), P, _month_earned())}
      <div class="ck-cards">{_card('IRA', P['blue'], r['ira'], P)}{_card('LLC', P['purple'], r['llc'], P)}</div>
      <div class="ck-cards ck-sumrow">{_card('COMBINED', P['steel'], _combined(r['ira'], r['llc']), P)}{_perf(_mdf, P)}</div>
    </div>"""
    html = "\n".join(line.lstrip() for line in html.splitlines())
    st.markdown(html, unsafe_allow_html=True)
