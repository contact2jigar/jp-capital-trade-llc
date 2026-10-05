"""Financial Parameters — reference page.

The full quality framework, three tiers:
  A · TRADABILITY (F1–F5)      — the FinViz screen + weeklies: can I trade it at all?
  B · FINANCIAL QUALITY (F6–F11) — Rev · Inc · OCF · FCF · A>L · Net Cash (our badges)
  C · OWNERSHIP REVIEW          — Years-to-Clear, when a name carries net debt
These INFORM the decision; only the gates you set actually block a name."""

from __future__ import annotations

import streamlit as st

_NAVY = "#1b2c35"   # group header bar — reads on both Grey and Dark

# (group_id, accent, title, subtitle, badge, [(#, parameter, technical rule, purpose), ...])
_GROUPS = [
    ("A", "#3988d7", "TRADABILITY", "Can I trade it at all?", "F1–F5 · the screen", [
        ("F1", "🏢 Size", "Market Cap &gt; $2B", "Avoid fragile small companies"),
        ("F2", "💵 Price", "Stock Price &gt; $15", "Avoid weak premium and wide spreads"),
        ("F3", "💧 Liquidity", "Average Daily Volume &gt; 1M", "Supports fair entry and exit"),
        ("F4", "📅 Options", "Optionable = TRUE · Weeklies = TRUE", "Required for the Wheel strategy"),
        ("F5", "💰 Profit", "Net Profit Margin &gt; 0%", "Company is currently profitable"),
    ]),
    ("B", "#2f9e59", "FINANCIAL QUALITY", "Rev · Inc · OCF · FCF · A&gt;L · Net Cash",
     "4 gates + 2 review", [
        ("F6", "📈 Revenue", "Latest Quarter Revenue YoY &gt; 0%", "Sales growing vs the year-ago quarter"),
        ("F7", "🧾 Income", "Latest Quarter Net Income &gt; $0", "Business is currently profitable"),
        ("F8", "🔄 OCF", "Latest Quarter Operating Cash Flow &gt; $0", "Core operations generate cash"),
        ("F9", "🏭 FCF", "FCF = OCF − CapEx · positive preferred",
         "Cash kept after capex · review if negative (capex burn)"),
        ("F10", "⚖️ A&gt;L", "Total Assets &gt; Total Liabilities", "Assets cover total obligations"),
        ("F11", "🏦 Net Cash", "Net Cash = Cash − Total Debt", "Balance-sheet cushion · net debt → review"),
    ]),
    ("C", "#8b6bd1", "OWNERSHIP REVIEW", "Can the company carry or clear its debt?",
     "when net cash &lt; 0", [
        ("REVIEW", "⏱️ Years to Clear",
         "If Net Cash &lt; 0: Net Debt ÷ Annual FCF · If FCF ≤ 0: —",
         "How quickly internally-generated cash could clear the debt"),
    ]),
]


