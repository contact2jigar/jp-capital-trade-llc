"""Shared WheelEngine UI pieces. Theme-aware — every builder takes the palette `c`."""

from __future__ import annotations


def _panel(c: dict, num: str, title: str, badge: str, cols: tuple, rows: list) -> str:
    """One side of a signal-stack card: numbered header + a mini grid.
    Each row: ((emoji, name), cell, ...) with one cell per non-name column."""
    grid = "1.05fr 1.75fr 0.9fr" if len(cols) == 3 else "1fr 1.8fr"
    head = "".join(
        f"<div style='font-size:10px;letter-spacing:.06em;text-transform:uppercase;"
        f"color:{c['muted']};font-weight:700;'>{h}</div>" for h in cols)
    body = ""
    for r in rows:
        emoji, name = r[0]
        cells = (f"<div style='color:{c['text']};font-weight:700;white-space:nowrap;'>"
                 f"{emoji}&nbsp;{name}</div>")
        for cell in r[1:]:
            cells += f"<div style='color:{c['mid']};font-size:12.5px;line-height:1.4;'>{cell}</div>"
        body += (f"<div style='display:grid;grid-template-columns:{grid};gap:10px;"
                 f"padding:10px 0;border-top:1px solid {c['border_soft']};'>{cells}</div>")
    return (
        f"<div style='background:{c['panel']};border:1px solid {c['border']};border-radius:12px;"
        f"padding:14px 16px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"padding-bottom:10px;border-bottom:1px solid {c['border']};'>"
        f"<div style='display:flex;align-items:center;gap:9px;'>"
        f"<span style='display:inline-flex;align-items:center;justify-content:center;width:22px;"
        f"height:22px;border-radius:50%;background:{c['nav_active_bg']};color:{c['nav_active_fg']};"
        f"font-size:12px;font-weight:800;'>{num}</span>"
        f"<span style='color:{c['text']};font-size:16px;font-weight:800;'>{title}</span></div>"
        f"<span style='color:{c['nav_active_fg']};font-size:11px;font-weight:800;letter-spacing:.06em;'>{badge}</span></div>"
        f"<div style='display:grid;grid-template-columns:{grid};gap:10px;padding:11px 0 2px;'>{head}</div>"
        f"{body}</div>")


def signal_stack_card(c: dict, *, title: str, note: str, left: dict, right: dict,
                      footer_text: str, verdict: str) -> str:
    """Two-panel 'Signal Stack' card (always shown). Returns HTML for st.markdown."""
    lp = _panel(c, left["num"], left["title"], left["badge"], left["cols"], left["rows"])
    rp = _panel(c, right["num"], right["title"], right["badge"], right["cols"], right["rows"])
    return (
        f"<div style='background:{c['bg']};border:1px solid {c['border']};border-radius:14px;"
        f"padding:14px 20px 18px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline;"
        f"padding-bottom:12px;border-bottom:1px solid {c['border_soft']};'>"
        f"<span style='color:{c['text']};font-size:20px;font-weight:800;'>{title}</span>"
        f"<span style='color:{c['muted']};font-size:13px;'>{note}</span></div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));"
        f"gap:16px;margin-top:16px;'>{lp}{rp}</div>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:14px;"
        f"background:{c['raised']};border:1px solid {c['border']};border-radius:11px;"
        f"padding:13px 18px;margin-top:16px;'>"
        f"<span style='color:{c['mid']};font-size:13.5px;'>{footer_text}</span>"
        f"<span style='background:#86efac;color:#08351b;font-weight:800;font-size:13px;"
        f"padding:6px 14px;border-radius:999px;white-space:nowrap;'>{verdict}</span></div>"
        f"</div>")


