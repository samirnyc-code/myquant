"""dashboard_keepalive.py — keep the options desk dashboard (port 8600) alive.

options_dashboard_live.py is NOT supervised (the Desk Watchdog does not cover it) — it
died once overnight and stayed dead, breaking remote Tailscale access. Scheduled every
~10 min, this relaunches it ONLY when port 8600 is not listening. It NEVER kills or
touches a running dashboard, and options_dashboard_live self-guards against a double
bind, so this is safe to run alongside everything. Quiet on the happy path (no log spam);
logs only when it actually has to relaunch.

Run: .venv/Scripts/pythonw.exe scripts/dashboard_keepalive.py
"""
from __future__ import annotations
import datetime as dt
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8600
PY = ROOT / ".venv" / "Scripts" / "pythonw.exe"
SCRIPT = ROOT / "scripts" / "options_dashboard_live.py"
LOG = ROOT / "data" / "_catalog" / "logs" / "dashboard_keepalive.log"


def port_up(port):
    s = socket.socket()
    s.settimeout(2)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}\n")


def main():
    if port_up(PORT):
        return 0  # already up — no-op, stay quiet
    log(f"port {PORT} DOWN — relaunching options_dashboard_live")
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    try:
        subprocess.Popen([str(PY), str(SCRIPT), "--host", "0.0.0.0", "--port", str(PORT)],
                         cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True)
        log("relaunch issued")
    except Exception as e:
        log(f"relaunch FAILED: {e!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
