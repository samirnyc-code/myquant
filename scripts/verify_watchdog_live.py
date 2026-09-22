"""verify_watchdog_live.py — one-shot live proof that the desk watchdog + trigger
daemon actually work in-window (the 2026-09-16 hang exposed that neither was).

Polls until a target CT time (default 08:45, after the watchdog's 08:40 trigger
check has had a chance to act), then captures and writes a dated PASS/FAIL report:

  - resident watchdog wrote 'all green (daemon)' lines TODAY  (loop truly ran)
  - watchdog Live + meta-guard processes present
  - trigger daemon process present AND its heartbeat is fresh (<180s = not hung)
  - any watchdog restart ACTIONs logged today

Read-only: it changes nothing, just observes. Run in background:
  .venv/Scripts/python.exe scripts/verify_watchdog_live.py --until 08:45
"""
import argparse
import datetime as dt
import time
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
WDLOG = ROOT / "data" / "_catalog" / "logs" / "desk_watchdog.log"
OUT = ROOT / "data" / "options_sim"


def now():
    return dt.datetime.now(CT)


def age_s(p):
    p = Path(p)
    return 1e9 if not p.exists() else (dt.datetime.now() - dt.datetime.fromtimestamp(p.stat().st_mtime)).total_seconds()


def procs(pattern):
    import subprocess
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          f"Where-Object {{ $_.CommandLine -match '{pattern}' }} | "
          "Select-Object -ExpandProperty ProcessId")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=60)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="08:45", help="CT HH:MM to report at")
    a = ap.parse_args()
    target = now().replace(hour=int(a.until[:2]), minute=int(a.until[3:]), second=0, microsecond=0)

    while now() < target:
        time.sleep(120)

    today = now().date().isoformat()
    wd_lines = []
    if WDLOG.exists():
        wd_lines = [l for l in WDLOG.read_text(encoding="utf-8", errors="replace").splitlines()
                    if l.startswith(today)]
    green_daemon = [l for l in wd_lines if "all green (daemon)" in l]
    actions = [l for l in wd_lines if "ACTION" in l or "restarting" in l or "sleeping to open" in l]

    live_pids = procs("desk_watchdog.py --daemon")
    trig_pids = procs("options_trigger_daemon")
    hb_age = age_s(SIM / "trigger_daemon_heartbeat.txt")

    checks = {
        "watchdog resident loop ran today (all green daemon lines)": len(green_daemon) > 0,
        "watchdog Live process present": len(live_pids) > 0,
        "trigger daemon process present": len(trig_pids) > 0,
        "trigger daemon heartbeat fresh (<180s, not hung)": hb_age < 180,
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    lines = [f"WATCHDOG LIVE VERIFY @ {now():%Y-%m-%d %H:%M:%S} CT  ->  {verdict}", ""]
    for k, v in checks.items():
        lines.append(f"  [{'OK ' if v else 'XX '}] {k}")
    lines += ["",
              f"  watchdog green-daemon lines today: {len(green_daemon)} (first: {green_daemon[0] if green_daemon else '-'})",
              f"  watchdog Live pids: {live_pids}",
              f"  trigger daemon pids: {trig_pids}  heartbeat age: {hb_age:.0f}s",
              f"  watchdog actions today: {len(actions)}"]
    for l in actions[-8:]:
        lines.append(f"    {l}")
    report = "\n".join(lines)

    out = OUT / f"watchdog_verify_{today}.txt"
    out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
