"""Candidate-Hunt bot — runs the app's own Decision Desk logic on a schedule and alerts.

Calls csp_scanner._scan() and logic.candidate_hunt.size() directly, so the bot and the
Decision Desk can never drift. NEVER places an order.

  python3 bot/hunt.py --dry      scan + print, send nothing
  python3 bot/hunt.py --force    run outside market hours
  python3 bot/hunt.py --loose    keep green / sub-floor rows (filters are ON by default)
  python3 bot/hunt.py --status   last run + what is armed
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from bot import notify  # noqa: E402

STATE = HERE / "hunt_state.json"
LOG = HERE / "hunt.log"
ET = ZoneInfo("America/New_York")
OPEN_AT, CLOSE_AT = dtime(10, 0), dtime(16, 0)   # Yahoo chains aren't live before ~9:55
# Gate 3 v17 tiers — a flat floor let CAVA 39% and SKHY 43% through as GO
MEGA = {"AMZN", "AVGO", "NVDA", "TSLA"}
AOR_MEGA, AOR_PLTR, AOR_REST = 27.0, 40.0, 47.0
AOR_SANITY = 150.0      # above this it is a data artifact, not an opportunity
                        # (ALLT 154%, SNAP 374% both ranked #1 on bad chains)
PRICE_MIN = 30.0        # roster screen floor; no ceiling here — it would block
                        # the megas and the names already held above $255
AOR_RECHECK = 0.15      # re-alert an existing name only if AOR moves 15%+
DIGEST_OVER = 3


def log(msg: str) -> None:
    with LOG.open("a") as f:
        f.write(f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} {msg}\n")


def market_open_now() -> bool:
    n = datetime.now(ET)
    return n.weekday() < 5 and OPEN_AT <= n.time() <= CLOSE_AT


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=1))


def run_hunt() -> dict:
    """The app's exact pipeline, headless. Only st.progress is stubbed."""
    import streamlit as st

    class _Bar:                      # headless stand-in for st.progress
        def progress(self, *a, **k): return None
        def empty(self, *a, **k): return None
    st.progress = lambda *a, **k: _Bar()

    from ui.pages import csp_scanner, candidate_hunt as chp
    from logic import candidate_hunt as hunt

    inp = csp_scanner.default_hunt_inputs()
    if not inp:
        raise RuntimeError("WatchList or expiry list is empty")
    df = chp._tradelog()
    ext, mkt = chp._externals(), chp._market()
    vix = mkt.get("vix") or ext.get("vix") or 16.0
    vchg = mkt.get("vix_chg") or ext.get("vix_chg") or 0.0
    trend = mkt.get("trend") or ext.get("trend") or "Uptrend"
    ath_ira, ath_llc = ext.get("ath_ira", 0), ext.get("ath_llc", 0)

    cands = csp_scanner._scan(inp["stocks"], inp["cat_map"], inp["exp_iso"],
                              inp["aor"], inp["delta"], vix)
    payload = hunt.size(cands, df, ath_ira, ath_llc, vix, vchg, trend,
                        inp["dte"], inp["aor"], inp["exp_iso"])
    payload["_expiry"], payload["_vix"], payload["_n_scanned"] = inp["exp_iso"], vix, len(inp["stocks"])
    return payload


def aor_floor_for(tk: str) -> float:
    """Gate 3 is three tiers, not one number."""
    tk = str(tk).upper()
    return AOR_MEGA if tk in MEGA else AOR_PLTR if tk == "PLTR" else AOR_REST


def expiry_exists(tk: str, exp_iso: str) -> bool:
    """The scanner prices every name at one target date without checking the
    chain lists it. MOD and ALLT both ranked #1 on expiries that don't exist."""
    try:
        import yfinance as yf
        return exp_iso in (yf.Ticker(str(tk)).options or ())
    except Exception:
        return True          # a feed error is not evidence against the row


def strict_drop(r: dict, exp_iso: str = "") -> str | None:
    """Documented gates the Decision Desk doesn't yet enforce. Returns a reason to skip."""
    tk, px, aor = r.get("ticker"), r.get("cur") or 0, r.get("aor") or 0
    if (r.get("chg") or 0) >= 0:
        return f"green {r.get('chg'):+.1f}%"
    if aor > AOR_SANITY:
        return f"AOR {aor:.0f}% implausible — bad chain"
    floor = aor_floor_for(tk)
    if aor < floor:
        return f"AOR {aor:.0f}% under {floor:.0f}%"
    if px and px < PRICE_MIN:
        return f"${px:,.2f} under ${PRICE_MIN:.0f} floor"
    if exp_iso and not expiry_exists(tk, exp_iso):
        return f"no {exp_iso} chain"
    return None


