"""Performance charts. Monthly = my accounts in actual $ (IRA · LLC · Total, from
the Performance tab). Weekly & Daily = the Scoreboard comparison Mine · Rayan · SPY
as growth-of-$100 (so SPY shares the axis). Theme-aware Altair, no new dependency."""

from __future__ import annotations

import re

import altair as alt
import pandas as pd

from services import gsheet


def _num(s):
    s = str(s).replace("%", "").replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ── Monthly: actual account dollars ─────────────────────────────────────────
def monthly_df() -> tuple[pd.DataFrame, list]:
    """Monthly actual $: Total · IRA · LLC (+ cumulative % return vs SPY for the header).
    Starts at the first month IRA & LLC both have a value."""
    g = gsheet.performance()
    if g.empty or len(g) < 3:
        return pd.DataFrame(), []
    data = list(reversed([r for r in g.values.tolist()[2:] if str(r[0]).strip()]))
    recs, pret, sret, qret = [], None, None, None
    for r in data:
        r = [str(x).strip() for x in r]
        ira_start = _num(r[1]) if len(r) > 1 else None         # IRA Start (month opening balance)
        ira = _num(r[2]) if len(r) > 2 else None              # IRA End
        llc_start = _num(r[5]) if len(r) > 5 else None         # LLC Start
        llc = _num(r[6]) if len(r) > 6 else None              # LLC End
        spy_start = _num(r[9]) if len(r) > 9 else None         # SPY Start (month opening level)
        spy = _num(r[10]) if len(r) > 10 else None            # SPY End (index level)
        qqq_start = _num(r[13]) if len(r) > 13 else None       # QQQ Start
        qqq = _num(r[14]) if len(r) > 14 else None            # QQQ End (index level)
        tot_start = _num(r[17]) if len(r) > 17 else None       # Total Start (month opening balance)
        total = _num(r[18]) if len(r) > 18 else None
        pr = _num(r[19]) if len(r) > 19 else None            # Total % Return (deposit-adjusted)
        sr = _num(r[12]) if len(r) > 12 else None             # SPY %Chg
        qr = _num(r[16]) if len(r) > 16 else None             # QQQ %Chg
        dt = pd.to_datetime(re.sub(r"[^A-Za-z0-9]+", " ", r[0]).strip(),
                            format="%b %Y", errors="coerce")
        if pd.isna(dt) or not total or not ira or not llc:
            continue
        if pret is None:
            pret, sret, qret = 100.0, 100.0, 100.0            # first shown month = baseline
        else:
            if pr is not None:
                pret *= 1 + pr / 100
            if sr is not None and sr > -99:
                sret *= 1 + sr / 100
            if qr is not None and qr > -99:
                qret *= 1 + qr / 100
        recs.append({"date": dt, "Total": total, "tot_start": tot_start,
                     "IRA": ira, "ira_start": ira_start, "LLC": llc, "llc_start": llc_start,
                     "SPY": spy, "spy_start": spy_start, "QQQ": qqq, "qqq_start": qqq_start,
                     "port_ret": round(pret, 2), "spy_ret": round(sret, 2)})
    return pd.DataFrame(recs), ["Total", "IRA", "LLC"]


# ── Weekly / Daily: Mine vs Rayan vs SPY, growth-of-$100 ─────────────────────
def scoreboard_df(freq: str = "D") -> tuple[pd.DataFrame, list]:
    """Mine (J End) · Rayan (R End) · SPY (SPY End) actual levels from the Scoreboard tab.
    Raw End values, NOT the %-change columns — those only capture each row's own Start→End
    and miss the gaps between recorded dates. Callers rebase to growth-of-$100 / % as needed.
    freq='D' daily · 'W' weekly (last value per Fri-week, labelled 'Sep W2')."""
    g = gsheet.scoreboard()
    if g.empty or len(g) < 3:
        return pd.DataFrame(), []
    recs = []
    for row in g.values.tolist()[1:]:
        row = [str(x).strip() for x in row]
        dt = pd.to_datetime(row[0], errors="coerce")
        j = _num(row[2]) if len(row) > 2 else None            # J End (Mine)
        r_ = _num(row[6]) if len(row) > 6 else None            # R End (Rayan)
        s = _num(row[10]) if len(row) > 10 else None           # SPY End
        if pd.isna(dt) or j is None:
            continue
        recs.append({"date": dt, "Mine": j, "Rayan": r_, "SPY": s})
    df = pd.DataFrame(recs)
    if freq == "W" and not df.empty:
        df = df.set_index("date").resample("W-FRI").last().dropna(how="all").reset_index()
        df["wk"] = df["date"].apply(lambda d: f"{d:%b} W{(d.day - 1) // 7 + 1}")
    return df, ["Mine", "Rayan", "SPY"]


