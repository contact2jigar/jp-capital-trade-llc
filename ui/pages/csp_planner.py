"""🧭 CSP Planner — type tickers, see cash-secured puts in a Δ band across 2–4 week
expiries with premium · AOR · cash reserve, so you can pick a strike + week fast.

Recovery-style: input a comma-separated ticker list, pick the expiry weeks and the Δ
band (default 0.20–0.30), and each ticker gets a small ladder of candidate puts. Chain
is the bulk CBOE feed (real delta, ~15-min delayed), same as the Recovery tool."""

from __future__ import annotations

import re
from datetime import date, datetime

import streamlit as st

from services import gsheet, option_chain
from logic import csp_pricing


@st.cache_data(ttl=120, show_spinner=False)
def _universe() -> dict[str, list[str]]:
    """{Invest Type → sorted tickers} from the TradeLog. Normalizes the sheet's messy
    prefixes (01-Core / 1-Value / 02-Growth / 2-Growth …) to a clean label."""
    df = gsheet.tradelog()
    if df.empty:
        return {}
    cols = {col.strip(): col for col in df.columns}
    sc, tc = cols.get("Stock"), cols.get("Invest Type")
    if not sc:
        return {}
    latest: dict[str, str] = {}
    for _, r in df.iterrows():
        s = str(r[sc]).strip().upper()
        if s in ("", "CASH", "VAULT", "NAN"):
            continue
        t = (str(r[tc]).strip() if tc else "")
        t = re.sub(r"^\d+\s*-\s*", "", t).strip().title() or "Others"
        latest[s] = t                        # last occurrence wins (most recent invest type)
    uni: dict[str, list[str]] = {}
    for s, t in latest.items():
        uni.setdefault(t, []).append(s)
    return {t: sorted(set(v)) for t, v in sorted(uni.items())}


def _num(x) -> float:
    try:
        s = str(x).replace("$", "").replace(",", "").replace("%", "").strip()
        return float(s) if s not in ("", "—", "-", "nan", "#REF!", "#N/A") else 0.0
    except Exception:
        return 0.0


def _m2(v: float) -> str:
    return f"${v:,.2f}"


def _money(v: float) -> str:
    return ("-$" if v < 0 else "$") + f"{abs(v):,.0f}"


def _fmt_exp(iso) -> str:
    try:
        return datetime.strptime(str(iso), "%Y-%m-%d").strftime("%b %d")
    except Exception:
        return str(iso)


def _candidates(ticker: str, weeks: list[int], lo: float, hi: float) -> tuple[float, list[dict]]:
    """(spot, rows) — puts with |Δ| in [lo,hi] at the expiry nearest each selected week."""
    wk_max = max(weeks) if weeks else 4
    df = option_chain.load_chain(ticker, max_dte=wk_max * 7 + 10, cboe_first=True)
    if df.empty or "type" not in df.columns:
        return 0.0, 0.0, 0.0, []
    puts = df[df["type"] == "put"]
    spot = float(df["spot"].iloc[0]) if "spot" in df.columns else 0.0
    prev = _num(df["prev_close"].iloc[0]) if "prev_close" in df.columns else 0.0
    chg = _num(df["chg_pct"].iloc[0]) if "chg_pct" in df.columns else 0.0
    if puts.empty:
        return spot, prev, chg, []
    rows: list[dict] = []
    for w in sorted(weeks):
        dtes = sorted(puts["dte"].unique(), key=lambda d: abs(int(d) - w * 7))
        if not dtes:
            continue
        dte = int(dtes[0])
        exp_iso = str(puts[puts["dte"] == dte]["expiry"].iloc[0])
        for _, r in puts[puts["dte"] == dte].iterrows():
            d = abs(_num(r.get("delta"))); k = _num(r.get("strike"))
            prem = _num(r.get("bid")) or _num(r.get("last")) or _num(r.get("mark"))   # bid = sellable
            if k <= 0 or prem <= 0 or not (lo <= d <= hi):
                continue
            rows.append({"week": w, "dte": dte, "exp": exp_iso, "strike": k, "delta": d,
                         "prem": prem, "oi": int(_num(r.get("oi"))),
                         "aor": csp_pricing.aor(prem, k, dte) or 0.0, "reserve": k * 100})
    rows.sort(key=lambda x: (x["week"], -x["strike"]))     # per week, nearest-money (highest strike) first
    return spot, prev, chg, rows


