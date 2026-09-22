"""Scrape Take Profit Trader rules via a real Chrome (Playwright).

The main marketing site (takeprofittrader.com) is WebFetch-readable, but the
authoritative rule articles live on a Zendesk help center
(takeprofittraderhelp.zendesk.com) that 403s WebFetch/curl. A real browser gets
through. Mirrors scripts/apex_scrape.py: one reused context, crawl the help
center + marketing pages, save each page's text.

  python scripts/tpt_scrape.py [max_pages]
Output: reports/tpt_scrape/<slug>.txt (per page) + _INDEX.md + _ALL.md
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "reports" / "tpt_scrape"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
SEEDS = [
    "https://takeprofittrader.com/",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us",
]
HOSTS = ("takeprofittrader.com", "takeprofittraderhelp.zendesk.com")
SKIP = re.compile(r"(login|sign-?up|register|cart|checkout|my-account|add-to-cart|"
                  r"wp-admin|wp-json|wp-login|/feed|community|/requests|hc/en-us/signin|"
                  r"\?add|\.(png|jpg|jpeg|gif|svg|css|js|ico|zip|mp4|pdf|woff))",
                  re.I)


def slug(url):
    net = urlparse(url).netloc.split(".")[0]
    p = urlparse(url).path.strip("/").replace("/", "__") or "index"
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", f"{net}__{p}")[:150]


def main():
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set(); queue = list(SEEDS); saved = []

    def blocked(title, txt):
        t = (title or "").lower()
        return ("attention required" in t or "just a moment" in t or "cloudflare" in t
                or "403" in t or len(txt) < 200)

    def load(page, url):
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        for _ in range(8):
            page.wait_for_timeout(1800)
            txt = page.inner_text("body"); title = page.title()
            if not blocked(title, txt):
                return title, txt
        return page.title(), page.inner_text("body")

    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=False)
        ctx = br.new_context(user_agent=UA, locale="en-US",
                             viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        load(page, SEEDS[0])
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
                (OUT / f"{slug(url)}.txt").write_text(
                    f"URL: {url}\nTITLE: {title}\n\n{txt}", encoding="utf-8")
                saved.append((url, title, len(txt)))
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
            time.sleep(1.2)
        br.close()

    (OUT / "_INDEX.md").write_text(
        "# Take Profit Trader scrape index\n\n"
        + "\n".join(f"- [{t}]({u}) — {n} chars — `{slug(u)}.txt`" for (u, t, n) in saved),
        encoding="utf-8")
    combined = []
    for (u, t, n) in saved:
        combined.append(f"\n\n{'='*90}\n# {t}\n{u}\n{'='*90}\n")
        combined.append((OUT / f"{slug(u)}.txt").read_text(encoding="utf-8"))
    (OUT / "_ALL.md").write_text("".join(combined), encoding="utf-8")
    print(f"\nDONE: {len(saved)} pages -> {OUT}")


if __name__ == "__main__":
    main()
