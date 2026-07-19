"""Targeted re-scrape of the MenthorQ course the first crawl missed:
'Trade Futures with MenthorQ' — its lesson bodies contain the operational rules
(first/second touch, pinning, broken levels, timing/location/setup).
Reuses the saved auth state. Output -> data/menthorq/knowledge/lessons_futures/
"""
import json, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menthorq" / "knowledge" / "lessons_futures"
AUTH = ROOT / "gamma_tracker" / "auth_state_mqcom.json"
COURSES = [
    "https://menthorq.com/academy/trade-futures-with-menthorq/",
    "https://menthorq.com/academy/how-to-use-blind-spots-levels/",
    "https://menthorq.com/academy/gamma-levels/",
]

def slug(u):
    return re.sub(r"[^a-z0-9]+", "_", u.replace("https://menthorq.com/", "").lower()).strip("_")[:110]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    idx = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH) if AUTH.exists() else None,
                             viewport={"width": 1500, "height": 1000})
        pg = ctx.new_page()
        lesson_urls = []
        for c in COURSES:
            try:
                pg.goto(c, wait_until="networkidle", timeout=60000)
                hrefs = pg.eval_on_selector_all(
                    "a[href*='/lessons/']", "e=>[...new Set(e.map(x=>x.href))]")
                got = [h for h in hrefs if "/lessons/" in h]
                lesson_urls += got
                print(f"  {c} -> {len(got)} lesson links", flush=True)
            except Exception as e:
                print(f"  {c} FAILED: {e}", flush=True)
        lesson_urls = sorted(set(lesson_urls))
        print(f"total unique lessons: {len(lesson_urls)}", flush=True)
        for i, u in enumerate(lesson_urls, 1):
            try:
                pg.goto(u, wait_until="networkidle", timeout=60000)
                pg.wait_for_timeout(600)
                title = pg.title()
                txt = pg.eval_on_selector("body", "b=>b.innerText")
                f = OUT / f"{slug(u)}.txt"
                f.write_text(txt, encoding="utf-8")
                idx.append({"url": u, "title": title, "file": f.name, "chars": len(txt)})
                print(f"  [{i}/{len(lesson_urls)}] {len(txt):>6}c  {title[:70]}", flush=True)
            except Exception as e:
                print(f"  [{i}] {u} FAILED: {e}", flush=True)
        br.close()
    (OUT / "_index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")
    print(f"\nwrote {len(idx)} lessons -> {OUT}")

if __name__ == "__main__":
    main()
