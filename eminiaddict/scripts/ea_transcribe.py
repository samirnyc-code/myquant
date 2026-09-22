"""ea_transcribe.py — reusable: download a public EminiAddict S3 mp4, extract audio, and
transcribe it with faster-whisper (timestamped). Used for both the Getting Started lesson
videos and the daily market-analysis videos. No cookie needed (S3 videos are public).

Transcripts are DERIVED study notes (copyrighted source) — text only, media not kept.

CLI:
  # transcribe the 8 Getting Started lesson videos from the scraped manifest:
  python ea_transcribe.py --gs
  # transcribe one video by url:
  python ea_transcribe.py --url https://.../073126.mp4 --out path/to/out.txt
  # transcribe a daily video by date (MMDDYY resolved to public S3):
  python ea_transcribe.py --daily 073126
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GS = os.path.join(ROOT, "eminiaddict", "data", "site", "getting_started")
DAILY_BUCKET = "https://ttmm25.s3.us-west-2.amazonaws.com"   # daily videos <MMDDYY>.mp4
UA = "Mozilla/5.0"
_MODEL = {}


def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    return dst


def to_wav(mp4, wav):
    subprocess.run(["ffmpeg", "-y", "-i", mp4, "-vn", "-ac", "1", "-ar", "16000", wav],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def transcribe(wav, out_txt, model_name="small.en"):
    from faster_whisper import WhisperModel
    if model_name not in _MODEL:
        _MODEL[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    model = _MODEL[model_name]
    segments, info = model.transcribe(wav, language="en", vad_filter=True,
                                      vad_parameters=dict(min_silence_duration_ms=500))
    lines = []
    for s in segments:
        lines.append(f"[{int(s.start//60):02d}:{int(s.start%60):02d}] {s.text.strip()}")
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)
    open(out_txt, "w", encoding="utf-8").write("\n".join(lines))
    return len(lines), info.duration


def process(url, out_txt, model_name="small.en"):
    if os.path.exists(out_txt) and os.path.getsize(out_txt) > 200:
        print(f"  skip (exists): {os.path.relpath(out_txt, ROOT)}"); return
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = os.path.join(tmp, "v.mp4"); wav = os.path.join(tmp, "v.wav")
        print(f"  downloading {url}")
        download(url, mp4)
        print(f"  extracting audio -> wav")
        to_wav(mp4, wav)
        print(f"  transcribing ({model_name}) ...")
        n, dur = transcribe(wav, out_txt, model_name)
        print(f"  wrote {os.path.relpath(out_txt, ROOT)}  ({n} segs, {dur:.0f}s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gs", action="store_true", help="transcribe Getting Started lesson videos")
    ap.add_argument("--daily", help="MMDDYY date of a daily video")
    ap.add_argument("--url"); ap.add_argument("--out")
    ap.add_argument("--model", default="small.en")
    a = ap.parse_args()

    if a.gs:
        man = json.load(open(os.path.join(GS, "manifest.json")))
        outdir = os.path.join(GS, "transcripts")
        jobs = [(f"{r['idx']:02d}_{re.sub(r'[^a-z0-9]+','-',r['label'].lower()).strip('-')[:40]}",
                 v) for r in man for v in r.get("videos", []) if v.endswith(".mp4")]
        print(f"Getting Started: {len(jobs)} lesson videos")
        for name, url in jobs:
            print(f"[{name}]")
            try:
                process(url, os.path.join(outdir, name + ".txt"), a.model)
            except Exception as e:
                print(f"  FAIL {name}: {str(e)[:80]}")
    elif a.daily:
        url = f"{DAILY_BUCKET}/{a.daily}.mp4"
        out = a.out or os.path.join(ROOT, "eminiaddict", "data", "daily", a.daily, "transcript.txt")
        process(url, out, a.model)
    elif a.url and a.out:
        process(a.url, a.out, a.model)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
