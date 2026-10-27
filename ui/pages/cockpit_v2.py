"""Cockpit ✨ — a new tab trialing the mobile app's card design on the web.

POC: the Performance card (headline · You/SPY/QQQ race · horizontal month bars),
with a Year tab (2026 / 2025) and an Account tab (Total / IRA / LLC). Reuses the
Performance tab via services.gsheet; the existing Cockpit/Board page is untouched.
"""

from __future__ import annotations

import re

import streamlit as st

from services import gsheet


# ── parse the Performance tab ────────────────────────────────────────────────
def _num(s) -> float | None:
    t = str(s).strip()
    if not t or t in ("—", "-", "#REF!", "nan"):
        return None
    neg = t.startswith("-") or t.startswith("−")
    clean = "".join(ch for ch in t if ch.isdigit() or ch == ".")
    if not clean:
        return None
    try:
        v = float(clean)
    except ValueError:
        return None
    return -v if neg else v


def _head(row0, key: str):
    """Row-0 summary cell 'IRA: +$159,222 (+19.71%)' → (gain, pct-fraction)."""
    for cell in row0:
        s = str(cell)
        if s.startswith(key):
            parts = s.split("(")
            gain = _num(parts[0])
            pctm = re.search(r"\(([^)]+)\)", s)
            pct = (_num(pctm.group(1)) / 100.0) if pctm and _num(pctm.group(1)) is not None else None
            return gain, pct
    return None, None


def _load():
    g = gsheet.performance()
    if g is None or g.empty or g.shape[0] < 3:
        return None
    row0 = list(g.iloc[0])

    def cell(r, col):
        try:
            return g.iat[r, col]
        except Exception:
            return ""

    months = []     # oldest→newest later; parse newest-first here
    for r in range(2, g.shape[0]):
        label = str(cell(r, 0)).replace(" ,", "").strip()
        ym = re.search(r"(20\d\d)", label)
        if not ym:
            continue
        pf = lambda v: (_num(v) / 100.0 if _num(v) is not None else None)   # noqa: E731
        tstart, tend = _num(cell(r, 17)), _num(cell(r, 18))
        months.append({
            "label": label, "year": int(ym.group(1)),
            "total": pf(cell(r, 19)), "ira": pf(cell(r, 4)), "llc": pf(cell(r, 8)),
            "spy": pf(cell(r, 12)), "qqq": pf(cell(r, 16)),
            "total_chg": (tend - tstart) if (tstart is not None and tend is not None) else None,
            "ira_chg": _num(cell(r, 3)), "llc_chg": _num(cell(r, 7)),
        })
    months.reverse()   # oldest → newest
    ytd = {k: _head(row0, lbl) for k, lbl in
           (("total", "Total:"), ("ira", "IRA:"), ("llc", "LLC:"),
            ("spy", "SPY:"), ("qqq", "QQQ:"))}
    return {"months": months, "ytd": ytd}