def _es_section_head(c: dict, num: str, title: str, badge: str) -> str:
    """Numbered-circle section header with a right-aligned count badge."""
    return (
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"padding:14px 18px;border-bottom:1px solid {c['border']};'>"
        f"<div style='display:flex;align-items:center;gap:11px;'>"
        f"<span style='display:inline-flex;align-items:center;justify-content:center;width:26px;"
        f"height:26px;border-radius:50%;background:{c['nav_active_bg']};color:{c['nav_active_fg']};"
        f"font-size:13px;font-weight:800;'>{num}</span>"
        f"<span style='color:{c['text']};font-size:17px;font-weight:800;'>{title}</span></div>"
        f"<span style='color:{c['nav_active_fg']};font-size:11px;font-weight:800;"
        f"letter-spacing:.08em;'>{badge}</span></div>")


def entry_setup_card(c: dict, *, setups: list, checks: list) -> str:
    """The Entry-Setup page: a full-width 'Entry Setup' table (colored per-row
    accent bar + numbered chip) over a 'Quality Filter' grid of cards.

    setups = [(accent, emoji, name, trigger_html, meaning), ...]
    checks = [(emoji, name, rule), ...]"""
    card = (f"background:{c['panel']};border:1px solid {c['border']};border-radius:14px;"
            f"overflow:hidden;")

    # ── Section 1: Entry Setup table ──────────────────────────────────────
    cols = ("Setup", "Trigger", "Meaning")
    grid = "1.15fr 2.4fr 1fr"
    head = "".join(
        f"<div style='font-size:10px;letter-spacing:.07em;text-transform:uppercase;"
        f"color:{c['muted']};font-weight:700;'>{h}</div>" for h in cols)
    rows_html = ""
    for i, (accent, emoji, name, trigger, meaning) in enumerate(setups, 1):
        chip = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                f"width:22px;height:22px;border-radius:50%;background:{accent};color:#0b0f14;"
                f"font-size:11px;font-weight:800;flex-shrink:0;'>{i}</span>")
        setup_cell = (f"<div style='display:flex;align-items:center;gap:9px;'>{chip}"
                      f"<span style='color:{c['text']};font-weight:700;white-space:nowrap;'>"
                      f"{emoji}&nbsp;{name}</span></div>")
        rows_html += (
            f"<div style='display:grid;grid-template-columns:{grid};gap:14px;align-items:center;"
            f"padding:12px 16px 12px 13px;border-top:1px solid {c['border_soft']};"
            f"border-left:3px solid {accent};'>"
            f"{setup_cell}"
            f"<div style='color:{c['mid']};font-size:12.5px;line-height:1.45;'>{trigger}</div>"
            f"<div style='color:{accent};font-size:12.5px;font-weight:700;'>{meaning}</div></div>")
    sec1 = (f"<div style='{card}'>"
            f"{_es_section_head(c, '1', 'Entry Setup', f'ANY 1 OF {len(setups)}')}"
            f"<div style='display:grid;grid-template-columns:{grid};gap:14px;"
            f"padding:9px 16px 4px 13px;'>{head}</div>{rows_html}</div>")

    # ── Section 2: Quality Filter grid ────────────────────────────────────
    cells = ""
    for emoji, name, rule in checks:
        cells += (
            f"<div style='display:flex;gap:11px;align-items:center;background:{c['raised']};"
            f"border:1px solid {c['border_soft']};border-radius:11px;padding:13px 15px;'>"
            f"<div style='font-size:19px;line-height:1;'>{emoji}</div>"
            f"<div><div style='color:{c['text']};font-weight:700;font-size:13.5px;'>{name}</div>"
            f"<div style='color:{c['mid']};font-size:12px;line-height:1.4;margin-top:1px;'>{rule}</div>"
            f"</div></div>")
    sec2 = (f"<div style='{card}margin-top:16px;'>"
            f"{_es_section_head(c, '2', 'Quality Filter', f'ALL {len(checks)} MUST PASS')}"
            f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));"
            f"gap:12px;padding:16px;'>{cells}</div></div>")

    return sec1 + sec2