def rebase(df: pd.DataFrame, series: list) -> pd.DataFrame:
    """Re-index the growth columns to 100 at the first row (for a filtered window)."""
    if df.empty:
        return df
    df = df.copy()
    for k in series:
        base = df[k].iloc[0]
        if base:
            df[k] = (df[k] / base * 100).round(2)
    return df


# ── Chart ────────────────────────────────────────────────────────────────────
def chart(c: dict, df: pd.DataFrame, series: list, *, mode: str = "index",
          x_field: str = "date", x_fmt: str = "%b %d", tip_fmt: str = "%b %d, %Y"):
    """One panel; first series = gold + thick. mode 'dollar' → $ axis, 'index' → growth."""
    ax = dict(labelColor=c["mid"], titleColor=c["muted"], gridColor=c["border_soft"],
              domainColor=c["border"], tickColor=c["border"],
              labelFontSize=13, titleFontSize=13)
    palette = [c["gold"], c["blue"], c["muted"], c["accent"]]
    cscale = alt.Scale(domain=series, range=palette[:len(series)])
    wscale = alt.Scale(domain=series, range=[3.6] + [1.8] * (len(series) - 1))

    if x_field == "date":
        xenc = alt.X("date:T", title=None,
                     axis=alt.Axis(format=x_fmt, labelOverlap="greedy", **ax))
        selfields = ["date"]
        tip_x = alt.Tooltip("date:T", title="Date", format=tip_fmt)
    else:                                                     # nominal labels (weeks / months), keep order
        xenc = alt.X(f"{x_field}:N", title=None, sort=df[x_field].tolist(),
                     axis=alt.Axis(labelAngle=0, **ax))
        selfields = [x_field]
        xt = "Week" if x_field == "wk" else "Month" if x_field == "mon" else x_field.title()
        tip_x = alt.Tooltip(f"{x_field}:N", title=xt)

    y_title = "Account value ($)" if mode == "dollar" else "Growth of $100"
    y_fmt = "$.3s" if mode == "dollar" else "~f"
    tip_v = (alt.Tooltip("value:Q", title="Value", format="$,.0f") if mode == "dollar"
             else alt.Tooltip("value:Q", title="Index", format=".1f"))

    long = df.melt([x_field], series, var_name="series", value_name="value").dropna(subset=["value"])
    sel = alt.selection_point(fields=selfields, nearest=True, on="mouseover", empty=False)

    line = alt.Chart(long).mark_line().encode(
        x=xenc,
        y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False), axis=alt.Axis(format=y_fmt, **ax)),
        color=alt.Color("series:N", scale=cscale,
                        legend=alt.Legend(title=None, labelColor=c["text"], orient="top-left")),
        size=alt.Size("series:N", scale=wscale, legend=None))
    pts = alt.Chart(long).mark_circle(size=60).encode(
        x=xenc, y="value:Q", color=alt.Color("series:N", scale=cscale, legend=None),
        opacity=alt.condition(sel, alt.value(1), alt.value(0)),
        tooltip=[tip_x, alt.Tooltip("series:N", title="Series"), tip_v])
    rule = alt.Chart(long).mark_rule(color=c["muted"], strokeDash=[3, 3]).encode(x=xenc).transform_filter(sel)

    return ((line + rule + pts.add_params(sel)).properties(height=340)
            .configure_view(strokeWidth=0, fill=None)
            .configure(background="transparent"))


