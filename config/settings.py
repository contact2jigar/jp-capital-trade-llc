"""Config + secrets loader — one door for every credential and setting.

Reads from st.secrets first (works locally via .streamlit/secrets.toml AND on
Streamlit Cloud via the Secrets UI, unchanged), falls back to environment
variables. Never read creds from loose files scattered around the repo.

    from config import settings
    user = settings.rh_credentials()["username"]
    tickers = settings.universe()
"""

from __future__ import annotations

import os
from functools import lru_cache

import streamlit as st

_UNIVERSE_FILE = "config/universe.txt"


def get_secret(path: str, default=None):
    """Fetch a secret by dotted path, e.g. 'robinhood.username'.

    Order: st.secrets → env var (dots → underscores, upper) → default.
    """
    # st.secrets (nested tables supported via dotted path)
    try:
        node = st.secrets
        for part in path.split("."):
            node = node[part]
        return node
    except Exception:
        pass
    env_key = path.replace(".", "_").upper()
    return os.environ.get(env_key, default)


def rh_credentials() -> dict:
    """Robinhood login. Empty strings until login is implemented/configured."""
    return {
        "username": get_secret("robinhood.username", ""),
        "password": get_secret("robinhood.password", ""),
        "mfa": get_secret("robinhood.mfa", ""),
    }


def gsheet_config() -> dict:
    """Read-only Google Sheet source config."""
    return {
        "sheet_id": get_secret("gsheet.sheet_id", ""),
        # Either a service-account JSON block under [gsheet.service_account],
        # or a published CSV URL under gsheet.csv_url — whichever is set.
        "csv_url": get_secret("gsheet.csv_url", ""),
        "service_account": get_secret("gsheet.service_account", None),
    }


@lru_cache(maxsize=1)
def universe() -> list[str]:
    """Ticker universe — one config file, replaces scattered watchlist.txt."""
    try:
        with open(_UNIVERSE_FILE) as f:
            return [
                ln.strip().upper()
                for ln in f
                if ln.strip() and not ln.startswith("#")
            ]
    except FileNotFoundError:
        return []
