"""Candidate Hunt — size scanned candidates against per-account gates, rank by AOR.

The flagship decision engine. It NEVER places an order: it takes the candidates a
Candidate-Hunt scan found (ticker · setup · strike · Δ · premium · AOR), sizes each
against the live per-account gates, ranks by AOR, and names the binding gate.

Gates (from the Monitor Board math + current per-name exposure):
  • 5% name cap  — no position over 5% of the COMBINED (IRA+LLC) Wheel Capital — a shared
                   budget on total single-name exposure, not per-account (STRICT). 1-lot
                   starter may tip to 7% of combined.
  • Layer 2.5%   — max 2.5% of the account's Wheel Capital as a same-day entry per name.
  • CSP room     — the account's Ready-to-deploy (VIX Target − Deployed) — per account.
  • CC Breaker   — ≥45% freezes NEW CSPs in that account — per account.
Contracts = floor(min(room) / (strike × 100)). The binding gate is the tightest one.
"""

from __future__ import annotations

import math
import re

import pandas as pd

from logic import gtc_refresh
from logic import monitor as mb

NAME_CAP = 0.05      # 5% of COMBINED (IRA+LLC) Wheel Capital per name (STRICT · combined basis Oct 8 2026)
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

    # ── 5% name cap is COMBINED (IRA + LLC): a shared budget on TOTAL single-name exposure,
    # not a per-account check. A high-priced lot that won't fit either account's 5% alone still
    # fits when it's under 5% of the WHOLE wheel (AMAT 4.1%). This is TIGHTER on total
    # concentration than the old per-account rule, which allowed up to 10% across two accounts.
    exp = {a: _name_exposure(od, a, tk) for a in accts}
    tot_wcap = sum((d.get("wcap") or 0) for d in accts.values())
    tot_exp = sum(exp.values())
    cap_room = NAME_CAP * tot_wcap - tot_exp             # $ room under the combined 5% cap (HARD)
    n_cap = int(cap_room // cash_pc) if cash_pc > 0 else 0
    fresh = tot_exp <= 0
    starter_ok = fresh and cash_pc <= STARTER_CEIL * tot_wcap   # 1-lot starter up to 7% of COMBINED
    cap_eff = max(n_cap, 1) if starter_ok else n_cap
    held_comb = (tot_exp / tot_wcap * 100) if tot_wcap else 0.0
    lot_comb = (cash_pc / tot_wcap * 100) if tot_wcap else 0.0

    # Per-account constraints that STAY per-account: CSP room (ready-to-deploy), layer, breaker.
    per = {}
    for a, d in accts.items():
        wcap = d.get("wcap") or 0
        frozen = d["ccbrk"] >= BREAKER
        n_csp = int(d["rtd"] // cash_pc) if cash_pc > 0 else 0
        n_layer = int((LAYER * wcap) // cash_pc) if cash_pc > 0 else 0
        per[a] = dict(frozen=frozen, n_csp=n_csp, n_layer=n_layer, exposure=exp[a], wcap=wcap,
                      n=0, binding="", cap_room=cap_room,
                      held_pct=(exp[a] / wcap * 100 if wcap else 0.0),
                      lot_pct=(cash_pc / wcap * 100 if wcap else 0.0), over_cap=False)

    # Allocate the COMBINED cap budget across accounts (preferred = more CSP room first) so the
    # per-account lots (IRA·x + LLC·y) never sum past the combined cap.
    remaining = cap_eff if (cap_room > 0 and cap_eff > 0) else 0
    for a in sorted(accts.keys(), key=lambda k: per[k]["n_csp"], reverse=True):
        p = per[a]
        if not (p["frozen"] or p["n_csp"] <= 0 or remaining <= 0):
            p["n"] = min(p["n_csp"], max(p["n_layer"], 1), remaining)
            remaining -= p["n"]
        if p["frozen"]:
            p["binding"] = "CC Breaker"
        elif cap_eff <= 0:
            p["binding"] = "5% name cap"
        elif p["n_csp"] <= 0:
            p["binding"] = "CSP room"
        elif p["n"] == 0:                               # combined cap already used by the other acct
            p["binding"] = "5% name cap"
        else:
            opts = {"5% name cap": cap_eff, "Layer 2.5%": max(p["n_layer"], 1), "CSP room": p["n_csp"]}
            p["binding"] = min(opts, key=opts.get)
        p["over_cap"] = (n_cap <= 0 and p["n"] > 0)

    ira, llc = per["IRA"], per["LLC"]
    best, decision, why = None, "BLOCKED", ""
    if ira["n"] == 0 and llc["n"] == 0:
        b_ira, b_llc = ira["binding"], llc["binding"]
        if "CC Breaker" in (b_ira, b_llc) and "5% name cap" not in (b_ira, b_llc):
            why = "CC Breaker frozen — new CSPs halted"
        elif "5% name cap" in (b_ira, b_llc):
            if cap_room <= 0:
                why = f"Already over the 5% combined cap (held {held_comb:.1f}%)"
            elif cap_eff <= 0:                          # fresh/under but 1 lot too big for 7% ceiling
                why = f"One lot is {lot_comb:.1f}% — over the {STARTER_CEIL * 100:.0f}% combined cap ceiling"
            else:
                why = f"Adding one lot breaches the 5% combined cap (held {held_comb:.1f}%)"
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
                industry=(cand.get("Industry") or "—"), cash=_num(cand.get("Cash")),
                cash_pc=cash_pc, gtc=gtc, dte=dte,
                cur=cur, chg=_num(cand.get("Chg%")), disc=disc, disc3=disc3,
                ira=ira, llc=llc, best=best, decision=decision, why=why,
                tradable=best is not None)


def _clean_setup(s) -> str:
    """'✓ IV Drop · Reversal' → 'IV Drop' (first, the precedence winner)."""
    s = str(s or "").replace("✓", "").strip()
    return s.split("·")[0].strip() if s and s != "—" else "—"


def _all_setups(s) -> str:
    """'✓ IV Drop · Reversal' → 'IV Drop · Reversal' — every trigger that fired, not just the first."""
    s = str(s or "").replace("✓", "").strip()
    return s if (s and s != "—") else "—"


def _earn_days(earn: str) -> str:
    m = re.search(r"\((\d+)d\)", str(earn))
    return f"{m.group(1)}d" if m else ""


def _blank_row(cand: dict, dte: int) -> dict:
    """Display fields for a name we don't size (vetoed / below AOR) — no room calc."""
    strike, prem, aor = _num(cand.get("Strike")), _num(cand.get("Prem")), _num(cand.get("AOR"))
    gtc = gtc_refresh.gtc_target(prem, dte) if prem is not None else None
    return dict(ticker=str(cand["Ticker"]).upper(), setup=_clean_setup(cand.get("Setup")),
                strike=strike, delta=_num(cand.get("Δ")), prem=prem, aor=aor,
                iv=_num(cand.get("IV")), industry=(cand.get("Industry") or "—"),
                cash=_num(cand.get("Cash")), cash_pc=None,
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
        # Earnings unknown ("unknown") is NOT clear — could report inside the window.
        earn_unknown = "unknown" in earn.lower()
        earn_ok = (not earn_unknown) and (edays is None or edays > dte)  # veto if ON/BEFORE expiry
        # IV ≫ realized vol = the option is pricing an event (merger/litigation/FDA),
        # not normal premium — flag it and keep it out of GO.
        ivrv = _num(d.get("IV/RV"))
        event_ok = ivrv is None or ivrv <= 1.5
        delta_ok = delta is None or delta <= 0.30
        veto_ok = rsi_ok and bb_ok and earn_ok and event_ok           # framework hard vetoes

        # Only size the name if it clears the vetoes — otherwise no room calc.
        if veto_ok:
            row = _size_one(d, accts, od, dte)
            room_ok = bool(row["tradable"])
        else:
            row = _blank_row(d, dte)
            room_ok = False

        go = veto_ok and aor_ok and delta_ok and room_ok
        # The single reason we're not a GO (first failing gate, in precedence).
        if earn_unknown:
            why = "Earnings date unknown — verify"
        elif not earn_ok:
            why = f"Earnings in {edays}d (≤ {dte}d exp)"
        elif not event_ok:
            why = f"IV/RV {ivrv:.1f}× — event-driven"
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
                   off4=_num(d.get("Off4mo")),
                   offhigh=_num(str(d.get("% off High") or "").replace("%", "")),
                   cush=_num(str(d.get("Cushion") or "").replace("%", "")),
                   pe=_num(d.get("P/E")),
                   setup_full=_all_setups(d.get("Setup")),
                   stype=(str(d.get("Type") or "—").strip() or "—"),
                   bbpct=_num(d.get("%B")),
                   name=(d.get("Name") or "—"),
                   aor_ok=aor_ok, rsi_ok=rsi_ok, bb_ok=bb_ok, earn_ok=earn_ok,
                   delta_ok=delta_ok, room_ok=room_ok, veto_ok=veto_ok,
                   go=go, decision=("GO" if go else "NO"), why=why)
        rows.append(row)

    # GO first, then the rest — each by AOR descending.
    rows.sort(key=lambda r: (0 if r["go"] else 1, -(r["aor"] or 0)))
    go_rows = [r for r in rows if r["go"]]
    return dict(board=board, rows=rows, tradable=go_rows, n_tradable=len(go_rows),
                n_blocked=len(rows) - len(go_rows), best=(go_rows[0] if go_rows else None))
