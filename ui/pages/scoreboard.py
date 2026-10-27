"""🏁 Scoreboard — progress of the wheel (J) vs SPY, from the daily Scoreboard tab.

The Scoreboard tab logs each trading day's wheel capital (J Start → J End) and SPY
(Start → End) since Sep 1. This page rolls that up into This Week / This Month / Since
Sep tiles (wheel % + $ with SPY beside) and a week-by-week list of wheel vs SPY.
A period's return = last End ÷ first Start − 1 (point-to-point), so it matches the sheet.
"""

from __future__ import annotations

import datetime as _dt

import altair as alt
import pandas as pd
import streamlit as st

from services import gsheet


def _num(x):
    try:
        s = str(x).replace(",", "").replace("$", "").replace("%", "").strip()
        return float(s) if s not in ("", "—", "-", "nan", "#N/A", "#REF!") else None
    except Exception:
        return None


def _date(x):
    for f in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(str(x).strip(), f).date()
        except Exception:
            continue
    return None


@st.cache_data(ttl=300, show_spinner=False)
def _rows() -> list[dict]:
    """[{date, jStart, jEnd, spyStart, spyEnd, vix}] sorted by date (header row dropped)."""
    df = gsheet.scoreboard()
    out: list[dict] = []
    if df is None or df.empty:
        return out
    for _, r in df.iterrows():
        d = _date(r.iloc[0])
        if d is None:                                  # header / blank row
            continue
        js, je = _num(r.iloc[1]), _num(r.iloc[2])
        ss = _num(r.iloc[9]) if len(r) > 9 else None
        se = _num(r.iloc[10]) if len(r) > 10 else None
        vix = _num(r.iloc[13]) if len(r) > 13 else None
        if js and je:
            out.append({"date": d, "jStart": js, "jEnd": je,
                        "spyStart": ss, "spyEnd": se, "vix": vix})
    out.sort(key=lambda x: x["date"])
    return out


def _period(rows: list[dict]) -> dict | None:
    """Point-to-point rollup for a slice of days: first Start → last End."""
    if not rows:
        return None
    rows = sorted(rows, key=lambda x: x["date"])
    j0, j1 = rows[0]["jStart"], rows[-1]["jEnd"]
    wheel_d = j1 - j0
    wheel_p = (wheel_d / j0) if j0 else 0.0
    spy_p = None
    if rows[0]["spyStart"] and rows[-1]["spyEnd"]:
        spy_p = rows[-1]["spyEnd"] / rows[0]["spyStart"] - 1
    return {"wheel_d": wheel_d, "wheel_p": wheel_p, "spy_p": spy_p,
            "n": len(rows), "start": rows[0]["date"], "end": rows[-1]["date"]}


def _money(v: float) -> str:
    return ("-$" if v < 0 else "$") + f"{abs(v):,.0f}"


