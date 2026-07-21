"""alert_monitor.py — decide what is worth waking the user for, and page it via Telegram.

Runs pipeline_health, and pushes ONLY the conditions that need a human overnight:

  * depth TAPE ONLY / stalled   — the one dataset that cannot be re-collected
  * NT8 down while market open   — nothing is recording
  * disk critical               — recording will fail soon
  * recorder on the wrong contract

Everything else (weekend idle, a stale weekday task, footprint quirks) is visible on the
board but must NEVER page — an alarm that cries wolf is one you learn to ignore.

Each condition pages ONCE (1h cooldown) and sends a RECOVERY ping when it clears, so the
phone reflects state changes, not a running commentary.

    python scripts/alert_monitor.py            # one pass
    python scripts/alert_monitor.py --loop 300 # check every 5 min (foreground)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# (dedup_key, predicate(check) -> bool, message builder) per health check name.
# predicate True == PROBLEM worth paging.
RULES = {
    "L2 depth": (
        "depth",
        lambda c: c["state"] == "bad",
        lambda c: f"L2 DEPTH: {c['detail']}",
    ),
    "NinjaTrader": (
        "nt8",
        lambda c: c["state"] == "bad",
        lambda c: f"NINJATRADER: {c['detail']}",
    ),
    "Contract": (
        "contract",
        lambda c: c["state"] == "bad",
        lambda c: f"WRONG CONTRACT: {c['detail']}",
    ),
    "Disk": (
        "disk",
        lambda c: c["state"] == "bad",
        lambda c: f"DISK: {c['detail']}",
    ),
    "IB gateway": (
        "gateway",
        lambda c: c["state"] == "bad",     # WARN on gateway is normal off-hours; only BAD pages
        lambda c: f"IB GATEWAY: {c['detail']}",
    ),
    # 2026-07-20: sim daemon died at the 08:28 launch and nothing paged. BAD here means
    # desk hours + market open + (no gameplan after 08:35 CT, or feed dead >10 min).
    "Options sim": (
        "options_sim",
        lambda c: c["state"] == "bad",
        lambda c: f"OPTIONS DESK: {c['detail']}",
    ),
    # 2026-07-20: dashboard crashed on a bad trade record and stayed dead all session.
    "Options dashboard": (
        "options_dashboard",
        lambda c: c["state"] == "warn",     # WARN only fires during desk hours
        lambda c: f"OPTIONS DASHBOARD: {c['detail']}",
    ),
}


def _heal_options_sim(c, tg, verbose: bool) -> None:
    """Self-heal a dead desk instead of only paging about it (2026-07-20: daemon failed
    at 08:28 launch, sat dead until manually restarted). Direct invocation, NOT
    Start-ScheduledTask - the run_at_ct wrapper would skip outside its 25-min window,
    which is exactly when a heal is needed. At most one attempt per 30 min so a genuinely
    broken script cannot be relaunch-spammed; if the cause persists (e.g. truly stale
    levels) the BAD page keeps firing and the human decides."""
    import subprocess
    py = str(ROOT / ".venv" / "Scripts" / "python.exe")
    if not tg.send("🔧 attempting desk self-heal (gameplan + sim daemon)…", level="info",
                   dedup_key="desk_heal", cooldown_s=1800):
        return                                  # healed too recently - let the page stand
    if "NO GAMEPLAN" in c["detail"]:
        r = subprocess.run([py, str(ROOT / "scripts" / "options_gameplan.py")],
                           capture_output=True, text=True, timeout=180,
                           cwd=str(ROOT), creationflags=0x08000000)
        tg.send("✅ self-heal: gameplan rebuilt" if r.returncode == 0 else
                f"❌ self-heal: gameplan still failing:\n{(r.stderr or r.stdout)[-400:]}",
                level="info" if r.returncode == 0 else "alert")
        if r.returncode != 0:
            return                              # no point starting the daemon on no plan
    # restart the daemon detached (DETACHED_PROCESS|CREATE_NO_WINDOW) - it exits by
    # itself if another instance already holds the lock, so double-start is safe
    subprocess.Popen([py, str(ROOT / "scripts" / "options_sim_daemon.py")],
                     cwd=str(ROOT), creationflags=0x08000008,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if verbose:
        print("self-heal: daemon relaunched")


def _heal_dashboard(tg, verbose: bool) -> None:
    """Relaunch the options dashboard server if its port died (throttled 30 min)."""
    import subprocess
    if not tg.send("🔧 relaunching options dashboard (:8600)…", level="info",
                   dedup_key="dash_heal", cooldown_s=1800):
        return
    pyw = str(ROOT / ".venv" / "Scripts" / "pythonw.exe")
    subprocess.Popen([pyw, str(ROOT / "scripts" / "options_dashboard_live.py"),
                      "--host", "0.0.0.0", "--port", "8600"],
                     cwd=str(ROOT), creationflags=0x08000008,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if verbose:
        print("dashboard relaunched")


def run_once(verbose: bool = False) -> int:
    import pipeline_health as ph
    import notify_telegram as tg

    if not tg._load().get("token"):
        if verbose:
            print("telegram not configured — run notify_telegram.py --setup first")
        return 2

    h = ph.health()
    by = {c["name"]: c for c in h["checks"]}
    paged = 0
    for name, (key, is_problem, msg) in RULES.items():
        c = by.get(name)
        if not c:
            continue
        if is_problem(c):
            if tg.send(msg(c), level="alert", dedup_key=key, cooldown_s=3600):
                paged += 1
                if verbose:
                    print(f"PAGED [{key}]: {msg(c)}")
            if key == "options_sim":
                try:
                    _heal_options_sim(c, tg, verbose)
                except Exception as e:
                    if verbose:
                        print(f"self-heal error: {type(e).__name__}: {e}")
            if key == "options_dashboard":
                try:
                    _heal_dashboard(tg, verbose)
                except Exception as e:
                    if verbose:
                        print(f"dashboard heal error: {type(e).__name__}: {e}")
        else:
            # condition healthy -> if we had paged it, announce recovery once
            import json
            try:
                sent = json.loads(tg.SENT.read_text()) if tg.SENT.exists() else {}
            except Exception:
                sent = {}
            if key in sent:
                tg.clear_dedup(key)
                tg.send(f"recovered: {name} — {c['detail']}", level="ok")
                if verbose:
                    print(f"RECOVERED [{key}]")
    # positive session-milestone pings (open, first readings, ...) - additive, never noise
    for mod in ("session_pings", "activity_pings", "cool_pings"):
        try:
            __import__(mod).main()
        except Exception as e:
            if verbose:
                print(f"{mod} error: {type(e).__name__}: {e}")

    if verbose and not paged:
        print(f"all clear (overall={h['overall']}, market={h['market']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, metavar="SEC", help="repeat every SEC seconds")
    a = ap.parse_args()
    if not a.loop:
        return run_once(verbose=True)
    print(f"alert monitor: every {a.loop}s")
    while True:
        try:
            run_once(verbose=True)
        except Exception as e:
            print(f"monitor error: {type(e).__name__}: {e}")
        time.sleep(a.loop)


if __name__ == "__main__":
    sys.exit(main())
