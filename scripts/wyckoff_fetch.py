"""Fetch tradingwyckoff.com Wyckoff-method page via a fresh headless Chrome
(WebFetch gets Cloudflare 403). Same single-fresh-fetch pattern as
scripts/apex_fetch_pages.py. Saves page text to reports/wyckoff_scrape/.

  python scripts/wyckoff_fetch.py            # fetch the built-in page list
  python scripts/wyckoff_fetch.py <url>      # test a single url
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "reports" / "wyckoff_scrape"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
URLS = [
    "https://tradingwyckoff.com/en/wyckoff-method/",
]


def slug(url):
    p = urlparse(url).path.strip("/").replace("/", "__") or "index"
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", p)[:150]


def blocked(title, txt):
    t = (title or "").lower()
    return ("attention required" in t or "just a moment" in t
            or "cloudflare" in t or len(txt) < 250)


def fetch_one(url):
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=True)
        try:
            pg = br.new_context(user_agent=UA, locale="en-US",
                                viewport={"width": 1366, "height": 850}).new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            title, txt = "", ""
            for _ in range(16):
                pg.wait_for_timeout(2500)
                txt = pg.inner_text("body"); title = pg.title()
                if not blocked(title, txt):
                    break
            return title, txt
        finally:
            br.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    urls = [sys.argv[1]] if len(sys.argv) > 1 else URLS
    ok = 0
    for i, url in enumerate(urls):
        try:
            title, txt = fetch_one(url)
            status = "BLOCKED" if blocked(title, txt) else "OK"
            if status == "OK":
                (OUT / f"{slug(url)}.txt").write_text(
                    f"URL: {url}\nTITLE: {title}\n\n{txt}", encoding="utf-8")
                ok += 1
            print(f"[{i+1}/{len(urls)}] {status}  {title[:55]}  ({len(txt)}c)  {url}", flush=True)
        except Exception as e:
            print(f"[{i+1}/{len(urls)}] ERR {url}: {e}", flush=True)
        time.sleep(3)
    print(f"\nsaved {ok}/{len(urls)} -> {OUT}")


if __name__ == "__main__":
    main()
