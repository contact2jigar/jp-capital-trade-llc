"""WheelEngine — by JP Capital & Trade.

The unified wheel-trading cockpit: Command Center · CSP Scanner · Entry Setup ·
Risk Gates · Candidate Hunt. Finds · sizes · ranks — never places an order.

Run locally:   streamlit run app.py
Deploy:        push this folder to GitHub → Streamlit Cloud, main file = app.py.
               No secrets needed (the Google Sheet is read as a public CSV).

Scaffold: sidebar shell + Dark/Grey theme + empty templates. Each section renders
from ui/pages/<section>.py so we fill them one at a time.
"""

from __future__ import annotations

import importlib

import streamlit as st

from ui import brand                       # noqa: E402

st.set_page_config(page_title="WheelEngine", page_icon=brand.write_favicon(),
                   layout="wide", initial_sidebar_state="expanded")

from ui import nav                       # noqa: E402
from ui.sidebar import render_sidebar    # noqa: E402
from ui.topnav import render_topnav      # noqa: E402
from ui.theme import apply_theme         # noqa: E402

# ── State (URL-driven, so nav + theme survive every anchor click) ────────────
from ui.theme import PALETTES     # noqa: E402

page = st.query_params.get("nav", nav.DEFAULT)
if page not in nav.ROUTES:
    page = nav.DEFAULT
theme = st.query_params.get("theme", "Dark")
if theme not in PALETTES:
    theme = "Dark"

# ── Chrome ────────────────────────────────────────────────────────────────────
c = apply_theme(theme)            # inject CSS, return palette
render_sidebar(c, page, theme)
render_topnav(page, theme)        # top tabs = WheelEngine's 3 workflow sections

# ── Route ─────────────────────────────────────────────────────────────────────
module_path = nav.ROUTES.get(page)
if not module_path:
    st.error(f"Unknown page: {page}")
else:
    mod = importlib.import_module(module_path)
    try:
        importlib.reload(mod)                 # pick up edits without a full restart
    except Exception:
        mod = importlib.import_module(module_path)   # reload is best-effort, never fatal
    mod.render(c)
