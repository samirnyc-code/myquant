"""databento_0dte_submit.py — SUBMIT the one-shot 0DTE SPXW cbbo-1m batch jobs.

⚠️ THIS SPENDS against the account credit. get_cost already priced it at ~$7.73.
Submits one batch job per chunk of ~11 sessions (<=1800 raw_symbols/job, the 2000 cap),
each covering its own date range. Captures job_id + billed cost per job, sums, and
writes a manifest the downloader consumes. Resumable: skips chunks already in manifest.

Safety: --max-chunks N submits only the first N new chunks. Run with --max-chunks 1
first to confirm the LIVE returned cost matches the ~$0.10/chunk prediction before
firing the rest.

Grid: prior_close +/- 200pt, 5-pt, C+P (calls+puts), 0DTE (expiry == session).
Window: 2023-03-28 -> last close in spx_daily_ohlc.csv.

Run: .venv/Scripts/python.exe scripts/databento_0dte_submit.py --max-chunks 1
     .venv/Scripts/python.exe scripts/databento_0dte_submit.py            # all remaining
Out: data/databento/_0dte_jobs.json (manifest)
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import datetime as dt

import databento as db
from databento_0dte_band_price import construct, BAND_PTS, STEP

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
SPX_CSV = ROOT / "data" / "spx_daily_ohlc.csv"
MANIFEST = ROOT / "data" / "databento" / "_0dte_jobs.json"

DATASET = "OPRA.PILLAR"
SCHEMA = "cbbo-1m"
WINDOW_START = "2023-03-28"
WINDOW_END = "2026-08-04"          # last settled historical session (OPRA live-gates T and T-0)
MAX_SYMS_PER_JOB = 1800            # under the 2000 hard cap
DAYS_PER_CHUNK = MAX_SYMS_PER_JOB // 162   # ~11 sessions/job


def load_closes():
    closes = {}
    with open(SPX_CSV) as f:
        for r in csv.DictReader(f):
            if r["Close"]:
                closes[r["Date"]] = float(r["Close"])
    return closes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-chunks", type=int, default=None, help="submit only first N new chunks")
    args = ap.parse_args()

    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)
    closes = load_closes()
    dates = sorted(closes)
    sessions = [d for d in dates if WINDOW_START <= d <= WINDOW_END]

    # chunk sessions
    chunks = [sessions[i:i + DAYS_PER_CHUNK] for i in range(0, len(sessions), DAYS_PER_CHUNK)]

    man = {"dataset": DATASET, "schema": SCHEMA, "band_pts": BAND_PTS,
           "created": dt.datetime.now().isoformat(timespec="seconds"), "jobs": []}
    if MANIFEST.exists():
        man = json.loads(MANIFEST.read_text())
    done_starts = {j["start"] for j in man["jobs"]}

    submitted = 0
    total = sum(j.get("cost_usd", 0) for j in man["jobs"])
    for ch in chunks:
        start, last = ch[0], ch[-1]
        if start in done_starts:
            continue
        if args.max_chunks is not None and submitted >= args.max_chunks:
            break
        syms = []
        for d in ch:
            pc = closes[dates[dates.index(d) - 1]]
            syms += construct(d, pc, band=BAND_PTS, step=STEP)
        end = (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat()
        job = client.batch.submit_job(
            dataset=DATASET, symbols=syms, stype_in="raw_symbol", schema=SCHEMA,
            start=start, end=end, encoding="dbn", compression="zstd",
            split_duration="day", delivery="download")
        cost = float(job.get("cost_usd") or job.get("cost") or 0)
        total += cost
        rec = {"job_id": job["id"], "start": start, "end": end, "n_sessions": len(ch),
               "n_symbols": len(syms), "cost_usd": cost,
               "billed_size": job.get("billed_size") or job.get("actual_size")}
        man["jobs"].append(rec)
        submitted += 1
        MANIFEST.write_text(json.dumps(man, indent=2))
        print(f"[{submitted}] job {job['id']}  {start}..{last}  "
              f"{len(ch)}d {len(syms)}sym  ${cost:.4f}   (running ${total:.4f})")

    print(f"\nsubmitted {submitted} new job(s). manifest total: ${total:.4f}  "
          f"({len(man['jobs'])}/{len(chunks)} chunks)")
    print(f"manifest -> {MANIFEST}")


if __name__ == "__main__":
    main()
