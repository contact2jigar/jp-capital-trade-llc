"""WheelEngine theme — Dark / Grey palettes + CSS injection.

Sidebar uses the anchor-link nav style (grouped sections, blue active highlight
with a left accent bar) — same treatment as the JP Capital rebuild.
"""

from __future__ import annotations

import streamlit as st

PALETTES = {
    "Dark": {
        "bg": "#0a0e13", "panel": "#141b24", "raised": "#1b2531", "sidebar": "#0d131b",
        "border": "#28323f", "border_soft": "#1f2833",
        "text": "#e8eef4", "mid": "#b6c2cf", "muted": "#7d8b9a",
        "accent": "#3fd0c9", "pos": "#43c463", "neg": "#f2555a", "amber": "#e3a63a",
        "blue": "#58a6ff", "gold": "#e3b23c",
        "nav_active_bg": "#1f3a5f", "nav_active_fg": "#58a6ff", "nav_hover": "#1c2530",
        "input_bg": "#1b2531", "input_bd": "#3d4b5c",
    },
    # Grey = a LIGHT theme (matches the POC's grey-theme exactly).
    "Grey": {
        "bg": "#eef0f1", "panel": "#f4f5f6", "raised": "#d8dcde", "sidebar": "#e2e5e7",
        "border": "#aeb5ba", "border_soft": "#cfd5d9",
        "text": "#16212c", "mid": "#2c3a45", "muted": "#59646e",
        "accent": "#347fd1", "pos": "#2f7e25", "neg": "#b62027", "amber": "#8a6800",
        "blue": "#347fd1", "gold": "#b8860b",
        "nav_active_bg": "#d3e5fb", "nav_active_fg": "#14283c", "nav_hover": "#e1e4e6",
        "input_bg": "#ffffff", "input_bd": "#aeb5ba",
    },
}


