"""Probe MenthorQ dashboard pages with the saved gamma_tracker session:
is auth still valid, and what JSON APIs feed matrix / exposure / heatmap?"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "scratchpad" / "mq_probe"
OUT.mkdir(exist_ok=True)

PAGES = {
    "matrix": "https://dashboard.menthorq.io/en/options/matrix?symbol=SPX",
    "exposure": "https://dashboard.menthorq.io/en/options/exposure?symbol=SPX",
    "heatmap": "https://dashboard.menthorq.io/en/options/heatmap?symbol=SPX",
}

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH))
    page = ctx.new_page()
    api_hits = []

    def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct and "menthorq" in resp.url:
            try:
                body = resp.text()
                api_hits.append({"url": resp.url, "status": resp.status, "bytes": len(body),
                                 "preview": body[:400]})
            except Exception:
                pass

    page.on("response", on_response)
    for name, url in PAGES.items():
        api_hits.clear()
        print(f"\n=== {name} ===")
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"  goto: {e}")
        title = page.title()
        logged_out = "login" in page.url.lower() or "sign" in title.lower()
        print(f"  final url: {page.url}\n  title: {title}\n  LOGGED OUT: {logged_out}")
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
        (OUT / f"{name}_apis.json").write_text(json.dumps(api_hits, indent=1), encoding="utf-8")
        print(f"  captured {len(api_hits)} JSON responses:")
        for h in api_hits[:8]:
            print(f"    [{h['status']}] {h['bytes']:>7}B  {h['url'][:110]}")
    br.close()
print(f"\nscreenshots + api dumps -> {OUT}")
