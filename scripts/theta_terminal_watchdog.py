"""Theta Terminal watchdog — keep :25503 alive (created S115 after the 9/10
mid-session terminal death silently killed all TD-dependent work).

Every run (scheduled 10-min task "MyQuant Theta Terminal Watchdog"):
  1. probe the REST port with a tiny request
  2. healthy -> log OK, exit
  3. dead -> kill any hung ThetaTerminalv3 java process, relaunch the jar
     (C:\\ThetaTerminal, key comes from the user-env THETADATA_API_KEY),
     wait for the port, Telegram-alert the outcome either way

Log: data/_catalog/logs/theta_watchdog.log (one line per action; OK probes
log nothing to keep the file readable).
"""
import datetime as dt
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import notify_telegram as TG
except Exception:
    TG = None

LOG = ROOT / "data/_catalog/logs/theta_watchdog.log"
JAR_DIR = Path(r"C:\ThetaTerminal")
PROBE = ("http://127.0.0.1:25503/v3/index/history/eod"
         "?symbol=SPX&start_date=20260102&end_date=20260102&format=csv")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}\n")


def alive(timeout=10):
    try:
        with urllib.request.urlopen(PROBE, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def kill_hung():
    # kill only java processes running the Theta jar (never the IB Gateway java)
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'java%'\" | "
          "Where-Object { $_.CommandLine -match 'ThetaTerminal' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


def main():
    if alive():
        return
    log("terminal DOWN — restarting")
    killed = kill_hung()
    if killed:
        log(f"killed hung terminal pid(s): {killed}")
        time.sleep(3)
    subprocess.Popen(
        ["java", "-jar", "ThetaTerminalv3.jar"], cwd=JAR_DIR,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
    for _ in range(18):          # up to ~90 s to auth + serve
        time.sleep(5)
        if alive(timeout=5):
            log("terminal RESTARTED ok")
            if TG:
                try:
                    TG.send("Theta Terminal restarted — watchdog found :25503 "
                            "dead and brought it back", level="warn")
                except Exception:
                    pass
            return
    log("terminal RESTART FAILED (port never came up)")
    if TG:
        try:
            TG.send("Theta Terminal DOWN — watchdog restart FAILED; "
                    "manual attention needed", level="error")
        except Exception:
            pass


if __name__ == "__main__":
    main()
