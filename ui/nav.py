"""WheelEngine navigation — grouped sections (sidebar order) + routing."""

from __future__ import annotations

# TOP tabs — the WheelEngine daily flow.
TOP: list[tuple[str, str]] = [
    ("Cockpit", "🛰️"),
    ("Trade Positions", "📒"),
    ("Decision Desk", "⚖️"),
    ("Candidate Scanner", "🔎"),
]

# LEFT sidebar groups → [(label, icon, target_page)]. "Command Center" points back to
# the WheelEngine home so we don't need a Back button on every page.
SIDE_GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "WHEEL STRATEGY": [
        ("Command Center", "🎛️", "Cockpit"),
        ("Portfolio Center", "🏦", "Portfolio Center"),   # classic board — phasing out
        ("P/L", "📊", "P/L"),
        ("Performance", "📈", "Performance"),
        ("Allocation", "🧮", "Allocation"),
    ],
    "ANALYSIS": [
        ("Price Wall Map", "🧱", "Price Wall Map"),
        ("Seasonality", "📅", "Seasonality"),
    ],
    "TOOLS": [
        ("Reconcile", "🔄", "Reconcile"),
        ("Report", "📄", "Report"),
    ],
    "REFERENCE": [
        ("Entry Setup", "📊", "Entry Setup"),
        ("Risk Gates", "🛡️", "Risk Gates"),
    ],
}

ROUTES: dict[str, str] = {
    "Portfolio Center":  "ui.pages.command_center",
    "Cockpit":           "ui.pages.cockpit",
    "Trade Positions":   "ui.pages.trade_position",
    "Candidate Scanner": "ui.pages.csp_scanner",
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
}

DEFAULT = "Cockpit"
