"""Scrape recent EminiAddict daily-analysis posts (member content) — the slide charts
+ video refs — using the user's session cookie. Slides/videos are copyrighted (user is a
paying subscriber); everything lands under eminiaddict/data/site/ which is gitignored.

Usage: EA_COOKIE=<path> python scrape_ea.py [n_posts]
   cookie file = the raw "name=value; ..." header string (session-scratchpad, not committed).
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "eminiaddict", "data", "site")
SITEMAP = "https://eminiaddict.com/post-sitemap.xml"
COOKIE = open(os.environ["EA_COOKIE"], encoding="utf-8").read().strip()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"Cookie": COOKIE, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else r.read().decode("utf-8", "ignore")


def recent_posts(n):
    x = get(SITEMAP)
    rows = []
    for b in re.finditer(r"<url>(.*?)</url>", x, re.S):
        loc = re.search(r"<loc>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</loc>", b.group(1))
        lm = re.search(r"<lastmod>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</lastmod>", b.group(1))
        if loc:
            rows.append((lm.group(1) if lm else "", loc.group(1)))
    rows.sort(reverse=True)
    return rows[:n]


def parse_post(html):
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"\s*\|\s*Emini Addict.*", "", t.group(1)).strip() if t else ""
    slides = []
    for m in re.findall(r'https://eminiaddict\.com/keylevels/[A-Za-z0-9]+\.png', html):
        if m not in slides:
            slides.append(m)                          # preserve document order
    vid = re.search(r'(ttmm\d+\.s3[^"]+?)(\d{6})_player\.html', html)
    video = None
    if vid:
        base = vid.group(1).split("//", 1)[-1].split("/", 1)[0]  # bucket host
        mmddyy = vid.group(2)
        video = f"https://{base}/{mmddyy}.mp4"
    body = re.search(r'entry-content clearfix">(.*?)</div>\s*<footer', html, re.S)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.group(1))) if body else ""
    return title, slides, video, txt.strip()[:2000]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    os.makedirs(OUT, exist_ok=True)
    posts = recent_posts(n)
    print(f"{len(posts)} recent posts, {posts[-1][0][:10]} .. {posts[0][0][:10]}")
    manifest = []
    for lm, url in posts:
        pid = re.search(r"p=(\d+)", url).group(1)
        html = get(url)
        title, slides, video, txt = parse_post(html)
        if "protected for members only" in html.lower():
            print(f"  [{pid}] NOT AUTHENTICATED — cookie expired?"); break
        d = os.path.join(OUT, f"{lm[:10]}_{pid}")
        os.makedirs(d, exist_ok=True)
        got = 0
        for i, s in enumerate(slides):
            fp = os.path.join(d, f"slide_{i:02d}.png")
            if not os.path.exists(fp):
                try:
                    open(fp, "wb").write(get(s, binary=True)); got += 1; time.sleep(0.15)
                except Exception as e:
                    print(f"    slide fail {s}: {e}")
        open(os.path.join(d, "post.json"), "w", encoding="utf-8").write(json.dumps(
            {"pid": pid, "date": lm[:10], "lastmod": lm, "title": title, "url": url,
             "n_slides": len(slides), "video": video, "text": txt}, indent=1))
        manifest.append({"pid": pid, "date": lm[:10], "title": title, "dir": os.path.basename(d),
                         "n_slides": len(slides), "video": video})
        print(f"  [{pid}] {lm[:10]}  {len(slides)} slides ({got} new)  {title[:48]}")
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    print(f"wrote manifest ({len(manifest)} posts) -> {OUT}/manifest.json")


if __name__ == "__main__":
    main()
