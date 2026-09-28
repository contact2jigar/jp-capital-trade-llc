"""Live ticker universes — Yahoo predefined screeners (Most Active, etc.).

Yahoo's screener endpoint now requires a cookie + crumb handshake (a bare GET
returns 401/empty). We prime cookies from finance.yahoo.com, fetch a crumb, then
call the predefined screener with it — paged so we can pull more than 100.
Returns [] on any failure so the page degrades cleanly.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from services.cache import TTL, cached

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_SAVED = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
_CRUMB = "https://query1.finance.yahoo.com/v1/test/getcrumb"


def _session():
    """A urllib opener that keeps cookies (needed for the crumb to validate)."""
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", _UA), ("Accept", "*/*")]
    return op


def _crumb(op) -> str | None:
    try:
        op.open("https://finance.yahoo.com", timeout=10).read(2000)   # set A1/A3 cookies
    except Exception:
        pass
    try:
        c = op.open(_CRUMB, timeout=10).read().decode().strip()
        return c or None
    except Exception:
        return None


def _get_json(op, url: str, params: dict):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": _UA, "Accept": "application/json"})
    with op.open(req, timeout=12) as r:
        return json.load(r)


def _via_yfinance(scr_id: str, count: int) -> list[str]:
    """Primary path: yfinance.screen() — handles the crumb/cookie handshake itself."""
    import yfinance as yf
    out: list[str] = []
    start, per = 0, 100
    while len(out) < count:
        res = yf.screen(scr_id, size=min(per, count - len(out)), offset=start)
        quotes = (res or {}).get("quotes") or []
        page = [q.get("symbol", "").strip().upper() for q in quotes if q.get("symbol")]
        if not page:
            break
        out.extend(page)
        if len(page) < per:
            break
        start += per
    return out


def _via_raw(scr_id: str, count: int) -> list[str]:
    """Fallback: raw endpoint with our own cookie + crumb handshake."""
    op = _session()
    crumb = _crumb(op)
    out: list[str] = []
    start, per = 0, 100
    while len(out) < count:
        params = {"scrIds": scr_id, "count": min(per, count - len(out)), "start": start}
        if crumb:
            params["crumb"] = crumb
        data = _get_json(op, _SAVED, params)
        quotes = (((data or {}).get("finance") or {}).get("result") or [{}])[0].get("quotes") or []
        page = [q["symbol"].strip().upper() for q in quotes if q.get("symbol")]
        if not page:
            break
        out.extend(page)
        if len(page) < per:
            break
        start += per
    return out


@cached(TTL["fundamentals"])
def _predefined(scr_id: str, count: int) -> list[str]:
    out: list[str] = []
    for fn in (_via_yfinance, _via_raw):
        try:
            out = fn(scr_id, count)
            if out:
                break
        except Exception:
            continue
    seen, clean = set(), []
    for s in out:
        # keep normal tickers incl. share classes (BRK.B, RDS-A); drop dupes / ^index / weird
        ok = s and s not in seen and s[0].isalpha() and all(c.isalnum() or c in ".-" for c in s)
        if ok:
            seen.add(s)
            clean.append(s)
    return clean[:count]


def most_active(count: int = 200) -> list[str]:
    """Yahoo 'Most Active' names (by volume), up to `count`. [] if Yahoo blocks it."""
    return _predefined("most_actives", count)


def day_gainers(count: int = 100) -> list[str]:
    return _predefined("day_gainers", count)
