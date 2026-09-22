#!/usr/bin/env python
"""backfill_eth_from_nt.py — one-command full-session (ETH) backfill from NT8's
.ncd into data/ticks_continuous_eth/, contract by contract.

Requires NinjaTrader RUNNING with TickExportAddOn loaded (it auto-loads on start;
if you just compiled, it's loaded). Per contract in the coverage map it:
  1. writes data/nt_ticks/_request.json {contract, from, to, period:1, hours:ETH}
  2. waits for _request.done.json (the AddOn exports one CSV per weekday)
  3. runs ingest_nt_ticks_eth.py on those CSVs (RTH trove untouched; parallel store)
  4. deletes that contract's CSVs before the next (bounds disk to ~one contract)

Coverage map = what NT still holds (verified 2026-09-12): 2025-07-11 -> 2026-09-11.
Re-runnable: the ETH ingest skips dates already written (unless --force).

  python scripts/backfill_eth_from_nt.py                # full map
  python scripts/backfill_eth_from_nt.py --only "ES 09-26"   # one contract
  python scripts/backfill_eth_from_nt.py --dry-run      # print the plan, do nothing
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NT = ROOT / "data" / "nt_ticks"
REQ, DONE = NT / "_request.json", NT / "_request.done.json"
HOURS = "CME US Index Futures ETH"
PY = sys.executable

# NT .ncd contiguous coverage (folder date span); the ETH ingest roll-guard trims
# each to the days that contract was actually front-month, so overlaps are safe.
COVERAGE = [
    ("ES 09-25", "2025-07-11", "2025-09-12"),
    ("ES 12-25", "2025-09-14", "2025-12-12"),
    ("ES 03-26", "2025-12-14", "2026-03-13"),
    ("ES 06-26", "2026-03-15", "2026-06-18"),
    ("ES 09-26", "2026-06-08", "2026-09-11"),
]


def run_contract(contract, frm, to, timeout, force):
    tag = contract.replace(" ", "_")
    for f in NT.glob(f"{tag}_ticks_*.csv"):
        f.unlink()
    if DONE.exists():
        DONE.unlink()
    REQ.write_text(json.dumps({"contract": contract, "from": frm, "to": to,
                               "period": 1, "hours": HOURS}), encoding="utf-8")
    print(f"\n=== {contract} {frm}..{to} — requested (ETH); waiting for AddOn ===", flush=True)
    waited = 0
    while waited < timeout:
        if DONE.exists():
            break
        time.sleep(15)
        waited += 15
    else:
        print(f"! {contract}: TIMEOUT after {timeout}s — is NinjaTrader running with the AddOn?")
        return False
    print(f"  export done: {DONE.read_text(encoding='utf-8').strip()}")
    csvs = sorted(NT.glob(f"{tag}_ticks_*.csv"))
    if not csvs:
        print(f"! {contract}: no CSVs produced (out of .ncd retention?) — skipping")
        return True
    cmd = [PY, str(ROOT / "scripts" / "ingest_nt_ticks_eth.py"),
           "--glob", f"data/nt_ticks/{tag}_ticks_*.csv", "--validate-rth"]
    if force:
        cmd.append("--force")
    subprocess.run(cmd, check=False)
    for f in csvs:                      # free disk before the next contract
        f.unlink()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="single contract, e.g. 'ES 09-26'")
    ap.add_argument("--timeout", type=int, default=3600, help="secs to wait per contract")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    plan = [c for c in COVERAGE if (not a.only or c[0] == a.only)]
    print("BACKFILL PLAN (ETH -> data/ticks_continuous_eth/):")
    for c, f, t in plan:
        print(f"  {c}: {f} .. {t}")
    if a.dry_run:
        return
    for contract, frm, to in plan:
        if not run_contract(contract, frm, to, a.timeout, a.force):
            print("aborting remaining contracts (export failed)."); break
    if REQ.exists():
        REQ.unlink()
    print("\nBACKFILL COMPLETE. ETH store: data/ticks_continuous_eth/")


if __name__ == "__main__":
    main()
