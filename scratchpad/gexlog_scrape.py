from playwright.sync_api import sync_playwright
import json, sys

url = "https://gexlog.com/dashboard/"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    captured = []
    def on_resp(r):
        ct = r.headers.get("content-type","")
        if "json" in ct or r.url.endswith(".json"):
            try: captured.append((r.url, r.json()))
            except: captured.append((r.url, "<non-json body>"))
    pg.on("response", on_resp)
    pg.goto(url, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(4000)
    txt = pg.inner_text("body")
    b.close()

print("=== CAPTURED JSON ENDPOINTS ===")
for u,d in captured:
    print(u)
    print(json.dumps(d, indent=2)[:3000] if not isinstance(d,str) else d)
    print("---")
print("\n=== VISIBLE BODY TEXT ===")
print(txt)
