"""Dead-man switch, 08:32 CT: if the trigger daemon isn't running or the open
wasn't stamped, ALERT the phone. No silent mornings — ever again.

08-08 fix: the ORIGINAL was single-shot at 08:32 and cried wolf because the
daemon's FIRST fire lands ~08:33 (IB connect + first live tick after the bell) —
a reader race, not a persistence bug (the daemon saves fired=True atomically on
every status change, verified). So we now poll for a GRACE window: re-check every
15s for up to 3 min and only alarm on what is STILL wrong. A genuinely dead desk
(no daemon / no gameplan) stays wrong the whole window and still alarms; a desk
that simply fires a minute late clears before the deadline and stays quiet.
"""
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from notify_telegram import send

CT = ZoneInfo("America/Chicago")
GRACE_SECS = 180        # tolerate the observed 08:30->08:33 first-fire latency
RECHECK_SECS = 15


def check(date):
    """Return the list of problems RIGHT NOW (empty = desk is trading)."""
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
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # a mid-write read is transient — treat as "not yet", let the grace retry
            return ["gameplan unreadable (transient)"]
        if d.get("open_spot") is None:
            problems.append("open_spot NOT captured")
        if not any(t.get("fired") for t in d.get("triggers", [])):
            problems.append("ZERO triggers fired")
    return problems


def main():
    date = dt.datetime.now(CT).strftime("%Y%m%d")
    deadline = time.monotonic() + GRACE_SECS
    problems = check(date)
    while problems and time.monotonic() < deadline:
        # daemon DOWN won't self-heal in 3 min, but a short wait is harmless and lets
        # a slow-starting daemon appear; open/fire latency is exactly what we wait out.
        print(f"deadman: pending {problems} — recheck in {RECHECK_SECS}s")
        time.sleep(RECHECK_SECS)
        problems = check(date)

    if problems:
        send("🚨 DEADMAN 08:32 — DESK NOT TRADING\n"
             + "\n".join("• " + x for x in problems)
             + f"\n(still failing after {GRACE_SECS//60}min grace)"
             + "\nManual start: python scripts/options_trigger_daemon.py --until 15:00",
             level="alert")
        print("ALERT SENT:", problems)
    else:
        print("deadman OK: daemon up, open stamped, fires present")


if __name__ == "__main__":
    main()
