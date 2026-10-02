"""GTC coverage via a small CSV the user maintains.

Fidelity can't export open orders, so the app generates a template of the current
open short puts; the user fills a GTC price for the ones actually placed at the
broker (a 10-second glance at Fidelity's Pending screen) and re-uploads. Any put
left blank flags as MISSING. Keys line up with action_queue.gtc_key.
"""

from __future__ import annotations

import csv
import datetime
import io
import re

from logic import action_queue as aq

HEADER = ["Account", "Ticker", "Strike", "Expiry", "GTC Price"]


def template_csv(put_rows: list[dict]) -> str:
    """A ready-to-fill template of the open short puts (GTC Price left blank)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    for r in put_rows:
        strike = f"{float(r['strike']):g}" if r.get("strike") not in (None, "") else ""
        w.writerow([r["acct"], r["ticker"], strike, r["expiry"], ""])
    return buf.getvalue()


def _norm_expiry(v) -> str:
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%b %d, %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def _acct(v) -> str:
    s = str(v).strip().upper()
    if "IRA" in s:
        return "IRA"
    if "LLC" in s or "LIABILITY" in s:
        return "LLC"
    return s


def parse_gtc_csv(data) -> set:
    """Return the set of gtc_key()s that have a GTC placed (non-blank GTC Price).

    `data` may be bytes, str, or a Streamlit UploadedFile."""
    if hasattr(data, "read"):
        data = data.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig", errors="replace")
    placed: set = set()
    reader = csv.DictReader(io.StringIO(data))
    # tolerant header lookup (case/space-insensitive)
    def col(row, *names):
        for k in row:
            kk = str(k).strip().lower()
            if kk in names:
                return row[k]
        return None
    for row in reader:
        if not row:
            continue
        price = col(row, "gtc price", "gtc", "price", "limit")
        if price is None or str(price).strip() in ("", "-", "—"):
            continue
        acct = _acct(col(row, "account", "acct"))
        ticker = str(col(row, "ticker", "symbol", "stock") or "").strip().upper()
        strike = col(row, "strike", "strike price")
        expiry = _norm_expiry(col(row, "expiry", "exp date", "expiration"))
        if ticker and strike not in (None, ""):
            placed.add(aq.gtc_key(acct, ticker, strike, expiry))
    return placed


# --- Active Trader Pro "Orders" export -------------------------------------
# ATP can export working orders (the web Positions CSV can't), which makes the
# GTC diff automatic instead of a template the user fills by hand.

_ATP_SYM = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([PC])([\d.]+)$")


def parse_atp_orders(data) -> dict:
    """Open Buy-to-Close PUT orders from an ATP Orders export.

    Returns {gtc_key: limit_price}. Rolls, fills and cancels are ignored —
    only live working orders count as coverage."""
    if hasattr(data, "read"):
        data = data.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig", errors="replace")
    lines = data.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("Symbol,")), 0)
    out: dict = {}
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        if str(row.get("Status", "")).strip() != "Open":
            continue
        if "Buy to Close" not in str(row.get("Action", "")):
            continue
        m = _ATP_SYM.match(str(row.get("Symbol", "")).strip())
        if not m:
            continue                      # rolls and multi-leg legs
        tk, yy, mm, dd, cp, strike = m.groups()
        if cp != "P":
            continue
        try:
            limit = float(str(row.get("Order Type", "")).split("$")[-1])
        except (ValueError, IndexError):
            continue
        out[(_acct(row.get("Account", "")), tk, float(strike),
             f"20{yy}-{mm}-{dd}")] = limit
    return out
