"""WheelEngine PDF report — Monitor Board · Decision Desk (Action Queue) · P/L ·
Performance · Allocation, generated server-side with reportlab (no system deps,
so it works on Streamlit Cloud). One section per block, branded, dated.

The Portfolio Action Queue is the centerpiece (full table + GTC status).
"""

from __future__ import annotations

import datetime
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from logic import action_queue as aq
from logic import monitor as mb
from services import gsheet, yahoo

# Brand palette
NAVY = colors.HexColor("#141b24")
STEEL = colors.HexColor("#8aa0b8")
GOLD = colors.HexColor("#b8860b")
POS = colors.HexColor("#2f7e25")
NEG = colors.HexColor("#b62027")
INK = colors.HexColor("#16212c")
MUTE = colors.HexColor("#59646e")
LINE = colors.HexColor("#c9d0d6")
HEADBG = colors.HexColor("#e7ebee")
ZEBRA = colors.HexColor("#f4f6f7")

_styles = getSampleStyleSheet()
_H = ParagraphStyle("H", parent=_styles["Heading2"], textColor=INK, fontSize=13,
                    spaceBefore=10, spaceAfter=4)
_SUB = ParagraphStyle("SUB", parent=_styles["Normal"], textColor=MUTE, fontSize=8.5, spaceAfter=6)
_CELL = ParagraphStyle("CELL", parent=_styles["Normal"], fontSize=8, textColor=INK, leading=10)


def _money(v):
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _neg(s) -> bool:
    return str(s).strip().startswith("-") or "(" in str(s)


def _ascii(s) -> str:
    """Drop emoji / non-latin glyphs that the PDF core fonts can't render."""
    return "".join(ch for ch in str(s) if ord(ch) < 0x2190).strip()


def _table(header, rows, widths=None, right_cols=None, color_cols=None, align_first_left=True):
    """A styled reportlab Table. right_cols/color_cols are sets of column indices."""
    right_cols = right_cols or set()
    color_cols = color_cols or set()
    data = [header] + rows
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADBG),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
    ]
    for ci in right_cols:
        style.append(("ALIGN", (ci, 0), (ci, -1), "RIGHT"))
    # sign coloring on data cells of color_cols
    for r_i, row in enumerate(rows, start=1):
        for ci in color_cols:
            if ci < len(row):
                v = row[ci]
                if str(v).strip() not in ("", "—", "0", "0.00%"):
                    style.append(("TEXTCOLOR", (ci, r_i), (ci, r_i), NEG if _neg(v) else POS))
    return Table(data, colWidths=widths, repeatRows=1, style=TableStyle(style))


def _header_flow(story, subtitle):
    now = datetime.datetime.now().strftime("%b %d, %Y · %I:%M %p")
    brand = ParagraphStyle("BR", parent=_styles["Normal"], fontSize=16, textColor=INK, leading=18)
    story.append(Paragraph(
        '<font color="#16212c"><b>Wheel</b></font><font color="#b8860b"><b>Engine</b></font>'
        '<font color="#59646e" size="9">&nbsp;&nbsp;by JP Capital &amp; Trade</font>', brand))
    story.append(Paragraph(f'<font color="#59646e" size="8">{subtitle} &nbsp;·&nbsp; {now}</font>',
                           _styles["Normal"]))
    story.append(Spacer(1, 8))


