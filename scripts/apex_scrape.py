"""Scrape Apex Trader Funding (Cloudflare-protected) via a real Chrome (Playwright),
since WebFetch/curl are 403-blocked. Crawls the help-center + legacy product/rule
pages and saves each page's text for analysis.

One browser context is reused so the Cloudflare clearance cookie carries over and
pages after the first load fast (no re-challenge).

  python scripts/apex_scrape.py [max_pages]
Output: reports/apex_scrape/<slug>.txt (per page) + _INDEX.md (list) + _ALL.md (combined)
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "reports" / "apex_scrape"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
SEEDS = [
    "https://apextraderfunding.com/",
    "https://apextraderfunding.com/legacy-products/",
    "https://apextraderfunding.com/help-center/",
    "https://apextraderfunding.com/faq/",
    "https://support.apextraderfunding.com/hc/en-us",
]
HOSTS = ("apextraderfunding.com", "support.apextraderfunding.com")
# skip non-content / transactional / binary
SKIP = re.compile(r"(login|sign-?up|register|cart|checkout|my-account|add-to-cart|"
                  r"wp-admin|wp-json|wp-login|/feed|\?add|\.(png|jpg|jpeg|gif|svg|css|js|ico|zip|mp4|woff))",
                  re.I)


def slug(url):
    net = urlparse(url).netloc.replace("apextraderfunding.com", "").strip(".") or "www"
    p = urlparse(url).path.strip("/").replace("/", "__") or "index"
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", f"{net}__{p}")[:150]


def main():
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set(); queue = list(SEEDS); saved = []
    def blocked(title, txt):
        t = (title or "").lower()
        return ("attention required" in t or "just a moment" in t or "cloudflare" in t
                or len(txt) < 250)

    def load(page, url):
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        for _ in range(14):                    # poll up to ~35s for the challenge to clear
            page.wait_for_timeout(2500)
            txt = page.inner_text("body"); title = page.title()
            if not blocked(title, txt):
                return title, txt
        return page.title(), page.inner_text("body")

    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=False)   # visible = passes Cloudflare
        ctx = br.new_context(user_agent=UA, locale="en-US",
                             viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        load(page, SEEDS[0])                   # establish clearance cookie
        while queue and len(saved) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                title, txt = load(page, url)
                if blocked(title, txt):
                    print(f"  BLOCKED {url}", flush=True)
                    continue
                (OUT / f"{slug(url)}.txt").write_text(f"URL: {url}\nTITLE: {title}\n\n{txt}", encoding="utf-8")
                saved.append((url, title, len(txt)))
                # discover links within allowed prefixes
                for href in page.eval_on_selector_all("a", "els => els.map(e => e.href)"):
                    try:
                        u = urljoin(url, href).split("#")[0].rstrip("/")
                        pr = urlparse(u)
                        if (any(pr.netloc.endswith(h) for h in HOSTS) and not SKIP.search(u)
                                and u not in seen and u not in queue):
                            queue.append(u)
                    except Exception:
                        pass
                print(f"[{len(saved)}] {title[:60]}  ({len(txt)} chars)  {url}", flush=True)
            except Exception as e:
                print(f"  ERR {url}: {e}", flush=True)
            time.sleep(2.0)
        br.close()

    (OUT / "_INDEX.md").write_text(
        "# Apex scrape index\n\n" + "\n".join(f"- [{t}]({u}) — {n} chars — `{slug(u)}.txt`"
                                              for (u, t, n) in saved), encoding="utf-8")
    combined = []
    for (u, t, n) in saved:
        combined.append(f"\n\n{'='*90}\n# {t}\n{u}\n{'='*90}\n")
        combined.append((OUT / f"{slug(u)}.txt").read_text(encoding="utf-8"))
    (OUT / "_ALL.md").write_text("".join(combined), encoding="utf-8")
    print(f"\nDONE: {len(saved)} pages -> {OUT}")


if __name__ == "__main__":
    main()
