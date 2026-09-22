"""Fetch a CURATED list of Take Profit Trader PRO/payout rule pages one at a time
with a FRESH browser per page (the bulk crawl in tpt_scrape.py crashed the tab on
these). Saves each page's text to reports/tpt_scrape/.

  python scripts/tpt_fetch_pages.py            # fetch the built-in list
  python scripts/tpt_fetch_pages.py <url>      # test a single url
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "reports" / "tpt_scrape"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
URLS = [
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171769361053-PRO-Account-Rules",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171820366109-How-to-Keep-Track-Of-Your-Drawdown",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171929948829-Advantages-of-PRO",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171895352733-Resetting-A-PRO-Account",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171522280733-Utilizing-Your-Wallet",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171820366109-How-to-Keep-Track-Of-Your-Drawdown",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15168980013085-Keeping-Track-of-Your-Progress",
    "https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15170470213789-Finding-Your-Accounts",
]


def slug(url):
    net = urlparse(url).netloc.split(".")[0]
    p = urlparse(url).path.strip("/").replace("/", "__") or "index"
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", f"{net}__{p}")[:150]


def blocked(title, txt):
    t = (title or "").lower()
    return "attention required" in t or "just a moment" in t or "403" in t or len(txt) < 200


def fetch_one(url):
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=True)
        try:
            pg = br.new_context(user_agent=UA, locale="en-US",
                                viewport={"width": 1366, "height": 850}).new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            title, txt = "", ""
            for _ in range(10):
                pg.wait_for_timeout(2000)
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
