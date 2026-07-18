"""Find the correct historical-date parameter for MenthorQ snapshot endpoints.
Try many param names/formats against gamma-levels; a HIT = returned timestamp
matches the requested past date (not today 2026-07-14)."""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(r"c:\Users\Admin\myquant")
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
GW = "https://gateway.menthorq.io/clickhouse-api/api/web/v1"
tok = {"v": None}
TARGET = "2026-06-02"  # a recent past weekday we KNOW QUIN had levels for

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.on("request", lambda r: tok.__setitem__("v", r.headers.get("authorization"))
            if "gateway.menthorq.io" in r.url and r.headers.get("authorization") and not tok["v"] else None)
    page.goto("https://dashboard.menthorq.io/en/tickers/SPX", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)

    def api(path):
        return page.evaluate(
            """async ([u, t]) => { const r = await fetch(u, {headers:{'accept':'application/json','authorization':t}});
               const x = await r.text(); return {s:r.status, b:x.slice(0,220)}; }""", [GW + path, tok["v"]])

    variants = []
    for base in ["/gamma-levels/SPX/eod", "/gamma-levels/SPX"]:
        for p in ["date", "report_date", "as_of", "as_of_date", "asOf", "timestamp",
                  "day", "trading_date", "from", "start_date", "eod_date"]:
            for val in [TARGET, TARGET.replace("-", ""), TARGET + "T20:00:00"]:
                variants.append((f"{base}?{p}={val}", p, val))
    # also path-style: /gamma-levels/SPX/eod/2026-06-02
    for base in ["/gamma-levels/SPX/eod/", "/gamma-levels/SPX/"]:
        variants.append((f"{base}{TARGET}", "PATH", TARGET))

    hits = []
    for path, p, val in variants:
        try:
            r = api(path)
            ts = re.search(r'"timestamp":"(\d{4}-\d{2}-\d{2})', r["b"])
            got = ts.group(1) if ts else None
            if r["s"] == 200 and got and got.startswith("2026-06"):
                hits.append((p, val, got, path))
                print(f"  *** HIT: {p}={val} -> timestamp {got}")
            elif r["s"] not in (200, 404, 422):
                print(f"  {p}={val}: status {r['s']} {r['b'][:60]}")
        except Exception as e:
            pass
    print("\nHITS:" if hits else "\nNo param produced a past date (all returned today).")
    for h in hits:
        print("  ", h)
    br.close()
