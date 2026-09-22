"""l1_recorder_watchdog.py — page if the L1 tape recorder stops while the market is open.

Runs every ~10 min (scheduled, pythonw = no console). Deliberately PAGE-ONLY: it never
closes or restarts NinjaTrader. Two reasons —
  1. L1TapeRecorderAddOn self-heals a SILENT stall on its own (unsubscribe→resubscribe every
     StallResubSecs), so most jams recover with no external action.
  2. Auto-closing NT triggers the "Save workspace?" popup that cannot be reliably answered
     unattended (the 2026-08 flapping). NEVER auto-close a running NT (see nt8_watchdog).
So this alerts a human and gets out of the way; recovery is the AddOn's job (or a manual
NT relaunch, after which the AddOn resumes by itself).

    python scripts/l1_recorder_watchdog.py            # one pass
    python scripts/l1_recorder_watchdog.py --stale 6  # not used directly; check_l1_tape owns the threshold
"""
from __future__ import annotations

import argparse
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
    ap.add_argument("--stale", type=float, default=None, help="unused; check_l1_tape owns the freshness rule")
    ap.parse_args()

    import pipeline_health as ph

    now = ph.chicago_now()
    mkt = ph.market_state(now)
    if mkt != "open":
        print(f"{now:%H:%M} market {mkt} - nothing should be recording, standing by")
        return 0

    r = ph.check_l1_tape()
    state, detail = r["state"], r["detail"]

    # IDLE 'not started' means the AddOn has never written — pre-F5 or NT down. Page softly:
    # during an open market the recorder SHOULD be writing.
    if state == ph.IDLE and "not started" in detail:
        try:
            import nt8_maintenance as ntm
            running = ntm.nt8_running()
        except Exception:
            running = None
        _ping(f"⚪ L1 recorder not started while market OPEN ({detail}). "
              f"NT8 {'running — F5/enable the AddOn' if running else 'appears DOWN — relaunch NT'}.",
              level="alert", dedup="l1_not_started", cooldown=3600)
        print(f"{now:%H:%M} L1 not started (NT running={running})")
        return 1

    if state != ph.BAD:
        print(f"{now:%H:%M} L1 tape OK ({detail})")
        return 0

    # ---- L1 recording is DOWN while the market is open ----
    try:
        import nt8_maintenance as ntm
        running = ntm.nt8_running()
    except Exception:
        running = None
    tail = f" quote={r.get('quote')} tape={r.get('tape')}" if "quote" in r else ""
    _ping(f"🔴 L1 TAPE RECORDING DOWN — {detail}.{tail} "
          f"NT8 {'running (jammed — AddOn should self-heal; restart NT if it persists)' if running else 'NOT running — relaunch NT'}.",
          level="alert", dedup="l1_down", cooldown=1800)
    print(f"{now:%H:%M} L1 STALLED - {detail} (NT running={running}) -> paged, page-only by design")
    return 1


if __name__ == "__main__":
    sys.exit(main())
