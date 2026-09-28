"""
Fundamental Scorer — engine.

Pulls fundamentals from yfinance and scores each ticker against the 10-check
Fundamental Card. Score ≥ 8/10 = qualifies for the Wheel Universe.

Checks (per user_wheel_fundamental_card.md):
  1. Rev YoY %          > 0
  2. EPS YoY %          > 0
  3. FCF YoY %          > 0
  4. Op Margin Δ (bps)  ≥ 0
  5. Credit Rating      ≥ BBB−       (manual — yfinance doesn't expose)
  6. Leverage (D/FCF)   < 3.0
  7. Analyst Buy %      ≥ 60
  8. PT Upside %        ≥ 30
  9. Secular Thesis     Yes           (manual — subjective)
 10. LT Guide           Yes           (manual — subjective)
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd
import yfinance as yf


ETF_TICKERS = {
    "QQQ", "SPY", "IWM", "DIA", "VOO", "VTI", "VXUS", "VEA", "VWO",
    "GLD", "SLV", "TLT", "AGG", "BND", "TQQQ", "SQQQ", "SPXL", "SPXU",
    "ETHA", "IBIT", "FBTC",
}


@dataclass
class FundResult:
    ticker: str
    is_etf: bool = False
    error: str = ""
    # data
    market_cap_b: Optional[float] = None
    sector: str = ""
    industry: str = ""
    # market snapshot (captured from the same info call — Wheel Scanner columns)
    price: Optional[float] = None
    chg_1d: Optional[float] = None             # 1-day % change
    pe: Optional[float] = None                 # trailing P/E
    volume: Optional[float] = None
    avg_volume: Optional[float] = None
    iv: Optional[float] = None                 # ATM IV %, filled in by the page (optional)
    # Health badges (Rev up YoY · Net Income >0 · Operating CF >0 · Assets > Liabilities)
    rev_up: Optional[bool] = None
    income_pos: Optional[bool] = None
    cf_pos: Optional[bool] = None
    assets_gt_liab: Optional[bool] = None
    rev_yoy: Optional[float] = None            # decimal, e.g. 0.17 = +17%
    eps_yoy: Optional[float] = None
    ocf_yoy: Optional[float] = None            # operating cash flow — SCORED (capex-agnostic)
    fcf_yoy: Optional[float] = None            # free cash flow — WARNING ONLY, not scored
    fcf_level_neg: bool = False                # current FCF ≤ 0 → ⚠ capex/burn warning
    op_margin_delta_bps: Optional[float] = None
    leverage_debt_over_ocf: Optional[float] = None
    analyst_buy_pct: Optional[float] = None    # decimal, e.g. 0.79
    pt_upside: Optional[float] = None          # decimal
    latest_quarter: str = ""                   # most recent reported quarter in the data
    # score
    pass_flags: dict = field(default_factory=dict)
    auto_score: int = 0                        # passes among AVAILABLE auto checks
    max_auto: int = 0                          # checks with data (None = excluded, not failed)


def _safe_div(a, b):
    try:
        a = float(a); b = float(b)
        if b == 0 or math.isnan(a) or math.isnan(b):
            return None
        return a / b
    except (TypeError, ValueError):
        return None


def _yoy(current, prior):
    v = _safe_div(current, prior)
    if v is None:
        return None
    return v - 1  # (current/prior) - 1 = growth %


def _find_row(df: pd.DataFrame, row_labels: list[str]):
    """Return the first matching row (a Series over quarters, date-descending) or None."""
    if df is None or df.empty:
        return None
    for lbl in row_labels:
        if lbl in df.index:
            return df.loc[lbl]
    return None


def _yoy_pair(row, row2=None):
    """Newest clean YoY pair: quarter at offset o vs the same quarter a year
    earlier (o+4), sliding back one quarter at a time when the latest print
    hasn't reached Yahoo's parsed statements yet. Returns (latest, prior, o)
    or (None, None, -1). `row2` only bounds usable length (for paired rows)."""
    if row is None:
        return None, None, -1
    n = len(row) if row2 is None else min(len(row), len(row2))
    for o in range(0, n - 4):
        latest = row.iloc[o]
        prior = row.iloc[o + 4]
        if pd.isna(latest) or pd.isna(prior):
            continue
        return float(latest), float(prior), o
    return None, None, -1


def _yoy_guarded(latest, prior):
    """YoY with a junk-base guard: a % that explodes past ±500% carries no
    information (near-zero year-ago base) → treated as no-data."""
    v = _yoy(latest, prior)
    if v is None or abs(v) > 5:
        return None
    return v


def score_ticker(ticker: str) -> FundResult:
    """Fetch fundamentals and score one ticker. Never raises — returns error in result."""
    t = ticker.upper().strip()
    out = FundResult(ticker=t)

    if t in ETF_TICKERS:
        out.is_etf = True
        out.error = "ETF — fundamental scoring N/A"
        return out

    # Level-override flags: None = decide from the YoY number; False = the
    # current-period LEVEL is negative (bad regardless of growth math).
    eps_flag = None
    ocf_flag = None
    lev_flag = None

    try:
        tk = yf.Ticker(t)

        # ── Info ──
        info = tk.info or {}
        out.sector = info.get("sector", "") or info.get("industry", "")
        out.industry = info.get("industry", "") or info.get("sector", "")
        mcap = info.get("marketCap")
        if mcap:
            out.market_cap_b = mcap / 1e9

        # Market snapshot — from the SAME info call (no extra fetch).
        px = info.get("currentPrice") or info.get("regularMarketPrice")
        prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
        out.price = float(px) if px else None
        if px and prev:
            out.chg_1d = (float(px) - float(prev)) / float(prev) * 100
        pe = info.get("trailingPE")
        out.pe = float(pe) if pe else None
        vol = info.get("volume") or info.get("regularMarketVolume")
        out.volume = float(vol) if vol else None
        avol = info.get("averageVolume")
        out.avg_volume = float(avol) if avol else None

        # PT Upside
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        target = info.get("targetMeanPrice")
        if current and target:
            out.pt_upside = _yoy(target, current)  # (target/current) - 1

        # Analyst rating — yfinance exposes recommendationKey OR recommendations df
        rec_key = info.get("recommendationKey", "")  # e.g. 'buy', 'strong_buy'
        try:
            rec_df = tk.recommendations
            if rec_df is not None and not rec_df.empty:
                # Latest period row
                latest = rec_df.iloc[0]
                sb = float(latest.get("strongBuy", 0) or 0)
                b  = float(latest.get("buy", 0) or 0)
                h  = float(latest.get("hold", 0) or 0)
                s  = float(latest.get("sell", 0) or 0)
                ss = float(latest.get("strongSell", 0) or 0)
                total = sb + b + h + s + ss
                if total > 0:
                    out.analyst_buy_pct = (sb + b) / total
        except Exception:
            pass

        # Fallback via recommendationKey
        if out.analyst_buy_pct is None:
            key_map = {"strong_buy": 0.90, "buy": 0.70, "hold": 0.50, "sell": 0.30, "strong_sell": 0.10}
            if rec_key in key_map:
                out.analyst_buy_pct = key_map[rec_key]

        # ── Quarterly financials — Revenue, EPS, Operating Margin ──
        qfin = tk.quarterly_income_stmt
        if qfin is None or qfin.empty:
            qfin = tk.quarterly_financials  # legacy alias

        rev_row = _find_row(qfin, ["Total Revenue", "Revenue"])
        rev_latest, rev_prior, rev_o = _yoy_pair(rev_row)
        out.rev_yoy = _yoy_guarded(rev_latest, rev_prior)

        # Data Thru = the quarter actually used (slides back with the pair)
        if qfin is not None and not qfin.empty:
            try:
                col = qfin.columns[rev_o] if rev_o >= 0 else qfin.columns[0]
                out.latest_quarter = str(pd.Timestamp(col).date())
            except Exception:
                pass

        op_row = _find_row(qfin, ["Operating Income", "Operating Revenue"])
        if op_row is not None and rev_row is not None:
            op_l, op_p, o = _yoy_pair(op_row, rev_row)
            if o >= 0 and not pd.isna(rev_row.iloc[o]) and not pd.isna(rev_row.iloc[o + 4]):
                om_latest = _safe_div(op_l, float(rev_row.iloc[o]))
                om_prior = _safe_div(op_p, float(rev_row.iloc[o + 4]))
                if om_latest is not None and om_prior is not None:
                    out.op_margin_delta_bps = (om_latest - om_prior) * 10000

        # EPS — diluted, newest clean pair. Negative current EPS = LEVEL fail.
        # Positive current EPS off a tiny year-ago base (< $0.10, the COHR
        # −981% class) = growth unknowable → excluded.
        eps_row = _find_row(qfin, ["Diluted EPS", "Basic EPS"])
        eps_l, eps_p, _ = _yoy_pair(eps_row)
        if eps_l is not None:
            if eps_l <= 0:
                eps_flag = False
            elif eps_p is not None and abs(eps_p) >= 0.10:
                out.eps_yoy = _yoy_guarded(eps_l, eps_p)

        # ── Cash flow ──
        # OCF YoY is the SCORED check (cash engine, capex-agnostic).
        # FCF YoY is computed for DISPLAY as a capex/burn warning — not scored.
        qcf = tk.quarterly_cashflow
        ocf_row = None
        fcf_row = None
        if qcf is not None and not qcf.empty:
            ocf_row = _find_row(qcf, ["Operating Cash Flow", "Total Cash From Operating Activities"])
            capex_row = _find_row(qcf, ["Capital Expenditure", "Capital Expenditures"])
            if ocf_row is not None and capex_row is not None:
                fcf_row = ocf_row + capex_row  # aligned by quarter; capex is negative

        ocf_l, ocf_p, _ = _yoy_pair(ocf_row)
        if ocf_l is not None:
            if ocf_l <= 0:
                ocf_flag = False               # cash engine negative = LEVEL fail
            elif ocf_p is not None and ocf_p > 0:
                out.ocf_yoy = _yoy_guarded(ocf_l, ocf_p)

        fcf_l, fcf_p, _ = _yoy_pair(fcf_row)
        if fcf_l is not None:
            if fcf_l <= 0:
                out.fcf_level_neg = True       # ⚠ warning only (AMZN AI-capex class)
            elif fcf_p is not None and fcf_p > 0:
                out.fcf_yoy = _yoy_guarded(fcf_l, fcf_p)

        # ── Balance sheet — Debt / FCF ──
        qbs = tk.quarterly_balance_sheet
        if qbs is not None and not qbs.empty:
            debt = None
            for lbl in ["Total Debt", "Long Term Debt", "Net Debt"]:
                if lbl in qbs.index:
                    debt = qbs.loc[lbl].iloc[0]
                    break
            if debt is not None and not pd.isna(debt) and ocf_row is not None:
                # Annualized OCF: LTM sum of the newest 4 clean quarters, else newest ×4.
                # OCF denominator (not FCF) so a deliberate capex cycle doesn't
                # read as dangerous leverage.
                ocf_ann = None
                ocf_clean = ocf_row.dropna()
                if len(ocf_clean) >= 4:
                    ocf_ann = float(ocf_clean.iloc[0:4].sum())
                elif len(ocf_clean) >= 1:
                    ocf_ann = float(ocf_clean.iloc[0]) * 4
                if ocf_ann is not None:
                    out.leverage_debt_over_ocf = _safe_div(debt, ocf_ann)
                    if float(debt) <= 0:
                        lev_flag = True          # net cash — best case
                    elif ocf_ann <= 0:
                        lev_flag = False         # debt with no operating cash — worst case
                    elif out.leverage_debt_over_ocf is not None:
                        lev_flag = out.leverage_debt_over_ocf < 3.0

        # ── Health badges (Rev up · Net Income >0 · Op CF >0 · Assets > Liab) ──
        out.rev_up = bool(out.rev_yoy is not None and out.rev_yoy > 0)
        ni_row = _find_row(qfin, ["Net Income", "Net Income Common Stockholders",
                                  "Net Income Continuous Operations"])
        if ni_row is not None:
            niv = ni_row.dropna()
            if len(niv):
                out.income_pos = bool(float(niv.iloc[0]) > 0)
        if ocf_row is not None:
            ov = ocf_row.dropna()
            if len(ov):
                out.cf_pos = bool(float(ov.iloc[0]) > 0)
        if qbs is not None and not qbs.empty:
            assets = _find_row(qbs, ["Total Assets"])
            liab = _find_row(qbs, ["Total Liabilities Net Minority Interest",
                                   "Total Liabilities", "Total Liab"])
            if assets is not None and liab is not None:
                av, lv = assets.dropna(), liab.dropna()
                if len(av) and len(lv):
                    out.assets_gt_liab = bool(float(av.iloc[0]) > float(lv.iloc[0]))

    except Exception as e:
        out.error = f"{type(e).__name__}: {e}"

    # ── Compute pass flags — tri-state: True / False / None (no data = excluded) ──
    def gt(v, thresh):  return None if v is None else v > thresh
    def gte(v, thresh): return None if v is None else v >= thresh

    flags = {
        "rev_yoy":            gt(out.rev_yoy, 0),
        "eps_yoy":            eps_flag if eps_flag is not None else gt(out.eps_yoy, 0),
        "ocf_yoy":            ocf_flag if ocf_flag is not None else gt(out.ocf_yoy, 0),
        "op_margin_expand":   gte(out.op_margin_delta_bps, 0),
        "leverage_ok":        lev_flag,
        "analyst_buy":        gte(out.analyst_buy_pct, 0.60),
        "pt_upside":          gte(out.pt_upside, 0.10),   # 30% was a small-cap bar; mega-caps never carry it
    }
    out.pass_flags = flags
    out.auto_score = sum(1 for v in flags.values() if v is True)
    out.max_auto = sum(1 for v in flags.values() if v is not None)
    return out


def score_batch(tickers: list[str], progress_cb=None) -> pd.DataFrame:
    """Score a list of tickers. `progress_cb(i, n, ticker)` called each iteration."""
    results = []
    n = len(tickers)
    for i, t in enumerate(tickers):
        if progress_cb:
            progress_cb(i, n, t)
        r = score_ticker(t)
        results.append(_row_from_result(r))
    if progress_cb:
        progress_cb(n, n, "done")
    df = pd.DataFrame(results)
    return df


def _verdict(r: FundResult) -> str:
    """Three-state verdict — mirrors the CSP gate pattern: score is the
    checklist, gates are the vetoes, REVIEW is the judgment pile.

    NO      dead on arrival: shrinking revenue, negative operating cash flow,
            Debt/OCF > 6, or pass rate < 50%.
    YES     clean: score ≥ 5/7 of available AND no soft gate tripped.
    REVIEW  everything between — passes the score but trips a soft gate
            (Debt/OCF 3-6, EPS YoY ≤ −50%, thin data). Human reads it.

    Gates fire only on actual bad numbers — blanks route to REVIEW, never NO.
    """
    if r.is_etf:
        return "N/A"
    ratio = (r.auto_score / r.max_auto) if r.max_auto else 0.0

    # ── Hard gates → NO ──
    rev_shrinking = r.rev_yoy is not None and r.rev_yoy <= 0
    ocf_level_neg = r.ocf_yoy is None and r.pass_flags.get("ocf_yoy") is False
    lev = r.leverage_debt_over_ocf
    lev_danger = lev is not None and lev > 6
    if rev_shrinking or ocf_level_neg or lev_danger or (r.max_auto >= 4 and ratio < 0.5):
        return "NO"

    # ── Soft gates → REVIEW ──
    eps_deep = r.eps_yoy is not None and r.eps_yoy <= -0.5
    lev_band = lev is not None and 3.0 <= lev <= 6.0
    thin_data = r.max_auto < 4
    score_ok = r.max_auto >= 4 and ratio >= 5 / 7

    if score_ok and not eps_deep and not lev_band and not thin_data:
        return "YES"
    return "REVIEW"


def _row_from_result(r: FundResult) -> dict:
    """Flatten a FundResult into a row for the display table."""
    def pct(v):
        return None if v is None else round(v * 100, 1)
    def growth_cell(v, flag):
        """Numeric YoY when computable; 'NEG' when the check failed on a
        negative current-period LEVEL (v is None but flag is False)."""
        if v is not None:
            return pct(v)
        return "NEG" if flag is False else None

    # FCF display — warning only, never scored
    if r.fcf_yoy is not None:
        fcf_cell = pct(r.fcf_yoy)
    elif r.fcf_level_neg:
        fcf_cell = "⚠ NEG"
    else:
        fcf_cell = None

    def _b(v):
        return "✅" if v is True else ("❌" if v is False else "◻️")

    financials = (f"Rev{_b(r.rev_up)} Inc{_b(r.income_pos)} "
                  f"CF{_b(r.cf_pos)} A>L{_b(r.assets_gt_liab)}")

    return {
        "Ticker": r.ticker,
        "Financials": financials,
        "Price": None if r.price is None else round(r.price, 2),
        "1D %": None if r.chg_1d is None else round(r.chg_1d, 2),
        "IV %": None if r.iv is None else round(r.iv, 1),
        "P/E": None if r.pe is None else round(r.pe, 1),
        "Vol": None if r.volume is None else int(r.volume),
        "Avg Vol": None if r.avg_volume is None else int(r.avg_volume),
        "Sector": r.sector,
        "Industry": r.industry,
        "MCap $B": None if r.market_cap_b is None else round(r.market_cap_b, 1),
        "Rev YoY %": pct(r.rev_yoy),
        "EPS YoY %": growth_cell(r.eps_yoy, r.pass_flags.get("eps_yoy")),
        "OCF YoY %": growth_cell(r.ocf_yoy, r.pass_flags.get("ocf_yoy")),
        "FCF ⚠": fcf_cell,
        "OpM Δ bps": None if r.op_margin_delta_bps is None else round(r.op_margin_delta_bps, 0),
        "Debt/OCF": None if r.leverage_debt_over_ocf is None else round(r.leverage_debt_over_ocf, 2),
        "Buy %": pct(r.analyst_buy_pct),
        "PT Upside %": pct(r.pt_upside),
        "Data Thru": r.latest_quarter,
        "Auto Score": f"{r.auto_score}/{r.max_auto}",
        "Universe?": _verdict(r),
        "Error": r.error,
    }
