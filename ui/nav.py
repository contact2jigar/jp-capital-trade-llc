"""WheelEngine navigation — grouped sections (sidebar order) + routing."""

from __future__ import annotations

# TOP tabs — the WheelEngine daily flow. Candidate Scanner is now a Tool (discovery,
# occasional — it builds the WatchList), so it's off the daily top nav.
TOP: list[tuple[str, str]] = [
    ("Cockpit", "🛰️"),
    ("Trade Positions", "📒"),
    ("Decision Desk", "⚖️"),
    ("LEAP Scanner", "🚀"),
]

# LEFT sidebar groups → [(label, icon, target_page)]. "Command Center" points back to
# the WheelEngine home so we don't need a Back button on every page.
SIDE_GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "WHEEL STRATEGY": [
        ("Command Center", "🎛️", "Cockpit"),              # home → the Cockpit (Board)
        ("P/L", "📊", "P/L"),
        ("Performance", "📈", "Performance"),
        ("Allocation", "🧮", "Allocation"),
    ],
    "ANALYSIS": [
        ("Price Wall Map", "🧱", "Price Wall Map"),
        ("Seasonality", "📅", "Seasonality"),
    ],
    "TOOLS": [
        ("Candidate Scanner", "🔎", "Candidate Scanner"),   # discovery → build the WatchList
        ("Reconcile", "🔄", "Reconcile"),
        ("Report", "📄", "Report"),
    ],
    "REFERENCE": [
        ("Framework 2.0", "🎯", "Framework 2.0"),
        ("Risk Gates", "🛡️", "Risk Gates"),
        ("Entry Setup", "📊", "Entry Setup"),
        ("3-Tier & Deployment", "🪜", "3-Tier & Deployment"),
        ("Financials", "💵", "Financials"),
    ],
    "LEGACY": [   # classic views — phasing out
        ("Portfolio Center", "🏦", "Portfolio Center"),
        ("Cockpit (Classic)", "🛰️", "Cockpit (Classic)"),
    ],
}

ROUTES: dict[str, str] = {
    "Portfolio Center":  "ui.pages.command_center",
    "Cockpit":           "ui.pages.cockpit_board",       # the Board is now the Cockpit
    "Cockpit (Classic)": "ui.pages.cockpit",             # old instrument view — phasing out
    "Trade Positions":   "ui.pages.trade_position",
    "Candidate Scanner": "ui.pages.csp_scanner",
    "LEAP Scanner":      "ui.pages.leap_scanner",
    "Decision Desk":     "ui.pages.candidate_hunt",
    "P/L":               "ui.pages.pl",
    "Performance":       "ui.pages.performance",
    "Allocation":        "ui.pages.allocation",
    "Price Wall Map":    "ui.pages.price_wall_map",
    "Seasonality":       "ui.pages.seasonality",
    "Reconcile":         "ui.pages.reconcile",
    "Report":            "ui.pages.report",
    "Entry Setup":       "ui.pages.entry_setup",
    "Risk Gates":        "ui.pages.risk_gates",
    "Framework 2.0":     "ui.pages.ref_framework2",
    "3-Tier & Deployment": "ui.pages.ref_tier_deploy",
    "Financials":        "ui.pages.financials_ref",
}

DEFAULT = "Cockpit"
