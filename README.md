# ⚙️ WheelEngine — by JP Capital & Trade

The unified wheel-trading cockpit. **Finds · sizes · ranks — never places an order.**

Sections: **Command Center · CSP Scanner · Entry Setup · Risk Gates · Candidate Hunt**.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud
1. Push this folder to a GitHub repo.
2. On [share.streamlit.io](https://share.streamlit.io) → New app → pick the repo, **main file = `app.py`**.
3. No secrets required — the Google Sheet is read as a public CSV.
4. On iPhone: open the app URL in Safari → **Share → Add to Home Screen** for an app-like icon.

## Layout
```
app.py                 thin shell: theme + sidebar + route
ui/theme.py            Dark / Grey palettes
ui/nav.py              the 5 sections
ui/sidebar.py          brand + nav + theme toggle
ui/pages/*.py          one file per section (render(c))
```
Engines (setups, pricing, GTC, gates, sheet, IV) get copied in as each section is built.
