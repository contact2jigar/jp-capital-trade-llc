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


def day_losers(count: int = 100) -> list[str]:
    """Yahoo 'Day Losers' — names down the most today (the CSP setup trigger: stock down)."""
    return _predefined("day_losers", count)


# FinViz quality + optionable screen: mid-cap+, current ratio >1, D/E <1, positive net margin,
# 3-yr sales growth >10%, liquid (avg vol >1M, cur vol >300K), optionable, price >$30.
_FINVIZ_FILTERS = ("cap_midover,fa_netmargin_pos,sh_avgvol_o1000,sh_opt_option,sh_price_o15")
_FINVIZ_FT = 4   # FinViz filter-type toggle (matches the saved screen URL)


def finviz_screen_rows(count: int = 100, filters: str = _FINVIZ_FILTERS) -> list[tuple]:
    """FinViz screener rows as (ticker, sector) for the filter string — the sector comes
    free from the screener page (its row carries data-boxover-ticker + a Sector cell), so
    the Stage-1 sector filter costs zero Yahoo calls. [] if FinViz blocks / rate-limits.
    Scrapes 20 rows/page, market-cap descending."""
    import re
    import certifi
    import requests
    out: list[tuple] = []
    seen: set = set()
    start = 1
    while len(out) < count:
        # o=-marketcap: biggest names first, so a capped pull surfaces the mega/quality names.
        url = (f"https://finviz.com/screener.ashx?v=111&f={filters}"
               f"&ft={_FINVIZ_FT}&o=-marketcap&r={start}")
        try:
            resp = requests.get(url, headers={"User-Agent": _UA},
                                verify=certifi.where(), timeout=15)
            html = resp.text
        except Exception:
            break
        page = 0
        for row in re.split(r'<tr class="styled-row', html)[1:]:
            m = re.search(r'data-boxover-ticker="([A-Z][A-Z.\-]{0,6})"', row)
            if not m:
                continue
            tkr = m.group(1)
            if tkr in seen:
                continue
            # Row left-align cells: [Company, Sector, Industry, Country, …]; [1] = Sector.
            cells = re.findall(r'<td[^>]*align="left"[^>]*>\s*<a[^>]*>\s*([^<]+?)\s*</a>\s*</td>', row)
            seen.add(tkr)
            out.append((tkr, cells[1] if len(cells) > 1 else ""))
            page += 1
        if not page:
            break
        if page < 20:                                      # last page reached
            break
        start += 20
    return out[:count]


def finviz_screen(count: int = 100, filters: str = _FINVIZ_FILTERS) -> list[str]:
    """FinViz screener tickers for the filter string (just the symbols; see
    finviz_screen_rows for ticker+sector). [] on block / rate-limit."""
    return [t for t, _ in finviz_screen_rows(count, filters)]
