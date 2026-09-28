"""📒 Trade Position — the Trade Log (all open/closed wheel + LEAP positions)."""

from __future__ import annotations

from ui.pages import command_center as cc


def render(c: dict) -> None:
    cc.render_trade_log(c)
