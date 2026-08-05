"""Poll for TODAY's GexLog morning brief: start 07:15 CT, every 15 min, stop when
found (rebuild the gameplan from it) or at 08:25 CT (scheduled build takes over)."""
import sys, time, subprocess, datetime as dt
from zoneinfo import ZoneInfo
sys.path.insert(0, "scripts")
from gexlog_brief import fetch

CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")

def now_ct():
    return dt.datetime.now(CT)

# wait until 07:15 CT
first = now_ct().replace(hour=7, minute=15, second=0, microsecond=0)
if now_ct() < first:
    wait = (first - now_ct()).total_seconds()
    print(f"[{now_ct():%H:%M:%S CT}] waiting {wait/60:.0f}min until 07:15 CT", flush=True)
    time.sleep(wait)

deadline = now_ct().replace(hour=8, minute=25, second=0, microsecond=0)
while now_ct() < deadline:
    today_et = dt.datetime.now(ET).strftime("%Y-%m-%d")
    g = fetch()
    ga = str(g.get("generated_at") or "")
    print(f"[{now_ct():%H:%M:%S CT}] brief generated_at = {ga or '(none)'}", flush=True)
    if ga.startswith(today_et):
        print("TODAY'S BRIEF FOUND — rebuilding the gameplan from it", flush=True)
        r = subprocess.run([sys.executable, "scripts/options_gameplan.py", "--force"],
                           capture_output=True, text=True, cwd=".")
        print(r.stdout[-2000:], flush=True)
        if r.returncode != 0:
            print("REBUILD FAILED:", r.stderr[-500:], flush=True)
        break
    time.sleep(15 * 60)
else:
    print("08:25 CT reached without a fresh brief — scheduled 08:28 build (staleness guard) takes over.", flush=True)