# ── Sections ────────────────────────────────────────────────────────────────
def _monitor_section(story, board):
    story.append(Paragraph("Monitor Board", _H))
    story.append(Paragraph(
        f"VIX {board['vix']:.2f} · {board.get('trend', '')} · Allocation "
        f"{board.get('alloc', 0) * 100:.0f}% of Wheel Cap", _SUB))
    I, L = board["ira"], board["llc"]
    labels = [("Capital", "cap"), ("All-Time High", "ath"), ("Cash Vault (30% ATH)", "vault"),
              ("Wheel Capital", "wcap"), ("VIX Target", "vtgt"), ("Cash in Hand", "cih"),
              ("Deployed", "dep"), ("Covered Calls", "cc"), ("CSP", "csp"), ("LEAP", "leap"),
              ("Ready to Deploy", "rtd")]
    rows = [[lab, _money(I.get(k)), _money(L.get(k))] for lab, k in labels]
    story.append(_table(["Metric", "IRA", "LLC"], rows,
                        widths=[2.4 * inch, 1.6 * inch, 1.6 * inch], right_cols={1, 2}))
    story.append(Spacer(1, 6))
    # Gates + premium side note
    grow = [["CC Breaker", f"{I.get('ccbrk', 0) * 100:.1f}%", f"{L.get('ccbrk', 0) * 100:.1f}%"],
            ["CSP ITM", f"{I.get('cspitm', 0) * 100:.1f}%", f"{L.get('cspitm', 0) * 100:.1f}%"],
            ["LEAP %", f"{I.get('leappct', 0) * 100:.1f}%", f"{L.get('leappct', 0) * 100:.1f}%"]]
    story.append(_table(["Gate", "IRA", "LLC"], grow,
                        widths=[2.4 * inch, 1.6 * inch, 1.6 * inch], right_cols={1, 2}))
    story.append(Spacer(1, 6))
    prem = board.get("premium") or []
    prow = [[_ascii(lbl), _money(val)] for lbl, val in prem]
    story.append(Paragraph("Premium Tracker", _SUB))
    story.append(_table(["", "Amount"], prow, widths=[2.4 * inch, 1.6 * inch], right_cols={1}))


def _decision_section(story, board, aqres):
    story.append(Paragraph("Decision Desk", _H))
    prem = dict(board.get("premium") or [])
    wk_e = prem.get("💰 Wk Earned", 0); wk_g = prem.get("⏳ Wk Gap", 0)
    mo_e = prem.get("💰 Mo Earned", 0); mo_g = prem.get("⏳ Mo Gap", 0)
    gtc = aqres["cards"]["gtc"]; stuck = aqres["cards"]["stuck"]; cc = aqres["cards"]["cc"]
    answers = [
        ["1 · Are we earning?", f"Wk {_money(wk_e)} (gap {_money(wk_g)}) · Mo {_money(mo_e)} (gap {_money(mo_g)})"],
        ["2 · What is stuck?", f"{_money(stuck['value'])} · {stuck['count']} positions" if aqres["has_fidelity"] else "Upload Fidelity"],
        ["4 · Which GTCs are missing?", ("Upload GTC CSV" if not gtc.get("has_data")
                                         else (f"{gtc['missing']} missing" if gtc["missing"] else "All covered"))],
        ["5 · Which shares need a call?", (f"{cc['shares']} shares · max {cc['max']}" if aqres["has_fidelity"] and cc["shares"]
                                           else ("None" if aqres["has_fidelity"] else "Upload Fidelity"))],
    ]
    story.append(_table(["Question", "Answer"], answers, widths=[2.6 * inch, 6.4 * inch]))
    story.append(Spacer(1, 8))

    # Portfolio Action Queue — the centerpiece
    story.append(Paragraph("Portfolio Action Queue", _H))
    header = ["Ticker", "Acct", "Type", "Current", "Strike", "Qty", "Expiry", "GTC", "Action"]
    rows = []
    for r in sorted(aqres["rows"], key=lambda x: (x["ticker"], x["acct"])):
        rows.append([
            r["ticker"], r["acct"], r["type"],
            (f"${r['cur']:.2f}" if r.get("cur") else "—"),
            (f"${r['strike']:g}" if r.get("strike") else "—"),
            str(r["qty"]), r["expiry"] or "—", r["gtc"] or "—", r["action"] or "—"])
    widths = [0.8, 0.6, 0.6, 0.9, 0.8, 0.5, 1.0, 1.1, 1.4]
    t = _table(header, rows, widths=[w * inch for w in widths], right_cols={3, 4, 5})
    # color the GTC / Action columns by state
    ts = []
    for ri, r in enumerate(sorted(aqres["rows"], key=lambda x: (x["ticker"], x["acct"])), start=1):
        gcol = POS if r["gtc_state"] == "good" else (NEG if r["gtc_state"] == "bad" else INK)
        acol = NEG if r["action_state"] == "bad" else (GOLD if r["action_state"] == "warn" else POS)
        ts.append(("TEXTCOLOR", (7, ri), (7, ri), gcol))
        ts.append(("TEXTCOLOR", (8, ri), (8, ri), acol))
    if ts:
        t.setStyle(TableStyle(ts))
    story.append(t)


