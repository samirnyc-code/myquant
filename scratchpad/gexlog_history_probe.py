from playwright.sync_api import sync_playwright
import json
calls=[]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page()
    def on_resp(r):
        u=r.url
        if any(x in u for x in ("api/","report.php","history","archive",".json",".php")):
            try: body=r.json()
            except: body=None
            calls.append((r.request.method, u, r.status, (json.dumps(body)[:400] if body is not None else None)))
    pg.on("response", on_resp)
    pg.goto("https://gexlog.com/dashboard/history/", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(5000)
    # try clicking any date/history item
    try:
        pg.wait_for_timeout(2000)
    except: pass
    html = pg.content()
    b.close()
print("=== NETWORK CALLS ===")
for m,u,s,bd in calls:
    print(f"[{s}] {m} {u}")
    if bd: print("     body:", bd)
# look for date links in html
import re
dates=set(re.findall(r'20260[1-9]-\d\d-\d\d|2026-0[1-9]-\d\d', html))
print("\ndates seen in page:", sorted(dates)[:20], "..." if len(dates)>20 else "")
open("scratchpad/gexlog_history.html","w",encoding="utf-8").write(html)
