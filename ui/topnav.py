"""WheelEngine top nav — horizontal tab bar (matches the POC), URL-driven.

The 5 main sections live across the top of the main area as tabs. The left
sidebar stays (brand · theme · future tools). Every link carries
`?nav=<Page>&theme=<Theme>` so both survive each click.
"""

from __future__ import annotations

import streamlit as st

from ui import brand, nav

def _href(page: str, theme: str) -> str:
    return f"?nav={page.replace(' ', '%20')}&theme={theme}"


def _banner(active: str) -> None:
    """Full-width brand header (Banner A) — a dark command strip with a gold hairline,
    shown identically on every page; the current page name sits on the right."""
    st.markdown(
        '<div style="display:flex;align-items:center;gap:15px;padding:12px 20px;margin-bottom:12px;'
        'border-radius:12px;background:linear-gradient(90deg,#161f2b,#0e151d);'
        'border:1px solid #26333f;border-bottom:2px solid #e3b23c;'
        'box-shadow:0 10px 30px -22px #000;">'
        f'{brand.gearframe(40)}'
        '<span style="font-size:22px;font-weight:800;color:#e9eff5;letter-spacing:-.01em;'
        'font-family:\'IBM Plex Sans\',system-ui,sans-serif;">Wheel<span style="color:#e3b23c;">Engine</span></span>'
        '<span style="font-size:13px;color:#8aa0b8;">by JP Capital &amp; Trade</span>'
        f'<span style="margin-left:auto;font-size:16px;font-weight:700;color:#cfd8e0;'
        f'letter-spacing:.01em;">{active}</span>'
        '</div>', unsafe_allow_html=True)


def render_topnav(active: str, theme: str) -> None:
    _banner(active)                                       # persistent brand strip, every page
    top_names = {name for name, _ in nav.TOP}
    if active not in top_names:
        return                                            # banner already names the page
    inner = ""
    for name, icon in nav.TOP:
        cls = "tn-tab active" if name == active else "tn-tab"
        inner += (f'<a href="{_href(name, theme)}" target="_self" class="{cls}">'
                  f'{icon}&nbsp;{name}</a>')
    st.markdown(f'<div class="tn-wrap"><div class="tn-tabs">{inner}</div></div>',
                unsafe_allow_html=True)
