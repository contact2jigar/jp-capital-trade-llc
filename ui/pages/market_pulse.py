"""📰 Market Pulse — "why is the market up / down today?" answered by two grounded LLMs
side by side (Gemini + Claude), so you can compare. Both do a live web-grounded call
(Google Search grounding / Claude web_search), cached 1h. Keys live in Streamlit secrets:

    .streamlit/secrets.toml
    GEMINI_API_KEY    = "AIza..."
    ANTHROPIC_API_KEY = "sk-ant-..."

Raw HTTP (requests) for both — no extra dependency to deploy.
"""
from __future__ import annotations

import datetime as _dt

import requests
import streamlit as st

_PROMPT = (
    "You are a markets analyst. Using today's REAL market data and news, explain concisely why "
    "the US stock market is up or down TODAY ({date}).\n\n"
    "Format:\n"
    "1. One bold headline line with the day's index moves — S&P 500, Nasdaq, Dow — each with its % change and direction.\n"
    "2. Then 3–5 short bullets naming the SPECIFIC drivers (earnings, the Fed, rates, macro prints, sectors). "
    "Name the actual companies / events moving it.\n"
    "Be factual and current — do not speculate or give advice. Keep it under 180 words."
)


def _key(name: str) -> str | None:
    try:
        v = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        v = None
    return v or None


@st.cache_data(ttl=3600, show_spinner=False)
def _gemini(prompt: str, key: str) -> tuple[bool, str]:
    """Gemini 2.5 Flash with Google Search grounding. → (ok, text)."""
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.5-flash:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    try:
        r = requests.post(url, json=body, timeout=40)
    except Exception as e:
        return False, f"Network error: {e}"
    if r.status_code != 200:
        return False, f"Gemini error {r.status_code}: {r.text[:300]}"
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        txt = "".join(p.get("text", "") for p in parts).strip()
        return (bool(txt), txt or "No text returned.")
    except Exception as e:
        return False, f"Parse error: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def _claude(prompt: str, key: str) -> tuple[bool, str]:
    """Claude Opus 5.5 with the web_search server tool. → (ok, text)."""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": "claude-opus-5-5",
                "max_tokens": 1200,
                "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
    except Exception as e:
        return False, f"Network error: {e}"
    if r.status_code != 200:
        return False, f"Claude error {r.status_code}: {r.text[:300]}"
    try:
        blocks = r.json().get("content", [])
        txt = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        return (bool(txt), txt or "No text returned.")
    except Exception as e:
        return False, f"Parse error: {e}"


def _card(title: str, key_name: str, fn, c: dict) -> None:
    key = _key(key_name)
    with st.expander(title, expanded=False):          # DEFAULT COLLAPSED
        if not key:
            st.info(f"Add **{key_name}** to `.streamlit/secrets.toml` to enable this card.")
            return
        cols = st.columns([1, 1, 4])
        if cols[0].button("↻ Refresh", key=f"mp_refresh_{key_name}"):
            fn.clear()                                 # drop cached result → regenerate
        with st.spinner("Reading today's tape…"):
            ok, text = fn(_PROMPT.format(date=_dt.date.today().strftime("%A, %b %d, %Y")), key)
        if ok:
            st.markdown(text)
            st.caption(f"Grounded · cached 1h · {_dt.datetime.now():%-I:%M %p}")
        else:
            st.error(text)


def render(c: dict) -> None:
    st.markdown("#### 📰 Market Pulse")
    st.caption("Why is the market up or down today — same question, two grounded models. Compare.")
    _card("🔵  Gemini — why's the market moving today?", "GEMINI_API_KEY", _gemini, c)
    _card("🟣  Claude — why's the market moving today?", "ANTHROPIC_API_KEY", _claude, c)
