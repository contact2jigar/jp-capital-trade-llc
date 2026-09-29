"""WheelEngine BOT — watches the open book and alerts only when there is
something to DO.

  ROLL    the sheet's Action column says Roll up / Roll down
  EXPIRY  <= 3 DTE and ITM with no roll flagged
  GTC     the position reached its ladder price
  CUT     Action says Cut Loss

It reads the TradeLog (the sheet is the source of truth) and NEVER places an
order. State lives in bot/state.json so nothing alerts twice.
"""
from __future__ import annotations
import sys, json, hashlib
from pathlib import Path
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from services import gsheet          # noqa: E402
from bot import notify               # noqa: E402
from bot import basis as basis_src   # noqa: E402

STATE = HERE / "state.json"
EXPIRY_DTE = 3          # flag ITM positions inside this many days
ROLL_RECHECK = 0.25     # re-alert a roll only if it moves 25%+
DIGEST_OVER  = 3        # more than this in one run -> one summary, not N pings
OPEN_AT  = dtime(10, 0)   # Yahoo option chains (deltas) are not live until ~9:55 ET
CLOSE_AT = dtime(15, 55)
ET = ZoneInfo("America/New_York")
LOG = HERE / "bot.log"


def market_open_now() -> bool:
    n = datetime.now(ET)
    return n.weekday() < 5 and OPEN_AT <= n.time() <= CLOSE_AT


def log(msg: str) -> None:
    with LOG.open("a") as f:
        f.write(f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} {msg}\n")


def status() -> None:
    st = load_state()
    hb = st.get("_heartbeat", {})
    last = hb.get("at", "never")
    print(f"  last run     {last}")
    print(f"  runs today   {hb.get('runs_today', 0)}")
    print(f"  market open  {market_open_now()}")
    print(f"  sms channel  {'ready' if notify.sms_available() else 'not configured'}")
    today = date.today().isoformat()
    fired = [k for k, v in st.items()
             if k != "_heartbeat" and isinstance(v, dict) and v.get("day") == today]
    print(f"  alerted today ({len(fired)})")
    for k in fired:
        print(f"    {k.replace('::', '  ')}")
    import subprocess
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    loaded = "com.jp.wheelengine.bot" in r.stdout
    print(f"  scheduler    {'LOADED — running every 20 min' if loaded else 'not installed'}")


# ── state ────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=2, default=str))


def key(r) -> str:
    return f"{r['Stock']}|{r['Account']}|{r['Opt Typ']}|{r['Strike Price']:g}|{r['Exp Date']}"


# ── scan ─────────────────────────────────────────────────────────────────
def open_book():
    tl = gsheet.tradelog()
    tl.columns = [str(c).strip() for c in tl.columns]
    op = tl[tl["Status"].astype(str).str.upper().str.startswith("OPEN")].copy()
    op = op[op["Opt Typ"].astype(str).str.upper().isin(["PUT", "CALL", "LEAP"])]
    return op


def itm(r) -> bool:
    t = str(r["Opt Typ"]).upper()
    px, k = r["Current Price"], r["Strike Price"]
    if any(x != x for x in (px, k)):      # NaN
        return False
    return px < k if t == "PUT" else px > k


