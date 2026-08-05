"""Poll gexlog until TODAY's morning brief appears, then build the official gameplan."""
import sys, time, subprocess, datetime as dt
sys.path.insert(0, "scripts")
from gexlog_brief import fetch

for i in range(120):                      # up to ~60 min
    g = fetch()
    ga = str(g.get("generated_at") or "")
    print(f"[{dt.datetime.now():%H:%M:%S}] brief generated_at = {ga}", flush=True)
    if ga.startswith("2026-08-04"):
        print("TODAY'S BRIEF IS LIVE — building the official gameplan", flush=True)
        r = subprocess.run([sys.executable, "scripts/options_gameplan.py"],
                           capture_output=True, text=True, cwd=".")
        print(r.stdout[-1500:], r.stderr[-500:], flush=True)
        break
    time.sleep(30)
else:
    print("brief never flipped to 2026-08-04 — scheduled 07:28 CT run will handle it", flush=True)
