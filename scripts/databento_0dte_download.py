"""databento_0dte_download.py — download all 0DTE batch jobs in the manifest.

Manifest-driven (data/databento/_0dte_jobs.json = 77 job IDs). For each job that is
`done`, downloads every file to data/databento/<job_id>/, skipping files already on
disk at the correct size (resumable), with retry on transient errors. Jobs still
processing are skipped and picked up on the next run. Downloads are FREE (the job was
already billed); re-downloadable for 30 days.

Run: .venv/Scripts/python.exe scripts/databento_0dte_download.py
Out: data/databento/<job_id>/*.dbn.zst  + console progress
"""
from __future__ import annotations
import json
import time
from pathlib import Path

import databento as db

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
MANIFEST = ROOT / "data" / "databento" / "_0dte_jobs.json"
OUTROOT = ROOT / "data" / "databento" / "0dte_spxw_cbbo1m"


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)
    job_ids = [j["job_id"] for j in json.loads(MANIFEST.read_text())["jobs"]]
    states = {j["id"]: j.get("state") for j in client.batch.list_jobs() if j.get("id") in job_ids}

    done = [j for j in job_ids if states.get(j) == "done"]
    pending = [j for j in job_ids if states.get(j) != "done"]
    print(f"{len(job_ids)} jobs: {len(done)} done, {len(pending)} pending (skipped this run)\n")

    tot_files = tot_bytes = 0
    for n, job in enumerate(done, 1):
        out = OUTROOT / job
        fs = client.batch.list_files(job)
        for f in fs:
            fn = f["filename"]
            sz = f.get("size", 0)
            dest = out / fn
            if dest.exists() and dest.stat().st_size == sz:
                tot_files += 1; tot_bytes += sz
                continue
            for attempt in range(5):
                try:
                    client.batch.download(output_dir=str(OUTROOT), job_id=job, filename_to_download=fn)
                    tot_files += 1; tot_bytes += sz
                    break
                except Exception as e:
                    print(f"  retry{attempt} {job}/{fn}: {str(e)[:60]}")
                    time.sleep(15)
        print(f"[{n}/{len(done)}] {job}  ({tot_files} files, {tot_bytes/1e9:.2f} GB)", flush=True)

    print(f"\nDONE: {tot_files} files, {tot_bytes/1e9:.2f} GB in {OUTROOT}")
    if pending:
        print(f"{len(pending)} jobs still processing — re-run to fetch them.")


if __name__ == "__main__":
    main()
