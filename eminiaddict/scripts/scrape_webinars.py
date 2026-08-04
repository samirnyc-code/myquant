"""scrape_webinars.py — pull the EminiAddict "Webinars" collection (page_id=1867) that the
Getting Started scrape never followed: the hub lists ~26 webinars, each on its own ?p= page
with an S3 SmartPlayer video. Captures per-webinar title, text, video URL(s); dedupes against
the Getting Started lesson videos (8 of the webinars are the same mp4s).

Output (gitignored, copyrighted): eminiaddict/data/site/webinars/
    manifest.json                      ordered list w/ video refs + dupe_of_lesson marker
    <NN>_<slug>/item.json              per-webinar record

--transcribe: download+transcribe every non-dupe mp4 (faster-whisper via ea_transcribe),
resumable (skips existing transcripts) -> webinars/transcripts/<NN>_<slug>.txt
Key-point nuggets (assistant-written) go to webinars/nuggets/<NN>.md.

Usage: EA_COOKIE=<path to cookie file> python scrape_webinars.py [--transcribe] [--model small.en]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_getting_started import get, find_videos, content_area, slug  # noqa: E402  (reads EA_COOKIE)
import ea_transcribe  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "eminiaddict", "data", "site", "webinars")
GS_MAN = os.path.join(ROOT, "eminiaddict", "data", "site", "getting_started", "manifest.json")
HUB = "https://eminiaddict.com/?page_id=1867"


def webinar_list():
    """Ordered (label, url) from the webinars hub content area, deduped by ?p= id."""
    area = content_area(get(HUB))
    items, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(https?://eminiaddict\.com/\?p=(\d+))"[^>]*>(.*?)</a>',
                         area, re.S):
        url, pid = m.group(1).replace("http://", "https://"), m.group(2)
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(3))).strip()
        if pid in seen:
            continue
        seen.add(pid)
        items.append((label, url))
    return items


def gs_lesson_by_mp4():
    """mp4 url -> lesson idx for the Getting Started videos (to mark webinar dupes)."""
    man = json.load(open(GS_MAN, encoding="utf-8"))
    return {v: r["idx"] for r in man for v in r.get("videos", []) if v.endswith(".mp4")}


def scrape():
    os.makedirs(OUT, exist_ok=True)
    dupes = gs_lesson_by_mp4()
    items = webinar_list()
    print(f"webinars hub: {len(items)} sub-pages")
    manifest = []
    for i, (label, url) in enumerate(items):
        try:
            html = get(url)
        except Exception as e:
            print(f"  [{i:02d}] FETCH FAIL {url}: {e}")
            continue
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        title = re.sub(r"\s*\|\s*Emini Addict.*", "", t.group(1)).strip() if t else label
        label = label or title
        area = content_area(html)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", area)).strip()
        videos = find_videos(html)
        mp4s = [v for v in videos if v.endswith(".mp4")]
        dupe = next((dupes[v] for v in mp4s if v in dupes), None)
        d = os.path.join(OUT, f"{i:02d}_{slug(label)}")
        os.makedirs(d, exist_ok=True)
        rec = {"idx": i, "label": label, "title": title, "url": url, "videos": videos,
               "mp4": mp4s[0] if mp4s else None, "dupe_of_lesson": dupe,
               "text": text, "dir": os.path.basename(d)}
        json.dump(rec, open(os.path.join(d, "item.json"), "w", encoding="utf-8"), indent=1)
        manifest.append(rec)
        print(f"  [{i:02d}] {label[:52]:54s} mp4={'Y' if mp4s else '-'} "
              f"{'dupe of lesson %02d' % dupe if dupe is not None else ''}")
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"),
              indent=1)
    new = [m for m in manifest if m["mp4"] and m["dupe_of_lesson"] is None]
    print(f"\nwrote {len(manifest)} webinars -> manifest.json; {len(new)} new mp4s to transcribe")
    return manifest


# the trading-METHOD webinars (user-approved 2026-08-04); macro/crypto commentary excluded
METHOD_IDX = [3, 8, 9, 10, 11, 12, 16, 20, 21, 22, 25]


def transcribe_all(model="small.en", idx=None):
    man = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
    outdir = os.path.join(OUT, "transcripts")
    jobs = [m for m in man if m["mp4"] and m["dupe_of_lesson"] is None
            and (idx is None or m["idx"] in idx)]
    print(f"transcribing {len(jobs)} webinars (resumable; dupes of lessons skipped)")
    for m in jobs:
        name = f"{m['idx']:02d}_{slug(m['label'])}"
        print(f"[{name}]")
        try:
            ea_transcribe.process(m["mp4"], os.path.join(outdir, name + ".txt"), model)
        except Exception as e:
            print(f"  FAIL {name}: {str(e)[:100]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcribe", action="store_true")
    ap.add_argument("--method-only", action="store_true", help="only the METHOD_IDX webinars")
    ap.add_argument("--idx", help="comma-separated webinar idx filter")
    ap.add_argument("--model", default="small.en")
    a = ap.parse_args()
    if a.transcribe:
        idx = ([int(x) for x in a.idx.split(",")] if a.idx
               else METHOD_IDX if a.method_only else None)
        transcribe_all(a.model, idx)
    else:
        scrape()