def render(c: dict) -> None:
    warn = c.get("warn", c["text"])
    uni = _universe()
    all_stocks = sorted({s for v in uni.values() for s in v})

    c1, c2 = st.columns([1, 2.6])
    sel_type = c1.selectbox("Stock type", ["All"] + list(uni.keys()), key="csp_type")
    pool = all_stocks if sel_type == "All" else uni.get(sel_type, [])
    tickers = c2.multiselect("Stocks", pool, key="csp_stocks")

    ca, cb = st.columns([1.2, 1])
    wsel = ca.multiselect("Expiry weeks", [2, 3, 4], default=[2, 3], key="csp_weeks")
    bsel = cb.radio("Δ band", ["0.20–0.30", "0.15–0.25", "0.25–0.35", "0.10–0.20"],
                    horizontal=True, key="csp_band")
    lo, hi = {"0.20–0.30": (0.20, 0.30), "0.15–0.25": (0.15, 0.25),
              "0.25–0.35": (0.25, 0.35), "0.10–0.20": (0.10, 0.20)}[bsel]
    weeks = sorted(wsel) or [2, 3]

    if not uni:                              # universe unavailable → fall back to typing
        raw = st.text_input("Tickers (comma-separated)", key="csp_tickers", placeholder="AMZN, BE, SPCX")
        tickers = [t.strip().upper() for t in re.split(r"[,\s]+", raw or "") if t.strip()]
    if not tickers:
        st.info("Pick a **stock type** (e.g. Growth) and one or more **stocks** to see a cash-secured-put "
                "ladder: strike · Δ · premium · AOR · cash reserve, per expiry.")
        return
    st.caption(f"Puts with Δ {lo:.2f}–{hi:.2f} · {', '.join(f'{w}w' for w in weeks)} expiries · "
               f"premium = bid × 100 (what you collect) · cash reserve = strike × 100 (1 contract) · "
               f"CBOE feed (~15-min delayed)")

    for tk in tickers:
        with st.spinner(f"Loading {tk}…"):
            spot, prev, chg, rows = _candidates(tk, weeks, lo, hi)
        chg_html = (f" &nbsp; <span style='font-size:12px;font-weight:800;"
                    f"color:{c['pos'] if chg >= 0 else c['neg']};'>{chg:+.2f}% today</span>"
                    f" <span style='font-size:11px;color:{c['muted']};'>· prev {_m2(prev)}</span>"
                    if (spot and prev) else "")
        head = (f"<div style='background:{c['raised']};border:1px solid {c['border']};"
                f"border-radius:10px 10px 0 0;border-bottom:none;padding:10px 15px;margin-top:14px;"
                f"display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;'>"
                f"<span style='font-size:16px;font-weight:950;color:{c['text']};'>{tk}</span>"
                f"<span style='font-size:12px;font-weight:700;color:{c['muted']};'>"
                f"{('spot ' + _m2(spot)) if spot else 'no chain data'}</span>{chg_html}</div>")
        st.markdown(head, unsafe_allow_html=True)
        if not rows:
            st.markdown(f"<div style='border:1px solid {c['border']};border-radius:0 0 10px 10px;"
                        f"padding:12px 15px;color:{c['muted']};font-size:13px;'>No puts in the "
                        f"Δ {lo:.2f}–{hi:.2f} band for the selected weeks.</div>", unsafe_allow_html=True)
            continue
        hdrs = ("WEEK", "EXPIRY", "DTE", "STRIKE", "Δ", "OI", "PREMIUM", "AOR", "CASH RESERVE")
        thead = "".join(f"<th style='background:{c['panel']};color:{c['muted']};border:1px solid {c['border']};"
                        f"padding:6px 12px;text-align:{'left' if i < 2 else 'right'};font-weight:800;"
                        f"font-size:11px;white-space:nowrap;'>{h}</th>" for i, h in enumerate(hdrs))
        body = ""
        for r in rows:
            cells = [
                (f"{r['week']}w", "left", c["text"], 800),
                (_fmt_exp(r["exp"]), "left", c["muted"], 600),
                (f"{r['dte']}d", "right", c["muted"], 600),
                (_m2(r["strike"]), "right", c["text"], 800),
                (f"{r['delta']:.2f}", "right", c["muted"], 600),
                (f"{r['oi']:,}", "right", c["muted"], 600),
                (_money(r["prem"] * 100), "right", c["pos"], 800),
                (f"{r['aor']:.0f}%", "right", warn, 800),
                (_money(r["reserve"]), "right", c["text"], 700),
            ]
            tds = "".join(f"<td style='border:1px solid {c['border']};padding:7px 12px;text-align:{al};"
                          f"color:{cl};font-weight:{fw};white-space:nowrap;font-size:13px;'>{v}</td>"
                          for v, al, cl, fw in cells)
            body += f"<tr style='background:{c['panel']};'>{tds}</tr>"
        st.markdown(f"<div style='overflow:auto;border:1px solid {c['border']};border-radius:0 0 10px 10px;'>"
                    f"<table style='border-collapse:collapse;width:100%;'>"
                    f"<thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></div>",
                    unsafe_allow_html=True)
