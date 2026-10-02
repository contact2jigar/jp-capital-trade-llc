"""Candidate Hunt — size scanned candidates against per-account gates, rank by AOR.

The flagship decision engine. It NEVER places an order: it takes the candidates a
Candidate-Hunt scan found (ticker · setup · strike · Δ · premium · AOR), sizes each
against the live per-account gates, ranks by AOR, and names the binding gate.

Gates (per account, from the Monitor Board math + current per-name exposure):
  • 5% name cap  — no position over 5% of that account's Wheel Capital (STRICT).
  • Layer 2.5%   — max 2.5% of Wheel Capital as a same-day entry per name.
  • CSP room     — the account's Ready-to-deploy (VIX Target − Deployed).
  • CC Breaker   — ≥45% freezes NEW CSPs in that account.
Contracts = floor(min(room) / (strike × 100)). The binding gate is the tightest one.
"""

from __future__ import annotations

import math
import re

import pandas as pd

from logic import gtc_refresh
from logic import monitor as mb

NAME_CAP = 0.05      # 5% of Wheel Capital per name (STRICT, LOCKED 9/18)
LAYER = 0.025        # 2.5% same-day entry per name (LOCKED 9/18)
BREAKER = 0.45       # CC Breaker freeze threshold (v16)
STARTER_CEIL = 0.07  # a 1-lot starter may tip over 5% only up to 7% of Wheel Cap (9/27)


