"""scrape_getting_started.py — pull the ENTIRE EminiAddict "Getting Started" curriculum
(page_id=1872) into a local knowledge base: every teaching page/post in his order, with
title, cleaned text, all slide images, the glossary, and any embedded video URLs
(S3 mp4 / YouTube / Vimeo / Wistia). Member content -> uses the session cookie.

Output (gitignored, copyrighted): eminiaddict/data/site/getting_started/
    <NN>_<slug>/item.json  + slide_*.png/.jpg
    manifest.json  (ordered curriculum with video refs -> feeds the transcript/nugget step)

Usage: EA_COOKIE=<path to cookie file> python scrape_getting_started.py
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "eminiaddict", "data", "site", "getting_started")
HUB = "https://eminiaddict.com/?page_id=1872"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
COOKIE = open(os.environ["EA_COOKIE"], encoding="utf-8").read().strip()

# labels in the hub we DON'T treat as curriculum items (nav / external / daily-video feed)
SKIP_LABELS = {"emini addict", "testimonials", "chat room", "get started", "getting started",
               "posts", "market analysis videos", "thinkorswim thinkdesktop"}


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"Cookie": COOKIE, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read() if binary else r.read().decode("utf-8", "ignore")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "item"


def content_area(html):
    # entry-content contains nested divs; capture everything up to the entry-meta/footer
    for end in (r'<div class="entry-meta', r'<footer', r'<div class="sharedaddy'):
        m = re.search(r'class="entry-content[^"]*"[^>]*>(.*?)' + end, html, re.S)
        if m:
            return m.group(1)
    return html


def find_videos(html):
    vids = []
    # ANY S3 SmartPlayer page  .../<name>_player.html  ->  sibling  .../<name>.mp4
    for m in re.finditer(r'(https?://[^"\']*?/)([^"\'/]+?)_player\.html', html):
        vids.append(f"{m.group(1)}{m.group(2)}.mp4")
    vids += re.findall(r'https?://[^"\']*\.s3[^"\']*/\d+\.mp4', html)
    vids += re.findall(r'<source[^>]+src="([^"]+\.mp4)"', html)          # self-hosted <video>
    vids += re.findall(r'https?://[^"\']+\.mp4', html)
    vids += re.findall(r'https?://(?:www\.)?(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)'
                       r'[A-Za-z0-9_\-]+', html)
    vids += re.findall(r'https?://player\.vimeo\.com/video/\d+', html)
    vids += re.findall(r'https?://[^"\']*(?:wistia|jwplatform|dailymotion|vidyard)[^"\']+', html)
    # any iframe embed (webinar players)
    for src in re.findall(r'<iframe[^>]+src="([^"]+)"', html):
        if any(k in src for k in ("youtube", "vimeo", "wistia", "player", "video", ".mp4",
                                  "jwplat", "embed")):
            vids.append(src if src.startswith("http") else "https:" + src)
    out = []
    for v in vids:
        v = v.replace("&#038;", "&")
        if v not in out and "favicon" not in v:
            out.append(v)
    return out


def clean_img_urls(area):
    """Collect full-size slide images from src/data-src/srcset/href; drop thumbnails & chrome."""
    cands = []
    cands += re.findall(r'<img[^>]+(?:data-lazy-src|data-src|src)="([^"]+)"', area)
    for ss in re.findall(r'srcset="([^"]+)"', area):
        for part in ss.split(","):
            u = part.strip().split(" ")[0]
            if u:
                cands.append(u)
    cands += re.findall(r'<a[^>]+href="([^"]+\.(?:png|jpe?g|gif|webp))"', area, re.I)
    out, seen = [], set()
    for u in cands:
        u = u.strip().split("?")[0]                       # drop query/resize params
        if not re.match(r"https?://", u) or not re.search(r"\.(png|jpe?g|gif|webp)$", u, re.I):
            continue
        if any(k in u.lower() for k in ("favicon", "logo", "gravatar", "avatar", "emoji",
                                        "loading", "spinner", "/plugins/", "/themes/",
                                        "-150x", "-300x", "-1x1", "spacer", "blank")):
            continue
        base = re.sub(r"-\d+x\d+(?=\.\w+$)", "", u)        # WP thumbnail suffix
        base = re.sub(r"-scaled(?=\.\w+$)", "", base)      # WP -scaled variant
        key = re.sub(r".*/", "", base).lower()             # dedupe by basename (any host/size)
        if key not in seen:
            seen.add(key); out.append(base)
    return out


def curriculum():
    """Ordered (label, url) teaching items from the hub page, deduped, nav/external removed."""
    html = get(HUB)
    area = content_area(html)
    # include nav-bar section links too (Book/Tools/Indicators/Webinars live above content)
    anchors = re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S)
    items, seen = [], set()
    for href, txt in anchors:
        label = re.sub(r"<[^>]+>", "", txt)
        label = re.sub(r"\s+", " ", label).strip()
        if not label or label.lower() in SKIP_LABELS:
            continue
        if "eminiaddict.com" not in href:
            continue
        if not re.search(r"[?&](p|page_id)=\d+", href):
            continue
        url = href.replace("http://", "https://")
        key = re.search(r"[?&](?:p|page_id)=(\d+)", url).group(1)
        if key in seen:
            continue
        seen.add(key)
        items.append((label, url))
    return items


def main():
    os.makedirs(OUT, exist_ok=True)
    items = curriculum()
    print(f"curriculum: {len(items)} teaching items")
    manifest = []
    for i, (label, url) in enumerate(items):
        try:
            html = get(url)
        except Exception as e:
            print(f"  [{i:02d}] FETCH FAIL {url}: {e}"); continue
        gated = ("protected for members only" in html.lower()
                 or re.search(r"<title>\s*Members Only", html, re.I))
        if gated:
            print(f"  [{i:02d}] GATED (cookie invalid/expired): {label[:40]} {url} — skipping")
            manifest.append({"idx": i, "label": label, "title": "GATED", "url": url,
                             "n_images": 0, "videos": [], "dir": None, "gated": True})
            continue
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        title = re.sub(r"\s*\|\s*Emini Addict.*", "", t.group(1)).strip() if t else label
        area = content_area(html)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", area)).strip()
        imgs = clean_img_urls(area)
        videos = find_videos(html)
        d = os.path.join(OUT, f"{i:02d}_{slug(label)}")
        os.makedirs(d, exist_ok=True)
        for old in [f for f in os.listdir(d) if f.startswith("slide_")]:  # fresh, consistent
            os.remove(os.path.join(d, old))
        got = 0
        for j, im in enumerate(imgs):
            ext = re.search(r"\.(png|jpe?g|gif|webp)$", im, re.I)
            ext = "." + ext.group(1).lower() if ext else ".png"
            fp = os.path.join(d, f"slide_{j:02d}{ext}")
            try:
                data = get(im, binary=True)
                if len(data) < 1500:            # 1x1 pixels / broken -> skip, don't leave empties
                    continue
                open(fp, "wb").write(data); got += 1; time.sleep(0.1)
            except Exception as e:
                print(f"      img fail {im}: {str(e)[:60]}")
        rec = {"idx": i, "label": label, "title": title, "url": url,
               "n_images": len(imgs), "images": imgs, "videos": videos,
               "text": text, "dir": os.path.basename(d)}
        json.dump(rec, open(os.path.join(d, "item.json"), "w", encoding="utf-8"), indent=1)
        manifest.append({k: rec[k] for k in ("idx", "label", "title", "url", "n_images",
                                             "videos", "dir")})
        print(f"  [{i:02d}] {label[:40]:42s} imgs={len(imgs)}({got} new) vids={len(videos)} "
              f"words={len(text.split())}")
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {len(manifest)} items -> {os.path.relpath(OUT, ROOT)}/manifest.json")
    nv = sum(len(m["videos"]) for m in manifest)
    print(f"videos found across curriculum: {nv} (feed these to transcribe+nugget step)")


if __name__ == "__main__":
    main()