def _balance_chart(c: dict, rows: list[dict]) -> None:
    """Brokerage-style balance line: wheel capital (J End) over the selected range, with the
    big current balance + % change. Range toggle fits the data (daily since Aug 31)."""
    pos, neg, mut, text = c["pos"], c["neg"], c["muted"], c["text"]
    choice = st.radio("range", ["1W", "1M", "All"], index=1, horizontal=True,
                      key="sb_range", label_visibility="collapsed")
    n = {"1W": 5, "1M": 22}.get(choice)
    sel = rows[-n:] if n else rows
    if len(sel) < 2:
        sel = rows                                           # not enough points → show all

    bal = sel[-1]["jEnd"]
    base = sel[0]["jStart"]
    chg_d = bal - base
    chg_p = (chg_d / base) if base else 0.0
    col = pos if chg_d >= 0 else neg
    rng_lbl = {"1W": "this week", "1M": "this month", "All": "since " + sel[0]["date"].strftime("%b %-d")}[choice]

    st.markdown(
        f"<div style='font-size:11px;color:{mut};text-transform:uppercase;letter-spacing:.5px;"
        f"font-weight:800'>Wheel balance</div>"
        f"<div style='font-size:30px;font-weight:900;color:{text};font-variant-numeric:tabular-nums;"
        f"line-height:1.05'>${bal:,.0f}</div>"
        f"<div style='font-size:13px;font-weight:700;color:{col};margin-bottom:2px'>"
        f"{'+' if chg_d >= 0 else '−'}${abs(chg_d):,.0f} ({chg_p*100:+.2f}%) <span style='color:{mut};"
        f"font-weight:600'>{rng_lbl}</span></div>", unsafe_allow_html=True)

    line_c = pos if chg_d >= 0 else neg
    cdf = pd.DataFrame({"date": [r["date"] for r in sel], "Balance": [float(r["jEnd"]) for r in sel]})
    # float() is required — numpy floats don't JSON-serialize, which silently drops the Scale domain
    # and makes Altair fall back to a 0-baseline (line squashed at the top). background = card colour
    # because the app's Streamlit base theme is dark, which would otherwise render the plot black.
    lo, hi = float(cdf["Balance"].min()), float(cdf["Balance"].max())
    pad = (hi - lo) * 0.15 or hi * 0.01
    ch = (alt.Chart(cdf).mark_line(color=line_c, strokeWidth=2.5, interpolate="monotone")
          .encode(
            x=alt.X("date:T", axis=alt.Axis(title=None, format="%b %-d", tickCount=5, orient="bottom",
                                            labelColor=mut, domain=False, ticks=False, grid=False)),
            y=alt.Y("Balance:Q", scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False, zero=False),
                    axis=alt.Axis(title=None, labelColor=mut, format="$,.3s", tickCount=3,
                                  domain=False, ticks=False, grid=True,
                                  gridColor=c["border_soft"], gridDash=[2, 3])),
            tooltip=[alt.Tooltip("date:T", title="Date", format="%b %-d"),
                     alt.Tooltip("Balance:Q", title="Balance", format="$,.0f")])
          .properties(height=220, background=c["panel"]))
    st.altair_chart(ch, use_container_width=True, theme=None)


