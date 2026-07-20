"""smoke_test.py — run the automated processes that CAN be tested and report what breaks.

Not everything is testable on demand: the session-phase jobs (spot feed, marks, sim daemon,
trigger daemon, levels engine) need live quotes and prove nothing with the market shut. This
runs the rest — the ones that only need an API, a file or the IB API port — so a failure is
found deliberately rather than at 08:28 on a Monday.

    python scripts/smoke_test.py               # safe set (default)
    python scripts/smoke_test.py --all         # include the slow archive jobs
    python scripts/smoke_test.py --only levels_fetch,gamma_scanner
    python scripts/smoke_test.py --list

Each check runs the REAL script with a timeout and reports exit code + last output line.
Nothing here places an order or restarts Gateway.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
NOWIN = 0x08000000

# id, label, argv, timeout_s, slow
CHECKS = [
    ("gateway_ensure", "Gateway ensure (API 4002)",
     [PY, "scripts/gateway_ensure.py"], 90, False),
    ("levels_fetch", "MenthorQ levels fetch",
     [PY, "scripts/mq_levels_fetch.py"], 120, False),
    ("gamma_scanner", "Cross-symbol gamma scanner",
     [PY, "scripts/options_gamma_scanner.py"], 180, False),
    ("gameplan", "Premarket gameplan",
     [PY, "scripts/options_gameplan.py"], 120, False),
    ("healthcheck", "Morning health check",
     [PY, "scripts/options_healthcheck.py"], 120, False),
    ("postmortem", "Daily postmortem",
     [PY, "scripts/options_postmortem.py"], 120, False),
    ("eod_report", "EOD desk report",
     [PY, "scripts/eod_report.py"], 150, False),
    ("catalog_scan", "Data catalog scan",
     [PY, "scripts/data_catalog.py", "scan"], 300, False),
    ("levels_history", "Levels history backfill",
     [PY, "scripts/mq_levels_backfill_batch.py", "--recent", "3"], 300, False),
    # --- slow archive jobs: real API load, only with --all ---
    ("levels_db", "Levels DB + viewer",
     [PY, "scripts/mq_levels_db.py"], 900, True),
    ("mq_mine", "MenthorQ full-surface mine",
     [PY, "scripts/mq_mine.py"], 1800, True),
    ("mq_harvest", "MenthorQ dashboard harvest (Playwright)",
     [PY, "scripts/mq_harvest.py"], 1800, True),
]


def run(argv, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout, creationflags=NOWIN)
        out = (p.stdout or "") + (p.stderr or "")
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return p.returncode, (lines[-1][:110] if lines else ""), time.time() - t0
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {timeout}s", time.time() - t0
    except Exception as e:
        return -2, f"{type(e).__name__}: {e}", time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include slow archive jobs")
    ap.add_argument("--only", default="", help="comma-separated ids")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for cid, label, _, t, slow in CHECKS:
            print(f"  {cid:<16} {'[slow] ' if slow else '       '}{label}  (timeout {t}s)")
        return 0

    sel = [c for c in CHECKS if (a.all or not c[4])]
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        sel = [c for c in CHECKS if c[0] in want]

    print(f"\nsmoke test — {len(sel)} process(es)\n" + "=" * 66)
    results = []
    for cid, label, argv, timeout, _ in sel:
        print(f"  running {label} …", flush=True)
        rc, tail, secs = run(argv, timeout)
        ok = rc == 0
        results.append((cid, label, rc, tail, secs, ok))
        print(f"    [{'PASS' if ok else 'FAIL'}] rc={rc}  {secs:.0f}s  {tail}")

    print("\n" + "=" * 66)
    bad = [r for r in results if not r[5]]
    for cid, label, rc, tail, secs, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<38} rc={rc:<4} {secs:5.0f}s")
    print(f"\n{len(results)-len(bad)}/{len(results)} passed")
    if bad:
        print("\nfailing:")
        for cid, label, rc, tail, secs, ok in bad:
            print(f"  {cid}: rc={rc}  {tail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