def _pl_section(story, df):
    story.append(Paragraph("P/L by Open Date", _H))
    mt = mb.monthly_totals(mb.pl_rollup(df, "Open Date"))
    rows = [[str(r["Year"]), r["Month"], _money(r["P/L"]), _money(r["Cash Release"]), str(int(r["Trades"]))]
            for _, r in mt.iterrows()]
    story.append(_table(["Year", "Month", "P/L", "Cash Release", "Trades"], rows,
                        widths=[1.0 * inch, 1.2 * inch, 1.6 * inch, 1.8 * inch, 1.0 * inch],
                        right_cols={2, 3, 4}, color_cols={2}))


def _performance_section(story):
    grid = gsheet.performance()
    if grid.empty or len(grid) < 3:
        return
    story.append(Paragraph("Performance", _H))
    rows = grid.values.tolist()
    header = [str(x).strip() for x in rows[1]]
    data = [[str(x).strip() for x in r] for r in rows[2:] if str(r[0]).strip()]
    n = len(header)
    story.append(_table(header, data, widths=[(10.0 / max(n, 1)) * inch] * n,
                        right_cols=set(range(1, n)), color_cols={4, 8, 12, 16, 19}))


def _allocation_section(story):
    grid = gsheet.allocation()
    if grid.empty or len(grid) < 2:
        return
    story.append(Paragraph("Allocation", _H))
    rows = grid.values.tolist()[1:]
    _LLC = [0, 1, 2, 3, 4, 5, 6, 7]
    _IRA = [10, 11, 12, 13, 14, 15, 16, 17, 18]
    llc_head = ["Group", "Stock", "P/L", "% Alloc", "Cash Res", "Cur Px", "Qty", "Strike"]
    ira_head = ["Group", "Stock", "P/L", "% Alloc", "Cash Res", "Cur Px", "Qty", "% Ret", "Strike"]

    def _rows(cols):
        out = []
        for r in rows:
            vals = [str(r[i]).strip() if i < len(r) else "" for i in cols]
            if any(vals):
                out.append(vals)
        return out

    story.append(Paragraph("LLC", _SUB))
    story.append(_table(llc_head, _rows(_LLC), right_cols={2, 3, 4, 5, 6, 7}, color_cols={2}))
    story.append(Spacer(1, 6))
    story.append(Paragraph("IRA", _SUB))
    story.append(_table(ira_head, _rows(_IRA), right_cols={2, 3, 4, 5, 6, 7, 8}, color_cols={2, 7}))


def _externals():
    """Best-effort ATH + live VIX/trend; never fail the report."""
    ath_ira = ath_llc = 0
    vix, vix_chg, trend = 16.0, 0.0, "Uptrend"
    try:
        ext = gsheet.monitor_externals()
        ath_ira, ath_llc = ext.get("ath_ira", 0), ext.get("ath_llc", 0)
        vix_chg = ext.get("vix_chg", 0.0) or 0.0
        trend = ext.get("trend") or trend
    except Exception:  # noqa: BLE001
        pass
    try:
        mkt = yahoo.market_context()
        vix = mkt.get("vix") or vix
        vix_chg = mkt.get("vix_chg", vix_chg)
        trend = mkt.get("trend") or trend
    except Exception:  # noqa: BLE001
        pass
    return ath_ira, ath_llc, vix, vix_chg, trend


def build_report(fidelity=None, gtc_placed=None) -> bytes:
    """Assemble the full PDF and return its bytes."""
    df = gsheet.tradelog()
    ath_ira, ath_llc, vix, vix_chg, trend = _externals()
    board = mb.monitor_board(df, ath_ira, ath_llc, vix, vix_chg, trend)
    aqres = aq.build(df, fidelity, gtc_placed=gtc_placed)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter),
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            title="WheelEngine Report")
    story = []
    _header_flow(story, "Portfolio Report")
    _monitor_section(story, board)
    _decision_section(story, board, aqres)
    _pl_section(story, df)
    _performance_section(story)
    _allocation_section(story)
    doc.build(story)
    return buf.getvalue()
