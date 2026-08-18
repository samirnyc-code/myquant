"""singleton.py — one instance per daemon. Stops the duplicate pile-ups that starve
each other of IB market-data lines and silently lose data (5 markers, 10 recorders).

Call `ensure("<name>")` at the very top of a daemon's main(). If a LIVE process whose
command line contains <name> already holds the lock, this one prints and exit(0)s.
Stale locks (dead PID, or PID reused by an unrelated process) are taken over — the
cmdline check prevents a reused PID from wedging the lock forever.
"""
from __future__ import annotations
import atexit
import os
import sys
from pathlib import Path

LOCKDIR = Path(__file__).resolve().parents[1] / "data" / "_catalog" / "locks"


def _holder_is_live(name: str, pid: int) -> bool:
    """True only if `pid` is alive AND it's actually a <name> daemon (not a reused PID)."""
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        cl = " ".join(psutil.Process(pid).cmdline() or [])
        return name in cl
    except Exception:
        return False


def ensure(name: str) -> None:
    LOCKDIR.mkdir(parents=True, exist_ok=True)
    lock = LOCKDIR / f"{name}.pid"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip())
        except (ValueError, OSError):
            pid = -1
        if pid != os.getpid() and _holder_is_live(name, pid):
            print(f"singleton: {name} already running (pid {pid}) — exiting")
            sys.exit(0)
    # take (or reclaim a stale) lock; drop it on clean exit
    lock.write_text(str(os.getpid()))
    atexit.register(lambda: lock.unlink(missing_ok=True)
                    if lock.exists() and lock.read_text().strip() == str(os.getpid()) else None)