def _compound(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    p = 1.0
    for v in vals:
        p *= (1 + v)
    return p - 1


# ── render ───────────────────────────────────────────────────────────────────
def render(c: dict) -> None:
    st.markdown("# ✨ Cockpit — new look")
    st.caption("Trialing the mobile app's card design on the web (Performance card). "
               "The existing Cockpit is unchanged.")

    data = _load()
    if not data:
        st.info("No performance data available.")
        return

    all_years = sorted({m["year"] for m in data["months"]}, reverse=True)[:2]
    cur_year = all_years[0] if all_years else 2026

    a, b = st.columns([1.3, 1.6])
    with a:
        year = st.radio("Year", all_years, horizontal=True, key="cv2_year")
    with b:
        series = st.radio("Account", ["Total", "IRA", "LLC"], horizontal=True, key="cv2_series")
    skey = series.lower()

    ym = [m for m in data["months"] if m["year"] == year]
    is_cur = year == cur_year

    # headline + race for the chosen account/year
    if is_cur:
        gain, you = data["ytd"].get(skey, (None, None))
    else:
        gain = sum(m[f"{skey}_chg"] for m in ym if m.get(f"{skey}_chg") is not None) if ym else None
        you = _compound([m[skey] for m in ym])
    spy = (data["ytd"]["spy"][1] if is_cur else None) or _compound([m["spy"] for m in ym])
    qqq = (data["ytd"]["qqq"][1] if is_cur else None) or _compound([m["qqq"] for m in ym])
    you_label = "YOU" if series == "Total" else series

    st.markdown(_card_html(c, year, series, you_label, you, gain, spy, qqq, ym, skey),
                unsafe_allow_html=True)


def _m(v):            # "$1,234" / "—"
    return "—" if v is None else f"${v:,.0f}"


def _mk(v):           # "$12.9K" / "$1.2M"
    if v is None:
        return "—"
    a = abs(v)
    s = f"${a/1e6:.1f}M" if a >= 1e6 else f"${a/1e3:.1f}K"
    return ("-" if v < 0 else "") + s


def _pct(v):          # "+19.71%"
    return "—" if v is None else f"{v*100:+.2f}%"


def _card_html(c, year, series, you_label, you, gain, spy, qqq, months, skey) -> str:
    g, r, tx, mid, mut = c["pos"], c["neg"], c["text"], c["mid"], c["muted"]
    panel, raised, bd, bsoft = c["panel"], c["raised"], c["border"], c["border_soft"]
    you_col = g if (you or 0) >= 0 else r

    def tile(lbl, v):
        col = g if (v or 0) >= 0 else r
        return (f'<div style="flex:1;background:{raised};border-radius:10px;padding:11px 13px">'
                f'<div style="font-size:11px;font-weight:700;letter-spacing:.04em;color:{mut};'
                f'text-transform:uppercase">{lbl}</div>'
                f'<div style="font-size:18px;font-weight:700;color:{col};'
                f'font-family:ui-monospace,monospace;margin-top:3px">{_pct(v)}</div></div>')

    maxabs = max((abs(m[skey]) for m in months if m.get(skey) is not None), default=0.01) or 0.01
    rows = []
    for m in months:
        p = m.get(skey)
        if p is None:
            continue
        col = g if p >= 0 else r
        chg = m.get("total_chg" if skey == "total" else f"{skey}_chg")
        w = min(abs(p) / maxabs, 1) * 50
        label = m["label"].split(" ")[0]
        bar = (f'<div style="position:absolute;left:50%;width:{w:.1f}%;height:13px;'
               f'background:{col};border-radius:2px;top:1px"></div>' if p >= 0 else
               f'<div style="position:absolute;right:50%;width:{w:.1f}%;height:13px;'
               f'background:{col};border-radius:2px;top:1px"></div>')
        rows.append(
            f'<div style="display:flex;align-items:center;gap:12px;margin:9px 0">'
            f'<div style="width:46px;color:{mid};font-weight:600;font-size:14px">{label}</div>'
            f'<div style="flex:1;position:relative;height:15px">'
            f'<div style="position:absolute;left:50%;width:1px;height:15px;background:{bsoft}"></div>{bar}</div>'
            f'<div style="width:72px;text-align:right;color:{col};font-weight:700;font-size:14px;'
            f'font-family:ui-monospace,monospace">{p*100:+.1f}%</div>'
            f'<div style="width:84px;text-align:right;color:{col};opacity:.8;font-size:13px;'
            f'font-family:ui-monospace,monospace">{_mk(chg)}</div></div>')

    return (
        f'<div style="background:{panel};border:1px solid {bd};border-radius:14px;padding:18px;'
        f'max-width:620px">'
        # header
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<div style="width:3px;height:15px;background:{c["blue"]};border-radius:2px"></div>'
        f'<div style="font-size:13px;font-weight:800;letter-spacing:.12em;color:{mid}">📈 PERFORMANCE</div>'
        f'<div style="margin-left:auto;font-size:11px;font-weight:700;color:{mut};background:{raised};'
        f'padding:3px 9px;border-radius:6px">{year}</div></div>'
        # headline
        f'<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:12px">'
        f'<span style="font-size:30px;font-weight:800;color:{you_col};'
        f'font-family:ui-monospace,monospace">{_pct(you)}</span>'
        f'<span style="font-size:16px;font-weight:700;color:{you_col};'
        f'font-family:ui-monospace,monospace">{("+" if (gain or 0)>=0 else "")+_m(gain) if gain is not None else ""}</span>'
        f'</div>'
        # race tiles
        f'<div style="display:flex;gap:10px;margin-bottom:14px">'
        f'{tile(you_label, you)}{tile("SPY", spy)}{tile("QQQ", qqq)}</div>'
        # month bars
        f'{"".join(rows)}'
        f'</div>')