def _num(v):
    """'$145' / '4.15' / 145 / '46%' → float. None if blank/unparseable."""
    if v is None:
        return None
    s = str(v).replace("$", "").replace(",", "").replace("%", "").strip()
    if s in ("", "—", "None", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _name_exposure(od: pd.DataFrame, acct: str, ticker: str) -> float:
    """Open Cash Reserve already committed to `ticker` in `acct` (for the 5% cap)."""
    d = od[(od["Account"].astype(str).str.upper() == acct)
           & (od["Stock"].astype(str).str.upper() == ticker.upper())]
    return float(d["Cash Reserve"].map(mb._money).sum()) if "Cash Reserve" in d else 0.0


def _size_one(cand: dict, accts: dict, od: pd.DataFrame, dte: int) -> dict:
    tk = str(cand["Ticker"]).upper()
    strike = _num(cand.get("Strike"))
    prem = _num(cand.get("Prem"))
    aor = _num(cand.get("AOR"))
    delta = _num(cand.get("Δ"))
    cash_pc = (strike or 0) * 100                       # collateral per contract
    per = {}
    for a, d in accts.items():
        wcap = d["wcap"]
        exposure = _name_exposure(od, a, tk)
        cap_room = NAME_CAP * wcap - exposure            # room under the 5% name cap (HARD)
        csp_room = d["rtd"]                              # account Ready-to-deploy (HARD)
        layer_room = LAYER * wcap                        # 2.5% same-day ceiling (soft — 1 ctr exempt)
        frozen = d["ccbrk"] >= BREAKER
        n_cap = int(cap_room // cash_pc) if cash_pc > 0 else 0
        n_csp = int(csp_room // cash_pc) if cash_pc > 0 else 0
        n_layer = int(layer_room // cash_pc) if cash_pc > 0 else 0
        # The 1-lot starter exception applies ONLY to a FRESH name (no existing
        # position) whose single lot tips just over 5% — up to 7% of Wheel Cap. If the
        # name is already held, we may only ADD what fits strictly under 5% (n_cap);
        # topping up past the cap is never allowed. A name at/over 5% is a hard block.
        fresh = exposure <= 0
        starter_ok = fresh and cash_pc <= STARTER_CEIL * wcap
        cap_eff = max(n_cap, 1) if starter_ok else n_cap
        if frozen or n_csp <= 0 or cap_room <= 0 or cap_eff <= 0:
            n = 0
        else:
            n = min(n_csp, cap_eff, max(n_layer, 1))

        if frozen:
            binding = "CC Breaker"
        elif cap_room <= 0 or cap_eff <= 0:
            binding = "5% name cap"
        elif n_csp <= 0:
            binding = "CSP room"
        else:
            opts = {"5% name cap": cap_eff, "Layer 2.5%": max(n_layer, 1), "CSP room": n_csp}
            binding = min(opts, key=opts.get)
        per[a] = dict(n=n, binding=binding, cap_room=cap_room, exposure=exposure,
                      held_pct=(exposure / wcap * 100 if wcap else 0.0),
                      lot_pct=(cash_pc / wcap * 100 if wcap else 0.0),
                      over_cap=(n_cap <= 0 and n > 0))

    ira, llc = per["IRA"], per["LLC"]
    best, decision, why = None, "BLOCKED", ""
    if ira["n"] == 0 and llc["n"] == 0:
        b_ira, b_llc = ira["binding"], llc["binding"]
        if "CC Breaker" in (b_ira, b_llc):
            why = "CC Breaker frozen — new CSPs halted"
        elif b_ira == "5% name cap" and b_llc == "5% name cap":
            # Describe the account closest to fitting (the most cap room).
            close = ira if ira["cap_room"] >= llc["cap_room"] else llc
            if close["cap_room"] <= 0:
                why = f"Already over the 5% cap (held {close['held_pct']:.1f}%)"
            elif close["held_pct"] <= 0.05:      # fresh, but 1 lot too big
                why = f"One lot is {close['lot_pct']:.1f}% — over the {STARTER_CEIL * 100:.0f}% cap ceiling"
            else:                                # already held — adding would breach 5%
                why = f"Adding one lot breaches the 5% cap (held {close['held_pct']:.1f}%)"
        elif b_ira == "CSP room" and b_llc == "CSP room":
            why = "No CSP room left in either account"
        else:
            why = f"Blocked — {b_ira} / {b_llc}"
    else:
        best = "IRA" if ira["n"] >= llc["n"] else "LLC"
        # Show EVERY account that can take it, not just the preferred one.
        parts = [f"{a}·{per[a]['n']}" for a in ("IRA", "LLC") if per[a]["n"] > 0]
        decision = "TRADE · " + " / ".join(parts)
        # Why = the gate that caps the size (per traded account). That's the actual
        # binding constraint — e.g. "Size capped by Layer 2.5%" means you could take
        # more but the same-day layer limits it.
        binds = []
        for a in ("IRA", "LLC"):
            if per[a]["n"] > 0 and per[a]["binding"] not in binds:
                binds.append(per[a]["binding"])
        why = "Size capped by " + " / ".join(binds)

    gtc = gtc_refresh.gtc_target(prem, dte) if prem is not None else None
    cur = _num(cand.get("Price"))
    disc = _num(cand.get("Cushion"))                       # % below current (from the scan)
    if disc is None and cur and strike:
        disc = (cur - strike) / cur * 100
    disc3 = _num(cand.get("3mo ↓"))                         # % below the 3-month high
    return dict(ticker=tk, setup=_clean_setup(cand.get("Setup")), strike=strike, delta=delta,
                prem=prem, aor=aor, iv=_num(cand.get("IV")),
                industry=(cand.get("Industry") or "—"), cash_pc=cash_pc, gtc=gtc, dte=dte,
                cur=cur, chg=_num(cand.get("Chg%")), disc=disc, disc3=disc3,
                ira=ira, llc=llc, best=best, decision=decision, why=why,
                tradable=best is not None)


def _clean_setup(s) -> str:
    """'✓ IV Drop · Reversal' → 'IV Drop' (first, the precedence winner)."""
    s = str(s or "").replace("✓", "").strip()
    return s.split("·")[0].strip() if s and s != "—" else "—"


def _earn_days(earn: str) -> str:
    m = re.search(r"\((\d+)d\)", str(earn))
    return f"{m.group(1)}d" if m else ""


def _blank_row(cand: dict, dte: int) -> dict:
    """Display fields for a name we don't size (vetoed / below AOR) — no room calc."""
    strike, prem, aor = _num(cand.get("Strike")), _num(cand.get("Prem")), _num(cand.get("AOR"))
    gtc = gtc_refresh.gtc_target(prem, dte) if prem is not None else None
    return dict(ticker=str(cand["Ticker"]).upper(), setup=_clean_setup(cand.get("Setup")),
                strike=strike, delta=_num(cand.get("Δ")), prem=prem, aor=aor,
                iv=_num(cand.get("IV")), industry=(cand.get("Industry") or "—"), cash_pc=None,
                gtc=gtc, dte=dte, cur=_num(cand.get("Price")), chg=_num(cand.get("Chg%")),
                disc=_num(cand.get("Cushion")),
                disc3=_num(cand.get("3mo ↓")), ira=None, llc=None, best=None, tradable=False)


def size(candidates: pd.DataFrame, tl_df: pd.DataFrame, ath_ira: float, ath_llc: float,
         vix: float, vix_chg: float, trend: str, dte: int, min_aor: float,
         expiry: str = "") -> dict:
    """Full Decision-Desk payload: board capacity + ranked candidate rows.

    Every setup-fired name meeting the AOR floor is shown. A name that fails the
    quality/earnings veto is marked VETO (with the reason) and NOT sized — so it
    can never get a TRADE/BLOCKED decision for the wrong reason (fixes AMD RSI 73).
    Names passing the veto are sized against the per-account gates."""
    board = mb.monitor_board(tl_df, ath_ira, ath_llc, vix, vix_chg, trend)
    od = mb._openrows(tl_df)
    accts = {"IRA": board["ira"], "LLC": board["llc"]}

    rows = []
    for _, cand in candidates.iterrows():
        d = cand.to_dict()
        setup = str(d.get("Setup", ""))
        strike = _num(d.get("Strike"))
        if not setup.startswith("✓") or strike in (None, 0):
            continue

        aor, rsi = _num(d.get("AOR")), _num(d.get("RSI"))
        delta = _num(d.get("Δ"))
        bb = str(d.get("BB", "")).lower()
        earn = str(d.get("Earnings", "")).strip()

        # Per-factor gates (each a red/green column).
        em = re.search(r"\((\d+)d\)", earn)
        edays = int(em.group(1)) if em else None
        aor_ok = aor is not None and aor >= min_aor
        if not aor_ok:
            continue                      # below the AOR floor → not a candidate, don't list it
        rsi_ok = rsi is None or rsi < 64
        bb_ok = not ("upper" in bb or "above" in bb)
        earn_ok = edays is None or edays > dte            # veto only if ON/BEFORE expiry
        delta_ok = delta is None or delta <= 0.30
        veto_ok = rsi_ok and bb_ok and earn_ok            # framework hard vetoes

        # Only size the name if it clears the vetoes — otherwise no room calc.
        if veto_ok:
            row = _size_one(d, accts, od, dte)
            room_ok = bool(row["tradable"])
        else:
            row = _blank_row(d, dte)
            room_ok = False

        go = veto_ok and aor_ok and delta_ok and room_ok
        # The single reason we're not a GO (first failing gate, in precedence).
        if not earn_ok:
            why = f"Earnings in {edays}d (≤ {dte}d exp)"
        elif not rsi_ok:
            why = f"RSI {rsi:.0f} ≥ 64"
        elif not bb_ok:
            why = "Near high BB"
        elif not delta_ok:
            why = f"Δ {delta:.2f} > 0.30"
        elif not aor_ok:
            why = f"AOR {aor:.0f}% < {min_aor:.0f}%" if aor is not None else "No AOR"
        elif not room_ok:
            why = row.get("why") or "No room"
        else:
            why = row.get("why") or "Clear"

        row.update(expiry=expiry, rsi=(f"{rsi:.0f}" if rsi is not None else "—"),
                   bb=(d.get("BB") or "—"), earn=(earn or "—"), fin=(d.get("Financials") or "—"),
                   aor_ok=aor_ok, rsi_ok=rsi_ok, bb_ok=bb_ok, earn_ok=earn_ok,
                   delta_ok=delta_ok, room_ok=room_ok, veto_ok=veto_ok,
                   go=go, decision=("GO" if go else "NO"), why=why)
        rows.append(row)

    # GO first, then the rest — each by AOR descending.
    rows.sort(key=lambda r: (0 if r["go"] else 1, -(r["aor"] or 0)))
    go_rows = [r for r in rows if r["go"]]
    return dict(board=board, rows=rows, tradable=go_rows, n_tradable=len(go_rows),
                n_blocked=len(rows) - len(go_rows), best=(go_rows[0] if go_rows else None))