def apply_theme(name: str) -> dict:
    """Inject the palette's CSS and return the palette dict."""
    c = PALETTES.get(name, PALETTES["Dark"])
    st.markdown(f"""<style>
      html {{ font-size: 13.5px; }}   /* scale the whole app down to fit more */
      .block-container {{ padding:2.2rem 2rem 2rem !important; max-width:100% !important; }}
      h1 {{ font-size:1.7rem !important; }} h2 {{ font-size:1.4rem !important; }}
      .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{
        background:{c['bg']} !important; color:{c['text']}; }}
      /* main-area text follows the theme (needed for the light Grey theme) */
      [data-testid="stMain"] .stMarkdown, [data-testid="stMain"] p,
      [data-testid="stMain"] li, [data-testid="stMain"] label,
      [data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 {{
        color:{c['text']} !important; }}
      [data-testid="stMain"] [data-testid="stCaptionContainer"] {{ color:{c['muted']} !important; }}
      [data-testid="stHeader"] {{ background:transparent; }}
      /* blue accent for selected fields (chips), primary buttons, sliders */
      [data-baseweb="tag"] {{ background:#347fd1 !important; }}
      [data-baseweb="tag"] span, [data-baseweb="tag"] svg {{ color:#fff !important; fill:#fff !important; }}
      .stButton > button[kind="primary"] {{ background:#347fd1 !important;
        border-color:#347fd1 !important; color:#fff !important; }}
      [data-testid="stSlider"] [role="slider"] {{ background:#347fd1 !important; }}
      /* download / secondary buttons follow the theme (were stuck dark on Grey) */
      .stDownloadButton > button, [data-testid="stDownloadButton"] > button {{
        background:{c['panel']} !important; color:{c['text']} !important;
        border:1px solid {c['border']} !important; font-weight:600 !important; }}
      .stDownloadButton > button:hover {{ border-color:{c['accent']} !important;
        color:{c['accent']} !important; }}
      /* input fields — distinct bg + clear border so fields read as fields (not scattered) */
      div[data-baseweb="select"] > div, div[data-baseweb="input"],
      .stNumberInput [data-baseweb="input"], .stTextInput [data-baseweb="input"] {{
        background:{c['input_bg']} !important; border:1px solid {c['input_bd']} !important;
        border-radius:9px !important; }}
      .stTextInput input, .stNumberInput input, [data-baseweb="base-input"],
      div[data-baseweb="input"] input {{ background:{c['input_bg']} !important; color:{c['text']} !important; }}
      div[data-baseweb="select"] div {{ color:{c['text']} !important; }}
      div[data-baseweb="select"] svg {{ fill:{c['muted']} !important; }}
      .stNumberInput button {{ background:{c['input_bg']} !important; border-color:{c['input_bd']} !important; }}
      .stNumberInput button svg {{ fill:{c['text']} !important; }}
      ul[role="listbox"], div[data-baseweb="popover"] ul, div[data-baseweb="menu"] {{
        background:{c['panel']} !important; border:1px solid {c['border']} !important; }}
      li[role="option"], ul[role="listbox"] li {{ color:{c['text']} !important; }}
      li[role="option"]:hover, ul[role="listbox"] li:hover {{ background:{c['nav_hover']} !important; }}
      section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div {{
        background:{c['sidebar']} !important; border-right:1px solid {c['border_soft']}; }}
      /* sidebar collapse («) + re-expand arrows — follow the theme (invisible on Grey) */
      [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"],
      [data-testid="collapsedControl"] {{ background:{c['nav_hover']} !important;
        border:1px solid {c['border']} !important; border-radius:8px !important; }}
      [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] *,
      [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapsedControl"] *,
      [data-testid="collapsedControl"], [data-testid="collapsedControl"] * {{ color:{c['text']} !important; }}
      [data-testid="stSidebarCollapseButton"] svg, [data-testid="stSidebarCollapseButton"] svg path,
      [data-testid="stSidebarCollapsedControl"] svg, [data-testid="stSidebarCollapsedControl"] svg path,
      [data-testid="collapsedControl"] svg, [data-testid="collapsedControl"] svg path {{
        color:{c['text']} !important; fill:{c['text']} !important; stroke:{c['text']} !important; }}

      .sb-logo {{ display:flex; align-items:center; gap:10px; padding:8px 8px 12px;
                  border-bottom:1px solid {c['border_soft']}; margin-bottom:6px; }}
      .sb-logo-icon {{ font-size:20px; width:34px; height:34px; border-radius:9px;
                       background:{c['nav_active_bg']}; display:flex; align-items:center;
                       justify-content:center; flex-shrink:0; }}
      .sb-logo-title {{ font-size:16px; font-weight:800; color:{c['text']}; line-height:1.15; }}
      .sb-logo-title .eng {{ color:{c['gold']}; }}
      .sb-logo-sub {{ font-size:10px; color:{c['muted']}; margin-top:1px; }}
      .sb-section {{ font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase;
                     color:{c['muted']}; padding:14px 6px 5px; display:block; }}
      .sb-item {{ display:flex !important; align-items:center !important; gap:8px;
                  padding:8px 12px !important; margin:2px 0 !important; border-radius:7px !important;
                  font-size:14px !important; color:{c['text']} !important; font-weight:600 !important;
                  text-decoration:none !important;
                  border-left:3px solid transparent !important; line-height:1.4 !important;
                  transition:background .1s, color .1s !important; }}
      .sb-item:hover {{ background:{c['nav_hover']} !important; color:{c['text']} !important;
                        border-left-color:{c['border']} !important; }}
      .sb-item.active {{ background:{c['nav_active_bg']} !important; color:{c['nav_active_fg']} !important;
                         font-weight:700 !important; border-left-color:{c['nav_active_fg']} !important; }}
      .sb-tagline {{ font-size:11px; color:{c['muted']}; padding:14px 6px 0;
                     border-top:1px solid {c['border_soft']}; margin-top:14px; }}
      .sb-themes {{ display:flex; gap:6px; padding:2px 0 6px; }}
      .sb-theme {{ flex:1; text-align:center; padding:6px 8px; border-radius:7px; font-size:12px;
                   text-decoration:none !important; border:1px solid {c['border']};
                   color:{c['mid']} !important; }}
      .sb-theme.active {{ background:{c['nav_active_bg']}; color:{c['nav_active_fg']} !important;
                          border-color:{c['nav_active_fg']}; font-weight:700; }}

      /* sub-tabs (Monitor Board / Trade Log / P/L) — active = solid pill, not a blendy tint */
      .stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid {c['border_soft']}; }}
      .stTabs [data-baseweb="tab"] {{ color:{c['muted']} !important; font-weight:600 !important;
        padding:6px 14px !important; border-radius:8px 8px 0 0 !important; }}
      .stTabs [data-baseweb="tab"] p {{ color:inherit !important; font-weight:inherit !important; }}
      .stTabs [aria-selected="true"] {{ background:transparent !important; }}
      .stTabs [aria-selected="true"] p {{ color:{c['accent']} !important; font-weight:800 !important; }}
      .stTabs [data-baseweb="tab-highlight"] {{ background:{c['accent']} !important; height:3px !important; }}

      /* expander (closable card) header — follow the theme (was dark on Grey) */
      [data-testid="stExpander"] details {{ background:{c['panel']} !important;
        border:1px solid {c['border']} !important; border-radius:12px !important; }}
      [data-testid="stExpander"] summary {{ background:{c['raised']} !important;
        color:{c['text']} !important; border-radius:12px 12px 0 0 !important; }}
      [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span,
      [data-testid="stExpander"] summary svg {{ color:{c['text']} !important; fill:{c['text']} !important; }}

      /* ── TOP NAV (horizontal tabs, main workflow sections) ── */
      .tn-wrap {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px;
                  padding:0 0 12px; margin-bottom:16px; border-bottom:1px solid {c['border_soft']}; }}
      .tn-tabs {{ display:flex; gap:8px; flex-wrap:wrap; }}
      .tn-tab {{ display:inline-flex; align-items:center; gap:5px; padding:9px 18px;
                 border-radius:11px; font-size:15px; font-weight:600; color:{c['mid']} !important;
                 text-decoration:none !important; border:1px solid transparent; white-space:nowrap;
                 transition:background .1s, border-color .1s, color .1s; }}
      .tn-tab:hover {{ background:{c['nav_hover']}; color:{c['text']} !important; }}
      .tn-tab.active {{ color:{c['nav_active_fg']} !important; border-color:{c['accent']};
                        background:{c['nav_active_bg']}; font-weight:800; }}
      .tn-title {{ font-size:18px; font-weight:800; color:{c['text']}; padding:4px 0;
                   display:flex; align-items:baseline; flex-wrap:wrap; }}
      .tn-title .eng {{ color:{c['gold']}; }}
      .tn-title-sub {{ font-size:13px; font-weight:600; color:{c['muted']}; }}
      .tn-title-page {{ font-size:15px; font-weight:800; color:{c['text']}; }}
      .tn-brand-inline {{ font-size:16px; font-weight:800; color:{c['text']}; white-space:nowrap;
                          display:flex; align-items:baseline; }}
      .tn-brand-inline .eng {{ color:{c['gold']}; }}
      .sb-soon {{ font-size:11.5px; color:{c['muted']}; padding:4px 8px 2px; line-height:1.45;
                  border:1px dashed {c['border']}; border-radius:8px; margin:4px 2px 0; }}

      .we-stub {{ border:1px dashed {c['border']}; background:{c['panel']}; border-radius:14px;
                  padding:44px; text-align:center; color:{c['muted']}; margin-top:10px; }}
      .we-stub b {{ color:{c['mid']}; }}
    </style>""", unsafe_allow_html=True)
    return c
