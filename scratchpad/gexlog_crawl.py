from playwright.sync_api import sync_playwright
import json, re
seen_api={}; pages_visited=[]; links=set()
PAGES=["https://gexlog.com/","https://gexlog.com/dashboard/","https://gexlog.com/dashboard/history/",
       "https://gexlog.com/dashboard/methodology/","https://gexlog.com/about/","https://gexlog.com/contact/",
       "https://gexlog.com/dashboard/status.php"]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page()
    def on_resp(r):
        u=r.url
        if "api/" in u or u.endswith(".php"):
            key=u.split("?")[0]
            try: body=r.json()
            except: body=None
            if key not in seen_api:
                seen_api[key]={"status":r.status,"keys":(list(body.keys()) if isinstance(body,dict) else type(body).__name__ if body is not None else None),
                               "sample_url":u}
    pg.on("response", on_resp)
    for url in PAGES:
        try:
            pg.goto(url, wait_until="networkidle", timeout=45000); pg.wait_for_timeout(2500)
            pages_visited.append((url,pg.title()))
            for a in pg.query_selector_all("a[href]"):
                h=a.get_attribute("href")
                if h and not h.startswith(("mailto","http")) or (h and "gexlog.com" in h): links.add(h)
        except Exception as e:
            pages_visited.append((url,f"ERR {str(e)[:40]}"))
    # brute-force common api endpoint names
    guesses=["vix","vix.php","term-structure.php","ops.php","trades.php","positions.php","pnl.php",
             "scorecard.php","calendar.php","news.php","gex.php","profile.php","levels.php",
             "archive.php?action=list","report.php?type=weekend","report.php?type=scorecard",
             "config.php","meta.php","health.php"]
    print("=== ENDPOINT GUESSES ===")
    for gq in guesses:
        u=f"https://gexlog.com/dashboard/api/{gq}"
        try:
            r=pg.request.get(u); 
            if r.status==200:
                try: j=r.json(); info=list(j.keys()) if isinstance(j,dict) else type(j).__name__
                except: info=r.text()[:60]
                print(f"  [200] {gq} -> {info}")
            else: print(f"  [{r.status}] {gq}")
        except Exception as e: print(f"  [ERR] {gq} {str(e)[:30]}")
    b.close()
print("\n=== PAGES ===")
for u,t in pages_visited: print(f"  {u}  ::  {t}")
print("\n=== API ENDPOINTS AUTO-CAPTURED ===")
for k,v in seen_api.items(): print(f"  {k}\n     status={v['status']} keys={v['keys']}")
print("\n=== INTERNAL LINKS ===")
for l in sorted(links): print("  ",l)
