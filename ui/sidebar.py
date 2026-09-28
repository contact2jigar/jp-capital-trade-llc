"""WheelEngine sidebar — brand + anchor-link grouped nav + Dark/Grey toggle.

Everything is URL-driven (`?nav=<Page>&theme=<Theme>`) so both the active page
and the theme survive every click — no session state, no reset.
"""

from __future__ import annotations

import streamlit as st

from ui import brand, nav


def _href(page: str, theme: str) -> str:
    return f"?nav={page.replace(' ', '%20')}&theme={theme}"


def render_sidebar(c: dict, active: str, theme: str) -> None:
    with st.sidebar:
        html = (
            f'<div class="sb-logo"><div class="sb-logo-icon">{brand.gearframe(26)}</div>'
            '<div><div class="sb-logo-title">Wheel<span class="eng">Engine</span></div>'
            '<div class="sb-logo-sub">by JP Capital &amp; Trade</div></div></div>'
        )
        for section, items in nav.SIDE_GROUPS.items():
            html += f'<span class="sb-section">{section}</span>'
            for label, icon, target in items:
                cls = "sb-item active" if target == active else "sb-item"
                html += (f'<a href="{_href(target, theme)}" target="_self" class="{cls}">'
                         f'{icon}&nbsp;&nbsp;{label}</a>')

        html += ('<div class="sb-tagline">Finds · sizes · ranks.<br>Never places an order.</div>'
                 '<span class="sb-section">Theme</span><div class="sb-themes">')
        for t, label in (("Dark", "🌙 Dark"), ("Grey", "◻︎ Grey")):
            tc = "sb-theme active" if t == theme else "sb-theme"
            html += f'<a href="{_href(active, t)}" target="_self" class="{tc}">{label}</a>'
        html += '</div>'

        st.markdown(html, unsafe_allow_html=True)