def _group_html(c: dict, gid: str, accent: str, title: str, sub: str, badge: str, rows: list) -> str:
    num = (f"<span style='display:grid;place-items:center;width:24px;height:24px;border-radius:50%;"
           f"background:{accent};color:#081116;font-size:11px;font-weight:900;flex-shrink:0;'>{gid}</span>")
    head = (f"<div style='display:flex;align-items:center;justify-content:space-between;gap:16px;"
            f"padding:11px 14px;background:{_NAVY};color:#fff;'>"
            f"<div style='display:flex;align-items:center;gap:10px;'>{num}"
            f"<div><strong style='font-size:13px;letter-spacing:.02em;'>{title}</strong>"
            f"<span style='color:#b9c5cc;font-size:11px;font-style:italic;'> · {sub}</span></div></div>"
            f"<span style='color:{accent};font-size:10px;font-weight:800;text-transform:uppercase;"
            f"white-space:nowrap;'>{badge}</span></div>")
    body = ""
    for fid, param, rule, why in rows:
        chip = (f"<code style='font-family:ui-monospace,SFMono-Regular,Consolas,monospace;"
                f"font-size:10.5px;background:{c['raised']};border:1px solid {c['border']};"
                f"border-radius:4px;padding:2px 6px;color:{c['text']};'>{rule}</code>")
        body += (
            f"<div style='display:grid;grid-template-columns:62px 1.35fr 2.5fr 2fr;gap:12px;"
            f"align-items:center;padding:11px 14px;border-top:1px solid {c['border_soft']};'>"
            f"<div style='color:{accent};font-weight:900;font-size:11px;'>{fid}</div>"
            f"<div style='color:{c['text']};font-weight:800;font-size:12.5px;'>{param}</div>"
            f"<div style='line-height:1.5;'>{chip}</div>"
            f"<div style='color:{c['muted']};font-size:11.5px;font-weight:600;line-height:1.4;'>{why}</div></div>")
    colhead = (
        f"<div style='display:grid;grid-template-columns:62px 1.35fr 2.5fr 2fr;gap:12px;"
        f"padding:8px 14px 4px;font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;"
        f"color:{c['muted']};font-weight:700;'>"
        f"<div>#</div><div>Parameter</div><div>Technical Rule</div><div>Purpose</div></div>")
    return (f"<div style='border:1px solid {c['border']};border-radius:12px;overflow:hidden;"
            f"background:{c['panel']};margin-top:12px;'>{head}{colhead}{body}</div>")


def render(c: dict) -> None:
    st.caption("The financial quality framework — **tradability · quality · ownership**. "
               "These inform the call; only the gates you set actually block a name.")

    groups = "".join(_group_html(c, *g) for g in _GROUPS)

    # Decision logic + status rules footer.
    def _part(strong, span):
        return (f"<div style='text-align:center;'>"
                f"<div style='color:{c['pos']};font-weight:800;font-size:12.5px;'>{strong}</div>"
                f"<div style='color:{c['muted']};font-size:10px;margin-top:3px;'>{span}</div></div>")
    plus = f"<div style='text-align:center;color:{c['pos']};font-size:18px;font-weight:900;'>+</div>"
    decision = (
        f"<div style='border:1px solid {c['border']};border-radius:12px;background:{c['panel']};"
        f"overflow:hidden;'>"
        f"<div style='padding:9px 13px;border-bottom:1px solid {c['border_soft']};background:{c['raised']};"
        f"font-size:11px;font-weight:800;color:{c['text']};'>Decision Logic</div>"
        f"<div style='display:grid;grid-template-columns:1fr 28px 1fr 28px 1fr;align-items:center;"
        f"padding:16px 14px;'>"
        f"{_part('F1–F5 PASS', 'Tradable universe')}{plus}"
        f"{_part('REV·INC·OCF·A&gt;L PASS', 'Financial quality')}{plus}"
        f"{_part('FCF + NET CASH', 'Comfortable to own')}</div></div>")
    status = (
        f"<div style='border:1px solid {c['border']};border-radius:12px;background:{c['panel']};"
        f"overflow:hidden;'>"
        f"<div style='padding:9px 13px;border-bottom:1px solid {c['border_soft']};background:{c['raised']};"
        f"font-size:11px;font-weight:800;color:{c['text']};'>Status Rules</div>"
        f"<ul style='margin:0;padding:11px 16px 13px 28px;color:{c['muted']};font-size:11px;line-height:1.6;'>"
        f"<li><b style='color:{c['text']};'>✅ Pass:</b> Rev, Inc, OCF and A&gt;L meet their rules.</li>"
        f"<li><b style='color:{c['text']};'>⚠️ Review:</b> negative FCF may be deliberate capex (e.g. AMZN).</li>"
        f"<li><b style='color:{c['text']};'>◻️ Missing:</b> show —; never count missing data as a pass.</li>"
        f"</ul></div>")
    footer = (f"<div style='display:grid;grid-template-columns:1.15fr .85fr;gap:12px;margin-top:14px;'>"
              f"{decision}{status}</div>")

    st.markdown(groups + footer, unsafe_allow_html=True)
