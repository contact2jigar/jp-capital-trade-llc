"""🎛️ Cockpit — a control-room re-imagining of the Monitor Board.

Same live numbers as the Command Center (via command_center.board_data), rendered
as instrument panels: a VIX regime meter with the deploy-target range, per-account
allocation rings + CC-breaker gauges, and premium bars. Theme-aware (dark + grey),
server-side HTML/SVG (no JS), large type for easy reading."""

from __future__ import annotations

import math

import streamlit as st

from logic import monitor as engine
from ui.pages import command_center as cc

# VIX bands: label + segment color (bright in either theme, so dark text on them).
BANDS = [("8–13", "#e06666"), ("13–15", "#ef9a5c"), ("15–20", "#ffd966"),
         ("20–25", "#b7d77a"), ("25–30", "#93c47d"), ("30–100", "#6aa84f")]
EDGES = [8, 13, 15, 20, 25, 30, 100]

# ── two palettes; data-hues shift darker on the light skin for contrast ──────
DARK = dict(
    bg="#0a0e13", glow="#12202e", phi="#18222e", plo="#0f161e", line="#26333f", lsoft="#1b242f",
    ink="#e9eff5", mid="#aebac7", mut="#6f7d8c", subv="#9aa7b4", steel="#3a4757",
    hole1="#151d27", hole2="#0e141c", track="#0c131b", hi="rgba(255,255,255,.045)",
    gold="#e3b23c", blue="#58a6ff", purple="#a78bfa", green="#43c463", amber="#e3a63a", red="#f2555a",
    shadow="0 22px 46px -28px rgba(0,0,0,.85)")
