"""Gateway readiness watchdog (S103) — kill the cold-auth-hang failure mode.

WHY THIS EXISTS (2026-08-10 incident):
  Monday's IB Gateway login was a *full cold authentication* (the "autorestart"
  token had expired over the weekend -> "autorestart file not found: full
  authentication will be required"). That cold auth HUNG on IB's side for ~85
  minutes (07:30 -> 08:56 CT), so the API port / market data was dead straight
  through the 08:30 open. The 08:29 trigger daemon connected into that dead
  gateway, ib_conn.connect() raised (it only retries ONCE), and the daemon died
  having fired nothing. Every premium-selling setup was missed.

WHAT THIS DOES:
  Runs in the pre-open window and verifies TRUE readiness — not just "port 4002
  is listening" (the old gateway_ensure check, which a stuck cold-auth passes
  falsely) but "the API answers AND the account is authenticated (managed
  accounts present, paper DU...)". If the gateway is NOT truly ready and has
  been stuck longer than STUCK_GRACE, it FORCE-RESTARTS the gateway (kills the
  IB java + the IBC launcher, relaunches StartGateway.bat) and alerts. A fresh
  login almost always clears a hung one; with an early start there is time for
  several attempts before the open.

  SAFE BY CONSTRUCTION: it only ever kills/relaunches inside the pre-open
  WINDOW and only while NOT ready. The instant it sees a ready+authenticated
  gateway it stops touching anything and exits 0. It never acts during RTH, so
  it cannot kill a live session mid-trade.

MODES:
  (default)  resident loop over the window, cadence POLL_S. Exits 0 the moment
             the gateway is ready, or when the window ends. Task "MyQuant
             Gateway Watchdog" starts it early (see schedule_gateway_login.ps1).
  --once     single readiness check (+ one restart if stuck); for a 5-min
             Task-Scheduler cadence instead of a resident loop.
  --check    read-only: print readiness verdict, touch nothing, exit 0/1.

Run:
  .venv/Scripts/python.exe scripts/gateway_watchdog.py --check
  .venv/Scripts/python.exe scripts/gateway_watchdog.py            # resident
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import notify

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CT = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "_catalog" / "gateway_watchdog_state.json"
LOG = ROOT / "data" / "_catalog" / "logs" / "gateway_watchdog.log"
STARTGATEWAY = r"C:\IBC\StartGateway.bat"

# --- tunables ---
WINDOW = ("05:30", "08:25")   # CT; only ever acts inside this pre-open window
POLL_S = 60                   # readiness re-check cadence in resident mode
STUCK_GRACE_S = 8 * 60        # a healthy cold-auth finishes in ~1-2 min; >8 stuck = restart
COOLDOWN_S = 12 * 60          # min seconds between force-restarts (anti-flap)
DAILY_CAP = 6                 # max force-restarts per day
NO_WINDOW = 0x08000000        # CREATE_NO_WINDOW — no console flash


def now():
    return dt.datetime.now(CT)


def hhmm(s):
    h, m = map(int, s.split(":"))
    return now().replace(hour=h, minute=m, second=0, microsecond=0)


def in_window():
    return hhmm(WINDOW[0]) <= now() < hhmm(WINDOW[1])


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now():%Y-%m-%d %H:%M:%S CT} {msg}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line)


def load_state():
    try:
        d = json.loads(STATE.read_text())
    except Exception:
        d = {}
    if d.get("day") != now().strftime("%Y-%m-%d"):
        d = {"day": now().strftime("%Y-%m-%d"), "restarts": 0, "last_restart": 0.0,
             "stuck_since": 0.0}
    return d


def save_state(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=2))


def gateway_ready():
    """TRUE readiness: the API answers AND the account is authenticated.

    Returns (ready: bool, detail: str). A stuck cold-auth typically has the port
    down OR up-but-no-managedAccounts — both fail here, unlike a bare port probe.
    """
    try:
        import ib_conn
        ib = ib_conn.connect(timeout=8)           # raises unless truly logged in (paper DU…)
        accts = ib.managedAccounts()
        ib.disconnect()
        if accts:
            return True, f"authenticated {accts[0]}"
        return False, "port up but NO managed accounts (auth not complete)"
    except SystemExit as e:
        return False, f"refused: {e}"
    except Exception as e:
        return False, f"no connect ({type(e).__name__})"


def java_pids():
    """PIDs of the IB Gateway JVM (java.exe). On this box java == IB Gateway."""
    ps = ("Get-Process -Name java -ErrorAction SilentlyContinue | "
          "Select-Object -ExpandProperty Id")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def launcher_pids():
    """PIDs of lingering StartGateway / IBC launcher processes (cmd + run_at_ct)."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
          "'StartGateway|IBC.jar|ibgateway' } | Select-Object -ExpandProperty ProcessId")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def kill_pids(pids):
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, creationflags=NO_WINDOW)


