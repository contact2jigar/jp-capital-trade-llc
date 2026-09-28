"""📊 P/L — realized (Close Date) and by-entry (Open Date) drill-downs."""

from __future__ import annotations

from ui.pages import command_center as cc


def render(c: dict) -> None:
    cc.render_pl(c)
