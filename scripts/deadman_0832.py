"""Dead-man switch, 08:32 CT: if the trigger daemon isn't running or the open
wasn't stamped, ALERT the phone. No silent mornings — ever again."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from notify_telegram import send

CT = ZoneInfo("America/Chicago")
date = dt.datetime.now(CT).strftime("%Y%m%d")
problems = []

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -match 'trigger_daemon' }).Count"],
                   capture_output=True, text=True)
if not (r.stdout.strip() and int(r.stdout.strip() or 0) > 0):
    problems.append("trigger daemon NOT RUNNING")

p = ROOT / "data" / "options_sim" / f"gameplan_{date}.json"
if not p.exists():
    problems.append(f"no gameplan_{date}.json")
else:
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("open_spot") is None:
        problems.append("open_spot NOT captured")
    if not any(t.get("fired") for t in d.get("triggers", [])):
        problems.append("ZERO triggers fired")

if problems:
    send("🚨 DEADMAN 08:32 — DESK NOT TRADING\n" + "\n".join("• " + x for x in problems)
         + "\nManual start: python scripts/options_trigger_daemon.py --until 15:00",
         level="alert")
    print("ALERT SENT:", problems)
else:
    print("deadman OK: daemon up, open stamped, fires present")
