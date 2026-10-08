"""Reference — 3-Tier Entry Logic & 60% Deployment study.

Documented at Jigar's request (Oct 2026). This is a RESEARCH / PROPOSAL view: it sits
alongside the locked framework (it does not replace the retired Stage-7 ladder or the
9/30 'deployment & cash are outputs, not dials' amendment). Drop the banner in render()
if it is ever promoted to locked reference.
"""

from __future__ import annotations

import streamlit as st


def _tbl(c: dict, headers: list, rows: list, bolds: set | None = None) -> str:
    """A themed HTML table. `bolds` = set of row indices rendered bold (totals)."""
    bolds = bolds or set()
    th = "".join(
        f"<th style='background:{c['raised']};color:{c['text']};border:1px solid {c['border']};"
        f"padding:8px 12px;text-align:{'left' if i == 0 else 'left'};font-size:12px;font-weight:700;"
        f"white-space:nowrap'>{h}</th>" for i, h in enumerate(headers))
    body = ""
    for ri, r in enumerate(rows):
        strong = ri in bolds
        tds = ""
        for ci, cell in enumerate(r):
            fw = "800" if (strong or ci == 0) else "500"
            col = c["text"]
            tds += (f"<td style='border:1px solid {c['border']};padding:7px 12px;color:{col};"
                    f"font-weight:{fw};font-size:12.5px;vertical-align:top'>{cell}</td>")
        bg = f"background:{c['raised']}55;" if strong else ""
        body += f"<tr style='{bg}'>{tds}</tr>"
    return (f"<table style='border-collapse:collapse;width:100%;margin:6px 0 14px'>"
            f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")


def _h(c: dict, txt: str) -> str:
    return (f"<div style='font-size:16px;font-weight:800;color:{c['text']};"
            f"margin:18px 0 6px'>{txt}</div>")


def _p(c: dict, txt: str) -> str:
    return f"<div style='font-size:13px;color:{c['text']};line-height:1.55;margin:4px 0 8px'>{txt}</div>"


def render(c: dict) -> None:
    b = c.get("muted", "#888")
    pos, neg = c.get("pos", "#2f7e25"), c.get("neg", "#b62027")

    banner = (f"<div style='border-left:4px solid {c.get('gold', '#b8860b')};background:"
              f"{c.get('gold', '#b8860b')}1a;border-radius:8px;padding:9px 13px;margin-bottom:14px;"
              f"font-size:12px;color:{c['text']}'>"
              f"<b>Study / proposal — not locked.</b> Documented for reference. It sits alongside the "
              f"locked framework and does <b>not</b> replace the retired Stage-7 ladder or the 9/30 "
              f"amendment (deployment & cash are <i>outputs</i>, not dials). Validate before acting.</div>")

    # ── 3-Tier Entry Logic ──
    tier = _tbl(c,
                ["Step", "Condition", "Action"],
                [["1", "Growth setup fires at 47%+", "<b>Take it</b> (no cap unless Growth tier full)"],
                 ["2", "No 47% setup fires today", "<b>Try Mid (40%)</b> — max 1–2 trades"],
                 ["3", "No 40% either", "<b>Try Core (36%)</b> — max 1–2 trades"],
                 ["4", "<b>Ahead of pace by Tuesday</b>", "<b>STOP at 47%</b> — don't drop to lower tiers"]])

    # ── Why This Exists ──
    why = (_p(c, "<b>The GTC connection:</b> before GTC, deployment was sticky — you can't un-deploy "
              "a 25-day CSP. The GTC ladder (100% coverage, 25–40% remaining BTC) made deployment "
              "<b>fluid</b> — capital turns over in days. That makes lower-AOR tiers thinkable: you're "
              "not trapped if you take a sub-optimal entry.")
           + _p(c, "<b>The core thesis:</b> lower tiers are <b>time-weighted insurance against "
                "zero-fill weeks</b>, not permanent floor relaxation. They prevent the Thursday "
                "\"behind pace\" pressure that forces bad trades."))

    # ── $16–18K floor ──
    floor = _p(c, "Maintain <b>$16–18K of open outstanding premium at all times</b> (the fuel floor) "
               "— roughly <b>42–45 open positions</b>. Snapshot at writing: 39 positions / $13.7K open.")

    prem = _tbl(c,
                ["Blend", "Monthly", "% ATH"],
                [["All 47%", "$40.3K", "2.35%"],
                 ["<b>3-tier (41%)</b>", "<b>$35.1K</b>", "<b>2.05%</b>"],
                 ["Realistic (10/15/35 split, blend 44%)", "$37.6K", "2.19%"]],
                bolds={1})

    # ── Why 60% is safe ──
    research = _p(c, "<b>93-week research:</b> 47% is <b>not</b> the choke on the core list — 3 zero-weeks "
                  "out of 93, median 8 qualifying names/week. The 40% floor adds effectively nothing.")
    stress = _tbl(c,
                  ["", "2025 actual", "Framework at 60%"],
                  [["Feb loss", f"<span style='color:{neg}'>−$45K (−6.6%)</span>",
                    f"<span style='color:{neg}'>−$31K (−4.5%)</span>"],
                   ["Mar loss", f"<span style='color:{neg}'>−$71K (−11.3%)</span>",
                    f"<span style='color:{neg}'>−$21K (−3%)</span>"],
                   ["<b>Combined</b>", f"<b style='color:{neg}'>−$116K (−17.9%)</b>",
                    f"<b style='color:{neg}'>−$52K (−7.5%)</b>"]],
                  bolds={2})
    reduction = _p(c, f"<b style='color:{pos}'>55% drawdown reduction.</b> The framework holds at 60%.")

    protections = (f"<ol style='font-size:13px;color:{c['text']};line-height:1.7;margin:4px 0 8px 18px'>"
                   "<li><b>5% name cap</b> → kills single-name blowup</li>"
                   "<li><b>RSI &lt; 64 + below BB mid</b> → blocks momentum tops</li>"
                   "<li><b>60% deployment ceiling</b> → smaller base when it drops</li>"
                   "<li><b>Breaker freeze at 45%</b> → stops the bleed in month 2</li></ol>")

    gate3 = _p(c, "<b>Gate 3 (RSI &lt; 64 + below BB mid) is the real safety filter.</b> A red day serves "
               "AOR <i>quality</i> more than safety. Entries on green days with Gate 3 passing are "
               "structurally safer than they feel.")

    html = (banner
            + _h(c, "3-Tier Entry Logic — the entry priority") + tier
            + _h(c, "Why this exists") + why
            + _h(c, "The $16–18K premium floor") + floor
            + _h(c, "Monthly premium at 60% deployment") + prem
            + _p(c, f"<span style='color:{b}'>All above the 1.5% goal, with buffer.</span>")
            + _h(c, "Why 60% deployment is safe") + research
            + _p(c, "<b>Feb-stress projection</b> (if 2025 had run at 60% + the framework):") + stress + reduction
            + _h(c, "The 4 compounding protections") + protections
            + _h(c, "Critical insight — Gate 3 vs red day") + gate3)

    st.markdown(html, unsafe_allow_html=True)
