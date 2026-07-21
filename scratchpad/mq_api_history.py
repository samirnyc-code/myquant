"""How far back does the MenthorQ API serve history? Probe the endpoints
with the saved dashboard session (Bearer token pulled from the live page)."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
GW = "https://gateway.menthorq.io/clickhouse-api/api/web/v1"

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    # load a dashboard page so the app attaches its auth; then call the API from
    # inside the page context (inherits cookies + bearer automatically)
    page.goto("https://dashboard.menthorq.io/en/tickers/SPX", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(4000)

    def api(path):
        return page.evaluate(
            """async (u) => {
                const r = await fetch(u, {headers: {'accept':'application/json'}});
                const t = await r.text();
                return {status: r.status, len: t.length, body: t.slice(0, 400), tail: t.slice(-300)};
            }""", GW + path)

    for name, path in [
        ("gamma-insights limit=5000", "/gamma-insights/SPX?limit=5000"),
        ("gamma-insights limit=2000", "/gamma-insights/SPX?limit=2000"),
        ("metrics eod", "/metrics/SPX/eod?fields=option&fields=momentum&limit=5000"),
        ("vol-insights", "/volatility-insights/SPX"),
        ("candles 1d far", "/tickers/SPX/candles?interval=1d&from=1451606400000&to=1784000000000"),
        ("gamma-levels dated old", "/gamma-levels/SPX/eod?date=2023-01-03"),
    ]:
        try:
            r = api(path)
            # count records + find earliest date in the body if present
            import re
            dates = re.findall(r'"(?:report_date|date|expiration_date)":"(\d{4}-\d{2}-\d{2})"', r["body"] + r["tail"])
            n = r["body"].count('"report_date"') or r["body"].count('{"date"') or r["body"].count('"t":')
            print(f"\n=== {name} === status {r['status']} len {r['len']:,}")
            print(f"  first dates: {dates[:2]}  ... tail dates: {dates[-2:] if len(dates)>2 else ''}")
            print(f"  head: {r['body'][:160]}")
        except Exception as e:
            print(f"{name}: ERR {e}")
    br.close()
