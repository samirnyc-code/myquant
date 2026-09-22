from playwright.sync_api import sync_playwright
import json

reports = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    def on_resp(r):
        if "report.php" in r.url:
            try: reports[r.url] = r.json()
            except: pass
    pg.on("response", on_resp)
    pg.goto("https://gexlog.com/dashboard/", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(5000)
    # try to trigger evening report if a toggle exists
    b.close()

json.dump(reports, open("scratchpad/gexlog_report.json","w"), indent=2)
for u,d in reports.items():
    print("URL:", u)
    print("meta:", d.get("meta"))
    m=d.get("market",{})
    print("  ES:", m.get("es",{}).get("price"), "VIX:", m.get("vix",{}).get("price"))
    g=d.get("forecast",{}).get("factors",{}).get("gamma",{})
    print("  net_gex:", g.get("net_gex"), "gex_flip:", g.get("gex_flip"))
    print("  top keys:", list(d.keys()))
    for k in d.keys():
        if k not in ("meta","market","forecast","risk"):
            print(f"    {k}:", json.dumps(d[k])[:800])
    print("  forecast.factors keys:", list(d.get("forecast",{}).get("factors",{}).keys()))
    print("======")
