"""🛟 Recovery Tool — assigned-share piles (basis = strike − premium), with a suggested
covered call at a chosen delta + expiry. Mirrors the mobile Recovery page.

Chain feed: bulk CBOE (one request per symbol → real delta/IV/OI, ~15-min delayed),
falling back to RH live then yfinance. Delta is the feed's own, so the suggested strike is
exact; PREM is the bid/ask mark (CBOE delayed), so it lags the mobile RH live mark slightly."""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from services import gsheet, option_chain
from logic import csp_pricing


def _parse_date(x) -> date | None:
    """Parse a sheet date like 10/23/26, 10/23/2026 or 2026-10-23 → date (None if bad)."""
    s = str(x).strip()
    if not s or s in ("—", "-", "nan"):
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _num(x) -> float:
    try:
        s = str(x).replace("$", "").replace(",", "").replace("%", "").strip()
        return float(s) if s not in ("", "—", "-", "nan", "#REF!", "#N/A") else 0.0
    except Exception:
        return 0.0


def _money(v: float) -> str:
    return ("-$" if v < 0 else "$") + f"{abs(v):,.0f}"


def _m2(v: float) -> str:
    return f"${v:,.2f}"


@st.cache_data(ttl=120, show_spinner=False)
def _cc_suggest(stock: str, spot: float, target_delta: float, weeks: int) -> dict | None:
    """A ~target_delta covered call ~weeks out: {strike, delta, prem, aor, dte}. Approximate."""
    if spot <= 0:
        return None
    # Bulk CBOE feed: ONE request returns the whole chain with REAL delta (no BS
    # estimate), fast. Falls back to RH/yfinance inside load_chain; the wide hi_band
    # only matters if it lands on RH (a 20Δ call on a high-IV name sits ~+26% OTM).
    df = option_chain.load_chain(stock, max_dte=weeks * 7 + 14,
                                 lo_band=0.05, hi_band=0.90, cboe_first=True)
    if df.empty or "type" not in df.columns:
        return None
    calls = df[df["type"] == "call"]
    if calls.empty:
        return None
    prev_close = _num(df["prev_close"].iloc[0]) if "prev_close" in df.columns else 0.0
    chg_pct = _num(df["chg_pct"].iloc[0]) if "chg_pct" in df.columns else 0.0
    target_dte = weeks * 7
    dtes = sorted(calls["dte"].unique(), key=lambda d: abs(int(d) - target_dte))
    cands = calls[calls["dte"] == dtes[0]]
    best, best_diff = None, 9e9
    for _, r in cands.iterrows():
        k = _num(r.get("strike")); dte = int(r.get("dte") or 0)
        # BID = what a seller actually collects (the mid overstates on wide/illiquid spreads);
        # fall back to last, then mark, only when there's no bid.
        prem = _num(r.get("bid")) or _num(r.get("last")) or _num(r.get("mark"))
        if k <= 0 or prem <= 0 or dte <= 0:
            continue
        cdelta = _num(r.get("delta"))                       # CBOE real call delta (positive)
        if cdelta <= 0:                                     # RH/yfinance have no delta → estimate it
            pdelta = csp_pricing.bs_put_delta(spot, k, dte, r.get("iv"))
            if pdelta is None:
                continue
            cdelta = pdelta + 1.0                           # put-call parity: Δcall = Δput + 1
        diff = abs(cdelta - target_delta)
        if diff < best_diff:
            best_diff = diff
            best = {"strike": k, "delta": cdelta, "prem": prem, "dte": dte,
                    "aor": csp_pricing.aor(prem, k, dte)}
    if best is not None:
        best["prev_close"] = prev_close
        best["chg_pct"] = chg_pct
    return best