def build_alerts(payload: dict, strict: bool = True) -> tuple[list[dict], list[str]]:
    """One line per GO candidate, exactly as Jigar reads them:
       HOOD · IV Drop · 47% AOR · $112.64 Current · 106 strike · $3.3 Prem"""
    rows, dropped = [], []
    for r in payload.get("rows", []):
        if str(r.get("decision", "")).upper() != "GO":
            continue
        if strict:
            why = strict_drop(r, payload.get("_expiry", ""))
            if why:
                dropped.append(f"{r.get('ticker')} ({why})")
                continue
        rows.append(r)
    rows.sort(key=lambda r: -(r.get("aor") or 0))
    alerts = [{
        "k": f"{r.get('ticker')}|{r.get('strike')}|{payload['_expiry']}",
        "val": float(r.get("aor") or 0),
        "line": (f"{r.get('ticker')} {r.get('aor'):.0f}% {_setup(r)} · "
                 f"{r.get('cur',0):,.2f}\u2192{r.get('strike'):g} · "
                 f"${r.get('prem',0):.2f} · {_room(r)}"),
    } for r in rows]
    return alerts, dropped


SETUP_NAMES = {"IV": "IV Drop", "IV2": "IV Drop 2-Day", "Rev": "Reversal",
               "DV": "Deep Value", "QP": "Quality Pullback", "SMA50": "50-SMA Recovery"}


def _room(r: dict) -> str:
    """'IRA2 LLC1' — every account with room, so the alert stands on its own."""
    parts = []
    for acct in ("ira", "llc"):
        n = (r.get(acct) or {}).get("n") or 0
        if n > 0:
            parts.append(f"{acct.upper()}{n}")
    return " ".join(parts) or "no room"


def _setup(r: dict) -> str:
    """'📄 IV🟠' -> 'IV Drop'. Strips emoji, keeps the precedence winner, expands short forms."""
    from logic.candidate_hunt import _clean_setup
    s = _clean_setup(r.get("setup"))
    s = "".join(c for c in s if c.isascii()).strip(" -·")
    return SETUP_NAMES.get(s, s) or "—"


def fire(alerts, state, dry=False, expiry="") -> list[dict]:
    """One digest message carrying the whole GO list. New or materially-moved names only."""
    today, sent = date.today().isoformat(), []
    for a in alerts:
        prev = state.get(a["k"])
        if prev and prev.get("day") == today:
            pv = prev.get("val") or 0
            if not (pv and abs(a["val"] - pv) / pv > AOR_RECHECK):
                continue
        state[a["k"]] = {"day": today, "val": a["val"],
                         "at": datetime.now().isoformat(timespec="seconds")}
        sent.append(a)
    if dry or not sent:
        return sent
    notify.send(f"🎯 {len(alerts)} GO · {expiry[5:]}",
                datetime.now().strftime("%a %H:%M"),
                "\n".join(a["line"] for a in alerts), kind="GO")
    return sent


def status() -> None:
    s = load_state()
    hb = s.get("_heartbeat", {})
    print(f"last run   {hb.get('at','never')}")
    print(f"runs today {hb.get('runs_today',0)}")
    names = [k for k in s if not k.startswith("_")]
    print(f"tracked    {len(names)} candidates")
    if LOG.exists():
        print("--- log tail ---")
        print("".join(LOG.read_text().splitlines(keepends=True)[-5:]), end="")


def main(dry=False, force=False, strict=True):
    if not force and not dry and not market_open_now():
        log("skip — market closed")
        return []
    payload = run_hunt()
    alerts, dropped = build_alerts(payload, strict=strict)
    state = load_state()
    sent = fire(alerts, state, dry=dry, expiry=payload["_expiry"])
    if not dry:
        today = date.today().isoformat()
        hb = state.get("_heartbeat", {})
        state["_heartbeat"] = {
            "at": datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "runs_today": (hb.get("runs_today", 0) + 1) if hb.get("day") == today else 1,
            "day": today}
        save_state(state)
        log(f"{payload['_n_scanned']} scanned · {payload.get('n_tradable',0)} GO · "
            f"{len(alerts)} pass strict · {len(sent)} sent")

    stamp = datetime.now().strftime("%H:%M")
    print(f"[{stamp}] {payload['_n_scanned']} scanned · {payload.get('n_tradable',0)} GO · "
          f"{len(alerts)} pass strict · {len(sent)} sent{' (DRY)' if dry else ''}")
    for a in alerts:
        print(f"  {a['line']}")
    if dropped:
        print(f"  dropped by strict gate: {', '.join(dropped)}")
    return sent


if __name__ == "__main__":
    if "--status" in sys.argv:
        status()
    else:
        main(dry="--dry" in sys.argv, force="--force" in sys.argv,
             strict="--loose" not in sys.argv)
