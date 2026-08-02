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


def process(mmddyy):
    d = os.path.join(DAILY, mmddyy)
    rp = os.path.join(d, "report.json"); tp = os.path.join(d, "transcript.txt")
    if not (os.path.exists(rp) and os.path.exists(tp)):
        print(f"! {mmddyy}: missing report/transcript"); return
    r = json.load(open(rp, encoding="utf-8"))
    url = r.get("video_url")
    lines = ts_lines(tp)
    fdir = os.path.join(d, "frames"); os.makedirs(fdir, exist_ok=True)
    plan = []
    for topic, phrases in TOPICS:
        sec = cue(lines, phrases)
        if sec is None:
            continue
        plan.append((topic, sec + OFFSET))
        if topic == "ES":                       # grab the extra ES timeframes he flips through
            nxt = first_hit(lines, ES_TF_CUES, after=sec)
            k = 2
            while nxt and k <= 3:
                plan.append((f"ES-tf{k}", nxt + OFFSET))
                nxt2 = first_hit(lines, ES_TF_CUES, after=nxt + 5)
                nxt = nxt2; k += 1
    plan.sort(key=lambda x: x[1])
    idx = []
    print(f"{mmddyy}: grabbing {len(plan)} frames")
    for i, (topic, sec) in enumerate(plan):
        out = os.path.join(fdir, f"{i:02d}_{topic}.png")
        ok = grab(url, sec, out)
        print(f"  [{'ok' if ok else 'FAIL'}] {topic} @ {sec//60:02d}:{sec%60:02d}")
        if ok:
            idx.append({"topic": topic, "sec": sec, "file": os.path.basename(out)})
    json.dump(idx, open(os.path.join(fdir, "frames.json"), "w"), indent=1)
    print(f"  wrote {len(idx)} frames + frames.json")


def main():
    args = sys.argv[1:]
    if args == ["--all"]:
        args = sorted(d for d in os.listdir(DAILY) if os.path.isdir(os.path.join(DAILY, d)))
    for mmddyy in args:
        process(mmddyy)


if __name__ == "__main__":
    main()