def render(c: dict) -> None:
    ca, cb, cc = st.columns([1, 1, 1])
    dsel = ca.radio("Target Δ", ["35Δ", "30Δ", "25Δ", "20Δ", "15Δ", "10Δ"], index=3, horizontal=True, key="rec_delta")
    wsel = cb.radio("CC expiry", ["2w", "3w", "4w"], horizontal=True, key="rec_weeks")
    layout = cc.radio("Layout", ["By Expiry", "Positions"], horizontal=True, key="rec_layout")
    target_delta = {"35Δ": 0.35, "30Δ": 0.30, "25Δ": 0.25, "20Δ": 0.20, "15Δ": 0.15, "10Δ": 0.10}[dsel]
    weeks = {"2w": 2, "3w": 3, "4w": 4}[wsel]

    df = gsheet.tradelog()
    if df.empty:
        st.info("TradeLog is empty.")
        return
    cols = {col.strip(): col for col in df.columns}

    def cell(row, name):
        col = cols.get(name)
        return row[col] if col is not None else ""

    # ── Build piles: PUT assignments give basis; keep only those with an OPEN covered call.
    #    Capture each pile's OPEN CC expiry (earliest) so we can group by expiry batch. ──
    lots: dict[tuple, list] = {}            # (stock,acct) → put-assignment lots (for per-share basis)
    cc_batch: dict[tuple, float] = {}       # (stock,acct,exp) → open-CC contracts = ONE batch
    cur_by_stock: dict[str, float] = {}
    for _, row in df.iterrows():
        stock = str(cell(row, "Stock")).strip().upper()
        if stock in ("", "CASH", "VAULT"):
            continue
        acct = str(cell(row, "Account")).strip().upper()
        status = str(cell(row, "Status")).upper()
        opt = str(cell(row, "Opt Typ")).upper()
        cur = _num(cell(row, "Current Price"))
        if cur > 0 and stock not in cur_by_stock:
            cur_by_stock[stock] = cur
        if status.startswith("ASSI") and "PUT" in opt:
            k = _num(cell(row, "Strike Price"))
            if k > 0:
                lots.setdefault((stock, acct), []).append(
                    (k, _num(cell(row, "Init Prem")), _num(cell(row, "Qty"))))
        elif status.startswith("OPEN") and "CALL" in opt:
            exp = _parse_date(cell(row, "Exp Date"))
            cc_batch[(stock, acct, exp)] = cc_batch.get((stock, acct, exp), 0.0) + _num(cell(row, "Qty"))

    # Per-account weighted basis (strike & break-even) from the put assignments.
    basis: dict[tuple, tuple] = {}
    for (stock, acct), ll in lots.items():
        assh = int(round(sum(q for _, _, q in ll))) * 100
        if assh <= 0:
            continue
        basis[(stock, acct)] = (sum(k * q * 100 for k, _, q in ll) / assh,
                                sum((k - pm) * q * 100 for k, pm, q in ll) / assh)

    # ONE pile per (stock, account, CC-expiry): quantity = that batch's CC contracts × 100.
    # A name with CCs at two expiries (e.g. IREN LLC 10/23 ×3 + 10/30 ×3) becomes two batches.
    piles = []
    for (stock, acct, exp), q in cc_batch.items():
        b = basis.get((stock, acct))
        if b is None:                       # need a put-assignment basis to be a recovery pile
            continue
        shares = int(round(q)) * 100
        if shares <= 0:
            continue
        wstrike, wbe = b
        cur = cur_by_stock.get(stock, 0.0)
        under = (cur - wbe) / wbe * 100 if (cur and wbe) else None
        piles.append({"stock": stock, "acct": acct, "shares": shares, "wstrike": wstrike,
                      "wbe": wbe, "cur": cur, "under": under, "cc_exp": exp})
    piles.sort(key=lambda p: (p["stock"], p["acct"]))        # order by stock (then account)

    underwater = sum(1 for p in piles if (p["under"] or 0) < 0)
    unreal = sum((p["cur"] - p["wbe"]) * p["shares"] for p in piles if p["cur"])

    # ── CC suggestions (cached per stock+Δ+weeks) — load FIRST so the header can
    #    report the economics of actually writing these calls. ──
    with st.spinner("Loading option chains…"):
        sug = {}
        for stock in {p["stock"] for p in piles}:
            sug[stock] = _cc_suggest(stock, cur_by_stock.get(stock, 0.0), target_delta, weeks)

    # ── Aggregate the recovery move at the selected Δ / expiry ──
    prem_cycle = upside = net_basis = coll = aor_wt = cur_value = 0.0
    covered = 0
    for p in piles:
        s = sug.get(p["stock"])
        if not s:
            continue
        sh = p["shares"]
        covered += 1
        prem_cycle += s["prem"] * sh                               # cash collected this cycle
        upside += max(0.0, s["strike"] - p["cur"]) * sh            # appreciation now → CC strike
        net_basis += (s["strike"] - p["wbe"]) * sh                 # where you land vs basis if called
        cur_value += p["cur"] * sh                                 # current market value of the shares
        c_ = s["strike"] * sh
        coll += c_
        if s["aor"]:
            aor_wt += s["aor"] * c_
    total_called = prem_cycle + upside                            # total cash if every CC is assigned
    blended_aor = (aor_wt / coll) if coll else 0.0                # capital-weighted annualized premium %
    total_roi = (total_called / cur_value * 100) if cur_value > 0 else 0.0   # cycle return on current value
    prem_roi = (prem_cycle / cur_value * 100) if cur_value > 0 else 0.0      # premium-only yield this cycle

    # ── Projected portfolio: whole-account value today vs if every CC is called away ──
    cells = gsheet.monitor_board_cells()
    cap_ira = (cells.get("ira", {}) or {}).get("cap") or 0.0
    cap_llc = (cells.get("llc", {}) or {}).get("cap") or 0.0
    k401 = 540000.0                       # 401k (matches the Projection page's fixed web assumption)
    port_today = cap_ira + cap_llc + k401
    port_gain = upside + prem_cycle       # premium collected + appreciation now → CC strikes
    port_proj = port_today + port_gain
    port_pct = (port_gain / port_today * 100) if port_today else 0.0
    st.markdown(
        f"<div style='background:{c['panel']};border:1px solid {c['border']};border-left:3px solid "
        f"{c.get('warn', c['accent'])};border-radius:12px;padding:12px 18px;margin:4px 0 12px;'>"
        f"<div style='font-size:11px;font-weight:900;letter-spacing:.4px;color:{c['muted']};'>"
        f"🔮 PROJECTED PORTFOLIO &nbsp;·&nbsp; if all {covered} CCs called @ {int(target_delta*100)}Δ ({weeks}w)</div>"
        f"<div style='display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:5px;'>"
        f"<div style='display:flex;align-items:baseline;gap:12px;'>"
        f"<span style='font-size:30px;font-weight:950;color:{c['text']};'>{_money(port_proj)}</span>"
        f"<span style='font-size:15px;font-weight:900;color:{c['pos']};'>+{_money(port_gain)} · +{port_pct:.1f}%</span></div>"
        f"<div style='font-size:12px;font-weight:600;color:{c['muted']};'>"
        f"today {_money(port_today)} &nbsp;·&nbsp; +prem {_money(prem_cycle)} &nbsp;·&nbsp; +upside {_money(upside)}</div>"
        f"</div></div>", unsafe_allow_html=True)

    # ── Header: recovery economics, driven by the Δ / week selectors ──
    def _tile(label, value, color, sub=""):
        sub_html = (f"<div style='margin-top:2px;font-size:10.5px;font-weight:600;color:{c['muted']};'>{sub}</div>"
                    if sub else "")
        return (f"<div style='flex:1;min-width:150px;background:{c['panel']};border:1px solid {c['border']};"
                f"border-radius:11px;padding:12px 15px;'>"
                f"<div style='font-size:10px;font-weight:900;letter-spacing:.3px;color:{c['muted']};'>{label}</div>"
                f"<div style='margin-top:3px;font-size:19px;font-weight:950;color:{color};'>{value}</div>{sub_html}</div>")

    nb_col = c["pos"] if net_basis >= 0 else c["neg"]
    warn = c.get("warn", c["text"])
    tiles = [
        _tile("UNREALIZED", _money(unreal), c["neg"] if unreal < 0 else c["pos"], "paper loss vs basis"),
        _tile(f"PREMIUM / {weeks}w", _money(prem_cycle), c["pos"], f"{covered} piles · {prem_roi:.1f}% this cycle"),
        _tile("TOTAL AOR", f"{blended_aor:.0f}%", warn, "annualized premium yield"),
        _tile("PREMIUM %", f"{prem_roi:.1f}%", c["pos"], "collected · this cycle"),
        _tile("TOTAL IF CALLED", _money(total_called), c["pos"], "premium + upside"),
        _tile("NET vs BASIS", _money(net_basis), nb_col, "where you land if called"),
    ]
    st.markdown(f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin:4px 0 10px;'>{''.join(tiles)}</div>",
                unsafe_allow_html=True)

    # ── By-Expiry: group piles by their CURRENT open-CC expiry (the "ready to deploy" batch),
    #    and show, per batch, what writing a fresh ~Δ CC on it would do. ──
    if layout == "By Expiry":
        today = date.today()
        groups: dict[object, list] = {}
        for p in piles:
            groups.setdefault(p.get("cc_exp"), []).append(p)

        def _agg(members):
            cap = called = prem = collat = aor_wt = 0.0
            for p in members:
                s = sug.get(p["stock"]); sh = p["shares"]
                cap += p["cur"] * sh
                if s:
                    called += s["strike"] * sh
                    prem += s["prem"] * sh
                    collat += s["strike"] * sh
                    if s["aor"]:
                        aor_wt += s["aor"] * s["strike"] * sh
            return {"cap": cap, "called": called, "prem": prem,
                    "roi": (prem / cap * 100) if cap else 0.0,
                    "aor": (aor_wt / collat) if collat else 0.0}

        order = sorted(groups.keys(), key=lambda e: (e is None, e or date.max))
        for exp in order:
            members = sorted(groups[exp], key=lambda p: (p["stock"], p["acct"]))
            g = _agg(members)
            dte = (exp - today).days if isinstance(exp, date) else None
            title = (exp.strftime("%b %d, %Y") if isinstance(exp, date) else "No expiry date")
            when = (f" · in {dte}d" if (dte is not None and dte >= 0) else (f" · {abs(dte)}d ago" if dte is not None else ""))
            gain_now = g["called"] - g["cap"]                               # upside: current → CC strike
            orig_val = sum(p["wstrike"] * p["shares"] for p in members)     # original assigned-strike cost
            vs_strike = g["called"] - orig_val                             # still down vs our strike if called
            st.markdown(
                f"<div style='background:{c['raised']};border:1px solid {c['border']};border-radius:10px 10px 0 0;"
                f"border-bottom:none;padding:10px 15px;margin-top:14px;display:flex;align-items:baseline;"
                f"justify-content:space-between;gap:12px;flex-wrap:wrap;'>"
                f"<span><span style='font-size:15px;font-weight:950;color:{c['text']};'>📅 {title}{when}</span>"
                f"&nbsp;&nbsp;<span style='font-size:11px;font-weight:800;color:{c['muted']};'>{len(members)} positions</span></span>"
                f"<span style='font-size:11.5px;font-weight:800;color:{c['muted']};'>IF CALLED "
                f"<b style='color:{c.get('accent', c['text'])};'>{_money(g['called'])}</b>"
                f" &nbsp;·&nbsp; vs now <b style='color:{c['pos'] if gain_now >= 0 else c['neg']};'>{'+' if gain_now >= 0 else ''}{_money(gain_now)}</b>"
                f" &nbsp;·&nbsp; vs strike <b style='color:{c['pos'] if vs_strike >= 0 else c['neg']};'>{'+' if vs_strike >= 0 else ''}{_money(vs_strike)}</b></span>"
                f"</div>", unsafe_allow_html=True)

            warn = c.get("warn", c["text"])
            tot_cap = sum(p["cur"] * p["shares"] for p in members)
            tot_prem = sum((sug[p["stock"]]["prem"] * p["shares"]) for p in members if sug.get(p["stock"]))
            tot_sh = sum(p["shares"] for p in members)
            mhdrs = ("STOCK", "ACCOUNT", "ORIG STRIKE", "BREAK EVEN", "CURRENT", "UNDER WATER", f"CC {weeks}w",
                     "IF CALLED", "AOR", "PREM/SH", "PREMIUM", "CASH RESERVE", "% CAP", "QTY", "YESTERDAY", "% CHG")
            mhead = "".join(f"<th style='background:{c['panel']};color:{c['muted']};border:1px solid {c['border']};"
                            f"padding:6px 12px;text-align:{'left' if i < 2 else 'right'};font-weight:800;"
                            f"font-size:11px;white-space:nowrap;'>{h}</th>" for i, h in enumerate(mhdrs))
            mrows = ""
            for p in members:
                s = sug.get(p["stock"]); sh = p["shares"]
                cap = p["cur"] * sh
                # tint each independently vs the suggested CC strike: green when the call's strike is
                # at/above that level (called there = good), red below. Orig strike vs wstrike, BE vs wbe.
                strike_col = (c["pos"] if s["strike"] >= p["wstrike"] else c["neg"]) if s else None
                be_col = (c["pos"] if s["strike"] >= p["wbe"] else c["neg"]) if s else None
                loss_ifc = (s["strike"] - p["wstrike"]) * sh if s else None   # capital P/L if called, vs ORIGINAL assigned strike (premium booked separately)
                uw = (p["cur"] - p["wstrike"]) * sh                           # current paper P/L vs ORIGINAL strike (same basis as IF CALLED)
                mcells = [
                    (p["stock"], "left", c["text"], 800),
                    (p["acct"], "left", c["muted"], 700),
                    (_m2(p["wstrike"]), "right", strike_col or c["muted"], 700),
                    (_m2(p["wbe"]), "right", be_col or c["text"], 800),
                    (_m2(p["cur"]), "right", c["muted"], 600),
                    (_money(uw), "right", c["pos"] if uw >= 0 else c["neg"], 800),
                    (_m2(s["strike"]) if s else "…", "right", c["text"], 700),
                    (_money(loss_ifc) if s else "…", "right",
                     (c["pos"] if loss_ifc >= 0 else c["neg"]) if s else c["muted"], 800),
                    (f"{s['aor']:.0f}%" if (s and s["aor"] is not None) else "…", "right", warn if s else c["muted"], 800),
                    (_m2(s["prem"]) if s else "…", "right", c["muted"], 600),             # per-share option price
                    (_money(s["prem"] * sh) if s else "…", "right", c["pos"] if s else c["muted"], 800),
                    (_money(cap), "right", c["text"], 700),
                    (f"{cap / tot_cap * 100:.0f}%" if tot_cap else "—", "right", c["muted"], 600),
                    (f"{sh}", "right", c["muted"], 600),
                    (_m2(s["prev_close"]) if (s and s.get("prev_close")) else "—", "right", c["muted"], 600),
                    (f"{s['chg_pct']:+.1f}%" if (s and s.get("chg_pct") is not None) else "—", "right",
                     (c["pos"] if (s and (s.get("chg_pct") or 0) >= 0) else c["neg"]) if s else c["muted"], 700),
                ]
                tds = "".join(f"<td style='border:1px solid {c['border']};padding:7px 12px;text-align:{al};"
                              f"color:{cl};font-weight:{fw};white-space:nowrap;font-size:13px;'>{v}</td>"
                              for v, al, cl, fw in mcells)
                mrows += f"<tr style='background:{c['panel']};'>{tds}</tr>"
            # TOTAL row: average AOR (capital-weighted), total premium, total cash reserve, total shares
            tot_loss = sum((sug[p["stock"]]["strike"] - p["wstrike"]) * p["shares"]
                           for p in members if sug.get(p["stock"]))     # total capital P/L if all called (= header 'vs strike')
            tot_uw = sum((p["cur"] - p["wstrike"]) * p["shares"] for p in members)   # total current paper P/L vs original strike
            fcells = [
                ("TOTAL", "left", c["text"], 900), ("", "left", c["muted"], 600),
                ("", "right", c["muted"], 600), ("", "right", c["muted"], 600),    # orig strike, break even
                ("", "right", c["muted"], 600),                                    # current
                (_money(tot_uw), "right", c["pos"] if tot_uw >= 0 else c["neg"], 900),   # under water
                ("", "right", c["muted"], 600),                                    # CC Nw
                (_money(tot_loss), "right", c["pos"] if tot_loss >= 0 else c["neg"], 900),   # if called
                (f"{g['aor']:.0f}%", "right", warn, 900),
                ("", "right", c["muted"], 600),                                    # prem/sh (no total)
                (_money(tot_prem), "right", c["pos"], 900),
                (_money(tot_cap), "right", c["text"], 900),
                ("100%", "right", c["muted"], 700),
                (f"{tot_sh}", "right", c["muted"], 700),
                ("", "right", c["muted"], 600), ("", "right", c["muted"], 600),   # yesterday, % chg
            ]
            ftds = "".join(f"<td style='border:1px solid {c['border']};padding:8px 13px;text-align:{al};"
                           f"color:{cl};font-weight:{fw};white-space:nowrap;font-size:13px;'>{v}</td>"
                           for v, al, cl, fw in fcells)
            st.markdown(f"<div style='overflow:auto;border:1px solid {c['border']};border-radius:0 0 10px 10px;'>"
                        f"<table style='border-collapse:collapse;width:100%;'>"
                        f"<thead><tr>{mhead}</tr></thead><tbody>{mrows}</tbody>"
                        f"<tfoot><tr style='background:{c['raised']};'>{ftds}</tr></tfoot></table></div>",
                        unsafe_allow_html=True)
        return

    # ── Positions table ──
    hdrs = ("STOCK", "AC", "STRK", "BREAK EVEN", "NOW", "UNDER WATER", "↓ %", "SH",
            f"CC {weeks}w", "IF CALLED", "↑ vs NOW", "Δ", "PREM", "AOR")
    head = "".join(f"<th style='position:sticky;top:0;background:{c['raised']};color:{c['text']};"
                   f"border:1px solid {c['border']};padding:8px 12px;text-align:{'left' if i < 2 else 'right'};"
                   f"font-weight:800;font-size:12.5px;white-space:nowrap;'>{h}</th>" for i, h in enumerate(hdrs))
    rows = ""
    for p in piles:
        s = sug.get(p["stock"])
        strike_col = be_col = None
        if s:
            strike_col = c["pos"] if s["strike"] >= p["wstrike"] else c["neg"]   # orig strike vs CC strike
            be_col = c["pos"] if s["strike"] >= p["wbe"] else c["neg"]           # break-even vs CC strike
        otm = ((s["strike"] - p["cur"]) / p["cur"] * 100) if (s and p["cur"]) else None
        under_col = c["neg"] if (p["under"] or 0) < 0 else c["pos"]
        cells = [
            (p["stock"], "left", c["text"], 800),
            (p["acct"], "left", c["muted"], 700),
            (_m2(p["wstrike"]), "right", strike_col or c["muted"], 700),
            (_m2(p["wbe"]), "right", be_col or c["text"], 800),
            (_m2(p["cur"]), "right", c["muted"], 600),
            (_money((p["cur"] - p["wstrike"]) * p["shares"]), "right",
             c["pos"] if (p["cur"] - p["wstrike"]) >= 0 else c["neg"], 800),
            (f"{p['under']:+.0f}%" if p["under"] is not None else "—", "right", under_col, 800),
            (f"{p['shares']}", "right", c["muted"], 600),
            (_m2(s["strike"]) if s else "…", "right", c["text"], 700),
            (_money((s["strike"] - p["wstrike"]) * p["shares"]) if s else "…", "right",
             (c["pos"] if (s["strike"] - p["wstrike"]) >= 0 else c["neg"]) if s else c["muted"], 800),
            (f"+{otm:.0f}%" if otm is not None else "—", "right", c["accent"] if "accent" in c else c["text"], 700),
            (f"{s['delta']:.2f}" if s else "…", "right", c["muted"], 600),
            (_m2(s["prem"]) if s else "…", "right", c["pos"] if s else c["muted"], 700),
            (f"{s['aor']:.0f}%" if (s and s["aor"] is not None) else "…", "right",
             c.get("warn", c["text"]) if s else c["muted"], 800),
        ]
        tds = "".join(f"<td style='border:1px solid {c['border']};padding:7px 12px;text-align:{al};"
                      f"color:{cl};font-weight:{fw};white-space:nowrap;font-size:13px;'>{v}</td>"
                      for v, al, cl, fw in cells)
        rows += f"<tr style='background:{c['panel']};'>{tds}</tr>"
    st.markdown(f"<div style='overflow:auto;max-height:620px;border:1px solid {c['border']};border-radius:9px;'>"
                f"<table style='border-collapse:collapse;width:max-content;min-width:100%;'>"
                f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>", unsafe_allow_html=True)
    st.caption("STRIKE & BREAK EVEN tinted green when the suggested CC is at/above basis, red when below.")