# ── Monthly % up/down vs the indexes (with a real-dollar tooltip) ─────────────
def growth_chart(c: dict, df: pd.DataFrame, order: list, colmap: dict, actcol: dict,
                 dollar_keys: set, *, x_field: str = "mon", x_title: str = "Month",
                 y_title: str = "Up / down since Jan start (0%)",
                 actual_title: str = "Fidelity $ / index level"):
    """% up/down since the window's start, one line per series, with a 0% reference line
    (above = up, below = down). The hover tooltip shows the ACTUAL figure — a $ value for
    series in `dollar_keys`, a plain number otherwise. Expects: an `x_field` label column,
    one 100-index column per series in `order`, and each series' actual in `actcol`."""
    ax = dict(labelColor=c["mid"], titleColor=c["muted"], gridColor=c["border_soft"],
              domainColor=c["border"], tickColor=c["border"],
              labelFontSize=13, titleFontSize=13)
    cscale = alt.Scale(domain=order, range=[colmap[k] for k in order])
    wscale = alt.Scale(domain=order, range=[2.8 if k in dollar_keys else 1.9 for k in order])

    recs = []
    for _, row in df.iterrows():
        for k in order:
            idx = row.get(k)
            if pd.isna(idx):
                continue
            av = row.get(actcol[k])
            act = _money(av, "$") if k in dollar_keys else (f"{av:,.0f}" if pd.notna(av) else "—")
            recs.append({"x": row[x_field], "series": k, "pct": idx / 100 - 1, "actual": act})
    long = pd.DataFrame(recs)

    xenc = alt.X("x:N", title=None, sort=df[x_field].tolist(), axis=alt.Axis(labelAngle=0, **ax))
    sel = alt.selection_point(fields=["x"], nearest=True, on="mouseover", empty=False)
    tips = [alt.Tooltip("x:N", title=x_title), alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("pct:Q", title="Up / down", format="+.1%"),
            alt.Tooltip("actual:N", title=actual_title)]

    last_x = df[x_field].iloc[-1]
    ends = long[long["x"] == last_x]

    zero = alt.Chart(long).mark_rule(color=c["muted"], size=1).encode(y=alt.datum(0))
    line = alt.Chart(long).mark_line().encode(
        x=xenc,
        y=alt.Y("pct:Q", title=y_title, scale=alt.Scale(zero=True),
                axis=alt.Axis(format="+.0%", **ax)),
        color=alt.Color("series:N", scale=cscale, sort=order,
                        legend=alt.Legend(title=None, labelColor=c["text"], labelFontSize=14,
                                          symbolStrokeWidth=3, orient="top-left")),
        size=alt.Size("series:N", scale=wscale, legend=None))
    enddot = alt.Chart(ends).mark_circle(size=90).encode(
        x=xenc, y="pct:Q", color=alt.Color("series:N", scale=cscale, legend=None))
    endlbl = alt.Chart(ends).mark_text(align="left", dx=9, fontWeight="bold", fontSize=15).encode(
        x=xenc, y="pct:Q", text=alt.Text("pct:Q", format="+.1%"),
        color=alt.Color("series:N", scale=cscale, legend=None))
    pts = alt.Chart(long).mark_circle(size=60).encode(
        x=xenc, y="pct:Q", color=alt.Color("series:N", scale=cscale, legend=None),
        opacity=alt.condition(sel, alt.value(1), alt.value(0)), tooltip=tips)
    cross = alt.Chart(long).mark_rule(color=c["muted"], strokeDash=[3, 3]).encode(
        x=xenc).transform_filter(sel)

    return ((zero + line + cross + enddot + endlbl + pts.add_params(sel))
            .properties(height=320, padding={"left": 4, "top": 6, "bottom": 4, "right": 56})
            .configure_view(strokeWidth=0, fill=None)
            .configure(background="transparent"))


