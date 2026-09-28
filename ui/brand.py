"""JP Capital & Trade brand mark — the 'Gearframe' logo, one source of truth.

Steel gear ring + gold "JP" monogram. Used inline in the sidebar icon and the
top-bar brand, and written to assets/logo.svg for the browser / iPhone favicon.
"""

from __future__ import annotations

from pathlib import Path

RING = "#8aa0b8"   # steel
JP = "#e3b23c"     # gold

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
FAVICON_PATH = str(_ASSETS / "logo.svg")


def _gear_inner(ring: str, jp: str) -> str:
    """Teeth + ring + JP, centered in a 100×100 viewBox (no background)."""
    teeth = "".join(
        f'<rect x="44" y="5" width="12" height="13" rx="2" fill="{ring}" '
        f'transform="rotate({a} 50 50)"/>' for a in range(0, 360, 45))
    return (f'{teeth}'
            f'<circle cx="50" cy="50" r="33" fill="none" stroke="{ring}" stroke-width="6"/>'
            f'<text x="50" y="62" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="34" font-weight="700" fill="{jp}">JP</text>')


def gearframe(size: int = 26, ring: str = RING, jp: str = JP) -> str:
    """Inline SVG mark on a transparent ground (sits on themed surfaces)."""
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="JP Capital & Trade">{_gear_inner(ring, jp)}</svg>')


def favicon_svg() -> str:
    """App-tile version: navy rounded square so it reads on any browser chrome."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect width="100" height="100" rx="22" fill="#141b24"/>'
            f'{_gear_inner(RING, JP)}</svg>')


def write_favicon() -> str:
    """Write assets/logo.svg (idempotent) and return its path for page_icon."""
    _ASSETS.mkdir(exist_ok=True)
    Path(FAVICON_PATH).write_text(favicon_svg(), encoding="utf-8")
    return FAVICON_PATH
