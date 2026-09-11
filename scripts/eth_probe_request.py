"""ETH-recoverability probe — fire ONE TickExportAddOn request for a recent day
with an ETH trading-hours override, then report the exported CSV's session span
so we can see whether NT's .ncd actually holds the overnight tape.

Writes data/nt_ticks/_request.json {contract, from, to, period, hours} and waits
for _request.done.json, then prints first/last timestamps + row count of the new
CSV. Does NOT ingest anything into the trove.

Run AFTER the user F5-reloads the AddOn (so it understands the new `hours` field):
  python scripts/eth_probe_request.py [YYYY-MM-DD] [hours-template]
Default day = 2026-09-10, default hours = "CME US Index Futures ETH".
"""
import json
import sys
import time
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NT = ROOT / "data" / "nt_ticks"
REQ, DONE = NT / "_request.json", NT / "_request.done.json"

day = sys.argv[1] if len(sys.argv) > 1 else "2026-09-10"
hours = sys.argv[2] if len(sys.argv) > 2 else "CME US Index Futures ETH"

before = {p.name for p in NT.glob("ES_*_ticks_*.csv")}
if DONE.exists():
    DONE.unlink()
REQ.write_text(json.dumps({
    "contract": "ES 09-26", "from": day, "to": day, "period": 1, "hours": hours
}), encoding="utf-8")
print(f"requested {day} with hours='{hours}'. waiting for AddOn (F5 must be done)...")

for _ in range(120):            # up to 20 min
    if DONE.exists():
        break
    time.sleep(10)
else:
    print("TIMEOUT — AddOn never answered. Did you F5-reload NinjaScript?")
    raise SystemExit(1)

print("done:", DONE.read_text(encoding="utf-8").strip())
new = sorted(p for p in NT.glob("ES_*_ticks_*.csv") if p.name not in before)
if not new:
    print("no new CSV produced (day had no data / wrong contract).")
    raise SystemExit(0)
f = new[-1]
lines = f.read_text(encoding="utf-8").splitlines()
n = len(lines) - 1
first = lines[1].split(",")[0] if n else "?"
last = lines[-1].split(",")[0] if n else "?"
print(f"\n{f.name}: {n:,} rows")
print(f"  first tick: {first}")
print(f"  last  tick: {last}")
# ETH present if ANY tick lands outside the RTH window [08:30,15:15) CT.
import csv as _csv
outside = 0
tod_min, tod_max = "23:59:59", "00:00:00"
with open(f, newline="") as fh:
    rd = _csv.reader(fh)
    next(rd, None)
    for row in rd:
        if not row:
            continue
        tod = row[0][11:19]
        if tod < tod_min:
            tod_min = tod
        if tod > tod_max:
            tod_max = tod
        if tod < "08:30:00" or tod >= "15:15:00":
            outside += 1
print(f"  clock span: {tod_min} .. {tod_max}   ticks OUTSIDE RTH: {outside:,}")
print("\nVERDICT: ", end="")
if outside > 1000:
    print("ETH IS RECOVERABLE — NT's .ncd holds the overnight tape "
          f"({outside:,} ticks outside 08:30-15:15). The RTH trove was just an "
          "extraction filter; widen the pipeline to capture ETH.")
else:
    print("RTH-only — NT's .ncd has no meaningful overnight ticks for this "
          "instrument. ETH cannot be recovered retroactively.")