# ── Monthly dual-axis: account $ (left) vs SPY·QQQ index (right) ──────────────
def monthly_chart(c: dict, df: pd.DataFrame):
    """One year: account value ($, left axis) + SPY/QQQ index points (right axis).
    Two independent y-scales because $1.6M and ~760 index points can't share one axis.
    Portfolio lines are solid + colored; the benchmarks are dashed grays (secondary)."""
    ax = dict(labelColor=c["mid"], titleColor=c["muted"], gridColor=c["border_soft"],
              domainColor=c["border"], tickColor=c["border"],
              labelFontSize=13, titleFontSize=13)
    dols = ["Total", "IRA", "LLC"]
    idx = ["SPY", "QQQ"]
    order = dols + idx
    colmap = {"Total": c["gold"], "IRA": c["blue"], "LLC": c["accent"],
              "SPY": c["muted"], "QQQ": c["mid"]}
    cscale = alt.Scale(domain=order, range=[colmap[k] for k in order])
    wscale = alt.Scale(domain=order, range=[3.6, 2.0, 2.0, 1.6, 1.6])

    xenc = alt.X("mon:N", title=None, sort=df["mon"].tolist(), axis=alt.Axis(labelAngle=0, **ax))
    sel = alt.selection_point(fields=["mon"], nearest=True, on="mouseover", empty=False)

    dlong = df.melt(["mon"], dols, var_name="series", value_name="value").dropna(subset=["value"])
    ilong = df.melt(["mon"], idx, var_name="series", value_name="value").dropna(subset=["value"])

    dline = alt.Chart(dlong).mark_line().encode(
        x=xenc,
        y=alt.Y("value:Q", title="Account value ($)", scale=alt.Scale(zero=False),
                axis=alt.Axis(format="$.3s", **ax)),
        color=alt.Color("series:N", scale=cscale, sort=order,
                        legend=alt.Legend(title=None, labelColor=c["text"], orient="top-left")),
        size=alt.Size("series:N", scale=wscale, legend=None))
    iline = alt.Chart(ilong).mark_line(strokeDash=[5, 3]).encode(
        x=xenc,
        y=alt.Y("value:Q", title="Index (SPY · QQQ)", scale=alt.Scale(zero=False),
                axis=alt.Axis(format="~f", **ax)),
        color=alt.Color("series:N", scale=cscale, legend=None),
        size=alt.Size("series:N", scale=wscale, legend=None))

    dpts = alt.Chart(dlong).mark_circle(size=55).encode(
        x=xenc, y="value:Q", color=alt.Color("series:N", scale=cscale, legend=None),
        opacity=alt.condition(sel, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("mon:N", title="Month"), alt.Tooltip("series:N", title="Series"),
                 alt.Tooltip("value:Q", title="Value", format="$,.0f")])
    ipts = alt.Chart(ilong).mark_circle(size=55).encode(
        x=xenc, y="value:Q", color=alt.Color("series:N", scale=cscale, legend=None),
        opacity=alt.condition(sel, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("mon:N", title="Month"), alt.Tooltip("series:N", title="Series"),
                 alt.Tooltip("value:Q", title="Index", format=".0f")])
    rule = alt.Chart(dlong).mark_rule(color=c["muted"], strokeDash=[3, 3]).encode(
        x=xenc).transform_filter(sel)

    left = dline + dpts + rule
    right = iline + ipts.add_params(sel)
    return (alt.layer(left, right).resolve_scale(y="independent")
            .properties(height=320)
            .configure_view(strokeWidth=0, fill=None)
            .configure(background="transparent"))


