"""Single source of truth for the Google Sheet the app reads.

WHY THIS FILE EXISTS
--------------------
Every module that touches the WatchList imports from here, so replacing the sheet
in the future is a ONE-LINE change: update ``WORKBOOK_ID`` below and nothing else.

Google preserves each tab's gid when you "Make a copy" of a workbook — only the
workbook (file) ID changes. Verified 2026-09-13: after a fresh copy, the WatchList
tab kept gid 337359953; just the file ID changed. So the ``TABS`` gids below stay
valid across copies and normally never need touching.

SHARING REQUIREMENT
-------------------
The app reads the sheet through the public CSV-export URL, so the workbook must be
shared **"Anyone with the link → Viewer"** (Share → General access). A fresh copy
starts private; if reads fail with an HTML sign-in page instead of data, re-check
this setting.
"""

from __future__ import annotations

# The workbook (file) ID — the ONLY thing that changes on a fresh copy.
WORKBOOK_ID = "1--5d-n6PbCs9wFigk_LRwJ7aEfGKr5mB2zGGGIuiL0E"

# Logical tab name → gid. Stable across copies; edit only if a tab is recreated.
TABS: dict[str, str] = {
    "watchlist": "337359953",
    "tradelog": "1662549766",
    "monitorboard": "700303030",
    "performance": "1485071492",
}


def gid(tab: str) -> str:
    """gid for a named tab (KeyError if the name isn't registered above)."""
    return TABS[tab]
