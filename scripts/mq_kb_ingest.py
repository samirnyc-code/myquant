"""Ingest MenthorQ trading-strategies guides + Financial Wiki / knowledge base
(user directive). Crawls both, saves clean text per article, builds an index.
Output -> data/menthorq/knowledge/{guides,wiki}/ + _index.json

Sources:
  menthorq.com/account/?action=guides&category=trading-strategies (mqcom session)
  dashboard 'Financial Wiki' + academy knowledge-base pages (dashboard session)
"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menthorq" / "knowledge"
AUTH_DASH = ROOT / "gamma_tracker" / "auth_state.json"
AUTH_COM = ROOT / "gamma_tracker" / "auth_state_mqcom.json"


def crawl(page, seeds, out_dir, link_filter, cap=120):
    out_dir.mkdir(parents=True, exist_ok=True)
    seen, queue, idx = set(), list(seeds), []
    while queue and len(idx) < cap:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1800)
            if "password" in page.inner_text("body").lower()[:1500]:
                print(f"  (auth needed) {url}")
                continue
            txt = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
            slug = re.sub(r"[^a-z0-9]+", "_", url.split("//")[-1])[:70]
            (out_dir / f"{slug}.txt").write_text(txt, encoding="utf-8")
            idx.append({"url": url, "title": page.title(), "chars": len(txt)})
            # discover more links matching the filter
            hrefs = page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href)")
            for h in hrefs:
                if link_filter(h) and h not in seen and h not in queue:
                    queue.append(h)
            print(f"  [{len(idx)}] {page.title()[:55]}")
        except Exception as e:
            print(f"  FAIL {url}: {str(e)[:70]}")
    (out_dir / "_index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")
    return idx


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        total = 0
        # 1) trading-strategies guides (menthorq.com account area)
        if AUTH_COM.exists():
            ctx = br.new_context(storage_state=str(AUTH_COM), viewport={"width": 1500, "height": 1000})
            page = ctx.new_page()
            print("=== trading-strategies guides ===")
            idx = crawl(page, ["https://menthorq.com/account/?action=guides&category=trading-strategies"],
                        OUT / "guides",
                        lambda h: "menthorq.com/account/" in h and ("guides" in h or "knowledge" in h))
            total += len(idx)
            ctx.close()
        # 2) Financial Wiki + knowledge base (dashboard session)
        ctx2 = br.new_context(storage_state=str(AUTH_DASH), viewport={"width": 1500, "height": 1000})
        p2 = ctx2.new_page()
        print("=== financial wiki / knowledge base ===")
        idx2 = crawl(p2, ["https://dashboard.menthorq.io/en/wiki",
                          "https://dashboard.menthorq.io/en/financial-wiki",
                          "https://menthorq.com/academy/"],
                     OUT / "wiki",
                     lambda h: any(k in h for k in ("/wiki", "financial-wiki", "/academy/", "knowledge")))
        total += len(idx2)
        ctx2.close()
        br.close()
    print(f"\ningested {total} pages -> {OUT}")


if __name__ == "__main__":
    main()
