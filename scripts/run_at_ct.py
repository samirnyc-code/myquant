"""run_at_ct.py — run a command only when it is really the intended CHICAGO time.

THE PROBLEM
    Every MyQuant task is scheduled in Berlin local time on the assumption Berlin = CT+7
    (15:00 Berlin = 08:00 CT). Europe and the US change DST on different dates, so for
    ~3 weeks each March and ~1 week each Oct/Nov the offset is +6 and every task fires an
    hour off. Task Scheduler reports success; the desk just starts an hour into the
    session, or the levels fetch misses the open. Silent, twice a year.

THE FIX (no sleeping, no clock change)
    Give each task TWO triggers - the +7 local time and the +6 local time, one hour apart -
    and wrap the action in this script with the intended CT time. Whichever trigger lands
    on the correct Chicago time runs the payload; the other exits 0 as a no-op.

USAGE
    python scripts/run_at_ct.py --at 08:27 -- python scripts\\mq_levels_fetch.py
    python scripts/run_at_ct.py --at 08:00 --window 25 -- cmd /c C:\\IBC\\StartGateway.bat

    --at      intended time in America/Chicago, HH:MM
    --window  minutes either side that count as "on time" (default 25; must be < 30 so the
              two candidate triggers can never both match)
    --check   print the decision and exit, run nothing

EXIT CODES
    payload's own exit code when it runs; 0 when it correctly no-ops; 2 on bad arguments.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys


def chicago_now() -> dt.datetime:
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/Chicago"))


def offset_hours() -> float:
    """Current Berlin - Chicago offset. 7 normally, 6 during the DST mismatch windows."""
    from zoneinfo import ZoneInfo
    now = dt.datetime.now(dt.timezone.utc)
    ber = now.astimezone(ZoneInfo("Europe/Berlin")).utcoffset()
    chi = now.astimezone(ZoneInfo("America/Chicago")).utcoffset()
    return (ber - chi).total_seconds() / 3600


def minutes_from(target: str, now: dt.datetime) -> float:
    """Signed minutes between now (CT) and today's target time, wrapping across midnight."""
    hh, mm = (int(x) for x in target.split(":"))
    tgt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    d = (now - tgt).total_seconds() / 60
    if d > 720:
        d -= 1440
    elif d < -720:
        d += 1440
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, help="intended America/Chicago time, HH:MM")
    ap.add_argument("--window", type=float, default=25.0, help="tolerance in minutes (<30)")
    ap.add_argument("--check", action="store_true", help="report the decision, run nothing")
    a, rest = ap.parse_known_args()

    if a.window >= 30:
        print("run_at_ct: --window must be < 30 so only ONE trigger can match", file=sys.stderr)
        sys.exit(2)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest and not a.check:
        print("run_at_ct: no command given (put it after --)", file=sys.stderr)
        sys.exit(2)

    now = chicago_now()
    delta = minutes_from(a.at, now)
    on_time = abs(delta) <= a.window
    off = offset_hours()

    stamp = (f"run_at_ct: target {a.at} CT | now {now:%H:%M} CT | "
             f"delta {delta:+.0f}min | berlin-chicago {off:.0f}h")

    if a.check:
        print(f"{stamp} | would {'RUN' if on_time else 'skip'}")
        sys.exit(0)

    if not on_time:
        print(f"{stamp} | SKIP (other trigger owns this slot)")
        sys.exit(0)

    if off != 7:
        print(f"{stamp} | NOTE: DST mismatch window active (offset {off:.0f}h, normally 7h)")
    print(f"{stamp} | RUN: {' '.join(rest)}")
    # CREATE_NO_WINDOW: the wrapped child must NOT pop a console. Without this, every
    # run_at_ct-wrapped scheduled task flashed a python.exe window when it launched its
    # real command (2026-07-21 - user watching consoles strobe every few minutes).
    sys.exit(subprocess.run(rest, creationflags=0x08000000).returncode)


if __name__ == "__main__":
    main()
