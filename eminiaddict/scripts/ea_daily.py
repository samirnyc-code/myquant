"""ea_daily.py — daily EminiAddict video tool: find the latest daily video (public S3),
download + transcribe it, and scaffold a structured template report + scenario-tracker entry.

The report FIELDS are filled from the transcript (market state, bias, current MM, ES watch,
per-instrument notes, scenarios). Extraction is done by the assistant reading the transcript
(no API key here); this script owns discovery, transcription, storage, and the schema so the
report is consistent and the scenario tracker accumulates across days.

Layout:  eminiaddict/data/daily/<MMDDYY>/  transcript.txt  +  report.json

CLI:
  python ea_daily.py --latest [--since 2026-08-02]   # find newest, transcribe, scaffold
  python ea_daily.py --date 073126
"""
import argparse
import datetime as dt
import json
import os
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DAILY = os.path.join(ROOT, "eminiaddict", "data", "daily")
BUCKET = "https://ttmm25.s3.us-west-2.amazonaws.com"
UA = "Mozilla/5.0"

# instruments DH covers (indices + FX + commodities/bonds); report scaffolds these, transcript fills
INSTRUMENTS = ["ES", "NQ", "YM", "RTY", "6E", "CL", "GC", "ZB"]

REPORT_TEMPLATE = {
    "date": "", "mmddyy": "", "video_url": "", "transcribed": False, "extracted": False,
    "market_state": "",        # overall (trend day? balance? risk-on/off, VIX/DXY note)
    "outlook": "",             # bullish / bearish / neutral (overall bias)
    "current_mm": "",          # which measured move / series we're in (traditional/extension/#)
    "es_watch": "",            # the key ES levels + what to watch (user's top interest)
    "instruments": {k: {"bias": "", "levels": "", "notes": ""} for k in INSTRUMENTS},
    "scenarios": [],           # [{instrument, prediction, trigger, target, invalidation,
                               #   outcome: pending|hit|miss|partial, resolved_note}]
    "other_notes": "",
}


def head_ok(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception:
        return False


def find_latest(since=None, back=10):
    d0 = dt.date.fromisoformat(since) if since else dt.date.today()
    for i in range(back):
        d = d0 - dt.timedelta(days=i)
        mmddyy = d.strftime("%m%d%y")
        if head_ok(f"{BUCKET}/{mmddyy}.mp4"):
            return d.isoformat(), mmddyy
    return None, None


def scaffold(date_iso, mmddyy):
    d = os.path.join(DAILY, mmddyy)
    os.makedirs(d, exist_ok=True)
    rp = os.path.join(d, "report.json")
    if not os.path.exists(rp):
        r = json.loads(json.dumps(REPORT_TEMPLATE))
        r["date"] = date_iso; r["mmddyy"] = mmddyy
        r["video_url"] = f"{BUCKET}/{mmddyy}.mp4"
        json.dump(r, open(rp, "w", encoding="utf-8"), indent=1)
    return d, rp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--since", help="YYYY-MM-DD anchor for --latest (machine clock is unreliable)")
    ap.add_argument("--date", help="MMDDYY")
    ap.add_argument("--model", default="small.en")
    a = ap.parse_args()

    if a.latest:
        date_iso, mmddyy = find_latest(a.since)
        if not mmddyy:
            print("! no daily video found near", a.since or "today"); return
    elif a.date:
        mmddyy = a.date
        date_iso = dt.datetime.strptime(mmddyy, "%m%d%y").date().isoformat()
    else:
        ap.print_help(); return

    print(f"daily: {date_iso}  ({mmddyy})")
    d, rp = scaffold(date_iso, mmddyy)
    # transcribe (reuse ea_transcribe)
    import ea_transcribe
    out_txt = os.path.join(d, "transcript.txt")
    ea_transcribe.process(f"{BUCKET}/{mmddyy}.mp4", out_txt, a.model)
    r = json.load(open(rp))
    r["transcribed"] = os.path.exists(out_txt) and os.path.getsize(out_txt) > 200
    json.dump(r, open(rp, "w", encoding="utf-8"), indent=1)
    print(f"scaffolded {os.path.relpath(rp, ROOT)}  transcribed={r['transcribed']}")
    print("NEXT: fill report.json fields from transcript.txt (assistant extraction).")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    main()
