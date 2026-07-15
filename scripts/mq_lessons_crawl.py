"""Deep-crawl MenthorQ ACADEMY LESSON BODIES (S73 night) — the actual content
behind each course page's "Start" links, which the first crawl missed.
Output -> data/menthorq/knowledge/lessons/ + _index.json
"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menthorq" / "knowledge" / "lessons"
AUTH = ROOT / "gamma_tracker" / "auth_state_mqcom.json"
NAV_JUNK = ("facebook", "twitter", "instagram", "youtube", "linkedin", "/cart",
            "/checkout", "/pricing", "/login", "/terms", "/privacy", "#")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    idx = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH) if AUTH.exists() else None,
                             viewport={"width": 1500, "height": 1000})
        page = ctx.new_page()
        # collect lesson links from every course page
        course_urls = []
        page.goto("https://menthorq.com/academy/", wait_until="networkidle", timeout=60000)
        hrefs = page.eval_on_selector_all("a[href*='/academy/']", "els=>[...new Set(els.map(e=>e.href))]")
        course_urls = [h for h in hrefs if "menthorq.com/academy/" in h][:40]
        lesson_urls = set()
        for cu in course_urls:
            try:
                page.goto(cu, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(1200)
                links = page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href)")
                for h in links:
                    if ("menthorq.com" in h and h not in course_urls
                            and not any(j in h for j in NAV_JUNK)
                            and any(k in h.lower() for k in ("/lesson", "/lessons", "/topic",
                                                             "/courses", "/academy/"))):
                        lesson_urls.add(h.split("#")[0])
            except Exception as e:
                print(f"course FAIL {cu[:60]}: {str(e)[:60]}")
        lesson_urls -= set(course_urls)
        print(f"{len(lesson_urls)} candidate lesson URLs")
        for i, u in enumerate(sorted(lesson_urls)[:180]):
            slug = re.sub(r"[^a-z0-9]+", "_", u.split("menthorq.com/")[-1])[:75]
            try:
                page.goto(u, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(1200)
                txt = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
                if len(txt) < 800:
                    continue
                (OUT / f"{slug}.txt").write_text(txt, encoding="utf-8")
                idx.append({"url": u, "title": page.title(), "chars": len(txt)})
                print(f"  [{len(idx)}] {page.title()[:60]} ({len(txt)}ch)")
            except Exception as e:
                print(f"  FAIL {u[:70]}: {str(e)[:50]}")
        (OUT / "_index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")
        br.close()
    print(f"\n{len(idx)} lesson pages -> {OUT}")


if __name__ == "__main__":
    main()
