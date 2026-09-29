"""Share cost basis, read from the newest Fidelity positions export in ~/Downloads.

The TradeLog has no basis column, so a covered call flagged 'Roll up' looks the
same whether the strike is above or below what you paid. That distinction is the
whole rule: strike >= basis -> LET ASSIGN, no greed roll.
"""
from __future__ import annotations
import csv, glob, os, re
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
ACCT = {"148537624": "IRA", "Z52229635": "LLC"}


def _num(s):
    s = (s or "").strip().replace("$", "").replace(",", "").replace("+", "")
    if not s or s == "--":
        return None
    try:
        return -float(s[1:-1]) if s.startswith("(") else float(s)
    except ValueError:
        return None


def latest_csv() -> Path | None:
    files = glob.glob(str(DOWNLOADS / "Portfolio_Positions_*.csv"))
    return Path(max(files, key=os.path.getmtime)) if files else None


def share_basis() -> dict:
    """{(TICKER, ACCT): avg cost per share} for every share lot held."""
    f = latest_csv()
    out = {}
    if not f:
        return out
    for r in csv.DictReader(f.open(encoding="utf-8-sig")):
        a = ACCT.get((r.get("Account number") or "").strip())
        sym = (r.get("Symbol") or "").strip()
        qty = (r.get("Quantity") or "").strip()
        if not a or not sym or sym.startswith("-") or not qty:
            continue
        if sym.endswith("**") or "Pending" in sym:
            continue
        b = _num(r.get("Average cost basis"))
        if b:
            out[(sym.upper(), a)] = b
    return out