def build_alerts(op) -> list[dict]:
    out = []
    BASIS = basis_src.share_basis()
    for _, r in op.iterrows():
        act = str(r.get("Action", "")).strip()
        dte = r.get("DTE")
        tick, acct = r["Stock"], r["Account"]
        typ, strike = str(r["Opt Typ"]).upper(), r["Strike Price"]
        qty, px = r.get("Qty"), r.get("Current Price")
        cur, gtc = r.get("Current Prem"), r.get("GTC")
        cap = str(r.get("% Captured", "")).strip()
        pos = f"{tick} {acct} {r['Exp Date']} ${strike:g} {typ}"

        # ✅ GTC reached
        if gtc == gtc and cur == cur and gtc and cur <= gtc:
            out.append(dict(kind="GTC", k=key(r), title=f"✅ GTC HIT · {tick}",
                            sub=f"{acct} · ${strike:g} {typ}",
                            body=f"{pos}\nmark ${cur:.2f} <= GTC ${gtc:.2f}\n"
                                 f"slot open · ${strike*100*(qty or 1):,.0f} freed",
                            val=float(cur)))
            continue

        # 🔄 roll flagged by the sheet
        if act.lower().startswith("roll"):
            # A CALL whose strike is at/above your share basis is NOT a roll —
            # your rule is let it assign, no greed rolls. Suppress it.
            if typ == "CALL":
                b = BASIS.get((str(tick).upper(), str(acct).upper()))
                if b is not None and strike >= b:
                    continue
            out.append(dict(kind="ROLL", k=key(r), title=f"🔄 {act.upper()} · {tick}",
                            sub=f"{acct} · {dte:.0f} DTE" if dte == dte else acct,
                            body=f"{pos}\npx ${px:,.2f} vs ${strike:g} · "
                                 f"{'ITM' if itm(r) else 'OTM'}\n"
                                 f"prem ${r['Init Prem']:.2f} -> ${cur:.2f} · {cap}",
                            val=float(cur) if cur == cur else 0.0))
            continue

        # ⛔ cut loss flagged by the sheet
        if "cut" in act.lower():
            out.append(dict(kind="CUT", k=key(r), title=f"⛔ CUT LOSS · {tick}",
                            sub=f"{acct} · {typ}",
                            body=f"{pos}\n{cap} · sheet flags Cut Loss",
                            val=0.0))
            continue

        # ⏰ expiring ITM with nothing queued
        if dte == dte and dte <= EXPIRY_DTE and itm(r):
            out.append(dict(kind="EXPIRY", k=key(r), title=f"⏰ EXPIRY · {tick}",
                            sub=f"{acct} · {dte:.0f} DTE",
                            body=f"{pos}\nITM ${abs(px-strike):,.2f} · no action flagged",
                            val=float(dte)))
    return out


def fire(alerts, state, dry=False) -> list[dict]:
    """Send only what is new or materially changed. Returns what was sent."""
    today, sent = date.today().isoformat(), []
    for a in alerts:
        sk = f"{a['k']}::{a['kind']}"
        prev = state.get(sk)
        if prev:
            if a["kind"] == "GTC":                       # one-time event
                continue
            if prev.get("day") == today:                 # once a day
                pv = prev.get("val") or 0
                moved = abs(a["val"] - pv) / pv > ROLL_RECHECK if pv else False
                if not (a["kind"] == "ROLL" and moved):
                    continue
        state[sk] = {"day": today, "val": a["val"],
                     "at": datetime.now().isoformat(timespec="seconds")}
        sent.append(a)

    if dry or not sent:
        return sent

    if len(sent) > DIGEST_OVER:                      # one summary
        lines = [f"{a['title'].split(' · ')[0]} {a['title'].split(' · ')[-1]} "
                 f"{a['sub'].split(' · ')[0]}" for a in sent]
        notify.send(f"🔔 {len(sent)} actions on the book",
                    datetime.now().strftime("%a %H:%M"),
                    "\n".join(lines), kind="EXPIRY")
    else:
        for a in sent:
            notify.send(a["title"], a["sub"], a["body"], kind=a["kind"])
    return sent


def main(dry=False, force=False):
    if not force and not dry and not market_open_now():
        log("skip — market closed")
        return []
    op = open_book()
    alerts = build_alerts(op)
    state = load_state()
    sent = fire(alerts, state, dry=dry)
    if not dry:
        today = date.today().isoformat()
        hb = state.get("_heartbeat", {})
        state["_heartbeat"] = {
            "at": datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "runs_today": (hb.get("runs_today", 0) + 1) if hb.get("day") == today else 1,
            "day": today}
        save_state(state)
        log(f"{len(op)} open · {len(alerts)} actionable · {len(sent)} sent")
    stamp = datetime.now().strftime("%H:%M")
    print(f"[{stamp}] {len(op)} open · {len(alerts)} actionable · {len(sent)} sent"
          f"{' (DRY)' if dry else ''}")
    for a in sent:
        print(f"  {a['title']}  {a['sub']}")
    return sent


if __name__ == "__main__":
    if "--status" in sys.argv:
        status()
    else:
        main(dry="--dry" in sys.argv, force="--force" in sys.argv)
