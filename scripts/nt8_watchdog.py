"""nt8_watchdog.py — keep the unattended L2 recording alive across NT8 crashes.

2026-07-21: NT8's SuperDOM GUI threw a NullReferenceException at 22:29 CT, jammed the
platform's realtime data pump, and recording sat DEAD for 55 minutes until the user
happened to wake and restart it by hand. Nothing paged, nothing recovered. For a
two-week unattended run that is unacceptable — this closes the hole.

Runs every few minutes (scheduled, pythonw = no console). Logic, in order of safety:

  depth flowing            -> do nothing.
  market shut              -> do nothing (nothing should be recording).
  depth STALLED, open:
     PAGE once (deduped).
     NT process DEAD           -> relaunch (nothing to lose) -> verify -> page result.
     NT alive but JAMMED:
        overnight (unattended) -> CLEAN restart (save-first) -> verify -> page.
        desk hours (you may be
        drawing on a chart)    -> PAGE ONLY. Never auto-restart and risk your workspace;
                                  you decide. This is the deliberate safety line.

The restart itself is nt8_maintenance.restart() (120s graceful, workspace-saving, never
blind force-kills) + verify() (confirms the recorder re-armed and pages if not).

    python scripts/nt8_watchdog.py            # one pass
    python scripts/nt8_watchdog.py --stale 8  # stall threshold minutes (default 8)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _ping(text, level="info", dedup=None, cooldown=0):
    try:
        import notify_telegram as tg
        tg.send(text, level=level, dedup_key=dedup, cooldown_s=cooldown)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale", type=float, default=8.0, help="stall minutes before acting")
    a = ap.parse_args()

    import pipeline_health as ph
    import nt8_maintenance as ntm

    now = ph.chicago_now()
    mkt = ph.market_state(now)
    if mkt != "open":
        print(f"{now:%H:%M} market {mkt} - nothing should be recording, standing by")
        return 0

    depth = ph.check_depth()
    # check_depth already knows the session-template filenames and the book/tape mix.
    # It is BAD only when the market is open and nothing is arriving - exactly our trigger.
    if depth["state"] != ph.BAD:
        print(f"{now:%H:%M} depth OK ({depth['detail']})")
        return 0

    # ---- depth is stalled while the market is open: recording is DOWN ----
    running = ntm.nt8_running()
    desk = ph._desk_hours()          # True during 08:00-15:15 CT weekday = you may be active
    _ping(f"🔴 L2 RECORDING DOWN — {depth['detail']}. NT8 {'running (jammed)' if running else 'NOT running'}.",
          level="alert", dedup="rec_down", cooldown=1800)
    print(f"{now:%H:%M} DEPTH STALLED - NT running={running} desk_hours={desk}")

    # THE RULE THAT KILLS THE POPUP (2026-08-12): NEVER auto-CLOSE a running NT8.
    # Closing it triggers the "Save workspace?" dialog, which cannot be reliably
    # auto-answered — so the close hangs, the restart aborts, and the popup lands on
    # the user (the whole 08-11/08-12 flood). We ONLY ever RELAUNCH NT when it is
    # already DOWN — that path closes nothing, shows no popup, and the AddOn L2
    # recorder resumes on its own once the feed reconnects.
    if running:
        # up but recording stalled (jammed): page once, do NOT touch it. The user
        # restarts manually when ready; recording comes back by itself on relaunch.
        _ping("⚠️ NT8 is up but recording is STALLED. NOT auto-restarting — restart NT "
              "yourself when ready (the L2 recorder resumes on its own on relaunch).",
              level="alert", dedup="jam", cooldown=1800)
        print("  NT running but stalled -> page only, NEVER auto-close (popup-safe)")
        return 1

    # NT is DOWN (crashed/closed): safe to relaunch — nothing to close, no popup.
    _ping("🔧 NT8 is down — relaunching to resume recording…", level="info",
          dedup="auto_relaunch", cooldown=600)
    print("  NT down -> relaunch (no close dialog, no popup)")
    ok = ntm.restart(force_ok=False)     # NT not running, so restart() skips the close, just relaunches
    if not ok:
        _ping("🔴 NT8 relaunch could NOT bring it back. Needs a human.", level="alert")
        return 1
    armed = ntm.verify(wait_s=90)
    if not armed:
        _ping("🔴 NT8 relaunched but the recorder is NOT recording — enable MarketDepthRecorder "
              "in Control Center. (Auto-enable is not yet trusted.)", level="alert",
              dedup="not_armed", cooldown=1800)
    return 0 if armed else 1


if __name__ == "__main__":
    sys.exit(main())
