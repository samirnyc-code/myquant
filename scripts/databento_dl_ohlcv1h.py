"""databento_dl_ohlcv1h.py — poll + download the ES ohlcv-1h batch job (user-submitted).

Job: GLBX-20260723-QSMLGGLMWB  (ohlcv-1h, ES.FUT parent, 2010-06-06 -> 2026-07-22)
Downloads per-file (the whole-zip route 504'd on the big MBO job; harmless habit here)
into data/databento/GLBX-20260723-QSMLGGLMWB/. Skips files already fully present.

Run: .venv/Scripts/python.exe scripts/databento_dl_ohlcv1h.py   (loops until job done + files down)
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import databento as db

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
JOB_ID = "GLBX-20260723-QSMLGGLMWB"
DEST = ROOT / "data" / "databento" / JOB_ID
POLL_S = 60
MAX_WAIT_S = 3600


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    c = db.Historical(key)
    t0 = time.time()
    while True:
        jobs = {j["id"]: j for j in c.batch.list_jobs()}
        j = jobs.get(JOB_ID)
        if j is None:
            print(f"job {JOB_ID} not found"); sys.exit(1)
        state = j.get("state")
        print(f"[{time.strftime('%H:%M:%S')}] state={state} size={j.get('actual_size')}")
        if state == "done":
            break
        if state == "expired" or (time.time() - t0) > MAX_WAIT_S:
            print("giving up (expired or >1h)"); sys.exit(2)
        time.sleep(POLL_S)

    DEST.mkdir(parents=True, exist_ok=True)
    files = c.batch.list_files(JOB_ID)
    print(f"{len(files)} files in job")
    got = 0
    for f in files:
        name = f["filename"]
        want = int(f.get("size") or 0)
        tgt = DEST / name
        if tgt.exists() and tgt.stat().st_size == want:
            print(f"  skip (have) {name}")
            continue
        c.batch.download(job_id=JOB_ID, output_dir=DEST, filename_to_download=name)
        ok = tgt.exists() and (want == 0 or tgt.stat().st_size == want)
        print(f"  {'ok  ' if ok else 'SIZE MISMATCH'} {name} ({tgt.stat().st_size if tgt.exists() else 0:,} B)")
        got += 1
    print(f"downloaded {got} files -> {DEST}")


if __name__ == "__main__":
    main()
