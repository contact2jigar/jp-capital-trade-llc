"""WheelEngine navigation — grouped sections (sidebar order) + routing."""

from __future__ import annotations

# TOP tabs — the WheelEngine daily flow. Candidate Scanner is now a Tool (discovery,
# occasional — it builds the WatchList), so it's off the daily top nav.
TOP: list[tuple[str, str]] = [
    ("Cockpit", "🛰️"),
    ("Trade Positions", "📒"),
    ("Decision Desk", "⚖️"),
    ("LEAP Scanner", "🚀"),
    ("Day Predictor", "🔮"),
]

# LEFT sidebar groups → [(label, icon, target_page)]. "Command Center" points back to
# the WheelEngine home so we don't need a Back button on every page.
#
# TOP of the side menu mirrors the iPhone app's page order (the clean daily flow
# Jigar prefers) + Reconcile pulled up here because it's his most-used tool. Pages
# that exist only on the web (portfolio analytics, scanners, reference) sit BELOW,
# so the menus feel like one product. iPhone order:
#   Cockpit · Trade Log · Trade Radar · Day Predictor · Recovery · Projection ·
#   Scope · BB Reversion · Price Wall · Seasonality
SIDE_GROUPS: dict[str, list[tuple[str, str, str]]] = {
    # Labels mirror the iPhone app EXACTLY; the 3rd tuple item is the (unchanged) route key.
    # Cockpit stands alone at the TOP (no header), like the iPhone.
    "": [
        ("Cockpit", "🎛️", "Cockpit"),                     # was "Command Center"
    ],
    "STRATEGY": [                                          # iPhone "STRATEGY" group
        ("Trade Log", "📒", "Trade Positions"),            # iPhone label; routes to Trade Positions
        ("Trade Radar", "📡", "Decision Desk"),            # iPhone label; routes to Decision Desk
        ("Day Predictor", "🔮", "Day Predictor"),
        ("Recovery Tool", "🛟", "Recovery Tool"),
        ("Projection", "🎯", "Projection"),
        ("Reconcile", "🔄", "Reconcile"),                  # most-used → kept here (web-only)
    ],
    "RESEARCH": [                                          # iPhone "RESEARCH" group
        ("Scope", "🔭", "Stock Scope"),                    # iPhone label; routes to Stock Scope
        ("BB Reversion", "⤵️", "BB Reversion"),
        ("Price Wall", "🏛️", "Price Wall Map"),            # iPhone label; routes to Price Wall Map
        ("Seasonality", "📅", "Seasonality"),
        ("Scoreboard", "🏁", "Scoreboard"),                # wheel vs SPY: WTD/MTD/since-Sep + weekly
        ("Market Pulse", "📰", "Market Pulse"),            # why's the market up/down today — Gemini vs Claude
    ],
    # ── below here = web-only (not on the iPhone app) ──
    "PORTFOLIO": [
        ("P/L", "📊", "P/L"),
        ("Performance", "📈", "Performance"),
        ("Allocation", "🧮", "Allocation"),
    ],
    "TOOLS": [
        ("CSP Planner", "🧭", "CSP Planner"),               # type tickers → put ladder (Δ band × weeks)
        ("LEAP Scanner", "🚀", "LEAP Scanner"),
        ("Candidate Scanner", "🔎", "Candidate Scanner"),   # discovery → build the WatchList
        ("Report", "📄", "Report"),
    ],
    "REFERENCE": [
        ("Framework 2.0", "🎯", "Framework 2.0"),
        ("Risk Gates", "🛡️", "Risk Gates"),
        ("Entry Setup", "📊", "Entry Setup"),
        ("3-Tier & Deployment", "🪜", "3-Tier & Deployment"),
        ("Financials", "💵", "Financials"),
    ],
}

# NOTE: command_center.py and cockpit.py are no longer menu pages, but both stay in
# the tree as SHARED code — command_center.board_data + cockpit's palettes/helpers are
# imported by cockpit_board, pl, leap_scanner, trade_position and day_predictor.
ROUTES: dict[str, str] = {
    "Cockpit":           "ui.pages.cockpit_board",       # the Board is the Cockpit
    "Trade Positions":   "ui.pages.trade_position",
    "Candidate Scanner": "ui.pages.csp_scanner",
    "LEAP Scanner":      "ui.pages.leap_scanner",
    "Decision Desk":     "ui.pages.candidate_hunt",
    "Day Predictor":     "ui.pages.day_predictor",
    "P/L":               "ui.pages.pl",
    "Performance":       "ui.pages.performance",
    "Projection":        "ui.pages.projection",
    "Recovery Tool":     "ui.pages.recovery",
    "Market Pulse":      "ui.pages.market_pulse",
    "CSP Planner":       "ui.pages.csp_planner",
    "Allocation":        "ui.pages.allocation",
    "Stock Scope":       "ui.pages.stock_scope",
    "BB Reversion":      "ui.pages.bb_reversion",
    "Price Wall Map":    "ui.pages.price_wall_map",
    "Seasonality":       "ui.pages.seasonality",
    "Scoreboard":        "ui.pages.scoreboard",
    "Reconcile":         "ui.pages.reconcile",
    "Report":            "ui.pages.report",
    "Entry Setup":       "ui.pages.entry_setup",
    "Risk Gates":        "ui.pages.risk_gates",
    "Framework 2.0":     "ui.pages.ref_framework2",
    "3-Tier & Deployment": "ui.pages.ref_tier_deploy",
    "Financials":        "ui.pages.financials_ref",
}

DEFAULT = "Cockpit"
