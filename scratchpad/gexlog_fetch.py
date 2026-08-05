from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    out = {}
    for typ in ("morning","evening"):
        r = pg.request.get(f"https://gexlog.com/dashboard/api/report.php?type={typ}")
        out[typ] = r.json()
    b.close()

with open("scratchpad/gexlog_report.json","w") as f:
    json.dump(out, f, indent=2)

for typ in ("morning","evening"):
    d = out[typ]
    print(f"\n========== {typ.upper()} — {d.get('meta',{}).get('generatedAt')} ==========")
    print("KEYS:", list(d.keys()))
    mk = d.get("market",{})
    for k,v in mk.items():
        if isinstance(v,dict) and "price" in v: print(f"  {k}: {v['price']}")
    fc = d.get("forecast",{})
    fac = fc.get("factors",{})
    g = fac.get("gamma",{})
    print("  net_gex:", g.get("net_gex"))
    print("  gex_flip:", g.get("gex_flip"))
    # walls
    for key in ("levels","walls","keyLevels","support_resistance"):
        if key in d: print(f"  {key}:", json.dumps(d[key])[:600])
    for key in ("call_wall","put_wall","callWall","putWall"):
        if key in fac: print(f"  {key}:", fac[key])
    print("  factors keys:", list(fac.keys()))
