"""Reference — Framework 2.0.

Jigar's Oct 8 2026 reframe. The realization: after the Feb-style drawdown the book went so
defensive it stopped SELLING fear and started being RULED by it. Framework 2.0 separates the
three jobs cleanly — PROTECTION (structural, always-on), SETUP+VETO (find the trigger, reject the
bad trade), PREMIUM ENGINE (the offense) — so fear-caution can't creep into the offense when the
protection already has Feb covered.

The one rule that makes it safe: "don't be ruled by fear" loosens the OFFENSE, never the LOCKS.
The locks stay 30% / 5% / 45% with no exception; within them, take the well-qualified trade.
"""

from __future__ import annotations

import streamlit as st


def _sec(c: dict, accent: str, title: str, sub: str) -> str:
    return (f"<div style='display:flex;align-items:baseline;gap:10px;border-left:4px solid {accent};"
            f"padding:4px 0 4px 12px;margin:18px 0 8px'>"
            f"<span style='font-size:15px;font-weight:800;color:{c['text']};text-transform:uppercase;"
            f"letter-spacing:.03em'>{title}</span>"
            f"<span style='font-size:12px;color:{c.get('muted', '#888')}'>{sub}</span></div>")


def _rows(c: dict, accent: str, items: list) -> str:
    out = ""
    for n, head, tail in items:
        num = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
               f"min-width:20px;height:20px;border-radius:5px;background:{accent}22;color:{accent};"
               f"font-size:11px;font-weight:800;margin-right:10px'>{n}</span>" if n else
               f"<span style='color:{accent};margin-right:10px;font-weight:800'>•</span>")
        tailh = (f" <span style='color:{c.get('muted', '#888')};font-size:12px'>— {tail}</span>"
                 if tail else "")
        out += (f"<div style='display:flex;align-items:baseline;padding:4px 0 4px 14px;font-size:13px;"
                f"color:{c['text']}'>{num}<span><b>{head}</b>{tailh}</span></div>")
    return out


def render(c: dict) -> None:
    b = c.get("muted", "#888")
    pos, neg, amb = c.get("pos", "#2f7e25"), c.get("neg", "#b62027"), c.get("gold", "#b8860b")
    blue = "#3b82f6"

    head = (f"<div style='font-size:22px;font-weight:800;color:{c['text']}'>Framework 2.0</div>"
            f"<div style='font-size:14px;color:{pos};font-weight:700;margin-top:2px'>"
            f"Sells fear — not ruled by it.</div>")

    thesis = (f"<div style='border-left:4px solid {pos};background:{pos}14;border-radius:8px;"
              f"padding:11px 14px;margin:12px 0 4px;font-size:13px;color:{c['text']};line-height:1.6'>"
              f"After the Feb-style drawdown the book went so defensive that <b>SPY will always beat it</b> "
              f"— and that means it stopped <b>selling</b> fear and started being <b>ruled</b> by it. "
              f"<b>Don't chase premium — but don't let a past drawdown block a well-qualified risk today.</b> "
              f"The Setup only finds the <b>trigger</b>; the Veto + Locks are the protection against a bad "
              f"trade. Offense doesn't also need to be defensive — the Locks already did that.</div>")

    protection = _sec(c, blue, "Protection", "5 locks · structural · always on") + _rows(c, blue, [
        ("1", "Vault 30%", "never deployed, even in a crash"),
        ("2", "5% name cap", "7% for a 1-lot starter"),
        ("3", "CC Breaker", "45% wheel cap, LEAP excluded"),
        ("4", "1 contract / wk / acct", "no same expiry"),
        ("5", "VIX allocation", "total deployment by regime"),
    ])

    veto = _sec(c, amb, "Setup Veto", "3 locks · quality gate") + _rows(c, amb, [
        ("6", "Earnings", "none inside the CSP window (<24 DTE)"),
        ("7", "RSI ≤ 65 + not near upper BB", "the real safety filter"),
        ("8", "≥ 20% off the 52w high", "a genuine discount"),
    ])

    engine = _sec(c, pos, "Premium Engine", "3-stage AOR · the offense") + _rows(c, pos, [
        ("", "Growth 47%", "always try first (primary, 80%+ of entries)"),
        ("", "Core 30%", "only if cash ≥ 50% (safety valve, rarely)"),
        ("", "Quality 40%", "only if cash ≥ 50% (fallback)"),
        ("", "Brake", "ahead of pace → STOP at 47%, don't drop tiers"),
    ])

    standards = _sec(c, b, "Untold standards", "the quiet defaults") + _rows(c, b, [
        ("", "Delta ≤ 0.30", ""),
        ("", "21–30 DTE", "preference"),
    ])

    setups = _sec(c, blue, "Entry setups", "8, simplified") + (
        f"<div style='padding:4px 0 4px 14px;font-size:13px;color:{c['text']}'>"
        f"<b>Pure triggers. The Locks handle quality.</b> A setup's only job is to <i>find</i> a "
        f"candidate — it doesn't need to be conservative, because the Veto + Protection locks reject "
        f"anything unsafe. Generous setups + strict locks = more qualified trades, same protection.</div>")

    twin = _sec(c, pos, "Twin objectives", "both achieved") + _rows(c, pos, [
        ("", "Protection against Feb-style events", "intact"),
        ("", "Premium engine", "restored"),
        ("", "Sells fear", "instead of being ruled by it"),
    ])

    note = (f"<div style='margin-top:16px;font-size:11px;color:{b};border-top:1px solid {c['border']};"
            f"padding-top:8px'>One figure to pin: the 3-stage AOR reads 47 / 30 / 40 here; an earlier "
            f"note logged 47 / 40 / 36 — reconcile which tiers are current. Structure (the locks) is "
            f"unchanged and stays locked through Dec 2026.</div>")

    st.markdown(head + thesis + protection + veto + engine + standards + setups + twin + note,
                unsafe_allow_html=True)
