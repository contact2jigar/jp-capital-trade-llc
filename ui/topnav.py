"""WheelEngine top nav — horizontal tab bar (matches the POC), URL-driven.

The 5 main sections live across the top of the main area as tabs. The left
sidebar stays (brand · theme · future tools). Every link carries
`?nav=<Page>&theme=<Theme>` so both survive each click.
"""

from __future__ import annotations

import streamlit as st

from ui import brand, nav

_MARK = (f'<span style="display:inline-flex;vertical-align:middle;margin-right:8px;">'
         f'{brand.gearframe(22)}</span>')


def _href(page: str, theme: str) -> str:
    return f"?nav={page.replace(' ', '%20')}&theme={theme}"


def render_topnav(active: str, theme: str) -> None:
    # WheelEngine tabs show only on the WheelEngine pages. On Tools / Reference pages
    # there's no top bar — the sidebar "Command Center" link takes you back.
    top_names = {name for name, _ in nav.TOP}
    if active not in top_names:
        # Tools / Reference page → a brand + page title instead of the workflow tabs.
        st.markdown(
            f'<div class="tn-wrap"><div class="tn-title">{_MARK}Wheel<span class="eng">Engine</span>'
            f'<span class="tn-title-sub">&nbsp;by JP Capital &amp; Trade</span>'
            f'<span class="tn-title-page">&nbsp;—&nbsp;{active}</span></div></div>',
            unsafe_allow_html=True)
        return
    inner = ""
    for name, icon in nav.TOP:
        cls = "tn-tab active" if name == active else "tn-tab"
        inner += (f'<a href="{_href(name, theme)}" target="_self" class="{cls}">'
                  f'{icon}&nbsp;{name}</a>')
    brand_html = (f'<div class="tn-brand-inline">{_MARK}Wheel<span class="eng">Engine</span>'
                  '<span class="tn-title-sub">&nbsp;by JP Capital &amp; Trade</span></div>')
    st.markdown(f'<div class="tn-wrap" style="justify-content:space-between;">'
                f'<div class="tn-tabs">{inner}</div>{brand_html}</div>',
                unsafe_allow_html=True)