def gates_table_card(c: dict, *, gates: list, footer: str) -> str:
    """Risk-Gates page — a full-width numbered table (colored per-row accent bar)
    over a red 'miss any' footer banner. Matches the Entry-Setup styling.

    gates = [(accent, emoji, name, rule, purpose), ...]"""
    card = (f"background:{c['panel']};border:1px solid {c['border']};border-radius:14px;"
            f"overflow:hidden;")
    cols = ("Gate", "Rule", "Purpose / Consequence")
    grid = "1.15fr 2.5fr 1.35fr"
    head = "".join(
        f"<div style='font-size:10px;letter-spacing:.07em;text-transform:uppercase;"
        f"color:{c['muted']};font-weight:700;'>{h}</div>" for h in cols)

    rows_html = ""
    for i, (accent, emoji, name, rule, purpose) in enumerate(gates, 1):
        chip = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                f"width:22px;height:22px;border-radius:50%;background:{accent};color:#0b0f14;"
                f"font-size:11px;font-weight:800;flex-shrink:0;'>{i}</span>")
        gate_cell = (f"<div style='display:flex;align-items:center;gap:9px;'>{chip}"
                     f"<span style='color:{c['text']};font-weight:700;white-space:nowrap;'>"
                     f"{emoji}&nbsp;{name}</span></div>")
        rows_html += (
            f"<div style='display:grid;grid-template-columns:{grid};gap:14px;align-items:center;"
            f"padding:13px 16px 13px 13px;border-top:1px solid {c['border_soft']};"
            f"border-left:3px solid {accent};'>"
            f"{gate_cell}"
            f"<div style='color:{c['mid']};font-size:12.5px;line-height:1.45;'>{rule}</div>"
            f"<div style='color:{c['text']};font-size:12.5px;font-weight:600;'>{purpose}</div></div>")

    header = (
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"padding:14px 18px;border-bottom:1px solid {c['border']};'>"
        f"<div style='display:flex;align-items:center;gap:10px;'>"
        f"<span style='font-size:18px;'>🛡️</span>"
        f"<span style='color:{c['text']};font-size:17px;font-weight:800;'>"
        f"{len(gates)} Portfolio Gates</span></div>"
        f"<span style='color:{c['muted']};font-size:12px;'>"
        f"All must stay green before opening a new CSP</span></div>")

    table = (f"<div style='{card}'>{header}"
             f"<div style='display:grid;grid-template-columns:{grid};gap:14px;"
             f"padding:9px 16px 4px 13px;'>{head}</div>{rows_html}</div>")

    banner = (f"<div style='text-align:center;background:{c['neg']}14;"
              f"border:1px solid {c['neg']}55;border-radius:12px;padding:15px;margin-top:16px;"
              f"color:{c['neg']};font-weight:800;font-size:15px;letter-spacing:.01em;'>{footer}</div>")
    return table + banner


def gates_card(c: dict, *, title: str, note: str, gates: list, footer: str) -> str:
    """A card of portfolio gates in a 2-column grid. gates = [(emoji, name, desc)]."""
    cells = ""
    for emoji, name, desc in gates:
        cells += (
            f"<div style='display:flex;gap:11px;background:{c['panel']};border:1px solid {c['border_soft']};"
            f"border-radius:11px;padding:12px 14px;'>"
            f"<div style='font-size:20px;line-height:1;'>{emoji}</div>"
            f"<div><div style='color:{c['text']};font-weight:700;font-size:14px;margin-bottom:2px;'>{name}</div>"
            f"<div style='color:{c['mid']};font-size:12.5px;line-height:1.45;'>{desc}</div></div></div>")
    return (
        f"<div style='background:{c['bg']};border:1px solid {c['border']};border-radius:14px;"
        f"padding:14px 20px 18px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline;"
        f"padding-bottom:12px;border-bottom:1px solid {c['border_soft']};'>"
        f"<span style='color:{c['text']};font-size:20px;font-weight:800;'>{title}</span>"
        f"<span style='color:{c['muted']};font-size:13px;'>{note}</span></div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));"
        f"gap:12px;margin-top:16px;'>{cells}</div>"
        f"<div style='text-align:center;background:{c['raised']};border:1px solid {c['neg']}55;"
        f"border-radius:11px;padding:13px;margin-top:16px;color:{c['neg']};font-weight:800;"
        f"letter-spacing:.02em;'>{footer}</div></div>")
