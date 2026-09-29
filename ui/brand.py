"""JP Capital & Trade brand mark — the 'Ascending Trade' logo, one source of truth.

A gold JP over a rising chart + breakout arrow, on a dark rounded tile. Used inline
in the sidebar icon and the top-bar brand, and written to assets/logo.svg for the
browser / iPhone favicon. The tile is part of the mark, so it reads on any surface."""

from __future__ import annotations

from pathlib import Path

GOLD = "#e3b23c"     # JP + bars
ARROW = "#f8fafc"    # breakout line
TILE = "#141b24"     # dark rounded ground
EDGE = "#2c3a48"     # tile border
# Back-compat aliases (older callers referenced these names).
RING = EDGE
JP = GOLD

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
FAVICON_PATH = str(_ASSETS / "logo.svg")


def _mark_inner() -> str:
    """The full mark in a 100×100 viewBox — JP hero, rising bars, breakout arrow,
    on a dark rounded tile (so it sits on light or dark surfaces alike)."""
    tile = (f'<rect x="3" y="3" width="94" height="94" rx="22" fill="{TILE}" '
            f'stroke="{EDGE}" stroke-width="1.5"/>')
    jp = ('<text x="50" y="41" text-anchor="middle" '
          'font-family="Arial, Helvetica, sans-serif" font-weight="800" '
          f'font-size="37" letter-spacing="-1.5" fill="{GOLD}">JP</text>')
    bars = (f'<rect x="28" y="72" width="11" height="8" rx="2" fill="{GOLD}" opacity="0.5"/>'
            f'<rect x="44.5" y="65" width="11" height="15" rx="2" fill="{GOLD}" opacity="0.78"/>'
            f'<rect x="61" y="58" width="11" height="22" rx="2" fill="{GOLD}"/>')
    arrow = (f'<path d="M28 69 L50 60 L61 63 L79 52" fill="none" stroke="{ARROW}" '
             'stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>'
             f'<path d="M79 52 L79 61 M79 52 L70 52" fill="none" stroke="{ARROW}" '
             'stroke-width="3.2" stroke-linecap="round"/>')
    return tile + jp + bars + arrow


def gearframe(size: int = 26, ring: str = RING, jp: str = JP) -> str:
    """Inline SVG mark at the requested pixel size (name kept for back-compat)."""
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="JP Capital & Trade">{_mark_inner()}</svg>')


def favicon_svg() -> str:
    """App-tile version for the favicon — the mark already carries its dark tile."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            f'{_mark_inner()}</svg>')


def write_favicon() -> str:
    """Write assets/logo.svg (idempotent) and return its path for page_icon."""
    _ASSETS.mkdir(exist_ok=True)
    Path(FAVICON_PATH).write_text(favicon_svg(), encoding="utf-8")
    return FAVICON_PATH
