"""Capture the gateway Bearer token from a live request, then replay the
history endpoints with it to find how far back the data goes."""
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
GW = "https://gateway.menthorq.io/clickhouse-api/api/web/v1"
token = {"v": None}

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    def grab(req):
        if "gateway.menthorq.io" in req.url:
            a = req.headers.get("authorization")
            if a and not token["v"]:
                token["v"] = a

    page.on("request", grab)
    page.goto("https://dashboard.menthorq.io/en/tickers/SPX", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)
    print("token captured:", bool(token["v"]), (token["v"][:22] + "...") if token["v"] else "")

    def api(path):
        return page.evaluate(
            """async ([u, tok]) => {
                const r = await fetch(u, {headers: {'accept':'application/json','authorization':tok}});
                const t = await r.text();
                return {status: r.status, len: t.length, body: t.slice(0,500), tail: t.slice(-400)};
            }""", [GW + path, token["v"]])

    for name, path in [
        ("gamma-insights 5000", "/gamma-insights/SPX?limit=5000"),
        ("metrics eod 5000", "/metrics/SPX/eod?fields=option&limit=5000"),
        ("vol-insights", "/volatility-insights/SPX"),
        ("candles 1d 2016+", "/tickers/SPX/candles?interval=1d&from=1451606400000&to=1784000000000"),
        ("gamma-levels 2023", "/gamma-levels/SPX/eod?date=2023-01-03"),
        ("gamma-levels 2024", "/gamma-levels/SPX/eod?date=2024-06-03"),
        ("matrix dated 2024 (OI?)", "/options/matrix/SPX?frequency=eod&date=2024-06-03"),
        ("net-gex-by-exp dated 2024", "/options/net-gex-by-expiration/SPX?frequency=eod&date=2024-06-03"),
        ("gamma-insights 2000d", "/gamma-insights/SPX?limit=2000"),
    ]:
        try:
            r = api(path)
            all_dates = sorted(set(re.findall(r'"(?:report_date|date)":"(\d{4}-\d{2}-\d{2})"', r["body"] + r["tail"])))
            tstamps = re.findall(r'"t":(\d{10,13})', r["body"] + r["tail"])
            import datetime as dt
            tds = sorted({dt.datetime.utcfromtimestamp(int(x[:10])).date().isoformat() for x in tstamps})
            n = r["body"].count('report_date') + r["body"].count('"t":')
            print(f"\n=== {name} === status {r['status']} len {r['len']:,}  (~{n} recs in head)")
            if all_dates:
                print(f"  date span in sample: {all_dates[0]} .. {all_dates[-1]}")
            if tds:
                print(f"  candle span in sample: {tds[0]} .. {tds[-1]}")
            print(f"  head: {r['body'][:150]}")
        except Exception as e:
            print(f"{name}: ERR {e}")
    br.close()
