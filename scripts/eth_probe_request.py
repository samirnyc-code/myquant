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
print("\nVERDICT: ", end="")
if first[11:16] < "08:30":
    print("ETH IS RECOVERABLE — tape starts before the 08:30 RTH open. "
          ".ncd holds the overnight session; pipeline can be widened.")
else:
    print("RTH-only — even with the ETH template the tape starts at 08:30. "
          "NT's .ncd does NOT hold overnight for this instrument (feed/subscription "
          "was RTH-only). ETH cannot be recovered retroactively.")
