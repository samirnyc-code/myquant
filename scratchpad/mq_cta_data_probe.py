"""Does the CTA/Vol models page expose data (JSON/CSV/img URLs) or only pixels?"""
import json
from playwright.sync_api import sync_playwright

hits = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state="gamma_tracker/auth_state_mqcom.json",
                         viewport={"width": 1600, "height": 1000})
    page = ctx.new_page()

    def on_resp(r):
        ct = r.headers.get("content-type", "")
        if ("json" in ct or "csv" in ct) and "menthorq" in r.url:
            try:
                hits.append({"url": r.url[:160], "bytes": len(r.body())})
            except Exception:
                pass

    page.on("response", on_resp)
    page.goto("https://menthorq.com/account/?action=data&type=dashboard&commands=cta&date=2026-07-14",
              wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(6000)
    imgs = page.eval_on_selector_all(
        "img", "els => els.map(e => e.src)")
    charts = [u for u in imgs if any(k in u.lower() for k in ("chart", "cta", "model", "upload", "png"))]
    print("JSON/CSV endpoints:", json.dumps(hits, indent=1))
    print(f"chart-like <img> URLs: {len(charts)}")
    for u in charts[:8]:
        print("  ", u[:140])
    br.close()