LIGHT = dict(
    bg="#eef1f3", glow="#dce7f2", phi="#ffffff", plo="#f2f5f7", line="#c7ced3", lsoft="#dde2e6",
    ink="#16212c", mid="#38454f", mut="#66727d", subv="#5c6873", steel="#9aa7b4",
    hole1="#ffffff", hole2="#eef1f3", track="#e4e8eb", hi="rgba(255,255,255,.7)",
    gold="#b8860b", blue="#2f6fb0", purple="#6b3fa0", green="#2f7e25", amber="#8a6800", red="#b62027",
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


def _pct(part, whole) -> float:
    return (float(part) / float(whole) * 100.0) if whole else 0.0


# (brand mark now comes from ui.brand.gearframe)


# ── semicircle CC-breaker gauge: 45% cap = full deflection (the freeze redline) ─
def _gauge(v: float, P: dict) -> str:
    cx, cy, r, S = 90, 86, 70, 45.0     # full arc = the 45% breaker cap

    def pol(deg):
        a = math.radians(deg)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    def arc(v1, v2, col):
        x1, y1 = pol(180 - v1 / S * 180)
        x2, y2 = pol(180 - v2 / S * 180)
        return (f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" '
                f'fill="none" stroke="{col}" stroke-width="12" stroke-linecap="round"/>')

    # Zones against the real cap: green < 30, amber 30–43, red 43–45 (the redline).
    gz, ay, rz = "#43c463", "#e6b93e", "#f2555a"
    nx, ny = pol(180 - min(v, S) / S * 180)
    return f"""<svg viewBox="0 0 180 92" width="100%" style="max-width:172px" aria-label="CC breaker {v:.1f}% of 45% cap">
      {arc(0, 29, gz)}{arc(30, 42, ay)}{arc(43, 45, rz)}
      <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{P['ink']}" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="{cx}" cy="{cy}" r="5" fill="{P['ink']}"/>
      <circle cx="{cx}" cy="{cy}" r="10" fill="none" stroke="{P['line']}" stroke-width="1.5"/>
    </svg>"""


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
            {li(P['blue'], 'CSP', csp, d.get('csp'))}{li(P['gold'], 'CC', ccp, d.get('cc'))}
            {li(P['purple'], 'LEAP', leap, d.get('leap'))}{li(P['steel'], 'Cash', cash, d.get('cih'))}
          </div>
        </div>
        <div class="ck-gauge">{_gauge(brk, P)}
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


def _vix_meter(vix: float, band: int, up: bool) -> str:
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
    return (f"<div class='ck-segs'>{segs}</div>"
            f"<div class='ck-needle' style='left:{left:.1f}%'></div>")


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
        row = row if not row.empty else tot.head(1)         # else newest month
        return float(row["P/L"].iloc[0])
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
        rcol = P["green"] if rate >= 100 else P["gold"]
        gaptxt = (f"Beat goal by · {_m(-gap)}" if gap < 0 else f"Gap to goal · {_m(gap)}")
        gcol = P["green"] if gap < 0 else P["amber"]
        return (f"<div class='ck-pcard'>"
                f"<div class='ck-phead'><div>"
                f"<div class='ck-plabel'>{title} earned premium</div>"
                f"<div class='ck-pval'><b>{_m(earned)}</b> <span>/ {_m(goal)}</span></div>"
                f"</div><div class='ck-picon'>💰</div></div>"
                f"<div class='ck-prate'><span>{title} run rate</span>"
                f"<span class='ck-prpct' style='color:{rcol}'>{rate:.0f}%</span></div>"
                f"<div class='ck-ptrack'><div class='ck-pfill' style='width:{w:.1f}%'></div></div>"
                f"<div class='ck-pgap' style='color:{gcol}'>{gaptxt}</div></div>")

    return f"<div class='ck-prow'>{card('wk', 'Weekly')}{card('mo', 'Monthly')}</div>"


def _css(P: dict) -> str:
    return f"""<style>
.ck-wrap{{font-family:'IBM Plex Sans',system-ui,sans-serif;color:{P['ink']};
  background:radial-gradient(1000px 420px at 72% -12%,{P['glow']} 0%,transparent 60%),{P['bg']};
  border:1px solid {P['line']};border-radius:18px;padding:22px 22px 26px;margin-top:4px}}
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
.ck-vix{{padding:16px 20px;margin-bottom:16px;display:grid;grid-template-columns:auto 1fr auto;gap:22px;align-items:center}}
.ck-vixnow{{display:flex;align-items:baseline;gap:9px}}
.ck-vixnow .l{{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:{P['mut']}}}
.ck-vixnow .vv{{font-size:31px;font-weight:600;letter-spacing:-.02em}}
.ck-chg{{font-size:13px;font-weight:600;padding:3px 9px;border-radius:6px}}
.ck-meter{{position:relative}}
.ck-segs{{display:flex;height:46px;border-radius:9px;overflow:hidden;border:1px solid {P['line']}}}
.ck-seg{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  color:#12181f;line-height:1.1}}
.ck-seg.ck-dim{{opacity:.74}}
.ck-sr{{font-size:12.5px;font-weight:700;white-space:nowrap}}
.ck-sd{{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;opacity:.82;white-space:nowrap}}
.ck-seg:not(.ck-dim) .ck-sd{{opacity:1}}
.ck-needle{{position:absolute;top:-7px;bottom:-7px;width:2px;background:{P['ink']};border-radius:2px;
  box-shadow:0 0 0 3px {P['bg']}}}
.ck-needle::before{{content:"";position:absolute;top:-5px;left:50%;transform:translateX(-50%);
  border:5px solid transparent;border-top-color:{P['ink']}}}
.ck-regime{{text-align:right;white-space:nowrap}}
.ck-tl{{font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;color:{P['mut']}}}
.ck-target{{font-size:27px;font-weight:600;color:{P['gold']};line-height:1.05;margin:3px 0}}
.ck-regime .s{{font-size:12.5px;color:{P['mut']};margin-top:2px}}
.ck-cards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.ck-card{{padding:20px}}
.ck-chead{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}
.ck-acct{{display:flex;align-items:center;gap:10px}}
.ck-tag{{font-weight:700;font-size:13px;letter-spacing:.06em;padding:5px 11px;border-radius:7px}}
.ck-sub{{font-size:13px;color:{P['mut']}}}
.ck-ath{{font-size:13.5px;color:{P['mid']};margin-top:3px}}
.ck-cap{{font-size:29px;font-weight:600;letter-spacing:-.02em}}
.ck-inst{{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:center;margin:10px 0 16px}}
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
.ck-lv{{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;line-height:1.2}}
.ck-lv b{{color:{P['ink']};font-weight:700;font-size:15.5px}}
.ck-lv em{{font-style:normal;color:{P['subv']};font-size:12.5px}}
.ck-gauge{{display:flex;flex-direction:column;align-items:center;gap:2px}}
.ck-gv{{font-size:23px;font-weight:600;margin-top:-28px}}
.ck-gl{{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:{P['mut']};margin-top:5px}}
.ck-gz{{font-size:12.5px;font-weight:600;margin-top:3px}}
.ck-ready{{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-radius:11px;
  background:{P['green']}1e;border:1px solid {P['green']}55}}
.ck-rl{{font-size:12.5px;letter-spacing:.09em;text-transform:uppercase;color:{P['green']};font-weight:600}}
.ck-rv{{font-size:21px;font-weight:700;color:{P['green']}}}
.ck-rp{{font-size:13.5px;color:{P['green']};margin-left:8px}}
.ck-prow{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.ck-pcard{{padding:18px 20px}}
.ck-phead{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}}
.ck-plabel{{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:{P['mut']}}}
.ck-pval{{margin-top:6px;font-family:'IBM Plex Mono',monospace;font-size:26px;font-weight:700;color:{P['gold']}}}
.ck-pval span{{color:{P['subv']};font-size:16px;font-weight:600}}
.ck-picon{{width:40px;height:40px;border-radius:11px;display:flex;align-items:center;justify-content:center;
  font-size:20px;background:{P['gold']}1e;border:1px solid {P['gold']}44}}
.ck-prate{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}}
.ck-prate span:first-child{{font-size:12.5px;letter-spacing:.06em;text-transform:uppercase;color:{P['mut']}}}
.ck-prpct{{font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:700}}
.ck-ptrack{{height:12px;border-radius:7px;background:{P['track']};border:1px solid {P['lsoft']};overflow:hidden}}
.ck-pfill{{height:100%;border-radius:7px;background:linear-gradient(90deg,#e8893a,{P['amber']},{P['green']});
  box-shadow:0 0 14px -2px {P['green']}66}}
.ck-pgap{{font-family:'IBM Plex Mono',monospace;font-size:12px;margin-top:9px}}
@media (max-width:820px){{.ck-vix,.ck-cards,.ck-prow,.ck-inst{{grid-template-columns:1fr}}.ck-regime{{text-align:left}}}}
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
    band = r.get("band", 2)
    bdef = engine.BANDS[band] if 0 <= band < len(engine.BANDS) else engine.BANDS[2]
    up = str(trend).lower().startswith("up")
    dmin, dmax = (bdef[1] if up else bdef[3]) * 100, (bdef[2] if up else bdef[4]) * 100
    band_lbl = bdef[0]
    chg_col = P["red"] if vix_chg > 0 else P["green"]

    html = f"""{_css(P)}
    <div class="ck-wrap">
      <div class="ck-panel ck-vix">
        <div class="ck-vixnow"><span class="l">VIX</span><span class="vv">{vix:.2f}</span>
          <span class="ck-chg" style="color:{chg_col};background:{chg_col}22;border:1px solid {chg_col}55">
          {vix_chg * 100:+.1f}%</span></div>
        <div class="ck-meter">{_vix_meter(vix, band, up)}</div>
        <div class="ck-regime">
          <div class="ck-tl">Deploy target · {trend}</div>
          <div class="ck-target">{dmin:.0f}–{dmax:.0f}%</div>
          <div class="s">of wheel · band {band_lbl} · now {r.get('alloc', 0) * 100:.0f}%</div>
        </div>
      </div>
      <div class="ck-cards">{_card('IRA', P['blue'], r['ira'], P)}{_card('LLC', P['purple'], r['llc'], P)}</div>
      {_premium(r.get('premium', []), P, _month_earned())}
    </div>"""
    html = "\n".join(line.lstrip() for line in html.splitlines())
    st.markdown(html, unsafe_allow_html=True)
    src = "live Yahoo" if data["live"] else "sheet"
    st.caption(f"Concept · all figures live from the TradeLog · VIX/trend from {src}. "
               f"Same numbers as the Command Center, different instrument.")
