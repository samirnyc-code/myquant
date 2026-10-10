"""fix_oct1_mislated_settlement.py — S134 incident, part 2.

6 Oct-1 0DTE iron-condor legs (eodic_p/c, openic_p/c, gx_bcs, +1) were still OPEN in the
git-reverted trades.parquet snapshot (commit 1bbb7183, frozen ~12:06 CT on 2026-10-01 —
BEFORE that night's 22:15 CT Postmortem settlement run). When the desk resumed on
2026-10-09 and Postmortem ran settle_0dte() again, it correctly found them still "open"
and cash-settled them — using the CORRECT formula (each leg priced off ITS OWN expiry
date's close, so the dollar values are right) — but stamped exit_dt as the RUN date
(2026-10-09) instead of their true expiry/settlement date (2026-10-01). That mis-dates
them on the calendar: Oct 1 shows -$1,498 (missing this +$1,242) and Oct 9 shows a phony
+$1,242 (no real Oct-9 trades exist at all).

This does NOT touch pnl/exit_cost (already correct) — only corrects exit_dt so the
calendar/analytics attribute the money to the day it actually happened.

Run:  .venv/Scripts/python.exe scripts/fix_oct1_mislated_settlement.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

TRADE_IDS = [
    "auto_20261001_083033",
    "auto_20261001_083441",
    "auto_20261001_083502",
    "auto_20261001_083706",
    "auto_20261001_083748",
    "auto_20261001_083814",
]
CORRECT_EXIT_DT = "2026-10-01 16:00"


def main():
    df = tlog.load()
    for tid in TRADE_IDS:
        row = df[df.trade_id == tid]
        if not len(row):
            print(f"  ! {tid} not found — skipping")
            continue
        before = row.iloc[0]["exit_dt"]
        tlog.annotate(tid, exit_dt=CORRECT_EXIT_DT)
        df = tlog.load()  # reload to report the real post-write state
        after = df[df.trade_id == tid].iloc[0]["exit_dt"]
        print(f"  {tid}: exit_dt {before} -> {after}")

    print("\ndone — re-run scripts/options_dashboard.py to refresh dashboard.html")


if __name__ == "__main__":
    main()