def port_open(port=4002, host="127.0.0.1"):
    import socket
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def gateway_down():
    """Fully down: no JVM AND the API port is closed (vs up-but-not-authenticated)."""
    return not java_pids() and not port_open()


def relaunch_gateway():
    # StartGateway.bat self-guards against a second launch if 4002 already listens.
    subprocess.Popen(["cmd", "/c", STARTGATEWAY, "/INLINE"], creationflags=NO_WINDOW)


def force_restart(st, reason):
    """Kill the hung gateway + IBC launcher and relaunch. Anti-flap guarded."""
    if st["restarts"] >= DAILY_CAP:
        log(f"NOT restarting — daily cap {DAILY_CAP} hit ({reason})")
        return False
    if time.time() - st["last_restart"] < COOLDOWN_S:
        return False
    jp, lp = java_pids(), launcher_pids()
    log(f"FORCE-RESTART gateway [{reason}] — killing java={jp} launcher={lp}")
    kill_pids(jp + lp)
    time.sleep(3)
    relaunch_gateway()
    st["restarts"] += 1
    st["last_restart"] = time.time()
    st["stuck_since"] = 0.0
    save_state(st)
    notify("⚠ Gateway force-restarted",
           f"cold-auth hang cleared ({reason}); relaunched, attempt "
           f"{st['restarts']}/{DAILY_CAP}. {WINDOW[0]}-{WINDOW[1]} CT pre-open watchdog.")
    return True


def evaluate_and_act(st):
    """One readiness evaluation; force-restart if stuck past grace. Returns ready bool."""
    ready, detail = gateway_ready()
    if ready:
        if st.get("stuck_since"):
            log(f"gateway READY — {detail} (was stuck)")
        st["stuck_since"] = 0.0
        save_state(st)
        return True
    # not ready. If it is FULLY down (no JVM, port closed), just launch it — a
    # clean start, no kill, no grace wait (this is also the early-start path at
    # the top of the window, before/independent of the Gateway Login task).
    if gateway_down():
        if time.time() - st.get("last_restart", 0) >= COOLDOWN_S and st["restarts"] < DAILY_CAP:
            log(f"gateway DOWN — launching StartGateway.bat ({detail})")
            relaunch_gateway()
            st["restarts"] += 1
            st["last_restart"] = time.time()
        st["stuck_since"] = time.time()
        save_state(st)
        return False
    # up but NOT authenticated — track how long, force-restart if past grace
    if not st.get("stuck_since"):
        st["stuck_since"] = time.time()
        save_state(st)
        log(f"gateway NOT ready — {detail} (grace {STUCK_GRACE_S//60}min before restart)")
        return False
    stuck_for = time.time() - st["stuck_since"]
    if stuck_for >= STUCK_GRACE_S:
        force_restart(st, f"{detail}, stuck {stuck_for/60:.0f}min")
    else:
        log(f"gateway NOT ready — {detail} (stuck {stuck_for/60:.0f}min)")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single check+act (for 5-min scheduler)")
    ap.add_argument("--check", action="store_true", help="read-only readiness verdict; act on nothing")
    a = ap.parse_args()

    if a.check:
        ready, detail = gateway_ready()
        print(f"gateway {'READY' if ready else 'NOT READY'} — {detail}")
        return 0 if ready else 1

    if not in_window() and not a.once:
        print(f"outside pre-open window {WINDOW[0]}-{WINDOW[1]} CT — nothing to do")
        return 0

    st = load_state()

    if a.once:
        return 0 if evaluate_and_act(st) else 1

    log(f"gateway watchdog up — window {WINDOW[0]}-{WINDOW[1]} CT, poll {POLL_S}s")
    while in_window():
        if evaluate_and_act(st):
            log("gateway ready — watchdog standing down (exit 0)")
            return 0
        time.sleep(POLL_S)
    log("window ended — gateway still not confirmed ready" if not gateway_ready()[0]
        else "window ended — gateway ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
