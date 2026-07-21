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

    if running and desk:
        # jammed during the session — do NOT auto-restart, it could wipe chart drawings
        # you are actively working on. You decide.
        _ping("⚠️ NT8 is up but recording is stalled during DESK HOURS. Not auto-restarting "
              "(it could lose chart drawings). Restart it yourself when ready, or run "
              "nt8_maintenance.py.", level="alert", dedup="jam_desk", cooldown=1800)
        print("  jammed during desk hours -> page only, no auto-restart (protect drawings)")
        return 1

    # safe to act: NT is dead (nothing to lose), OR jammed overnight (no one is drawing)
    why = "NT8 crashed/closed" if not running else "NT8 jammed overnight"
    _ping(f"🔧 {why} — auto-restarting to resume recording…", level="info",
          dedup="auto_restart", cooldown=600)
    print(f"  {why} -> auto-restart")
    ok = ntm.restart(force_ok=False)     # 120s graceful, workspace-saving, no blind kill
    if not ok:
        _ping("🔴 Auto-restart could NOT bring NT8 back cleanly. Needs a human.", level="alert")
        return 1
    # verify() watches the depth file grow AND checks the recorder is armed, and pages.
    armed = ntm.verify(wait_s=90)
    if not armed:
        _ping("🔴 NT8 restarted but the MarketDepthRecorder is NOT recording — enable it in "
              "Control Center → Strategies. (Auto-enable is not yet trusted.)", level="alert",
              dedup="not_armed", cooldown=1800)
    return 0 if armed else 1


if __name__ == "__main__":
    sys.exit(main())
