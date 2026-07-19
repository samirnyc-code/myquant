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
}


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
    for mod in ("session_pings", "activity_pings"):
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