def render(c: dict) -> None:
    pos, neg, text, mut = c["pos"], c["neg"], c["text"], c["muted"]
    raised, border, bsoft, panel = c["raised"], c["border"], c["border_soft"], c["panel"]

    rows = _rows()
    if not rows:
        st.info("Couldn't read the Scoreboard tab (daily J vs SPY). Check the workbook.")
        return

    last = rows[-1]["date"]
    iso = last.isocalendar()
    wtd = [r for r in rows if r["date"].isocalendar()[:2] == iso[:2]]      # same ISO year+week
    mtd = [r for r in rows if (r["date"].year, r["date"].month) == (last.year, last.month)]

    # ── Balance line (brokerage style): wheel capital over time + range toggle ──
    _balance_chart(c, rows)

    st.caption(f"Wheel capital (J) vs SPY · daily since {rows[0]['date']:%b %-d} · "
               f"as of {last:%b %-d} · point-to-point (first Start → last End)")

    # ── summary tiles: This Week · This Month · Since Sep ──
    def _tile(label, p):
        if not p:
            return (f"<div style='flex:1;min-width:150px;background:{panel};border:1px solid {border};"
                    f"border-radius:12px;padding:12px 14px'>"
                    f"<div style='font-size:10px;letter-spacing:.5px;text-transform:uppercase;"
                    f"color:{mut};font-weight:800'>{label}</div><div style='color:{mut};"
                    f"font-size:20px;font-weight:800;margin-top:4px'>—</div></div>")
        wc = pos if p["wheel_p"] >= 0 else neg
        spy_txt = (f"SPY {p['spy_p']*100:+.2f}%" if p["spy_p"] is not None else "SPY —")
        spy_c = (pos if (p["spy_p"] or 0) >= 0 else neg) if p["spy_p"] is not None else mut
        beat = (p["wheel_p"] - (p["spy_p"] or 0)) * 100 if p["spy_p"] is not None else None
        beat_txt = (f"<span style='color:{pos if beat >= 0 else neg};font-weight:700'>"
                    f"{beat:+.2f} pts vs SPY</span>" if beat is not None else "")
        return (f"<div style='flex:1;min-width:150px;background:{panel};border:1px solid {border};"
                f"border-radius:12px;padding:12px 14px'>"
                f"<div style='font-size:10px;letter-spacing:.5px;text-transform:uppercase;"
                f"color:{mut};font-weight:800'>{label} <span style='color:{mut};font-weight:600'>"
                f"· {p['n']}d</span></div>"
                f"<div style='font-size:24px;font-weight:900;color:{wc};margin-top:3px;"
                f"font-variant-numeric:tabular-nums'>{p['wheel_p']*100:+.2f}%</div>"
                f"<div style='font-size:13px;font-weight:700;color:{wc}'>{_money(p['wheel_d'])}</div>"
                f"<div style='margin-top:6px;font-size:11px;color:{spy_c};font-weight:700'>{spy_txt}</div>"
                f"<div style='font-size:10.5px;margin-top:1px'>{beat_txt}</div></div>")

    tiles = (f"<div style='display:flex;gap:12px;flex-wrap:wrap;margin:4px 0 16px'>"
             f"{_tile('This Week', _period(wtd))}{_tile('This Month', _period(mtd))}"
             f"{_tile('Since ' + rows[0]['date'].strftime('%b %-d'), _period(rows))}</div>")
    st.markdown(tiles, unsafe_allow_html=True)

    # ── week-by-week list: each ISO week's wheel % + $ vs SPY % ──
    weeks: dict[tuple, list] = {}
    for r in rows:
        weeks.setdefault(r["date"].isocalendar()[:2], []).append(r)
    wk_rows = ""
    for key in sorted(weeks, reverse=True):                 # most recent week first
        p = _period(weeks[key])
        if not p:
            continue
        wc = pos if p["wheel_p"] >= 0 else neg
        sc = (pos if (p["spy_p"] or 0) >= 0 else neg) if p["spy_p"] is not None else mut
        spy_s = f"{p['spy_p']*100:+.2f}%" if p["spy_p"] is not None else "—"
        beat = (p["wheel_p"] - (p["spy_p"] or 0)) * 100 if p["spy_p"] is not None else None
        beat_s = (f"<span style='color:{pos if beat >= 0 else neg}'>{beat:+.2f}</span>"
                  if beat is not None else "—")
        label = (f"{p['start']:%b %-d}" if p["start"] == p["end"]
                 else f"{p['start']:%b %-d}–{p['end']:%-d}")
        wk_rows += (f"<tr><td class='sb-l'>{label}</td>"
                    f"<td style='color:{wc};font-weight:800'>{p['wheel_p']*100:+.2f}%</td>"
                    f"<td style='color:{wc}'>{_money(p['wheel_d'])}</td>"
                    f"<td style='color:{sc}'>{spy_s}</td>"
                    f"<td style='font-weight:700'>{beat_s}</td></tr>")

    css = (f"<style>.sb-tbl{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;"
           f"font-size:14px;border:1px solid {bsoft};border-radius:10px;overflow:hidden}}"
           f".sb-tbl th{{text-align:right;color:{mut};font-size:10px;font-weight:700;letter-spacing:.4px;"
           f"text-transform:uppercase;padding:9px 13px;background:{raised};border-bottom:1px solid {bsoft}}}"
           f".sb-tbl th:first-child,.sb-tbl td:first-child{{text-align:left}}"
           f".sb-tbl td{{text-align:right;padding:9px 13px;border-bottom:1px solid {bsoft};color:{text}}}"
           f".sb-tbl td.sb-l{{font-weight:700}}</style>")
    head = "".join(f"<th>{h}</th>" for h in ["Week", "Wheel %", "Wheel $", "SPY %", "vs SPY (pts)"])
    st.markdown("##### 📆 By week", unsafe_allow_html=True)
    st.markdown(css + f"<table class='sb-tbl'><thead><tr>{head}</tr></thead>"
                f"<tbody>{wk_rows}</tbody></table>", unsafe_allow_html=True)
