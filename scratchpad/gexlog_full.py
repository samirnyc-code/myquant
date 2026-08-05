from playwright.sync_api import sync_playwright
import json
reports = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    def on_resp(r):
        if "report.php" in r.url or "status.php" in r.url:
            try: reports[r.url.split("&t=")[0]] = r.json()
            except: pass
    pg.on("response", on_resp)
    pg.goto("https://gexlog.com/dashboard/", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(6000)
    b.close()
json.dump(reports, open("scratchpad/gexlog_full.json","w"), indent=2)

for u,d in reports.items():
    if "report.php" not in u: continue
    typ = u.split("type=")[-1]
    meta = d.get("meta") or {}
    print(f"\n### {typ} — generatedAt={meta.get('generatedAt')} src={meta.get('dataSource')}")
    if "levels" in d: print("  levels:", json.dumps(d["levels"]))
    g = d.get("forecast",{}).get("factors",{}).get("gamma",{})
    if g:
        print("  net_gex:", g.get("net_gex"), "gex_flip:", g.get("gex_flip"),
              "method:", g.get("gex_method"), "regime:", g.get("value"))
        prof = g.get("gex_profile") or []
        print("  gex_profile strikes:", len(prof))
        # top 10 by abs net_gex
        top = sorted(prof, key=lambda x: -abs(x.get("net_gex",0)))[:12]
        for s in top:
            print(f"    {s['strike']:.0f}  net={s['net_gex']:>14.0f}  call={s.get('call_gex',0):>12.0f}  put={s.get('put_gex',0):>12.0f}")
    m = d.get("market",{})
    if m: print("  ES:", m.get("es",{}).get("price"), "SPX-impl VIX:", m.get("vix",{}).get("price"))