# ── Headers ──────────────────────────────────────────────────────────────────
def _money(v, esc: str = "\\$") -> str:
    """Compact dollars for a header chip: 1493700 → '\\$1.49M'. `esc` = '$' for
    tooltip text (plain), '\\$' for Streamlit markdown (escaped from LaTeX)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    a = abs(v)
    if a >= 1e6:
        return f"{esc}{v / 1e6:.2f}M"
    if a >= 1e3:
        return f"{esc}{v / 1e3:.0f}K"
    return f"{esc}{v:,.0f}"


def year_edge(c: dict, df: pd.DataFrame, year: int, order: list) -> str:
    """Year chip: combined account \\$ (start→now, +gain), each series' % for the year,
    and the combined portfolio's edge vs SPY. All % come straight from the 100-indices."""
    def ret(k):
        return df[k].iloc[-1] - 100 if k in df and not df[k].empty else 0.0
    start = df["tot_start"].iloc[0] if "tot_start" in df and not df["tot_start"].empty else None
    now = df["Total"].iloc[-1] if "Total" in df and not df["Total"].empty else None
    gain = (now - start) if (start is not None and now is not None) else None
    gcol = c["pos"] if (gain or 0) >= 0 else c["neg"]
    dollars = (f"{_money(start)} → <b style='color:{c['text']};'>{_money(now)}</b> "
               f"<b style='color:{gcol};'>({'+' if (gain or 0) >= 0 else ''}{_money(gain)})</b>"
               if start is not None else "")
    parts = []
    for k in order:
        v = ret(k)
        col = c["pos"] if v >= 0 else c["neg"]
        parts.append(f"{k} <b style='color:{col};'>{v:+.1f}%</b>")
    port = (now / start * 100 - 100) if (start and now) else 0.0    # combined, raw
    edge = port - ret("SPY")
    ecol = c["pos"] if edge >= 0 else c["neg"]
    return (f"### {year} &nbsp; <span style='font-size:15px;color:{c['muted']};'>{dollars}</span>\n\n"
            f"<span style='font-size:14px;color:{c['muted']};'>"
            f"{' · '.join(parts)} &nbsp;·&nbsp; combined edge vs SPY "
            f"<b style='color:{ecol};'>{edge:+.1f} pts</b></span>")


def header_dollar(c: dict, df: pd.DataFrame, series: list, label: str) -> str:
    # Raw Start→End over the whole span (matches the sheet's own return figures).
    p = (df["Total"].iloc[-1] / df["tot_start"].iloc[0] * 100 - 100
         if "tot_start" in df and df["tot_start"].iloc[0] else 0)
    s = (df["SPY"].iloc[-1] / df["spy_start"].iloc[0] * 100 - 100
         if "spy_start" in df and df["spy_start"].iloc[0] else 0)
    edge = p - s
    vals = " · ".join(f"{k} <b>\\${df[k].iloc[-1]:,.0f}</b>"
                      for k in series if k in df.columns and pd.notna(df[k].iloc[-1]))
    return (f"##### 📈 Account value ({label})  "
            f"<span style='font-size:12px;color:{c['muted']};'>{vals} &nbsp;·&nbsp; "
            f"return <b style='color:{c['pos'] if p >= 0 else c['neg']};'>{p:+.1f}%</b> vs SPY "
            f"<b>{s:+.1f}%</b> · edge <b style='color:{c['pos'] if edge >= 0 else c['neg']};'>"
            f"{edge:+.1f} pts</b></span>")


def header_index(c: dict, df: pd.DataFrame, series: list, label: str) -> str:
    def ret(k):
        return df[k].iloc[-1] / df[k].iloc[0] * 100 - 100
    spy = ret("SPY") if "SPY" in df else 0
    parts = []
    for k in series:
        v = ret(k)
        col = c["pos"] if v >= 0 else c["neg"]
        parts.append(f"{k} <b style='color:{col};'>{v:+.1f}%</b>")
    edge = ret("Mine") - spy
    ecol = c["pos"] if edge >= 0 else c["neg"]
    return (f"### 📈 Mine vs Rayan vs SPY "
            f"<span style='font-size:15px;color:{c['muted']};'>({label})</span>\n\n"
            f"<span style='font-size:14px;color:{c['muted']};'>{' · '.join(parts)} &nbsp;·&nbsp; "
            f"edge vs SPY <b style='color:{ecol};'>{edge:+.1f} pts</b></span>")
