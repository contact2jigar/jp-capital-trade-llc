"""📈 Performance — monthly IRA · LLC · SPY · QQQ · Total, mirrored from the sheet's
Performance tab. Read-only; the sheet is the source of truth."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from services import gsheet
from ui import benchmark

# Column groups in the Performance grid (0-indexed): the %-change column of each.
_PCT_COLS = {4, 8, 12, 16, 19}          # IRA/LLC/SPY/QQQ %Chg + Total % Return
_CHG_COLS = {3, 7, 11, 15}              # IRA/LLC/SPY/QQQ Chg
_SUMMARY = [(1, "IRA"), (5, "LLC"), (9, "SPY"), (13, "QQQ"), (17, "Total")]


@st.cache_data(ttl=300, show_spinner=False)
def _grid():
    return gsheet.performance()


def _neg(s: str) -> bool:
    return "-" in str(s) or "(" in str(s)


def _summary_cards(c, row0):
    cards = []
    for col, name in _SUMMARY:
        raw = str(row0[col]).strip() if col < len(row0) else ""
        # "IRA: +$156,222.00 (+19.34%)" → value + pct
        m = re.search(r":\s*(.+?)\s*\((.+?)\)", raw)
        val = m.group(1) if m else raw
        pct = m.group(2) if m else ""
        col_hex = c["neg"] if _neg(val) else c["pos"]
        cards.append(
            f"<div style='flex:1;min-width:150px;background:{c['panel']};border:1px solid {c['border']};"
            f"border-radius:11px;padding:13px 15px;'>"
            f"<div style='font-size:10px;font-weight:900;letter-spacing:.06em;color:{c['muted']};'>{name}</div>"
            f"<div style='margin-top:4px;font-size:20px;font-weight:950;color:{col_hex};'>{val}</div>"
            f"<div style='margin-top:2px;font-size:12px;font-weight:800;color:{col_hex};'>{pct}</div></div>")
    return f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;'>{''.join(cards)}</div>"


def _table(c, header, rows):
    head = "".join(
        f"<th style='position:sticky;top:0;{'left:0;z-index:3;' if i == 0 else 'z-index:2;'}"
        f"background:{c['raised']};color:{c['text']};"
        f"border:1px solid {c['border']};padding:11px 16px;text-align:{'left' if i == 0 else 'right'};"
        f"font-weight:800;font-size:14.5px;white-space:nowrap;'>{h}</th>" for i, h in enumerate(header))
    body = ""
    for r in rows:
        tds = ""
        for i, h in enumerate(header):
            v = str(r[i]).strip() if i < len(r) else ""
            base = (f"border:1px solid {c['border']};padding:10px 16px;color:{c['text']};"
                    f"white-space:nowrap;text-align:{'left' if i == 0 else 'right'};font-size:15px;")
            if i == 0:                                   # Date — freeze it so it stays while scrolling right
                base += f"position:sticky;left:0;z-index:1;background:{c['raised']};font-weight:800;"
            elif (i in _PCT_COLS or i in _CHG_COLS) and v and v not in ("0", "0.00%", "—"):
                base += f"color:{c['neg'] if _neg(v) else c['pos']};font-weight:800;"
            tds += f"<td style='{base}'>{v or '—'}</td>"
        body += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    # width:max-content lets the table keep its natural (wide) width so the many
    # columns overflow horizontally → a horizontal scrollbar to reach Total.
    return (f"<div style='overflow:auto;max-height:700px;border:1px solid {c['border']};border-radius:9px;'>"
            f"<table style='border-collapse:collapse;font-size:15px;width:max-content;min-width:100%;'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def render(c: dict) -> None:
    gran = st.radio("Granularity", ["Monthly", "Weekly", "Daily"], horizontal=True,
                    label_visibility="collapsed", key="perf_gran")

    if gran == "Monthly":
        df, series = benchmark.monthly_df()
        if not df.empty:
            st.markdown(benchmark.header_dollar(c, df, series, "monthly"), unsafe_allow_html=True)
            order = ["IRA", "LLC", "SPY", "QQQ"]
            colmap = {"IRA": c["gold"], "LLC": c["pos"], "SPY": c["blue"], "QQQ": c["muted"]}
            actcol = {"IRA": "ira_usd", "LLC": "llc_usd", "SPY": "s_lvl", "QQQ": "q_lvl"}
            dollar_keys = {"IRA", "LLC"}
            years = sorted(df["date"].dt.year.unique(), reverse=True)
            cols = st.columns(len(years)) if len(years) > 1 else [st]
            for col, y in zip(cols, years):
                ydf = df[df["date"].dt.year == y].sort_values("date").copy()
                ydf["mon"] = ydf["date"].dt.strftime("%b")
                b_i, b_l = ydf["ira_start"].iloc[0], ydf["llc_start"].iloc[0]
                b_s, b_q = ydf["spy_start"].iloc[0], ydf["qqq_start"].iloc[0]
                ydf["ira_usd"], ydf["llc_usd"] = ydf["IRA"], ydf["LLC"]     # month-end $ (tooltip)
                ydf["s_lvl"], ydf["q_lvl"] = ydf["SPY"], ydf["QQQ"]         # index points (tooltip)
                ydf["IRA"] = ydf["ira_usd"] / b_i * 100 if b_i else 100     # 100-index at Jan opening
                ydf["LLC"] = ydf["llc_usd"] / b_l * 100 if b_l else 100
                ydf["SPY"] = ydf["s_lvl"] / b_s * 100 if b_s else 100
                ydf["QQQ"] = ydf["q_lvl"] / b_q * 100 if b_q else 100
                col.markdown(benchmark.year_edge(c, ydf, y, order, colmap), unsafe_allow_html=True)
                anchor = pd.DataFrame([{"mon": "Start", "IRA": 100, "LLC": 100, "SPY": 100, "QQQ": 100,
                                        "ira_usd": b_i, "llc_usd": b_l, "s_lvl": b_s, "q_lvl": b_q}])
                keep = ["mon", "IRA", "LLC", "SPY", "QQQ", "ira_usd", "llc_usd", "s_lvl", "q_lvl"]
                aydf = pd.concat([anchor, ydf[keep]], ignore_index=True)
                col.altair_chart(benchmark.growth_chart(c, aydf, order, colmap, actcol, dollar_keys),
                                 use_container_width=True)

    elif gran == "Weekly":
        dwk, series = benchmark.scoreboard_df("W")    # Mine/Rayan/SPY growth-of-$100, weekly
        dday, _ = benchmark.scoreboard_df("D")         # daily — for each month's true opening
        if not dwk.empty:
            dwk["month"] = dwk["date"].dt.to_period("M")
            mlabels = {p.strftime("%B %Y"): p for p in sorted(dwk["month"].unique(), reverse=True)}
            pick = st.selectbox("Month", list(mlabels) + ["All weeks"], key="perf_wk_month")
            keep = ["wk"] + series
            if pick == "All weeks":
                wdf, lbl = benchmark.rebase(dwk, series)[keep].copy(), "all weeks"
            else:
                p = mlabels[pick]
                wdf, lbl = dwk[dwk["month"] == p].copy(), pick
                prior = dday[dday["date"] < p.start_time]      # last close before the month
                if not prior.empty:
                    base = prior.iloc[-1]                       # month opening = 0% anchor
                    for k in series:
                        wdf[k] = wdf[k] / base[k] * 100 if base[k] else 100
                    anchor = pd.DataFrame([{"wk": "Start", **{k: 100.0 for k in series}}])
                    wdf = pd.concat([anchor, wdf[keep]], ignore_index=True)
                else:
                    wdf = benchmark.rebase(wdf, series)[keep].copy()
            colmap = {"Mine": c["gold"], "Rayan": c["accent"], "SPY": c["blue"]}
            actcol = {k: k for k in series}
            st.markdown(benchmark.header_index(c, wdf, series, lbl, colmap), unsafe_allow_html=True)
            st.altair_chart(benchmark.growth_chart(c, wdf, series, colmap, actcol,
                            dollar_keys=set(series), x_field="wk", x_title="Week",
                            y_title="Up / down since the month's start (0%)",
                            actual_title="Value per $100 start"), use_container_width=True)

    else:  # Daily — pick a month
        df, series = benchmark.scoreboard_df("D")
        if not df.empty:
            months = sorted(df["date"].dt.to_period("M").unique(), reverse=True)
            labels = {p.strftime("%B %Y"): p for p in months}
            pick = st.selectbox("Month", list(labels), key="perf_day_month")
            mdf = df[df["date"].dt.to_period("M") == labels[pick]]
            mdf = benchmark.rebase(mdf, series)
            colmap = {"Mine": c["gold"], "Rayan": c["accent"], "SPY": c["blue"]}
            st.markdown(benchmark.header_index(c, mdf, series, pick, colmap), unsafe_allow_html=True)
            st.altair_chart(benchmark.chart(c, mdf, series, mode="index", x_fmt="%b %d",
                                            tip_fmt="%b %d, %Y"), use_container_width=True)

    # The full monthly IRA·LLC·SPY·QQQ table lives under the Monthly view.
    if gran == "Monthly":
        grid = _grid()
        if not grid.empty and len(grid) >= 3:
            rows = grid.values.tolist()
            st.write("")
            st.markdown(_summary_cards(c, rows[0]), unsafe_allow_html=True)
            hdr = [str(x).strip() for x in rows[1]]
            data = [r for r in rows[2:] if str(r[0]).strip()]
            st.markdown(_table(c, hdr, data), unsafe_allow_html=True)
