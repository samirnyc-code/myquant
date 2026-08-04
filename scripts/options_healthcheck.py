"""Morning health-check (S75) — turn silent failures loud.

Runs ~08:40 CT (after the 08:26 feed / 08:28 gameplan / 08:33 daemon should all
be up) and verifies the autonomous chain is actually alive:
  GATEWAY  — ib_conn connects on paper 4002 (the login worked)
  FEED     — live.json is fresh (< 3 min) and state=live
  LEVELS   — mq_levels_today.json was refreshed TODAY (not stale / QUIN-dead)
  GAMEPLAN — gameplan_<today>.json exists (the plan generated)
  DAEMON   — the trigger daemon process is running

Sends ONE desktop toast (+ email if configured) summarising status — green if
all good, and a loud ⚠ list of what's broken otherwise. Also logs to the
notifications log. Never raises (a health-check that crashes helps no one).

Run:
  .venv/Scripts/python.exe scripts/options_healthcheck.py
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import notify

try:  # console is cp1252; status text uses ✓ ⚠
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")


def check_gateway():
    try:
        import ib_conn
        ib = ib_conn.connect()
        ok = ib.isConnected() and bool(ib.managedAccounts())
        acct = (ib.managedAccounts() or ["?"])[0]
        ib.disconnect()
        return ok, f"connected {acct}" if ok else "connected but no account"
    except Exception as e:
        return False, f"NO CONNECT ({type(e).__name__})"


def check_feed():
    f = SIM / "live.json"
    if not f.exists():
        return False, "live.json missing"
    try:
        d = json.loads(f.read_text())
    except Exception:
        return False, "live.json unreadable"
    if d.get("state") != "live":
        return False, f"state={d.get('state')}"
    ts = d.get("ts_et", "")
    try:
        now = dt.datetime.now(CT)
        t = now.replace(hour=int(ts[:2]), minute=int(ts[3:5]), second=int(ts[6:8]),
                        microsecond=0)
        age = (now - t).total_seconds()
        return (age < 180), f"spx {d.get('spx')} @ {ts} ({age:.0f}s old)"
    except Exception:
        return True, f"spx {d.get('spx')} @ {ts}"


def check_levels():
    """GexLog brief health (MQ removed 2026-08-04): today's gameplan must carry a
    band, and ideally a brief generated TODAY (stale brief -> computed-VIX fallback)."""
    date = dt.datetime.now(CT).strftime("%Y%m%d")
    f = SIM / f"gameplan_{date}.json"
    if not f.exists():
        return False, "no gameplan yet (brief unchecked)"
    try:
        d = json.loads(f.read_text())
    except Exception:
        return False, "gameplan unreadable"
    gx = d.get("gexlog", {}) or {}
    today_et = dt.datetime.now(dt.timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    fresh = str(gx.get("generated_at") or "").startswith(today_et)
    band = d.get("em_low") is not None and d.get("em_high") is not None
    note = "" if fresh else " (brief STALE — computed-VIX fallback)"
    return band, (f"GexLog {gx.get('signal_bucket', '?')} · EM {d.get('em_low')}–{d.get('em_high')}"
                  f" · src {str(gx.get('generated_at') or '?')[:16]}{note}")


def check_gameplan():
    date = dt.datetime.now(CT).strftime("%Y%m%d")
    f = SIM / f"gameplan_{date}.json"
    if not f.exists():
        return False, f"no gameplan_{date}.json"
    try:
        n = len(json.loads(f.read_text()).get("triggers", []))
        return n > 0, f"{n} triggers armed"
    except Exception:
        return False, "gameplan unreadable"


def check_daemon():
    try:
        import subprocess
        out = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get",
                              "commandline"], capture_output=True, text=True, timeout=10,
                             creationflags=0x08000000).stdout   # CREATE_NO_WINDOW: no wmic flash (runs every 5 min)
        running = "options_trigger_daemon" in out
        return running, "running" if running else "NOT running"
    except Exception as e:
        return True, f"could not check ({type(e).__name__})"  # don't fail on this


def main():
    checks = [("GATEWAY", check_gateway), ("FEED", check_feed), ("LEVELS", check_levels),
              ("GAMEPLAN", check_gameplan), ("DAEMON", check_daemon)]
    results = []
    for name, fn in checks:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"check errored: {type(e).__name__}"
        results.append((name, ok, detail))
        print(f"  {'OK ' if ok else 'XX '} {name:9} {detail}")

    bad = [n for n, ok, _ in results if not ok]
    if bad:
        title = "⚠ OPTIONS DESK — " + ", ".join(bad) + " DOWN"
        body = " · ".join(f"{n}: {d}" for n, ok, d in results if not ok)
    else:
        title = "✓ Options desk healthy"
        body = " · ".join(f"{n} {d}" for n, ok, d in results if n in ("FEED", "LEVELS", "GAMEPLAN"))
    notify(title, body)
    print(f"\n{title}\n{body}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
