"""Deep-crawl the MenthorQ dashboard with the saved session: enumerate every
internal nav link, visit each (bounded), save title + text + screenshot.
Output -> scratchpad/mq_discover/ + sitemap.json"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "scratchpad" / "mq_discover"
OUT.mkdir(exist_ok=True)
BASE = "https://dashboard.menthorq.io"
MAX_PAGES = 30

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1600, "height": 1000})
    page = ctx.new_page()
    page.goto(f"{BASE}/en/levels?symbol=SPX", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(4000)
    # expand collapsible nav sections if any, then collect internal links
    hrefs = page.eval_on_selector_all(
        "a[href^='/en/'], a[href^='https://dashboard.menthorq.io/en/']",
        "els => els.map(e => ({href: e.getAttribute('href'), text: (e.innerText||'').trim()}))")
    seen, queue = set(), []
    for h in hrefs:
        u = h["href"] if h["href"].startswith("http") else BASE + h["href"]
        u = u.split("#")[0]
        if u not in seen and "/en/" in u:
            seen.add(u)
            queue.append({"url": u, "label": h["text"]})
    sitemap = []
    for i, item in enumerate(queue[:MAX_PAGES]):
        u = item["url"]
        # add symbol param where missing so pages render data
        if "symbol=" not in u and "?" not in u:
            u2 = u + "?symbol=SPX"
        else:
            u2 = u
        slug = re.sub(r"[^a-z0-9]+", "_", u.replace(BASE + "/en/", ""))[:60] or "root"
        try:
            page.goto(u2, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(4000)
            txt = page.inner_text("body")
            (OUT / f"{slug}.txt").write_text(txt, encoding="utf-8")
            page.screenshot(path=str(OUT / f"{slug}.png"), full_page=False)
            sitemap.append({"label": item["label"], "url": u, "title": page.title(),
                            "chars": len(txt), "shot": f"{slug}.png"})
            print(f"  [{i+1}/{min(len(queue), MAX_PAGES)}] {item['label'][:30]:30s} {u[:80]}")
        except Exception as e:
            sitemap.append({"label": item["label"], "url": u, "error": str(e)[:120]})
            print(f"  FAIL {u[:80]}: {str(e)[:80]}")
    (OUT / "sitemap.json").write_text(json.dumps(sitemap, indent=1), encoding="utf-8")
    br.close()
print(f"\n{len(sitemap)} pages mapped -> {OUT}\\sitemap.json")
