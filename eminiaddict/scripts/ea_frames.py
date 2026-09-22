"""ea_frames.py — snap David Halsey's ACTUAL chart frames out of the daily video (his fibs,
anchors, opposing/HTF levels) and save them per instrument, so the report shows HIS charts
rather than abstract levels.

How: the transcript is timestamped. We find where he says "let's move on to our <X> chart"
(and the timeframe cues inside the ES discussion) and use ffmpeg to seek DIRECTLY into the
public S3 mp4 (HTTP range seek — no full download) and grab that frame a few seconds later,
once the chart is on screen.

Output: eminiaddict/data/daily/<MMDDYY>/frames/<NN>_<topic>.png  (+ frames.json index)

Usage: python ea_frames.py <MMDDYY> [MMDDYY ...]      # e.g. 073126
       python ea_frames.py --all                       # every day under data/daily/
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import matplotlib.image as mpimg

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DAILY = os.path.join(ROOT, "eminiaddict", "data", "daily")
OFFSET = 8          # seconds after the cue (let him get the chart up / zoom)
UA = "Mozilla/5.0"

# topic -> ordered phrases (first match in the transcript wins); order = display order
TOPICS = [
    ("DXY",  ["dxy", "dollar chart", "the actual dollar"]),
    ("BANK", ["bank chart", "bank is", "the bank"]),
    ("VIX",  ["vix chart", "the vix"]),
    ("ES",   ["es chart", "our es"]),
    ("NQ",   ["nq chart", "nq is", "nasdaq"]),
    ("YM",   ["ym chart", "the ym"]),
    ("RTY",  ["rty chart", "russell"]),
    ("BTC",  ["bitcoin"]),
    ("ETH",  ["ethereum", "aetherium"]),
    ("CL",   ["crude oil", "crude"]),
    ("6J",   ["dollar yen"]),
    ("6E",   ["the euro", "euro chart"]),
    ("GC",   ["gold chart", "gc is", " gold "]),
    ("SI",   ["silver"]),
]
ES_TF_CUES = ["four-hour", "4-hour", "12-hour", "twelve-hour", "hourly chart", "daily chart",
              "12 hour", "four hour"]


def ts_lines(path):
    out = []
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"\[(\d+):(\d+)\]\s*(.*)", ln)
        if m:
            out.append((int(m.group(1)) * 60 + int(m.group(2)), m.group(3).lower()))
    return out


_TRANS = ("moving on", "move on", "let's go", "let's move", "here to our", "here to the",
          "go to our", "go to the", "look at our", "then there", "then the", "onto our",
          "on to our")


def first_hit(lines, phrases, after=0):
    for sec, txt in lines:
        if sec < after:
            continue
        if any(p in txt for p in phrases):
            return sec
    return None


def cue(lines, phrases, after=0):
    """Prefer the line where he TRANSITIONS to that chart (has 'chart'/'moving on to our ...'),
    not an earlier passing mention in the econ/regime intro."""
    for sec, txt in lines:
        if sec < after:
            continue
        if any(p in txt for p in phrases) and ("chart" in txt or any(t in txt for t in _TRANS)):
            return sec
    return first_hit(lines, phrases, after)


def grab(url, sec, out_png):
    r = subprocess.run(["ffmpeg", "-y", "-ss", str(sec), "-i", url, "-frames:v", "1",
                        "-q:v", "3", out_png],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and os.path.exists(out_png) and os.path.getsize(out_png) > 3000


def blue_hlines(png):
    """Count horizontal CYAN/BLUE lines = a fib being DRAWN (not yet set). The 21-EMA is also
    cyan but wavy (few pixels per row), so a width-spanning blue row = an in-progress fib."""
    try:
        im = mpimg.imread(png)
    except Exception:
        return 999
    if im.ndim < 3:
        return 999
    if im.max() > 1:
        im = im / 255.0
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    blue = (b > 0.5) & (r < 0.5) & (g > 0.35) & (g < 0.92)
    rowfrac = blue.mean(axis=1)
    return int((rowfrac > 0.30).sum())


def best_frame(url, base, endcap, out_png):
    """Sample a few offsets after the cue; keep the frame with the FEWEST blue (drawing) lines."""
    offs = [o for o in (8, 18, 30, 45, 62, 80) if base + o < endcap] or [8]
    best_score, best_off = None, None
    with tempfile.TemporaryDirectory() as td:
        for o in offs:
            tmp = os.path.join(td, f"{o}.png")
            if not grab(url, base + o, tmp):
                continue
            s = blue_hlines(tmp)
            if best_score is None or s < best_score:
                best_score, best_off = s, o
                import shutil
                shutil.copy(tmp, out_png)
            if s == 0:
                break
    return (best_off is not None), best_score, best_off


def process(mmddyy):
    d = os.path.join(DAILY, mmddyy)
    rp = os.path.join(d, "report.json"); tp = os.path.join(d, "transcript.txt")
    if not (os.path.exists(rp) and os.path.exists(tp)):
        print(f"! {mmddyy}: missing report/transcript"); return
    r = json.load(open(rp, encoding="utf-8"))
    url = r.get("video_url")
    lines = ts_lines(tp)
    fdir = os.path.join(d, "frames"); os.makedirs(fdir, exist_ok=True)
    for old in os.listdir(fdir):
        if old.endswith(".png") or old == "frames.json":
            os.remove(os.path.join(fdir, old))
    # plan (topic, cue_sec); ES gets its extra timeframe frames
    plan = []
    for topic, phrases in TOPICS:
        sec = cue(lines, phrases)
        if sec is None:
            continue
        plan.append((topic, sec))
        if topic == "ES":
            nxt = first_hit(lines, ES_TF_CUES, after=sec)
            k = 2
            while nxt and k <= 3:
                plan.append((f"ES-tf{k}", nxt))
                nxt = first_hit(lines, ES_TF_CUES, after=nxt + 5); k += 1
    plan.sort(key=lambda x: x[1])
    idx = []
    print(f"{mmddyy}: {len(plan)} charts (picking the SETTLED frame = no blue/drawing)")
    for i, (topic, sec) in enumerate(plan):
        endcap = plan[i + 1][1] if i + 1 < len(plan) else sec + 90
        out = os.path.join(fdir, f"{i:02d}_{topic}.png")
        ok, score, off = best_frame(url, sec, min(endcap, sec + 90), out)
        tag = "ok" if ok else "FAIL"
        print(f"  [{tag}] {topic:7s} @ {(sec+(off or 0))//60:02d}:{(sec+(off or 0))%60:02d}"
              f"  blue-lines={score}")
        if ok:
            idx.append({"topic": topic, "sec": sec + (off or 0), "blue": score,
                        "file": os.path.basename(out)})
    json.dump(idx, open(os.path.join(fdir, "frames.json"), "w"), indent=1)
    print(f"  wrote {len(idx)} settled frames + frames.json")


def main():
    args = sys.argv[1:]
    if args == ["--all"]:
        args = sorted(d for d in os.listdir(DAILY) if os.path.isdir(os.path.join(DAILY, d)))
    for mmddyy in args:
        process(mmddyy)


if __name__ == "__main__":
    main()
